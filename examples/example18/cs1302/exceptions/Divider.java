package cs1302.exceptions;

public class Divider {

    public static int divide(int numerator, int denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException("Cannot divide by zero");
        } // if
        return numerator / denominator;
    } // divide

} // Divider
