package cs1302.exceptions;

public class Driver {

    public static void main(String[] args) {
        int result = compute(10, 0);
        System.out.println("Result: " + result);
    } // main

    public static int compute(int a, int b) {
        int val = -1;
        try {
            val = Divider.divide(a, b);
        } catch (IllegalArgumentException e) {
            System.err.println("Caught exception: " + e.getMessage());
            val = 0;
        } finally {
            System.out.println("Computation attempt finished");
        } // try
        return val;
    } // compute

} // Driver
