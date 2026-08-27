package cs1302.shapes;

public class Rectangle extends Shape {

    private double width;
    private double height;

    public Rectangle(double width, double height) {
        super("Rectangle");
        this.width = width;
        this.height = height;
    } // Rectangle

    public double getWidth() {
        return this.width;
    } // getWidth

    public double getHeight() {
        return this.height;
    } // getHeight

    @Override
    public double getArea() {
        return this.width * this.height;
    } // getArea

} // Rectangle
