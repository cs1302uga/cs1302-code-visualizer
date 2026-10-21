import {describe, expect, it, vi} from "vitest";
import {SvgConnectorManager} from "../js/svgConnectors";
import {pathPoints} from "./routingFixture";

type Point=[number,number];
const same=(a:Point,b:Point)=>Math.hypot(a[0]-b[0],a[1]-b[1])<1e-6;
const shown=(element:Element):boolean=>{
  for(let at:Element|null=element;at;at=at.parentElement) {
    const style=getComputedStyle(at);
    if(style.display==="none"||style.visibility==="hidden"||style.opacity==="0")return false;
  }
  return true;
};

function measuredScene() {
  document.body.innerHTML='<div class="ExecutionVisualizer"><div id="dataViz"></div></div>';
  const container=document.querySelector<HTMLElement>(".ExecutionVisualizer")!,root=document.getElementById("dataViz")!;
  const measure=(element:Element,x:number,y:number,width:number,height:number)=>
    vi.spyOn(element,"getBoundingClientRect").mockReturnValue(new DOMRect(x,y,width,height));
  measure(container,0,0,320,350);measure(root,0,0,320,350);
  const owner=(id:string,className:string,x:number,y:number,width:number,height:number)=>{
    const element=document.createElement("div");element.id=id;element.className=className;root.append(element);
    measure(element,x,y,width,height);
    const body=document.createElement("table");body.className="instTbl";element.append(body);measure(body,x,y,width,height);
    return {element,body};
  };
  const stack=owner("stack","stackFrame",20,110,88,200);
  const target=owner("alias-target","heapObject",180,40,5,5);
  const foreignOwner=owner("foreign-owner","heapObject",98,88,22,24);
  const foreignTarget=owner("foreign-target","heapObject",230,85,50,30);
  const source=(id:string,parent:Element,x:number,y:number,width:number,height:number)=>{
    const box=document.createElement("span");box.className="value-box";parent.append(box);measure(box,x,y,width,height);
    const element=document.createElement("div");element.id=id;box.append(element);measure(element,x+7,y+4,18,12);
    return element;
  };
  const aliases=Array.from({length:4},(_,i)=>source(`alias-${i}`,stack.body,50,140+i*40,50,20));
  const foreign=source("foreign-source",foreignOwner.body,100,90,18,20);
  const manager=new SvgConnectorManager({Container:container});
  manager.setReferenceRoutingPolicy("independent");
  manager.beginBatch();
  for(const element of aliases)manager.connect({source:element,target:target.element});
  manager.connect({source:foreign,target:foreignTarget.element});
  manager.endBatch();
  return {manager,foreignOwner:foreignOwner.element,foreign};
}

/** Follow actual visible SVG endpoints in their drawn direction, without group
 * membership metadata. The physical painter splits every declared join there.
 */
function assertVisibleTargets(manager:SvgConnectorManager) {
  const paths=Array.from(manager.svgCanvas.querySelectorAll("path")).filter(shown).map(path=>{
    const points=pathPoints(path.getAttribute("d")!);
    return {from:points[0],to:points[points.length-1]};
  });
  const heads=Array.from(manager.svgCanvas.querySelectorAll("polygon")).filter(shown).map(head=>{
    const points=head.getAttribute("points")!.trim().split(/\s+/).map(p=>p.split(",").map(Number) as Point);
    return {tip:points[0],rear:[(points[1][0]+points[2][0])/2,(points[1][1]+points[2][1])/2] as Point};
  });
  for(const connection of manager.connections.filter(c=>shown(c.groupElement))) {
    const start:Point=[Number(connection.dotElement.getAttribute("cx")),Number(connection.dotElement.getAttribute("cy"))];
    const reached:Point[]=[start],queue:Point[]=[start];
    while(queue.length) {
      const point=queue.shift()!;
      for(const path of paths)if(same(point,path.from)&&!reached.some(p=>same(p,path.to))) {
        reached.push(path.to);queue.push(path.to);
      }
    }
    const arrivals=heads.filter(h=>reached.some(p=>same(p,h.rear)));
    expect(arrivals,connection.sourceId).toHaveLength(1);
    const target=(connection.target[0].querySelector(".instTbl")??connection.target[0]).getBoundingClientRect();
    const [x,y]=arrivals[0].tip;
    expect((x===target.left||x===target.right)&&y>=target.top&&y<=target.bottom ||
      (y===target.top||y===target.bottom)&&x>=target.left&&x<=target.right,connection.sourceId).toBe(true);
  }
}

function painted(manager:SvgConnectorManager):string[] {
  return Array.from(manager.svgCanvas.querySelectorAll("path,polygon,circle")).filter(shown)
    .map(e=>JSON.stringify([e.tagName,e.getAttribute("d"),e.getAttribute("points"),e.getAttribute("cx"),e.getAttribute("cy")])).sort();
}

describe("owned baseline and later references",()=>{
  it("protects an established suffix from a later foreign reference and restores visible relationships",()=>{
    const {manager,foreignOwner}=measuredScene();
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    expect(manager.referenceSharingPlan!.groups.length).toBeGreaterThan(0);
    expect(manager.referenceSharingPlan!.groups.every(g=>g.kind==="factored")).toBe(true);
    expect(manager.svgCanvas.querySelectorAll(".shared-reference-segment").length).toBeGreaterThan(0);
    assertVisibleTargets(manager);
    const foreign=manager.connections.find(c=>c.sourceId==="foreign-source")!;
    const foreignPoints=pathPoints(foreign.pathElement.getAttribute("d")!);
    const sourceX=Number(foreign.dotElement.getAttribute("cx")),sourceY=Number(foreign.dotElement.getAttribute("cy"));
    const targetLeft=foreign.target[0].getBoundingClientRect().left;
    let directWouldCross=false;
    for(const path of Array.from(manager.svgCanvas.querySelectorAll(".shared-reference-segment"))) {
      const sharedPoints=pathPoints(path.getAttribute("d")!);
      directWouldCross ||= sharedPoints.some(p=>Math.abs(p[1]-sourceY)<.2&&p[0]>sourceX&&p[0]<targetLeft);
      const gap=Math.min(...foreignPoints.map(p=>Math.min(...sharedPoints.map(q=>Math.hypot(p[0]-q[0],p[1]-q[1])))));
      expect(gap).toBeGreaterThanOrEqual(7-1e-5);
    }
    expect(directWouldCross).toBe(true);
    const before=painted(manager);
    manager.connections.reverse();manager.repaintEverything();
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    expect(painted(manager)).toEqual(before);assertVisibleTargets(manager);
    foreignOwner.style.display="none";manager.repaintEverything();
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);assertVisibleTargets(manager);
    foreignOwner.style.display="";manager.repaintEverything();
    expect(manager.referenceSharingPlan?.baselineValid).toBe(true);
    expect(painted(manager)).toEqual(before);assertVisibleTargets(manager);
  });
});
