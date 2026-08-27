package cs1302.nodes;

public class Node {

    private String item;
    private Node next;

    public Node(String item, Node next) {
        this.item = item;
        this.next = next;
    } // Node

    public Node(String item) {
        this(item, null);
    } // Node

    public String getItem() {
        return this.item;
    } // getItem

    public void setItem(String item) {
        this.item = item;
    } // setItem

    public Node getNext() {
        return this.next;
    } // getNext

    public void setNext(Node next) {
        this.next = next;
    } // setNext

} // Node
