package cs1302.io.stderr;

public class Driver {

    public static void main(String[] args) {
        int[] scores = { 85, -5, 92, 110 };

        System.out.println("Beginning score validation:");
        for (int score : scores) {
            if (score < 0 || score > 100) {
                System.err.printf("Warning: Invalid score encountered: %d%n", score);
            } else {
                System.out.printf("Valid score recorded: %d%n", score);
            } // if
        } // for
        System.out.println("Validation complete.");
    } // main

} // Driver
