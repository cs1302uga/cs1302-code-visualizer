/** DOM measurement and SVG publication. The routing DTO has no DOM bindings. */
import { SOURCE_INSET } from "./connectorGeometry";
import { Attachment, Rect, bounds, expand, pathData } from "./referenceRouting";
import type { SvgConnection } from "./svgConnectors";
import type { ConnectorRoutePlan, MeasuredConnectorEdge, MeasuredConnectorScene } from "./connectorRouting";
import type { SharedReferencePlan } from "./sharedReferenceRouting";

const bodies=".instTbl,.classTbl,.dictTbl,.listTbl,.tupleTbl,.stackTbl,.queueTbl";
const ownerSelector=".heapObject,.stackFrame,.zombieStackFrame";

/** Private-to-the-host bindings, kept beside, never inside, the solver scene. */
export interface ConnectorMeasurement {
  scene: MeasuredConnectorScene;
  bindings: {
    connections: readonly SvgConnection[];
    owners: HTMLElement[];
    targetBodies: Map<number, HTMLElement>;
    sourceBoxes: Map<number, HTMLElement>;
  };
}

/** SVG publication adapter. Solver input contains only the measured facts above. */
export interface ConnectorPaintHost {
  paintReferencePlan(ordered: SvgConnection[], plan?: SharedReferencePlan): void;
  clearReferencePaint(): void;
}

/** Read each element rectangle once in this pass, including repair passes. No paint writes. */
export function measureConnectorScene(container: HTMLElement, connections: readonly SvgConnection[]): ConnectorMeasurement {
  const origin=container.getBoundingClientRect(),cache=new Map<Element,Rect>();
  const canvas={left:0,top:0,right:origin.width,bottom:origin.height};
  cache.set(container,canvas);
  const rect=(el:Element):Rect=>{
    let r=cache.get(el);if(r)return r;
    const b=el.getBoundingClientRect();
    r={left:b.left-origin.left,top:b.top-origin.top,right:b.right-origin.left,bottom:b.bottom-origin.top};
    cache.set(el,r);return r;
  };
  const root=container.querySelector("#dataViz")??container;
  const elements=Array.from(root.querySelectorAll<HTMLElement>(ownerSelector));
  const text:Rect[]=[],textOwners:number[]=[];
  const walker=container.ownerDocument.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  const range=container.ownerDocument.createRange();
  const visibility=new Map<Element,boolean>();
  const visible=(el:Element|null):boolean=>{
    if(!el||el===root.parentElement)return true;
    const cached=visibility.get(el);if(cached!==undefined)return cached;
    const style=getComputedStyle(el),ok=style.display!=="none"&&style.visibility!=="hidden"&&
      style.visibility!=="collapse"&&style.opacity!=="0"&&visible(el.parentElement);
    visibility.set(el,ok);return ok;
  };
  const objects=elements.map(el=>visible(el)?rect(el):{left:0,top:0,right:0,bottom:0});
  while(walker.nextNode()) {
    const n=walker.currentNode,parent=n.parentElement;
    if(!n.textContent?.trim()||!parent||parent.closest("svg,script,style")||!visible(parent))continue;
    range.selectNodeContents(n);
    if(typeof range.getClientRects!=="function")continue;
    for(const b of Array.from(range.getClientRects()))if(b.width&&b.height) {
      text.push({left:b.left-origin.left,top:b.top-origin.top,right:b.right-origin.left,bottom:b.bottom-origin.top});
      textOwners.push(elements.indexOf(parent.closest<HTMLElement>(ownerSelector)!));
    }
  }
  const localEndpoints=Array.from(root.querySelectorAll(".compact-string-arrow circle,.compact-string-arrow polygon,.compact-string-arrow path"))
    .filter(visible).map(el=>expand(rect(el),.5));
  const targetBodies=new Map<number,HTMLElement>(),sourceBoxes=new Map<number,HTMLElement>();
  const targetIdentities=new Map<Element,number>();
  const edges:MeasuredConnectorEdge[]=[];
  connections.forEach((c,connectionIndex)=>{
    const source=c.source[0],target=c.target[0];
    if(!source||!target||!container.contains(source)||!container.contains(target))return;
    const box=source.closest<HTMLElement>(".value-box");
    const sb=rect(box??source),t=rect(target);
    if(!visible(source)||!visible(target)||sb.right<=sb.left||sb.bottom<=sb.top||t.right<=t.left||t.bottom<=t.top)return;
    const enclosure=rect(source.closest(`${bodies},.stackFrame,.zombieStackFrame`)??source);
    const so=elements.indexOf(source.closest<HTMLElement>(ownerSelector)!),to=elements.indexOf(target.closest<HTMLElement>(ownerSelector)!);
    const body=(target.querySelector(bodies)??target) as HTMLElement;
    const heapOrigin=!!source.closest(".heapObject");
    const a:Attachment={source:[sb.right-(box?SOURCE_INSET:0),(sb.top+sb.bottom)/2],sourceBox:sb,enclosure,
      target:rect(body),targetKey:c.targetId,legacyTarget:t,sourceOwner:so,targetOwner:to,
      returning:so>=0&&to>=0&&heapOrigin&&objects[to].left<=objects[so].left,
      width:Math.max(c.paintStyle.lineWidth??1,c.hoverPaintStyle.lineWidth??1)};
    if(c.scope==="frameParentPointer") {
      a.parent={sourceSide:c.anchors[0]==="LeftMiddle"?-1:1,
        targetSide:c.anchors[1]==="RightMiddle"?1:-1,curviness:c.curviness??45};
      a.source=[a.parent.sourceSide<0?sb.left:sb.right,(sb.top+sb.bottom)/2];
      a.target=t;
    }
    targetBodies.set(connectionIndex,body);
    if(box)sourceBoxes.set(connectionIndex,box);
    if(!targetIdentities.has(target))targetIdentities.set(target,targetIdentities.size);
    const styleKey=c.semanticStyle?JSON.stringify([
      c.scope,c.semanticStyle,
      c.paintStyle.lineWidth??1,c.paintStyle.strokeStyle,c.paintStyle.fillStyle,
      c.hoverPaintStyle.lineWidth??1,c.hoverPaintStyle.strokeStyle,c.hoverPaintStyle.fillStyle]):null;
    edges.push({connectionIndex,sourceId:c.sourceId,targetId:c.targetId,heapOrigin,attachment:a,
      targetIdentity:targetIdentities.get(target)!,styleKey,sharingEligible:false});
  });
  // Resolve element identity and naming ambiguities once at the host boundary.
  // Search consumes numeric identities and eligibility facts, never DOM nodes.
  const targets=new Map<string,number>(),ambiguous=new Set<string>(),sourceCounts=new Map<string,number>();
  for(const edge of edges) {
    if(targets.has(edge.targetId)&&targets.get(edge.targetId)!==edge.targetIdentity)ambiguous.add(edge.targetId);
    targets.set(edge.targetId,edge.targetIdentity!);
    sourceCounts.set(edge.sourceId,(sourceCounts.get(edge.sourceId)??0)+1);
  }
  for(const edge of edges) {
    const a=edge.attachment,c=connections[edge.connectionIndex];
    edge.sharingEligible=!!edge.sourceId&&!!edge.targetId&&sourceCounts.get(edge.sourceId)===1&&
      !ambiguous.has(edge.targetId)&&c.target[0].id===edge.targetId&&
      !a.parent&&!a.returning&&!(a.sourceOwner>=0&&a.sourceOwner===a.targetOwner);
  }
  edges.sort((a,b)=>Number(a.heapOrigin)-Number(b.heapOrigin)||
    a.attachment.source[1]-b.attachment.source[1]||a.attachment.source[0]-b.attachment.source[0]||
    a.attachment.target.left-b.attachment.target.left||a.attachment.target.top-b.attachment.target.top||
    a.sourceId.replace(/^v\d+__/,"").localeCompare(b.sourceId.replace(/^v\d+__/,"")));
  const content=objects.length?bounds(objects.flatMap(r=>[[r.left,r.top],[r.right,r.bottom]])):rect(root);
  return {scene:{objects,heapOwners:elements.map(e=>e.matches(".heapObject")),text,textOwners,localEndpoints,edges,content,canvas},
    bindings:{connections,owners:elements,targetBodies,sourceBoxes}};
}

/** Only the coordinator's final accepted plan is published. Invisible endpoints stay hidden. */
export function paintConnectorPlan(measurement: ConnectorMeasurement, plan: ConnectorRoutePlan,
  host?: ConnectorPaintHost): void {
  for(const c of measurement.bindings.connections)c.groupElement.style.display="none";
  for(const {connectionIndex,attachment:a,route:r} of plan.connectors) {
    const c=measurement.bindings.connections[connectionIndex];
    c.dotElement.setAttribute("cx",String(a.source[0]));c.dotElement.setAttribute("cy",String(a.source[1]));
    c.pathElement.setAttribute("d",pathData(r));c.pathElement.dataset.routing=r.kind;
    c.arrowElement.setAttribute("points",r.head.map(p=>p.join(",")).join(" "));
    delete c.pathElement.dataset.returnLane;
    c.groupElement.style.display="";
  }
  host?.paintReferencePlan(plan.connectors.map(c=>measurement.bindings.connections[c.connectionIndex]),plan.sharingPlan);
}

/** Failure/reset removes stale route geometry as well as hiding every group. */
export function clearConnectorPaint(connections: readonly SvgConnection[], host?: ConnectorPaintHost): void {
  host?.clearReferencePaint();
  for(const c of connections) {
    c.groupElement.style.display="none";
    c.pathElement.setAttribute("d","");c.arrowElement.setAttribute("points","");
    c.dotElement.removeAttribute("cx");c.dotElement.removeAttribute("cy");
    delete c.pathElement.dataset.routing;delete c.pathElement.dataset.returnLane;
    if(c.branchElement) {
      c.branchElement.style.display="none";
      c.branchElement.setAttribute("d","");
    }
    delete c.groupElement.dataset.sharedReference;
  }
}
