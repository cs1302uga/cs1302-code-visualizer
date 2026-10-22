"""Generate native reference-sharing comparisons and a portable review package.

Run after building the frontend: uv run python -m scripts.review_shared_references
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
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

from cs1302_code_visualizer import RenderingSession, browser_driver

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "cs1302_code_visualizer/frontend/tests/fixtures/reference-sharing"
OBSERVE = """
const m=window.optFrontend.dataViz.jsPlumbInstance;
const visible=e=>{for(let p=e;p;p=p.parentElement){const s=getComputedStyle(p);
  if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0')return false;}return true;};
const paths=[...m.svgCanvas.querySelectorAll('path')].filter(visible);
const heads=[...m.svgCanvas.querySelectorAll('polygon')].filter(visible);
return {policy:m.referenceRoutingPolicy,sources:m.connections.length,heads:heads.length,
  paintedLength:paths.reduce((n,p)=>n+p.getTotalLength(),0),
  relations:m.connections.map(c=>({source:c.sourceId,target:c.targetId})),
  plan:m.referenceSharingPlan?{baselineValid:m.referenceSharingPlan.baselineValid,
    groups:m.referenceSharingPlan.groups.length,diagnostics:m.referenceSharingPlan.diagnostics}:null,
  browser:navigator.userAgent,viewport:[innerWidth,innerHeight]};
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / ".scratch/reference-sharing-review")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["CS1302_HEADLESS"] = "true"
    results = []
    source_paths = [
        *ROOT.glob("cs1302_code_visualizer/frontend/js/*.ts"),
        *FIXTURES.glob("*.json"),
        *ROOT.glob("cs1302_code_visualizer/frontend/build/*.js"),
        Path(__file__),
    ]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}

    def capture(frontend, label, **details):
        driver, viz = frontend["driver"], frontend["dataViz"]
        for image_format in ["SVG", "PNG"]:
            payload = browser_driver._capture_viz(
                driver, viz, dpi=1, format=image_format, visualizer="pytutor", session=session
            )
            (out / f"{label}.{image_format.lower()}").write_bytes(payload)
        observed = driver.execute_script(OBSERVE)
        if observed["plan"] and not observed["plan"]["baselineValid"]:
            raise AssertionError(f"Invalid baseline: {label}: {observed}")
        observed.update(name=label, **details)
        results.append(observed)
        print(f"Captured {label}", flush=True)
        return observed

    cases = [
        ("small-aliases", "light", "default", "horizontal"),
        ("small-aliases", "dark", "default", "horizontal"),
        ("aliases", "light", "default", "horizontal"),
        ("dense-aliases", "light", "default", "horizontal"),
        ("aliases", "dark", "default", "horizontal"),
        ("dense-aliases", "dark", "default", "horizontal"),
        ("structures", "light", "compact", "vertical"),
        ("structures", "dark", "inline", "horizontal"),
    ]
    with RenderingSession(max_browsers=1) as session:
        for name, theme, style, orientation in cases:
            for policy in ["historical", "independent", "shared"]:
                with browser_driver.online_python_tutor_frontend(
                    trace=(FIXTURES / f"{name}.json").read_text(),
                    include_types=False,
                    text_memory_labels=False,
                    theme=theme,
                    string_style=style,
                    array_orientation=orientation,
                    session=session,
                ) as frontend:
                    frontend["driver"].execute_script(
                        "window.optFrontend.dataViz.jsPlumbInstance.setReferenceRoutingPolicy(arguments[0])",
                        policy,
                    )
                    capture(frontend, f"{name}-{theme}-{style}-{policy}", theme=theme)

        for name, narrow, emphasis in [
            ("dense-aliases", False, True),
            ("small-aliases", True, False),
            ("cycle-long-labels", True, False),
        ]:
            with browser_driver.online_python_tutor_frontend(
                trace=(FIXTURES / f"{name}.json").read_text(),
                include_types=False,
                text_memory_labels=False,
                session=session,
            ) as frontend:
                driver = frontend["driver"]
                if narrow:
                    driver.execute_cdp_cmd(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": 360,
                            "height": 800,
                            "deviceScaleFactor": 1,
                            "mobile": False,
                        },
                    )
                    driver.execute_script("""
                    document.getElementById('visualizerDiv').style.width='340px';
                    window.optFrontend.redrawConnectors();
                    """)
                driver.execute_script(
                    "window.optFrontend.dataViz.jsPlumbInstance.setReferenceRoutingPolicy('shared')"
                )
                if emphasis:
                    driver.execute_script("""
                    const m=window.optFrontend.dataViz.jsPlumbInstance;m.beginBatch();
                    for(const c of m.connections)c.setHoverPaintStyle({lineWidth:3,strokeStyle:'#a11b43'});
                    m.endBatch();const c=m.connections.find(c=>c.groupElement.dataset.sharedReference);
                    if(!c)throw Error('No shared member');c.setHover(true);
                    """)
                label = f"{name}-{'narrow' if narrow else 'emphasized'}"
                capture(frontend, label, narrow=narrow, emphasis=emphasis)
                if emphasis:
                    driver.get((out / f"{label}.svg").as_uri())
                    driver.execute_async_script(
                        "const done=arguments[arguments.length-1];document.fonts.ready.then(()=>done())"
                    )
                    if driver.execute_script("return document.documentElement.localName") != "svg":
                        raise AssertionError("Standalone SVG failed to reopen")
                    driver.save_screenshot(str(out / f"{label}-reopened.png"))

        trace = json.loads((FIXTURES / "dense-aliases.json").read_text())
        initial = trace["trace"][0]
        initial["heap"]["2"] = ["INSTANCE", "Node", ["value", 42]]
        assigned = deepcopy(initial)
        assigned["stack_to_render"][0]["encoded_locals"]["alias0"] = ["REF", 2]
        mutated = deepcopy(assigned)
        mutated["heap"]["2"][2][1] = 99
        trace["trace"] = [initial, assigned, mutated]
        signatures = []
        with browser_driver.online_python_tutor_frontend(
            trace=json.dumps(trace),
            include_types=False,
            text_memory_labels=False,
            session=session,
        ) as frontend:
            for index, label in [
                (0, "initial"),
                (1, "reassigned"),
                (2, "mutated"),
                (0, "restored"),
            ]:
                frontend["driver"].execute_script(
                    """
                const v=window.optFrontend;v.curInstr=arguments[0];v.updateOutput();
                v.dataViz.jsPlumbInstance.setReferenceRoutingPolicy('shared');v.redrawConnectors();
                """,
                    index,
                )
                observed = capture(frontend, f"transition-{label}")
                if index == 0 and not observed["plan"]["groups"]:
                    raise AssertionError("Expected positive sharing in initial/restored state")
                svg = ET.parse(out / f"transition-{label}.svg")
                ns = {"s": "http://www.w3.org/2000/svg"}
                description = svg.find("s:desc", ns).text or ""
                if f"alias0: reference to object {1 if index == 0 else 2}" not in description:
                    raise AssertionError("Reassigned reference description is incorrect")
                if index == 2 and "value: 99" not in description:
                    raise AssertionError("Mutated value is missing")
                signatures.append((
                    [p.attrib["d"] for p in svg.findall(".//s:path", ns)],
                    [p.attrib["points"] for p in svg.findall(".//s:polygon", ns)],
                ))
        if signatures[0] != signatures[3]:
            raise AssertionError("Restored physical paint differs from initial state")

    by_name = {result["name"]: result for result in results}
    for scene in ["small-aliases", "dense-aliases"]:
        for theme in ["light", "dark"]:
            baseline = by_name[f"{scene}-{theme}-default-independent"]
            shared = by_name[f"{scene}-{theme}-default-shared"]
            if not (
                shared["heads"] < baseline["heads"]
                and shared["paintedLength"] < baseline["paintedLength"]
                and shared["sources"] == baseline["sources"]
            ):
                raise AssertionError(f"Expected fewer heads and less shaft paint: {scene}/{theme}")

    if source_hashes != {str(p.relative_to(ROOT)): sha(p) for p in source_paths}:
        raise AssertionError("Source or assets changed during capture; regenerate the package")
    manifest = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "workingTreeChanges": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ),
        "hardware": platform.platform(),
        "results": results,
        "sourceSha256": source_hashes,
        "exportSha256": {
            p.name: sha(p) for p in sorted(out.glob("*.svg")) + sorted(out.glob("*.png"))
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    figures = []
    for r in results:
        name = r["name"]
        encoded = base64.b64encode((out / f"{name}.png").read_bytes()).decode()
        figures.append(
            f"<figure><figcaption>{html.escape(name)} — {r['sources']} sources, "
            f'{r["heads"]} heads</figcaption><div class="scroll"><img '
            f'alt="{html.escape(name)}" src="data:image/png;base64,{encoded}"></div>'
            f'<a href="{name}.svg">Native SVG</a> · <a href="{name}.png">Native PNG</a></figure>'
        )
    page = """<!doctype html><meta charset="utf-8"><title>Shared reference review</title>
<style>body{font:16px system-ui;margin:24px;color:#222;background:#fafafa}button{margin:4px;padding:8px}
figure{margin:24px 0;padding:16px;background:white;border:1px solid #aaa}.scroll{overflow:auto}
img{display:block;max-width:none}.half img{zoom:.5}.mono img{filter:grayscale(1)}
figcaption{margin-bottom:12px}a{display:inline-block;margin-top:12px}</style>
<h1>Shared reference review</h1><p>Compare controlled independent/shared output for small and dense aliases.
Historical output is contextual; it is not the validated baseline for optional sharing.</p>
<p>Trace named sources; identify aliases; count source locations and objects separately; distinguish
joins from crossings; explain reassignment versus mutation. Inspect themes, native/half-size,
monochrome, narrow inputs and emphasis. Half-size labels may need zoom; long narrow diagrams
retain content by exporting beyond their input container. Record approval or specific objections
in issue #27. This package does not record maintainer approval.</p>
<button onclick="document.body.classList.toggle('half')">Native / 50%</button>
<button onclick="document.body.classList.toggle('mono')">Color / monochrome</button>
<p><a href="manifest.json">Source and export provenance</a></p>
""" + "\n".join(figures)
    (out / "index.html").write_text(page)
    print(f"Review package: {out / 'index.html'} ({len(results)} native SVG/PNG pairs)")


if __name__ == "__main__":
    main()
