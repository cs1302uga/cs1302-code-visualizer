package cs1302.poly;

/**
 * Generic two-item container where the first item satisfies {@link Container}.
 *
 * @param <A> First item type.
 * @param <B> Second item type.
 */
public class PairContainer<A, B> implements Container<A> {

    private final A first;
    private final B second;

    /**
     * Constructs a pair container.
     *
     * @param first The first item.
     * @param second The second item.
     */
    public PairContainer(A first, B second) {
        this.first = first;
        this.second = second;
    } // PairContainer

    @Override
    public A getItem() {
        return this.first;
    } // getItem

    /**
     * Gets the second item.
     *
     * @return The second item.
     */
    public B getSecond() {
        return this.second;
    } // getSecond

} // PairContainer
