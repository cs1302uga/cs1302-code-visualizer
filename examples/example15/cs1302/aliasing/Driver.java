package cs1302.aliasing;

public class Driver {
    public static void main(String[] args) {
        Person alice = new Person("Alice", 20);
        Person friend = alice; // Pointer aliasing: friend and alice point to the same object on heap
        int[] scores = new int[] { 95, 88, 92 };

        friend.haveBirthday();
        scores[0] = 100;
    }
}
