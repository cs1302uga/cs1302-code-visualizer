# Separate placement strategies and transactional repair ownership

Use independent stack/global and heap placement models under a per-visualizer
layout coordinator. Routing consumes measured geometry and reports a plan or
constraint failure; the coordinator owns bounded movement, resizing, canvas
allocation, and repair rollback. This keeps cross-region geometry coherent while
allowing future placement approaches to change either region deliberately.

Preserve the existing synchronous public lifecycle and initial placement policy.
Choose the long-lived strategy design with a repair transaction over a required
compiled trace program or full semantic-view transaction. Rollback restores the
current state's intrinsic layout and clears stale paint; it does not rewind
semantic navigation. Supplied-sequence context and measured geometry stay
separate so later temporal strategies can reconstruct canonical states without
using arbitrary navigation history as a cache seed.

See the [interface comparison](../layout-coordination/design.md) and
[research qualifications](../layout-coordination/research.md). No global
rearrangement, temporal optimality, automatic sharing enablement, or performance
acceptance follows from this architectural decision.
