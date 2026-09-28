public class Main {
    public static void main(String[] args) {
        Node finish = new Node("Hello");
        finish.next = new Node("World");
        Node n = finish.next;
        System.out.println("snapshot");
    }
}

class Node {
    String item;
    Node next;
    Node(String item) { this.item = item; }
}
