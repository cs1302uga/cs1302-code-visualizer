# Coordinated layout and routing: source algorithm audit

Scope: static source inspection only, against main
`b6b2e2b9a0593662ac336016706809151cfa1c04` (B) and PR28 comparison
`971e89341e9fba85459ff3ad1d1dc7aac4145e5b` (P). No literature, builds, tests,
browser sessions, branch changes, or Git mutations. Only these notes and the
[durable algorithm inventory](../algorithm-inventory.md)
were written. The inventory contains the detailed algorithm sequence, complexity
qualifications, integration recommendations, regression obligations, and pinned
source index. `researcher.md`, `AGENTS.md`, and `CONTRIBUTING.md` were read.

## What actually places and sizes the diagram?

### Takeaway

B combines browser table layout with predecessor-derived heap row membership and
a rightward nudge heuristic. Trace-wide label measurement provides limited
stability; it is not a trace-wide pixel-placement optimizer. [Row model][row-model],
[nudge][nudge], [label model][labels].

### Cited Findings

- Stack/global and heap regions are adjacent table cells. Globals precede stack
  frames; frames follow reversed supplied Java stack order, keyed by
  `unique_hash`, with D3 ordering/enter/exit. [Stack DOM][stack-dom],
  [Java reversal][java-reversal], [frame join][frames].
- Heap precomputation copies the previous layout, traverses ordered visible roots
  and referenced children, groups structurally equivalent chains, splices or
  appends rows, then removes unreached old IDs and empty rows. The browser later
  lays out rebuilt tables. The sorted cross-row nudge adds the executable **96 px**
  margin allowance, despite a nearby comment saying 32. Dragged CSS overrides
  these nudges. [Row model][row-model], [root/removal][roots], [nudge][nudge],
  [drag restoration][drag].
- Stack type/name widths use all supplied states plus optional shared type labels,
  cached by font signature. Value widths instead use the current contents'
  `max(40, ceil(textWidth)+22)` maximum per table; P batches resets before reads.
  [Label model][labels], [B value sizing][values], [P sizing][p-values].

### Inferences

- Retained row membership is a continuity preference, not pixel invariance:
  changed dimensions, removed rows, nudges, and drag offsets affect positions.
  The repeated row scans/splices/removals admit quadratic work in laid-out object
  count, plus entry traversal and structural comparisons. [Row model][row-model],
  [root/removal][roots], [nudge][nudge].
- Preserve current stack and heap behavior as separate initial strategy models;
  frame append/prepend and heap peak/intersection anchors are future policies,
  not existing implementation features. [Frame join][frames], [row model][row-model].

### Gaps

- Requested `docs/agents/domain.md` was absent when first read; no replacement
  domain guidance was assumed.
- No runtime/rendered evidence was gathered, as required by the assignment.

## What does routing guarantee, and what did PR28 change?

### Takeaway

B routes sequentially using validated finite candidate families and bounded
visibility searches, then mutates layout locally on failure. P adds controlled
baseline/sharing behavior and indexes while explicitly retaining historical as
the default. Neither establishes shortest drawing, complete discovery, or a
routing deadline. [B planning/repair][routing], [B search][search],
[P policy][p-policy], [P coordination][p-routing].

### Cited Findings

- DOM geometry is collected once per routing pass in container-relative CSS
  pixels; repairs repeat the pass. Nonheap sources route first, then source y/x,
  target geometry, and normalized source ID decide order. Previous paths and
  future departure reservations constrain each edge. [Snapshot/planning][routing].
- Families include direct/one-bend routes, preferred right departures within
  24 px, legacy cubics, lower/exterior routes, per-port two-corner paths, doglegs,
  narrow fallbacks, sweeps, grids, and historical alias-head sharing. Target ports
  also occur every 10 px, so port count is not constant. [Candidate families][candidates].
- Grid coordinates use sorted exact obstacle/channel/port boundaries. State is
  `(grid point, initial|horizontal|vertical)`, **orientation rather than signed
  direction**. Costs add Manhattan length and 18 per axis change; source stubs
  initialize multiport costs but have no incoming orientation. Final approach
  stub/head and rounding are checked after search. The heuristic is nearest-goal
  Manhattan distance times 1.25 for references or 1 for parent searches. Ties use
  lower f, larger g, then smaller state ID. [Search implementation][search],
  [postprocessing][grid-call].
- Caps count queue removals including stale entries: 5,000 for body-avoiding
  reference grids, 200,000 for paint-only reference grids, and 5,000 for each
  parent grid. Up to three margins are tried. The 512 cap covers selected dogleg
  validations, not all candidates. [Search limits][search], [doglegs/grid][candidates].
- Protected text/source/target/head/shaft checks are acceptance conditions;
  unrelated-body avoidance, spacious departures, and distinct alias arrivals are
  preferences. Historical alias shaft/head exemptions remain explicit.
  [Validators][validators], [shaft checks][shafts], [candidate acceptance][candidates].
- Repairs translate the first foreign source-dot text blocker, widen target or
  source by 24 px, or allocate canvas padding, with full rerouting and per-scene
  attempt bounds. Restore callbacks run in reverse on clear; failure has no
  immediate `finally` rollback. [Repair implementation][routing].
- B has linear geometry scans and route/width-dependent shaft caches. P adds
  median-split rectangle indexes, lazy repeated-query indexes, per-search caches,
  strict controlled alias handling, crowded target ordering/capacity repair,
  explicit owned baselines, and optional bounded spine sharing. Physical paint
  ownership stays distinct from logical routes. [B shafts][shafts],
  [P index][p-index], [P coordination][p-routing], [P sharing][p-sharing],
  [P paint][p-paint].
- Existing gates remain 16/50 ms p95 redraw and **300 ms maximum fresh layout**;
  P requires the latter for dense-48, fan-in-48, and many-groups-12x4 under both
  controlled policies and the original policy-switch protocol. These are
  benchmark gates, not runtime limits. [B gates][gates], [P checker][p-checker].

### Inferences

- Weighted/truncated search, first-valid family selection, grid orientation-only
  cost, omitted terminal costs, sequential occupancy, and final shape rejection
  prevent shortest-drawing or complete-discovery claims. A same-graph exact
  oracle must preserve the actual graph/cost model; changing to signed direction
  changes that model. [Search][search], [grid return][grid-call].
- An X-by-Y grid has up to 3XY state slots and four neighbors per state; both axes
  grow with obstacle/channel/port count. Rectangle-tree balance does not prove
  logarithmic queries: overlapping bounds permit full traversal. [Grid][search],
  [P index][p-index].
- The coordinator should own movement, resizing, canvas allocation, bounded
  retries, and rollback. Geometry-only routing and separate painting can use the
  current snapshot/route structures as extraction seams; structured failures and
  rollback-on-failure need an explicit new contract. [Current mutation seam][routing],
  [redraw/measurement seam][redraw].

### Gaps

- No runtime, visual, or performance pass is claimed. The 300 ms gates and
  historical default were inspected, not changed or reevaluated.
- Finite queue/attempt/profile bounds do not supply a whole-render complexity or
  wall-clock guarantee; port enumeration and geometry validation remain material.

## What temporal context and identities can future strategies rely on?

### Takeaway

The frontend can begin at the end and seek backward or directly to any supplied
index. Existing heap row precomputation already uses predecessor trace context,
but modern frame keys are method/line/depth keys, and selected snapshot payloads
can omit execution history. [Factory/start][factory], [navigation][navigation],
[row model][row-model], [adapter identity][adapter], [selection][selection].

### Cited Findings

- Factory options enable `jumpToEnd`; the underlying visualizer supports
  `renderStep`, `stepBack`, and `stepForward`. Same-index `renderStep` is a no-op.
  Heap plans are prepared for every supplied step before the first displayed
  state. [Factory][factory], [initial render][initial], [navigation][navigation],
  [direct seek][seek].
- Heap DOM identity omits step number; heap map IDs are preserved from input.
  Heap source endpoint counters reset each render. Modern `frame_id` is array
  position and `unique_hash` is `methodName:line:frameIdx`; the frame interface
  has no invocation-ID field. [Heap IDs][heap-ids], [endpoint lifecycle][endpoints],
  [modern adapter][adapter], [modern frame schema][frame-schema].
- Payload resolution can select one breakpoint occurrence; the adapter flattens
  only supplied states. Sequence export traverses all states for bounds, then
  again for capture. Separate snapshot documents share a type budget, not prior
  geometric state. [Selection][selection], [adapter][adapter],
  [sequence lifecycle][sequence], [snapshot lifecycle][snapshots].

### Inferences

- A line-dependent key can change within an invocation or recur across distinct
  invocations. Do not equate it with stable call identity. Peak live sets or
  interval-intersection anchors require an explicit supplied-trace scope,
  membership definition, objective/ties, identity policy, and missing-history
  fallback. [Frame schema/conversion][adapter], [payload scope][selection].
- Initial strategies should preserve behavior and be independently replaceable.
  Future temporal output should be indexed by trace/settings and explicitly
  retained state, not accidental navigation order. Compare direct seeks with
  repeated forward/backward traversal, two-pass export, and fresh isolated
  snapshots; test transactional restoration, geometry/style/identity cache
  invalidation, and complete SVG/PNG bounds. Existing replay, stack-header, and
  export tests support this work but do not establish those new contracts.
  [Existing geometry regressions][regressions], [header regression][header-test],
  [export regression][export-test], [lifecycle][sequence].

### Gaps

- No stable tracer invocation identity, heap peak/intersection summary, committed
  per-step pixel/route history, temporal transition objective, or optimizer was
  established in this frontend audit.
- A complete execution history cannot be inferred from a selected single-state
  public payload. No literature or new temporal algorithm was evaluated.

[row-model]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1795-L2129
[roots]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2162-L2230
[nudge]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L3038-L3162
[labels]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/stackLabelLayout.ts#L1-L76
[stack-dom]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1425-L1460
[java-reversal]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L979-L995
[frames]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2692-L2865
[drag]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L3346-L3408
[values]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/valueLayout.ts#L18-L44
[p-values]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/valueLayout.ts#L18-L51
[routing]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/connectorRouting.ts#L22-L191
[search]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L174-L229
[grid-call]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L456-L482
[p-policy]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/svgConnectors.ts#L327-L348
[p-routing]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/connectorRouting.ts#L100-L252
[candidates]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L277-L482
[validators]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/referenceRouting.ts#L33-L151
[shafts]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/shaftClearance.ts#L1-L109
[p-index]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/rectangleIndex.ts#L1-L62
[p-sharing]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/sharedReferenceRouting.ts#L480-L927
[p-paint]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/cs1302_code_visualizer/frontend/js/svgConnectors.ts#L455-L538
[gates]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/docs/reference-routing/README.md#L140-L154
[p-checker]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/971e89341e9fba85459ff3ad1d1dc7aac4145e5b/scripts/benchmark_reference_routing/check-budgets.cjs#L5-L44
[redraw]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L4354-L4359
[factory]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/CodeVisualizer.ts#L175-L228
[initial]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L657-L713
[navigation]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L802-L839
[seek]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L960-L975
[adapter]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L151-L233
[frame-schema]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L19-L25
[selection]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/browser_driver.py#L395-L457
[heap-ids]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1524-L1537
[endpoints]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2343-L2373
[sequence]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/browser_driver.py#L816-L851
[snapshots]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/browser_driver.py#L979-L1021
[regressions]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/tests/svgConnectors.test.ts#L190-L486
[header-test]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/tests/stackFrameHeaders.test.ts#L35-L97
[export-test]: https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/tests/test_export_cropping.py#L46-L142
