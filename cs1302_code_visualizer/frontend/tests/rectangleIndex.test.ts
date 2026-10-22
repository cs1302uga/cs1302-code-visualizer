import {describe,expect,it} from "vitest";
import {RectangleIndex} from "../js/rectangleIndex";
import {clear,intersects,type Rect,type Route,type Segment} from "../js/referenceRouting";

describe("rectangle broad phase",()=>{
  it("preserves painted curve and head clearance at multiple stroke widths",()=>{
    const obstacles=Array.from({length:100},(_,i)=>({left:i*12-100,right:i*12-94,top:20,bottom:28}));
    const index=new RectangleIndex(obstacles,r=>r);
    const segments:Segment[][]=[[[[-110,10],[120,10]]],[[[-110,16],[120,16]]],
      [[[-110,0],[10,60],[120,0]]],[[[-110,0],[-60,40],[60,-40],[120,0]]]];
    for(const width of [1,3,9])for(const path of segments)for(const y of [10,19,25,40]) {
      const route:Route={segments:path,head:[[130,y],[124,y-3],[124,y+3]],kind:"test"};
      expect(clear(route,obstacles,width,index)).toBe(clear(route,obstacles,width));
    }
  });
  it("retains exact collision decisions for fractional, negative, boundary and zero-area queries",()=>{
    const rectangles:Rect[]=Array.from({length:120},(_,i)=>({left:(i%12)*17.125-100,
      right:(i%12)*17.125-90,top:Math.floor(i/12)*13.75-60,bottom:Math.floor(i/12)*13.75-51}));
    const index=new RectangleIndex(rectangles,r=>r);
    const segments:Segment[]=rectangles.flatMap(r=>[
      [[r.left-5,r.top],[r.right+5,r.top]],
      [[r.left-5,r.top+1],[r.right+5,r.top+1]],
      [[r.left,r.top-5],[r.left,r.bottom+5]],
      [[r.left+1,r.top-5],[r.left+1,r.bottom+5]],
      [[r.left+1,r.top+1],[r.left+1,r.top+1]],
      [[r.left-1,r.top-1],[r.right+1,r.bottom+1]],
    ] as Segment[]);
    for(const segment of segments) {
      const [a,b]=segment;
      const query={left:Math.min(a[0],b[0]),right:Math.max(a[0],b[0]),
        top:Math.min(a[1],b[1]),bottom:Math.max(a[1],b[1])};
      expect(index.some(query,r=>intersects(segment,r))).toBe(rectangles.some(r=>intersects(segment,r)));
      if(a[0]===b[0]||a[1]===b[1]) {
        expect(index.intersectsInterior(query)).toBe(rectangles.some(r=>intersects(segment,r)));
      }
    }
    // A caller may treat boundary contact as occupied even when interior
    // intersection does not: broad-phase filtering must keep that choice.
    expect(index.some({left:-100,right:-100,top:-60,bottom:-60},()=>true)).toBe(true);
    expect(new RectangleIndex<Rect>([],r=>r).some(rectangles[0],()=>true)).toBe(false);
    expect(new RectangleIndex<Rect>([],r=>r).intersectsInterior(rectangles[0])).toBe(false);
  });
});
