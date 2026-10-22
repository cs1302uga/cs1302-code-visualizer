"""Native and public-navigation contracts for frame insertion and restoration."""

import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

from cs1302_code_visualizer import browser_driver

FIXTURE = Path(__file__).parent / "fixtures/layout-coordinator-frames.json"
NS = {"s": "http://www.w3.org/2000/svg"}
FRAME_ORDER = [
    ["main:6"],
    ["helper1:6", "main:6"],
    ["helper2:6", "helper1:6", "main:6"],
    ["main:6"],
]


def test_native_frame_transitions_preserve_heap_and_restore_pixels(rendering_session):
    trace = FIXTURE.read_text()
    states = json.loads(trace)["trace"]
    assert [len(state["stack_to_render"]) for state in states] == [1, 2, 3, 1]
    assert all(state["heap"] == states[0]["heap"] for state in states)
    assert all(state["heap_attrs"] == states[0]["heap_attrs"] for state in states)
    pngs = browser_driver.generate_step_images(trace, session=rendering_session)
    svgs = [
        ET.fromstring(data)
        for data in browser_driver.generate_step_images(
            trace, format="SVG", session=rendering_session
        )
    ]
    assert len(pngs) == len(svgs) == 4
    heap_sections = []
    for png, svg, expected_order in zip(pngs, svgs, FRAME_ORDER, strict=True):
        metadata = svg.find("s:metadata", NS)
        assert metadata is not None and metadata.text
        sections = json.loads(metadata.text)["sections"]
        assert [
            section["heading"].removeprefix("Stack frame: ")
            for section in sections
            if section["heading"].startswith("Stack frame: ")
        ] == expected_order
        heap = [section for section in sections if section["heading"].startswith("Heap object ")]
        assert sorted(section["heading"].split()[2].removesuffix(":") for section in heap) == [
            "70",
            "71",
            "96",
            "97",
        ]
        heap_sections.append(heap)
        with Image.open(io.BytesIO(png)) as image:
            assert image.size == (int(svg.attrib["width"]), int(svg.attrib["height"]))
    assert all(heap == heap_sections[0] for heap in heap_sections)
    assert any("Hello" in item for section in heap_sections[0] for item in section["items"])
    assert any("World" in item for section in heap_sections[0] for item in section["items"])
    first, restored = (Image.open(io.BytesIO(pngs[index])).convert("RGBA") for index in (0, 3))
    assert first.size == restored.size
    assert first.tobytes() == restored.tobytes()
    routes = [[node.attrib for node in svg.findall(".//s:path", NS)] for svg in svgs]
    assert routes[0] and routes[0] == routes[3]
    final = ET.fromstring(
        browser_driver.generate_image(trace, format="SVG", session=rendering_session)
    )
    final_metadata = final.find("s:metadata", NS)
    restored_metadata = svgs[3].find("s:metadata", NS)
    assert final_metadata is not None and restored_metadata is not None
    assert final_metadata.text == restored_metadata.text
    assert "helper" not in "".join(final.itertext())


# Read only rendered DOM and the same connector paint used by the existing native
# frame-parent test. IDs for transient endpoints are not invocation identities.
SCENE = """
    const v=window.optFrontend, root=v.domRoot[0], origin=root.querySelector('#dataViz').getBoundingClientRect();
    const relative=e=>{const r=e.getBoundingClientRect();return [r.left-origin.left,r.top-origin.top,r.width,r.height].map(n=>Math.round(n*1000)/1000);};
    const frames=[...root.querySelectorAll('#stack > .stackFrame[data-frame_id]')];
    const objects=[...root.querySelectorAll('.heapObject[data-object-id]')];
    const visible=e=>{for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0)return false;}return true;};
    const routes=v.dataViz.jsPlumbInstance.connections.map(c=>({
        source:[c.source[0].closest('.stackFrame')?.getAttribute('data-frame_id')??null,
            c.source[0].closest('[data-object-id]')?.getAttribute('data-object-id')??null,
            c.source[0].closest('tr')?.querySelector('.stackVarName,.instKey')?.textContent.trim()??null],
        target:c.target[0].closest('[data-object-id]')?.getAttribute('data-object-id'),
        frame:c.source[0].closest('.stackFrame')?.getAttribute('data-frame_id')??null,
        path:c.pathElement.getAttribute('d'),
        dot:[c.dotElement.getAttribute('cx'),c.dotElement.getAttribute('cy')],
        head:c.arrowElement.getAttribute('points'),
        stroke:c.pathElement.getAttribute('stroke'),
        connected:c.source[0].isConnected&&c.target[0].isConnected&&c.pathElement.isConnected,
        visible:visible(c.groupElement),
        validLength:Number.isFinite(c.pathElement.getTotalLength())&&c.pathElement.getTotalLength()>0,
        finitePaint:!/(?:NaN|Infinity)/.test([c.pathElement.getAttribute('d'),c.arrowElement.getAttribute('points'),c.dotElement.getAttribute('cx'),c.dotElement.getAttribute('cy')].join(' ')),
    })).sort((a,b)=>JSON.stringify(a.source).localeCompare(JSON.stringify(b.source)));
    return {
        step:v.curInstr,
        frames:frames.map(e=>({id:e.getAttribute('data-frame_id'),name:e.querySelector('.stackFrameHeader').textContent.trim(),rect:relative(e)})),
        uniqueFrameIds:new Set(frames.map(e=>e.id)).size===frames.length,
        heap:objects.map(e=>({id:e.getAttribute('data-object-id'),text:e.textContent,rect:relative(e)})).sort((a,b)=>a.id.localeCompare(b.id)),
        routes,
        visibleGroups:[...root.querySelectorAll('svg.svg-connector-canvas > g._svg_connector')].filter(visible).length,
        references:[...root.querySelectorAll('#stack [data-reference-target]')].map(e=>e.getAttribute('data-reference-target')).sort(),
    };
"""


def test_navigation_settles_like_direct_initial_seek_without_retained_frames():
    trace = FIXTURE.read_text()
    # Raw WebDriver changes own a fresh browser, as required by CONTRIBUTING.
    with browser_driver.online_python_tutor_frontend(trace, text_memory_labels=False) as frontend:
        driver = frontend["driver"]
        presentation_style = driver.execute_script(
            "return window.optFrontend.domRoot[0].style.cssText;"
        )

        def fresh(step):
            driver.execute_script(
                """
                const old=window.optFrontend, Constructor=old.constructor;
                const root=document.createElement('div');root.id='coordinator-navigation';
                // Every cold seek gets the same presentation input, rather
                // than copying repairs from whichever state was visited last.
                root.style.cssText=arguments[2];
                old.domRoot[0].replaceWith(root);
                window.optFrontend=new Constructor(root.id,arguments[0],{
                    ...old.params,jumpToEnd:false,startingInstruction:arguments[1]
                });
                """,
                json.loads(trace),
                step,
                presentation_style,
            )
            driver.execute_script("window.optFrontend.renderStep(arguments[0]);", step)
            return settled()

        def settled():
            # Observe ordinary navigation before an export helper can repair it.
            # Font/animation-frame readiness is a passive barrier: it never
            # invokes redrawConnectors or another coordinator transaction.
            driver.execute_async_script(
                "const done=arguments[arguments.length-1];document.fonts.ready.then("
                "()=>requestAnimationFrame(()=>requestAnimationFrame(done)));"
            )
            return driver.execute_script(SCENE)

        direct = [fresh(step) for step in range(4)]
        fresh(0)
        forward = [settled()]
        for _ in range(3):
            assert driver.execute_script("return window.optFrontend.stepForward();")
            forward.append(settled())
        backward = []
        for _ in range(3):
            assert driver.execute_script("return window.optFrontend.stepBack();")
            backward.append(settled())
        assert forward == direct
        assert backward == list(reversed(direct[:-1]))
        # Arbitrary indexed seeks must have the same result as fresh initial
        # selection, even after a larger and a smaller state were visited.
        for step in (2, 0, 1, 3, 2, 1, 0):
            driver.execute_script("window.optFrontend.renderStep(arguments[0]);", step)
            assert settled() == direct[step]
        for index, scene in enumerate(direct):
            assert scene["step"] == index
            assert scene["uniqueFrameIds"]
            assert [frame["name"] for frame in scene["frames"]] == FRAME_ORDER[index]
            assert [frame["id"] for frame in scene["frames"]] == [
                ["0"],
                ["1", "0"],
                ["2", "1", "0"],
                ["0"],
            ][index]
            assert [obj["id"] for obj in scene["heap"]] == ["70", "71", "96", "97"]
            assert len(scene["routes"]) == [5, 6, 7, 5][index]
            assert scene["visibleGroups"] == len(scene["routes"])
            assert all(
                route["connected"]
                and route["visible"]
                and route["validLength"]
                and route["finitePaint"]
                for route in scene["routes"]
            )
            assert sorted(route["target"] for route in scene["routes"]) == [
                "70",
                *("71" for _ in range(len(FRAME_ORDER[index]))),
                "71",
                "96",
                "97",
            ]
            expected_edges = {
                ("0", None, "70"),
                ("0", None, "71"),
                (None, "70", "96"),
                (None, "70", "71"),
                (None, "71", "97"),
                *((str(frame), None, "71") for frame in range(1, len(FRAME_ORDER[index]))),
            }
            assert {
                (route["source"][0], route["source"][1], route["target"])
                for route in scene["routes"]
            } == expected_edges
            assert scene["references"] == ["70", *("71" for _ in range(len(FRAME_ORDER[index])))]
            # Frame insertion may move heap geometry. Identity, rendered values,
            # and object count must remain stable throughout the transition.
            assert [(obj["id"], obj["text"]) for obj in scene["heap"]] == [
                (obj["id"], obj["text"]) for obj in direct[0]["heap"]
            ]
        assert {key: value for key, value in direct[0].items() if key != "step"} == {
            key: value for key, value in direct[3].items() if key != "step"
        }
