package cs1302.inheritance;

/**
 * Represents a manager extending Employee with department and bonus.
 */
public class Manager extends Employee {

    private String department;
    private double bonus;

    /**
     * Constructs a new Manager chaining to super Employee constructor.
     *
     * @param name Manager name.
     * @param age Manager age.
     * @param id Manager ID.
     * @param salary Manager salary.
     * @param department Managed department name.
     * @param bonus Manager annual bonus.
     */
    public Manager(
            String name,
            int age,
            int id,
            double salary,
            String department,
            double bonus) {
        super(name, age, id, salary);
        this.department = department;
        this.bonus = bonus;
    } // Manager

    /**
     * Returns the manager's department.
     *
     * @return The department.
     */
    public String getDepartment() {
        return this.department;
    } // getDepartment

    /**
     * Returns the manager's bonus.
     *
     * @return The bonus.
     */
    public double getBonus() {
        return this.bonus;
    } // getBonus

    @Override
    public String getRole() {
        return "Manager";
    } // getRole

} // Manager
