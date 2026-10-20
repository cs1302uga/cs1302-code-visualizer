"""Per-step exports follow the selected execution sequence in either trace format."""

import json
import sys
from io import BytesIO, StringIO
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from cs1302_code_visualizer.browser_driver import generate_image, generate_step_images
from cs1302_code_visualizer.browser_driver import main as driver_main
from cs1302_code_visualizer.cli import _image_lines


def modern_trace(shape):
    steps = [
        {
            "step": index,
            "line": line,
            "callStack": [
                {
                    "methodName": "main",
                    "line": line,
                    "locals": [{"name": "x", "type": "int", "value": index + 1}],
                }
            ],
            "heap": {},
        }
        for index, line in enumerate([3, 4, 3])
    ]
    root = {"code": "class Demo {\n void main() {\n int x = 1;\n x++;\n }}", "format": "modern"}
    if shape == "steps":
        root["steps"] = steps
        expected = [(3, 1), (4, 2), (3, 3)]
    elif shape == "breakpoints":
        # JavaScript enumerates integer keys numerically, irrespective of JSON order.
        root["breakpoints"] = {"4": steps[1], "3": [steps[0], steps[2]]}
        expected = [(3, 1), (3, 3), (4, 2)]
    else:
        root["breakpoints"] = {"-1": steps, "99": steps[-1]}
        expected = [(3, 1), (4, 2), (3, 3)]
    return json.dumps(root), expected


@pytest.mark.parametrize("shape", ["steps", "breakpoints", "accumulated"])
def test_modern_step_exports_retain_all_selected_states(rendering_session, shape):
    trace, expected = modern_trace(shape)
    images = generate_step_images(trace, format="SVG", session=rendering_session)
    assert len(images) == len(expected)
    for image, (line, value) in zip(images, expected, strict=True):
        root = ET.fromstring(image)
        text = " ".join(root.itertext())
        assert f"main:{line}" in text
        assert f"int x: {value}" in text
    assert _image_lines(trace, len(images)) == [line for line, _ in expected]


@pytest.mark.parametrize("breakpoint, expected", [(4, (4, 2)), ((3, 2), (3, 3))])
def test_modern_step_exports_honor_selected_breakpoint(rendering_session, breakpoint, expected):
    trace, _ = modern_trace("breakpoints")
    images = generate_step_images(
        trace, breakpoint=breakpoint, format="SVG", session=rendering_session
    )
    assert len(images) == 1
    text = " ".join(ET.fromstring(images[0]).itertext())
    assert f"main:{expected[0]}" in text
    assert f"int x: {expected[1]}" in text


def test_modern_raster_sequence_changes_values_on_one_canvas(rendering_session):
    trace, _ = modern_trace("steps")
    frames = generate_step_images(trace, session=rendering_session)
    assert len(frames) == 3
    decoded = [Image.open(BytesIO(frame)).convert("RGB") for frame in frames]
    assert len({image.size for image in decoded}) == 1
    assert len({image.tobytes() for image in decoded}) == 3
    final = Image.open(BytesIO(generate_image(trace, session=rendering_session))).convert("RGB")
    assert decoded[-1].size == final.size
    assert decoded[-1].tobytes() == final.tobytes()


def test_modern_json_pre_still_exports_one_document(rendering_session):
    trace, _ = modern_trace("steps")
    frames = generate_step_images(
        trace, visualizer="json-pre", format="SVG", session=rendering_session
    )
    assert len(frames) == 1
    text = " ".join(ET.fromstring(frames[0]).itertext())
    assert '"format": "modern"' in text


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"format": "modern", "steps": [{"line": 9}, {"line": 3}]}, [9, 3]),
        ({"steps": [{"line": 9}, {"line": 3}]}, [9, 3]),
        ({"breakpoints": {"9": {"line": 9}, "3": [{"line": 3}, {"line": 3}]}}, [3, 3, 9]),
        ({"breakpoints": {"-1": [{"line": 9}, {"line": 3}]}}, [9, 3]),
    ],
)
def test_modern_output_line_metadata_matches_frontend_order(payload, expected):
    text = json.dumps(payload)
    assert _image_lines(text, len(expected)) == expected
    assert _image_lines(text, 1) == expected[-1:]


@pytest.mark.parametrize("event", ["raw_input", "mouse_input", "instruction_limit_reached"])
def test_output_lines_skip_terminal_events_removed_by_frontend(event):
    trace = {"trace": [{"line": 3}, {"line": 4}, {"event": event}]}
    assert _image_lines(json.dumps(trace), 2) == [3, 4]
    assert _image_lines(json.dumps(trace), 1) == [4]


def test_legacy_step_exports_refresh_stable_frame_headings(rendering_session):
    trace, _ = modern_trace("steps")
    modern = json.loads(trace)
    states = []
    for index, line in enumerate([3, 4]):
        states.append({
            "line": line,
            "event": "step_line",
            "stdout": "",
            "globals": {},
            "ordered_globals": [],
            "heap": {},
            "stack_to_render": [
                {
                    "unique_hash": "same-frame",
                    "frame_id": 0,
                    "func_name": f"main:{line}",
                    "is_highlighted": True,
                    "is_zombie": False,
                    "is_parent": False,
                    "parent_frame_id_list": [],
                    "ordered_varnames": ["x"],
                    "encoded_locals": {"x": index + 1},
                    "locals_attrs": {"x": {"type": "int"}},
                }
            ],
        })
    images = generate_step_images(
        json.dumps({"code": modern["code"], "trace": states}),
        format="SVG",
        session=rendering_session,
    )
    for image, line, value in zip(images, [3, 4], [1, 2], strict=True):
        text = " ".join(ET.fromstring(image).itertext())
        assert f"main:{line}" in text
        assert f"int x: {value}" in text


def test_trace_cli_exports_every_modern_step(tmp_path, monkeypatch):
    trace, _ = modern_trace("steps")
    monkeypatch.setattr(sys, "stdin", StringIO(trace))
    output = tmp_path / "modern.png"
    monkeypatch.setattr(sys, "argv", ["generate_visualization", "-a", "-o", str(output)])
    driver_main()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "modern.0.png",
        "modern.1.png",
        "modern.2.png",
        "modern.png",
    ]
    pixels = [Image.open(tmp_path / f"modern.{index}.png").tobytes() for index in range(3)]
    assert len(set(pixels)) == 3
    assert output.read_bytes() == (tmp_path / "modern.2.png").read_bytes()
