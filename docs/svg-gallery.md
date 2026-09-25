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
