#!/usr/bin/env python3
"""Generate all example traces and gallery images with JDK 25, preserving source artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cs1302_code_visualizer import RenderingSession
from cs1302_code_visualizer.browser_driver import generate_step_images
from cs1302_code_visualizer.trace_generator import (
    ensure_code_tracer_installed,
    ensure_jdk_installed,
    get_sanitized_java_env,
    jdk_exists,
    read_tracer_url_and_sum_from_toml,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "build" / "gallery"


def parse_readme(readme_path: Path) -> tuple[str, list[str]]:
    content = readme_path.read_text(encoding="utf-8")
    title = next(line.lstrip("#").strip() for line in content.splitlines() if line.startswith("#"))
    concepts = []
    in_concepts = False
    for line in content.splitlines():
        if re.search(r"##\s*Concepts Illustrated", line, re.IGNORECASE):
            in_concepts = True
        elif in_concepts and line.startswith("##"):
            break
        elif in_concepts and line.strip().startswith("-"):
            concepts.append(line.strip())
    return title, concepts


def example_command(example_dir: Path) -> tuple[Path, list[str]]:
    """Read the source and tracer arguments from an example's existing test command."""
    lines = (example_dir / "test.sh").read_text().splitlines()
    commands = [shlex.split(line) for line in lines if line.strip().startswith('../test.sh "$@" ')]
    if len(commands) != 1 or commands[0][1] != "$@":
        raise ValueError(f"Expected one example command in {example_dir / 'test.sh'}")
    source = example_dir / commands[0][2]
    args = commands[0][3:]
    breakpoint_flags = ("-a", "--all-breakpoints", "-b", "--breakpoint", "--breakpoints")
    if not any(arg.split("=", 1)[0] in breakpoint_flags for arg in args):
        args.insert(0, "-a")
    return source, args


def trace_sequences(data: dict) -> list[dict]:
    """Expand breakpoint hits without discarding accumulated snapshots."""
    if isinstance(data.get("trace"), list) or isinstance(data.get("steps"), list):
        return [data]
    if data.get("format") == "modern":
        raise ValueError("Expected chronological modern steps in gallery trace")
    sequences = []
    for value in data.values():
        for item in value if isinstance(value, list) else [value]:
            if not isinstance(item, dict):
                raise TypeError("Invalid breakpoint trace")
            sequences.extend(trace_sequences(item))
    if not sequences:
        raise ValueError("No execution steps in gallery trace")
    return sequences


def build_example(index: int, artifact_dir: Path, java_home: Path, dpi: int) -> dict:
    example_dir = REPO_ROOT / "examples" / f"example{index}"
    source, args = example_command(example_dir)
    title, concepts = parse_readme(example_dir / "README.md")
    env = get_sanitized_java_env()
    env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
    command = [
        sys.executable,
        "-m",
        "cs1302_code_visualizer.trace_generator",
        "--jdk",
        str(java_home),
        *args,
    ]
    print(f"Tracing example{index}...", flush=True)
    process = subprocess.run(
        command,
        input=source.read_text(encoding="utf-8"),
        cwd=example_dir,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(process.stdout)
    (artifact_dir / "traces" / f"example{index}.json").write_text(process.stdout, encoding="utf-8")
    steps = []
    with RenderingSession(max_browsers=1) as session:
        for sequence in trace_sequences(data):
            raw_steps = sequence.get("trace", sequence.get("steps", []))
            if not raw_steps:
                raise ValueError(f"example{index}: empty execution sequence")
            images = generate_step_images(json.dumps(sequence), dpi=dpi, session=session)
            if len(images) != len(raw_steps):
                raise ValueError(f"example{index}: image and trace step counts differ")
            for snapshot, image in zip(raw_steps, images, strict=True):
                step = len(steps)
                filename = f"example{index}_{step}.png"
                (artifact_dir / "gallery_images" / filename).write_bytes(image)
                steps.append({
                    "step": step,
                    "filename": filename,
                    "line": snapshot["line"],
                    "func": snapshot.get("func_name", snapshot.get("method", "")),
                })
    sources = [source, *sorted(p for p in example_dir.rglob("*.java") if p != source)]
    print(f"example{index}: {len(steps)} steps rendered", flush=True)
    return {
        "index": index,
        "title": title,
        "java_file": str(source.relative_to(example_dir)),
        "code": source.read_text(encoding="utf-8"),
        "concepts": concepts,
        "sources": [
            {"path": str(p.relative_to(example_dir)), "code": p.read_text(encoding="utf-8")}
            for p in sources
        ],
        "cmd": f"generate_trace {shlex.join(args)} < {source.relative_to(example_dir)}",
        "step_count": len(steps),
        "steps": steps,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--jdk", type=Path, help="JDK 25 home; otherwise use Java on PATH")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--dpi", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1 or args.dpi < 1:
        parser.error("--jobs and --dpi must be positive")
    java_home = (args.jdk or ensure_jdk_installed()).resolve()
    if not jdk_exists(java_home):
        parser.error(f"Invalid JDK home: {java_home}")
    release = (java_home / "release").read_text()
    match = re.search(r'JAVA_VERSION="([^"]+)"', release)
    if not match or match[1].split(".")[0] != "25":
        parser.error("Gallery generation requires JDK 25; supply --jdk /path/to/jdk25")
    ensure_code_tracer_installed()
    artifact_dir = args.artifact_dir.resolve()
    for name in ("gallery_images", "traces"):
        (artifact_dir / name).mkdir(parents=True, exist_ok=True)
    # Do not leave an old manifest looking like a successful build after a failure.
    metadata_path = artifact_dir / "example_metadata.json"
    metadata_path.unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        examples = list(
            workers.map(
                lambda index: build_example(index, artifact_dir, java_home, args.dpi), range(34)
            )
        )
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    pin = read_tracer_url_and_sum_from_toml()
    metadata = {
        "visualizer_version": project["project"]["version"],
        "java_version": match[1],
        "tracer_url": pin[0] if pin else None,
        "tracer_sha256": pin[1] if pin else None,
        "dpi": args.dpi,
        "examples": examples,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved {len(examples)} examples to {metadata_path}", flush=True)


if __name__ == "__main__":
    main()
