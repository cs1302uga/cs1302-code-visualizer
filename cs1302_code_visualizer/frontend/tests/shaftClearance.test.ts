import {fixture} from "./routingFixture";
const crowded=fixture("parallel-run");
import {describe,expect,it} from "vitest";
import {ShaftClearance} from "../js/shaftClearance";
import {routeReference,clearsSource,expand,type Route,type Segment,type Attachment} from "../js/referenceRouting";
const target={left:300,top:0,right:340,bottom:40};
const other={left:400,top:0,right:440,bottom:40};
const route=(segments:Segment[], destination=other,width=1):Route=>
  ({segments,head:[[400,20],[394,17],[394,23]],kind:"test",target:destination,width});
describe("shaft separation",()=>{
  it("separates horizontal aliases away from the target, regardless of segment subdivision",()=>{
    const occupied=route([[[0,60],[410,60]]],other);
    const clearance=new ShaftClearance([occupied],other,1);
    expect(clearance.clearSegment([[30,60],[250,60]])).toBe(false);
    expect(clearance.clearSegment([[30,68],[250,68]])).toBe(true);
    const arrival=route([[[390,20],[400,20]]],other);
    expect(new ShaftClearance([arrival],other,1).clear(arrival)).toBe(true);
    const split=route([[[0,60],[200,60]],[[200,60],[410,60]]],other);
    expect(new ShaftClearance([split],other,1).clearSegment([[30,60],[250,60]])).toBe(false);
  });
  it("keeps its first bend clear of source borders when space permits",()=>{
    const a:Attachment={source:[92,150],sourceBox:{left:50,top:140,right:100,bottom:160},
      enclosure:{left:40,top:130,right:110,bottom:170},target:{left:180,top:40,right:250,bottom:90},
      sourceOwner:0,targetOwner:1,returning:true,width:1};
    const chosen=routeReference(a,[],[a.enclosure,a.target],[])!;
    expect(chosen).toBeDefined();
    expect(clearsSource(chosen,expand(a.sourceBox,6),a.width)).toBe(true);
  });

  it("opens another lane in a crowded row instead of sharing a different target's shaft",()=>{
    const a=crowded.a as Attachment, occupied=crowded.occupiedRoutes as Route[];
    const chosen=routeReference(a,crowded.text,crowded.objects,crowded.occupiedHeads,occupied)!;
    expect(chosen).toBeDefined();
    expect(new ShaftClearance(occupied,a.target,a.width).clear(chosen)).toBe(true);
  });
  it("rejects overlapping and nearby parallel strokes, including reverse directions and hover width",()=>{
    const clearance=new ShaftClearance([route([[[0,0],[0,100]]],other,3)],target,3);
    expect(clearance.clear(route([[[0,20],[0,80]]]))).toBe(false);
    expect(clearance.clear(route([[[8,80],[8,20]]]))).toBe(false);
    expect(clearance.clear(route([[[9,20],[9,80]]]))).toBe(true);
    expect(clearance.clear(route([[[0,101],[0,140]]]))).toBe(false);
    expect(clearance.clear(route([[[0,109],[0,140]]]))).toBe(true);
  });
  it("keeps perpendicular crossings but separates aliases away from their arrival",()=>{
    const occupied=route([[[0,0],[0,100]]]);
    expect(new ShaftClearance([occupied],target,1).clear(route([[[-20,50],[20,50]]]))).toBe(true);
    expect(new ShaftClearance([occupied],other,1).clear(occupied)).toBe(true);
  });
  it.each(["parallel-alias","parallel-stack","parallel-packed","parallel-blocked","parallel-dense","parallel-late-stack"])("finds a separate channel through %s",name=>{
    const captured=fixture(name);
    const a=captured.a as Attachment;
    const chosen=routeReference(a,captured.text,captured.objects,captured.occupiedHeads,captured.occupiedRoutes)!;
    expect(chosen).toBeDefined();
    expect(new ShaftClearance(captured.occupiedRoutes,a.target,a.width,a.targetKey).clear(chosen)).toBe(true);
  });
  it("checks a close curve consistently before and after subdividing a search edge",()=>{
    const clearance=new ShaftClearance([route([[[808.0625,760.5],[820.0625,760.5],[820.0625,748.5]]])],target,1);
    const whole:Segment=[[811.546875,730],[811.546875,780]];
    const pieces=Array.from({length:50},(_,i):Segment=>[[811.546875,730+i],[811.546875,731+i]]);
    expect(clearance.clearSegment(whole)).toBe(false);
    expect(pieces.every(p=>clearance.clearSegment(p))).toBe(false);
  });
  it("does not multiply search channels for floating-point noise",()=>{
    const occupied=[route([[[10,0],[10,100]]]),route([[[10+1e-13,0],[10+1e-13,100]]])];
    const clearance=new ShaftClearance(occupied,target,1);
    expect(clearance.channels[0]).toEqual(clearance.channels[2]);
    expect(clearance.channels[1]).toEqual(clearance.channels[3]);
  });
  it("uses object identity when distinct targets have coincident bounds",()=>{
    const occupied={...route([[[395,20],[399,20]]]),targetKey:"first"};
    expect(new ShaftClearance([occupied],other,1,"second").clear(occupied)).toBe(false);
    expect(new ShaftClearance([occupied],other,1,"first").clear(occupied)).toBe(true);
  });
  it("checks diagonal shafts and curves, not just horizontal and vertical lines",()=>{
    const diagonal=route([[[0,0],[100,100]]]);
    expect(new ShaftClearance([diagonal],target,1).clear(route([[[0,3],[100,103]]]))).toBe(false);
    const curved=route([[[0,0],[50,0],[50,100],[100,100]]]);
    const close=route([[[0,3],[50,3],[50,103],[100,103]]]);
    const far=route([[[0,30],[50,30],[50,130],[100,130]]]);
    const clearance=new ShaftClearance([curved],target,1);
    expect(clearance.clear(close)).toBe(false);
    expect(clearance.clear(far)).toBe(true);
  });
  it("chooses a different route when the easiest bend would follow another target's shaft",()=>{
    const a:Attachment={source:[92,150],sourceBox:{left:50,top:140,right:100,bottom:160},
      enclosure:{left:40,top:130,right:110,bottom:170},target:{left:180,top:40,right:250,bottom:90},
      sourceOwner:0,targetOwner:1,returning:false,width:1};
    const occupied=route([[[96,40],[96,135]]]);
    const chosen=routeReference(a,[],[a.enclosure,a.target],[],[occupied])!;
    expect(chosen).toBeDefined();
    expect(new ShaftClearance([occupied],a.target,1).clear(chosen)).toBe(true);
    expect(routeReference(a,[],[a.enclosure,a.target],[],[occupied])).toEqual(chosen);
  });
});
