# Example 16: Singly Linked Nodes & Pointer Chaining

This example demonstrates singly linked lists and heap pointer manipulation (Chapter 8: ADTs & Links).

## Concepts Illustrated

- **Recursive Data Structures**: `Node` objects containing a reference `next` to another `Node`.
- **Pointer Manipulation**: Prepending nodes by setting `head = new Node("Alpha", head);`.
- **List Traversal**: Stepping pointer `curr = curr.getNext()` along the chain until reaching `null`.

## Files

- `cs1302/nodes/Node.java`: Node implementation with `item` and `next` reference.
- `cs1302/nodes/Driver.java`: Builds and traverses a 3-node linked list.
