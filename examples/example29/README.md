# Example 29: Numeric Primitive Wrapper Classes

This example demonstrates the heap layout and visualization of all six numeric primitive wrapper class types in Java: `Byte`, `Short`, `Integer`, `Long`, `Float`, and `Double`.

## Concepts Illustrated

- **Numeric Autoboxing**: Automatic conversion from primitive numeric literals to their corresponding `java.lang.Number` wrapper objects.
- **Heap Object Representation**: Each boxed numeric wrapper on the heap forms an `INSTANCE` object box labeled with its wrapper type (e.g., `Byte`, `Double`, `Integer`, etc.) containing a single field `value` with the corresponding primitive type label (`byte`, `short`, `int`, `long`, `float`, `double`).
- **Polymorphic Number Array (`Number[]`)**: An array of `Number` references pointing to instances of distinct numeric wrapper classes, illustrating common superclass reference polymorphism.

## Files

- `cs1302/wrappers/numeric/Driver.java`: Main driver demonstrating numeric wrapper instances and array references.
