# Coordinator interface comparison

Three independent designs explored different ownership and lifetime models.
These sketches describe interface shapes, not additional public factory options.
The [algorithm inventory](algorithm-inventory.md) and [research](research.md)
define the source observations and qualified algorithm guarantees.

## A single transaction

The first design exposes one operation:

```typescript
interface TransactionalCoordinator {
  transact(request: SettleRequest | RestoreRequest): LayoutResult;
}
```

For example, a redraw submits a settle request containing the selected state,
context, and expected geometry revision; destruction submits a restore request.
Independent stack and heap proposal functions produce data, while a private host
adapter applies effects, measures, routes, and commits or unwinds them.

This interface hides phase ordering and makes stale-result rejection explicit.
Its cost is a substantial request/result vocabulary and effect adapter. A small
method count alone does not make the data model small. Requiring complete semantic
DOM transactions would expand this repair extraction beyond its approved scope.

## A long-lived owner and region strategies

The second design binds a coordinator to one visualizer lifetime:

```typescript
interface RegionCoordinator {
  show(context: LayoutContext, step: number): LayoutOutcome;
  redraw(): LayoutOutcome;
  use(models: { stack?: StackPlacementModel; heap?: HeapPlacementModel }): void;
  dispose(): void;
}
```

For example, step navigation selects a state through `show`, while dragging,
font changes, or ordinary redraws settle the selected state through `redraw`.
The independent region strategies propose order, grouping, or placement. The
coordinator owns shared origins, measurements, bounded repair, and routing.

This shape matches the existing per-visualizer lifecycle and permits either
region model to change independently. Its state must have clear invalidation
and disposal rules. A hidden registry of arbitrary plugins or negotiation rounds
would be unnecessary in the first implementation; concrete legacy adapters are
preferable. Temporal reuse must depend on canonical context, not the last state
the user happened to visit.

## A compiled trace plan

The third design separates trace preparation, state resolution, and geometry:

```typescript
compileTrace(trace, { stackGlobals, heap }): TracePlan;
resolveStep(plan, step, settings): StepRecipe;
materialize(recipe, surface): Promise<LayoutOutcome>;
```

For example, loading a trace prepares one immutable program; seeking directly
to a state resolves its recipe and binds it to current measurements. Independent
providers can later prepare peak sets, canonical predecessors, and anchor-based
plans without storing accidental DOM coordinates in the semantic program.

This model is attractive for offline temporal planning and demand measurement.
It introduces more preparation and provenance machinery, and its asynchronous
materialization/full-view rollback would change the current synchronous caller
contract. Compiling topology does not eliminate font, content, occupancy, and
viewport dependencies. It is a future direction, not a requirement to implement
a timeline optimizer during a bounded-repair extraction.

## Selected synthesis

Use one long-lived coordinator with independent stack/global and heap strategies.
Borrow transactional repair ownership from the first design and the separation
of semantic trace context from measured geometry from the third. Preserve the
public synchronous lifecycle and existing placement policy.

The implementation has four boundaries:

1. Region models decide stack/global order and heap row/placement behavior. The
   legacy adapters retain Java ordering, predecessor-derived heap rows, the
   existing rightward nudge, and explicit drag restoration. Both models must be
   wired to real rendering paths; unused strategy declarations are insufficient.
2. A measurement adapter produces a coherent scene. Routing receives measured
   rectangles, attachments, identities, styles, and occupied paths, rather than
   obtaining new DOM geometry during a search.
3. Routing produces a complete route plan or a structured constraint failure.
   Bounded exhaustion is not proof of geometric impossibility. Reservation-only
   retries remain distinct from geometric repairs.
4. The coordinator applies resizing, movement, and canvas allocation, journals
   its writes, remeasures, and reroutes. It publishes paint only after the final
   accepted scene and restores owned repair writes on failure or reset.

The exact concrete signatures may follow the existing materialization seams;
the ownership and data boundaries above are the contract. Legacy semantic
templates and DOM creation need not become a new rendering framework. Private
legacy adapters may invoke existing materialization code; replacement models
must not need to copy the renderer or reach into another region's DOM.

For a normal render, the coordinator selects the region plans for the supplied
state, materialization applies them, sizing settles, and one scene is measured.
The router then returns a plan or a constraint. A covered source dot can produce
an owned blocker translation; the coordinator records the previous style,
applies that repair, and remeasures before another attempt. A failed attempt
never grants permission to paint a partially routed scene.

Rollback means restoring the current state's intrinsic, sized, model-placed
baseline and clearing stale route paint. It does not rewind semantic trace
navigation or promise reconstruction of the previously displayed state. Keep
the original repair priority and attempt bounds, while strengthening immediate
failure cleanup. Preserve explicit user offsets as input and keep their scope
distinct from temporary repair overrides.

## Trace context and future strategies

Expose the supplied sequence, selected index, model identity/version, measured
geometry, and available canonical context separately. Supplied snapshots are
not assumed to contain omitted execution history. A frame render key is not
automatically an invocation lifetime ID. A prior canonical plan is distinct from
an arbitrary previously visited DOM state.

Future stack models may change insertion order or region-wide placement. Future
heap models may use lifetime evidence, dimension catalogs, metric-tagged peak
sets, interval intersections, or forward/backward anchors. Both can return
region proposals that the coordinator reconciles before cross-region routing.
These extension points do not activate those algorithms now.

Any future cache must include the relevant trace/horizon, identity, options,
fonts, measurements, geometry, occupancy, model version, policy, and explicit
offset dependencies. Any finite-candidate DP must define sufficient state and
transition costs before claiming optimality. The first extraction adds no
navigation-seeded temporal cache and no global placement optimum.

## Routing comparison oracle

Keep current graph construction, neighbor order, source costs, axis-change cost,
heuristic weights, work caps, and candidate ranking. A DOM-free search seam lets
production A* and a small independent Dijkstra oracle consume the same graph.
Exactness is limited to that graph and cost, including its endpoint omissions;
painted geometry still requires validation. Sparse graph construction and
incremental search require later measured experiments.

## Verification

Check real production use of both region models, cross-region repairs, immediate
failure rollback, lifecycle cleanup, direct seeking/backward restoration,
measurement and policy changes, and the oracle's same-graph scope. Compare
rendered output and native PNG/SVG against the source-bound baseline. The
original controlled-policy startup/redraw gates remain PR #28 acceptance; the
current-main baseline is a separate refactor comparison.
