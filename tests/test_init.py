import io
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
import importlib
import cs1302_code_visualizer
from cs1302_code_visualizer import render_image, render_images, main

SAMPLE_JAVA = """
public class Driver {
    public static void main(String[] args) {
        int x = 10;
    }
}
"""


class MockStdout:
    def __init__(self, buffer):
        self.buffer = buffer


def test_debug_mode_init(monkeypatch):
    monkeypatch.setenv("CS1302_DEBUG", "1")
    importlib.reload(cs1302_code_visualizer)
    assert cs1302_code_visualizer.DEBUG_MODE is True


def test_render_image():
    img = render_image(SAMPLE_JAVA, breakpoint_line=-1, verbose=True)
    assert isinstance(img, bytes)
    assert img[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_image_tuple_breakpoint():
    img = render_image(SAMPLE_JAVA, breakpoint_line=(4, 1))
    assert isinstance(img, bytes)
    assert img[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_image_tuple_breakpoint_out_of_bounds():
    img = render_image(SAMPLE_JAVA, breakpoint_line=(4, 999))
    assert isinstance(img, bytes)
    assert img[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_image_tracer_installer_error():
    with patch(
        "cs1302_code_visualizer.trace_generator.ensure_code_tracer_installed",
        side_effect=Exception("Failed"),
    ):
        with pytest.raises(Exception, match="Unable to ensure code tracer is installed!"):
            render_image(SAMPLE_JAVA)


def test_render_image_trace_generation_error():
    with patch(
        "cs1302_code_visualizer.trace_generator.generate_trace", side_effect=Exception("Trace fail")
    ):
        with pytest.raises(Exception, match="Unable to generate execution trace!"):
            render_image(SAMPLE_JAVA)


def test_render_image_browser_driver_error():
    with patch(
        "cs1302_code_visualizer.browser_driver.generate_image",
        side_effect=Exception("Render error"),
    ):
        with pytest.raises(Exception, match="Unable to generate image from execution trace"):
            render_image(SAMPLE_JAVA)


def test_render_images_single_occurrence():
    res = render_images(SAMPLE_JAVA, breakpoints={4}, render_all_breakpoint_occurrences=False)
    assert isinstance(res, dict)
    assert 4 in res
    assert isinstance(res[4], bytes)


def test_render_images_all_occurrences():
    res = render_images(SAMPLE_JAVA, breakpoints={4}, render_all_breakpoint_occurrences=True)
    assert isinstance(res, dict)
    assert 4 in res
    assert isinstance(res[4], list)
    assert len(res[4]) > 0
    assert isinstance(res[4][0], bytes)


def test_init_main(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_JAVA))
    monkeypatch.setattr("sys.argv", ["main"])
    output_buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", MockStdout(output_buffer))
    main()
    val = output_buffer.getvalue()
    assert len(val) > 0
    assert val[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_image_type_style():
    img_simple = render_image(SAMPLE_JAVA, type_style="simple")
    assert isinstance(img_simple, bytes)
    img_fqn = render_image(SAMPLE_JAVA, type_style="fqn")
    assert isinstance(img_fqn, bytes)


def test_render_images_type_style():
    res = render_images(SAMPLE_JAVA, breakpoints={4}, type_style="simple")
    assert isinstance(res, dict)
    assert 4 in res


def test_render_image_tuple_breakpoint_non_list_trace():
    with patch(
        "cs1302_code_visualizer.trace_generator.generate_trace",
        return_value=json.dumps({"4": {"trace": []}}),
    ):
        with patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"PNGDATA"):
            img = render_image(SAMPLE_JAVA, breakpoint_line=(4, 1))
            assert img == b"PNGDATA"

