# Example 24: Generic Integer Lists & Autoboxing (List<Integer> & ArrayList<Integer>)

This example demonstrates standard library generic lists (`List<Integer>` and `ArrayList<Integer>`), primitive autoboxing, in-place element mutation, and polymorphic method parameter passing.

## Concepts Illustrated

- **Interface vs. Implementation References**: Declaring variables with the interface type (`List<Integer> primes = new ArrayList<>();`) versus concrete class type (`ArrayList<Integer> scores = new ArrayList<>();`).
- **Autoboxing and Boxed Heap Primitives**: Adding primitive `int` values (`add(2)`, `add(10)`) causing the runtime to allocate boxed `java.lang.Integer` heap instances.
- **In-Place Element Mutation**: Mutating existing list slots via `set(i, newValue)` in helper method `doubleValues`.
- **Subtype Polymorphism via Method Parameters**: Passing an `ArrayList<Integer>` object into a helper method expecting interface type `List<Integer>`.
- **Concrete Runtime Reification**: Stack variable `primes` retains declared interface type `java.util.List<java.lang.Integer>`, while the referenced heap instance is accurately reified as concrete implementation `java.util.ArrayList<java.lang.Integer>`.

## Files

- `cs1302/list/Driver.java`: Instantiates lists, populates elements, and mutates values via helper method.
