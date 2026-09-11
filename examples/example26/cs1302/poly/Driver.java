package cs1302.poly;

import java.util.ArrayList;
import java.util.List;

/**
 * Demonstrates polymorphic generic container references, wildcard normalization,
 * concrete subclass reification, and nested generic collections.
 */
public class Driver {

    /**
     * Main entry point.
     *
     * @param args Command-line arguments.
     */
    public static void main(String[] args) {
        // 1. Generic interface pointing to multi-param generic subclass
        Container<String> pair = new PairContainer<>("apple", 42);

        // 2. Generic interface pointing to non-generic concrete subclass
        Container<Integer> boxed = new IntContainer(100);

        // 3. Wildcard upper bound normalized to bound
        List<? extends Number> numbers = new ArrayList<Integer>();

        // 4. Nested generic container
        List<List<String>> matrix = new ArrayList<>();
        List<String> row = new ArrayList<>();
        row.add("hello");
        matrix.add(row);
    } // main

} // Driver
