"""Behavioral contracts for standalone SVG exports."""

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from cs1302_code_visualizer import browser_driver
from cs1302_code_visualizer.browser_driver import generate_image, generate_step_images

NS = {"s": "http://www.w3.org/2000/svg"}
TRACE = Path("small-trace-examples/example0/Driver.java.json").read_text()


def test_svg_is_standalone_editable_and_scales_without_relayout(rendering_session):
    first = ET.fromstring(generate_image(TRACE, format="svg", session=rendering_session))
    scaled = ET.fromstring(generate_image(TRACE, format="SVG", dpi=2, session=rendering_session))
    assert first.tag == f"{{{NS['s']}}}svg"
    assert first.findall(".//s:text", NS)
    assert first.findall(".//s:path", NS)
    assert not first.findall(".//s:image", NS)
    assert not first.findall(".//s:foreignObject", NS)
    assert first.attrib["viewBox"] == scaled.attrib["viewBox"]
    for dimension in ("width", "height"):
        assert int(scaled.attrib[dimension]) == 2 * int(first.attrib[dimension])
    assert [ET.tostring(child) for child in first] == [ET.tostring(child) for child in scaled]
    png = generate_image(TRACE, session=rendering_session)
    assert Image.open(io.BytesIO(png)).size == (
        int(first.attrib["width"]),
        int(first.attrib["height"]),
    )


def test_svg_steps_do_not_accumulate_previous_frames(rendering_session):
    payload = browser_driver.resolve_trace_payload(TRACE)
    payload["trace"] = payload["trace"][-2:]
    trace = json.dumps(payload)
    frames = generate_step_images(trace, format="SVG", session=rendering_session)
    assert len(frames) == len(payload["trace"])
    final = generate_image(trace, format="SVG", session=rendering_session)
    assert ET.tostring(ET.fromstring(frames[-1])) == ET.tostring(ET.fromstring(final))


def test_svg_json_text_is_escaped_and_remains_text(rendering_session):
    trace = json.dumps({"label": '<script>& "café Ω 😀 e\u0301 👩‍💻"'}, ensure_ascii=False)
    result = generate_image(trace, format="SVG", visualizer="json-pre", session=rendering_session)
    svg = ET.fromstring(result)
    text = "".join(svg.itertext())
    assert "<script>" in text
    assert "café Ω 😀" in text
    assert "e\u0301 👩‍💻" in text
    assert not svg.findall(".//s:script", NS)
    assert b"&lt;script&gt;" in result


def test_svg_fresh_browser_matches_pooled_geometry(rendering_session):
    fresh = ET.fromstring(generate_image(TRACE, format="SVG"))
    pooled = ET.fromstring(generate_image(TRACE, format="SVG", session=rendering_session))
    assert fresh.attrib["viewBox"] == pooled.attrib["viewBox"]
    assert list(fresh.itertext()) == list(pooled.itertext())


def test_svg_frontend_error_propagates_without_raster_fallback():
    driver = MagicMock()
    driver.execute_async_script.return_value = {"error": "Cannot export an empty diagram"}
    viz = MagicMock()
    viz.location = {"x": 0, "y": 0}
    viz.size = {"width": 20, "height": 10}
    with (
        patch.object(browser_driver, "_fit_session_viewport"),
        pytest.raises(ValueError, match="SVG export failed: Cannot export an empty diagram"),
    ):
        browser_driver._capture_viz(
            driver, viz, dpi=1, format="SVG", visualizer="pytutor", session=MagicMock()
        )
    driver.get_screenshot_as_png.assert_not_called()


def test_svg_invalid_scale_fails(rendering_session):
    with pytest.raises(ValueError, match="SVG scale must be positive"):
        generate_image(TRACE, format="SVG", dpi=0, session=rendering_session)


def test_svg_exposes_summary_and_complete_nonrecursive_description(rendering_session):
    svg = ET.fromstring(generate_image(TRACE, format="SVG", session=rendering_session))
    title = svg.find("s:title", NS)
    desc = svg.find("s:desc", NS)
    metadata = svg.find("s:metadata", NS)
    assert svg.attrib["aria-labelledby"] == title.attrib["id"]
    assert svg.attrib["aria-describedby"] == desc.attrib["id"]
    structured = json.loads(metadata.text)
    assert title.text == structured["summary"]
    assert structured["sections"][0]["heading"].startswith("Stack frame:")
    assert "reference to object" in desc.text
    assert '"Alice"' in desc.text
    for section in structured["sections"]:
        assert section["heading"] in desc.text
        assert all(item in desc.text for item in section["items"])
