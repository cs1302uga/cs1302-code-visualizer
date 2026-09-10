
function escapeCssSelector(id: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(id);
  }
  return id.replace(/([ #;?%&,.+*~\':"!^$[\]()=>|\/@])/g, "\\$1");
}
/**
 * @fileoverview Native TypeScript SVG connector engine for Code Visualizer.
 * Provides vector curve routing, endpoints, and arrowhead overlays for pointer visualization.
 */

import $ from "jquery";

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
      const $s = $(options.source);
      rawSource = $s[0] as HTMLElement;
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
      const $t = $(options.target);
      rawTarget = $t[0] as HTMLElement;
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
    this.dotElement.setAttribute("r", "3");
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

    // Dot position
    this.dotElement.setAttribute("cx", String(x1));
    this.dotElement.setAttribute("cy", String(y1));

    // Path & Arrow trajectory
    let d = "";
    let endAngle = 0;

    if (this.anchors[0] === "LeftMiddle" && this.anchors[1] === "LeftMiddle") {
      // Frame parent pointer curve (arches out to the left)
      const c = this.curviness || 45;
      const cp1x = x1 - c;
      const cp1y = y1;
      const cp2x = x2 - c;
      const cp2y = y2;
      d = `M ${x1} ${y1} C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${x2} ${y2}`;
      endAngle = Math.atan2(y2 - cp2y, x2 - cp2x);
    } else {
      // Standard Stack/Heap pointer curve
      if (x2 >= x1) {
        const dx = x2 - x1;
        const c = Math.max(dx * 0.5, 30);
        const cp1x = x1 + c;
        const cp1y = y1;
        const cp2x = x2 - c;
        const cp2y = y2;
        d = `M ${x1} ${y1} C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${x2} ${y2}`;
        endAngle = Math.atan2(y2 - cp2y, x2 - cp2x);
      } else {
        // Self-loop / backward pointer
        const cp1x = x1 + 40;
        const cp1y = y1;
        const cp2x = x2 - 40;
        const cp2y = y2;
        d = `M ${x1} ${y1} C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${x2} ${y2}`;
        endAngle = Math.atan2(y2 - cp2y, x2 - cp2x);
      }
    }

    this.pathElement.setAttribute("d", d);

    // Arrow geometry: length 5, width 7, foldback 0.55
    const len = 5;
    const halfWidth = 3.5;
    const foldbackDist = len * (1 - 0.55); // 2.25

    const cos = Math.cos(endAngle);
    const sin = Math.sin(endAngle);

    const rotatePoint = (rx: number, ry: number): [number, number] => [
      x2 + rx * cos - ry * sin,
      y2 + rx * sin + ry * cos,
    ];

    const pTip = rotatePoint(0, 0);
    const pTop = rotatePoint(-len, -halfWidth);
    const pFold = rotatePoint(-foldbackDist, 0);
    const pBot = rotatePoint(-len, halfWidth);

    this.arrowElement.setAttribute(
      "points",
      `${pTip[0]},${pTip[1]} ${pTop[0]},${pTop[1]} ${pFold[0]},${pFold[1]} ${pBot[0]},${pBot[1]}`
    );
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
  }

  /**
   * Repaints all active connection curves and arrowheads.
   */
  public repaintEverything(): void {
    for (const conn of this.connections) {
      conn.update();
    }
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
