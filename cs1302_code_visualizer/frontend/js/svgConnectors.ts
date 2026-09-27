
function escapeCssSelector(id: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(id);
  }
  return id.replace(/([\\ #;?%&,.+*~\':"!^$[\]()=>|\/@])/g, "\\$1");
}
/**
 * @fileoverview Native TypeScript SVG connector engine for Code Visualizer.
 * Provides vector curve routing, endpoints, and arrowhead overlays for pointer visualization.
 */

import $ from "jquery";

export const ARROW_LENGTH = 6;
export const SOURCE_INSET = 8;
export const SOURCE_RADIUS = 3;

/** Shared, notch-free triangle used by both local string and heap arrows. */
export function arrowTriangle(x: number, y: number, direction = 1): string {
  const rear = x - direction * ARROW_LENGTH;
  return `${x},${y} ${rear},${y-3} ${rear},${y+3}`;
}

type Point = [number, number];

/** Round the corners of an orthogonal route; the caller supplies the initial move. */
function roundedSegments(points: Point[]): string {
  const clean = points.filter((p, i) => !i || p[0] !== points[i-1][0] || p[1] !== points[i-1][1]);
  let result = "";
  for (let i = 1; i < clean.length - 1; i++) {
    const [before, at, after] = [clean[i-1], clean[i], clean[i+1]];
    const incoming = Math.hypot(at[0]-before[0], at[1]-before[1]);
    const outgoing = Math.hypot(after[0]-at[0], after[1]-at[1]);
    const r = Math.min(8, incoming/2, outgoing/2);
    const entry = at.map((v, j) => v + (before[j]-v)*r/incoming);
    const exit = at.map((v, j) => v + (after[j]-v)*r/outgoing);
    result += ` L ${entry[0]} ${entry[1]} Q ${at[0]} ${at[1]} ${exit[0]} ${exit[1]}`;
  }
  const end = clean[clean.length-1];
  return result + ` L ${end[0]} ${end[1]}`;
}


/**
 * Visual styling configuration for SVG connector paths and endpoints.
 */
export interface SvgPaintStyle {
  lineWidth?: number;
  strokeStyle?: string;
  fillStyle?: string;
}

/**
 * Options passed to SvgConnectorManager.connect to establish a connection.
 */
export interface SvgConnectOptions {
  source: string | HTMLElement | JQuery;
  target: string | HTMLElement | JQuery;
  scope?: string;
  anchors?: [string, string];
  connector?: unknown[];
  endpoint?: unknown[];
  endpointStyles?: [SvgPaintStyle?, SvgPaintStyle?];
  paintStyle?: SvgPaintStyle;
  hoverPaintStyle?: SvgPaintStyle;
  overlays?: unknown[];
}

/**
 * Represents an endpoint anchor attached to a DOM element.
 */
export class SvgEndpoint {
  public readonly elementId: string;
  public readonly element: HTMLElement;
  public readonly isSource: boolean;
  public paintStyle: SvgPaintStyle;
  public hoverPaintStyle: SvgPaintStyle;
  public visible = true;
  public circleElement?: SVGCircleElement;

  public constructor(
    elementId: string,
    element: HTMLElement,
    isSource: boolean,
    style: SvgPaintStyle
  ) {
    this.elementId = elementId;
    this.element = element;
    this.isSource = isSource;
    this.paintStyle = { ...style };
    this.hoverPaintStyle = { ...style };
  }

  /**
   * Sets the standard paint style for this endpoint.
   * @param style The paint style to apply.
   */
  public setPaintStyle(style: SvgPaintStyle): void {
    Object.assign(this.paintStyle, style);
    if (this.circleElement && style.fillStyle) {
      this.circleElement.setAttribute("fill", style.fillStyle);
    }
  }

  /**
   * Sets the hover paint style for this endpoint.
   * @param style The hover style to apply.
   */
  public setHoverPaintStyle(style: SvgPaintStyle): void {
    Object.assign(this.hoverPaintStyle, style);
  }

  /**
   * Sets the visibility of the endpoint circle.
   * @param visible Whether the endpoint circle is visible.
   */
  public setVisible(visible: boolean, _unusedA?: unknown, _unusedB?: unknown): void {
    this.visible = visible;
    if (this.circleElement) {
      this.circleElement.style.display = visible ? "" : "none";
    }
  }
}

/**
 * Represents a single directed SVG connection between a source and target DOM element.
 */
export class SvgConnection {
  public readonly manager: SvgConnectorManager;
  public readonly source: JQuery;
  public readonly target: JQuery;
  public readonly sourceId: string;
  public readonly targetId: string;
  public readonly scope: string;
  public readonly anchors: [string, string];
  public readonly curviness?: number;
  public paintStyle: SvgPaintStyle;
  public hoverPaintStyle: SvgPaintStyle;
  public isHovered = false;

  public readonly endpoints: [SvgEndpoint, SvgEndpoint];
  public readonly canvas: SVGSVGElement;
  public readonly groupElement: SVGGElement;
  public readonly pathElement: SVGPathElement;
  public readonly dotElement: SVGCircleElement;
  public readonly arrowElement: SVGPolygonElement;

  public constructor(manager: SvgConnectorManager, options: SvgConnectOptions) {
    this.manager = manager;

    // Resolve source element and ID
    let rawSource: HTMLElement | null = null;
    if (typeof options.source === "string") {
      this.sourceId = options.source;
      const el =
        manager.container.querySelector("#" + escapeCssSelector(this.sourceId)) ||
        document.getElementById(this.sourceId);
      rawSource = el as HTMLElement;
    } else {
      const node = options.source instanceof HTMLElement ? options.source : options.source[0];
      rawSource = node instanceof HTMLElement ? node : null;
      this.sourceId = rawSource ? rawSource.id : "";
    }
    this.source = $(rawSource);

    // Resolve target element and ID
    let rawTarget: HTMLElement | null = null;
    if (typeof options.target === "string") {
      this.targetId = options.target;
      const el =
        manager.container.querySelector("#" + escapeCssSelector(this.targetId)) ||
        document.getElementById(this.targetId);
      rawTarget = el as HTMLElement;
    } else {
      const node = options.target instanceof HTMLElement ? options.target : options.target[0];
      rawTarget = node instanceof HTMLElement ? node : null;
      this.targetId = rawTarget ? rawTarget.id : "";
    }
    this.target = $(rawTarget);

    this.scope = options.scope || "default";
    this.anchors = options.anchors || ["RightMiddle", "LeftMiddle"];

    if (
      options.connector &&
      Array.isArray(options.connector) &&
      options.connector[1] &&
      typeof (options.connector[1] as Record<string, unknown>).curviness === "number"
    ) {
      this.curviness = (options.connector[1] as Record<string, unknown>).curviness as number;
    }

    this.paintStyle = {
      lineWidth: 1,
      strokeStyle: "#005583",
      ...manager.defaults.PaintStyle,
      ...options.paintStyle,
    };
    this.hoverPaintStyle = {
      lineWidth: 1,
      strokeStyle: "#e93f34",
      ...manager.defaults.HoverPaintStyle,
      ...options.hoverPaintStyle,
    };

    const srcStyle =
      (options.endpointStyles && options.endpointStyles[0]) || {
        fillStyle: this.paintStyle.strokeStyle,
      };
    const dstStyle =
      (options.endpointStyles && options.endpointStyles[1]) || {
        fillStyle: undefined,
      };

    this.endpoints = [
      new SvgEndpoint(this.sourceId, rawSource!, true, srcStyle),
      new SvgEndpoint(this.targetId, rawTarget!, false, dstStyle),
    ];

    // Create SVG DOM elements
    this.canvas = manager.svgCanvas;
    this.groupElement = document.createElementNS("http://www.w3.org/2000/svg", "g");
    this.groupElement.setAttribute("class", "_jsPlumb_connector _svg_connector");

    this.pathElement = document.createElementNS("http://www.w3.org/2000/svg", "path");
    this.pathElement.setAttribute("fill", "none");
    this.pathElement.setAttribute("stroke", this.paintStyle.strokeStyle || "#005583");
    this.pathElement.setAttribute("stroke-width", String(this.paintStyle.lineWidth || 1));
    this.groupElement.appendChild(this.pathElement);

    this.dotElement = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    this.dotElement.setAttribute("r", String(SOURCE_RADIUS));
    this.dotElement.setAttribute(
      "fill",
      srcStyle.fillStyle || this.paintStyle.strokeStyle || "#005583"
    );
    this.endpoints[0].circleElement = this.dotElement;
    this.groupElement.appendChild(this.dotElement);

    this.arrowElement = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    this.arrowElement.setAttribute("fill", this.paintStyle.strokeStyle || "#005583");
    this.groupElement.appendChild(this.arrowElement);

    this.canvas.appendChild(this.groupElement);
    this.update();
  }

  /**
   * Sets the standard paint style for the connector line and arrow.
   * @param style The paint style to apply.
   */
  public setPaintStyle(style: SvgPaintStyle): void {
    Object.assign(this.paintStyle, style);
    if (!this.isHovered) {
      this.applyStyle(this.paintStyle);
    }
  }

  /**
   * Sets the hover paint style for the connector line and arrow.
   * @param style The hover paint style to apply.
   */
  public setHoverPaintStyle(style: SvgPaintStyle): void {
    Object.assign(this.hoverPaintStyle, style);
    if (this.isHovered) {
      this.applyStyle(this.hoverPaintStyle);
    }
  }

  /**
   * Toggles the hovered state and applies corresponding paint style.
   * @param hover Whether the connection is hovered.
   */
  public setHover(hover: boolean): void {
    this.isHovered = hover;
    this.applyStyle(hover ? this.hoverPaintStyle : this.paintStyle);
    if (this.endpoints[0]) {
      this.endpoints[0].setPaintStyle({
        fillStyle: (hover ? this.hoverPaintStyle : this.paintStyle).strokeStyle,
      });
    }
  }

  private applyStyle(style: SvgPaintStyle): void {
    if (style.strokeStyle) {
      this.pathElement.setAttribute("stroke", style.strokeStyle);
      this.arrowElement.setAttribute("fill", style.strokeStyle);
      this.dotElement.setAttribute("fill", style.strokeStyle);
    }
    if (style.lineWidth !== undefined) {
      this.pathElement.setAttribute("stroke-width", String(style.lineWidth));
    }
  }

  /**
   * Recalculates anchor coordinates, curve path, and arrowhead orientation.
   */
  public update(): void {
    const rawSource = this.source[0];
    const rawTarget = this.target[0];
    if (!rawSource || !rawTarget || !this.manager.container) {
      return;
    }

    const containerRect = this.manager.container.getBoundingClientRect();
    const srcRect = rawSource.getBoundingClientRect();
    const dstRect = rawTarget.getBoundingClientRect();

    let x1 = 0;
    let y1 = 0;
    let x2 = 0;
    let y2 = 0;

    // Anchor calculation
    if (this.anchors[0] === "LeftMiddle") {
      x1 = srcRect.left - containerRect.left;
      y1 = srcRect.top + srcRect.height / 2 - containerRect.top;
    } else {
      // Default: RightMiddle
      x1 = srcRect.right - containerRect.left;
      y1 = srcRect.top + srcRect.height / 2 - containerRect.top;
    }

    if (this.anchors[1] === "RightMiddle") {
      x2 = dstRect.right - containerRect.left;
      y2 = dstRect.top + dstRect.height / 2 - containerRect.top;
    } else {
      // Default: LeftMiddle
      x2 = dstRect.left - containerRect.left;
      y2 = dstRect.top + dstRect.height / 2 - containerRect.top;
    }

    const valueBox = rawSource.closest(".value-box");
    const enclosure = rawSource.closest(".instTbl,.classTbl,.dictTbl,.listTbl,.tupleTbl,.stackTbl,.queueTbl,.stackFrame,.zombieStackFrame");
    if (valueBox && this.anchors[0] !== "LeftMiddle") {
      const box = valueBox.getBoundingClientRect();
      x1 = box.right - containerRect.left - SOURCE_INSET;
      y1 = box.top + box.height / 2 - containerRect.top;
    }
    this.dotElement.setAttribute("cx", String(x1));
    this.dotElement.setAttribute("cy", String(y1));

    // Every shaft meets the rear edge of the same filled triangular head.
    const direction = this.anchors[1] === "RightMiddle" ? -1 : 1;
    const end = x2 - direction * ARROW_LENGTH;
    let d: string;
    if (this.anchors[0] === "LeftMiddle") {
      const c = this.curviness || 45;
      d = `M ${x1} ${y1} C ${x1-c} ${y1} ${end-direction*c} ${y2} ${end} ${y2}`;
    } else {
      const exit = enclosure && valueBox
        ? Math.max(x1, enclosure.getBoundingClientRect().right - containerRect.left - 4) : x1;
      const sourceHeap = rawSource.closest(".heapObject");
      const targetHeap = rawTarget.closest(".heapObject");
      const isReturn = sourceHeap && targetHeap &&
        targetHeap.getBoundingClientRect().left <= sourceHeap.getBoundingClientRect().left;
      if (isReturn && enclosure) {
        const returns = this.manager.connections.filter(c => {
          const source = c.source[0]?.closest(".heapObject");
          const target = c.target[0]?.closest(".heapObject");
          return source && target && target.getBoundingClientRect().left <= source.getBoundingClientRect().left;
        });
        const lane = Math.max(0, returns.indexOf(this));
        const enclosureRect = enclosure.getBoundingClientRect();
        const objects = Array.from(this.manager.container.querySelectorAll(".heapObject"))
          .map(e => e.getBoundingClientRect()).filter(r => r.width && r.height);
        const bottom = Math.max(enclosureRect.bottom, dstRect.bottom, ...objects.map(r => r.bottom)) - containerRect.top + 24 + lane * 12;
        const sourceRight = enclosureRect.right - containerRect.left + 16;
        const targetLeft = dstRect.left - containerRect.left - 20;
        const right = Math.max(sourceRight, ...objects.map(r => r.right - containerRect.left + 16)) + lane * 12;
        const left = Math.min(targetLeft, ...objects.map(r => r.left - containerRect.left - 20)) - lane * 12;
        const points: Point[] = [[exit, y1], [sourceRight, y1]];
        // Reach the outer rails through the gap below each endpoint's row, rather
        // than descending through unrelated arrays elsewhere in the heap.
        if (right > sourceRight) {
          const belowSource = sourceHeap.getBoundingClientRect().bottom - containerRect.top + 12;
          points.push([sourceRight, belowSource], [right, belowSource]);
        }
        points.push([right, bottom], [left, bottom]);
        if (left < targetLeft) {
          const belowTarget = targetHeap.getBoundingClientRect().bottom - containerRect.top + 12;
          points.push([left, belowTarget], [targetLeft, belowTarget]);
        }
        points.push([targetLeft, y2], [end, y2]);
        d = `M ${x1} ${y1} H ${exit}` + roundedSegments(points);
        this.pathElement.dataset.returnLane = String(lane);
      } else {
        const bend = end >= exit ? (end - exit) / 2 : 40;
        d = `M ${x1} ${y1} H ${exit} C ${exit+bend} ${y1} ${end-direction*bend} ${y2} ${end} ${y2}`;
        delete this.pathElement.dataset.returnLane;
      }
    }
    this.pathElement.setAttribute("d", d);
    this.arrowElement.setAttribute("points", arrowTriangle(x2, y2, direction));
  }

  /**
   * Detaches and destroys this connection and its SVG elements.
   */
  public detach(): void {
    if (this.groupElement && this.groupElement.parentNode) {
      this.groupElement.parentNode.removeChild(this.groupElement);
    }
    const idx = this.manager.connections.indexOf(this);
    if (idx !== -1) {
      this.manager.connections.splice(idx, 1);
    }
  }
}

/**
 * Manages the collection and lifecycle of SVG pointer connectors in a container.
 */
export class SvgConnectorManager {
  public container: HTMLElement;
  public readonly svgCanvas: SVGSVGElement;
  public connections: SvgConnection[] = [];
  public defaults: Record<string, any> = {};

  public constructor(defaults?: Record<string, unknown>) {
    this.defaults = defaults || {};
    this.container = document.body;
    this.svgCanvas = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    this.svgCanvas.setAttribute("class", "svg-connector-canvas");
    this.svgCanvas.style.position = "absolute";
    this.svgCanvas.style.top = "0px";
    this.svgCanvas.style.left = "0px";
    this.svgCanvas.style.width = "100%";
    this.svgCanvas.style.height = "100%";
    this.svgCanvas.style.pointerEvents = "none";
    this.svgCanvas.style.overflow = "visible";
    this.svgCanvas.style.zIndex = "100";

    if (defaults && defaults["Container"]) {
      this.setContainer(defaults["Container"] as HTMLElement | JQuery | string);
    }
  }

  /**
   * Sets the visualizer container element hosting the SVG canvas.
   * @param container Target container element, selector string, or jQuery object.
   */
  public setContainer(container: HTMLElement | JQuery | string): void {
    if (typeof container === "string") {
      this.container = (document.querySelector(container) || document.body) as HTMLElement;
    } else if ("jquery" in (container as any) || Array.isArray(container)) {
      this.container = (container as JQuery)[0] as HTMLElement;
    } else {
      this.container = container as HTMLElement;
    }

    if (this.container && this.svgCanvas.parentNode !== this.container) {
      if (getComputedStyle(this.container).position === "static") {
        this.container.style.position = "relative";
      }
      this.container.appendChild(this.svgCanvas);
    }
  }

  /**
   * Updates default options for newly created connections.
   * @param newDefaults Dictionary of default configuration options.
   */
  public importDefaults(newDefaults: Record<string, unknown>): void {
    Object.assign(this.defaults, newDefaults);
    if (newDefaults["Container"]) {
      this.setContainer(newDefaults["Container"] as HTMLElement | JQuery | string);
    }
  }

  /**
   * Creates and establishes a new SVG connection.
   * @param options Connection endpoints, anchors, and styling options.
   * @return The created connection instance.
   */
  public connect(options: SvgConnectOptions): SvgConnection {
    const conn = new SvgConnection(this, options);
    this.connections.push(conn);
    return conn;
  }

  /**
   * Resets and clears all active connections.
   */
  public reset(): void {
    for (const conn of [...this.connections]) {
      conn.detach();
    }
    this.connections = [];
    this.container.style.paddingBottom = "";
    this.container.style.paddingRight = "";
  }

  /**
   * Repaints all active connection curves and arrowheads.
   */
  public repaintEverything(): void {
    for (const conn of this.connections) conn.update();
    const returns = this.connections.filter(c => c.pathElement.dataset.returnLane !== undefined).length;
    this.container.style.paddingBottom = returns ? `${32 + returns * 12}px` : "";
    this.container.style.paddingRight = returns ? `${24 + returns * 12}px` : "";
  }

  /**
   * Filters and selects a subset of active connections.
   * @param filter Optional filter criteria by source ID, target ID, or scope.
   * @return Selection object supporting iteration and batch detachment.
   */
  public select(filter?: { source?: string; target?: string; scope?: string }): {
    length: number;
    each: (fn: (conn: SvgConnection) => void) => void;
    detach: () => void;
  } {
    const matched = this.connections.filter((c) => {
      if (filter?.source && c.sourceId !== filter.source) return false;
      if (filter?.target && c.targetId !== filter.target) return false;
      if (filter?.scope && c.scope !== filter.scope) return false;
      return true;
    });

    return {
      length: matched.length,
      each: (fn: (conn: SvgConnection) => void): void => {
        matched.forEach(fn);
      },
      detach: (): void => {
        matched.forEach((c) => c.detach());
      },
    };
  }

  /**
   * Factory helper returning a new SvgConnectorManager instance.
   * @param defaults Optional default connection options.
   * @return A new SvgConnectorManager instance.
   */
  public static getInstance(defaults?: Record<string, unknown>): SvgConnectorManager {
    return new SvgConnectorManager(defaults);
  }
}
