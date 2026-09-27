"""Package unmodified browser screenshots into a shareable review PDF."""

import json
import shutil
import zipfile
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
captures = json.loads((ROOT / "captures.json").read_text())
screenshots = ROOT / "screenshots"
screenshots.mkdir(exist_ok=True)
pdf = ROOT / "option-b-prototype-review.pdf"
c = canvas.Canvas(str(pdf), pagesize=(1280, 720))
c.setTitle("Option B - approved string-style prototype")
c.setSubject("Twelve browser screenshots of the approved compact-string visual prototype")

for item in captures:
    number = item["index"] + 1
    name = f"{number:02d}-{item['example']}-{item['orientation']}-{item['theme']}.png"
    dest = screenshots / name
    source = ROOT / item["path"]
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    item["file"] = f"screenshots/{name}"
    c.setFillColorRGB(0.09, 0.17, 0.23)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(24, 683, "Option B | Approved visual prototype")
    c.setFont("Helvetica", 12)
    c.drawRightString(1256, 685, f"{number} / {len(captures)}")
    c.setFont("Helvetica", 11)
    c.drawString(
        24, 661, "Compact strings with reference values, aligned value boxes, and consistent arrows"
    )
    # Clip only unused viewport whitespace; preserve the original PNG bytes.
    scale = 1232 / 1280
    visible_height = min(570, (item["contentHeight"] * 800 / 960 + 8) * scale)
    top = 642
    c.saveState()
    clip = c.beginPath()
    clip.rect(24, top - visible_height, 1232, visible_height)
    c.clipPath(clip, stroke=0)
    c.drawImage(str(dest), 24, top - 800 * scale, width=1232, height=800 * scale)
    c.restoreState()
    c.setFillColorRGB(0.35, 0.4, 0.45)
    c.setFont("Helvetica", 10)
    c.drawString(
        24,
        36,
        "Reconstructed course examples and edge cases. Prototype only; feature implementation pending.",
    )
    c.drawRightString(1256, 36, "2026-09-27 | prototype cc98e9c")
    c.bookmarkPage(f"example-{number}")
    c.addOutlineEntry(item["title"], f"example-{number}", 0)
    c.showPage()
c.save()

manifest = [{k: v for k, v in item.items() if k != "path"} for item in captures]
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
(ROOT / "README.md").write_text("""# Option B prototype review

The PDF combines twelve browser screenshots of approved Option B. PNG files in
`screenshots/` are the original, unmodified browser captures. The PDF hides unused
viewport whitespace through page clipping and includes navigation bookmarks.

Examples: Node chain, cycle, LinkBasedList, ArrayBasedList in both orientations,
both implementations after removal and clear, shared references, long/empty
strings in both orientations, and two dark-theme views.

These are reconstructed course memory snapshots and additional edge cases,
not screenshots of actual Java execution. Production implementation is pending.

Prototype commit: cc98e9c, branch prototype/string-style-option-b.
Capture date: 2026-09-27.

To rebuild the review PDF and ZIP from the captured screenshots, run
`uv run --extra review python artifacts/option-b-review/build_review.py`.
""")
with zipfile.ZipFile(ROOT / "option-b-review-bundle.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
    for path in [
        pdf,
        ROOT / "README.md",
        ROOT / "manifest.json",
        *sorted(screenshots.glob("*.png")),
    ]:
        bundle.write(path, path.relative_to(ROOT))
reader = PdfReader(pdf)
assert len(reader.pages) == 12
assert all(len(page.images) == 1 for page in reader.pages)
print(f"Created {pdf.name}: {len(reader.pages)} pages; {pdf.stat().st_size:,} bytes")
