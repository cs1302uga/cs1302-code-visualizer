# Example 23: Uncaught Runtime Exceptions & Trace Termination

This example illustrates the runtime behavior of the tracer when an uncaught runtime exception (`ArithmeticException: / by zero`) occurs during execution using the modern trace format (`--format=modern -a`).

## Concepts Illustrated

- **Uncaught Exception Behavior**: When an exception is thrown and not caught by an enclosing `try-catch` block, execution terminates abruptly at the throwing statement (`return a / b;`).
- **Preserved Call Stack at Crash**: The final captured execution step preserves the active call stack across method boundaries (both `main` at line 15 and `divide` at line 28), including all local variables (`a = 10`, `b = 0`).
- **Standard Error Capture**: The standard error message and stack trace emitted by the JVM's uncaught exception handler are captured in the final execution step's `stderr` property.
- **Unreachable Code**: Statements following the exception trigger (such as line 16 in `main`) are never reached or recorded in the trace.

## Files

- `cs1302/exceptions/uncaught/Driver.java`: Main program invoking a `divide(10, 0)` helper method that encounters an unhandled integer division by zero.
