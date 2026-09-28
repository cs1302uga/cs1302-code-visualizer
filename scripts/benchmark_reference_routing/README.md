# Reference-routing browser benchmark

From the repository root, build the frontend and serve the checkout:

```sh
npm --prefix cs1302_code_visualizer/frontend run build
uv run python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/scripts/benchmark_reference_routing/` in Chrome.
Set the viewport to 1536 × 960 CSS pixels and run `await benchmarkRouting()` in
the browser console. Save the returned JSON under `.scratch/`. Use the same
browser, hardware, viewport, and assets for comparisons; avoid concurrent tests.

The six fixture traces contain their Java source and one captured state each.
They exercise later-node references, aliases, cycles, self-loops, sibling fields,
and arrays. The harness covers nine combinations of these cases and string
styles. It also constructs 24- and 48-object scenes with two heap references per
object and one stack reference per four objects, giving 54 and 108 references.

For each case the harness waits for Recursive fonts, measures six new visualizer
instances with warm assets, warms routing with five repaints, and records 40
repaints and 40 full redraws. It also counts bounding-rectangle reads during one
repaint. Full redraw includes value-box layout; neither measurement represents
cold loading or a complete execution-step transition. The reported maximum fresh
layout is the maximum of six samples, not a population percentile.

The [routing guide](../../docs/reference-routing/README.md#validation-and-performance)
contains the accepted budgets and geometry requirements. Runtime results alone
cannot establish route readability or export correctness. Preserve raw results
with browser/hardware details when investigating a regression.
