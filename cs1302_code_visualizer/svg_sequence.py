"""Self-contained shared SVG sequences for HTML exports."""

import json
from pathlib import Path
from xml.etree import ElementTree as ET


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


def sequence_html(manifest, *, fragment=False):
    """Embed generated SVG data as inert JSON and a local player without network calls."""
    data = json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    player = (Path(__file__).parent / "frontend/js/svgSequence.js").read_text()
    player = player.replace("export function", "function")
    content = """<div class="codevis-sequence">
<style>
*{box-sizing:border-box}
:host{display:block;min-width:0;font:14px system-ui;color:#222}
nav{background:white}
nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px;
    border-bottom:1px solid #ddd}
button,input{font:inherit;min-height:32px}
button{padding:4px 10px}
label{display:flex;align-items:center;gap:8px;flex:1 1 140px;min-width:0}
input[type=range]{width:100%;min-width:0}
output{font-variant-numeric:tabular-nums;white-space:nowrap}
#diagram{padding:8px;overflow:auto}
#diagram svg{display:block;max-width:100%;height:auto}
@media print{nav{display:none}#diagram{padding:0}}
</style>
<nav aria-label="Execution steps"><button id="previous">Previous</button>
<label>Step <input id="step" type="range" min="0" value="0"></label>
<button id="next">Next</button><output id="position" aria-live="polite"></output>
<button id="download">Download SVG</button></nav>
<div id="diagram"></div><script type="application/json" id="sequence">""" + data + """</script>
</div><script>
(() => {
""" + player + """
const host = document.currentScript.previousElementSibling;
const root = host.attachShadow({mode: "open"});
root.append(...Array.from(host.childNodes));
const manifest = JSON.parse(root.getElementById('sequence').textContent);
const player = createSequencePlayer(root.getElementById('diagram'), manifest);
const slider = root.getElementById('step');
slider.max = String(manifest.frames.length - 1);
function show(index) {
  player.seek(index); slider.value = String(index);
  root.getElementById('position').textContent = `${index + 1} / ${manifest.frames.length}`;
  root.getElementById('previous').disabled = index === 0;
  root.getElementById('next').disabled = index === manifest.frames.length - 1;
}
slider.addEventListener('input', () => show(Number(slider.value)));
root.getElementById('previous').onclick = () => show(Number(slider.value) - 1);
root.getElementById('next').onclick = () => show(Number(slider.value) + 1);
root.getElementById('download').onclick = () => {
  const url = URL.createObjectURL(new Blob([player.serialize()], {type:'image/svg+xml'}));
  const link = document.createElement('a'); link.href = url;
  link.download = `step-${slider.value}.svg`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
show(0);
})();
</script>"""
    if fragment:
        return content
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Java execution sequence</title><style>body{margin:0}</style></head><body>'
        + content + "</body></html>"
    )

