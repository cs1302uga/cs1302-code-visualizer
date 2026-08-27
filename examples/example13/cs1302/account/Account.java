package cs1302.account;

public class Account {

    private String owner;
    private double balance;

    public Account(String owner, double balance) {
        this.owner = owner;
        this.balance = balance;
    } // Account

    public void deposit(double amount) {
        this.balance += amount;
    } // deposit

    public boolean withdraw(double amount) {
        if (amount <= this.balance) {
            this.balance -= amount;
            return true;
        } // if
        return false;
    } // withdraw

    public double getBalance() {
        return this.balance;
    } // getBalance

    public String getOwner() {
        return this.owner;
    } // getOwner

} // Account
