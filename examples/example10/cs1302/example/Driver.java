package cs1302.example;

public class Driver {

    public static void main(String[] args) {
        Person alice = new Person("Alice", 20);
        Person bob = new Person("Bob", 22);

        System.out.printf("%s is %d years old.%n", alice.name(), alice.age());
        System.out.printf("%s is %d years old.%n", bob.name(), bob.age());
    } // main

} // Driver
