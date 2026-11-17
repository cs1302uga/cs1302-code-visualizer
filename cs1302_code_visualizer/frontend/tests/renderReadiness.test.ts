import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const lifecycle = vi.hoisted(() => ({ construct: vi.fn(), redraw: vi.fn() }));

vi.mock("../js/pytutor", () => ({
  ExecutionVisualizer: class {
    constructor() { lifecycle.construct(); }
    redrawConnectors() { lifecycle.redraw(); }
  },
}));
vi.mock("../js/CodeVisualizer", () => ({ JsonPreVisualizer: class {} }));
vi.mock("../js/svgExport", () => ({ exportSvg: vi.fn() }));
vi.mock("../js/exportBounds", () => ({
  measureExportBounds: vi.fn(), settleExport: vi.fn(),
}));
import "../js/render-trace";

beforeEach(() => {
  vi.useFakeTimers();
  lifecycle.construct.mockReset();
  lifecycle.redraw.mockReset();
  document.body.innerHTML = '<div id="visualizerDiv"></div>';
  document.documentElement.removeAttribute("data-codevis-construction-complete");
  window.history.replaceState({}, "", "/?tracePath=/trace.json");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: () => Promise.resolve({}) }));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("document readiness lifecycle", () => {
  it("marks construction only after it returns and captures only after redraw", async () => {
    lifecycle.construct.mockImplementation(() => {
      expect(document.documentElement.hasAttribute("data-codevis-construction-complete")).toBe(false);
    });
    document.dispatchEvent(new Event("DOMContentLoaded"));
    await vi.advanceTimersByTimeAsync(0);
    expect(lifecycle.construct).toHaveBeenCalledOnce();
    expect(document.documentElement.getAttribute("data-codevis-construction-complete")).toBe("true");
    expect(document.getElementById("screenshotReadyIndicator")).toBeNull();
    expect(lifecycle.redraw).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(50);
    expect(lifecycle.redraw).toHaveBeenCalledOnce();
    expect(document.getElementById("screenshotReadyIndicator")).not.toBeNull();
  });

  it.each(["construct", "redraw"] as const)("retains explicit %s failure", async stage => {
    lifecycle[stage].mockImplementation(() => { throw new Error(`${stage} failed`); });
    document.dispatchEvent(new Event("DOMContentLoaded"));
    await vi.runAllTimersAsync();
    expect(document.getElementById("screenshotReadyIndicator")).toBeNull();
    expect(document.getElementById("screenshotError")?.textContent).toContain(`${stage} failed`);
    expect(document.documentElement.hasAttribute("data-codevis-construction-complete")).toBe(stage === "redraw");
  });

  it("leaves a failed fetch without a construction milestone", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("fetch failed")));
    document.dispatchEvent(new Event("DOMContentLoaded"));
    await vi.runAllTimersAsync();
    expect(lifecycle.construct).not.toHaveBeenCalled();
    expect(document.documentElement.hasAttribute("data-codevis-construction-complete")).toBe(false);
    expect(document.getElementById("screenshotReadyIndicator")).toBeNull();
    expect(document.getElementById("screenshotError")?.textContent).toContain("fetch failed");
  });

  it("keeps json-pre readiness immediate without a layout milestone", async () => {
    window.history.replaceState({}, "", "/?tracePath=/trace.json&visualizer=json-pre");
    document.dispatchEvent(new Event("DOMContentLoaded"));
    await vi.advanceTimersByTimeAsync(0);
    expect(lifecycle.construct).not.toHaveBeenCalled();
    expect(lifecycle.redraw).not.toHaveBeenCalled();
    expect(document.documentElement.hasAttribute("data-codevis-construction-complete")).toBe(false);
    expect(document.getElementById("screenshotReadyIndicator")).not.toBeNull();
  });
});
