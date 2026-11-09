import { afterEach, describe, expect, it, vi } from "vitest";
import { ConnectorRouting, MeasuredConnectorScene } from "../js/connectorRouting";
import { measureConnectorScene } from "../js/connectorScene";
import { LayoutConstraintError } from "../js/layoutCoordinator";
import { LegacyStackGlobalsPlacement } from "../js/placementModels";
import { SvgConnectorManager } from "../js/svgConnectors";
import { pathData } from "../js/referenceRouting";
import { replay, textHits } from "./routingFixture";

/** Dynamic geometry responds to the actual coordinator's owned inline writes. */
function scene(options: {foreignText?: boolean; ownText?: boolean; sourceLeft?: number; parent?: boolean}={}) {
  document.body.innerHTML='<div id="scene"><div id="frame" class="stackFrame">'+
    '<span id="source" class="value-box">source</span></div>'+
    '<div id="target" class="heapObject"></div>'+
    '<div id="blocker" class="heapObject"><span id="cover">cover</span></div></div>';
  const container=document.getElementById("scene")!;
  const frame=document.getElementById("frame")!,source=document.getElementById("source")!;
  const target=document.getElementById("target")!,blocker=document.getElementById("blocker")!;
  const cover=document.getElementById("cover")!;
  const state={ownText:!!options.ownText,foreignText:!!options.foreignText,textWidth:60,
    targetLeft:200,sourceLeft:options.sourceLeft??40,throwAtWidth:Infinity};
  const px=(property:string)=>parseFloat(container.style.getPropertyValue(property))||0;
  const shift=()=>({x:px("padding-left"),y:px("padding-top")});
  const translated=()=>blocker.style.translate.split(/\s+/).map(parseFloat);
  const sourceRect=()=>{
    const width=Math.max(40,parseFloat(source.style.minWidth)||0),{x,y}=shift();
    if(width>=state.throwAtWidth)throw new Error("late measurement failure");
    return new DOMRect(state.sourceLeft+x,40+y,width,19);
  };
  vi.spyOn(container,"getBoundingClientRect").mockImplementation(()=>new DOMRect(0,0,
    400+px("padding-left")+px("padding-right"),200+px("padding-top")+px("padding-bottom")));
  vi.spyOn(frame,"getBoundingClientRect").mockImplementation(()=>{
    const {x,y}=shift();return new DOMRect(state.sourceLeft-20+x,20+y,80,60);
  });
  vi.spyOn(source,"getBoundingClientRect").mockImplementation(sourceRect);
  vi.spyOn(target,"getBoundingClientRect").mockImplementation(()=>{
    const {x,y}=shift();return new DOMRect(state.targetLeft+x,30+y,Math.max(70,parseFloat(target.style.minWidth)||0),50);
  });
  vi.spyOn(blocker,"getBoundingClientRect").mockImplementation(()=>{
    const {x,y}=shift(),[tx,ty]=translated();return new DOMRect(65+x+(tx||0),38+y+(ty||0),40,20);
  });
  if(!Range.prototype.getClientRects)Object.defineProperty(Range.prototype,"getClientRects",{
    configurable:true,value:()=>[],
  });
  vi.spyOn(Range.prototype,"getClientRects").mockImplementation(function(this:Range) {
    const parent=this.commonAncestorContainer.parentElement,{x,y}=shift();
    if(parent===source&&state.ownText)return [new DOMRect(state.sourceLeft+7+x,42+y,state.textWidth,12)] as any;
    if(parent===cover&&state.foreignText) {
      const [tx,ty]=translated();return [new DOMRect(68+x+(tx||0),43+y+(ty||0),10,12)] as any;
    }
    return [] as any;
  });
  const manager=new SvgConnectorManager({Container:container});
  const connect=()=>manager.connect({source:options.parent?frame:source,target,
    ...(options.parent?{scope:"frameParentPointer",anchors:["RightMiddle","RightMiddle"] as [string,string]}:{})});
  return {container,frame,source,target,blocker,manager,state,connect};
}

function painted(manager: SvgConnectorManager) {
  return Object.fromEntries(manager.connections.map(c=>[c.sourceId,{
    path:c.pathElement.getAttribute("d"),head:c.arrowElement.getAttribute("points"),
    x:c.dotElement.getAttribute("cx"),y:c.dotElement.getAttribute("cy"),kind:c.pathElement.dataset.routing,
  }]));
}

function freeze<T>(value:T):T {
  if(value&&typeof value==="object") {
    Object.freeze(value);
    Object.values(value).forEach(freeze);
  }
  return value;
}

afterEach(()=>{vi.restoreAllMocks();document.body.innerHTML="";});

describe("production layout coordination",()=>{
  it.each(["aliases-default","cycle-default","self-loop-default","arrays-compact"])(
    "routes the real measured %s scene deterministically through the default coordinator",name=>{
      const {manager,data}=replay(name);
      const first=painted(manager),coordinator=manager.layoutCoordinator;
      expect(coordinator.diagnostics.outcome).toBe("accepted");
      expect(coordinator.diagnostics.attempts).toBeGreaterThan(0);
      expect(coordinator.acceptedPlan?.connectors).toHaveLength(data.connectors.length);
      expect(textHits(manager,data.texts)).toEqual([]);
      manager.connections.reverse();manager.repaintEverything();
      expect(painted(manager)).toEqual(first);
      const endpoints=manager.connections.map(c=>({source:c.sourceId,target:c.targetId}));
      manager.reset();manager.beginBatch();
      endpoints.forEach(e=>manager.connect(e));manager.endBatch();
      expect(painted(manager)).toEqual(first);
      manager.dispose();
    });

  it("gives the pure planner geometry/IDs only and never reads or changes DOM",()=>{
    const {manager,container}=replay("aliases-default");
    const measured=measureConnectorScene(container,manager.connections);
    const input=freeze(JSON.parse(JSON.stringify(measured.scene)) as MeasuredConnectorScene);
    const before=JSON.stringify(input),markup=container.innerHTML;
    const read=vi.spyOn(Element.prototype,"getBoundingClientRect").mockImplementation(()=>{throw new Error("DOM read in solver");});
    const style=vi.spyOn(window,"getComputedStyle").mockImplementation(()=>{throw new Error("style read in solver");});
    const write=vi.spyOn(Element.prototype,"setAttribute").mockImplementation(()=>{throw new Error("DOM write in solver");});
    const planner=new ConnectorRouting();
    let result=planner.plan(input);
    if(result.ok===false&&result.constraint.kind==="reservation-retry")result=planner.plan(input,true);
    expect(result.ok).toBe(true);
    expect(JSON.stringify(input)).toBe(before);
    read.mockRestore();style.mockRestore();write.mockRestore();
    expect(container.innerHTML).toBe(markup);
    if(result.ok)for(const planned of result.plan.connectors) {
      const c=manager.connections[planned.connectionIndex];
      expect(pathData(planned.route)).toBe(c.pathElement.getAttribute("d"));
    }
  });

  it("returns a typed covered-source constraint without publishing a partial route",()=>{
    const f=scene({foreignText:true});
    f.manager.beginBatch();f.connect();
    const measured=measureConnectorScene(f.container,f.manager.connections);
    const markup=f.container.innerHTML;
    const result=new ConnectorRouting().plan(measured.scene);
    expect(result).toMatchObject({ok:false,constraint:{kind:"covered-source",edgeIndex:0}});
    if(result.ok===false&&result.constraint.kind==="covered-source")
      expect(result.constraint.blockerOwners).toEqual([2]);
    expect(f.container.innerHTML).toBe(markup);
    f.manager.cancelBatch();
  });

  it("translates a heap blocker covering a stack source and remeasures before final paint",()=>{
    const f=scene({foreignText:true});
    f.blocker.style.setProperty("translate","2px 3px","important");
    const c=f.connect();
    expect(f.manager.layoutCoordinator.diagnostics.repairKinds).toContain("blocker-translation");
    expect(f.manager.layoutCoordinator.diagnostics.measurementPasses).toBeGreaterThan(1);
    expect(c.groupElement.style.display).toBe("");
    const first=painted(f.manager),translation=f.blocker.style.translate;
    expect(translation).not.toBe("2px 3px");
    f.manager.repaintEverything();
    expect(painted(f.manager)).toEqual(first);
    expect(f.blocker.style.translate).toBe(translation);
    f.blocker.remove();f.manager.reset();
    expect(f.blocker.style.translate).toBe("2px 3px");
    expect(f.blocker.style.getPropertyPriority("translate")).toBe("important");
    expect(f.manager.layoutCoordinator.acceptedPlan).toBeUndefined();
  });

  it("restores exact inline values/priorities after a late failure following two owned writes",()=>{
    const f=scene();
    f.source.style.setProperty("min-width","40px","important");
    f.container.style.setProperty("padding-right","7px","important");
    const c=f.connect();
    expect(c.pathElement.getAttribute("d")).not.toBe("");
    f.state.ownText=true;f.state.throwAtWidth=88;
    expect(()=>f.manager.repaintEverything()).toThrow("late measurement failure");
    const coordinator=f.manager.layoutCoordinator;
    expect(coordinator.diagnostics.repairKinds.filter(k=>k==="source-widening")).toHaveLength(2);
    expect(coordinator.diagnostics.outcome).toBe("failed");
    expect(f.source.style.minWidth).toBe("40px");
    expect(f.source.style.getPropertyPriority("min-width")).toBe("important");
    expect(f.container.style.paddingRight).toBe("7px");
    expect(f.container.style.getPropertyPriority("padding-right")).toBe("important");
    expect(c.groupElement.style.display).toBe("none");
    expect(c.pathElement.getAttribute("d")).toBe("");
    expect(c.arrowElement.getAttribute("points")).toBe("");
    expect(c.pathElement.dataset.routing).toBeUndefined();
    expect(coordinator.acceptedPlan).toBeUndefined();
    // A failed pass cannot leave a reusable route or repair behind.
    f.state.ownText=false;f.state.throwAtWidth=Infinity;f.manager.repaintEverything();
    expect(c.groupElement.style.display).toBe("");
    expect(coordinator.acceptedPlan).toBeDefined();
    f.manager.reset();
    expect(f.source.style.getPropertyPriority("min-width")).toBe("important");
  });

  it("rolls back on bounded local exhaustion and can subsequently route revised geometry",()=>{
    const f=scene({ownText:true});
    f.source.style.setProperty("min-width","40px","important");
    f.state.textWidth=5000;
    expect(()=>f.connect()).toThrow(LayoutConstraintError);
    expect(f.manager.layoutCoordinator.diagnostics.repairAttempts).toBe(f.manager.connections.length+4);
    expect(f.source.style.minWidth).toBe("40px");
    expect(f.source.style.getPropertyPriority("min-width")).toBe("important");
    expect(f.manager.layoutCoordinator.acceptedPlan).toBeUndefined();
    f.state.ownText=false;f.state.targetLeft=275;f.manager.repaintEverything();
    expect(f.manager.layoutCoordinator.diagnostics.outcome).toBe("accepted");
    expect(f.manager.connections[0].arrowElement.getAttribute("points")).toContain("275,");
  });

  it("keeps the sized model-placed baseline on route failure, then restores model effects on reset",()=>{
    const f=scene({ownText:true}),coordinator=f.manager.layoutCoordinator;
    const legacy=new LegacyStackGlobalsPlacement();
    coordinator.placement.use({stackGlobals:{
      id:"baseline-stack",version:"1",plan:context=>legacy.plan(context),
      place:()=>[{key:"stack",styles:{"margin-top":"13px"}}],
    }});
    const selection=coordinator.placement.select([{stack_to_render:[],ordered_globals:[]}],0,{},()=>[]);
    coordinator.configurePreparation(()=>{
      f.source.style.setProperty("min-width","40px","important");
      coordinator.placement.place(selection,{
        dimensions:{stackGlobals:[{key:"stack",left:20,top:20,width:80,height:60}],heap:[]},
        apply:(region,effects,journal)=>{
          if(effects.length)expect(region).toBe("stackGlobals");
          for(const effect of effects)for(const [property,value] of Object.entries(effect.styles))
            journal.style(f.frame,property,value);
        },
        legacyHeap:()=>{},
      });
    });
    f.state.throwAtWidth=88;
    expect(()=>f.connect()).toThrow("late measurement failure");
    expect(coordinator.diagnostics.repairKinds.filter(k=>k==="source-widening")).toHaveLength(2);
    expect(f.source.style.minWidth).toBe("40px");
    expect(f.source.style.getPropertyPriority("min-width")).toBe("important");
    expect(f.frame.style.marginTop).toBe("13px");
    f.manager.reset();expect(f.frame.style.marginTop).toBe("");
  });

  it("allocates leading canvas space using fresh measurements and restores it on dispose",()=>{
    const f=scene({sourceLeft:-30});
    f.container.style.setProperty("padding-left","2px","important");
    const c=f.connect();
    expect(f.manager.layoutCoordinator.diagnostics.repairKinds).toContain("leading-padding");
    expect(f.manager.layoutCoordinator.diagnostics.measurementPasses).toBeGreaterThan(1);
    expect(Number(c.dotElement.getAttribute("cx"))).toBeGreaterThanOrEqual(8);
    f.container.remove();f.manager.dispose();
    expect(f.container.style.paddingLeft).toBe("2px");
    expect(f.container.style.getPropertyPriority("padding-left")).toBe("important");
    expect(f.manager.svgCanvas.parentNode).toBeNull();
    expect(f.manager.layoutCoordinator.diagnostics.outcome).toBe("idle");
  });

  it("defers preparation and routing until batch end, and cancels without routing partial DOM",()=>{
    const f=scene(),preparation=vi.fn();
    f.manager.layoutCoordinator.configurePreparation(preparation);
    const planner=vi.spyOn(ConnectorRouting.prototype,"plan");
    f.manager.beginBatch();f.manager.beginBatch();const c=f.connect();
    expect(planner).not.toHaveBeenCalled();expect(preparation).not.toHaveBeenCalled();
    expect(c.groupElement.style.display).toBe("none");
    f.manager.endBatch();expect(planner).not.toHaveBeenCalled();
    f.manager.endBatch();expect(preparation).toHaveBeenCalledTimes(1);
    expect(planner).toHaveBeenCalled();
    planner.mockClear();preparation.mockClear();
    f.manager.beginBatch();const partial=f.connect();f.manager.cancelBatch();
    expect(planner).not.toHaveBeenCalled();expect(preparation).not.toHaveBeenCalled();
    expect(f.manager.connections.every(c=>c.groupElement.style.display==="none")).toBe(true);
    partial.detach();
    f.manager.repaintEverything();expect(preparation).toHaveBeenCalledTimes(1);
  });

  it("matches cold/direct/backward redraws and responds to geometry and stroke changes",()=>{
    const f=scene(),c=f.connect();
    const first=painted(f.manager);
    f.state.targetLeft=290;f.manager.repaintEverything();
    const other=painted(f.manager);
    expect(other).not.toEqual(first);
    f.state.targetLeft=200;f.manager.repaintEverything();expect(painted(f.manager)).toEqual(first);
    c.setHoverPaintStyle({lineWidth:5});
    expect(f.manager.layoutCoordinator.acceptedPlan!.connectors[0].attachment.width).toBe(5);
    c.setHoverPaintStyle({lineWidth:1});
    expect(painted(f.manager)).toEqual(first);
    const prior=f.manager.layoutCoordinator.acceptedPlan;
    f.manager.layoutCoordinator.placement.invalidate({horizon:"selected snapshots"});
    expect(f.manager.layoutCoordinator.acceptedPlan).toBeUndefined();
    f.manager.repaintEverything();
    expect(f.manager.layoutCoordinator.acceptedPlan).not.toBe(prior);
    expect(painted(f.manager)).toEqual(first);
    f.manager.dispose();
    const cold=scene();cold.connect();expect(painted(cold.manager)).toEqual(first);
  });

  it.each([false,true])("remeasures trailing canvas allocation and reroutes only when geometry changes (%s)",movesTarget=>{
    const f=scene({parent:true,sourceLeft:120});
    if(movesTarget)vi.spyOn(f.target,"getBoundingClientRect").mockImplementation(()=>
      new DOMRect(200+(parseFloat(f.container.style.paddingRight)||0),30,70,50));
    const planner=vi.spyOn(ConnectorRouting.prototype,"plan");
    const c=f.connect(),coordinator=f.manager.layoutCoordinator;
    expect(coordinator.diagnostics.repairKinds).toContain("trailing-padding");
    expect(coordinator.diagnostics.measurementPasses).toBe(2);
    expect(planner).toHaveBeenCalledTimes(movesTarget?2:1);
    expect(coordinator.acceptedPlan!.connectors[0].attachment.target.right).toBe(f.target.getBoundingClientRect().right);
    expect(c.groupElement.style.display).toBe("");
  });

  it("reuses only accepted measured scenes and invalidates reuse on failure/revision/geometry",()=>{
    const f=scene();f.connect();
    const planner=vi.spyOn(ConnectorRouting.prototype,"plan");
    f.manager.repaintEverything();
    expect(planner).not.toHaveBeenCalled();
    expect(f.manager.layoutCoordinator.diagnostics.routeCacheHits).toBe(1);
    f.state.targetLeft=280;f.manager.repaintEverything();
    expect(planner).toHaveBeenCalled();planner.mockClear();
    f.manager.layoutCoordinator.placement.invalidate({canonical:"new supplied context"});
    f.manager.repaintEverything();expect(planner).toHaveBeenCalled();planner.mockClear();
    f.state.ownText=true;f.state.throwAtWidth=88;
    expect(()=>f.manager.repaintEverything()).toThrow("late measurement failure");
    expect(f.manager.layoutCoordinator.acceptedPlan).toBeUndefined();
    f.state.ownText=false;f.state.throwAtWidth=Infinity;planner.mockClear();
    f.manager.repaintEverything();
    expect(planner).toHaveBeenCalled();
    expect(f.manager.layoutCoordinator.diagnostics.routeCacheHits).toBe(0);
    f.manager.reset();planner.mockClear();
    f.connect();expect(planner).toHaveBeenCalled();
  });
});
