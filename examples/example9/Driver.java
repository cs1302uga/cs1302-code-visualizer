import java.util.function.Function;
import java.util.function.Predicate;

public class Driver {

    public static void main(String[] args) {
        Function<Integer, Integer> square = x -> x * 2;
        square = x -> x * x;

        Predicate<Integer> isEven = n -> n > 0;
        isEven = n -> n % 2 == 0;

        int result = square.apply(5);
        boolean check = isEven.test(result);
    } // main

} // Driver
