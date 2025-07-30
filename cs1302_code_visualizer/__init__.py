#!/bin/env python3

import fileinput

import json
from pathlib import Path
from sys import stdout

from . import browser_driver
from . import trace_generator


def render_images(
    java_source: str,
    breakpoints: set[int],
    *,
    java_home: Path | None = None,
    timeout_secs: int | None = None,
    dpi: int = 4,
    format: str = "PNG",
    inline_strings: bool = True,
) -> dict[int, bytes]:
    """Visualize the state of a Java program at given breakpoints.
    java_source:    The Java source code to visualize.
    breakpoints:    The source lines at which an execution snapshot should be taken. If a line is
                    executed multiple times, the last execution is the one visualized. If a breakpoint
                    cannot be created on a line, it will not be included in this function's output.
    java_home:      A path to a JDK 21+ installation home. If not provided, a JDK will be fetched
                    automatically.
    timeout_secs:   Maximum execution time for the Java source's trace generation, or no limit if
                    None.
    dpi:            A positive, integer multiplicative factor for the output image's resolution.
    format:         The image output format. This gets passed directly into PIL's Image.save() method,
                    refer to that method's documentation for acceptable values.
    inline_strings: True if strings should be inlined in the visualization, false if they should be
                    rendered seperately on the heap.

    out:            Mapping from breakpoint lines to visualization images.

    Note that exceptions may be raised if image generation fails.
    """
    if not (java_home and trace_generator.jdk_exists(java_home)):
        java_home = trace_generator.ensure_jdk_installed()

    trace_generator.ensure_code_tracer_installed()

    trace = trace_generator.generate_trace(
        java_home, java_source, timeout_secs, inline_strings, breakpoints
    )

    traces: dict[str, dict] = json.loads(trace)
    out = dict()
    for line in traces:
        out[int(line)] = browser_driver.generate_image(json.dumps(traces[line]), dpi=dpi, format=format)
    return out


def render_image(
    java_source: str,
    *,
    java_home: Path | None = None,
    timeout_secs: int | None = None,
    dpi: int = 4,
    format: str = "PNG",
    inline_strings: bool = True,
) -> bytes:
    """Visualize the state of a Java program just before exiting as an image.
    java_source:    The Java source code to visualize.
    java_home:      A path to a JDK 21+ installation home. If not provided, a JDK will be fetched
                    automatically.
    timeout_secs:   Maximum execution time for the Java source's trace generation, or no limit if
                    None.
    dpi:            A positive, integer multiplicative factor for the output image's resolution.
    format:         The image output format. This gets passed directly into PIL's Image.save() method,
                    refer to that method's documentation for acceptable values.
    inline_strings: True if strings should be inlined in the visualization, false if they should be
                    rendered seperately on the heap.

    out:            Raw bytes of the visualization image.

    Note that exceptions may be raised if image generation fails.
    """
    if not (java_home and trace_generator.jdk_exists(java_home)):
        java_home = trace_generator.ensure_jdk_installed()

    trace_generator.ensure_code_tracer_installed()

    trace = trace_generator.generate_trace(
        java_home, java_source, timeout_secs, inline_strings
    )

    return browser_driver.generate_image(trace, dpi=dpi, format=format)


def main() -> None:
    java_source: str = "".join(fileinput.input())
    rendered_image: bytes = render_image(java_source)
    stdout.buffer.write(rendered_image)
