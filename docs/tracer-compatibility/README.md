# Tracer 4.3 compatibility example

[Main.java](Main.java) demonstrates the date/time and set inspection supplied by
[tracer 4.3.0](https://github.com/cs1302uga/cs1302-tracer/releases/tag/v4.3.0).
The regression tests use this same source with both trace formats and consecutive
jobs in one reusable batch worker.

`meeting` refers to a `LocalDateTime` whose `date` and `time` fields refer to the
same objects as the two local variables. `original` retains the first `Duration`
when `elapsed` is reassigned. A duration of negative one nanosecond stores
`seconds = -1` and `nanos = 999999999`; the later value stores `seconds = 1` and
the same nanosecond component. These are stored components, without calls to
date/time getters. The additional fields and reachable objects consume tracing
heap and element budgets; unknown date/time layouts can remain opaque.

`backing`, `view`, and `second` refer to three distinct set objects. `alias` and
`view` refer to one wrapper. All three sets contain the same `item` reference and
`null` in insertion order, then acquire the final string when `backing` changes.
The wrapper prevents changes through its own interface; it remains a live view
of the mutable backing set. `item.value` also changes through the shared object.
Python Tutor represents these collections with `SET`; modern traces retain the
existing `kind: "array"` representation and their actual collection type labels.

After [contributor setup](../../CONTRIBUTING.md), generate a chronological modern
trace and render its final captured state from the repository root:

```sh
mkdir -p .scratch/tracer-compatibility
uv run generate_trace --format=modern -a < docs/tracer-compatibility/Main.java > .scratch/tracer-compatibility/modern.json
uv run generate_visualization --output .scratch/tracer-compatibility/modern.png < .scratch/tracer-compatibility/modern.json
uv run code-visualizer docs/tracer-compatibility/Main.java --format SVG --output .scratch/tracer-compatibility/example.svg
```

Change `--format=modern` to `--format=pytutor` to compare trace formats, or add
`--all-steps` to `generate_visualization` to inspect successive states. The
unified `code-visualizer` command traces the source and writes its final state
directly as SVG. Generated traces and exports belong under `.scratch/`.

Trusted collection inspection invokes `toArray()`. A guest exception or a null
result falls back to object fields; field-only and multithread inspection retain
raw fields. Input observation is paused during collection accessor calls, so
input consumed there can be absent from the logical input cursor, including
after later observed reads. Reader observation resumes when the accessor
finishes. See the [continuing compatibility exceptions](../known-exceptions.md)
and the [tagged upstream compatibility notes](https://github.com/cs1302uga/cs1302-tracer/blob/v4.3.0/CHANGELOG.md#unreleased).
