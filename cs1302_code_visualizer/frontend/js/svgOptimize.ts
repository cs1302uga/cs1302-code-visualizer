/** Conservative, document-local reuse. Text and accessible metadata stay ordinary nodes. */
const NS = "http://www.w3.org/2000/svg";
const shapes = new Set(["rect", "path", "line", "polygon", "polyline", "circle", "ellipse"]);

export function optimizeSvg(svg: SVGElement): void {
  // Only unwrap identity groups: opacity and clipping on other groups are significant.
  for (const group of Array.from(svg.querySelectorAll("g")).reverse()) {
    if (group.attributes.length === 1 && group.getAttribute("opacity") === "1") {
      group.replaceWith(...Array.from(group.childNodes));
    }
  }
  const defs = svg.querySelector("defs");
  if (!defs) return;
  const serializer = new XMLSerializer();
  const offsets = new WeakMap<Element, string>();
  const origins = (e: Element): string[] => e.localName === "rect" ? ["x", "y"]
    : ["circle", "ellipse"].includes(e.localName) ? ["cx", "cy"] : [];
  const groups = new Map<string, { source: Element; instances: Element[] }>();
  for (const element of Array.from(svg.querySelectorAll("*"))) {
    if (!shapes.has(element.localName) || element.closest("defs") || element.hasAttribute("id")) continue;
    if (Array.from(element.attributes).some(a => a.value.includes("url("))) continue;
    const axes = origins(element);
    if (axes.some(a => !Number.isFinite(Number(element.getAttribute(a) ?? "0")))) continue;
    if (axes.length) offsets.set(element, `translate(${axes.map(a => element.getAttribute(a) ?? "0").join(" ")})`);
    const key = JSON.stringify([element.localName, Array.from(element.attributes)
      .filter(a => a.name !== "transform").map(a => [a.name, axes.includes(a.name) ? "0" : a.value]).sort()]);
    const group = groups.get(key) ?? { source: element, instances: [] };
    group.instances.push(element);
    groups.set(key, group);
  }
  let next = 0;
  for (const { source: original, instances } of groups.values()) {
    if (instances.length < 2) continue;
    const source = original.cloneNode(true) as Element;
    source.removeAttribute("transform");
    for (const axis of origins(source)) source.setAttribute(axis, "0");
    let id: string;
    do { id = `geometry-${next++}`; } while (svg.querySelector(`[id="${id}"]`));
    source.setAttribute("id", id);
    const uses = instances.map(element => {
      const use = document.createElementNS(NS, "use");
      use.setAttribute("href", `#${id}`);
      use.setAttribute("pointer-events", "none");
      const transform = [element.getAttribute("transform"), offsets.get(element)].filter(Boolean).join(" ");
      if (transform) use.setAttribute("transform", transform);
      return use;
    });
    const before = instances.reduce((n, e) => n + serializer.serializeToString(e).length, 0);
    const after = serializer.serializeToString(source).length +
      uses.reduce((n, e) => n + serializer.serializeToString(e).length, 0);
    if (after >= before) continue;
    defs.append(source);
    instances.forEach((element, index) => element.replaceWith(uses[index]));
  }
}

/** Font metrics can survive steps; geometry and text ranges cannot. */
export class SvgExportContext {
  private readonly descents = new Map<string, number>();
  readonly canvas = document.createElement("canvas").getContext("2d")!;
  readonly graphemes = new Intl.Segmenter(undefined, { granularity: "grapheme" });

  clear(): void { this.descents.clear(); }

  descent(font: string): number {
    const cached = this.descents.get(font);
    if (cached !== undefined) return cached;
    this.canvas.font = font;
    const result = this.canvas.measureText("Mg").fontBoundingBoxDescent;
    if (this.descents.size >= 128) this.descents.clear();
    this.descents.set(font, result);
    return result;
  }
}

const contexts = new WeakMap<Document, SvgExportContext>();
export function exportContext(doc: Document): SvgExportContext {
  let context = contexts.get(doc);
  if (!context) {
    context = new SvgExportContext();
    contexts.set(doc, context);
    const current = context;
    doc.fonts.addEventListener?.("loadingdone", () => current.clear());
    doc.fonts.addEventListener?.("loadingerror", () => current.clear());
  }
  return context;
}
