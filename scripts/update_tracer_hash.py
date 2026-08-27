#!/usr/bin/env python3
"""Utility script to compute and update tracer-sha256 in pyproject.toml."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from cs1302_code_visualizer.trace_generator import CACHE_DIR, ensure_jdk_installed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch code-tracer JAR, compute SHA256 checksum, and update pyproject.toml."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--version",
        "-v",
        help="Release tag to update to (e.g. 'v2.0.1' or '2.0.1'). Updates tracer-url accordingly.",
    )
    group.add_argument(
        "--url",
        "-u",
        help="Direct URL to code-tracer.jar. Updates tracer-url in pyproject.toml.",
    )
    parser.add_argument(
        "--pyproject",
        "-p",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml (defaults to ./pyproject.toml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and display hash without modifying pyproject.toml or cache.",
    )
    return parser.parse_args()


def get_current_tracer_url(pyproject_path: Path) -> str:
    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'tracer-url\s*=\s*"([^"]+)"', content)
    if not match:
        raise ValueError(f"Could not find 'tracer-url' in {pyproject_path}")
    return match.group(1)


def update_pyproject_toml(
    pyproject_path: Path, new_url: str, new_sha256: str
) -> None:
    content = pyproject_path.read_text(encoding="utf-8")

    # Update tracer-url
    content = re.sub(
        r'tracer-url\s*=\s*"[^"]+"',
        f'tracer-url  = "{new_url}"',
        content,
    )

    # Update tracer-sha256
    content = re.sub(
        r'tracer-sha256\s*=\s*"[^"]+"',
        f'tracer-sha256 = "{new_sha256}"',
        content,
    )

    pyproject_path.write_text(content, encoding="utf-8")


def download_and_hash(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "cs1302-code-visualizer/updater"},
    )
    hasher = hashlib.sha256()
    chunks: list[bytes] = []

    print(f"Downloading: {url} ...")
    with urllib.request.urlopen(req) as resp:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            hasher.update(chunk)

    data = b"".join(chunks)
    sha256 = hasher.hexdigest()
    return data, sha256


def get_binary_version(jar_bytes: bytes) -> str:
    try:
        java_home = ensure_jdk_installed()
        with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as tmp:
            tmp.write(jar_bytes)
            tmp_path = Path(tmp.name)

        proc = subprocess.run(
            [str(java_home / "bin" / "java"), "-jar", str(tmp_path), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        tmp_path.unlink(missing_ok=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    return "(unknown)"


def main() -> int:
    args = parse_args()
    pyproject_path = args.pyproject.resolve()

    if not pyproject_path.is_file():
        print(f"Error: {pyproject_path} not found.", file=sys.stderr)
        return 1

    current_url = get_current_tracer_url(pyproject_path)

    if args.url:
        target_url = args.url
    elif args.version:
        ver = args.version if args.version.startswith("v") else f"v{args.version}"
        target_url = (
            f"https://github.com/cs1302uga/cs1302-tracer/releases/download/{ver}/code-tracer.jar"
        )
    else:
        target_url = current_url

    try:
        jar_data, sha256_sum = download_and_hash(target_url)
    except Exception as exc:
        print(f"Error downloading {target_url}: {exc}", file=sys.stderr)
        return 1

    binary_ver = get_binary_version(jar_data)

    print("\n--- Download & Verification Summary ---")
    print(f"Target URL:       {target_url}")
    print(f"File Size:        {len(jar_data):,} bytes")
    print(f"SHA256 Checksum:  {sha256_sum}")
    print(f"Binary --version: {binary_ver}")

    if args.dry_run:
        print("\n[Dry Run] No files modified.")
        return 0

    # Update pyproject.toml
    update_pyproject_toml(pyproject_path, target_url, sha256_sum)
    print(f"\n[OK] Updated {pyproject_path}")

    # Refresh local cache
    target_jar = CACHE_DIR / "code-tracer.jar"
    dl_info = CACHE_DIR / "code_tracer_dl_headers.json"
    target_jar.write_bytes(jar_data)
    if dl_info.exists():
        dl_info.unlink(missing_ok=True)
    print(f"[OK] Refreshed cache at {target_jar}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
