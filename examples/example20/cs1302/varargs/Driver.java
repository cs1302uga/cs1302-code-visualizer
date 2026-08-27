package cs1302.varargs;

public class Driver {

    public static void main(String[] args) {
        int total1 = MathUtil.sum(10, 1, 2, 3);
        int total2 = MathUtil.sum(5);
        int[] moreValues = new int[] { 20, 30 };
        int total3 = MathUtil.sum(0, moreValues);

        System.out.printf("total1 = %d, total2 = %d, total3 = %d%n", total1, total2, total3);
    } // main

} // Driver
