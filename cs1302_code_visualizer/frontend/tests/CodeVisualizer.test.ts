/**
 * @fileoverview Unit tests for CodeVisualizer factory and trace decoding logic.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { create, JsonPreVisualizer } from "../js/CodeVisualizer";

describe("CodeVisualizer", () => {
  let container: HTMLElement;

  beforeEach(() => {
    document.body.innerHTML = "";
    container = document.createElement("div");
    container.id = "test-visualizer";
    document.body.appendChild(container);
  });

  describe("JsonPreVisualizer", () => {
    it("renders formatted JSON inside pre and code elements", () => {
      const data = { foo: "bar", count: 42 };
      const viz = new JsonPreVisualizer(container, data);

      const pre = container.querySelector("pre");
      const code = container.querySelector("code.language-json");

      expect(pre).not.toBeNull();
      expect(code).not.toBeNull();
      expect(code?.textContent).toBe(JSON.stringify(data, null, 2));

      // Test updateOutput
      viz.updateOutput();
      expect(code?.textContent).toBe(JSON.stringify(data, null, 2));

      // Test destroy
      viz.destroy();
      expect(container.innerHTML).toBe("");
    });
  });

  describe("create() factory with json-pre", () => {
    it("creates and initializes a JsonPreVisualizer instance", () => {
      const traceObj = { code: "int x = 10;", trace: [] };
      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
        options: { visualizer: "json-pre" },
      });

      expect(instance).toBeDefined();
      expect(container.querySelector("code.language-json")).not.toBeNull();
      expect(container.querySelector("code.language-json")?.textContent).toBe(
        JSON.stringify(traceObj, null, 2)
      );

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("decodes raw JSON string traces", () => {
      const rawJson = JSON.stringify({ code: "int y = 20;", trace: [] });
      create({
        lang: "java",
        trace: rawJson,
        element: container,
        options: { visualizer: "json-pre" },
      });

      expect(container.querySelector("code")?.textContent).toContain("int y = 20;");
    });

    it("decodes base64 data URI traces", () => {
      const rawJson = JSON.stringify({ code: "int z = 30;", trace: [] });
      const base64Uri = "data:application/json;base64," + btoa(rawJson);
      create({
        lang: "java",
        trace: base64Uri,
        element: container,
        options: { visualizer: "json-pre" },
      });

      expect(container.querySelector("code")?.textContent).toContain("int z = 30;");
    });

    it("decodes raw base64 string traces with UTF-8 support", () => {
      const rawJson = JSON.stringify({ code: "String greeting = \"Hello, 🌍!\";", trace: [] });
      const bytes = new TextEncoder().encode(rawJson);
      const binary = Array.from(bytes, (b) => String.fromCharCode(b)).join("");
      const rawBase64 = btoa(binary);

      create({
        lang: "java",
        trace: rawBase64,
        element: container,
        options: { visualizer: "json-pre" },
      });

      expect(container.querySelector("code")?.textContent).toContain("Hello, 🌍!");
    });
  });

  describe("create() factory with pytutor", () => {
    it("initializes pytutor visualizer instance on target element", () => {
      const traceObj = {
        code: "public class Main { public static void main(String[] args) {} }",
        trace: [
          {
            line: 1,
            event: "step_line",
            func_name: "main",
            stack_to_render: [],
            globals: {},
            ordered_globals: [],
            heap: {},
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
      });

      expect(instance).toBeDefined();
      expect(typeof instance.updateOutput).toBe("function");
      expect(typeof instance.redrawConnectors).toBe("function");
      expect(typeof instance.destroy).toBe("function");
      expect(instance.element).toBe(container);

      // Verify DOM container was populated with visualizer elements
      expect(container.querySelector(".ExecutionVisualizer")).not.toBeNull();
      expect(container.children.length).toBeGreaterThan(0);

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("renders a styled rectangle for an empty object instance", () => {
      const traceObj = {
        code: "Object obj = new Object();",
        trace: [
          {
            line: 1,
            event: "step_line",
            func_name: "main",
            stack_to_render: [
              {
                func_name: "main",
                frame_id: 1,
                unique_hash: "main_1",
                is_parent: false,
                is_zombie: false,
                parent_frame_id_list: [],
                ordered_varnames: ["obj"],
                encoded_locals: { obj: ["REF", 1] },
              },
            ],
            globals: {},
            ordered_globals: [],
            heap: {
              "1": ["INSTANCE", "Object"],
            },
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
      });

      const heapObject = container.querySelector(".heapObject");
      expect(heapObject).not.toBeNull();

      const typeLabel = heapObject?.querySelector(".typeLabel");
      expect(typeLabel).not.toBeNull();
      expect(typeLabel?.textContent).toBe("Object");

      const emptyInstTable = heapObject?.querySelector("table.instTbl.emptyInst");
      expect(emptyInstTable).not.toBeNull();
      expect(emptyInstTable?.classList.contains("emptyInst")).toBe(true);

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("renders a styled rectangle when all fields of an instance are hidden", () => {
      const traceObj = {
        code: "class Secret { int hidden = 42; } Secret s = new Secret();",
        trace: [
          {
            line: 1,
            event: "step_line",
            func_name: "main",
            stack_to_render: [
              {
                func_name: "main",
                frame_id: 1,
                unique_hash: "main_1",
                is_parent: false,
                is_zombie: false,
                parent_frame_id_list: [],
                ordered_varnames: ["s"],
                encoded_locals: { s: ["REF", 1] },
              },
            ],
            globals: {},
            ordered_globals: [],
            heap: {
              "1": ["INSTANCE", "Secret", ["hidden", 42]],
            },
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
        options: {
          hideFields: ["Secret:hidden"],
        },
      });

      const heapObject = container.querySelector(".heapObject");
      expect(heapObject).not.toBeNull();

      const emptyInstTable = heapObject?.querySelector("table.instTbl.emptyInst");
      expect(emptyInstTable).not.toBeNull();
      expect(emptyInstTable?.classList.contains("emptyInst")).toBe(true);
      expect(heapObject?.querySelector(".typeLabel")?.textContent).toBe("Secret");

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("renders a color swatch preview and hex label for COLOR heap objects", () => {
      const traceObj = {
        code: "Color c = Color.RED;",
        trace: [
          {
            line: 1,
            event: "step_line",
            func_name: "main",
            stack_to_render: [
              {
                func_name: "main",
                frame_id: 1,
                unique_hash: "main_1",
                is_parent: false,
                is_zombie: false,
                parent_frame_id_list: [],
                ordered_varnames: ["c1", "c2"],
                encoded_locals: { c1: ["REF", 1], c2: ["REF", 2] },
              },
            ],
            globals: {},
            ordered_globals: [],
            heap: {
              "1": ["COLOR", "java.awt.Color", "#FF0000"],
              "2": ["COLOR", "Color", "#00FF0080"],
            },
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
        options: {
          stripTypePrefixes: ["java.awt."],
        },
      });

      const heapObjects = container.querySelectorAll(".heapObject");
      expect(heapObjects.length).toBe(2);

      // Object 1: java.awt.Color (#FF0000)
      const obj1 = heapObjects[0];
      expect(obj1.querySelector(".typeLabel")?.textContent).toBe("Color");
      const colorTbl1 = obj1.querySelector("table.colorObjTbl");
      expect(colorTbl1).not.toBeNull();
      const swatch1 = obj1.querySelector(".colorSwatch") as HTMLElement;
      expect(swatch1).not.toBeNull();
      expect(swatch1.style.backgroundColor).toBe("rgb(255, 0, 0)");
      const hexLabel1 = obj1.querySelector(".colorHexLabel");
      expect(hexLabel1?.textContent).toBe("#FF0000");

      // Object 2: Color with alpha (#00FF0080)
      const obj2 = heapObjects[1];
      expect(obj2.querySelector(".typeLabel")?.textContent).toBe("Color");
      const colorTbl2 = obj2.querySelector("table.colorObjTbl");
      expect(colorTbl2).not.toBeNull();
      const swatch2 = obj2.querySelector(".colorSwatch") as HTMLElement;
      expect(swatch2).not.toBeNull();
      const hexLabel2 = obj2.querySelector(".colorHexLabel");
      expect(hexLabel2?.textContent).toBe("#00FF0080");

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("attaches ARIA attributes and handles keyboard arrow navigation", () => {
      const traceObj = {
        code: "int x = 1;",
        trace: [
          {
            line: 1,
            event: "step_line",
            func_name: "main",
            stack_to_render: [],
            globals: {},
            ordered_globals: [],
            heap: {},
            stdout: "",
            stderr: "",
          },
          {
            line: 2,
            event: "step_line",
            func_name: "main",
            stack_to_render: [],
            globals: {},
            ordered_globals: [],
            heap: {},
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
      });

      expect(container.getAttribute("role")).toBe("region");
      expect(container.getAttribute("aria-label")).toBe("Code Execution Visualizer");
      expect(container.getAttribute("tabindex")).toBe("0");

      // Dispatch ArrowLeft and ArrowRight
      const leftEvent = new KeyboardEvent("keydown", { key: "ArrowLeft" });
      const rightEvent = new KeyboardEvent("keydown", { key: "ArrowRight" });
      container.dispatchEvent(leftEvent);
      container.dispatchEvent(rightEvent);

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("renders int[] (length 0) with emptyList table, and String (length 0) header", () => {
      const traceObj = {
        code: 'String emptyStr = ""; int[] emptyArr = new int[0];',
        trace: [
          {
            line: 1,
            event: "step_line",
            func_name: "main",
            stack_to_render: [
              {
                func_name: "main",
                frame_id: 1,
                unique_hash: "main_1",
                is_parent: false,
                is_zombie: false,
                parent_frame_id_list: [],
                ordered_varnames: ["emptyStr", "emptyArr"],
                encoded_locals: {
                  emptyStr: ["REF", 1],
                  emptyArr: ["REF", 2],
                },
              },
            ],
            globals: {},
            ordered_globals: [],
            heap: {
              "1": ["INSTANCE", "String", ["___NO_LABEL!___", ""]],
              "2": ["LIST"],
            },
            heap_attrs: {
              "2": { type: "int[]" },
            },
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
      });

      // Verify empty array header and empty body table
      const heapObjects = container.querySelectorAll(".heapObject");
      expect(heapObjects.length).toBe(2);

      // Verify empty string (heap id 1)
      const emptyStrObj = heapObjects[0];
      const emptyStrTypeLabel = emptyStrObj.querySelector(".typeLabel");
      expect(emptyStrTypeLabel?.textContent).toBe("String (length 0)");
      const emptyStringTbl = emptyStrObj.querySelector(".instTbl.emptyStringTbl");
      expect(emptyStringTbl).not.toBeNull();
      const emptyStringVal = emptyStringTbl?.querySelector(".instVal.emptyStringVal");
      expect(emptyStringVal).not.toBeNull();
      expect(emptyStringVal?.textContent?.trim()).toBe('""');

      // Verify empty array (heap id 2)
      const emptyArrObj = heapObjects[1];
      const emptyArrTypeLabel = emptyArrObj.querySelector(".typeLabel");
      expect(emptyArrTypeLabel?.textContent).toBe("int[] (length 0)");
      const emptyListTable = emptyArrObj.querySelector("table.listTbl.emptyList");
      expect(emptyListTable).not.toBeNull();

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("renders populated array with (length N) and collection with (size N)", () => {
      const traceObj = {
        code: 'String str = "hello"; int[] arr = {1, 2, 3}; ArrayList<Integer> list = new ArrayList<>();',
        trace: [
          {
            line: 1,
            event: "step_line",
            func_name: "main",
            stack_to_render: [
              {
                func_name: "main",
                frame_id: 1,
                unique_hash: "main_1",
                is_parent: false,
                is_zombie: false,
                parent_frame_id_list: [],
                ordered_varnames: ["str", "arr", "list"],
                encoded_locals: {
                  str: ["REF", 1],
                  arr: ["REF", 2],
                  list: ["REF", 3],
                },
              },
            ],
            globals: {},
            ordered_globals: [],
            heap: {
              "1": ["INSTANCE", "String", ["___NO_LABEL!___", "hello"]],
              "2": ["LIST", 1, 2, 3],
              "3": ["LIST", 10, 20],
            },
            heap_attrs: {
              "2": { type: "int[]" },
              "3": { type: "ArrayList<Integer>" },
            },
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
      });

      const heapObjects = container.querySelectorAll(".heapObject");
      expect(heapObjects.length).toBe(3);

      // Populated string: simple String header
      expect(heapObjects[0].querySelector(".typeLabel")?.textContent).toBe("String");

      // Populated array: int[] (length 3)
      expect(heapObjects[1].querySelector(".typeLabel")?.textContent).toBe("int[] (length 3)");

      // Populated collection: ArrayList<Integer> (size 2)
      expect(heapObjects[2].querySelector(".typeLabel")?.textContent).toBe(
        "ArrayList<Integer> (size 2)",
      );

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("renders primitive field type for boxed primitives on heap and handles non-array type attributes defensively", () => {
      const traceObj = {
        code: "Integer a = 42;\nInteger b = 99;\n",
        trace: [
          {
            event: "step_line",
            line: 2,
            func_name: "main:2",
            stack_to_render: [
              {
                func_name: "main:2",
                frame_id: 0,
                is_parent: false,
                is_zombie: false,
                is_highlighted: true,
                parent_frame_id_list: [],
                unique_hash: "main_0",
                ordered_varnames: ["a", "b"],
                locals_attrs: {
                  a: { type: "Integer" },
                  b: { type: "Integer" },
                },
                encoded_locals: {
                  a: ["REF", 1],
                  b: ["REF", 2],
                },
              },
            ],
            globals: {},
            ordered_globals: [],
            heap: {
              "1": ["INSTANCE", "Integer", ["value", 42]],
              "2": ["INSTANCE", "Integer", ["value", 99]],
            },
            heap_attrs: {
              "1": { type: ["int"] },
              "2": { type: "Integer" }, // non-array scalar string safeguard
            },
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
      });

      const heapObjects = container.querySelectorAll(".heapObject");
      expect(heapObjects.length).toBe(2);

      // Object 1: has field type label "int"
      const obj1FieldLabel = heapObjects[0].querySelector(".fieldTypeLabel");
      expect(obj1FieldLabel).not.toBeNull();
      expect(obj1FieldLabel?.textContent).toBe("int");

      // Object 2: scalar string "Integer" must NOT evaluate to "I" via string indexing
      const obj2FieldLabel = heapObjects[1].querySelector(".fieldTypeLabel");
      expect(obj2FieldLabel).toBeNull();

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });

    it("does not render stdin block even when stdin is present in trace", () => {
      const traceObj = {
        code: "Scanner s = new Scanner(System.in);",
        stdin: "Hello World\n",
        trace: [
          {
            event: "step_line",
            line: 1,
            func_name: "main:1",
            stack_to_render: [],
            globals: {},
            ordered_globals: [],
            heap: {},
            stdout: "",
            stderr: "",
          },
        ],
      };

      const instance = create({
        lang: "java",
        trace: traceObj,
        element: container,
      });

      const stdinWrap = container.querySelector("#stdinWrap");
      const stdinShow = container.querySelector("#stdinShow");
      expect(stdinWrap).toBeNull();
      expect(stdinShow).toBeNull();

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });
  });
});

