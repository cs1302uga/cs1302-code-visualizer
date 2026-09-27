public class Lists {
    public static void main(String[] args) {
        Node head = new Node("Cheese", new Node("Bread", new Node("Milk", null)));
        head.next.next.next = head;
        List arrayList = new ArrayBasedList(new String[] { "Milk", "Bread", "Ice Cream", "", null }, 4);
        List linkList = new LinkBasedList(head, 3);
        String shared = head.next.next.item;
        String[] items = { shared, shared, "Say \"hello\"", "Extra creamy vanilla ice cream with chocolate sprinkles" };
        char letter = 'x';
        System.out.println("snapshot");
    }
}
class Node {
    String item;
    Node next;
    Node(String item, Node next) { this.item = item; this.next = next; }
}
interface List { int size(); }
class ArrayBasedList implements List {
    int size;
    String[] array;
    ArrayBasedList(String[] array, int size) { this.array = array; this.size = size; }
    public int size() { return size; }
}
class LinkBasedList implements List {
    int size;
    Node head;
    LinkBasedList(Node head, int size) { this.head = head; this.size = size; }
    public int size() { return size; }
}
