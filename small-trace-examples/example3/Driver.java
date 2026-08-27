public class Driver {

    public static void main(String[] args) {
        Person[] roster = new Person[] {
            new Person("Alice", 20),
            new Person("Bob", 22)
        };
        swap(roster, 0, 1);
    } // main

    public static void swap(Person[] arr, int i, int j) {
        Person temp = arr[i];
        arr[i] = arr[j];
        arr[j] = temp;
    } // swap

} // Driver

record Person(String name, int age) { }
