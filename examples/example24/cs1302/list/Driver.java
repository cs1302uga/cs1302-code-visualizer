package cs1302.list;

import java.util.ArrayList;
import java.util.List;

public class Driver {

    /**
     * Doubles each integer element in the provided list.
     *
     * @param numbers The list of integers to modify.
     */
    public static void doubleValues(List<Integer> numbers) {
        for (int i = 0; i < numbers.size(); i++) {
            int original = numbers.get(i);
            numbers.set(i, original * 2);
        } // for
    } // doubleValues

    public static void main(String[] args) {
        // Interface reference type pointing to an ArrayList implementation
        List<Integer> primes = new ArrayList<>();
        primes.add(2);
        primes.add(3);
        primes.add(5);

        // Concrete class reference type pointing to an ArrayList implementation
        ArrayList<Integer> scores = new ArrayList<>();
        scores.add(10);
        scores.add(20);
        scores.add(30);

        // Mutate via helper method expecting interface type List<Integer>
        doubleValues(scores);
    } // main

} // Driver
