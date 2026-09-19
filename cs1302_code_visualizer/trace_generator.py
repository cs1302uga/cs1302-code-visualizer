"""Java execution trace generator.

This module manages downloading the JDK and code-tracer JAR if needed,
invoking the trace generator on Java source code, and post-processing
the resulting trace JSON.

Normative References:
    PEP 257 – Docstring Conventions (https://peps.python.org/pep-0257/)
    PEP 484 – Type Hints (https://peps.python.org/pep-0484/)
    Adoptium API v3 Specification (https://api.adoptium.net/v3/)
"""

from __future__ import annotations

import argparse
import fileinput
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import tomllib
import zipfile
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from os import PathLike
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Any, Final, cast

if TYPE_CHECKING:
    from .batch_tracer import BatchTraceJob, BatchTracerClient

import certifi
import platformdirs
import requests

from .errors import (
    CodeVisTraceGeneratorError,
    JDKInstallationError,
    TracerDownloadError,
)
from .util.certificates import ensure_certifi_bundle

logger: logging.Logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))

_TRACER_INSTALL_LOCK: Final[threading.Lock] = threading.Lock()
_JDK_INSTALL_LOCK: Final[threading.Lock] = threading.Lock()

DEFAULT_REQUEST_TIMEOUT: Final[int] = 30
DOWNLOAD_CHUNK_SIZE: Final[int] = 64 * 1024


# Enable DEBUG_MODE with
# CS1302_DEBUG=1
# CS1302_DEBUG=True
DEBUG_MODE: Final[bool] = os.getenv("CS1302_DEBUG", "").strip().lower() in ["1", "true"]


# Disable HEADLESS_MODE with
# CS1302_HEADLESS=1
# CS1302_HEADLESS=True
DISABLE_HEADLESS_MODE: Final[bool] = os.getenv("CS1302_HEADLESS", "").strip().lower() in [
    "1",
    "true",
]


if DEBUG_MODE:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


DEFAULT_BREAKPOINTS_SET: Final[set[int]] = {-1}


PACKAGE_DIR: Final[Path] = Path(os.path.dirname(__file__)).resolve()


CACHE_DIR: Final[Path] = Path(
    platformdirs.user_cache_dir(
        "cs1302-code-visualizer",
        ensure_exists=True,
    )
)


JDK_CACHE_DIR: Final[Path] = CACHE_DIR / "jdk"


BOXED_PRIMITIVE_TYPES: Final[dict[str, str]] = {
    "Integer": "int",
    "Double": "double",
    "Boolean": "boolean",
    "Character": "char",
    "Byte": "byte",
    "Short": "short",
    "Long": "long",
    "Float": "float",
}


def get_sanitized_java_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an environment dictionary sanitized of JVM options that emit startup banners.

    If ``JAVA_TOOL_OPTIONS`` or ``_JAVA_OPTIONS`` contains ``-Djava.awt.headless=true``,
    that property is stripped since it is supplied explicitly on the JVM command line.
    If the variable becomes empty, it is removed entirely to prevent the JVM from emitting
    ``Picked up JAVA_TOOL_OPTIONS`` to standard error.

    Args:
        env: Base environment mapping to sanitize, or None to use ``os.environ``.

    Returns:
        A sanitized dictionary copy of the environment.
    """
    clean_env: dict[str, str] = dict(os.environ if env is None else env)
    for var in ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS"):
        if var in clean_env:
            val = clean_env[var]
            cleaned_val = re.sub(
                r'(?:^|\s+)-Djava\.awt\.headless=["\']?(?:true|false)["\']?(?:\s+|$)',
                " ",
                val,
            ).strip()
            if cleaned_val:
                clean_env[var] = cleaned_val
            else:
                del clean_env[var]
    return clean_env


def normalize_heap_primitives(trace_obj: dict[str, Any]) -> None:
    """Ensure all heap objects in a trace are formatted as lists for OnlinePythonTutor."""
    raw_trace = trace_obj.get("trace", [])
    events: list[Any] = raw_trace if isinstance(raw_trace, list) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        heap: Any = event.get("heap", {})
        heap_attrs: Any = event.get("heap_attrs", {})
        if isinstance(heap, dict):
            for addr, obj in list(heap.items()):
                if not isinstance(obj, list):
                    type_name: str = "Object"
                    if (
                        isinstance(heap_attrs, dict)
                        and addr in heap_attrs
                        and isinstance(heap_attrs[addr], dict)
                        and "type" in heap_attrs[addr]
                    ):
                        t = heap_attrs[addr]["type"]
                        if isinstance(t, str):
                            type_name = t.split(".")[-1].split("<")[0]
                    elif isinstance(obj, int) and not isinstance(obj, bool):
                        type_name = "Integer"
                    elif isinstance(obj, float):
                        type_name = "Double"
                    elif isinstance(obj, bool):
                        type_name = "Boolean"
                    elif isinstance(obj, str):
                        type_name = "String"
                    heap[addr] = ["INSTANCE", type_name, ["value", obj]]
                    if type_name in BOXED_PRIMITIVE_TYPES and isinstance(heap_attrs, dict):
                        if addr not in heap_attrs or not isinstance(heap_attrs[addr], dict):
                            heap_attrs[addr] = {}
                        heap_attrs[addr]["type"] = [BOXED_PRIMITIVE_TYPES[type_name]]
                elif (
                    isinstance(obj, list)
                    and len(obj) >= 2
                    and obj[0] == "INSTANCE"
                    and isinstance(obj[1], str)
                ):
                    if obj[1].endswith("[]"):
                        obj[1] = obj[1].removesuffix("[]")
                    if (
                        obj[1] in BOXED_PRIMITIVE_TYPES
                        and isinstance(heap_attrs, dict)
                        and addr in heap_attrs
                        and isinstance(heap_attrs[addr], dict)
                        and isinstance(heap_attrs[addr].get("type"), str)
                    ):
                        heap_attrs[addr]["type"] = [BOXED_PRIMITIVE_TYPES[obj[1]]]

        stack_to_render = event.get("stack_to_render")
        if isinstance(stack_to_render, list):
            for frame in stack_to_render:
                if isinstance(frame, dict):
                    locals_attrs = frame.get("locals_attrs")
                    if isinstance(locals_attrs, dict):
                        this_attr = locals_attrs.get("this")
                        if (
                            isinstance(this_attr, dict)
                            and isinstance(this_attr.get("type"), str)
                            and this_attr["type"].endswith("[]")
                        ):
                            this_attr["type"] = this_attr["type"].removesuffix("[]")


def generate_trace(
    java_home: Path,
    java_program: str,
    timeout_secs: float | None = None,
    inline_strings: bool = False,
    remove_main_args_parameter: bool = True,
    breakpoints: set[int] = DEFAULT_BREAKPOINTS_SET,
    accumulate_breakpoints: bool = False,
    include_enum_static_fields: bool = False,
    auto_detect: bool = False,
    type_style: str | None = "simple",
    stdin: str | None = None,
    stdin_file: Path | str | None = None,
    extra_tracer_args: Sequence[str] | None = None,
    eval_enum_hash: bool = True,
    all_breakpoints: bool = False,
) -> str:
    """Generate an execution trace for a Java source program.

    Args:
        java_home: Path to the JDK home directory.
        java_program: Java source code text.
        timeout_secs: Timeout in seconds for trace execution.
        inline_strings: Whether to inline strings in the trace.
        remove_main_args_parameter: Whether to remove main args from the trace.
        breakpoints: Set of breakpoint line numbers.
        accumulate_breakpoints: Whether to accumulate multiple hits per breakpoint.
        include_enum_static_fields: Whether to keep enum constants in global static fields.
        auto_detect: Whether to automatically detect and compile dependent source files.
        type_style: Type qualification style ('fqn' or 'simple').
        stdin: Standard input string provided to the traced Java program.
        stdin_file: Path to file whose content is provided via standard input.
        extra_tracer_args: Additional CLI arguments to pass to code-tracer.
        eval_enum_hash: Whether to eagerly evaluate lazy enum hash codes.
        all_breakpoints: Whether to include all encountered breakpoint instances in chronological order.

    Returns:
        JSON string representing the execution trace.
    """
    if stdin is not None and stdin_file is not None:
        raise ValueError("Cannot specify both stdin and stdin_file")

    cli_args: list[str] = ["-v"]

    has_explicit_breakpoints = breakpoints != DEFAULT_BREAKPOINTS_SET
    effective_all_breakpoints = all_breakpoints or auto_detect
    if extra_tracer_args and (
        "-a" in extra_tracer_args or "--all-breakpoints" in extra_tracer_args
    ):
        effective_all_breakpoints = True

    if has_explicit_breakpoints or not effective_all_breakpoints:
        for breakpoint in sorted(breakpoints):
            cli_args.extend(["-b", str(breakpoint)])

    if inline_strings:
        cli_args.append("--inline-strings")

    if remove_main_args_parameter:
        cli_args.append("--remove-main-args")

    if accumulate_breakpoints:
        cli_args.append("--accumulate-breakpoints")

    if not eval_enum_hash:
        cli_args.append("--no-eval-enum-hash")

    if effective_all_breakpoints and not (
        extra_tracer_args
        and ("-a" in extra_tracer_args or "--all-breakpoints" in extra_tracer_args)
    ):
        cli_args.append("-a")

    if type_style:
        cli_args.append(f"--type-style={type_style}")

    if stdin is not None:
        cli_args.extend(["--stdin", stdin])

    if stdin_file is not None:
        cli_args.extend(["--stdin-file", str(stdin_file)])

    if extra_tracer_args:
        cli_args.extend(extra_tracer_args)

    trace: str = "(none)"

    try:
        trace_command: list[str] = [
            str(java_home / "bin" / "java"),
            "-Djava.awt.headless=true",
            "--enable-native-access=ALL-UNNAMED",
            "-jar",
            str(CACHE_DIR / "code-tracer.jar"),
            "trace",
        ] + cli_args

        process = subprocess.run(
            trace_command,
            input=java_program,
            timeout=timeout_secs,
            text=True,
            capture_output=True,
            check=True,
            env=get_sanitized_java_env(),
        )

        trace = process.stdout

    except CalledProcessError as cpe:
        logger.exception("problem encountered while calling the trace generator")
        raise CodeVisTraceGeneratorError.from_cpe(
            cpe=cpe,
            source_code=java_program,
            cli_args=cli_args,
        )

    trace_json: dict[str, Any] = json.loads(trace)

    # Normalize heap primitives across all traces
    if "trace" in trace_json and isinstance(trace_json["trace"], list):
        normalize_heap_primitives(trace_json)
    else:
        for line, trace_value in trace_json.items():
            items_list: list[Any] = trace_value if isinstance(trace_value, list) else [trace_value]
            for item in items_list:
                if isinstance(item, dict):
                    normalize_heap_primitives(item)

    # cleanup/remove enum constants and $VALUES from global static fields list
    if not include_enum_static_fields:
        if "trace" in trace_json and isinstance(trace_json["trace"], list):
            enum_types: list[str] = get_enum_types(trace_json)
            enum_globals: list[str] = get_enum_globals(trace_json, enum_types)
            delete_globals(trace_json, enum_globals)
        else:
            for line, trace_value in trace_json.items():
                logger.debug(f"removing enum constants and $VALUES for line {line}")
                line_items: list[Any] = (
                    trace_value if isinstance(trace_value, list) else [trace_value]
                )
                for item in line_items:
                    if isinstance(item, dict):
                        line_enum_types: list[str] = get_enum_types(item)
                        line_enum_globals: list[str] = get_enum_globals(item, line_enum_types)
                        delete_globals(item, line_enum_globals)

    return json.dumps(trace_json)


def generate_traces(
    jobs: Sequence[BatchTraceJob],
    *,
    java_home: Path | None = None,
    workers: int = 1,
    max_jobs_per_worker: int = 100,
    client: BatchTracerClient | None = None,
) -> list[dict[str, Any]]:
    """Execute multiple trace jobs in parallel using code-tracer batch-trace.

    Args:
        jobs: A sequence of BatchTraceJob specifications to execute.
        java_home: Optional path to a JDK installation home.
        workers: Number of guest worker JVMs to run in parallel (default: 1).
        max_jobs_per_worker: Maximum jobs before recycling a guest worker JVM (default: 100).
        client: Optional existing BatchTracerClient instance to reuse.

    Returns:
        List of trace dictionaries in the same order as input jobs.
    """
    from .batch_tracer import BatchTracerClient

    if client is not None:
        futures = [client.submit(job) for job in jobs]
        return [f.result() for f in futures]
    with BatchTracerClient(
        java_home=java_home,
        workers=workers,
        max_jobs_per_worker=max_jobs_per_worker,
    ) as c:
        futures = [c.submit(job) for job in jobs]
        return [f.result() for f in futures]


def jdk_exists(maybe_java_home: str | PathLike[str]) -> bool:
    """Check if a JDK installation with java and javac binaries exists at the path."""
    maybe_home_path: Path = Path(maybe_java_home)
    return all([
        (maybe_home_path / "bin" / "java").is_file(),
        (maybe_home_path / "bin" / "javac").is_file(),
    ])


def download_jdk() -> None:
    """Download and extract a compatible JDK to the local cache directory."""
    with _JDK_INSTALL_LOCK:
        if JDK_CACHE_DIR.exists():
            return

        match platform.system():
            case "Linux":
                os = "linux"
            case "Windows":
                os = "windows"
            case "Darwin":
                os = "mac"
            case str(s):
                message: str = (
                    f"Cannot automatically download a JDK for your computer's platform ({s})."
                )
                raise JDKInstallationError(message)

        match platform.machine().lower():
            case "amd64" | "x86_64":
                arch = "x64"
            case "aarch64" | "arm64":
                arch = "aarch64"
            case str(m):
                raise JDKInstallationError(
                    f"Cannot automatically download a JDK for your computer's architecture ({m} {os}). Please download and provide one yourself."
                )

        resp = requests.get(
            "https://api.adoptium.net/v3/info/available_releases",
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

        lts_jdk_num = resp.json()["most_recent_lts"]

        resp = requests.get(
            f"https://api.adoptium.net/v3/binary/latest/{lts_jdk_num}/ga/{os}/{arch}/jdk/hotspot/normal/eclipse",
            stream=True,
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )

        if resp.status_code == 404:
            # fall back to JDK 21
            fallback_jdk_num = "21"
            resp = requests.get(
                f"https://api.adoptium.net/v3/binary/latest/{fallback_jdk_num}/ga/{os}/{arch}/jdk/hotspot/normal/eclipse",
                stream=True,
                timeout=DEFAULT_REQUEST_TIMEOUT,
            )

        resp.raise_for_status()

        with tempfile.NamedTemporaryFile() as temp_file:
            with temp_file.file as f:
                for chunk in resp.iter_content(DOWNLOAD_CHUNK_SIZE):
                    _ = f.write(chunk)
            if os == "windows":
                with zipfile.ZipFile(temp_file) as zip:
                    toplevel_dir = zip.namelist()[0]
                    zip.extractall(CACHE_DIR)
            elif os == "mac":
                with tarfile.open(temp_file.name, mode="r:*", errorlevel=0) as tar:
                    toplevel_dir = Path(tar.getnames()[0]) / "Contents" / "Home"
                    tar.extractall(CACHE_DIR, numeric_owner=True, filter="tar")
            else:
                with tarfile.open(temp_file.name, mode="r:*", errorlevel=0) as tar:
                    toplevel_dir = tar.getnames()[0]
                    tar.extractall(CACHE_DIR, numeric_owner=True, filter="tar")

        _ = shutil.move(CACHE_DIR / toplevel_dir, CACHE_DIR / "jdk")

        if not jdk_exists(str(CACHE_DIR / "jdk")):
            raise JDKInstallationError(
                "Could not extract the JDK. Please download and provide one yourself."
            )


def ensure_jdk_installed(install_dir: str | PathLike[str] = JDK_CACHE_DIR) -> Path:
    """Ensure a JDK 21+ is available on PATH or download one to the cache directory."""
    # 1. check if javac is on the path and version 21 or greater
    java21_found: bool = False
    if which_java := shutil.which("java"):
        java_exe: Path = Path(which_java).resolve()
        java_props: str = subprocess.check_output(
            [
                java_exe,
                "-Djava.awt.headless=true",
                "-XshowSettings:properties",
                "-version",
            ],
            text=True,
            stderr=subprocess.STDOUT,
            env=get_sanitized_java_env(),
        )

        for line in java_props.splitlines():
            stripped_line: str = line.strip()
            if stripped_line and stripped_line.startswith("java.home = "):
                install_dir = Path(stripped_line.split(" = ")[1])
            elif stripped_line and stripped_line.startswith("java.version = "):
                ver_str = stripped_line.split(" = ")[1].strip('"')
                match = re.match(r"^(\d+)", ver_str)
                if match:
                    java21_found = int(match.group(1)) >= 21

    if java21_found and jdk_exists(install_dir):
        logger.debug(f"Using existing JDK installation at {install_dir}")
        return Path(install_dir)
    else:
        # otherwise, we have to download a jdk
        install_dir = Path(install_dir)
        logger.debug(f"No existing JDK installation found at {install_dir}")
        try:
            download_jdk()
        except Exception as e:
            raise JDKInstallationError("Failed to download JDK") from e
        return CACHE_DIR / "jdk"


def read_tracer_url_and_sum_from_toml() -> tuple[str, str] | None:
    """Load tracer URL and SHA256 sum from pyproject.toml if present."""
    try:
        with open(PACKAGE_DIR.parent / "pyproject.toml", "rb") as t:
            pyproject = tomllib.load(t)
            package_constants = pyproject.get("tool", {}).get("cs1302-code-visualizer", {})
            tracer_url = package_constants.get("tracer-url")
            if tracer_url is None or not isinstance(tracer_url, str):
                return None
            tracer_sha256 = package_constants.get("tracer-sha256")
            if tracer_sha256 is None or not isinstance(tracer_sha256, str):
                return None
            return (
                package_constants.get("tracer-url"),
                package_constants.get("tracer-sha256"),
            )
    except (OSError, tomllib.TOMLDecodeError):
        return None


def ensure_code_tracer_installed(update_existing: bool = False) -> None:
    """Ensure the code-tracer JAR is downloaded and validated against its SHA256 checksum."""
    with _TRACER_INSTALL_LOCK:
        target_jar = CACHE_DIR / "code-tracer.jar"
        tracer_url_and_sum = read_tracer_url_and_sum_from_toml()
        if target_jar.is_file():
            if not update_existing:
                if tracer_url_and_sum and tracer_url_and_sum[1]:
                    try:
                        with open(target_jar, "rb") as f:
                            if hashlib.sha256(f.read()).hexdigest() == tracer_url_and_sum[1]:
                                return
                    except OSError:
                        pass
                else:
                    return
            # make sure we have an internet connection before proceeding
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                sock.connect(("1.1.1.1", 53))
                sock.close()
            except OSError:
                logger.debug(
                    "The code tracer jar already exists, but we can't update it because we're offline."
                )
                logger.debug("Continuing with existing tracer version.")
                return

        dl_info_path = Path(CACHE_DIR / "code_tracer_dl_headers.json")

        headers: dict[str, str] = {}

        if target_jar.is_file() and dl_info_path.is_file():
            try:
                with open(dl_info_path, "r") as dl_info_file:
                    dl_info = json.load(dl_info_file)
                if "Last-Modified" in dl_info:
                    headers["If-Modified-Since"] = dl_info["Last-Modified"]
            except (OSError, json.JSONDecodeError):
                pass

        tracer_url_and_sum = read_tracer_url_and_sum_from_toml()

        ensure_certifi_bundle()
        with requests.get(
            (tracer_url_and_sum and tracer_url_and_sum[0])
            or "https://github.com/cs1302uga/cs1302-tracer/releases/latest/download/code-tracer.jar",
            headers=headers,
            stream=True,
            timeout=DEFAULT_REQUEST_TIMEOUT,
            verify=certifi.where(),
        ) as resp:

            if resp.status_code == 304:
                return

            resp.raise_for_status()

            tmp_jar_path = CACHE_DIR / f"code-tracer.jar.tmp.{os.getpid()}"
            with open(tmp_jar_path, "wb") as jar_file:
                sha256_hash = hashlib.sha256()
                for chunk in resp.iter_content(DOWNLOAD_CHUNK_SIZE):
                    _ = jar_file.write(chunk)
                    sha256_hash.update(chunk)

            if tracer_url_and_sum and tracer_url_and_sum[1] != sha256_hash.hexdigest():
                if tmp_jar_path.exists():
                    tmp_jar_path.unlink()
                raise TracerDownloadError(
                    f"Downloaded tracer JAR doesn't have the correct SHA256 sum. Expected: {tracer_url_and_sum[1]}, got {sha256_hash.hexdigest()}."
                )

            _ = tmp_jar_path.replace(target_jar)

            with open(dl_info_path, "w") as dl_info_file:
                json.dump(dict(resp.headers), dl_info_file)


def get_enum_types(trace_json: dict[str, Any]) -> list[str]:
    """Extract enum type names from the trace JSON."""
    enum_types: list[str] = []
    for trace_event in trace_json.get("trace", cast(list[dict[str, Any]], [])):
        for global_field in trace_event.get("globals", cast(list[str], [])):
            if global_field.endswith(".$VALUES"):
                enum_types.append(global_field.removesuffix(".$VALUES"))
    return enum_types


def get_enum_globals(
    trace_json: dict[str, Any], enum_types: Sequence[str] | None = None
) -> list[str]:
    """Extract global enum field identifiers from the trace JSON."""
    types_list = list(enum_types) if enum_types is not None else get_enum_types(trace_json)
    enum_globals: list[str] = []
    for trace_event in trace_json.get("trace", cast(list[dict[str, Any]], [])):
        for global_field in trace_event.get("globals", cast(list[str], [])):
            for enum_type in types_list:
                if global_field.startswith(f"{enum_type}."):
                    enum_globals.append(global_field)
    return enum_globals


def delete_globals(trace_json: dict[str, Any], global_keys: Sequence[str] | None = None) -> None:
    """Delete specified global static fields from trace events without removing heap objects."""
    keys_to_delete = list(global_keys) if global_keys is not None else []
    for trace_event in trace_json.get("trace", cast(list[dict[str, Any]], [])):
        globals_dict: dict[str, Any] = trace_event.get("globals", {})
        globals_attrs: dict[str, Any] = trace_event.get("globals_attrs", {})
        ordered_globals: list[str] = trace_event.get("ordered_globals", [])
        for global_key in keys_to_delete:
            # NOTE: do not remove the associated objects in the heap
            #       so that they can still be rendered, if needed
            #       when the trace is visualized
            globals_dict.pop(global_key, None)
            globals_attrs.pop(global_key, None)
            if global_key in ordered_globals:
                ordered_globals.remove(global_key)


def main() -> None:
    """Command-line entry point for generating Java execution traces."""
    parser = argparse.ArgumentParser(description="Java program trace generator and visualizer")

    _ = parser.add_argument(
        "--trace-timeout",
        help="Max execution time (in seconds) of the trace execution.",
        type=float,
    )

    _ = parser.add_argument(
        "--verbose",
        "-v",
        help="Enable more output from logger.",
        action="store_true",
    )

    _ = parser.add_argument(
        "--input",
        "-i",
        help="Path to Java source file to be traced, or `-` for stdin.",
        default="-",
    )

    _ = parser.add_argument(
        "--output",
        "-o",
        help="Output path. If not provided, traces are printed to standard output.",
    )

    _ = parser.add_argument(
        "--jdk",
        help=(
            "Path to the home of a JDK 21+ installation. If not provided, "
            "the script will attempt to download one itself."
        ),
    )

    _ = parser.add_argument(
        "-a",
        "--all-breakpoints",
        "--auto-detect",
        dest="all_breakpoints",
        help="Include all encountered breakpoint instances in chronological order.",
        action="store_true",
    )

    _ = parser.add_argument(
        "--include-enum-static-fields",
        help=(
            "Include enum constants and $VALUES in the global static fields list. "
            "They are removed from the global static fields list by default "
            "to reduce clutter. "
            "The associated objects in the heap are always included in the "
            "resulting trace, regardless of whether this option is set, so that "
            "they can be referred to elsewhere in the trace, as needed."
        ),
        action="store_true",
    )

    _ = parser.add_argument(
        "-b",
        "--breakpoint",
        dest="breakpoints",
        action="append",
        type=str,
        help="Breakpoint line(s) at which to capture a snapshot (e.g. -b 10 or -b 10,20).",
    )

    _ = parser.add_argument(
        "--type-style",
        choices=["fqn", "simple"],
        default="simple",
        help="Type qualification style: fqn (fully-qualified) or simple (default: simple).",
    )

    _ = parser.add_argument(
        "--no-eval-enum-hash",
        dest="eval_enum_hash",
        action="store_false",
        default=True,
        help=(
            "Disable eager evaluation of lazy enum hash codes. By default, "
            "enum hash codes are eagerly evaluated so that non-zero hash values "
            "are shown in trace visualizations."
        ),
    )

    _ = parser.add_argument(
        "--batch",
        action="store_true",
        help=(
            "Run in batch mode, processing an NDJSON stream of trace requests "
            "from input and writing NDJSON responses to output."
        ),
    )

    _ = parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent guest worker JVMs in batch mode (default: 1).",
    )

    _ = parser.add_argument(
        "--max-jobs-per-worker",
        type=int,
        default=100,
        help="Maximum jobs before recycling a guest worker JVM in batch mode (default: 100).",
    )

    stdin_group = parser.add_mutually_exclusive_group()
    _ = stdin_group.add_argument(
        "--stdin",
        help="Input string provided to the traced program via standard input.",
        default=None,
    )

    _ = stdin_group.add_argument(
        "--stdin-file",
        help="Path to file whose content is provided to the traced program via standard input.",
        default=None,
    )

    args, extra_tracer_args = parser.parse_known_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    if args.jdk is not None and jdk_exists(args.jdk):
        java_home = Path(args.jdk)
    else:
        java_home = ensure_jdk_installed()

    ensure_code_tracer_installed()

    if args.batch:
        from .batch_tracer import BatchTraceJob, BatchTracerClient
        client = BatchTracerClient(
            java_home=java_home,
            workers=args.workers,
            max_jobs_per_worker=args.max_jobs_per_worker,
        )
        with client, ExitStack() as stack, fileinput.input(args.input) as f:
            out_file = (
                stack.enter_context(open(args.output, "w", encoding="utf-8"))
                if args.output
                else sys.stdout
            )
            for line in f:
                line_s = line.strip()
                if not line_s:
                    continue
                try:
                    data = json.loads(line_s)
                    source = data.get("source")
                    if not isinstance(source, str):
                        raise TypeError("Batch request must include string field 'source'")
                    bps_val = data.get("breakpoints")
                    bps_list = [int(x) for x in bps_val] if bps_val is not None else None
                except (json.JSONDecodeError, TypeError, ValueError) as err:
                    raise ValueError(f"Invalid batch request line: {line_s}") from err
                raw_id = data.get("id")
                if raw_id is not None and not isinstance(raw_id, str):
                    raise ValueError(f"Invalid batch request line: {line_s}")
                job = BatchTraceJob(
                    id=raw_id or "",
                    source=source,
                    stdin=data.get("stdin", ""),
                    breakpoints=bps_list,
                    all_breakpoints=data.get("allBreakpoints", data.get("all_breakpoints", True)),
                    accumulate_breakpoints=data.get(
                        "accumulateBreakpoints",
                        data.get("accumulate_breakpoints", False),
                    ),
                    remove_main_args=data.get("removeMainArgs", data.get("remove_main_args", True)),
                    inline_strings=data.get("inlineStrings", data.get("inline_strings", False)),
                    type_style=data.get("typeStyle", data.get("type_style", "simple")),
                    timeout_ms=data.get("timeout_ms", 30000),
                    include_enum_static_fields=data.get("include_enum_static_fields", False),
                )
                result = client.execute(job)
                out_file.write(json.dumps({"id": job.id, "result": result}) + "\n")
                out_file.flush()
        return

    # get java file from stdin
    with fileinput.input(args.input) as f:
        java_input = "".join(f).rstrip()

    parsed_breakpoints: set[int] = set()
    if args.breakpoints:
        for bp_str in args.breakpoints:
            for item in bp_str.split(","):
                item_trimmed = item.strip()
                if item_trimmed:
                    parsed_breakpoints.add(int(item_trimmed))
    breakpoints = parsed_breakpoints or DEFAULT_BREAKPOINTS_SET

    trace = generate_trace(
        java_home,
        java_input,
        args.trace_timeout,
        include_enum_static_fields=args.include_enum_static_fields,
        breakpoints=breakpoints,
        all_breakpoints=args.all_breakpoints,
        type_style=args.type_style,
        stdin=args.stdin,
        stdin_file=args.stdin_file,
        extra_tracer_args=extra_tracer_args or None,
        eval_enum_hash=args.eval_enum_hash,
    )

    if args.output is None:
        print(trace)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            _ = f.write(trace)


if __name__ == "__main__":
    main()
