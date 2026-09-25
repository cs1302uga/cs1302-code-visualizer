"""Validation and reproducibility checks for the comparison gallery."""

import json

import pytest

from scripts.svg_gallery import cases, gallery_html, validate_svg


def test_gallery_has_every_example_and_distinct_edge_cases():
    configurations = list(cases())
    names = [row[0] for row in configurations]
    assert len(names) == len(set(names))
    assert {f"example{i}" for i in range(34)} <= set(names)
    assert {"edges-override", "edges-prefix", "edges-dpi2", "edges-step10"} <= set(names)
    assert all(source.is_file() for _, source, _, _, _ in configurations)


def test_gallery_escapes_notes_and_omits_broken_downloads():
    page = gallery_html(
        [
            {
                "name": "example0",
                "command": "run <file>",
                "status": '<script>alert("bad")</script>',
                "options": {},
                "png": True,
            }
        ],
        "test",
    )
    assert "<script>" not in page
    assert 'href="example0.png"' in page
    assert 'href="example0.svg"' not in page
    assert 'src="example0.svg"' not in page
    assert 'href="example0.trace.json"' in page
    assert "&lt;file&gt;" in page


@pytest.mark.parametrize(
    "content",
    [
        '<svg xmlns="http://www.w3.org/2000/svg"><image/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><use href="other.svg"/></svg>',
        "<html/>",
    ],
)
def test_gallery_rejects_nonstandalone_exports(tmp_path, content):
    path = tmp_path / "invalid.svg"
    path.write_text(content)
    with pytest.raises(ValueError):
        validate_svg(path, False)


def test_gallery_validates_editable_svg_without_claiming_inkscape_check(tmp_path):
    path = tmp_path / "valid.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>hello</text></svg>')
    assert "Inkscape not checked" in validate_svg(path, False)
    # The options recorded for each focused case are reproducible JSON values.
    for _, _, _, options, _ in cases():
        assert json.loads(json.dumps(options)) == options


def test_inline_svg_scopes_references_and_exposes_one_structured_description(tmp_path):
    from scripts.svg_gallery import inline_svg

    path = tmp_path / "test.svg"
    description = {
        "summary": "One object",
        "sections": [{"heading": "Heap <1>", "items": ["a & b"]}],
    }
    from html import escape

    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title" aria-describedby="desc">'
        '<title id="title">One object</title><desc id="desc">Full description</desc>'
        f'<metadata data-description="1">{escape(json.dumps(description))}</metadata>'
        '<defs><clipPath id="clip"><rect width="10" height="10"/></clipPath></defs>'
        '<g clip-path="url(#clip)"><text>value</text></g></svg>'
    )
    first, transcript = inline_svg(path, "first")
    second, _ = inline_svg(path, "second")
    assert 'aria-label="One object"' in first
    assert "<title" not in first
    assert 'clip-path="url(#first-clip)"' in first
    assert 'id="second-clip"' in second
    assert "aria-describedby" not in first
    assert "<desc" not in first
    assert "metadata" not in first
    assert "<h3>Heap &lt;1&gt;</h3><ul><li>a &amp; b</li>" in transcript
    assert "<summary>Text description</summary>" in transcript

    page = gallery_html(
        [{"name": "test", "command": "run", "status": "ready", "png": True, "svg": True}],
        "test",
        tmp_path,
    )
    assert "<svg " in page
    assert 'src="test.svg"' not in page
    assert "<summary>Text description</summary>" in page
    assert 'href="test.svg" download' in page
