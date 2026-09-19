"""Tests for cs1302_code_visualizer.cli."""

import argparse
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cs1302_code_visualizer.cli import (
    AtomicJobWriter,
    format_output_path,
    main,
    run_batch_cli,
    run_single_cli,
    validate_pattern,
)


def test_format_output_path_placeholders(tmp_path: Path):
    source = Path("pkg/sub/Driver.java")
    out = format_output_path(
        "{dirname}/{basename}.{step}.{format}",
        out_dir=tmp_path,
        job_id="my_job",
        source_path=source,
        step=3,
        line=15,
        format="PNG",
    )
    assert out == tmp_path / "pkg/sub" / "Driver.3.png"

    # Line formatting and source with current dir parent "."
    source_root = Path("Main.java")
    out2 = format_output_path(
        "{dirname}{basename}_{line}.{format}",
        source_path=source_root,
        line=42,
        format="png",
    )
    assert out2 == Path("Main_L42.png")

    # Absolute path pattern should not be prepended with out_dir
    abs_pattern = str(tmp_path / "custom_{id}.json")
    out_abs = format_output_path(abs_pattern, out_dir=tmp_path / "ignored", job_id="test1")
    assert out_abs == tmp_path / "custom_test1.json"


def test_validate_pattern():
    # Multi-step requires {step} or {line}
    validate_pattern("{basename}.{step}.png", multi_step=True)
    validate_pattern("{basename}_{line}.png", multi_step=True)

    with pytest.raises(ValueError, match=r"must contain '\{step\}' or '\{line\}'"):
        validate_pattern("{basename}.png", multi_step=True)

    # Single-step allows anything
    validate_pattern("{basename}.png", multi_step=False)


def test_atomic_job_writer_commit(tmp_path: Path):
    target = tmp_path / "subdir" / "result.png"
    writer = AtomicJobWriter(force=False)

    temp_p = writer.stage_file(target, b"IMG_DATA")
    assert temp_p.exists()
    assert not target.exists()

    committed = writer.commit()
    assert committed == [target]
    assert target.exists()
    assert target.read_bytes() == b"IMG_DATA"
    assert not temp_p.exists()

    # Once committed, cleanup does nothing
    writer.cleanup()
    assert target.exists()


def test_atomic_job_writer_text_and_force(tmp_path: Path):
    target = tmp_path / "trace.json"
    target.write_text("OLD", encoding="utf-8")

    writer_no_force = AtomicJobWriter(force=False)
    with pytest.raises(FileExistsError, match="Use --force to overwrite"):
        writer_no_force.stage_file(target, "NEW")

    writer_force = AtomicJobWriter(force=True)
    writer_force.stage_file(target, "NEW")
    writer_force.commit()
    assert target.read_text(encoding="utf-8") == "NEW"


def test_atomic_job_writer_cleanup_on_failure(tmp_path: Path):
    target = tmp_path / "result.png"
    writer = AtomicJobWriter(force=False)
    temp_p = writer.stage_file(target, b"TEMP")

    assert temp_p.exists()
    writer.cleanup()
    assert not temp_p.exists()
    assert not target.exists()


def test_atomic_job_writer_cleanup_oserror(tmp_path: Path, monkeypatch):
    target = tmp_path / "result.png"
    writer = AtomicJobWriter(force=False)
    _ = writer.stage_file(target, b"TEMP")

    def mock_unlink(self, missing_ok=False):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "unlink", mock_unlink)
    # Should not raise exception
    writer.cleanup()


def test_run_batch_cli_invalid_pattern(capsys):
    args = argparse.Namespace(
        all_steps=True,
        breakpoints=[],
        output_pattern="{basename}.png",
        out_dir=None,
    )

    code = run_batch_cli(args)
    assert code == 2
    captured = capsys.readouterr()
    assert "must contain '{step}' or '{line}'" in captured.err


def test_run_batch_cli_input_dir_not_found(capsys):
    args = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        out_dir=None,
        input_dir="non_existent_directory_12345",
        files=[],
        input=None,
    )

    code = run_batch_cli(args)
    assert code == 1
    captured = capsys.readouterr()
    assert "Input directory not found" in captured.err


def test_run_batch_cli_input_dir_read_error(tmp_path: Path, monkeypatch, capsys):
    f = tmp_path / "Test.java"
    f.write_text("class Test {}", encoding="utf-8")

    args = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        out_dir=None,
        input_dir=str(tmp_path),
        files=[],
        input=None,
    )

    def mock_read_text(self, encoding="utf-8"):
        raise OSError("Read failed")

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    code = run_batch_cli(args)
    assert code == 1
    captured = capsys.readouterr()
    assert "Error reading" in captured.err


def test_run_batch_cli_files_not_found_and_read_error(tmp_path: Path, monkeypatch, capsys):
    args1 = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        out_dir=None,
        input_dir=None,
        files=["non_existent_file.java"],
        input=None,
    )

    assert run_batch_cli(args1) == 1

    f = tmp_path / "A.java"
    f.write_text("class A {}", encoding="utf-8")

    args2 = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        out_dir=None,
        input_dir=None,
        files=[str(f)],
        input=None,
    )

    def mock_read_text(self, encoding="utf-8"):
        raise OSError("Read fail")

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    assert run_batch_cli(args2) == 1


def test_run_batch_cli_manifest_not_found_and_decode_error(tmp_path: Path, capsys):
    args1 = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        out_dir=None,
        input_dir=None,
        files=[],
        input="non_existent_manifest.ndjson",
    )

    assert run_batch_cli(args1) == 1

    bad_manifest = tmp_path / "bad.ndjson"
    bad_manifest.write_text("NOT_JSON\n", encoding="utf-8")

    args2 = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        out_dir=None,
        input_dir=None,
        files=[],
        input=str(bad_manifest),
    )

    assert run_batch_cli(args2) == 1


def test_run_batch_cli_no_jobs(capsys):
    args = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        out_dir=None,
        input_dir=None,
        files=[],
        input=None,
    )

    assert run_batch_cli(args) == 1
    assert "No Java sources found" in capsys.readouterr().err


def test_run_batch_cli_success_all_steps_and_trace_pattern(tmp_path: Path):
    f1 = tmp_path / "Test1.java"
    f1.write_text("class Test1 {}", encoding="utf-8")

    out_dir = tmp_path / "out"

    args = argparse.Namespace(
        all_steps=True,
        breakpoints=[4],
        output_pattern="{dirname}/{basename}.{step}.png",
        trace_pattern="{dirname}/{basename}.json",
        out_dir=str(out_dir),
        input_dir=str(tmp_path),
        files=[],
        input=None,
        browsers=2,
        workers=1,
        dpi=1,
        format="PNG",
        force=True,
        include_types=True,
        text_memory_labels=False,
        strip_type_prefixes=None,
        keep_going=False,
    )

    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.generate_trace.return_value = json.dumps({"trace": [{"line": 4}]})

    with (
        patch("cs1302_code_visualizer.cli.RenderingSession", return_value=mock_session),
        patch(
            "cs1302_code_visualizer.cli.trace_generator.ensure_jdk_installed",
            return_value=Path("/jdk"),
        ),
        patch("cs1302_code_visualizer.cli.trace_generator.ensure_code_tracer_installed"),
        patch(
            "cs1302_code_visualizer.cli.generate_step_images",
            return_value=[b"STEP0_IMG", b"STEP1_IMG"],
        ),
    ):
        code = run_batch_cli(args)
        assert code == 0
        assert (out_dir / "Test1.0.png").read_bytes() == b"STEP0_IMG"
        assert (out_dir / "Test1.1.png").read_bytes() == b"STEP1_IMG"
        assert (out_dir / "Test1.json").exists()


def test_run_batch_cli_positional_files_success(tmp_path: Path):
    f1 = tmp_path / "Pos.java"
    f1.write_text("class Pos {}", encoding="utf-8")
    out_dir = tmp_path / "out"

    args = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        trace_pattern=None,
        out_dir=str(out_dir),
        input_dir=None,
        files=[str(f1)],
        input=None,
        browsers=1,
        workers=1,
        dpi=1,
        format="PNG",
        force=True,
        include_types=True,
        text_memory_labels=False,
        strip_type_prefixes=None,
        keep_going=False,
    )

    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.generate_trace.return_value = "{}"

    with (
        patch("cs1302_code_visualizer.cli.RenderingSession", return_value=mock_session),
        patch(
            "cs1302_code_visualizer.cli.trace_generator.ensure_jdk_installed",
            return_value=Path("/jdk"),
        ),
        patch("cs1302_code_visualizer.cli.trace_generator.ensure_code_tracer_installed"),
        patch(
            "cs1302_code_visualizer.cli.browser_driver.generate_image",
            return_value=b"POS_IMG",
        ),
    ):
        code = run_batch_cli(args)
        assert code == 0
        assert (out_dir / "Pos.png").read_bytes() == b"POS_IMG"


def test_run_batch_cli_fail_no_keep_going(tmp_path: Path):
    f1 = tmp_path / "Fail.java"
    f1.write_text("class Fail {}", encoding="utf-8")

    args = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{basename}.png",
        trace_pattern=None,
        out_dir=None,
        input_dir=None,
        files=[str(f1)],
        input=None,
        browsers=1,
        workers=1,
        dpi=1,
        format="PNG",
        force=True,
        include_types=True,
        text_memory_labels=False,
        strip_type_prefixes=None,
        keep_going=False,
    )

    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.generate_trace.side_effect = RuntimeError("Fatal error")

    with (
        patch("cs1302_code_visualizer.cli.RenderingSession", return_value=mock_session),
        patch(
            "cs1302_code_visualizer.cli.trace_generator.ensure_jdk_installed",
            return_value=Path("/jdk"),
        ),
        patch("cs1302_code_visualizer.cli.trace_generator.ensure_code_tracer_installed"),
    ):
        code = run_batch_cli(args)
        assert code == 1


def test_run_batch_cli_single_step_manifest_keep_going(tmp_path: Path):
    manifest = tmp_path / "jobs.ndjson"
    manifest.write_text(
        json.dumps({"id": "j1", "source": "class J1 {}", "breakpoints": [5]})
        + "\n\n"
        + json.dumps({"id": "j2", "source": "class J2 {}"})
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    args = argparse.Namespace(
        all_steps=False,
        breakpoints=[],
        output_pattern="{id}.png",
        trace_pattern=None,
        out_dir=str(out_dir),
        input_dir=None,
        files=[],
        input=str(manifest),
        browsers=1,
        workers=1,
        dpi=1,
        format="PNG",
        force=True,
        include_types=True,
        text_memory_labels=False,
        strip_type_prefixes=None,
        keep_going=True,
    )

    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.generate_trace.side_effect = ["trace1", RuntimeError("Trace failed")]

    with (
        patch("cs1302_code_visualizer.cli.RenderingSession", return_value=mock_session),
        patch(
            "cs1302_code_visualizer.cli.trace_generator.ensure_jdk_installed",
            return_value=Path("/jdk"),
        ),
        patch("cs1302_code_visualizer.cli.trace_generator.ensure_code_tracer_installed"),
        patch("cs1302_code_visualizer.cli.browser_driver.generate_image", return_value=b"J1_IMG"),
    ):
        code = run_batch_cli(args)
        assert code == 1  # 1 out of 2 failed, so exit code 1
        assert (out_dir / "j1.png").read_bytes() == b"J1_IMG"
        assert not (out_dir / "j2.png").exists()


def test_run_single_cli_file_read_error(monkeypatch):
    args1 = argparse.Namespace(files=["Test.java"], input=None)

    def mock_read_text(self, encoding="utf-8"):
        raise OSError("Read err")

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    assert run_single_cli(args1) == 1

    args2 = argparse.Namespace(files=[], input="Test.java")
    assert run_single_cli(args2) == 1


def test_run_single_cli_all_steps(tmp_path: Path):
    out_file = tmp_path / "output.png"

    args = argparse.Namespace(
        files=[],
        input="-",
        breakpoints=[4],
        all_steps=True,
        output=str(out_file),
        dpi=1,
        format="PNG",
        include_types=True,
        text_memory_labels=False,
        strip_type_prefixes=None,
    )

    with (
        patch("sys.stdin.read", return_value="class A {}"),
        patch(
            "cs1302_code_visualizer.cli.trace_generator.ensure_jdk_installed",
            return_value=Path("/jdk"),
        ),
        patch("cs1302_code_visualizer.cli.trace_generator.ensure_code_tracer_installed"),
        patch("cs1302_code_visualizer.cli.trace_generator.generate_trace", return_value="{}"),
        patch("cs1302_code_visualizer.cli.generate_step_images", return_value=[b"S0", b"S1"]),
    ):
        code = run_single_cli(args)
        assert code == 0
        assert (tmp_path / "output.0.png").read_bytes() == b"S0"
        assert (tmp_path / "output.1.png").read_bytes() == b"S1"
        assert out_file.read_bytes() == b"S1"

    # Missing output when all_steps=True
    args.output = None
    with (
        patch("sys.stdin.read", return_value="class A {}"),
        patch(
            "cs1302_code_visualizer.cli.trace_generator.ensure_jdk_installed",
            return_value=Path("/jdk"),
        ),
        patch("cs1302_code_visualizer.cli.trace_generator.ensure_code_tracer_installed"),
        patch("cs1302_code_visualizer.cli.trace_generator.generate_trace", return_value="{}"),
        patch("cs1302_code_visualizer.cli.generate_step_images", return_value=[]),
    ):
        assert run_single_cli(args) == 1


def test_run_single_cli_single_step(tmp_path: Path):
    out_file = tmp_path / "single.png"

    args = argparse.Namespace(
        files=[],
        input="-",
        breakpoints=[],
        all_steps=False,
        output=str(out_file),
        dpi=1,
        format="PNG",
        include_types=True,
        text_memory_labels=False,
        strip_type_prefixes=None,
    )

    with (
        patch("sys.stdin.read", return_value="class A {}"),
        patch(
            "cs1302_code_visualizer.cli.trace_generator.ensure_jdk_installed",
            return_value=Path("/jdk"),
        ),
        patch("cs1302_code_visualizer.cli.trace_generator.ensure_code_tracer_installed"),
        patch("cs1302_code_visualizer.cli.trace_generator.generate_trace", return_value="{}"),
        patch(
            "cs1302_code_visualizer.cli.browser_driver.generate_image", return_value=b"SINGLE_IMG"
        ),
    ):
        code = run_single_cli(args)
        assert code == 0
        assert out_file.read_bytes() == b"SINGLE_IMG"

        # Output to stdout buffer
        args.output = None
        mock_stdout = MagicMock()
        with patch("sys.stdout.buffer.write", mock_stdout):
            code = run_single_cli(args)
            assert code == 0
            mock_stdout.assert_called_with(b"SINGLE_IMG")


def test_main_entry_point():
    with patch("cs1302_code_visualizer.cli.run_single_cli", return_value=0) as mock_single:
        main(["file.java"])
        mock_single.assert_called_once()

    with patch("cs1302_code_visualizer.cli.run_batch_cli", return_value=0) as mock_batch:
        main(["--batch", "file.java"])
        mock_batch.assert_called_once()

    with (
        patch("cs1302_code_visualizer.cli.run_batch_cli", return_value=1),
        pytest.raises(SystemExit) as exc_info,
    ):
        main(["--batch", "file.java"])
    assert exc_info.value.code == 1


def test_cli_module_main_execution(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["code-visualizer", "--batch"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("cs1302_code_visualizer.cli", run_name="__main__")
    assert exc_info.value.code == 1
