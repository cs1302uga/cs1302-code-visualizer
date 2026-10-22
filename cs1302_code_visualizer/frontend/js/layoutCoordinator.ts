/** Per-visualizer ownership of preparation, bounded repair, measurement, and final paint. */
import { ConnectorRouting, ConnectorRoutePlan, ReferenceRoutingPolicy, RoutingConstraint } from "./connectorRouting";
import { clearConnectorPaint, ConnectorMeasurement, ConnectorPaintHost, measureConnectorScene, paintConnectorPlan } from "./connectorScene";
import { PlacementController } from "./placementModels";
import type { SvgConnection } from "./svgConnectors";

export type LayoutRepairKind = "blocker-translation" | "target-widening" | "source-widening" |
  "leading-padding" | "trailing-padding";
export type LayoutFailure = RoutingConstraint | {kind: "canvas-exhausted"; side: "leading" | "trailing"};

export class LayoutConstraintError extends Error {
  public constructor(public readonly constraint: LayoutFailure) {
    super(constraint.kind==="frame-parent" ?
      "Cannot route a frame-parent reference; inspect overlapping or constrained content" :
      "Cannot route a reference after bounded layout repair; inspect overlapping or constrained content");
    this.name="LayoutConstraintError";
  }
}

export interface LayoutRunDiagnostics {
  /** Routing attempts, including reservation-only retries and accepted-scene reuse. */
  attempts: number;
  measurementPasses: number;
  repairAttempts: number;
  reservationRetries: number;
  routeCacheHits: number;
  repairKinds: LayoutRepairKind[];
  searchTimings: {kind: string; ms: number}[];
  outcome: "idle" | "running" | "accepted" | "failed";
}

/** Inline properties are owned individually; restoration also works on detached elements. */
class RepairJournal {
  private entries:{element:HTMLElement; property:string; value:string; priority:string}[]=[];

  public write(element: HTMLElement, property: string, value: string): boolean {
    const style=element.style,old=style.getPropertyValue(property),priority=style.getPropertyPriority(property);
    if(old===value&&!priority)return false;
    // Journal before writing: even a throwing host setter cannot lose the old value.
    this.entries.push({element,property,value:old,priority});
    if(value)style.setProperty(property,value);else style.removeProperty(property);
    return true;
  }

  public restore(): void {
    const entries=this.entries;
    this.entries=[];
    for(let i=entries.length-1;i>=0;i--) {
      const {element,property,value,priority}=entries[i];
      if(value)element.style.setProperty(property,value,priority);else element.style.removeProperty(property);
    }
  }
}

function idleDiagnostics(): LayoutRunDiagnostics {
  return {attempts:0,measurementPasses:0,repairAttempts:0,reservationRetries:0,routeCacheHits:0,
    repairKinds:[],searchTimings:[],outcome:"idle"};
}

export class LayoutCoordinator {
  public readonly placement=new PlacementController();
  public diagnostics: LayoutRunDiagnostics=idleDiagnostics();
  private committedPlan?: ConnectorRoutePlan;
  private committedPlacementRevision=-1;
  private acceptedRouteCache?: {key:string;sceneKey:string;reserveTurns:boolean;plan:ConnectorRoutePlan};
  private readonly repairs=new RepairJournal();
  private preparation?:()=>void;
  private connections:readonly SvgConnection[]=[];

  public constructor(private readonly routing=new ConnectorRouting(), private readonly paintHost?: ConnectorPaintHost) {}

  /** Policy changes invalidate accepted paint even when routing is batched. */
  public invalidateRouting(): void {
    this.committedPlan=undefined;
    this.acceptedRouteCache=undefined;
    clearConnectorPaint(this.connections,this.paintHost);
  }

  /** Only a fully accepted run under the current placement revision. Never a route cache. */
  public get acceptedPlan(): ConnectorRoutePlan | undefined {
    return this.committedPlacementRevision===this.placement.revision?this.committedPlan:undefined;
  }

  /** Internal renderer adapter, not a new public visualizer policy option. */
  public configurePreparation(callback: ()=>void): void { this.preparation=callback; }

  /** Restore temporary repairs before intrinsic sizing and model placement. */
  public prepareLayout(): void {
    this.committedPlan=undefined;
    this.repairs.restore();
    this.placement.restore();
    try { this.preparation?.(); }
    catch(error) { this.acceptedRouteCache=undefined;clearConnectorPaint(this.connections,this.paintHost);throw error; }
  }

  /** Synchronous bounded settling; geometry writes always precede fresh measurement. */
  public settle(container: HTMLElement, connections: readonly SvgConnection[],
    policy: ReferenceRoutingPolicy="historical"): ConnectorRoutePlan {
    this.connections=connections;
    this.diagnostics={...idleDiagnostics(),outcome:"running"};
    const diagnostics=this.diagnostics;
    const measure=()=>{
      diagnostics.measurementPasses++;
      return measureConnectorScene(container,connections);
    };
    try {
      this.prepareLayout();
      let measured=measure(),attempt=0,reserveTurns=false,trailingPasses=0;
      while(true) {
        diagnostics.attempts++;
        // These are exactly the solver's dependencies, including ordered edge
        // IDs/indices, attachment widths and parent styles. Canvas/content are
        // independently revalidated below, even when their padding was restored.
        const {objects,heapOwners,text,textOwners,localEndpoints,edges}=measured.scene;
        const sceneKey=JSON.stringify(["coordinated-reference-routing-1",policy,this.placement.revision,
          objects,heapOwners,text,textOwners,localEndpoints,edges]);
        // An accepted reservation-only retry is canonical for this same scene,
        // so identical redraws need not rediscover the failed unreserved pass.
        if(this.acceptedRouteCache?.sceneKey===sceneKey)reserveTurns=this.acceptedRouteCache.reserveTurns;
        const key=JSON.stringify([sceneKey,reserveTurns]);
        const cached=this.acceptedRouteCache?.key===key?this.acceptedRouteCache.plan:undefined;
        const result=cached?{ok:true as const,plan:cached}:this.routing.plan(measured.scene,reserveTurns,policy);
        if(cached)diagnostics.routeCacheHits++;
        if(result.ok===false) {
          this.acceptedRouteCache=undefined;
          const constraint=result.constraint;
          if(constraint.kind==="reservation-retry") {
            reserveTurns=true;diagnostics.reservationRetries++;
            continue;
          }
          if(constraint.kind==="frame-parent"||attempt>=connections.length+4||!this.repair(measured,constraint))
            throw new LayoutConstraintError(constraint);
          attempt++;diagnostics.repairAttempts=attempt;
          measured=measure();reserveTurns=false;
          continue;
        }
        const plan=result.plan,ext=plan.extent;
        if(ext&&(ext.left<8||ext.top<8)) {
          if(attempt>=connections.length+6)throw new LayoutConstraintError({kind:"canvas-exhausted",side:"leading"});
          const style=getComputedStyle(container);
          this.repairs.write(container,"padding-left",`${(parseFloat(style.paddingLeft)||0)+Math.max(0,Math.ceil(8-ext.left))}px`);
          this.repairs.write(container,"padding-top",`${(parseFloat(style.paddingTop)||0)+Math.max(0,Math.ceil(8-ext.top))}px`);
          diagnostics.repairKinds.push("leading-padding");
          attempt++;diagnostics.repairAttempts=attempt;
          measured=measure();reserveTurns=false;
          continue;
        }
        // Trailing space normally changes only the canvas. If it changes geometry,
        // remeasure and reroute rather than publishing a plan for the old scene.
        if(this.allocateTrailing(container,measured,plan)) {
          diagnostics.repairKinds.push("trailing-padding");
          if(++trailingPasses>connections.length+6)throw new LayoutConstraintError({kind:"canvas-exhausted",side:"trailing"});
          measured=measure();reserveTurns=false;
          continue;
        }
        paintConnectorPlan(measured,plan,this.paintHost);
        freezePlan(plan);
        this.committedPlan=plan;
        this.committedPlacementRevision=this.placement.revision;
        this.acceptedRouteCache={key,sceneKey,reserveTurns,plan};
        diagnostics.searchTimings=cached?[]:plan.searchTimings;
        diagnostics.outcome="accepted";
        return plan;
      }
    } catch(error) {
      this.committedPlan=undefined;
      this.acceptedRouteCache=undefined;
      diagnostics.outcome="failed";
      this.repairs.restore();
      clearConnectorPaint(connections,this.paintHost);
      throw error;
    }
  }

  private repair(measured: ConnectorMeasurement, constraint: Exclude<RoutingConstraint,
    {kind:"reservation-retry"}|{kind:"frame-parent"}>): boolean {
    const {scene,bindings}=measured;
    const edge=scene.edges[constraint.edgeIndex],a=edge.attachment;
    if(constraint.kind==="covered-source") {
      const owner=constraint.blockerOwners[0],blocker=bindings.owners[owner];
      if(blocker) {
        const dy=a.enclosure.bottom-scene.objects[owner].top+16;
        this.repairs.write(blocker,"translate",`0px ${Math.max(16,dy)}px`);
        this.diagnostics.repairKinds.push("blocker-translation");
        return true;
      }
    }
    if(constraint.kind==="no-candidate"&&constraint.sourceCanExit) {
      const target=bindings.targetBodies.get(edge.connectionIndex)!;
      this.repairs.write(target,"min-width",`${Math.max(Math.ceil(a.target.right-a.target.left)+24,
        constraint.targetCapacity??0)}px`);
      this.diagnostics.repairKinds.push("target-widening");
      return true;
    }
    const box=bindings.sourceBoxes.get(edge.connectionIndex);
    if(box) {
      this.repairs.write(box,"min-width",`${Math.ceil(a.sourceBox.right-a.sourceBox.left)+24}px`);
      this.diagnostics.repairKinds.push("source-widening");
      return true;
    }
    return false;
  }

  private allocateTrailing(container: HTMLElement, measured: ConnectorMeasurement, plan: ConnectorRoutePlan): boolean {
    const ext=plan.extent,content=measured.scene.content,style=getComputedStyle(container);
    const bottom=ext?`${Math.max(0,Math.ceil(ext.bottom-content.bottom+8))}px`:"";
    const right=ext?`${Math.max(0,Math.ceil(ext.right-content.right+8))}px`:"";
    const oldBottom=style.paddingBottom,oldRight=style.paddingRight;
    const wroteBottom=this.repairs.write(container,"padding-bottom",bottom);
    const wroteRight=this.repairs.write(container,"padding-right",right);
    // Setting an absent zero inline value does not alter measured geometry.
    // For removals, compare the resulting computed value with the old value.
    const after=(!bottom||!right)?getComputedStyle(container):undefined;
    return (wroteBottom&&(parseFloat(oldBottom)||0)!==(parseFloat(bottom||after!.paddingBottom)||0))||
      (wroteRight&&(parseFloat(oldRight)||0)!==(parseFloat(right||after!.paddingRight)||0));
  }

  /** Reset repair/model effects without discarding the renderer's preparation adapter. */
  public reset(connections: readonly SvgConnection[]=this.connections): void {
    this.repairs.restore();
    this.placement.restore();
    clearConnectorPaint(connections,this.paintHost);
    this.connections=[];this.committedPlan=undefined;this.committedPlacementRevision=-1;
    this.acceptedRouteCache=undefined;
    this.diagnostics=idleDiagnostics();
  }

  public dispose(): void {
    this.reset();
    this.placement.dispose();
    this.preparation=undefined;
  }
}

/** Cached routes are data, and consumers cannot mutate their geometry after acceptance. */
function freezePlan(value: unknown): void {
  if(!value||typeof value!=="object"||Object.isFrozen(value))return;
  for(const child of Object.values(value))freezePlan(child);
  Object.freeze(value);
}
