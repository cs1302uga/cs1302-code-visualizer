/** Shared dimensions and endpoint geometry, in CSS pixels. */
export type Point = [number, number];
export const ARROW_LENGTH = 6;
export const ARROW_HALF_WIDTH = 3;
export const SOURCE_INSET = 8;
export const SOURCE_RADIUS = 3;

/** The normal points outward from the target surface. */
export function arrowHead(tip: Point, normal: Point): Point[] {
  const rear: Point = [tip[0] + normal[0] * ARROW_LENGTH, tip[1] + normal[1] * ARROW_LENGTH];
  return [tip,
    [rear[0] - normal[1] * ARROW_HALF_WIDTH, rear[1] + normal[0] * ARROW_HALF_WIDTH],
    [rear[0] + normal[1] * ARROW_HALF_WIDTH, rear[1] - normal[0] * ARROW_HALF_WIDTH]];
}

/** Shared, notch-free triangle used by local string and heap arrows. */
export function arrowTriangle(x: number, y: number, direction = 1): string {
  return arrowHead([x, y], [-direction, 0]).map(p => p.join(",")).join(" ");
}
