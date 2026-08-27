package cs1302.generics;

public class Pair<K, V> {

    private K key;
    private V value;

    public Pair(K key, V value) {
        this.key = key;
        this.value = value;
    } // Pair

    public K getKey() {
        return this.key;
    } // getKey

    public V getValue() {
        return this.value;
    } // getValue

    public void setKey(K key) {
        this.key = key;
    } // setKey

    public void setValue(V value) {
        this.value = value;
    } // setValue

} // Pair
