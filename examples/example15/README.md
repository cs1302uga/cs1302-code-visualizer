# Example 15: Reference Aliasing & Mutability

This example demonstrates pointer aliasing where multiple reference variables point to the same object on the heap.

## Concepts Illustrated

- **Reference Aliasing**: `Person friend = alice;` creates a second pointer to the single `Person` object.
- **Heap Mutation**: Mutating `friend` (via `friend.haveBirthday()`) updates the object visible through `alice`.
- **Array Mutation**: Modifying array indices in place.

## Files

- `cs1302/aliasing/Person.java`: Person class with mutable `age`.
- `cs1302/aliasing/Driver.java`: Demonstrates reference aliasing and mutation.
