/** Geometry-only reference routing. Coordinates are CSS pixels in the connector canvas. */
import { arrowHead as head, Point } from "./connectorGeometry";
export type { Point } from "./connectorGeometry";
export interface Rect { left: number; top: number; right: number; bottom: number }
export type Segment = Point[];
export interface Route { segments: Segment[]; head: Point[]; kind: string }
export interface Attachment {
  source: Point;
  sourceBox: Rect;
  enclosure: Rect;
  target: Rect;
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
  for(const r of obstacles) {
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

/** Rounded polyline with revalidation by the caller, including corner cut-ins. */
function polyline(points: Point[], h: Point[], radius: number): Route {
  const clean=points.filter((p,i)=>!i||p[0]!==points[i-1][0]||p[1]!==points[i-1][1]);
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
function search(start: Point,end: Point,obstacles: Rect[],margin: number): Point[]|undefined {
  const region=expand(bounds([start,end]),margin);
  const local=obstacles.filter(r=>overlaps(region,r));
  const xs=[region.left,region.right,start[0],end[0]],ys=[region.top,region.bottom,start[1],end[1]];
  for(const r of local) { xs.push(Math.max(region.left,r.left),Math.min(region.right,r.right));
    ys.push(Math.max(region.top,r.top),Math.min(region.bottom,r.bottom)); }
  const unique=(v:number[])=>[...new Set(v)].sort((a,b)=>a-b);
  const x=unique(xs),y=unique(ys),nx=x.length,ny=y.length;
  const si=y.indexOf(start[1])*nx+x.indexOf(start[0]),ei=y.indexOf(end[1])*nx+x.indexOf(end[0]);
  const point=(i:number):Point=>[x[i%nx],y[Math.floor(i/nx)]];
  const dist=new Map<number,number>(),prev=new Map<number,number>();
  // Binary heap ordered by distance + admissible Manhattan heuristic, then state ID.
  const heap: [number,number,number][]=[];
  const less=(a:number[],b:number[])=>a[0]<b[0]||(a[0]===b[0]&&a[1]<b[1]);
  const push=(v:[number,number,number])=>{ heap.push(v); let i=heap.length-1;
    while(i) {const p=(i-1)>>1;if(!less(v,heap[p]))break;heap[i]=heap[p];i=p;} heap[i]=v; };
  const pop=()=>{const v=heap[0],last=heap.pop()!; if(heap.length){let i=0;
    while(i*2+1<heap.length){let k=i*2+1;if(k+1<heap.length&&less(heap[k+1],heap[k]))k++;
      if(!less(heap[k],last))break;heap[i]=heap[k];i=k;}heap[i]=last;}return v;};
  dist.set(si*3,0);push([0,si*3,0]);
  const visibility=new Map<string,boolean>();
  while(heap.length) {
    const [,state,cost]=pop(); if(dist.get(state)!==cost)continue;
    const i=Math.floor(state/3),dir=state%3,p=point(i);
    if(i===ei){const result:Point[]=[];let s=state;while(true){result.push(point(Math.floor(s/3)));
      if(!prev.has(s))break;s=prev.get(s)!;}return result.reverse();}
    const col=i%nx,row=Math.floor(i/nx);
    for(const [j,nd] of [[col>0?i-1:-1,1],[col+1<nx?i+1:-1,1],[row>0?i-nx:-1,2],[row+1<ny?i+nx:-1,2]]) {
      if(j<0)continue;
      const q=point(j),key=`${Math.min(i,j)}:${Math.max(i,j)}`;
      let open=visibility.get(key);
      if(open===undefined){open=!local.some(r=>intersects([p,q],r));visibility.set(key,open);}
      if(!open)continue;
      const next=j*3+nd,ncost=cost+Math.abs(p[0]-q[0])+Math.abs(p[1]-q[1])+(dir&&dir!==nd?18:0);
      if(ncost>=(dist.get(next)??Infinity))continue;
      dist.set(next,ncost);prev.set(next,state);
      push([ncost+Math.abs(q[0]-end[0])+Math.abs(q[1]-end[1]),next,ncost]);
    }
  }
}

/** Frame-parent links attach to frame boundaries, not reference value boxes. */
export function routeFrameParent(a: Attachment, text: Rect[], objects: Rect[], occupiedHeads: Rect[]): Route | undefined {
  const {sourceSide, targetSide, curviness} = a.parent!;
  const s = a.source, t = a.target;
  const protectedRects = [...text.map(r => expand(r, 1)), ...occupiedHeads.map(r => expand(r, 2))];
  const frames = [a.sourceBox, t];
  const unrelated = objects.filter((r, i) => i !== a.sourceOwner && i !== a.targetOwner && r.right > r.left);
  const valid = (route: Route, obstacles: Rect[]) => clear(route, obstacles, a.width) &&
    // The boundary attachment is allowed; crossing either frame's contents is not.
    frames.every(frame => !overlaps(bounds(route.head), frame) &&
      route.segments.every(segment => !intersects(segment, frame)));
  for (const obstacles of [[...protectedRects, ...unrelated.map(r => expand(r, 8))], protectedRects]) {
    for (const fraction of [.5, .75, .25, .875, .125]) {
      const tip: Point = [targetSide < 0 ? t.left : t.right, t.top + (t.bottom - t.top) * fraction];
      const h = head(tip, [targetSide, 0]), end = rear(h);
      const original: Route = {kind: "parent", head: h, segments: [
        [s, [s[0] + sourceSide * curviness, s[1]], [end[0] + targetSide * curviness, end[1]], end],
      ]};
      if (valid(original, obstacles)) return original;
      const depart: Point = [s[0] + sourceSide * 12, s[1]];
      const approach: Point = [end[0] + targetSide * 12, end[1]];
      const searchObstacles = [...obstacles.map(r => expand(r, a.width / 2 + 2)), ...frames];
      const extent = bounds(searchObstacles.flatMap(r => [[r.left, r.top], [r.right, r.bottom]]));
      const exterior = Math.max(128, approach[0] - extent.left, extent.right - approach[0],
        approach[1] - extent.top, extent.bottom - approach[1]) + 32;
      for (const margin of [...new Set([32, 128, exterior])]) {
        const points = search(depart, approach, searchObstacles, margin);
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

export function routeReference(a: Attachment,text: Rect[],objects: Rect[],occupiedHeads: Rect[]): Route|undefined {
  const s=a.source,t=a.target,exit:Point=[Math.max(s[0],a.enclosure.right-4),s[1]];
  const protectedRects=[...text.map(r=>expand(r,1)),...occupiedHeads.map(r=>expand(r,2))];
  const unrelated=objects.filter((r,i)=>i!==a.sourceOwner&&i!==a.targetOwner&&r.right>r.left&&r.bottom>r.top);
  const strict=[...protectedRects,...unrelated.map(r=>expand(r,8))];
  const valid=(r:Route,obs=protectedRects)=>clear(r,obs,a.width)&&clearsSource(r,a.sourceBox,a.width);
  const tips: {tip:Point;normal:Point}[]=[];
  for(const f of [.5,.75,.25,.875,.125]) tips.push(
    {tip:[t.left,t.top+(t.bottom-t.top)*f],normal:[-1,0]},
    {tip:[t.left+(t.right-t.left)*f,t.bottom],normal:[0,1]},
    {tip:[t.right,t.top+(t.bottom-t.top)*f],normal:[1,0]},
    {tip:[t.left+(t.right-t.left)*f,t.top],normal:[0,-1]});
  // Additional ten-pixel ports accommodate many aliases after spacing repair.
  for(let x=t.left+10;x<t.right-5;x+=10) tips.push(
    {tip:[x,t.bottom],normal:[0,1]},{tip:[x,t.top],normal:[0,-1]});
  for(let y=t.top+10;y<t.bottom-5;y+=10) tips.push(
    {tip:[t.left,y],normal:[-1,0]},{tip:[t.right,y],normal:[1,0]});
  const legacy=a.legacyTarget??t;
  const h=head([legacy.left,(legacy.top+legacy.bottom)/2],[-1,0]),end=rear(h),bend=end[0]>=exit[0]?(end[0]-exit[0])/2:40;
  const original:Route={segments:[[s,exit],[exit,[exit[0]+bend,exit[1]],[end[0]-bend,end[1]],end]],head:h,kind:"original"};
  if(!a.returning&&valid(original,strict))return original;
  const relevant=objects.filter(r=>r.right>=Math.min(s[0],t.left)&&r.left<=Math.max(s[0],t.right));
  const bottom=Math.max(a.enclosure.bottom,t.bottom,...relevant.map(r=>r.bottom))+(a.lane??0)*12;
  // Broad, tangent-continuous sweeps give visible separation at reduced zoom.
  for(const gap of [32,48,72,104]) for(const f of [.5,.75,.25]) for(const down of a.returning?[true,false]:[false,true]) {
    const tip:Point=[t.left+(t.right-t.left)*f,t.bottom],h=head(tip,[0,1]),e=rear(h);
    const lead=down?s:exit,lane=bottom+gap,j:Point=[(lead[0]+tip[0])/2,lane];
    const handle=Math.abs(tip[0]-lead[0])/(down?4:2),sign=tip[0]>=lead[0]?1:-1;
    const route:Route={head:h,kind:"sweep",segments:[
      ...(!down?[[s,lead]]:[]),
      [lead,down?[lead[0],lane]:[lead[0]+20,lead[1]],[j[0]-sign*handle,j[1]],j],
      [j,[j[0]+sign*handle,j[1]],[tip[0],lane],e]]};
    if(valid(route,strict))return route;
    if(!down) {
      const channel=a.enclosure.right+12+(a.lane??0)*8,turn:Point=[channel+12,lane];
      const compact:Route={head:h,kind:"sweep",segments:[[s,[channel,s[1]]],
        [[channel,s[1]],[channel+12,s[1]],[channel,lane],turn],
        [turn,[tip[0],lane],[tip[0],lane],e]]};
      if(valid(compact,strict))return compact;
    }
  }
  // Fixed-position search first avoids bodies, then permits readable empty-body crossings.
  for(const obs of [strict,protectedRects]) {
    if(!a.returning&&valid(original,obs))return original;
    for(const {tip,normal} of tips) {
      const h=head(tip,normal),e=rear(h);
      if(occupiedHeads.some(r=>overlaps(expand(bounds(h),2),r)))continue;
      const approach:Point=[e[0]+normal[0]*12,e[1]+normal[1]*12];
      if(!clear({segments:[[approach,e]],head:h,kind:"arrival"},obs,a.width))continue;
      const departures:Point[]=[[a.sourceBox.right+12,s[1]],[s[0],a.sourceBox.bottom+12],[s[0],a.sourceBox.top-12]];
      for(const depart of departures) {
        if(obs.some(r=>intersects([s,depart],expand(r,a.width/2))))continue;
        for(const corner of [[depart[0],approach[1]],[approach[0],depart[1]]] as Point[]) {
          for(const radius of [12,0]) {
            const r=polyline([s,depart,corner,approach,e],h,radius);
            if(valid(r,obs))return r;
          }
        }
        // Try exterior doglegs before constructing a grid. This is particularly
        // useful for the last link in a long row or a cycle.
        for(const lane of [bottom+32,bottom+48,Math.min(a.enclosure.top,t.top)-32]) {
          const points=[s,depart,[depart[0],lane] as Point,[approach[0],lane] as Point,approach,e];
          for(const radius of [12,0]) {const r=polyline(points,h,radius);if(valid(r,obs))return r;}
        }
        const extent=bounds(obs.flatMap(r=>[[r.left,r.top],[r.right,r.bottom]]));
        const exterior=Math.max(128,approach[0]-extent.left,extent.right-approach[0],
          approach[1]-extent.top,extent.bottom-approach[1])+32;
        for(const margin of [...new Set([32,128,exterior])]) {
          const points=search(depart,approach,obs.map(r=>expand(r,a.width/2+2)),margin);
          if(!points)continue;
          // Collapse grid subdivisions before rounding corners.
          const all=[s,...points,e],simple=all.filter((p,i)=>!i||i===all.length-1||
            (p[0]-all[i-1][0])*(all[i+1][1]-p[1])!==(p[1]-all[i-1][1])*(all[i+1][0]-p[0]));
          for(const radius of [12,6,0]) {const r=polyline(simple,h,radius);if(valid(r,obs))return r;}
        }
      }
    }
  }
  return undefined;
}
