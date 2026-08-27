package cs1302.nodes;

public class Driver {

    public static void main(String[] args) {
        Node head = new Node("Beta");
        head.setNext(new Node("Gamma"));

        // Prepend "Alpha"
        head = new Node("Alpha", head);

        // Traverse the linked nodes
        Node curr = head;
        while (curr != null) {
            System.out.println(curr.getItem());
            curr = curr.getNext();
        } // while
    } // main

} // Driver
