/** Collect stack/global declared types across the supplied execution states. */
export function declaredTypes(trace: any[]): string[] {
  const types = new Set<string>();
  const add = (type: unknown) => {
    for (const value of Array.isArray(type) ? type : [type]) {
      if (typeof value === "string") types.add(value);
    }
  };
  for (const state of trace) {
    for (const attrs of Object.values(state.globals_attrs ?? {}) as any[]) add(attrs?.type);
    for (const frame of state.stack_to_render ?? []) {
      for (const attrs of Object.values(frame.locals_attrs ?? {}) as any[]) add(attrs?.type);
    }
  }
  return [...types].sort();
}

/** Measure both label columns once per font configuration, across the whole trace. */
export class StackLabelLayout {
  private columns: {
    selector: string;
    property: string;
    labels: string[];
    signature: string;
    width: number;
  }[];

  constructor(trace: any[], sharedTypes: string[], trim: (type: string) => string) {
    const names = trace.flatMap(state => [
      ...(state.ordered_globals ?? []),
      ...(state.stack_to_render ?? []).flatMap(frame =>
        (frame.ordered_varnames ?? []).flatMap(name =>
          name === "__return__" ? ["Return", "value"] : [name])),
    ]).filter(name => typeof name === "string");
    this.columns = [
      {
        selector: ".stackFrameVar .fieldTypeLabel",
        property: "--type-label-width",
        labels: [...new Set([...declaredTypes(trace), ...sharedTypes].map(trim))],
        signature: "", width: 0,
      },
      {
        selector: ".stackVarName",
        property: "--stack-name-width",
        labels: [...new Set<string>(names)],
        signature: "", width: 0,
      },
    ];
  }

  apply(root: HTMLElement): void {
    for (const column of this.columns) {
      const label = root.querySelector<HTMLElement>(column.selector);
      if (!label) continue;
      const style = getComputedStyle(label);
      const signature = [style.font, style.fontVariationSettings, style.letterSpacing,
        document.fonts?.status, style.font ? document.fonts?.check?.(style.font) : false].join("|");
      if (signature !== column.signature) {
        const probe = document.createElement("span");
        probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap";
        probe.style.font = style.font;
        probe.style.fontVariationSettings = style.fontVariationSettings;
        probe.style.letterSpacing = style.letterSpacing;
        root.append(probe);
        column.width = 0;
        for (const text of column.labels) {
          probe.textContent = text;
          column.width = Math.max(column.width, Math.ceil(probe.getBoundingClientRect().width));
        }
        probe.remove();
        column.signature = signature;
      }
      root.style.setProperty(column.property, `${column.width}px`);
    }
  }
}
