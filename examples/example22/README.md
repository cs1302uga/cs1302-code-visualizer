# Example 22: Interleaved Standard Output & Standard Error Logging

This example demonstrates concurrent, isolated capture of standard output (`stdout`) and standard error (`stderr`) streams using the modern trace format (`--format=modern -a`).

## Concepts Illustrated

- **Stream Separation**: `stdout` and `stderr` are captured into their respective fields in each execution step snapshot without cross-contamination.
- **Diagnostic Logging**: Emitting status updates to `System.out` and warning messages for invalid inputs to `System.err`.
- **Modern Trace Format**: Visualizing execution steps containing explicit `stdout` and `stderr` string properties.

## Files

- `cs1302/io/stderr/Driver.java`: Iterates through an array of scores, writing valid entries to `System.out` and validation warnings to `System.err`.
