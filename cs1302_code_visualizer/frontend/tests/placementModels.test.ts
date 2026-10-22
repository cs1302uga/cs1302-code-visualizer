import { afterEach, describe, expect, it, vi } from "vitest";
import $ from "jquery";
import { ExecutionVisualizer } from "../js/pytutor";
import { LegacyStackGlobalsPlacement, PlacementController, PlacementJournal,
  type HeapPlacementModel, type StackGlobalsPlacementModel } from "../js/placementModels";

const views: ExecutionVisualizer[] = [];
let nextRoot = 0;

function frame(id: number, locals: Record<string, any> = { value: id }, order = Object.keys(locals)) {
  return { unique_hash: `frame-${id}`, frame_id: id, func_name: `method${id}`,
    is_highlighted: id === 0, is_zombie: false, is_parent: false,
    parent_frame_id_list: [], ordered_varnames: order, encoded_locals: locals,
    locals_attrs: Object.fromEntries(order.map(name => [name, { type: "int" }])) };
}

function state(stack = [frame(0)], globals: Record<string, any> = {}, heap: Record<string, any> = {},
  orderedGlobals = Object.keys(globals)) {
  return { event: "step_line", line: 1, func_name: "main", stdout: "",
    stack_to_render: stack, globals, ordered_globals: orderedGlobals, heap };
}

function render(states: any[], options: Record<string, any> = {}, layoutTypes: string[] = []) {
  const root = document.createElement("div");
  root.id = `placement-${nextRoot++}`;
  document.body.append(root);
  const input = { code: "class Driver { void main() {} }", trace: states, _layoutTypes: layoutTypes };
  const view = new ExecutionVisualizer(root.id, input, {
    lang: "java", hideCode: true, disableHeapNesting: true, textualMemoryLabels: true, ...options,
  });
  views.push(view);
  const data = view.dataViz;
  const manager = data.jsPlumbInstance;
  const placement = manager.layoutCoordinator.placement as PlacementController;
  return { root, view, data, manager, placement, input };
}

function frameOrder(root: HTMLElement) {
  return [...root.querySelectorAll("#stack > .stackFrame")].map(element => element.getAttribute("data-frame_id"));
}

function heapRows(root: HTMLElement) {
  return [...root.querySelectorAll("#heap > .heapRow")].map(row =>
    [...row.querySelectorAll(":scope > .toplevelHeapObject > .heapObject")].map(object =>
      Number((object as HTMLElement).dataset.objectId)));
}

function globalOrder(root: HTMLElement) {
  return [...root.querySelectorAll("#globals_area .stackVarName")].map(element => element.textContent);
}

function topologyStates() {
  const node = (next: any) => ["INSTANCE", "Node", ["next", next]];
  return [
    state([frame(1), frame(0)], { head: ["REF", 1] }, { 1: node(["REF", 2]), 2: node(null) }),
    state([frame(2), frame(1), frame(0)], { head: ["REF", 3] },
      { 1: node(["REF", 2]), 2: node(null), 3: node(["REF", 1]) }),
    state([frame(0), frame(2)], { head: ["REF", 3], alias: ["REF", 3] },
      { 1: node(["REF", 2]), 2: node(["REF", 3]), 3: node(["REF", 2]) }),
  ];
}

afterEach(() => {
  for (const view of views.splice(0)) view.dataViz.jsPlumbInstance.dispose();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("production placement strategies", () => {
  it("configures initial filters before materializing only the selected step, then updates live filters", () => {
    const materialized: number[] = [],original=ExecutionVisualizer.prototype.try_hook;
    vi.spyOn(ExecutionVisualizer.prototype,"try_hook").mockImplementation(function(this:ExecutionVisualizer,name,args) {
      if(name==="end_renderDataStructures")materialized.push(this.curInstr);
      return original.call(this,name,args);
    });
    const {root,data}=render([state([frame(0)]),state([frame(1)]),state([frame(2)])],
      {hideVars:["value"],hideFields:[],jumpToEnd:true});
    expect(materialized).toEqual([2]);
    expect(frameOrder(root)).toEqual(["2"]);
    expect(root.querySelectorAll(".stackVarName")).toHaveLength(0);
    data.selectivelyHideVarsAndFields([],[]);
    expect(materialized).toEqual([2,2]);
    expect(root.querySelectorAll(".stackVarName")).toHaveLength(1);
  });

  it("reverses Java's supplied frame order once and retains keyed frame nodes through reordering", () => {
    const states = [state([frame(2), frame(1), frame(0)]), state([frame(0), frame(2), frame(1)])];
    const original = structuredClone(states);
    const { root, view, data, placement } = render(states);
    expect(frameOrder(root)).toEqual(["0", "1", "2"]);
    expect(placement.plans()[0].stackGlobals.frames.map(item => item.frame_id)).toEqual([0, 1, 2]);
    const nodes = [...root.querySelectorAll("#stack > .stackFrame")];
    view.renderStep(1);
    expect(frameOrder(root)).toEqual(["1", "2", "0"]);
    for (const node of nodes) expect(root.querySelector(`[data-frame_id="${node.getAttribute("data-frame_id")}"]`)).toBe(node);
    data.precomputeCurTraceLayouts();
    view.renderStep(0);
    view.redrawConnectors();
    data.selectivelyHideVarsAndFields(["value"], []);
    data.selectivelyHideVarsAndFields([], []);
    expect(frameOrder(root)).toEqual(["0", "1", "2"]);
    expect(view.curTrace[0].stack_to_render.map(item => item.frame_id)).toEqual([0, 1, 2]);
    expect(states).toEqual(original);
  });

  it("replaces real frame/global order and positioning without changing heap plans or placement", () => {
    const states = [state([frame(1), frame(0)], { left: ["REF", 1], right: ["REF", 2] },
      { 1: ["LIST", 1], 2: ["LIST", 2] })];
    const { root, data, placement } = render(states);
    const heapBefore = heapRows(root);
    const heapPlans = structuredClone(placement.plans().map(plan => plan.heap));
    const frames = [...root.querySelectorAll("#stack > .stackFrame")];
    const legacy = new LegacyStackGlobalsPlacement();
    placement.use({ stackGlobals: {
      id: "reverse-stack-and-globals", version: "1",
      plan: context => {
        const plan = legacy.plan(context);
        return { ...plan, frames: [...plan.frames].reverse(), globals: [...plan.globals].reverse() };
      },
      place: () => [{ key: "stack", styles: { "margin-top": "23px" } }],
    } });
    data.renderDataStructures(0);
    expect(frameOrder(root)).toEqual(["1", "0"]);
    expect(globalOrder(root)).toEqual(["right", "left"]);
    expect((root.querySelector("#stack") as HTMLElement).style.marginTop).toBe("23px");
    for (const node of frames) expect(root.contains(node)).toBe(true);
    expect(heapRows(root)).toEqual(heapBefore);
    expect(placement.plans().map(plan => plan.heap)).toEqual(heapPlans);
    expect([...root.querySelectorAll<HTMLElement>(".heapObject")].map(element => element.style.cssText)).toEqual(["", ""]);
    placement.use({ stackGlobals: legacy });
    data.renderDataStructures(0);
    expect(frameOrder(root)).toEqual(["0", "1"]);
    expect(globalOrder(root)).toEqual(["left", "right"]);
    expect((root.querySelector("#stack") as HTMLElement).style.marginTop).toBe("");
  });

  it("prepends and removes frames with unique IDs, correct reference emphasis, and correct parent links", () => {
    const make = (id: number, active = false) => ({ ...frame(id, { ref: ["REF", 1] }),
      is_highlighted: active, parent_frame_id_list: id ? [id - 1] : [] });
    const { root, view, data, manager, placement } = render([
      state([make(1, true), make(0)], { shared: ["REF", 1] }, { 1: ["LIST", 5] }),
      state([make(2, true), make(1), make(0)], { shared: ["REF", 1] }, { 1: ["LIST", 5] }),
    ], { textualMemoryLabels: false, drawParentPointers: true });
    const legacy = new LegacyStackGlobalsPlacement();
    placement.use({ stackGlobals: { id: "newest-first", version: "1", plan: context => {
      const plan = legacy.plan(context);
      return { ...plan, frames: [...plan.frames].reverse() };
    } } });
    data.renderDataStructures(0);
    const main = root.querySelector<HTMLElement>('[data-frame_id="0"]')!;
    const helper = root.querySelector<HTMLElement>('[data-frame_id="1"]')!;
    for (const step of [1, 0, 1]) {
      view.renderStep(step);
      const frames = [...root.querySelectorAll<HTMLElement>("#stack > .stackFrame")];
      expect(new Set(frames.map(element => element.id)).size).toBe(frames.length);
      expect(frameOrder(root)).toEqual(step ? ["2", "1", "0"] : ["1", "0"]);
      expect(root.querySelector('[data-frame_id="0"]')).toBe(main);
      expect(root.querySelector('[data-frame_id="1"]')).toBe(helper);
      const activeID = step ? "2" : "1";
      const active = root.querySelector<HTMLElement>(`[data-frame_id="${activeID}"]`)!;
      expect(root.querySelector(".highlightedStackFrame")).toBe(active);
      const reference = (id: string) => manager.connections.find(connection =>
        connection.scope === "varValuePointer" && connection.source.closest(".stackFrame").attr("data-frame_id") === id);
      expect(reference("0")).toBeDefined();
      expect(reference(activeID)).toBeDefined();
      expect(reference("0").paintStyle.strokeStyle).not.toBe(reference(activeID).paintStyle.strokeStyle);
      expect(manager.connections.some(connection => connection.scope === "frameParentPointer" &&
        connection.sourceId === active.id && connection.targetId === (step ? helper.id : main.id))).toBe(true);
    }
  });

  it("replaces heap topology and measured placement while retaining the other region's order and nodes", () => {
    const { root, data, placement } = render([state([frame(1), frame(0)],
      { a: ["REF", 1], b: ["REF", 2] }, { 1: ["LIST", 1], 2: ["LIST", 2] })]);
    const stackBefore = frameOrder(root), globalsBefore = globalOrder(root);
    const nodes = [...root.querySelectorAll("#stack > .stackFrame")];
    const seen: any[] = [];
    placement.use({ heap: {
      id: "one-reversed-row", version: "3",
      plan: (context, legacy) => {
        seen.push(context);
        return [["custom-row", ...legacy().flatMap(row => row.slice(1)).reverse()]];
      },
      place: context => {
        expect(context.dimensions.heap.some(box => box.key === "row:custom-row")).toBe(true);
        return [{ key: "object:2", styles: { "margin-left": "31px" } }];
      },
    } });
    data.renderDataStructures(0);
    expect(heapRows(root)).toEqual([[2, 1]]);
    expect((root.querySelector('[data-object-id="2"]') as HTMLElement).style.marginLeft).toBe("31px");
    expect(frameOrder(root)).toEqual(stackBefore);
    expect(globalOrder(root)).toEqual(globalsBefore);
    expect([...root.querySelectorAll("#stack > .stackFrame")]).toEqual(nodes);
    expect(seen[0].models.heap).toEqual({ id: "one-reversed-row", version: "3" });
  });

  it("traverses ordered global roots then normalized frames and ordered locals, skipping hidden/missing roots and aliases", () => {
    const heap = Object.fromEntries([1, 2, 3, 4, 5, 99].map(id => [id, ["LIST", id]]));
    const states = [state([frame(1, { leaf: ["REF", 5] }),
      frame(0, { first: ["REF", 3], second: ["REF", 4], alias: ["REF", 1] }, ["second", "first", "alias"])],
    { a: ["REF", 1], b: ["REF", 2] }, heap, ["b", "missing", "a"])];
    const { root, data } = render(states);
    expect(heapRows(root)).toEqual([[2], [1], [4], [3], [5]]);
    expect(globalOrder(root)).toEqual(["b", "a"]);
    expect(root.querySelectorAll('[data-object-id="1"]')).toHaveLength(1);
    expect(root.querySelector('[data-object-id="99"]')).toBeNull();
    data.selectivelyHideVarsAndFields(["global:b", "second"], []);
    expect(heapRows(root)).toEqual([[1], [3], [5]]);
  });

  it("retains predecessor row keys, prepends links, prunes unreachable objects, and terminates cycles canonically", () => {
    const states = topologyStates();
    const normal = render(states);
    const expected = [[["row1", 1, 2]], [["row1", 3, 1, 2]], [["row1", 3, 2]]];
    expect(normal.data.curTraceLayouts).toEqual(expected);
    const firstPlan = normal.placement.plans()[0].heap;
    const snapshot = JSON.stringify(firstPlan);
    for (const target of [2, 0, 1, 2, 1, 0]) {
      normal.view.renderStep(target);
      const cold = render(states, { startingInstruction: target });
      expect(cold.data.curTraceLayouts).toEqual(expected);
      expect(heapRows(normal.root)).toEqual(expected[target].map(row => row.slice(1)));
      expect(heapRows(cold.root)).toEqual(heapRows(normal.root));
      expect(frameOrder(cold.root)).toEqual(frameOrder(normal.root));
      expect(JSON.stringify(firstPlan)).toBe(snapshot);
    }
    normal.view.renderStep(2);
    expect(normal.root.querySelector('[data-object-id="1"]')).toBeNull();
    expect(normal.root.querySelectorAll('[data-object-id="3"]')).toHaveLength(1);
    const finalCold = render(states, { jumpToEnd: true });
    expect(heapRows(finalCold.root)).toEqual([[3, 2]]);
  });

  it("keeps legacy structural/traversal hooks in the production heap planner", () => {
    const { view, data, root } = render([state([frame(0)], { head: ["REF", 1] },
      { 1: ["LIST", ["REF", 2]], 2: ["LIST", 7] })]);
    expect(heapRows(root)).toEqual([[1, 2]]);
    const visited: any[] = [];
    view.add_pytutor_hook("isLinearObj", ({ heapObj }) => { visited.push(heapObj); return [true, false]; });
    data.precomputeCurTraceLayouts();
    data.renderDataStructures(0);
    expect(visited).not.toHaveLength(0);
    expect(data.curTraceLayouts).toEqual([[["row1", 1]]]);
    // Rendering may materialize the referenced object through a nested template;
    // the selected top-level topology is still owned by the heap model.
    expect(heapRows(root)).toEqual([[1]]);
  });

  it("supplies selected state, options, canonical context, model versions and fresh dimensions on every redraw", () => {
    const { root, view, data, placement } = render([state([frame(0)]), state([frame(1)])],
      { startingInstruction: 1, arrayOrientation: "vertical" });
    let width = 81;
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return new DOMRect(10, 20, this.matches("#stack > .stackFrame") ? width : 0, 31);
    });
    const calls: any[] = [];
    const legacy = new LegacyStackGlobalsPlacement();
    placement.use({ stackGlobals: { id: "dimension-stack", version: "2", plan: context => legacy.plan(context),
      place: context => {
        calls.push(context);
        const frame = context.dimensions.stackGlobals.find(box => box.key.startsWith("frame:"))!;
        return [{ key: frame.key, styles: { "margin-left": `${frame.width}px` } }];
      } } });
    const canonical = { horizon: "supplied-snapshots", anchor: 17 };
    placement.invalidate(canonical);
    data.renderDataStructures(1);
    const selected = root.querySelector<HTMLElement>('#stack > .stackFrame')!;
    expect(selected.style.marginLeft).toBe("81px");
    const request = calls[calls.length - 1]!;
    expect(request.sequence).toBe(view.curTrace);
    expect(request.state).toBe(view.curTrace[1]);
    expect(request.index).toBe(1);
    expect(request.options.arrayOrientation).toBe("vertical");
    expect(request.canonical.supplied).toBe(canonical);
    expect(request.models.stackGlobals).toEqual({ id: "dimension-stack", version: "2" });
    for (const nextWidth of [141, 141, 40]) {
      width = nextWidth;
      view.redrawConnectors();
      expect(selected.style.marginLeft).toBe(`${nextWidth}px`);
    }
    view.params.arrayOrientation = "horizontal";
    view.redrawConnectors();
    expect(calls[calls.length - 1].options.arrayOrientation).toBe("horizontal");
    expect(calls.length).toBeGreaterThanOrEqual(5);
    data.jsPlumbInstance.reset();
    expect(selected.style.marginLeft).toBe("");
  });

  it("retains trace-wide label budgets and per-table value widths during ordinary redraw sizing", () => {
    let characterWidth = 10;
    const createRange = document.createRange.bind(document);
    vi.spyOn(document, "createRange").mockImplementation(() => {
      const range = createRange();
      range.getBoundingClientRect = function () {
        return new DOMRect(0, 0, (this.commonAncestorContainer.textContent?.length ?? 0) * characterWidth, 19);
      };
      return range;
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return new DOMRect(0, 0, this.style.visibility === "hidden" ? (this.textContent?.length ?? 0) * 7 : 0, 19);
    });
    const { root, view } = render([
      state([frame(1, { short: 9 }), frame(0, { a: 1, b: 12345 })], { globalValue: 123456789 }),
      state([frame(0, { futureLongName: 3 })]),
    ], { includeTypes: true, stripTypePrefixes: ["java.util."] }, ["java.util.LongType"]);
    const dataRoot = root.querySelector<HTMLElement>("#vizLayoutTdSecond")!;
    const widths = (frameID: string) => [...root.querySelectorAll<HTMLElement>(`[data-frame_id="${frameID}"] .value-box`)]
      .map(box => box.style.width);
    expect(widths("0")).toEqual(["72px", "72px"]);
    expect(widths("1")).toEqual(["40px"]);
    expect(root.querySelector<HTMLElement>("#globals_area .value-box")!.style.width).toBe("112px");
    expect(dataRoot.style.getPropertyValue("--type-label-width")).toBe("56px");
    expect(dataRoot.style.getPropertyValue("--stack-name-width")).toBe(`${"futureLongName".length * 7}px`);
    dataRoot.style.setProperty("--type-label-width", "0px");
    characterWidth = 20;
    view.redrawConnectors();
    expect(widths("0")).toEqual(["122px", "122px"]);
    expect(widths("1")).toEqual(["42px"]);
    expect(dataRoot.style.getPropertyValue("--type-label-width")).toBe("56px");
  });

  it("nudges by the executable 96px allowance once, then restores explicit drag CSS after the nudge", () => {
    vi.spyOn($.fn, "offset").mockImplementation(function (this: JQuery) {
      return { left: this[0]?.id.includes("heap_pointer_src") ? 200 : 40, top: 0 };
    } as any);
    const states = [state([frame(0)], { root: ["REF", 1] },
      { 1: ["INSTANCE", "Parent", ["child", ["REF", 2]]], 2: ["INSTANCE", "Leaf", ["value", 1]] })];
    const { root, view, data } = render(states, { textualMemoryLabels: false });
    let target = root.querySelector<HTMLElement>('[data-object-id="2"]')!;
    expect(target.style.marginLeft).toBe("256px");
    for (let iteration = 0; iteration < 3; iteration++) {
      view.redrawConnectors();
      expect(target.style.marginLeft).toBe("256px");
    }
    const saved = "margin-left: 7px; position: relative; left: 13px; top: 4px;";
    data.draggedHeapObjectCSS.set(target.id, saved);
    data.renderDataStructures(0);
    target = root.querySelector<HTMLElement>('[data-object-id="2"]')!;
    expect(target.style.marginLeft).toBe("7px");
    expect(target.style.left).toBe("13px");
    view.redrawConnectors();
    expect(target.style.marginLeft).toBe("7px");
    expect(target.style.top).toBe("4px");
    target.classList.add("ui-draggable-dragging");
    target.style.left = "83px";
    target.style.top = "19px";
    for (const margin of ["7px", "256px"]) {
      target.style.marginLeft = margin;
      view.redrawConnectors();
      expect(target.style.marginLeft).toBe(margin);
      expect(target.style.left).toBe("83px");
      expect(target.style.top).toBe("19px");
    }
    target.classList.remove("ui-draggable-dragging");
  });

  it("cancels a failed materialization without leaving a deferred route pass or masking its failure", () => {
    const { data, manager, placement } = render([state()]);
    const error = new Error("heap proposal failed");
    placement.use({ heap: { id: "throwing", version: "1", plan: () => { throw error; } } });
    expect(() => data.renderDataStructures(0)).toThrow(error);
    expect(manager.layoutCoordinator.acceptedPlan).toBeUndefined();
    expect(manager.svgCanvas.querySelectorAll("path[d]")).toHaveLength(0);
    placement.use({ heap: { id: "empty", version: "1", plan: () => [] } });
    data.renderDataStructures(0);
    expect(manager.layoutCoordinator.diagnostics.outcome).toBe("accepted");
  });
});

describe("placement context and ownership", () => {
  it("rebuilds independent canonical predecessors after options/context/version changes and releases them on dispose", () => {
    const controller = new PlacementController();
    const legacy = new LegacyStackGlobalsPlacement();
    const contexts: any[] = [];
    const heap: HeapPlacementModel = { id: "predecessor", version: "1", plan: context => {
      contexts.push(context);
      return [["row", ...(context.predecessor?.[0]?.slice(1) ?? []), context.index]];
    } };
    const stack: StackGlobalsPlacementModel = { id: "independent", version: "1", plan: context => {
      expect(context.predecessor?.globals ?? []).toEqual([]);
      return legacy.plan(context);
    } };
    const sequence = [state(), state(), state()];
    const fallback = () => { throw new Error("replacement does not require legacy traversal"); };
    controller.use({ stackGlobals: stack, heap });
    expect(controller.select(sequence, 2, { includeTypes: true }, fallback).heap).toEqual([["row", 0, 1, 2]]);
    expect(contexts.map(context => context.index)).toEqual([0, 1, 2]);
    controller.select(sequence, 0, { includeTypes: true }, fallback);
    expect(contexts).toHaveLength(3);
    controller.select(sequence, 2, { includeTypes: false }, fallback);
    expect(contexts).toHaveLength(6);
    (heap as { version: string }).version = "2";
    controller.select(sequence, 1, { includeTypes: false }, fallback);
    expect(contexts).toHaveLength(9);
    const revision = controller.revision;
    controller.invalidate({ omittedHistory: true });
    const selected = controller.select(sequence, 2, {}, fallback);
    expect(selected.context.canonical.revision).toBeGreaterThan(revision);
    expect(selected.context.canonical.supplied).toEqual({ omittedHistory: true });
    expect(Object.isFrozen(selected.heap[0])).toBe(true);
    controller.dispose();
    expect(controller.plans()).toEqual([]);
    const reset = controller.select(sequence, 1, {}, () => []);
    expect(reset.context.canonical.supplied).toBeUndefined();
    expect(reset.context.models.heap.id).toBe("legacy-heap");
  });

  it("restores model styles independently while preserving subsequent user values and priorities", () => {
    const journal = new PlacementJournal();
    const element = document.createElement("div");
    element.style.setProperty("margin-left", "9px", "important");
    journal.style(element, "margin-left", "32px");
    journal.style(element, "top", "17px");
    journal.restore();
    expect(element.style.marginLeft).toBe("9px");
    expect(element.style.getPropertyPriority("margin-left")).toBe("important");
    expect(element.style.top).toBe("");
    journal.style(element, "margin-left", "32px");
    element.style.setProperty("margin-left", "32px", "important");
    journal.style(element, "top", "17px");
    element.style.top = "22px";
    journal.restore();
    expect(element.style.marginLeft).toBe("32px");
    expect(element.style.getPropertyPriority("margin-left")).toBe("important");
    expect(element.style.top).toBe("22px");
  });
});
