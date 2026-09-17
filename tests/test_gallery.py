"""Regression tests for complete, portable gallery generation."""

import json
from unittest.mock import MagicMock, patch

from cs1302_code_visualizer import browser_driver


def test_modern_step_images_include_every_step():
    trace = json.dumps({"format": "modern", "code": "", "steps": [{"line": 1}, {"line": 2}]})
    frontend = MagicMock()
    frontend.__enter__.return_value = {"driver": MagicMock(), "dataViz": MagicMock()}
    with (
        patch.object(browser_driver, "online_python_tutor_frontend", return_value=frontend),
        patch.object(browser_driver, "_capture_viz", side_effect=[b"first", b"second"]),
        patch.object(browser_driver, "generate_image", return_value=b"last only"),
    ):
        assert browser_driver.generate_step_images(trace) == [b"first", b"second"]
    driver = frontend.__enter__.return_value["driver"]
    assert [c.args[0] for c in driver.execute_script.call_args_list] == [
        "window.optFrontend.renderStep(0);",
        "window.optFrontend.renderStep(1);",
    ]


def test_gallery_preserves_accumulated_and_modern_steps():
    from scripts.build_gallery_data import trace_sequences

    first = {"trace": [{"line": 6, "stdout": "first"}]}
    second = {"trace": [{"line": 6, "stdout": "second"}]}
    assert trace_sequences({"6": [first, second]}) == [first, second]
    modern = {"format": "modern", "steps": [{"line": 1}, {"line": 2}]}
    assert trace_sequences(modern) == [modern]
    assert trace_sequences({"29": first}) == [first]


def test_gallery_renders_all_hits_without_deleting_existing_artifacts(tmp_path, monkeypatch):
    from scripts import build_gallery_data as gallery

    example = tmp_path / "examples" / "example0"
    example.mkdir(parents=True)
    source = example / "Driver.java"
    source.write_text("class Driver {}")
    (example / "Helper.java").write_text("class Helper {}")
    (example / "test.sh").write_text('../test.sh "$@" Driver.java -b=6 --accumulate-breakpoints\n')
    (example / "README.md").write_text("# Loop\n\n## Concepts Illustrated\n- Accumulation\n")
    saved = example / "saved.png"
    saved.write_bytes(b"keep image")
    saved_json = example / "saved.json"
    saved_json.write_text('{"keep": true}')
    artifacts = tmp_path / "artifacts"
    (artifacts / "gallery_images").mkdir(parents=True)
    (artifacts / "traces").mkdir()
    payload = {
        "6": [
            {"trace": [{"line": 6, "func_name": "main", "stdout": "first"}]},
            {"trace": [{"line": 6, "func_name": "main", "stdout": "second"}]},
        ]
    }
    run = MagicMock(return_value=MagicMock(stdout=json.dumps(payload)))
    monkeypatch.setattr(gallery, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gallery.subprocess, "run", run)
    monkeypatch.setattr(gallery, "RenderingSession", MagicMock())
    render = MagicMock(side_effect=[[b"first image"], [b"second image"]])
    monkeypatch.setattr(gallery, "generate_step_images", render)
    java_home = tmp_path / "jdk25"
    metadata = gallery.build_example(0, artifacts, java_home, 2)
    assert metadata["step_count"] == 2
    assert [step["line"] for step in metadata["steps"]] == [6, 6]
    assert [src["path"] for src in metadata["sources"]] == ["Driver.java", "Helper.java"]
    assert (artifacts / "gallery_images" / "example0_1.png").read_bytes() == b"second image"
    assert saved.read_bytes() == b"keep image"
    assert saved_json.read_text() == '{"keep": true}'
    assert json.loads((artifacts / "traces" / "example0.json").read_text()) == payload
    assert run.call_args.kwargs["cwd"] == example
    assert str(java_home) in run.call_args.args[0]
    assert "-a" not in run.call_args.args[0]
