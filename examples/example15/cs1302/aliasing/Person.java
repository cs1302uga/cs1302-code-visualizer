package cs1302.aliasing;

public class Person {
    private String name;
    private int age;

    public Person(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public void haveBirthday() {
        this.age++;
    }

    public int getAge() {
        return this.age;
    }

    public String getName() {
        return this.name;
    }
}
