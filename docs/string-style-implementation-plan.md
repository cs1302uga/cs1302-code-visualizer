# String style implementation plan

Status: approved and implemented on `feature/string-style`. See
[string style validation](string-style/validation.md) for checks and review artifacts.

## Approved behavior

Introduce the public Python type `StringStyle = Literal["compact", "default", "inline"]`
and the rendering option `string_style`, whose effective default is `"default"`.

| Style | String presentation |
| --- | --- |
| `default` | Separate string heap objects, equivalent to the existing `inline_strings=False` representation. |
| `inline` | Literal inside the value box, equivalent to the existing `inline_strings=True` representation. |
| `compact` | Reference value in its box, followed by a short horizontal arrow and the full literal inside the enclosing object, frame, or array component. |

The approved visual reference is Option B at commit `cc98e9c` on
`prototype/string-style-option-b`. Its geometry is documented in
`../cs1302_code_visualizer/frontend/prototypes/string-style/README.md`.
The review screenshots are in `../artifacts/option-b-review/`.
Preserve this prototype independently; implement the feature in production modules,
without importing the prototype or carrying over its DOM patching approach.

Apply the shared Option B refinements to all three styles:

- Value boxes are 19 px high, with common widths within each enclosing object,
  frame, or array, at least 40 px. Expand for contents; compact literals do not
  determine box width. Keep reference values left-aligned, with 6 px left and
  14 px right padding.
- Source dots sit 8 px inside the right border, vertically centered. All arrows
  use 1 px shafts, 3 px radius source dots, and filled 6 by 6 px triangular heads.
  Shafts terminate at the midpoint of the arrowhead's rear edge.
- Non-string reference arrows remain horizontal until 4 px inside the enclosing
  object's, frame's, or array's right border. Curves approach arrowheads horizontally.
- Backward heap references use rounded return routes below objects, with 24 px
  clearance and 12 px separation between lanes. Include these routes in bounds.
- Compact strings retain an 18 px box-to-literal gap; tips stop 3 px before literals.
  Literals neither wrap nor truncate. Shared strings repeat locally with the same ID.
  Null has no arrow.
- Field and stack-variable labels use a non-wrapping flex row, baseline alignment,
  end justification, and a 0.25 rem gap, without `text-align: right`.
- Heap labels use concrete runtime `ClassName@ref`, retaining array lengths.
  References are trace IDs, not identity hash codes. Declared variable types remain
  separate from concrete heap types.

`include_types=False` continues to hide declared variable/field types only; heap
identity labels remain. `text_memory_labels=True` suppresses persistent arrows
and source dots in every style. Compact strings then show the reference and
adjacent literal. Preserve existing hover arrows where a separate heap target
exists; omit hover connections to string heap objects hidden by compact/inline.

## 1. Resolve options and preserve compatibility

Add a small `string_options.py` module, following the existing theme/array option
modules, and export `StringStyle` from the package. Centralize value validation,
legacy-option resolution, and conflict handling.

- Cover `render_image`, `render_images`, and `BatchRenderJob` in `__init__.py`.
- Both render functions and batch jobs default to `default`. This intentionally
  changes the omitted-option behavior of `render_images` and `BatchRenderJob`,
  which currently default to inline strings.
- Explicit `inline_strings=False` maps to `default`; `True` maps to `inline`.
  Emit `DeprecationWarning` at the public caller, once per explicit use rather
  than per frame or internal forwarding call.
- Reject explicitly supplying both options with `TypeError`, even when they agree.
  Invalid styles fail early, before tracing or browser startup.
- Use a private omitted-value sentinel at compatibility boundaries, including the
  batch-job initializer. A literal runtime default of `"default"` alone cannot
  distinguish omission from explicit `string_style="default"`; document the
  effective public default and keep public typing constrained to `StringStyle`.
  Normalize once and forward only the resolved style internally.
- Keep deprecated rendering arguments throughout the current major version;
  remove them in the next major, after at least one warning-bearing release.

Trace-only controls remain unchanged: `generate_trace.inline_strings`,
`BatchTraceJob.inline_strings`, tracer JSONL inputs, and trace-only session calls
still control trace serialization. Do not add `StringStyle` to trace-only APIs.

## 2. Preserve string identities through rendering

Update rendering paths in `__init__.py`, `cli.py`, and session/batch integration
to request non-inlined traces for every style. Rendering style must not change
the generated trace or its reference IDs. Preserve trace-only behavior and verify
that session/cache keys still distinguish trace serialization options correctly.

In `frontend/js/modernTraceAdapter.ts` and `pytutor.ts`, retain canonical string
objects and references, and derive their displayed representation from the style.
Avoid mutating input traces so the same trace can render in different styles.
Hide standalone string heap objects in compact/inline while preserving every
non-string object, reference, and shared identity.

For imported legacy traces whose string identities were already discarded:

- Allow `inline`.
- Reject `default` and `compact` with an actionable message asking the caller to
  regenerate the trace with string inlining disabled or render with `inline`.
- Detect identity loss from the supported trace schema's value representations;
  do not mistake unrelated metadata strings for inlined Java String values.
  Traces without string values remain usable in all styles.
- Never invent reference IDs to make a legacy trace appear identity-preserving.

## 3. Carry the option through every rendering entry point

Thread the normalized option through `browser_driver.py`, rendering sessions,
HTML embedding, `frontend/js/CodeVisualizer.ts`, `render-trace.ts`, and both
frontend HTML entry points. Follow existing naming conventions: `string_style`
for Python/manifest fields and `stringStyle` for frontend options.

Expose `--string-style {compact,default,inline}` in the unified CLI and lower-level
rendering CLIs. Apply it to single, multi-step, directory, and manifest batch runs.
Per-job manifest `string_style` overrides the CLI value; omission inherits it;
the CLI default is `default`. Report invalid per-job values with the manifest
line/job context. Route any supported legacy rendering inputs through the same
deprecation/conflict resolver rather than silently ignoring them.

Ensure PNG, SVG, and embedded HTML all receive identical resolved settings.

## 4. Implement production layout and connector geometry

Implement compact string pairs in the renderer's normal field, stack, and array
rendering paths. Apply shared styling in `frontend/css/pytutor.css` and, where
appropriate, `codevis.css`. Measure equal box widths after content/fonts settle,
and recalculate when frames or array orientations change.

Centralize common arrow geometry in `frontend/js/svgConnectors.ts`; use it for
compact arrows and ordinary reference connectors. Implement the approved initial
horizontal segment and return-lane routing using enclosing-container bounds.
Reserve space for return routes and ensure redraws do not retain stale connectors.
Exercise self-loops, multiple backward edges, and shared targets as extensions of
the approved cycle rule, without changing its visible geometry.

Update `svgExport.ts`, `exportBounds.ts`, and `svgDescription.ts` as needed so
exported text, identities, compact pairs, arrowheads, and external return lanes
match the live view and remain inside the output bounds.

## 5. Validate behavior and appearance

Extend existing test suites at the relevant boundaries rather than relying only
on prototype fixtures:

| Area | Required coverage |
| --- | --- |
| Python options | All three styles; omitted defaults; explicit legacy booleans; warning caller location; both-option conflicts including explicit `default`; invalid inputs; batch-job omission. |
| CLI and manifests | Help/choices; global defaults; per-job override/inheritance; invalid values; single/multi-step and batch propagation. |
| Trace integration | All styles request identity-preserving traces; trace-only inline controls remain usable; session reuse does not leak styles. |
| Frontend | One canonical trace rendered three ways without mutation; shared identities; strings in frames, fields, and arrays; null, empty, escaped, and long strings; legacy rejection/inline acceptance. |
| Presentation options | Both themes and array orientations, mixed orientation overrides, hidden declared types, text-only references and applicable hover behavior. |
| Geometry and exports | Box height/alignment, source-dot placement, shared arrowheads, horizontal exits, self/three-node/multiple cycles, frame changes, export bounds and PNG/SVG consistency. |

Use actual traced Java examples of `Node`, `List`, `ArrayBasedList`, and
`LinkBasedList`, alongside targeted synthetic edge fixtures. Compare compact
renders against the approved screenshots; compare default/inline semantics against
their previous representations while allowing the explicitly approved shared
visual refinements. Browser geometry assertions should verify routing/placement;
unit tests alone cannot validate layout.

Run the relevant Python tests and frontend Vitest suites first, then the complete
project test suites and required lint/type checks. Rebuild the checked-in frontend
bundle with `npm run build`. Capture representative PNG and SVG outputs for final
visual review, including the cycle and long-string cases.

## 6. Document and deliver

Update `README.md`, `docs/cli.md`, API docstrings, embedding examples, and release
notes with the style table, default change, deprecation schedule, migration
examples, manifest inheritance, and the legacy-trace regeneration requirement.
Explain that compact repeats literals while preserving their underlying identity.

Deliver the implementation with the rebuilt frontend assets, regression tests,
and comparison captures. Report validation results and any remaining limitations.
This document records the approved scope; implementation and validation are now complete.
