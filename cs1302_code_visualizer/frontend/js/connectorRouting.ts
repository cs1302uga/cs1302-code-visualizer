/** One DOM geometry snapshot per routing pass; search itself never reads the DOM. */
import { SOURCE_INSET, SOURCE_RADIUS } from "./connectorGeometry";
import type { SvgConnection } from "./svgConnectors";
import { Attachment, Rect, Route, bounds, circleIntersects, expand, intersects, pathData, routeReference, routeFrameParent } from "./referenceRouting";

const bodies=".instTbl,.classTbl,.dictTbl,.listTbl,.tupleTbl,.stackTbl,.queueTbl";
const owners=".heapObject,.stackFrame,.zombieStackFrame";

export class ConnectorRouting {
  public searchTimings: {kind:string; ms:number}[]=[];
  private fingerprint="";
  private routes: Route[]=[];
  private repairs: (()=>void)[]=[];

  public clearRepairs(): void {
    for(const restore of this.repairs.reverse())restore();
    this.repairs=[];
  }

  public repaint(container: HTMLElement, connections: SvgConnection[], attempt=0): void {
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
    const localEndpoints=Array.from(root.querySelectorAll(".compact-string-arrow circle,.compact-string-arrow polygon"))
      .filter(visible).map(rect);
    const edges=connections.filter(c=>{
      if(!c.source[0]||!c.target[0])return false;
      const s=rect(c.source[0].closest(".value-box")??c.source[0]),t=rect(c.target[0]);
      const shown=visible(c.source[0])&&visible(c.target[0])&&s.right>s.left&&s.bottom>s.top&&t.right>t.left&&t.bottom>t.top;
      c.groupElement.style.display=shown?"":"none";
      return shown;
    }).map(c=>{
      const source=c.source[0],target=c.target[0],box=source.closest(".value-box");
      const sb=rect(box??source),enclosure=rect(source.closest(`${bodies},.stackFrame,.zombieStackFrame`)??source);
      const so=elements.indexOf(source.closest(owners)!),to=elements.indexOf(target.closest(owners)!);
      const a:Attachment={source:[sb.right-(box?SOURCE_INSET:0),(sb.top+sb.bottom)/2],sourceBox:sb,enclosure,
        target:rect(target.querySelector(bodies)??target),legacyTarget:rect(target),sourceOwner:so,targetOwner:to,
        returning:so>=0&&to>=0&&!!source.closest(".heapObject")&&objects[to].left<=objects[so].left,
        width:Math.max(c.paintStyle.lineWidth??1,c.hoverPaintStyle.lineWidth??1)};
      if (c.scope === "frameParentPointer") {
        a.parent = {sourceSide: c.anchors[0] === "LeftMiddle" ? -1 : 1,
          targetSide: c.anchors[1] === "RightMiddle" ? 1 : -1, curviness: c.curviness ?? 45};
        a.source = [a.parent.sourceSide < 0 ? sb.left : sb.right, (sb.top + sb.bottom) / 2];
        a.target = rect(target);
      }
      return {c,a};
    }).sort((a,b)=>Number(!a.c.source[0].closest(".heapObject"))-Number(!b.c.source[0].closest(".heapObject"))||
      a.a.source[1]-b.a.source[1]||a.a.source[0]-b.a.source[0]||a.a.target.left-b.a.target.left||a.a.target.top-b.a.target.top||
      a.c.sourceId.replace(/^v\d+__/,"").localeCompare(b.c.sourceId.replace(/^v\d+__/,"")));
    const key=JSON.stringify([objects,text,localEndpoints,edges.map(e=>e.a)]);
    if(key!==this.fingerprint) {
      const heads:Rect[]=[],routes:Route[]=[];
      const arrivals=new Map<number,number>();
      this.searchTimings=[];
      for(const {a,c} of edges) {
        const started=performance.now();
        a.lane=arrivals.get(a.targetOwner)??0;
        const dots=edges.filter(e=>e.a!==a).map(e=>({left:e.a.source[0]-SOURCE_RADIUS-1,top:e.a.source[1]-SOURCE_RADIUS-1,
          right:e.a.source[0]+SOURCE_RADIUS+1,bottom:e.a.source[1]+SOURCE_RADIUS+1}));
        const dotHits=text.map((r,i)=>({r,i})).filter(({r})=>
          circleIntersects(a.source,SOURCE_RADIUS,expand(r,1)));
        const route=dotHits.length?undefined:(a.parent ? routeFrameParent : routeReference)(a,[...text,...dots,...localEndpoints],objects,heads);
        if(!route) {
          if (a.parent) throw new Error("Cannot route a frame-parent reference; inspect overlapping or constrained content");
          // Fixed-position candidates are exhausted. Repair the smallest local
          // obstruction and remeasure every reference, rather than hiding a link.
          const blocker=dotHits.map(h=>textOwners[h.i]).find(e=>e&&e!==elements[a.sourceOwner]) as HTMLElement|undefined;
          if(blocker&&attempt<connections.length+4) {
            const old=blocker.style.translate,b=rect(blocker),dy=a.enclosure.bottom-b.top+16;
            blocker.style.translate=`0px ${Math.max(16,dy)}px`;
            this.repairs.push(()=>{blocker.style.translate=old;});
            return this.repaint(container,connections,attempt+1);
          }
          const departures:[number,number][]=[[a.sourceBox.right+12,a.source[1]],
            [a.source[0],a.sourceBox.bottom+12],[a.source[0],a.sourceBox.top-12]];
          const sourceCanExit=departures.some(p=>![...text,...dots,...localEndpoints].some(r=>
            intersects([a.source,p],expand(r,1+a.width/2))));
          if(!dotHits.length&&sourceCanExit&&attempt<connections.length+4) {
            const target=(c.target[0].querySelector(bodies)??c.target[0]) as HTMLElement;
            const old=target.style.minWidth;
            target.style.minWidth=`${Math.ceil(a.target.right-a.target.left)+24}px`;
            this.repairs.push(()=>{target.style.minWidth=old;});
            return this.repaint(container,connections,attempt+1);
          }
          const box=c.source[0].closest<HTMLElement>(".value-box");
          if(box&&attempt<connections.length+4) {
            const old=box.style.minWidth;
            box.style.minWidth=`${Math.ceil(a.sourceBox.right-a.sourceBox.left)+24}px`;
            this.repairs.push(()=>{box.style.minWidth=old;});
            return this.repaint(container,connections,attempt+1);
          }
          throw new Error("Cannot route a reference after local layout repair; inspect overlapping or constrained content");
        }
        routes.push(route);heads.push(bounds(route.head));
        arrivals.set(a.targetOwner,a.lane+1);
        this.searchTimings.push({kind:route.kind,ms:performance.now()-started});
      }
      this.routes=routes;this.fingerprint=key;
    }
    edges.forEach(({c,a},i)=>{
      const r=this.routes[i];
      c.dotElement.setAttribute("cx",String(a.source[0]));c.dotElement.setAttribute("cy",String(a.source[1]));
      c.pathElement.setAttribute("d",pathData(r));c.pathElement.dataset.routing=r.kind;
      c.arrowElement.setAttribute("points",r.head.map(p=>p.join(",")).join(" "));
      delete c.pathElement.dataset.returnLane;
    });
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
        return this.repaint(container,connections,attempt+1);
      }
      container.style.paddingBottom=`${Math.max(0,Math.ceil(ext.bottom-content.bottom+8))}px`;
      container.style.paddingRight=`${Math.max(0,Math.ceil(ext.right-content.right+8))}px`;
    } else {
      container.style.paddingBottom="";
      container.style.paddingRight="";
    }
  }
}
