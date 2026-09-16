#!/usr/bin/env python3
"""Generate a publication-grade PDF gallery of all 34 examples in cs1302-code-visualizer."""

from __future__ import annotations

import argparse
import base64
import json
import re
import tomllib
from pathlib import Path

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import JavaLexer

from cs1302_code_visualizer.browser_driver import get_webdriver

REPO_ROOT = Path(__file__).resolve().parent.parent
METADATA_PATH = Path(
    "/Users/mepcott/.gemini/antigravity-ide/brain/23001bca-d34b-4919-879c-5a79a1815fae/scratch/example_metadata.json"
)
GALLERY_IMAGES_DIR = Path(
    "/Users/mepcott/.gemini/antigravity-ide/brain/23001bca-d34b-4919-879c-5a79a1815fae/gallery_images"
)
ARTIFACT_DIR = Path(
    "/Users/mepcott/.gemini/antigravity-ide/brain/23001bca-d34b-4919-879c-5a79a1815fae"
)


def get_visualizer_version() -> str:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return str(data.get("project", {}).get("version", "unknown"))
    return "unknown"


def load_metadata() -> list[dict]:
    if METADATA_PATH.exists():
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(f"Metadata file not found: {METADATA_PATH}")


def encode_image(img_path: Path) -> str:
    if not img_path.exists():
        return ""
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def build_html(examples: list[dict]) -> str:
    formatter = HtmlFormatter(style="friendly", nowrap=False)
    pygments_css = formatter.get_style_defs(".highlight")

    total_steps = sum(ex.get("step_count", 1) for ex in examples)
    version = get_visualizer_version()

    # Build TOC rows
    toc_items_html = []
    for ex in examples:
        idx = ex["index"]
        title = ex["title"]
        steps = ex.get("step_count", 1)
        if title.lower().startswith(f"example {idx}:"):
            title_clean = title
        elif title.lower().startswith(f"example {idx}"):
            title_clean = f"Example {idx}: " + title[len(f"example {idx}"):].lstrip(" -:").strip()
        else:
            title_clean = f"Example {idx}: {title}"
        slug = f"example-{idx}"
        toc_items_html.append(
            f"""<div class="toc-item">
                <span class="toc-num">Ex {idx:02d} ({steps}s)</span>
                <span class="toc-title"><a href="#{slug}">{title_clean}</a></span>
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
            title_clean = f"Example {idx}: " + title[len(f"example {idx}"):].lstrip(" -:").strip()
        else:
            title_clean = f"Example {idx}: {title}"

        slug = f"example-{idx}"
        rel_java = ex["java_file"]
        cmd = ex.get("cmd", "")

        # Concepts list
        concepts_html = ""
        if ex.get("concepts"):
            items = []
            for c in ex["concepts"]:
                clean_c = c.lstrip("- *").strip()
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
        if step_count > 1 and steps_data:
            step_cards = []
            for s in steps_data:
                s_idx = s["step"]
                s_line = s.get("line", "?")
                s_path = GALLERY_IMAGES_DIR / s["filename"]
                s_data = encode_image(s_path)
                if s_data:
                    step_cards.append(
                        f"""
                        <div class="step-card">
                            <div class="step-card-header">Step {s_idx + 1} of {step_count} (Line {s_line})</div>
                            <img class="step-card-img" src="{s_data}" alt="Step {s_idx + 1}" />
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
            img_path = GALLERY_IMAGES_DIR / f"example{idx}.png"
            img_data = encode_image(img_path)
            img_html = ""
            if img_data:
                img_html = f"""
                <div class="diagram-card">
                    <div class="diagram-badge">Memory Execution State Diagram</div>
                    <img class="diagram-img" src="{img_data}" alt="{title_clean}" />
                </div>
                """

        # Syntax highlighted code
        code_str = ex.get("code", "")
        code_html = ""
        if code_str:
            highlighted = highlight(code_str.strip(), JavaLexer(), formatter)
            code_html = f"""
            <div class="code-card">
                <div class="code-card-header">
                    <span>Source Code: <code>{rel_java}</code></span>
                </div>
                <div class="code-card-body">
                    {highlighted}
                </div>
            </div>
            """

        cmd_html = f'<div class="command-box"><code>{cmd}</code></div>' if cmd else ""

        sections_html.append(
            f"""
        <section class="example-page" id="{slug}">
            <div class="example-header">
                <div class="example-title-group">
                    <span class="example-badge">Example {idx:02d}</span>
                    <span class="example-steps-pill">{step_count} {'Step' if step_count == 1 else 'Steps'}</span>
                    <h2 class="example-heading">{title_clean}</h2>
                </div>
                <span class="example-file-badge">{rel_java}</span>
            </div>
            {cmd_html}
            {concepts_html}
            {img_html}
            {code_html}
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
    width: 75px;
    flex-shrink: 0;
}}

.toc-title {{
    color: #334155;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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

.step-card-img {{
    max-width: 100%;
    max-height: 200px;
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
        A complete catalog of 34 memory execution trace diagrams, heap object graphs, and call stack states.
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
            <div class="stat-value">Java 21</div>
            <div class="stat-label">LTS Runtime</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">v{version}</div>
            <div class="stat-label">Visualizer</div>
        </div>
    </div>
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


def generate_pdf(output_paths: list[Path]):
    print("Loading example metadata...")
    examples = load_metadata()
    print(f"Loaded {len(examples)} examples.")

    print("Building printable HTML...")
    html_content = build_html(examples)

    temp_html = ARTIFACT_DIR / "scratch" / "gallery_print.html"
    temp_html.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Wrote temporary HTML to {temp_html} ({len(html_content)} bytes)")

    print("Launching headless Chrome via Selenium driver...")
    driver = get_webdriver(dpi=2)
    try:
        driver.get(f"file://{temp_html.resolve()}")

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

        for out_path in output_paths:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(pdf_bytes)
            print(f"Successfully wrote PDF to {out_path} ({len(pdf_bytes):,} bytes)")

    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Generate PDF visualizer gallery")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=REPO_ROOT / "examples" / "examples_gallery.pdf",
        help="Primary output path for the generated PDF",
    )
    args = parser.parse_args()

    artifact_pdf = ARTIFACT_DIR / "examples_gallery.pdf"
    targets = [args.output.resolve()]
    if artifact_pdf.resolve() != args.output.resolve():
        targets.append(artifact_pdf.resolve())

    generate_pdf(targets)


if __name__ == "__main__":
    main()
