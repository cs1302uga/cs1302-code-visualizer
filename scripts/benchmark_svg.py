"""Measure fixed-trace SVG exports without retracing Java programs."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from xml.etree import ElementTree as ET

from cs1302_code_visualizer import RenderingSession, browser_driver
from cs1302_code_visualizer.browser_driver import generate_image, generate_step_images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sequence", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    measurements = []
    capture = browser_driver._capture_viz

    def measured_capture(driver, *args, **kwargs):
        result = capture(driver, *args, **kwargs)
        measurements.append(driver.execute_script("return window.codevisSvgMetrics || null"))
        return result
    with RenderingSession(max_browsers=1) as session, patch.object(
        browser_driver, "_capture_viz", measured_capture
    ):
        for index, path in enumerate(args.traces):
            trace = path.read_text()
            times = []
            measurements.clear()
            for _ in range(args.repeats):
                started = perf_counter()
                frames = (generate_step_images(trace, format="SVG", session=session)
                          if args.sequence else [generate_image(trace, format="SVG", session=session)])
                times.append(perf_counter() - started)
            for step, frame in enumerate(frames):
                (args.output / f"trace-{index}-step-{step}.svg").write_bytes(frame)
            records.append({
                "trace": str(path), "sha256": hashlib.sha256(trace.encode()).hexdigest(),
                "export_metrics": measurements.copy(),
                "seconds": times, "frames": len(frames),
                "raw_bytes": sum(map(len, frames)),
                "gzip_bytes": sum(len(gzip.compress(frame, mtime=0)) for frame in frames),
                "elements": sum(sum(1 for _ in ET.fromstring(frame).iter()) for frame in frames),
            })
    (args.output / "metrics.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
