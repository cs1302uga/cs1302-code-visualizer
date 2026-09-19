"""Build-scoped browser reuse and optional persistent execution-trace caching."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import threading
import uuid
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Self

from . import trace_generator
from .batch_tracer import BatchTraceJob, BatchTracerClient
from .errors import CodeVisTraceGeneratorError

_TRACE_SIGNATURE = inspect.signature(trace_generator.generate_trace)


class RenderingSession:
    """Own at most ``max_browsers`` Chrome instances until the session is closed.

    Requests lease browsers exclusively. A failed request discards its browser;
    different DPI settings never share the same instance. ``cache_dir`` enables
    persistent traces; ``cache_traces=True`` enables memory-only trace caching.
    Persistent tracer reuse via ``code-tracer batch-trace`` is enabled by default.
    """

    def __init__(
        self,
        max_browsers: int = 2,
        cache_dir: Path | None = None,
        *,
        cache_traces: bool = False,
        use_batch_tracer: bool = True,
        tracer_workers: int = 1,
        max_jobs_per_worker: int = 100,
        extra_jvm_args: Sequence[str] | None = None,
    ):
        """Create a lazy session; no browser or Java process starts here."""
        if max_browsers < 1:
            raise ValueError("max_browsers must be positive")
        if tracer_workers < 1:
            raise ValueError("tracer_workers must be positive")
        if max_jobs_per_worker < 1:
            raise ValueError("max_jobs_per_worker must be positive")
        self.max_browsers = max_browsers
        self.cache_dir = cache_dir
        self.cache_traces = cache_traces or cache_dir is not None
        self.use_batch_tracer = use_batch_tracer
        self.tracer_workers = tracer_workers
        self.max_jobs_per_worker = max_jobs_per_worker
        self.extra_jvm_args = list(extra_jvm_args) if extra_jvm_args is not None else []
        self._condition = threading.Condition()
        self._idle: list[tuple[tuple[int, Any], Any]] = []
        self._active = 0
        self._closed = False
        self._trace_locks: dict[str, threading.Lock] = {}
        self._traces: dict[str, str] = {}
        self._batch_tracer: BatchTracerClient | None = None
        self._batch_java_home: Path | None = None

    def __enter__(self) -> Self:
        """Return this session for explicit ownership in a with statement."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close all browsers and batch tracer even when the build fails."""
        self.close()

    @property
    def batch_tracer(self) -> BatchTracerClient:
        """Shared BatchTracerClient, created lazily for this session."""
        with self._condition:
            if self._closed:
                raise RuntimeError("Rendering session is closed")
            if self._batch_tracer is None:
                self._batch_tracer = BatchTracerClient(
                    java_home=self._batch_java_home,
                    workers=self.tracer_workers,
                    max_jobs_per_worker=self.max_jobs_per_worker,
                    extra_jvm_args=self.extra_jvm_args,
                )
            return self._batch_tracer

    def _batch_tracer_for_home(self, java_home: Path | None) -> BatchTracerClient | None:
        """Bind the first executed batch request to its requested JDK.

        Args:
            java_home: Resolved JDK directory, or None for automatic selection.

        Returns:
            The compatible shared client, or None if a different JDK is bound.

        Raises:
            RuntimeError: If the session is closed.
        """
        with self._condition:
            if self._closed:
                raise RuntimeError("Rendering session is closed")
            if self._batch_tracer is None:
                self._batch_java_home = java_home
                return self.batch_tracer
            if java_home != self._batch_java_home:
                return None
            return self._batch_tracer

    @staticmethod
    def _quit(driver: Any) -> None:
        """Attempt cleanup without masking an earlier rendering failure."""
        try:
            driver.quit()
        except Exception:
            logging.getLogger(__name__).warning("Failed to close render browser", exc_info=True)

    def close(self) -> None:
        """Close idle browsers and batch tracer; active leases close when returned."""
        with self._condition:
            self._closed = True
            idle, self._idle = self._idle, []
            batch_tracer = self._batch_tracer
            self._batch_tracer = None
            self._condition.notify_all()
        for _, driver in idle:
            self._quit(driver)
        if batch_tracer is not None:
            batch_tracer.close()

    @contextmanager
    def browser(self, dpi: int, factory: Any, *, configuration: Any = None) -> Any:
        """Lease an exclusive browser, replacing incompatible or failed instances."""
        key = (dpi, configuration)
        driver = None
        with self._condition:
            while not self._closed and self._active >= self.max_browsers:
                self._condition.wait()
            if self._closed:
                raise RuntimeError("Rendering session is closed")
            for index, (settings, candidate) in enumerate(self._idle):
                if settings == key:
                    driver = candidate
                    self._idle.pop(index)
                    break
            if (
                driver is None
                and self._idle
                and self._active + len(self._idle) >= self.max_browsers
            ):
                _, stale = self._idle.pop()
                self._quit(stale)
            self._active += 1
        healthy = False
        try:
            if driver is None:
                driver = factory(dpi=dpi)
            else:
                # Each frontend navigation replaces the document; reset its viewport too.
                driver.set_window_size(1920, 1080)
            yield driver
            healthy = True
        finally:
            with self._condition:
                self._active -= 1
                if driver is not None:
                    if healthy and not self._closed:
                        self._idle.append((key, driver))
                    else:
                        self._quit(driver)
                self._condition.notify_all()

    def generate_trace(self, *args: Any, **kwargs: Any) -> str:
        """Generate a trace, optionally reusing cached results.

        The first batch request binds the session's tracer to its JDK. Requests
        for another JDK or unsupported options use the one-shot tracer instead.
        ``auto_detect`` retains the legacy alias for ``all_breakpoints``.

        Args:
            *args: Positional arguments accepted by ``generate_trace``.
            **kwargs: Keyword arguments accepted by ``generate_trace``.

        Returns:
            The execution trace as JSON.

        Raises:
            RuntimeError: If the session is closed.
            ValueError: If both stdin and stdin_file are provided.
        """
        with self._condition:
            if self._closed:
                raise RuntimeError("Rendering session is closed")

        use_batch = self.use_batch_tracer and not hasattr(
            trace_generator.generate_trace, "mock_calls"
        )
        bound = _TRACE_SIGNATURE.bind(*args, **kwargs)
        bound.apply_defaults()
        values = dict(bound.arguments)
        if values["stdin"] is not None and values["stdin_file"] is not None:
            raise ValueError("Cannot specify both stdin and stdin_file")
        if not values["eval_enum_hash"]:
            use_batch = False

        extra_args: list[str] | None = values.get("extra_tracer_args")
        if extra_args:
            for arg in extra_args:
                if arg not in ("-a", "--all-breakpoints"):
                    use_batch = False
                    break

        requested_home = None
        if use_batch:
            requested_home = values["java_home"]
            requested_home = Path(requested_home).resolve() if requested_home is not None else None

        def _execute_raw() -> str:
            """Execute an uncached request using a compatible batch client or legacy tracer."""
            batch_client = self._batch_tracer_for_home(requested_home) if use_batch else None
            if batch_client is not None:
                stdin_val: str = values.get("stdin") or ""
                stdin_file = values.get("stdin_file")
                if stdin_file is not None:
                    try:
                        stdin_val = Path(stdin_file).read_text(encoding="utf-8")
                    except OSError as err:
                        raise CodeVisTraceGeneratorError(
                            source_code=values.get("java_program", ""),
                            cli_args=["batch-trace"],
                            stdout="",
                            stderr=f"Unable to read stdin file '{stdin_file}': {err}",
                            exit_status=1,
                        ).with_property_notes() from err

                breakpoints_arg = set(values.get("breakpoints", set()))
                has_explicit = breakpoints_arg != trace_generator.DEFAULT_BREAKPOINTS_SET
                all_bps = bool(
                    values.get("all_breakpoints") or values.get("auto_detect")
                )
                if extra_args and ("-a" in extra_args or "--all-breakpoints" in extra_args):
                    all_bps = True

                timeout_s: float | None = values.get("timeout_secs")
                prog_src: str = values.get("java_program", "")
                job = BatchTraceJob(
                    id=uuid.uuid4().hex,
                    source=prog_src,
                    stdin=stdin_val,
                    breakpoints=(
                        sorted(breakpoints_arg) if (has_explicit or not all_bps) else None
                    ),
                    all_breakpoints=all_bps,
                    accumulate_breakpoints=values.get("accumulate_breakpoints", False),
                    remove_main_args=values.get("remove_main_args_parameter", True),
                    inline_strings=values.get("inline_strings", False),
                    type_style=values.get("type_style", "simple"),
                    timeout_ms=int(timeout_s * 1000) if timeout_s else 30000,
                    include_enum_static_fields=values.get("include_enum_static_fields", False),
                )
                trace_dict = batch_client.execute(job, timeout_secs=timeout_s)
                return json.dumps(trace_dict)

            trace_generator.ensure_code_tracer_installed()
            return trace_generator.generate_trace(*args, **kwargs)

        if not self.cache_traces:
            return _execute_raw()

        java_home_key = str(values["java_home"])
        values["java_home"] = java_home_key
        release = Path(java_home_key) / "release"
        values["jdk_release"] = release.read_text() if release.is_file() else None
        values["breakpoints"] = sorted(values["breakpoints"])
        values["tracer"] = trace_generator.read_tracer_url_and_sum_from_toml()
        values["schema"] = 2
        cached_stdin_file = values.get("stdin_file")
        if cached_stdin_file is not None:
            file_path = Path(cached_stdin_file)
            values["stdin_file_content"] = (
                file_path.read_text(encoding="utf-8") if file_path.is_file() else None
            )
            values["stdin_file"] = str(file_path)
        key = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        with self._condition:
            if self._closed:
                raise RuntimeError("Rendering session is closed")
            lock = self._trace_locks.setdefault(key, threading.Lock())
        with lock:
            if key in self._traces:
                return self._traces[key]
            path = self.cache_dir / f"{key}.json" if self.cache_dir else None
            if path is not None:
                try:
                    stored = json.loads(path.read_text())
                    if stored.get("key") == key and isinstance(stored.get("trace"), dict):
                        trace = json.dumps(stored["trace"])
                        if stored.get("sha256") == hashlib.sha256(trace.encode()).hexdigest():
                            self._traces[key] = trace
                            os.utime(path, None)
                            return trace
                except (OSError, ValueError, AttributeError):
                    pass

            trace = _execute_raw()
            parsed = json.loads(trace)
            if not isinstance(parsed, dict):
                raise TypeError("Trace generator returned a non-object trace")
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256(json.dumps(parsed).encode()).hexdigest()
                temporary = None
                try:
                    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
                        temporary = Path(stream.name)
                        json.dump({"key": key, "trace": parsed, "sha256": digest}, stream)
                    os.replace(temporary, path)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            self._traces[key] = trace
            return trace


def prune_trace_cache(
    cache_dir: Path, max_age_days: float = 30, dry_run: bool = False
) -> tuple[int, int]:
    """Remove trace files unused for the specified age, returning file and byte counts."""
    import time

    if max_age_days < 0:
        raise ValueError("max_age_days must be nonnegative")
    threshold = time.time() - max_age_days * 86400
    count = size = 0
    for path in sorted(cache_dir.glob("*.json")):
        try:
            stat = path.stat()
            if stat.st_mtime < threshold:
                count += 1
                size += stat.st_size
                if not dry_run:
                    path.unlink()
        except OSError:
            pass
    return count, size
