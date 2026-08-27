# Example 18: Exception Handling & Stack Frame Unwinding

This example demonstrates exception instantiation, throwing across method boundaries, catch block handling, and finally block execution (Chapter 3: Exceptions).

## Concepts Illustrated

- **Throwing Exceptions**: `throw new IllegalArgumentException(...)` constructing an exception object on the heap.
- **Stack Unwinding**: The runtime unwinding active frames from `Divider.divide` back to the enclosing `try` block in `compute`.
- **Catch & Finally Blocks**: Handling the exception, capturing its message, and guaranteeing execution of `finally`.

## Files

- `cs1302/exceptions/Divider.java`: Method throwing `IllegalArgumentException`.
- `cs1302/exceptions/Driver.java`: Nested helper method with `try-catch-finally`.
