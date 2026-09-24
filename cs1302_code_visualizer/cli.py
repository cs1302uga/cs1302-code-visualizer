"""Command-line interface for CS1302 Code Visualizer."""

import argparse
import json
import os
import shutil
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import browser_driver, trace_generator
from .array_options import add_array_arguments, array_options_from_args
from .browser_driver import generate_step_images
from .errors import CodeVisError, CodeVisualizerError
from .session import RenderingSession


def format_output_path(
    pattern: str,
    *,
    out_dir: Path | None = None,
    job_id: str = "",
    source_path: Path | None = None,
    step: int | str = "",
    line: int | str = "",
    format: str = "png",
) -> Path:
    """Format an output path using template variables."""
    dirname = ""
    filename = ""
    basename = job_id or "job"
    ext = "java"

    if source_path is not None:
        filename = source_path.name
        basename = source_path.stem
        ext = source_path.suffix.lstrip(".")
        dirname = str(source_path.parent) if str(source_path.parent) != "." else ""

    line_str = f"L{line}" if line != "" else ""

    formatted = pattern.format(
        id=job_id,
        dirname=dirname,
        filename=filename,
        basename=basename,
        ext=ext,
        step=str(step),
        line=line_str,
        format=format.lower(),
    )

    # Avoid accidental leading slash when {dirname} expands to empty string
    if not pattern.startswith("/") and formatted.startswith("/"):
        formatted = formatted.lstrip("/")

    path = Path(formatted)
    if out_dir is not None and not path.is_absolute():
        path = out_dir / path
    return path


def validate_pattern(pattern: str, *, multi_step: bool) -> None:
    """Validate that multi-step outputs include step or line placeholders to avoid collisions."""
    if multi_step and "{step}" not in pattern and "{line}" not in pattern:
        raise ValueError(
            f"Output pattern '{pattern}' must contain '{{step}}' or '{{line}}' when rendering multi-step traces."
        )


class AtomicJobWriter:
    """Safely stages output files to temporary paths and commits them on job success."""

    def __init__(self, *, force: bool = False) -> None:
        """Initialize the atomic writer with optional overwrite force flag."""
        self.force = force
        self.temp_files: list[tuple[Path, Path]] = []
        self.committed = False

    def stage_file(self, target_path: Path, data: bytes | str) -> Path:
        """Stage data alongside its destination without publishing it.

        Args:
            target_path: Destination to publish on successful commit.
            data: Bytes or UTF-8 text to write.

        Returns:
            The temporary file path, tracked for cleanup even if writing fails.

        Raises:
            ValueError: The job already stages this destination.
            FileExistsError: The destination exists and force is disabled.
            OSError: Creating or writing the temporary file fails.
        """
        if any(target.resolve() == target_path.resolve() for _, target in self.temp_files):
            raise ValueError(f"Duplicate output destination: {target_path}. Include '{{step}}'.")
        if target_path.exists() and not self.force:
            raise FileExistsError(
                f"Destination file already exists: {target_path}. Use --force to overwrite."
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = f".{target_path.name}.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
        temp_path = target_path.with_name(temp_name)
        self.temp_files.append((temp_path, target_path))

        if isinstance(data, str):
            temp_path.write_text(data, encoding="utf-8")
        else:
            temp_path.write_bytes(data)

        return temp_path

    def commit(self) -> list[Path]:
        """Publish staged files, rolling back earlier replacements on failure.

        Returns:
            Published destination paths in staging order.

        Raises:
            OSError: Publication failed. Rollback failures are attached as notes,
                and any unrestored backup is retained for recovery.
        """
        committed_paths: list[Path] = []
        backups: list[tuple[Path, Path | None]] = []
        try:
            for temp_path, target_path in self.temp_files:
                backup = None
                if target_path.exists():
                    if not self.force:
                        raise FileExistsError(f"Destination file already exists: {target_path}")
                    backup = temp_path.with_name(f"{temp_path.name}.backup")
                    try:
                        shutil.copy2(target_path, backup)
                    except OSError:
                        backup.unlink(missing_ok=True)
                        raise
                backups.append((target_path, backup))
                temp_path.replace(target_path)
                committed_paths.append(target_path)
        except OSError as exc:
            for target_path, backup in reversed(backups):
                try:
                    if backup is not None:
                        backup.replace(target_path)
                    else:
                        target_path.unlink(missing_ok=True)
                except OSError as rollback_error:
                    exc.add_note(
                        f"Could not restore {target_path}: {rollback_error}; backup: {backup}"
                    )
            raise
        self.committed = True
        for _, backup in backups:
            if backup is not None:
                try:
                    backup.unlink(missing_ok=True)
                except OSError:
                    pass
        return committed_paths

    def cleanup(self) -> None:
        """Remove any uncommitted temporary files."""
        if not self.committed:
            for temp_path, _ in self.temp_files:
                try:
                    if temp_path.exists():
                        temp_path.unlink(missing_ok=True)
                except OSError:
                    pass


def _process_batch_job(
    *,
    job_id: str,
    source_code: str,
    source_path: Path | None,
    out_dir: Path | None,
    output_pattern: str,
    trace_pattern: str | None,
    all_steps: bool,
    breakpoints: set[int],
    dpi: int,
    format: str,
    force: bool,
    include_types: bool,
    text_memory_labels: bool,
    strip_type_prefixes: Sequence[str] | None,
    session: RenderingSession,
    java_home: Path | None,
    array_options: dict[str, Any] | None = None,
) -> list[Path]:
    """Execute trace generation, rendering, and atomic file emission for a single batch job."""
    writer = AtomicJobWriter(force=force)
    try:
        # Generate trace
        trace_text = session.generate_trace(
            java_home,
            source_code,
            breakpoints=breakpoints or {-1},
            accumulate_breakpoints=all_steps,
            all_breakpoints=all_steps or not bool(breakpoints),
        )

        # Stage trace file if requested
        if trace_pattern:
            trace_path = format_output_path(
                trace_pattern,
                out_dir=out_dir,
                job_id=job_id,
                source_path=source_path,
                format="json",
            )
            writer.stage_file(trace_path, trace_text)

        # Stage image files
        if all_steps:
            images = generate_step_images(
                trace_text,
                dpi=dpi,
                format=format,
                include_types=include_types,
                text_memory_labels=text_memory_labels,
                strip_type_prefixes=strip_type_prefixes,
                **(array_options or {}),
                session=session,
            )
            lines = _image_lines(trace_text, len(images)) if "{line}" in output_pattern else []
            for idx, img_bytes in enumerate(images):
                img_path = format_output_path(
                    output_pattern,
                    out_dir=out_dir,
                    job_id=job_id,
                    source_path=source_path,
                    step=idx,
                    line=lines[idx] if lines else "",
                    format=format,
                )
                writer.stage_file(img_path, img_bytes)
        else:
            img_bytes = browser_driver.generate_image(
                trace_text,
                dpi=dpi,
                format=format,
                include_types=include_types,
                text_memory_labels=text_memory_labels,
                strip_type_prefixes=strip_type_prefixes,
                **(array_options or {}),
                session=session,
            )
            img_path = format_output_path(
                output_pattern,
                out_dir=out_dir,
                job_id=job_id,
                source_path=source_path,
                step="final",
                line=_image_lines(trace_text, 1)[-1] if "{line}" in output_pattern else "",
                format=format,
            )
            writer.stage_file(img_path, img_bytes)

        return writer.commit()
    except Exception:
        writer.cleanup()
        raise


def _image_lines(trace_text: str, count: int) -> list[int]:
    """Resolve source lines for the frames selected by the image renderer.

    Args:
        trace_text: Raw or breakpoint-keyed execution trace JSON.
        count: Number of rendered frames; one selects the final frame.

    Returns:
        Source line numbers in rendering order.

    Raises:
        ValueError: A rendered frame has no integer source line.
    """
    payload = browser_driver.resolve_trace_payload(trace_text)
    frames = payload.get("trace") if isinstance(payload, dict) else None
    if not isinstance(frames, list) or not frames:
        raise ValueError("Output pattern '{line}' requires source line metadata.")
    selected = frames[-1:] if count == 1 else frames
    if len(selected) != count or any(
        not isinstance(frame, dict) or type(frame.get("line")) is not int for frame in selected
    ):
        raise ValueError("Output pattern '{line}' requires source line metadata for every frame.")
    return [frame["line"] for frame in selected]


def run_batch_cli(args: argparse.Namespace) -> int:
    """Handle batch mode execution across files, directory, or NDJSON manifest."""
    multi_step = bool(args.all_steps or args.breakpoints)
    output_pattern: str = (
        args.output_pattern
        if args.output_pattern is not None
        else ("{dirname}/{basename}.{step}.png" if multi_step else "{dirname}/{basename}.png")
    )

    try:
        validate_pattern(output_pattern, multi_step=multi_step)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else None

    # Collect jobs
    jobs: list[tuple[str, str, Path | None, set[int], dict[str, Any]]] = []
    array_defaults = array_options_from_args(args)

    # 1. Directory scan
    if args.input_dir:
        input_dir = Path(args.input_dir)
        if not input_dir.is_dir():
            print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
            return 1
        for java_file in sorted(input_dir.rglob("*.java")):
            try:
                code = java_file.read_text(encoding="utf-8")
                rel_path = java_file.relative_to(input_dir)
                jobs.append((
                    java_file.stem,
                    code,
                    rel_path,
                    set(args.breakpoints or []),
                    array_defaults,
                ))
            except OSError as exc:
                print(f"Error reading {java_file}: {exc}", file=sys.stderr)
                return 1

    # 2. Positional files
    if args.files:
        for file_arg in args.files:
            file_path = Path(file_arg)
            if not file_path.is_file():
                print(f"Error: File not found: {file_path}", file=sys.stderr)
                return 1
            try:
                code = file_path.read_text(encoding="utf-8")
                jobs.append((
                    file_path.stem,
                    code,
                    file_path,
                    set(args.breakpoints or []),
                    array_defaults,
                ))
            except OSError as exc:
                print(f"Error reading {file_path}: {exc}", file=sys.stderr)
                return 1

    # 3. NDJSON manifest
    if args.input and args.input != "-":
        input_path = Path(args.input)
        if not input_path.is_file():
            print(f"Error: Input file not found: {input_path}", file=sys.stderr)
            return 1
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise TypeError(f"line {line_idx + 1}: job must be a JSON object")
                    try:
                        array_options = array_options_from_args(args, payload)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"line {line_idx + 1}: {exc}") from exc
                    job_id = payload.get("id", f"job_{line_idx}")
                    src = payload.get("source", "")
                    bps = set(payload.get("breakpoints", [])) or set(args.breakpoints or [])
                    jobs.append((job_id, src, None, bps, array_options))
        except (OSError, TypeError, ValueError) as exc:
            print(f"Error reading manifest {input_path}: {exc}", file=sys.stderr)
            return 1

    if not jobs:
        print("Error: No Java sources found or specified for batch execution.", file=sys.stderr)
        return 1

    java_home = trace_generator.ensure_jdk_installed()
    trace_generator.ensure_code_tracer_installed()

    success_count = 0
    with RenderingSession(
        max_browsers=args.browsers,
        tracer_workers=args.workers,
        use_batch_tracer=True,
    ) as session:
        for job_id, source_code, source_path, bps, array_options in jobs:
            try:
                _process_batch_job(
                    job_id=job_id,
                    source_code=source_code,
                    source_path=source_path,
                    out_dir=out_dir,
                    output_pattern=output_pattern,
                    trace_pattern=args.trace_pattern,
                    all_steps=args.all_steps,
                    breakpoints=bps,
                    dpi=args.dpi,
                    format=args.format,
                    force=args.force,
                    include_types=args.include_types,
                    text_memory_labels=args.text_memory_labels,
                    strip_type_prefixes=args.strip_type_prefixes,
                    session=session,
                    java_home=java_home,
                    array_options=array_options,
                )
                success_count += 1
            except (
                CodeVisError,
                CodeVisualizerError,
                FileExistsError,
                OSError,
                ValueError,
                RuntimeError,
            ) as exc:
                print(f"Job '{job_id}' failed: {exc}", file=sys.stderr)
                if not args.keep_going:
                    return 1

    return 0 if success_count == len(jobs) else 1


def run_single_cli(args: argparse.Namespace) -> int:
    """Handle single-file visualization."""
    source_code = ""
    array_options = array_options_from_args(args)

    if args.files and len(args.files) == 1:
        source_path = Path(args.files[0])
        try:
            source_code = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error reading {source_path}: {exc}", file=sys.stderr)
            return 1
    elif args.input and args.input != "-":
        source_path = Path(args.input)
        try:
            source_code = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error reading {source_path}: {exc}", file=sys.stderr)
            return 1
    else:
        source_code = sys.stdin.read()

    java_home = trace_generator.ensure_jdk_installed()
    trace_generator.ensure_code_tracer_installed()

    bps = set(args.breakpoints or [])
    trace_text = trace_generator.generate_trace(
        java_home,
        source_code,
        breakpoints=bps or {-1},
        accumulate_breakpoints=args.all_steps,
        all_breakpoints=args.all_steps or not bool(bps),
    )

    with RenderingSession(max_browsers=1) as session:
        if args.all_steps:
            images = generate_step_images(
                trace_text,
                dpi=args.dpi,
                format=args.format,
                include_types=args.include_types,
                text_memory_labels=args.text_memory_labels,
                strip_type_prefixes=args.strip_type_prefixes,
                **array_options,
                session=session,
            )
            if not args.output:
                print("Error: --output is required when rendering --all-steps.", file=sys.stderr)
                return 1
            out_base = Path(args.output)
            out_base.parent.mkdir(parents=True, exist_ok=True)
            for idx, img in enumerate(images):
                step_file = out_base.with_name(f"{out_base.stem}.{idx}{out_base.suffix}")
                step_file.write_bytes(img)
            if images:
                out_base.write_bytes(images[-1])
        else:
            img_bytes = browser_driver.generate_image(
                trace_text,
                dpi=args.dpi,
                format=args.format,
                include_types=args.include_types,
                text_memory_labels=args.text_memory_labels,
                strip_type_prefixes=args.strip_type_prefixes,
                **array_options,
                session=session,
            )
            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(img_bytes)
            else:
                sys.stdout.buffer.write(img_bytes)

    return 0


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point for code-visualizer."""
    parser = argparse.ArgumentParser(
        prog="code-visualizer",
        description="Visualize Java program memory states and execution traces.",
    )

    # Positional files
    parser.add_argument("files", nargs="*", help="Java source files to visualize.")

    # Execution mode
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run in high-performance batch mode using pooled browsers and workers.",
    )

    # Inputs
    parser.add_argument(
        "-i",
        "--input",
        help="Input source file or NDJSON batch manifest ('-' for stdin).",
    )
    parser.add_argument(
        "--input-dir",
        help="Directory to recursively scan for Java source files.",
    )

    # Outputs
    parser.add_argument(
        "-o",
        "--output",
        help="Output image path (for single-file mode).",
    )
    parser.add_argument(
        "--out-dir",
        help="Base directory for batch outputs.",
    )
    parser.add_argument(
        "--output-pattern",
        help="Template pattern for image paths (e.g. '{dirname}/{basename}.{step}.png').",
    )
    parser.add_argument(
        "--trace-pattern",
        help="Template pattern for saving intermediate trace JSON files.",
    )

    # Trace & Rendering options
    parser.add_argument(
        "-a",
        "--all-steps",
        action="store_true",
        help="Trace and render visualizations for all execution steps.",
    )
    parser.add_argument(
        "-b",
        "--breakpoint",
        dest="breakpoints",
        action="append",
        type=int,
        help="Line number breakpoint to capture.",
    )
    parser.add_argument(
        "--format",
        default="PNG",
        help="Image format (PNG, SVG, etc.). Default: PNG.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=1,
        help="DPI scaling factor for rendered images. Default: 1.",
    )
    parser.add_argument(
        "--no-types",
        dest="include_types",
        action="store_false",
        default=True,
        help="Hide type tags in visualizations.",
    )
    parser.add_argument(
        "--text-memory-labels",
        action="store_true",
        help="Render memory addresses as text labels instead of arrows.",
    )
    parser.add_argument(
        "--strip-type-prefix",
        dest="strip_type_prefixes",
        action="append",
        help="Prefix to strip from type names.",
    )

    # Concurrency & Safety
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=1,
        help="Number of background tracer worker JVMs. Default: 1.",
    )
    parser.add_argument(
        "--browsers",
        type=int,
        default=2,
        help="Number of pooled browser instances. Default: 2.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue processing remaining jobs if a job fails in batch mode.",
    )

    add_array_arguments(parser)
    args = parser.parse_args(argv)

    if args.batch:
        exit_code = run_batch_cli(args)
    else:
        exit_code = run_single_cli(args)

    if exit_code != 0:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
