# Existing layout and routing algorithms

Static source audit for the layout coordinator. **B** means main baseline
`b6b2e2b9a0593662ac336016706809151cfa1c04`; **P** means PR28 comparison
`971e89341e9fba85459ff3ad1d1dc7aac4145e5b`. Citations pin those commits rather
than this moving branch. Production files examined in the worktree matched B.
PR28 behavior below is comparison evidence, not functionality present in B.
No builds, tests, browser captures, benchmarks, or Git mutations were performed.
`AGENTS.md` and `CONTRIBUTING.md` were read; requested `docs/agents/domain.md`
was absent at audit time.

## Placement and sizing at B

- **Stack/global placement:** one HTML table has a top-aligned stack cell on the
  left and heap cell on the right. The persistent globals frame precedes the
  separate `#stack` container. Globals follow filtered `ordered_globals`; hiding
  the globals frame tests the original ordered list's length, not the filtered
  count. Stack frames use a D3 join keyed by `unique_hash`, append entering divs,
  remove exits, and reorder the merged selection to `stack_to_render`. Java
  reverses every supplied stack array before rendering. Thus actual order is the
  reversed supplied order; the renderer has no independent append/prepend
  strategy. Modern statics retain class/field iteration order. [B stack DOM][b-stack-dom],
  [B global order][b-globals], [B frame order][b-frames],
  [B Java reversal][b-java], [B statics][b-statics].
- **Stack dimensions:** CSS and content determine frame width/height; frames have
  bottom margins, globals/stack have horizontal padding, and frame variable tables
  align to the right. There is no numeric frame-packing or frame-height solver.
  `StackLabelLayout` gathers all supplied states' declared global/local types and
  variable names, adds `_layoutTypes` to the type budget, trims prefixes, and
  measures unique labels. It reserves maximum type/name widths with CSS custom
  properties. `__return__` contributes `Return` and `value`; headers and value
  widths are not part of this trace-wide label budget. Measurements are cached
  by the sampled label's font, variation settings, letter spacing, and font
  readiness/check status. [B frame CSS][b-frame-css], [B label model][b-labels],
  [B label CSS][b-label-css].
- **Heap row plan:** `precomputeCurTraceLayouts()` processes all supplied states
  forward, deep-copies the preceding row-ID/object-ID lists, traverses visible
  globals then stack variables, and recursively visits referenced children.
  Structurally equivalent linked objects can share a row. New chains splice
  before an encountered existing object, append to an existing chain, or append
  a new row. A visited-ID set terminates reference cycles. Previously laid-out
  IDs no longer reached through this traversal are removed, then empty rows
  disappear. This is a reachability/order heuristic, not a scan placing every raw
  heap entry. Structural equivalence checks tags, array lengths or field-name
  sets, not general graph isomorphism. [B row initialization][b-heap-init],
  [B recursion][b-heap-recursion], [B row insertion][b-heap-update],
  [B roots/removal][b-heap-roots], [B equivalence][b-equivalence].
- **Heap pixel placement:** each render clears `#heap` and rebuilds row tables and
  ordered object cells from the selected plan. CSS table layout supplies pixels.
  The enabled rightward nudge visits sorted heap-connector source IDs; for a
  cross-row source lying right of its target, it adds
  `sourceLeft - targetLeft + 96` to the target object's left margin and propagates
  through remembered row nudgees, excluding the current source row. The comment
  mentions 32 px; the executable constant is **96**. Saved dragged-object CSS is
  restored afterward and overrides nudges. Row deletion, content changes, table
  sizing, nudges, and drag offsets can change pixels despite row continuity.
  [B heap rebuild][b-heap-dom], [B nudge flag][b-nudge-flag],
  [B nudge][b-nudge], [B drag restore][b-drag], [B heap CSS][b-heap-css].
- **Value surfaces:** two passes over eligible cells reset each box to
  `max-content`, measure its text Range, calculate
  `max(40, ceil(textWidth) + 22)`, retain the maximum per closest table, then apply
  that common width and update compact-string arrows. B interleaves resets and
  reads in its first pass. P batches all resets before reads, preserving the
  sizing formula. CSS sets a 19 px box height, 40 px minimum, and no text wrapping.
  Array orientation, string style, hidden content, types, fonts, and trace values
  therefore affect measured geometry. [B value sizing][b-values],
  [P batched sizing][p-values], [B value CSS][b-value-css],
  [B array options][b-arrays], [B string transformation][b-strings].

**Complexity inference:** heap precomputation retains one row plan per supplied
state, so plan storage is proportional to their combined row memberships. For a
state with at most H current/previous laid-out objects, repeated whole-layout
lookup, removal, and splicing can take quadratic work in H, in addition to
encoded-entry traversal and structural comparisons. It is not a linear graph
layout algorithm. Label collection scans supplied state metadata; measurements
scale with unique labels when the font signature changes. Browser layout cost
is additional to these source-level operation counts. [B heap implementation][b-heap-update],
[B roots/removal][b-heap-roots], [B labels][b-labels].

## DOM snapshot and sequential route planning at B

`ConnectorRouting.repaint()` creates a fresh rectangle cache relative to the
connector container's bounding rectangle. It collects heap/frame owners, visible
text Range rectangles, and compact-string circle/polygon/path bounds. Visibility
checks display, visibility, opacity, and ancestors. Each requested element's
bounding rectangle is cached once **per pass**; text Range rectangles and styles
are separate reads. Repairs cause additional complete passes. [B snapshot][b-snapshot].

Reference dots sit at the value-box right edge minus 8 px and its vertical center;
the dot radius is 3 px, head length 6 px, and half-width 3 px. Target geometry uses
the contained object table when present. `returning` means a heap-origin link
whose target owner is at or left of its source owner. Width is the maximum normal
and hover stroke width. Frame-parent links instead retain configured frame sides.
Edges sort nonheap before heap origins, then source y/x, target left/top, and
visualizer-prefix-normalized source ID. [B attachments/order][b-attachments],
[B shared dimensions][b-dimensions].

The scene routes sequentially: earlier accepted routes/heads and later sources'
first usable departure stubs constrain each edge. A lane counter increments per
target-owner index. Crowded aligned stack sources reserve additional future-turn
rectangles; an initial failed pass can retry with those reservations. This is
order-sensitive coordination using a canonical sort, not joint optimization of
all connections. Snapshot preprocessing itself contains owner-list linear
lookups, nested stack comparisons, and per-edge construction of other-source
lists, so one rectangle read per element does not imply linear total work.
[B reservations/planning][b-planning].

### Candidate families and selection

Reference candidates are tried in this implemented order. [B reference planner][b-reference].

1. Direct/one-bend orthogonal routes across arrival ports; retain the shortest
   accepted simple alternative by unrounded Manhattan-to-tip length.
2. Prefer a right departure with at most two bends and no backtracking, within
   24 px of that simple length. Then use the retained simple route if available.
3. Try the legacy straight-departure/cubic route for nonreturning references,
   shallow-enclosure lower/exterior routes, per-port two-corner routes, and
   horizontal/vertical exterior doglegs. Retain the first safe narrow departure
   while looking for room beside borders.
4. Return a retained narrow departure, otherwise try broad cubic sweeps and
   multiport visibility searches. If all distinct-arrival attempts fail,
   historical aliases can retry with shared arrowheads.

Ports include five fractions on each target side, aligned positions when
applicable, and additional 10 px interval positions. Their count grows with target
dimensions. Polylines try corner radii 12/0; grid output tries 12/6/0. Every accepted
shape passes validation after rounding. A path's `kind: "visibility"` also labels
simple polylines; it does not prove a grid search ran. Frame-parent links have
their own side-preserving simple/cubic/single-pair-grid family. [B ports/simple][b-simple],
[B remaining candidates][b-fallback], [B parent planner][b-parent],
[B polyline construction][b-polyline].

### Visibility graph, objective, limits, and guarantees

- **Graph:** sort/deduplicate exact x/y coordinates from region edges, departure
  and approach ports, clipped local-obstacle bounds, and shaft-channel bounds.
  The Cartesian grid is implicit; edges connect adjacent coordinates horizontally
  or vertically. Region margins are the distinct values among 32, 128, and a
  scene-derived exterior margin. [B grid][b-search], [B grid invocation][b-grid-call].
- **State:** `pointIndex * 3 + orientation`, with 0 initial, 1 horizontal, and 2
  vertical. Left/right share orientation 1; up/down share orientation 2. **This
  is orientation, not signed direction.** Same-axis reversal has no bend charge.
  [B state/relaxation][b-search].
- **Cost:** source-to-departure Manhattan distance initializes multiport states;
  each grid edge adds Manhattan length plus 18 for a horizontal/vertical change.
  Initial orientation 0 adds no turn cost. Goals are approach points; terminal
  stubs, heads, and rounded geometry are attached and checked afterward. This
  objective is not complete painted route length or full bend count.
  [B cost][b-search], [B postprocessing][b-grid-call].
- **Heuristic/ties:** nearest approach-point Manhattan distance, multiplied by
  1.25 for multiport references and 1 for single-pair parent searches. Queue ties
  favor larger g, then smaller numeric state ID; equal-g relaxations are ignored.
  Each search returns its first popped goal. [B priority/search][b-search].
- **Limits:** strict body-avoiding reference grids allow 5,000 queue removals;
  paint-only reference grids allow 200,000. Parent grids allow 5,000 per call.
  Stale entries count because the counter increments before the stale test.
  Selected exterior dogleg validations share a 512 cap; direct, simple,
  per-departure two-corner checks, port enumeration, and all other families are
  outside that cap. Alias fallback and layout retries can repeat work.
  [B search limits][b-search], [B dogleg cap][b-doglegs],
  [B grid limits/fallback][b-grid-call].

**Supported guarantees:** accepted reference candidates satisfy the implemented
protected-paint, source departure/re-entry, target boundary/early-passage,
head-versus-prior-shaft, and shaft-clearance predicates. Text is expanded by 1 px
plus stroke extent. Curve/rectangle testing conservatively subdivides, rejecting
uncertain contacts at depth 20 or hull size below .01. Shaft chords retain curve
error bounds, with 6 px plus both stroke extents. Chord pairs whose squared
normalized dot product is below .75 bypass the shaft-conflict test as crossings
(strictly beyond the 30-degree threshold, modulo reversal); equality is still
checked. Historical aliases exempt near-vertical
same-target shafts and portions within target+16 px, and can ultimately share
heads. These exemptions are part of B's contract, not universal disjointness.
[B validators][b-validators], [B candidate acceptance][b-accept],
[B shaft clearance][b-shafts].

**Preferences:** unrelated-body avoidance (8 px), right departures, spacious
shallow-enclosure exits, distinct alias arrivals, and short/simple paths can be
relaxed by later candidates. Neither shortest route, complete route discovery,
minimum crossings/bends/ink, successful repair, nor a wall-clock deadline follows
from this code. Weighted A*, work truncation, fixed candidate families,
orientation-only state, sequential occupancy, and post-search shape rejection
limit any optimality claim. [B selection][b-reference], [B search][b-search].

**Complexity inference:** with X distinct x coordinates and Y y coordinates there
are at most 3XY state slots and four neighbors per state; coordinates can each
grow with obstacle/channel/port count, giving a quadratic Cartesian product.
Maps allocate lazily. For one capped search with D initial departure states and
L pops, binary-heap work is O((D + L) log(D + L)); successful relaxations add at
most four entries per popped state. Heuristic evaluations scan all goal ports, and uncached grid-edge
visibility queries scan local obstacles and occupied shaft chords. Candidate and
curve-check work remains additional. Rectangle subdivision has a fixed depth
cap, not constant practical cost. No useful whole-render time bound follows
from the queue-pop cap. [B search][b-search], [B intersections][b-validators],
[B shaft scans][b-shafts].

## Repairs, caches, and paint ownership

- **Current repair owner:** `ConnectorRouting` restores recorded mutations in
  reverse order before an outer pass. After reservation retry, parent failure
  throws. Other failures can translate the first foreign text owner covering
  the source dot downward, widen a target by 24 px when a source departure is
  possible, or widen the source value box by 24 px. Each mutation triggers full
  remeasurement/rerouting while `attempt < connections.length + 4`. The first
  matching blocker is used; the comment's “smallest” is not a computed minimum.
  Left/top padding can retry below an 8 px paint margin while
  `attempt < connections.length + 6`; right/bottom padding is set from extents.
  There is no transactional `finally` restoring a failed pass immediately:
  restores occur through a later clear/reset/prepare operation. [B repair loop][b-repair].
- **Restoration seam:** `DataVisualizer.redrawConnectors()` calls manager
  `prepareLayout()`, applies stack label widths, sizes value boxes, then repaints.
  Manager reset clears repairs and right/bottom padding. Batch depth defers routing
  until `endBatch()`; ordinary renders reconstruct endpoint mappings and heap DOM.
  [B redraw][b-redraw], [B manager lifecycle][b-manager],
  [B render lifecycle][b-render-start].
- **Caches:** B's route fingerprint serializes ordered owner/text/local-arrow
  rectangles and attachments, including maximum widths. Cache hits still measure
  the DOM and paint SVG. Search distance/predecessor/visibility maps are per call.
  Shaft flattening uses route-object identity; channel hints use route identity
  and candidate width, rounding hints to 1/1024 px with extra clearance. Cached
  route objects therefore implicitly require unchanged segments/width. Exact
  geometry is not rounded. B has no rectangle spatial index. [B fingerprint][b-planning],
  [B shaft caches][b-shafts], [B cache-hit painting][b-paint].
- **Painting/export:** B writes a complete L/Q/C path, dot position, and polygon
  head for each logical connection. Stroke/emphasis styles live in SVG connection
  objects; routing reserves maximum normal/hover width. Export waits for fonts
  and a rendered frame, includes painted SVG stroke extents and clipped content,
  and measures shared raster/vector bounds independently of layout containers.
  Routing's control-point paint bounds are not a substitute for that export
  measurement. [B SVG path/paint][b-paint], [B path serialization][b-validators],
  [B export bounds][b-export].

## PR28 comparison at P

- **Placement remains the same heuristic:** P retains the stack/heap row plan and
  nudge model; its value sizing batches resets before reads. It adds controlled
  `historical`, `independent`, and `shared` manager policies, initialized to
  **historical**. These are internal comparison controls, not public factory/CLI
  options. [P policy][p-policy], [P sizing][p-values], [P stack/heap implementation][p-placement].
- **Controlled baseline coordination:** crowded ordinary stack-reference slots
  can reorder target-first; parent/heap-reference slots retain their positions.
  Controlled attachments set `strict`, disabling implicit alias exemptions.
  A validated owned-suffix baseline fallback can attach a pending reference when
  arrival capacity is oversubscribed or an owned group already exists; it makes
  no optional-improvement claim for a previously unaccepted route. Controlled
  target repair can allocate estimated incoming-reference capacity instead of
  only another 24 px. Strict self-references add a finite diagonal-departure
  family. [P coordination][p-coordination], [P strict/fallback][p-reference],
  [P strict shafts][p-shafts].
- **Spatial indexes:** P's immutable `RectangleIndex` splits at the median after
  sorting rectangle centers on the longer bounding-box axis, with leaves of at
  most eight entries. Inclusive broad-phase queries retain boundary contacts;
  strict interior queries handle axis-aligned grid edges. Grid obstacles are
  indexed immediately; other obstacle queries build at call 128, head queries
  after 64 distinct cached decisions, and shaft queries from call 32 when more
  than 16 occupied chords exist. Exact predicates still decide admission.
  **Complexity inference:** repeated recursive sorting gives O(n log² n)
  construction under comparison-sort accounting; overlapping node bounds can
  force O(n) query work despite balanced height. No logarithmic query guarantee
  is justified. [P rectangle index][p-index], [P head/grid indexes][p-grid-index],
  [P candidate index][p-reference], [P shaft indexes][p-shafts]. P retains B's
  orientation states, graph cost, weighted heuristic, pop limits, and tie rules;
  it memoizes per-point heuristic values and uses numeric grid-edge cache keys.
  [P search implementation][p-grid-index].
- **Sharing/paint:** P factors compatible exact suffixes, validates an independent
  or explicitly owned baseline, then optionally considers straight monotone
  spines with ordered joins and at most one terminal bend. Partitions use target
  identity, persistent semantic style, width, and arrival side; self/returning/
  parent references are excluded. Up to four tips and 24 retained profiles per
  partition bound this family, not total planning. Admission checks nonincreasing
  complete member length/bends, fixed direct geometry and exit side, strict
  ink/head reduction, and complete ownership/clearance constraints. Complete
  logical paths remain available; grouped full-path/head paint is hidden while
  private branches and owned physical suffix/head paint are drawn once.
  [P profile limit][p-sharing-limits], [P eligibility][p-sharing-eligibility],
  [P planner/admission][p-sharing], [P physical paint][p-paint].
- **Added cache dependencies:** P fingerprints policy, endpoint IDs, persistent
  style, and eligibility, and reuses head/heuristic/departure decisions within
  fixed searches. Sharing caches depend on route/segment identity, geometry,
  widths, and sharing roles, scoped by scene object-array identity where used.
  A future coordinator must invalidate these when geometry, ownership, policy,
  identity, or persistent style changes. [P scene cache][p-coordination],
  [P search caches][p-grid-index], [P planner caches][p-sharing-caches].

## Trace lifecycle and available temporal context

The public factory constructs a fresh execution visualizer with `jumpToEnd`,
hidden code, and disabled heap nesting; it exposes the underlying `.visualizer`
alongside update/redraw/destroy. The initial render selects the first error or
last state, but precomputes every supplied state's heap row plan first.
`renderStep(i)` supports arbitrary indexed seeks and ignores the already-selected
index. Back/forward can jump between breakpoints. Java postprocessing reverses
cloned stack arrays; caller data is protected by the string-style clone.
[B public factory][b-factory], [B initial planning][b-initial],
[B navigation][b-navigation], [B direct seek][b-seek], [B clone/style][b-strings].

Existing prior context comprises the supplied normalized trace, predecessor-derived
heap row plans, trace-wide label budgets, dragged CSS, current DOM, and the last
geometry-keyed route cache. It does **not** comprise a committed per-step pixel
layout/route history, lifetime anchor map, trace transition objective, or temporal
optimizer. A retained D3 element is not evidence of such a model.
[B retained state][b-state], [B row precomputation][b-heap-init],
[B current-route cache][b-planning].

Identity has distinct scopes:

- Heap DOM IDs use visualizer prefix + heap object ID, **without step number**.
  The adapter preserves heap-map keys/references; this lets supplied IDs identify
  the same traced object across states but establishes no cross-execution
  identity guarantee. Heap endpoint source counters reset each render and are
  explicitly not stable across execution points. [B heap IDs][b-heap-ids],
  [B encoded references][b-adapter-ids], [B heap-map keys][b-adapter-heap],
  [B endpoint counter reset][b-endpoint-reset], [B render endpoint reset][b-render-start].
- Legacy frame joins trust `unique_hash`; modern frames synthesize
  `frame_id = frameIdx` and `unique_hash = methodName:line:frameIdx`.
  Modern frame input has no invocation-ID field. Line changes alter the key,
  and repeated invocations at the same method/line/depth can reuse it. Therefore
  these keys do not establish stable invocation identity. Stack div IDs are
  assigned from enter position; variable endpoint IDs incorporate frame hash
  and variable name. [B modern frame schema][b-adapter-frames],
  [B modern frame conversion][b-adapter-sequence],
  [B frame DOM IDs][b-frames], [B variable IDs][b-variable-ids].

The available trace can be a selected snapshot rather than a complete execution:
Python payload resolution selects breakpoint/hit payloads, and the modern adapter
flattens supplied breakpoint values without reconstructing omitted history.
`generate_step_images()` makes a measurement traversal and then a capture
traversal using `renderStep`; separate snapshot-image documents share only a type
budget, not prior placement state. New strategies must tolerate full traces,
single states, repeated forward/backward traversal, and direct initial seeks.
[B selection][b-selection], [B adapter sequence][b-adapter-sequence],
[B sequence capture][b-sequence], [B separate snapshots][b-snapshots].

## Coordinator seams and regression obligations

These are integration recommendations from the audited call graph, not claims
that a coordinator or strategy interfaces already exist.

1. **Independent stack and heap models:** wrap current frame/global ordering and
   heap row-precomputation/nudge behavior separately. Preserve the current
   reversed input order and predecessor row-plan semantics initially. Keep
   measurement, label budgets, and endpoint identity explicit inputs. The source
   seams are stack/global D3 materialization, `precomputeCurTraceLayouts`, and
   rightward nudge/drag restoration. [B frames][b-frames],
   [B row plan][b-heap-init], [B nudge][b-nudge].
2. **Coordinator ownership:** extract clear/restore, sizing, translation, widening,
   canvas allocation, bounded retries, and rollback from `ConnectorRouting` and
   `DataVisualizer.redrawConnectors`. Routing should consume one measured snapshot
   and return a plan or structured failure, without DOM mutation. Preserve the
   existing repair/reservation order and attempt accounting as compatibility
   behavior; define rollback-on-failure separately because B does not ensure it.
   [B repairs][b-repair], [B redraw seam][b-redraw], [B batch lifecycle][b-manager].
3. **Future trace-aware extensions:** support stack append versus prepend as
   distinct policies, and heap peak-set or interval-intersection anchors as
   distinct policies. Define the interval, reachable versus raw heap membership,
   peak metric/ties, identity matching, and insufficient-history behavior before
   implementing either anchor model. None of those summaries or policies exists
   in the current row plan. Plan by supplied trace/index/settings rather than
   accidental visit order; explicit user drag state needs an explicit policy.
   [B current plan][b-heap-init], [B lifecycle][b-navigation],
   [B selected histories][b-selection], [B frame identity][b-adapter-frames].
4. **Meaningful proposed regressions:** compare initial strategy output against
   current order/coordinates/routes on recursive push/pop, globals-only,
   disconnected/aliased/cyclic heaps, linked-row splice/removal, and drag restore.
   Compare fresh direct seek with forward/backward/repeated seek at the same
   index; include two-pass sequence export and isolated snapshots. Test repair
   success and exhausted/throwing repair with every mutated style restored,
   preserved connection identity, and bounded attempts. Change fonts, labels,
   string style, orientation, widths, endpoint identity, container, and controlled
   policy/style independently to exercise cache dependencies. Assert routes pass
   clearance and SVG/PNG bounds after each coordination pass. Existing replay,
   frame-header, array-navigation, label, native export, and snapshot tests are
   starting points, not evidence these additional obligations already pass.
   [B geometry tests][b-routing-tests], [B header tests][b-header-tests],
   [B array tests][b-array-tests], [B label tests][b-label-tests],
   [B crop tests][b-crop-tests], [B SVG tests][b-svg-tests],
   [B snapshot tests][b-snapshot-tests].
5. **Comparison oracle:** if an exact same-graph Dijkstra/admissible-A* oracle is
   added, share coordinate generation, orientation state, costs, ports, and
   occupancy with production; account explicitly for terminal-cost omissions and
   rounding rejection. Such an oracle can test that graph objective, not global
   drawing optimality or a temporal recurrence. Signed direction would be a
   changed state model. [B graph/cost][b-search], [B terminal processing][b-grid-call].

## Unchanged acceptance boundaries and evidence gaps

B documents representative p95 full redraw ≤16 ms, dense 48-object/108-reference
p95 ≤50 ms, and dense maximum fresh layout ≤300 ms. Its benchmark measures six
new-instance warm-asset layouts, five warmups, and 40 repaint/full-redraw samples.
P additionally retains the **300 ms maximum** for `fan-in-48` and
`many-groups-12x4`, for both controlled policies. Its checker requires all 14
cases, valid baselines, six finite fresh samples, 40 redraw samples, and the
original policy-switch protocol; public creation under historical routing is
included before selecting the controlled policy. Do not substitute initial-policy
measurements or queue caps for those gates. Historical remains the default.
[B gates/protocol][b-gates], [B benchmark][b-benchmark],
[P unchanged gates][p-gates], [P checker][p-checker], [P default][p-policy].

This audit establishes source behavior only. It does not establish current
runtime correctness, performance, visual traceability, tracer-level invocation
identity, or a complete temporal objective. The missing domain guidance and
unrun runtime/render/export checks remain explicit gaps. No literature was used.

[b-stack-dom]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1425-L1460
[b-globals]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2505-L2688
[b-frames]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2692-L2865
[b-java]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L979-L995
[b-statics]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L237-L253
[b-frame-css]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/css/pytutor.css#L579-L661
[b-labels]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/stackLabelLayout.ts#L1-L76
[b-label-css]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/css/pytutor.css#L1160-L1187
[b-heap-init]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1795-L1877
[b-heap-recursion]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1879-L2021
[b-heap-update]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2031-L2129
[b-heap-roots]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2162-L2230
[b-equivalence]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2241-L2288
[b-heap-dom]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2388-L2495
[b-nudge-flag]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L141-L142
[b-nudge]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L3038-L3162
[b-drag]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L3346-L3408
[b-heap-css]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/css/pytutor.css#L663-L685
[b-values]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/valueLayout.ts#L4-L44
[b-value-css]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/css/pytutor.css#L1110-L1148
[b-arrays]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/arrayOrientation.ts#L1-L35
[b-strings]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/stringStyle.ts#L21-L63
[b-snapshot]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/connectorRouting.ts#L33-L77
[b-attachments]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/connectorRouting.ts#L78-L102
[b-dimensions]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/connectorGeometry.ts#L1-L18
[b-planning]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/connectorRouting.ts#L93-L164
[b-reference]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L277-L482
[b-simple]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L309-L361
[b-fallback]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L362-L482
[b-parent]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L231-L275
[b-polyline]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L154-L171
[b-search]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L174-L229
[b-grid-call]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L456-L482
[b-doglegs]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L383-L430
[b-validators]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L33-L151
[b-accept]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L277-L307
[b-shafts]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/shaftClearance.ts#L1-L109
[b-repair]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/connectorRouting.ts#L125-L191
[b-redraw]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L4354-L4359
[b-manager]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/svgConnectors.ts#L361-L397
[b-render-start]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2343-L2373
[b-paint]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/connectorRouting.ts#L158-L191
[b-export]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/exportBounds.ts#L16-L109
[b-factory]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/CodeVisualizer.ts#L175-L228
[b-initial]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L657-L713
[b-navigation]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L802-L839
[b-seek]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L960-L975
[b-state]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1360-L1423
[b-heap-ids]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1524-L1537
[b-adapter-ids]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L108-L131
[b-adapter-heap]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L256-L283
[b-endpoint-reset]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1606-L1635
[b-adapter-frames]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L19-L25
[b-variable-ids]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2860-L2929
[b-selection]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/browser_driver.py#L395-L457
[b-adapter-sequence]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L151-L233
[b-sequence]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/browser_driver.py#L816-L851
[b-snapshots]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/browser_driver.py#L979-L1021
[b-routing-tests]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/tests/svgConnectors.test.ts#L190-L486
[b-header-tests]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/tests/stackFrameHeaders.test.ts#L35-L97
[b-array-tests]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/tests/arrayOrientation.test.ts#L15-L115
[b-label-tests]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/tests/stackLabelLayout.test.ts#L5-L27
[b-crop-tests]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/tests/test_export_cropping.py#L46-L142
[b-svg-tests]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/tests/test_svg_export.py#L40-L93
[b-snapshot-tests]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/tests/test_snapshot_images.py#L154-L247
[b-gates]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/docs/reference-routing/README.md#L140-L154
[b-benchmark]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/scripts/benchmark_reference_routing/benchmark.js#L42-L68
[p-values]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/valueLayout.ts#L18-L51
[p-policy]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/svgConnectors.ts#L327-L348
[p-placement]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/pytutor.ts#L1796-L2231
[p-coordination]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/connectorRouting.ts#L100-L252
[p-reference]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L320-L446
[p-shafts]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/shaftClearance.ts#L60-L129
[p-index]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/rectangleIndex.ts#L1-L62
[p-grid-index]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L136-L270
[p-sharing]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/sharedReferenceRouting.ts#L480-L927
[p-sharing-limits]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/sharedReferenceRouting.ts#L54-L58
[p-sharing-eligibility]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/sharedReferenceRouting.ts#L197-L201
[p-paint]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/svgConnectors.ts#L455-L538
[p-sharing-caches]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/sharedReferenceRouting.ts#L568-L603
[p-gates]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/docs/reference-routing/README.md#L252-L282
[p-checker]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/scripts/benchmark_reference_routing/check-budgets.cjs#L5-L44
