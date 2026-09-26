"""Exercise event-driven readiness against real document changes and failures."""

from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import JavascriptException, NoSuchElementException
from selenium.webdriver.remote.webelement import WebElement

from cs1302_code_visualizer import browser_driver


@pytest.mark.parametrize("result", [None, {}, "not an element"])
def test_readiness_rejects_absent_or_malformed_indicator(result):
    driver = MagicMock()
    driver.execute_async_script.return_value = result
    with pytest.raises(NoSuchElementException, match="four seconds"):
        browser_driver._wait_for_screenshot_ready(driver)


def test_readiness_propagates_script_errors():
    driver = MagicMock()
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
    indicator = MagicMock(spec=WebElement)
    driver.execute_async_script.return_value = indicator
    assert browser_driver._wait_for_screenshot_ready(driver) is indicator
