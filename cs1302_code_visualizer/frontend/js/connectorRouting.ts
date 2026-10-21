/** One DOM geometry snapshot per routing pass; search itself never reads the DOM. */
import { SHAFT_CLEARANCE } from "./shaftClearance";
import { SOURCE_INSET, SOURCE_RADIUS } from "./connectorGeometry";
import type { SvgConnection, SvgConnectorManager } from "./svgConnectors";
import { Attachment, Point, Rect, Route, bounds, circleIntersects, expand, intersects, pathData, routeReference, routeFrameParent } from "./referenceRouting";
import { attachSharedReferenceBaseline, planSharedReferences, type SharedReferencePlan } from "./sharedReferenceRouting";

const bodies=".instTbl,.classTbl,.dictTbl,.listTbl,.tupleTbl,.stackTbl,.queueTbl";
const owners=".heapObject,.stackFrame,.zombieStackFrame";

/** Attachment exits used by both reservations and constrained-layout repair. */
function departureCandidates(a: Attachment): Point[] {
  return a.parent ? [[a.source[0]+a.parent.sourceSide*12,a.source[1]]] :
    [[a.sourceBox.right+12,a.source[1]],[a.source[0],a.sourceBox.bottom+12],[a.source[0],a.sourceBox.top-12]];
}

function sourceDotBounds(source: Point): Rect {
  const padding=SOURCE_RADIUS+1;
  return {left:source[0]-padding,top:source[1]-padding,
    right:source[0]+padding,bottom:source[1]+padding};
}

export class ConnectorRouting {
  public searchTimings: {kind:string; ms:number}[]=[];
  public baselineOrdering: "source"|"target"="source";
  private fingerprint="";
  private routes: Route[]=[];
  private sharingPlan?: SharedReferencePlan;
  private repairs: (()=>void)[]=[];

  public clearRepairs(): void {
    for(const restore of this.repairs.reverse())restore();
    this.repairs=[];
  }

  public repaint(container: HTMLElement, connections: SvgConnection[], attempt=0, reserveTurns=false,
    manager?: SvgConnectorManager): void {
    const policy=manager?.referenceRoutingPolicy??"historical";
    const controlled=policy!=="historical";
    if(!attempt)this.clearRepairs();
    const origin=container.getBoundingClientRect(),cache=new Map<Element,Rect>();
    cache.set(container,{left:0,top:0,right:origin.width,bottom:origin.height});
    const rect=(el:Element):Rect=>{
      let r=cache.get(el);if(r)return r;
      const b=el.getBoundingClientRect();
      r={left:b.left-origin.left,top:b.top-origin.top,right:b.right-origin.left,bottom:b.bottom-origin.top};
      cache.set(el,r);return r;
    };
    const root=container.querySelector("#dataViz")??container;
    const elements=Array.from(root.querySelectorAll(owners));
    const text:Rect[]=[];
    const textOwners:(Element|null)[]=[];
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    const range=document.createRange();
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
      if(!n.textContent?.trim()||!parent||parent.closest("svg,script,style"))continue;
      if(!visible(parent))continue;
      range.selectNodeContents(n);
      // getClientRects also excludes descendants of display:none ancestors.
      if(typeof range.getClientRects!=="function")continue;
      for(const b of Array.from(range.getClientRects())) if(b.width&&b.height) {
        text.push({left:b.left-origin.left,top:b.top-origin.top,right:b.right-origin.left,bottom:b.bottom-origin.top});
        textOwners.push(parent.closest(owners));
      }
    }
    const localEndpoints=Array.from(root.querySelectorAll(".compact-string-arrow circle,.compact-string-arrow polygon,.compact-string-arrow path"))
      .filter(visible).map(el=>expand(rect(el),.5));
    const edges=connections.filter(c=>{
      c.groupElement.style.display="none";
      if(!c.source[0]||!c.target[0]||!container.contains(c.source[0])||!container.contains(c.target[0]))return false;
      const s=rect(c.source[0].closest(".value-box")??c.source[0]),t=rect(c.target[0]);
      const shown=visible(c.source[0])&&visible(c.target[0])&&s.right>s.left&&s.bottom>s.top&&t.right>t.left&&t.bottom>t.top;
      c.groupElement.style.display=shown?"":"none";
      return shown;
    }).map(c=>{
      const source=c.source[0],target=c.target[0],box=source.closest(".value-box");
      const sb=rect(box??source),enclosure=rect(source.closest(`${bodies},.stackFrame,.zombieStackFrame`)??source);
      const so=elements.indexOf(source.closest(owners)!),to=elements.indexOf(target.closest(owners)!);
      const a:Attachment={source:[sb.right-(box?SOURCE_INSET:0),(sb.top+sb.bottom)/2],sourceBox:sb,enclosure,
        target:rect(target.querySelector(bodies)??target),targetKey:c.targetId,legacyTarget:rect(target),sourceOwner:so,targetOwner:to,
        returning:so>=0&&to>=0&&!!source.closest(".heapObject")&&objects[to].left<=objects[so].left,
        width:Math.max(c.paintStyle.lineWidth??1,c.hoverPaintStyle.lineWidth??1),strict:controlled};
      if (c.scope === "frameParentPointer") {
        a.parent = {sourceSide: c.anchors[0] === "LeftMiddle" ? -1 : 1,
          targetSide: c.anchors[1] === "RightMiddle" ? 1 : -1, curviness: c.curviness ?? 45};
        a.source = [a.parent.sourceSide < 0 ? sb.left : sb.right, (sb.top + sb.bottom) / 2];
        a.target = rect(target);
      }
      return {c,a};
    }).sort((a,b)=>Number(!!a.c.source[0].closest(".heapObject"))-Number(!!b.c.source[0].closest(".heapObject"))||
      a.a.source[1]-b.a.source[1]||a.a.source[0]-b.a.source[0]||a.a.target.left-b.a.target.left||a.a.target.top-b.a.target.top||
      a.c.sourceId.replace(/^v\d+__/,"").localeCompare(b.c.sourceId.replace(/^v\d+__/,"")));
    // Reserve turns up front when aligned stack sources need more distinct
    // lanes than fit between their boxes and the heap. Smaller scenes first
    // try their simpler routes, then retry coordination only if necessary.
    const stack=edges.filter(e=>!e.c.source[0].closest(".heapObject"));
    const heapLeft=Math.min(...objects.filter((r,i)=>elements[i].matches(".heapObject")&&
      (!controlled||(r.right>r.left&&r.bottom>r.top))).map(r=>r.left));
    const crowded=(sources:typeof stack)=>sources.some(({a})=>new Set(sources.filter(e=>e.a.source[0]===a.source[0])
      .map(e=>e.a.targetKey)).size*(SHAFT_CLEARANCE+a.width)>heapLeft-a.sourceBox.right);
    reserveTurns ||= crowded(stack);
    const ordinaryStack=stack.filter(e=>!e.a.parent);
    this.baselineOrdering=controlled&&crowded(ordinaryStack)?"target":"source";
    if(this.baselineOrdering==="target") {
      // Establish a crowded independent baseline target by target. This happens
      // before optional sharing; parent pointers and heap-reference slots stay fixed.
      const ordered=[...ordinaryStack].sort((x,y)=>
        x.a.target.left-y.a.target.left||x.a.target.top-y.a.target.top||
        x.c.targetId.replace(/^v\d+__/,"").localeCompare(y.c.targetId.replace(/^v\d+__/,""))||
        x.a.source[1]-y.a.source[1]||x.a.source[0]-y.a.source[0]||
        x.c.sourceId.replace(/^v\d+__/,"").localeCompare(y.c.sourceId.replace(/^v\d+__/,"")));
      let next=0;
      edges.forEach((edge,i)=>{if(ordinaryStack.includes(edge))edges[i]=ordered[next++];});
    }
    const styleKey=(c:SvgConnection):string|null=>c.semanticStyle ? JSON.stringify([
      c.scope,c.semanticStyle,
      c.paintStyle.lineWidth??1,c.paintStyle.strokeStyle,c.paintStyle.fillStyle,
      c.hoverPaintStyle.lineWidth??1,c.hoverPaintStyle.strokeStyle,c.hoverPaintStyle.fillStyle]) : null;
    const targets=new Map<string,Element>(),ambiguous=new Set<string>(),sourceCounts=new Map<string,number>();
    for(const {c} of edges) {
      if(targets.has(c.targetId)&&targets.get(c.targetId)!==c.target[0])ambiguous.add(c.targetId);
      targets.set(c.targetId,c.target[0]);
      sourceCounts.set(c.sourceId,(sourceCounts.get(c.sourceId)??0)+1);
    }
    const eligible=(c:SvgConnection,a:Attachment)=>!!c.sourceId&&!!c.targetId&&
      sourceCounts.get(c.sourceId)===1&&
      !ambiguous.has(c.targetId)&&c.target[0].id===c.targetId&&
      !a.parent&&!a.returning&&!(a.sourceOwner>=0&&a.sourceOwner===a.targetOwner);
    const logicalEdges=(routes:Route[])=>routes.map((route,i)=>{
      const {c,a}=edges[i];
      // Per-scene connection keys remain unique even for ineligible anonymous sources.
      return {key:JSON.stringify([c.sourceId,sourceCounts.get(c.sourceId)===1?null:i]),
        attachment:a,route,styleKey:styleKey(c),eligible:eligible(c,a)};
    });
    const key=JSON.stringify([policy,objects,text,localEndpoints,edges.map(e=>[
      e.a,e.c.sourceId,e.c.targetId,controlled?styleKey(e.c):null,controlled?eligible(e.c,e.a):false])]);
    if(key!==this.fingerprint) {
      const heads:Rect[]=[],routes:Route[]=[];
      let ownedGroups:SharedReferencePlan["groups"]=[];
      const arrivals=new Map<number,number>();
      this.searchTimings=[];
      // Reserve a usable departure for references routed later. Otherwise an
      // earlier parallel shaft can trap their only text-clear exit.
      const reservations=edges.map(({a})=>{
        const ends=departureCandidates(a);
        const obstacles=[...text,...localEndpoints,...edges.filter(e=>e.a!==a).map(e=>sourceDotBounds(e.a.source))];
        const end=ends.find(p=>!obstacles.some(r=>intersects([a.source,p],expand(r,1+a.width/2))));
        return end ? {segments:[[a.source,end]],head:[],kind:"departure",width:a.width,target:a.target,targetKey:a.targetKey,guard:expand(bounds([end]),SHAFT_CLEARANCE+a.width/2)} as Route : undefined;
      });
      for(const [index,{a,c}] of edges.entries()) {
        const started=performance.now();
        a.lane=arrivals.get(a.targetOwner)??0;
        const dots=edges.filter(e=>e.a!==a).map(e=>sourceDotBounds(e.a.source));
        const dotHits=text.map((r,i)=>({r,i})).filter(({r})=>
          circleIntersects(a.source,SOURCE_RADIUS,expand(r,1)));
        const future=reservations.slice(index+1).filter((r):r is Route=>!!r);
        const turns=reserveTurns?future.filter(r=>r.targetKey!==a.targetKey).map(r=>r.guard!):[];
        let ownedBaseline:SharedReferencePlan|undefined;
        const ownedFallback=()=>{
          if(!controlled||!eligible(c,a))return undefined;
          const incoming=edges.filter(e=>e.c.target[0]===c.target[0]);
          const spacing=Math.max(8,SHAFT_CLEARANCE+Math.max(...incoming.map(e=>e.a.width)));
          const perimeter=2*(a.target.right-a.target.left+a.target.bottom-a.target.top);
          // Keep ordinary scenes' independent search. The early owned-baseline
          // option is for oversubscribed arrival capacity, or extending an
          // already established owned suffix for that same target.
          if(incoming.length*spacing<=perimeter&&
            !ownedGroups.some(g=>g.targetKey===a.targetKey))return undefined;
          ownedBaseline=attachSharedReferenceBaseline({
            edges:logicalEdges([...routes,{segments:[],head:[],kind:"pending"}]),objects,
            obstacles:[...text,...localEndpoints,...turns,
              ...edges.slice(index+1).map(e=>sourceDotBounds(e.a.source)),
              ...future.flatMap(r=>r.segments.map(s=>expand(bounds(s),SHAFT_CLEARANCE+(r.width??1)/2)))],
            optimize:false,
          },index);
          return ownedBaseline?.routes[index];
        };
        // Ordinary crossings remain readable elsewhere, but a declared suffix
        // must also be protected from references routed later in the scene.
        const sharedObstacles=ownedGroups.flatMap(g=>g.physicalPieces.map(p=>
          expand(bounds(p.segment),SHAFT_CLEARANCE+Math.max(...p.members.map(i=>edges[i].a.width))/2)));
        const obstacles=[...text,...dots,...localEndpoints,...turns,...sharedObstacles];
        const route=dotHits.length?undefined:a.parent
          ? routeFrameParent(a,obstacles,objects,heads,[...routes,...future])
          : routeReference(a,obstacles,objects,heads,[...routes,...future],false,ownedFallback);
        if(!route) {
          // Retry coordination before changing any layout. Ordinary diagrams
          // retain their simpler routes; crowded ones reserve room to turn.
          if(!dotHits.length&&!reserveTurns)return this.repaint(container,connections,attempt,true,manager);
          if (a.parent) throw new Error("Cannot route a frame-parent reference; inspect overlapping or constrained content");
          // Fixed-position candidates are exhausted. Repair the smallest local
          // obstruction and remeasure every reference, rather than hiding a link.
          const blocker=dotHits.map(h=>textOwners[h.i]).find(e=>e&&e!==elements[a.sourceOwner]) as HTMLElement|undefined;
          if(blocker&&attempt<connections.length+4) {
            const old=blocker.style.translate,b=rect(blocker),dy=a.enclosure.bottom-b.top+16;
            blocker.style.translate=`0px ${Math.max(16,dy)}px`;
            this.repairs.push(()=>{blocker.style.translate=old;});
            return this.repaint(container,connections,attempt+1,false,manager);
          }
          const departures=departureCandidates(a);
          const sourceCanExit=departures.some(p=>![...text,...dots,...localEndpoints].some(r=>
            intersects([a.source,p],expand(r,1+a.width/2))));
          if(!dotHits.length&&sourceCanExit&&attempt<connections.length+4) {
            const target=(c.target[0].querySelector(bodies)??c.target[0]) as HTMLElement;
            const old=target.style.minWidth;
            // A controlled baseline needs distinct arrival capacity before the
            // optional sharing pass. Avoid dozens of failed +24px searches for
            // high fan-in; this is still only a repair hint, never clearance.
            const incoming=edges.filter(e=>e.c.target[0]===c.target[0]);
            const capacity=controlled ? incoming.length*Math.max(8,
              SHAFT_CLEARANCE+Math.max(...incoming.map(e=>e.a.width)))+20 : 0;
            target.style.minWidth=`${Math.max(Math.ceil(a.target.right-a.target.left)+24,capacity)}px`;
            this.repairs.push(()=>{target.style.minWidth=old;});
            return this.repaint(container,connections,attempt+1,false,manager);
          }
          const box=c.source[0].closest<HTMLElement>(".value-box");
          if(box&&attempt<connections.length+4) {
            const old=box.style.minWidth;
            box.style.minWidth=`${Math.ceil(a.sourceBox.right-a.sourceBox.left)+24}px`;
            this.repairs.push(()=>{box.style.minWidth=old;});
            return this.repaint(container,connections,attempt+1,false,manager);
          }
          throw new Error("Cannot route a reference after local layout repair; inspect overlapping or constrained content");
        }
        if(ownedBaseline) {
          routes.splice(0,routes.length,...ownedBaseline.routes.slice(0,index));
          ownedGroups=ownedBaseline.groups;
        }
        route.width=a.width;route.target=a.target;route.targetKey=a.targetKey;
        routes.push(route);heads.push(bounds(route.head));
        arrivals.set(a.targetOwner,a.lane+1);
        this.searchTimings.push({kind:route.kind,ms:performance.now()-started});
      }
      let plan:SharedReferencePlan|undefined;
      if(controlled) {
        plan=planSharedReferences({
          edges:logicalEdges(routes),
          obstacles:[...text,...localEndpoints],objects,optimize:policy==="shared",
        });
        if(!plan.baselineValid)throw new Error("Cannot establish an independent or explicitly shared reference baseline: "+
          plan.diagnostics.map(d=>d.reason).join("; "));
      }
      this.routes=plan?.routes??routes;this.sharingPlan=plan;this.fingerprint=key;
    }
    edges.forEach(({c,a},i)=>{
      const r=this.routes[i];
      c.dotElement.setAttribute("cx",String(a.source[0]));c.dotElement.setAttribute("cy",String(a.source[1]));
      c.pathElement.setAttribute("d",pathData(r));c.pathElement.dataset.routing=r.kind;
      c.arrowElement.setAttribute("points",r.head.map(p=>p.join(",")).join(" "));
      delete c.pathElement.dataset.returnLane;
    });
    manager?.paintReferencePlan(edges.map(e=>e.c),this.sharingPlan);
    const content=objects.length?bounds(objects.flatMap(r=>[[r.left,r.top],[r.right,r.bottom]])):rect(root);
    const paint=this.routes.flatMap(r=>[...r.segments.flat(),...r.head]);
    if(paint.length) {
      const ext=bounds(paint);
      // Left/top detours need real canvas space: raster capture cannot recover
      // paint outside the document origin by merely enlarging export bounds.
      if ((ext.left < 8 || ext.top < 8) && attempt < connections.length + 6) {
        const oldLeft=container.style.paddingLeft,oldTop=container.style.paddingTop;
        const style=getComputedStyle(container);
        container.style.paddingLeft=`${(parseFloat(style.paddingLeft)||0)+Math.max(0,Math.ceil(8-ext.left))}px`;
        container.style.paddingTop=`${(parseFloat(style.paddingTop)||0)+Math.max(0,Math.ceil(8-ext.top))}px`;
        this.repairs.push(()=>{container.style.paddingLeft=oldLeft;container.style.paddingTop=oldTop;});
        return this.repaint(container,connections,attempt+1,false,manager);
      }
      container.style.paddingBottom=`${Math.max(0,Math.ceil(ext.bottom-content.bottom+8))}px`;
      container.style.paddingRight=`${Math.max(0,Math.ceil(ext.right-content.right+8))}px`;
    } else {
      container.style.paddingBottom="";
      container.style.paddingRight="";
    }
  }
}
