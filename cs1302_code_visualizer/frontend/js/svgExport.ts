/**
 * Export the visualizer's laid-out DOM as standalone, editable SVG primitives.
 * This is a renderer for the visualizer's vocabulary, not a general HTML converter.
 */

import { describeSvg } from "./svgDescription";
import { PaintRole, palettes, paintRole, themeCss } from "./theme";
import { ExportBounds, measureExportBounds } from "./exportBounds";

const NS = "http://www.w3.org/2000/svg";

function primitive(tag: string, attributes: Record<string, string | number> = {}): SVGElement {
  const element = document.createElementNS(NS, tag);
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value));
  }
  return element;
}

function visibleColor(color: string): boolean {
  return color !== "transparent" && color !== "rgba(0, 0, 0, 0)" && color !== "";
}

function themedPrimitive(
  tag: string, attributes: Record<string, string | number>,
  roles: { fill?: PaintRole; stroke?: PaintRole } = {},
): SVGElement {
  const element = primitive(tag, attributes);
  for (const [property, role] of Object.entries(roles)) {
    if (role) element.setAttribute(`data-codevis-${property}`, role);
  }
  return element;
}

/**
 * Serialize a diagram after fonts and layout have settled. Coordinates stay in
 * CSS pixels; scale changes only the declared outer dimensions.
 */
export async function exportSvg(root: HTMLElement, scale = 1, bounds?: ExportBounds): Promise<string> {
  if (!Number.isFinite(scale) || scale <= 0) {
    throw new Error("SVG scale must be positive and finite");
  }
  await document.fonts.ready;
  const crop = bounds ?? measureExportBounds(root);
  const width = crop.right - crop.left;
  const height = crop.bottom - crop.top;
  if (width <= 0 || height <= 0) throw new Error("Cannot export an empty diagram");
  const left = crop.left - scrollX;
  const top = crop.top - scrollY;
  const svg = primitive("svg", {
    width: width * scale, height: height * scale, viewBox: `0 0 ${width} ${height}`,
    role: "img", "aria-labelledby": "state-title", "aria-describedby": "state-description",
    style: "user-select:text;-webkit-user-select:text",
    class: "codevis-diagram",
  });
  const theme = root.closest("[data-codevis-theme]")?.getAttribute("data-codevis-theme");
  // Light is the standalone fallback; an inline SVG may follow its host theme.
  if (theme === "light" || theme === "dark" || theme === "auto") svg.setAttribute("data-codevis-theme", theme);
  const stylesheet = primitive("style");
  stylesheet.textContent = themeCss;
  svg.append(stylesheet);
  const description = describeSvg(root);
  const title = primitive("title", { id: "state-title" });
  title.textContent = description.summary;
  const desc = primitive("desc", { id: "state-description" });
  desc.textContent = description.sections.map(section =>
    `${section.heading}\n${section.items.length ? section.items.join("\n") : "No visible entries."}`
  ).join("\n\n");
  const metadata = primitive("metadata", { "data-description": "1" });
  metadata.textContent = JSON.stringify(description);
  svg.append(title, desc, metadata, themedPrimitive("rect", {
    width, height, fill: theme === "dark" ? palettes.dark.canvas : palettes.light.canvas,
  }, { fill: "canvas" }));
  const defs = primitive("defs");
  svg.append(defs);
  let nextClip = 0;
  const context = document.createElement("canvas").getContext("2d")!;
  const graphemes = new Intl.Segmenter(undefined, { granularity: "grapheme" });

  function text(node: Text, parent: SVGElement): void {
    const style = getComputedStyle(node.parentElement!);
    if (style.visibility !== "visible") return;
    context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const metrics = context.measureText("Mg");
    const descent = metrics.fontBoundingBoxDescent;
    const range = document.createRange();
    let offset = 0;
    let current: SVGElement | undefined;
    let currentY = NaN;
    let start = 0;
    let end = 0;
    let value = "";
    const flush = () => {
      if (current) {
        current.setAttribute("x", String(start));
        current.setAttribute("textLength", String(end - start));
        current.setAttribute("lengthAdjust", "spacingAndGlyphs");
        current.textContent = value;
        parent.append(current);
      }
      value = "";
    };
    // Measure complete graphemes so zero-width combining marks and emoji joiners
    // remain part of the editable string instead of being discarded as whitespace.
    for (const { segment: character } of graphemes.segment(node.data)) {
      range.setStart(node, offset);
      offset += character.length;
      range.setEnd(node, offset);
      const rect = range.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0 || character === "\n" || character === "\r") continue;
      const y = rect.bottom - top - descent;
      if (y !== currentY) {
        flush();
        current = themedPrimitive("text", {
          y, fill: style.color,
          "font-family": style.fontFamily.includes("Recursive")
            ? 'Recursive, "DejaVu Sans", Arial, sans-serif' : style.fontFamily,
          "font-size": style.fontSize, "font-weight": style.fontWeight,
          "font-style": style.fontStyle, "xml:space": "preserve",
          "text-decoration": style.textDecorationLine,
          style: `white-space:pre;font-variation-settings:${style.fontVariationSettings}`,
        }, { fill: paintRole(node.parentElement!, "text") });
        currentY = y;
      }
      if (!value) start = rect.left - left;
      end = rect.right - left;
      value += character === "\t" ? " " : character;
    }
    flush();
  }

  function box(element: HTMLElement, parent: SVGElement): void {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    const x = rect.left - left;
    const y = rect.top - top;
    const radius = parseFloat(style.borderTopLeftRadius) || 0;
    if (visibleColor(style.backgroundColor)) {
      parent.append(themedPrimitive("rect", {
        x, y, width: rect.width, height: rect.height, rx: radius, fill: style.backgroundColor,
      }, { fill: paintRole(element, "background") }));
    }
    // The only CSS background image in memory diagrams is the alpha checkerboard.
    if (element.classList.contains("colorSwatchContainer")) {
      const id = `checker-${nextClip++}`;
      const pattern = primitive("pattern", { id, width: 8, height: 8, patternUnits: "userSpaceOnUse", x, y });
      pattern.append(primitive("path", { d: "M0 0h4v4H0zM4 4h4v4H4z", fill: "#ccc" }));
      defs.append(pattern);
      parent.append(primitive("rect", { x, y, width: rect.width, height: rect.height, rx: radius, fill: `url(#${id})` }));
    }
    const sides = ["top", "right", "bottom", "left"];
    const widths = sides.map(side => parseFloat(style.getPropertyValue(`border-${side}-width`)) || 0);
    const colors = sides.map(side => style.getPropertyValue(`border-${side}-color`));
    const styles = sides.map(side => style.getPropertyValue(`border-${side}-style`));
    if (widths.every(w => w === widths[0]) && colors.every(c => c === colors[0]) && styles.every(s => s === "solid")) {
      const w = widths[0];
      if (w && visibleColor(colors[0])) parent.append(themedPrimitive("rect", {
        x: x + w / 2, y: y + w / 2, width: Math.max(0, rect.width - w),
        height: Math.max(0, rect.height - w), rx: Math.max(0, radius - w / 2),
        fill: "none", stroke: colors[0], "stroke-width": w,
      }, { stroke: paintRole(element, "border") }));
    } else {
      const [t, r, b, l] = widths;
      const lines = [
        [x, y + t / 2, x + rect.width, y + t / 2],
        [x + rect.width - r / 2, y, x + rect.width - r / 2, y + rect.height],
        [x, y + rect.height - b / 2, x + rect.width, y + rect.height - b / 2],
        [x + l / 2, y, x + l / 2, y + rect.height],
      ];
      sides.forEach((_, i) => {
        if (!widths[i] || !visibleColor(colors[i]) || ["none", "hidden"].includes(styles[i])) return;
        const [x1, y1, x2, y2] = lines[i];
        const line = themedPrimitive("line", { x1, y1, x2, y2, stroke: colors[i], "stroke-width": widths[i] },
          { stroke: paintRole(element, "border") });
        if (styles[i] === "dashed" || styles[i] === "dotted") {
          const dash = widths[i] * (styles[i] === "dashed" ? 3 : 1);
          line.setAttribute("stroke-dasharray", `${dash} ${dash}`);
        }
        parent.append(line);
      });
    }
  }

  // The connector layer is a sibling of #dataViz, inside its visualizer instance.
  const vectors = new Set<SVGSVGElement>(
    root.closest(".ExecutionVisualizer")?.querySelectorAll<SVGSVGElement>("svg.svg-connector-canvas") ?? []
  );
  function walk(node: Node, parent: SVGElement): void {
    if (node instanceof Text) { text(node, parent); return; }
    if (!(node instanceof Element)) return;
    const style = getComputedStyle(node);
    if (style.display === "none" || style.opacity === "0") return;
    if (node instanceof SVGSVGElement) { vectors.add(node); return; }
    if (!(node instanceof HTMLElement)) return;
    const group = primitive("g", { opacity: style.opacity });
    parent.append(group);
    if (style.visibility === "visible") box(node, group);
    // Preserve rounded clipping on swatches and any scroll containers.
    let content = group;
    if ([style.overflowX, style.overflowY].some(v => v === "hidden" || v === "auto" || v === "scroll")) {
      const rect = node.getBoundingClientRect();
      const id = `clip-${nextClip++}`;
      const clip = primitive("clipPath", { id });
      clip.append(primitive("rect", {
        x: rect.left - left + node.clientLeft, y: rect.top - top + node.clientTop,
        width: node.clientWidth, height: node.clientHeight,
        rx: parseFloat(style.borderTopLeftRadius) || 0,
      }));
      defs.append(clip);
      content = primitive("g", { "clip-path": `url(#${id})` });
      group.append(content);
    }
    node.childNodes.forEach(child => walk(child, content));
  }
  walk(root, svg);

  // Connectors have z-index 100 in the visualizer. Flatten their actual screen
  // transforms and computed paint attributes rather than carrying HTML/CSS over.
  for (const vector of vectors) {
    for (const source of Array.from(vector.querySelectorAll("path,polygon,polyline,line,circle,ellipse,rect"))) {
      const element = source as SVGGraphicsElement;
      const style = getComputedStyle(element);
      if (style.visibility !== "visible" || style.display === "none" || !element.getClientRects().length) continue;
      const matrix = element.getScreenCTM();
      if (!matrix) continue;
      const copy = primitive(element.localName, {
        transform: `matrix(${matrix.a} ${matrix.b} ${matrix.c} ${matrix.d} ${matrix.e - left} ${matrix.f - top})`,
      });
      for (const attr of ["d", "points", "x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "x1", "x2", "y1", "y2"]) {
        if (element.hasAttribute(attr)) copy.setAttribute(attr, element.getAttribute(attr)!);
      }
      for (const attr of ["fill", "fill-opacity", "fill-rule", "stroke", "stroke-opacity", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray"]) {
        copy.setAttribute(attr, style.getPropertyValue(attr));
        if (attr === "fill" || attr === "stroke") {
          const role = /^var\(--codevis-(\w+),/.exec(element.getAttribute(attr) ?? "")?.[1];
          if (role && role in palettes.light) copy.setAttribute(`data-codevis-${attr}`, role);
        }
      }
      let opacity = 1;
      for (let ancestor: Element | null = element; ancestor && ancestor !== root; ancestor = ancestor.parentElement) {
        const computed = getComputedStyle(ancestor);
        if (computed.display === "none") opacity = 0;
        opacity *= Number(computed.opacity);
      }
      copy.setAttribute("opacity", String(opacity));
      svg.append(copy);
    }
  }
  // SVG 1.1 consumers (including Inkscape's importer) need alpha separate
  // from RGB paint; CSS rgba() presentation attributes can render as black.
  for (const element of Array.from(svg.querySelectorAll("*"))) {
    if (["rect", "path", "line", "polygon", "polyline", "circle", "ellipse"].includes(element.localName)) {
      element.setAttribute("pointer-events", "none");
    }
    for (const paint of ["fill", "stroke"]) {
      const color = element.getAttribute(paint) ?? "";
      const rgba = /^rgba\(([^)]+)\)$/.exec(color);
      if (!rgba) continue;
      const channels = rgba[1].split(",").map(v => v.trim());
      element.setAttribute(paint, `rgb(${channels.slice(0, 3).join(", ")})`);
      const opacity = Number(element.getAttribute(`${paint}-opacity`) ?? 1);
      element.setAttribute(`${paint}-opacity`, String(opacity * Number(channels[3])));
    }
  }
  return new XMLSerializer().serializeToString(svg);
}
