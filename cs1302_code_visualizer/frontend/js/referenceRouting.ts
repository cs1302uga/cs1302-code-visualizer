/** Geometry-only reference routing. Coordinates are CSS pixels in the connector canvas. */
import { ShaftClearance } from "./shaftClearance";
import { arrowHead as head, Point } from "./connectorGeometry";
export type { Point } from "./connectorGeometry";
export interface Rect { left: number; top: number; right: number; bottom: number }
export type Segment = Point[];
export interface Route { segments: Segment[]; head: Point[]; kind: string; width?: number; target?: Rect; targetKey?: string; guard?: Rect }
export interface Attachment {
  source: Point;
  sourceBox: Rect;
  enclosure: Rect;
  target: Rect;
  targetKey?: string;
  legacyTarget?: Rect;
  sourceOwner: number;
  targetOwner: number;
  returning: boolean;
  width: number;
  lane?: number;
  parent?: { sourceSide: -1 | 1; targetSide: -1 | 1; curviness: number };
}
export const expand = (r: Rect, n: number): Rect =>
  ({ left: r.left-n, top: r.top-n, right: r.right+n, bottom: r.bottom+n });
export function bounds(points: Point[]): Rect {
  let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity;
  for(const p of points) {left=Math.min(left,p[0]);right=Math.max(right,p[0]);top=Math.min(top,p[1]);bottom=Math.max(bottom,p[1]);}
  return {left,top,right,bottom};
}
const overlaps = (a: Rect, b: Rect) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
const inside = (p: Point, r: Rect) => p[0] > r.left && p[0] < r.right && p[1] > r.top && p[1] < r.bottom;
const mix = (a: Point,b: Point,t=.5): Point => [a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t];

/** Exact circle/rectangle interior overlap; the caller supplies text clearance. */
export function circleIntersects(center: Point, radius: number, rect: Rect): boolean {
  const x=Math.max(rect.left,Math.min(center[0],rect.right));
  const y=Math.max(rect.top,Math.min(center[1],rect.bottom));
  return (center[0]-x)**2+(center[1]-y)**2 < radius**2;
}

/** Conservative subdivision: reject uncertain contacts, never miss a narrow crossing. */
export function intersects(segment: Segment, rect: Rect, depth=0): boolean {
  const b = bounds(segment);
  // Include zero-width/height hulls (straight horizontal/vertical segments).
  if (b.right <= rect.left || b.left >= rect.right || b.bottom <= rect.top || b.top >= rect.bottom) return false;
  if (segment.some(p=>inside(p,rect)) && segment.length===2) return true;
  if (segment.length===2) {
    let lo=0, hi=1;
    for(let axis=0;axis<2;axis++) {
      const a=segment[0][axis], d=segment[1][axis]-a;
      const min=axis ? rect.top : rect.left, max=axis ? rect.bottom : rect.right;
      if (!d) { if(a<=min || a>=max) return false; continue; }
      const t1=(min-a)/d,t2=(max-a)/d;
      lo=Math.max(lo,Math.min(t1,t2)); hi=Math.min(hi,Math.max(t1,t2));
      if(lo>=hi) return false;
    }
    return true;
  }
  if(depth>=20 || Math.max(b.right-b.left,b.bottom-b.top)<.01) return true;
  let layer=segment;
  const left=[layer[0]],right=[layer[layer.length-1]];
  while(layer.length>1) {
    layer=layer.slice(1).map((p,i)=>mix(layer[i],p));
    left.push(layer[0]); right.unshift(layer[layer.length-1]);
  }
  return intersects(left,rect,depth+1)||intersects(right,rect,depth+1);
}

export function pathData(route: Route): string {
  const p=route.segments[0][0];
  return `M ${p[0]} ${p[1]}`+route.segments.map(s=>
    ` ${s.length===4 ? "C" : s.length===3 ? "Q" : "L"} `+s.slice(1).map(p=>p.join(" ")).join(" ")).join("");
}
const rear = (h: Point[]) => mix(h[1],h[2]);
export function clear(route: Route, obstacles: Rect[], width: number): boolean {
  const hb=expand(bounds(route.head),.5);
  const hulls=route.segments.map(s=>expand(bounds(s),width/2));
  const extent={...hb};
  for(const h of hulls) {
    extent.left=Math.min(extent.left,h.left);extent.right=Math.max(extent.right,h.right);
    extent.top=Math.min(extent.top,h.top);extent.bottom=Math.max(extent.bottom,h.bottom);
  }
  for(const r of obstacles) {
    if(!overlaps(extent,r))continue;
    if(overlaps(hb,r))return false;
    for(let i=0;i<hulls.length;i++) if(overlaps(hulls[i],r)&&intersects(route.segments[i],expand(r,width/2)))return false;
  }
  return true;
}

/** Keep the initial departure monotone, then forbid source-box re-entry. */
export function clearsSource(route: Route, sourceBox: Rect, width: number): boolean {
  if (sourceBox.right <= sourceBox.left || sourceBox.bottom <= sourceBox.top) return true;
  const start = route.segments[0][0];
  const tangent = route.segments.flat().find(p => p[0] !== start[0] || p[1] !== start[1]);
  if (!tangent) return false;
  const dx = tangent[0] - start[0], dy = tangent[1] - start[1];
  const axis = Math.abs(dx) >= Math.abs(dy) ? 0 : 1;
  const direction = (axis === 0 ? dx : dy) > 0 ? 1 : -1;
  if (axis === 0 && direction < 0) return false;
  const box = expand(sourceBox, width / 2);
  const leftWall = {left: box.left - 1, right: box.left, top: box.top, bottom: box.bottom};
  let departed = false;
  for (const segment of route.segments) {
    if (intersects(segment, leftWall)) return false;
    if (departed) {
      if (intersects(segment, box)) return false;
      continue;
    }
    // Both coordinates must be monotone until departure: otherwise a curve could
    // leave a perpendicular side and return before reaching its chosen exit.
    const crossAxis = 1 - axis;
    const crossDeltas = segment.slice(1).map((p,i) => p[crossAxis] - segment[i][crossAxis]);
    if (crossDeltas.some(d => d < -1e-9) && crossDeltas.some(d => d > 1e-9)) return false;
    // Monotone Bezier control coordinates prove a one-way departure without sampling.
    for (let i = 1; i < segment.length; i++) {
      if (direction * (segment[i][axis] - segment[i - 1][axis]) < -1e-9) return false;
    }
    const end = segment[segment.length - 1];
    if (end[0] >= box.right || end[1] <= box.top || end[1] >= box.bottom) departed = true;
  }
  return departed && !overlaps(expand(bounds(route.head), .5), box);
}

/** A new head must also clear every shaft already routed, including hover width. */
function headClearsRoutes(h: Point[], routes: Route[], width: number): boolean {
  return routes.every(route => route.segments.every(segment =>
    !intersects(segment, expand(bounds(h), 2 + (route.width ?? width) / 2))));
}

/** Only a self-reference's initial departure may occupy the target body. */
export function clearsTarget(route: Route, a: Attachment): boolean {
  const [x,y]=route.head[0], t=a.target;
  const onBoundary = ((x===t.left || x===t.right) && y>=t.top && y<=t.bottom) ||
    ((y===t.top || y===t.bottom) && x>=t.left && x<=t.right);
  if (!onBoundary) return false;
  const target = expand(t, a.width / 2);
  let departing = a.sourceOwner >= 0 && a.sourceOwner === a.targetOwner && inside(a.source, target);
  let departure: Point | undefined;
  for (const segment of route.segments) {
    if (!departing && intersects(segment, target)) return false;
    if (departing) {
      // Departure is straight and monotone until outside the target.
      if (segment.length !== 2) return false;
      const delta:Point=[segment[1][0]-segment[0][0],segment[1][1]-segment[0][1]];
      if (departure && (departure[0]*delta[1] !== departure[1]*delta[0] ||
          departure[0]*delta[0]+departure[1]*delta[1] < 0)) return false;
      if (delta[0] || delta[1]) departure=delta;
      if (!inside(segment[segment.length - 1], target)) departing = false;
    }
  }
  return !departing && !overlaps(bounds(route.head), a.target);
}

/** Rounded polyline with revalidation by the caller, including corner cut-ins. */
function polyline(points: Point[], h: Point[], radius: number): Route {
  const distinct=points.filter((p,i)=>!i||p[0]!==points[i-1][0]||p[1]!==points[i-1][1]);
  const clean=distinct.filter((p,i)=>!i||i===distinct.length-1||
    (p[0]-distinct[i-1][0])*(distinct[i+1][1]-p[1]) !==
    (p[1]-distinct[i-1][1])*(distinct[i+1][0]-p[0]))
    .filter((p,i,all)=>!i||p[0]!==all[i-1][0]||p[1]!==all[i-1][1]);
  const segments: Segment[]=[];
  let current=clean[0];
  for(let i=1;i<clean.length-1;i++) {
    const [a,b,c]=[clean[i-1],clean[i],clean[i+1]];
    const l=Math.hypot(b[0]-a[0],b[1]-a[1]),r=Math.hypot(c[0]-b[0],c[1]-b[1]);
    const size=Math.min(radius,l/2,r/2),enter=mix(b,a,size/l),exit=mix(b,c,size/r);
    segments.push([current,enter]); if(size) segments.push([enter,b,exit]);
    current=exit;
  }
  segments.push([current,clean[clean.length-1]]);
  return {segments,head:h,kind:"visibility"};
}

/** Local orthogonal visibility grid; expands to exterior channels when necessary. */
function search(start: Point,end: Point,obstacles: Rect[],margin: number, shafts: ShaftClearance,
  ports?:{starts:Point[];ends:Point[];source:Point;limit?:number}): Point[]|undefined {
  const starts=ports?.starts??[start],ends=ports?.ends??[end];
  const region=expand(bounds([...starts,...ends]),margin);
  const estimate=(p:Point)=>{
    let distance=Infinity;
    for(const q of ends)distance=Math.min(distance,Math.abs(p[0]-q[0])+Math.abs(p[1]-q[1]));
    return distance*(ports?1.25:1);
  };
  const local=obstacles.filter(r=>overlaps(region,r));
  const xs=[region.left,region.right,...starts.map(p=>p[0]),...ends.map(p=>p[0])],
    ys=[region.top,region.bottom,...starts.map(p=>p[1]),...ends.map(p=>p[1])];
  for(const r of [...local,...shafts.channels.filter(r=>overlaps(region,r))]) { xs.push(Math.max(region.left,r.left),Math.min(region.right,r.right));
    ys.push(Math.max(region.top,r.top),Math.min(region.bottom,r.bottom)); }
  const unique=(v:number[])=>[...new Set(v)].sort((a,b)=>a-b);
  const x=unique(xs),y=unique(ys),nx=x.length,ny=y.length;
  const index=(p:Point)=>y.indexOf(p[1])*nx+x.indexOf(p[0]);
  const goals=new Set(ends.map(index));
  const point=(i:number):Point=>[x[i%nx],y[Math.floor(i/nx)]];
  const dist=new Map<number,number>(),prev=new Map<number,number>();
  // A* ties prefer progress toward the goal, then stable state ID.
  // This avoids exploring every equal-cost cell in long, open channels.
  const heap: [number,number,number][]=[];
  const less=(a:number[],b:number[])=>a[0]<b[0]||(a[0]===b[0]&&(a[2]>b[2]||(a[2]===b[2]&&a[1]<b[1])));
  const push=(v:[number,number,number])=>{ heap.push(v); let i=heap.length-1;
    while(i) {const p=(i-1)>>1;if(!less(v,heap[p]))break;heap[i]=heap[p];i=p;} heap[i]=v; };
  const pop=()=>{const v=heap[0],last=heap.pop()!; if(heap.length){let i=0;
    while(i*2+1<heap.length){let k=i*2+1;if(k+1<heap.length&&less(heap[k+1],heap[k]))k++;
      if(!less(heap[k],last))break;heap[i]=heap[k];i=k;}heap[i]=last;}return v;};
  for(const p of starts) {
    const state=index(p)*3,cost=ports?Math.abs(p[0]-ports.source[0])+Math.abs(p[1]-ports.source[1]):0;
    dist.set(state,cost);push([cost+estimate(p),state,cost]);
  }
  const visibility=new Map<string,boolean>();
  // Bound each candidate search; exhaustion tries another port or exterior route.
  let visited=0;
  while(heap.length && visited++<(ports?.limit??(ports?200000:5000))) {
    const [,state,cost]=pop(); if(dist.get(state)!==cost)continue;
    const i=Math.floor(state/3),dir=state%3,p=point(i);
    if(goals.has(i)){const result:Point[]=[];let s=state;while(true){result.push(point(Math.floor(s/3)));
      if(!prev.has(s))break;s=prev.get(s)!;}return result.reverse();}
    const col=i%nx,row=Math.floor(i/nx);
    for(const [j,nd] of [[col>0?i-1:-1,1],[col+1<nx?i+1:-1,1],[row>0?i-nx:-1,2],[row+1<ny?i+nx:-1,2]]) {
      if(j<0)continue;
      const q=point(j),key=`${Math.min(i,j)}:${Math.max(i,j)}`;
      let open=visibility.get(key);
      if(open===undefined){open=!local.some(r=>intersects([p,q],r))&&shafts.clearSegment([p,q]);visibility.set(key,open);}
      if(!open)continue;
      const next=j*3+nd,ncost=cost+Math.abs(p[0]-q[0])+Math.abs(p[1]-q[1])+(dir&&dir!==nd?18:0);
      if(ncost>=(dist.get(next)??Infinity))continue;
      dist.set(next,ncost);prev.set(next,state);
      push([ncost+estimate(q),next,ncost]);
    }
  }
}

/** Frame-parent links attach to frame boundaries, not reference value boxes. */
export function routeFrameParent(a: Attachment, text: Rect[], objects: Rect[], occupiedHeads: Rect[], occupiedRoutes: Route[] = []): Route | undefined {
  const shafts=new ShaftClearance(occupiedRoutes,a.target,a.width,a.targetKey);
  const {sourceSide, targetSide, curviness} = a.parent!;
  const s = a.source, t = a.target;
  const protectedRects = [...text.map(r => expand(r, 1)), ...occupiedHeads.map(r => expand(r, 2))];
  const frames = [a.sourceBox, t];
  const unrelated = objects.filter((r, i) => i !== a.sourceOwner && i !== a.targetOwner && r.right > r.left);
  const valid = (route: Route, obstacles: Rect[]) => clear(route, obstacles, a.width) &&
    headClearsRoutes(route.head, occupiedRoutes, a.width) && shafts.clear(route) &&
    // The boundary attachment is allowed; crossing either frame's contents is not.
    frames.every(frame => !overlaps(bounds(route.head), frame) &&
      route.segments.every(segment => !intersects(segment, frame)));
  for (const obstacles of [[...protectedRects, ...unrelated.map(r => expand(r, 8))], protectedRects]) {
    for (const fraction of [.5, .75, .25, .875, .125]) {
      const tip: Point = [targetSide < 0 ? t.left : t.right, t.top + (t.bottom - t.top) * fraction];
      const h = head(tip, [targetSide, 0]), end = rear(h);
      if (!headClearsRoutes(h, occupiedRoutes, a.width)) continue;
      const original: Route = {kind: "parent", head: h, segments: [
        [s, [s[0] + sourceSide * curviness, s[1]], [end[0] + targetSide * curviness, end[1]], end],
      ]};
      const channel = sourceSide < 0 ? Math.min(s[0], end[0]) - 20 : Math.max(s[0], end[0]) + 20;
      for (const radius of [12,0]) {
        const simple=polyline([s,[channel,s[1]],[channel,end[1]],end],h,radius);
        if ((channel-end[0])*targetSide > 0 && valid(simple,obstacles)) return simple;
      }
      if (valid(original, obstacles)) return original;
      const depart: Point = [s[0] + sourceSide * 12, s[1]];
      const approach: Point = [end[0] + targetSide * 12, end[1]];
      const searchObstacles = [...obstacles.map(r => expand(r, a.width / 2 + 2)), ...frames];
      const extent = bounds(searchObstacles.flatMap(r => [[r.left, r.top], [r.right, r.bottom]]));
      const exterior = Math.max(128, approach[0] - extent.left, extent.right - approach[0],
        approach[1] - extent.top, extent.bottom - approach[1]) + 32;
      for (const margin of [...new Set([32, 128, exterior])]) {
        const points = search(depart, approach, searchObstacles, margin, shafts);
        if (!points) continue;
        for (const radius of [12, 6, 0]) {
          const route = polyline([s, ...points, end], h, radius);
          if (valid(route, obstacles)) return route;
        }
      }
    }
  }
  return undefined;
}

export function routeReference(a: Attachment,text: Rect[],objects: Rect[],occupiedHeads: Rect[], occupiedRoutes: Route[] = [], shareAliasHeads=false): Route|undefined {
  const shafts=new ShaftClearance(occupiedRoutes,a.target,a.width,a.targetKey);
  const aliases=occupiedRoutes.filter(r=>a.targetKey!==undefined&&r.targetKey===a.targetKey);
  if(shareAliasHeads) {
    occupiedHeads=occupiedHeads.filter(h=>!aliases.some(r=>{
      const b=bounds(r.head);return b.left===h.left&&b.right===h.right&&b.top===h.top&&b.bottom===h.bottom;
    }));
    occupiedRoutes=occupiedRoutes.filter(r=>!aliases.includes(r));
  }
  const s=a.source,t=a.target,exit:Point=[Math.max(s[0],a.enclosure.right-4),s[1]];
  const protectedRects=[...text.map(r=>expand(r,1)),...occupiedHeads.map(r=>expand(r,2))];
  const unrelated=objects.filter((r,i)=>i!==a.sourceOwner&&i!==a.targetOwner&&r.right>r.left&&r.bottom>r.top);
  const strict=[...protectedRects,...unrelated.map(r=>expand(r,8))];
  const box=a.enclosure;
  const borders=new ShaftClearance([{segments:[
    [[box.left,box.top],[box.right,box.top]],[[box.left,box.bottom],[box.right,box.bottom]],
    [[box.left,box.top],[box.left,box.bottom]],[[box.right,box.top],[box.right,box.bottom]]],
    head:[],kind:"border",width:1}],a.target,a.width);
  let closeDeparture:Route|undefined;
  // A shallow enclosure has room for a useful exterior departure. In tall
  // containers, a trip around the whole container obscures ordinary field links.
  let preferRoom=box.bottom-box.top<=2*(a.sourceBox.bottom-a.sourceBox.top)+16;
  // Candidate selection is stateful: retain the first safe narrow departure
  // as a fallback while continuing to look for a roomier route.
  const acceptCandidate=(r:Route,obs=protectedRects)=>{
    const roomy=!preferRoom||(clearsSource(r,expand(a.sourceBox,6),a.width)&&borders.clear(r));
    if(!roomy&&closeDeparture)return false;
    if(!clear(r,obs,a.width)||!clearsSource(r,a.sourceBox,a.width)||
      !clearsTarget(r,a)||!headClearsRoutes(r.head,occupiedRoutes,a.width)||!shafts.clear(r))return false;
    if(!roomy) {closeDeparture=r;return false;}
    return true;
  };
  const tips: {tip:Point;normal:Point}[]=[];
  for(const f of [.5,.75,.25,.875,.125]) tips.push(
    {tip:[t.left,t.top+(t.bottom-t.top)*f],normal:[-1,0]},
    {tip:[t.left+(t.right-t.left)*f,t.bottom],normal:[0,1]},
    {tip:[t.right,t.top+(t.bottom-t.top)*f],normal:[1,0]},
    {tip:[t.left+(t.right-t.left)*f,t.top],normal:[0,-1]});
  if (s[0] > t.left + 8 && s[0] < t.right - 8) tips.unshift(
    {tip:[s[0],t.bottom],normal:[0,1]}, {tip:[s[0],t.top],normal:[0,-1]});
  if (s[1] > t.top + 8 && s[1] < t.bottom - 8) tips.unshift(
    {tip:[t.left,s[1]],normal:[-1,0]}, {tip:[t.right,s[1]],normal:[1,0]});
  // Additional ten-pixel ports accommodate many aliases after spacing repair.
  for(let x=t.left+10;x<t.right-5;x+=10) tips.push(
    {tip:[x,t.bottom],normal:[0,1]},{tip:[x,t.top],normal:[0,-1]});
  for(let y=t.top+10;y<t.bottom-5;y+=10) tips.push(
    {tip:[t.left,y],normal:[-1,0]},{tip:[t.right,y],normal:[1,0]});
  // Compare against the shortest clear direct/one-bend route across arrivals.
  // These orthogonal candidates are monotone, so Manhattan distance to the tip
  // is their length before rounding (including the arrowhead).
  const arrivalLength=(tip:Point)=>Math.abs(tip[0]-s[0])+Math.abs(tip[1]-s[1]);
  let simpleRoute:Route|undefined,simpleLength=Infinity;
  for (const {tip,normal} of tips) {
    const length=arrivalLength(tip);
    if(length>=simpleLength)continue;
    const h=head(tip,normal),e=rear(h);
    const corner:Point=normal[0] ? [s[0],e[1]] : [e[0],s[1]];
    const previous=corner[0]===e[0]&&corner[1]===e[1] ? s : corner;
    if((previous[0]-e[0])*normal[0]+(previous[1]-e[1])*normal[1]<0)continue;
    for(const radius of [12,0]) {
      const route=polyline([s,corner,e],h,radius);
      if(acceptCandidate(route,strict)) {simpleRoute=route;simpleLength=length;break;}
    }
  }
  // Keep the existing right-first ordering for narrow departure fallbacks.
  const simpleCloseDeparture=closeDeparture;
  closeDeparture=undefined;
  // Prefer a right exit with at most two bends and no backtracking, allowing
  // at most 24 extra CSS pixels over a clear simple alternative. Merely staying
  // between the source and a chosen arrival would not bound wide-target detours.
  for (const {tip,normal} of tips) {
    if(arrivalLength(tip)>simpleLength+24)continue;
    const h=head(tip,normal),e=rear(h);
    if(e[0]<=a.sourceBox.right || normal[0]>0 || (s[1]-e[1])*normal[1]<0)continue;
    const x=normal[0] ? (a.sourceBox.right+e[0])/2 : e[0];
    const points:Point[]=normal[0] ? [s,[x,s[1]],[x,e[1]],e] : [s,[x,s[1]],e];
    for(const radius of [12,0]) {
      const route=polyline(points,h,radius),first=route.segments[0];
      // Rounding must not turn upward/downward before crossing the right edge.
      if(first[1][0]<a.sourceBox.right+a.width/2 || first[1][1]!==s[1])continue;
      if(acceptCandidate(route,strict))return route;
    }
  }
  if(simpleRoute)return simpleRoute;
  closeDeparture??=simpleCloseDeparture;
  const legacy=a.legacyTarget??t;
  const h=head([legacy.left,(legacy.top+legacy.bottom)/2],[-1,0]),end=rear(h),bend=end[0]>=exit[0]?(end[0]-exit[0])/2:40;
  const original:Route={segments:[[s,exit],[exit,[exit[0]+bend,exit[1]],[end[0]-bend,end[1]],end]],head:h,kind:"original"};
  if(!a.returning&&acceptCandidate(original,strict))return original;
  const outerRight=Math.max(...objects.map(r=>r.right),...text.map(r=>r.right),...shafts.channels.map(r=>r.right))+16;
  // A clear lower exit and exterior lane often solve a border-hugging alias
  // immediately. Try every arrival before spending the dogleg search budget.
  const below:Point=[s[0],Math.max(a.sourceBox.bottom,box.bottom)+12];
  if(preferRoom&&!protectedRects.some(r=>intersects([s,below],expand(r,a.width/2)))&&shafts.clearSegment([s,below])) {
    for(const obs of [strict,protectedRects])for(const {tip,normal} of tips) {
      const h=head(tip,normal),e=rear(h),approach:Point=[e[0]+normal[0]*12,e[1]+normal[1]*12];
      for(const radius of [12,0]) {
        const r=polyline([s,below,[outerRight,below[1]],[outerRight,approach[1]],approach,e],h,radius);
        if(acceptCandidate(r,obs))return r;
      }
    }
  }
  const relevant=objects.filter(r=>r.right>=Math.min(s[0],t.left)&&r.left<=Math.max(s[0],t.right));
  const bottom=Math.max(a.enclosure.bottom,t.bottom,...relevant.map(r=>r.bottom))+(a.lane??0)*12;
  // Fixed-position search first avoids bodies, then permits readable empty-body crossings.
  const deferred:{depart:Point;approach:Point;h:Point[];e:Point;obs:Rect[]}[]=[];
  let cheapAttempts=0;
  const cheap=(r:Route,obs:Rect[])=>++cheapAttempts<=512&&acceptCandidate(r,obs);
  for(const obs of [strict,protectedRects]) {
    if(!a.returning&&acceptCandidate(original,obs))return original;
    for(const {tip,normal} of tips) {
      const h=head(tip,normal),e=rear(h);
      if(occupiedHeads.some(r=>overlaps(expand(bounds(h),2),r))||!headClearsRoutes(h,occupiedRoutes,a.width))continue;
      const approach:Point=[e[0]+normal[0]*12,e[1]+normal[1]*12];
      if(!clear({segments:[[approach,e]],head:h,kind:"arrival"},obs,a.width)||!shafts.clearSegment([approach,e]))continue;
      const exits=[...new Set(shafts.channels.flatMap(r=>[r.left,r.right]))]
        .filter(x=>x>=a.sourceBox.right+12).sort((x,y)=>x-y);
      // A same-target lane may fit between the source box and a different
      // target's shaft. Include it even when it is closer than the usual stub.
      const shared=[...new Set(aliases.flatMap(r=>r.segments.flat().map(p=>Math.round(p[0]*1024)/1024)))]
        .filter(x=>x>a.sourceBox.right+a.width/2).sort((x,y)=>x-y);
      const right=[a.sourceBox.right+12,...shared,...exits.slice(0,24),Math.max(...exits)].filter(Number.isFinite);
      const short=a.width/2+.5;
      const departures:Point[]=[...(preferRoom?[below]:[]),
        ...right.map((x):Point=>[x,s[1]]),[s[0],a.sourceBox.bottom+12],[s[0],a.sourceBox.top-12],
        [s[0],a.sourceBox.bottom+short],[s[0],a.sourceBox.top-short]];
      for(const depart of departures) {
        if(obs.some(r=>intersects([s,depart],expand(r,a.width/2)))||!shafts.clearSegment([s,depart]))continue;
        for(const corner of [[depart[0],approach[1]],[approach[0],depart[1]]] as Point[]) {
          for(const radius of [12,0]) {
            const r=polyline([s,depart,corner,approach,e],h,radius);
            if(acceptCandidate(r,obs))return r;
          }
        }
        if(cheapAttempts>=512){deferred.push({depart,approach,h,e,obs});continue;}
        // Try exterior doglegs before constructing a grid. This is particularly
        // useful for the last link in a long row or a cycle.
        const horizontal=[...new Set(shafts.channels.flatMap(r=>[r.top,r.bottom]))]
          .sort((x,y)=>Math.abs(x-depart[1])+Math.abs(x-approach[1])-Math.abs(y-depart[1])-Math.abs(y-approach[1])||x-y);
        const lanes=[...(preferRoom?[box.bottom+12,box.top-12]:[]),bottom+32,bottom+48,Math.min(a.enclosure.top,t.top)-32,
          ...horizontal.slice(0,8),Math.min(...horizontal),Math.max(...horizontal)].filter(Number.isFinite);
        for(const lane of lanes) {
          const points=[s,depart,[depart[0],lane] as Point,[approach[0],lane] as Point,approach,e];
          for(const radius of [12,0]) {const r=polyline(points,h,radius);if(cheap(r,obs))return r;}
        }
        const channels=[...new Set(shafts.channels.flatMap(r=>[r.left,r.right]))]
          .sort((x,y)=>Math.abs(x-depart[0])+Math.abs(x-approach[0])-Math.abs(y-depart[0])-Math.abs(y-approach[0])||x-y);
        for(const x of [...new Set([...(preferRoom?[box.left-12,box.right+12]:[]),...channels.slice(0,8),Math.min(...channels),Math.max(...channels)])].filter(Number.isFinite)) {
          for(const radius of [12,0]) {
            const r=polyline([s,depart,[x,depart[1]],[x,approach[1]],approach,e],h,radius);
            if(cheap(r,obs))return r;
          }
        }
        deferred.push({depart,approach,h,e,obs});
      }
    }
  }
  // Prefer a visible gap beside source borders, but retain a readable narrow
  // departure when tightly stacked rows leave no room for the wider candidates.
  if(closeDeparture)return closeDeparture;
  preferRoom=false;
  // Broad, tangent-continuous sweeps give visible separation at reduced zoom.
  for(const gap of [32,48,72,104]) for(const f of [.5,.75,.25]) for(const down of a.returning?[true,false]:[false,true]) {
    const tip:Point=[t.left+(t.right-t.left)*f,t.bottom],h=head(tip,[0,1]),e=rear(h);
    const lead=down?s:exit,lane=bottom+gap,j:Point=[(lead[0]+tip[0])/2,lane];
    const handle=Math.abs(tip[0]-lead[0])/(down?4:2),sign=tip[0]>=lead[0]?1:-1;
    const route:Route={head:h,kind:"sweep",segments:[
      ...(!down?[[s,lead]]:[]),
      [lead,down?[lead[0],lane]:[lead[0]+20,lead[1]],[j[0]-sign*handle,j[1]],j],
      [j,[j[0]+sign*handle,j[1]],[tip[0],lane],e]]};
    if(acceptCandidate(route,strict))return route;
    if(!down) {
      const channel=a.enclosure.right+12+(a.lane??0)*8,turn:Point=[channel+12,lane];
      const compact:Route={head:h,kind:"sweep",segments:[[s,[channel,s[1]]],
        [[channel,s[1]],[channel+12,s[1]],[channel,lane],turn],
        [turn,[tip[0],lane],[tip[0],lane],e]]};
      if(acceptCandidate(compact,strict))return compact;
    }
  }
  // Search all viable departures and arrivals together. Rebuilding the same
  // grid for every pair scales poorly in tall traces with many aliases.
  for(const obs of [strict,protectedRects]) {
    const candidates=deferred.filter(c=>c.obs===obs);
    if(!candidates.length)continue;
    const unique=(points:Point[])=>[...new Map(points.map(p=>[String(p),p])).values()];
    const starts=unique(candidates.map(c=>c.depart)),ends=unique(candidates.map(c=>c.approach));
    const extent=bounds(obs.flatMap(r=>[[r.left,r.top],[r.right,r.bottom]]));
    const exterior=Math.max(128,t.left-extent.left,extent.right-t.right,
      t.top-extent.top,extent.bottom-t.bottom)+32;
    for(const margin of [...new Set([32,128,exterior])]) {
      // Match the final stroke clearance: extra search-only padding can seal
      // valid passages between adjacent field rows in a dense trace.
      const points=search(starts[0],ends[0],[...obs.map(r=>expand(r,a.width/2)),
        expand(t,a.width/2),expand(a.sourceBox,a.width/2)],margin,shafts,{starts,ends,source:s,limit:obs===strict?5000:200000});
      if(!points)continue;
      const end=points[points.length-1];
      const {h,e}=candidates.find(c=>c.approach[0]===end[0]&&c.approach[1]===end[1])!;
      const all=[s,...points,e],simple=all.filter((p,i)=>!i||i===all.length-1||
        (p[0]-all[i-1][0])*(all[i+1][1]-p[1])!==(p[1]-all[i-1][1])*(all[i+1][0]-p[0]));
      for(const radius of [12,6,0]) {const r=polyline(simple,h,radius);if(acceptCandidate(r,obs))return r;}
    }
  }
  // Preserve distinct alias arrivals whenever a route is available. Only
  // crowded targets that exhaust those options may share an arrival arrowhead.
  if(!shareAliasHeads&&aliases.length)return routeReference(a,text,objects,occupiedHeads,occupiedRoutes,true);
  return undefined;
}
