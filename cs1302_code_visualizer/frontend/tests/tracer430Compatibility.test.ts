import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { create } from "../js/CodeVisualizer";
import { convertModernTraceToOpt, type ModernTrace } from "../js/modernTraceAdapter";
import { describeSvg } from "../js/svgDescription";

// One actual final captured state from docs/tracer-compatibility/Main.java,
// produced by the pinned 4.3.0 JAR. Guest reference IDs remain unmodified.
function fixture(): ModernTrace {
  return JSON.parse(readFileSync(resolve(__dirname, "fixtures/tracer-430-modern.json"), "utf8"));
}

function localIds(trace: ModernTrace): Record<string, number | string> {
  const frame = trace.steps![0].callStack!.find(frame => frame.locals?.some(local => local.name === "meeting"))!;
  return Object.fromEntries(frame.locals!.map(local => [local.name, (local.value as { ref: number }).ref]));
}

describe("tracer 4.3 date/time and set compatibility", () => {
  it("retains stored component types, nested references, and distinct live views", () => {
    const trace = fixture();
    const original = structuredClone(trace);
    const ids = localIds(trace);
    const step = (convertModernTraceToOpt(trace).trace as any[])[0];
    expect(step.heap[ids.original]).toEqual(["INSTANCE", "Duration", ["seconds", -1], ["nanos", 999999999]]);
    expect(step.heap_attrs[ids.original]).toEqual({ type: ["long", "int"], final: [true, true] });
    expect(step.heap[ids.elapsed]).toEqual(["INSTANCE", "Duration", ["seconds", 1], ["nanos", 999999999]]);
    expect(ids.elapsed).not.toEqual(ids.original);
    expect(step.heap[ids.meeting]).toEqual([
      "INSTANCE", "LocalDateTime", ["date", ["REF", ids.date]], ["time", ["REF", ids.time]],
    ]);
    expect(step.heap_attrs[ids.date]).toEqual({ type: ["int", "short", "short"], final: [true, true, true] });
    expect(step.heap_attrs[ids.time]).toEqual({ type: ["byte", "byte", "byte", "int"], final: [true, true, true, true] });
    expect(ids.alias).toEqual(ids.view);
    expect(new Set([ids.backing, ids.view, ids.second]).size).toBe(3);
    const last = trace.steps![0].heap![ids.backing].elements![2] as { ref: number };
    for (const id of [ids.backing, ids.view, ids.second]) {
      expect(step.heap[id]).toEqual(["LIST", ["REF", ids.item], null, ["REF", last.ref]]);
      expect(step.heap_attrs[id].type).toMatch(/(?:LinkedHashSet|UnmodifiableSet)/);
    }
    expect(step.heap[ids.item]).toEqual(["INSTANCE", "Main$Item", ["value", 2]]);
    expect(trace).toEqual(original);
  });

  it.each(["default", "compact", "inline"] as const)("renders shared time components and ordered set contents with %s strings", (stringStyle) => {
    const trace = fixture();
    const ids = localIds(trace);
    const original = structuredClone(trace);
    document.body.innerHTML = '<div id="compatibility"></div>';
    const element = document.getElementById("compatibility")!;
    const view = create({ lang: "java", trace, element, options: { stringStyle } });
    try {
      const object = (id: number | string) => element.querySelector(`.heapObject[data-object-id="${id}"]`)!;
      expect(element.querySelectorAll(`.heapObject[data-object-id="${ids.view}"]`)).toHaveLength(1);
      expect(object(ids.meeting).querySelector('[data-reference-target="' + ids.date + '"]')).not.toBeNull();
      expect(object(ids.meeting).querySelector('[data-reference-target="' + ids.time + '"]')).not.toBeNull();
      expect(object(ids.original).textContent).toContain("999999999");
      for (const id of [ids.backing, ids.view, ids.second]) {
        const set = object(id);
        const cells = Array.from(set.querySelectorAll(".listElt"));
        expect(cells).toHaveLength(3);
        expect(set.querySelector(".typeLabel")?.textContent).toContain("size 3");
        expect(cells[0].getAttribute("data-reference-target")).toBe(String(ids.item));
        expect(cells[1].textContent).toBe("null");
      }
      const description = describeSvg(element);
      expect(description.sections.filter(section => section.heading.startsWith(`Heap object ${ids.item}:`))).toHaveLength(1);
      expect(JSON.stringify(description)).toContain(`reference to object ${ids.view}`);
      expect(element.textContent).toContain("last");
      expect(trace).toEqual(original);
    } finally {
      view.destroy?.();
    }
  });
});
