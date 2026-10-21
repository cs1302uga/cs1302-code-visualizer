import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

/** Demonstrates stored time components and live set views in tracer 4.3.0. */
public class Main {
    static class Item {
        int value = 1;
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(12, 30, 0, 123456789);
        LocalDateTime meeting = LocalDateTime.of(date, time);
        Duration elapsed = Duration.ofNanos(-1);
        Duration original = elapsed;
        elapsed = elapsed.plusSeconds(2);
        Item item = new Item();
        Set<Object> backing = new LinkedHashSet<>();
        backing.add(item);
        backing.add(null);
        Set<Object> view = Collections.unmodifiableSet(backing);
        Set<Object> second = Collections.unmodifiableSet(backing);
        Set<Object> alias = view;
        System.out.println("before");
        backing.add("last");
        item.value = 2;
        System.out.println("after");
        System.out.println(original);
        System.out.println(elapsed);
    }
}
