"""Real-browser contracts for tight content crops and stable step framing."""

import copy
import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, ImageChops

from cs1302_code_visualizer.browser_driver import (
    generate_image,
    generate_step_images,
    resolve_trace_payload,
)

NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture
def changing_trace():
    payload = resolve_trace_payload(
        Path("small-trace-examples/example0/Driver.java.json").read_text()
    )
    small = copy.deepcopy(payload["trace"][0])
    large = copy.deepcopy(small)
    frame = large["stack_to_render"][0]
    frame["encoded_locals"]["wideArray"] = ["REF", 100]
    frame["ordered_varnames"].append("wideArray")
    frame["locals_attrs"]["wideArray"] = {"type": "int[]"}
    large["heap"]["100"] = ["LIST", *range(40)]
    large["heap_attrs"]["100"] = {"type": "int[]"}
    large["heap"]["68"][2][1] = "A long label with accents café Ω and emoji 😀"
    payload["trace"] = [small, large, copy.deepcopy(small)]
    return json.dumps(payload)


def image_size(data):
    return Image.open(io.BytesIO(data)).size


@pytest.mark.parametrize(
    "theme,dpi,orientation", [("light", 1, "horizontal"), ("dark", 2, "vertical")]
)
def test_sequence_has_fixed_bounds_and_preserves_each_state(
    changing_trace, rendering_session, theme, dpi, orientation
):
    options = {
        "theme": theme,
        "dpi": dpi,
        "array_orientation": orientation,
        "session": rendering_session,
    }
    pngs = generate_step_images(changing_trace, **options)
    svgs = [
        ET.fromstring(data)
        for data in generate_step_images(changing_trace, format="SVG", **options)
    ]
    assert len(pngs) == len(svgs) == 3
    assert len({image_size(data) for data in pngs}) == 1
    assert len({svg.attrib["viewBox"] for svg in svgs}) == 1
    assert all(
        image_size(data) == (int(svg.attrib["width"]), int(svg.attrib["height"]))
        for data, svg in zip(pngs, svgs)
    )
    # Revisiting a state does not retain content from the larger middle frame.
    first, last = (Image.open(io.BytesIO(pngs[i])) for i in (0, 2))
    assert ImageChops.difference(first, last).getbbox() is None
    assert "wideArray" in "".join(svgs[1].itertext())
    assert "wideArray" not in "".join(svgs[-1].itertext())
    standalone = generate_image(changing_trace, **options)
    assert image_size(standalone)[0] <= first.width
    assert image_size(standalone)[1] <= first.height
    assert image_size(standalone) != first.size
    # Padding must remain free of content at every edge, including tall/wide overflow.
    for data in pngs:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        background = Image.new("RGB", image.size, image.getpixel((0, 0)))
        box = ImageChops.difference(image, background).getbbox()
        assert box is not None
        assert min(box[0], box[1], image.width - box[2], image.height - box[3]) >= 4 * dpi


def test_fresh_and_reused_raster_captures_match(changing_trace, rendering_session):
    fresh = Image.open(io.BytesIO(generate_image(changing_trace, dpi=2)))
    pooled = Image.open(
        io.BytesIO(generate_image(changing_trace, dpi=2, session=rendering_session))
    )
    assert fresh.size == pooled.size
    assert ImageChops.difference(fresh, pooled).getbbox() is None


def test_padding_outside_document_uses_canvas_color(monkeypatch):
    import base64
    from unittest.mock import MagicMock

    from cs1302_code_visualizer import browser_driver

    bounds = {"left": -4, "top": -4, "right": 10, "bottom": 10}
    monkeypatch.setattr(browser_driver, "_export_bounds", lambda *args: bounds)
    driver = MagicMock()
    source = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(source, format="PNG")
    driver.execute_cdp_cmd.return_value = {"data": base64.b64encode(source.getvalue()).decode()}
    driver.execute_script.return_value = "rgb(19, 20, 22)"
    data = browser_driver._capture_viz(
        driver,
        MagicMock(),
        dpi=2,
        format="PNG",
        visualizer="pytutor",
        session=None,
        bounds=bounds,
    )
    image = Image.open(io.BytesIO(data))
    assert image.size == (28, 28)
    assert image.getpixel((0, 0)) == (19, 20, 22)
    assert image.getpixel((8, 8)) == (255, 0, 0)
    clip = driver.execute_cdp_cmd.call_args.args[1]["clip"]
    assert clip == {"x": 0, "y": 0, "width": 10, "height": 10, "scale": 2}


def test_changed_sequence_layout_fails_before_clipping(monkeypatch):
    from unittest.mock import MagicMock

    from cs1302_code_visualizer import browser_driver

    driver = MagicMock()
    bounds = {"left": 10, "top": 10, "right": 100, "bottom": 100}
    monkeypatch.setattr(browser_driver, "_export_bounds", lambda *args: {**bounds, "right": 110})
    with pytest.raises(ValueError, match="layout changed"):
        browser_driver._capture_viz(
            driver,
            MagicMock(),
            dpi=1,
            format="PNG",
            visualizer="pytutor",
            session=None,
            bounds=bounds,
        )
    driver.execute_cdp_cmd.assert_not_called()


def test_bounds_failure_is_reported():
    from unittest.mock import MagicMock

    from cs1302_code_visualizer import browser_driver

    driver = MagicMock()
    driver.execute_async_script.return_value = {"error": "Cannot export an empty diagram"}
    with pytest.raises(ValueError, match="Export bounds failed: Cannot export an empty diagram"):
        browser_driver._export_bounds(driver, MagicMock())
