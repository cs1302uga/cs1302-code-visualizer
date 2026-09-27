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
                const enclosure=c.source[0].closest('.instTbl,.listTbl,.stackFrame').getBoundingClientRect();
                const path=c.pathElement.getAttribute('d');
                return {dot:Math.abs(Number(c.dotElement.getAttribute('cx'))-(b.right-o.left-8)),
                  height:Math.abs(Number(c.dotElement.getAttribute('cy'))-(b.top+b.height/2-o.top)),
                  triangle:tip.length===3 && Math.abs(tip[0][0]-tip[1][0])===6 && Math.abs(tip[1][1]-tip[2][1])===6,
                  exit:Number(path.split(' H ')[1].split(' ')[0]),
                  expectedExit:Math.max(b.right-o.left-8,enclosure.right-o.left-4),
                  shaftEnd:path.endsWith(`${tip[0][0]-6} ${tip[0][1]}`) || path.endsWith(`H ${tip[0][0]-6}`),
                  width:c.pathElement.getAttribute('stroke-width'),
                  crossesObject: c.pathElement.dataset.returnLane !== undefined &&
                    [...root.querySelectorAll('.heapObject')].filter(e=>
                      e!==c.source[0].closest('.heapObject') && e!==c.target[0].closest('.heapObject'))
                    .some(e=>{
                      const r=e.getBoundingClientRect();
                      const length=c.pathElement.getTotalLength();
                      for(let t=0;t<length;t+=1) {
                        const p=c.pathElement.getPointAtLength(t), x=p.x+o.left, y=p.y+o.top;
                        if(x>r.left && x<r.right && y>r.top && y<r.bottom) return true;
                      }
                      return false;
                    })};
              }),
              returns:root.querySelectorAll('[data-return-lane]').length
            };
        """)
        assert result["heights"] and all(abs(h - 19) < 0.1 for h in result["heights"])
        assert all(len(set(widths)) <= 1 for widths in result["widths"])
        assert (result["pairs"] > 0) == (style == "compact")
        assert (result["strings"] > 0) == (style == "default")
        assert result["returns"] >= 1
        for connection in result["connections"]:
            assert connection["dot"] < 0.1 and connection["height"] < 0.1
            assert connection["triangle"] and connection["shaftEnd"]
            assert abs(connection["exit"] - connection["expectedExit"]) < 0.1
            assert connection["width"] == "1"
            assert not connection["crossesObject"]
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


def test_self_loop_and_multiple_return_lanes(rendering_session):
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
            return manager.connections.filter(c=>c.pathElement.dataset.returnLane!==undefined)
                .map(c=>({lane:c.pathElement.dataset.returnLane,path:c.pathElement.getAttribute('d')}));
        """)
        assert len(result) >= 2
        assert len({item["lane"] for item in result}) == len(result)
        assert all(" Q " in item["path"] and "NaN" not in item["path"] for item in result)
