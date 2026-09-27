import { describe, expect, it, beforeEach } from "vitest";
import $ from "jquery";
import { safeMarkup, safeHtml } from "../js/safeMarkup";
import { ExecutionVisualizer } from "../js/pytutor";
import { create } from "../js/CodeVisualizer";
import { convertModernTraceToOpt } from "../js/modernTraceAdapter";
import { prepareStringTrace } from "../js/stringStyle";

describe("untrusted trace rendering", () => {
  beforeEach(() => { document.body.innerHTML = '<div id="viz"></div>'; });

  it("removes active HTML while retaining renderer table fragments", () => {
    const table = document.createElement("table");
    $(table).append(safeMarkup('<tr><td id="value"><img src=x onerror="alert(1)"><script>alert(1)</script><span onclick="alert(1)">safe</span></td></tr>'));
    expect(table.querySelector("td#value")?.textContent).toBe("safe");
    expect(table.querySelector("script,img,[onclick],[onerror]")).toBeNull();
    expect(safeHtml(() => '<span onclick="bad()">code</span>')()).toBe("<span>code</span>");
    const root = document.getElementById("viz")!;
    $(root).html(safeHtml(() => '<a href="javascript:alert(1)">link</a>'));
    expect(root.querySelector("a")?.hasAttribute("href")).toBe(false);
  });

  it("renders a malicious reference label without creating active elements", () => {
    const id = '<img src=x onerror="alert(1)">';
    const trace = { code: "", trace: [{ event: "step_line", line: 1,
      globals: { item: ["REF", id] }, ordered_globals: ["item"],
      heap: { [id]: ["INSTANCE", "Example", ["field", 1]] },
      stack_to_render: [], stdout: "" }] };
    const instance = create({ lang: "java", trace, element: document.getElementById("viz")!,
      options: { textualMemoryLabels: true } });
    expect(document.querySelector("#viz img,#viz script,#viz [onerror]")).toBeNull();
    expect(document.querySelector(".objectIdLabel")).not.toBeNull();
    instance.destroy?.();
  });

  it("retains source text and SVG controls in the full code view", () => {
    const code = 'String s = "<tag>";';
    new ExecutionVisualizer("viz", { code, trace: [{ event: "step_line", line: 1,
      globals: {}, ordered_globals: [], heap: {}, stack_to_render: [], stdout: "" }] },
      { lang: "java", hideCode: false });
    expect(document.querySelector(".cod")?.textContent).toBe(code.replace(/ /g, "\u00a0"));
    expect(document.querySelector('svg#leftCodeGutterSVG polygon#curLineArrow')).not.toBeNull();
    expect(document.querySelector(".cod tag")).toBeNull();
  });

  it("preserves prototype-named variables as ordinary own properties", () => {
    const modern: any = { format: "modern", steps: [{ line: 1, callStack: [{
      methodName: "main", line: 1, locals: [{ name: "__proto__", value: 7, type: "int" },
        { name: "constructor", value: 8, type: "int" }],
    }], heap: {} }] };
    const trace: any = convertModernTraceToOpt(modern);
    for (const candidate of [trace, prepareStringTrace(trace, "default")]) {
      const locals = candidate.trace[0].stack_to_render[0].encoded_locals;
      expect(Object.getPrototypeOf(locals)).toBeNull();
      expect(Object.prototype.hasOwnProperty.call(locals, "__proto__")).toBe(true);
      expect(locals.__proto__).toBe(7);
      expect(locals.constructor).toBe(8);
      expect(locals.toString).toBeUndefined();
    }
    expect(Object.getPrototypeOf({})).toBe(Object.prototype);
  });
});
