# Example 2: Complex Object Graphs & References

This example demonstrates nested object references and associations on the heap.

## Concepts Illustrated

- **Object References**: `CourseOffering` references a `Person` instructor instance and a `Semester` enum.
- **Reference Resolution**: Multi-level pointer relationships traced across the heap.

## Files

- `Driver.java`: Instantiates a `Person`, `Semester`, and links them via a `CourseOffering`.
