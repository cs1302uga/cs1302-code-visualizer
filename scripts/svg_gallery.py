"""Generate reproducible PNG/SVG comparisons and browser evidence, without a server."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

from cs1302_code_visualizer.browser_driver import (
    generate_image,
    get_webdriver,
    resolve_trace_payload,
)
from cs1302_code_visualizer.errors import CodeVisError, CodeVisualizerError
from cs1302_code_visualizer.session import RenderingSession
from cs1302_code_visualizer.trace_generator import ensure_jdk_installed
from examples.run_batch import _trace_options, parse_example_test_sh

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "svg-gallery"


def cases():
    """Yield existing example configurations and focused presentation cases."""
    for path in sorted(
        (ROOT / "examples").glob("example*/test.sh"),
        key=lambda p: int(p.parent.name.removeprefix("example")),
    ):
        source, arguments = parse_example_test_sh(path)
        yield path.parent.name, path.parent / source, arguments, {}, None
    source = ROOT / "scripts" / "svg_cases" / "EdgeCases.java"
    for name, options in [
        ("edges", {}),
        ("edges-vertical", {"array_orientation": "vertical"}),
        ("edges-alternating", {"alternate_array_orientations": True}),
        ("edges-labels", {"text_memory_labels": True}),
        ("edges-no-types", {"include_types": False}),
        ("edges-prefix", {"strip_type_prefixes": ["EdgeCases$", "java.lang."]}),
        ("edges-override", {"array_orientation": "vertical", "alternate_array_orientations": True}),
        ("edges-dpi2", {"dpi": 2}),
        ("edges-json", {"visualizer": "json-pre"}),
    ]:
        yield name, source, [], options, 0 if name == "edges-json" else None
    for step in [0, 5, 10]:
        yield f"edges-step{step}", source, [], {}, step


def inline_svg(path: Path, prefix: str) -> tuple[str, str]:
    """Scope IDs for embedding and render the export's description as semantic HTML."""
    root = ET.fromstring(path.read_bytes())
    namespace = "{http://www.w3.org/2000/svg}"
    metadata = root.find(f"{namespace}metadata[@data-description='1']")
    description = json.loads(metadata.text) if metadata is not None else None
    if description is None:
        raise ValueError("SVG has no structured text description")
    identifiers = {
        e.attrib["id"]: f"{prefix}-{e.attrib['id']}" for e in root.iter() if "id" in e.attrib
    }
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if key == "id":
                value = identifiers[value]
            elif key in {"aria-labelledby", "aria-describedby"}:
                value = " ".join(identifiers.get(token, token) for token in value.split())
            else:
                for original, replacement in identifiers.items():
                    value = value.replace(f"url(#{original})", f"url(#{replacement})")
            element.set(key, value)
    # The adjacent disclosure is the single full narration in the gallery.
    root.attrib.pop("aria-describedby", None)
    root.attrib.pop("aria-labelledby", None)
    root.set("aria-label", description["summary"])
    root.remove(root.find(namespace + "title"))
    root.remove(root.find(namespace + "desc"))
    root.remove(metadata)
    ET.register_namespace("", namespace[1:-1])
    transcript = f'<details class="description"><summary>Text description</summary><p>{html.escape(description["summary"])}</p>'
    for section in description["sections"]:
        transcript += f"<h3>{html.escape(section['heading'])}</h3><ul>"
        transcript += "".join(
            f"<li>{html.escape(item)}</li>" for item in section["items"] or ["No visible entries."]
        )
        transcript += "</ul>"
    return ET.tostring(root, encoding="unicode"), transcript + "</details>"


def gallery_html(records: list[dict], stage: str, output: Path | None = None) -> str:
    """Build a local, accessible gallery that displays the original exports."""
    cards = []
    for row in records:
        name = html.escape(row["name"])
        panels = []
        transcript = ""
        for format in ["png", "svg"]:
            filename = f"{name}.{format}"
            display = f'<img src="{filename}" alt="{name} {format.upper()} export">'
            if format == "svg" and row.get("svg"):
                if output is None:
                    raise ValueError("SVG gallery panels require an export directory")
                display, transcript = inline_svg(output / f"{row['name']}.svg", row["name"])
            panels.append(
                f"<figure><figcaption>{format.upper()} · "
                + (
                    f'<a href="{filename}" download>Download original</a>'
                    if row.get(format)
                    else "Unavailable"
                )
                + "</figcaption>"
                + (display if row.get(format) else '<p class="missing">Export unavailable</p>')
                + "</figure>"
            )
        cards.append(
            f'<article id="{name}"><h2>{name}</h2>'
            f'<p class="status">{html.escape(row["status"])}</p>'
            f'<div class="pair">{"".join(panels)}</div>{transcript}'
            f"<details><summary>Reproduce this comparison</summary>"
            f"<pre>{html.escape(row['command'])}</pre>"
            f"<pre>{html.escape(json.dumps(row.get('options', {}), indent=2))}</pre>"
            f"<p>Source: {html.escape(row.get('source', ''))}; step: {row.get('step') if row.get('step') is not None else 'final'}</p>"
            + (f'<a href="{name}.trace.json">Exact trace</a>' if row.get("png") else "")
            + (
                f' · <a href="{name}.inkscape.png">Inkscape rendering</a>'
                if row.get("inkscape")
                else ""
            )
            + "</details></article>"
        )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PNG / SVG export comparisons</title><style>
:root{color-scheme:light;--ink:#183046;--muted:#455d70;--paper:#eef3f8;--rule:#bacbd9;--accent:#075b83}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 'Trebuchet MS',sans-serif}
header,main{max-width:1600px;margin:auto;padding:24px}header{border-bottom:4px solid var(--accent)}
h1{font:600 clamp(28px,4vw,48px)/1.1 'Avenir Next',sans-serif;margin:8px 0}h2{margin:0;font-size:22px}
a{color:var(--accent)}a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
article{background:white;border:1px solid var(--rule);border-radius:8px;padding:20px;margin-bottom:28px}
.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:start}
figure{margin:0;min-width:0;border:1px solid var(--rule);overflow:auto;background:white}
figcaption{padding:8px 12px;background:var(--paper);font:13px/1.5 monospace;border-bottom:1px solid var(--rule)}
img,figure svg{display:block;max-width:100%;height:auto}.status{color:var(--muted)}.missing{padding:24px;color:#9b2d27}
details{margin-top:16px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
@media(max-width:700px){.pair{grid-template-columns:1fr}header,main{padding:12px}article{padding:12px}}
</style><header><p>CODE VISUALIZER / EXPORT LAB</p><h1>One state. Two formats.</h1>
<p>Original PNG and SVG exports from identical traces and presentation options.</p>
<p>Select and copy text in the SVG panels. Expand Text description to read the stack and heap as headings and lists.</p>
"""
        + f"<p>Milestone: {html.escape(stage)} · {len(records)} comparisons</p></header><main>"
        + "".join(cards)
        + "</main></html>"
    )


def capture_gallery(output: Path) -> None:
    """Check local image loading and save overview and per-case screenshots."""
    driver = get_webdriver()
    try:
        driver.set_window_size(1500, 1100)
        driver.get((output / "index.html").as_uri())
        driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            Promise.all(Array.from(document.images, image => image.decode().catch(() => null)))
                .then(() => document.fonts.ready).then(() => done());
        """)
        broken = driver.execute_script(
            "return Array.from(document.images).filter(i => !i.naturalWidth).map(i => i.src)"
        )
        if broken:
            raise RuntimeError(f"Gallery images failed to load: {broken}")
        driver.save_screenshot(str(output / "overview.png"))
        for card in driver.find_elements(By.CSS_SELECTOR, "article"):
            rect = card.rect
            result = driver.execute_cdp_cmd(
                "Page.captureScreenshot",
                {
                    "format": "png",
                    "captureBeyondViewport": True,
                    "clip": {
                        **{key: rect[key] for key in ("x", "y", "width", "height")},
                        "scale": 1,
                    },
                },
            )
            (output / f"{card.get_attribute('id')}.comparison.png").write_bytes(
                base64.b64decode(result["data"])
            )
    finally:
        driver.quit()


def validate_svg(path: Path, inkscape: bool) -> str:
    """Check standalone primitives and optionally exercise the Inkscape importer."""
    root = ET.fromstring(path.read_bytes())
    namespace = "{http://www.w3.org/2000/svg}"
    if root.tag != namespace + "svg":
        raise ValueError("Export is not an SVG document")
    for element in root.iter():
        if element.tag in {namespace + tag for tag in ("image", "foreignObject", "script")}:
            raise ValueError("Export contains non-vector or active content")
        if any("href" in key for key in element.attrib):
            raise ValueError("Export depends on an external resource")
    if inkscape:
        subprocess.run(
            [
                "inkscape",
                str(path),
                "--export-type=png",
                f"--export-filename={path.with_suffix('.inkscape.png')}",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return "Standalone SVG verified; Inkscape import rendered."
    return "Standalone SVG verified; Inkscape not checked."


def main() -> None:
    """Generate a milestone; preserve prior milestones and report export failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="final")
    parser.add_argument("--case", action="append", dest="selected")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--refresh-traces", action="store_true")
    parser.add_argument("--inkscape", action="store_true", help="Also render each SVG in Inkscape")
    parser.add_argument("--review-file", type=Path, help="JSON mapping case names to visual notes")
    args = parser.parse_args()
    if Path(args.stage).name != args.stage or args.stage in (".", ".."):
        parser.error("--stage must be a single directory name")
    os.environ["CS1302_HEADLESS"] = "true"
    output = ARTIFACTS / args.stage
    output.mkdir(parents=True, exist_ok=True)
    cache = ARTIFACTS / "traces"
    cache.mkdir(exist_ok=True)
    records = []
    reviews = json.loads(args.review_file.read_text()) if args.review_file else {}
    with RenderingSession(max_browsers=1, use_batch_tracer=True) as session:
        java_home = ensure_jdk_installed()
        for name, source, arguments, options, step in cases():
            if args.selected and name not in args.selected:
                continue
            command = f"uv run python -m scripts.svg_gallery --stage {shlex.quote(args.stage)} --case {name}"
            if args.inkscape:
                command += " --inkscape"
            record = {
                "name": name,
                "command": command,
                "options": options,
                "step": step,
                "source": str(source.relative_to(ROOT)),
            }
            try:
                source_root = (
                    ROOT / "examples" / name if name.startswith("example") else source.parent
                )
                settings = _trace_options(arguments, source_root)
                settings["extra_tracer_args"] += ["--input", str(source)]
                if name.startswith("edges"):
                    settings.update(all_breakpoints=True, accumulate_breakpoints=True)
                fingerprint = json.dumps(
                    {
                        "sources": {
                            str(p.relative_to(source_root)): p.read_text()
                            for p in sorted(source_root.rglob("*.java"))
                        },
                        "arguments": arguments,
                        "settings": settings,
                        "stdin_file": settings["stdin_file"].read_text()
                        if settings["stdin_file"]
                        else None,
                        "jdk": (java_home / "release").read_text(),
                        "pin": (ROOT / "pyproject.toml").read_text(),
                    },
                    sort_keys=True,
                    default=str,
                )
                key = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
                trace_path = cache / f"{name if name.startswith('example') else 'edges'}-{key}.json"
                if not trace_path.exists() or args.refresh_traces:
                    trace_path.write_text(
                        session.generate_trace(
                            java_home,
                            source.read_text(),
                            **settings,
                        )
                    )
                payload = resolve_trace_payload(trace_path.read_text())
                if name == "edges-override":
                    matrix = payload["trace"][-1]["stack_to_render"][0]["encoded_locals"]["matrix"][
                        1
                    ]
                    options["array_orientations"] = {str(matrix): "horizontal"}
                if step is not None:
                    payload = {**payload, "trace": payload["trace"][: step + 1]}
                trace = json.dumps(payload)
                (output / f"{name}.trace.json").write_text(trace)
                baseline = ARTIFACTS / "baseline" / f"{name}.png"
                baseline_trace = baseline.with_suffix(".trace.json")
                baseline_rows = ARTIFACTS / "baseline" / "results.json"
                baseline_options = (
                    {r["name"]: r["options"] for r in json.loads(baseline_rows.read_text())}
                    if baseline_rows.exists()
                    else {}
                )
                if (
                    baseline.exists()
                    and args.stage != "baseline"
                    and baseline_trace.exists()
                    and baseline_trace.read_text() == trace
                    and baseline_options.get(name) == options
                ):
                    shutil.copy2(baseline, output / f"{name}.png")
                else:
                    (output / f"{name}.png").write_bytes(
                        generate_image(trace, session=session, **options)
                    )
                record["png"] = True
                record["status"] = "PNG baseline captured."
                if not args.baseline_only:
                    (output / f"{name}.svg").write_bytes(
                        generate_image(
                            trace,
                            format="SVG",
                            session=session,
                            **options,
                        )
                    )
                    record["svg"] = True
                    record["status"] = validate_svg(output / f"{name}.svg", args.inkscape)
                    record["inkscape"] = args.inkscape
                    record["status"] += " " + reviews.get(name, "Visual review pending.")
            except (
                CodeVisError,
                CodeVisualizerError,
                OSError,
                ValueError,
                RuntimeError,
                KeyError,
                WebDriverException,
                ET.ParseError,
                subprocess.SubprocessError,
            ) as exc:
                record["status"] = f"FAILED: {type(exc).__name__}: {exc}"
            records.append(record)
            print(name, record["status"], flush=True)
    if not records:
        parser.error("no matching cases")
    (output / "results.json").write_text(json.dumps(records, indent=2))
    (output / "index.html").write_text(gallery_html(records, args.stage, output))
    capture_gallery(output)
    print(output / "index.html")
    if any(row["status"].startswith("FAILED") for row in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
