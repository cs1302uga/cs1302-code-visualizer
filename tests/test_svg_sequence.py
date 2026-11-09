"""Shared sequence manifests preserve complete, independent XML states."""

import json
from xml.etree import ElementTree as ET

import pytest

from scripts.svg_sequence import pack_frames, sequence_html


def test_shared_sequence_round_trip():
    frames = [
        (b'<svg xmlns="http://www.w3.org/2000/svg"><defs><path id="p" d="M0 0"/></defs>'
        b'<title>First</title><use href="#p"/><text>hello<tspan>world</tspan>!</text></svg>'),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><defs><path id="p" d="M0 0"/></defs>'
        b'<title>Second</title><use href="#p" transform="translate(2 3)"/></svg>'),
    ]
    manifest = pack_frames(frames + frames[:1])
    assert manifest["frames"][0] == manifest["frames"][2]
    assert len([n for n in manifest["nodes"] if n[0].endswith("}defs")]) == 1

    def expand(index):
        tag, attributes, children = manifest["nodes"][index]
        element = ET.Element(tag, dict(attributes))
        previous = None
        for child in children:
            if isinstance(child, str):
                if previous is None:
                    element.text = child
                else:
                    previous.tail = child
            else:
                previous = expand(child)
                element.append(previous)
        return element

    for index, frame in zip(manifest["frames"], frames, strict=False):
        assert signature(expand(index)) == signature(ET.fromstring(frame))
    with pytest.raises(ValueError, match="at least one"):
        pack_frames([])


def test_embedded_data_cannot_close_script():
    manifest = pack_frames([b"<svg><text>&lt;/script&gt;&lt;script&gt;alert(1)</text></svg>"])
    page = sequence_html(manifest)
    data = page.split('id="sequence">')[1].split("</script>")[0]
    assert "<" not in data
    assert json.loads(data) == manifest


def signature(element):
    return (element.tag, sorted(element.attrib.items()), element.text, element.tail,
            [signature(child) for child in element])


def test_player_real_trace_random_seek(tmp_path, rendering_session):
    from selenium.webdriver.support.ui import WebDriverWait

    from cs1302_code_visualizer.browser_driver import generate_step_images, get_webdriver
    from scripts.svg_sequence import ROOT

    trace = (ROOT / "docs/array-orientation/fixtures/edges.json").read_text()
    frames = generate_step_images(trace, format="SVG", session=rendering_session)
    assert len(frames) > 1
    page = tmp_path / "sequence.html"
    page.write_text(sequence_html(pack_frames(frames)))
    driver = get_webdriver()
    try:
        driver.get(page.as_uri())
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return !!document.querySelector('#diagram svg')")
        )
        order = list(range(len(frames))) + list(reversed(range(len(frames)))) + [0, len(frames) - 1, 0]
        for index in order:
            actual = driver.execute_script("""
                const slider = document.getElementById('step');
                slider.value = arguments[0]; slider.dispatchEvent(new Event('input'));
                return new XMLSerializer().serializeToString(document.querySelector('#diagram svg'));
            """, index)
            assert signature(ET.fromstring(actual)) == signature(ET.fromstring(frames[index]))
            assert driver.execute_script("return document.querySelectorAll('#diagram > svg').length") == 1
        driver.execute_script("""
            window.sequenceDownload = null;
            URL.createObjectURL = blob => { window.sequenceDownload = blob; return 'blob:test'; };
            HTMLAnchorElement.prototype.click = function() {};
            document.getElementById('download').click();
        """)
        downloaded = driver.execute_async_script("""
            const done = arguments[0]; window.sequenceDownload.text().then(done);
        """)
        assert signature(ET.fromstring(downloaded)) == signature(ET.fromstring(frames[0]))
    finally:
        driver.quit()
