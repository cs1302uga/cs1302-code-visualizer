"""Standalone installers must not import the application or its dependencies."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "script",
    [
        "install_deps.py",
        "installer/enchant.py",
        "installer/graphviz.py",
        "installer/jdk.py",
        "installer/plantuml.py",
        "installer/uv.py",
        "installers/jdk.py",
    ],
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


def test_archive_helper_supports_installed_layout_without_application_imports(tmp_path):
    """The standalone helper uses installed source without initializing the app."""
    root = Path(__file__).resolve().parents[1]
    site_packages = tmp_path / "site-packages"
    for relative in (
        "scripts/installer/archives.py",
        "cs1302_code_visualizer/util/archives.py",
    ):
        destination = site_packages / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((root / relative).read_bytes())
    exported = site_packages / "scripts" / "installer" / "archives.py"
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
            raise AssertionError(f"Standalone helper imported {fullname}")

sys.meta_path.insert(0, RejectApplicationImports())
helper = runpy.run_path(sys.argv[1])
assert callable(helper["extract_zip"])
""",
            str(exported),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
