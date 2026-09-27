"""Standalone installers must not import the application or its dependencies."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "script", ["installer/graphviz.py", "installer/jdk.py", "installers/jdk.py"]
)
def test_standalone_help_without_application_imports(tmp_path, script):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / script
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            """
import importlib.abc
import runpy
import sys

class RejectApplicationImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"cs1302_code_visualizer", "selenium", "PIL"}:
            raise AssertionError(f"Standalone installer imported {fullname}")

sys.meta_path.insert(0, RejectApplicationImports())
sys.argv = [sys.argv[1], "--help"]
runpy.run_path(sys.argv[0], run_name="__main__")
""",
            str(script_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Usage:" in result.stdout
