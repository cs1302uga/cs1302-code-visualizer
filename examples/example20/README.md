# Example 20: Varargs & Synthesized Parameter Arrays

This example demonstrates variable-length arguments (`varargs`) and compiler array allocation (Chapters 4 & 6: Varargs).

## Concepts Illustrated

- **Varargs Parameter**: Method signature `sum(int initial, int... values)`.
- **Compiler Array Synthesis**: The compiler automatically packaging trailing arguments into an `int[]` array allocated on the heap.
- **Explicit Array Passing**: Passing a pre-allocated array vs comma-separated arguments.

## Files

- `cs1302/varargs/MathUtil.java`: Static method accepting varargs.
- `cs1302/varargs/Driver.java`: Driver invoking `MathUtil.sum` with various argument forms.
