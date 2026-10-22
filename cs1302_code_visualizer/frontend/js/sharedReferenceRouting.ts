/** Bounded, geometry-only terminal sharing. Logical references never disappear. */
import { SOURCE_RADIUS, arrowHead, type Point } from "./connectorGeometry";
import { SHAFT_CLEARANCE, ShaftClearance } from "./shaftClearance";
import {
  bounds, circleIntersects, clear, clearsSource, clearsTarget, expand, intersects,
  type Attachment, type Rect, type Route, type Segment,
} from "./referenceRouting";

export interface SharedReferenceEdge {
  /** Stable source identity, not its position in the connection collection. */
  key: string;
  attachment: Attachment;
  route: Route;
  /** Null means that the caller cannot establish compatible semantic paint. */
  styleKey: string | null;
  eligible?: boolean;
}

export interface SharedReferenceInput {
  edges: SharedReferenceEdge[];
  /** Raw text and compact-string paint rectangles; source dots are added here. */
  obstacles: Rect[];
  objects: Rect[];
  optimize?: boolean;
}

export interface SharedReferenceGroup {
  id: string;
  kind: "factored" | "spine";
  targetKey: string;
  styleKey: string;
  members: number[];
  segments: Segment[];
  head: Point[];
  branches: { index: number; segments: Segment[] }[];
  /** Upstream spine pieces may belong to fewer members than the terminal head. */
  physicalPieces: { segment: Segment; members: number[] }[];
}

export interface SharedReferenceDiagnostic {
  members: number[];
  reason: string;
}

export interface SharedReferencePlan {
  routes: Route[];
  groups: SharedReferenceGroup[];
  diagnostics: SharedReferenceDiagnostic[];
  baselineValid: boolean;
  accepted: boolean;
  profilesTried: number;
}

const EPS = 1e-7;
const MAX_PROFILES = 24;
// Small cohorts seldom repeat enough validation to repay serialized keys.
const CACHE_COHORT = 8;
const MAX_CACHED_CHECKS = 32768;
const eq = (a: Point, b: Point) => a[0] === b[0] && a[1] === b[1];
const sub = (a: Point, b: Point): Point => [a[0] - b[0], a[1] - b[1]];
const dot = (a: Point, b: Point) => a[0] * b[0] + a[1] * b[1];
const cross = (a: Point, b: Point) => a[0] * b[1] - a[1] * b[0];
const mix = (a: Point, b: Point, t = .5): Point => [a[0] * (1-t) + b[0] * t, a[1] * (1-t) + b[1] * t];
const distance = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const last = <T>(a: T[]) => a[a.length - 1];
const sameSegment = (a: Segment, b: Segment) => a.length === b.length && a.every((p, i) => eq(p, b[i]));
const rear = (head: Point[]): Point => mix(head[1], head[2]);
const inside = (p: Point, r: Rect) => p[0] >= r.left && p[0] <= r.right && p[1] >= r.top && p[1] <= r.bottom;
const overlaps = (a: Rect, b: Rect) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
const route = (segments: Segment[], head: Point[], a: Attachment): Route => ({
  segments, head, kind: "shared", width: a.width, target: a.target, targetKey: a.targetKey,
});

function split(segment: Segment): [Segment, Segment] {
  let layer = segment;
  const left = [layer[0]], right = [last(layer)];
  while (layer.length > 1) {
    layer = layer.slice(1).map((p, i) => mix(layer[i], p));
    left.push(layer[0]); right.unshift(last(layer));
  }
  return [left, right];
}

/** Bounds converge from both sides, so admission does not trust sampled lengths. */
const lengthCache = new WeakMap<Segment, [number, number]>();
const boundsCache = new WeakMap<Segment, Rect>();
function segmentBounds(segment: Segment): Rect {
  let found = boundsCache.get(segment);
  if (!found) { found = bounds(segment); boundsCache.set(segment, found); }
  return found;
}
function separated(a: Segment, b: Segment, margin: number): boolean {
  const x = segmentBounds(a), y = segmentBounds(b);
  return separatedRects(x,y,margin);
}
function separatedRects(x: Rect,y: Rect,margin: number): boolean {
  return x.right+margin < y.left || x.left-margin > y.right ||
    x.bottom+margin < y.top || x.top-margin > y.bottom;
}
function lengthBounds(segment: Segment, depth = 0): [number, number] {
  const cached = depth === 0 ? lengthCache.get(segment) : undefined;
  if (cached) return cached;
  if(!depth&&segment.length===3) {
    const u=sub(segment[1],segment[0]),v=sub(segment[2],segment[1]);
    // An axis-aligned quadratic round corner has equal perpendicular legs.
    // Its exact arc length is r * (1 + asinh(1) / sqrt(2)); use an outward
    // floating-point allowance instead of recursively subdividing identical
    // corner shapes at every proposed join.
    const radius=Math.max(Math.abs(u[0]),Math.abs(u[1]));
    if(radius>0&&((u[0]===0&&v[1]===0&&Math.abs(u[1])===Math.abs(v[0]))||
      (u[1]===0&&v[0]===0&&Math.abs(u[0])===Math.abs(v[1])))) {
      const length=radius*(1+Math.asinh(1)/Math.SQRT2);
      const error=64*Number.EPSILON*Math.max(1,...segment.flat().map(Math.abs));
      const result:[number,number]=[Math.max(0,length-error),length+error];
      lengthCache.set(segment,result);return result;
    }
  }
  const lower = distance(segment[0], last(segment));
  const upper = segment.slice(1).reduce((sum, p, i) => sum + distance(segment[i], p), 0);
  if (upper - lower <= .00001 || depth === 16) {
    const result: [number, number] = [lower, upper];
    if (!depth) lengthCache.set(segment, result);
    return result;
  }
  const [a, b] = split(segment), x = lengthBounds(a, depth+1), y = lengthBounds(b, depth+1);
  const result: [number, number] = [x[0] + y[0], x[1] + y[1]];
  if (!depth) lengthCache.set(segment, result);
  return result;
}

/** Complete logical geometry including the head; bends count control-polygon turns.
 * A rounded orthogonal quadratic counts once. A more complex legacy cubic may
 * count several turns, conservatively admitting only simpler replacement shapes.
 */
const metricsCache = new WeakMap<Route, {length:number; lowerLength:number; bends:number}>();
export function sharedRouteMetrics(r: Route): { length: number; lowerLength: number; bends: number } {
  const cached = metricsCache.get(r);
  if (cached) return cached;
  const lengths = r.segments.map(s => lengthBounds(s));
  const points = r.segments.flatMap((s, i) => i ? s.slice(1) : s);
  let previous: Point | undefined, bends = 0;
  for (let i = 1; i < points.length; i++) {
    const d = sub(points[i], points[i-1]);
    if (!dot(d, d)) continue;
    if (previous && (Math.abs(cross(previous, d)) > EPS || dot(previous, d) < 0)) bends++;
    previous = d;
  }
  const arrow = r.head.length === 3 ? distance(rear(r.head), r.head[0]) : 0;
  const result = {length: lengths.reduce((sum, p) => sum + p[1], arrow),
    lowerLength: lengths.reduce((sum, p) => sum + p[0], arrow), bends};
  metricsCache.set(r,result); return result;
}

/** Bound length change after cancelling congruent rounded corners. The integral
 * of the Bezier derivative difference is bounded by the sum of control-edge
 * differences. This also handles harmless floating-point translation noise
 * without rounding painted geometry or granting an added-detour allowance.
 */
function lengthIncreaseUpper(next:Route,old:Route):number {
  const available=old.segments.filter(s=>s.length>2);
  let increase=next.segments.filter(s=>s.length===2).reduce((sum,s)=>sum+distance(s[0],s[1]),0)-
    old.segments.filter(s=>s.length===2).reduce((sum,s)=>sum+distance(s[0],s[1]),0)+
    distance(rear(next.head),next.head[0])-distance(rear(old.head),old.head[0]);
  for(const candidate of next.segments.filter(s=>s.length>2)) {
    let at=-1,error=Infinity;
    for(let i=0;i<available.length;i++) {
      const baseline=available[i];if(baseline.length!==candidate.length)continue;
      for(const swap of [false,true])for(const x of [-1,1])for(const y of [-1,1]) {
        let difference=0;
        for(let j=1;j<candidate.length;j++) {
          const d=sub(candidate[j],candidate[j-1]),other=sub(baseline[j],baseline[j-1]);
          difference+=distance([x*d[swap?1:0],y*d[swap?0:1]],other);
        }
        if(difference<error){error=difference;at=i;}
      }
    }
    if(at>=0&&error<.00001){increase+=error;available.splice(at,1);}
    else increase+=lengthBounds(candidate)[1];
  }
  return increase-available.reduce((sum,s)=>sum+lengthBounds(s)[0],0);
}

function normalized(segments: Segment[]): Segment[] {
  const result: Segment[] = [];
  for (const segment of segments) {
    if (segment.every(p => eq(p, segment[0]))) continue;
    const p = last(result);
    if (p?.length === 2 && segment.length === 2 && eq(p[1], segment[0]) &&
        cross(sub(p[1], p[0]), sub(segment[1], segment[0])) === 0 &&
        dot(sub(p[1], p[0]), sub(segment[1], segment[0])) > 0) {
      result[result.length-1] = [p[0], segment[1]];
    } else result.push(segment);
  }
  return result;
}

function eligible(edge: SharedReferenceEdge): boolean {
  const a = edge.attachment;
  return edge.eligible !== false && !!edge.key && edge.styleKey !== null &&
    !!a.targetKey && !a.parent && !a.returning &&
    !(a.sourceOwner >= 0 && a.sourceOwner === a.targetOwner);
}

function groupId(input: SharedReferenceInput, members: number[]): string {
  const edge = input.edges[members[0]];
  return JSON.stringify([edge.attachment.targetKey, edge.styleKey, members.map(i => input.edges[i].key).sort()]);
}

function commonSuffix(paths: Segment[][]): Segment[] {
  const out: Segment[] = [];
  for (let offset = 1; offset <= Math.min(...paths.map(p => p.length)); offset++) {
    const pieces = paths.map(p => p[p.length-offset]);
    if (pieces.every(s => sameSegment(s, pieces[0]))) { out.unshift(pieces[0]); continue; }
    if (pieces.every(s => s.length === 2 && eq(s[1], pieces[0][1]))) {
      const v = sub(pieces[0][1], pieces[0][0]);
      if (pieces.every(s => cross(v, sub(s[1], s[0])) === 0 && dot(v, sub(s[1], s[0])) > 0)) {
        const shortest = [...pieces].sort((a, b) => distance(a[0], a[1]) - distance(b[0], b[1]))[0];
        out.unshift(shortest);
      }
    }
    break;
  }
  return out;
}

function prefixTo(segments: Segment[], point: Point): Segment[] | undefined {
  const result: Segment[] = [];
  for (const s of segments) {
    if (eq(s[0], point)) return result;
    if (s.length === 2 && cross(sub(s[1], s[0]), sub(point, s[0])) === 0 &&
        dot(sub(point, s[0]), sub(point, s[1])) <= 0) {
      if (!eq(s[0], point)) result.push([s[0], point]);
      return result;
    }
    result.push(s);
    if (eq(last(s), point)) return result;
  }
  return undefined;
}

interface SuffixChecks {
  paths: Map<string,number>;
  pairs: Map<string,{segments:Segment[];length:number;key:string}>;
}
const suffixChecks=new WeakMap<Rect[],SuffixChecks>();

function factorSuffixes(input: SharedReferenceInput, routes: Route[]): SharedReferenceGroup[] {
  const cohorts = new Map<string, number[]>();
  input.edges.forEach((edge, i) => {
    if (!eligible(edge)) return;
    const key = JSON.stringify([edge.attachment.targetKey, edge.styleKey, edge.attachment.width, routes[i].head]);
    cohorts.set(key, [...(cohorts.get(key) ?? []), i]);
  });
  const groups: SharedReferenceGroup[] = [];
  for (const members of cohorts.values()) {
    if (members.length < 2) continue;
    members.sort((a, b) => input.edges[a].key.localeCompare(input.edges[b].key));
    const paths = members.map(i => normalized(routes[i].segments));
    let cache=members.length>=CACHE_COHORT?suffixChecks.get(input.objects):undefined;
    if(!cache&&members.length>=CACHE_COHORT){cache={paths:new Map(),pairs:new Map()};suffixChecks.set(input.objects,cache);}
    const identities=cache?paths.map(path=>{
      const key=JSON.stringify(path);
      let id=cache!.paths.get(key);
      if(id===undefined){id=cache!.paths.size;cache!.paths.set(key,id);}
      return id;
    }):[];
    // Nested suffixes are still one directed chain: an upstream pair can share
    // before another member joins. Choose the longest existing pair suffix,
    // then declare each member's exact downstream interval on that chain.
    let suffix:Segment[]=[],suffixLength=-Infinity,suffixKey="";
    for(let i=0;i<paths.length;i++)for(let j=i+1;j<paths.length;j++) {
      const pair=`${identities[i]},${identities[j]}`;
      let found=cache?.pairs.get(pair);
      if(!found) {
        const segments=commonSuffix([paths[i],paths[j]]);
        found={segments,length:segments.reduce((n,s)=>n+lengthBounds(s)[1],0),key:JSON.stringify(segments)};
        if(cache&&cache.pairs.size<MAX_CACHED_CHECKS)cache.pairs.set(pair,found);
      }
      const {segments:shared,length,key}=found;
      if(!shared.length)continue;
      if(length<suffixLength)continue;
      if(length>suffixLength||key.localeCompare(suffixKey)<0) {
        suffix=shared;suffixLength=length;suffixKey=key;
      }
    }
    if (!suffix.length) continue;
    const branches = members.map((index, j) => {
      const shared=commonSuffix([paths[j],suffix]);
      return {index,segments:shared.length ? prefixTo(paths[j],shared[0][0])! : []};
    });
    if (branches.some(b => !b.segments?.length)) continue;
    const joins=branches.map(b=>last(last(b.segments)));
    const segments=suffix.flatMap(s=>{
      if(s.length!==2)return [s];
      const vector=sub(s[1],s[0]),length=dot(vector,vector);
      const cuts=[s[0],...joins.filter(p=>!eq(p,s[0])&&!eq(p,s[1])&&
        cross(vector,sub(p,s[0]))===0&&dot(sub(p,s[0]),sub(p,s[1]))<0),s[1]];
      const ordered=[...new Map(cuts.map(p=>[String(p),p])).values()]
        .sort((a,b)=>dot(sub(a,b),vector)/length);
      return ordered.slice(1).map((p,i)=>[ordered[i],p]);
    });
    const at=joins.map(p=>segments.findIndex(s=>eq(s[0],p)));
    if(at.some(i=>i<0))continue;
    const first = input.edges[members[0]];
    groups.push({id: groupId(input, members), kind: "factored", targetKey: first.attachment.targetKey!,
      styleKey: first.styleKey!, members, segments, head: routes[members[0]].head, branches,
      physicalPieces: segments.map((segment,i) => ({segment,members:members.filter((_,j)=>at[j]<=i)}))});
    for (const [j,b] of branches.entries()) routes[b.index] = route([...b.segments, ...segments.slice(at[j])],
      routes[b.index].head, input.edges[b.index].attachment);
  }
  return groups;
}

interface FlatLine { a: Point; b: Point; error: number }
const flatCache = new WeakMap<Segment, FlatLine[]>();
function pointLineDistance(p: Point, a: Point, b: Point): number {
  const d = sub(b, a), n = dot(d, d);
  return distance(p, mix(a, b, n ? Math.max(0, Math.min(1, dot(sub(p, a), d)/n)) : 0));
}
function flat(segment: Segment): FlatLine[] {
  let found = flatCache.get(segment);
  if (found) return found;
  found = [];
  const visit = (s: Segment, depth: number) => {
    const a = s[0], b = last(s), error = Math.max(0, ...s.slice(1, -1).map(p => pointLineDistance(p, a, b)));
    if (error <= .02 || depth === 16) {
      if (!eq(a, b)) found!.push({a, b, error});
    } else { const [left, right] = split(s); visit(left, depth+1); visit(right, depth+1); }
  };
  visit(segment, 0); flatCache.set(segment, found); return found;
}

function intersection(a: FlatLine, b: FlatLine): Point | undefined {
  const u = sub(a.b, a.a), v = sub(b.b, b.a), d = cross(u, v), w = sub(b.a, a.a);
  if (Math.abs(d) < EPS) return undefined;
  const t = cross(w, v)/d, q = cross(w, u)/d;
  return t >= -EPS && t <= 1+EPS && q >= -EPS && q <= 1+EPS ? mix(a.a, a.b, t) : undefined;
}

function lineDistance(a: FlatLine, b: FlatLine): number {
  if (intersection(a, b)) return 0;
  return Math.min(pointLineDistance(a.a, b.a, b.b), pointLineDistance(a.b, b.a, b.b),
    pointLineDistance(b.a, a.a, a.b), pointLineDistance(b.b, a.a, a.b));
}

function near(a: Segment, b: Segment, clearance: number): boolean {
  if (separated(a,b,clearance)) return false;
  return flat(a).some(x => flat(b).some(y => lineDistance(x, y) < clearance+x.error+y.error-EPS));
}

/** Count isolated crossings with conservative uncertainty for curved pieces.
 * Straight intersections are exact. For a curved chord pair, opposite-side
 * endpoints outside both error strips prove a transverse crossing. An uncertain
 * contact spends candidate crossing budget but grants no baseline budget.
 */
function crossingBounds(a: Route, b: Route): {definite:number; possible:number} {
  const events:{point:Point; definite:boolean}[]=[];
  const possible=new Set<string>();let uncertain=false;
  const add=(point:Point,definite:boolean)=>{
    possible.add(String(point));uncertain ||= !definite;
    const previous=events.find(e=>distance(e.point,point)<.1);
    if(previous)previous.definite ||= definite;
    else events.push({point,definite});
  };
  for(const s of a.segments)for(const t of b.segments) {
    if(separated(s,t,.04))continue;
    for(const x of flat(s))for(const y of flat(t)) {
      const error=x.error+y.error,p=intersection(x,y);
      if(p) {
        const u=sub(x.b,x.a),v=sub(y.b,y.a);
        const side=(point:Point,line:FlatLine,vector:Point)=>cross(vector,sub(point,line.a))/Math.hypot(...vector);
        const xa=side(x.a,y,v),xb=side(x.b,y,v),ya=side(y.a,x,u),yb=side(y.b,x,u);
        const definite=error===0 || xa*xb<0&&ya*yb<0&&Math.min(Math.abs(xa),Math.abs(xb),Math.abs(ya),Math.abs(yb))>error;
        add(p,definite);
      } else if(error>0&&lineDistance(x,y)<=error+EPS) {
        add(x.a,false);
      }
    }
  }
  return {definite:events.filter(e=>e.definite).length,possible:uncertain?Infinity:possible.size};
}

/** Clip only a declared join's small neighborhood, retaining curve error bounds. */
function outside(line: FlatLine, rect: Rect): FlatLine[] {
  const d = sub(line.b, line.a), cuts = [0, 1];
  for (const [axis, values] of [[0, [rect.left, rect.right]], [1, [rect.top, rect.bottom]]] as [number, number[]][]) {
    if (d[axis]) for (const value of values) {
      const t = (value-line.a[axis])/d[axis]; if (t > 0 && t < 1) cuts.push(t);
    }
  }
  cuts.sort((a, b) => a-b);
  return cuts.slice(1).flatMap((t, i) => inside(mix(line.a, line.b, (cuts[i]+t)/2), rect) ? [] :
    [{a: mix(line.a, line.b, cuts[i]), b: mix(line.a, line.b, t), error: line.error}]);
}

interface Piece { segment: Segment; members: number[]; width: number; group?: SharedReferenceGroup; shared: boolean }
function pieces(input: SharedReferenceInput, routes: Route[], groups: SharedReferenceGroup[]): Piece[] {
  const grouped = new Set(groups.flatMap(g => g.members));
  const out: Piece[] = [];
  routes.forEach((r, i) => {
    if (!grouped.has(i)) for (const segment of r.segments) out.push({segment, members: [i], width: input.edges[i].attachment.width, shared: false});
  });
  for (const group of groups) {
    for (const b of group.branches) for (const segment of b.segments) out.push({segment, members: [b.index],
      width: input.edges[b.index].attachment.width, group, shared: false});
    for (const p of group.physicalPieces) out.push({...p,
      width: Math.max(...p.members.map(i => input.edges[i].attachment.width)), group, shared: true});
  }
  return out;
}

function exitSide(r: Route): string {
  const p = r.segments[0][0];
  // Only the first nonzero control step defines departure. Long owned suffixes
  // must not be flattened again by every comparison in candidate sorting.
  for(const segment of r.segments)for(const q of segment) {
    if(eq(p,q))continue;
    const dx=q[0]-p[0],dy=q[1]-p[1];
    return Math.abs(dx)>=Math.abs(dy)?(dx>0?"right":"left"):(dy>0?"bottom":"top");
  }
  return "none";
}

function edgeError(input: SharedReferenceInput, r: Route, index: number): string | undefined {
  const a = input.edges[index].attachment;
  if (!r.segments.length || r.head.length !== 3 ||
      !r.segments.every(s => s.length >= 2 && s.length <= 4 && s.every(p => p.every(Number.isFinite))) ||
      !r.head.every(p => p.every(Number.isFinite))) return "invalid route geometry";
  if (!eq(r.segments[0][0], a.source) || !eq(last(last(r.segments)), rear(r.head)) ||
      r.segments.some((s, i) => i > 0 && !eq(last(r.segments[i-1]), s[0]))) return "discontinuous logical route";
  const dots = input.edges.flatMap((other, j) => j === index ? [] : [expand(bounds([other.attachment.source]), SOURCE_RADIUS+1)]);
  if (!clear(r, [...input.obstacles, ...dots].map(o => expand(o, 1)), a.width)) return "text or source-dot clearance";
  if (input.obstacles.some(o => circleIntersects(a.source, SOURCE_RADIUS, expand(o, 1)))) return "source dot intersects protected paint";
  if (!a.parent && !clearsSource(r, a.sourceBox, a.width)) return "source departure or re-entry";
  if (!clearsTarget(r, a)) return "target boundary or premature target passage";
  if (a.parent && r.segments.some(s => intersects(s, a.sourceBox))) return "frame-parent source interior";
  return undefined;
}

function simplePathError(full: Segment[]): string|undefined {
  // Coordinate-monotone Beziers cannot revisit an earlier point: each
  // control-polygon step has the same sign on each axis. Distinct segment
  // endpoints were checked above. This proves simplicity without comparing
  // every flattened interval of every member of a long shared suffix.
  const directions=[0,0];
  const monotone=full.every(segment=>segment.slice(1).every((p,i)=>p.every((v,axis)=>{
    const sign=Math.sign(v-segment[i][axis]);
    if(sign&&directions[axis]&&sign!==directions[axis])return false;
    directions[axis] ||= sign;
    return true;
  })));
  const lines=monotone?[]:full.flatMap(flat);
  const boxes=lines.map(line=>bounds([line.a,line.b]));
  for(let i=0;i<lines.length;i++)for(let j=i+1;j<lines.length;j++) {
    if(j===i+1) {
      const u=sub(lines[i].b,lines[i].a),v=sub(lines[j].b,lines[j].a);
      if(Math.abs(cross(u,v))<=EPS&&dot(u,v)<0)return "member reverses along a directed interval";
    } else if(!separatedRects(boxes[i],boxes[j],lines[i].error+lines[j].error+EPS)&&
      lineDistance(lines[i],lines[j])<=lines[i].error+lines[j].error+EPS) {
      return "member has a self-intersection or repeated interval";
    }
  }
  return undefined;
}

const simplicityChecks=new WeakMap<Rect[],Map<string,string|null>>();
function checkedSimplicity(input: SharedReferenceInput,full: Segment[]): string|undefined {
  let cache=simplicityChecks.get(input.objects);
  if(!cache){cache=new Map();simplicityChecks.set(input.objects,cache);}
  // Factoring inserts collinear join vertices without changing an existing
  // member's path. Normalize only the cache key, never the painted geometry.
  const key=JSON.stringify(normalized(full));
  const previous=cache.get(key);
  if(previous!==undefined)return previous??undefined;
  const result=simplePathError(full);
  if(cache.size<MAX_CACHED_CHECKS)cache.set(key,result??null);
  return result;
}

function groupError(input: SharedReferenceInput, routes: Route[], group: SharedReferenceGroup): string | undefined {
  if (group.members.length < 2 || new Set(group.members).size !== group.members.length ||
      group.members.some(i => !Number.isInteger(i) || !input.edges[i]) ||
      group.branches.length !== group.members.length || !group.segments.length) return "invalid shared membership";
  if (group.id !== groupId(input, group.members)) return "unstable shared identity";
  const first = input.edges[group.members[0]];
  if (group.members.some(i => !input.edges[i] || !eligible(input.edges[i]) ||
      input.edges[i].attachment.targetKey !== group.targetKey || input.edges[i].styleKey !== group.styleKey ||
      input.edges[i].attachment.width !== first.attachment.width ||
      JSON.stringify(input.edges[i].attachment.target) !== JSON.stringify(first.attachment.target))) return "incompatible shared identity or style";
  if (group.physicalPieces.length !== group.segments.length ||
      group.physicalPieces.some((p, i) => !sameSegment(p.segment, group.segments[i]) || !p.members.length ||
        new Set(p.members).size !== p.members.length || p.members.some(m => !group.members.includes(m)))) return "unowned shared segment";
  const ownership = group.physicalPieces.map(() => [] as number[]);
  for (const member of group.members) {
    const branch = group.branches.find(b => b.index === member);
    if (!branch?.segments.length) return "missing private source branch";
    const join = last(last(branch.segments));
    if (input.objects.some(o => inside(join, expand(o, first.attachment.width/2))) ||
        input.edges.some(e => inside(join, expand(e.attachment.sourceBox, e.attachment.width/2)))) return "join inside a source or object body";
    const at = group.segments.findIndex(s => eq(s[0], join));
    if (at < 0) return "branch does not join canonical suffix";
    const full = [...branch.segments, ...group.segments.slice(at)];
    if (full.length !== routes[member].segments.length ||
        !full.every((s, i) => sameSegment(s, routes[member].segments[i])) ||
        !sameSegment(group.head, routes[member].head)) return "logical path disagrees with shared paint";
    const nodes=full.map(s=>String(s[0]));nodes.push(String(last(last(full))));
    if(new Set(nodes).size!==nodes.length)return "member has a directed cycle";
    const simplicity=group.members.length>=CACHE_COHORT?checkedSimplicity(input,full):simplePathError(full);
    if(simplicity)return simplicity;
    for (let i = at; i < ownership.length; i++) ownership[i].push(member);
  }
  if (ownership.some((members, i) => members.length !== group.physicalPieces[i].members.length ||
      members.some(m => !group.physicalPieces[i].members.includes(m)))) return "incorrect suffix ownership";
  // A directed chain is deliberate: no candidate tree, split, reversal, or cycle.
  if (group.segments.some((s, i) => i && !eq(last(group.segments[i-1]), s[0]))) return "discontinuous physical suffix";
  const nodes = group.segments.map(s => String(s[0]));
  nodes.push(String(last(last(group.segments))));
  if (new Set(nodes).size !== nodes.length) return "shared physical cycle";
  return undefined;
}

function pairError(a: Piece, b: Piece): string | undefined {
  const sameGroup = a.group && a.group === b.group;
  const ownRoute = a.members.length === 1 && b.members.length === 1 && a.members[0] === b.members[0];
  if (!sameGroup && ownRoute) return undefined;
  // Control-polygon bounds enclose each entire Bezier. Distant pairs cannot
  // interact, so avoid flattening and occupied-route construction for them.
  if (separated(a.segment,b.segment,SHAFT_CLEARANCE+(a.width+b.width)/2)) return undefined;
  const starts = [a.segment[0], last(a.segment)], ends = [b.segment[0], last(b.segment)];
  const joins = starts.filter(p => ends.some(q => eq(p, q)));
  if (sameGroup) {
    // Undeclared interior intersections remain forbidden even near a real join.
    for (const x of flat(a.segment)) for (const y of flat(b.segment)) {
      const u=sub(x.b,x.a),v=sub(y.b,y.a),w=sub(y.a,x.a);
      // Clipping a join neighborhood must never conceal an interval traversed
      // twice, particularly a short reversal ending at that declared join.
      if(Math.abs(cross(u,v))<=EPS&&Math.abs(cross(u,w))<=EPS) {
        const length=dot(u,u),p=dot(w,u)/length,q=dot(sub(y.b,x.a),u)/length;
        if(Math.min(1,Math.max(p,q))-Math.max(0,Math.min(p,q))>EPS)
          return "undeclared directed interval overlap inside a group";
      }
      const p = intersection(x, y);
      if (p && !joins.some(j => distance(j, p) <= x.error+y.error+EPS)) return "undeclared intersection inside a group";
    }
    const clearance = SHAFT_CLEARANCE + (a.width+b.width)/2;
    const cut = (s: Segment) => flat(s).flatMap(line => {
      let remains = [line];
      for (const join of joins) remains = remains.flatMap(l => outside(l, expand(bounds([join]), clearance+.5+l.error)));
      return remains;
    });
    const left = cut(a.segment), right = cut(b.segment);
    for (const x of left) for (const y of right) {
      const u = sub(x.b, x.a), v = sub(y.b, y.a);
      if (dot(u,v)**2 >= .75*dot(u,u)*dot(v,v) &&
          lineDistance(x,y) < clearance+x.error+y.error-EPS) return "undeclared parallel overlap inside a group";
    }
    return undefined;
  }
  if ((a.shared || b.shared) && near(a.segment, b.segment, SHAFT_CLEARANCE+(a.width+b.width)/2)) {
    return "unrelated route crosses or approaches shared suffix";
  }
  const occupied: Route = {segments: [b.segment], head: [], kind: "physical", width: b.width};
  if (!new ShaftClearance([occupied], {left:0, top:0, right:0, bottom:0}, a.width, undefined, true)
    .clearSegment(a.segment)) return "undeclared parallel overlap";
  return undefined;
}

// Owned-baseline construction repeatedly validates an unchanged partial scene
// as a new source joins. Reuse only the geometry-dependent pair predicate;
// membership, identities, complete logical paths and obstacles are still checked
// on every call. The scene's measured object array bounds the cache lifetime.
interface PairChecks {
  segments: WeakMap<Segment,number>;
  identities: Map<string,number>;
  results: Map<string,string|null>;
}
const pairChecks=new WeakMap<Rect[],PairChecks>();
function segmentIdentity(cache:PairChecks,segment:Segment):number {
  let id=cache.segments.get(segment);
  if(id===undefined) {
    const key=JSON.stringify(segment);
    id=cache.identities.get(key);
    if(id===undefined){id=cache.identities.size;cache.identities.set(key,id);}
    cache.segments.set(segment,id);
  }
  return id;
}
function checkedPair(input: SharedReferenceInput,a: Piece,b: Piece): string|undefined {
  const sameGroup=!!a.group&&a.group===b.group;
  if(!sameGroup&&a.members.length===1&&b.members.length===1&&a.members[0]===b.members[0])return undefined;
  if(separated(a.segment,b.segment,SHAFT_CLEARANCE+(a.width+b.width)/2))return undefined;
  let cache=pairChecks.get(input.objects);
  if(!cache) {
    cache={segments:new WeakMap(),identities:new Map(),results:new Map()};
    pairChecks.set(input.objects,cache);
  }
  const roles=(sameGroup?1:0)|(a.shared?2:0)|(b.shared?4:0);
  const key=`${segmentIdentity(cache,a.segment)},${segmentIdentity(cache,b.segment)},${a.width},${b.width},${roles}`;
  const previous=cache.results.get(key);
  if(previous!==undefined)return previous??undefined;
  const result=pairError(a,b);
  if(cache.results.size<MAX_CACHED_CHECKS)cache.results.set(key,result??null);
  return result;
}

/** Validates geometry and ownership, never trusting declared member labels alone. */
export function validateSharedReferencePlan(input: SharedReferenceInput, routes: Route[], groups: SharedReferenceGroup[]): string[] {
  const errors: string[] = [];
  if (routes.length !== input.edges.length) return ["logical reference count changed"];
  if (new Set(input.edges.map(e => e.key)).size !== input.edges.length) return ["duplicate source identity"];
  for (let i = 0; i < routes.length; i++) {
    const error = edgeError(input, routes[i], i);
    if (error) return [`${input.edges[i].key}: ${error}`];
  }
  if (new Set(groups.flatMap(g => g.members)).size !== groups.reduce((n, g) => n+g.members.length, 0)) return ["reference belongs to multiple groups"];
  for (const group of groups) {
    const error = groupError(input, routes, group);
    if (error) return [error];
  }
  const painted = pieces(input, routes, groups);
  const reuse=groups.some(g=>g.members.length>=CACHE_COHORT);
  for (let i = 0; i < painted.length; i++) for (let j = i+1; j < painted.length; j++) {
    const error = reuse?checkedPair(input,painted[i], painted[j]):pairError(painted[i],painted[j]);
    if (error) return [error];
  }
  const grouped = new Set(groups.flatMap(g => g.members));
  const heads = [...groups.map(g => ({head:g.head, members:g.members})),
    ...routes.flatMap((r,i) => grouped.has(i) ? [] : [{head:r.head, members:[i]}])];
  for (let i = 0; i < heads.length; i++) {
    const hb = expand(bounds(heads[i].head), 2);
    for (let j = i+1; j < heads.length; j++) if (overlaps(hb, bounds(heads[j].head))) return ["unowned or overlapping arrival heads"];
    for (const p of painted) if (!p.members.some(m => heads[i].members.includes(m)) &&
        intersects(p.segment, expand(hb, p.width/2))) return ["arrival head intersects unrelated shaft"];
  }
  return errors;
}

function terminalNormal(r: Route): Point | undefined {
  if (r.head.length !== 3) return undefined;
  const d = sub(rear(r.head), r.head[0]);
  if (d[0] && !d[1]) return [Math.sign(d[0]), 0];
  if (d[1] && !d[0]) return [0, Math.sign(d[1])];
  return undefined;
}

function sceneBounds(input: SharedReferenceInput, routes: Route[]): Rect {
  const rects = [...input.objects, ...input.obstacles, ...input.edges.map(e => e.attachment.sourceBox)];
  const points: Point[] = rects.flatMap(r => [[r.left,r.top], [r.right,r.bottom]] as Point[]);
  for (const [i, r] of routes.entries()) {
    const b = expand(bounds([...r.segments.flat(), ...r.head]), Math.max(.5, input.edges[i].attachment.width/2));
    points.push([b.left,b.top], [b.right,b.bottom]);
  }
  return bounds(points);
}

function bodyHits(input: SharedReferenceInput, r: Route, index: number): number[] {
  const a = input.edges[index].attachment;
  return input.objects.flatMap((o, i) => i === a.sourceOwner || i === a.targetOwner ? [] :
    r.segments.some(s => intersects(s, o)) ? [i] : []);
}

function makeSpine(input: SharedReferenceInput, members: number[], tip: Point, normal: Point, lane: number): SharedReferenceGroup | undefined {
  const tangent: Point = [-normal[1], normal[0]], vTip = dot(tip,tangent);
  const local = (u: number, v: number): Point => [normal[0]*u+tangent[0]*v, normal[1]*u+tangent[1]*v];
  const first = input.edges[members[0]], h = arrowHead(tip, normal), end = rear(h), uEnd = dot(end,normal);
  if (lane <= uEnd+2) return undefined;
  const direction = Math.sign(vTip-dot(first.attachment.source,tangent));
  if (!direction) return undefined;
  const branches: SharedReferenceGroup["branches"] = [];
  const joins: {index:number; v:number}[] = [];
  for (const index of members) {
    const a = input.edges[index].attachment, u = dot(a.source,normal), v = dot(a.source,tangent);
    if (u <= lane+2 || Math.sign(vTip-v) !== direction) return undefined;
    const radius = Math.min(12, (u-lane)/3, Math.abs(vTip-v)/4);
    if (radius < 1) return undefined;
    const corner = local(lane,v), enter = local(lane+radius,v), join = local(lane,v+direction*radius);
    branches.push({index, segments:[[a.source,enter],[enter,corner,join]]});
    joins.push({index, v:v+direction*radius});
  }
  const closest = Math.min(...joins.map(j => Math.abs(vTip-j.v)));
  const radius = Math.min(12, (lane-uEnd)/2, closest/2);
  if (radius < 1) return undefined;
  joins.sort((a,b) => direction*(a.v-b.v) || input.edges[a.index].key.localeCompare(input.edges[b.index].key));
  const physicalPieces: SharedReferenceGroup["physicalPieces"] = [];
  const joined: number[] = [];
  for (let i = 0; i < joins.length; i++) {
    joined.push(joins[i].index);
    const from = local(lane, joins[i].v), to = local(lane, i+1 < joins.length ? joins[i+1].v : vTip-direction*radius);
    if (!eq(from,to)) physicalPieces.push({segment:[from,to], members:[...joined]});
  }
  const enter = local(lane,vTip-direction*radius), corner = local(lane,vTip), exit = local(lane-radius,vTip);
  physicalPieces.push({segment:[enter,corner,exit], members:[...members]});
  if (!eq(exit,end)) physicalPieces.push({segment:[exit,end], members:[...members]});
  return {id:groupId(input,members), kind:"spine", targetKey:first.attachment.targetKey!, styleKey:first.styleKey!, members,
    head:h, branches, segments:physicalPieces.map(p => p.segment), physicalPieces};
}

/** A straight terminal spine needs no extra bend for ordinary bottom arrivals. */
function makeStraightSpine(input: SharedReferenceInput, members: number[], tip: Point, normal: Point): SharedReferenceGroup | undefined {
  const tangent:Point=[-normal[1],normal[0]], vTip=dot(tip,tangent);
  const local=(u:number,v:number):Point=>[normal[0]*u+tangent[0]*v,normal[1]*u+tangent[1]*v];
  const first=input.edges[members[0]], head=arrowHead(tip,normal), end=rear(head), uEnd=dot(end,normal);
  const branches:SharedReferenceGroup["branches"]=[], joins:{index:number;u:number}[]=[];
  for(const index of members) {
    const a=input.edges[index].attachment,u=dot(a.source,normal),v=dot(a.source,tangent),side=Math.sign(v-vTip);
    const radius=Math.min(12,Math.abs(v-vTip)/3,(u-uEnd)/4);
    if(!side||radius<1)return undefined;
    const enter=local(u,vTip+side*radius),corner=local(u,vTip),join=local(u-radius,vTip);
    branches.push({index,segments:[[a.source,enter],[enter,corner,join]]});
    joins.push({index,u:u-radius});
  }
  joins.sort((a,b)=>b.u-a.u||input.edges[a.index].key.localeCompare(input.edges[b.index].key));
  const physicalPieces:SharedReferenceGroup["physicalPieces"]=[],joined:number[]=[];
  for(let i=0;i<joins.length;i++) {
    joined.push(joins[i].index);
    const from=local(joins[i].u,vTip),to=local(i+1<joins.length?joins[i+1].u:uEnd,vTip);
    if(!eq(from,to))physicalPieces.push({segment:[from,to],members:[...joined]});
  }
  return {id:groupId(input,members),kind:"spine",targetKey:first.attachment.targetKey!,styleKey:first.styleKey!,members,
    head,branches,segments:physicalPieces.map(p=>p.segment),physicalPieces};
}

function routesForGroup(input: SharedReferenceInput, current: Route[], group: SharedReferenceGroup): Route[] {
  const output = [...current];
  for (const branch of group.branches) {
    const join = last(last(branch.segments)), at = group.segments.findIndex(s => eq(s[0],join));
    if (at < 0) continue;
    output[branch.index] = route([...branch.segments,...group.segments.slice(at)],group.head,input.edges[branch.index].attachment);
  }
  return output;
}

function memberAdmissionError(input: SharedReferenceInput, old: Route, next: Route, i: number): string | undefined {
  const before = sharedRouteMetrics(old), after = sharedRouteMetrics(next);
  if (!before.bends && (JSON.stringify(normalized(old.segments)) !== JSON.stringify(normalized(next.segments)) ||
      !sameSegment(old.head,next.head))) return "direct route must retain its geometry";
  if (lengthIncreaseUpper(next,old)>EPS || after.bends > before.bends) return "member length or bends would increase";
  if (exitSide(old) !== exitSide(next)) return "source exit preference would change";
  const oldBodies = bodyHits(input,old,i);
  if (bodyHits(input,next,i).some(o => !oldBodies.includes(o))) return "additional empty-body intersection";
  return undefined;
}

/** A profile yields only maximal contiguous admissible runs, never subsets from
 * a powerset. Removed members retain their independent routes, and whole-scene
 * validation still treats them as foreign obstacles to the resulting spine.
 */
function admissibleRuns(input: SharedReferenceInput, baseline: Route[], group: SharedReferenceGroup): SharedReferenceGroup[] {
  const trial = routesForGroup(input,baseline,group);
  const ordered = [...group.branches].sort((a,b) => {
    const at = (branch: typeof a) => group.segments.findIndex(s => eq(s[0],last(last(branch.segments))));
    return at(a)-at(b) || input.edges[a.index].key.localeCompare(input.edges[b.index].key);
  });
  const runs:number[][] = []; let current:number[] = [];
  for (const {index} of ordered) {
    if (memberAdmissionError(input,baseline[index],trial[index],index) || edgeError(input,trial[index],index)) {
      if (current.length >= 2) runs.push(current); current = [];
    } else current.push(index);
  }
  if (current.length >= 2) runs.push(current);
  return runs.map(run => {
    const members = group.members.filter(i => run.includes(i));
    const physicalPieces = group.physicalPieces.map(p => ({segment:p.segment,members:p.members.filter(i => run.includes(i))}))
      .filter(p => p.members.length);
    return {...group,id:groupId(input,members),members,
      branches:group.branches.filter(b => run.includes(b.index)),physicalPieces,
      segments:physicalPieces.map(p => p.segment)};
  });
}

function proposals(input: SharedReferenceInput, routes: Route[], members: number[]): SharedReferenceGroup[] {
  const first = input.edges[members[0]], t = first.attachment.target, n = terminalNormal(routes[members[0]])!;
  const tangent: Point = [-n[1],n[0]];
  const port = (f: number): Point => n[0] ? [n[0]<0?t.left:t.right,t.top+(t.bottom-t.top)*f] :
    [t.left+(t.right-t.left)*f,n[1]<0?t.top:t.bottom];
  const tips = [...new Map([...members.map(i => routes[i].head[0]), ...[.5,.75,.25,.875,.125].map(port)].map(p => [String(p),p])).values()]
    .sort((a,b) => members.reduce((sum,i) => sum+distance(input.edges[i].attachment.source,a)-distance(input.edges[i].attachment.source,b),0) ||
      a[0]-b[0] || a[1]-b[1]).slice(0,4);
  const result: SharedReferenceGroup[] = [];
  for (const tip of tips) {
    for(const side of [1,-1]) {
      const selected=members.filter(i=>Math.sign(dot(sub(input.edges[i].attachment.source,tip),tangent))===side);
      if(selected.length>=2) {
        const straight=makeStraightSpine(input,selected,tip,n);
        if(straight)result.push(straight);
      }
    }
    for (const direction of [1,-1]) {
    const selected = members.filter(i => Math.sign(dot(sub(tip,input.edges[i].attachment.source),tangent)) === direction);
    if (selected.length < 2) continue;
    const end = rear(arrowHead(tip,n)), outer = Math.min(...selected.map(i => dot(input.edges[i].attachment.source,n)));
    const lanes = selected.flatMap(i => routes[i].segments.filter(s => s.length === 2 && dot(sub(s[1],s[0]),n) === 0)
      .map(s => dot(s[0],n))).filter(u => u > dot(end,n)+2 && u < outer-2);
    const unique = [...new Set(lanes)].sort((a,b) => a-b);
    const possible = [...new Set([unique[Math.floor(unique.length/2)], (dot(end,n)+outer)/2].filter(Number.isFinite))].slice(0,2);
    for (const lane of possible) {
      const group = makeSpine(input,selected,tip,n,lane);
      if (group) result.push(group);
    }
    }
  }
  // Both construction and retained candidate lists are bounded by 24. A
  // rejected proximal/direct member cannot veto a useful farther cohort.
  return result.slice(0,MAX_PROFILES).flatMap(group => admissibleRuns(input,routes,group)).slice(0,MAX_PROFILES);
}

function admissionError(input: SharedReferenceInput, baseline: Route[], candidate: Route[], group: SharedReferenceGroup): string | undefined {
  for (const i of group.members) {
    const reason=memberAdmissionError(input,baseline[i],candidate[i],i);
    if(reason)return reason;
  }
  const oldBounds = sceneBounds(input,baseline), nextBounds = sceneBounds(input,candidate);
  if (nextBounds.left < oldBounds.left-EPS || nextBounds.top < oldBounds.top-EPS ||
      nextBounds.right > oldBounds.right+EPS || nextBounds.bottom > oldBounds.bottom+EPS) return "painted scene bounds would grow";
  const oldInk = group.members.reduce((n,i) => n+baseline[i].segments.reduce((sum,s) => sum+lengthBounds(s)[0],0),0);
  const newInk = [...group.branches.flatMap(b => b.segments),...group.segments].reduce((sum,s) => sum+lengthBounds(s)[1],0);
  if (newInk >= oldInk-EPS || new Set(group.members.map(i => JSON.stringify(baseline[i].head))).size < 2) return "no strict reduction in unique ink and heads";
  // Bound each logical pair: ordinary branch crossings may remain, whereas the
  // physical validator separately forbids every foreign contact on the spine.
  for (const i of group.members) for (let j = 0; j < candidate.length; j++) {
    if (group.members.includes(j)) continue;
    if(crossingBounds(candidate[i],candidate[j]).possible>crossingBounds(baseline[i],baseline[j]).definite)
      return "ordinary crossing count could increase";
  }
  return undefined;
}

/** Atomic optimization; an invalid baseline is reported, never silently painted. */
export function planSharedReferences(input: SharedReferenceInput): SharedReferencePlan {
  const diagnostics: SharedReferenceDiagnostic[] = [];
  const routes = input.edges.map(e => e.route);
  const baseline = [...routes], baseGroups = factorSuffixes(input,baseline);
  const invalid = validateSharedReferencePlan(input,baseline,baseGroups);
  if (invalid.length) return {routes,groups:[],diagnostics:invalid.map(reason => ({members:[],reason:`invalid baseline: ${reason}`})),
    baselineValid:false,accepted:false,profilesTried:0};
  let current = baseline;
  const groups = [...baseGroups], occupied = new Set(groups.flatMap(g => g.members));
  let profilesTried = 0;
  if (input.optimize !== false) {
    const partitions = new Map<string,number[]>();
    input.edges.forEach((edge,i) => {
      const normal = terminalNormal(baseline[i]);
      if (!eligible(edge) || !normal || occupied.has(i) || !sharedRouteMetrics(baseline[i]).bends) return;
      const key = JSON.stringify([edge.attachment.targetKey,edge.styleKey,edge.attachment.width,normal]);
      partitions.set(key,[...(partitions.get(key) ?? []),i]);
    });
    for (const [,members] of [...partitions].sort(([a],[b]) => a.localeCompare(b))) {
      if (members.length < 2) continue;
      members.sort((a,b) => input.edges[a].key.localeCompare(input.edges[b].key));
      const candidates = proposals(input,baseline,members).map(group => {
        const trial = routesForGroup(input,baseline,group);
        const lengths = group.members.map(i => lengthIncreaseUpper(trial[i],baseline[i]));
        const bends = group.members.reduce((n,i) => n+sharedRouteMetrics(trial[i]).bends-sharedRouteMetrics(baseline[i]).bends,0);
        return {group,bends,detour:Math.max(...lengths)};
      }).sort((a,b) => a.bends-b.bends || a.detour-b.detour || b.group.members.length-a.group.members.length ||
        JSON.stringify(a.group.segments).localeCompare(JSON.stringify(b.group.segments)));
      const rejected = new Set<string>();
      for (const {group} of candidates) {
        profilesTried++;
        if (group.members.some(i => occupied.has(i))) continue;
        const trial = routesForGroup(input,current,group);
        const reason = admissionError(input,baseline,trial,group) ?? validateSharedReferencePlan(input,trial,[...groups,group])[0];
        if (reason) {rejected.add(reason);continue;}
        current = trial; groups.push(group); group.members.forEach(i => occupied.add(i));
      }
      if (members.every(i => !occupied.has(i))) diagnostics.push({members,reason:
        rejected.size ? [...rejected].sort().join("; ") : "no compatible monotone spine profile"});
    }
  }
  const finalErrors = current === baseline ? [] : validateSharedReferencePlan(input,current,groups);
  if (finalErrors.length) return {routes:baseline,groups:baseGroups,baselineValid:true,accepted:baseGroups.length>0,profilesTried,
    diagnostics:[...diagnostics,...finalErrors.map(reason => ({members:[],reason:`optimized scene rolled back: ${reason}`}))]};
  return {routes:current,groups,diagnostics,baselineValid:true,accepted:groups.length>0,profilesTried};
}

/** Construct an owned baseline when independent simple arrivals are exhausted.
 * This is deliberately separate from optional optimization: no independent
 * route exists yet for the new edge, so length-improvement admission cannot be
 * claimed. Every prior path keeps its exact painted geometry; only an existing
 * directed suffix can become shared. The caller supplies all future source dots
 * and reserved departures as protected obstacles for this partial scene.
 */
export function attachSharedReferenceBaseline(input: SharedReferenceInput, newIndex: number): SharedReferencePlan | undefined {
  const edge=input.edges[newIndex];
  if(!edge||!eligible(edge))return undefined;
  const source=edge.attachment.source;
  const candidates:{route:Route;key:string;length:number;right:boolean}[]=[];
  for(const [index,other] of input.edges.entries()) {
    if(index===newIndex||!eligible(other)||other.styleKey!==edge.styleKey||
      other.attachment.targetKey!==edge.attachment.targetKey||other.attachment.width!==edge.attachment.width)continue;
    for(const [at,segment] of other.route.segments.entries()) {
      if(segment.length!==2)continue;
      const vector=sub(segment[1],segment[0]),length=Math.hypot(...vector);
      if(length<2||vector[0]&&vector[1])continue;
      const direction:Point=[vector[0]/length,vector[1]/length],normal:Point=[-direction[1],direction[0]];
      const relative=sub(source,segment[0]),along=dot(relative,direction),across=dot(relative,normal);
      const radius=Math.min(12,Math.abs(across)/3,(length-along)/2);
      if(radius<1)continue;
      const local=(u:number,v:number):Point=>[segment[0][0]+direction[0]*u+normal[0]*v,
        segment[0][1]+direction[1]*u+normal[1]*v];
      const enter=local(along,Math.sign(across)*radius),corner=local(along,0),turn=local(along+radius,0);
      const join=local(Math.max(0,along+radius),0);
      const branch:Segment[]=[[source,enter],[enter,corner,turn]];
      if(!eq(turn,join))branch.push([turn,join]);
      const suffix:Segment[]=[...(eq(join,segment[1])?[]:[[join,segment[1]]]),...other.route.segments.slice(at+1)];
      const proposed=route([...branch,...suffix],other.route.head,edge.attachment);
      // Ranking needs length, not bends. Preserve the metric's exact sum order
      // while avoiding a scan of every suffix control edge for every proposal.
      const candidateLength=proposed.segments.reduce((sum,s)=>sum+lengthBounds(s)[1],distance(rear(proposed.head),proposed.head[0]));
      candidates.push({route:proposed,key:JSON.stringify([other.key,at]),length:candidateLength,
        right:exitSide(proposed)==="right"});
    }
  }
  candidates.sort((a,b)=>Number(b.right)-Number(a.right) ||
    a.length-b.length||a.key.localeCompare(b.key));
  let profilesTried=0;
  for(const candidate of candidates.slice(0,MAX_PROFILES)) {
    profilesTried++;
    if(edgeError(input,candidate.route,newIndex))continue;
    const edges=input.edges.map((e,i)=>i===newIndex?{...e,route:candidate.route}:e);
    const planned=planSharedReferences({...input,edges,optimize:false});
    if(planned.baselineValid&&planned.groups.some(g=>g.members.includes(newIndex))) {
      return {...planned,profilesTried,diagnostics:[...planned.diagnostics,
        {members:[newIndex],reason:"constructed baseline with an explicitly owned existing suffix"}]};
    }
  }
  return undefined;
}
