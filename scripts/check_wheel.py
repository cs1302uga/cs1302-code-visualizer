"""Smoke-test the built wheel's installer commands outside the checkout."""

from __future__ import annotations

import argparse
import configparser
import email
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

from packaging.requirements import Requirement

INSTALLER_COMMANDS = (
    "install-deps",
    "install-enchant",
    "install-graphviz",
    "install-jdk",
    "install-plantuml",
    "install-uv",
)

IMPORT_GUARD = """\
import importlib.abc
import sys

class RejectApplicationImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"cs1302_code_visualizer", "selenium", "PIL"}:
            raise AssertionError(f"Installer imported {fullname}")

sys.meta_path.insert(0, RejectApplicationImports())
"""


def run(command: list[str], cwd: Path, env: dict[str, str]) -> str:
    """Run one isolated command and retain useful diagnostics if it fails."""
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, timeout=120, check=False
    )
    if result.returncode:
        raise RuntimeError(
            f"{command[0]} exited {result.returncode}:\n{result.stdout}{result.stderr}"
        )
    return result.stdout


def inspect_wheel(wheel: Path) -> tuple[str, dict[str, str]]:
    """Validate installer members and read expected packaged version and defaults."""
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        canonical_archive = "cs1302_code_visualizer/util/archives.py"
        if canonical_archive not in names:
            raise RuntimeError(
                f"Wheel is missing the application archive helper: {canonical_archive}"
            )
        entry_points_path = next(
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = configparser.ConfigParser(interpolation=None)
        entry_points.read_string(archive.read(entry_points_path).decode())
        for command in INSTALLER_COMMANDS:
            module = entry_points["console_scripts"][command].split(":", 1)[0]
            if f"{module.replace('.', '/')}.py" not in names:
                raise RuntimeError(f"Wheel is missing the target module for {command}: {module}")
        for name in names:
            if (
                name.startswith("scripts/")
                and name != "scripts/install_deps.py"
                and not (name.startswith("scripts/installer/") and name.endswith(".py"))
            ):
                raise RuntimeError(f"Wheel unexpectedly bundles a development script: {name}")
        metadata_path = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(archive.read(metadata_path))
        version = str(metadata["Version"])
        config = tomllib.loads(archive.read("cs1302_code_visualizer/_tracer.toml").decode())
        if config["project"]["version"] != version:
            raise RuntimeError("Packaged configuration version differs from wheel metadata")
        requirements = config["tool"]["cs1302book"]["system-dependencies"]["system-dependencies"]
    dependencies = {}
    for value in requirements:
        requirement = Requirement(value)
        dependencies[requirement.name] = next(
            (spec.version for spec in requirement.specifier if spec.operator in (">=", "==")),
            "latest",
        )
    return version, dependencies


def check_wheel(wheel: Path, *, offline: bool = False) -> None:
    """Install a wheel in a temporary venv and exercise every installer entrypoint."""
    expected_version, expected_dependencies = inspect_wheel(wheel)
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to create the isolated wheel smoke environment")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    env["PYTHONSAFEPATH"] = "1"
    env["NO_COLOR"] = "1"
    with tempfile.TemporaryDirectory(prefix="codevis-wheel-smoke-") as temporary:
        root = Path(temporary)
        venv = root / "venv"
        run([uv, "venv", "--python", sys.executable, str(venv)], root, env)
        bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        install = [uv, "pip", "install", "--python", str(python)]
        if offline:
            install.append("--offline")
        run([*install, str(wheel)], root, env)
        run(
            [
                str(python),
                "-I",
                "-c",
                (
                    "from cs1302_code_visualizer import browser_driver; "
                    "from cs1302_code_visualizer.util.archives import archive_path, extract_zip; "
                    "assert callable(archive_path) and callable(extract_zip)"
                ),
            ],
            root,
            env,
        )
        print("Installed application and archive helper imports OK")
        purelib = Path(
            run(
                [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                root,
                env,
            ).strip()
        )
        (purelib / "sitecustomize.py").write_text(IMPORT_GUARD)
        for command in INSTALLER_COMMANDS:
            executable = bin_dir / (f"{command}.exe" if os.name == "nt" else command)
            output = run([str(executable), "--help"], root, env)
            if "Usage:" not in output:
                raise RuntimeError(f"{command} --help did not print usage")
            output = run([str(executable), "self", "version", "--short"], root, env)
            if output.strip() != expected_version:
                raise RuntimeError(
                    f"{command} reported version {output.strip()!r}, expected {expected_version}"
                )
            print(f"{command}: help and installed version OK")
        output = run(
            [
                str(python),
                "-I",
                "-c",
                (
                    "import json; from scripts.installer import common; "
                    "root = common.find_project_root(); "
                    "print(json.dumps(common.get_configured_dependencies(root)))"
                ),
            ],
            root,
            env,
        )
        if json.loads(output) != expected_dependencies:
            raise RuntimeError(
                f"Installed dependency defaults differ from packaged configuration: {output}"
            )
        caller = root / "caller"
        caller.mkdir()
        (caller / "pyproject.toml").write_text(
            '[project]\nversion = "1.2.3"\n'
            '[tool.cs1302book.system-dependencies]\nsystem-dependencies = ["jdk>=42"]\n'
        )
        output = run(
            [
                str(bin_dir / ("install-jdk.exe" if os.name == "nt" else "install-jdk")),
                "self",
                "version",
                "--short",
            ],
            caller,
            env,
        )
        if output.strip() != "1.2.3":
            raise RuntimeError("Installed command did not honor caller project configuration")
        print("Packaged dependency defaults and caller configuration OK")


def main() -> None:
    """Run installer smoke checks for one already-built wheel."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="Path to an already-built wheel")
    parser.add_argument(
        "--offline", action="store_true", help="Use only cached Python dependencies"
    )
    args = parser.parse_args()
    check_wheel(args.wheel.resolve(), offline=args.offline)


if __name__ == "__main__":
    main()
