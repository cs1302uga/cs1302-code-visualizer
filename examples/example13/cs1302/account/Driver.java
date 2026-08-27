package cs1302.account;

public class Driver {

    public static void main(String[] args) {
        Account alice = new Account("Alice", 100.0);
        Account bob = new Account("Bob", 50.0);

        alice.deposit(50.0);
        alice.withdraw(30.0);

        bob.deposit(25.0);

        System.out.printf("%s balance: $%.2f%n", alice.getOwner(), alice.getBalance());
        System.out.printf("%s balance: $%.2f%n", bob.getOwner(), bob.getBalance());
    } // main

} // Driver
