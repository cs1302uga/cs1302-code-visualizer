/** Reserve one stable declared-type column for the supplied execution states. */
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

export class TypeLabelLayout {
  private types: string[];
  private signature = "";
  private width = 0;
  constructor(trace: any[], shared: string[], trim: (type: string) => string) {
    this.types = [...new Set([...declaredTypes(trace), ...shared].map(trim))];
  }
  apply(root: HTMLElement): void {
    const label = root.querySelector<HTMLElement>(".stackFrameVar .fieldTypeLabel");
    if (!label) return;
    const style = getComputedStyle(label);
    const signature = [style.font, style.fontVariationSettings, style.letterSpacing,
      document.fonts?.status, style.font ? document.fonts?.check?.(style.font) : false].join("|");
    if (signature !== this.signature) {
      const probe = document.createElement("span");
      probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap";
      probe.style.font = style.font;
      probe.style.fontVariationSettings = style.fontVariationSettings;
      probe.style.letterSpacing = style.letterSpacing;
      root.append(probe);
      this.width = 0;
      for (const type of this.types) {
        probe.textContent = type;
        this.width = Math.max(this.width, Math.ceil(probe.getBoundingClientRect().width));
      }
      probe.remove();
      this.signature = signature;
    }
    root.style.setProperty("--type-label-width", `${this.width}px`);
  }
}
