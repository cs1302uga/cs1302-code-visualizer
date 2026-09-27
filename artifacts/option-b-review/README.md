# Option B prototype review

The PDF combines twelve browser screenshots of approved Option B. PNG files in
`screenshots/` are the original, unmodified browser captures. The PDF hides unused
viewport whitespace through page clipping and includes navigation bookmarks.

Examples: Node chain, cycle, LinkBasedList, ArrayBasedList in both orientations,
both implementations after removal and clear, shared references, long/empty
strings in both orientations, and two dark-theme views.

These are reconstructed course memory snapshots and additional edge cases,
not screenshots of actual Java execution. Production implementation is pending.

Prototype commit: cc98e9c, branch prototype/string-style-option-b.
Capture date: 2026-09-27.

To rebuild the review PDF and ZIP from the captured screenshots, run
`uv run --extra review python artifacts/option-b-review/build_review.py`.
