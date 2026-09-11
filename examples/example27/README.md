# Example 27: Multi-Level Inheritance, Constructor Chaining & Polymorphism

This example demonstrates multi-level class inheritance (`Person` -> `Employee` -> `Manager`), constructor chaining with `super(...)`, tiered field layout on heap objects, polymorphic reference variables, dynamic method dispatch, and safe downcasting.

## Concepts Illustrated

- **Multi-Level Inheritance (`extends`)**: A 3-tier class hierarchy where `Manager` extends `Employee`, which extends `Person`.
- **Constructor Chaining (`super(...)`)**: Each constructor delegates initialization of inherited state to its direct superclass constructor before initializing its own fields.
- **Heap Object Field Accumulation**: An instantiated `Manager` object on the heap contains all fields defined across the hierarchy (`name`, `age`, `id`, `salary`, `department`, `bonus`).
- **Polymorphic Reference Variables**: Assigning a subclass instance (`Manager`) to a superclass reference variable (`Person polyPerson`).
- **Dynamic Method Dispatch**: Invoking `polyPerson.getRole()` resolves at runtime to `Manager.getRole()`.
- **Pattern-Matching Downcasting (`instanceof`)**: Safely checking and binding the more specific type `Manager` to access subclass-specific fields and methods.

## Files

- `cs1302/inheritance/Person.java`: Base class with `name`, `age`, and `getRole()`.
- `cs1302/inheritance/Employee.java`: Middle-tier class adding `id`, `salary`, and overriding `getRole()`.
- `cs1302/inheritance/Manager.java`: Leaf-tier class adding `department`, `bonus`, and overriding `getRole()`.
- `cs1302/inheritance/Driver.java`: Driver demonstrating instantiation, polymorphic dispatch, and downcasting.
