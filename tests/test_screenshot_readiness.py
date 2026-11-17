"""Exercise event-driven readiness against real document changes and failures."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import JavascriptException, NoSuchElementException, TimeoutException
from selenium.webdriver.remote.webelement import WebElement

from cs1302_code_visualizer import browser_driver
from cs1302_code_visualizer.readiness import ReadinessTimeout


@pytest.mark.parametrize("result", [None, {}, "not an element"])
def test_readiness_rejects_absent_or_malformed_indicator(result):
    driver = MagicMock()
    driver.timeouts.script = 30
    driver.execute_async_script.return_value = result
    with pytest.raises(NoSuchElementException, match="four seconds"):
        browser_driver._wait_for_screenshot_ready(driver)


def test_readiness_propagates_script_errors():
    driver = MagicMock()
    driver.timeouts.script = 30
    driver.execute_async_script.side_effect = JavascriptException("document unavailable")
    with pytest.raises(JavascriptException, match="document unavailable"):
        browser_driver._wait_for_screenshot_ready(driver)


@pytest.mark.parametrize("timing", ["existing", "delayed", "absent"])
def test_readiness_observes_existing_signal_and_cleans_up(timing):
    driver = browser_driver.get_webdriver()
    try:
        driver.get("about:blank")
        driver.execute_script(
            """
            const timing = arguments[0];
            window.activeObservers = 0;
            window.readinessTimersCleared = 0;
            const Observer = window.MutationObserver;
            window.MutationObserver = class extends Observer {
                observe(...args) {
                    window.activeObservers++;
                    const result = super.observe(...args);
                    if (timing === 'delayed') schedule(insert, 50);
                    return result;
                }
                disconnect() { window.activeObservers--; super.disconnect(); }
            };
            const schedule = window.setTimeout.bind(window);
            const cancel = window.clearTimeout.bind(window);
            let readinessTimer;
            window.setTimeout = (callback, delay) => {
                const id = schedule(callback, delay);
                if (delay === 4000) readinessTimer = id;
                return id;
            };
            window.clearTimeout = id => {
                if (id === readinessTimer) window.readinessTimersCleared++;
                cancel(id);
            };
            function insert() {
                const indicator = document.createElement('div');
                indicator.id = 'screenshotReadyIndicator';
                document.body.appendChild(indicator);
            }
            if (timing === 'existing') insert();
            """,
            timing,
        )
        if timing == "absent":
            with pytest.raises(NoSuchElementException, match="four seconds"):
                browser_driver._wait_for_screenshot_ready(driver)
        else:
            indicator = browser_driver._wait_for_screenshot_ready(driver)
            assert isinstance(indicator, WebElement)
            assert indicator.get_attribute("id") == "screenshotReadyIndicator"
        assert driver.execute_script("return window.activeObservers") == 0
        assert driver.execute_script("return window.readinessTimersCleared") == (
            0 if timing == "existing" else 1
        )
    finally:
        driver.quit()


def test_readiness_returns_the_browser_indicator():
    driver = MagicMock()
    driver.timeouts.script = 30
    indicator = MagicMock(spec=WebElement)
    driver.execute_async_script.return_value = indicator
    assert browser_driver._wait_for_screenshot_ready(driver) is indicator


@pytest.mark.parametrize("previous, bounded", [(30, 8), (2, 2), (0, 0)])
def test_readiness_restores_caller_timeout(previous, bounded):
    driver = MagicMock()
    driver.timeouts.script = previous
    indicator = MagicMock(spec=WebElement)
    driver.execute_async_script.return_value = indicator
    assert browser_driver._wait_for_screenshot_ready(driver) is indicator
    assert [call.args for call in driver.set_script_timeout.call_args_list] == [
        (bounded,),
        (previous,),
    ]


def test_only_readiness_command_timeout_is_classified():
    driver = MagicMock()
    driver.timeouts.script = 30
    error = TimeoutException("remote asynchronous script expired")
    driver.execute_async_script.side_effect = error
    with pytest.raises(ReadinessTimeout) as caught:
        browser_driver._wait_for_screenshot_ready(driver)
    assert caught.value.__cause__ is error
    driver.set_script_timeout.assert_any_call(30)
    driver.set_script_timeout.side_effect = error
    with pytest.raises(TimeoutException) as caught:
        browser_driver._wait_for_screenshot_ready(driver)
    assert caught.value is error


@pytest.mark.parametrize("outcome", ["success", "frontend", "script", "cancel"])
def test_timeout_restoration_preserves_primary_error(outcome):
    driver = MagicMock()
    driver.timeouts.script = 30
    driver.set_script_timeout.side_effect = [None, OSError("restore failed")]
    if outcome == "frontend":
        driver.execute_async_script.return_value = {"error": "layout failed"}
        expected, message = ValueError, "layout failed"
    elif outcome in {"script", "cancel"}:
        error = JavascriptException("script failed") if outcome == "script" else KeyboardInterrupt()
        driver.execute_async_script.side_effect = error
        expected, message = type(error), None
    else:
        driver.execute_async_script.return_value = MagicMock(spec=WebElement)
        expected, message = OSError, "restore failed"
    with pytest.raises(expected, match=message):
        browser_driver._wait_for_screenshot_ready(driver)


def test_remote_watchdog_honors_shorter_timeout():
    driver = browser_driver.get_webdriver()
    try:
        driver.get("about:blank")
        driver.set_script_timeout(0.1)
        with pytest.raises(ReadinessTimeout) as caught:
            browser_driver._wait_for_screenshot_ready(driver)
        assert isinstance(caught.value.__cause__, TimeoutException)
        assert driver.timeouts.script == pytest.approx(0.1)
    finally:
        driver.quit()


@pytest.mark.parametrize("activity", ["milestone", "unrelated", "already-constructed"])
def test_activity_cannot_renew_settling_repeatedly(activity):
    driver = browser_driver.get_webdriver()
    try:
        driver.get("about:blank")
        driver.execute_script(
            """
            const activity = arguments[0];
            const milestone = 'data-codevis-construction-complete';
            if (activity === 'already-constructed') {
                document.documentElement.setAttribute(milestone, 'true');
            }
            window.waitStarted = performance.now();
            window.activityCount = 0;
            setInterval(() => {
                window.activityCount++;
                if (activity === 'unrelated') document.body.appendChild(document.createElement('i'));
                else document.documentElement.setAttribute(milestone, 'true');
            }, 100);
            """,
            activity,
        )
        with pytest.raises(ReadinessTimeout):
            browser_driver._wait_for_screenshot_ready(driver)
        # One milestone can renew the initial window, but repeated writes and
        # other document activity cannot keep renewing it to the outer ceiling.
        assert driver.execute_script("return performance.now() - window.waitStarted") < 6500
        assert driver.execute_script("return window.activityCount") > 2
    finally:
        driver.quit()


def test_blocked_document_cannot_publish_readiness_after_ceiling():
    driver = browser_driver.get_webdriver()
    try:
        driver.get("about:blank")
        driver.execute_script(
            """
            setTimeout(() => {
                const end = performance.now() + 8200;
                while (performance.now() < end) {}
                document.documentElement.setAttribute('data-codevis-construction-complete', 'true');
                const ready = document.createElement('div');
                ready.id = 'screenshotReadyIndicator';
                document.body.appendChild(ready);
            }, 100);
            """
        )
        with pytest.raises(ReadinessTimeout):
            browser_driver._wait_for_screenshot_ready(driver)
        assert driver.timeouts.script == 30
    finally:
        driver.quit()


def test_frontend_error_takes_priority_over_ready_and_milestone():
    driver = browser_driver.get_webdriver()
    try:
        driver.get("about:blank")
        driver.execute_script(
            """
            setTimeout(() => {
                document.documentElement.setAttribute('data-codevis-construction-complete', 'true');
                document.body.innerHTML = '<div id=screenshotError>explicit failure</div>'
                    + '<div id=screenshotReadyIndicator></div>';
            }, 100);
            """
        )
        with pytest.raises(ValueError, match="explicit failure"):
            browser_driver._wait_for_screenshot_ready(driver)
    finally:
        driver.quit()


@pytest.mark.parametrize("mode", ["initial", "snapshot"])
def test_construction_completion_precedes_queued_expiry(mode):
    """A completed constructor gets its deferred redraw before being rejected."""
    payload = json.dumps(
        browser_driver.resolve_trace_payload(
            Path("small-trace-examples/example0/Driver.java.json").read_text()
        )
    )
    driver = browser_driver.get_webdriver()
    script = """
        const fetchTrace = window.fetch.bind(window);
        window.fetch = (...args) => fetchTrace(...args).then(response => {
            const parse = response.json.bind(response);
            response.json = () => parse().then(value => new Promise(resolve => {
                setTimeout(() => {
                    const end = performance.now() + 4100;
                    while (performance.now() < end) {}
                    resolve(value);
                }, 150);
            }));
            return response;
        });
    """
    try:
        if mode == "snapshot":
            with (
                patch.object(browser_driver, "get_webdriver", return_value=driver),
                browser_driver.online_python_tutor_frontend(payload),
            ):
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})
                with browser_driver._snapshot_frame(
                    driver, payload, driver.current_url
                ) as visualization:
                    assert visualization.get_attribute("id") == "dataViz"
                    assert driver.execute_script(
                        "return !!document.getElementById('screenshotReadyIndicator')"
                    )
                assert driver.find_elements("tag name", "iframe") == []
        else:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})
            with (
                patch.object(browser_driver, "get_webdriver", return_value=driver),
                browser_driver.online_python_tutor_frontend(payload) as frontend,
            ):
                assert frontend["dataViz"].get_attribute("id") == "dataViz"
    finally:
        if driver.service.process is not None and driver.service.process.poll() is None:
            driver.quit()
