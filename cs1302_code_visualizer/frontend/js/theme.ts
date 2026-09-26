/** Shared semantic paints for the live renderer and portable SVG exports. */
export const palettes = {
  light: {
    canvas: "#ffffff", stack: "#f8f9fb", activeStack: "#eff3fa",
    object: "#e9edf3", value: "#e6efff", text: "#1e1e1e",
    muted: "#454950", border: "#718096", arrow: "#2757dd",
    inactiveArrow: "#788496", special: "#8a1c3a",
  },
  dark: {
    canvas: "#131416", stack: "#1a1c1e", activeStack: "#1c2736",
    object: "#252b34", value: "#233754", text: "#cfd0d0",
    muted: "#c9cdd3", border: "#8b98aa", arrow: "#5ca5ff",
    inactiveArrow: "#758397", special: "#ffd0dc",
  },
} as const;

export type PaintRole = keyof typeof palettes.light;
export type Theme = "light" | "dark" | "auto";

/** Public variables inherit from a host; private defaults follow the theme. */
export function paint(role: PaintRole): string {
  return `var(--codevis-${role}, var(--_codevis-${role}, ${palettes.light[role]}))`;
}

const roots = ":is(.ExecutionVisualizer, .codevis-render-page, .codevis-json, svg.codevis-diagram)";
function defaults(theme: "light" | "dark", important = false): string {
  return Object.entries(palettes[theme]).map(([role, color]) =>
    `--_codevis-${role}:${color}${important ? " !important" : ""};`
  ).join("");
}

/** Scoped rules also work when several exported SVGs share one document. */
export const themeCss = `
${roots} { ${defaults("light")} }
[data-theme="dark"] ${roots}:not([data-codevis-theme]),
${roots}[data-codevis-theme="dark"] { ${defaults("dark")} }
@media (prefers-color-scheme: dark) {
  [data-theme="auto"] ${roots}:not([data-codevis-theme="light"]):not([data-codevis-theme="dark"]),
  ${roots}[data-codevis-theme="auto"] { ${defaults("dark")} }
}
/* An explicit instance choice wins over both the host and the OS preference. */
${roots}[data-codevis-theme="light"] { ${defaults("light")} }
${roots}[data-codevis-theme="dark"] { ${defaults("dark")} }
svg.codevis-diagram:not(:root) { --_codevis-canvas: transparent !important; }
${Object.keys(palettes.light).map(role => `
svg.codevis-diagram [data-codevis-fill="${role}"] { fill: ${paint(role as PaintRole)}; }
svg.codevis-diagram [data-codevis-stroke="${role}"] { stroke: ${paint(role as PaintRole)}; }
`).join("")}
@media print {
  ${roots} { ${defaults("light", true)} }
}
`;

// Keep export classification and DOM styling together. First matching role wins.
const surfaces: [PaintRole, string][] = [
  ["activeStack", ".highlightedStackFrame"],
  ["stack", ".stackFrame, .zombieStackFrame"],
  ["value", ".instVal, .listElt, .stackFrameValue, .colorObjTbl, .lambdaObjTbl"],
  ["object", ".instTbl, .listTbl, .instKey"],
  ["canvas", ".ExecutionVisualizer"],
];
const mutedText = ".typeLabel, .fieldTypeLabel, .objectIdLabel, .listHeader, .cdataHeader";
const specialText = ".javaStackVarThis, .retval, .errorOutput";

export function paintRole(element: Element, kind: "text" | "background" | "border"): PaintRole | undefined {
  // Program colors and the alpha checkerboard must never be interpreted as UI paint.
  if (element.closest(".colorSwatch, .colorSwatchContainer")) return undefined;
  if (kind === "text") {
    if (element.closest(specialText)) return "special";
    return element.closest(mutedText) ? "muted" : "text";
  }
  if (kind === "border") return "border";
  if (element.matches(".instTbl:not(.emptyInst)") && !element.querySelector(".instKey")) return "value";
  return surfaces.find(([, selector]) => element.matches(selector))?.[0];
}

/** Install once per document; styles remain scoped to visualizer instances. */
export function installTheme(): void {
  if (document.getElementById("codevis-theme-styles")) return;
  const style = document.createElement("style");
  style.id = "codevis-theme-styles";
  const scoped = (selector: string) => selector.split(", ").map(s => `div.ExecutionVisualizer ${s}`).join(", ");
  style.textContent = themeCss + `
.codevis-render-page, .codevis-json, div.ExecutionVisualizer {
  color: ${paint("text")}; background-color: ${paint("canvas")};
  --object-background-color: ${paint("object")};
  --value-background-color: ${paint("value")};
  --object-border: 1px solid ${paint("border")};
  --value-border: var(--object-border);
}
div.ExecutionVisualizer * { color: inherit; }
div.ExecutionVisualizer .instTbl:not(:has(.instKey)):not(.emptyInst) { background-color: ${paint("value")} !important; }
div.ExecutionVisualizer .colorHexLabel { color: ${paint("text")} !important; }
${scoped(mutedText)} { color: ${paint("muted")} !important; }
${scoped(specialText)} { color: ${paint("special")} !important; }
${[...surfaces].reverse().filter(([, selector]) => selector !== ".ExecutionVisualizer").map(([role, selector]) =>
  `${scoped(selector)} { background-color: ${paint(role)} !important; }`
).join("\n")}
div.ExecutionVisualizer .stackFrame { border-left-color: ${paint("border")} !important; border-right-color: ${paint("border")} !important; }
/* Finality is semantic, not a brightness filter that can break text contrast. */
div.ExecutionVisualizer .isFinal .stackFrameValue,
div.ExecutionVisualizer .isFinal .instVal { filter: none; }
`;
  document.head.append(style);
}

export function applyTheme(element: HTMLElement, theme?: Theme): void {
  if (theme !== undefined && !["light", "dark", "auto"].includes(theme)) {
    throw new Error("Theme must be light, dark, or auto");
  }
  installTheme();
  if (theme !== undefined) element.dataset.codevisTheme = theme;
}
