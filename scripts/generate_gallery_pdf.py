#!/usr/bin/env python3
"""Generate a publication-grade PDF gallery of all 34 examples in cs1302-code-visualizer."""

from __future__ import annotations

import argparse
import base64
import json
import re
from html import escape
from pathlib import Path

from PIL import Image
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import JavaLexer

from cs1302_code_visualizer.browser_driver import get_webdriver

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "build" / "gallery"


def load_metadata(artifact_dir: Path) -> dict:
    with (artifact_dir / "example_metadata.json").open(encoding="utf-8") as source:
        metadata = json.load(source)
    examples = metadata["examples"]
    if [ex["index"] for ex in examples] != list(range(34)):
        raise ValueError("Gallery metadata must contain all 34 examples in order")
    for example in examples:
        if not example["steps"] or example["step_count"] != len(example["steps"]):
            raise ValueError(f"Invalid step count for example{example['index']}")
    return metadata


def encode_image(img_path: Path) -> str:
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def build_html(metadata: dict, artifact_dir: Path) -> str:
    examples = metadata["examples"]
    images_dir = artifact_dir / "gallery_images"
    formatter = HtmlFormatter(style="friendly", nowrap=False)
    pygments_css = formatter.get_style_defs(".highlight")

    total_steps = sum(ex.get("step_count", 1) for ex in examples)
    version = escape(metadata["visualizer_version"])
    java_version = escape(metadata["java_version"])

    # Build TOC rows
    toc_items_html = []
    for ex in examples:
        idx = ex["index"]
        title = ex["title"]
        steps = ex.get("step_count", 1)
        if title.lower().startswith(f"example {idx}:"):
            title_clean = title
        elif title.lower().startswith(f"example {idx}"):
            title_clean = f"Example {idx}: " + title[len(f"example {idx}") :].lstrip(" -:").strip()
        else:
            title_clean = f"Example {idx}: {title}"
        slug = f"example-{idx}"
        toc_items_html.append(
            f"""<div class="toc-item">
                <span class="toc-num">Ex {idx:02d} · {steps} steps</span>
                <span class="toc-title"><a href="#{slug}">{escape(title_clean)}</a></span>
            </div>"""
        )
    toc_html = "\n".join(toc_items_html)

    # Build Example Sections
    sections_html = []
    for ex in examples:
        idx = ex["index"]
        title = ex["title"]
        step_count = ex.get("step_count", 1)
        steps_data = ex.get("steps", [])

        if title.lower().startswith(f"example {idx}:"):
            title_clean = title
        elif title.lower().startswith(f"example {idx}"):
            title_clean = f"Example {idx}: " + title[len(f"example {idx}") :].lstrip(" -:").strip()
        else:
            title_clean = f"Example {idx}: {title}"

        slug = f"example-{idx}"
        rel_java = escape(ex["java_file"])
        cmd = ex.get("cmd", "")

        # Concepts list
        concepts_html = ""
        if ex.get("concepts"):
            items = []
            for c in ex["concepts"]:
                clean_c = escape(re.sub(r"^[-*]\s+", "", c).strip())
                clean_c = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", clean_c)
                clean_c = re.sub(r"`([^`]+)`", r"<code>\1</code>", clean_c)
                items.append(f"<li>{clean_c}</li>")
            concepts_html = f"""
            <div class="concepts-box">
                <div class="concepts-title">Concepts Illustrated</div>
                <ul class="concepts-list">
                    {"".join(items)}
                </ul>
            </div>
            """

        # Diagram images
        if steps_data:
            step_cards = []
            for s in steps_data:
                s_idx = s["step"]
                s_line = s.get("line", "?")
                s_path = images_dir / s["filename"]
                with Image.open(s_path) as diagram:
                    width, height = (dimension / metadata["dpi"] for dimension in diagram.size)
                card_class = "step-card wide" if width > 330 or height > 240 else "step-card"
                s_data = encode_image(s_path)
                if s_data:
                    step_cards.append(
                        f"""
                        <div class="{card_class}">
                            <div class="step-card-header">Step {s_idx + 1} of {step_count} (Line {s_line})</div>
                            <img class="step-card-img" style="width: {width}px" src="{s_data}" alt="Step {s_idx + 1}" />
                        </div>
                        """
                    )
            img_html = f"""
            <div class="steps-section">
                <div class="steps-section-title">Breakpoint Execution Sequence ({step_count} Steps)</div>
                <div class="steps-grid">
                    {"".join(step_cards)}
                </div>
            </div>
            """
        else:
            raise ValueError(f"No step images for example{idx}")

        # Syntax highlighted code
        code_html = ""
        for source in ex["sources"]:
            highlighted = highlight(source["code"].strip(), JavaLexer(), formatter)
            code_html += f"""
            <div class="code-card">
                <div class="code-card-header">
                    <span>Source Code: <code>{escape(source["path"])}</code></span>
                </div>
                <div class="code-card-body">
                    {highlighted}
                </div>
            </div>
            """

        cmd_html = f'<div class="command-box"><code>{escape(cmd)}</code></div>' if cmd else ""

        sections_html.append(
            f"""
        <section class="example-page" id="{slug}">
            <div class="example-header">
                <div class="example-title-group">
                    <span class="example-badge">Example {idx:02d}</span>
                    <span class="example-steps-pill">{step_count} {"Step" if step_count == 1 else "Steps"}</span>
                    <h2 class="example-heading">{escape(title_clean)}</h2>
                </div>
                <span class="example-file-badge">{rel_java}</span>
            </div>
            {cmd_html}
            {concepts_html}
            {code_html}
            {img_html}
        </section>
        """
        )

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CS1302 Code Visualizer Examples Gallery</title>
<style>
@page {{
    size: letter portrait;
    margin: 0.5in;
}}

* {{
    box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1e293b;
    margin: 0;
    padding: 0;
    font-size: 9pt;
    line-height: 1.45;
    background-color: #ffffff;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}

/* Cover Page */
.cover-page {{
    page-break-after: always;
    min-height: 9.8in;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    background: radial-gradient(circle at 50% 30%, #1e293b 0%, #0f172a 100%);
    color: #ffffff;
    padding: 2in 1in;
    margin: -0.5in;
}}

.cover-pill {{
    display: inline-block;
    background: rgba(56, 189, 248, 0.15);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.35);
    padding: 6px 18px;
    border-radius: 9999px;
    font-size: 10pt;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 24px;
}}

.cover-title {{
    font-size: 32pt;
    font-weight: 800;
    line-height: 1.15;
    margin: 0 0 16px 0;
    letter-spacing: -0.5px;
}}

.cover-title span {{
    color: #38bdf8;
}}

.cover-subtitle {{
    font-size: 15pt;
    color: #94a3b8;
    font-weight: 400;
    max-width: 600px;
    margin: 0 auto 36px auto;
    line-height: 1.4;
}}

.cover-stats {{
    display: flex;
    gap: 32px;
    justify-content: center;
    margin-top: 24px;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    padding-top: 24px;
}}

.stat-item {{
    text-align: center;
}}

.stat-value {{
    font-size: 20pt;
    font-weight: 700;
    color: #f8fafc;
}}

.stat-label {{
    font-size: 8.5pt;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* Table of Contents */
.toc-page {{
    page-break-after: always;
    padding-top: 0.1in;
}}

.toc-header {{
    font-size: 18pt;
    font-weight: 700;
    color: #0f172a;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 8px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}}

.toc-subtitle {{
    font-size: 9pt;
    font-weight: 400;
    color: #64748b;
}}

.toc-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    column-gap: 24px;
    row-gap: 6px;
}}

.toc-item {{
    font-size: 8pt;
    display: flex;
    align-items: baseline;
    padding: 3px 0;
    border-bottom: 1px dotted #e2e8f0;
}}

.toc-num {{
    font-weight: 700;
    color: #0284c7;
    width: 88px;
    flex-shrink: 0;
}}

.toc-title {{
    color: #334155;
    overflow-wrap: anywhere;
}}

.toc-title a {{
    color: inherit;
    text-decoration: none;
}}

/* Example Page */
.example-page {{
    page-break-before: always;
    break-inside: auto;
    padding-top: 0.1in;
    margin-bottom: 0.2in;
}}

.example-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #0f172a;
    padding-bottom: 6px;
    margin-bottom: 10px;
}}

.example-title-group {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
}}

.example-badge {{
    background: #0284c7;
    color: #ffffff;
    font-size: 8pt;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 4px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

.example-heading {{
    font-size: 13pt;
    font-weight: 700;
    color: #0f172a;
    margin: 0;
}}

.example-file-badge {{
    overflow-wrap: anywhere;
    max-width: 35%;
    font-family: monospace;
    font-size: 7.5pt;
    background: #f1f5f9;
    color: #475569;
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid #cbd5e1;
}}

.command-box {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 4px 8px;
    margin-bottom: 8px;
    font-size: 7.5pt;
    color: #334155;
}}

.command-box code {{
    font-family: monospace;
    overflow-wrap: anywhere;
}}

.concepts-box {{
    background: #f0fdf4;
    border-left: 3px solid #16a34a;
    border-radius: 0 4px 4px 0;
    padding: 6px 10px;
    margin-bottom: 10px;
}}

.concepts-title {{
    font-size: 7.5pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #15803d;
    margin-bottom: 2px;
}}

.concepts-list {{
    margin: 0;
    padding-left: 16px;
    font-size: 8pt;
    color: #1e293b;
}}

.concepts-list li {{
    margin-bottom: 2px;
}}

.example-steps-pill {{
    background: #e0f2fe;
    color: #0369a1;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 4px;
    border: 1px solid #bae6fd;
}}

.steps-section {{
    margin-bottom: 12px;
}}

.steps-section-title {{
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #0284c7;
    margin-bottom: 6px;
}}

.steps-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}}

.step-card {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 6px;
    text-align: center;
    flex: 0 0 calc(50% - 4px);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    page-break-inside: avoid;
    break-inside: avoid;
}}

.step-card-header {{
    font-size: 7pt;
    font-weight: 700;
    color: #475569;
    margin-bottom: 4px;
    text-align: left;
}}

.step-card.wide {{
    flex-basis: 100%;
}}

.step-card-img {{
    max-width: 100%;
    max-height: 8.5in;
    object-fit: contain;
    display: inline-block;
}}

.diagram-card {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 8px;
    text-align: center;
    margin-bottom: 10px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}}

.diagram-badge {{
    font-size: 7pt;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
    margin-bottom: 6px;
}}

.diagram-img {{
    max-width: 100%;
    max-height: 380px;
    object-fit: contain;
    display: inline-block;
}}

.code-card {{
    break-inside: avoid;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    overflow: hidden;
    margin-top: 8px;
}}

.code-card-header {{
    background: #f1f5f9;
    border-bottom: 1px solid #cbd5e1;
    padding: 4px 8px;
    font-size: 7.5pt;
    font-weight: 600;
    color: #475569;
}}

.code-card-header code {{
    font-family: monospace;
}}

.code-card-body {{
    background: #fafafa;
    padding: 6px 8px;
    font-family: monospace;
    font-size: 7pt;
    line-height: 1.35;
    overflow-x: auto;
}}

.code-card-body pre {{
    margin: 0;
    font-family: monospace;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}}

{pygments_css}

</style>
</head>
<body>

<!-- Cover Page -->
<div class="cover-page">
    <div class="cover-pill">CS1302 Reference Catalog</div>
    <h1 class="cover-title">Code Visualizer<br><span>Examples Gallery</span></h1>
    <div class="cover-subtitle">
        All 34 reference examples, with memory diagrams, heap object graphs, and call stack states at every configured execution step.
    </div>
    <div class="cover-stats">
        <div class="stat-item">
            <div class="stat-value">34</div>
            <div class="stat-label">Suites (00–33)</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">{total_steps}</div>
            <div class="stat-label">Breakpoint Steps</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">Java 25</div>
            <div class="stat-label">LTS Runtime</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">v{version}</div>
            <div class="stat-label">Visualizer</div>
        </div>
    </div>
    <p>JDK {java_version}</p>
</div>

<!-- Table of Contents -->
<div class="toc-page">
    <div class="toc-header">
        <span>Table of Contents</span>
        <span class="toc-subtitle">34 Reference Suites</span>
    </div>
    <div class="toc-grid">
        {toc_html}
    </div>
</div>

<!-- Example Pages -->
{"".join(sections_html)}

</body>
</html>
"""
    return full_html


def generate_pdf(output_path: Path, artifact_dir: Path):
    print("Loading example metadata...")
    metadata = load_metadata(artifact_dir)
    print(f"Loaded {len(metadata['examples'])} examples.")

    print("Building printable HTML...")
    html_content = build_html(metadata, artifact_dir)

    temp_html = artifact_dir / "gallery_print.html"
    temp_html.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Wrote temporary HTML to {temp_html} ({len(html_content)} bytes)")

    print("Launching headless Chrome via Selenium driver...")
    driver = get_webdriver(dpi=2)
    try:
        driver.get(f"file://{temp_html.resolve()}")
        driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            Promise.all([document.fonts.ready, ...Array.from(document.images, image => image.decode())])
              .then(() => done(true), error => done(String(error)));
        """)
        if not driver.execute_script(
            "return Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)"
        ):
            raise ValueError("A gallery image failed to load")

        print("Executing Page.printToPDF via CDP...")
        pdf_res = driver.execute_cdp_cmd(
            "Page.printToPDF",
            {
                "printBackground": True,
                "preferCSSPageSize": True,
                "displayHeaderFooter": True,
                "headerTemplate": "<div></div>",
                "footerTemplate": (
                    "<div style='font-family: -apple-system, BlinkMacSystemFont, sans-serif; "
                    "font-size: 7.5pt; color: #94a3b8; width: 100%; text-align: center; "
                    "padding-bottom: 0.1in;'>"
                    "CS1302 Code Visualizer &bull; Reference Gallery &bull; "
                    "Page <span class='pageNumber'></span> of <span class='totalPages'></span>"
                    "</div>"
                ),
            },
        )
        pdf_bytes = base64.b64decode(pdf_res["data"])
        print(f"Generated PDF payload: {len(pdf_bytes):,} bytes.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)
        print(f"Successfully wrote PDF to {output_path} ({len(pdf_bytes):,} bytes)")

    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Generate PDF visualizer gallery")
    parser.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR)
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=REPO_ROOT / "examples" / "examples_gallery.pdf",
        help="Primary output path for the generated PDF",
    )
    args = parser.parse_args()

    generate_pdf(args.output.resolve(), args.artifact_dir.resolve())


if __name__ == "__main__":
    main()
