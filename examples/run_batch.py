"""Runner script for executing and rendering all examples with batching."""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import shlex
import subprocess
import sys
import time
from collections import deque
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cs1302_code_visualizer.browser_driver import generate_step_images
from cs1302_code_visualizer.errors import CodeVisError, CodeVisualizerError
from cs1302_code_visualizer.session import RenderingSession
from cs1302_code_visualizer.trace_generator import ensure_jdk_installed


def open_files(files: Sequence[Path]) -> None:
    """Open files using platform-specific viewer."""
    if not files:
        return
    file_strs = [str(f) for f in files]
    ostype = sys.platform
    try:
        if ostype == "darwin":
            subprocess.run(
                ["qlmanage", "-p", *file_strs],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        elif ostype.startswith("linux"):
            for f in file_strs:
                subprocess.run(["xdg-open", f], check=False)
        elif ostype in ("win32", "cygwin", "msys"):
            for f in file_strs:
                os.startfile(f)  # type: ignore[attr-defined]
        else:
            print(
                f"unable to open files automatically: platform {ostype} not supported",
                file=sys.stderr,
            )
    except OSError as exc:
        print(f"Error opening files: {exc}", file=sys.stderr)


def parse_example_test_sh(test_sh: Path) -> tuple[str, list[str]]:
    """Parse ../test.sh arguments from an example's test.sh."""
    for line in test_sh.read_text().splitlines():
        line = line.strip()
        if line.startswith("../test.sh"):
            tokens = shlex.split(line)
            args = [
                t
                for t in tokens
                if t not in ("../test.sh", "$@", '"$@"') and not t.startswith("$") and t != ""
            ]
            if args:
                return args[0], args[1:]
    raise ValueError(f"Could not find ../test.sh command line in {test_sh}")


def run_batch_examples(
    examples_dir: Path,
    *,
    rm_json: bool,
    rm_image: bool,
    open_image: bool,
    max_browsers: int = 2,
    tracer_workers: int = 1,
) -> int:
    """Trace and render examples concurrently using one persistent session.

    Args:
        examples_dir: Directory containing the numbered example directories.
        rm_json: Whether to remove successful trace output files.
        rm_image: Whether to remove successful image output files.
        open_image: Whether to open generated step images.
        max_browsers: Maximum number of concurrently leased browsers.
        tracer_workers: Number of persistent tracer workers.

    Returns:
        Zero on success, or one if tracing or rendering an example fails.
    """
    configs: list[tuple[int, Path, str, list[str]]] = []
    for i in range(34):
        example_dir = examples_dir / f"example{i}"
        test_sh = example_dir / "test.sh"
        if not test_sh.exists():
            continue
        try:
            input_file, extra_args = parse_example_test_sh(test_sh)
            configs.append((i, example_dir, input_file, extra_args))
        except (ValueError, OSError) as exc:
            print(f"Warning: skipping example{i}: {exc}", file=sys.stderr)

    print(
        f"Running {len(configs)} examples in batch mode "
        f"(browsers: {max_browsers}, tracer workers: {tracer_workers})..."
    )
    start_time = time.perf_counter()

    traces: list[tuple[Path, Path, list[Path]]] = []
    all_step_images: list[Path] = []

    def process_example(
        config: tuple[int, Path, str, list[str]],
    ) -> tuple[Path, Path, list[Path]]:
        """Trace, render, and save one example without changing working directory.

        Args:
            config: Example index, directory, source filename, and trace arguments.

        Returns:
            Trace path, final image path, and ordered step image paths.
        """
        i, example_dir, input_file, extra_args = config
        target_java = example_dir / input_file
        trace_file = example_dir / f"{input_file}.json"
        image_file = example_dir / f"{input_file}.png"
        options = _trace_options(extra_args, example_dir)
        # File input lets the tracer discover companion compilation units. The
        # single-source batch protocol cannot resolve these from a source string.
        if len(list(example_dir.rglob("*.java"))) > 1:
            options["extra_tracer_args"] += ["--input", str(target_java.resolve())]
        trace_text = session.generate_trace(
            java_home,
            target_java.read_text(encoding="utf-8"),
            **options,
        )
        trace_file.write_text(trace_text, encoding="utf-8")
        print(f"  example{i:2d}: trace generated ({len(trace_text)} bytes)")
        t0 = time.perf_counter()
        images = generate_step_images(trace_text, session=session)
        if images:
            image_file.write_bytes(images[-1])
        step_files = []
        for idx, img_data in enumerate(images):
            sf = example_dir / f"{input_file}.{idx}.png"
            sf.write_bytes(img_data)
            step_files.append(sf)
        if not step_files and image_file.exists():
            step_files.append(image_file)
        print(
            f"  example{i:2d}: {len(images):2d} images rendered "
            f"in {time.perf_counter() - t0:.2f}s"
        )
        return trace_file, image_file, step_files

    print("--- Tracing and rendering with pooled RenderingSession ---")
    with RenderingSession(
        max_browsers=max_browsers,
        tracer_workers=tracer_workers,
        use_batch_tracer=True,
    ) as session:
        java_home = ensure_jdk_installed() if configs else None
        workers = max(max_browsers, tracer_workers)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        try:
            remaining = iter(configs)
            pending = deque()
            for config in remaining:
                pending.append(executor.submit(process_example, config))
                if len(pending) == workers:
                    break
            while pending:
                result = pending.popleft().result()
                traces.append(result)
                all_step_images.extend(result[2])
                next_config = next(remaining, None)
                if next_config is not None:
                    pending.append(executor.submit(process_example, next_config))
        except (CodeVisError, CodeVisualizerError, OSError, ValueError, RuntimeError) as exc:
            print(f"Failed to process examples: {exc}", file=sys.stderr)
            return 1
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    elapsed = time.perf_counter() - start_time
    print(
        f"Successfully processed {len(configs)} examples in {elapsed:.2f}s "
        f"({len(all_step_images)} total images)."
    )

    # Phase 3: Post-processing (Open images / Cleanup)
    if open_image and all_step_images:
        print(f"Opening {len(all_step_images)} images...")
        open_files(all_step_images)

    if rm_json:
        print("Cleaning up generated JSON trace files...")
        for trace_file, _, _ in traces:
            trace_file.unlink(missing_ok=True)

    if rm_image:
        print("Cleaning up generated PNG image files...")
        for _, image_file, _ in traces:
            image_file.unlink(missing_ok=True)
            for f in image_file.parent.glob(f"{image_file.stem}.*.png"):
                f.unlink(missing_ok=True)

    return 0


def _trace_options(extra_args: list[str], example_dir: Path) -> dict[str, Any]:
    """Translate supported flags, retaining unsupported flags for legacy tracing.

    Args:
        extra_args: Arguments extracted from the example's test script.
        example_dir: Base directory for relative stdin file paths.

    Returns:
        Keyword arguments for ``RenderingSession.generate_trace``.
    """
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("-a", "--all-breakpoints", "--auto-detect", action="store_true")
    parser.add_argument("-b", "--breakpoint", action="append", default=[])
    parser.add_argument("--accumulate-breakpoints", action="store_true")
    parser.add_argument("--include-enum-static-fields", action="store_true")
    parser.add_argument("--inline-strings", action="store_true")
    parser.add_argument("--no-eval-enum-hash", action="store_false", dest="eval_enum_hash")
    parser.add_argument("--type-style", default="simple")
    parser.add_argument("--trace-timeout", type=float)
    parser.add_argument("--stdin")
    parser.add_argument("--stdin-file")
    args, unsupported = parser.parse_known_args(extra_args)
    breakpoints = {
        int(value) for group in args.breakpoint for value in group.split(",") if value.strip()
    }
    return {
        "breakpoints": breakpoints or {-1},
        "all_breakpoints": args.all_breakpoints or not args.breakpoint,
        "accumulate_breakpoints": args.accumulate_breakpoints,
        "include_enum_static_fields": args.include_enum_static_fields,
        "inline_strings": args.inline_strings,
        "eval_enum_hash": args.eval_enum_hash,
        "type_style": args.type_style,
        "timeout_secs": args.trace_timeout,
        "stdin": args.stdin,
        "stdin_file": (
            (example_dir / args.stdin_file).resolve() if args.stdin_file is not None else None
        ),
        "extra_tracer_args": unsupported,
    }


def main() -> None:
    """Parse CLI arguments and run batch runner."""
    parser = argparse.ArgumentParser(description="Batch runner for example visualizer tests.")
    _ = parser.add_argument(
        "-J",
        "--rm-json",
        action="store_true",
        default=False,
        help="Automatically delete generated JSON trace files",
    )
    _ = parser.add_argument(
        "-I",
        "--rm-image",
        action="store_true",
        default=False,
        help="Automatically delete generated PNG image files",
    )
    _ = parser.add_argument(
        "-o",
        "--open",
        action="store_true",
        default=False,
        help="Automatically open generated images",
    )
    _ = parser.add_argument(
        "--browsers",
        type=int,
        default=2,
        help="Number of pooled browser instances for rendering (default: 2)",
    )
    _ = parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=1,
        help="Number of persistent worker JVMs in batch mode (default: 1)",
    )
    args = parser.parse_args()

    examples_dir = Path(__file__).parent.resolve()
    sys.exit(
        run_batch_examples(
            examples_dir,
            rm_json=args.rm_json,
            rm_image=args.rm_image,
            open_image=args.open,
            max_browsers=args.browsers,
            tracer_workers=args.workers,
        )
    )


if __name__ == "__main__":
    main()
