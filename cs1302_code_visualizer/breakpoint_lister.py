"""List available breakpoints for a Java source program."""

import argparse
import fileinput
import json
import logging
import subprocess
import sys
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any

import platformdirs
from rich.console import Console

from . import trace_generator

logger: logging.Logger = logging.getLogger(__name__)

cache_dir: Path = Path(
    platformdirs.user_cache_dir(
        "cs1302-code-visualizer",
        ensure_exists=True,
    )
)


def list_breakpoints(
    java_program: str,
    java_home: Path | None,
    timeout_secs: float | None = None,
    output_json: bool = False,
    verbose: bool = False,
) -> str:
    """List available breakpoints for a Java source program as raw text or JSON string."""
    if not (java_home and trace_generator.jdk_exists(java_home)):
        java_home = trace_generator.ensure_jdk_installed()

    try:
        trace_generator.ensure_code_tracer_installed()
    except Exception as exc:
        raise Exception("Unable to ensure code tracer is installed!") from exc

    args: list[str] = []

    args.append("list-breakpoints")
    if output_json:
        args.append("--json")

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


def list_breakpoints_json(
    java_program: str,
    java_home: Path | None,
    timeout_secs: float | None = None,
    verbose: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List available breakpoints for a Java source program as parsed JSON object."""
    list_breakpoints_output = list_breakpoints(
        java_program=java_program,
        java_home=java_home,
        timeout_secs=timeout_secs,
        output_json=True,
        verbose=verbose,
    ).strip()
    return json.loads(list_breakpoints_output)


def main() -> None:
    """Command-line entry point for listing Java breakpoints."""
    console = Console(stderr=True)
    parser = argparse.ArgumentParser(description="List available breakpoints for a Java program.")

    _ = parser.add_argument(
        "--json",
        "-j",
        help="Output JSON.",
        action="store_true",
    )

    _ = parser.add_argument(
        "--trace-timeout",
        help="Max execution time (in seconds) of the trace execution.",
        type=float,
    )

    _ = parser.add_argument(
        "--verbose",
        "-v",
        help="Enable output from logger.",
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

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.jdk is not None and trace_generator.jdk_exists(args.jdk):
        java_home = Path(args.jdk)
    else:
        with console.status("Installing the JDK..."):
            java_home = trace_generator.ensure_jdk_installed()

    with console.status("Downloading Java tracer..."):
        trace_generator.ensure_code_tracer_installed()

    # get java file from stdin
    java_input = "".join(fileinput.input(args.input))

    try:
        with console.status("Generating execution trace..."):
            list_breakpoints_output = list_breakpoints(
                java_program=java_input,
                java_home=java_home,
                timeout_secs=args.trace_timeout,
                output_json=args.json,
            )
    except CalledProcessError as e:
        logger.exception("Trace generation failed with exit code %d and output:", e.returncode)
        sys.exit(1)

    if args.output is None:
        print(list_breakpoints_output)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            _ = f.write(list_breakpoints_output)


if __name__ == "__main__":
    main()
