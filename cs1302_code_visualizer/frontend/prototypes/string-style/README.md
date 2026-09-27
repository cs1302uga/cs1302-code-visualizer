# String style — throwaway visual prototype

Option B approved by the user on 2026-09-27. This branch is the visual reference
for the implementation plan: `prototype/string-style-option-b`. Approval selects
the appearance; API migration and implementation scope are still being interviewed.

Run from the repository root:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory cs1302_code_visualizer/frontend
```

Open http://localhost:8765/prototypes/string-style/?variant=B

The checked-in frontend bundle supplies the existing renderer. No build is needed.
Use the bottom switcher or left/right keys for A (24/12 px), B (40 px minimum
width / 18 px gap), C (40/24 px), default, and inline. The gap is measured from
the box's right edge to the literal's left edge. String arrow tips stop 3 px
before the literal. A and C use 20 px box height. Refined B uses 19 px for
every value box, matching the array examples. All value boxes in each object,
stack frame, or array share one
width: at least 40 px including the added right padding, expanding to fit the
widest reference ID or non-string value plus padding and borders. Both borders align down the rows; horizontal array boxes
have equal widths. String literals do not affect box width. Non-string boxes
leave unused space to their right where necessary. Arrows remain vertically
centered, and B retains its 18 px gap.

Non-string reference arrows in B run strictly horizontally from their source
until 4 px inside the right border of the containing object, stack frame, or
array. They then curve to the original target. This routing is a local connector
instance override and recalculates on redraw/resize; compact string arrows keep
their existing short horizontal routes.

Backward heap references (including the cycle's closing edge) use rounded
external return lanes below the intervening objects, rather than cutting through
their contents. Lanes have 24 px lower clearance and 12 px separation when more
than one return is present. Source dots, initial horizontal exits, and target
arrowheads retain B's shared geometry. The panel reserves space for these lanes.

All B arrows use a filled 6 × 6 px triangular head without an inward notch.
Their shafts end at the midpoint of the triangle's rear edge, 6 px before the
tip. Curves approach that midpoint horizontally; tips remain at their targets.
String and non-string arrows share that geometry, a 1 px shaft, and a 3 px
source dot. A and C retain the native 5 × 7 px head with 0.55 foldback.
In B, every value box has 8 px additional right padding (14 px total), with its
width increased by 8 px to preserve content space (40 px minimum). Every source
dot sits 8 px inside the right border, centered vertically.
The target reference ID is left-aligned inside the box. Compact strings use the same
IDs as their heap objects in the default comparison view, including shared
identities. Box widths grow to fit IDs as well as other values. String and
non-string dots align down each object, frame, and vertical array; horizontal
arrays use the same inset placement in each component.

B labels every heap object with its concrete runtime type and snapshot reference
ID (`Node@10`, `ArrayBasedList@10`, `String[]@11`). Array lengths remain after the
identity label. The declared type of a reference variable, such as `List`, is
unchanged; it does not replace the object's concrete class. IDs are the fixture's
trace references, not Java identity hash codes.

Object-field labels and stack variable labels use a non-wrapping flex row with
baseline alignment, end justification, and a 0.25 rem gap between type and name.

The example, variant, array orientation, theme, and all-views toggle are preserved
in the URL. Diagrams remain at 100% scale with horizontal scrolling, so wider
variants cannot appear deceptively smaller. The footer measures stack/object
bounds after fonts settle.

Fixtures reconstruct states described by these local course pages:

- http://localhost:8000/java/adt-and-links/node-introduction.html
- http://localhost:8000/java/adt-and-links/list-interface.html
- http://localhost:8000/java/adt-and-links/examples-both-implementations.html

Node has String item and Node next. ArrayBasedList has int size and String[]
array (capacity five in these examples). LinkBasedList has int size and Node
head. The list variables use the course's custom List interface. Shared strings
and long/empty/quoted strings are additional stress fixtures. The Node cycle
fixture links Cheese → Bread → Milk → Cheese by assigning the last node's next
reference to head, exposing the return-arrow routing in all five views. These are memory
snapshots, not trace outputs from executing new Java programs. Default and inline
use the corresponding existing trace representations with the unmodified
renderer; compact changes only the local rendered DOM.

Confirmed visual rules: pairs stay inside their enclosing frame/object/array
component; null gets no arrow; literals do not wrap or truncate; shared strings
repeat locally in compact mode. Production API, tracing, exports, and deprecation
behavior are outside this prototype. After a prototype is approved, run the
requested second grilling session before proposing the implementation plan.

This directory is not a production entry point and is not imported by the bundle.
Preserved on the throwaway branch above as review evidence. Production code should
be implemented separately after the implementation interview and plan.
