package cs1302.scanner;

import java.util.Scanner;

/**
 * Demonstrates visualizing guest execution with standard input supplied via Scanner.
 */
public class Driver {

    /**
     * Main entry point reading from System.in using Scanner.
     *
     * @param args Command-line arguments.
     */
    public static void main(String[] args) {
        Scanner input = new Scanner(System.in);
        String greeting = input.next();
        int courseNumber = input.nextInt();
        double score = input.nextDouble();
        System.out.printf("%s, CS %d! Score: %.1f\n", greeting, courseNumber, score);
    } // main

} // Driver
