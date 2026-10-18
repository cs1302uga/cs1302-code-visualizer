import { beforeEach, describe, expect, it } from "vitest";
import { create } from "../js/CodeVisualizer";

const body = '{\n    // java.lang.String stays in the body\n' +
  '    /* java.util.List<java.lang.String> */\n' +
  '    return java.lang.String.valueOf("java.lang.String <script>alert(1)</script>");\n}';
const implementation = `java.util.List<java.lang.String[]> apply(java.lang.String[] text) ${body}`;
const displayed = `List<String[]> apply(String[] text) ${body}`;

function lambdaTrace(format: string, code = implementation) {
  if (format === "legacy") {
    return { code: "", trace: [{ event: "step_line", line: 1,
      globals: { f: ["REF", 1] }, ordered_globals: ["f"],
      globals_attrs: { f: { type: "java.util.function.Function" } },
      heap: { "1": ["JAVA_LAMBDA", code] },
      heap_attrs: { "1": { type: "lambda" } }, stack_to_render: [], stdout: "" }] };
  }
  return { code: "", format: "modern", steps: [{ event: "step_line", line: 1,
    statics: [{ className: "Example", fields: [{ name: "f", type: "java.util.function.Function", value: { ref: 1 } }] }],
    heap: { "1": { id: 1, kind: "lambda", type: "lambda", [format]: code } } }] };
}

describe("lambda type display", () => {
  beforeEach(() => { document.body.innerHTML = '<div id="lambda"></div>'; });

  const cases = ["legacy", "sam", "value"].flatMap(format =>
    [true, false].map(includeTypes => ({ format, includeTypes })));
  it.each(cases)("formats $format signature types with includeTypes=$includeTypes and preserves body text", ({ format, includeTypes }) => {
    const container = document.getElementById("lambda")!;
    const instance = create({ lang: "java", element: container, trace: lambdaTrace(format),
      options: { stripTypePrefixes: ["java.lang.", "java.util."], includeTypes } });
    expect(container.querySelector(".lambdaObjElt code")?.textContent).toBe(displayed);
    expect(container.querySelector(".heapObject > .typeLabel")?.textContent).toBe("lambda@1");
    expect(container.querySelector(".fieldTypeLabel") !== null).toBe(includeTypes);
    expect(container.querySelector("script, img, [onerror]")).toBeNull();
    instance.destroy?.();
  });

  it("keeps fully qualified signature types when no prefixes are configured", () => {
    const container = document.getElementById("lambda")!;
    const instance = create({ lang: "java", element: container, trace: lambdaTrace("legacy") });
    expect(container.querySelector(".lambdaObjElt code")?.textContent).toBe(implementation);
    instance.destroy?.();
  });

  it.each(["legacy", "sam", "value"])("preserves pre-body comments and their braces in %s input", format => {
    const container = document.getElementById("lambda")!;
    const comment = " /* java.lang. before block { } */\n";
    const code = `java.lang.String apply(java.lang.Integer x)${comment}${body}`;
    const instance = create({ lang: "java", element: container, trace: lambdaTrace(format, code),
      options: { stripTypePrefixes: ["java.lang."], includeTypes: false } });
    expect(container.querySelector(".lambdaObjElt code")?.textContent).toBe(
      `String apply(Integer x)${comment}${body}`,
    );
    instance.destroy?.();
  });
});
