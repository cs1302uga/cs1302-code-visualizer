"""Compare fresh and reused Chrome rendering with identical decoded pixels.

Run with: python -m scripts.benchmark_rendering trace.json --requests 6
Input traces are already generated, so Java execution and trace caching cannot
influence the measurement. Timings include browser startup and teardown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from PIL import Image

from cs1302_code_visualizer import RenderingSession, browser_driver


def fingerprint(data: bytes) -> tuple[tuple[int, int], str]:
    """Compare dimensions and decoded RGBA pixels, ignoring PNG metadata."""
    with Image.open(BytesIO(data)) as image:
        return image.size, hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def main() -> None:
    """Measure the same workload with and without a browser-only session."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--requests", type=int, default=6)
    parser.add_argument("--dpi", type=int, default=1)
    args = parser.parse_args()
    if args.requests < 2 or args.dpi < 1:
        parser.error("requests must be at least 2 and dpi must be positive")
    trace = args.trace.read_text(encoding="utf-8")
    report = {}
    outputs = {}
    for mode in ("fresh", "reused"):
        with patch.object(
            browser_driver, "get_webdriver", wraps=browser_driver.get_webdriver
        ) as factory:
            started = perf_counter()
            with RenderingSession(max_browsers=1) as session:
                outputs[mode] = [
                    fingerprint(
                        browser_driver.generate_image(
                            trace,
                            dpi=args.dpi,
                            session=session if mode == "reused" else None,
                        )
                    )
                    for _ in range(args.requests)
                ]
            report[mode] = {
                "seconds": round(perf_counter() - started, 3),
                "chrome_launches": factory.call_count,
            }
    if outputs["fresh"] != outputs["reused"]:
        raise RuntimeError("Fresh and reused image dimensions or decoded pixels differ")
    report["identical_pixels"] = True
    report["requests"] = args.requests
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
