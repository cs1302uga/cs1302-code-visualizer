#!/usr/bin/env python3

import fileinput
import socket
import json
import shutil
import tempfile
import argparse
import os
import platform
import sys
import subprocess
import logging
import platformdirs
import requests
import zipfile
import tarfile

from subprocess import CalledProcessError
from pathlib import Path
from halo import Halo as spinner
from os import PathLike


logger: logging.Logger = logging.getLogger(__name__)

current_dir: Path = Path(os.path.dirname(__file__)).resolve()

cache_dir: Path = Path(
    platformdirs.user_cache_dir("cs1302-code-visualizer", ensure_exists=True)
)


def generate_trace(
    java_home: Path,
    java_program: str,
    timeout_secs: float | None = None,
    inline_strings: bool = True,
    breakpoints: set[int] = set(),
) -> str:
    args = ["-s"] if inline_strings else []
    for breakpoint in breakpoints:
        args.extend(["-b", str(breakpoint)])

    return subprocess.check_output(
        (
            [
                str(java_home / "bin" / "java"),
                "-jar",
                str(cache_dir / "code-tracer.jar"),
            ]
            + args
        ),
        input=java_program,
        timeout=timeout_secs,
        text=True,
    )


def jdk_exists(maybe_java_home: str | PathLike[str]) -> bool:
    maybe_home_path: Path = Path(maybe_java_home)
    return all(
        [
            (maybe_home_path / "bin" / "java").is_file(),
            (maybe_home_path / "bin" / "javac").is_file(),
        ]
    )


def download_jdk():
    match platform.system():
        case "Linux":
            os = "linux"
        case "Windows":
            os = "windows"
        case "Darwin":
            os = "mac"
        case s:
            raise Exception(
                f"Cannot automatically download a JDK for your computer's platform ({s}). Please download and provide one yourself."
            )

    match platform.machine().lower():
        case "amd64" | "x86_64":
            arch = "x64"
        case "aarch64" | "arm64":
            arch = "aarch64"
        case m:
            raise Exception(
                f"Cannot automatically download a JDK for your computer's architecture ({m} {os}). Please download and provide one yourself."
            )

    lts_jdk_num = requests.get(
        "https://api.adoptium.net/v3/info/available_releases"
    ).json()["most_recent_lts"]
    resp = requests.get(
        f"https://api.adoptium.net/v3/binary/latest/{lts_jdk_num}/ga/{os}/{arch}/jdk/hotspot/normal/eclipse",
        stream=True,
    )

    with tempfile.NamedTemporaryFile() as temp_file:
        with temp_file.file as f:
            for chunk in resp.iter_content(2**8):
                f.write(chunk)
        if os == "Windows":
            with zipfile.ZipFile(temp_file) as zip:
                toplevel_dir = zip.namelist()[0]
                zip.extractall(cache_dir)
        else:
            with tarfile.open(temp_file.name, mode="r:gz") as tar:
                toplevel_dir = tar.getnames()[0]
                tar.extractall(cache_dir)

    shutil.move(cache_dir / toplevel_dir, cache_dir / "jdk")

    if not jdk_exists(str(cache_dir / "jdk")):
        raise Exception(
            "Could not extract the JDK. Please download and provide one yourself."
        )


def ensure_jdk_installed(
    install_dir: str | PathLike[str] = str(cache_dir / "jdk"),
) -> Path:
    if jdk_exists(install_dir):
        # jdk is already installed
        logger.debug(f"Using existing JDK installation at {install_dir}")
        return Path(install_dir)

    # we have to grab the jdk
    install_dir = Path(install_dir)
    logger.debug(f"No existing JDK installation found at {install_dir}")
    download_jdk()
    return cache_dir / "jdk"


def ensure_code_tracer_installed(update_existing: bool = False):
    if (cache_dir / "code-tracer.jar").is_file():
        if not update_existing:
            return
        # make sure we have an internet connection before proceeding
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect(("1.1.1.1", 53))
            sock.close()
        except socket.error:
            logger.debug(
                "The code tracer jar already exists, but we can't update it because we're offline. "
                "Continuing with existing version."
            )
            return

    dl_info_path = Path(cache_dir / "code_tracer_dl_headers.json")

    headers = {}
    if (cache_dir / "code-tracer.jar").is_file() and dl_info_path.is_file():
        with open(dl_info_path, "r") as dl_info_file:
            dl_info = json.load(dl_info_file)
        if "Last-Modified" in dl_info:
            headers["If-Modified-Since"] = dl_info["Last-Modified"]

    resp = requests.get(
        "https://github.com/cs1302uga/cs1302-tracer/releases/latest/download/code-tracer.jar",
        headers=headers,
        stream=True,
    )

    if resp.status_code == 304:
        return

    resp.raise_for_status()

    with tempfile.TemporaryFile() as temp_file:
        for chunk in resp.iter_content(2**8):
            temp_file.write(chunk)

    with open(cache_dir / "code-tracer.jar", "wb") as jar_file:
        shutil.copyfileobj(temp_file, jar_file)

    with open(dl_info_path, "w") as dl_info_file:
        json.dump(dict(resp.headers), dl_info_file)


def main():
    parser = argparse.ArgumentParser(
        description="Java program trace generator and visualizer"
    )

    parser.add_argument(
        "--trace-timeout",
        help="Max execution time (in seconds) of the trace execution.",
        type=float,
    )

    parser.add_argument(
        "--verbose",
        "-v",
        help="Enable output from logger.",
        action="store_true",
    )

    parser.add_argument(
        "--input",
        "-i",
        help="Path to Java source file to be traced, or `-` for stdin.",
        default="-",
    )

    parser.add_argument(
        "--output",
        "-o",
        help="Output path. If not provided, traces are printed to standard output.",
    )

    parser.add_argument(
        "--jdk",
        help=(
            "Path to the home of a JDK 21+ installation. If not provided, "
            "the script will attempt to download one itself."
        ),
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.jdk != None and jdk_exists(args.jdk):
        java_home = Path(args.jdk)
    else:
        with spinner(text="Installing the JDK...", stream=sys.stderr):
            java_home: Path = ensure_jdk_installed()

    with spinner(text="Downloading Java tracer...", stream=sys.stderr):
        ensure_code_tracer_installed()

    # get java file from stdin
    java_input = "".join(fileinput.input(args.input))

    try:
        with spinner(text="Generating execution trace...", stream=sys.stderr):
            trace = generate_trace(
                java_home,
                java_input,
                args.trace_timeout,
            )
    except CalledProcessError as e:
        logger.exception(
            "Trace generation failed with exit code %d and output:", e.returncode
        )
        exit(1)

    if args.output is None:
        print(trace)
    else:
        with open(args.output, "w") as f:
            f.write(trace)


if __name__ == "__main__":
    main()
