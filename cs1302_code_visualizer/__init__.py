"""CS1302 Java Code Visualizer package.

Normative References:
    PEP 257 – Docstring Conventions (https://peps.python.org/pep-0257/)
    PEP 484 – Type Hints (https://peps.python.org/pep-0484/)
    PEP 695 – Type Parameter Syntax (https://peps.python.org/pep-0695/)
"""

import argparse
import concurrent.futures
import fileinput
import json
import logging
import os
import sys
import uuid
from collections import defaultdict, deque
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import browser_driver, trace_generator
from .array_options import ArrayOrientation, validate_array_options
from .batch_tracer import BatchTraceJob, BatchTracerClient
from .breakpoint_lister import list_breakpoints, list_breakpoints_json
from .browser_driver import (
    generate_image,
    generate_step_images,
    render_html,
    render_html_cli,
)
from .errors import (
    BreakpointResolutionError,
    CodeVisError,
    CodeVisRenderError,
    CodeVisTraceGeneratorError,
    CodeVisualizerError,
    JDKError,
    JDKInstallationError,
    RenderError,
    TraceGeneratorError,
    TracerDownloadError,
)
from .session import RenderingSession
from .theme_options import Theme, add_theme_argument, theme_options
from .trace_generator import generate_trace, generate_traces, get_sanitized_java_env

__all__ = [
    "BatchRenderJob",
    "BatchTraceJob",
    "BatchTracerClient",
    "BreakpointResolutionError",
    "CodeVisError",
    "CodeVisRenderError",
    "CodeVisTraceGeneratorError",
    "CodeVisualizerError",
    "JDKError",
    "JDKInstallationError",
    "RenderError",
    "RenderingSession",
    "TraceGeneratorError",
    "TracerDownloadError",
    "generate_image",
    "generate_step_images",
    "generate_trace",
    "generate_traces",
    "get_sanitized_java_env",
    "list_breakpoints",
    "list_breakpoints_json",
    "main",
    "render_batch_images",
    "render_html",
    "render_html_cli",
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
    theme: Theme | None = None,
    array_orientation: ArrayOrientation = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: dict[str, ArrayOrientation] | None = None,
    render_all_breakpoint_occurrences: bool = False,
    include_enum_static_fields: bool = False,
    type_style: str = "simple",
    stdin: str | None = None,
    stdin_file: Path | str | None = None,
    session: RenderingSession | None = None,
    eval_enum_hash: bool = True,
) -> dict[int, bytes] | dict[int, list[bytes]]:
    """Visualize the state of a Java program at given breakpoints.

    Args:
        java_source: The Java source code to visualize.
        breakpoints: The source lines at which an execution snapshot should be taken. If a line is
            executed multiple times, the last execution is the one visualized. If a breakpoint
            cannot be created on a line, it will not be included in this function's output.
        java_home: A path to a JDK 21+ installation home. If not provided, a JDK will be fetched
            automatically.
        timeout_secs: Maximum execution time for the Java source's trace generation, or no limit if
            None.
        dpi: Positive integer scale for raster resolution or SVG display dimensions.
        format: SVG for standalone vector output with editable text, or a raster format
            accepted by PIL's Image.save() method.
        inline_strings: True if strings should be inlined in the visualization, false if they should be
            rendered separately on the heap.
        remove_main_args: False if the visualization should include the main method's `args` parameter,
            True otherwise.
        include_types: True if type tags should be included in this visualization, False otherwise.
        text_memory_labels: True if object connections should be rendered as text labels, False otherwise.
        strip_type_prefixes: A list of prefix strings to strip from the beginning of type labels.
        theme: Light, dark, auto, or None for the default host-inherited theme.
        array_orientation: Base array orientation, or the 1D orientation when alternating.
        alternate_array_orientations: Flip orientation for each additional dimension.
        array_orientations: Per-heap-object orientation overrides, taking precedence over the base.
        render_all_breakpoint_occurrences: If true, render each occurrence of a breakpoint as a separate image.
            This changes the return type of the function.
        session: Optional build-scoped browser and trace-cache owner.
        type_style: Type qualification style ('fqn' or 'simple').
        stdin: Standard input string provided to the traced Java program.
        stdin_file: Path to file whose content is provided via standard input.
        include_enum_static_fields: True if enum constants and $VALUES should be included in the
            global static fields list, False otherwise.
        eval_enum_hash: True if lazy enum hash codes should be eagerly evaluated,
            False to leave uninitialized hash codes as 0.

    Returns:
        Mapping from a breakpoint line to a visualization image. If
        render_all_breakpoint_occurrences is true, then this instead returns a mapping from
        a breakpoint line to a list of visualization images (first occurrence first,
        last occurrence last).

    Note that exceptions may be raised if image generation fails.
    """
    theme_options(theme)
    validate_array_options(array_orientation, alternate_array_orientations, array_orientations)
    if not (java_home and trace_generator.jdk_exists(java_home)):
        java_home = trace_generator.ensure_jdk_installed()

    if session is None:
        trace_generator.ensure_code_tracer_installed()

    generate = session.generate_trace if session is not None else trace_generator.generate_trace
    trace = generate(
        java_home,
        java_source,
        timeout_secs,
        inline_strings,
        remove_main_args,
        breakpoints,
        accumulate_breakpoints=render_all_breakpoint_occurrences,
        include_enum_static_fields=include_enum_static_fields,
        type_style=type_style,
        stdin=stdin,
        stdin_file=stdin_file,
        eval_enum_hash=eval_enum_hash,
    )

    logger.debug(f"{render_all_breakpoint_occurrences=}")
    return _resolve_and_render_trace(
        trace,
        breakpoints,
        dpi=dpi,
        format=format,
        include_types=include_types,
        text_memory_labels=text_memory_labels,
        strip_type_prefixes=strip_type_prefixes,
        **theme_options(theme),
        array_orientation=array_orientation,
        alternate_array_orientations=alternate_array_orientations,
        array_orientations=array_orientations,
        render_all_occurrences=render_all_breakpoint_occurrences,
        session=session,
    )


def _resolve_and_render_trace(
    trace: str,
    breakpoints: set[int],
    *,
    dpi: int = 1,
    format: str = "PNG",
    include_types: bool = True,
    text_memory_labels: bool = False,
    strip_type_prefixes: Sequence[str] | None = None,
    theme: Theme | None = None,
    array_orientation: ArrayOrientation = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: dict[str, ArrayOrientation] | None = None,
    render_all_occurrences: bool = False,
    session: RenderingSession | None = None,
) -> dict[int, bytes] | dict[int, list[bytes]]:
    parsed_trace: Any = json.loads(trace)
    is_chronological = (
        isinstance(parsed_trace, dict)
        and "trace" in parsed_trace
        and isinstance(parsed_trace["trace"], list)
    )

    if is_chronological:
        source_code: str = parsed_trace.get("code", "")
        frames_list: list[dict[str, Any]] = [
            f for f in parsed_trace["trace"] if isinstance(f, dict)
        ]
        if render_all_occurrences:
            out_accumulated: dict[int, list[bytes]] = defaultdict(list)
            for frame in frames_list:
                line_no = frame.get("line")
                if line_no is not None and (line_no in breakpoints or -1 in breakpoints):
                    target_key = line_no if line_no in breakpoints else -1
                    frame_payload = {"code": source_code, "trace": [frame]}
                    out_accumulated[target_key].append(
                        browser_driver.generate_image(
                            json.dumps(frame_payload),
                            dpi=dpi,
                            format=format,
                            include_types=include_types,
                            text_memory_labels=text_memory_labels,
                            strip_type_prefixes=strip_type_prefixes,
                            **theme_options(theme),
                            array_orientation=array_orientation,
                            alternate_array_orientations=alternate_array_orientations,
                            array_orientations=array_orientations,
                            session=session,
                        )
                    )
            return out_accumulated
        else:
            latest_by_line: dict[int, dict[str, Any]] = {}
            for frame in frames_list:
                line_no = frame.get("line")
                if line_no is not None and line_no in breakpoints:
                    latest_by_line[line_no] = frame
            if -1 in breakpoints and frames_list:
                latest_by_line[-1] = frames_list[-1]
            out_single: dict[int, bytes] = {}
            for line_no, frame in latest_by_line.items():
                frame_payload = {"code": source_code, "trace": [frame]}
                out_single[line_no] = browser_driver.generate_image(
                    json.dumps(frame_payload),
                    dpi=dpi,
                    format=format,
                    include_types=include_types,
                    text_memory_labels=text_memory_labels,
                    strip_type_prefixes=strip_type_prefixes,
                    **theme_options(theme),
                    array_orientation=array_orientation,
                    alternate_array_orientations=alternate_array_orientations,
                    array_orientations=array_orientations,
                    session=session,
                )
            return out_single
    elif render_all_occurrences:
        traces_accumulated: dict[str, list[dict[str, Any]]] = parsed_trace
        out_accumulated_dict: dict[int, list[bytes]] = defaultdict(list)
        for line, occurrences in traces_accumulated.items():
            for occurrence in occurrences:
                out_accumulated_dict[int(line)].append(
                    browser_driver.generate_image(
                        json.dumps(occurrence),
                        dpi=dpi,
                        format=format,
                        include_types=include_types,
                        text_memory_labels=text_memory_labels,
                        strip_type_prefixes=strip_type_prefixes,
                        **theme_options(theme),
                        array_orientation=array_orientation,
                        alternate_array_orientations=alternate_array_orientations,
                        array_orientations=array_orientations,
                        session=session,
                    )
                )
        return out_accumulated_dict
    else:
        traces_dict: dict[str, dict[str, Any]] = parsed_trace
        out_single_dict: dict[int, bytes] = {}
        for line, trace_dict in traces_dict.items():
            out_single_dict[int(line)] = browser_driver.generate_image(
                json.dumps(trace_dict),
                dpi=dpi,
                format=format,
                include_types=include_types,
                text_memory_labels=text_memory_labels,
                strip_type_prefixes=strip_type_prefixes,
                **theme_options(theme),
                array_orientation=array_orientation,
                alternate_array_orientations=alternate_array_orientations,
                array_orientations=array_orientations,
                session=session,
            )
        return out_single_dict


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
    theme: Theme | None = None,
    array_orientation: ArrayOrientation = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: dict[str, ArrayOrientation] | None = None,
    include_enum_static_fields: bool = False,
    type_style: str = "simple",
    stdin: str | None = None,
    stdin_file: Path | str | None = None,
    eval_enum_hash: bool = True,
) -> bytes:
    """Visualize the state of a Java program just before exiting as an image.

    Args:
        java_source: The Java source code to visualize.

        java_home: A path to a JDK 21+ installation home. If not provided, a JDK will be fetched
            automatically.

        timeout_secs: Maximum execution time for the Java source's trace generation, or no limit if
            None.

        dpi: Positive integer scale for raster resolution or SVG display dimensions.

        format: SVG for standalone vector output with editable text, or a raster format
            accepted by PIL's Image.save() method.

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

        verbose: True to enable debug logging, False otherwise.

        include_types: True if type tags should be included in this visualization, False otherwise.

        text_memory_labels: True if object connections should be rendered as text labels, False otherwise.

        strip_type_prefixes: A list of prefix strings to strip from the beginning of type labels.
        theme: Light, dark, auto, or None for the default host-inherited theme.
        array_orientation: Base array orientation, or the 1D orientation when alternating.
        alternate_array_orientations: Flip orientation for each additional dimension.
        array_orientations: Per-heap-object orientation overrides, taking precedence over the base.

        include_enum_static_fields: True if enum constants and $VALUES should be included in the
            global static fields list, False otherwise.

        type_style: Type qualification style ('fqn' or 'simple').

        stdin: Standard input string provided to the traced Java program.

        stdin_file: Path to file whose content is provided via standard input.

        eval_enum_hash: True if lazy enum hash codes should be eagerly evaluated,
            False to leave uninitialized hash codes as 0.

    Returns:
        Raw bytes of the visualization image.

    Note that exceptions may be raised if image generation fails.

    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    theme_options(theme)
    validate_array_options(array_orientation, alternate_array_orientations, array_orientations)
    if not (java_home and trace_generator.jdk_exists(java_home)):
        java_home = trace_generator.ensure_jdk_installed()

    try:
        trace_generator.ensure_code_tracer_installed()
    except Exception as exc:
        raise TracerDownloadError("Unable to ensure code tracer is installed!") from exc

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
            type_style=type_style,
            stdin=stdin,
            stdin_file=stdin_file,
            eval_enum_hash=eval_enum_hash,
        )

        traces: dict[str, Any] = json.loads(execution_trace)

        logger.debug(f"TRACES: {traces=}")

        if breakpoint_index is not None:
            for line_traces in traces.values():
                if isinstance(line_traces, list) and breakpoint_index in range(len(line_traces)):
                    trace = json.dumps(line_traces[breakpoint_index])
                elif isinstance(line_traces, list) and line_traces:
                    trace = json.dumps(line_traces[-1])
                else:
                    trace = json.dumps(line_traces)
                break
        else:
            for trace_val in traces.values():
                trace = json.dumps(trace_val)
                break

    except Exception as exc:
        raise CodeVisError("Unable to generate execution trace!") from exc

    try:
        output: bytes = browser_driver.generate_image(
            trace,
            dpi=dpi,
            format=format,
            include_types=include_types,
            text_memory_labels=text_memory_labels,
            strip_type_prefixes=strip_type_prefixes,
            **theme_options(theme),
            array_orientation=array_orientation,
            alternate_array_orientations=alternate_array_orientations,
            array_orientations=array_orientations,
            breakpoint=None,
        )
        return output
    except Exception as exc:
        raise CodeVisRenderError(
            f"Unable to generate image from execution trace:\n\n{trace}\n",
        ) from exc


@dataclass(frozen=True)
class BatchRenderJob:
    """Specification for a batch rendering job."""

    java_source: str
    breakpoints: set[int]
    job_id: str | None = None
    all_breakpoints: bool = False
    accumulate_breakpoints: bool = False
    inline_strings: bool = True
    remove_main_args: bool = True
    include_types: bool = True
    text_memory_labels: bool = False
    strip_type_prefixes: Sequence[str] | None = None
    render_all_breakpoint_occurrences: bool = False
    include_enum_static_fields: bool = False
    dpi: int = 1
    format: str = "PNG"
    type_style: str = "simple"
    stdin: str = ""
    timeout_secs: int | None = None
    theme: Theme | None = None
    array_orientation: ArrayOrientation = "horizontal"
    alternate_array_orientations: bool = False
    array_orientations: dict[str, ArrayOrientation] | None = None

    def __post_init__(self) -> None:
        """Reject invalid array settings before a batch job starts tracing."""
        theme_options(self.theme)
        validate_array_options(
            self.array_orientation,
            self.alternate_array_orientations,
            self.array_orientations,
        )


def _render_batch_with_session(
    jobs: Sequence[BatchRenderJob], session: RenderingSession
) -> Iterator[dict[int, bytes] | dict[int, list[bytes]]]:
    """Yield ordered rendered jobs while bounding submitted and retained work.

    Args:
        jobs: Rendering specifications in their desired output order.
        session: Shared tracer and browser pool, owned by the caller.

    Yields:
        Image mappings for each input job in order.
    """

    def _submit_trace(i: int, job: BatchRenderJob) -> concurrent.futures.Future[dict[str, Any]]:
        """Submit one job without waiting for its trace.

        Args:
            i: Input position used when generating a job identifier.
            job: Source and tracing options for the request.

        Returns:
            The submitted trace future.
        """
        job_id = job.job_id or f"render_job_{i}_{uuid.uuid4().hex}"
        all_breakpoints = job.all_breakpoints or not job.breakpoints
        trace_job = BatchTraceJob(
            id=job_id,
            source=job.java_source,
            stdin=job.stdin,
            breakpoints=sorted(job.breakpoints) if not all_breakpoints else None,
            all_breakpoints=all_breakpoints,
            accumulate_breakpoints=(
                job.accumulate_breakpoints or job.render_all_breakpoint_occurrences
            ),
            remove_main_args=job.remove_main_args,
            inline_strings=job.inline_strings,
            type_style=job.type_style,
            timeout_ms=int(job.timeout_secs * 1000) if job.timeout_secs else 30000,
            include_enum_static_fields=job.include_enum_static_fields,
        )
        return session.batch_tracer.submit(trace_job)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=session.max_browsers)
    try:

        def _render_one(
            job_spec: BatchRenderJob, trace_fut: concurrent.futures.Future[dict[str, Any]]
        ) -> dict[int, bytes] | dict[int, list[bytes]]:
            """Render one submitted trace using the shared browser pool.

            Args:
                job_spec: Rendering options and selected breakpoints.
                trace_fut: Future providing the execution trace.

            Returns:
                Rendered images keyed by breakpoint.
            """
            trace_dict = trace_fut.result()
            trace_json_str = json.dumps(trace_dict)
            return _resolve_and_render_trace(
                trace_json_str,
                job_spec.breakpoints,
                dpi=job_spec.dpi,
                format=job_spec.format,
                include_types=job_spec.include_types,
                text_memory_labels=job_spec.text_memory_labels,
                strip_type_prefixes=job_spec.strip_type_prefixes,
                **theme_options(job_spec.theme),
                array_orientation=job_spec.array_orientation,
                alternate_array_orientations=job_spec.alternate_array_orientations,
                array_orientations=job_spec.array_orientations,
                render_all_occurrences=job_spec.render_all_breakpoint_occurrences,
                session=session,
            )

        pending = deque()
        remaining = iter(enumerate(jobs))
        window = max(session.max_browsers, session.tracer_workers)
        for i, job in remaining:
            pending.append(executor.submit(_render_one, job, _submit_trace(i, job)))
            if len(pending) == window:
                break
        while pending:
            yield pending.popleft().result()
            next_job = next(remaining, None)
            if next_job is not None:
                i, job = next_job
                pending.append(executor.submit(_render_one, job, _submit_trace(i, job)))
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def render_batch_images(
    jobs: Sequence[BatchRenderJob],
    *,
    session: RenderingSession | None = None,
    max_browsers: int = 2,
    tracer_workers: int = 1,
) -> Iterator[dict[int, bytes] | dict[int, list[bytes]]]:
    """Render execution traces for multiple Java programs in parallel.

    Traces are generated concurrently using the session's BatchTracerClient and streamed
    directly into available pooled browsers for rendering. Results are yielded as a generator
    in the same deterministic order as the input jobs. At most the larger of the
    browser and tracer worker counts is submitted ahead of consumption; memory
    also depends on the size of each trace and its rendered images.

    Args:
        jobs: A sequence of BatchRenderJob specifications.
        session: Optional shared RenderingSession. If None, a new session is created and managed.
        max_browsers: Number of concurrent browser instances when session is not provided.
        tracer_workers: Number of guest worker JVMs when session is not provided.

    Yields:
        Rendered image mappings in the same order as input jobs.
    """
    if not jobs:
        return

    if session is not None:
        yield from _render_batch_with_session(jobs, session)
        return

    with RenderingSession(
        max_browsers=max_browsers,
        tracer_workers=tracer_workers,
        use_batch_tracer=True,
    ) as managed_session:
        yield from _render_batch_with_session(jobs, managed_session)


def main() -> None:
    """Read Java source from standard input and write rendered image to standard output."""
    parser = argparse.ArgumentParser(description="Render Java execution state to an image.")
    _ = parser.add_argument(
        "--input",
        "-i",
        help="Path to Java source file, or `-` for stdin.",
        default="-",
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
    add_theme_argument(parser)
    args = parser.parse_args()

    with fileinput.input(args.input) as f:
        java_source: str = "".join(f)
    rendered_image: bytes = render_image(
        java_source,
        **theme_options(args.theme),
        dpi=2,
        strip_type_prefixes=["java.lang."],
        inline_strings=False,
        include_types=True,
        include_enum_static_fields=False,
        stdin=args.stdin,
        stdin_file=args.stdin_file,
        eval_enum_hash=args.eval_enum_hash,
    )
    _ = sys.stdout.buffer.write(rendered_image)
