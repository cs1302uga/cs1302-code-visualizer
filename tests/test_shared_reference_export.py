"""Native export acceptance for the internal shared-reference routing policy."""

import io
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, ImageChops

from cs1302_code_visualizer import browser_driver
from cs1302_code_visualizer.browser_driver import generate_image

NS = {"s": "http://www.w3.org/2000/svg"}
FIXTURES = Path("cs1302_code_visualizer/frontend/tests/fixtures/reference-sharing")


@pytest.fixture
def sharing_capture(monkeypatch):
    """Opt in on the real manager without adding a public render option."""
    original_capture = browser_driver._capture_viz
    state = {"policy": "shared", "observations": []}

    def capture(driver, viz, **options):
        driver.execute_script(
            "window.optFrontend.dataViz.jsPlumbInstance.setReferenceRoutingPolicy(arguments[0]);",
            state["policy"],
        )
        if state.get("emphasis"):
            driver.execute_script(
                """
                const m=window.optFrontend.dataViz.jsPlumbInstance;
                m.beginBatch();
                for(const c of m.connections)c.setHoverPaintStyle({lineWidth:3,strokeStyle:'#a11b43'});
                m.endBatch();
                const member=m.connections.find(c=>c.groupElement.dataset.sharedReference);
                if(!member)throw new Error('Expected a real shared member for emphasis acceptance');
                member.setHover(true);
                """
            )
        result = original_capture(driver, viz, **options)
        state["observations"].append(
            driver.execute_script(
                """
                const manager = window.optFrontend.dataViz.jsPlumbInstance;
                const root = document.getElementById('dataViz');
                const visible = element => {
                  for (let node = element; node; node = node.parentElement) {
                    const style = getComputedStyle(node);
                    if (style.display === 'none' || style.visibility === 'hidden' ||
                        Number(style.opacity) === 0) return false;
                  }
                  return true;
                };
                const local = [...root.querySelectorAll('.compact-string-arrow')];
                const canvases = [manager.svgCanvas, ...local];
                const primitives = selector => canvases.flatMap(canvas =>
                  [...canvas.querySelectorAll(selector)].filter(visible));
                return {
                  policy: manager.referenceRoutingPolicy,
                  baselineValid: manager.referenceSharingPlan?.baselineValid ?? null,
                  sources: manager.connections.map(connection => ({
                    source: connection.sourceId, target: connection.targetId,
                    sourceVisible: visible(connection.dotElement)
                  })),
                  paths: primitives('path').map(path => path.getAttribute('d')),
                  heads: primitives('polygon').map(head => head.getAttribute('points')),
                  dots: primitives('circle').length,
                  groups: manager.svgCanvas.querySelectorAll('.shared-reference-group').length
                };
                """
            )
        )
        return result

    monkeypatch.setattr(browser_driver, "_capture_viz", capture)
    return state


@pytest.mark.parametrize(
    "name,theme,string_style,orientation",
    [
        ("aliases", "light", "default", "horizontal"),
        ("small-aliases", "light", "default", "horizontal"),
        ("dense-aliases", "dark", "default", "horizontal"),
        ("structures", "light", "compact", "vertical"),
        ("structures", "dark", "inline", "horizontal"),
    ],
)
def test_native_sharing_exports_keep_all_visible_paint_and_source_descriptions(
    name, theme, string_style, orientation, sharing_capture, rendering_session
):
    trace = (FIXTURES / f"{name}.json").read_text()
    options = {
        "session": rendering_session,
        "theme": theme,
        "string_style": string_style,
        "array_orientation": orientation,
        "include_types": False,
    }
    svg = ET.fromstring(generate_image(trace, format="SVG", **options))
    observed = sharing_capture["observations"][-1]
    assert observed["policy"] == "shared"
    assert observed["baselineValid"] is True
    assert observed["sources"]
    assert all(source["sourceVisible"] for source in observed["sources"])
    assert len({source["source"] for source in observed["sources"]}) == len(observed["sources"])
    if name in {"small-aliases", "dense-aliases"}:
        assert observed["groups"] > 0
        assert len(observed["heads"]) < len(observed["sources"])
    # Compare actual exported paths/heads, not ownership metadata or hidden logical paths.
    assert Counter(path.attrib["d"] for path in svg.findall(".//s:path", NS)) == Counter(
        observed["paths"]
    )
    assert Counter(head.attrib["points"] for head in svg.findall(".//s:polygon", NS)) == Counter(
        observed["heads"]
    )
    assert len(svg.findall(".//s:circle", NS)) == observed["dots"]
    assert not svg.findall(".//s:foreignObject", NS)
    assert not svg.findall(".//s:image", NS)
    description = json.loads(svg.find("s:metadata", NS).text)
    plain = svg.find("s:desc", NS).text
    for section in description["sections"]:
        assert section["heading"] in plain
        assert all(item in plain for item in section["items"])
    object_sections = [
        section
        for section in description["sections"]
        if section["heading"].startswith("Heap object")
    ]
    assert len({section["heading"] for section in object_sections}) == len(object_sections)
    if name == "aliases":
        assert "a: reference to object 1" in plain
        assert "b: reference to object 1" in plain
        assert "c: reference to object 1" in plain
        assert "equalCopy: reference to object 2" in plain
        assert len(object_sections) == 2
    elif name in {"small-aliases", "dense-aliases"}:
        count = 4 if name == "small-aliases" else 12
        assert all(f"alias{index}: reference to object 1" in plain for index in range(count))
        assert len(object_sections) == 1
    else:
        assert "self: reference to object 1" in plain
        assert "Index 1: reference to object 3" in plain
        assert "absent: null" in plain

    png = Image.open(io.BytesIO(generate_image(trace, format="PNG", **options))).convert("RGB")
    assert png.size == (int(svg.attrib["width"]), int(svg.attrib["height"]))
    background = Image.new("RGB", png.size, png.getpixel((0, 0)))
    content = ImageChops.difference(png, background).getbbox()
    assert content is not None
    assert min(content[0], content[1], png.width - content[2], png.height - content[3]) >= 4


def test_sharing_policy_preserves_description_across_baseline_and_reconstruction(
    sharing_capture, rendering_session
):
    trace = (FIXTURES / "aliases.json").read_text()

    def capture_description(policy):
        sharing_capture["policy"] = policy
        data = generate_image(trace, format="SVG", session=rendering_session, include_types=False)
        root = ET.fromstring(data)
        return json.loads(root.find("s:metadata", NS).text), root

    baseline, _ = capture_description("historical")
    shared, first = capture_description("shared")
    reconstructed, second = capture_description("shared")
    assert baseline == shared == reconstructed
    assert first.attrib["viewBox"] == second.attrib["viewBox"]
    assert [node.attrib.get("d") for node in first.findall(".//s:path", NS)] == [
        node.attrib.get("d") for node in second.findall(".//s:path", NS)
    ]


def test_emphasized_shared_export_reopens_with_complete_paint(
    sharing_capture, rendering_session, tmp_path
):
    """A standalone SVG retains private and shared emphasis with padded raster bounds."""
    sharing_capture["emphasis"] = True
    trace = (FIXTURES / "dense-aliases.json").read_text()
    options = {"session": rendering_session, "include_types": False}
    payload = generate_image(trace, format="SVG", **options)
    root = ET.fromstring(payload)
    paths = root.findall(".//s:path", NS)
    emphasis = "rgb(161, 27, 67)"
    emphasized = [p for p in paths if p.attrib.get("stroke") == emphasis]
    assert len(emphasized) >= 2  # Private branch and at least one shared interval.
    assert all(
        float(p.attrib["stroke-width"].removesuffix("px")) == pytest.approx(3) for p in emphasized
    )
    assert any(p.attrib.get("stroke") != emphasis for p in paths)
    assert len(root.findall(".//s:polygon", NS)) < 12
    png = Image.open(io.BytesIO(generate_image(trace, format="PNG", **options))).convert("RGB")
    background = Image.new("RGB", png.size, png.getpixel((0, 0)))
    content = ImageChops.difference(png, background).getbbox()
    assert content is not None
    assert min(content[0], content[1], png.width - content[2], png.height - content[3]) >= 4
    standalone = tmp_path / "emphasized.svg"
    standalone.write_bytes(payload)
    with rendering_session.browser(1, browser_driver.new_webdriver) as driver:
        driver.get(standalone.as_uri())
        driver.execute_async_script(
            "const done=arguments[arguments.length-1];document.fonts.ready.then(()=>done());"
        )
        observed = driver.execute_script(
            """
            const root=document.documentElement,b=root.getBBox();
            return {tag:root.localName,heads:root.querySelectorAll('polygon').length,
              paths:[...root.querySelectorAll('path')].map(p=>p.getAttribute('d')),
              bounds:{x:b.x,y:b.y,width:b.width,height:b.height},description:root.querySelector('desc').textContent};
            """
        )
        assert observed["tag"] == "svg"
        assert observed["heads"] == len(root.findall(".//s:polygon", NS))
        assert observed["paths"] == [p.attrib["d"] for p in paths]
        assert observed["bounds"]["width"] > 0
        assert all(f"alias{i}: reference to object 1" in observed["description"] for i in range(12))
