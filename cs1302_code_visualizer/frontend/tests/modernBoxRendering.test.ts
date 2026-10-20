import { beforeEach, describe, expect, it } from "vitest";
import { create } from "../js/CodeVisualizer";
import type { ModernHeapObject, ModernLocal, ModernTrace } from "../js/modernTraceAdapter";

const wrappers = [
  ["Boolean", false, "false"],
  ["Byte", 0, "0"],
  ["Short", -2, "-2"],
  ["Character", "\n", "'\\n'"],
  ["Integer", 42, "42"],
  ["Long", 1234567890123, "1234567890123"],
  ["Float", 1.5, "1.5"],
  ["Double", 2.25, "2.25"],
  ["Float", "NaN", "NaN"],
  ["Double", "Infinity", "Infinity"],
] as const;

function traceWithBoxes(): ModernTrace {
  const heap: Record<string, ModernHeapObject> = {
    1: { id: 1, type: "Demo", kind: "object", fields: [] },
    2: { id: 2, type: "java.lang.String", kind: "string", value: "text" },
  };
  const locals: ModernLocal[] = [
    { name: "message", type: "java.lang.String", value: { ref: 2 } },
    { name: "alias", type: "java.lang.Integer", value: { ref: 104 } },
  ];
  wrappers.forEach(([name, value], index) => {
    const id = 100 + index;
    const type = `java.lang.${name}`;
    heap[id] = { id, type, kind: "box", value };
    locals.push({ name: `box${index}`, type, value: { ref: id } });
  });
  return { code: "class Demo {\n  void visit() {}\n}", format: "modern", steps: [{
    line: 2, heap, callStack: [{ methodName: "visit", line: 2, this: { ref: 1 }, locals }],
  }] };
}

let root: HTMLDivElement;
beforeEach(() => {
  document.body.innerHTML = "";
  root = document.createElement("div");
  document.body.appendChild(root);
});

describe("modern receiver and boxed scalar rendering", () => {
  it.each(["default", "compact", "inline"] as const)("renders wrapper contents and receiver with String style %s", (style) => {
    const trace = traceWithBoxes();
    const original = structuredClone(trace);
    const view = create({ lang: "java", trace, element: root, options: { stringStyle: style } });
    try {
      wrappers.forEach(([, , expected], index) => {
        const object = root.querySelector(`.heapObject[data-object-id="${100 + index}"]`);
        expect(object?.querySelector(".instVal")?.textContent).toBe(expected);
        expect(object?.querySelector(".instKey")?.getAttribute("style")).toContain("display: none");
      });
      expect(root.querySelectorAll('.heapObject[data-object-id="104"]')).toHaveLength(1);
      expect(root.querySelector(".javaStackVarThis")?.textContent).toBe("this");
      expect(root.textContent).toContain("text");
      expect(trace).toEqual(original);
    } finally {
      view.destroy?.();
    }
  });
});
