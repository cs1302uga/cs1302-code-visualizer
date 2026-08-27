# Example 4: Instance Methods & `this` References

This example demonstrates instance method dispatch and the implicit `this` reference within method stack frames.

## Concepts Illustrated

- **Instance Methods**: Calling `alice.isOlderThan(bob)`.
- **`this` Parameter**: The receiver object (`alice`) bound to `this` inside the method frame while `other` refers to `bob`.

## Files

- `Driver.java`: Defines `Person` with an `isOlderThan` comparison method.
