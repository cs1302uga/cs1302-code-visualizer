public class Driver {

    public static void main(String[] args) {
        long result = factorial(4);
        System.out.println("4! = " + result);
    } // main

    public static long factorial(int n) {
        if (n <= 1) {
            return 1;
        } // if
        return n * factorial(n - 1);
    } // factorial

} // Driver
