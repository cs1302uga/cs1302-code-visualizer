import io
import sys
import json
import runpy
import pytest
import importlib
from unittest.mock import patch, MagicMock
import cs1302_code_visualizer.browser_driver as browser_driver
from cs1302_code_visualizer.trace_generator import generate_trace, ensure_jdk_installed
from cs1302_code_visualizer.browser_driver import (
    new_webdriver_options,
    get_webdriver,
    generate_html,
    generate_image,
    main as driver_main,
)

SAMPLE_JAVA = """
public class Driver {
    public static void main(String[] args) {
        String msg = "Hello";
    }
}
"""


class MockStdout:
    def __init__(self, buffer):
        self.buffer = buffer


@pytest.fixture(scope="module")
def sample_trace_json():
    java_home = ensure_jdk_installed()
    trace_raw = generate_trace(java_home, SAMPLE_JAVA, breakpoints={-1})
    data = json.loads(trace_raw)
    inner = data.get("-1", list(data.values())[0])
    return json.dumps(inner)


def test_browser_driver_debug_and_headless_env(monkeypatch):
    monkeypatch.setenv("CS1302_DEBUG", "1")
    monkeypatch.setenv("CS1302_HEADLESS", "1")
    importlib.reload(browser_driver)
    opts = browser_driver.new_webdriver_options(dpi=1)
    assert opts is not None


def test_get_webdriver_with_explicit_chromedriver_path(monkeypatch):
    mock_driver = MagicMock()
    with patch("shutil.which", return_value="/usr/local/bin/chromedriver"):
        with patch("selenium.webdriver.chrome.service.Service.__init__", return_value=None):
            with patch("selenium.webdriver.Chrome", return_value=mock_driver):
                driver = get_webdriver(dpi=1)
                assert driver is mock_driver


def test_generate_html(sample_trace_json):
    html = generate_html(sample_trace_json, dpi=1)
    assert isinstance(html, str)
    assert "vizDiv" in html


def test_generate_html_failure(monkeypatch):
    mock_frontend = MagicMock()
    mock_elem = MagicMock()
    mock_elem.get_attribute.return_value = None
    mock_frontend.__getitem__.return_value = mock_elem
    mock_frontend.__enter__.return_value = mock_frontend
    mock_frontend.__exit__.return_value = None
    with patch(
        "cs1302_code_visualizer.browser_driver.online_python_tutor_frontend",
        return_value=mock_frontend,
    ):
        with pytest.raises(Exception, match="unable to generate an HTML visualization"):
            generate_html("{}", dpi=1)


def test_generate_image_with_options(sample_trace_json):
    img = generate_image(
        sample_trace_json,
        dpi=1,
        format="PNG",
        include_types=True,
        text_memory_labels=False,
        strip_type_prefixes=["java.lang."],
    )
    assert isinstance(img, bytes)
    assert img[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_image_with_line_keyed_trace(sample_trace_json):
    data = json.loads(sample_trace_json)
    wrapper = json.dumps({"5": data})
    img = generate_image(wrapper, breakpoint=5)
    assert isinstance(img, bytes)
    assert img[:8] == b"\x89PNG\r\n\x1a\n"


def test_driver_main_cli(sample_trace_json, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(sample_trace_json))
    output_buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", MockStdout(output_buffer))
    monkeypatch.setattr("sys.argv", ["generate_visualization", "--dpi", "1"])
    driver_main()
    val = output_buffer.getvalue()
    assert len(val) > 0
    assert val[:8] == b"\x89PNG\r\n\x1a\n"


def test_driver_main_invalid_dpi(monkeypatch):
    monkeypatch.setattr("sys.argv", ["generate_visualization", "--dpi", "0"])
    with pytest.raises(SystemExit):
        driver_main()


def test_driver_runpy_main(sample_trace_json, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(sample_trace_json))
    output_buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", MockStdout(output_buffer))
    monkeypatch.setattr("sys.argv", ["generate_visualization", "--dpi", "1"])
    runpy.run_module("cs1302_code_visualizer.browser_driver", run_name="__main__")
    val = output_buffer.getvalue()
    assert len(val) > 0


def test_is_headless_enabled_env_vars(monkeypatch):
    monkeypatch.setenv("CS1302_DISABLE_HEADLESS", "1")
    monkeypatch.delenv("CS1302_HEADLESS", raising=False)
    assert browser_driver.is_headless_enabled() is False

    monkeypatch.delenv("CS1302_DISABLE_HEADLESS", raising=False)
    monkeypatch.setenv("CS1302_HEADLESS", "0")
    assert browser_driver.is_headless_enabled() is False


def test_online_python_tutor_frontend_json_pre(sample_trace_json):
    # Test json-pre visualizer option
    with browser_driver.online_python_tutor_frontend(
        sample_trace_json, visualizer="json-pre"
    ) as frontend:
        assert frontend["vizDiv"] is not None
        assert frontend["dataViz"] is not None


def test_online_python_tutor_frontend_json_pre_fallback(monkeypatch, sample_trace_json):
    mock_driver = MagicMock()
    mock_wait = MagicMock()
    mock_elem = MagicMock()
    mock_viz_div = MagicMock()
    mock_viz_div.find_element.side_effect = Exception("No pre tag")

    mock_driver.find_element.side_effect = lambda by, val: (
        mock_elem if val == "screenshotReadyIndicator" else mock_viz_div
    )
    with patch("cs1302_code_visualizer.browser_driver.get_webdriver", return_value=mock_driver):
        with browser_driver.online_python_tutor_frontend(
            sample_trace_json, visualizer="json-pre"
        ) as frontend:
            assert frontend["dataViz"] == mock_viz_div


def test_generate_image_breakpoint_resolution_branches(sample_trace_json):
    data = json.loads(sample_trace_json)

    mock_driver = MagicMock()
    mock_driver.get_screenshot_as_png.return_value = b"\x89PNG\r\n\x1a\n"
    mock_viz = MagicMock()
    mock_viz.location = {"x": 0, "y": 0}
    mock_viz.size = {"width": 100, "height": 100}

    with patch("cs1302_code_visualizer.browser_driver.tidy_set_window_size_for_element"):
        with patch("cs1302_code_visualizer.browser_driver.online_python_tutor_frontend") as mock_fe:
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = {
                "driver": mock_driver,
                "dataViz": mock_viz,
                "wait": MagicMock(),
            }
            mock_fe.return_value = mock_ctx
            with patch("PIL.Image.open") as mock_img_open:
                mock_im = MagicMock()
                mock_img_open.return_value = mock_im

                # 1. Breakpoints dict with tuple (found list, in range & out of range)
                t1 = json.dumps({"breakpoints": {"6": [data, data]}})
                _ = generate_image(t1, breakpoint=(6, 1))
                _ = generate_image(t1, breakpoint=(6, 99))  # out of bounds fallback

                # 2. Breakpoints dict with tuple (not a list), int breakpoint, -1 in bps, len(bps)==1
                t2 = json.dumps({"breakpoints": {"6": data}})
                _ = generate_image(t2, breakpoint=(6, 1))
                _ = generate_image(t2, breakpoint=6)
                _ = generate_image(json.dumps({"breakpoints": {"-1": data}}), breakpoint=None)
                _ = generate_image(json.dumps({"breakpoints": {"10": data}}), breakpoint=None)

                # 3. Line-keyed traces without "breakpoints" key
                t3 = json.dumps({"6": [data, data]})
                _ = generate_image(t3, breakpoint=(6, 1))
                _ = generate_image(t3, breakpoint=(6, 99))
                _ = generate_image(json.dumps({"6": data}), breakpoint=(6, 1))
                _ = generate_image(json.dumps({"6": data}), breakpoint=6)
                _ = generate_image(json.dumps({"-1": data}), breakpoint=None)
                _ = generate_image(json.dumps({"10": data}), breakpoint=None)

                # 4. List of traces
                t4 = json.dumps([data, data])
                _ = generate_image(t4, breakpoint=(1, 1))
                _ = generate_image(t4, breakpoint=(1, 99))
                _ = generate_image(t4, breakpoint=None)


