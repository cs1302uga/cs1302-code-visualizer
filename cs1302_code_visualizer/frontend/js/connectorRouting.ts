/** Pure sequential routing over one coherent, measured scene. */
import { SHAFT_CLEARANCE } from "./shaftClearance";
import { SOURCE_RADIUS } from "./connectorGeometry";
import { Attachment, Point, Rect, Route, bounds, circleIntersects, expand, intersects,
  routeReference, routeFrameParent } from "./referenceRouting";

/** IDs and indices bind results outside the solver; none of these facts contain DOM nodes. */
export interface MeasuredConnectorEdge {
  connectionIndex: number;
  sourceId: string;
  targetId: string;
  heapOrigin: boolean;
  attachment: Attachment;
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
  connectors: PlannedConnector[];
  /** Unexpanded control-point/head bounds, matching legacy canvas allocation. */
  extent?: Rect;
  searchTimings: {kind: string; ms: number}[];
}

export type RoutingConstraint =
  | {kind: "reservation-retry"; edgeIndex: number}
  | {kind: "covered-source"; edgeIndex: number; blockerOwners: number[]; sourceCanExit: boolean}
  | {kind: "no-candidate"; edgeIndex: number; sourceCanExit: boolean}
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
  public plan(scene: MeasuredConnectorScene, reserveTurns=false): RoutingResult {
    const {objects,text,localEndpoints,edges}=scene;
    const stack=edges.filter(e=>!e.heapOrigin);
    const heapLeft=Math.min(...objects.filter((_,i)=>scene.heapOwners[i]).map(r=>r.left));
    reserveTurns ||= stack.some(({attachment:a})=>new Set(stack.filter(e=>e.attachment.source[0]===a.source[0])
      .map(e=>e.attachment.targetKey)).size*(SHAFT_CLEARANCE+a.width)>heapLeft-a.sourceBox.right);
    const heads:Rect[]=[],routes:Route[]=[],connectors:PlannedConnector[]=[];
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
      const started=performance.now();
      // Lane assignment is per plan, never a mutation of the supplied measurement.
      const a:Attachment={...edge.attachment,lane:arrivals.get(edge.attachment.targetOwner)??0};
      const dots=edges.filter((_,i)=>i!==index).map(e=>sourceDotBounds(e.attachment.source));
      const dotHits=text.map((r,i)=>({r,i})).filter(({r})=>circleIntersects(a.source,SOURCE_RADIUS,expand(r,1)));
      const future=reservations.slice(index+1).filter((r):r is Route=>!!r);
      const turns=reserveTurns?future.filter(r=>r.targetKey!==a.targetKey).map(r=>r.guard!):[];
      const route=dotHits.length?undefined:(a.parent ? routeFrameParent : routeReference)(a,
        [...text,...dots,...localEndpoints,...turns],objects,heads,[...routes,...future]);
      if(!route) {
        if(!dotHits.length&&!reserveTurns)return {ok:false,constraint:{kind:"reservation-retry",edgeIndex:index}};
        if(a.parent)return {ok:false,constraint:{kind:"frame-parent",edgeIndex:index}};
        const sourceCanExit=departureCandidates(a).some(p=>![...text,...dots,...localEndpoints].some(r=>
          intersects([a.source,p],expand(r,1+a.width/2))));
        return {ok:false,constraint:dotHits.length ? {kind:"covered-source",edgeIndex:index,sourceCanExit,
          blockerOwners:dotHits.map(h=>scene.textOwners[h.i]).filter(owner=>owner>=0&&owner!==a.sourceOwner)} :
          {kind:"no-candidate",edgeIndex:index,sourceCanExit}};
      }
      route.width=a.width;route.target=a.target;route.targetKey=a.targetKey;
      routes.push(route);heads.push(bounds(route.head));
      connectors.push({connectionIndex:edge.connectionIndex,attachment:a,route});
      arrivals.set(a.targetOwner,a.lane!+1);
      searchTimings.push({kind:route.kind,ms:performance.now()-started});
    }
    const paint=routes.flatMap(r=>[...r.segments.flat(),...r.head]);
    return {ok:true,plan:{connectors,extent:paint.length?bounds(paint):undefined,searchTimings}};
  }
}
