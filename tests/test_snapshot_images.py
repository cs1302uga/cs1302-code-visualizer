"""Contracts for independent payload batching without cross-snapshot layout state."""

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image
from selenium.webdriver.remote.webelement import WebElement

from cs1302_code_visualizer import browser_driver, generate_snapshot_images


def payloads():
    return [json.dumps({"code": name, "trace": []}) for name in ("first", "other")]


def test_empty_snapshots_do_not_open_browser():
    with patch.object(browser_driver, "online_python_tutor_frontend") as frontend:
        assert generate_snapshot_images([]) == []
    frontend.assert_not_called()


@pytest.mark.parametrize("session", [None, MagicMock()])
@pytest.mark.parametrize("format", ["PNG", "SVG"])
def test_snapshot_batch_preserves_order_options_and_resets_viewport(session, format):
    driver = MagicMock()
    driver.execute_async_script.return_value = MagicMock(spec=WebElement)
    driver.get_window_size.return_value = {"width": 800, "height": 600}
    driver.current_url = (
        "file:///frontend/render-trace.html?arrayOrientation=vertical&theme=dark&tracePath=old"
    )
    first_viz = MagicMock()
    second_viz = driver.find_element.return_value
    options = {
        "dpi": 2,
        "theme": "dark",
        "format": format,
        "include_types": False,
        "text_memory_labels": True,
        "strip_type_prefixes": ["java.lang."],
        "array_orientation": "vertical",
        "alternate_array_orientations": True,
        "array_orientations": {"1": "horizontal"},
        "session": session,
    }
    with (
        patch.object(browser_driver, "online_python_tutor_frontend") as frontend,
        patch.object(browser_driver, "_capture_viz", side_effect=[b"first", b"second"]) as capture,
        patch.object(browser_driver, "_prepare_session_viewport") as reset,
    ):
        frontend.return_value.__enter__.return_value = {"driver": driver, "dataViz": first_viz}
        assert generate_snapshot_images(payloads(), **options) == [b"first", b"second"]
    assert [call.args[1] for call in capture.call_args_list] == [first_viz, second_viz]
    frame_url = driver.execute_script.call_args_list[0].args[1]
    assert parse_qs(urlsplit(frame_url).query)["arrayOrientation"] == ["vertical"]
    assert parse_qs(urlsplit(frame_url).query)["theme"] == ["dark"]
    driver.switch_to.frame.assert_called_once()
    driver.switch_to.default_content.assert_called_once()
    assert "remove()" in driver.execute_script.call_args.args[0]
    assert frontend.call_count == 1
    expected = {key: value for key, value in options.items() if key not in {"format", "session"}}
    expected.update(trace=payloads()[0], dpi=1, visualizer="pytutor")
    if session is not None:
        expected["session"] = session
    reset.assert_called_once_with(driver)
    driver.set_window_size.assert_not_called()
    assert frontend.call_args.kwargs == expected


def test_snapshot_json_text_falls_back_to_individual_requests():
    with patch.object(browser_driver, "generate_image", side_effect=[b"one", b"two"]) as generate:
        assert generate_snapshot_images(
            payloads(), visualizer="json-pre", format="SVG", theme="auto"
        ) == [
            b"one",
            b"two",
        ]
    assert [call.args[0] for call in generate.call_args_list] == payloads()
    assert all(call.kwargs["format"] == "SVG" for call in generate.call_args_list)
    assert all(call.kwargs["theme"] == "auto" for call in generate.call_args_list)


def test_snapshot_frontend_failure_never_returns_partial_results():
    driver = MagicMock()
    driver.execute_async_script.return_value = MagicMock(spec=WebElement)
    driver.current_url = "file:///frontend/render-trace.html?tracePath=old"
    with (
        patch.object(browser_driver, "online_python_tutor_frontend") as frontend,
        patch.object(
            browser_driver, "_capture_viz", side_effect=[b"first", RuntimeError("failed capture")]
        ) as capture,
        patch.object(browser_driver, "_prepare_session_viewport"),
    ):
        frontend.return_value.__enter__.return_value = {"driver": driver, "dataViz": MagicMock()}
        with pytest.raises(RuntimeError, match="failed capture"):
            generate_snapshot_images(payloads(), session=MagicMock())
    assert capture.call_count == 2
    assert frontend.return_value.__exit__.call_args.args[0] is RuntimeError
    driver.switch_to.default_content.assert_called_once()
    assert "remove()" in driver.execute_script.call_args.args[0]


def test_single_snapshot_uses_existing_image_path():
    with patch.object(browser_driver, "generate_image", return_value=b"single") as generate:
        assert generate_snapshot_images(payloads()[:1], format="SVG", theme="dark") == [b"single"]
    generate.assert_called_once()
    assert generate.call_args.kwargs["theme"] == "dark"


@pytest.mark.parametrize("visualizer", ["pytutor", "json-pre"])
def test_snapshot_payloads_validate_before_browser_start(visualizer):
    with (
        patch.object(browser_driver, "online_python_tutor_frontend") as frontend,
        pytest.raises(json.JSONDecodeError),
    ):
        generate_snapshot_images([payloads()[0], "not json"], visualizer=visualizer)
    frontend.assert_not_called()


def image_content(data, format):
    if format == "SVG":
        return data
    with Image.open(BytesIO(data)) as image:
        rgba = image.convert("RGBA")
        return rgba.size, rgba.tobytes()


@pytest.mark.parametrize(
    "options",
    [
        {"format": "SVG"},
        {"format": "SVG", "theme": "auto"},
        {"format": "SVG", "dpi": 2, "text_memory_labels": True, "theme": "light"},
        {"format": "PNG", "theme": "auto"},
        {
            "format": "PNG",
            "dpi": 2,
            "include_types": False,
            "text_memory_labels": True,
            "theme": "dark",
        },
        {
            "format": "SVG",
            "array_orientation": "vertical",
            "alternate_array_orientations": True,
            "theme": "dark",
        },
        {"format": "WEBP", "strip_type_prefixes": ["java.lang."]},
    ],
)
def test_real_snapshot_output_matches_individual_payloads(rendering_session, options):
    traces = [
        next(Path(f"small-trace-examples/example{number}").glob("*.json")).read_text()
        for number in (0, 1, 2)
    ]
    resolved = [json.dumps(browser_driver.resolve_trace_payload(trace)) for trace in traces]
    expected = [
        image_content(
            browser_driver.generate_image(trace, session=rendering_session, **options),
            options["format"],
        )
        for trace in resolved
    ]
    for order in ([0, 1, 2], [2, 0, 2], [0, 2], [1]):
        actual = generate_snapshot_images(
            [resolved[index] for index in order], session=rendering_session, **options
        )
        assert [image_content(data, options["format"]) for data in actual] == [
            expected[index] for index in order
        ]


@pytest.mark.parametrize("format", ["SVG", "PNG"])
def test_real_snapshot_without_session_matches_fresh_browser_images(format):
    traces = [
        next(Path(f"small-trace-examples/example{number}").glob("*.json")).read_text()
        for number in (1, 2)
    ]
    expected = [
        image_content(browser_driver.generate_image(trace, format=format, dpi=2), format)
        for trace in traces
    ]
    actual = generate_snapshot_images(traces, format=format, dpi=2)
    assert [image_content(image, format) for image in actual] == expected


@pytest.mark.parametrize("stage", ["switch", "ready", "lookup"])
def test_snapshot_frame_failure_restores_context_and_removes_temporary_payload(stage):
    driver = MagicMock()
    driver.execute_async_script.return_value = MagicMock(spec=WebElement)
    if stage == "switch":
        driver.switch_to.frame.side_effect = RuntimeError(stage)
    elif stage == "ready":
        driver.execute_async_script.side_effect = RuntimeError(stage)
    else:
        driver.find_element.side_effect = RuntimeError(stage)
    with (
        pytest.raises(RuntimeError, match=stage),
        browser_driver._snapshot_frame(
            driver, payloads()[0], "file:///renderer.html?tracePath=old&theme=auto"
        ),
    ):
        pytest.fail("failed document must not reach capture")
    frame_url = driver.execute_script.call_args_list[0].args[1]
    trace_path = Path(parse_qs(urlsplit(frame_url).query)["tracePath"][0])
    assert not trace_path.exists()
    driver.switch_to.default_content.assert_called_once()
    assert driver.execute_script.call_args.args == (
        "arguments[0].remove();",
        driver.execute_script.return_value,
    )
