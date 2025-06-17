#!/usr/bin/env python3

import fileinput
import jdk
import shutil
import tempfile
import argparse
import json
import os
import sys
import subprocess
from subprocess import CalledProcessError
from pathlib import Path
from halo import Halo as spinner

this_files_dir = Path(os.path.realpath(os.path.dirname(__file__)))


def compile_backend(java_home: Path) -> None:
    if os.path.isdir(this_files_dir / ".backend_classes"):
        # we already have classes from a previous run, short circuit
        return

    backend_dir = this_files_dir / "backend"
    java_files = Path(backend_dir / "cp").rglob("*.java")
    try:
        os.mkdir(this_files_dir / ".backend_classes")
        with spinner(text="Compiling backend...", stream=sys.stderr):
            subprocess.run(
                [
                    java_home / "bin" / "javac",
                    "-cp",
                    f"""{backend_dir / "cp"}:{backend_dir / "cp" / "javax.json-1.0.jar"}:{java_home / "lib" / "tools.jar"}""",
                    "-d",
                    this_files_dir / ".backend_classes",
                    *java_files,
                ],
                capture_output=True,
                check=True,
                text=True,
            )
    except CalledProcessError as e:
        os.rmdir(this_files_dir / ".backend_classes")
        print(
            f"Backend compilation failed with exit code {e.returncode} and the following output:",
            file=sys.stderr,
        )
        print(e.stderr, file=sys.stderr)
        exit(1)


def generate_trace(
    java_home: Path, java_program: str, timeout_secs: float | None = None
) -> str:
    backend_dir = this_files_dir / "backend"
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
                    java_home / "bin" / "java",
                    "-cp",
                    f"""{this_files_dir / ".backend_classes"}:{backend_dir / "cp" / "javax.json-1.0.jar"}:{java_home / "lib" / "tools.jar"}""",
                    "traceprinter.InMemory",
                ],
                input=tracegen_input,
                capture_output=True,
                check=True,
                text=True,
                timeout=timeout_secs,
            ).stdout
    except CalledProcessError as e:
        print(e.cmd)
        print(
            f"Trace generation failed with exit code {e.returncode} and the following output:",
            file=sys.stderr,
        )
        print(e.stderr, file=sys.stderr)
        exit(1)


# if (!trace ||
#     (trace.length == 0) ||
#     (trace[trace.length - 1].event == 'uncaught_exception')) {
#
#   if (trace.length == 1) {
#     var errorLineNo = trace[0].line - 1; /* CodeMirror lines are zero-indexed */
#     if (errorLineNo !== undefined) {
#       // highlight the faulting line in pyInputCodeMirror
#       pyInputCodeMirror.focus();
#       pyInputCodeMirror.setCursor(errorLineNo, 0);
#       var marked = pyInputCodeMirror.addLineClass(errorLineNo, null, 'errorLine');
#       //console.log(marked);
#       var hook = function(marked) { return function() {
#         pyInputCodeMirror.removeLineClass(marked, null, 'errorLine'); // reset line back to normal
#         pyInputCodeMirror.off('change', hook); // cancel
#       }} (marked);
#       pyInputCodeMirror.on('change', hook);
#     }
#
#     alert(trace[0].exception_msg);
#   }
#   else if (trace[trace.length - 1].exception_msg) {
#     alert(trace[trace.length - 1].exception_msg);
#   }
#   else {
#     alert("Whoa, unknown error! Reload to try again, or report a bug to daveagp@gmail.com\n\n(Click the 'Generate URL' button to include a unique URL in your email bug report.)");
#   }
#
#   $('#executeBtn').html("Visualize execution");
#   $('#executeBtn').attr('disabled', false);
# }
def validate_trace(trace_json: str):
    """Catch "show-stopping errors", derived from jv-frontend.js."""
    trace: list = json.loads(trace_json)["trace"]
    if trace and trace[-1]["event"] != "uncaught_exception":
        # no error
        return


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

    args = parser.parse_args()

    if not args.jdk8_home:
        # no java provided, get our own
        if os.path.isdir(this_files_dir / ".jdk8"):
            # assume .jdk8 has a previous download and use that
            java_home = this_files_dir / ".jdk8"
        else:
            # no jdk found, download one from the web
            with (
                tempfile.TemporaryDirectory() as tmp_dir,
                spinner(text="Installing JDK 8...", stream=sys.stderr),
            ):
                java_home = jdk.install("8", path=tmp_dir)
                shutil.move(java_home, this_files_dir / ".jdk8")
                java_home = this_files_dir / ".jdk8"
    else:
        java_home = parser.parse_args().jdk8_home

    compile_backend(java_home)

    # get java file from stdin
    java_input = "".join(fileinput.input())

    trace = generate_trace(
        java_home,
        java_input,
        args.trace_timeout,
    )
    validate_trace(trace)
    print(trace)


if __name__ == "__main__":
    main()
