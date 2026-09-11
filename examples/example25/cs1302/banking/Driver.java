package cs1302.banking;

public class Driver {

    public static void main(String[] args) {
        BankAccount checking = new BankAccount("Alice", 500.00);
        BankAccount savings = new BankAccount("Bob", 100.00);

        boolean success = checking.transferTo(savings, 150.00);
        System.out.printf("Transfer status: %b%n", success);
    } // main

} // Driver
