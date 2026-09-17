import importlib
import io
import json
import os
import runpy
import sys
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import NoSuchElementException

from cs1302_code_visualizer import browser_driver
from cs1302_code_visualizer.browser_driver import (
    generate_html,
    generate_image,
    generate_step_images,
    get_default_bundle_url,
    get_webdriver,
    render_html,
    render_html_cli,
)
from cs1302_code_visualizer.browser_driver import (
    main as driver_main,
)
from cs1302_code_visualizer.trace_generator import ensure_jdk_installed, generate_trace

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
    inner = data.get("-1", next(iter(data.values())))
    return json.dumps(inner)


def test_browser_driver_debug_and_headless_env(monkeypatch):
    monkeypatch.setenv("CS1302_DEBUG", "1")
    monkeypatch.setenv("CS1302_HEADLESS", "1")
    importlib.reload(browser_driver)
    opts = browser_driver.new_webdriver_options(dpi=1)
    assert opts is not None


def test_get_webdriver_with_explicit_chromedriver_path(monkeypatch):
    mock_driver = MagicMock()
    with (
        patch("shutil.which", return_value="/usr/local/bin/chromedriver"),
        patch("selenium.webdriver.chrome.service.Service.__init__", return_value=None),
        patch("selenium.webdriver.Chrome", return_value=mock_driver),
    ):
        driver = get_webdriver(dpi=1)
        assert driver is mock_driver


@pytest.mark.parametrize("existing", [None, "", "/old/cacert.pem", "/current/cacert.pem"])
@pytest.mark.parametrize("driver_path", [None, "/usr/local/bin/chromedriver"])
def test_webdriver_configures_certifi_before_startup(monkeypatch, existing, driver_path):
    bundle = "/current/cacert.pem"
    if existing is None:
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    else:
        monkeypatch.setenv("SSL_CERT_FILE", existing)
    monkeypatch.setattr("certifi.where", lambda: bundle)
    monkeypatch.setattr(browser_driver.shutil, "which", lambda _: driver_path)
    driver = MagicMock()

    def start_chrome(*, service, options):
        assert os.environ["SSL_CERT_FILE"] == bundle
        assert service.env["SSL_CERT_FILE"] == bundle
        return driver

    with patch.object(browser_driver.webdriver, "Chrome", side_effect=start_chrome):
        assert get_webdriver() is driver
    driver.implicitly_wait.assert_called_once_with(4)


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
    ), pytest.raises(Exception, match="unable to generate an HTML visualization"):
        generate_html("{}", dpi=1)


def test_generate_image_with_options(sample_trace_json, rendering_session):
    img = generate_image(
        sample_trace_json,
        dpi=1,
        format="PNG",
        include_types=True,
        text_memory_labels=False,
        strip_type_prefixes=["java.lang."],
        session=rendering_session,
    )
    assert isinstance(img, bytes)
    assert img[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_image_with_line_keyed_trace(sample_trace_json, rendering_session):
    data = json.loads(sample_trace_json)
    wrapper = json.dumps({"5": data})
    img = generate_image(wrapper, breakpoint=5, session=rendering_session)
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


def test_driver_main_cli_breakpoint(sample_trace_json, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(sample_trace_json))
    output_buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", MockStdout(output_buffer))
    monkeypatch.setattr("sys.argv", ["generate_visualization", "-b", "6,1"])
    with patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"\x89PNG\r\n\x1a\n") as mock_gi:
        driver_main()
        assert mock_gi.call_args[1]["breakpoint"] == (6, 1)

    monkeypatch.setattr("sys.argv", ["generate_visualization", "-b", "29"])
    with patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"\x89PNG\r\n\x1a\n") as mock_gi:
        driver_main()
        assert mock_gi.call_args[1]["breakpoint"] == 29

    monkeypatch.setattr("sys.argv", ["generate_visualization", "-b", "29,"])
    with patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"\x89PNG\r\n\x1a\n") as mock_gi:
        driver_main()
        assert mock_gi.call_args[1]["breakpoint"] == 29


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
    mock_elem = MagicMock()
    mock_viz_div = MagicMock()
    mock_viz_div.find_element.side_effect = NoSuchElementException("No pre tag")

    mock_driver.find_element.side_effect = lambda by, val: (
        mock_elem if val == "screenshotReadyIndicator" else mock_viz_div
    )
    with (
        patch("cs1302_code_visualizer.browser_driver.get_webdriver", return_value=mock_driver),
        browser_driver.online_python_tutor_frontend(
            sample_trace_json, visualizer="json-pre"
        ) as frontend,
    ):
        assert frontend["dataViz"] == mock_viz_div


def test_generate_image_breakpoint_resolution_branches(sample_trace_json):
    data = json.loads(sample_trace_json)

    mock_driver = MagicMock()
    mock_driver.get_screenshot_as_png.return_value = b"\x89PNG\r\n\x1a\n"
    mock_viz = MagicMock()
    mock_viz.location = {"x": 0, "y": 0}
    mock_viz.size = {"width": 100, "height": 100}

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = {
        "driver": mock_driver,
        "dataViz": mock_viz,
        "wait": MagicMock(),
    }
    with (
        patch("cs1302_code_visualizer.browser_driver.tidy_set_window_size_for_element"),
        patch(
            "cs1302_code_visualizer.browser_driver.online_python_tutor_frontend",
            return_value=mock_ctx,
        ),
        patch("PIL.Image.open") as mock_img_open,
    ):
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
        _ = generate_image(t2, breakpoint=999)  # len(bps) == 1 fallback
        _ = generate_image(json.dumps({"breakpoints": {"-1": data}}), breakpoint=None)
        _ = generate_image(json.dumps({"breakpoints": {"10": data}}), breakpoint=None)

        # 3. Line-keyed traces without "breakpoints" key
        t3 = json.dumps({"6": [data, data]})
        _ = generate_image(t3, breakpoint=(6, 1))
        _ = generate_image(t3, breakpoint=(6, 99))
        _ = generate_image(json.dumps({"6": data}), breakpoint=(6, 1))
        _ = generate_image(json.dumps({"6": data}), breakpoint=6)
        _ = generate_image(json.dumps({"6": data}), breakpoint=999)  # len(trace_json) == 1 fallback
        _ = generate_image(json.dumps({"-1": data}), breakpoint=None)
        _ = generate_image(json.dumps({"10": data}), breakpoint=None)

        # 4. List of traces
        t4 = json.dumps([data, data])
        _ = generate_image(t4, breakpoint=(1, 1))
        _ = generate_image(t4, breakpoint=(1, 99))
        _ = generate_image(t4, breakpoint=None)


def test_get_default_bundle_url():
    url = get_default_bundle_url()
    assert "https://github.com/cs1302uga/cs1302-code-visualizer/releases/download/v" in url
    assert url.endswith("/vis-module.bundle.js")

    with patch("importlib.metadata.version", side_effect=browser_driver.metadata.PackageNotFoundError):
        fallback_url = get_default_bundle_url()
        assert "v0.7.1" in fallback_url


def test_render_html_basic(sample_trace_json):
    html = render_html(sample_trace_json)
    assert '<div id="codevis-' in html
    assert '<script src="https://github.com/cs1302uga/cs1302-code-visualizer/releases/download/' in html
    assert "CodeVisualizer.create({" in html
    assert 'lang: "java"' in html
    assert "options: {" in html


def test_render_html_custom(sample_trace_json):
    html = render_html(
        sample_trace_json,
        container_id="custom-container",
        bundle_url="https://example.com/custom.bundle.js",
        include_bundle_script=False,
        include_types=False,
        text_memory_labels=True,
        strip_type_prefixes=["java.lang."],
        hide_fields=["Secret:hidden"],
        hide_vars=["unused"],
        visualizer="json-pre",
        lang="java",
    )
    assert '<div id="custom-container"></div>' in html
    assert '<script src="' not in html
    assert 'document.getElementById("custom-container")' in html
    assert '"includeTypes": false' in html
    assert '"textualMemoryLabels": true' in html
    assert '"stripTypePrefixes": ["java.lang."]' in html
    assert '"hideFields": ["Secret:hidden"]' in html
    assert '"hideVars": ["unused"]' in html
    assert '"visualizer": "json-pre"' in html


def test_render_html_escaping_and_dict():
    trace_dict = {"code": 'String s = "</script><script>alert(1)</script>";', "trace": []}
    html = render_html(trace_dict)
    assert "</script><script>" not in html
    assert r"<\/script><script>" in html


def test_driver_main_cli_html(sample_trace_json, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(sample_trace_json))
    output_buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_buffer)
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_visualization",
            "--html",
            "--container-id",
            "cli-container",
            "--bundle-url",
            "https://test.bundle.js",
            "--no-bundle-script",
            "-b",
            "6,1",
        ],
    )
    driver_main()
    val = output_buffer.getvalue()
    assert '<div id="cli-container"></div>' in val
    assert '<script src="' not in val


def test_render_html_cli(sample_trace_json, monkeypatch):
    # Test 1: with comma breakpoint
    monkeypatch.setattr(sys, "stdin", io.StringIO(sample_trace_json))
    output_buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_buffer)
    monkeypatch.setattr(
        "sys.argv",
        [
            "render_html",
            "-b",
            "6,1",
            "--container-id",
            "test-id",
            "--bundle-url",
            "https://cdn.example/bundle.js",
            "--text-memory-labels",
            "--no-include-types",
            "--visualizer",
            "json-pre",
        ],
    )
    render_html_cli()
    val = output_buffer.getvalue()
    assert '<div id="test-id"></div>' in val
    assert '<script src="https://cdn.example/bundle.js"></script>' in val
    assert '"visualizer": "json-pre"' in val

    # Test 2: with int breakpoint
    monkeypatch.setattr(sys, "stdin", io.StringIO(sample_trace_json))
    output_buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_buffer)
    monkeypatch.setattr("sys.argv", ["render_html", "-b", "29", "--no-bundle-script"])
    render_html_cli()
    val2 = output_buffer.getvalue()
    assert "<div id=" in val2
    assert "<script src=" not in val2

    # Test 3: with trailing comma breakpoint
    monkeypatch.setattr(sys, "stdin", io.StringIO(sample_trace_json))
    output_buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output_buffer)
    monkeypatch.setattr("sys.argv", ["render_html", "-b", "29,"])
    render_html_cli()
    val3 = output_buffer.getvalue()
    assert "<div id=" in val3


def test_generate_step_images_single_and_json_pre(sample_trace_json, rendering_session):
    imgs1 = generate_step_images(sample_trace_json, session=rendering_session)
    assert len(imgs1) == 1
    assert isinstance(imgs1[0], bytes)

    imgs2 = generate_step_images(sample_trace_json, visualizer="json-pre", session=rendering_session)
    assert len(imgs2) == 1
    assert isinstance(imgs2[0], bytes)


def test_generate_step_images_multi_step_and_cli(tmp_path, monkeypatch):
    multi_java = """
    public class Driver {
        public static void main(String[] args) {
            int a = 1;
            int b = 2;
        }
    }
    """
    java_home = ensure_jdk_installed()
    trace_raw = generate_trace(java_home, multi_java, all_breakpoints=True)
    step_imgs = generate_step_images(trace_raw)
    assert len(step_imgs) >= 2
    assert all(isinstance(img, bytes) for img in step_imgs)

    # CLI with --all-steps and -o ending in .png
    out_file = tmp_path / "Driver.java.png"
    monkeypatch.setattr(sys, "stdin", io.StringIO(trace_raw))
    monkeypatch.setattr(
        "sys.argv",
        ["generate_visualization", "--all-steps", "-o", str(out_file)],
    )
    driver_main()
    assert out_file.exists()
    assert (tmp_path / "Driver.java.0.png").exists()
    assert (tmp_path / "Driver.java.1.png").exists()

    # CLI with --all-steps and -o NOT ending in .png
    out_no_ext = tmp_path / "OutputNoExt"
    monkeypatch.setattr(sys, "stdin", io.StringIO(trace_raw))
    monkeypatch.setattr(
        "sys.argv",
        ["generate_visualization", "--all-steps", "-o", str(out_no_ext)],
    )
    driver_main()
    assert (tmp_path / "OutputNoExt.png").exists()
    assert (tmp_path / "OutputNoExt.0.png").exists()

    # CLI with --all-steps writing to stdout
    out_buf = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(trace_raw))
    monkeypatch.setattr(sys, "stdout", MockStdout(out_buf))
    monkeypatch.setattr(
        "sys.argv",
        ["generate_visualization", "--all-steps"],
    )
    driver_main()
    assert len(out_buf.getvalue()) > 0

    # CLI without --all-steps with -o
    single_out = tmp_path / "Single.png"
    monkeypatch.setattr(sys, "stdin", io.StringIO(trace_raw))
    monkeypatch.setattr(
        "sys.argv",
        ["generate_visualization", "-o", str(single_out)],
    )
    driver_main()
    assert single_out.exists()

