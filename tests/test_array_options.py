"""Array settings across CLI, batch manifests, Python APIs and browser rendering."""

import argparse
import concurrent.futures
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import cs1302_code_visualizer as package
from cs1302_code_visualizer import browser_driver, cli
from cs1302_code_visualizer.array_options import (
    add_array_arguments,
    array_options_from_args,
    validate_array_options,
)

FLAGS = [
    "--array-orientation",
    "vertical",
    "--alternate-array-orientations",
    "--array-orientation-for",
    "4=horizontal",
    "--array-orientation-for",
    "missing=vertical",
]
OPTIONS = {
    "array_orientation": "vertical",
    "alternate_array_orientations": True,
    "array_orientations": {"4": "horizontal", "missing": "vertical"},
}
FIXTURE = Path(__file__).resolve().parents[1] / "docs/array-orientation/fixtures/dimensions.json"


@pytest.mark.parametrize(
    "settings",
    [
        {"array_orientation": "diagonal"},
        {"alternate_array_orientations": "false"},
        {"array_orientations": []},
        {"array_orientations": {"": "vertical"}},
        {"array_orientations": {4: "vertical"}},
        {"array_orientations": {"4": "diagonal"}},
    ],
)
def test_invalid_python_settings(settings):
    with pytest.raises((ValueError, TypeError)):
        validate_array_options(**settings)


def test_parser_defaults_repeated_ids_and_manifest_merge():
    parser = argparse.ArgumentParser()
    add_array_arguments(parser)
    assert array_options_from_args(parser.parse_args([])) == {
        "array_orientation": "horizontal",
        "alternate_array_orientations": False,
        "array_orientations": {},
    }
    args = parser.parse_args(FLAGS + ["--array-orientation-for", "4=vertical"])
    assert array_options_from_args(args)["array_orientations"]["4"] == "vertical"
    merged = array_options_from_args(
        args,
        {
            "array_orientation": "horizontal",
            "alternate_array_orientations": False,
            "array_orientations": {"4": "horizontal", "5": "vertical"},
        },
    )
    assert merged == {
        "array_orientation": "horizontal",
        "alternate_array_orientations": False,
        "array_orientations": {"4": "horizontal", "5": "vertical", "missing": "vertical"},
    }
    assert array_options_from_args(args)["array_orientations"]["4"] == "vertical"


@pytest.mark.parametrize("value", ["4", "=vertical", "4=diagonal", "4=vertical=horizontal"])
def test_bad_cli_override_fails_before_work(value, monkeypatch, capsys):
    trace = MagicMock()
    monkeypatch.setattr(cli.trace_generator, "ensure_jdk_installed", trace)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--array-orientation-for", value])
    assert exc.value.code == 2
    assert "HEAP_ID" in capsys.readouterr().err
    trace.assert_not_called()


@pytest.mark.parametrize("all_steps", [False, True])
def test_source_cli_passes_options(all_steps, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdin", io.StringIO("class Main {}"))
    monkeypatch.setattr(cli.trace_generator, "ensure_jdk_installed", lambda: None)
    monkeypatch.setattr(cli.trace_generator, "ensure_code_tracer_installed", lambda: None)
    monkeypatch.setattr(cli.trace_generator, "generate_trace", lambda *a, **kw: "{}")
    renderer = MagicMock(return_value=[b"image"] if all_steps else b"image")
    if all_steps:
        monkeypatch.setattr(cli, "generate_step_images", renderer)
    else:
        monkeypatch.setattr(cli.browser_driver, "generate_image", renderer)
    cli.main(FLAGS + (["--all-steps"] if all_steps else []) + ["-o", str(tmp_path / "out.png")])
    assert {key: renderer.call_args.kwargs[key] for key in OPTIONS} == OPTIONS


@pytest.mark.parametrize("command", ["image", "steps", "html", "render_html"])
def test_trace_clis_pass_options(command, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    args = FLAGS.copy()
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
    assert {key: renderer.call_args.kwargs[key] for key in OPTIONS} == OPTIONS


@pytest.mark.parametrize(
    "job",
    [
        [],
        {"array_orientations": None},
        {"array_orientations": []},
        {"array_orientation": "diagonal"},
        {"alternate_array_orientations": "false"},
    ],
)
def test_manifest_validation_precedes_all_tracing(job, monkeypatch, tmp_path, capsys):
    manifest = tmp_path / "jobs.ndjson"
    manifest.write_text(
        json.dumps({"id": "valid", "source": "class Main {}"}) + "\n" + json.dumps(job)
    )
    ensure = MagicMock()
    monkeypatch.setattr(cli.trace_generator, "ensure_jdk_installed", ensure)
    with pytest.raises(SystemExit):
        cli.main(["--batch", "--keep-going", "-i", str(manifest)])
    assert "line 2" in capsys.readouterr().err
    ensure.assert_not_called()


@pytest.mark.parametrize("all_steps", [False, True])
def test_manifest_settings_reach_renderer(all_steps, monkeypatch, tmp_path):
    manifest = tmp_path / "jobs.ndjson"
    manifest.write_text(
        json.dumps({
            "id": "one",
            "source": "class Main {}",
            "alternate_array_orientations": False,
            "array_orientations": {"4": "vertical"},
        })
        + "\n"
        + json.dumps({"id": "two", "source": "class Main {}"})
    )
    monkeypatch.setattr(cli.trace_generator, "ensure_jdk_installed", lambda: None)
    monkeypatch.setattr(cli.trace_generator, "ensure_code_tracer_installed", lambda: None)
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
    cli.main(
        FLAGS
        + [
            "--batch",
            "-i",
            str(manifest),
            "--out-dir",
            str(tmp_path),
            "--output-pattern",
            "{id}.{step}.png",
        ]
        + (["--all-steps"] if all_steps else [])
    )
    first, second = renderer.call_args_list
    assert first.kwargs["array_orientation"] == "vertical"
    assert first.kwargs["alternate_array_orientations"] is False
    assert first.kwargs["array_orientations"] == {"4": "vertical", "missing": "vertical"}
    assert {key: second.kwargs[key] for key in OPTIONS} == OPTIONS


def test_html_embeds_settings_and_escapes_heap_ids():
    html = browser_driver.render_html(FIXTURE.read_text(), **OPTIONS)
    assert '"arrayOrientation": "vertical"' in html
    assert '"alternateArrayOrientations": true' in html
    assert '"arrayOrientations": {"4": "horizontal", "missing": "vertical"}' in html
    html = browser_driver.render_html(
        FIXTURE.read_text(), array_orientations={"</script>": "vertical"}
    )
    assert '"<\\/script>"' in html


@pytest.mark.parametrize("all_occurrences", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_python_breakpoint_rendering_forwards_settings(all_occurrences, legacy, monkeypatch):
    trace = FIXTURE.read_text()
    if legacy:
        trace = json.dumps({
            "5": [json.loads(trace), json.loads(trace)] if all_occurrences else json.loads(trace)
        })
    renderer = MagicMock(return_value=b"image")
    monkeypatch.setattr(browser_driver, "generate_image", renderer)
    package._resolve_and_render_trace(
        trace, {5} if legacy else {-1}, render_all_occurrences=all_occurrences, **OPTIONS
    )
    calls = renderer.call_args_list
    assert calls
    for call in calls:
        assert {key: call.kwargs[key] for key in OPTIONS} == OPTIONS


def test_batch_job_validates_options():
    with pytest.raises(ValueError, match="array_orientation"):
        package.BatchRenderJob("class Main {}", {-1}, array_orientation="diagonal")


@pytest.mark.parametrize("multiple", [False, True])
def test_source_python_apis_forward_settings(multiple, monkeypatch):
    monkeypatch.setattr(package.trace_generator, "ensure_jdk_installed", lambda: None)
    monkeypatch.setattr(package.trace_generator, "ensure_code_tracer_installed", lambda: None)
    monkeypatch.setattr(
        package.trace_generator,
        "generate_trace",
        lambda *a, **kw: json.dumps({"1": json.loads(FIXTURE.read_text())}),
    )
    renderer = MagicMock(return_value=b"image")
    monkeypatch.setattr(browser_driver, "generate_image", renderer)
    if multiple:
        package.render_images("class Main {}", {1}, **OPTIONS)
    else:
        package.render_image("class Main {}", **OPTIONS)
    assert {key: renderer.call_args.kwargs[key] for key in OPTIONS} == OPTIONS


def test_python_batch_job_forwards_settings(monkeypatch):
    session = MagicMock(max_browsers=1, tracer_workers=1)
    future = concurrent.futures.Future()
    future.set_result(json.loads(FIXTURE.read_text()))
    session.batch_tracer.submit.return_value = future
    renderer = MagicMock(return_value=b"image")
    monkeypatch.setattr(browser_driver, "generate_image", renderer)
    jobs = [package.BatchRenderJob("class Main {}", {-1}, **OPTIONS)]
    assert list(package.render_batch_images(jobs, session=session)) == [{-1: b"image"}]
    assert {key: renderer.call_args.kwargs[key] for key in OPTIONS} == OPTIONS


@pytest.mark.parametrize("steps", [1, 2])
def test_image_apis_forward_options_to_browser(steps, monkeypatch):
    trace = json.loads(FIXTURE.read_text())
    trace["trace"] = trace["trace"][:steps]
    frontend = MagicMock()
    frontend.__enter__.return_value = {"driver": MagicMock(), "dataViz": MagicMock()}
    factory = MagicMock(return_value=frontend)
    monkeypatch.setattr(browser_driver, "online_python_tutor_frontend", factory)
    monkeypatch.setattr(browser_driver, "_capture_viz", lambda *a, **kw: b"image")
    assert browser_driver.generate_step_images(json.dumps(trace), **OPTIONS) == [b"image"] * steps
    assert {key: factory.call_args.kwargs[key] for key in OPTIONS} == OPTIONS


def test_browser_uses_options_across_steps(rendering_session):
    with browser_driver.online_python_tutor_frontend(
        FIXTURE.read_text(),
        session=rendering_session,
        **OPTIONS,
    ) as frontend:
        driver = frontend["driver"]
        for step in [0, 1, 0]:
            driver.execute_script("window.optFrontend.renderStep(arguments[0])", step)
            classes = driver.execute_script("""return [1,2,4].map(id =>
                document.querySelector(`.heapObject[id$="_heap_object_${id}"] > table`).className)""")
            assert ["array-vertical" in c for c in classes] == [True, False, False]
