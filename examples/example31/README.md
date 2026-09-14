# Example 31: java.awt.Color Objects and Transparency

This example demonstrates the heap layout and visualization of `java.awt.Color` objects, including custom RGB values, alpha transparency, and reference aliasing.

## Concepts Illustrated

- **Color Heap Objects**: `java.awt.Color` instances reside on the heap with specialized color representations displaying visual color swatches and hex strings (`#RRGGBB` or `#RRGGBBAA`).
- **Transparency Support**: Colors with alpha < 255 include an 8-digit hex string with alpha channel information.
- **Reference Aliasing**: Multiple variable references (`red` and `redAlias`) pointing to the same `Color` heap instance.
- **Color Arrays (`Color[]`)**: Arrays containing references to multiple `Color` objects on the heap.

## Files

- `cs1302/color/Driver.java`: Main driver demonstrating Color instances, transparency, and aliasing.
