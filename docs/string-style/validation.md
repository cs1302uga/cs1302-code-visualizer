# String style validation

Validated on 2026-09-27 against the production bundle and real Java tracer output.

| Check | Result |
| --- | --- |
| Complete Python suite: `uv run pytest -q --tb=short` | 558 passed; 100% coverage of 2,024 statements. |
| Frontend: `npm --prefix cs1302_code_visualizer/frontend test -- --reporter=dot` | 94 passed across 10 files. |
| After final return-route adjustment: string rendering, export cropping, and SVG export suites | 31 passed. |
| `npm --prefix cs1302_code_visualizer/frontend run build` | Passed; existing webpack bundle-size advisories remain. |
| Repository Ruff, Markdown, and local links (`make check`) | Passed; 48 Markdown files, no missing links. |
| `make test-examples` under JDK 25 | 34 examples passed; 389 images rendered. |
| `make deptry` | Passed. |
| `make build` and final `make build-py` | Frontend, wheel, and source distribution passed. |
| `uv run basedpyright cs1302_code_visualizer` | No errors or warnings. |
| `git diff --check` | Passed. |

The browser matrix covers all three styles, horizontal/vertical arrays, and
light/dark themes. Assertions check equal box widths per container, 19 px heights,
source-dot positions, horizontal exits, common triangular heads, shaft endpoints,
shared identities, legacy-trace errors, text-only references, self-loops, multiple
return lanes, and SVG contents. Return paths are sampled to ensure they do not
cross unrelated heap objects in the representative fixture.

The complete `make check` suite and all examples passed after the final route
refinement and the raster snapshot repair. The production bundle was rebuilt
and the PNG/SVG examples regenerated.

The full gate run exposed clipping of outer reference routes inside batch
snapshot iframes. Raster capture now expands those frames to the measured painted
bounds. All 52 focused browser-driver/snapshot tests and the full suite pass.

Visual review caught a return line passing through an unrelated array. Return
routes now use outer heap rails, entering/leaving those rails through gaps below
the endpoint rows, while retaining the approved 24 px bottom clearance and 12 px
lane separation. The tests cover this combined-list case as well as self-loops.

The official type-check gate scopes Basedpyright to the production package.
PDF review helpers declare their dependencies in the optional `review` extra.

CodeQL 2.27.1 was rerun after security remediation. The same 233 Python and
245 JavaScript queries completed, and both database quality checks passed without
extractor errors. All remaining non-debug alerts have documented dispositions in
[the CodeQL remediation report](../codeql-remediation.md). Final logs, databases,
raw SARIF, and per-alert triage are under `static_analysis_codeql_2/`.

The approved prototype is preserved separately at `cc98e9c`; the production
review page is `docs/string-style/index.html`. Comparison images are in `images/`.
