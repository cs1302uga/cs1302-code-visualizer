// @vitest-environment node
import {describe,expect,it,vi} from "vitest";
import {searchOrthogonalGrid as search,exactOrthogonalDijkstra as oracle,ORACLE_MAX_STATES,
  type OrthogonalGrid,type GridPoint} from "../js/orthogonalSearch";

const key=(a:GridPoint,b:GridPoint)=>[String(a),String(b)].sort().join("|");
const allowed=(edges:[GridPoint,GridPoint][])=>{
  const keys=new Set(edges.map(([a,b])=>key(a,b)));
  return (a:GridPoint,b:GridPoint)=>keys.has(key(a,b));
};
const grid=(x=[0,2,4],y=[0,2]):OrthogonalGrid=>({x,y,sources:[{point:[x[0],y[0]],initialCost:0}],
  ends:[[x[x.length-1],y[y.length-1]]],segmentVisible:()=>true});

describe("orthogonal grid search",()=>{
  it("retains equal-cost arrivals at J with different orientations",()=>{
    const s:GridPoint=[0,0],a:GridPoint=[2,0],b:GridPoint=[0,2],j:GridPoint=[2,2],g:GridPoint=[4,2];
    const graph={...grid(),segmentVisible:allowed([[s,a],[a,j],[s,b],[b,j],[j,g]])};
    const expected={status:"found",points:[s,b,j,g],cost:24}; // Other branch costs 42.
    expect(search(graph)).toEqual(expected);
    expect(oracle(graph)).toEqual(expected);
  });
  it("adds each source's initial stub cost and starts with no incoming orientation",()=>{
    const graph={...grid([0,1,3],[0]),sources:[{point:[0,0] as GridPoint,initialCost:2},
      {point:[1,0] as GridPoint,initialCost:10}]};
    expect(search(graph)).toEqual({status:"found",points:[[0,0],[1,0],[3,0]],cost:5});
    expect(oracle(graph)).toEqual(search(graph));
    const vertical={...grid([0],[0,2]),sources:[{point:[0,0] as GridPoint,initialCost:7}]};
    expect(search(vertical)).toMatchObject({status:"found",cost:9});
  });
  it("keeps larger-g queue ties ahead of smaller-g seeds within a tight budget",()=>{
    const graph={...grid([0,1,2],[0]),sources:[{point:[0,0] as GridPoint,initialCost:0},
      {point:[1,0] as GridPoint,initialCost:1}]};
    expect(search(graph,{maxPops:2})).toEqual({status:"found",points:[[1,0],[2,0]],cost:2});
    // At the goal, horizontal arrival (state 10) beats vertical arrival (state 11).
    expect(search(grid([0,1],[0,1]))).toEqual({status:"found",points:[[0,0],[0,1],[1,1]],cost:20});
  });
  it("matches independent Dijkstra for every blocked-edge subset of integer and fractional grids",()=>{
    for(const [x,y] of [[[0,1,3],[0,2]],[[0,.5,3.25],[-.25,1.5]]]){
      const p=(i:number):GridPoint=>[x[i%3],y[Math.floor(i/3)]];
      const links=[[0,1],[1,2],[3,4],[4,5],[0,3],[1,4],[2,5]];
      for(let mask=0;mask<128;mask++){
        const graph={...grid(x,y),segmentVisible:allowed(links.filter((_,i)=>mask&(1<<i))
          .map(([a,b]):[GridPoint,GridPoint]=>[p(a),p(b)]))};
        const exact=oracle(graph),actual=search(graph,{heuristicWeight:1,maxPops:10000});
        expect(actual.status).toBe(exact.status);
        if(actual.status==="found"&&exact.status==="found"){
          expect(actual.cost).toBe(exact.cost);
          expect(actual.points.slice(1).every((q,i)=>graph.segmentVisible(actual.points[i],q))).toBe(true);
        }
      }
    }
  });
  it("distinguishes a fully drained frontier from an exhausted pop budget",()=>{
    const blocked={...grid([0,1],[0]),segmentVisible:()=>false};
    expect(search(blocked,{maxPops:0})).toEqual({status:"budget-exhausted"});
    expect(search(blocked,{maxPops:1})).toEqual({status:"unreachable"});
    expect(oracle(blocked)).toEqual({status:"unreachable"});
    expect(search(grid([0,1],[0]),{maxPops:1})).toEqual({status:"budget-exhausted"});
    expect(search(grid([0],[0]),{maxPops:0})).toEqual({status:"budget-exhausted"});
    expect(search(grid([0],[0]),{maxPops:1})).toMatchObject({status:"found",cost:0});
    const stale={...blocked,ends:[[1,0]] as GridPoint[],sources:[
      {point:[0,0] as GridPoint,initialCost:0},{point:[0,0] as GridPoint,initialCost:1},
      {point:[1,0] as GridPoint,initialCost:10}]};
    expect(search(stale,{maxPops:2})).toEqual({status:"budget-exhausted"});
    expect(search(stale,{maxPops:3})).toMatchObject({status:"found",cost:10});
  });
  it("caches edge decisions within a search, then rechecks a new occupancy snapshot",()=>{
    const occupied=vi.fn((a:GridPoint,b:GridPoint)=>a[0]<2&&b[0]<2);
    const graph={...grid([0,1,2],[0]),segmentVisible:occupied};
    expect(search(graph)).toEqual({status:"unreachable"}); // Includes reverse traversal of 0--1.
    expect(occupied).toHaveBeenCalledTimes(2);
    const clear=vi.fn(()=>true);
    expect(search({...graph,segmentVisible:clear})).toMatchObject({status:"found",cost:2});
    expect(clear).toHaveBeenCalledTimes(2);
  });
  it("minimizes over every end and repeated source costs",()=>{
    const graph={...grid([0,1,4],[0]),ends:[[0,0],[4,0]] as GridPoint[],
      sources:[{point:[1,0] as GridPoint,initialCost:2},{point:[1,0] as GridPoint,initialCost:9}]};
    for(const solve of [search,oracle])expect(solve(graph)).toEqual({status:"found",points:[[1,0],[0,0]],cost:3});
  });
  it("bounds oracle diagnostics before allocation and validates their cost/coordinate assumptions",()=>{
    expect(()=>oracle(grid(Array.from({length:ORACLE_MAX_STATES},(_,i)=>i),[0]))).toThrow(/limited/);
    for(const initialCost of [-1,NaN,Infinity])
      expect(()=>oracle({...grid(),sources:[{point:[0,0],initialCost}]})).toThrow(/finite costs/);
    for(const x of [[0,0],[1,0],[0,Infinity],[0,NaN],[]])expect(()=>oracle(grid(x))).toThrow(/coordinates/);
    expect(()=>oracle({...grid(),ends:[[5,2]]})).toThrow(/endpoints/);
    expect(()=>oracle(grid([-Number.MAX_VALUE,Number.MAX_VALUE],[0]))).toThrow(/finite costs/);
  });
});
