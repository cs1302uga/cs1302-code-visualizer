"""CS1302 Java Code Visualizer package."""

import fileinput
import json
import logging
import os
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import browser_driver, trace_generator
from .breakpoint_lister import list_breakpoints, list_breakpoints_json
from .browser_driver import generate_image
from .errors import CodeVisError, CodeVisRenderError, CodeVisTraceGeneratorError
from .trace_generator import generate_trace

__all__ = [
    "CodeVisError",
    "CodeVisRenderError",
    "CodeVisTraceGeneratorError",
    "generate_image",
    "generate_trace",
    "list_breakpoints",
    "list_breakpoints_json",
    "main",
    "render_image",
    "render_images",
]

logger: logging.Logger = logging.getLogger(__name__)

# Enable DEBUG_MODE with
# CS1302_DEBUG=1
# CS1302_DEBUG=True
DEBUG_MODE: bool = os.getenv("CS1302_DEBUG", "").strip().lower() in ["1", "true"]

# Disable HEADLESS_MODE with
# CS1302_HEADLESS=1
# CS1302_HEADLESS=True
DISABLE_HEADLESS_MODE: bool = os.getenv("CS1302_HEADLESS", "").strip().lower() in [
    "1",
    "true",
]

if DEBUG_MODE:
    # our logger
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())


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
    include_types: bool = True,
    text_memory_labels: bool = False,
    strip_type_prefixes: Sequence[str] | None = None,
    render_all_breakpoint_occurrences: bool = False,
    include_enum_static_fields: bool = False,
) -> dict[int, bytes] | dict[int, list[bytes]]:
    """Visualize the state of a Java program at given breakpoints.
    java_source:         The Java source code to visualize.
    breakpoints:         The source lines at which an execution snapshot should be taken. If a line is
                         executed multiple times, the last execution is the one visualized. If a breakpoint
                         cannot be created on a line, it will not be included in this function's output.
    java_home:           A path to a JDK 21+ installation home. If not provided, a JDK will be fetched
                         automatically.
    timeout_secs:        Maximum execution time for the Java source's trace generation, or no limit if
                         None.
    dpi:                 A positive, integer multiplicative factor for the output image's resolution.
    format:              The image output format. This gets passed directly into PIL's Image.save() method,
                         refer to that method's documentation for acceptable values.
    inline_strings:      True if strings should be inlined in the visualization, false if they should be
                         rendered separately on the heap.
    remove_main_args:    False if the visualization should include the main method's `args` parameter,
                         True otherwise
    include_types:       True if type tags should be included in this visualization, False otherwise.
    text_memory_labels:  True if object connections should be rendered as text labels, False otherwise.
    strip_type_prefixes: A list of prefix strings to strip from the beginning of type labels.
    render_all_breakpoint_occurrences: If true, render each occurrence of a breakpoint as a separate image.
                         This changes the return type of the function.

    out:                 Mapping from a breakpoint line to a visualization image. If
                         render_all_breakpoint_occurrences is true, then this instead returns a mapping from
                         a breakpoint line to a list of visualization images (first occurrence first,
                         last occurrence last).
    include_enum_static_fields: True if enum constants and $VALUES should be included in the
                         global static fields list, False otherwise.

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
        accumulate_breakpoints=render_all_breakpoint_occurrences,
        include_enum_static_fields=include_enum_static_fields,
    )

    logger.debug(f"{render_all_breakpoint_occurrences=}")
    if render_all_breakpoint_occurrences:
        traces_accumulated: dict[str, list[dict[str, Any]]] = json.loads(trace)
        out_accumulated: dict[int, list[bytes]] = defaultdict(list)
        for line in traces_accumulated:
            for occurrence in traces_accumulated[line]:
                out_accumulated[int(line)].append(
                    browser_driver.generate_image(
                        json.dumps(occurrence),
                        dpi=dpi,
                        format=format,
                        include_types=include_types,
                        text_memory_labels=text_memory_labels,
                        strip_type_prefixes=strip_type_prefixes,
                    )
                )
        return out_accumulated
    else:
        traces: dict[str, dict[str, Any]] = json.loads(trace)
        out_single: dict[int, bytes] = dict()
        for line in traces:
            out_single[int(line)] = browser_driver.generate_image(
                json.dumps(traces[line]),
                dpi=dpi,
                format=format,
                include_types=include_types,
                text_memory_labels=text_memory_labels,
                strip_type_prefixes=strip_type_prefixes,
            )
        return out_single


def render_image(
    java_source: str,
    *,
    java_home: Path | None = None,
    timeout_secs: int | None = None,
    dpi: int = 1,
    format: str = "PNG",
    inline_strings: bool = False,
    remove_main_args: bool = True,
    breakpoint_line: int | tuple[int, int] = -1,
    verbose: bool = False,
    include_types: bool = True,
    text_memory_labels: bool = False,
    strip_type_prefixes: Sequence[str] | None = None,
    include_enum_static_fields: bool = False,
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
            be rendered separately on the heap.

        remove_main_args: False if the visualization should include the main method's `args`
            parameter, True otherwise.

        breakpoint_line: The breakpoint line number to use for the visualization. Breakpoints happen
            before the line they are associated with, so you need to specify the first breakpoint
            line that is available after the code you want to visualize in order for it to ensure
            that it is executed. The default value is -1, which indicates that that the
            visualization should depict what memory looks like just after the entire body of the
            main method has executed.

            If a tuple (a,b) is passed, an image is generated at the b-th occurrence of the breakpoint at
            line a. If there is no b-th occurrence, the last occurrence is used.

        include_types: True if type tags should be included in this visualization, False otherwise.

        text_memory_labels: True if object connections should be rendered as text labels, False otherwise.

        strip_type_prefixes: A list of prefix strings to strip from the beginning of type labels.

        include_enum_static_fields: True if enum constants and $VALUES should be included in the
            global static fields list, False otherwise.

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

    breakpoint_index: int | None = None
    if (
        isinstance(breakpoint_line, tuple)
        and len(breakpoint_line) == 2
        and all(isinstance(x, int) for x in breakpoint_line)
    ):
        breakpoints: set[int] = {breakpoint_line[0]}
        breakpoint_index = breakpoint_line[1] - 1
    else:
        assert isinstance(breakpoint_line, int), (
            "breakpoint_line must be either an int or an (int, int)"
        )
        breakpoints = {breakpoint_line}

    try:
        execution_trace: str = trace_generator.generate_trace(
            java_home,
            java_source,
            timeout_secs,
            inline_strings,
            remove_main_args,
            breakpoints=breakpoints,
            accumulate_breakpoints=breakpoint_index is not None,
            include_enum_static_fields=include_enum_static_fields,
        )

        traces: dict[str, Any] = json.loads(execution_trace)

        logging.debug(f"TRACES: {traces=}")

        if breakpoint_index is not None:
            for line in traces:
                line_traces = traces[line]
                if isinstance(line_traces, list) and breakpoint_index in range(len(line_traces)):
                    trace = json.dumps(line_traces[breakpoint_index])
                elif isinstance(line_traces, list) and line_traces:
                    trace = json.dumps(line_traces[-1])
                else:
                    trace = json.dumps(line_traces)
                break
        else:
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
            include_types=include_types,
            text_memory_labels=text_memory_labels,
            strip_type_prefixes=strip_type_prefixes,
            breakpoint=None,
        )
        return output
    except Exception as exc:
        raise Exception(
            f"Unable to generate image from execution trace:\n\n{trace}\n",
        ) from exc


def main() -> None:
    """Read Java source from standard input and write rendered image to standard output."""
    java_source: str = "".join(fileinput.input("-"))
    rendered_image: bytes = render_image(
        java_source,
        dpi=2,
        strip_type_prefixes=["java.lang."],
        inline_strings=False,
        include_types=True,
        include_enum_static_fields=False,
    )
    _ = sys.stdout.buffer.write(rendered_image)
