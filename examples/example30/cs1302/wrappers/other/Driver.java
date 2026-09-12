package cs1302.wrappers.other;

/**
 * Demonstrates non-numeric primitive wrapper class types in Java:
 * {@link Boolean} and {@link Character}.
 *
 * <p>
 * Normative References:
 * <ul>
 *   <li>The Java Language Specification (JLS), Java SE 21 Edition, §5.1.7 (Boxing Conversion).</li>
 *   <li>The Java Language Specification (JLS), Java SE 21 Edition, §4.3.1 (Objects).</li>
 *   <li>The Java Language Specification (JLS), Java SE 21 Edition, §4.2 (Primitive Types and Values).</li>
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
        // Individual non-numeric wrapper objects instantiated via autoboxing
        Boolean boolTrue = true;
        Boolean boolFalse = false;
        Character charAlpha = 'A';
        Character charOmega = 'Z';

        // Array referencing non-numeric wrapper instances
        Object[] items = new Object[] {
            boolTrue,
            boolFalse,
            charAlpha,
            charOmega
        };
    } // main

} // Driver
