// --- cs1302/math/Calculator.java ---
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

// --- cs1302/math/Driver.java ---
package cs1302.math;

public class Driver {

    public static void main(String[] args) {
        int x = 4;
        int y = 3;
        int product = Calculator.multiply(x, y);
        System.out.printf("%d * %d = %d%n", x, y, product);
    } // main

} // Driver
