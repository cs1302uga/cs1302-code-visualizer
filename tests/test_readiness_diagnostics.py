"""Bounded evidence and classified recovery without hidden attempts."""

import hashlib
import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import InvalidSessionIdException, JavascriptException

from cs1302_code_visualizer import RenderingSession, browser_driver
from cs1302_code_visualizer.readiness import (
    BrowserTransportError,
    ReadinessTimeout,
    RenderAttempt,
    diagnostic_scope,
    render_diagnostic,
)


def test_bounded_diagnostics():
    driver = MagicMock(session_id="lease")
    driver.execute_script.return_value = [False, ""]
    driver.get_log.return_value = [{"level": "SEVERE", "message": "x" * 900}] * 20
    failure = ReadinessTimeout("expired")
    with (
        pytest.raises(ReadinessTimeout) as caught,
        diagnostic_scope(
            driver, "payload", RenderAttempt("r" * 900, "page:10", "a"), "initial-readiness"
        ),
    ):
        raise failure
    assert caught.value is failure
    evidence = render_diagnostic(failure)
    assert evidence.request_id == "r" * 512
    assert evidence.source == "page:10" and evidence.attempt_id == "a"
    assert evidence.lease_id == "lease" and evidence.elapsed_seconds >= 0
    assert len(evidence.payload_sha256) == 64
    assert evidence.ready is False and evidence.frontend_error == ""
    assert evidence.console_errors == ("x" * 512,) * 8


@pytest.mark.parametrize("markers", [None, [1, 2], [True, "error"]])
def test_optional_evidence(markers):
    driver = MagicMock(session_id=None)
    driver.execute_script.return_value = markers
    driver.get_log.return_value = [{"level": "INFO", "message": "ignored"}]
    with pytest.raises(ValueError) as caught, diagnostic_scope(driver, "p", None, "export"):
        raise ValueError("explicit")
    evidence = render_diagnostic(caught.value)
    assert evidence.lease_id is None
    assert evidence.console_errors == ()
    assert evidence.ready == (True if markers == [True, "error"] else None)


@pytest.mark.parametrize("severe_count", [1, 12])
def test_severe_console_tail_survives_warning_noise(severe_count):
    driver = MagicMock()
    messages = [f"failure {index}" for index in range(severe_count)]
    driver.get_log.return_value = [
        {"level": "SEVERE", "message": message} for message in messages
    ] + [{"level": "WARNING", "message": "noise"}] * 9
    with pytest.raises(ReadinessTimeout) as caught, diagnostic_scope(driver, "p", None, "render"):
        raise ReadinessTimeout("expired")
    evidence = render_diagnostic(caught.value)
    assert evidence is not None
    assert evidence.console_errors == tuple(messages[-8:])


def test_replacement_preparation_identifies_next_payload_without_previous_markers():
    driver = MagicMock(session_id="lease")
    driver.execute_script.return_value = [True, "previous document"]
    payloads = [json.dumps({"code": name, "trace": []}) for name in ("first", "second")]
    attempt = RenderAttempt("batch", "lesson:2", "attempt-1")
    failure = InvalidSessionIdException("lost preparing replacement")

    @contextmanager
    def frontend(trace, **_kwargs):
        with diagnostic_scope(driver, trace, attempt, "render"):
            yield {"driver": driver, "dataViz": MagicMock()}

    with (
        patch.object(browser_driver, "online_python_tutor_frontend", frontend),
        patch.object(browser_driver, "_capture_viz", return_value=b"first") as capture,
        patch.object(browser_driver, "_prepare_session_viewport", side_effect=failure),
        pytest.raises(BrowserTransportError) as caught,
    ):
        browser_driver.generate_snapshot_images(payloads, attempt=attempt)
    assert caught.value.__cause__ is failure
    evidence = render_diagnostic(caught.value)
    assert evidence is not None
    assert evidence.payload_sha256 == hashlib.sha256(payloads[1].encode()).hexdigest()
    assert evidence.stage == "snapshot-preparation"
    assert evidence.request_id == "batch" and evidence.attempt_id == "attempt-1"
    assert evidence.ready is None and evidence.frontend_error is None
    capture.assert_called_once()
    driver.execute_script.assert_not_called()


@pytest.mark.parametrize("phase", ["entry", "switch", "cleanup"])
def test_snapshot_host_markers_are_not_attributed_to_replacement(phase):
    driver = MagicMock(session_id="lease")
    driver.execute_script.return_value = [True, "host marker"]
    failure = InvalidSessionIdException(f"lost during {phase}")
    if phase == "entry":
        driver.execute_script.side_effect = [failure, [True, "host marker"]]
    elif phase == "switch":
        driver.switch_to.frame.side_effect = failure
    else:
        driver.switch_to.default_content.side_effect = failure
    with (
        patch.object(browser_driver, "_wait_for_screenshot_ready"),
        pytest.raises(BrowserTransportError) as caught,
        browser_driver._snapshot_frame(driver, "replacement", "file:///render.html"),
    ):
        assert phase == "cleanup"
    evidence = render_diagnostic(caught.value)
    assert evidence is not None
    assert caught.value.__cause__ is failure
    assert evidence.payload_sha256 == hashlib.sha256(b"replacement").hexdigest()
    assert evidence.ready is None and evidence.frontend_error is None
    assert not any(
        "screenshotReadyIndicator" in str(call.args[0])
        for call in driver.execute_script.call_args_list
    )


def test_diagnostic_failure_preserves_original():
    driver = MagicMock()
    driver.execute_script.side_effect = RuntimeError("diagnosis")
    driver.get_log.side_effect = RuntimeError("console")
    with pytest.raises(ValueError) as caught, diagnostic_scope(driver, "p", None, "render"):
        raise ValueError("original")
    assert render_diagnostic(caught.value).console_errors is None
    original = InvalidSessionIdException("lost")
    with (
        patch("cs1302_code_visualizer.readiness._capture", side_effect=RuntimeError),
        pytest.raises(InvalidSessionIdException) as caught,
        diagnostic_scope(driver, "p", None, "render"),
    ):
        raise original
    assert caught.value is original


def test_nesting_preserves_specific_evidence():
    driver = MagicMock()
    with (
        pytest.raises(ValueError) as caught,
        diagnostic_scope(driver, "outer", None, "outer"),
        diagnostic_scope(driver, "inner", None, "inner"),
    ):
        raise ValueError("layout")
    assert render_diagnostic(caught.value).stage == "inner"


@pytest.mark.parametrize(
    "failure", [KeyboardInterrupt(), JavascriptException("bad script"), OSError("disk")]
)
def test_nonretryable_and_cancellation(failure):
    with pytest.raises(type(failure)) as caught, diagnostic_scope(MagicMock(), "p", None, "render"):
        raise failure
    assert caught.value is failure


def test_real_browser_transport_and_expiry():
    driver = browser_driver.get_webdriver()
    try:
        driver.get("about:blank")
        with (
            pytest.raises(ReadinessTimeout) as caught,
            diagnostic_scope(driver, "{}", RenderAttempt("image"), "readiness"),
        ):
            browser_driver._wait_for_screenshot_ready(driver)
        assert render_diagnostic(caught.value).ready is False
        driver.quit()
        with (
            pytest.raises(BrowserTransportError) as caught,
            diagnostic_scope(driver, "{}", None, "readiness"),
        ):
            raise InvalidSessionIdException("closed session")
        assert isinstance(caught.value.__cause__, InvalidSessionIdException)
    finally:
        driver.quit()


def test_fresh_lease_keeps_unrelated_active_browser():
    factory = MagicMock(side_effect=lambda **kw: MagicMock())
    with RenderingSession(max_browsers=2) as session:
        with session.browser(1, factory) as active:
            with session.browser(1, factory) as idle:
                pass
            with session.browser(1, factory, fresh=True) as fresh:
                assert fresh is not idle and fresh is not active
                idle.quit.assert_called_once()
                active.quit.assert_not_called()
                assert session._active == 2
        assert factory.call_count == 3
    active.quit.assert_called_once()
    fresh.quit.assert_called_once()


@pytest.mark.parametrize("mode", ["initial", "delayed", "snapshot"])
def test_real_frontend_failure_marker(mode):
    import json
    from pathlib import Path

    payload = Path("small-trace-examples/example0/Driver.java.json").read_text()
    # Freeze one legacy payload; no tracing is involved.
    resolved = json.dumps(browser_driver.resolve_trace_payload(payload))
    driver = browser_driver.get_webdriver()
    script = """
        const schedule = window.setTimeout.bind(window);
        const create = document.createElement.bind(document);
        let failing = false;
        window.setTimeout = (callback, delay, ...args) => schedule(() => {
            failing = delay === 50;
            try { callback(...args); } finally { failing = false; }
        }, delay);
        document.createElement = (...args) => {
            if (failing) throw new Error('controlled delayed readiness failure');
            return create(...args);
        };
    """
    if mode == "initial":
        script = "window.fetch = () => Promise.reject(new Error('controlled initial failure'));"
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})
        if mode == "snapshot":
            driver.get(
                (Path(browser_driver.this_files_dir) / "frontend/render-trace.html").as_uri()
            )
            with (
                pytest.raises(ValueError, match="controlled delayed"),
                browser_driver._snapshot_frame(driver, resolved, driver.current_url),
            ):
                pytest.fail("failed readiness must not yield an exportable visualization")
        else:
            with (
                patch.object(browser_driver, "get_webdriver", return_value=driver),
                pytest.raises(ValueError, match="controlled"),
                browser_driver.online_python_tutor_frontend(resolved),
            ):
                pytest.fail("failed readiness must not yield an exportable visualization")
    finally:
        driver.quit()


def test_parallel_fresh_failures_wake_waiting_consumers():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    lock = threading.Lock()
    alive = peak = 0

    def factory(**kwargs):
        nonlocal alive, peak
        with lock:
            alive += 1
            peak = max(peak, alive)

        def quit():
            nonlocal alive
            with lock:
                alive -= 1

        return MagicMock(quit=quit)

    with RenderingSession(max_browsers=2) as session, ThreadPoolExecutor(max_workers=6) as workers:

        def fail(index):
            with pytest.raises(ReadinessTimeout), session.browser(1, factory, fresh=True):
                raise ReadinessTimeout(str(index))

        list(workers.map(fail, range(12)))
        with session.browser(1, factory, fresh=True):
            assert alive == 1
    assert alive == 0 and peak <= 2


def test_real_lost_window_is_classified():
    driver = browser_driver.get_webdriver()
    try:
        driver.get("about:blank")
        driver.close()
        with (
            pytest.raises(BrowserTransportError),
            diagnostic_scope(driver, "{}", None, "readiness"),
        ):
            browser_driver._wait_for_screenshot_ready(driver)
    finally:
        driver.quit()


@pytest.mark.parametrize("active", [False, True])
def test_standalone_cleanup_never_masks_original(active):
    driver = MagicMock()
    driver.quit.side_effect = OSError("cleanup")
    with patch.object(browser_driver, "get_webdriver", return_value=driver):
        if active:
            with (
                pytest.raises(ValueError, match="original"),
                browser_driver._browser_scope(1, None),
            ):
                raise ValueError("original")
        else:
            with pytest.raises(OSError, match="cleanup"), browser_driver._browser_scope(1, None):
                pass


@pytest.mark.parametrize("active", [False, True])
def test_snapshot_cleanup_never_masks_original(active):
    from selenium.webdriver.remote.webelement import WebElement

    driver = MagicMock()
    driver.timeouts.script = 30
    driver.execute_async_script.return_value = MagicMock(spec=WebElement)
    driver.switch_to.default_content.side_effect = OSError("cleanup")
    if active:
        with (
            pytest.raises(ValueError, match="original"),
            browser_driver._snapshot_frame(driver, "{}", "file:///render.html"),
        ):
            raise ValueError("original")
    else:
        with (
            pytest.raises(OSError, match="cleanup"),
            browser_driver._snapshot_frame(driver, "{}", "file:///render.html"),
        ):
            pass


def test_attempt_forwarding_for_text_steps():
    attempt = RenderAttempt("image", "page:1", "attempt", True)
    with patch.object(browser_driver, "generate_image", return_value=b"image") as render:
        assert browser_driver.generate_step_images(
            '{"trace": []}', visualizer="json-pre", attempt=attempt
        ) == [b"image"]
    assert render.call_args.kwargs["attempt"] is attempt


def test_fresh_attempt_forwarding_through_session():
    from contextlib import contextmanager

    driver = MagicMock()

    @contextmanager
    def browser(*args, **kwargs):
        assert kwargs["fresh"] is True
        yield driver

    session = MagicMock(browser=browser)
    with browser_driver._browser_scope(1, session, RenderAttempt(fresh_browser=True)) as result:
        assert result is driver


@pytest.mark.parametrize("persistent", [False, True])
def test_caller_budget_frozen_payload_and_sibling_reuse(tmp_path, persistent):
    from pathlib import Path

    from cs1302_code_visualizer import trace_generator

    payload = Path("small-trace-examples/example0/Driver.java.json").read_text()
    original_factory = browser_driver.get_webdriver
    launches = []

    def factory(dpi=1):
        driver = original_factory(dpi)
        launches.append(driver.session_id)
        if persistent or len(launches) == 1:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": "const schedule = window.setTimeout.bind(window); window.setTimeout = (fn, delay, ...args) => delay === 50 ? 0 : schedule(fn, delay, ...args);"
                },
            )
        return driver

    sibling = tmp_path / "successful-sibling.svg"
    sibling.write_bytes(b"already published sibling")
    output = tmp_path / "pending.svg"
    failures = []
    with (
        RenderingSession(max_browsers=1) as session,
        patch.object(browser_driver, "get_webdriver", side_effect=factory),
        patch.object(
            trace_generator, "generate_trace", side_effect=AssertionError("must not retrace")
        ),
    ):
        for number in range(2):
            try:
                image = browser_driver.generate_image(
                    payload,
                    format="SVG",
                    session=session,
                    attempt=RenderAttempt(
                        "image", "lesson:1", str(number), fresh_browser=number > 0
                    ),
                )
            except ReadinessTimeout as error:
                failures.append(error)
                assert not output.exists()
            else:
                output.write_bytes(image)
                break
    assert len(launches) == 2
    assert len(failures) == (2 if persistent else 1)
    assert output.exists() is not persistent
    assert sibling.read_bytes() == b"already published sibling"
    assert render_diagnostic(failures[0]).attempt_id == "0"


def test_snapshot_transport_before_frame_entry_retains_payload_identity():
    import hashlib

    driver = MagicMock(session_id="lease")
    driver.execute_script.side_effect = InvalidSessionIdException("lost while creating frame")
    with (
        pytest.raises(BrowserTransportError) as caught,
        browser_driver._snapshot_frame(driver, "second-payload", "file:///render.html"),
    ):
        pytest.fail("transport failure must not yield")
    evidence = render_diagnostic(caught.value)
    assert evidence.payload_sha256 == hashlib.sha256(b"second-payload").hexdigest()
    assert evidence.stage == "snapshot-render"
