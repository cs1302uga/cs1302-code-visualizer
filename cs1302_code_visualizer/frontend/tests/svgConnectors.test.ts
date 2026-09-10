/**
 * @fileoverview Unit tests for native TypeScript SVG connector engine.
 */

import { describe, it, expect, beforeEach } from "vitest";
import $ from "jquery";
import {
  SvgConnectorManager,
  SvgConnection,
  SvgEndpoint,
} from "../js/svgConnectors";

describe("svgConnectors", () => {
  let container: HTMLElement;
  let sourceEl: HTMLElement;
  let targetEl: HTMLElement;

  beforeEach(() => {
    document.body.innerHTML = "";
    container = document.createElement("div");
    container.id = "viz-container";
    container.style.position = "relative";
    container.style.width = "800px";
    container.style.height = "600px";
    document.body.appendChild(container);

    sourceEl = document.createElement("div");
    sourceEl.id = "source-node";
    sourceEl.style.position = "absolute";
    sourceEl.style.left = "50px";
    sourceEl.style.top = "50px";
    sourceEl.style.width = "100px";
    sourceEl.style.height = "30px";
    container.appendChild(sourceEl);

    targetEl = document.createElement("div");
    targetEl.id = "target-node";
    targetEl.style.position = "absolute";
    targetEl.style.left = "300px";
    targetEl.style.top = "50px";
    targetEl.style.width = "100px";
    targetEl.style.height = "30px";
    container.appendChild(targetEl);
  });

  describe("SvgEndpoint", () => {
    it("initializes with element, style, and visibility", () => {
      const ep = new SvgEndpoint("source-node", sourceEl, true, {
        fillStyle: "#005583",
        strokeStyle: "#005583",
      });

      expect(ep.elementId).toBe("source-node");
      expect(ep.element).toBe(sourceEl);
      expect(ep.isSource).toBe(true);
      expect(ep.paintStyle.fillStyle).toBe("#005583");
      expect(ep.visible).toBe(true);

      ep.setPaintStyle({ fillStyle: "#e93f34" });
      expect(ep.paintStyle.fillStyle).toBe("#e93f34");

      ep.setHoverPaintStyle({ fillStyle: "#ff0000" });
      expect(ep.hoverPaintStyle.fillStyle).toBe("#ff0000");
    });

    it("controls circleElement visibility via setVisible", () => {
      const ep = new SvgEndpoint("source-node", sourceEl, true, {});
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      ep.circleElement = circle;

      ep.setVisible(false);
      expect(ep.visible).toBe(false);
      expect(circle.style.display).toBe("none");

      ep.setVisible(true);
      expect(ep.visible).toBe(true);
      expect(circle.style.display).toBe("");
    });
  });

  describe("SvgConnectorManager", () => {
    it("creates SVG canvas overlay inside target container", () => {
      const manager = new SvgConnectorManager({ Container: container });

      expect(manager.container).toBe(container);
      expect(manager.svgCanvas).toBeDefined();
      expect(manager.svgCanvas.getAttribute("class")).toBe("svg-connector-canvas");
      expect(container.querySelector("svg.svg-connector-canvas")).toBe(manager.svgCanvas);
      expect(manager.connections).toEqual([]);
    });

    it("establishes connections between elements and updates connection list", () => {
      const manager = new SvgConnectorManager({ Container: container });

      const conn = manager.connect({
        source: "source-node",
        target: "target-node",
        scope: "test-scope",
      });

      expect(conn).toBeInstanceOf(SvgConnection);
      expect(manager.connections).toContain(conn);
      expect(conn.sourceId).toBe("source-node");
      expect(conn.targetId).toBe("target-node");
      expect(conn.scope).toBe("test-scope");

      // Verify SVG DOM elements creation
      expect(conn.groupElement).toBeDefined();
      expect(conn.pathElement).toBeDefined();
      expect(conn.dotElement).toBeDefined();
      expect(conn.arrowElement).toBeDefined();
      expect(manager.svgCanvas.contains(conn.groupElement)).toBe(true);
    });

    it("filters connections via select() and performs batch detachment", () => {
      const manager = new SvgConnectorManager({ Container: container });

      const conn1 = manager.connect({ source: "source-node", target: "target-node", scope: "scopeA" });
      const conn2 = manager.connect({ source: "source-node", target: "target-node", scope: "scopeB" });

      expect(manager.connections.length).toBe(2);

      const selectionA = manager.select({ scope: "scopeA" });
      expect(selectionA.length).toBe(1);

      let iteratedCount = 0;
      selectionA.each((c) => {
        expect(c).toBe(conn1);
        iteratedCount++;
      });
      expect(iteratedCount).toBe(1);

      selectionA.detach();
      expect(manager.connections.length).toBe(1);
      expect(manager.connections[0]).toBe(conn2);
    });

    it("resets and clears all active connections", () => {
      const manager = new SvgConnectorManager({ Container: container });

      manager.connect({ source: "source-node", target: "target-node" });
      manager.connect({ source: "source-node", target: "target-node" });
      expect(manager.connections.length).toBe(2);

      manager.reset();
      expect(manager.connections.length).toBe(0);
      expect(manager.svgCanvas.childNodes.length).toBe(0);
    });
  });

  describe("SvgConnection styling and hover interactions", () => {
    it("applies hover and base styling transitions", () => {
      const manager = new SvgConnectorManager({ Container: container });
      const conn = manager.connect({
        source: "source-node",
        target: "target-node",
        paintStyle: { strokeStyle: "#005583", lineWidth: 1 },
        hoverPaintStyle: { strokeStyle: "#e93f34", lineWidth: 2 },
      });

      expect(conn.pathElement.getAttribute("stroke")).toBe("#005583");
      expect(conn.pathElement.getAttribute("stroke-width")).toBe("1");

      conn.setHover(true);
      expect(conn.isHovered).toBe(true);
      expect(conn.pathElement.getAttribute("stroke")).toBe("#e93f34");
      expect(conn.pathElement.getAttribute("stroke-width")).toBe("2");

      conn.setHover(false);
      expect(conn.isHovered).toBe(false);
      expect(conn.pathElement.getAttribute("stroke")).toBe("#005583");
      expect(conn.pathElement.getAttribute("stroke-width")).toBe("1");
    });

    it("generates valid arrow polygon points and path curves", () => {
      const manager = new SvgConnectorManager({ Container: container });
      const conn = manager.connect({
        source: sourceEl,
        target: targetEl,
      });

      expect(conn.pathElement.getAttribute("d")).toMatch(/^M\s+\d+/);
      expect(conn.arrowElement.getAttribute("points")).toBeDefined();
      expect(conn.arrowElement.getAttribute("points")?.split(" ").length).toBe(4);
    });
  });
});
