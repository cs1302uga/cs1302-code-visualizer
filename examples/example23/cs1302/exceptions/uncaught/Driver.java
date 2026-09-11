package cs1302.exceptions.uncaught;

/**
 * Driver class demonstrating the runtime behavior of an uncaught ArithmeticException.
 */
public class Driver {

    /**
     * Entry point of the program.
     *
     * @param args Command-line arguments.
     */
    public static void main(String[] args) {
        System.out.println("Starting calculation...");
        int result = divide(10, 0);
        System.out.println("Result: " + result);
    } // main

    /**
     * Divides two integer values.
     *
     * @param a The numerator.
     * @param b The denominator.
     * @return The quotient.
     */
    public static int divide(int a, int b) {
        System.out.println("Attempting division: " + a + " / " + b);
        return a / b;
    } // divide

} // Driver
