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
