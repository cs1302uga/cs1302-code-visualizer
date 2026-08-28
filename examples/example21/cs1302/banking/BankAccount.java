package cs1302.banking;

public class BankAccount {

    private String owner;
    private double balance;

    public BankAccount(String owner, double initialBalance) {
        this.owner = owner;
        this.balance = initialBalance;
    } // BankAccount

    public String getOwner() {
        return this.owner;
    } // getOwner

    public double getBalance() {
        return this.balance;
    } // getBalance

    public void deposit(double amount) {
        this.balance += amount;
    } // deposit

    public boolean transferTo(BankAccount target, double amount) {
        double fee = 2.50;
        double totalDeduction = amount + fee;
        if (this.balance >= totalDeduction) {
            this.balance -= totalDeduction;
            target.deposit(amount);
            return true;
        } // if
        return false;
    } // transferTo

} // BankAccount
