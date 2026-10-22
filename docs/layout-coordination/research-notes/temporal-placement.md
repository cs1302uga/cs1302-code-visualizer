# Independent stack and heap placement over time

Research date: October 22, 2026. Assignment: spatial placement and mental-map stability; trace-aware temporal planning, dynamic programming (DP), and memoization. This is a research handoff, not an implementation or acceptance report. Only this note was written. No production edits, builds, tests, or Git writes were performed.

The controlling local brief preserves current placement and bounded repairs while creating independent stack and heap placement interfaces; global rearrangement requires a separate proposal. See [the repository brief](https://github.com/cs1302uga/cs1302-code-visualizer/blob/71ad672f7d89db4b497bb3c7e4cd21f2293d93d8/docs/layout-coordination/README.md#L3). The recommendations below respect that boundary.

Evidence labels: **published/manuscript result** means a claim made by a linked primary source, with its assumptions retained. **Repository observation** means static inspection of the cited local source. **Application inference** means an original derivation or proposed design for this project; it is not presented as an experimental finding or a theorem from a paper. Two complete search–synthesis–primary-reading cycles were completed for each theme; the reproducible search and access log is in section 3.

## 1. Spatial placement and mental-map stability

### Takeaway

Use separate stack and heap placement models, coordinated against a shared geometry and routing problem. Stability deserves an explicit objective, but the literature does not justify maximizing fixed positions at every cost or choosing a new stack order without evaluating the program-comprehension tasks it serves.

### Cited Findings

**Task-specific empirical support.** Archambault and Purchase's orientation experiment used 28 participants and tested locating previously indicated nodes and following paths through evolving graphs. Their mental-map-preserving condition produced faster answers and fewer errors on both tasks. Their conclusion explicitly limits the benefit to the nature of the task; this is evidence for orientation, not a Java stack/heap usability experiment (Archambault & Purchase, 2013b, §§3–6). [Primary author-uploaded full text](https://www.researchgate.net/publication/232747172_Mental_Map_Preservation_Helps_User_Orientation_in_Dynamic_Graphs).

**An apparent contradiction that must remain qualified.** The abstract of the same authors' review states that prior experiments had not conclusively established mental-map benefits for dynamic graph comprehension. The orientation paper, in contrast, reports positive results and distinguishes orientation from earlier readability and memorability tasks. The full review could not be fetched; consequently, its abstract must not be treated as refuting the orientation experiment or proving universal absence of benefit (Archambault & Purchase, 2013a, 2013b). [Review abstract and bibliographic record](https://research.monash.edu/en/publications/the-map-in-the-mental-map-experimental-results-in-dynamic-graph-d/); [orientation study](https://www.researchgate.net/publication/232747172_Mental_Map_Preservation_Helps_User_Orientation_in_Dynamic_Graphs).

**Constrained placement is an established mechanism.** Dwyer et al. describe application-specific placement constraints including alignment, containment, directional relationships, and non-overlap. Kieffer et al. distinguish soft alignment penalties from hard alignment constraints: soft terms can create local minima and do not guarantee exact satisfaction. Their grid-like placement paper explicitly leaves orthogonal bends to an extension or routing post-process; it is not itself a complete replacement router (Dwyer et al., 2008; Kieffer et al., 2013, §1). [Primary article abstract](https://eceasst.org/index.php/eceasst/article/view/1475); [primary full manuscript](https://arxiv.org/html/1308.6368v1).

**Separate stages can still influence one another.** Hegemann and Wolff's pipeline separates vertex placement, overlap removal, port assignment, routing, path ordering, and nudging. Its experiments report compactness advantages alongside cases with more crossings and bends than competitors. This is evidence for modular algorithms and competing objectives, not a guarantee that independently best stages compose into the best drawing (Hegemann & Wolff, 2023, §§1–3). [Primary full manuscript](https://arxiv.org/html/2309.01671v1).

**Routing optimality is conditional on geometry and cost.** Wybrow et al. compute object-avoiding orthogonal routes minimizing a monotonic function of length and bends for supplied shapes and connector points. Marriott et al. later reduce equivalent-route search using canonical obstacle-hugging representatives. Both work with a defined obstacle problem; neither supplies a theorem permitting unchanged routes under arbitrary new occupancy (Wybrow et al., 2009, §§1–5; Marriott et al., 2014, §§1–2). [Original routing manuscript](https://users.monash.edu/~mwybrow/papers/wybrow-gd-2009.pdf); [later primary paper](https://users.monash.edu/~mwybrow/papers/marriott-diagrams-2014.pdf).

**Repository observation.** `precomputeCurTraceLayouts()` already walks the complete trace, derives each heap row arrangement from the preceding arrangement, and removes empty rows. Its stored result is rows of object IDs, not measured coordinates, and the code's stated positional-invariance intention does not prove invariant rendered geometry. Stack rendering keys its D3 join with `frame.unique_hash` and appends entering frame elements. These are useful existing integration points, not evidence that a temporal geometric optimizer already exists. [Heap precomputation](https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1795); [predecessor copying](https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L1840); [empty-row removal](https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2221); [stack join](https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/pytutor.ts#L2692).

### Inferences

#### Independent region models, shared coordination

**Application inference.** The stack model should own frame order, frame placement, semantic ordering constraints, and any strategy-specific reservations. The heap model should own object placement, grouping, packing, and its temporal preferences. Each can propose a complete placement for its own region without embedding those choices in connector search. A coordinator must still resolve region origins and bounds, common measured geometry, source/target ports, reference routes, and bounded repair. Independent strategy interfaces do not imply an objective separable into independent stack and heap minima: cross-region edges couple their choices.

For a future optimization, a useful factorization is `Q(stack, heap, routes) = Qstack + Qheap + Qcross`, where `Qcross` contains reference costs, shared lanes, region separation, and any viewport cost. It is legitimate to optimize models independently and then coordinate as a heuristic; label it accordingly. Exact decomposition requires stronger assumptions about the coupling term, or explicit joint enumeration/optimization.

#### New active frame above versus below

**Application derivation under a fixed top origin.** Suppose there are `n` old frames, their dimensions remain unchanged, and a new frame has height `h` with interframe gap `g`. Inserting it above the old frames translates every old frame down by `delta = h + g`. The sum of old-frame vertical displacement is `n * delta`. Relative order and pairwise distances within the old stack remain unchanged, so this preserves some relational stability while changing absolute positions and every old stack reference's source coordinates.

Appending the active frame below leaves old frame coordinates unchanged under the same fixed-origin, fixed-size assumptions. It avoids that insertion-induced movement, but can move the active frame below the visible area, increase scrolling, and change the visual convention used to recognize the active call. This is a tradeoff to test, not a recommendation to flip the current default.

Neither conclusion is unconditional. Growth in an existing frame's locals can shift lower frames; a wide new frame can increase stack-column width and shift the heap origin; automatic fitting, centering, or rescaling can move both regions even when their internal placements are unchanged. A bottom-anchored or independently scrolling stack is another model with different consequences. Compare both local coordinates and settled screen coordinates, and record any camera transformation separately.

**Cross-region consequences.** Inserting above changes source-port heights for all surviving stack references while a fixed heap can keep target ports stationary. Appending below can leave old endpoints fixed, yet the new frame adds references and obstacles that may occupy existing channels. A longer stack or wider region boundary may alter lane availability and edge ordering. Neither stack order guarantees fewer crossings, shorter paths, or reusable routes. A shared route plan must be evaluated after both placements are known.

#### Stability and density need distinct measurements

**Application inference.** Measure absolute survivor displacement, relative-order changes, route changes, and active-frame visibility separately. A rigid translation of a stack can score poorly on absolute movement while preserving all internal relationships. For heap boxes, use hard non-overlap and text/port clearance constraints before soft area, aspect ratio, or edge-length preferences. Do not permit label shrinkage or illegible text as an unacknowledged way of improving density.

With fixed rendered box sizes, a possible occupancy density is `sum(box areas) / allocated region area`. That scalar omits reference crossings, lane clearance, offscreen content, and aspect ratio. A tightly packed drawing can obstruct routing; a drawing with room for readable references can have lower occupancy density. The objective must say whether it targets heap-only area, whole-diagram area, viewport fit, or total scroll extent.

#### Geometry reuse is conditional

**Application counterexamples.** In a width-2 container, a width-1 box centered on `[0.5, 1.5]` fits. Adding a second width-1 box cannot preserve the first position, although moving the first to `[0, 1]` makes room. Likewise, an inserted object can block an existing reference route while both endpoint objects remain fixed. Object identity and endpoint equality therefore do not establish reusable placement or routes.

Distinguish four operations: reusing measurements, reusing a feasible placement, reusing a valid route, and reusing an optimal solution. If boxes and incident edges are only removed, surviving dimensions/ports/coordinates and region constraints remain fixed, and no new requirements arise, the remaining old geometry stays feasible. Even in that restricted case, the compact or least-cost optimum can change. Adding occupancy requires validation against the new obstacle geometry or a previously proven reservation scheme.

A route cache key consequently needs relevant obstacle geometry, ports, widths/clearances, region constraints, routing policy, and any inter-route reservations; identities alone are insufficient. A reservation for the whole known trace can support conditional reuse, but may impose large empty areas and does not imply the reservation is best for density or readability.

### Gaps

No primary study found here compares top insertion with bottom insertion for Java stack/heap teaching diagrams. The orientation evidence supports a hypothesis, not a measured product benefit. No runtime behavior, current frame-order presentation, navigation invariance, or visual acceptance was tested during this assignment. The review's full text and the original mental-map paper's full text were inaccessible; fine-grained claims from those sources are deliberately omitted.

## 2. Trace-aware temporal planning, DP, and memoization

### Takeaway

A complete recorded trace permits deliberate planning across time, including object coexistence, changing dimensions, anchors, and future routing pressure. Exact sequence claims require a stated state space and objective; a bounded candidate DP can be exact over its candidates, whereas a chronological layout cache merely reproduces the algorithm that filled it.

### Cited Findings

**Offline linking differs from sequential anchoring.** Brandes and Mader compare aggregation, anchoring, and linking for dynamic undirected graphs using stress and vertex movement. Their linking method solves a coupled system across the sequence, rather than computing each layout one after another. Their results favor linking within the tested framework; they offer aggregate anchoring as a faster alternative and emphasize that other quality measures can matter. This is an algorithmic comparison, not proof of best orthogonal box placement or Java learning outcomes (Brandes & Mader, 2012, §§2, 4–5). [Primary full paper](https://kim246.wwwdns.kim.uni-konstanz.de/publications/bm-qcsma-12.pdf).

**Temporal regularization is a cost formulation, not automatic global sequence optimization.** Xu et al. add grouping and movement penalties to static graph-layout objectives, principally in an online setting using current and past snapshots. Their discussion of DGLL explicitly identifies nonconvexity and sensitivity to initialization. These methods support explicit temporal terms, without proving that a greedy per-step optimum minimizes a future-inclusive objective (Xu et al., 2012, §§1, 3.3). [Primary full manuscript](https://arxiv.org/html/1202.6042v1).

**Foresight has direct algorithm-animation precedent.** Diehl et al.'s verified abstract describes a foresighted layout using a static layouter as a parameter and names algorithm animation as an application. The PDF's extracted body is corrupted, so detailed claims about its contraction construction or guarantees are not used here (Diehl et al., 2001). [Primary author-hosted paper and indexed abstract](https://ivis.itn.liu.se/pubs/docs/VisSym01.pdf).

**Known lifetimes can save space, but temporal constraints can conflict.** Skambath and Tantau show examples where a union drawing wastes space because nodes do not coexist. For their dynamic-tree model, an acyclic supergraph permits a linear-time algorithm meeting specified ranking, ordering, centering, weak-symmetry, and stability criteria. The decision version of minimizing temporal cuts needed to obtain an acyclic supergraph is NP-complete. These are model-specific results, not a complexity classification of this visualizer's placement problem (Skambath & Tantau, 2016, §1; Theorems 3.1–3.2). [Primary full manuscript](https://arxiv.org/html/1608.08385v1).

**DP requires sufficient state.** Bertsekas develops finite-horizon DP and deterministic shortest-path formulations, then explains state augmentation for effects depending on earlier states or controls. His guideline retains information useful to subsequent decisions and warns that augmentation can make the state space intractable. The relevant source portions were read directly from the author-hosted PDF stream after the web tool rejected its size (Bertsekas, 1987, ch. 1, especially §§1.2–1.5, pp. 41–46). [Primary author-hosted book](https://web.mit.edu/dimitrib/www/Bertsekas1987DP.pdf).

### Inferences

#### Full-trace analysis: observed presence, identity, and dimensions

**Application proposal.** Build a trace index before attempting global placement. For each identity record the steps where it is captured, the steps where it is actually displayed after reachability/filtering/compact rendering, measured or reproducibly estimated dimensions at those steps, references and ports, and birth/disappearance/reappearance events. Preserve the difference between a heap entry and a top-level displayed box: compact or nested rendering can change which objects occupy independent regions.

Use the terms **observed capture interval** and **display interval** unless the tracer actually supplies allocation/deallocation or garbage-collection evidence. First and last appearance in a sampled/truncated trace do not prove real allocation and death. A first-to-last span with gaps is a conservative reservation interval, not evidence of continuous visibility. A later reappearance should be matched by durable object identity, subject to an explicit upstream guarantee against ID reuse or an allocation-generation discriminator.

**Repository identity limitation.** `ModernHeapObject` carries an ID, but the adapter's `ModernFrame` interface has no invocation ID. It currently constructs `frame_id` from the array index and `unique_hash` from method name, line, and index. That hash can change when the same invocation changes line; a depth/index can also be reused by later calls. It is insufficient as a guaranteed temporal invocation identity. Prefer upstream invocation IDs; any inference from call/return events must state what recursion, exceptions, sampling, and missing events permit. This is a prerequisite for future temporal matching, not an instruction to change the adapter in the first implementation. [Frame interface](https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L19); [constructed keys](https://github.com/cs1302uga/cs1302-code-visualizer/blob/b6b2e2b9a0593662ac336016706809151cfa1c04/cs1302_code_visualizer/frontend/js/modernTraceAdapter.ts#L219).

Dimensions are step-dependent: `w(i,t), h(i,t)`. Stable object identity does not make a mutable object or its rendered label constant-sized. Reserving each object's maximum width and maximum height across its lifetime can prevent some resizing, but may reserve a width/height combination that never actually occurs together and substantially reduce density. Fonts, string mode, array orientation, visibility, and viewport assumptions belong in the geometry context.

#### There is no objective-independent maximum heap

**Application derivation.** Let `O_t` be the displayed heap identities, and let box dimensions include the chosen box padding. Define:

```text
N_t    = |O_t|
Wsum_t = sum over i in O_t of w(i,t)
Hsum_t = sum over i in O_t of h(i,t)
Asum_t = sum over i in O_t of w(i,t) * h(i,t)
```

These demand metrics can all peak at different steps. Four snapshots illustrate this without any layout algorithm:

- Four `1 x 1` boxes give `(N, Wsum, Hsum, Asum) = (4, 4, 4, 4)`.
- One `10 x 1` box gives `(1, 10, 1, 10)`.
- One `1 x 10` box gives `(1, 1, 10, 10)`.
- Two `4 x 4` boxes give `(2, 8, 8, 32)`.

The maximizing identity sets can be disjoint and incomparable by inclusion. Even two cardinality maxima may be different sets. Distinguish maximum cardinality, inclusion-maximal sets, geometric demand peaks, and the union of all observed objects. None is a universal substitute for the others.

`Wsum` describes width demand for a single-row arrangement before gaps; `Hsum` similarly describes a single column. `Asum` lower-bounds the area needed for disjoint boxes, but does not include routing channels, region gaps, external labels, or packing inefficiency. It does not determine a feasible width/height pair. For a completed drawing, distinguish `max_t(width_t * height_t)` from `(max_t width_t) * (max_t height_t)`: their maxima need not occur at the same step.

Retain all tied peaks or a documented representative of each plateau. A Pareto frontier of `(N, Wsum, Hsum, Asum, route demand)` can supply candidates, but remains a heuristic for selecting anchors unless related to the actual objective. A nonpeak frame can be hardest to route because of topology, port positions, or a narrow stack/heap corridor.

#### Ordered peak-set intersections and bidirectional anchors

**Application proposal.** Keep anchor times in chronological order. For candidate peaks at `a_1 < ... < a_k`, write `P_j = O_(a_j)`. Adjacent intersections `P_j intersect P_(j+1)` identify possible bridges. For example, `{a,b}`, `{b,c}`, `{c,d}` have bridges `{b}` then `{c}`, while their all-peak intersection is empty. Collapsing the sequence to one global intersection loses those bridges.

Endpoint intersection alone does not prove uninterrupted displayed presence. For an interval `[a,b]`, explicitly compute `I_(a,b) = intersection of O_t for every t in [a,b]`, or prove the relevant identities have contiguous display intervals. Even `I_(a,b)` establishes only co-presence, not fixed dimensions, ports, references, route feasibility, or unchanged optimal positions.

A proposed planner can generate alternative full anchor states, seed surviving objects consistently, plan forward from a left anchor and backward from a right anchor, then reconcile the interior. If the two complete boundary states are fixed and the state is sufficient for the objective, an interval DP is exact **conditional on those anchors and candidates**. Choosing one cardinality-peak layout first and interpolating/repairing toward it does not establish a globally optimal sequence.

For finite candidate states, bidirectional messages can be made exact. Let `F_t(s)` include costs through state `s`, and let `B_t(s)` include costs strictly after it. Then `min_s(F_t(s) + B_t(s))` combines the same full state space without double counting. Agreement on box coordinates alone is insufficient if routes, reservations, or retained history differ. Optimizing anchor choices jointly is possible using interval costs as macro-transitions only when those costs faithfully preserve all boundary-state dependencies. Straight interpolation between valid endpoint layouts must also be collision-checked if animated intermediate geometry matters.

#### A concrete bounded candidate DP

**Application model and derivation, inspired by the cited DP framework.** Fix a finite trace, configuration, measurement context, and optimization horizon. At each time `t`, generate a finite set `C_t` of feasible candidate states. A state can contain:

- Stack frame placements and the matching identities required for movement costs.
- Heap placements and region origins/bounds.
- Ports and routes, or a sufficient route representation for future cost/feasibility.
- Any additional history that changes future decisions: persistent slot/lane reservations, last-seen positions, movement budgets, or earlier states needed for higher-order smoothness.

If routing is a deterministic function of placements and fixed geometry, and there is no route-history-dependent cost or reservation, routes may be derived rather than stored as independent state. If several routes with equal current cost have different future movement costs, collapsing them to one route can discard the best sequence.

Let `q_t(s)` measure within-step quality, with hard infeasibility represented by infinity. Let `m_t(r,s)` measure the transition, including survivor displacement and any route/port changes. With start cost `i(s)` and terminal cost `z(s)`, define:

```text
D_0(s) = i(s) + q_0(s)
D_t(s) = q_t(s) + min over r in C_(t-1) of [D_(t-1)(r) + m_t(r,s)]
answer = min over s in C_(T-1) of [D_(T-1)(s) + z(s)]
```

Retain backpointers and deterministic tie-breaking to reconstruct the selected sequence. A minimal proof is substitution: if two prefixes end in the same sufficient state, they permit the same future completions with the same incremental costs. Replacing the more expensive prefix by the cheaper one therefore cannot hurt any completion. If that premise fails, keeping just one best prefix per state is unsound.

**Counterexample to independent step optimization.** At step 0, layout A costs 0 and layout B costs 1. At step 1, only B is feasible. Transition A→B costs 10, while B→B costs 0. Independently optimal frames cost 10 overall; choosing the locally worse B at step 0 costs 1. The failure occurs even with unique, exactly solved local optima.

**Sufficient-history assumptions.** First-order DP works when the state captures all future-relevant choices and costs are additive over adjacent transitions. Penalizing acceleration needs another previous layout or velocity state. Matching a reappearing hidden object to its last position needs that last-seen position. A persistent movement budget or slot allocation needs its remaining budget or allocation state. Long-range coupling across many timeslices is not automatically a first-order recurrence; retain the needed window/statistics or solve the larger coupled problem.

If an objective combines accumulated movement and a maximum envelope over the sequence, two prefixes ending at the same geometry may have different relevant tradeoffs. Retain sufficient accumulated bounds or nondominated labels. A pure bottleneck objective can instead use a `max` recurrence; it need not retain the whole path. Weighted sums require chosen units and weights; lexicographic objectives require a compatible comparison and recurrence. The number of goals alone does not prove a particular DP correct.

**Complexity and exactness boundary.** With at most `K` candidates per step and pairwise costs, DP takes `O(T*K^2)` transition evaluations, `O(K)` working scores, and `O(T*K)` backpointers, excluding candidate generation, geometry storage, and evaluation cost. If candidates are combinations of `Kstack`, `Kheap`, and `Kroute`, their joint count can approach the product. Even `m` boxes choosing among `L` positions admit `L^m` assignments before routing alternatives. Arbitrary real coordinates create a continuous state space; discretization is an approximation unless its sufficiency is proved.

A beam search, pruned candidate set, or fixed candidate budget can control cost, but its guarantee is conditional on what remains. Candidate generation dependent on only one previously chosen layout may silently omit valuable alternatives. Report exactness as “minimum over these candidate states and transitions,” not “globally optimal layout.” The local brief's exact-routing oracle has the analogous same-graph/same-cost limitation. [Local guarantee boundary](https://github.com/cs1302uga/cs1302-code-visualizer/blob/71ad672f7d89db4b497bb3c7e4cd21f2293d93d8/docs/layout-coordination/README.md#L23).

#### DP, memoization, and canonical navigation are different contracts

**Application distinction.** Memoization reuses a result for an equivalent subproblem. Caching a greedy layout does not introduce competing predecessors, a cost-to-go, or an optimality proof. A DP can use memoization or bottom-up tabulation, and a cache can store a DP's chosen plans; these are compatible mechanisms with different purposes.

Require a settled-state contract of the form `L_t = F(trace revision, configuration, measurement context, strategy version, horizon, t)`. Forward stepping, backward stepping, direct seek, and random seek must yield the same canonical placements and routes at `t` under that key. Trace history can affect `F`; the user's visit order must not accidentally affect it. A “stay close to the currently displayed frame” rule can choose different layouts when approaching the same target from opposite directions.

Valid approaches include a deterministic whole-trace plan, or deterministic chronological replay from checkpoints containing sufficient state. A cache miss must reconstruct the canonical predecessor/plan, rather than seed itself from an arbitrary visited frame. Stable candidate order, stable identity matching, deterministic ties, and a defined measurement context are necessary. Animation can take different transient paths while settled canonical geometry remains the same; state explicitly which is tested.

Configuration/geometry changes require invalidation or revalidation. If future frames influence earlier layouts, appending to the trace can change those earlier layouts, so the trace horizon/revision must be part of the contract. A checkpoint of row order alone cannot reproduce a planner that also retains last-seen positions, routes, or reservations.

### Gaps

No primary source reviewed establishes this project's particular peak-set heuristic or a polynomial-time global optimum for variable-size stack/heap boxes with constrained references. The recurrence above is an explicit original finite-state model, not a published implementation. No experiment here selects density weights, anchor frequency, candidate count, movement metric, or a stable frame-identity reconstruction rule. Search found a DP-based local-search paper for dynamic bipartite drawing, but its primary text was not verified; it is excluded as evidence for a general temporal-layout guarantee.

## 3. Integration, confidence, experiments, and provenance

### What the architecture should enable now

**Application recommendation within the approved brief.** Keep current bounded repairs and initial placements. Give stack and heap strategies independent interfaces and let the coordinator own measured geometry, route/repair attempts, rollback, and retry limits. Routing should consume a coherent geometry snapshot and return a plan or structured failure. This follows the repository's explicit scope; it does not require implementing global planning now. [Approved behavior and ownership](https://github.com/cs1302uga/cs1302-code-visualizer/blob/71ad672f7d89db4b497bb3c7e4cd21f2293d93d8/docs/layout-coordination/README.md#L3).

The seam should permit an immutable trace/context handle, stable identity metadata when available, optional prior canonical state, and an optional precomputed plan handle. Define whether each strategy is stateless, chronological, or whole-trace. Associate measured geometry and plans with a revision so repair/rollback cannot paint a route calculated against a different obstacle state. These are enabling contracts, not a requirement to add a temporal cache, reserve lifetime maxima, or pass mutable DOM objects between planners.

Keep alternative frame ordering, global heap packing, lifetime reservations, peak-set anchors, backward/forward planning, and bounded candidate DP in a separate future design proposal. That proposal must choose an objective, candidate strategy, identity prerequisites, invalidation policy, and performance budget. Architectural extraction alone establishes neither speedup nor readability improvement. [Research/implementation distinction and acceptance boundary](https://github.com/cs1302uga/cs1302-code-visualizer/blob/71ad672f7d89db4b497bb3c7e4cd21f2293d93d8/docs/layout-coordination/README.md#L37).

### Contradictions and confidence

**High confidence in qualified literature statements:** primary orientation results, explicit constrained-placement mechanisms, fixed-geometry routing scope, offline coupling versus online penalties, and the stated dynamic-tree theorem conditions. **High confidence in the original counterexamples and finite-candidate recurrence under its assumptions:** maxima are incomparable; local optima need not minimize a sequence; sufficient state is essential; identity alone does not establish reusable geometry.

**Moderate confidence in architectural direction:** independent region models with shared coordination fit both the local scope and modular layout research. **Unestablished product hypotheses:** bottom-appended frames improve Java comprehension; a particular density metric improves usability; peak anchors beat greedy layouts; trace-wide planning pays for its preprocessing. Treat each as a proposed experiment.

The important tensions remain visible: stability versus compactness/readability; fixed union slots versus lifetime reuse; separate region strategies versus cross-region reference costs; offline sequence quality versus preprocessing and state-space size. Brandes and Mader's preference for linking is limited to their stress/movement experiment; it does not override orthogonal-routing or text-clearance requirements. The dynamic-tree NP-completeness theorem cannot be transferred to this product without a reduction and a defined decision problem.

### Next experiments, deliberately not run in this research task

1. Compare new active frame above and below using the same trace, fixed typography, and explicit camera policy. Measure old-frame movement in region and screen coordinates, active-frame visibility/scrolling, heap-origin movement, and reference rerouting. Include recursive calls, returns, wide new frames, and changing old-frame heights.
2. Construct traces whose cardinality, width-sum, height-sum, and area-sum peaks differ; include tied peaks, plateaus, mutable dimensions, noncoexisting objects, and hidden/reappearing objects. Measure box demand separately from packed region bounds and route clearance.
3. Compare greedy chronological layout, a fixed union reservation, ordered peak anchors, and exact finite-candidate DP on small instances using identical candidate sets and objectives. Report objective regret against that restricted oracle; matching tested cases is empirical support, not a proof for unrestricted geometry.
4. Evaluate anchor sensitivity: adjacent-intersection bridges with an empty global intersection, different anchor candidates, a route-critical nonpeak, and planning from both endpoints. Test whether macro-transitions retain enough history and whether anchors can be revised.
5. Exercise cross-region pressure: high alias fan-out, cycles, dense fields, constrained target ports, equal-cost route alternatives, and a newly blocked corridor with unchanged endpoints. Track total and maximum movement, bends/crossings, route changes, hard failures, repair count, and rollback integrity.
6. Compare canonical plan serialization under forward, backward, direct, and randomized visits, cold caches, eviction, font/viewport/filter changes, and trace extension. Include placements, routes, ports, and reservation/history state; transient animation screenshots alone are insufficient.
7. Record preprocessing latency, per-step latency, memory, candidate/transition counts, and time spent measuring, routing, and repairing. After mechanical feasibility, run representative teaching tasks—follow a reference, revisit an object, identify the active invocation, and distinguish object mutation from layout movement—with an appropriate human evaluation.

### Two-cycle search and synthesis log

All searches were conducted on October 22, 2026 using `web.run`; exact query strings are retained below. The academic protocol requests a landscape result count of 20, but the available API exposes no result-count argument. Broad searches used long responses and multiple query formulations; no claim of exactly 20 results or exhaustive literature coverage is made. Fifteen web calls covered search, full-text retrieval, focused finds, and unsuccessful PDF screenshot attempts. One additional read-only streamed fetch recovered the oversized Bertsekas source without writing a download.

**Spatial cycle 1 — landscape.** Queries: `dynamic graph drawing mental map stability readability evaluation`; `orthogonal graph drawing constraints incremental layout stability`; `dynamic graph layout node placement preserve mental map user study`. Primary retrieval targets were the [2013 review](https://www.sciencedirect.com/science/article/pii/S107158191300102X), [1995 mental-map paper](https://www.sciencedirect.com/science/article/pii/S1045926X85710105), [2023 pipeline](https://arxiv.org/html/2309.01671v1), and [foresighted layout](https://www.st.uni-trier.de/diehl/pubs/VisSym01.pdf). **Synthesis before the next search:** evidence mixed movement stability with task/readability effects; a universal freeze-everything objective was not justified. The pipeline suggested separate placement/routing stages, with possible cross-stage tradeoffs. Gaps were full empirical methods and constraint/route guarantee scope.

**Spatial cycle 2 — targeted primary investigation.** Queries: `Archambault Purchase 2012 mental map revisitation paths dynamic graph drawing author pdf`; `Dwyer Marriott Wybrow 2009 fast simple constraint-based graph layout incremental separation constraints pdf`; `Wybrow Marriott Stuckey 2010 orthogonal connector routing pdf`; `Misue Eades Lai Sugiyama Layout Adjustment Mental Map 1995 pdf`. Read [Kieffer et al.](https://arxiv.org/html/1308.6368v1), the [Dwyer abstract](https://eceasst.org/index.php/eceasst/article/view/1475), [Marriott et al.](https://users.monash.edu/~mwybrow/papers/marriott-diagrams-2014.pdf), and later the [original routing manuscript](https://users.monash.edu/~mwybrow/papers/wybrow-gd-2009.pdf). Follow-up queries were `"Mental Map Preservation Helps" filetype:pdf` and `"The Map" "mental map" Archambault Purchase pdf 2013`; read the [author-uploaded orientation paper](https://www.researchgate.net/publication/232747172_Mental_Map_Preservation_Helps_User_Orientation_in_Dynamic_Graphs) and [institutional review abstract](https://research.monash.edu/en/publications/the-map-in-the-mental-map-experimental-results-in-dynamic-graph-d/). **Re-evaluation:** orientation has positive primary evidence; blanket comprehension claims remain unjustified. Hard/soft constraints and fixed-obstacle route optimality have different guarantees. The original orientation chapter is published in 2013 although its conference was GD 2012 and the hosting page labels it September 2012.

**Temporal cycle 1 — landscape.** Queries: `dynamic graph drawing offline temporal global optimization foresighted layout`; `dynamic graph drawing temporal optimization dynamic programming layout sequence`; `Brandes Mader 2012 quantitative comparison dynamic graph drawing stability linking anchoring`. Retrieve [Brandes and Mader](https://kim246.wwwdns.kim.uni-konstanz.de/publications/bm-qcsma-12.pdf), [Xu et al.](https://arxiv.org/html/1202.6042v1), [Skambath and Tantau](https://arxiv.org/html/1608.08385v1), and the [Trier research project](https://www.uni-trier.de/universitaet/fachbereiche-faecher/fachbereich-iv/faecher/informatikwissenschaften/professuren/softwaretechnik/forschung/projekte/dynamic-graph-drawing). **Synthesis before targeted searches:** full-trace knowledge creates an offline opportunity; temporal penalties and joint sequence optimization are different algorithms. Union slots can waste space. Existing row precomputation is relevant infrastructure, not proof of global geometric planning. Missing pieces were sufficient DP state and any actual guarantee for peak anchoring.

**Temporal cycle 2 — targeted primary investigation.** Queries: `"Foresighted Layout" "Diehl" "Görg" 2001`; `"A Quantitative Comparison" "Brandes" "Mader" pdf offline`; `"On the Theory of Dynamic Programming" Bellman 1952 716`; `"Mental Map Preservation Helps User Orientation" pdf swansea`. Follow-ups: `"bm-qcsma-12.pdf"`; `"dynamic graph drawing" "dynamic programming" layout temporal`; `"A dynamic programming-based local search algorithm" "dynamic bipartite"`; `"Bertsekas" "state augmentation" "history" dynamic programming pdf`; `"Brandes" "Mader" "99–110" kops 2012`; `Bertsekas dynamic programming state augmentation chapter 1` restricted to `web.mit.edu`; and `"A dynamic programming-based local search" "582" "601"` restricted to `sciengine.com` and `scichina.com`. Read the eventual full Brandes PDF, its linking formulation and conclusion, the dynamic-tree theorem statements, Xu's nonconvexity discussion, the foresighted abstract, and Bertsekas ch. 1. **Final synthesis:** a sufficient finite-state DP is a defensible restricted oracle; peak/intersection selection and reduced candidate generation are application heuristics until proved or evaluated. Full object presence/size/identity information and deterministic reconstruction are prerequisites, not optional cache details.

**Access failures and restrictions retained.** ScienceDirect full-text requests returned 403. Swansea repository variants timed out or returned 403. The initial Brandes fetch timed out, but a later fetch of the same primary URL succeeded. The foresighted paper's alternate [author-hosted PDF](https://ivis.itn.liu.se/pubs/docs/VisSym01.pdf) fetched with corrupted text; screenshot calls first reported `Unable to resolve screenshot call because content type is not application/pdf and web screenshot is not enabled`, and later attempts produced no inspectable image. Its body was therefore not used. Bellman's [1952 PMC record](https://pmc.ncbi.nlm.nih.gov/articles/PMC1063639/) verified metadata, but its PDF returned a download interstitial; the [1954 AMS PDF](https://www.ams.org/journals/bull/1954-60-06/S0002-9904-1954-09848-8/S0002-9904-1954-09848-8.pdf) returned 403, and a 1952 mirror returned 502. These Bellman sources are bibliographic leads, not relied-on full-text evidence. A guessed alternate Konstanz URL and guessed ECEASST PDF URL were inaccessible; the verified primary URLs above supersede them. The verified ECEASST PDF-view link exposed no article text, so only its abstract supports the stated finding. The MIT PDF exceeded the web tool's 12,173,638-byte limit; `curl` streamed it to `pdftotext` and printed selected ch. 1 passages and title/copyright metadata without saving another file.

**Repository provenance and independent critique.** Static reads covered `AGENTS.md`, `CONTRIBUTING.md`, the local layout-coordination brief, heap precomputation and stack joins in `pytutor.ts`, `ModernFrame` and constructed IDs in `modernTraceAdapter.ts`, and focused routing/geometry references. A separate read-only reasoning audit supplied counterexamples and checked the DP/anchor/cache assumptions; its output was analytical review, not external evidence. No production behavior or research algorithm was executed. No prior-memory facts are relied on in this note.

### APA reference details

Archambault, D., & Purchase, H. C. (2013a). The “map” in the mental map: Experimental results in dynamic graph drawing. *International Journal of Human-Computer Studies, 71*(11), 1044–1055. [https://doi.org/10.1016/j.ijhcs.2013.08.004](https://doi.org/10.1016/j.ijhcs.2013.08.004). Accessed via the linked institutional abstract; full review not verified.

Archambault, D., & Purchase, H. C. (2013b). Mental map preservation helps user orientation in dynamic graphs. In W. Didimo & M. Patrignani (Eds.), *Graph drawing* (Lecture Notes in Computer Science, Vol. 7704, pp. 475–486). Springer. [https://doi.org/10.1007/978-3-642-36763-2_42](https://doi.org/10.1007/978-3-642-36763-2_42). GD 2012 conference; 2013 proceedings. [Full author-uploaded manuscript](https://www.researchgate.net/publication/232747172_Mental_Map_Preservation_Helps_User_Orientation_in_Dynamic_Graphs).

Bertsekas, D. P. (1987). *Dynamic programming: Deterministic and stochastic models*. Prentice-Hall. [Author-hosted full book](https://web.mit.edu/dimitrib/www/Bertsekas1987DP.pdf). ISBN 0-13-221581-0; relevant ch. 1 content and copyright/publisher metadata verified by streamed extraction.

Brandes, U., & Mader, M. (2012). A quantitative comparison of stress-minimization approaches for offline dynamic graph drawing. In M. van Kreveld & B. Speckmann (Eds.), *Graph drawing* (Lecture Notes in Computer Science, Vol. 7034, pp. 99–110). Springer. [https://doi.org/10.1007/978-3-642-25878-7_11](https://doi.org/10.1007/978-3-642-25878-7_11). [Full primary manuscript](https://kim246.wwwdns.kim.uni-konstanz.de/publications/bm-qcsma-12.pdf). Conference GD 2011; 2012 proceedings.

Diehl, S., Görg, C., & Kerren, A. (2001). Preserving the mental map using foresighted layout. In D. S. Ebert, J. M. Favre, & R. Peikert (Eds.), *Data visualization 2001* (pp. 175–184). Springer. [https://doi.org/10.1007/978-3-7091-6215-6_19](https://doi.org/10.1007/978-3-7091-6215-6_19). [Primary PDF](https://ivis.itn.liu.se/pubs/docs/VisSym01.pdf); only verified abstract used.

Dwyer, T., Marriott, K., & Wybrow, M. (2008). Interactive, constraint-based layout of engineering diagrams. *Electronic Communications of the EASST, 13*. [https://doi.org/10.14279/tuj.eceasst.13.168](https://doi.org/10.14279/tuj.eceasst.13.168). [Primary abstract](https://eceasst.org/index.php/eceasst/article/view/1475).

Hegemann, T., & Wolff, A. (2023). *A simple pipeline for orthogonal graph drawing* [Preprint]. arXiv. [https://arxiv.org/abs/2309.01671](https://arxiv.org/abs/2309.01671). Full v1 manuscript reviewed; later publication status not established here.

Kieffer, S., Dwyer, T., Marriott, K., & Wybrow, M. (2013). *Incremental grid-like layout using soft and hard constraints* [Preprint]. arXiv. [https://arxiv.org/abs/1308.6368](https://arxiv.org/abs/1308.6368). Full v1 manuscript reviewed; it notes acceptance for GD 2013. Proceedings metadata not needed for the cited manuscript.

Marriott, K., Stuckey, P. J., & Wybrow, M. (2014). *Seeing around corners: Fast orthogonal connector routing* [Author manuscript]. [https://users.monash.edu/~mwybrow/papers/marriott-diagrams-2014.pdf](https://users.monash.edu/~mwybrow/papers/marriott-diagrams-2014.pdf). Title/authors and full text verified; final volume/pages/DOI not verified, so not invented.

Skambath, M., & Tantau, T. (2016). *Offline drawing of dynamic trees: Algorithmics and document integration* [Preprint]. arXiv. [https://arxiv.org/abs/1608.08385](https://arxiv.org/abs/1608.08385). Full v1 manuscript and theorem statements reviewed.

Wybrow, M., Marriott, K., & Stuckey, P. J. (2009). *Orthogonal connector routing* [Author manuscript for GD 2009]. [https://users.monash.edu/~mwybrow/papers/wybrow-gd-2009.pdf](https://users.monash.edu/~mwybrow/papers/wybrow-gd-2009.pdf). The later chapter is indexed at pp. 219–231 in LNCS 5849, [https://doi.org/10.1007/978-3-642-11805-0_22](https://doi.org/10.1007/978-3-642-11805-0_22); hosting metadata varies between conference and proceedings dates, so the citation above identifies the reviewed manuscript rather than silently conflating them.

Xu, K. S., Kliger, M., & Hero, A. O., III. (2012). *A regularized graph layout framework for dynamic network visualization* [Preprint]. arXiv. [https://arxiv.org/abs/1202.6042](https://arxiv.org/abs/1202.6042). Full v1 manuscript reviewed; the citation identifies that version rather than an unverified later publication.
