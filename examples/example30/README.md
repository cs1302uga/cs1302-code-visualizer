# Example 30: Non-Numeric Primitive Wrapper Classes

This example demonstrates the heap layout and visualization of non-numeric primitive wrapper class types in Java: `Boolean` and `Character`.

## Concepts Illustrated

- **Non-Numeric Autoboxing**: Automatic conversion from boolean and character primitive literals to their corresponding `java.lang.Boolean` and `java.lang.Character` wrapper objects.
- **Heap Object Representation**: Each boxed wrapper on the heap forms an `INSTANCE` object box labeled with its wrapper type (`Boolean` or `Character`) containing a single field `value` with the corresponding primitive type label (`boolean` or `char`).
- **Object Reference Array (`Object[]`)**: An array of `Object` references pointing to instances of `Boolean` and `Character`, illustrating polymorphic reference containment.

## Files

- `cs1302/wrappers/other/Driver.java`: Main driver demonstrating non-numeric wrapper instances and array references.
