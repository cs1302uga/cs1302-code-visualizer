"""Real-browser checks for string geometry, identities, and export contracts."""

import json
from pathlib import Path

import pytest

from cs1302_code_visualizer import browser_driver

FIXTURE = Path(__file__).resolve().parents[1] / "docs/string-style/fixtures/lists.json"
TRACE = json.dumps(json.loads(FIXTURE.read_text())["10"])


@pytest.mark.parametrize("style", ["compact", "default", "inline"])
@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_string_styles_geometry_and_exports(style, orientation, theme, rendering_session):
    with browser_driver.online_python_tutor_frontend(
        TRACE,
        string_style=style,
        array_orientation=orientation,
        theme=theme,
        text_memory_labels=False,
        session=rendering_session,
    ) as frontend:
        driver = frontend["driver"]
        driver.execute_async_script(
            "const done=arguments[arguments.length-1]; document.fonts.ready.then(()=>{"
            "window.optFrontend.redrawConnectors(); done(); });"
        )
        result = driver.execute_script("""
            const root=document.querySelector('.ExecutionVisualizer');
            const boxes=[...root.querySelectorAll('.value-box')];
            const manager=window.optFrontend.dataViz.jsPlumbInstance;
            return {
              heights: boxes.map(b=>b.getBoundingClientRect().height),
              widths: [...root.querySelectorAll('table')].map(t=>
                [...t.querySelectorAll('.value-box')].filter(b=>b.closest('table')===t)
                .map(b=>b.getBoundingClientRect().width)),
              pairs: root.querySelectorAll('.compact-string').length,
              strings: [...root.querySelectorAll('.heapObject > .typeLabel')]
                .filter(e=>/^String@/.test(e.textContent)).length,
              connections: manager.connections.map(c=>{
                const b=c.source[0].closest('.value-box').getBoundingClientRect();
                const o=manager.container.getBoundingClientRect();
                const tip=c.arrowElement.getAttribute('points').split(' ').map(p=>p.split(',').map(Number));
                const target=c.target[0].closest('.heapObject');
                const owner=c.source[0].closest('.heapObject');
                const path=c.pathElement;
                const end=path.getPointAtLength(path.getTotalLength());
                const rear=[(tip[1][0]+tip[2][0])/2,(tip[1][1]+tip[2][1])/2];
                const head=[tip[0][0]-rear[0],tip[0][1]-rear[1]];
                const base=[tip[1][0]-tip[2][0],tip[1][1]-tip[2][1]];
                const texts=[];
                const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
                const range=document.createRange();
                while(walker.nextNode()) {
                  const node=walker.currentNode;
                  if(!node.textContent.trim() || node.parentElement.closest('svg,script,style')) continue;
                  if(getComputedStyle(node.parentElement).visibility!=='visible') continue;
                  range.selectNodeContents(node);
                  for(const r of range.getClientRects()) if(r.width && r.height) texts.push(r);
                }
                const stroke=Number(path.getAttribute('stroke-width'))/2;
                const source=[Number(c.dotElement.getAttribute('cx'))+o.left,
                  Number(c.dotElement.getAttribute('cy'))+o.top];
                let textHit=false,leftExit=false,reentry=false,departed=false;
                const length=path.getTotalLength();
                for(let t=0;t<=length;t+=.5) {
                  const p=path.getPointAtLength(t),x=p.x+o.left,y=p.y+o.top;
                  if(texts.some(r=>x>r.left-1-stroke && x<r.right+1+stroke &&
                    y>r.top-1-stroke && y<r.bottom+1+stroke)) textHit=true;
                  const inside=x>b.left && x<b.right && y>b.top && y<b.bottom;
                  if(departed && inside) reentry=true;
                  if(!departed && !inside) {
                    leftExit=x<=b.left && y>b.top && y<b.bottom;
                    departed=true;
                  }
                }
                const hb=c.arrowElement.getBoundingClientRect();
                const endpointHit=texts.some(r=> {
                  const x=Math.max(r.left-1,Math.min(source[0],r.right+1));
                  const y=Math.max(r.top-1,Math.min(source[1],r.bottom+1));
                  return Math.hypot(source[0]-x,source[1]-y)<3 ||
                    (hb.right>r.left-1 && hb.left<r.right+1 && hb.bottom>r.top-1 && hb.top<r.bottom+1);
                });
                return {dot:Math.abs(source[0]-(b.right-8)),
                  height:Math.abs(source[1]-(b.top+b.height/2)),
                  triangle:tip.length===3 && Math.abs(Math.hypot(...head)-6)<.1 &&
                    Math.abs(Math.hypot(...base)-6)<.1 && Math.abs(head[0]*base[0]+head[1]*base[1])<.1,
                  shaftEnd:Math.hypot(end.x-rear[0],end.y-rear[1])<.1,
                  leftExit,reentry,departed,textHit,endpointHit,
                  width:path.getAttribute('stroke-width'),
                  returning:!!owner && !!target &&
                    target.getBoundingClientRect().left<=owner.getBoundingClientRect().left};
              })
            };
        """)
        assert result["heights"] and all(abs(h - 19) < 0.1 for h in result["heights"])
        assert all(len(set(widths)) <= 1 for widths in result["widths"])
        assert (result["pairs"] > 0) == (style == "compact")
        assert (result["strings"] > 0) == (style == "default")
        assert any(connection["returning"] for connection in result["connections"])
        for connection in result["connections"]:
            assert connection["dot"] < 0.1 and connection["height"] < 0.1
            assert connection["triangle"] and connection["shaftEnd"]
            assert connection["departed"] and not connection["leftExit"]
            assert not connection["reentry"]
            assert connection["width"] == "1"
            assert not connection["textHit"] and not connection["endpointHit"]
        svg = browser_driver._capture_viz(
            driver,
            frontend["dataViz"],
            format="SVG",
            dpi=1,
            visualizer="pytutor",
            session=rendering_session,
        )
        assert b"Node@" in svg and b"<polygon" in svg
        if style == "compact":
            assert b"Milk" in svg and b"reference to object" in svg


@pytest.mark.parametrize("style", ["default", "compact", "inline"])
def test_legacy_strings_report_actionable_error(style, rendering_session):
    trace = json.loads(TRACE)
    trace["trace"][0]["stack_to_render"][0]["encoded_locals"]["shared"] = "Milk"
    if style == "inline":
        assert browser_driver.generate_image(
            json.dumps(trace), string_style=style, session=rendering_session
        ).startswith(b"\x89PNG")
    else:
        with pytest.raises(ValueError, match=r"Regenerate.*inline_strings=False"):
            browser_driver.generate_image(
                json.dumps(trace), string_style=style, session=rendering_session
            )


def test_text_only_strings_and_hover(rendering_session):
    with browser_driver.online_python_tutor_frontend(
        TRACE,
        string_style="compact",
        text_memory_labels=True,
        include_types=False,
        session=rendering_session,
    ) as frontend:
        result = frontend["driver"].execute_script("""
            const root=document.querySelector('.ExecutionVisualizer');
            return {arrows:root.querySelectorAll('.svg-connector-canvas polygon,.compact-string-arrow polygon').length,
                pairs:root.querySelectorAll('.compact-string').length,
                title:root.querySelector('.heapObject > .typeLabel').textContent};
        """)
        assert result["arrows"] == 0 and result["pairs"] > 0
        assert "@" in result["title"]


def test_self_loops_have_distinct_arrivals_and_stable_routes(rendering_session):
    trace = json.loads(TRACE)
    # Give both tail nodes self-loops and keep 115 independently reachable.
    step = trace["trace"][0]
    step["heap"]["103"][3][1] = ["REF", 103]
    step["heap"]["115"][3][1] = ["REF", 115]
    frame = step["stack_to_render"][0]
    frame["encoded_locals"]["tail"] = ["REF", 115]
    frame["ordered_varnames"].append("tail")
    with browser_driver.online_python_tutor_frontend(
        json.dumps(trace),
        string_style="compact",
        text_memory_labels=False,
        session=rendering_session,
    ) as frontend:
        result = frontend["driver"].execute_script("""
            window.optFrontend.redrawConnectors();
            const manager=window.optFrontend.dataViz.jsPlumbInstance;
            const loops=manager.connections.filter(c=>
                c.source[0].closest('.heapObject')===c.target[0].closest('.heapObject'));
            const snapshot=()=>loops.map(c=>({head:c.arrowElement.getAttribute('points'),
                path:c.pathElement.getAttribute('d')}));
            const before=snapshot(); manager.repaintEverything();
            return {loops:before,stable:JSON.stringify(before)===JSON.stringify(snapshot())};
        """)
        assert len(result["loops"]) >= 2
        assert len({item["head"] for item in result["loops"]}) == len(result["loops"])
        assert all(item["path"] and "NaN" not in item["path"] for item in result["loops"])
        assert result["stable"]
