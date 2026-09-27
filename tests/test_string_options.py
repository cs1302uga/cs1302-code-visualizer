"""String style compatibility and propagation across rendering entry points."""

import argparse
import json
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import cs1302_code_visualizer as package
from cs1302_code_visualizer import browser_driver, cli
from cs1302_code_visualizer.string_options import (
    add_string_argument,
    resolve_string_style,
    string_options_from_args,
)


def test_resolution_and_warning_location():
    assert resolve_string_style() == "default"
    for style in ("default", "compact", "inline"):
        assert resolve_string_style(style) == style
    for old, style in ((False, "default"), (True, "inline")):
        with pytest.warns(DeprecationWarning, match="inline_strings") as caught:
            job = package.BatchRenderJob("class Main {}", {1}, inline_strings=old)
        assert job.string_style == style
        assert Path(caught[0].filename) == Path(__file__)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert package.BatchRenderJob("class Main {}", {1}).string_style == "default"
    assert not caught


@pytest.mark.parametrize("old", [True, False])
@pytest.mark.parametrize("style", ["default", "compact", "inline"])
def test_explicit_conflicts_fail_before_tracing(old, style, monkeypatch):
    ensure = MagicMock()
    monkeypatch.setattr(package.trace_generator, "ensure_jdk_installed", ensure)
    for function, args in (
        (package.render_image, ("class Main {}",)),
        (package.render_images, ("class Main {}", {1})),
        (package.BatchRenderJob, ("class Main {}", {1})),
    ):
        with pytest.raises(TypeError, match="both"):
            function(*args, inline_strings=old, string_style=style)
    ensure.assert_not_called()


@pytest.mark.parametrize("value", [None, 1, [], "other"])
def test_invalid_style(value):
    with pytest.raises(ValueError, match="string_style"):
        resolve_string_style(value)


def test_invalid_legacy_boolean():
    with pytest.raises(TypeError, match="boolean"):
        resolve_string_style(inline_strings=1)


@pytest.mark.parametrize("style", ["default", "compact", "inline"])
@pytest.mark.parametrize("multiple", [False, True])
def test_renderers_keep_identity_and_forward_style(style, multiple, monkeypatch):
    monkeypatch.setattr(package.trace_generator, "ensure_jdk_installed", lambda: Path("jdk"))
    monkeypatch.setattr(package.trace_generator, "ensure_code_tracer_installed", lambda: None)
    trace = MagicMock(return_value=json.dumps({"1": {"code": "", "trace": []}}))
    monkeypatch.setattr(package.trace_generator, "generate_trace", trace)
    render = MagicMock(return_value=b"image")
    if multiple:
        monkeypatch.setattr(package, "_resolve_and_render_trace", render)
        package.render_images("class Main {}", {1}, string_style=style)
    else:
        monkeypatch.setattr(browser_driver, "generate_image", render)
        package.render_image("class Main {}", string_style=style)
    assert trace.call_args.args[3] is False
    assert render.call_args.kwargs["string_style"] == style


def test_manifest_inherits_and_overrides():
    parser = argparse.ArgumentParser()
    add_string_argument(parser)
    assert string_options_from_args(parser.parse_args([])) == {"string_style": "default"}
    args = parser.parse_args(["--string-style", "compact"])
    assert string_options_from_args(args, {}) == {"string_style": "compact"}
    assert string_options_from_args(args, {"string_style": "inline"}) == {"string_style": "inline"}
    with pytest.warns(DeprecationWarning):
        assert string_options_from_args(args, {"inline_strings": False}) == {
            "string_style": "default"
        }
    with pytest.raises(ValueError):
        string_options_from_args(args, {"string_style": None})


def test_invalid_cli_style_before_work(monkeypatch):
    ensure = MagicMock()
    monkeypatch.setattr(cli.trace_generator, "ensure_jdk_installed", ensure)
    with pytest.raises(SystemExit):
        cli.main(["--string-style", "other"])
    ensure.assert_not_called()


def test_html_style():
    html = browser_driver.render_html('{"code":"", "trace":[]}', string_style="compact")
    assert '"stringStyle": "compact"' in html


@pytest.mark.parametrize("all_steps", [False, True])
def test_cli_render_style_and_batch_inheritance(all_steps, monkeypatch, tmp_path):
    monkeypatch.setattr(cli.trace_generator, "ensure_jdk_installed", lambda: None)
    session = MagicMock()
    session.__enter__.return_value = session
    session.generate_trace.return_value = "{}"
    monkeypatch.setattr(cli, "RenderingSession", lambda **kw: session)
    renderer = MagicMock(return_value=[b"image"] if all_steps else b"image")
    monkeypatch.setattr(
        cli if all_steps else cli.browser_driver,
        "generate_step_images" if all_steps else "generate_image",
        renderer,
    )
    manifest = tmp_path / "jobs.ndjson"
    manifest.write_text(
        "\n".join(
            json.dumps(job)
            for job in [
                {"id": "a", "source": "class Main {}", "string_style": "inline"},
                {"id": "b", "source": "class Main {}"},
            ]
        )
    )
    cli.main(
        [
            "--batch",
            "--string-style",
            "compact",
            "-i",
            str(manifest),
            "--out-dir",
            str(tmp_path),
            "--output-pattern",
            "{id}.{step}.png",
        ]
        + (["--all-steps"] if all_steps else [])
    )
    assert [c.kwargs["string_style"] for c in renderer.call_args_list] == ["inline", "compact"]


@pytest.mark.parametrize("command", ["image", "steps", "html", "render_html"])
def test_lower_level_cli_style(command, monkeypatch, tmp_path):
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    args = ["--string-style", "compact"]
    if command in ("html", "render_html"):
        renderer = MagicMock(return_value="<div></div>")
        monkeypatch.setattr(browser_driver, "render_html", renderer)
        if command == "html":
            args.append("--html")
    else:
        renderer = MagicMock(return_value=[b"image"] if command == "steps" else b"image")
        monkeypatch.setattr(
            browser_driver,
            "generate_step_images" if command == "steps" else "generate_image",
            renderer,
        )
        args += ["-o", str(tmp_path / "out.png")]
        if command == "steps":
            args.append("--all-steps")
    monkeypatch.setattr(sys, "argv", ["renderer", *args])
    (browser_driver.render_html_cli if command == "render_html" else browser_driver.main)()
    assert renderer.call_args.kwargs["string_style"] == "compact"


def test_python_batch_requests_canonical_trace(monkeypatch):
    from concurrent.futures import Future

    session = MagicMock(max_browsers=1, tracer_workers=1)
    future = Future()
    future.set_result({"code": "", "trace": [{"line": 1}]})
    session.batch_tracer.submit.return_value = future
    renderer = MagicMock(return_value={1: b"image"})
    monkeypatch.setattr(package, "_resolve_and_render_trace", renderer)
    jobs = [package.BatchRenderJob("class Main {}", {1}, string_style="inline")]
    assert list(package.render_batch_images(jobs, session=session)) == [{1: b"image"}]
    assert session.batch_tracer.submit.call_args.args[0].inline_strings is False
    assert renderer.call_args.kwargs["string_style"] == "inline"


def test_compatibility_signature_has_stable_omitted_defaults():
    import inspect

    signature = str(inspect.signature(package.render_image))
    assert "<omitted>" in signature
    assert "object at 0x" not in signature
