/**
 * @fileoverview Unit tests for native TypeScript SVG connector engine.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { replay, textHits, pathPoints } from "./routingFixture";
import { intersects, routeReference, routeFrameParent, bounds, clear, expand, clearsSource, type Attachment } from "../js/referenceRouting";
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
      expect(conn.arrowElement.getAttribute("points")?.split(" ").length).toBe(3);
    });
  });
});

describe("reference routing on measured renderer geometry", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each(["later-node-compact", "later-node-inline", "later-node-default", "aliases-default",
    "cycle-default", "self-loop-default", "fields-default", "arrays-default", "arrays-compact"])(
    "%s keeps shafts out of visible text", name => {
      const { manager, data } = replay(name);
      expect(textHits(manager, data.texts)).toEqual([]);
      for(const c of manager.connections) {
        const dot=[Number(c.dotElement.getAttribute("cx")),Number(c.dotElement.getAttribute("cy"))];
        const head=c.arrowElement.getAttribute("points")!.split(" ").map(p=>p.split(",").map(Number));
        const shaft=pathPoints(c.pathElement.getAttribute("d")!);
        const box=c.source[0].closest(".value-box")!.getBoundingClientRect();
        const departure=shaft.find(p=>p[0]<box.left||p[0]>box.right||p[1]<box.top||p[1]>box.bottom)!;
        expect(departure[0]).toBeGreaterThanOrEqual(box.left);
        for(const t of data.texts) {
          const left=t.x-1,right=t.x+t.width+1,top=t.y-1,bottom=t.y+t.height+1;
          const overlap=(l:number,r:number,u:number,d:number)=>r>left&&l<right&&d>top&&u<bottom;
          expect(overlap(dot[0]-3,dot[0]+3,dot[1]-3,dot[1]+3),`${name}: dot / ${t.text}`).toBe(false);
          expect(overlap(Math.min(...head.map(p=>p[0])),Math.max(...head.map(p=>p[0])),
            Math.min(...head.map(p=>p[1])),Math.max(...head.map(p=>p[1]))),`${name}: head / ${t.text}`).toBe(false);
        }
      }
    },
  );

  it("measures each element once per pass and is independent of connection order",()=>{
    const {manager,reads}=replay("aliases-default");
    const paths=()=>Object.fromEntries(manager.connections.map(c=>[c.sourceId,[
      c.pathElement.getAttribute("d"),c.arrowElement.getAttribute("points")]]));
    const first=paths();reads.clear();manager.repaintEverything();
    expect(Math.max(...reads.values())).toBe(1);
    expect(paths()).toEqual(first);
    manager.connections.reverse();manager.repaintEverything();expect(paths()).toEqual(first);
  });

  it("keeps alias heads distinct and does not pass through another source dot",()=>{
    const {manager}=replay("aliases-default");
    const heads=manager.connections.map(c=>c.arrowElement.getAttribute("points"));
    expect(new Set(heads).size).toBe(heads.length);
    for(const c of manager.connections) {
      const points=pathPoints(c.pathElement.getAttribute("d")!);
      for(const other of manager.connections.filter(o=>o!==c)) {
        const x=Number(other.dotElement.getAttribute("cx")),y=Number(other.dotElement.getAttribute("cy"));
        expect(points.some(p=>Math.hypot(p[0]-x,p[1]-y)<4)).toBe(false);
      }
    }
  });

  it("detects narrow between-sample cubic collisions and clears a distant rectangle",()=>{
    const cubic:[number,number][]=[[0,0],[25,100],[75,-100],[100,0]];
    const t=.12345,x=75*t+75*t*t-50*t*t*t,y=300*t-900*t*t+600*t*t*t;
    expect(intersects(cubic,{left:x-.001,right:x+.001,top:y-.001,bottom:y+.001})).toBe(true);
    expect(intersects(cubic,{left:40,right:60,top:80,bottom:90})).toBe(false);
    expect(intersects([[0,1],[100,1]],{left:12,right:12.001,top:0,bottom:2})).toBe(true);
  });

  it("repairs a crowded source box and recomputes the same repair on repeated redraw",()=>{
    document.body.innerHTML='<div id="scene"><div class="stackFrame"><span class="value-box"><span id="source">123456</span></span></div><div id="target" class="heapObject"></div></div>';
    const scene=document.getElementById("scene")!,box=scene.querySelector<HTMLElement>(".value-box")!;
    const target=document.getElementById("target")!,source=document.getElementById("source")!;
    const r=()=>new DOMRect(10,10,Math.max(40,parseFloat(box.style.minWidth)||0),19);
    vi.spyOn(scene,"getBoundingClientRect").mockReturnValue(new DOMRect(0,0,300,100));
    vi.spyOn(box,"getBoundingClientRect").mockImplementation(r);
    vi.spyOn(source,"getBoundingClientRect").mockImplementation(r);
    vi.spyOn(box.parentElement!,"getBoundingClientRect").mockImplementation(r);
    vi.spyOn(target,"getBoundingClientRect").mockReturnValue(new DOMRect(180,10,70,40));
    vi.spyOn(Range.prototype,"getClientRects").mockReturnValue([new DOMRect(17,12,28,12)] as any);
    const manager=new SvgConnectorManager({Container:scene});
    const c=manager.connect({source,target});
    expect(Number(c.dotElement.getAttribute("cx"))).toBeGreaterThan(49);
    const first=c.pathElement.getAttribute("d");
    manager.repaintEverything();expect(c.pathElement.getAttribute("d")).toBe(first);
    expect(box.style.minWidth).toBe("64px");
    manager.reset();expect(box.style.minWidth).toBe("");
  });

  it("routes a two-node cycle with the third object still acting as an obstacle",()=>{
    const {manager,data}=replay("cycle-default",data=>{
      const back=data.connectors.find((c:any)=>c.sourceId.endsWith("heap_pointer_src_6"));
      const middle=data.connectors.find((c:any)=>c.sourceId.endsWith("heap_pointer_src_4"));
      middle.targetId=back.targetId;middle.target=back.target;middle.targetBody=back.targetBody;
    });
    expect(textHits(manager,data.texts)).toEqual([]);
    expect(manager.connections.every(c=>!!c.pathElement.getAttribute("d"))).toBe(true);
  });

  it("opens a target attachment when text covers every original boundary",()=>{
    document.body.innerHTML='<div id="scene"><div class="stackFrame"><span id="source" class="value-box"></span></div><div id="target" class="heapObject">label</div></div>';
    const scene=document.getElementById("scene")!,source=document.getElementById("source")!,target=document.getElementById("target")!;
    vi.spyOn(scene,"getBoundingClientRect").mockReturnValue(new DOMRect(0,0,400,200));
    vi.spyOn(source,"getBoundingClientRect").mockReturnValue(new DOMRect(10,10,40,19));
    vi.spyOn(source.parentElement!,"getBoundingClientRect").mockReturnValue(new DOMRect(5,5,60,30));
    vi.spyOn(target,"getBoundingClientRect").mockImplementation(()=>new DOMRect(180,10,Math.max(70,parseFloat(target.style.minWidth)||0),40));
    vi.spyOn(Range.prototype,"getClientRects").mockReturnValue([new DOMRect(180,10,70,40)] as any);
    const manager=new SvgConnectorManager({Container:scene});
    const c=manager.connect({source,target});
    expect(parseFloat(target.style.minWidth)).toBeGreaterThan(70);
    expect(pathPoints(c.pathElement.getAttribute("d")!).some(([x,y])=>x>180&&x<250&&y>10&&y<50)).toBe(false);
    const first=c.pathElement.getAttribute("d");manager.repaintEverything();
    expect(c.pathElement.getAttribute("d")).toBe(first);
  });

  it("preserves source spacing when the dot already has the required text clearance",()=>{
    document.body.innerHTML='<div id="scene"><div class="stackFrame"><span id="source" class="value-box">1234</span></div><div id="target" class="heapObject"></div></div>';
    const scene=document.getElementById("scene")!,source=document.getElementById("source")!,target=document.getElementById("target")!;
    vi.spyOn(scene,"getBoundingClientRect").mockReturnValue(new DOMRect(0,0,400,200));
    const r=()=>new DOMRect(10,10,Math.max(40,parseFloat(source.style.minWidth)||0),19);
    vi.spyOn(source,"getBoundingClientRect").mockImplementation(r);
    vi.spyOn(source.parentElement!,"getBoundingClientRect").mockImplementation(r);
    vi.spyOn(target,"getBoundingClientRect").mockReturnValue(new DOMRect(180,10,70,40));
    vi.spyOn(Range.prototype,"getClientRects").mockReturnValue([new DOMRect(17,12,20,12)] as any);
    const manager=new SvgConnectorManager({Container:scene});
    const c=manager.connect({source,target});
    // Text ends at 37; dot starts at 39. The required 1px clearance is already present.
    expect(source.style.minWidth).toBe("");
    expect(Number(c.dotElement.getAttribute("cx"))).toBe(42);
  });
});


describe("source attachment corridor", () => {
  const rect = (left: number, top: number, right: number, bottom: number) => ({left, top, right, bottom});
  const objects = [rect(260,80,310,120), rect(260,180,310,220),
    rect(75,160,125,200), rect(75,240,125,280)];
  const text = objects.map(r => rect(r.left+3,r.top+3,r.right-14,r.top+14));
  const attachment: Attachment = {
    source: [302,100], sourceBox: rect(270,90.5,310,109.5), enclosure: objects[0],
    target: objects[2], sourceOwner: 0, targetOwner: 2, returning: true, width: 1,
  };

  it("routes the review reproduction without doubling back through its source", () => {
    const route = routeReference(attachment, [...text,rect(298,196,306,204)], objects, [])!;
    expect(route).toBeDefined();
    expect(clear(route, text.map(r => expand(r,1)), 1)).toBe(true);
    // Independently protect the left edge and the dot after the initial departure.
    const leftEdge = rect(269.9,90.5,270.1,109.5);
    expect(route.segments.some(s => intersects(s,leftEdge))).toBe(false);
    let outside = false;
    for (const s of route.segments) {
      if (outside) expect(intersects(s,attachment.sourceBox)).toBe(false);
      const end = s[s.length-1];
      if (end[0]>310 || end[1]<90.5 || end[1]>109.5) outside = true;
    }
    expect(outside).toBe(true);
    expect(routeReference(attachment, [...text,rect(298,196,306,204)], objects, [])).toEqual(route);
  });

  it("rejects the original rightward stub followed by left-side re-entry", () => {
    expect(clearsSource({kind:"visibility",head:[[75,180],[69,177],[69,183]],
      segments:[[[302,100],[312,100]],[[312,100],[322,100],[312,100]],
        [[312,100],[69,100]],[[69,100],[69,180]]]}, attachment.sourceBox,1)).toBe(false);
  });
});

describe("frame-parent attachments", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([["LeftMiddle", "LeftMiddle", 100, 100], ["RightMiddle", "RightMiddle", 200, 200]] as const)(
    "retains clear %s/%s frame anchors and configured curviness", (sourceAnchor, targetAnchor, x, tipX) => {
      document.body.innerHTML='<div id="scene"><div id="child" class="stackFrame"></div><div id="parent" class="stackFrame"></div></div>';
      const scene=document.getElementById("scene")!, child=document.getElementById("child")!, parent=document.getElementById("parent")!;
      vi.spyOn(scene,"getBoundingClientRect").mockReturnValue(new DOMRect(0,0,400,300));
      vi.spyOn(child,"getBoundingClientRect").mockReturnValue(new DOMRect(100,160,100,40));
      vi.spyOn(parent,"getBoundingClientRect").mockReturnValue(new DOMRect(100,40,100,40));
      const manager=new SvgConnectorManager({Container:scene});
      const connection=manager.connect({source:child,target:parent,scope:"frameParentPointer",
        anchors:[sourceAnchor,targetAnchor],connector:["Bezier",{curviness:60}]});
      const sign=sourceAnchor==="LeftMiddle"?-1:1;
      expect(connection.dotElement.getAttribute("cx")).toBe(String(x));
      expect(connection.pathElement.getAttribute("d")).toBe(`M ${x} 180 C ${x+sign*60} 180 ${tipX+sign*66} 60 ${tipX+sign*6} 60`);
      expect(connection.arrowElement.getAttribute("points")!.split(" ")[0]).toBe(`${tipX},60`);
      const before=connection.pathElement.getAttribute("d");
      manager.repaintEverything();expect(connection.pathElement.getAttribute("d")).toBe(before);
    });

  it("detours around protected content while preserving frame sides and distinct arrivals", () => {
    const a:Attachment={source:[100,180],sourceBox:{left:100,right:200,top:160,bottom:200},
      enclosure:{left:100,right:200,top:160,bottom:200},target:{left:100,right:200,top:40,bottom:80},
      sourceOwner:0,targetOwner:1,returning:false,width:3,
      parent:{sourceSide:-1,targetSide:-1,curviness:45}};
    const text=[{left:40,right:90,top:105,bottom:135}];
    const frames=[a.sourceBox,a.target];
    const first=routeFrameParent(a,text,frames,[])!;
    expect(first).toBeDefined();
    expect(clear(first,text.map(r=>expand(r,1)),3)).toBe(true);
    expect(first.segments[0][1][0]).toBeLessThan(100);
    expect(first.head[0][0]).toBe(100);
    for(const frame of frames)expect(first.segments.some(s=>intersects(s,frame))).toBe(false);
    const second=routeFrameParent(a,text,frames,[bounds(first.head)])!;
    expect(second).toBeDefined();
    expect(second.head[0]).not.toEqual(first.head[0]);
    expect(second.head[0][0]).toBe(100);
    expect(clear(second,text.map(r=>expand(r,1)),3)).toBe(true);
  });
});
