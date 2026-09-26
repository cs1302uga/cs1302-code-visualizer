/** Content bounds shared by raster capture and standalone SVG export. */
import { paintRole } from "./theme";

export interface ExportBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

function visiblePaint(value: string): boolean {
  return value !== "" && value !== "none" && value !== "transparent" &&
    !/^rgba\([^)]*,\s*0(?:\.0+)?\)$/.test(value);
}

/** Wait for fonts and a rendered frame before measuring or capturing connectors. */
export async function settleExport(redraw?: () => void): Promise<void> {
  await document.fonts.ready;
  redraw?.();
  await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
}

/** Measure painted content, not layout containers or the page's background. */
export function measureExportBounds(root: HTMLElement): ExportBounds {
  let bounds: ExportBounds | undefined;
  const add = (rect: ExportBounds, clips: ExportBounds[]) => {
    let { left, top, right, bottom } = rect;
    for (const clip of clips) {
      left = Math.max(left, clip.left); top = Math.max(top, clip.top);
      right = Math.min(right, clip.right); bottom = Math.min(bottom, clip.bottom);
    }
    if (right <= left || bottom <= top) return;
    bounds = bounds ? {
      left: Math.min(bounds.left, left), top: Math.min(bounds.top, top),
      right: Math.max(bounds.right, right), bottom: Math.max(bounds.bottom, bottom),
    } : { left, top, right, bottom };
  };
  const walk = (node: Node, clips: ExportBounds[]) => {
    if (node instanceof Text) {
      if (!node.data.trim() || getComputedStyle(node.parentElement!).visibility !== "visible") return;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const rect of Array.from(range.getClientRects())) add(rect, clips);
      return;
    }
    if (!(node instanceof Element)) return;
    const style = getComputedStyle(node);
    if (style.display === "none" || Number(style.opacity || 1) === 0) return;
    if (node instanceof SVGElement) {
      if (node.matches("path,polygon,polyline,line,circle,ellipse,rect") && style.visibility === "visible") {
        const rect = node.getBoundingClientRect();
        const matrix = (node as SVGGraphicsElement).getScreenCTM();
        if (!matrix) return;
        const stroke = visiblePaint(style.stroke) ? parseFloat(style.strokeWidth) || 0 : 0;
        if (!visiblePaint(style.fill) && !stroke) return;
        // Stroke extents transform with the path; arrowheads are separate polygons.
        const dx = stroke / 2 * Math.hypot(matrix.a, matrix.c);
        const dy = stroke / 2 * Math.hypot(matrix.b, matrix.d);
        add({ left: rect.left - dx, top: rect.top - dy,
          right: rect.right + dx, bottom: rect.bottom + dy }, clips);
      }
    } else if (node instanceof HTMLElement) {
      const rect = node.getBoundingClientRect();
      const borderWidths = ["top", "right", "bottom", "left"].map(side =>
        !["none", "hidden"].includes(style.getPropertyValue(`border-${side}-style`)) &&
        visiblePaint(style.getPropertyValue(`border-${side}-color`))
          ? parseFloat(style.getPropertyValue(`border-${side}-width`)) || 0 : 0);
      const border = borderWidths.some(width => width > 0);
      const surface = visiblePaint(style.backgroundColor) && paintRole(node, "background") !== "canvas";
      if (style.visibility === "visible" && (border || surface || node.classList.contains("colorSwatchContainer"))) {
        // Tables may paint a collapsed border outside their DOM box. Allow its
        // half-width (also covering subpixel border rasterization) before rounding.
        const [t, r, b, l] = borderWidths.map(width => width / 2);
        add({ left: rect.left - l, top: rect.top - t,
          right: rect.right + r, bottom: rect.bottom + b }, clips);
      }
      const clipX = ["hidden", "clip", "auto", "scroll"].includes(style.overflowX);
      const clipY = ["hidden", "clip", "auto", "scroll"].includes(style.overflowY);
      if (clipX || clipY) clips = [...clips, {
        left: clipX ? rect.left + node.clientLeft : -Infinity,
        right: clipX ? rect.left + node.clientLeft + node.clientWidth : Infinity,
        top: clipY ? rect.top + node.clientTop : -Infinity,
        bottom: clipY ? rect.top + node.clientTop + node.clientHeight : Infinity,
      }];
    }
    node.childNodes.forEach(child => walk(child, clips));
  };
  walk(root, []);
  const instance = root.closest(".ExecutionVisualizer");
  for (const vector of Array.from(instance?.querySelectorAll("svg.svg-connector-canvas") ?? [])) {
    if (root.contains(vector)) continue;
    let hidden = false;
    for (let parent = vector.parentElement; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (style.display === "none" || Number(style.opacity || 1) === 0) hidden = true;
    }
    if (!hidden) walk(vector, []);
  }
  // A genuinely empty, laid-out view keeps a valid canvas. Zero geometry is an error.
  const content = bounds ?? root.getBoundingClientRect();
  if (content.right <= content.left || content.bottom <= content.top) {
    throw new Error("Cannot export an empty diagram");
  }
  return {
    left: Math.floor(content.left + scrollX - 4),
    top: Math.floor(content.top + scrollY - 4),
    right: Math.ceil(content.right + scrollX + 4),
    bottom: Math.ceil(content.bottom + scrollY + 4),
  };
}
