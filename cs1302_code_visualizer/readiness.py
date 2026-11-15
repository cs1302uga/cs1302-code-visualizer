"""Bounded render diagnostics and opt-in recovery metadata; never retries work."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Protocol, cast

from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchElementException,
    NoSuchWindowException,
    WebDriverException,
)
from selenium.webdriver.chrome.webdriver import WebDriver


@dataclass(frozen=True)
class RenderAttempt:
    """Caller-owned identities for one attempt in a shared downstream budget.

    Strings are bounded during capture. Do not put secrets in identifiers.
    ``fresh_browser`` requests a new session lease without resetting the pool.
    """

    request_id: str | None = None
    source: str | None = None
    attempt_id: str | None = None
    fresh_browser: bool = False


@dataclass(frozen=True)
class RenderDiagnostic:
    """Failure evidence; None means unknown, False/empty means observed absent."""

    request_id: str | None
    payload_sha256: str
    source: str | None
    attempt_id: str | None
    lease_id: str | None
    stage: str
    elapsed_seconds: float
    ready: bool | None
    frontend_error: str | None
    console_errors: tuple[str, ...] | None


class _DiagnosticError(Protocol):
    """Structural exception attribute used without broadening exception types."""

    render_diagnostic: RenderDiagnostic


class ReadinessTimeout(NoSuchElementException):
    """Readiness expired; compatible with the historical Selenium exception."""


class BrowserTransportError(WebDriverException):
    """A lost browser session/window; the original Selenium error is the cause."""


def render_diagnostic(error: BaseException) -> RenderDiagnostic | None:
    """Return captured evidence without changing an exception's classification."""
    result: object = getattr(error, "render_diagnostic", None)
    return result if isinstance(result, RenderDiagnostic) else None


def _bounded(value: str | None) -> str | None:
    """Bound caller strings without converting unknown to absent."""
    return value[:512] if value is not None else None


def _capture(
    driver: WebDriver,
    payload: str,
    attempt: RenderAttempt,
    stage: str,
    started: float,
    observe_markers: bool,
) -> RenderDiagnostic:
    """Collect independently optional browser evidence without masking failure."""
    ready = None
    frontend_error = None
    console = None
    if observe_markers:
        with suppress(Exception):
            markers: object = driver.execute_script(
                "return [!!document.getElementById('screenshotReadyIndicator'),"
                "document.getElementById('screenshotError')?.textContent?.slice(0,512) ?? ''];"
            )
            if isinstance(markers, list) and len(markers) == 2:
                ready = markers[0] if isinstance(markers[0], bool) else None
                frontend_error = markers[1] if isinstance(markers[1], str) else None
    with suppress(Exception):
        console = tuple(
            str(entry.get("message", ""))[:512]
            for entry in driver.get_log("browser")
            if entry.get("level") == "SEVERE"
        )[-8:]
    lease: object = driver.session_id
    return RenderDiagnostic(
        _bounded(attempt.request_id),
        hashlib.sha256(payload.encode()).hexdigest(),
        _bounded(attempt.source),
        _bounded(attempt.attempt_id),
        _bounded(lease) if isinstance(lease, str) else None,
        stage,
        time.monotonic() - started,
        ready,
        frontend_error,
        console,
    )


@contextmanager
def diagnostic_scope(
    driver: WebDriver,
    payload: str,
    attempt: RenderAttempt | None,
    stage: str,
    *,
    observe_markers: bool = True,
) -> Generator[None]:
    """Annotate failures once, classifying only concrete lost-session errors.

    Cancellation propagates untouched. Diagnostic collection is best effort;
    even an unexpected diagnostic failure preserves the original exception.
    Disable marker observation until the current document belongs to the payload.
    """
    started = time.monotonic()
    try:
        yield
    except Exception as original:
        error = original
        if isinstance(original, (InvalidSessionIdException, NoSuchWindowException)):
            error = BrowserTransportError(str(original))
        if render_diagnostic(original) is None:
            diagnosed = False
            with suppress(Exception):
                evidence = _capture(
                    driver, payload, attempt or RenderAttempt(), stage, started, observe_markers
                )
                cast(_DiagnosticError, error).render_diagnostic = evidence
                diagnosed = True
            if not diagnosed:
                raise
        if error is not original:
            raise error from original
        raise
