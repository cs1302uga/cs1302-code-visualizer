#!/bin/env python3

import fileinput

import json
from pathlib import Path
from sys import stdout
import logging

from . import browser_driver
from . import trace_generator


def render_images(
    java_source: str,
    breakpoints: set[int],
    *,
    java_home: Path | None = None,
    timeout_secs: int | None = None,
    dpi: int = 1,
    format: str = "PNG",
    inline_strings: bool = True,
    remove_main_args: bool = True,
) -> dict[int, bytes]:
    """Visualize the state of a Java program at given breakpoints.
    java_source:      The Java source code to visualize.
    breakpoints:      The source lines at which an execution snapshot should be taken. If a line is
                      executed multiple times, the last execution is the one visualized. If a breakpoint
                      cannot be created on a line, it will not be included in this function's output.
    java_home:        A path to a JDK 21+ installation home. If not provided, a JDK will be fetched
                      automatically.
    timeout_secs:     Maximum execution time for the Java source's trace generation, or no limit if
                      None.
    dpi:              A positive, integer multiplicative factor for the output image's resolution.
    format:           The image output format. This gets passed directly into PIL's Image.save() method,
                      refer to that method's documentation for acceptable values.
    inline_strings:   True if strings should be inlined in the visualization, false if they should be
                      rendered seperately on the heap.
    remove_main_args: False if the visualization should include the main method's `args` parameter,
                      True otherwise

    out:            Mapping from breakpoint lines to visualization images.

    Note that exceptions may be raised if image generation fails.
    """
    if not (java_home and trace_generator.jdk_exists(java_home)):
        java_home = trace_generator.ensure_jdk_installed()

    trace_generator.ensure_code_tracer_installed()

    trace = trace_generator.generate_trace(
        java_home,
        java_source,
        timeout_secs,
        inline_strings,
        remove_main_args,
        breakpoints,
    )

    traces: dict[str, dict] = json.loads(trace)
    out = dict()
    for line in traces:
        out[int(line)] = browser_driver.generate_image(
            json.dumps(traces[line]), dpi=dpi, format=format
        )
    return out


def render_image(
    java_source: str,
    *,
    java_home: Path | None = None,
    timeout_secs: int | None = None,
    dpi: int = 1,
    format: str = "PNG",
    inline_strings: bool = False,
    remove_main_args: bool = True,
    breakpoint_line: int = -1,
    verbose: bool = False,
) -> bytes:
    """Visualize the state of a Java program just before exiting as an image.

    Args:

        java_source: The Java source code to visualize.

        java_home: A path to a JDK 21+ installation home. If not provided, a JDK will be fetched
            automatically.

        timeout_secs: Maximum execution time for the Java source's trace generation, or no limit if
            None.

        dpi: A positive, integer multiplicative factor for the output image's resolution.

        format: The image output format. This gets passed directly into PIL's Image.save() method,
            refer to that method's documentation for acceptable values.

        inline_strings: True if strings should be inlined in the visualization, false if they should
            be rendered seperately on the heap.

        remove_main_args: False if the visualization should include the main method's `args`
            parameter, True otherwise.

        breakpoint_line: The breakpoint line number to use for the visualization. Breakpoints happen
            before the line they are associated with, so you need to specify the first breakpoint
            line that is available after the code you want to visualize in order for it to ensure
            that it is executed. The default value is -1, which indicates that that the
            visualization should depict what memory looks like just after the entire body of the
            main method has executed.

    Return:

        Raw bytes of the visualization image.

    Note that exceptions may be raised if image generation fails.

    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not (java_home and trace_generator.jdk_exists(java_home)):
        java_home = trace_generator.ensure_jdk_installed()

    try:
        trace_generator.ensure_code_tracer_installed()
    except Exception as exc:
        raise Exception("Unable to ensure code tracer is installed!") from exc

    trace: str = "{}"

    try:
        breakpoints: set[int] = {breakpoint_line}
        execution_trace: str = trace_generator.generate_trace(
            java_home,
            java_source,
            timeout_secs,
            inline_strings,
            remove_main_args,
            breakpoints=breakpoints,
        )
        traces: dict[str, dict] = json.loads(execution_trace)
        for line in traces:
            trace = json.dumps(traces[line])
            break
    except Exception as exc:
        raise Exception("Unable to generate execution trace!") from exc

    try:
        output: bytes = browser_driver.generate_image(
            trace,
            dpi=dpi,
            format=format,
        )
        return output
    except Exception as exc:
        raise Exception(
            f"Unable to generate image from execution trace:\n\n{trace}\n",
        ) from exc


def main() -> None:
    java_source: str = "".join(fileinput.input())
    rendered_image: bytes = render_image(java_source, dpi=2)
    stdout.buffer.write(rendered_image)
