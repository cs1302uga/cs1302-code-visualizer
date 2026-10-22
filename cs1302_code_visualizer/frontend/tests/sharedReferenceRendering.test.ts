import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { create, type Options, type VisualizerInstance } from "../js/CodeVisualizer";
import { describeSvg } from "../js/svgDescription";
import { exportSvg } from "../js/svgExport";
import { ConnectorRouting, type MeasuredConnectorScene } from "../js/connectorRouting";
import { measureConnectorScene } from "../js/connectorScene";
import { pathData } from "../js/referenceRouting";
import type { SvgConnection, SvgConnectorManager } from "../js/svgConnectors";
import { pathPoints } from "./routingFixture";

type Point = [number, number];

function fixture(name: string) {
  return JSON.parse(readFileSync(resolve(__dirname, `fixtures/reference-sharing/${name}.json`), "utf8"));
}

const instances: VisualizerInstance[] = [];

function render(name = "aliases", options: Options = {}) {
  const element = document.createElement("div");
  document.body.append(element);
  const instance = create({ lang: "java", trace: fixture(name), element, options: { includeTypes: false, ...options } });
  instances.push(instance);
  const manager = instance.visualizer.dataViz.jsPlumbInstance as SvgConnectorManager;
  manager.setReferenceSharingEnabled(true);
  return { element, instance, manager };
}

function locals(element: HTMLElement) {
  return Array.from(element.querySelectorAll<HTMLTableRowElement>(".stackFrameVarTable tr"), row => ({
    name: row.querySelector(".stackFrameVar")?.textContent?.trim(),
    target: row.querySelector(".stackFrameValue")?.getAttribute("data-reference-target"),
  }));
}

function relations(element: HTMLElement) {
  return locals(element).filter(row => row.target !== null).map(row => `${row.name}:${row.target}`).sort();
}

function referenceDescriptions(element: HTMLElement) {
  return describeSvg(element).sections.flatMap(section => section.items)
    .filter(item => item.includes("reference to object")).sort();
}

function shown(element: Element): boolean {
  for (let current: Element | null = element; current; current = current.parentElement) {
    const style = getComputedStyle(current);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
  }
  return true;
}

function points(element: Element): Point[] {
  return element.tagName.toLowerCase() === "path"
    ? pathPoints(element.getAttribute("d") ?? "")
    : (element.getAttribute("points") ?? "").trim().split(/\s+/)
      .filter(Boolean).map(pair => pair.split(",").map(Number) as Point);
}

function dot(connection: SvgConnection): Point {
  return [Number(connection.dotElement.getAttribute("cx")), Number(connection.dotElement.getAttribute("cy"))];
}

function near(a: Point, b: Point): boolean {
  return Math.hypot(a[0] - b[0], a[1] - b[1]) < 0.02;
}

function onSegment(point: Point, a: Point, b: Point): boolean {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const length = dx * dx + dy * dy;
  if (!length) return near(point, a);
  const t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length;
  return t >= 0 && t <= 1 && near(point, [a[0] + t * dx, a[1] + t * dy]);
}

/** Follow actual visible path direction, including a branch ending inside a trunk.
 * Hidden complete member routes and group membership metadata are not consulted.
 */
function reachableHeads(start: Point, canvas: Element, stroke?: string): Point[] {
  const paths = Array.from(canvas.querySelectorAll("path")).filter(shown)
    .filter(path => !stroke || path.getAttribute("stroke") === stroke).map(points)
    .filter(path => path.length > 1);
  const heads = Array.from(canvas.querySelectorAll("polygon")).filter(shown).map(points)
    .filter(head => head.length === 3);
  const queue = [start], seen: Point[] = [], reached: Point[] = [];
  while (queue.length) {
    const current = queue.shift()!;
    if (seen.some(point => near(point, current))) continue;
    seen.push(current);
    for (const head of heads) {
      const rear: Point = [(head[1][0] + head[2][0]) / 2, (head[1][1] + head[2][1]) / 2];
      if (near(current, rear) && !reached.some(point => near(point, head[0]))) reached.push(head[0]);
    }
    for (const path of paths) {
      const end = path[path.length - 1];
      if (near(current, end)) continue;
      if (path.slice(1).some((point, index) => onSegment(current, path[index], point))) queue.push(end);
    }
  }
  return reached;
}

function assertVisibleRelationships(manager: SvgConnectorManager) {
  for (const connection of manager.connections.filter(connection => shown(connection.groupElement))) {
    const heads = reachableHeads(dot(connection), manager.svgCanvas);
    expect(heads, `visible directed path from ${connection.sourceId}`).toHaveLength(1);
    const body = connection.target[0].querySelector("table") ?? connection.target[0];
    const target = body.getBoundingClientRect();
    const [x, y] = heads[0];
    expect((Math.abs(x - target.left) < 0.02 || Math.abs(x - target.right) < 0.02)
      && y >= target.top && y <= target.bottom ||
      (Math.abs(y - target.top) < 0.02 || Math.abs(y - target.bottom) < 0.02)
      && x >= target.left && x <= target.right, `${connection.sourceId} reaches ${connection.targetId}`).toBe(true);
  }
}

/** Geometry support seam only. Text/font/crop acceptance lives in native browser tests. */
function measureAliasScene(element: HTMLElement, manager: SvgConnectorManager, firstTargetLeft = 180, firstTargetTop = 40) {
  const rects = new Map<Element, DOMRect>();
  const assign = (node: Element | null, x: number, y: number, width: number, height: number) => {
    if (node) rects.set(node, new DOMRect(x, y, width, height));
  };
  assign(manager.container, 0, 0, 500, 400);
  assign(element.querySelector("#dataViz"), 0, 0, 500, 400);
  for (const frame of element.querySelectorAll(".stackFrame")) assign(frame, 20, 110, 88, 200);
  for (const [index, connection] of manager.connections.entries()) {
    const box = connection.source[0].closest(".value-box")!;
    const top = 140 + index * 40;
    assign(box, 50, top, 50, 20);
    assign(connection.source[0], 50, top, 50, 20);
  }
  for (const object of element.querySelectorAll(".heapObject[data-object-id]")) {
    const first = object.getAttribute("data-object-id") === "1";
    const r = first ? [firstTargetLeft, firstTargetTop, 70, 50] : [350, 250, 70, 50];
    assign(object, r[0], r[1], r[2], r[3]);
    assign(object.querySelector("table"), r[0], r[1], r[2], r[3]);
  }
  useMeasuredRects(manager, rects);
}

function useMeasuredRects(manager: SvgConnectorManager, rects: Map<Element, DOMRect>) {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const measured = rects.get(this);
    if (measured) return measured;
    if (this.matches("path,polygon")) {
      const ps = points(this);
      if (!ps.length) return new DOMRect();
      const xs = ps.map(p => p[0]), ys = ps.map(p => p[1]);
      return new DOMRect(Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    }
    if (this.matches("circle")) {
      const radius = Number(this.getAttribute("r"));
      return new DOMRect(Number(this.getAttribute("cx")) - radius, Number(this.getAttribute("cy")) - radius, radius * 2, radius * 2);
    }
    return new DOMRect();
  });
  manager.repaintEverything();
}

function paintedSnapshot(manager: SvgConnectorManager) {
  return Array.from(manager.svgCanvas.querySelectorAll("path,polygon,circle")).filter(shown)
    .map(node => [node.tagName, node.getAttribute("d"), node.getAttribute("points"),
      node.getAttribute("cx"), node.getAttribute("cy"), node.getAttribute("stroke"), node.getAttribute("fill")])
    .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
}

function groupedConnections(manager: SvgConnectorManager) {
  return manager.connections.filter(connection => connection.branchElement && shown(connection.branchElement));
}

beforeEach(() => { document.body.innerHTML = ""; });
afterEach(() => {
  for (const instance of instances.splice(0)) instance.destroy?.();
  vi.restoreAllMocks();
});

describe("shared references through public visualizer creation", () => {
  it("keeps sharing an internal opt-in rather than changing public creation defaults", () => {
    const element = document.createElement("div");
    document.body.append(element);
    const instance = create({ lang: "java", trace: fixture("aliases"), element });
    instances.push(instance);
    const manager = instance.visualizer.dataViz.jsPlumbInstance as SvgConnectorManager;
    expect(manager.referenceSharingEnabled).toBe(false);
    manager.setReferenceSharingEnabled(true);
    expect(manager.referenceSharingEnabled).toBe(true);
    manager.setReferenceSharingEnabled(false);
    expect(manager.referenceSharingEnabled).toBe(false);
  });

  it("preserves every named reference and distinguishes equal-looking object identities", () => {
    const { element, manager } = render();
    expect(relations(element)).toEqual(["a:1", "b:1", "c:1", "equalCopy:2"]);
    expect(manager.connections).toHaveLength(4);
    expect(new Set(manager.connections.map(connection => connection.sourceId)).size).toBe(4);
    expect(new Set(manager.connections.map(connection => connection.targetId)).size).toBe(2);
    expect(referenceDescriptions(element)).toEqual([
      "a: reference to object 1", "b: reference to object 1", "c: reference to object 1", "equalCopy: reference to object 2",
    ]);
    expect(describeSvg(element).sections.filter(section => section.heading.startsWith("Heap object"))).toHaveLength(2);
  });

  it("removes reassigned memberships and restores the same relationships by playback and direct seeking", () => {
    const { element, instance, manager } = render();
    const original = referenceDescriptions(element);
    instance.visualizer.stepBack();
    expect(relations(element)).toEqual(["a:1", "b:2", "c:1", "equalCopy:2"]);
    expect(manager.connections).toHaveLength(4);
    instance.visualizer.stepBack();
    expect(referenceDescriptions(element)).toEqual(original);
    instance.visualizer.renderStep(2);
    expect(referenceDescriptions(element)).toEqual(original);
    const recreated = render();
    expect(referenceDescriptions(recreated.element)).toEqual(original);
    expect(relations(recreated.element)).toEqual(relations(element));
  });

  it("counts twelve reference-valued locations separately from the single heap object", () => {
    const { element, manager } = render("dense-aliases");
    expect(manager.connections).toHaveLength(12);
    expect(referenceDescriptions(element)).toHaveLength(12);
    expect(describeSvg(element).sections.filter(section => section.heading.startsWith("Heap object"))).toHaveLength(1);
  });

  it.each([
    { hideVars: [] }, { hideVars: ["main:a", "main:b"] }, { hideVars: ["main:a", "main:b", "main:c"] },
  ])(
    "keeps filtered sources absent from both connections and descriptions: $hideVars", ({ hideVars }) => {
      const { element, manager } = render("aliases", { hideVars });
      expect(manager.connections).toHaveLength(4 - hideVars.length);
      for (const hidden of hideVars) {
        const name = hidden.slice("main:".length);
        expect(locals(element).some(row => row.name === name)).toBe(false);
        expect(referenceDescriptions(element).some(item => item.startsWith(`${name}:`))).toBe(false);
      }
    },
  );

  it("retains fields, map key/value sources, self-reference, cycles, and shared indexed rows", () => {
    const { element, manager } = render("structures");
    const description = describeSvg(element);
    const object = (id: number) => description.sections.find(section => section.heading.startsWith(`Heap object ${id}:`))!;
    expect(object(1).items).toContain("self: reference to object 1");
    expect(object(1).items).toContain("next: reference to object 2");
    expect(object(2).items).toContain("next: reference to object 1");
    expect(object(3).items).toEqual(["Index 0: reference to object 1", "Index 1: reference to object 1", "Index 2: reference to object 2", "Index 3: null"]);
    expect(object(4).items).toEqual(["Index 0: reference to object 3", "Index 1: reference to object 3"]);
    expect(object(7).items).toEqual(["reference to object 1: reference to object 2", "reference to object 2: reference to object 1"]);
    expect(manager.connections.filter(connection => connection.source[0].closest(".dictKey"))).toHaveLength(2);
    expect(description.sections.filter(section => section.heading.startsWith("Heap object"))).toHaveLength(7);
  });

  it("keeps active and inactive source-frame meanings distinct in both themes", () => {
    for (const theme of ["light", "dark"] as const) {
      const { manager } = render("structures", { theme });
      const stack = manager.connections.filter(connection => connection.source[0].closest(".stackFrame"));
      const inactive = stack.filter(connection => connection.sourceId.includes("caller_1"));
      const active = stack.filter(connection => connection.sourceId.includes("main_2"));
      expect(inactive).toHaveLength(1);
      expect(active.length).toBeGreaterThan(1);
      expect(inactive[0].semanticStyle).toBe("reference-inactive");
      expect(active.every(connection => connection.semanticStyle === "reference-active")).toBe(true);
      expect(active.some(connection => connection.targetId === inactive[0].targetId)).toBe(true);
    }
  });

  it.each(["horizontal", "vertical"] as const)("keeps array semantics under %s orientation", arrayOrientation => {
    const { element } = render("structures", { arrayOrientation, alternateArrayOrientations: true });
    const description = referenceDescriptions(element);
    expect(description.filter(item => item === "Index 0: reference to object 3")).toHaveLength(1);
    expect(description.filter(item => item === "Index 1: reference to object 3")).toHaveLength(1);
    expect(element.querySelector('.heapObject[data-object-id="3"] .listTbl')?.classList.contains(`array-${arrayOrientation}`)).toBe(true);
  });

  it.each(["default", "compact", "inline"] as const)("retains %s string presentation without deriving aliases from literal equality", stringStyle => {
    const { element, manager } = render("structures", { stringStyle });
    const strings = manager.connections.filter(connection => /_heap_object_[56]$/.test(connection.targetId));
    expect(strings).toHaveLength(stringStyle === "default" ? 5 : 0);
    const byName = Object.fromEntries(locals(element).map(row => [row.name!, row.target]));
    expect(byName.absent).toBeNull();
    expect(byName.firstString).toBe(stringStyle === "inline" ? null : "5");
    expect(byName.aliasString).toBe(stringStyle === "inline" ? null : "5");
    expect(byName.equalString).toBe(stringStyle === "inline" ? null : "6");
    expect(element.querySelectorAll(".compact-string-arrow")).toHaveLength(stringStyle === "compact" ? 5 : 0);
  });
});

describe("visible shared-reference paint and lifecycle", () => {
  it.each(["independent", "shared"] as const)("plans %s from a frozen measured DTO with no DOM access", policy => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    manager.setReferenceRoutingPolicy(policy);
    const input = JSON.parse(JSON.stringify(measureConnectorScene(manager.container, manager.connections).scene)) as MeasuredConnectorScene;
    const freeze = (value: unknown) => {
      if (value && typeof value === "object") {
        Object.values(value).forEach(freeze);
        Object.freeze(value);
      }
    };
    freeze(input);
    const before = JSON.stringify(input), markup = manager.container.innerHTML;
    const read = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(() => { throw new Error("DOM read in planner"); });
    const style = vi.spyOn(window, "getComputedStyle").mockImplementation(() => { throw new Error("style read in planner"); });
    const write = vi.spyOn(Element.prototype, "setAttribute").mockImplementation(() => { throw new Error("DOM write in planner"); });
    const planner = new ConnectorRouting();
    let result = planner.plan(input, false, policy);
    if (result.ok === false && result.constraint.kind === "reservation-retry") result = planner.plan(input, true, policy);
    read.mockRestore(); style.mockRestore(); write.mockRestore();
    expect(result.ok).toBe(true);
    expect(JSON.stringify(input)).toBe(before);
    expect(manager.container.innerHTML).toBe(markup);
    if (result.ok) {
      expect(result.plan.sharingPlan?.baselineValid).toBe(true);
      for (const connector of result.plan.connectors)
        expect(pathData(connector.route)).toBe(manager.connections[connector.connectionIndex].pathElement.getAttribute("d"));
    }
  });

  it("invalidates accepted shared paint during a batched policy change and clears it on a failed settle", () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-group").length).toBeGreaterThan(0);
    const planner = vi.spyOn(ConnectorRouting.prototype, "plan");
    manager.beginBatch();
    manager.setReferenceRoutingPolicy("independent");
    expect(planner).not.toHaveBeenCalled();
    expect(manager.layoutCoordinator.acceptedPlan).toBeUndefined();
    expect(manager.referenceSharingPlan).toBeUndefined();
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-group")).toHaveLength(0);
    expect(manager.connections.every(connection => !shown(connection.groupElement))).toBe(true);
    manager.endBatch();
    expect(planner).toHaveBeenCalled();
    expect(planner.mock.calls.every(([, , policy]) => policy === "independent")).toBe(true);
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    assertVisibleRelationships(manager);
    planner.mockClear();
    manager.repaintEverything();
    expect(planner).not.toHaveBeenCalled();
    manager.setReferenceRoutingPolicy("shared");
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-group").length).toBeGreaterThan(0);
    planner.mockImplementation(() => { throw new Error("controlled settle failed"); });
    manager.layoutCoordinator.placement.invalidate();
    expect(() => manager.repaintEverything()).toThrow("controlled settle failed");
    expect(manager.layoutCoordinator.acceptedPlan).toBeUndefined();
    expect(manager.referenceSharingPlan).toBeUndefined();
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-group")).toHaveLength(0);
    expect(manager.connections.every(connection => !shown(connection.groupElement))).toBe(true);
    planner.mockRestore();
    manager.repaintEverything();
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    assertVisibleRelationships(manager);
  });

  it.each(["", "duplicate-source"])("keeps distinct element sources with ID %j independent", sourceId => {
    const { element, manager } = render();
    const original = manager.connections.slice(0, 2).map(connection => ({
      source: connection.source[0], target: connection.target[0],
    }));
    manager.reset();
    manager.beginBatch();
    for (const { source, target } of original) {
      source.id = sourceId;
      manager.connect({ source, target, scope: "varValuePointer", semanticStyle: "reference-active" });
    }
    manager.endBatch();
    expect(() => measureAliasScene(element, manager)).not.toThrow();
    expect(manager.connections).toHaveLength(2);
    expect(manager.connections.map(connection => connection.sourceId)).toEqual([sourceId, sourceId]);
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-segment,.shared-reference-head")).toHaveLength(0);
    expect(Array.from(manager.svgCanvas.querySelectorAll("polygon")).filter(shown)).toHaveLength(2);
    assertVisibleRelationships(manager);
    const before = paintedSnapshot(manager);
    manager.connections.reverse();
    manager.repaintEverything();
    expect(paintedSnapshot(manager)).toEqual(before);
  });

  it("follows visible directed paths from every source to its actual target", () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-segment").length,
      JSON.stringify(manager.referenceSharingPlan?.diagnostics)).toBeGreaterThan(0);
    expect(Array.from(manager.svgCanvas.querySelectorAll("polygon")).filter(shown).length).toBeLessThan(manager.connections.length);
    assertVisibleRelationships(manager);
    expect(manager.svgCanvas.querySelectorAll("circle")).toHaveLength(manager.connections.length);
    expect(new Set(manager.connections.map(connection => dot(connection).join(","))).size).toBe(manager.connections.length);
  });

  it("uses target ordering only for crowded controlled scenes and restores state and insertion order", () => {
    const { element, instance, manager } = render();
    const ordering = () => manager.layoutCoordinator.acceptedPlan?.baselineOrdering;
    measureAliasScene(element, manager);
    expect(ordering()).toBe("source");
    instance.visualizer.renderStep(1);
    // Two interleaved targets require 14px of lanes, but this measured gap is 12px.
    measureAliasScene(element, manager, 112);
    expect(ordering()).toBe("target");
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    const targetIds = [1, 2].map(id => element.querySelector(`.heapObject[data-object-id="${id}"]`)!.id);
    expect(manager.referenceSharingPlan?.routes.map(route => route.targetKey)).toEqual([
      targetIds[0], targetIds[0], targetIds[1], targetIds[1],
    ]);
    assertVisibleRelationships(manager);
    const crowded = paintedSnapshot(manager);
    manager.connections.reverse();
    manager.repaintEverything();
    expect(ordering()).toBe("target");
    expect(paintedSnapshot(manager)).toEqual(crowded);
    manager.setReferenceRoutingPolicy("historical");
    expect(ordering()).toBe("source");
    manager.setReferenceRoutingPolicy("independent");
    expect(ordering()).toBe("target");
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    assertVisibleRelationships(manager);
    manager.setReferenceRoutingPolicy("shared");
    expect(paintedSnapshot(manager)).toEqual(crowded);

    instance.visualizer.renderStep(2);
    measureAliasScene(element, manager, 112);
    expect(relations(element)).toContain("b:1");
    instance.visualizer.renderStep(1);
    measureAliasScene(element, manager, 112);
    expect(ordering()).toBe("target");
    expect(paintedSnapshot(manager)).toEqual(crowded);
    assertVisibleRelationships(manager);

    measureAliasScene(element, manager);
    expect(ordering()).toBe("source");
    const roomy = paintedSnapshot(manager);
    const unrelatedTarget = element.querySelector<HTMLElement>('.heapObject[data-object-id="2"]')!;
    unrelatedTarget.style.display = "none";
    manager.repaintEverything();
    expect(ordering()).toBe("source");
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    assertVisibleRelationships(manager);
    unrelatedTarget.style.display = "";
    manager.repaintEverything();
    expect(ordering()).toBe("source");
    expect(paintedSnapshot(manager)).toEqual(roomy);
  });

  it("paints two compatible semantic groups to one exact target without combining their meanings", () => {
    const { element, manager } = render("dense-aliases");
    manager.beginBatch();
    manager.connections.forEach((connection, index) => connection.setSemanticStyle(
      index < 6 ? "reference-active" : "reference-inactive"));
    manager.endBatch();
    // The target lies between the two cohorts, leaving separate approach corridors.
    measureAliasScene(element, manager, 180, 350);
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    const groups = Array.from(manager.svgCanvas.querySelectorAll(".shared-reference-group"));
    expect(groups.length, JSON.stringify(manager.referenceSharingPlan?.diagnostics)).toBeGreaterThanOrEqual(2);
    const targets = new Set(manager.connections.map(connection => connection.targetId));
    expect(targets.size).toBe(1);
    const grouped = groupedConnections(manager);
    expect(new Set(grouped.map(connection => connection.semanticStyle))).toEqual(
      new Set(["reference-active", "reference-inactive"]));
    for (const style of ["reference-active", "reference-inactive"]) {
      expect(grouped.filter(connection => connection.semanticStyle === style).length).toBeGreaterThanOrEqual(2);
    }
    for (const group of groups) {
      const members = grouped.filter(connection => connection.groupElement.dataset.sharedReference ===
        (group as SVGGElement).dataset.sharedReference);
      expect(members.length).toBeGreaterThanOrEqual(2);
      expect(new Set(members.map(connection => connection.semanticStyle)).size).toBe(1);
      expect(new Set(members.map(connection => connection.targetId))).toEqual(targets);
    }
    assertVisibleRelationships(manager);
    expect(referenceDescriptions(element)).toHaveLength(12);
    const before = paintedSnapshot(manager);
    manager.connections.reverse();
    manager.repaintEverything();
    expect(paintedSnapshot(manager)).toEqual(before);
  });

  it("retains a three-node cycle and long source names in a narrow measured container", () => {
    const { element, manager } = render("cycle-long-labels");
    element.style.width = "340px";
    const rects = new Map<Element, DOMRect>();
    const assign = (node: Element | null, x: number, y: number, width: number, height: number) => {
      if (node) rects.set(node, new DOMRect(x, y, width, height));
    };
    assign(manager.container, 0, 0, 340, 400);
    assign(element.querySelector("#dataViz"), 0, 0, 340, 400);
    for (const frame of element.querySelectorAll(".stackFrame")) assign(frame, 10, 15, 155, 130);
    for (const object of element.querySelectorAll(".heapObject[data-object-id]")) {
      const top = 20 + (Number(object.getAttribute("data-object-id")) - 1) * 140;
      assign(object, 200, top, 120, 70);
      assign(object.querySelector("table"), 200, top, 120, 70);
    }
    let localIndex = 0;
    for (const connection of manager.connections) {
      const owner = connection.source[0].closest(".heapObject");
      const x = owner ? 270 : 100;
      const y = owner ? 55 + (Number(owner.getAttribute("data-object-id")) - 1) * 140 : 55 + localIndex++ * 30;
      assign(connection.source[0], x, y, 40, 20);
      assign(connection.source[0].closest(".value-box"), x, y, 40, 20);
    }
    useMeasuredRects(manager, rects);
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    expect(manager.connections).toHaveLength(6);
    assertVisibleRelationships(manager);
    const description = describeSvg(element);
    for (const [source, target] of [[1, 2], [2, 3], [3, 1]]) {
      const section = description.sections.find(item => item.heading.startsWith(`Heap object ${source}:`));
      expect(section?.items).toContain(`nextNodeInTheCycle: reference to object ${target}`);
    }
    expect(locals(element).map(row => row.name)).toEqual([
      "entryPointWithALongDescriptiveName", "anotherReferenceToTheEntryPoint", "thirdReferenceToTheEntryPoint",
    ]);
    expect(element.style.width).toBe("340px");
    expect(description.sections.filter(section => section.heading.startsWith("Heap object"))).toHaveLength(3);
    expect(groupedConnections(manager).every(connection => !connection.source[0].closest(".heapObject"))).toBe(true);
    const before = paintedSnapshot(manager);
    manager.repaintEverything();
    expect(paintedSnapshot(manager)).toEqual(before);
  });

  it("keeps geometry and sibling stems stable while emphasizing one complete reference", () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    const selected = groupedConnections(manager)[0];
    expect(selected).toBeDefined();
    const geometry = () => paintedSnapshot(manager).map(row => row.slice(0, 5));
    const before = geometry();
    selected.setHover(true);
    expect(geometry()).toEqual(before);
    expect(reachableHeads(dot(selected), manager.svgCanvas, selected.hoverPaintStyle.strokeStyle)).toHaveLength(1);
    for (const sibling of manager.connections.filter(connection => connection !== selected)) {
      expect(sibling.dotElement.getAttribute("fill")).toBe(sibling.paintStyle.strokeStyle);
    }
    selected.setHover(false);
    expect(geometry()).toEqual(before);
    assertVisibleRelationships(manager);
  });

  it("restores deterministic paint after base-style changes and connection-order permutations", () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    const before = paintedSnapshot(manager);
    const selected = groupedConnections(manager)[0];
    expect(selected).toBeDefined();
    const previousStyle = selected.semanticStyle;
    selected.setSemanticStyle("reference-inactive");
    expect(shown(selected.pathElement)).toBe(true);
    assertVisibleRelationships(manager);
    selected.setSemanticStyle(previousStyle);
    expect(paintedSnapshot(manager)).toEqual(before);
    const previousColor = selected.paintStyle.strokeStyle;
    selected.setPaintStyle({ strokeStyle: "#812345" });
    expect(shown(selected.pathElement)).toBe(true);
    assertVisibleRelationships(manager);
    selected.setPaintStyle({ strokeStyle: previousColor });
    expect(paintedSnapshot(manager)).toEqual(before);
    manager.connections.reverse();
    manager.repaintEverything();
    expect(paintedSnapshot(manager)).toEqual(before);
  });

  it("requires an explicit semantic declaration for custom paint even with a manager default", () => {
    const { element, manager } = render();
    const original = manager.connections.map(connection => ({
      source: connection.source[0], target: connection.target[0],
      paintStyle: { ...connection.paintStyle }, hoverPaintStyle: { ...connection.hoverPaintStyle },
    }));
    expect(manager.defaults.SemanticStyle).toBe("reference-active");
    manager.reset();
    manager.beginBatch();
    for (const options of original) manager.connect({ ...options, scope: "varValuePointer" });
    manager.endBatch();
    measureAliasScene(element, manager);
    expect(manager.connections.every(connection => connection.semanticStyle === null)).toBe(true);
    expect(groupedConnections(manager)).toHaveLength(0);
    expect(Array.from(manager.svgCanvas.querySelectorAll("polygon")).filter(shown)).toHaveLength(4);
    assertVisibleRelationships(manager);
    manager.beginBatch();
    for (const connection of manager.connections) connection.setSemanticStyle("reference-active");
    manager.endBatch();
    expect(groupedConnections(manager).length).toBeGreaterThan(0);
    assertVisibleRelationships(manager);
  });

  it("revalidates changed emphasis styles and preserves geometry during compatible wide emphasis", () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    const selected = groupedConnections(manager)[0];
    expect(selected).toBeDefined();
    const before = paintedSnapshot(manager);
    const originalHover = { ...selected.hoverPaintStyle };
    selected.setHoverPaintStyle({ strokeStyle: "#812345" });
    expect(shown(selected.pathElement)).toBe(true);
    assertVisibleRelationships(manager);
    selected.setHoverPaintStyle(originalHover);
    expect(paintedSnapshot(manager)).toEqual(before);

    manager.beginBatch();
    for (const connection of manager.connections) connection.setHoverPaintStyle({ lineWidth: 3 });
    manager.endBatch();
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    const wide = groupedConnections(manager)[0];
    expect(wide).toBeDefined();
    const geometry = () => paintedSnapshot(manager).map(row => row.slice(0, 5));
    const wideBefore = geometry();
    wide.setHover(true);
    expect(geometry()).toEqual(wideBefore);
    expect(reachableHeads(dot(wide), manager.svgCanvas, wide.hoverPaintStyle.strokeStyle)).toHaveLength(1);
    const emphasizedPaths = Array.from(manager.svgCanvas.querySelectorAll("path"))
      .filter(path => shown(path) && path.getAttribute("stroke") === wide.hoverPaintStyle.strokeStyle);
    expect(emphasizedPaths.length).toBeGreaterThan(1);
    expect(emphasizedPaths.every(path => path.getAttribute("stroke-width") === "3")).toBe(true);
    for (const sibling of manager.connections.filter(connection => connection !== wide)) {
      expect(sibling.dotElement.getAttribute("fill")).toBe(sibling.paintStyle.strokeStyle);
      if (sibling.branchElement && shown(sibling.branchElement)) {
        expect(sibling.branchElement.getAttribute("stroke")).toBe(sibling.paintStyle.strokeStyle);
      }
    }
    wide.setHover(false);
    expect(geometry()).toEqual(wideBefore);
    assertVisibleRelationships(manager);
  });

  it("preserves surviving visible routes through individual detach and reset", () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    const [removed, survivingMember] = groupedConnections(manager);
    expect(removed).toBeDefined();
    expect(survivingMember).toBeDefined();
    removed.detach();
    expect(manager.connections).not.toContain(removed);
    expect(removed.dotElement.isConnected).toBe(false);
    assertVisibleRelationships(manager);
    expect(shown(survivingMember.pathElement)).toBe(true);
    for (const connection of [...manager.connections].slice(0, 2)) connection.detach();
    expect(manager.connections).toHaveLength(1);
    assertVisibleRelationships(manager);
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-segment,.shared-reference-head")).toHaveLength(0);
    manager.reset();
    expect(manager.connections).toHaveLength(0);
    expect(manager.svgCanvas.querySelectorAll("path,polygon,circle")).toHaveLength(0);
  });

  it("removes a hidden member's physical path and restores grouping when it reappears", () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    const before = paintedSnapshot(manager);
    const selected = groupedConnections(manager)[0];
    expect(selected).toBeDefined();
    selected.source[0].style.display = "none";
    manager.repaintEverything();
    expect(shown(selected.groupElement)).toBe(false);
    expect(reachableHeads(dot(selected), manager.svgCanvas)).toHaveLength(0);
    assertVisibleRelationships(manager);
    selected.source[0].style.display = "";
    manager.repaintEverything();
    expect(paintedSnapshot(manager)).toEqual(before);
    assertVisibleRelationships(manager);
  });

  it("removes out-of-container paint and restores it when the original container is selected", () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    const before = paintedSnapshot(manager);
    const originalContainer = manager.container;
    const other = document.createElement("div");
    document.body.append(other);
    manager.setContainer(other);
    expect(manager.svgCanvas.parentElement).toBe(other);
    expect(Array.from(manager.svgCanvas.querySelectorAll("path,polygon,circle")).filter(shown)).toHaveLength(0);
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-segment,.shared-reference-head")).toHaveLength(0);
    manager.setContainer(originalContainer);
    expect(paintedSnapshot(manager)).toEqual(before);
    assertVisibleRelationships(manager);
  });

  it("exports the visible physical paint and full source descriptions without junction objects", async () => {
    const { element, manager } = render();
    measureAliasScene(element, manager);
    Object.defineProperty(document, "fonts", { configurable: true, value: { ready: Promise.resolve() } });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ measureText: () => ({ fontBoundingBoxDescent: 2 }) } as any);
    const createRange = document.createRange.bind(document);
    vi.spyOn(document, "createRange").mockImplementation(() => Object.assign(createRange(), {
      getBoundingClientRect: () => new DOMRect(), getClientRects: () => [] as any,
    }));
    for (const primitive of manager.svgCanvas.querySelectorAll<SVGGraphicsElement>("path,polygon,circle")) {
      Object.defineProperty(primitive, "getScreenCTM", { configurable: true, value: () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }) });
      vi.spyOn(primitive, "getClientRects").mockImplementation(() => shown(primitive) ? [primitive.getBoundingClientRect()] as any : []);
    }
    const svg = new DOMParser().parseFromString(await exportSvg(element), "image/svg+xml");
    const sourcePaint = Array.from(manager.svgCanvas.querySelectorAll("path,polygon,circle")).filter(shown);
    expect(svg.querySelectorAll("path,polygon,circle")).toHaveLength(sourcePaint.length);
    expect(svg.querySelectorAll("circle")).toHaveLength(4);
    expect(svg.querySelector("foreignObject,image,script")).toBeNull();
    expect(JSON.parse(svg.querySelector("metadata")!.textContent!)).toEqual(describeSvg(element));
    expect(svg.querySelector("desc")!.textContent).toContain("b: reference to object 1");
    expect(describeSvg(element).sections.filter(section => section.heading.startsWith("Heap object"))).toHaveLength(2);
  });
});
