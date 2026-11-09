/** Internal region strategies. Frame keys describe rendering, not invocation lifetimes. */
export type HeapPlacementPlan = readonly (readonly (string | number)[])[];

export interface StackGlobalsPlan {
  readonly frames: readonly any[];
  readonly globals: readonly string[];
  readonly showGlobals: boolean;
}

export interface PlacementContext {
  /** Only the supplied snapshots are available; omitted history is not inferred. */
  readonly sequence: readonly any[];
  readonly state: any;
  readonly index: number;
  readonly options: Readonly<Record<string, any>>;
  readonly models: {
    readonly stackGlobals: { readonly id: string; readonly version: string };
    readonly heap: { readonly id: string; readonly version: string };
  };
  readonly canonical: {
    readonly revision: number;
    readonly supplied: unknown;
  };
}

export interface PlacementBox {
  readonly key: string;
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

export interface PlacementDimensions {
  readonly stackGlobals: readonly PlacementBox[];
  readonly heap: readonly PlacementBox[];
}

/** Keys come from the region's measured boxes; models never need DOM elements. */
export interface PlacementEffect {
  readonly key: string;
  readonly styles: Readonly<Record<string, string>>;
}

export interface StackGlobalsPlacementModel {
  readonly id: string;
  readonly version: string;
  plan(context: PlacementContext & { readonly predecessor?: StackGlobalsPlan }): StackGlobalsPlan;
  place?(context: PlacementContext & {
    readonly plan: StackGlobalsPlan;
    readonly dimensions: PlacementDimensions;
  }): readonly PlacementEffect[];
}

export interface HeapPlacementModel {
  readonly id: string;
  readonly version: string;
  plan(context: PlacementContext & { readonly predecessor?: HeapPlacementPlan },
    legacy: () => HeapPlacementPlan): HeapPlacementPlan;
  /** The legacy nudge observes the intrinsic DOM before labels/values are sized. */
  prepare?(context: PlacementContext, legacy: () => void): void;
  place?(context: PlacementContext & {
    readonly plan: HeapPlacementPlan;
    readonly dimensions: PlacementDimensions;
  }, legacy: () => void): readonly PlacementEffect[];
}

export class LegacyStackGlobalsPlacement implements StackGlobalsPlacementModel {
  readonly id = "legacy-stack-globals";
  readonly version = "1";

  plan({ state }: PlacementContext): StackGlobalsPlan {
    // Java activation already reverses the cloned supplied arrays exactly once.
    return {
      frames: [...(state.stack_to_render ?? [])],
      globals: [...(state.ordered_globals ?? [])],
      showGlobals: (state.ordered_globals ?? []).length > 0,
    };
  }
}

export class LegacyHeapPlacement implements HeapPlacementModel {
  readonly id = "legacy-heap";
  readonly version = "1";

  plan(_context: PlacementContext, legacy: () => HeapPlacementPlan): HeapPlacementPlan {
    return legacy();
  }

  prepare(_context: PlacementContext, legacy: () => void): void { legacy(); }

  place(_context: PlacementContext, legacy: () => void): readonly PlacementEffect[] {
    legacy();
    return [];
  }
}

/** Placement writes have their own lifetime, independent of temporary route repairs. */
export class PlacementJournal {
  private restores: (() => void)[] = [];

  style(element: HTMLElement, property: string, value: string): void {
    const previous = element.style.getPropertyValue(property);
    const priority = element.style.getPropertyPriority(property);
    element.style.setProperty(property, value);
    const written = element.style.getPropertyValue(property);
    const writtenPriority = element.style.getPropertyPriority(property);
    this.restores.push(() => {
      // Preserve a newer explicit user change, including an in-progress drag.
      if (element.classList.contains("ui-draggable-dragging")) return;
      if (element.style.getPropertyValue(property) !== written ||
          element.style.getPropertyPriority(property) !== writtenPriority) return;
      if (previous) element.style.setProperty(property, previous, priority);
      else element.style.removeProperty(property);
    });
  }

  attribute(element: HTMLElement, name: string, value: string): void {
    const previous = element.getAttribute(name);
    element.setAttribute(name, value);
    const written = element.getAttribute(name);
    this.restores.push(() => {
      if (element.classList.contains("ui-draggable-dragging")) return;
      if (element.getAttribute(name) !== written) return;
      if (previous === null) element.removeAttribute(name);
      else element.setAttribute(name, previous);
    });
  }

  restore(): void {
    for (let index = this.restores.length - 1; index >= 0; index--) this.restores[index]();
    this.restores = [];
  }
}

export interface PlacementSelection {
  readonly context: PlacementContext;
  readonly stackGlobals: StackGlobalsPlan;
  readonly heap: HeapPlacementPlan;
}

export interface PlacementHost {
  readonly dimensions: PlacementDimensions;
  readonly options?: Readonly<Record<string, any>>;
  apply(region: "stackGlobals" | "heap", effects: readonly PlacementEffect[], journal: PlacementJournal): void;
  legacyHeap(journal: PlacementJournal): void;
}

/** One visualizer's semantic plans and reversible model positioning. No navigation seed. */
export class PlacementController {
  private stackModel: StackGlobalsPlacementModel = new LegacyStackGlobalsPlacement();
  private heapModel: HeapPlacementModel = new LegacyHeapPlacement();
  private journal = new PlacementJournal();
  private contextRevision = 0;
  private suppliedContext: unknown;
  private sequence: readonly any[];
  private signature = "";
  private selections: PlacementSelection[] = [];

  get revision(): number { return this.contextRevision; }

  use(models: { stackGlobals?: StackGlobalsPlacementModel; heap?: HeapPlacementModel }): void {
    if (models.stackGlobals) this.stackModel = models.stackGlobals;
    if (models.heap) this.heapModel = models.heap;
    this.invalidate();
  }

  /** Call after in-place trace/context changes. Options/model versions are checked on select. */
  invalidate(suppliedContext: unknown = this.suppliedContext): void {
    this.restore();
    this.suppliedContext = suppliedContext;
    this.contextRevision++;
    this.signature = "";
    this.selections = [];
  }

  select(sequence: readonly any[], index: number, options: Readonly<Record<string, any>>,
    legacyHeap: (context: PlacementContext & { readonly predecessor?: HeapPlacementPlan }) => HeapPlacementPlan,
  ): PlacementSelection {
    if (!Number.isInteger(index) || index < 0 || index >= sequence.length)
      throw new RangeError("Placement state index is outside the supplied sequence");
    const dependencies = () => JSON.stringify([this.contextRevision,
      this.stackModel.id, this.stackModel.version, this.heapModel.id, this.heapModel.version, options]);
    let signature = dependencies();
    if (sequence !== this.sequence || signature !== this.signature) {
      if (this.selections.length) {
        this.restore();
        this.contextRevision++;
        signature = dependencies();
      }
      this.selections = [];
      this.signature = "";
      // Build from the first supplied snapshot, even for a cold seek to the final state.
      // The two models receive their OWN canonical predecessor, never each other's proposal.
      const selections: PlacementSelection[] = [];
      const optionSnapshot = Object.freeze({ ...options });
      for (let current = 0; current < sequence.length; current++) {
        const context: PlacementContext = {
          sequence, state: sequence[current], index: current, options: optionSnapshot,
          models: Object.freeze({
            stackGlobals: Object.freeze({ id: this.stackModel.id, version: this.stackModel.version }),
            heap: Object.freeze({ id: this.heapModel.id, version: this.heapModel.version }),
          }),
          canonical: Object.freeze({ revision: this.contextRevision, supplied: this.suppliedContext }),
        };
        const previous = selections[current - 1];
        const stack = this.stackModel.plan({ ...context, predecessor: previous?.stackGlobals });
        const heapContext = { ...context, predecessor: previous?.heap };
        const heap = this.heapModel.plan(heapContext, () => legacyHeap(heapContext));
        // Freeze owned containers so a later model call cannot mutate a canonical predecessor.
        const stackGlobals = Object.freeze({ ...stack,
          frames: Object.freeze([...stack.frames]), globals: Object.freeze([...stack.globals]) });
        selections.push(Object.freeze({ context, stackGlobals,
          heap: Object.freeze(heap.map(row => Object.freeze([...row]))) }));
      }
      this.sequence = sequence;
      this.signature = signature;
      this.selections = selections;
    }
    return this.selections[index];
  }

  plans(): readonly PlacementSelection[] { return this.selections; }

  prepareHeap(selection: PlacementSelection, legacy: (journal: PlacementJournal) => void): void {
    try { this.heapModel.prepare?.(selection.context, () => legacy(this.journal)); }
    catch (error) { this.restore(); throw error; }
  }

  place(selection: PlacementSelection, host: PlacementHost): void {
    try {
      const context = { ...selection.context, options: host.options ?? selection.context.options,
        dimensions: host.dimensions };
      host.apply("stackGlobals", this.stackModel.place?.({ ...context, plan: selection.stackGlobals }) ?? [], this.journal);
      host.apply("heap", this.heapModel.place?.({ ...context, plan: selection.heap },
        () => host.legacyHeap(this.journal)) ?? [], this.journal);
    } catch (error) {
      this.restore();
      throw error;
    }
  }

  restore(): void { this.journal.restore(); }

  dispose(): void {
    this.invalidate(undefined);
    this.suppliedContext = undefined;
    this.sequence = undefined;
    this.stackModel = new LegacyStackGlobalsPlacement();
    this.heapModel = new LegacyHeapPlacement();
  }
}
