"""Benchmark batched streaming performance of the new unified code-visualizer CLI.

Compares:
1. Sequential Single-Job CLI runs (fresh JVM + fresh browser per job)
2. Unified Batched Streaming CLI with various worker / browser pool configurations:
   - 1 tracer worker, 1 browser
   - 1 tracer worker, 2 browsers
   - 2 tracer workers, 2 browsers
   - 2 tracer workers, 4 browsers

Measures:
- Total execution time (seconds)
- Latency to first emitted image (streaming responsiveness)
- Average throughput (images/sec and jobs/sec)
- Speedup multiplier relative to sequential execution
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def monitor_first_image(
    out_dir: Path, stop_event: threading.Event, result: list[float], start_time: float
) -> None:
    """Poll output directory for the first non-temporary .png file."""
    while not stop_event.is_set():
        if out_dir.exists():
            pngs = [p for p in out_dir.rglob("*.png") if not p.name.startswith(".")]
            if pngs:
                result.append(time.perf_counter() - start_time)
                return
        time.sleep(0.02)


def run_benchmark_run(
    name: str,
    cmd: list[str],
    out_dir: Path,
) -> dict[str, float | int | str]:
    """Execute a benchmark command and track total time and latency to first image."""
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    result_ttfi: list[float] = []
    stop_event = threading.Event()
    start_time = time.perf_counter()

    monitor_thread = threading.Thread(
        target=monitor_first_image,
        args=(out_dir, stop_event, result_ttfi, start_time),
        daemon=True,
    )
    monitor_thread.start()

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    total_time = time.perf_counter() - start_time
    stop_event.set()
    monitor_thread.join(timeout=0.5)

    if proc.returncode != 0:
        print(f"Error in {name}:", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"Run {name} failed with exit code {proc.returncode}")

    emitted_pngs = list(out_dir.rglob("*.png"))
    num_images = len(emitted_pngs)
    ttfi = result_ttfi[0] if result_ttfi else total_time

    return {
        "name": name,
        "total_seconds": round(total_time, 2),
        "ttfi_seconds": round(ttfi, 2),
        "images_emitted": num_images,
        "throughput_img_per_sec": round(num_images / total_time, 2) if total_time > 0 else 0,
    }


def main() -> None:
    """Run CLI benchmarks and report speedups when a sequential baseline exists."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--num-examples",
        type=int,
        default=6,
        help="Number of examples from examples/ to benchmark (default: 6).",
    )
    parser.add_argument(
        "--all-steps",
        action="store_true",
        default=True,
        help="Benchmark full trace execution with all steps (default: True).",
    )
    parser.add_argument(
        "--skip-sequential",
        action="store_true",
        help="Skip sequential baseline if you only want to compare batch pool sizes.",
    )
    args = parser.parse_args()

    # Discover example source files
    repo_root = Path(__file__).resolve().parents[1]
    examples_dir = repo_root / "examples"
    sources: list[Path] = []
    for i in range(args.num_examples):
        src = examples_dir / f"example{i}" / "Driver.java"
        if src.exists():
            sources.append(src.relative_to(repo_root))

    if not sources:
        print("No example sources found.", file=sys.stderr)
        sys.exit(1)

    print(f"Selected {len(sources)} benchmark sources: {[s.parent.name for s in sources]}")
    step_flag = ["-a"] if args.all_steps else []

    benchmarks_dir = repo_root / ".benchmark_scratch"
    if benchmarks_dir.exists():
        shutil.rmtree(benchmarks_dir, ignore_errors=True)
    benchmarks_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, float | int | str]] = []
    baseline_time: float | None = None

    # 1. Sequential CLI run
    if not args.skip_sequential:
        seq_out = benchmarks_dir / "sequential"
        seq_out.mkdir(parents=True, exist_ok=True)
        print("Running Sequential Single-Process CLI...")
        start_seq = time.perf_counter()
        seq_ttfi_list: list[float] = []
        stop_seq = threading.Event()
        mon = threading.Thread(
            target=monitor_first_image,
            args=(seq_out, stop_seq, seq_ttfi_list, start_seq),
            daemon=True,
        )
        mon.start()

        for src in sources:
            dest = seq_out / src.parent.name / "Driver.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["uv", "run", "code-visualizer", str(src), *step_flag, "-o", str(dest)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                print(f"Error on sequential {src}: {res.stderr}", file=sys.stderr)

        seq_total = time.perf_counter() - start_seq
        baseline_time = seq_total
        stop_seq.set()
        mon.join(timeout=0.5)
        seq_pngs = len(list(seq_out.rglob("*.png")))
        results.append({
            "name": "Sequential (Fresh JVM + Browser per job)",
            "total_seconds": round(seq_total, 2),
            "ttfi_seconds": round(seq_ttfi_list[0] if seq_ttfi_list else seq_total, 2),
            "images_emitted": seq_pngs,
            "throughput_img_per_sec": round(seq_pngs / seq_total, 2) if seq_total > 0 else 0,
        })
        print(
            f"  Done in {seq_total:.2f}s (TTFI: {results[-1]['ttfi_seconds']}s, {seq_pngs} images)"
        )

    # 2. Batch configurations
    configs = [
        ("Batch (1 worker, 1 browser)", 1, 1),
        ("Batch (1 worker, 2 browsers)", 1, 2),
        ("Batch (2 workers, 2 browsers)", 2, 2),
        ("Batch (2 workers, 4 browsers)", 2, 4),
    ]

    for label, workers, browsers in configs:
        out = benchmarks_dir / f"batch_w{workers}_b{browsers}"
        print(f"Running {label}...")
        cmd = [
            "uv",
            "run",
            "code-visualizer",
            "--batch",
            "--force",
            *step_flag,
            "--workers",
            str(workers),
            "--browsers",
            str(browsers),
            "--out-dir",
            str(out),
            *[str(s) for s in sources],
        ]
        res = run_benchmark_run(label, cmd, out)
        results.append(res)
        print(
            f"  Done in {res['total_seconds']}s (TTFI: {res['ttfi_seconds']}s, {res['images_emitted']} images)"
        )

    # Calculate speedups
    for r in results:
        t = float(r["total_seconds"])
        r["speedup"] = f"{baseline_time / t:.2f}x" if baseline_time is not None and t > 0 else "N/A"

    # Print summary table
    print("\n" + "=" * 90)
    print("BENCHMARK SUMMARY RESULTS")
    print("=" * 90)
    header = f"{'Configuration':<42} | {'Total (s)':<10} | {'TTFI (s)':<10} | {'Images':<8} | {'Img/s':<8} | {'Speedup':<8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['name']:<42} | {r['total_seconds']:<10} | {r['ttfi_seconds']:<10} | "
            f"{r['images_emitted']:<8} | {r['throughput_img_per_sec']:<8} | {r.get('speedup', '1.00x'):<8}"
        )
    print("=" * 90)

    # Save JSON report
    report_file = repo_root / "benchmark_cli_batch_results.json"
    report_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nReport written to {report_file}")

    # Cleanup scratch
    if benchmarks_dir.exists():
        shutil.rmtree(benchmarks_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
