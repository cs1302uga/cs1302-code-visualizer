package cs1302.poly;

/**
 * Concrete non-generic container implementing {@code Container<Integer>}.
 */
public class IntContainer implements Container<Integer> {

    private final Integer value;

    /**
     * Constructs an integer container.
     *
     * @param value The integer value.
     */
    public IntContainer(Integer value) {
        this.value = value;
    } // IntContainer

    @Override
    public Integer getItem() {
        return this.value;
    } // getItem

} // IntContainer
