package cs1302.inheritance;

/**
 * Demonstrates multi-level inheritance, constructor chaining with super(...),
 * inherited heap field layouts, polymorphic references, dynamic dispatch, and
 * pattern-matching downcasting.
 */
public class Driver {

    /**
     * Main entry point.
     *
     * @param args Command-line arguments.
     */
    public static void main(String[] args) {
        // 1. Direct base class instantiation
        Person person = new Person("Alice", 30);

        // 2. Direct second-tier class instantiation
        Employee employee = new Employee("Bob", 35, 101, 75000.0);

        // 3. Polymorphic assignment: Person variable referencing third-tier Manager object
        Person polyPerson = new Manager("Carol", 40, 201, 95000.0, "Engineering", 15000.0);

        // 4. Dynamic method dispatch
        String personRole = person.getRole();
        String employeeRole = employee.getRole();
        String polyRole = polyPerson.getRole();

        // 5. Downcasting with instanceof pattern matching
        if (polyPerson instanceof Manager mgr) {
            String dept = mgr.getDepartment();
            double totalComp = mgr.getSalary() + mgr.getBonus();
        } // if
    } // main

} // Driver
