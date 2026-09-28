/** Replay measured production DOM geometry through the real connector manager. */
import { readFileSync } from "node:fs";
import { vi } from "vitest";
import { SvgConnectorManager } from "../js/svgConnectors";

export function fixture(name: string) {
  return JSON.parse(readFileSync(`tests/fixtures/reference-routing/${name}.json`, "utf8"));
}

export function replay(name: string, transform?: (data:any)=>void) {
  const data = fixture(name);
  transform?.(data);
  document.body.innerHTML = '<div class="ExecutionVisualizer"><div id="dataViz"></div></div>';
  const container = document.querySelector<HTMLElement>(".ExecutionVisualizer")!;
  const root = document.getElementById("dataViz")!;
  const reads = new Map<Element, number>();
  const measure = (el: Element, r: any) => {
    vi.spyOn(el, "getBoundingClientRect").mockImplementation(() => {
      reads.set(el, (reads.get(el) ?? 0) + 1);
      return new DOMRect(r.x, r.y, r.width, r.height);
    });
  };
  const region = { x: 0, y: 0, width: data.bounds.right-data.bounds.left,
    height: data.bounds.bottom-data.bounds.top };
  measure(container, region); measure(root, region);
  const owners = new Map<string, HTMLElement>();
  const bodies = new Map<string, HTMLElement>();
  for (const s of data.shapes.filter((s: any) => s.className === "heapObject" || s.className.includes("stackFrame"))) {
    const el = document.createElement("div"); el.id = s.id; el.className = s.className;
    root.append(el); measure(el, s); owners.set(s.id, el);
    const body = document.createElement("table");
    body.className = s.text.startsWith("String[]") ? "listTbl" : "instTbl";
    el.append(body);
    const target = data.connectors.find((c: any) => c.targetId === s.id)?.targetBody;
    const table = data.shapes.find((t: any) => t.className.includes("Tbl") && t.x >= s.x &&
      t.x+t.width <= s.x+s.width+.1 && t.y >= s.y && t.y+t.height <= s.y+s.height+.1);
    measure(body, target ?? table ?? s); bodies.set(s.id, body);
  }
  for (const c of data.connectors) {
    const box = document.createElement("span"); box.className = "value-box";
    (bodies.get(c.sourceOwner) ?? root).append(box); measure(box, c.sourceBox);
    const source = document.createElement("div"); source.id = c.sourceId;
    box.append(source); measure(source, c.source);
  }
  const textRects = new Map<Node, DOMRect>();
  for (const t of data.texts) {
    const span = document.createElement("span"); span.textContent = t.text;
    root.append(span); measure(span, t);
    const r = new DOMRect(t.x, t.y, t.width, t.height);
    textRects.set(span, r); textRects.set(span.firstChild!, r);
  }
  if (!Range.prototype.getClientRects) Object.defineProperty(Range.prototype, "getClientRects", {
    configurable: true, value: () => [],
  });
  vi.spyOn(Range.prototype, "getClientRects").mockImplementation(function (this: Range) {
    const r = textRects.get(this.commonAncestorContainer);
    return (r ? [r] : []) as any;
  });
  const manager = new SvgConnectorManager({ Container: container });
  manager.beginBatch();
  for (const c of data.connectors) manager.connect({ source: c.sourceId, target: c.targetId });
  manager.endBatch();
  return { data, manager, root, container, reads, owners };
}

/** Independent dense sampling oracle for the finite recorded regression scenes. */
export function pathPoints(d: string): [number, number][] {
  const tokens = d.match(/[MLHCQ]|[-+]?(?:\d*\.\d+|\d+)(?:e[-+]?\d+)?/gi) ?? [];
  let i = 0, current: [number, number] = [0, 0];
  const out: [number, number][] = [];
  const point = (): [number, number] => [Number(tokens[i++]), Number(tokens[i++])];
  while (i < tokens.length) {
    const op = tokens[i++];
    if (op === "M") { current = point(); out.push(current); continue; }
    const controls = op === "C" ? [current, point(), point(), point()] :
      op === "Q" ? [current, point(), point()] :
      [current, op === "H" ? [Number(tokens[i++]), current[1]] as [number, number] : point()];
    for (let n = 1; n <= 500; n++) {
      const t = n/500;
      let layer = controls;
      while (layer.length > 1) layer = layer.slice(1).map((p, j) =>
        [layer[j][0]*(1-t)+p[0]*t, layer[j][1]*(1-t)+p[1]*t] as [number, number]);
      out.push(layer[0]);
    }
    current = controls[controls.length-1];
  }
  return out;
}

export function textHits(manager: SvgConnectorManager, texts: any[]) {
  return manager.connections.flatMap(c => {
    const points = pathPoints(c.pathElement.getAttribute("d")!);
    return texts.filter(t => points.some(([x,y]) => x > t.x && x < t.x+t.width &&
      y > t.y && y < t.y+t.height)).map(t => `${c.sourceId}: ${t.text}`);
  });
}
