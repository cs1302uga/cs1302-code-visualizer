package cs1302.generics;

public class Driver {

    public static void main(String[] args) {
        Pair<String, Integer> score = new Pair<>("Alice", 95);
        Pair<Integer, Boolean> flag = new Pair<>(101, true);

        System.out.printf("Score: %s -> %d%n", score.getKey(), score.getValue());
        System.out.printf("Flag: %d -> %b%n", flag.getKey(), flag.getValue());
    } // main

} // Driver
