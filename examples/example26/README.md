# Example 26: Polymorphic Generics, Subclass Reification & Wildcards

This example demonstrates polymorphic generic references, concrete subclass reification, wildcard normalization, and nested generic container structures.

## Concepts Illustrated

- **Generic Interface to Subclass Reification**: Reference variable declared as `Container<String>` pointing to concrete `PairContainer<String, Object>` (or `PairContainer<String, Integer>`) on the heap.
- **Non-Generic Implementation of Generic Interface**: Reference variable declared as `Container<Integer>` pointing to concrete non-generic `IntContainer` on the heap.
- **Wildcard Normalization**: `List<? extends Number>` reference normalized to its upper bound `List<Number>`, pointing to concrete `ArrayList<Integer>` on the heap.
- **Nested Generic Containers**: Nested generic list `List<List<String>> matrix` where inner elements inherit reified element type `List<String>`.

## Files

- `cs1302/poly/Container.java`: Generic single-item container interface.
- `cs1302/poly/PairContainer.java`: Generic two-item container implementing `Container<A>`.
- `cs1302/poly/IntContainer.java`: Non-generic container implementing `Container<Integer>`.
- `cs1302/poly/Driver.java`: Driver creating instances and demonstrating polymorphic heap types.
