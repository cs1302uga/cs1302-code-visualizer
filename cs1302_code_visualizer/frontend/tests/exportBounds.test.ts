import { beforeEach, describe, expect, it, vi } from "vitest";
import { measureExportBounds } from "../js/exportBounds";

function rect(element: Element, x: number, y: number, width: number, height: number) {
  vi.spyOn(element, "getBoundingClientRect").mockReturnValue(new DOMRect(x, y, width, height));
}

describe("export content bounds", () => {
  let root: HTMLElement;
  beforeEach(() => {
    document.body.innerHTML = '<div class="ExecutionVisualizer"><div id="dataViz"></div></div>';
    Object.defineProperty(Range.prototype, "getClientRects", { configurable: true, value: () => [] });
    root = document.getElementById("dataViz")!;
    rect(root, 10, 10, 1000, 800);
  });

  it("trims empty containers, retains painted surfaces, and rounds padding outward", () => {
    root.innerHTML = '<div><div style="background: red"></div></div>';
    rect(root.firstElementChild!, 10, 10, 900, 700);
    rect(root.firstElementChild!.firstElementChild!, 50.25, 60.75, 100.5, 40.5);
    expect(measureExportBounds(root)).toEqual({ left: 46, top: 56, right: 155, bottom: 106 });
  });

  it("includes text without counting hidden or transparent subtrees", () => {
    root.innerHTML = '<span>visible</span><div style="display:none"><b style="background:red"></b></div><div style="opacity:0;background:red"></div>';
    vi.spyOn(Range.prototype, "getClientRects").mockReturnValue([new DOMRect(40, 50, 60, 20)] as any);
    for (const element of root.querySelectorAll("div,b")) rect(element, 0, 0, 2000, 2000);
    expect(measureExportBounds(root)).toEqual({ left: 36, top: 46, right: 104, bottom: 74 });
  });

  it("respects scroll-container clipping", () => {
    root.innerHTML = '<div style="overflow-x:hidden;overflow-y:hidden"><div style="background:red"></div></div>';
    const clip = root.firstElementChild!;
    rect(clip, 50, 60, 100, 40);
    Object.defineProperties(clip, { clientWidth: { value: 100 }, clientHeight: { value: 40 } });
    rect(clip.firstElementChild!, 30, 40, 200, 200);
    expect(measureExportBounds(root)).toEqual({ left: 46, top: 56, right: 154, bottom: 104 });
  });

  it("includes sibling arrow strokes outside the root without other instances", () => {
    root.innerHTML = '<div style="background:red"></div>';
    rect(root.firstElementChild!, 50, 60, 100, 40);
    root.parentElement!.insertAdjacentHTML("beforeend", '<svg class="svg-connector-canvas"><path style="stroke:black;stroke-width:2;fill:none" /></svg>');
    const path = root.parentElement!.querySelector("path")!;
    rect(path, 20, 80, 160, 0);
    Object.defineProperty(path, "getScreenCTM", { value: () => ({ a: 1, b: 0, c: 0, d: 1 }) });
    document.body.insertAdjacentHTML("beforeend", '<div class="ExecutionVisualizer"><svg class="svg-connector-canvas"><path/></svg></div>');
    expect(measureExportBounds(root)).toEqual({ left: 15, top: 56, right: 185, bottom: 104 });
  });
});
