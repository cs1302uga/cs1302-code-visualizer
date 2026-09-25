import { beforeEach, describe, expect, it, vi } from "vitest";
import { exportSvg } from "../js/svgExport";

describe("standalone SVG export", () => {
  let root: HTMLDivElement;
  beforeEach(() => {
    document.body.innerHTML = "";
    Object.defineProperty(document, "fonts", { configurable: true, value: { ready: Promise.resolve() } });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ measureText: () => ({ fontBoundingBoxDescent: 2 }) } as any);
    root = document.createElement("div");
    document.body.append(root);
    vi.spyOn(root, "getBoundingClientRect").mockReturnValue(new DOMRect(10, 20, 100, 50));
  });

  it("keeps geometry fixed while scaling outer dimensions", async () => {
    root.style.backgroundColor = "rgb(250, 235, 191)";
    root.style.border = "1px solid black";
    const result = new DOMParser().parseFromString(await exportSvg(root, 2), "image/svg+xml");
    expect(result.documentElement.getAttribute("viewBox")).toBe("0 0 100 50");
    expect(result.documentElement.getAttribute("width")).toBe("200");
    expect(result.querySelector("rect[stroke]")?.getAttribute("width")).toBe("99");
    expect(result.querySelector("foreignObject,image,script")).toBeNull();
  });

  it.each([0, -1, NaN, Infinity])("rejects invalid scale %s", async (scale) => {
    await expect(exportSvg(root, scale)).rejects.toThrow("positive and finite");
  });

  it("rejects empty geometry", async () => {
    vi.mocked(root.getBoundingClientRect).mockReturnValue(new DOMRect());
    await expect(exportSvg(root)).rejects.toThrow("empty diagram");
  });

  it("omits hidden content and external HTML resources", async () => {
    root.innerHTML = '<div style="display:none"><img src="https://invalid.example/x.png"></div>';
    const result = await exportSvg(root);
    expect(result).not.toContain("invalid.example");
    expect(result).not.toContain("<image");
  });

  it("exports asymmetric dashed borders as vector strokes", async () => {
    root.style.borderLeft = "2px dashed red";
    const result = new DOMParser().parseFromString(await exportSvg(root), "image/svg+xml");
    const line = result.querySelector("line");
    expect(line?.getAttribute("stroke-dasharray")).toBe("6 6");
    expect(line?.getAttribute("x1")).toBe("1");
  });

  it("separates alpha from paint for Inkscape compatibility", async () => {
    root.style.backgroundColor = "rgba(255, 0, 0, 0.5)";
    root.style.border = "1px solid rgba(0, 0, 0, 0.3)";
    const output = await exportSvg(root);
    const result = new DOMParser().parseFromString(output, "image/svg+xml");
    expect(result.querySelector('rect[fill="rgb(255, 0, 0)"]')?.getAttribute("fill-opacity")).toBe("0.5");
    expect(result.querySelector("rect[stroke]")?.getAttribute("stroke-opacity")).toBe("0.3");
    expect(output).not.toContain("rgba(");
  });

  it("includes sibling connectors only from the diagram's own instance", async () => {
    const instance = document.createElement("div");
    instance.className = "ExecutionVisualizer";
    document.body.append(instance);
    instance.append(root);
    const namespace = "http://www.w3.org/2000/svg";
    const canvas = document.createElementNS(namespace, "svg");
    canvas.classList.add("svg-connector-canvas");
    const path = document.createElementNS(namespace, "path");
    path.setAttribute("d", "M10 20 L30 40");
    canvas.append(path);
    instance.append(canvas);
    Object.defineProperty(path, "getScreenCTM", { value: () => ({ a: 1, b: 0, c: 0, d: 1, e: 10, f: 20 }) });
    vi.spyOn(path, "getClientRects").mockReturnValue([new DOMRect(10, 20, 20, 20)] as any);
    const other = instance.cloneNode(true) as HTMLElement;
    document.body.append(other);
    const result = new DOMParser().parseFromString(await exportSvg(root), "image/svg+xml");
    expect(result.querySelectorAll("path")).toHaveLength(1);
    expect(result.querySelector("path")?.getAttribute("d")).toBe("M10 20 L30 40");
    expect(result.querySelector("path")?.getAttribute("transform")).toBe("matrix(1 0 0 1 0 0)");
  });
});
