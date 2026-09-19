import importlib
import io
import json
import sys
from unittest.mock import Mock, patch

import pytest

import cs1302_code_visualizer
from cs1302_code_visualizer import (
    generate_step_images,
    main,
    render_image,
    render_images,
)

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
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.ensure_code_tracer_installed",
            side_effect=Exception("Failed"),
        ),
        pytest.raises(Exception, match="Unable to ensure code tracer is installed!"),
    ):
        render_image(SAMPLE_JAVA)


def test_render_image_trace_generation_error():
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.generate_trace",
            side_effect=Exception("Trace fail"),
        ),
        pytest.raises(Exception, match="Unable to generate execution trace!"),
    ):
        render_image(SAMPLE_JAVA)


def test_render_image_browser_driver_error():
    with (
        patch(
            "cs1302_code_visualizer.browser_driver.generate_image",
            side_effect=Exception("Render error"),
        ),
        pytest.raises(Exception, match="Unable to generate image from execution trace"),
    ):
        render_image(SAMPLE_JAVA)


def test_render_images_single_occurrence(rendering_session):
    res = render_images(
        SAMPLE_JAVA,
        breakpoints={4},
        render_all_breakpoint_occurrences=False,
        session=rendering_session,
    )
    assert isinstance(res, dict)
    assert 4 in res
    assert isinstance(res[4], bytes)


def test_render_images_all_occurrences(rendering_session):
    res = render_images(
        SAMPLE_JAVA,
        breakpoints={4},
        render_all_breakpoint_occurrences=True,
        session=rendering_session,
    )
    assert isinstance(res, dict)
    assert 4 in res
    assert isinstance(res[4], list)
    assert len(res[4]) > 0
    assert isinstance(res[4][0], bytes)


def test_generate_step_images_export():
    assert callable(generate_step_images)


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


def test_render_images_type_style(rendering_session):
    res = render_images(
        SAMPLE_JAVA, breakpoints={4}, type_style="simple", session=rendering_session
    )
    assert isinstance(res, dict)
    assert 4 in res


def test_render_image_tuple_breakpoint_non_list_trace():
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.generate_trace",
            return_value=json.dumps({"4": {"trace": []}}),
        ),
        patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"PNGDATA"),
    ):
        img = render_image(SAMPLE_JAVA, breakpoint_line=(4, 1))
        assert img == b"PNGDATA"


def test_render_image_stdin():
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.generate_trace",
            return_value=json.dumps({"4": {"trace": []}}),
        ) as mock_gen,
        patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"PNGDATA"),
    ):
        res = render_image(SAMPLE_JAVA, stdin="Hello stdin")
        assert res == b"PNGDATA"
        assert mock_gen.call_args.kwargs["stdin"] == "Hello stdin"


def test_render_image_stdin_file(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("Hello file", encoding="utf-8")
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.generate_trace",
            return_value=json.dumps({"4": {"trace": []}}),
        ) as mock_gen,
        patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"PNGDATA"),
    ):
        res = render_image(SAMPLE_JAVA, stdin_file=f)
        assert res == b"PNGDATA"
        assert mock_gen.call_args.kwargs["stdin_file"] == f


def test_render_images_stdin():
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.generate_trace",
            return_value=json.dumps({"4": {"trace": []}}),
        ) as mock_gen,
        patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"PNGDATA"),
    ):
        res = render_images(SAMPLE_JAVA, breakpoints={4}, stdin="Hello stdin")
        assert 4 in res
        assert mock_gen.call_args.kwargs["stdin"] == "Hello stdin"


def test_render_images_stdin_file(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("Hello file", encoding="utf-8")
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.generate_trace",
            return_value=json.dumps({"4": {"trace": []}}),
        ) as mock_gen,
        patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"PNGDATA"),
    ):
        res = render_images(SAMPLE_JAVA, breakpoints={4}, stdin_file=f)
        assert 4 in res
        assert mock_gen.call_args.kwargs["stdin_file"] == f


def test_init_main_with_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_JAVA))
    monkeypatch.setattr("sys.argv", ["main", "--stdin", "Hello stdin"])
    with patch(
        "cs1302_code_visualizer.render_image", return_value=b"\x89PNG\r\n\x1a\n"
    ) as mock_render:
        output_buffer = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", MockStdout(output_buffer))
        main()
        assert mock_render.call_args.kwargs["stdin"] == "Hello stdin"
        assert output_buffer.getvalue() == b"\x89PNG\r\n\x1a\n"


def test_init_main_with_stdin_file(tmp_path, monkeypatch):
    f = tmp_path / "input.java"
    f.write_text(SAMPLE_JAVA, encoding="utf-8")
    in_file = tmp_path / "stdin.txt"
    in_file.write_text("Hello file", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["main", "-i", str(f), "--stdin-file", str(in_file)])
    with patch(
        "cs1302_code_visualizer.render_image", return_value=b"\x89PNG\r\n\x1a\n"
    ) as mock_render:
        output_buffer = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", MockStdout(output_buffer))
        main()
        assert mock_render.call_args.kwargs["stdin_file"] == str(in_file)
        assert output_buffer.getvalue() == b"\x89PNG\r\n\x1a\n"


def test_render_image_eval_enum_hash():
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.generate_trace",
            return_value='{"4": {"trace": []}}',
        ) as mock_gen,
        patch(
            "cs1302_code_visualizer.browser_driver.generate_image",
            return_value=b"\x89PNG\r\n\x1a\n",
        ),
    ):
        res = render_image(SAMPLE_JAVA, eval_enum_hash=False)
        assert res == b"\x89PNG\r\n\x1a\n"
        assert mock_gen.call_args.kwargs["eval_enum_hash"] is False

        res2 = render_image(SAMPLE_JAVA, eval_enum_hash=True)
        assert res2 == b"\x89PNG\r\n\x1a\n"
        assert mock_gen.call_args.kwargs["eval_enum_hash"] is True


def test_render_images_eval_enum_hash():
    with (
        patch(
            "cs1302_code_visualizer.trace_generator.generate_trace",
            return_value='{"4": {"trace": []}}',
        ) as mock_gen,
        patch(
            "cs1302_code_visualizer.browser_driver.generate_image",
            return_value=b"\x89PNG\r\n\x1a\n",
        ),
    ):
        res = render_images(SAMPLE_JAVA, breakpoints={4}, eval_enum_hash=False)
        assert 4 in res
        assert mock_gen.call_args.kwargs["eval_enum_hash"] is False

        res2 = render_images(SAMPLE_JAVA, breakpoints={4}, eval_enum_hash=True)
        assert 4 in res2
        assert mock_gen.call_args.kwargs["eval_enum_hash"] is True


def test_init_main_with_no_eval_enum_hash(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_JAVA))
    monkeypatch.setattr("sys.argv", ["main", "--no-eval-enum-hash"])
    with patch(
        "cs1302_code_visualizer.render_image", return_value=b"\x89PNG\r\n\x1a\n"
    ) as mock_render:
        output_buffer = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", MockStdout(output_buffer))
        main()
        assert mock_render.call_args.kwargs["eval_enum_hash"] is False
        assert output_buffer.getvalue() == b"\x89PNG\r\n\x1a\n"


def test_resolve_and_render_trace_modern():
    from cs1302_code_visualizer import _resolve_and_render_trace

    modern_trace = {
        "trace": [
            {"line": 2, "event": "step_line"},
            {"line": 4, "event": "step_line"},
            {"line": 4, "event": "step_line"},
        ]
    }
    with patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"IMG"):
        # Breakpoints with -1
        res_default = _resolve_and_render_trace(json.dumps(modern_trace), {-1})
        assert -1 in res_default
        assert res_default[-1] == b"IMG"

        # Single occurrence
        res_single = _resolve_and_render_trace(json.dumps(modern_trace), {4})
        assert res_single[4] == b"IMG"

        # All occurrences
        res_all = _resolve_and_render_trace(
            json.dumps(modern_trace), {4}, render_all_occurrences=True
        )
        assert isinstance(res_all[4], list)
        assert len(res_all[4]) == 2


def test_resolve_and_render_trace_legacy():
    from cs1302_code_visualizer import _resolve_and_render_trace

    legacy_trace = {
        "4": [
            {"line": 4, "event": "step_line"},
            {"line": 4, "event": "step_line"},
        ]
    }
    with patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"IMG"):
        res_all = _resolve_and_render_trace(
            json.dumps(legacy_trace), {4}, render_all_occurrences=True
        )
        assert res_all[4] == [b"IMG", b"IMG"]

        legacy_single = {"4": {"line": 4, "event": "step_line"}}
        res_single = _resolve_and_render_trace(
            json.dumps(legacy_single), {4}, render_all_occurrences=False
        )
        assert res_single[4] == b"IMG"


def test_render_batch_images_empty():
    from collections.abc import Iterator

    from cs1302_code_visualizer import render_batch_images

    gen = render_batch_images([])
    assert isinstance(gen, Iterator)
    assert list(gen) == []


def test_render_batch_images_with_session():
    import concurrent.futures
    from collections.abc import Iterator

    from cs1302_code_visualizer import BatchRenderJob, render_batch_images

    mock_session = Mock()
    mock_session.max_browsers = 2
    mock_batch_tracer = Mock()
    mock_session.batch_tracer = mock_batch_tracer

    f1 = concurrent.futures.Future()
    f1.set_result({"trace": [{"line": 4, "event": "step_line"}]})
    mock_batch_tracer.submit.return_value = f1

    with patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"BATCH_IMG"):
        jobs = [
            BatchRenderJob(
                java_source="class A {}",
                breakpoints={4},
                job_id="custom_id",
            )
        ]
        gen = render_batch_images(jobs, session=mock_session)
        assert isinstance(gen, Iterator)
        results = list(gen)
        assert len(results) == 1
        assert results[0] == {4: b"BATCH_IMG"}


def test_render_batch_images_creates_session():
    import concurrent.futures
    from collections.abc import Iterator

    from cs1302_code_visualizer import BatchRenderJob, render_batch_images

    mock_session = Mock()
    mock_session.max_browsers = 2
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=None)
    mock_batch_tracer = Mock()
    mock_session.batch_tracer = mock_batch_tracer

    f1 = concurrent.futures.Future()
    f1.set_result({"trace": [{"line": 4, "event": "step_line"}]})
    mock_batch_tracer.submit.return_value = f1

    with (
        patch("cs1302_code_visualizer.RenderingSession", return_value=mock_session),
        patch("cs1302_code_visualizer.browser_driver.generate_image", return_value=b"BATCH_IMG"),
    ):
        jobs = [
            BatchRenderJob(
                java_source="class A {}",
                breakpoints={4},
            )
        ]
        gen = render_batch_images(jobs, tracer_workers=2)
        assert isinstance(gen, Iterator)
        results = list(gen)
        assert len(results) == 1
        assert results[0] == {4: b"BATCH_IMG"}
