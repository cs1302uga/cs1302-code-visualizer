package cs1302.inheritance;

/**
 * Represents a base person in a hierarchy with name and age.
 */
public class Person {

    private String name;
    private int age;

    /**
     * Constructs a new Person with name and age.
     *
     * @param name Person's name.
     * @param age Person's age.
     */
    public Person(String name, int age) {
        this.name = name;
        this.age = age;
    } // Person

    /**
     * Returns the person's name.
     *
     * @return The name.
     */
    public String getName() {
        return this.name;
    } // getName

    /**
     * Returns the person's age.
     *
     * @return The age.
     */
    public int getAge() {
        return this.age;
    } // getAge

    /**
     * Returns the role descriptor for this person.
     *
     * @return The role string.
     */
    public String getRole() {
        return "Person";
    } // getRole

} // Person
