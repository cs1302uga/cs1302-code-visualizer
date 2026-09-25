import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { create } from "../js/CodeVisualizer";
import { describeSvg } from "../js/svgDescription";

function render(options = {}) {
  document.body.innerHTML = '<div id="description"></div>';
  const element = document.getElementById("description")!;
  const trace = JSON.parse(readFileSync(resolve(__dirname, "../../../docs/array-orientation/fixtures/dimensions.json"), "utf8"));
  const instance = create({ lang: "java", trace, element, options });
  return { element, instance };
}

describe("SVG descriptions", () => {
  it("lists shared objects once, describes references and follows step changes", () => {
    const { element, instance } = render();
    const final = describeSvg(element);
    expect(final.sections[0].heading).toMatch(/^Stack frame:/);
    expect(final.sections.filter(s => s.heading.startsWith("Heap object 4:"))).toHaveLength(1);
    expect(JSON.stringify(final)).toContain("reference to object 4");
    expect(JSON.stringify(final)).toContain("Index 1: 99");
    instance.visualizer.stepBack();
    expect(JSON.stringify(describeSvg(element))).toContain("Index 1: 20");
    expect(JSON.stringify(describeSvg(element))).not.toContain("Index 1: 99");
    instance.destroy?.();
  });

  it("keeps array descriptions independent of orientation", () => {
    const horizontal = render();
    const description = describeSvg(horizontal.element);
    horizontal.instance.destroy?.();
    const vertical = render({ arrayOrientation: "vertical", alternateArrayOrientations: true });
    expect(describeSvg(vertical.element)).toEqual(description);
    vertical.instance.destroy?.();
  });

  it("does not expose hidden fields and stops at cyclic references", () => {
    document.body.innerHTML = `<div id="root"><div class="heapObject" data-object-id="7">
      <div class="typeLabel">Node</div><table>
      <tr class="instEntry"><td>next</td><td data-reference-target="7"></td></tr>
      <tr class="instEntry" style="display:none"><td>secret</td><td>password</td></tr>
      <tr class="instEntry"><td>value</td><td><span style="visibility:hidden">private</span>42</td></tr>
      </table></div></div>`;
    const result = describeSvg(document.getElementById("root")!);
    expect(result.sections).toEqual([{ heading: "Heap object 7: Node", items: ["next: reference to object 7", "value: 42"] }]);
  });

  it("omits filtered variables and unreachable objects", () => {
    const { element, instance } = render({ hideVars: ["main:cube"] });
    const description = JSON.stringify(describeSvg(element));
    expect(description).not.toContain("cube:");
    expect(description).not.toContain("Heap object 1:");
    expect(description).toContain("sharedRow: reference to object 4");
    instance.destroy?.();
  });

  it("preserves literal spaces in string values", () => {
    document.body.innerHTML = `<div id="root"><div class="heapObject" data-object-id="1">
      <div class="typeLabel">String</div><table><tr class="instEntry"><td>
      <span class="stringObj">"a  b"</span></td></tr></table></div></div>`;
    expect(describeSvg(document.getElementById("root")!).sections[0].items).toEqual(['"a  b"']);
  });

  it("preserves JSON content as text", () => {
    const pre = document.createElement("pre");
    pre.textContent = '{"label":"<script> café 👩‍💻"}';
    expect(describeSvg(pre).sections[0].items).toEqual([pre.textContent]);
  });
});
