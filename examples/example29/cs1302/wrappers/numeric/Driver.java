package cs1302.wrappers.numeric;

/**
 * Demonstrates all six numeric primitive wrapper class types in Java:
 * {@link Byte}, {@link Short}, {@link Integer}, {@link Long}, {@link Float}, and {@link Double}.
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
        // Individual numeric wrapper objects instantiated via autoboxing
        Byte byteVal = (byte) 8;
        Short shortVal = (short) 16;
        Integer intVal = 32;
        Long longVal = 64L;
        Float floatVal = 1.25f;
        Double doubleVal = 2.5;

        // Polymorphic array referencing all numeric wrapper instances
        Number[] numbers = new Number[] {
            byteVal,
            shortVal,
            intVal,
            longVal,
            floatVal,
            doubleVal
        };
    } // main

} // Driver
