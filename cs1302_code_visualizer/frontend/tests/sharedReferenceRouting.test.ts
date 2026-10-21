import {describe, expect, it} from "vitest";
import {readFileSync} from "node:fs";
import {arrowHead, SOURCE_RADIUS} from "../js/connectorGeometry";
import {bounds, clear, clearsSource, clearsTarget, expand, intersects, routeReference, type Attachment, type Point, type Route} from "../js/referenceRouting";
import {ShaftClearance} from "../js/shaftClearance";
import {
  attachSharedReferenceBaseline, planSharedReferences, sharedRouteMetrics, validateSharedReferencePlan,
  type SharedReferenceInput,
} from "../js/sharedReferenceRouting";

function scene(count = 2, width = 1): SharedReferenceInput {
  const owner = {left:20, top:110, right:108, bottom:130+count*40};
  const target = {left:180, top:40, right:250, bottom:90};
  const attachments: Attachment[] = Array.from({length:count}, (_,i) => ({
    source:[92,150+i*40], sourceBox:{left:50,top:140+i*40,right:100,bottom:160+i*40},
    enclosure:owner, target, targetKey:"object", sourceOwner:0,targetOwner:1,
    returning:false,width,lane:i,strict:true,
  }));
  const occupied: Route[] = [];
  const edges = attachments.map((attachment,i) => {
    const dots = attachments.flatMap((a,j) => i === j ? [] : [expand(bounds([a.source]),SOURCE_RADIUS+1)]);
    const route = routeReference(attachment,dots,[owner,target],occupied.map(r => bounds(r.head)),occupied);
    expect(route, `baseline reference ${i}`).toBeDefined();
    route!.width=width;route!.target=target;route!.targetKey="object";occupied.push(route!);
    return {key:`source-${i}`,attachment,route:route!,styleKey:"active"};
  });
  return {edges,objects:[owner,target],obstacles:[]};
}

const pathsByKey = (input: SharedReferenceInput, routes: Route[]) =>
  Object.fromEntries(input.edges.map((edge,i) => [edge.key,routes[i]]));

/** Two bottom-arrival references known to admit a genuine shared suffix. */
function compatiblePair(): SharedReferenceInput {
  const input=scene(3);input.edges=input.edges.slice(1);
  expect(planSharedReferences(input).groups).toHaveLength(1);
  return input;
}

describe("explicit terminal reference sharing", () => {
  it.each([3,4,12])("shares compatible cohorts among %s aliases without losing a source or adding length/bends", count => {
    const input=scene(count), snapshot=JSON.stringify(input), plan=planSharedReferences(input);
    expect(plan.baselineValid,JSON.stringify(plan.diagnostics)).toBe(true);
    expect(plan.groups.length,JSON.stringify({diagnostics:plan.diagnostics,routes:input.edges.map(e=>e.route)})).toBeGreaterThan(0);
    expect(plan.groups[0].members.length).toBeGreaterThanOrEqual(2);
    expect(plan.routes).toHaveLength(count);
    expect(validateSharedReferencePlan(input,plan.routes,plan.groups)).toEqual([]);
    for(let i=0;i<count;i++) {
      expect(sharedRouteMetrics(plan.routes[i]).length).toBeLessThanOrEqual(sharedRouteMetrics(input.edges[i].route).length);
      expect(sharedRouteMetrics(plan.routes[i]).bends).toBeLessThanOrEqual(sharedRouteMetrics(input.edges[i].route).bends);
      expect(plan.routes[i].segments[0][0]).toEqual(input.edges[i].attachment.source);
      const [x,y]=plan.routes[i].head[0],t=input.edges[i].attachment.target;
      expect(x===t.left||x===t.right||y===t.top||y===t.bottom).toBe(true);
    }
    const approaches=new Set(input.edges.map(e=>{
      const h=e.route.head;
      return String([Math.sign((h[1][0]+h[2][0])/2-h[0][0]),Math.sign((h[1][1]+h[2][1])/2-h[0][1])]);
    }));
    expect(plan.profilesTried).toBeLessThanOrEqual(24*approaches.size);
    expect(JSON.stringify(input)).toBe(snapshot);
  });

  it("records the precise downstream owners of each spine interval", () => {
    const input=scene(4), plan=planSharedReferences(input), group=plan.groups[0];
    expect(group,JSON.stringify(plan.diagnostics)).toBeDefined();
    expect(new Set(group.physicalPieces.map(p=>p.members.length)).size).toBeGreaterThan(1);
    for(const member of group.members) {
      const owned=group.physicalPieces.filter(p=>p.members.includes(member)).map(p=>p.segment);
      const branch=group.branches.find(b=>b.index===member)!;
      expect(plan.routes[member].segments).toEqual([...branch.segments,...owned]);
    }
  });

  it("admits a two-source confluence while retaining both complete logical routes", () => {
    const input=compatiblePair();
    const plan=planSharedReferences(input);
    expect(plan.baselineValid,JSON.stringify(plan.diagnostics)).toBe(true);
    expect(plan.groups).toHaveLength(1);
    expect(plan.groups[0].members).toHaveLength(2);
    expect(validateSharedReferencePlan(input,plan.routes,plan.groups)).toEqual([]);
  });

  it.each([1,3])("preserves admission and continuity at fractional coordinates and width %s", width => {
    const input=scene(4,width),movePoint=([x,y]:Point):Point=>[x+.125,y+.375];
    const moveRect=(r:{left:number;right:number;top:number;bottom:number})=>
      ({left:r.left+.125,right:r.right+.125,top:r.top+.375,bottom:r.bottom+.375});
    const shifted:SharedReferenceInput={objects:input.objects.map(moveRect),obstacles:[],edges:input.edges.map(e=>({
      ...e,attachment:{...e.attachment,source:movePoint(e.attachment.source),sourceBox:moveRect(e.attachment.sourceBox),
        enclosure:moveRect(e.attachment.enclosure),target:moveRect(e.attachment.target)},
      route:{...e.route,segments:e.route.segments.map(s=>s.map(movePoint)),head:e.route.head.map(movePoint)},
    }))};
    const plan=planSharedReferences(shifted);
    expect(plan.baselineValid,JSON.stringify(plan.diagnostics)).toBe(true);
    expect(plan.groups.length,JSON.stringify(plan.diagnostics)).toBeGreaterThan(0);
    expect(validateSharedReferencePlan(shifted,plan.routes,plan.groups)).toEqual([]);
    for(let i=0;i<input.edges.length;i++) {
      expect(sharedRouteMetrics(plan.routes[i]).length).toBeLessThanOrEqual(sharedRouteMetrics(shifted.edges[i].route).length);
      expect(sharedRouteMetrics(plan.routes[i]).bends).toBeLessThanOrEqual(sharedRouteMetrics(shifted.edges[i].route).bends);
    }
  });

  it("retains a strict baseline when optimization is disabled", () => {
    const input=scene(4), plan=planSharedReferences({...input,optimize:false});
    expect(plan.baselineValid).toBe(true);
    expect(plan.groups).toEqual([]);
    expect(plan.routes).toEqual(input.edges.map(e=>e.route));
    expect(plan.profilesTried).toBe(0);
  });

  it("lifts nested coincident suffixes into exact ownership without optimizing their geometry", () => {
    const input=scene(4), optimized=planSharedReferences(input);
    expect(optimized.groups).toHaveLength(1);
    const owned={...input,optimize:false,edges:input.edges.map((e,i)=>({...e,route:optimized.routes[i]}))};
    const plan=planSharedReferences(owned);
    expect(plan.baselineValid,JSON.stringify(plan.diagnostics)).toBe(true);
    expect(plan.groups).toHaveLength(1);
    expect(plan.groups[0].kind).toBe("factored");
    expect(plan.groups[0].physicalPieces.map(p=>[...p.members].sort())).toEqual(
      optimized.groups[0].physicalPieces.filter(p=>p.members.length>1).map(p=>[...p.members].sort()));
    expect(plan.routes).toEqual(optimized.routes);
    expect(plan.profilesTried).toBe(0);
  });

  it("is independent of insertion order and does not mutate the baseline", () => {
    const input=scene(4), plan=planSharedReferences(input);
    const reversed={...input,edges:[...input.edges].reverse()}, second=planSharedReferences(reversed);
    expect(pathsByKey(input,plan.routes)).toEqual(pathsByKey(reversed,second.routes));
    expect(plan.groups.map(g=>g.id)).toEqual(second.groups.map(g=>g.id));
  });

  it("keeps an accepted group intact when another target's proposed join is blocked", () => {
    const first=scene(4),second=scene(4),move=([x,y]:Point):Point=>[x+400,y+400];
    const rect=(r:{left:number;right:number;top:number;bottom:number})=>
      ({left:r.left+400,right:r.right+400,top:r.top+400,bottom:r.bottom+400});
    const input:SharedReferenceInput={obstacles:[],objects:[...first.objects,...second.objects.map(rect)],
      edges:[...first.edges,...second.edges.map(e=>({...e,key:`second-${e.key}`,
        attachment:{...e.attachment,source:move(e.attachment.source),sourceBox:rect(e.attachment.sourceBox),
          enclosure:rect(e.attachment.enclosure),target:rect(e.attachment.target),targetKey:"second-object",
          sourceOwner:e.attachment.sourceOwner+first.objects.length,targetOwner:e.attachment.targetOwner+first.objects.length},
        route:{...e.route,segments:e.route.segments.map(s=>s.map(move)),head:e.route.head.map(move),
          target:rect(e.attachment.target),targetKey:"second-object"},
      }))]};
    const both=planSharedReferences(input);
    expect(both.baselineValid,JSON.stringify(both.diagnostics)).toBe(true);
    expect(both.groups).toHaveLength(2);
    const blocked={...input,objects:[...input.objects,{left:509,top:491,right:651,bottom:720}]};
    const partial=planSharedReferences(blocked);
    expect(partial.baselineValid,JSON.stringify(partial.diagnostics)).toBe(true);
    expect(partial.groups).toHaveLength(1);
    expect(partial.groups[0].targetKey).toBe("object");
    expect(partial.routes.slice(0,first.edges.length)).toEqual(both.routes.slice(0,first.edges.length));
    expect(partial.routes.slice(first.edges.length)).toEqual(input.edges.slice(first.edges.length).map(e=>e.route));
    expect(validateSharedReferencePlan(blocked,partial.routes,partial.groups)).toEqual([]);
  });

  it("does not group missing identity, persistent style differences, or excluded relations", () => {
    for(const mode of ["identity","style","return","parent","self","eligibility"] as const) {
      const input=compatiblePair();
      if(mode==="identity")input.edges[1].attachment.targetKey=undefined;
      if(mode==="style")input.edges[1].styleKey="inactive";
      if(mode==="return")input.edges[1].attachment.returning=true;
      if(mode==="parent") {
        const a=input.edges[1].attachment;
        a.parent={sourceSide:1,targetSide:-1,curviness:0};
        // A frame-parent source is on a frame boundary, never inside a value box.
        a.sourceBox={...a.sourceBox,top:a.source[1],bottom:a.source[1]};
      }
      if(mode==="self")input.edges[1].attachment.sourceOwner=input.edges[1].attachment.targetOwner;
      if(mode==="eligibility")input.edges[1].eligible=false;
      const plan=planSharedReferences(input);
      expect(plan.baselineValid,mode).toBe(true);
      expect(plan.groups,mode).toEqual([]);
    }
  });

  it("does not infer target identity from coincident target rectangles", () => {
    const input=compatiblePair();input.edges[1].attachment.targetKey="distinct-object";
    const plan=planSharedReferences(input);
    expect(plan.baselineValid).toBe(true);expect(plan.groups).toEqual([]);
  });

  it("keeps a direct baseline path unchanged", () => {
    const input=scene();
    const first=input.edges[0], a=first.attachment;
    a.source=[92,65];a.sourceBox={left:50,top:55,right:100,bottom:75};a.enclosure=a.sourceBox;a.sourceOwner=-1;
    const head=arrowHead([180,65],[-1,0]);
    first.route={segments:[[a.source,[174,65]]],head,kind:"direct",width:1,target:a.target,targetKey:a.targetKey};
    const plan=planSharedReferences(input);
    expect(plan.baselineValid,JSON.stringify(plan.diagnostics)).toBe(true);
    expect(plan.routes[0]).toEqual(first.route);expect(plan.groups).toEqual([]);
  });

  it("rejects an unowned legacy alias overlap rather than silently accepting it", () => {
    const input=scene();
    input.edges[1].route={...input.edges[0].route,segments:[
      [input.edges[1].attachment.source,[130,190]],[[130,190],[130,150]],
      ...input.edges[0].route.segments,
    ]};
    const plan=planSharedReferences(input);
    expect(plan.baselineValid).toBe(false);expect(plan.accepted).toBe(false);
    expect(plan.diagnostics[0].reason).toContain("invalid baseline");
  });

  it("detects forged ownership and a broken branch even when member labels look correct", () => {
    const input=scene(4), plan=planSharedReferences(input);
    expect(plan.groups.length).toBeGreaterThan(0);
    const forged=structuredClone(plan.groups);
    forged[0].physicalPieces[0].members=[...forged[0].members];
    expect(validateSharedReferencePlan(input,plan.routes,forged)).toContain("incorrect suffix ownership");
    const broken=structuredClone(plan.groups);
    broken[0].branches[0].segments[0][0][0]++;
    expect(validateSharedReferencePlan(input,plan.routes,broken)).toContain("logical path disagrees with shared paint");
  });

  it("rejects a short directed reversal even entirely inside the declared join neighborhood", () => {
    const input=scene(4), plan=planSharedReferences(input), groups=structuredClone(plan.groups), group=groups[0];
    const at=group.segments.length-1, [start,end]=group.segments[at];
    const point=(t:number):Point=>[start[0]+t*(end[0]-start[0]),start[1]+t*(end[1]-start[1])];
    const p=point(.02),q=point(.01),replacement=[[start,p],[p,q],[q,end]];
    const members=group.physicalPieces[at].members;
    group.segments.splice(at,1,...replacement);
    group.physicalPieces.splice(at,1,...replacement.map(segment=>({segment,members})));
    const routes=[...plan.routes];
    for(const branch of group.branches) {
      const tail=branch.segments[branch.segments.length-1],join=tail[tail.length-1];
      const from=group.segments.findIndex(s=>String(s[0])===String(join));
      routes[branch.index]={...routes[branch.index],segments:[...branch.segments,...group.segments.slice(from)]};
    }
    expect(validateSharedReferencePlan(input,routes,groups).join(" ")).toMatch(/revers|repeated interval/);
  });

  it("rejects a foreign perpendicular crossing on the entire shared suffix", () => {
    const input=scene(4), plan=planSharedReferences(input), group=plan.groups[0];
    const segment=group.physicalPieces.find(p=>p.members.length>1)!.segment;
    const end=segment[segment.length-1],x=(segment[0][0]+end[0])/2,y=(segment[0][1]+end[1])/2;
    const source:Point=[x-25,y],target={left:x+45,top:y-5,right:x+65,bottom:y+5};
    const sourceBox={left:x-27,top:y-2,right:x-23,bottom:y+2};
    const attachment:Attachment={source,sourceBox,enclosure:sourceBox,target,targetKey:"foreign",
      sourceOwner:-1,targetOwner:input.objects.length,returning:false,width:1,lane:0,strict:true};
    const foreign:Route={segments:[[source,[x+39,y]]],head:arrowHead([x+45,y],[-1,0]),kind:"direct",width:1,target,targetKey:"foreign"};
    const withForeign={...input,objects:[...input.objects,target],edges:[...input.edges,
      {key:"foreign",attachment,route:foreign,styleKey:"active"}]};
    expect(validateSharedReferencePlan(withForeign,[...plan.routes,foreign],plan.groups)).toContain(
      "unrelated route crosses or approaches shared suffix");
  });

  it("reports out-of-range ownership instead of accepting or dereferencing it", () => {
    const input=scene(4),plan=planSharedReferences(input),groups=structuredClone(plan.groups);
    groups[0].members[0]=999;
    expect(validateSharedReferencePlan(input,plan.routes,groups)).toContain("invalid shared membership");
  });

  it("retains the valid baseline when an object occupies the proposed join region", () => {
    const input=compatiblePair();
    // Each baseline remains valid; make every new join illegal without changing it.
    input.objects.push({left:109,top:91,right:251,bottom:300});
    const plan=planSharedReferences(input);
    expect(plan.baselineValid).toBe(true);
    expect(plan.groups).toEqual([]);
    expect(plan.routes).toEqual(input.edges.map(e=>e.route));
  });

  it("keeps ordinary perpendicular crossings while strict alias clearance forbids implicit sharing", () => {
    const input=scene(), target=input.edges[0].attachment.target;
    const occupied:Route={segments:[[[120,100],[120,200]]],head:[],kind:"test",width:3,target,targetKey:"object"};
    expect(new ShaftClearance([occupied],target,3,"object").clear(occupied)).toBe(true);
    expect(new ShaftClearance([occupied],target,3,"object",true).clear(occupied)).toBe(false);
    expect(new ShaftClearance([occupied],target,3,"object",true).clearSegment([[100,150],[140,150]])).toBe(true);
  });

  it("routes a measured self-reference past an occupied arrival without sharing or weakening clearance", () => {
    // Native compact-string, vertical-array scene after the old orthogonal-only
    // baseline exhausted all local repair attempts. Includes exact future stems.
    const data=JSON.parse(readFileSync("tests/fixtures/reference-routing/strict-self-reference.json","utf8"));
    const r=routeReference(data.a,data.text,data.objects,data.heads,data.occupiedRoutes);
    expect(r).toBeDefined();
    expect(clear(r!,data.text.map(o=>expand(o,1)),data.a.width)).toBe(true);
    expect(clearsSource(r!,data.a.sourceBox,data.a.width)).toBe(true);
    expect(clearsTarget(r!,data.a)).toBe(true);
    expect(new ShaftClearance(data.occupiedRoutes,data.a.target,data.a.width,data.a.targetKey,true).clear(r!)).toBe(true);
    for(const occupied of data.occupiedRoutes as Route[])for(const segment of occupied.segments) {
      expect(intersects(segment,expand(bounds(r!.head),2+(occupied.width??1)/2))).toBe(false);
    }
    for(const oldHead of data.heads) {
      expect(clear(r!,[expand(oldHead,2)],data.a.width)).toBe(true);
    }
  });

  it("constructs an explicitly owned baseline from a complete existing suffix before exhaustive independent search", () => {
    const input=scene(4),newIndex=3;
    input.edges[newIndex].route={segments:[],head:[],kind:"pending"};
    const plan=attachSharedReferenceBaseline(input,newIndex);
    expect(plan).toBeDefined();
    expect(plan!.baselineValid).toBe(true);
    expect(plan!.groups.some(g=>g.members.includes(newIndex))).toBe(true);
    expect(plan!.profilesTried).toBeLessThanOrEqual(24);
    expect(validateSharedReferencePlan(input,plan!.routes,plan!.groups)).toEqual([]);
    for(let i=0;i<newIndex;i++) {
      expect(sharedRouteMetrics(plan!.routes[i]).length).toBeCloseTo(sharedRouteMetrics(input.edges[i].route).length,8);
      expect(sharedRouteMetrics(plan!.routes[i]).bends).toBe(sharedRouteMetrics(input.edges[i].route).bends);
    }
    const reversed={...input,edges:[...input.edges].reverse()},again=attachSharedReferenceBaseline(reversed,0);
    expect(again).toBeDefined();
    expect(pathsByKey(input,plan!.routes)).toEqual(pathsByKey(reversed,again!.routes));
    expect(plan!.groups.map(g=>g.id)).toEqual(again!.groups.map(g=>g.id));
  });

  it("declines owned-baseline attachment for incompatible semantics or unresolved identity", () => {
    for(const kind of ["style","identity","excluded"] as const) {
      const input=scene(4),edge=input.edges[3];edge.route={segments:[],head:[],kind:"pending"};
      expect(attachSharedReferenceBaseline(input,3)).toBeDefined();
      if(kind==="style")edge.styleKey="inactive";
      if(kind==="identity")edge.attachment.targetKey=undefined;
      if(kind==="excluded")edge.eligible=false;
      expect(attachSharedReferenceBaseline(input,3),kind).toBeUndefined();
    }
  });

  it("does not create an owned baseline across a foreign crossing on the reusable suffix", () => {
    const input=scene(4),newIndex=3;input.edges[newIndex].route={segments:[],head:[],kind:"pending"};
    expect(attachSharedReferenceBaseline(input,newIndex)).toBeDefined();
    const source:Point=[110,120],target={left:270,top:110,right:300,bottom:130};
    const sourceBox={left:105,top:115,right:115,bottom:125};
    const attachment:Attachment={source,sourceBox,enclosure:sourceBox,target,targetKey:"foreign",
      sourceOwner:-1,targetOwner:input.objects.length,returning:false,width:1,strict:true};
    const foreign:Route={segments:[[source,[264,120]]],head:arrowHead([270,120],[-1,0]),kind:"direct",width:1,target,targetKey:"foreign"};
    input.objects.push(target);input.edges.push({key:"foreign",attachment,route:foreign,styleKey:"active"});
    const existing={...input,edges:input.edges.filter((_,i)=>i!==newIndex),optimize:false};
    expect(planSharedReferences(existing).baselineValid).toBe(true);
    expect(attachSharedReferenceBaseline(input,newIndex)).toBeUndefined();
  });
});
