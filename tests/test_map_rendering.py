"""Native regressions for reference-valued map keys and their exports."""

import json
from pathlib import Path

import pytest

from cs1302_code_visualizer import browser_driver

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "cs1302_code_visualizer/frontend/tests/fixtures/map-keys.json"
)


@pytest.mark.parametrize("style", ["default", "compact", "inline"])
@pytest.mark.parametrize("case", ["one", "multiple", "object", "primitive"])
def test_map_key_attachments(style, case, rendering_session):
    """Keys retain identity and clear text, including aliases and inline literals."""
    trace = json.loads(FIXTURE.read_text())
    step = trace["trace"][0 if case == "one" else 1]
    trace["trace"] = [step]
    mapping = next(obj for obj in step["heap"].values() if obj[0] == "DICT")
    if case == "object":
        for key, _value in mapping[1:]:
            step["heap"][str(key[1])] = ["INSTANCE", "Key", ["number", key[1]]]
            step["heap_attrs"][str(key[1])] = {"type": ["int"]}
    elif case == "primitive":
        for index, entry in enumerate(mapping[1:]):
            entry[0] = index
    with browser_driver.online_python_tutor_frontend(
        json.dumps(trace),
        string_style=style,
        text_memory_labels=False,
        session=rendering_session,
    ) as frontend:
        driver = frontend["driver"]
        result = driver.execute_script("""
            const root=document.querySelector('.ExecutionVisualizer');
            const manager=window.optFrontend.dataViz.jsPlumbInstance;
            const snapshot=()=>manager.connections.map(c=>c.pathElement.getAttribute('d'));
            window.optFrontend.redrawConnectors();
            const before=snapshot(); window.optFrontend.redrawConnectors();
            const origin=manager.container.getBoundingClientRect();
            const texts=[], range=document.createRange();
            const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
            while(walker.nextNode()) {
                const n=walker.currentNode;
                if(!n.textContent.trim()||n.parentElement.closest('svg,script,style'))continue;
                range.selectNodeContents(n);
                texts.push(...[...range.getClientRects()].filter(r=>r.width&&r.height));
            }
            const hit=(x,y,pad)=>texts.some(r=>x>r.left-pad&&x<r.right+pad&&y>r.top-pad&&y<r.bottom+pad);
            const errors=[];
            for(const c of manager.connections) {
                const box=c.source[0].closest('.value-box');
                if(!box){errors.push('missing value box');continue;}
                const b=box.getBoundingClientRect(),path=c.pathElement;
                const x=Number(c.dotElement.getAttribute('cx'))+origin.left;
                const y=Number(c.dotElement.getAttribute('cy'))+origin.top;
                if(Math.abs(x-(b.right-8))>.1)errors.push('dot attachment');
                if(texts.some(r=>Math.hypot(x-Math.max(r.left-1,Math.min(x,r.right+1)),
                    y-Math.max(r.top-1,Math.min(y,r.bottom+1)))<3))errors.push('dot text');
                let departed=false;
                for(let d=0;d<=path.getTotalLength();d+=.5){
                    const p=path.getPointAtLength(d),px=p.x+origin.left,py=p.y+origin.top;
                    if(hit(px,py,1.5))errors.push('shaft text');
                    const inside=px>b.left-.5&&px<b.right+.5&&py>b.top-.5&&py<b.bottom+.5;
                    if(departed&&inside)errors.push('source reentry');
                    if(!departed&&!inside){if(px<b.left-.5)errors.push('left exit');departed=true;}
                }
                if(!departed)errors.push('no departure');
                const h=c.arrowElement.getBoundingClientRect();
                if(texts.some(r=>h.right>r.left-1&&h.left<r.right+1&&h.bottom>r.top-1&&h.top<r.bottom+1))errors.push('head text');
                const key=c.source[0].closest('.dictKey');
                if(key&&key.dataset.referenceTarget!==c.target[0].dataset.objectId)errors.push('wrong target');
            }
            const keys=[...root.querySelectorAll('.dictKey')];
            return {errors:[...new Set(errors)],stable:JSON.stringify(before)===JSON.stringify(snapshot()),
                keys:keys.length,boxes:keys.filter(k=>k.querySelector('.value-box')).length,
                compact:keys.filter(k=>k.querySelector('.compact-string')).map(k=>{
                    const box=k.querySelector('.value-box').getBoundingClientRect();
                    const dot=k.querySelector('circle').getBoundingClientRect();
                    const label=k.querySelector('.stringObj').getBoundingClientRect();
                    return Math.abs(dot.left+dot.width/2-(box.right-8))<.1&&label.left>box.right;
                })};
        """)
        assert result["errors"] == []
        assert result["stable"]
        assert result["keys"] == (1 if case == "one" else 2)
        boxed = case == "object" or (case != "primitive" and style != "inline")
        assert result["boxes"] == (result["keys"] if boxed else 0)
        assert all(result["compact"])
        bounds = browser_driver._export_bounds(driver, frontend["dataViz"])
        paint = driver.execute_script("""
            return [...document.querySelectorAll('.svg-connector-canvas g,.compact-string-arrow')]
                .map(e=>e.getBoundingClientRect().toJSON()).filter(r=>r.width&&r.height);
        """)
        for rect in paint:
            assert rect["left"] >= bounds["left"] and rect["right"] <= bounds["right"]
            assert rect["top"] >= bounds["top"] and rect["bottom"] <= bounds["bottom"]
        for image_format in ["SVG", "PNG"]:
            image = browser_driver._capture_viz(
                driver,
                frontend["dataViz"],
                format=image_format,
                dpi=1,
                visualizer="pytutor",
                session=rendering_session,
            )
            assert b"<svg" in image if image_format == "SVG" else image.startswith(b"\x89PNG")
