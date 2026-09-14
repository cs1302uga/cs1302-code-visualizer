"""Build-scoped browser reuse and optional persistent execution-trace caching."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from . import trace_generator

_TRACE_SIGNATURE = inspect.signature(trace_generator.generate_trace)


class RenderingSession:
    """Own at most ``max_browsers`` Chrome instances until the session is closed.

    Requests lease browsers exclusively. A failed request discards its browser;
    different DPI settings never share the same instance. ``cache_dir`` enables
    persistent traces; without it, traces are reused only within this session.
    """

    def __init__(self, max_browsers: int = 2, cache_dir: Path | None = None):
        """Create a lazy session; no browser or Java process starts here."""
        if max_browsers < 1:
            raise ValueError("max_browsers must be positive")
        self.max_browsers = max_browsers
        self.cache_dir = cache_dir
        self._condition = threading.Condition()
        self._idle: list[tuple[int, Any]] = []
        self._active = 0
        self._closed = False
        self._trace_locks: dict[str, threading.Lock] = {}
        self._traces: dict[str, str] = {}

    def __enter__(self):
        """Return this session for explicit ownership in a with statement."""
        return self

    def __exit__(self, *exc):
        """Close all browsers even when the build fails."""
        self.close()

    @staticmethod
    def _quit(driver):
        """Attempt cleanup without masking an earlier rendering failure."""
        try:
            driver.quit()
        except Exception:
            logging.getLogger(__name__).warning("Failed to close render browser", exc_info=True)

    def close(self) -> None:
        """Close idle browsers; active leases close when returned."""
        with self._condition:
            self._closed = True
            idle, self._idle = self._idle, []
            self._condition.notify_all()
        for _, driver in idle:
            self._quit(driver)

    @contextmanager
    def browser(self, dpi: int, factory):
        """Lease an exclusive browser, replacing incompatible or failed instances."""
        driver = None
        with self._condition:
            while not self._closed and self._active >= self.max_browsers:
                self._condition.wait()
            if self._closed:
                raise RuntimeError("Rendering session is closed")
            for index, (scale, candidate) in enumerate(self._idle):
                if scale == dpi:
                    driver = candidate
                    self._idle.pop(index)
                    break
            if driver is None and self._idle and self._active + len(self._idle) >= self.max_browsers:
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
                        self._idle.append((dpi, driver))
                    else:
                        self._quit(driver)
                self._condition.notify_all()

    def generate_trace(self, *args, **kwargs) -> str:
        """Cache normalized traces by all execution arguments and tracer identity."""
        bound = _TRACE_SIGNATURE.bind(*args, **kwargs)
        bound.apply_defaults()
        values = dict(bound.arguments)
        values["java_home"] = str(values["java_home"])
        release = Path(values["java_home"]) / "release"
        values["jdk_release"] = release.read_text() if release.is_file() else None
        values["breakpoints"] = sorted(values["breakpoints"])
        values["tracer"] = trace_generator.read_tracer_url_and_sum_from_toml()
        values["schema"] = 1
        if values.get("stdin_file") is not None:
            file_path = Path(values["stdin_file"])
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
            trace_generator.ensure_code_tracer_installed()
            trace = trace_generator.generate_trace(*args, **kwargs)
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


def prune_trace_cache(cache_dir: Path, max_age_days: float = 30, dry_run: bool = False) -> tuple[int, int]:
    """Remove trace files unused for the specified age, returning file and byte counts."""
    import time

    if max_age_days < 0:
        raise ValueError("max_age_days must be nonnegative")
    threshold = time.time() - max_age_days * 86400
    count = size = 0
    for path in cache_dir.glob("*.json"):
        try:
            stat = path.stat()
            if stat.st_mtime >= threshold:
                continue
            if not dry_run:
                path.unlink()
            count += 1
            size += stat.st_size
        except FileNotFoundError:
            continue
    return count, size
