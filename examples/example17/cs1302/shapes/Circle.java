package cs1302.shapes;

public class Circle extends Shape {

    private double radius;

    public Circle(double radius) {
        super("Circle");
        this.radius = radius;
    } // Circle

    public double getRadius() {
        return this.radius;
    } // getRadius

    @Override
    public double getArea() {
        return Math.PI * this.radius * this.radius;
    } // getArea

} // Circle
