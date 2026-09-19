"""Client and job model for code-tracer batch-trace daemon mode.

Normative References:
    PEP 257 – Docstring Conventions (https://peps.python.org/pep-0257/)
    PEP 484 – Type Hints (https://peps.python.org/pep-0484/)
"""

from __future__ import annotations

import atexit
import concurrent.futures
import dataclasses
import json
import logging
import os
import signal
import subprocess
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from .errors import CodeVisTraceGeneratorError
from .trace_generator import (
    CACHE_DIR,
    delete_globals,
    ensure_code_tracer_installed,
    ensure_jdk_installed,
    get_enum_globals,
    get_enum_types,
    get_sanitized_java_env,
    normalize_heap_primitives,
)

logger: logging.Logger = logging.getLogger(__name__)


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    """Safely terminate a subprocess and all processes in its process group."""
    if proc.stdin is not None:
        try:
            proc.stdin.close()
        except OSError:
            logger.debug("Failed to close batch tracer stdin", exc_info=True)

    pgid: int | None = None
    if (
        hasattr(os, "getpgid")
        and hasattr(os, "killpg")
        and isinstance(getattr(proc, "pid", None), int)
    ):
        try:
            pgid = os.getpgid(proc.pid)
        except OSError:
            pgid = None

    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except OSError:
            logger.debug("Failed to send SIGTERM to process group %d", pgid, exc_info=True)

    try:
        proc.terminate()
    except OSError:
        logger.debug("Failed to terminate batch tracer process", exc_info=True)

    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                logger.debug("Failed to send SIGKILL to process group %d", pgid, exc_info=True)
        try:
            proc.kill()
            proc.wait(timeout=1)
        except (subprocess.TimeoutExpired, OSError):
            logger.debug("Failed to kill batch tracer process", exc_info=True)
    except OSError:
        logger.debug("Failed waiting for batch tracer process termination", exc_info=True)


@dataclass(frozen=True)
class BatchTraceJob:
    """A trace job configuration submitted to code-tracer batch-trace."""

    source: str
    id: str = ""
    format: str = "pytutor"
    stdin: str = ""
    breakpoints: Sequence[str | int] | None = None
    all_breakpoints: bool = True
    accumulate_breakpoints: bool = False
    remove_main_args: bool = True
    inline_strings: bool = False
    remove_method_this: bool = False
    type_style: str = "simple"
    timeout_ms: int = 30000
    max_snapshots: int = 1000
    inspection: str = "TRUSTED"
    include_enum_static_fields: bool = False

    def to_request_dict(self) -> dict[str, Any]:
        """Convert this job into a dictionary matching code-tracer BatchJobRequest."""
        req: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "format": self.format,
            "stdin": self.stdin,
            "allBreakpoints": self.all_breakpoints,
            "accumulateBreakpoints": self.accumulate_breakpoints,
            "removeMainArgs": self.remove_main_args,
            "inlineStrings": self.inline_strings,
            "removeMethodThis": self.remove_method_this,
            "typeStyle": self.type_style,
            "inspection": self.inspection,
        }
        if self.breakpoints is not None:
            req["breakpoints"] = [str(b) for b in self.breakpoints]

        limits: dict[str, Any] = {}
        if self.timeout_ms:
            limits["timeoutMillis"] = self.timeout_ms
        if self.max_snapshots:
            limits["snapshots"] = self.max_snapshots
        if limits:
            req["limits"] = limits

        return req


class BatchTracerClient:
    """Manages a persistent code-tracer batch-trace subprocess with multiplexed I/O."""

    def __init__(
        self,
        java_home: Path | None = None,
        *,
        workers: int = 1,
        max_jobs_per_worker: int = 100,
        extra_jvm_args: Sequence[str] | None = None,
    ) -> None:
        """Initialize the batch tracer client.

        Args:
            java_home: Path to JDK home. If None, installed automatically.
            workers: Number of persistent guest worker sessions in code-tracer.
            max_jobs_per_worker: Maximum jobs per worker session before recycling.
            extra_jvm_args: Extra command-line arguments to pass to the JVM.
        """
        if workers < 1:
            raise ValueError("workers must be positive")
        if max_jobs_per_worker < 1:
            raise ValueError("max_jobs_per_worker must be positive")

        self.java_home = java_home
        self.workers = workers
        self.max_jobs_per_worker = max_jobs_per_worker
        self.extra_jvm_args = list(extra_jvm_args) if extra_jvm_args is not None else []

        self._lock = threading.RLock()
        self._stdin_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_drainer: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._pending: dict[
            str, tuple[concurrent.futures.Future[dict[str, Any]], BatchTraceJob]
        ] = {}
        self._closed = False
        atexit.register(self.close)

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Context manager exit."""
        self.close()

    def __del__(self) -> None:
        """Cleanup tracer process when garbage collected."""
        try:
            self.close()
        except OSError:
            logger.debug("Failed to close batch tracer on garbage collection", exc_info=True)

    def _ensure_process(self) -> subprocess.Popen[str]:
        """Ensure the batch-trace subprocess is started and running."""
        with self._lock:
            if self._closed:
                raise RuntimeError("BatchTracerClient is closed")
            if self._process is not None:
                if self._process.poll() is None:
                    return self._process
                _terminate_process_tree(self._process)
                self._process = None

            # Reset state for new process
            self._stderr_lines.clear()
            resolved_java_home = (
                self.java_home if self.java_home is not None else ensure_jdk_installed()
            )
            ensure_code_tracer_installed()

            cmd: list[str] = [
                str(resolved_java_home / "bin" / "java"),
                "-Djava.awt.headless=true",
                "--enable-native-access=ALL-UNNAMED",
            ]
            cmd.extend(self.extra_jvm_args)
            cmd.extend([
                "-jar",
                str(CACHE_DIR / "code-tracer.jar"),
                "batch-trace",
                f"-w={self.workers}",
                f"--max-jobs-per-worker={self.max_jobs_per_worker}",
            ])

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=get_sanitized_java_env(),
                start_new_session=True,
            )
            self._process = proc

            reader = threading.Thread(
                target=self._reader_loop,
                args=(proc,),
                daemon=True,
                name="BatchTracer-StdoutReader",
            )
            self._reader_thread = reader
            reader.start()

            drainer = threading.Thread(
                target=self._drain_stderr,
                args=(proc,),
                daemon=True,
                name="BatchTracer-StderrDrainer",
            )
            self._stderr_drainer = drainer
            drainer.start()

            return proc

    def _drain_stderr(self, proc: subprocess.Popen[str]) -> None:
        """Drain stderr from the tracer subprocess."""
        if proc.stderr is None:
            return
        for line in iter(proc.stderr.readline, ""):
            line_str = line.strip()
            if line_str:
                logger.debug("code-tracer batch stderr: %s", line_str)
                with self._lock:
                    self._stderr_lines.append(line_str)
        proc.stderr.close()

    def _reader_loop(self, proc: subprocess.Popen[str]) -> None:
        """Read NDJSON responses from stdout and resolve corresponding Futures."""
        if proc.stdout is None:
            return

        for line in iter(proc.stdout.readline, ""):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                resp: dict[str, Any] = json.loads(stripped)
            except json.JSONDecodeError as jde:
                logger.warning("Failed to decode NDJSON line from tracer: %s", jde)
                continue

            job_id: str | None = resp.get("id")
            if not job_id:
                continue

            with self._lock:
                entry = self._pending.pop(job_id, None)

            if entry is None:
                continue

            future, job = entry
            self._handle_response(future, job, resp)

        # EOF reached on stdout (worker died or closed)
        with self._lock:
            orphans = list(self._pending.values())
            self._pending.clear()
            if self._process is proc:
                self._process = None

            if orphans and not self._closed:
                stderr_text = "\n".join(self._stderr_lines)
                exit_status = proc.poll()
                for future, job in orphans:
                    if not future.done():
                        err = CodeVisTraceGeneratorError(
                            source_code=job.source,
                            cli_args=["batch-trace"],
                            stdout="",
                            stderr=stderr_text or "Tracer batch worker terminated unexpectedly.",
                            exit_status=exit_status if exit_status is not None else -1,
                        ).with_property_notes()
                        future.set_exception(err)

    def _handle_response(
        self,
        future: concurrent.futures.Future[dict[str, Any]],
        job: BatchTraceJob,
        resp: dict[str, Any],
    ) -> None:
        """Process a single BatchJobResponse and resolve or reject the future."""
        result = resp.get("result", {})
        status = result.get("status")

        if status != "completed":
            diagnostics = result.get("diagnostics", [])
            phase = result.get("phase", "unknown")
            diag_text = (
                "\n".join(str(d) for d in diagnostics)
                if diagnostics
                else f"Batch trace job failed during phase: {phase}"
            )
            err = CodeVisTraceGeneratorError(
                source_code=job.source,
                cli_args=["batch-trace"],
                stdout=result.get("stdout", ""),
                stderr=diag_text,
                exit_status=1,
            ).with_property_notes()
            future.set_exception(err)
            return

        trace_obj = result.get("trace")
        if not isinstance(trace_obj, dict):
            future.set_exception(
                TypeError(f"Batch tracer returned unexpected trace shape: {type(trace_obj)}")
            )
            return

        # Normalize heap primitives
        if "trace" in trace_obj and isinstance(trace_obj["trace"], list):
            normalize_heap_primitives(trace_obj)

        # Cleanup enum globals if requested
        if (
            not job.include_enum_static_fields
            and "trace" in trace_obj
            and isinstance(trace_obj["trace"], list)
        ):
            enum_types = get_enum_types(trace_obj)
            enum_globals = get_enum_globals(trace_obj, enum_types)
            delete_globals(trace_obj, enum_globals)

        future.set_result(trace_obj)

    def submit(self, job: BatchTraceJob) -> concurrent.futures.Future[dict[str, Any]]:
        """Submit a trace job asynchronously.

        Args:
            job: The BatchTraceJob to execute.

        Returns:
            A Future resolving to the trace dictionary.
        """
        with self._lock:
            if not job.id:
                job = dataclasses.replace(job, id=uuid.uuid4().hex)
            if self._closed:
                raise RuntimeError("BatchTracerClient is closed")
            proc = self._ensure_process()
            future: concurrent.futures.Future[dict[str, Any]] = concurrent.futures.Future()
            self._pending[job.id] = (future, job)

        req_json = json.dumps(job.to_request_dict()) + "\n"
        with self._stdin_lock:
            try:
                if proc.stdin is None or proc.stdin.closed:
                    raise OSError("Batch tracer stdin is unavailable")
                proc.stdin.write(req_json)
                proc.stdin.flush()
            except OSError as err:
                with self._lock:
                    self._pending.pop(job.id, None)
                gen_err = CodeVisTraceGeneratorError(
                    source_code=job.source,
                    cli_args=["batch-trace"],
                    stdout="",
                    stderr=f"Failed to write job to batch tracer stdin: {err}",
                    exit_status=1,
                ).with_property_notes()
                future.set_exception(gen_err)
                return future

        return future

    def execute(
        self,
        job: BatchTraceJob,
        *,
        timeout_secs: float | None = None,
    ) -> dict[str, Any]:
        """Submit a job and block until the result is available.

        Args:
            job: The BatchTraceJob to execute.
            timeout_secs: Max seconds to wait for result.

        Returns:
            The trace dictionary.
        """
        future = self.submit(job)
        return future.result(timeout=timeout_secs)

    def close(self) -> None:
        """Terminate the tracer worker process and cancel outstanding requests."""
        atexit.unregister(self.close)
        with self._lock:
            if self._closed:
                return
            self._closed = True

            proc = self._process
            self._process = None

            # Cancel remaining futures
            orphans = list(self._pending.values())
            self._pending.clear()
            for future, _ in orphans:
                if not future.done():
                    future.cancel()

        if proc is not None:
            _terminate_process_tree(proc)
