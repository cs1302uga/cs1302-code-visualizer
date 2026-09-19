import json
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

from examples import run_batch


def make_example(root, index, arguments="", filename="Driver.java"):
    directory = root / f"example{index}"
    source = directory / filename
    source.parent.mkdir(parents=True)
    source.write_text(str(index))
    (directory / "test.sh").write_text(f'../test.sh "$@" {filename} {arguments}\n')
    return source


@pytest.fixture
def fake_runtime(monkeypatch):
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=None)
    session.generate_trace.side_effect = lambda home, source, **kwargs: json.dumps({"id": source})
    factory = Mock(return_value=session)
    monkeypatch.setattr(run_batch, "RenderingSession", factory)
    monkeypatch.setattr(run_batch, "ensure_jdk_installed", lambda: Path("/jdk"))
    monkeypatch.setattr(run_batch, "generate_step_images", lambda *a, **k: [b"first", b"last"])
    return session, factory


def run_examples(root, **kwargs):
    return run_batch.run_batch_examples(
        root, rm_json=False, rm_image=False, open_image=False, **kwargs
    )


def test_trace_options_preserve_supported_and_legacy_flags(tmp_path):
    options = run_batch._trace_options([
        "-b=6,7", "--accumulate-breakpoints", "--stdin", "hello world",
        "--format=modern", "--type-style=fqn", "--trace-timeout=2",
        "--include-enum-static-fields", "--inline-strings", "--no-eval-enum-hash",
    ], tmp_path)
    assert options == {
        "breakpoints": {6, 7}, "all_breakpoints": False,
        "accumulate_breakpoints": True, "stdin": "hello world",
        "stdin_file": None, "extra_tracer_args": ["--format=modern"],
        "type_style": "fqn", "timeout_secs": 2.0,
        "include_enum_static_fields": True, "inline_strings": True,
        "eval_enum_hash": False,
    }
    assert run_batch._trace_options([], tmp_path)["all_breakpoints"] is True
    assert run_batch._trace_options(["-a", "-b", "4"], tmp_path)["all_breakpoints"] is True
    assert run_batch._trace_options(["--stdin-file", "in.txt"], tmp_path)["stdin_file"] == (
        tmp_path / "in.txt"
    )


def test_examples_reuse_session_and_preserve_outputs(tmp_path, fake_runtime):
    session, factory = fake_runtime
    first = make_example(tmp_path, 0, '--stdin "hello world"')
    second = make_example(tmp_path, 1, "--format=modern -b=6", "nested/Driver.java")
    assert run_examples(tmp_path, max_browsers=2, tracer_workers=3) == 0
    factory.assert_called_once_with(max_browsers=2, tracer_workers=3, use_batch_tracer=True)
    session.__exit__.assert_called_once()
    assert session.generate_trace.call_count == 2
    by_source = {call.args[1]: call.kwargs for call in session.generate_trace.call_args_list}
    assert by_source["0"]["stdin"] == "hello world"
    assert by_source["1"]["extra_tracer_args"] == ["--format=modern"]
    assert by_source["1"]["breakpoints"] == {6}
    for source in [first, second]:
        assert Path(f"{source}.json").exists()
        assert Path(f"{source}.png").read_bytes() == b"last"
        assert Path(f"{source}.0.png").read_bytes() == b"first"
        assert Path(f"{source}.1.png").read_bytes() == b"last"


def test_examples_render_concurrently(tmp_path, fake_runtime, monkeypatch):
    session, _ = fake_runtime
    for index in range(4):
        make_example(tmp_path, index)
    barrier = threading.Barrier(2)
    rendered = []
    lock = threading.Lock()

    def render(trace, **kwargs):
        assert kwargs["session"] is session
        barrier.wait(timeout=3)
        with lock:
            rendered.append(trace)
        return [b"image"]

    monkeypatch.setattr(run_batch, "generate_step_images", render)
    assert run_examples(tmp_path, max_browsers=2, tracer_workers=2) == 0
    assert len(rendered) == 4


def test_examples_open_and_cleanup_nested_outputs(tmp_path, fake_runtime, monkeypatch):
    source = make_example(tmp_path, 0, filename="nested/Driver.java")
    Path(f"{source}.99.png").write_bytes(b"stale")
    opened = Mock()
    monkeypatch.setattr(run_batch, "open_files", opened)
    assert run_batch.run_batch_examples(
        tmp_path, rm_json=True, rm_image=True, open_image=True
    ) == 0
    opened.assert_called_once_with([Path(f"{source}.0.png"), Path(f"{source}.1.png")])
    assert not list(source.parent.glob("*.png"))
    assert not list(source.parent.glob("*.json"))


@pytest.mark.parametrize("stage", ["trace", "render"])
def test_examples_failure_closes_session(tmp_path, fake_runtime, monkeypatch, capsys, stage):
    session, _ = fake_runtime
    make_example(tmp_path, 0)
    failure = Mock(side_effect=RuntimeError(f"{stage} failed"))
    if stage == "trace":
        session.generate_trace.side_effect = failure
    else:
        monkeypatch.setattr(run_batch, "generate_step_images", failure)
    assert run_examples(tmp_path) == 1
    assert f"{stage} failed" in capsys.readouterr().err
    session.__exit__.assert_called_once()


def test_examples_skip_bad_configuration(tmp_path, fake_runtime, capsys):
    directory = tmp_path / "example0"
    directory.mkdir()
    (directory / "test.sh").write_text("echo no command")
    assert run_examples(tmp_path) == 0
    assert "skipping example0" in capsys.readouterr().err


def test_examples_empty_images_preserve_existing_final(tmp_path, fake_runtime, monkeypatch):
    source = make_example(tmp_path, 0)
    final = Path(f"{source}.png")
    final.write_bytes(b"existing")
    monkeypatch.setattr(run_batch, "generate_step_images", lambda *a, **k: [])
    assert run_examples(tmp_path) == 0
    assert final.read_bytes() == b"existing"
