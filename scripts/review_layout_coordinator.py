"""Capture source-bound native layout evidence without building or running Java.

Run ``uv run python -m scripts.review_layout_coordinator --out PATH
[--compare BASELINE_DIR]`` after the parent has built and frozen the frontend.
PNG pixels, SVG bytes, and separately reopened SVG rasters are distinct evidence.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from PIL import Image, ImageChops
from selenium.webdriver.common.by import By

from cs1302_code_visualizer import RenderingSession, browser_driver

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "tests/fixtures/layout-coordinator-frames.json"
EXAMPLES = ROOT / "scripts/benchmark_reference_routing/fixtures"
CASES = ("aliases", "cycle", "arrays", "self-loop")
NS = {"s": "http://www.w3.org/2000/svg"}


def sha(data: bytes) -> str:
    """Return the full SHA-256 of actual bytes."""
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    """Read repository identity without changing it."""
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).rstrip("\n")


def provenance() -> dict[str, Any]:
    """Bind sources and built assets separately to the actual checkout."""
    paths = {
        p for p in (ROOT / "cs1302_code_visualizer").rglob("*.py") if "node_modules" not in p.parts
    }
    frontend = ROOT / "cs1302_code_visualizer/frontend"
    for directory in ("js", "css", "build"):
        paths.update(p for p in (frontend / directory).rglob("*") if p.is_file())
    paths.update(p for p in frontend.iterdir() if p.is_file())
    paths.update((FRAMES, Path(__file__).resolve(), ROOT / "pyproject.toml", ROOT / "uv.lock"))
    paths.update(EXAMPLES / f"{name}.json" for name in CASES)
    tree = {
        line.split("\t", 1)[1]: line.split()[2]
        for line in git("ls-tree", "-r", "--full-tree", "HEAD").splitlines()
    }
    object_format = git("rev-parse", "--show-object-format")
    files = {}
    for path in sorted(paths):
        data = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        blob = hashlib.new(object_format, b"blob " + str(len(data)).encode() + b"\0" + data)
        files[relative] = {
            "sha256": sha(data),
            "bytes": len(data),
            "matches_head_blob": blob.hexdigest() == tree[relative] if relative in tree else None,
        }
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    return {
        "head": git("rev-parse", "HEAD"),
        "status_porcelain": status,
        "dirty": bool(status),
        "files": files,
        "bundle_source_binding": "Hashes identify actual files; a matching build is not inferred.",
        "head_binding": "Only matches_head_blob=true binds a file to HEAD; null means absent from HEAD.",
    }


def pixels(data: bytes) -> dict[str, Any]:
    """Measure decoded pixels and all four content margins against the corner color."""
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGB")
        background = Image.new("RGB", image.size, image.getpixel((0, 0)))
        box = ImageChops.difference(image, background).getbbox()
        margins = [box[0], box[1], image.width - box[2], image.height - box[3]] if box else []
        return {
            "dimensions": list(image.size),
            "rgba_sha256": sha(source.convert("RGBA").tobytes()),
            "padding_left_top_right_bottom": margins,
            "padding_at_least_4px": bool(margins) and min(margins) >= 4,
        }


def vector(data: bytes) -> dict[str, Any]:
    """Record SVG geometry, routes, and rendered-state descriptions."""
    root = ET.fromstring(data)
    metadata = root.find("s:metadata", NS)
    return {
        "dimensions": [int(root.attrib[key]) for key in ("width", "height")],
        "viewBox": root.attrib["viewBox"],
        "paths": [node.attrib for node in root.findall(".//s:path", NS)],
        "description": json.loads(metadata.text or "{}") if metadata is not None else None,
    }


def baseline_evidence(directory: Path) -> dict[str, Any]:
    """Preserve supplied historical records without inventing capture-time provenance."""
    records = {}
    for path in (
        directory / "manifest.json",
        directory / "hashes.json",
        directory.parent / "baseline-source.json",
        directory.parent / "baseline-assets.json",
    ):
        if path.is_file():
            records[str(path)] = {
                "sha256": sha(path.read_bytes()),
                "supplied_record": json.loads(path.read_text()),
            }
    return {
        "directory": str(directory),
        "records": records,
        "qualification": "Historical records are supplied evidence, not a fresh capture or clean-HEAD claim.",
    }


def compare(data: bytes, path: Path, image_format: str) -> dict[str, Any]:
    """Compare actual baseline files; SVG byte equality is not raster parity."""
    if not path.is_file():
        return {"available": False, "path": str(path)}
    baseline = path.read_bytes()
    current = pixels(data) if image_format == "PNG" else vector(data)
    previous = pixels(baseline) if image_format == "PNG" else vector(baseline)
    supplied = path.with_name("hashes.json")
    expected = json.loads(supplied.read_text()).get(path.name) if supplied.is_file() else None
    result = {
        "available": True,
        "baseline_sha256": sha(baseline),
        "matches_supplied_sha256": sha(baseline) == expected if expected is not None else None,
        "bytes_equal": data == baseline,
        "dimensions_equal": current["dimensions"] == previous["dimensions"],
    }
    if image_format == "PNG":
        result["decoded_pixels_equal"] = current["rgba_sha256"] == previous["rgba_sha256"]
    else:
        result["routes_equal"] = current["paths"] == previous["paths"]
        result["description_equal"] = current["description"] == previous["description"]
    return result


def reopen_svgs(
    session: RenderingSession, out: Path, pairs: dict[str, Any], baseline: Path | None
) -> dict[str, Any]:
    """Open standalone SVG documents using the repository WebDriver, then rasterize."""
    configuration = (browser_driver.is_headless_enabled(), browser_driver.DEBUG_MODE)
    with session.browser(1, browser_driver.get_webdriver, configuration=configuration) as driver:
        environment = {
            "capabilities": driver.capabilities,
            "frontend": driver.execute_script(
                "return {userAgent:navigator.userAgent,viewport:[innerWidth,innerHeight],"
                "devicePixelRatio,fonts:document.fonts.status,"
                "prefersDark:matchMedia('(prefers-color-scheme:dark)').matches};"
            ),
        }
        driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})

        def raster(path: Path, width: int, height: int) -> bytes:
            driver.set_window_size(max(800, width + 32), max(600, height + 160))
            driver.get(path.as_uri())
            driver.execute_async_script(
                "const done=arguments[arguments.length-1];"
                "document.fonts.ready.then(()=>requestAnimationFrame(()=>requestAnimationFrame(done)));"
            )
            return driver.find_element(By.CSS_SELECTOR, "svg").screenshot_as_png

        for name, record in pairs.items():
            width, height = record["SVG"]["dimensions"]
            data = raster(out / f"{name}.svg", width, height)
            (out / f"{name}.reopened.png").write_bytes(data)
            measured = pixels(data)
            record["SVG"]["standalone_reopened"] = {
                **measured,
                "sha256": sha(data),
                "dimensions_equal_native": measured["dimensions"] == record["PNG"]["dimensions"],
                "pixels_equal_native_png": measured["rgba_sha256"] == record["PNG"]["rgba_sha256"],
                "qualification": "Separate standalone-SVG raster; no PNG/SVG parity is presumed.",
            }
            if baseline is not None and (baseline / f"{name}.svg").is_file():
                path = baseline / f"{name}.svg"
                dimensions = vector(path.read_bytes())["dimensions"]
                previous = pixels(raster(path, *dimensions))
                record["SVG"]["standalone_reopened"]["baseline_comparison"] = {
                    "baseline_svg_sha256": sha(path.read_bytes()),
                    "baseline_raster": previous,
                    "dimensions_equal": measured["dimensions"] == previous["dimensions"],
                    "decoded_pixels_equal": measured["rgba_sha256"] == previous["rgba_sha256"],
                }
        return environment


def gallery(out: Path, baseline: Path | None, report: dict[str, Any]) -> None:
    """Write an offline, self-contained gallery with native file links and state records."""
    cards = []
    for name, record in report["pairs"].items():
        images = []
        for label, directory in (("Current", out), ("Baseline", baseline)):
            if directory is None:
                continue
            for suffix, mime in (("png", "image/png"), ("svg", "image/svg+xml")):
                path = directory / f"{name}.{suffix}"
                if path.is_file():
                    encoded = base64.b64encode(path.read_bytes()).decode()
                    link = (
                        f'<a href="{name}.{suffix}">native {suffix.upper()}</a>'
                        if directory == out
                        else ""
                    )
                    images.append(
                        f"<figure><figcaption>{label} {suffix.upper()} {link}</figcaption>"
                        f'<img alt="{html.escape(name)} {label} {suffix.upper()}" '
                        f'src="data:{mime};base64,{encoded}"></figure>'
                    )
        description = html.escape(json.dumps(record["SVG"]["description"], indent=2))
        comparison = html.escape(
            json.dumps({key: value.get("comparison") for key, value in record.items()}, indent=2)
        )
        cards.append(
            f'<section><h2>{name}</h2><div class="pair">{"".join(images)}</div>'
            f'<p><a href="{name}.reopened.png">Separate reopened SVG raster</a></p>'
            f"<details><summary>State semantics and comparison</summary><pre>{description}\n{comparison}</pre></details></section>"
        )
    manifest = html.escape(json.dumps(report, indent=2))
    (out / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>Layout coordinator native review</title>'
        "<style>body{font:16px system-ui;margin:2rem;line-height:1.5;background:#eef1f5;color:#18202a}"
        ".pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}"
        "section{background:white;padding:1rem;margin:1rem 0}figure{margin:0;overflow:auto}"
        "img{display:block;max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        "a{color:#1349b0}figcaption{font-weight:600}</style><h1>Layout coordinator native review</h1>"
        "<p>Frame states: 1 → 2 → 3 → 1; heap semantics are unchanged. Heap positions may change "
        "as frames are inserted. Native PNG pixels, native SVG routes/bytes, and separately reopened "
        "SVG rasters are reported independently. Images are embedded for offline review; native "
        'downloads accompany this page.</p><p><a href="manifest.json">Full manifest</a></p>'
        + "".join(cards)
        + f"<details><summary>Provenance, environment, and checks</summary><pre>{manifest}</pre></details></html>",
        encoding="utf-8",
    )


def main() -> None:
    """Capture the exact baseline workload with one exclusively leased browser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    baseline = args.compare.resolve() if args.compare is not None else None
    if baseline is not None and out == baseline:
        parser.error("--out must differ from --compare")
    if out.exists() and any(out.iterdir()):
        parser.error("--out must be empty so historical evidence cannot be mixed with this run")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["CS1302_HEADLESS"] = "true"
    os.environ.pop("CS1302_DISABLE_HEADLESS", None)
    report: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "command": sys.argv,
        "before": provenance(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "packages": {
                name: version(name) for name in ("cs1302-code-visualizer", "selenium", "pillow")
            },
            "headless": browser_driver.is_headless_enabled(),
        },
        "options": {
            "dpi": 1,
            "include_types": True,
            "text_memory_labels": False,
            "string_style": "default",
            "array_orientation": "horizontal",
            "alternate_array_orientations": False,
            "array_orientations": {},
            "strip_type_prefixes": [],
            "visualizer": "pytutor",
            "max_browsers": 1,
            "standalone_theme": None,
            "frames_themes": ["light", "dark"],
            "step_breakpoint": None,
            "standalone_breakpoint": -1,
        },
        "baseline": baseline_evidence(baseline) if baseline is not None else None,
        "pairs": {},
    }
    trace = FRAMES.read_text(encoding="utf-8")
    (out / "frame-transitions.trace.json").write_bytes(FRAMES.read_bytes())
    try:
        with RenderingSession(max_browsers=1) as session:
            for image_format in ("PNG", "SVG"):
                outputs = {}
                for theme in ("light", "dark"):
                    images = browser_driver.generate_step_images(
                        trace, format=image_format, theme=theme, session=session
                    )
                    if len(images) != 4:
                        raise ValueError(f"Expected four frame states, received {len(images)}")
                    outputs.update({f"frames-{theme}-{i}": data for i, data in enumerate(images)})
                for name in CASES:
                    outputs[name] = browser_driver.generate_image(
                        (EXAMPLES / f"{name}.json").read_text(),
                        format=image_format,
                        session=session,
                    )
                for name, data in outputs.items():
                    path = out / f"{name}.{image_format.lower()}"
                    path.write_bytes(data)
                    record = pixels(data) if image_format == "PNG" else vector(data)
                    report["pairs"].setdefault(name, {})[image_format] = {
                        **record,
                        "sha256": sha(data),
                        "bytes": len(data),
                        "comparison": compare(data, baseline / path.name, image_format)
                        if baseline
                        else None,
                    }
            report["environment"]["browser"] = reopen_svgs(session, out, report["pairs"], baseline)
    except Exception as error:
        report["capture_error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["after"] = provenance()
        report["source_and_bundles_stable"] = report["before"]["files"] == report["after"]["files"]
        report["head_stable"] = report["before"]["head"] == report["after"]["head"]
        report["finished_at"] = datetime.now(UTC).isoformat()
        (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    pairs = report["pairs"]
    report["checks"] = {
        "twelve_pairs": len(pairs) == 12,
        "png_svg_dimensions": all(
            pair["PNG"]["dimensions"] == pair["SVG"]["dimensions"] for pair in pairs.values()
        ),
        "png_padding": all(pair["PNG"]["padding_at_least_4px"] for pair in pairs.values()),
        "reopened_svg_padding": all(
            pair["SVG"]["standalone_reopened"]["padding_at_least_4px"] for pair in pairs.values()
        ),
        "reopened_svg_dimensions": all(
            pair["SVG"]["standalone_reopened"]["dimensions"] == pair["SVG"]["dimensions"]
            for pair in pairs.values()
        ),
        "first_restored_png": all(
            pairs[f"frames-{theme}-0"]["PNG"]["rgba_sha256"]
            == pairs[f"frames-{theme}-3"]["PNG"]["rgba_sha256"]
            for theme in ("light", "dark")
        ),
        "first_restored_svg_routes": all(
            pairs[f"frames-{theme}-0"]["SVG"]["paths"] == pairs[f"frames-{theme}-3"]["SVG"]["paths"]
            for theme in ("light", "dark")
        ),
    }
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    gallery(out, baseline, report)
    print(
        json.dumps(
            {
                "out": str(out),
                "checks": report["checks"],
                "source_and_bundles_stable": report["source_and_bundles_stable"],
            },
            indent=2,
        )
    )
    if (
        not report["source_and_bundles_stable"]
        or not report["head_stable"]
        or not all(report["checks"].values())
    ):
        raise SystemExit(
            "Capture checks failed; inspect manifest.json (baseline comparisons are observations)."
        )


if __name__ == "__main__":
    main()
