package cs1302.io;

/**
 * Demonstrates visualizing guest execution with standard input supplied via java.lang.IO.
 */
public class Driver {

    /**
     * Main entry point reading from standard input using IO.readln.
     *
     * @param args Command-line arguments.
     */
    public static void main(String[] args) {
        String name = IO.readln("Enter name: ");
        IO.println("Hello, " + name + "!");
    } // main

} // Driver
