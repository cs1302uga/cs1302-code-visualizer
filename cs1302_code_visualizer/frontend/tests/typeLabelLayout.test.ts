import {describe, expect, it, vi} from "vitest";
import {declaredTypes, TypeLabelLayout} from "../js/typeLabelLayout";
import {stringValue} from "../js/stringStyle";

describe("trace-wide type labels", () => {
  it("reserves future declared types, measures shared types after prefix stripping and caches measurements", () => {
    const states=[{globals_attrs:{x:{type:"int"}}},
      {stack_to_render:[{locals_attrs:{m:{type:"java.util.Map<String, Integer>"}}}],
        heap_attrs:{1:{type:["boolean"]},2:{type:"UnusedRuntimeType"}}}];
    expect(declaredTypes(states)).toEqual(["boolean","int","java.util.Map<String, Integer>"]);
    const root=document.createElement("div");root.innerHTML='<div class="fieldTypeLabel">int</div>';
    document.body.append(root);
    const spy=vi.spyOn(HTMLElement.prototype,"getBoundingClientRect").mockImplementation(function(this:HTMLElement){
      return {width:(this.textContent?.length??0)*7} as DOMRect;
    });
    const layout=new TypeLabelLayout(states,["java.util.List<VeryLongTypeName>"],s=>s.replace("java.util.",""));
    layout.apply(root);
    expect(root.style.getPropertyValue("--type-label-width")).toBe(`${"List<VeryLongTypeName>".length*7}px`);
    const count=spy.mock.calls.length;layout.apply(root);expect(spy).toHaveBeenCalledTimes(count);
    expect(root.children).toHaveLength(1);
    spy.mockRestore();root.remove();
  });
  it("uses Java UTF-16 length for standalone String labels", () => {
    expect(stringValue(["INSTANCE","String",["___NO_LABEL!___","A😀"]])?.length).toBe(3);
    expect(stringValue(["HEAP_PRIMITIVE","java.lang.String",""])?.length).toBe(0);
  });
});
