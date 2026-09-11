package cs1302.inheritance;

/**
 * Represents an employee extending Person with employee ID and salary.
 */
public class Employee extends Person {

    private int id;
    private double salary;

    /**
     * Constructs a new Employee chaining to super Person constructor.
     *
     * @param name Employee name.
     * @param age Employee age.
     * @param id Employee ID.
     * @param salary Employee salary.
     */
    public Employee(String name, int age, int id, double salary) {
        super(name, age);
        this.id = id;
        this.salary = salary;
    } // Employee

    /**
     * Returns the employee ID.
     *
     * @return The ID.
     */
    public int getId() {
        return this.id;
    } // getId

    /**
     * Returns the employee salary.
     *
     * @return The salary.
     */
    public double getSalary() {
        return this.salary;
    } // getSalary

    @Override
    public String getRole() {
        return "Employee";
    } // getRole

} // Employee
