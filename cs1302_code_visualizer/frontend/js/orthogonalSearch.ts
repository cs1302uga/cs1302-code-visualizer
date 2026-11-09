/** DOM-free search on an immutable Cartesian grid; geometry stays with the caller. */
export type GridPoint = [number, number];
export interface OrthogonalGrid {
  /** Nonempty, finite, strictly increasing coordinates containing every source/end. */
  readonly x: readonly number[];
  readonly y: readonly number[];
  readonly sources: readonly { readonly point: Readonly<GridPoint>; readonly initialCost: number }[];
  readonly ends: readonly Readonly<GridPoint>[];
  /** Symmetric visibility of adjacent points, fixed for the entire search snapshot. */
  readonly segmentVisible: (from: GridPoint, to: GridPoint) => boolean;
}
export interface SearchOptions {
  /** Default 1; current reference callers must explicitly pass 1.25. */
  heuristicWeight?: number;
  /** Queue removals INCLUDING stale entries; default 5000. Infinity is uncapped. */
  maxPops?: number;
}
export type ExactSearchResult =
  | { status: "found"; points: GridPoint[]; cost: number }
  | { status: "unreachable" };
export type SearchResult = ExactSearchResult | { status: "budget-exhausted" };

/**
 * Current-main A*: row-major point IDs, state = point*3 + (0 initial, 1 H, 2 V).
 * Cost is initial stub length + grid Manhattan length + 18 per axis change.
 * The source stub supplies NO incoming orientation. Terminal stubs, terminal
 * turns, signed directions/reversals, heads and rounded geometry are excluded.
 * Opposite signs on the same axis incur no turn penalty or direction constraint.
 * Callers construct coordinates and perform exact geometry/paint checks afterward.
 * Inputs are trusted internal snapshots: finite nonnegative costs and finite sums.
 * Weight <= 1 with enough budget is admissible on this graph; weighted A* has no
 * optimality promise here, nor does either solver establish global geometric quality.
 */
export function searchOrthogonalGrid(graph: OrthogonalGrid, options: SearchOptions = {}): SearchResult {
  const weight=options.heuristicWeight??1, limit=options.maxPops??5000;
  if(!Number.isFinite(weight)||weight<0||!(limit===Infinity||Number.isSafeInteger(limit)&&limit>=0))
    throw new RangeError("Expected a finite nonnegative weight and nonnegative integer pop budget");
  const {x,y,sources,ends}=graph, nx=x.length, ny=y.length;
  if(!sources.length||!ends.length)return {status:"unreachable"};
  const index=(p:Readonly<GridPoint>)=>y.indexOf(p[1])*nx+x.indexOf(p[0]);
  const point=(i:number):GridPoint=>[x[i%nx],y[Math.floor(i/nx)]];
  const goals=new Set(ends.map(index));
  // Both caches belong only to this immutable geometry/occupancy snapshot.
  const estimates=new Map<number,number>();
  const estimate=(i:number)=>{
    let result=estimates.get(i);
    if(result===undefined){
      const p=point(i);let distance=Infinity;
      for(const q of ends)distance=Math.min(distance,Math.abs(p[0]-q[0])+Math.abs(p[1]-q[1]));
      result=distance*weight;estimates.set(i,result);
    }
    return result;
  };
  const dist=new Map<number,number>(),prev=new Map<number,number>();
  // Preserve current main exactly: lower f, then larger g, then smaller state ID.
  const heap:[number,number,number][]=[];
  const less=(a:number[],b:number[])=>a[0]<b[0]||(a[0]===b[0]&&(a[2]>b[2]||(a[2]===b[2]&&a[1]<b[1])));
  const push=(v:[number,number,number])=>{heap.push(v);let i=heap.length-1;
    while(i){const p=(i-1)>>1;if(!less(v,heap[p]))break;heap[i]=heap[p];i=p;}heap[i]=v;};
  const pop=()=>{const v=heap[0],last=heap.pop()!;if(heap.length){let i=0;
    while(i*2+1<heap.length){let k=i*2+1;if(k+1<heap.length&&less(heap[k+1],heap[k]))k++;
      if(!less(heap[k],last))break;heap[i]=heap[k];i=k;}heap[i]=last;}return v;};
  for(const source of sources){
    const state=index(source.point)*3,cost=source.initialCost;
    // Existing callers supply unique starts. Retain duplicate queue entries, but
    // let the cheapest seed win if a diagnostic graph repeats a source point.
    dist.set(state,Math.min(cost,dist.get(state)??Infinity));
    push([cost+estimate(state/3),state,cost]);
  }
  const visibility=new Map<number,boolean>(); // Never reused across occupancy snapshots.
  let pops=0;
  while(heap.length&&pops<limit){
    pops++;
    const [,state,cost]=pop();if(dist.get(state)!==cost)continue;
    const i=Math.floor(state/3),dir=state%3,p=point(i);
    if(goals.has(i)){
      const points:GridPoint[]=[];
      for(let s=state;;s=prev.get(s)!){points.push(point(Math.floor(s/3)));if(!prev.has(s))break;}
      return {status:"found",points:points.reverse(),cost};
    }
    const col=i%nx,row=Math.floor(i/nx);
    // Left, right, up, down; orientation does not encode the sign of travel.
    for(let neighbor=0;neighbor<4;neighbor++){
      const nd=neighbor<2?1:2;
      const j=neighbor===0?(col>0?i-1:-1):neighbor===1?(col+1<nx?i+1:-1):
        neighbor===2?(row>0?i-nx:-1):(row+1<ny?i+nx:-1);
      if(j<0)continue;
      const q=point(j),key=Math.min(i,j)*2+(nd===2?1:0);
      let open=visibility.get(key);
      if(open===undefined){open=graph.segmentVisible(p,q);visibility.set(key,open);}
      if(!open)continue;
      const next=j*3+nd,ncost=cost+Math.abs(p[0]-q[0])+Math.abs(p[1]-q[1])+(dir&&dir!==nd?18:0);
      if(ncost>=(dist.get(next)??Infinity))continue;
      dist.set(next,ncost);prev.set(next,state);
      push([ncost+estimate(j),next,ncost]);
    }
  }
  return {status:heap.length?"budget-exhausted":"unreachable"};
}

/** Hard diagnostic bound on orientation-state slots, not just spatial points. */
export const ORACLE_MAX_STATES=2048;

/**
 * Independent O(V^2) Dijkstra oracle for SMALL graphs with the identical objective.
 * It materializes visible edges, scans unsettled states, and has no A* heap,
 * heuristic, production relaxation helper, pop cap, or shared visibility cache.
 * Tied optimal paths may differ from A*; compare costs, not their exact point lists.
 * Validation belongs here, outside production's trusted-input hot loop.
 */
export function exactOrthogonalDijkstra(graph: OrthogonalGrid): ExactSearchResult {
  const {x,y,sources,ends}=graph, nx=x.length, count=nx*y.length, states=count*3;
  if(states>ORACLE_MAX_STATES)throw new RangeError(`Oracle limited to ${ORACLE_MAX_STATES} orientation states`);
  for(const coords of [x,y]){
    if(!coords.length||coords.some((v,i)=>!Number.isFinite(v)||(i>0&&v<=coords[i-1])))
      throw new RangeError("Oracle coordinates must be nonempty, finite and strictly increasing");
  }
  const nonnegativeFinite=(cost:number)=>{
    if(!Number.isFinite(cost)||cost<0)throw new RangeError("Oracle requires nonnegative finite costs");
    return cost;
  };
  const vertex=(p:Readonly<GridPoint>)=>{
    const col=x.indexOf(p[0]),row=y.indexOf(p[1]);
    if(col<0||row<0)throw new RangeError("Oracle endpoints must belong to the coordinate grid");
    return row*nx+col;
  };
  const goals=new Set(ends.map(vertex));
  const distance=Array<number>(states).fill(Infinity),previous=Array<number>(states).fill(-1);
  const settled=Array<boolean>(states).fill(false);
  for(const source of sources){
    const state=vertex(source.point)*3,cost=nonnegativeFinite(source.initialCost);
    distance[state]=Math.min(distance[state],cost);
  }
  const points:GridPoint[]=[];
  for(const yy of y)for(const xx of x)points.push([xx,yy]);
  const edges:{to:number;axis:number;length:number}[][]=Array.from({length:count},()=>[]);
  // Enumerate each undirected edge once, independently of production's neighbors.
  for(let a=0;a<count;a++)for(let b=a+1;b<count;b++){
    const sameRow=Math.floor(a/nx)===Math.floor(b/nx),horizontal=sameRow&&b===a+1;
    if(!horizontal&&b!==a+nx)continue;
    if(!graph.segmentVisible(points[a],points[b]))continue;
    const length=nonnegativeFinite(Math.abs(points[b][0]-points[a][0])+Math.abs(points[b][1]-points[a][1]));
    const axis=horizontal?1:2;
    edges[a].push({to:b,axis,length});edges[b].push({to:a,axis,length});
  }
  while(true){
    let state=-1;
    for(let s=0;s<states;s++)if(!settled[s]&&distance[s]<Infinity&&(state<0||distance[s]<distance[state]))state=s;
    if(state<0)return {status:"unreachable"};
    settled[state]=true;
    const at=Math.floor(state/3),incoming=state%3;
    if(goals.has(at)){
      const path:GridPoint[]=[];
      for(let s=state;s>=0;s=previous[s])path.push(points[Math.floor(s/3)]);
      return {status:"found",points:path.reverse(),cost:distance[state]};
    }
    for(const edge of edges[at]){
      const next=edge.to*3+edge.axis;
      const cost=nonnegativeFinite(distance[state]+edge.length+(incoming!==0&&incoming!==edge.axis?18:0));
      if(!settled[next]&&cost<distance[next]){distance[next]=cost;previous[next]=state;}
    }
  }
}
