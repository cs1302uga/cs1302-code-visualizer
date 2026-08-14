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
    with patch("cs1302_code_visualizer.browser_driver.online_python_tutor_frontend", return_value=mock_frontend):
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
