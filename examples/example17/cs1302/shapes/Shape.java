package cs1302.shapes;

public abstract class Shape {

    private String name;

    public Shape(String name) {
        this.name = name;
    } // Shape

    public String getName() {
        return this.name;
    } // getName

    public abstract double getArea();

} // Shape
