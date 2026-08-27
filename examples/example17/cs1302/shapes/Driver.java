package cs1302.shapes;

public class Driver {

    public static void main(String[] args) {
        Shape[] shapes = new Shape[] {
            new Circle(2.0),
            new Rectangle(3.0, 4.0)
        };

        for (int i = 0; i < shapes.length; i++) {
            Shape s = shapes[i];
            double area = s.getArea();
            System.out.printf("%s area: %.2f%n", s.getName(), area);
        } // for
    } // main

} // Driver
