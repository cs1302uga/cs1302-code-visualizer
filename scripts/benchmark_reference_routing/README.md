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

For controlled terminal-sharing comparisons, use the manager's internal policy
through the harness. This does not add a public visualizer or CLI setting:

```js
await benchmarkRouting({
  routingPolicy: 'independent',
  hardware: 'record processor, memory, and operating system',
  assetRevision: 'record checkout revision and bundle SHA-256',
});
await benchmarkRouting({
  routingPolicy: 'shared',
  hardware: 'same hardware description',
  assetRevision: 'same checkout revision and bundle SHA-256',
});
```

During a run, `window.routingBenchmarkProgress` reports the current case, phase,
and completed sample count. `window.routingBenchmarkResults` and
`window.routingBenchmarkTransitions` expose completed results immediately. An
optional `onProgress(state)` callback receives the same updates outside timed
blocks. This makes a slow case observable without changing the router's
deterministic operation limits. Use `caseNames` to isolate a case; the harness
does not impose an elapsed-time cutoff on routing.

The default `historical` policy is the production comparison. `independent`
requests the controlled independent baseline; `shared` also tries terminal-path
sharing. A controlled-baseline failure is a failure to investigate, not a timing
sample to omit. Each result includes the available plan's baseline status, group
kinds and sizes, decline diagnostics, and `baselineOrdering` (`source` or
`target`) from the manager. Do not interpret zero accepted groups as a routing
failure when the independent baseline is valid.

Both controlled policies use the same baseline construction. If aligned ordinary
stack references need more distinct-target lane clearance than the stack-to-heap
gap to visible, nonempty heap objects provides, baseline construction orders those references by canonical target
geometry and identity. Frame-parent and heap-reference slots keep their order.
This narrow crowded-stack coordination is separate from the general target-first
experiment below; ordinary noncrowded scenes retain source order. When arrival
capacity is oversubscribed, or an owned suffix already exists for that target,
the controlled baseline may also attach a reference to a validated, explicitly
owned existing suffix after simple independent routes are exhausted. Existing
paths retain their geometry, and future source departures and shared suffixes
remain protected. Such baseline groups can exist under `independent`, so group
count or `accepted` alone does not measure the optional optimizer's benefit.
Compare the actual independent and shared results under the same conditions.

The six fixture traces contain their Java source and one captured state each.
They exercise later-node references, aliases, cycles, self-loops, sibling fields,
and arrays. The harness covers nine combinations of these cases and string
styles. It also constructs 24- and 48-object scenes with two heap references per
object and one stack reference per four objects, giving 54 and 108 references.
Additional cases contain 12 and 48 stack references to one target, and 48 stack
references interleaved among 12 targets. These probe high fan-in and many small
potential groups. They do not carry a separately agreed performance threshold.

For each case the harness waits for Recursive fonts, measures six new visualizer
instances with warm assets, warms routing with five repaints, and records 40
repaints and 40 full redraws. It also counts bounding-rectangle reads during one
repaint. Full redraw includes value-box layout; neither measurement represents
cold loading or a complete execution-step transition. The reported maximum fresh
layout is the maximum of six samples, not a population percentile.

Public creation initially uses the historical default. For `independent` and
`shared`, each fresh-layout sample therefore includes that initial layout, the
internal policy change and its repaint, font readiness, and the final redraw.
Independent/shared fresh-layout comparisons share this setup cost. A historical
fresh-layout sample has no second policy solve, so it is not a like-for-like
measure of the optimizer's cost. Use the strict `independent` baseline for the
shared-policy comparison, and report this startup overhead with the 300 ms
fresh-layout gate. Warm repaint and full-redraw samples run under the already
selected policy and do not include policy selection. These figures do not predict
the cost of a hypothetical future default that starts directly in shared mode.

## Initial-policy layout experiment

`benchmarkRoutingInitialPolicy` is a separately named controlled experiment for
that first-solve cost. Compare both policies with this entry point:

```js
await benchmarkRoutingInitialPolicy({
  routingPolicy: 'independent',
  caseNames: ['dense-48'],
  includeTransitions: false,
  hardware: 'record processor, memory, and operating system',
  assetRevision: 'record checkout revision and bundle SHA-256',
});
await benchmarkRoutingInitialPolicy({
  routingPolicy: 'shared',
  caseNames: ['dense-48'],
  includeTransitions: false,
  hardware: 'same hardware description',
  assetRevision: 'same checkout revision and bundle SHA-256',
});
```

An untimed historical bootstrap creates and destroys one instance solely to
obtain the bundled connector-manager prototype. A temporary, diagram-scoped
`connect` wrapper selects the internal policy before each new manager's first
connection, then calls the original method exactly once. The production renderer
batches connection creation, so the first nonempty routing solve uses the
requested policy. The wrapper never suppresses a repaint or reuses bootstrap
geometry. It asserts that selection occurs before any connection exists and that
every measured nonempty manager receives the policy. Its work and the policy
setter's work remain inside each timed creation. Empty managers receive the
policy in the timed configuration step. A `finally` block restores the original
method, and the harness rejects overlapping runs on the same page.

This experiment still includes six complete public creations with warm assets,
font readiness, and final redraws. The bootstrap also warms historical rendering
code; it does not measure cold initialization. The report's `initialization.mode`
distinguishes `initial-policy` from the original `policy-switch` method and records
initialized-manager counts. Progress updates carry the same method label.

Report these fresh-layout results separately. They estimate startup with the
selected policy from the first connection, while `benchmarkRouting` measures the
existing public creation followed by a policy switch. A passing initial-policy
result does not erase a failing policy-switch result or change the existing
300 ms budget definition. Applying that threshold to this additional controlled
measurement must be stated explicitly. Compare `shared` with `independent` under
the same method, assets, and isolated runtime; neither historical-only timing nor
timing collected alongside another test process establishes the controlled gate.

## State and style transitions

The harness separately measures 40 samples each for assignment, object mutation,
backward stepping, and direct state restoration after five full-state warmup
sequences. These measurements include the state update and connector redraw.
It also measures a persistent color change followed by restoration as one paired
operation, and checks whether the original state's logical route geometry is
restored. These checks do not replace the full lifecycle, physical-paint, or export
tests. State/style transition measurements must not be reported as ordinary
redraw latency.

For a focused investigation, select existing names and optionally skip transitions:

```js
await benchmarkRouting({
  routingPolicy: 'shared',
  caseNames: ['aliases-default', 'fan-in-12', 'fan-in-48', 'many-groups-12x4'],
  includeTransitions: false,
});
```

The [routing guide](../../docs/reference-routing/README.md#validation-and-performance)
contains the accepted budgets and geometry requirements. Runtime results alone
cannot establish route readability or export correctness. Preserve raw results
with browser/hardware details when investigating a regression.

## Broader routing policy experiments

The evaluation helper replays measured rectangles through the production
connector manager. It loads isolated in-memory versions of the TypeScript
modules; it never edits production routing files. Run it after the frontend
development dependencies are installed, from the repository root:

```sh
node scripts/benchmark_reference_routing/evaluate-policies.cjs \
  --out .scratch/reference-routing-implementation/policy-evaluation.json
node scripts/benchmark_reference_routing/evaluate-policies.cjs \
  --routing-policy independent \
  --out .scratch/reference-routing-implementation/policy-evaluation-independent.json
```

The report compares the historical policy with four separately identified
interventions:

| Intervention | Question |
| --- | --- |
| Target-first source ordering | Does processing interleaved references by target improve lane allocation? Stack references still precede heap references. |
| Source-rank port ordering | Does ranking arrival candidates by source order improve approaches to shared targets? Existing validation still chooses admissible geometry. |
| Strict straight-route precedence | Does accepting a clear straight route before the bounded right-exit preference simplify paths? |
| Bounded local reconsideration | Can at most four source-priority proposals remove crossings or reduce detours without changing routes outside the affected neighborhood or worsening member length/turn counts? |

The helper uses nine captured scenes and two synthetic scenes that isolate
interleaved targets and a straight-route/right-exit tradeoff. Use
`--fixtures synthetic-interleaved,synthetic-straight` for a focused replay. It
records fixture/source hashes, routing failures, insertion-order equivalence,
the production `baselineOrdering` selector,
sampled complete route lengths, transverse centerline crossings, and turn-region
counts. Turn regions are a complexity proxy, not the shared-path admission bend
count. Curve sampling and text-hit checks supplement production validation; they
do not prove clearance. In-memory intervention anchors fail explicitly if the
source changes, so stale experiments cannot silently compare a different policy.
Source bytes are frozen in memory for each run, so concurrent edits cannot mix
router versions within that report.

The ordering selector describes the production crowded-baseline branch; the
separately named target-order intervention can also replace the ordinary
comparator in memory. Interpret those two fields together rather than treating
the selector as a label for every experimental comparator.

The default historical policy is an internal comparison, including its documented
implicit-overlap exceptions. Repeat with `--routing-policy independent` to assess
the controlled baseline before drawing conclusions about production applicability.
Historical results are not the validated independent baseline required to admit
shared paths. Node replay elapsed times
are diagnostic only: they do not establish browser budgets, CSS/font behavior,
native export correctness, or readability. Keep adopt/defer conclusions separate
from terminal-sharing acceptance, and retain raw reports under `.scratch/`.
