public class Driver {
    public static void main(String[] args) {
        Person alice = new Person("Alice", 42);
    } // main
} // Driver

record Person(String name, int age) { };
