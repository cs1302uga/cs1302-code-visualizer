public class EdgeCases {
    static class Node {
        String label;
        Node next;
        Node(String label) { this.label = label; }
    }
    public static void main(String[] args) {
        String escaped = "<tag attr=\"value\"> & café Ω 😀 e\u0301 👩‍💻";
        String longLabel = "A deliberately long string to exercise exported text bounds";
        String empty = "";
        int[] emptyArray = {};
        int[][] matrix = {{1, 2, 3}, {}, {4, 5}};
        int[][][] cube = {{{1, 2}}, {{3, 4}}};
        Node first = new Node("first");
        Node second = new Node("second");
        first.next = second;
        second.next = first;
        Node alias = first;
        Object missing = null;
        System.out.println(escaped + longLabel + empty + matrix[0][0] + cube[0][0][0]);
    }
}
