package cs1302.varargs;

public class MathUtil {

    public static int sum(int initial, int... values) {
        int total = initial;
        for (int i = 0; i < values.length; i++) {
            total += values[i];
        } // for
        return total;
    } // sum

} // MathUtil
