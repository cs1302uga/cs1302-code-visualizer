#!/usr/bin/env python3

import fileinput
import jdk
import jdk.client
import jdk.enums
import shutil
import tempfile
import argparse
import json
import os
import platform
import sys
import subprocess
import logging

from subprocess import CalledProcessError
from pathlib import Path
from halo import Halo as spinner
from typing import Generator
from jdk.enums import Architecture
from os import PathLike


logger: logging.Logger = logging.getLogger(__name__)


jdk_vendors: list[str] = [
    vendor.removesuffix("Client").lower()
    for vendor in dir(jdk.client)
    if vendor.endswith("Client")
]


current_dir: Path = Path(os.path.dirname(__file__)).resolve()


backend_dir: Path = current_dir / "backend"


backend_classes_dir: Path = current_dir / ".backend_classes"


backend_classes_cp: list[Path] = [
    backend_classes_dir,
    backend_dir / "cp",
    backend_dir / "cp" / "javax.json-1.0.jar",
]


default_jdk8_install_dir: Path = current_dir / ".jdk8"


def compile_backend(java_home: Path) -> None:
    if dir_exists(backend_classes_dir):
        logger.debug("We already have classes from a previous run, short circuiting")
        return

    logger.debug("Compiling backend...")

    backend_java_files: Generator[Path, None, None] = (
        (backend_dir / "cp").resolve().rglob("*.java")
    )

    try:
        backend_classes_dir.mkdir()
        with spinner(text="Compiling backend...", stream=sys.stderr):
            subprocess.run(
                [
                    str(java_home / "bin" / "javac"),
                    "-cp",
                    ":".join(
                        map(str, backend_classes_cp + [java_home / "lib" / "tools.jar"])
                    ),
                    "-d",
                    str(backend_classes_dir),
                    *map(str, backend_java_files),
                ],
                capture_output=True,
                check=True,
                text=True,
            )
    except CalledProcessError as e:
        if backend_classes_dir.exists():
            backend_classes_dir.rmdir()
        logger.exception(
            "Backend compilation failed with exit code %d and output: %s",
            e.returncode,
            e.stderr,
        )
        exit(1)


def generate_trace(
    java_home: Path, java_program: str, timeout_secs: float | None = None
) -> str:
    tracegen_input = json.dumps(
        {
            "usercode": java_program,
            "options": {},
            "args": [],
            "stdin": "",
        }
    )

    try:
        with spinner(text="Generating execution trace...", stream=sys.stderr):
            return subprocess.run(
                [
                    str(java_home / "bin" / "java"),
                    "-cp",
                    ":".join(
                        map(str, backend_classes_cp + [java_home / "lib" / "tools.jar"])
                    ),
                    "traceprinter.InMemory",
                ],
                input=tracegen_input,
                capture_output=True,
                check=True,
                text=True,
                timeout=timeout_secs,
            ).stdout
    except CalledProcessError as e:
        logger.exception(
            "Trace generation failed with exit code %d and output:", e.returncode
        )
        exit(1)


def validate_trace(trace_json: str) -> bool:
    """Catch "show-stopping errors", derived from jv-frontend.js
    Returns true if trace is valid, false otherwise.
    """
    trace: list = json.loads(trace_json)["trace"]
    if trace and trace[-1]["event"] != "uncaught_exception":
        # no error
        return True
    if len(trace) == 1 and "line" in trace[0]:
        error_line = trace[0]["line"]
        logger.fatal(f"Error encountered on line {error_line} of the provided Java source code.")
    if "exception_msg" in trace[-1]:
        logger.fatal(trace[0]["exception_method"])
    else:
        logger.fatal("Whoa, unknown error!")
    return False


def dir_exists(path: str | PathLike[str]) -> bool:
    path = Path(path).resolve()
    return path.is_dir() and path.exists()


def file_exists(path: str | PathLike[str]) -> bool:
    path = Path(path).resolve()
    return path.is_file() and path.exists()


def jdk8_home(path: str | PathLike[str], raise_not_found: bool = False) -> Path | None:
    javac_paths = list(Path(path).glob("**/bin/javac"))
    logger.debug(f"Found `javac` executable(s): {javac_paths}")
    if not javac_paths and raise_not_found:
        raise FileNotFoundError(f"javac not found under {str(path)}")
    elif not javac_paths:
        return None
    else:
        return javac_paths[0].parent.parent.resolve()


def jdk8_exists(
    path: str | PathLike[str], raise_not_found: bool = False
) -> Path | None:
    home: Path | None = jdk8_home(path)
    logger.debug(f"Found JDK home directory: {home}")
    if not home and raise_not_found:
        raise FileNotFoundError(f"javac not found under {str(path)}")
    elif not home:
        return None
    result: bool = all(
        [
            file_exists(home / "bin" / "java"),
            file_exists(home / "bin" / "javac"),
        ]
    )
    result = (
        result
        and "1.8"
        in subprocess.check_output(
            [
                str(home / "bin" / "javac"),
                "-version",
            ],
            stderr=subprocess.STDOUT,
        )
        .decode()
        .strip()
    )
    if not result and raise_not_found:
        raise FileNotFoundError(f"JDK 8 not found at {str(path)}")
    return home


def detect_jdk8_architecture() -> Architecture:
    bits: int = int(platform.architecture()[0].removesuffix("bit"))
    machine: str = platform.machine()
    arch: Architecture | None = None
    if "arm" in machine and bits == 64:
        arch = Architecture.AARCH64
    else:
        arch = Architecture.detect()
    if arch:
        return arch
    else:
        raise OSError(f"Unable to detect JDK 8 architecture: {machine=}; {bits=}")


def install_jdk8(install_dir: str | PathLike[str] = default_jdk8_install_dir) -> Path:
    install_dir = Path(install_dir)
    if jdk8_exists(install_dir):
        logger.debug("Using existing JDK installation at %s", str(install_dir))
    else:
        logger.debug("No existing JDK installation found at %s", str(install_dir))
        arch: Architecture = detect_jdk8_architecture()
        for vendor in jdk_vendors:
            try:
                logger.debug(
                    "Attempting to install %s JDK 8 at %s", vendor, str(install_dir)
                )
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_install_dir: str = jdk.install(
                        "8",
                        arch=arch,
                        path=temp_dir,
                        vendor=vendor,
                    )
                    temp_install_dir = str(
                        jdk8_exists(temp_install_dir, raise_not_found=True)
                    )
                    shutil.move(temp_install_dir, str(install_dir))
                    logger.debug(
                        "Successfully installed %s JDK 8 at %s",
                        vendor,
                        str(install_dir),
                    )
                    return install_dir.resolve()
            except Exception:
                logger.exception("Unable to install %s JDK 8", vendor)
    jdk8_exists(install_dir, raise_not_found=True)
    return Path(install_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Java program trace generator and visualizer"
    )

    def validate_dir(s: str) -> Path:
        if os.path.isdir(s):
            return Path(s)
        else:
            raise NotADirectoryError(s)

    parser.add_argument(
        "--jdk8-home",
        help="Path to Java 8 JDK installation home. If not provided, the script will try to download the JDK on its own.",
        type=validate_dir,
    )

    parser.add_argument(
        "--trace-timeout",
        help="Max execution time (in seconds) of the trace execution.",
        type=float,
    )

    parser.add_argument(
        "--verbose", "-v", help="Enable output from logger.", action="store_true",
    )

    parser.add_argument(
        "--input", "-i", help="Path to Java source file to be traced, or `-` for stdin.", default="-",
    )

    parser.add_argument(
        "--output", "-o", help="Output path. If not provided, traces are printed to standard output.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.jdk8_home and jdk8_exists(args.jdk8_home):
        java_home: Path = Path(args.jdk8_home)
    elif args.jdk8_home:
        logger.error("JDK 8 installation not found at %s", args.jdk8_home)
        exit(1)
    else:
        java_home: Path = install_jdk8()

    compile_backend(java_home)

    # get java file from stdin
    java_input = "".join(fileinput.input(args.input))

    trace = generate_trace(
        java_home,
        java_input,
        args.trace_timeout,
    )

    if not validate_trace(trace):
        exit(1)

    if args.output is None:
        print(trace)
    else:
        with open(args.output, "w") as f:
            f.write(trace)


if __name__ == "__main__":
    main()
