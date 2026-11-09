"""Build a self-contained experimental player from shared SVG sequence nodes."""

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from cs1302_code_visualizer import RenderingSession
from cs1302_code_visualizer.browser_driver import generate_step_images

ROOT = Path(__file__).resolve().parents[1]


def pack_frames(frames):
    """Intern immutable XML subtrees; every frame is an independently seekable root."""
    nodes = []
    known = {}

    def intern(element):
        children = []
        if element.text:
            children.append(element.text)
        for child in element:
            children.append(intern(child))
            if child.tail:
                children.append(child.tail)
        record = [element.tag, sorted(element.attrib.items()), children]
        key = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        if key not in known:
            known[key] = len(nodes)
            nodes.append(record)
        return known[key]

    roots = [intern(ET.fromstring(frame)) for frame in frames]
    if not roots:
        raise ValueError("A sequence needs at least one frame")
    return {"version": 1, "nodes": nodes, "frames": roots}


def sequence_html(manifest):
    """Embed generated SVG data as inert JSON and a local player without network calls."""
    data = json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    player = (ROOT / "cs1302_code_visualizer/frontend/js/svgSequence.js").read_text()
    player = player.replace("export function", "function")
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<title>SVG sequence prototype</title>
<style>body{font:16px system-ui;margin:24px;background:#f4f4f4;color:#222}
nav{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
button,input{font:inherit}#diagram{overflow:auto;background:white;padding:16px}
#diagram svg{display:block}p{max-width:80ch}</style>
<h1>SVG sequence prototype</h1>
<p>Choose any execution step. Only the current diagram is mounted. Download SVG saves
that step with its definitions and accessible description.</p>
<nav aria-label="Execution steps"><button id="previous">Previous</button>
<label>Step <input id="step" type="range" min="0" value="0"></label>
<button id="next">Next</button><output id="position" aria-live="polite"></output>
<button id="download">Download SVG</button></nav>
<div id="diagram"></div><script type="application/json" id="sequence">""" + data + """</script>
<script type="module">""" + player + """
const manifest = JSON.parse(document.getElementById('sequence').textContent);
const player = createSequencePlayer(document.getElementById('diagram'), manifest);
const slider = document.getElementById('step');
slider.max = String(manifest.frames.length - 1);
function show(index) {
  player.seek(index); slider.value = String(index);
  document.getElementById('position').textContent = `${index + 1} / ${manifest.frames.length}`;
  document.getElementById('previous').disabled = index === 0;
  document.getElementById('next').disabled = index === manifest.frames.length - 1;
}
slider.addEventListener('input', () => show(Number(slider.value)));
document.getElementById('previous').onclick = () => show(Number(slider.value) - 1);
document.getElementById('next').onclick = () => show(Number(slider.value) + 1);
document.getElementById('download').onclick = () => {
  const url = URL.createObjectURL(new Blob([player.serialize()], {type:'image/svg+xml'}));
  const link = document.createElement('a'); link.href = url;
  link.download = `step-${slider.value}.svg`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
show(0);
</script></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with RenderingSession(max_browsers=1) as session:
        frames = generate_step_images(args.trace.read_text(), format="SVG", session=session)
    manifest = pack_frames(frames)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(sequence_html(manifest))
    print(f"{len(frames)} frames, {len(manifest['nodes'])} unique subtrees: {args.output}")


if __name__ == "__main__":
    main()
