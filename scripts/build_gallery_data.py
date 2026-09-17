#!/usr/bin/env python3
"""Run all 34 examples, collect multi-step visualization images, update metadata and markdown gallery."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BRAIN_DIR = Path("/Users/mepcott/.gemini/antigravity-ide/brain/23001bca-d34b-4919-879c-5a79a1815fae")
GALLERY_IMAGES_DIR = BRAIN_DIR / "gallery_images"
METADATA_PATH = BRAIN_DIR / "scratch" / "example_metadata.json"
MARKDOWN_GALLERY_PATH = BRAIN_DIR / "examples_gallery.md"

GALLERY_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)


def parse_readme(readme_path: Path) -> tuple[str, list[str]]:
    if not readme_path.exists():
        return "", []
    content = readme_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    title = ""
    for line in lines:
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break

    concepts = []
    in_concepts = False
    for line in lines:
        if re.search(r"##\s*Concepts Illustrated", line, re.IGNORECASE):
            in_concepts = True
            continue
        elif in_concepts and line.startswith("##"):
            break
        elif in_concepts and line.strip().startswith("-"):
            concepts.append(line.strip())

    return title, concepts


def main():
    print("Building multi-step gallery data for all 34 examples...")
    existing_meta = {}
    if METADATA_PATH.exists():
        for item in json.loads(METADATA_PATH.read_text(encoding="utf-8")):
            existing_meta[item["index"]] = item

    all_examples = []

    for idx in range(34):
        ex_dir = REPO_ROOT / "examples" / f"example{idx}"
        if not ex_dir.is_dir():
            continue

        test_sh = ex_dir / "test.sh"
        readme = ex_dir / "README.md"
        title, concepts = parse_readme(readme)

        # Run test.sh keeping json and images
        cmd = ["./test.sh", "--no-open", "--no-rm-json", "--no-rm-image"]
        print(f"Running example{idx}...")
        subprocess.run(cmd, cwd=ex_dir, check=True, capture_output=True)

        # Find json file
        json_files = list(ex_dir.rglob("*.java.json"))
        if not json_files:
            print(f"Warning: No JSON trace found for example{idx}")
            continue

        json_file = json_files[0]
        java_file = json_file.with_name(json_file.name[:-5]) # remove .json
        rel_java = java_file.relative_to(ex_dir)

        trace_data = json.loads(json_file.read_text(encoding="utf-8"))
        raw_steps = trace_data.get("trace", [])

        # Find all step pngs
        step_imgs = []
        step_idx = 0
        while True:
            step_file = java_file.with_name(f"{java_file.name}.{step_idx}.png")
            if not step_file.exists():
                break
            dest_name = f"example{idx}_{step_idx}.png"
            dest_path = GALLERY_IMAGES_DIR / dest_name
            shutil.copy2(step_file, dest_path)

            line_num = raw_steps[step_idx].get("line", "?") if step_idx < len(raw_steps) else "?"
            func_name = raw_steps[step_idx].get("func_name", "") if step_idx < len(raw_steps) else ""

            step_imgs.append({
                "step": step_idx,
                "filename": dest_name,
                "line": line_num,
                "func": func_name,
            })
            step_idx += 1

        # Copy final image as example{idx}.png
        final_img = java_file.with_name(f"{java_file.name}.png")
        if final_img.exists():
            shutil.copy2(final_img, GALLERY_IMAGES_DIR / f"example{idx}.png")

        # Clean up example dir
        for p in ex_dir.rglob("*.png"):
            p.unlink()
        for p in ex_dir.rglob("*.json"):
            p.unlink()

        # Command from test.sh
        test_content = test_sh.read_text(encoding="utf-8")
        test_line = next((line.strip() for line in test_content.splitlines() if "../test.sh" in line), "")

        all_examples.append({
            "index": idx,
            "title": title or f"Example {idx}",
            "java_file": str(rel_java),
            "code": java_file.read_text(encoding="utf-8"),
            "concepts": concepts,
            "cmd": test_line,
            "step_count": len(step_imgs),
            "steps": step_imgs,
        })

    # Save metadata JSON
    METADATA_PATH.write_text(json.dumps(all_examples, indent=2), encoding="utf-8")
    print(f"Updated metadata saved to {METADATA_PATH}")

    # Generate Markdown Gallery with Carousels
    md_lines = [
        "# Code Visualizer Examples Gallery",
        "",
        "A comprehensive visual gallery showcasing memory diagrams generated across all 34 reference example suites (`example0` through `example33`) in `cs1302-code-visualizer`, visualizing all breakpoint steps in execution chronological order.",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
    ]

    for ex in all_examples:
        idx = ex["index"]
        title = ex["title"]
        slug = f"example-{idx}"
        md_lines.append(f"- [Example {idx}: {title}](#{slug}) ({ex['step_count']} steps)")

    md_lines.extend(["", "---", ""])

    for ex in all_examples:
        idx = ex["index"]
        title = ex["title"]
        slug = f"example-{idx}"
        rel_java = ex["java_file"]
        cmd = ex["cmd"]
        step_count = ex["step_count"]

        md_lines.extend([
            f"## Example {idx}: {title}",
            "",
            f"- **Source File**: [`examples/example{idx}/{rel_java}`](file://{REPO_ROOT}/examples/example{idx}/{rel_java})",
            f"- **Execution Command**: `{cmd}`",
            f"- **Total Breakpoint Steps**: {step_count}",
            "- **Concepts Illustrated**:",
        ])

        for c in ex["concepts"]:
            md_lines.append(f"  {c}")

        md_lines.extend(["", "### Breakpoint Execution Steps", ""])

        if step_count > 1:
            md_lines.append("````carousel")
            for i, s in enumerate(ex["steps"]):
                img_path = GALLERY_IMAGES_DIR / s["filename"]
                caption = f"Step {s['step'] + 1} of {step_count} (Line {s['line']}, function: {s['func']})"
                if i > 0:
                    md_lines.append("<!-- slide -->")
                md_lines.append(f"![{caption}]({img_path})")
            md_lines.append("````")
        elif step_count == 1:
            s = ex["steps"][0]
            img_path = GALLERY_IMAGES_DIR / s["filename"]
            caption = f"Step 1 of 1 (Line {s['line']})"
            md_lines.append(f"![{caption}]({img_path})")
        else:
            img_path = GALLERY_IMAGES_DIR / f"example{idx}.png"
            md_lines.append(f"![Final Diagram]({img_path})")

        md_lines.extend([
            "",
            "<details>",
            f"<summary>View Source Code (examples/example{idx}/{rel_java})</summary>",
            "",
            "```java",
            ex["code"].strip(),
            "```",
            "</details>",
            "",
            "---",
            "",
        ])

    MARKDOWN_GALLERY_PATH.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Updated markdown gallery saved to {MARKDOWN_GALLERY_PATH}")


if __name__ == "__main__":
    main()
