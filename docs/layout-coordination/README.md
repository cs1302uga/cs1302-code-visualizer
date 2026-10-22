# Layout coordination

This work separates placement and layout repair from connector path selection.
The first implementation preserves the current placement model and moves
bounded resizing, movement, canvas allocation, rollback, and retry ownership into
a layout coordinator. Stack and heap placement have independent strategy
interfaces so future approaches can change either region deliberately.

## Approved scope

Routing consumes measured geometry and returns a valid route plan or a
structured failure. The coordinator owns any geometric changes before another
routing pass. Initial stack and heap strategies preserve existing behavior;
global rearrangement is a separate proposal.

Future strategies may use prior states or the complete execution trace. The
design must accommodate alternative frame insertion, stable object lifetimes,
heap peak-set anchors, and forward or backward planning without making output
depend accidentally on the user's navigation history. A locally optimal state
does not establish an optimal sequence: the state, transition costs, and retained
history must support the claimed recurrence.

Production routing retains bounded search and explicit guarantees. Exact
Dijkstra or admissible A* on the same graph and cost model provides a comparison
oracle; this does not claim optimality over every geometric drawing.

## Work sequence

1. Audit current layout and routing algorithms, assumptions, and guarantees.
2. Research spatial and temporal alternatives, including two research cycles per
   theme and primary-source evidence.
3. Compare at least three coordinator interfaces and document the chosen design.
4. Implement bounded coordination and independent stack/heap placement strategies
   in reviewable stages.
5. Verify geometry, native exports, navigation stability, and performance.

Each completed step receives a pull-request comment recording results, decisions,
verification limits, and the records needed by the next step. Research findings
and implementation status are separate claims.

## Acceptance

Public rendered traces and native SVG/PNG exports remain the primary acceptance
boundary, supported by geometry replay. Verify frame insertion/removal,
cross-region coordination, direct seeking, backward navigation, restoration,
repair rollback, and cache invalidation where applicable.

The shared-reference work retains its original performance and visual-review
gates. This coordinator does not authorize default enablement, release, or issue
closure, and an architectural extraction alone does not establish a speedup.

## Related work

Issue [#27](https://github.com/cs1302uga/cs1302-code-visualizer/issues/27) and pull
request [#28](https://github.com/cs1302uga/cs1302-code-visualizer/pull/28) depend on
this prerequisite work. Issue #27 is an issue, not a pull request.

## Implementation boundaries

The per-visualizer [layout coordinator](../../cs1302_code_visualizer/frontend/js/layoutCoordinator.ts)
owns preparation, bounded repair, canvas allocation, rollback, and final paint.
The [placement controller](../../cs1302_code_visualizer/frontend/js/placementModels.ts)
selects independent stack/global and heap plans from the supplied sequence in
canonical order. Models receive their own canonical predecessor, current state,
settings, model versions, and measured boxes for both regions. They can propose
region effects without obtaining DOM nodes. The legacy heap adapter retains the
existing row heuristic and nudge/drag behavior; the legacy stack model retains
the existing Java frame order.

The [scene adapter](../../cs1302_code_visualizer/frontend/js/connectorScene.ts)
keeps DOM bindings beside the measured routing data. The
[router](../../cs1302_code_visualizer/frontend/js/connectorRouting.ts) consumes
only that data and returns a complete plan or a typed constraint. Reservation
retries do not move shapes. Geometric repairs are journaled by the coordinator
and followed by fresh measurement. Failure clears stale paint and restores
temporary repairs to the current state's sized, model-placed baseline; it does
not rewind semantic navigation.

The [grid search](../../cs1302_code_visualizer/frontend/js/orthogonalSearch.ts)
preserves horizontal/vertical arrival states, Manhattan length, an 18-unit axis
change cost, current heuristic weights, deterministic ordering, and pop caps.
Its independent Dijkstra oracle is restricted to at most 2,048 orientation-state
slots and the same graph objective. Endpoint stub turns, terminal stubs, heads,
rounding, and signed directions remain outside that objective. A bounded or
weighted production search does not establish global geometric optimality.

These are internal seams. The public rendering factory gains no new placement
or routing options. Future global strategies still need explicit identity,
context, objective, and verification contracts described in the
[design](design.md) and [research](research.md).

## Native review

Build the frontend, then follow the
[native review instructions](../../CONTRIBUTING.md#rendering-tests-and-benchmarks)
to capture the four frame-transition states in light and dark themes plus four
reference fixtures. The generated gallery and manifest distinguish native PNG,
native SVG, and separately reopened SVG raster evidence. Geometry replay and the
same-graph oracle support the public rendering checks; neither replaces them.
