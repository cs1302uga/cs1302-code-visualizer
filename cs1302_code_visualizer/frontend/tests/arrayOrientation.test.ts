import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { create, Options } from "../js/CodeVisualizer";
import { arrayOrientationOptionsFromParams } from "../js/arrayOrientation";

function fixture(name: string) {
  return JSON.parse(readFileSync(resolve(__dirname, `../../../docs/array-orientation/fixtures/${name}.json`), "utf8"));
}

function table(container: HTMLElement, id: number): HTMLTableElement {
  return container.querySelector(`.heapObject[id$="_heap_object_${id}"] > table`)!;
}

describe("array orientation rendering", () => {
  let container: HTMLElement;
  beforeEach(() => {
    document.body.innerHTML = '<div id="arrays"></div>';
    container = document.getElementById("arrays")!;
  });

  const cases: [string, Options, string[]][] = [
    ["default", {}, ["horizontal", "horizontal", "horizontal"]],
    ["vertical", { arrayOrientation: "vertical" }, ["vertical", "vertical", "vertical"]],
    ["alternating horizontal", { alternateArrayOrientations: true }, ["horizontal", "vertical", "horizontal"]],
    ["alternating vertical", { arrayOrientation: "vertical", alternateArrayOrientations: true }, ["vertical", "horizontal", "vertical"]],
    ["horizontal override", { arrayOrientations: { "4": "vertical" } }, ["horizontal", "horizontal", "vertical"]],
    ["vertical override", { arrayOrientation: "vertical", arrayOrientations: { "4": "horizontal" } }, ["vertical", "vertical", "horizontal"]],
    ["override alternating horizontal", { alternateArrayOrientations: true, arrayOrientations: { "2": "horizontal" } }, ["horizontal", "horizontal", "horizontal"]],
    ["override alternating vertical", { arrayOrientation: "vertical", alternateArrayOrientations: true, arrayOrientations: { "2": "vertical" } }, ["vertical", "vertical", "vertical"]],
  ];

  it.each(cases)("renders %s through forward and backward steps", (_name, options, orientations) => {
    const instance = create({ lang: "java", trace: fixture("dimensions"), element: container, options });
    for (const direction of ["stepBack", "stepForward", "stepBack"]) {
      instance.visualizer[direction]();
      [1, 2, 4].forEach((id, index) => {
        const tbl = table(container, id);
        expect(tbl).not.toBeNull();
        expect(tbl.classList.contains(`array-${orientations[index]}`)).toBe(true);
        const cells = [...tbl.rows].map(row => [...row.cells].map(cell => cell.className));
        const length = id === 4 ? 3 : 2;
        expect(cells).toEqual(orientations[index] === "vertical"
          ? Array.from({ length }, () => ["listHeader", "listElt"])
          : [Array(length).fill("listHeader"), Array(length).fill("listElt")]);
      });
      // Both parents point to one shared 1D array, even when a parent has an override.
      expect(container.querySelectorAll('.heapObject[id$="_heap_object_4"]')).toHaveLength(1);
      expect(container.querySelectorAll("._svg_connector")).toHaveLength(7);
      expect([...table(container, 4).querySelectorAll(".listElt")].map(c => c.textContent?.trim()))
        .toEqual(["10", direction === "stepForward" ? "99" : "20", "30"]);
    }
    instance.destroy?.();
  });

  it("preserves empty arrays, elision indices, nulls and collections", () => {
    const instance = create({ lang: "java", trace: fixture("edges"), element: container,
      options: { arrayOrientation: "vertical", alternateArrayOrientations: true,
        arrayOrientations: { "12": "vertical" } } });
    expect(table(container, 10).matches(".emptyList.array-vertical")).toBe(true);
    expect(table(container, 10).rows).toHaveLength(0);
    expect([...table(container, 11).querySelectorAll(".listHeader")].map(c => c.textContent))
      .toEqual(["0", "…", "6"]);
    expect(table(container, 11).textContent).toContain("70");
    expect(table(container, 12).rows).toHaveLength(2);
    expect(table(container, 12).classList.contains("array-vertical")).toBe(false);
    expect(table(container, 13).classList.contains("array-horizontal")).toBe(true);
    expect(table(container, 13).querySelector(".nullObj")).not.toBeNull();
    // Legacy arrays with no type metadata use the base; alternation needs a known rank.
    expect(table(container, 14).classList.contains("array-vertical")).toBe(true);
    instance.destroy?.();
  });

  it("uses modern array type metadata even with hidden type labels", () => {
    const instance = create({ lang: "java", element: container,
      options: { alternateArrayOrientations: true, includeTypes: false },
      trace: { code: "int[][] a;", steps: [{ line: 1, event: "step_line", method: "main",
        callStack: [{ methodName: "main", locals: [{ name: "a", type: "int[][]", value: { ref: 1 } }] }],
        heap: { "1": { kind: "array", type: "int[][]", elements: [{ ref: 2 }] },
          "2": { kind: "array", type: "int[]", elements: [5, 6, 7] } } }] } });
    expect(table(container, 1).classList.contains("array-vertical")).toBe(true);
    expect(table(container, 2).classList.contains("array-horizontal")).toBe(true);
    instance.destroy?.();
  });

  it("keeps options isolated between visualizers", () => {
    const other = document.createElement("div");
    document.body.append(other);
    const first = create({ lang: "java", element: container, trace: fixture("dimensions"),
      options: { arrayOrientation: "vertical" } });
    const second = create({ lang: "java", element: other, trace: fixture("dimensions") });
    expect(table(container, 4).classList.contains("array-vertical")).toBe(true);
    expect(table(other, 4).classList.contains("array-horizontal")).toBe(true);
    first.destroy?.();
    second.destroy?.();
  });

  it("alternates a 4D array by rank, not by the graph root or type label prefix", () => {
    const trace = fixture("dimensions");
    trace.trace.forEach(step => { step.heap_attrs["1"].type = "example.Item[][][][]"; });
    const instance = create({ lang: "java", element: container, trace,
      options: { alternateArrayOrientations: true, stripTypePrefixes: ["example."] } });
    expect(table(container, 1).classList.contains("array-vertical")).toBe(true);
    expect(table(container, 2).classList.contains("array-vertical")).toBe(true);
    instance.destroy?.();
  });

  it("falls back safely for invalid JavaScript option values", () => {
    const instance = create({ lang: "java", element: container, trace: fixture("dimensions"),
      options: { arrayOrientation: "diagonal", alternateArrayOrientations: "false",
        arrayOrientations: { "4": "diagonal" } } as unknown as Options });
    expect(table(container, 2).classList.contains("array-horizontal")).toBe(true);
    expect(table(container, 4).classList.contains("array-horizontal")).toBe(true);
    instance.destroy?.();
  });
});

describe("array orientation URL options", () => {
  it("parses the same options as the public factory", () => {
    expect(arrayOrientationOptionsFromParams(new URLSearchParams({
      arrayOrientation: "vertical", alternateArrayOrientations: "true",
      arrayOrientations: '{"42":"horizontal","43":"invalid"}',
    }))).toEqual({ arrayOrientation: "vertical", alternateArrayOrientations: true,
      arrayOrientations: { "42": "horizontal" } });
  });

  it.each(["invalid JSON", "null", "[]", '"vertical"'])("ignores malformed overrides: %s", value => {
    expect(arrayOrientationOptionsFromParams(new URLSearchParams({
      arrayOrientation: "diagonal", alternateArrayOrientations: "false", arrayOrientations: value,
    }))).toEqual({ arrayOrientation: "horizontal", alternateArrayOrientations: false });
  });
});
