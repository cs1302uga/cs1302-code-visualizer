package cs1302.empty;

/**
 * Demonstrates empty string and zero-length array instances on the heap
 * alongside their non-empty counterparts.
 *
 * <p>
 * Normative References:
 * <ul>
 *   <li>The Java Language Specification (JLS), Java SE 21 Edition, §3.10.5 (String Literals).</li>
 *   <li>The Java Language Specification (JLS), Java SE 21 Edition, §10.1 (Array Types).</li>
 *   <li>The Java Language Specification (JLS), Java SE 21 Edition, §4.3.1 (Objects).</li>
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
        // Empty and non-empty String instances
        String emptyStr = "";
        String nonEmptyStr = "hello";

        // Empty and non-empty primitive arrays (int[])
        int[] emptyPrims = new int[0];
        int[] nonEmptyPrims = new int[] { 1, 2, 3 };

        // Empty and non-empty reference arrays (String[])
        String[] emptyRefs = new String[0];
        String[] nonEmptyRefs = new String[] { "a", "b" };
    } // main

} // Driver
