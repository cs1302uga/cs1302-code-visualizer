# SVG export comparisons

The gallery displays actual PNG and SVG exports side-by-side. It covers all 34 Java examples, focused presentation options, and selected intermediate steps. Each pair uses the same trace, execution step, and options. Download links preserve the original files; trace links and reproduction commands make each comparison inspectable.

## Generate visual evidence

Use the [checkout setup](../CONTRIBUTING.md#set-up-a-checkout), including Chrome. The full example collection requires JDK 25 because example 33 uses `java.lang.IO`. Ensure the selected `java` is JDK 25 before generating the gallery. Inkscape must be on `PATH` for `--inkscape`.

```sh
make build-frontend
uv run python -m scripts.svg_gallery --stage baseline --baseline-only
uv run python -m scripts.svg_gallery --stage final --inkscape
```

Open `artifacts/svg-gallery/final/index.html` directly in a browser. No server is required. Each milestone directory contains original exports, exact traces, a results manifest, an overview screenshot, and a comparison screenshot per case. With `--inkscape`, it also contains Inkscape rasterizations linked from each comparison's details.

Use different milestone names to preserve intermediate evidence. For a focused iteration:

```sh
uv run python -m scripts.svg_gallery --stage arrows-fixed --case example0 --case edges
```

The generator reports failed exports in the gallery and exits unsuccessfully if any fail. It checks SVG structure and loads every displayed image before taking browser screenshots. Successful generation is distinct from visual approval: status text marks visual review as pending until notes are supplied.

## Review comparisons

Check label content and bounds, object and array geometry, connectors and endpoints, clipping, colors, and repeated execution states. Inspect both browser comparisons and representative Inkscape renderings. SVG fonts are substituted when unavailable, so glyph shape and emoji support can differ. The text remains editable.

To attach review observations, supply a JSON object mapping case names to notes:

```json
{"example0": "Reviewed: labels, boxes, and connector endpoints match; font substitution visible."}
```

```sh
uv run python -m scripts.svg_gallery --stage final --inkscape \
  --review-file artifacts/svg-gallery/review-notes.json
```

Generated files stay in the ignored `artifacts/svg-gallery/` directory. The generator and focused Java inputs are version-controlled. Traces are cached using source contents, trace arguments, JDK release metadata, and project configuration; use `--refresh-traces` to force retracing. An existing PNG baseline is reused only when its trace and presentation options match the current case.

Gallery checks supplement the required `make check`, `make test-examples`, distribution checks, and CI matrix; they do not replace them.

## Check selection and accessibility

The gallery embeds SVG markup directly so its text can be selected and copied. Local IDs are scoped per diagram to keep clipping and accessible labels independent. Downloads retain the standalone SVG with its summary and complete description. The gallery exposes the full description once, in a keyboard-operable **Text description** disclosure with headings and lists.

Run the browser checks sequentially because they exercise the clipboard. They copy known test text and verify pasting into a controlled text area; they do not read pre-existing clipboard contents. The checks replace the clipboard with test text. Firefox and its Selenium driver are required for the second command.

```sh
uv run python -m scripts.check_svg_accessibility artifacts/svg-gallery/final
uv run python -m scripts.check_svg_accessibility artifacts/svg-gallery/final --browser firefox
```

These checks require `example0` and `edges` in the gallery. They save browser-version results, highlighted-selection screenshots, and an expanded-description screenshot. They cover mouse selection, copying Unicode text in both the gallery and a standalone SVG, Space to expand the description, and Tab to reach the next disclosure. Chrome normalizes layout nonbreaking spaces to ordinary spaces when copying.

For manual VoiceOver/Safari acceptance, open both the gallery and a standalone export. Confirm the diagram has a concise name, its description is available, and graphical labels are not narrated a second time. Navigate the gallery disclosure by keyboard and read its headings and lists. Check that stack frames precede heap objects, references name their targets, shared objects appear once, cycles terminate, and hidden fields stay absent. Test an intermediate step and a no-types case. Record the macOS/Safari versions and actual observations; browser automation and screenshots alone do not establish screen-reader acceptance.
