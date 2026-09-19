"""Runner script for executing and rendering all examples with batching."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from cs1302_code_visualizer.browser_driver import generate_step_images
from cs1302_code_visualizer.session import RenderingSession


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
) -> int:
    """Run trace generation and batch-rendered visualizations for all examples."""
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

    print(f"Running {len(configs)} examples in batch mode...")
    start_time = time.perf_counter()

    # Phase 1: Trace Generation
    traces: list[tuple[int, Path, str, str, Path, Path]] = []
    print("--- Generating traces ---")
    for i, example_dir, input_file, extra_args in configs:
        target_java = example_dir / input_file
        trace_file = example_dir / f"{input_file}.json"
        image_file = example_dir / f"{input_file}.png"

        has_bp = any(
            arg in ("-a", "--all-breakpoints", "-b", "--breakpoint")
            or arg.startswith(("-b=", "--breakpoint="))
            for arg in extra_args
        )
        tracer_args = list(extra_args)
        if not has_bp:
            tracer_args = ["-a", *tracer_args]

        cmd = ["uv", "run", "generate_trace", *tracer_args]
        with open(target_java, "r", encoding="utf-8") as f_in:
            proc = subprocess.run(
                cmd,
                stdin=f_in,
                capture_output=True,
                text=True,
                cwd=example_dir,
                check=False,
            )
        if proc.returncode != 0:
            print(
                f"Failed to generate trace for example{i} ({input_file}):",
                file=sys.stderr,
            )
            print(proc.stderr, file=sys.stderr)
            return 1

        trace_text = proc.stdout
        trace_file.write_text(trace_text, encoding="utf-8")
        traces.append((i, example_dir, input_file, trace_text, trace_file, image_file))
        print(f"  example{i:2d}: trace generated ({len(trace_text)} bytes)")

    # Phase 2: Batch Visualization Rendering
    print("--- Rendering visualizations with pooled RenderingSession ---")
    all_step_images: list[Path] = []
    with RenderingSession(max_browsers=max_browsers) as session:
        for i, example_dir, input_file, trace_text, _trace_file, image_file in traces:
            t0 = time.perf_counter()
            images = generate_step_images(trace_text, session=session)
            duration = time.perf_counter() - t0

            # Save generated step images
            if images:
                image_file.write_bytes(images[-1])
            step_files: list[Path] = []
            for idx, img_data in enumerate(images):
                sf = example_dir / f"{input_file}.{idx}.png"
                sf.write_bytes(img_data)
                step_files.append(sf)

            if not step_files and image_file.exists():
                step_files.append(image_file)

            all_step_images.extend(step_files)
            print(f"  example{i:2d}: {len(images):2d} images rendered in {duration:.2f}s")

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
        for _, _, _, _, trace_file, _ in traces:
            trace_file.unlink(missing_ok=True)

    if rm_image:
        print("Cleaning up generated PNG image files...")
        for _, example_dir, input_file, _, _, image_file in traces:
            image_file.unlink(missing_ok=True)
            for f in example_dir.glob(f"{Path(input_file).name}.*.png"):
                f.unlink(missing_ok=True)

    return 0


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
    args = parser.parse_args()

    examples_dir = Path(__file__).parent.resolve()
    sys.exit(
        run_batch_examples(
            examples_dir,
            rm_json=args.rm_json,
            rm_image=args.rm_image,
            open_image=args.open,
            max_browsers=args.browsers,
        )
    )


if __name__ == "__main__":
    main()
