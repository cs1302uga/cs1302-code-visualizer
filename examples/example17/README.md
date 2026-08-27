# Example 17: Inheritance & Subtype Polymorphism

This example demonstrates class inheritance, superclass constructors, and dynamic method dispatch (Chapter 7: Inheritance).

## Concepts Illustrated

- **Class Inheritance**: `Circle` and `Rectangle` extending the abstract base class `Shape`.
- **Superclass Constructor**: Invoking `super("Circle")` to initialize inherited fields on the heap object.
- **Subtype Polymorphism**: Storing diverse subtype instances inside a `Shape[]` array and dynamically invoking overridden `getArea()` methods.

## Files

- `cs1302/shapes/Shape.java`: Abstract base class.
- `cs1302/shapes/Circle.java`: Circle subtype.
- `cs1302/shapes/Rectangle.java`: Rectangle subtype.
- `cs1302/shapes/Driver.java`: Polymorphic array processing.
