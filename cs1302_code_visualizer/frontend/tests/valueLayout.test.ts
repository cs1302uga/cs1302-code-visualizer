import {afterEach,describe,expect,it,vi} from "vitest";
import {createValueBox,layoutValueBoxes,renderCompactString} from "../js/valueLayout";

afterEach(()=>vi.restoreAllMocks());

describe("value surface sizing",()=>{
  it("keeps widths local to each table and resizes compact arrows after values shrink",()=>{
    document.body.innerHTML='<div id="root"><table id="a"><tr><td class="instVal"></td><td class="instVal"></td></tr></table><table id="b"><tr><td class="instVal"></td></tr></table></div>';
    const root=document.getElementById("root")!;
    const cells=root.querySelectorAll<HTMLElement>("td");
    const long=createValueBox(cells[0]);long.textContent="12345678";
    renderCompactString(cells[1],"7","literal text stays outside the value box",false);
    const other=createValueBox(cells[2]);other.textContent="123456789012";
    for(const box of root.querySelectorAll<HTMLElement>(".value-box"))box.style.width="250px";
    vi.spyOn(document,"createRange").mockImplementation(()=>{
      let node:Node;
      return {selectNodeContents(value:Node){node=value;},getBoundingClientRect(){
        return {width:(node.textContent?.length??0)*7.2};
      }} as Range;
    });
    layoutValueBoxes(root);
    expect([...cells[0].closest("table")!.querySelectorAll<HTMLElement>(".value-box")].map(b=>b.style.width)).toEqual(["80px","80px"]);
    expect(other.style.width).toBe("109px");
    long.textContent="1";
    layoutValueBoxes(root);
    expect(long.style.width).toBe("40px");
    expect(cells[1].querySelector<HTMLElement>(".value-box")!.style.width).toBe("40px");
    expect(other.style.width).toBe("109px");
    expect(cells[1].querySelector("svg")!.getAttribute("width")).toBe("56");
    expect(cells[1].querySelector("circle")!.getAttribute("cx")).toBe("32");
  });
});
