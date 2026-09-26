"""Theme option propagation and browser-level theme behavior."""

import argparse
from pathlib import Path

import pytest

from cs1302_code_visualizer import BatchRenderJob, render_image, render_images
from cs1302_code_visualizer.browser_driver import online_python_tutor_frontend, render_html
from cs1302_code_visualizer.theme_options import add_theme_argument, theme_options


def test_theme_validation_and_html():
    assert theme_options(None) == {}
    assert theme_options("dark") == {"theme": "dark"}
    parser = argparse.ArgumentParser()
    add_theme_argument(parser)
    assert parser.parse_args(["--theme", "auto"]).theme == "auto"
    assert '"theme": "dark"' in render_html({}, theme="dark")
    for action in [
        lambda: theme_options("invalid"),
        lambda: render_html({}, theme="invalid"),
        lambda: render_image("", theme="invalid"),
        lambda: render_images("", set(), theme="invalid"),
        lambda: BatchRenderJob("", set(), theme="invalid"),
    ]:
        with pytest.raises(ValueError, match="theme must"):
            action()


def test_exported_svg_follows_host_and_system_theme(rendering_session):
    trace = Path("small-trace-examples/example0/Driver.java.json").read_text()
    with online_python_tutor_frontend(trace, session=rendering_session) as frontend:
        driver = frontend["driver"]
        svg = driver.execute_async_script("""
          const done = arguments[arguments.length - 1];
          window.exportVisualizationSvg(document.getElementById('dataViz')).then(done);
        """)
        driver.execute_script("document.body.innerHTML = arguments[0]", svg)

        def text_color():
            return driver.execute_script(
                "return getComputedStyle(document.querySelector('[data-codevis-fill=text]')).fill"
            )

        for theme, expected in [("light", "rgb(30, 30, 30)"), ("dark", "rgb(207, 208, 208)")]:
            driver.execute_script("document.body.dataset.theme = arguments[0]", theme)
            assert text_color() == expected
            assert driver.execute_script(
                "return getComputedStyle(document.querySelector('[data-codevis-fill=canvas]')).fill"
            ) == "rgba(0, 0, 0, 0)"
        driver.execute_script("document.body.dataset.theme = 'auto'")
        try:
            for scheme, expected in [("dark", "rgb(207, 208, 208)"), ("light", "rgb(30, 30, 30)")]:
                driver.execute_cdp_cmd(
                    "Emulation.setEmulatedMedia",
                    {"features": [{"name": "prefers-color-scheme", "value": scheme}]},
                )
                assert text_color() == expected
            driver.execute_script("document.querySelector('svg').dataset.codevisTheme = 'dark'")
            assert text_color() == "rgb(207, 208, 208)"
            driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "print"})
            assert text_color() == "rgb(30, 30, 30)"
        finally:
            driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "", "features": []})


def test_inactive_connectors_and_dark_export(rendering_session):
    import copy
    from xml.etree import ElementTree as ET

    from cs1302_code_visualizer.browser_driver import generate_image, resolve_trace_payload

    payload = resolve_trace_payload(
        Path("small-trace-examples/example0/Driver.java.json").read_text()
    )
    state = payload["trace"][-1]
    original = state["stack_to_render"][0]
    state["stack_to_render"] = []
    for index in range(3):
        frame = copy.deepcopy(original)
        frame.update(
            frame_id=index,
            unique_hash=str(index),
            is_highlighted=index == 2,
            func_name=["main:4", "visit:8", "inspect:12"][index],
        )
        state["stack_to_render"].append(frame)
    import json

    for theme, expected in [("light", "rgb(120, 132, 150)"), ("dark", "rgb(117, 131, 151)")]:
        output = generate_image(
            json.dumps(payload), theme=theme, format="SVG", session=rendering_session
        )
        root = ET.fromstring(output)
        assert root.attrib["data-codevis-theme"] == theme
        for tag, attribute in [("path", "stroke"), ("circle", "fill"), ("polygon", "fill")]:
            elements = root.findall(
                f'.//{{http://www.w3.org/2000/svg}}{tag}[@data-codevis-{attribute}="inactiveArrow"]'
            )
            assert len(elements) == 2
            assert all(element.attrib[attribute] == expected for element in elements)
        # The active frame and the heap's Person -> String connection remain blue.
        assert (
            len(root.findall('.//{http://www.w3.org/2000/svg}path[@data-codevis-stroke="arrow"]'))
            >= 2
        )
