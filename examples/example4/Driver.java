public class Driver {

    public static void main(String[] args) {
        Person alice = new Person("Alice", 25);
        Person bob = new Person("Bob", 20);
        boolean result = alice.isOlderThan(bob);
    } // main

} // Driver

class Person {

    private String name;
    private int age;

    public Person(String name, int age) {
        this.name = name;
        this.age = age;
    } // Person

    public boolean isOlderThan(Person other) {
        int ageDiff = this.age - other.age;
        return ageDiff > 0;
    } // isOlderThan

} // Person
