# Example 3: Array of References & Element Swapping

This example demonstrates arrays containing object references and pass-by-value reference manipulation in methods.

## Concepts Illustrated

- **Array of References**: `Person[] roster` pointing to individual heap objects.
- **Reference Passing**: Passing the array reference to a helper `swap` method.
- **Stack & Heap Interaction**: Demonstrates how swapping pointers inside an array in a called frame updates the shared array on the heap.

## Files

- `Driver.java`: Declares a `Person[]` array and swaps two element references.
