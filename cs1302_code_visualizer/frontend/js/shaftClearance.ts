/** Separate parallel shafts without prohibiting crossings. */
import {bounds, expand, type Point, type Rect, type Route, type Segment} from "./referenceRouting";

// Visible edge-to-edge space, in CSS pixels, in addition to both stroke extents.
export const SHAFT_CLEARANCE = 6;
interface Line { a: Point; b: Point; error: number; width: number; rect: Rect }
const cached = new WeakMap<Route, Line[]>();
const channelCache = new WeakMap<Route, Map<number, Rect[]>>();
const dot = (a: Point,b: Point) => a[0]*b[0]+a[1]*b[1];
const sub = (a: Point,b: Point): Point => [a[0]-b[0],a[1]-b[1]];
function distance(p: Point,a: Point,b: Point): number {
  const d=sub(b,a), length=dot(d,d);
  const t=length ? Math.max(0,Math.min(1,dot(sub(p,a),d)/length)) : 0;
  return Math.hypot(p[0]-a[0]-t*d[0],p[1]-a[1]-t*d[1]);
}
function flatten(segment: Segment,width: number, result: Line[],depth=0): void {
  const a=segment[0], b=segment[segment.length-1];
  // The convex hull bounds the entire curve's deviation from this finite chord.
  const error=Math.max(0,...segment.slice(1,-1).map(p=>distance(p,a,b)));
  if(error<=.25 || depth===16) {
    if(a[0]!==b[0]||a[1]!==b[1])result.push({a,b,error,width,rect:bounds([a,b])});
    return;
  }
  let layer=segment;
  const left=[a],right=[b];
  while(layer.length>1) {
    layer=layer.slice(1).map((p,i):Point=>[(p[0]+layer[i][0])/2,(p[1]+layer[i][1])/2]);
    left.push(layer[0]);right.unshift(layer[layer.length-1]);
  }
  flatten(left,width,result,depth+1);flatten(right,width,result,depth+1);
}
function lines(route: Route): Line[] {
  let result=cached.get(route);
  if(!result) {
    result=[];for(const segment of route.segments)flatten(segment,route.width??1,result);
    cached.set(route,result);
  }
  return result;
}
function conflict(a: Line,b: Line): boolean {
  const gap=SHAFT_CLEARANCE+(a.width+b.width)/2+a.error+b.error;
  if(a.rect.right+gap<b.rect.left || a.rect.left-gap>b.rect.right ||
     a.rect.bottom+gap<b.rect.top || a.rect.top-gap>b.rect.bottom)return false;
  const u=sub(a.b,a.a),v=sub(b.b,b.a),uu=dot(u,u),vv=dot(v,v);
  if(!uu||!vv || dot(u,v)**2 < .75*uu*vv)return false; // crossings of 30° or more
  // Include end caps: this makes clearance independent of grid subdivision
  // and avoids making two different references look like one continuous shaft.
  const cross=(p:Point,q:Point)=>p[0]*q[1]-p[1]*q[0];
  const w=sub(b.a,a.a),det=cross(u,v);
  if(det) {
    const t=cross(w,v)/det,s=cross(w,u)/det;
    if(t>=0&&t<=1&&s>=0&&s<=1)return true;
  }
  return Math.min(distance(a.a,b.a,b.b),distance(a.b,b.a,b.b),
    distance(b.a,a.a,a.b),distance(b.b,a.a,a.b)) < gap-1e-7;
}
const same=(a:Rect|undefined,b:Rect)=>a&&a.left===b.left&&a.right===b.right&&a.top===b.top&&a.bottom===b.bottom;

export class ShaftClearance {
  readonly channels: Rect[];
  private occupied: Line[];
  constructor(routes: Route[],target: Rect,private width: number,targetKey?: string) {
    const arrival=expand(target,16);
    const outsideArrival=(line:Line):Line[]=>{
      const delta=sub(line.b,line.a),cuts=[0,1];
      for(const [axis,edges] of [[0,[arrival.left,arrival.right]],[1,[arrival.top,arrival.bottom]]] as [number,number[]][]) {
        if(delta[axis])for(const edge of edges) {
          const t=(edge-line.a[axis])/delta[axis];if(t>0&&t<1)cuts.push(t);
        }
      }
      cuts.sort((a,b)=>a-b);
      const at=(t:number):Point=>[line.a[0]+t*delta[0],line.a[1]+t*delta[1]];
      return cuts.slice(1).flatMap((t,i)=>{
        const mid=at((cuts[i]+t)/2);
        if(mid[0]>=arrival.left&&mid[0]<=arrival.right&&mid[1]>=arrival.top&&mid[1]<=arrival.bottom)return [];
        const a=at(cuts[i]),b=at(t);return [{...line,a,b,rect:bounds([a,b])}];
      });
    };
    this.occupied=routes.flatMap(r=>{
      const alias=targetKey!==undefined&&r.targetKey!==undefined ? r.targetKey===targetKey : same(r.target,target);
      // Keep horizontal alias runs distinct outside the attachment corridor.
      // Shared vertical aliases remain available for tightly stacked sources.
      return alias?lines(r).filter(line=>Math.abs(line.b[0]-line.a[0])>=Math.sqrt(3)*Math.abs(line.b[1]-line.a[1])).flatMap(outsideArrival):lines(r);
    });
    // Bezier arithmetic can produce almost identical coordinates (x and x+1e-13).
    // Snap only search hints, with .001 extra clearance to cover rounding;
    // validate actual painted geometry at full precision. Otherwise aliases
    // multiply nearly zero-width grid cells and crowd out useful lane candidates.
    this.channels=routes.flatMap(r=>{
      let widths=channelCache.get(r);
      if(!widths){widths=new Map();channelCache.set(r,widths);}
      let channels=widths.get(width);
      if(!channels) {
        channels=r.segments.flatMap(s=>[.001,4].map(extra=>{
          const channel=expand(bounds(s),SHAFT_CLEARANCE+(width+(r.width??1))/2+extra);
          return Object.fromEntries(Object.entries(channel).map(([key,value])=>[key,Math.round(value*1024)/1024])) as unknown as Rect;
        }));
        widths.set(width,channels);
      }
      return channels;
    });
  }
  clearSegment(segment: Segment): boolean {
    if(!this.occupied.length)return true;
    const candidate:Line[]=[];flatten(segment,this.width,candidate);
    return candidate.every(a=>this.occupied.every(b=>!conflict(a,b)));
  }
  clear(route: Route): boolean { return route.segments.every(s=>this.clearSegment(s)); }
}
