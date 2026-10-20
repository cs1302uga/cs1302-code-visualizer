/**
 * @fileoverview Unit tests for modernTraceAdapter module.
 */

import { describe, it, expect } from "vitest";
import {
  isModernTrace,
  encodeValue,
  convertModernTraceToOpt,
  ModernTrace,
} from "../js/modernTraceAdapter";
import { prepareStringTrace } from "../js/stringStyle";

describe("modernTraceAdapter", () => {
  describe("isModernTrace", () => {
    it("identifies trace with format='modern'", () => {
      expect(isModernTrace({ code: "", format: "modern" })).toBe(true);
    });

    it("identifies trace with steps array but without legacy trace array", () => {
      expect(isModernTrace({ code: "", steps: [{ line: 1 }] })).toBe(true);
    });

    it("identifies trace with breakpoints dictionary", () => {
      expect(isModernTrace({ code: "", breakpoints: { "5": { line: 5 } } })).toBe(true);
    });

    it("returns false for standard OPT trace", () => {
      expect(isModernTrace({ code: "", trace: [{ line: 1, event: "step_line" }] })).toBe(false);
    });

    it("returns false for null or primitive inputs", () => {
      expect(isModernTrace(null)).toBe(false);
      expect(isModernTrace(undefined)).toBe(false);
      expect(isModernTrace("invalid")).toBe(false);
      expect(isModernTrace(123)).toBe(false);
    });
  });

  describe("encodeValue", () => {
    it("encodes primitive numbers, strings, and booleans as-is", () => {
      expect(encodeValue(42)).toBe(42);
      expect(encodeValue("hello")).toBe("hello");
      expect(encodeValue(true)).toBe(true);
      expect(encodeValue(false)).toBe(false);
    });

    it("encodes null and undefined as null", () => {
      expect(encodeValue(null)).toBeNull();
      expect(encodeValue(undefined)).toBeNull();
    });

    it("encodes reference objects with ref property into REF tuple", () => {
      expect(encodeValue({ ref: 101 })).toEqual(["REF", 101]);
      expect(encodeValue({ ref: "heap_1" })).toEqual(["REF", "heap_1"]);
    });

    it("encodes null reference as null", () => {
      expect(encodeValue({ ref: null })).toBeNull();
      expect(encodeValue({ ref: undefined })).toBeNull();
    });

    it("passes through objects without ref property", () => {
      const obj = { name: "test", count: 5 };
      expect(encodeValue(obj)).toEqual(obj);
    });
  });

  describe("convertModernTraceToOpt", () => {
    it.each([0, "receiver"])("preserves the dedicated receiver reference %s and its alias", (id) => {
      const modernTrace = {
        code: "class Node { void visit() {} }",
        steps: [{
          line: 1,
          callStack: [{
            methodName: "visit",
            line: 1,
            this: { ref: id },
            locals: [{ name: "other", type: "Node", value: { ref: id } }],
          }],
          heap: { [id]: { id, type: "Node", kind: "object", fields: [] } },
        }],
      };
      const original = structuredClone(modernTrace);
      const step = (convertModernTraceToOpt(modernTrace).trace as any[])[0];
      const frame = step.stack_to_render[0];

      expect(frame.ordered_varnames).toEqual(["this", "other"]);
      expect(frame.encoded_locals.this).toEqual(["REF", id]);
      expect(frame.encoded_locals.other).toEqual(["REF", id]);
      expect(frame.locals_attrs.this).toEqual({ type: "Node", final: false });
      expect(Object.keys(step.heap)).toEqual([String(id)]);
      expect(modernTrace).toEqual(original);
    });

    it("keeps this once when both receiver metadata and a local are present", () => {
      const modernTrace = { code: "", steps: [{ line: 1, callStack: [{
        methodName: "visit", line: 1, this: { ref: 12 }, locals: [
          { name: "this", type: "Node", value: { ref: 12 } },
          { name: "x", type: "int", value: 0 },
        ],
      }] }] };
      const frame = (convertModernTraceToOpt(modernTrace).trace as any[])[0].stack_to_render[0];
      expect(frame.ordered_varnames).toEqual(["this", "x"]);
      expect(frame.encoded_locals.this).toEqual(["REF", 12]);
      expect(frame.locals_attrs.this.type).toBe("Node");
    });

    it.each([undefined, null, { ref: null }])("does not invent this for an absent receiver %s", (receiver) => {
      const modernTrace = { code: "", steps: [{ line: 1, callStack: [{
        methodName: "main", line: 1, this: receiver,
        locals: [{ name: "v", type: "java.lang.Void", value: null }],
      }] }] };
      const frame = (convertModernTraceToOpt(modernTrace).trace as any[])[0].stack_to_render[0];
      expect(frame.ordered_varnames).toEqual(["v"]);
      expect(frame.encoded_locals).not.toHaveProperty("this");
      expect(frame.encoded_locals.v).toBeNull();
    });

    const wrapperCases = [
      ["Boolean", false, false],
      ["Byte", 0, 0],
      ["Short", -2, -2],
      ["Character", "\n", ["CHAR-LITERAL", "\n"]],
      ["Integer", 42, 42],
      ["Long", 1234567890123, 1234567890123],
      ["Float", 1.5, 1.5],
      ["Double", 2.25, 2.25],
      ["Float", "NaN", ["NUMBER-LITERAL", "NaN"]],
      ["Float", "Infinity", ["NUMBER-LITERAL", "Infinity"]],
      ["Float", "-Infinity", ["NUMBER-LITERAL", "-Infinity"]],
      ["Double", "NaN", ["NUMBER-LITERAL", "NaN"]],
      ["Double", "Infinity", ["NUMBER-LITERAL", "Infinity"]],
      ["Double", "-Infinity", ["NUMBER-LITERAL", "-Infinity"]],
    ] as const;

    describe.each(["", "java.lang."])("boxed scalar types with prefix '%s'", (prefix) => {
      it.each(wrapperCases)("preserves %s payload %s and all aliases", (name, value, expected) => {
        const type = `${prefix}${name}`;
        const modernTrace: ModernTrace = { code: "", steps: [{
          line: 1,
          callStack: [{ methodName: "main", line: 1, locals: [
            { name: "box", type, value: { ref: 10 } },
            { name: "alias", type, value: { ref: 10 } },
          ] }],
          statics: [{ className: "Demo", fields: [{ name: "saved", type, value: { ref: 10 } }] }],
          heap: {
            10: { id: 10, type, kind: "box", value },
            11: { id: 11, type: "Object[]", kind: "array", elements: [{ ref: 10 }, { ref: 10 }] },
            12: { id: 12, type: "Holder", kind: "object", fields: [{ name: "value", type, value: { ref: 10 } }] },
          },
        }] };
        const original = structuredClone(modernTrace);
        const converted = convertModernTraceToOpt(modernTrace);
        const step = (converted.trace as any[])[0];

        expect(step.heap[10]).toEqual(["INSTANCE", type, ["___NO_LABEL!___", expected]]);
        expect(step.heap_attrs[10]).toEqual({ type });
        expect(step.stack_to_render[0].encoded_locals).toEqual({ box: ["REF", 10], alias: ["REF", 10] });
        expect(step.globals["Demo.saved"]).toEqual(["REF", 10]);
        expect(step.heap[11]).toEqual(["LIST", ["REF", 10], ["REF", 10]]);
        expect(step.heap[12][2]).toEqual(["value", ["REF", 10]]);
        for (const style of ["default", "compact", "inline"] as const) {
          const prepared = prepareStringTrace(converted, style);
          expect(prepared.trace[0].heap[10]).toEqual(step.heap[10]);
          expect(prepared.trace[0].stack_to_render[0].encoded_locals.alias).toEqual(["REF", 10]);
        }
        expect(modernTrace).toEqual(original);
      });
    });

    it("retains the labeled value representation for legacy primitive heap objects", () => {
      const converted = convertModernTraceToOpt({ code: "", steps: [{ line: 1, heap: {
        10: { id: 10, type: "Integer", kind: "primitive", value: 0 },
      } }] });
      expect((converted.trace as any[])[0].heap[10]).toEqual(["INSTANCE", "Integer", ["value", 0]]);
    });

    it("converts modern trace with stack frames, statics, and heap objects", () => {
      const modernTrace: ModernTrace = {
        code: "public class Test { static int count = 1; public static void main(String[] args) { int x = 5; } }",
        steps: [
          {
            line: 1,
            event: "step_line",
            method: "main",
            stdout: "Output line\n",
            stderr: "",
            callStack: [
              {
                methodName: "main",
                line: 1,
                isHighlighted: true,
                locals: [
                  { name: "x", type: "int", value: 5, final: false },
                  { name: "objRef", type: "Test", value: { ref: 200 }, final: true },
                ],
              },
            ],
            statics: [
              {
                className: "Test",
                fields: [{ name: "count", type: "int", value: 1, final: false }],
              },
            ],
            heap: {
              "200": {
                id: 200,
                type: "Test",
                kind: "object",
                fields: [{ name: "value", type: "int", value: 100, final: false }],
              },
              "300": {
                id: 300,
                type: "int[]",
                kind: "array",
                elements: [10, 20, 30],
              },
              "400": {
                id: 400,
                type: "String",
                kind: "string",
                value: "Sample string",
              },
              "500": {
                id: 500,
                type: "java.awt.Color",
                kind: "color",
                value: "#FF0000",
              },
              "600": {
                id: 600,
                type: "java.awt.Color",
                kind: "color",
                value: "#00FF0080",
              },
              "700": {
                id: 700,
                type: "lambda",
                kind: "lambda",
                sam: "int apply(int x) {\n  return x * 2;\n}",
              },
            },
          },
        ],
      };

      const result = convertModernTraceToOpt(modernTrace);
      expect(result).toHaveProperty("code", modernTrace.code);
      expect(result).toHaveProperty("trace");
      expect(Array.isArray(result["trace"])).toBe(true);

      const traceArray = result["trace"] as any[];
      expect(traceArray).toHaveLength(1);

      const step = traceArray[0];
      expect(step.line).toBe(1);
      expect(step.func_name).toBe("main");
      expect(step.stdout).toBe("Output line\n");

      // Verify stack conversion
      expect(step.stack_to_render).toHaveLength(1);
      const frame = step.stack_to_render[0];
      expect(frame.func_name).toBe("main:1");
      expect(frame.is_highlighted).toBe(true);
      expect(frame.ordered_varnames).toEqual(["x", "objRef"]);
      expect(frame.encoded_locals).toEqual({
        x: 5,
        objRef: ["REF", 200],
      });
      expect(frame.locals_attrs).toEqual({
        x: { type: "int", final: false },
        objRef: { type: "Test", final: true },
      });

      // Verify statics -> globals conversion
      expect(step.ordered_globals).toEqual(["Test.count"]);
      expect(step.globals).toEqual({ "Test.count": 1 });
      expect(step.globals_attrs).toEqual({
        "Test.count": { type: "int", final: false },
      });

      // Verify heap conversion
      expect(step.heap["200"]).toEqual(["INSTANCE", "Test", ["value", 100]]);
      expect(step.heap_attrs["200"]).toEqual({ type: ["int"], final: [false] });

      expect(step.heap["300"]).toEqual(["LIST", 10, 20, 30]);
      expect(step.heap_attrs["300"]).toEqual({ type: "int[]" });

      expect(step.heap["400"]).toEqual(["INSTANCE", "String", ["___NO_LABEL!___", "Sample string"]]);
      expect(step.heap_attrs["400"]).toEqual({ type: "java.lang.String" });

      expect(step.heap["500"]).toEqual(["COLOR", "java.awt.Color", "#FF0000"]);
      expect(step.heap_attrs["500"]).toEqual({ type: "java.awt.Color" });

      expect(step.heap["600"]).toEqual(["COLOR", "java.awt.Color", "#00FF0080"]);
      expect(step.heap_attrs["600"]).toEqual({ type: "java.awt.Color" });

      expect(step.heap["700"]).toEqual([
        "JAVA_LAMBDA",
        "int apply(int x) {\n  return x * 2;\n}",
      ]);
      expect(step.heap_attrs["700"]).toEqual({ type: "lambda" });
    });

    it.each(["object", "custom", undefined])(
      "preserves ordered field metadata for %s instances with omitted null values",
      (kind) => {
        const modernTrace: ModernTrace = {
          code: "",
          steps: [{
            line: 1,
            heap: {
              "77": {
                id: 77,
                type: "dependency.Leaf<java.lang.String>",
                kind,
                fields: [
                  { name: "item", type: "java.lang.String" },
                  { name: "untyped", value: 7, final: true },
                  { name: "next", type: "dependency.Box<java.lang.String>", value: null },
                  { name: "comparator", type: "java.util.Comparator<java.lang.String>", value: { ref: 82 }, final: true },
                ],
              },
            },
          }],
        };

        const step = (convertModernTraceToOpt(modernTrace).trace as any[])[0];
        expect(step.heap["77"]).toEqual([
          "INSTANCE",
          "dependency.Leaf<java.lang.String>",
          ["item", null],
          ["untyped", 7],
          ["next", null],
          ["comparator", ["REF", 82]],
        ]);
        expect(step.heap_attrs["77"]).toEqual({
          type: [
            "java.lang.String",
            undefined,
            "dependency.Box<java.lang.String>",
            "java.util.Comparator<java.lang.String>",
          ],
          final: [false, true, false, true],
        });
      },
    );

    it("converts breakpoints-based modern traces", () => {
      const modernTrace: ModernTrace = {
        code: "int a = 1; int b = 2;",
        breakpoints: {
          "1": { line: 1, method: "main", callStack: [] },
          "2": [{ line: 2, method: "main", callStack: [] }],
        },
      };

      const result = convertModernTraceToOpt(modernTrace);
      const traceArray = result["trace"] as any[];
      expect(traceArray).toHaveLength(2);
      expect(traceArray[0].line).toBe(1);
      expect(traceArray[1].line).toBe(2);
    });

    it("preserves stdinConsumed and stdinOffset across steps", () => {
      const modernTrace: ModernTrace = {
        code: "Scanner s = new Scanner(System.in); int x = s.nextInt();",
        stdin: "42\n",
        steps: [
          { line: 1, method: "main", stdinConsumed: "", stdinOffset: 0 },
          { line: 2, method: "main", stdinConsumed: "42", stdinOffset: 2 },
        ],
      };

      const result = convertModernTraceToOpt(modernTrace);
      const traceArray = result["trace"] as any[];
      expect(traceArray).toHaveLength(2);
      expect(traceArray[0].stdinConsumed).toBe("");
      expect(traceArray[0].stdinOffset).toBe(0);
      expect(traceArray[1].stdinConsumed).toBe("42");
      expect(traceArray[1].stdinOffset).toBe(2);
    });
  });
});
