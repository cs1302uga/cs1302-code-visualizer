package cs1302.math;

public class Calculator {

    public static int multiply(int a, int b) {
        int result = 0;
        for (int i = 0; i < b; i++) {
            result += a;
        } // for
        return result;
    } // multiply

} // Calculator
