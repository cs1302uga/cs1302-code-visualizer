import io
import sys
import json
import runpy
import pytest
from unittest.mock import patch

from cs1302_code_visualizer.breakpoint_lister import (
    list_breakpoints,
    list_breakpoints_json,
    main as lister_main,
)
from cs1302_code_visualizer.trace_generator import ensure_jdk_installed

SAMPLE_JAVA = """
public class Driver {
    public static void main(String[] args) {
        int a = 1;
    }
}
"""


def test_list_breakpoints_none_java_home():
    output = list_breakpoints(SAMPLE_JAVA, java_home=None, output_json=False)
    assert isinstance(output, str)
    assert "Driver" in output or "main" in output


def test_list_breakpoints_tracer_error():
    java_home = ensure_jdk_installed()
    with patch(
        "cs1302_code_visualizer.trace_generator.ensure_code_tracer_installed",
        side_effect=Exception("Tracer fail"),
    ):
        with pytest.raises(Exception, match="Unable to ensure code tracer is installed!"):
            list_breakpoints(SAMPLE_JAVA, java_home=java_home)


def test_list_breakpoints_json_format():
    java_home = ensure_jdk_installed()
    res = list_breakpoints_json(SAMPLE_JAVA, java_home=java_home)
    assert isinstance(res, list)
    assert len(res) > 0


def test_list_breakpoints_command_arguments():
    java_home = ensure_jdk_installed()
    with patch("subprocess.check_output", return_value="breakpoints output") as mock_check_output:
        res = list_breakpoints(SAMPLE_JAVA, java_home=java_home)
        assert res == "breakpoints output"
        cmd = mock_check_output.call_args[0][0]
        assert "--enable-native-access=ALL-UNNAMED" in cmd


def test_lister_main_stdout(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_JAVA))
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    monkeypatch.setattr("sys.argv", ["list_breakpoints", "-v"])
    lister_main()
    out = captured.getvalue()
    assert len(out) > 0


def test_lister_main_file_output(tmp_path, monkeypatch):
    out_file = tmp_path / "breakpoints.txt"
    java_home = ensure_jdk_installed()
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_JAVA))
    monkeypatch.setattr(
        "sys.argv",
        [
            "list_breakpoints",
            "-o",
            str(out_file),
            "-j",
            "--jdk",
            str(java_home),
            "--trace-timeout",
            "10",
        ],
    )
    lister_main()
    assert out_file.exists()
    content = out_file.read_text()
    assert len(content) > 0


def test_lister_main_error_exit(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("invalid java {{{"))
    monkeypatch.setattr("sys.argv", ["list_breakpoints"])
    with pytest.raises(SystemExit):
        lister_main()


def test_lister_runpy_main(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_JAVA))
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    monkeypatch.setattr("sys.argv", ["list_breakpoints"])
    runpy.run_module("cs1302_code_visualizer.breakpoint_lister", run_name="__main__")
    assert len(captured.getvalue()) > 0
