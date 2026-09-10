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
      expect(typeLabel?.textContent).toContain("Object instance");

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

      instance.destroy?.();
      expect(container.innerHTML).toBe("");
    });
  });
});

