# Execution visualization

The visualizer presents program state as reference-valued locations, stack
frames, and heap objects connected by directed reference paths.

## Language

**Placement model**:
Rules that select the order, grouping, positions, or sizes of the visual elements
in a region of a program-state diagram.

**Layout**:
The spatial arrangement of stack frames, globals, heap objects, and the space
reserved around them for a rendered program state.

**Routing**:
The selection of directed connector paths between reference locations and their
targets in a layout.

**Layout repair**:
A bounded adjustment to the arrangement or reserved space made to resolve an
obstruction found while constructing reference paths.

**Supplied sequence**:
The ordered program states available to a visualization; the sequence may be a
complete execution trace or selected snapshots with omitted history.

**Canonical layout**:
A layout determined by a program state and its declared planning and presentation
conditions, independently of the order in which a reader visits states.

**Frame render key**:
An identifier used to associate a frame's visual representation with a supplied
state; it does not necessarily identify a method invocation throughout its life.

**Invocation identity**:
An identifier for one method invocation across the program states in which that
invocation exists.
