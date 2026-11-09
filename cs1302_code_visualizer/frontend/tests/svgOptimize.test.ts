import { describe, expect, it, vi } from "vitest";
import { optimizeSvg, SvgExportContext } from "../js/svgOptimize";

const NS = "http://www.w3.org/2000/svg";
function parse(body: string): SVGElement {
  return new DOMParser().parseFromString(`<svg xmlns="${NS}"><defs/>${body}</svg>`, "image/svg+xml").documentElement as unknown as SVGElement;
}

describe("SVG structural optimization", () => {
  it("reuses repeated complex geometry while keeping transforms, text and descriptions", () => {
    const d = "M0 0 " + Array.from({ length: 30 }, (_, n) => `L${n} ${n % 3}`).join(" ");
    const svg = parse('<title id="title">Graph</title><desc>Details</desc><metadata>{}</metadata>' +
      Array.from({ length: 8 }, (_, n) => `<g opacity="1"><path d="${d}" fill="none" data-codevis-stroke="reference" transform="translate(${n} 0)"/><text x="${n}">label ${n}</text></g>`).join(""));
    const before = new XMLSerializer().serializeToString(svg);
    optimizeSvg(svg);
    expect(svg.querySelectorAll("defs path")).toHaveLength(1);
    expect(svg.querySelectorAll("use")).toHaveLength(8);
    expect(Array.from(svg.querySelectorAll("use"), e => e.getAttribute("transform"))).toEqual(
      Array.from({ length: 8 }, (_, n) => `translate(${n} 0)`));
    expect(svg.querySelectorAll("text")).toHaveLength(8);
    expect(svg.querySelector("desc")?.textContent).toBe("Details");
    expect(svg.querySelector("metadata")?.textContent).toBe("{}");
    expect(new XMLSerializer().serializeToString(svg).length).toBeLessThan(before.length);
    const once = new XMLSerializer().serializeToString(svg);
    optimizeSvg(svg);
    expect(new XMLSerializer().serializeToString(svg)).toBe(once);
  });

  it("shares translated boxes without scaling stroke widths or merging different paints", () => {
    const svg = parse(Array.from({ length: 20 }, (_, n) =>
      `<rect x="${n * 20}" y="10" width="18" height="12" rx="2" fill="none" stroke="black" stroke-width="1" pointer-events="none"/>`).join("") +
      '<rect x="0" y="10" width="18" height="12" fill="red"/>');
    optimizeSvg(svg);
    expect(svg.querySelectorAll("use")).toHaveLength(20);
    expect(svg.querySelector("defs rect")?.getAttribute("x")).toBe("0");
    expect(svg.querySelector("defs rect")?.getAttribute("y")).toBe("0");
    expect(svg.querySelector("defs rect")?.getAttribute("stroke-width")).toBe("1");
    expect(svg.querySelectorAll("use")[5].getAttribute("transform")).toBe("translate(100 10)");
    expect(svg.querySelector('rect[fill="red"]')).not.toBeNull();
  });

  it("retains opacity, clips, distinct paints and small shapes", () => {
    const svg = parse('<g opacity="0.5"><rect width="1" height="1"/><rect width="1" height="1"/></g><g clip-path="url(#clip)"><text>x</text></g>');
    optimizeSvg(svg);
    expect(svg.querySelector('g[opacity="0.5"]')).not.toBeNull();
    expect(svg.querySelector('g[clip-path]')).not.toBeNull();
    expect(svg.querySelectorAll("rect")).toHaveLength(2);
    expect(svg.querySelector("use")).toBeNull();
  });

  it("reuses only font metrics and clears them when invalidated", () => {
    const measureText = vi.fn().mockReturnValue({ fontBoundingBoxDescent: 2 });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ measureText } as any);
    const context = new SvgExportContext();
    expect(context.descent("12px Arial")).toBe(2);
    expect(context.descent("12px Arial")).toBe(2);
    expect(measureText).toHaveBeenCalledTimes(1);
    context.descent("16px Arial");
    context.clear();
    context.descent("12px Arial");
    expect(measureText).toHaveBeenCalledTimes(3);
  });
});
