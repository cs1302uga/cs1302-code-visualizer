/** Pure sequential routing over one coherent, measured scene. */
import { SHAFT_CLEARANCE } from "./shaftClearance";
import { SOURCE_RADIUS } from "./connectorGeometry";
import { Attachment, Point, Rect, Route, bounds, circleIntersects, expand, intersects,
  routeReference, routeFrameParent } from "./referenceRouting";
import { attachSharedReferenceBaseline, planSharedReferences, type SharedReferencePlan } from "./sharedReferenceRouting";

export type ReferenceRoutingPolicy = "historical" | "independent" | "shared";

/** IDs and indices bind results outside the solver; none of these facts contain DOM nodes. */
export interface MeasuredConnectorEdge {
  connectionIndex: number;
  sourceId: string;
  targetId: string;
  heapOrigin: boolean;
  attachment: Attachment;
  /** Null or absent means compatible semantic paint has not been established. */
  styleKey?: string | null;
  /** The measurement adapter establishes source/target identity eligibility. */
  sharingEligible?: boolean;
  /** Per-measurement target element identity token, independent of target ID. */
  targetIdentity?: number;
}

export interface MeasuredConnectorScene {
  objects: Rect[];
  heapOwners: boolean[];
  text: Rect[];
  /** Owner index for each text rectangle; -1 means text outside a frame/object. */
  textOwners: number[];
  localEndpoints: Rect[];
  /** Canonically ordered by the measurement adapter. */
  edges: MeasuredConnectorEdge[];
  content: Rect;
  canvas: Rect;
}

export interface PlannedConnector {
  connectionIndex: number;
  attachment: Attachment;
  route: Route;
}

export interface ConnectorRoutePlan {
  /** Routing order; sharing-plan member indices address this array. */
  connectors: PlannedConnector[];
  /** Unexpanded control-point/head bounds, matching legacy canvas allocation. */
  extent?: Rect;
  searchTimings: {kind: string; ms: number}[];
  sharingPlan?: SharedReferencePlan;
  baselineOrdering?: "source" | "target";
}

/** Every edgeIndex addresses the original scene.edges, even after target ordering. */
export type RoutingConstraint =
  | {kind: "reservation-retry"; edgeIndex: number}
  | {kind: "covered-source"; edgeIndex: number; blockerOwners: number[]; sourceCanExit: boolean}
  | {kind: "no-candidate"; edgeIndex: number; sourceCanExit: boolean; targetCapacity?: number}
  | {kind: "frame-parent"; edgeIndex: number};

export type RoutingResult =
  | {ok: true; plan: ConnectorRoutePlan}
  | {ok: false; constraint: RoutingConstraint};

/** Attachment exits used by both reservations and constrained-layout diagnosis. */
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
  /** Stateless planner. Accepted-scene reuse belongs to the coordinator, outside the solver. */
  public plan(scene: MeasuredConnectorScene, reserveTurns=false,
    policy: ReferenceRoutingPolicy="historical"): RoutingResult {
    const controlled=policy!=="historical";
    const {objects,text,localEndpoints}=scene;
    // Lane and strictness belong to this plan, never to the supplied measurement.
    const edges=scene.edges.map((edge,originalIndex)=>({...edge,originalIndex,
      attachment:{...edge.attachment,strict:controlled}}));
    const stack=edges.filter(e=>!e.heapOrigin);
    const heapLeft=Math.min(...objects.filter((r,i)=>scene.heapOwners[i]&&
      (!controlled||(r.right>r.left&&r.bottom>r.top))).map(r=>r.left));
    const crowded=(sources:typeof stack)=>sources.some(({attachment:a})=>
      new Set(sources.filter(e=>e.attachment.source[0]===a.source[0])
        .map(e=>e.attachment.targetKey)).size*(SHAFT_CLEARANCE+a.width)>heapLeft-a.sourceBox.right);
    reserveTurns ||= crowded(stack);
    const ordinaryStack=stack.filter(e=>!e.attachment.parent);
    const baselineOrdering=controlled&&crowded(ordinaryStack)?"target":"source";
    if(baselineOrdering==="target") {
      // Parent-pointer and heap-reference slots stay fixed while ordinary stack
      // references establish the same crowded, target-ordered baseline as PR28.
      const canonical=(id:string)=>id.replace(/^v\d+__/,"");
      const ordered=[...ordinaryStack].sort((x,y)=>
        x.attachment.target.left-y.attachment.target.left||x.attachment.target.top-y.attachment.target.top||
        canonical(x.targetId).localeCompare(canonical(y.targetId))||
        x.attachment.source[1]-y.attachment.source[1]||x.attachment.source[0]-y.attachment.source[0]||
        canonical(x.sourceId).localeCompare(canonical(y.sourceId)));
      let next=0;
      edges.forEach((edge,i)=>{if(ordinaryStack.includes(edge))edges[i]=ordered[next++];});
    }
    const sourceCounts=new Map<string,number>();
    for(const edge of edges)sourceCounts.set(edge.sourceId,(sourceCounts.get(edge.sourceId)??0)+1);
    const eligible=(edge:MeasuredConnectorEdge)=>{
      const a=edge.attachment;
      return edge.sharingEligible===true&&!!edge.sourceId&&!!edge.targetId&&
        sourceCounts.get(edge.sourceId)===1&&!a.parent&&!a.returning&&
        !(a.sourceOwner>=0&&a.sourceOwner===a.targetOwner);
    };
    const sameTarget=(x:MeasuredConnectorEdge,y:MeasuredConnectorEdge)=>
      x.targetIdentity!==undefined&&y.targetIdentity!==undefined
        ?x.targetIdentity===y.targetIdentity:x.targetId===y.targetId;
    const logicalEdges=(routes:Route[])=>routes.map((route,i)=>{
      const edge=edges[i];
      // Keep per-scene keys unique for ineligible duplicate or anonymous sources.
      return {key:JSON.stringify([edge.sourceId,sourceCounts.get(edge.sourceId)===1?null:i]),
        attachment:edge.attachment,route,styleKey:edge.styleKey??null,eligible:eligible(edge)};
    });
    const heads:Rect[]=[],routes:Route[]=[];
    let ownedGroups:SharedReferencePlan["groups"]=[];
    const searchTimings:ConnectorRoutePlan["searchTimings"]=[];
    const arrivals=new Map<number,number>();
    // Keep the original reservation construction, candidate order, costs and caps.
    const reservations=edges.map(({attachment:a})=>{
      const ends=departureCandidates(a);
      const obstacles=[...text,...localEndpoints,...edges.filter(e=>e.attachment!==a).map(e=>sourceDotBounds(e.attachment.source))];
      const end=ends.find(p=>!obstacles.some(r=>intersects([a.source,p],expand(r,1+a.width/2))));
      return end ? {segments:[[a.source,end]],head:[],kind:"departure",width:a.width,target:a.target,targetKey:a.targetKey,
        guard:expand(bounds([end]),SHAFT_CLEARANCE+a.width/2)} as Route : undefined;
    });
    for(const [index,edge] of edges.entries()) {
      const started=performance.now(),a=edge.attachment;
      a.lane=arrivals.get(a.targetOwner)??0;
      const dots=edges.filter((_,i)=>i!==index).map(e=>sourceDotBounds(e.attachment.source));
      const dotHits=text.map((r,i)=>({r,i})).filter(({r})=>circleIntersects(a.source,SOURCE_RADIUS,expand(r,1)));
      const future=reservations.slice(index+1).filter((r):r is Route=>!!r);
      const turns=reserveTurns?future.filter(r=>r.targetKey!==a.targetKey).map(r=>r.guard!):[];
      let ownedBaseline:SharedReferencePlan|undefined;
      const ownedFallback=()=>{
        if(!controlled||!eligible(edge))return undefined;
        const incoming=edges.filter(e=>sameTarget(e,edge));
        const spacing=Math.max(8,SHAFT_CLEARANCE+Math.max(...incoming.map(e=>e.attachment.width)));
        const perimeter=2*(a.target.right-a.target.left+a.target.bottom-a.target.top);
        // Ordinary scenes retain independent search. Owned suffixes are an
        // option for oversubscribed arrivals or an already established suffix.
        if(incoming.length*spacing<=perimeter&&
          !ownedGroups.some(g=>g.targetKey===a.targetKey))return undefined;
        ownedBaseline=attachSharedReferenceBaseline({
          edges:logicalEdges([...routes,{segments:[],head:[],kind:"pending"}]),objects,
          obstacles:[...text,...localEndpoints,...turns,
            ...edges.slice(index+1).map(e=>sourceDotBounds(e.attachment.source)),
            ...future.flatMap(r=>r.segments.map(s=>expand(bounds(s),SHAFT_CLEARANCE+(r.width??1)/2)))],
          optimize:false,
        },index);
        return ownedBaseline?.routes[index];
      };
      // Once declared, an owned suffix is protected from every later reference.
      const sharedObstacles=ownedGroups.flatMap(g=>g.physicalPieces.map(p=>
        expand(bounds(p.segment),SHAFT_CLEARANCE+Math.max(...p.members.map(i=>edges[i].attachment.width))/2)));
      const obstacles=[...text,...dots,...localEndpoints,...turns,...sharedObstacles];
      const route=dotHits.length?undefined:a.parent
        ?routeFrameParent(a,obstacles,objects,heads,[...routes,...future])
        :routeReference(a,obstacles,objects,heads,[...routes,...future],false,ownedFallback);
      if(!route) {
        const edgeIndex=edge.originalIndex;
        if(!dotHits.length&&!reserveTurns)return {ok:false,constraint:{kind:"reservation-retry",edgeIndex}};
        if(a.parent)return {ok:false,constraint:{kind:"frame-parent",edgeIndex}};
        const sourceCanExit=departureCandidates(a).some(p=>![...text,...dots,...localEndpoints].some(r=>
          intersects([a.source,p],expand(r,1+a.width/2))));
        if(dotHits.length)return {ok:false,constraint:{kind:"covered-source",edgeIndex,sourceCanExit,
          blockerOwners:dotHits.map(h=>scene.textOwners[h.i]).filter(owner=>owner>=0&&owner!==a.sourceOwner)}};
        const incoming=controlled?edges.filter(e=>sameTarget(e,edge)):[];
        const targetCapacity=controlled?incoming.length*Math.max(8,
          SHAFT_CLEARANCE+Math.max(...incoming.map(e=>e.attachment.width)))+20:undefined;
        return {ok:false,constraint:{kind:"no-candidate",edgeIndex,sourceCanExit,targetCapacity}};
      }
      if(ownedBaseline) {
        routes.splice(0,routes.length,...ownedBaseline.routes.slice(0,index));
        ownedGroups=ownedBaseline.groups;
      }
      route.width=a.width;route.target=a.target;route.targetKey=a.targetKey;
      routes.push(route);heads.push(bounds(route.head));
      arrivals.set(a.targetOwner,a.lane+1);
      searchTimings.push({kind:route.kind,ms:performance.now()-started});
    }
    let sharingPlan:SharedReferencePlan|undefined;
    if(controlled) {
      sharingPlan=planSharedReferences({edges:logicalEdges(routes),
        obstacles:[...text,...localEndpoints],objects,optimize:policy==="shared"});
      if(!sharingPlan.baselineValid)throw new Error("Cannot establish an independent or explicitly shared reference baseline: "+
        sharingPlan.diagnostics.map(d=>d.reason).join("; "));
    }
    const finalRoutes=sharingPlan?.routes??routes;
    const connectors=edges.map((edge,i)=>({connectionIndex:edge.connectionIndex,attachment:edge.attachment,route:finalRoutes[i]}));
    const paint=finalRoutes.flatMap(r=>[...r.segments.flat(),...r.head]);
    return {ok:true,plan:{connectors,extent:paint.length?bounds(paint):undefined,searchTimings,sharingPlan,baselineOrdering}};
  }
}
