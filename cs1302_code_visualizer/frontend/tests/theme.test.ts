import { describe, expect, it } from "vitest";
import { applyTheme, paintRole, palettes } from "../js/theme";

function luminance(hex: string): number {
  const rgb = hex.slice(1).match(/../g)!.map(h => parseInt(h, 16) / 255)
    .map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
}
function contrast(a: string, b: string): number {
  const [dark, light] = [luminance(a), luminance(b)].sort((a, b) => a - b);
  return (light + .05) / (dark + .05);
}

describe("semantic themes", () => {
  it.each(Object.values(palettes))("keeps text at AAA contrast and meaningful graphics at 3:1", palette => {
    for (const background of [palette.canvas, palette.stack, palette.activeStack, palette.object, palette.value]) {
      for (const foreground of [palette.text, palette.muted, palette.special]) {
        expect(contrast(foreground, background)).toBeGreaterThanOrEqual(7);
      }
      for (const foreground of [palette.border, palette.arrow, palette.inactiveArrow]) {
        expect(contrast(foreground, background)).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it("classifies roles by meaning while preserving literal program colors", () => {
    const root = document.createElement("div");
    root.innerHTML = '<div class="stackFrame highlightedStackFrame"></div><span class="typeLabel"></span><span class="javaStackVarThis"></span><div class="colorSwatchContainer"><div class="colorSwatch"></div></div><table class="instTbl"></table>';
    expect(paintRole(root.children[0], "background")).toBe("activeStack");
    expect(paintRole(root.children[1], "text")).toBe("muted");
    expect(paintRole(root.children[2], "text")).toBe("special");
    for (const kind of ["text", "background", "border"] as const) {
      expect(paintRole(root.querySelector(".colorSwatch")!, kind)).toBeUndefined();
    }
    expect(paintRole(root.children[4], "background")).toBe("value");
  });

  it("validates explicit themes and installs styles once", () => {
    const root = document.createElement("div");
    applyTheme(root, "auto");
    applyTheme(root, "dark");
    expect(root.dataset.codevisTheme).toBe("dark");
    expect(document.querySelectorAll("#codevis-theme-styles")).toHaveLength(1);
    expect(() => applyTheme(root, "invalid" as any)).toThrow("Theme must");
  });
});
