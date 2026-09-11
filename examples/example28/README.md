# Example 28: Empty Strings and Zero-Length Array Instances

This example demonstrates the heap layout and visualization of empty string instances (`""`) and zero-length array instances (`new T[0]`) alongside non-empty counterparts in Java.

## Concepts Illustrated

- **Empty String Object (`""`)**: An instantiated `java.lang.String` object representing a zero-length character sequence. On the heap, it forms a tangible object box labeled `String (length 0)` with centered quotes `""`.
- **Zero-Length Primitive Array (`new int[0]`)**: A valid array instance created with length `0`. On the heap, it forms a tangible empty object box labeled `int[] (length 0)` so that reference pointers cleanly terminate at the object container.
- **Zero-Length Reference Array (`new String[0]`)**: A zero-length array of object references. On the heap, it forms a tangible empty object box labeled `String[] (length 0)`.
- **Non-Empty Comparisons**: Contrasted with non-empty strings (`String` header containing string literal) and populated arrays (`int[] (length 3)`, `String[] (length 2)`) with indexed array cells containing elements.

## Files

- `cs1302/empty/Driver.java`: Main driver class demonstrating empty strings, zero-length primitive arrays, and zero-length reference arrays.
