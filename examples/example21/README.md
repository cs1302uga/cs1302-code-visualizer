# Example 21: Unbuffered Standard Output & Progress Prompts

This example demonstrates step-by-step capture of unbuffered console output using `System.out.print` (without trailing newlines) alongside iterative loop execution (`trace -a`).

## Concepts Illustrated

- **Unbuffered Stdout Capture**: Output emitted via `System.out.print` is accurately flushed and recorded in `stdout` at each subsequent execution snapshot before any newline character is encountered.
- **Progress Tracking**: Progress indicator tokens (`"."`) accumulating step-by-step across loop iterations.
- **Chronological Trace**: Full step sequence preserving intermediate console output states.

## Files

- `cs1302/io/stdout/Driver.java`: Emits an unbuffered status prompt, iterates through a loop writing dots, and outputs a final completion message.
