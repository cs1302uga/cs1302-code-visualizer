package cs1302.color;

import java.awt.Color;

/**
 * Demonstrates java.awt.Color objects, aliasing, and transparency in the heap.
 *
 * <p>
 * Normative References:
 * <ul>
 *   <li>The Java Language Specification (JLS), Java SE 21 Edition, §4.3.1 (Objects).</li>
 *   <li>The Java Language Specification (JLS), Java SE 21 Edition, §4.3.4 (Type {@code Object}).</li>
 * </ul>
 * </p>
 */
public class Driver {

    /**
     * Main entry point.
     *
     * @param args Command-line arguments.
     */
    public static void main(String[] args) {
        // Standard constant color
        Color red = Color.RED;

        // Custom RGB color
        Color skyBlue = new Color(0, 128, 255);

        // Translucent RGBA color with alpha < 255
        Color semiTransparent = new Color(255, 0, 0, 128);

        // Aliased reference pointing to existing color
        Color redAlias = red;

        // Array referencing color instances
        Color[] palette = new Color[] {
            red,
            skyBlue,
            semiTransparent
        };
    } // main

} // Driver
