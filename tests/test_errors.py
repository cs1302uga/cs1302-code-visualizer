import pytest
from subprocess import CalledProcessError
from cs1302_code_visualizer.errors import (
    CodeVisError,
    CodeVisTraceGeneratorError,
    CodeVisRenderError,
)


def test_code_vis_error():
    err = CodeVisError("Test message")
    assert str(err) == "Test message"


def test_code_vis_render_error():
    err = CodeVisRenderError("Render failure")
    assert str(err) == "Render failure"
    assert isinstance(err, CodeVisError)


def test_code_vis_trace_generator_error():
    err = CodeVisTraceGeneratorError(
        source_code="class Driver {}",
        cli_args=["-v"],
        stdout="out",
        stderr="err",
        exit_status=1,
    )
    assert isinstance(err, CodeVisError)
    assert err.source_code == "class Driver {}"
    assert err.cli_args == ["-v"]
    assert err.stdout == "out"
    assert err.stderr == "err"
    assert err.exit_status == 1


def test_code_vis_trace_generator_error_null_streams():
    err = CodeVisTraceGeneratorError(
        source_code="class Driver {}",
        cli_args=["-v"],
        stdout=None,
        stderr=None,
        exit_status=1,
    )
    assert err.stdout == ""
    assert err.stderr == ""


def test_code_vis_trace_generator_error_from_cpe():
    cpe = CalledProcessError(1, ["java"], output="out", stderr="err")
    err = CodeVisTraceGeneratorError.from_cpe(cpe, "source", ["-v"])
    assert err.source_code == "source"
    assert err.cli_args == ["-v"]
    assert err.stdout == "out"
    assert err.stderr == "err"
    assert err.exit_status == 1
