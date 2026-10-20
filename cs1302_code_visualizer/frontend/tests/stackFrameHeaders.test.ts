import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ExecutionVisualizer } from "../js/pytutor";

function traceWithHeaders(
  names: string[],
  frameLabels: { is_parent?: boolean; parent_frame_id_list?: number[] } = {},
) {
  return {
    code: "class Driver { void main() { int x = 1; x = 2; } }",
    trace: names.map((name, index) => ({
      event: "step_line",
      line: index + 3,
      func_name: "main",
      globals: {},
      ordered_globals: [],
      heap: {},
      stdout: "",
      stack_to_render: [{
        unique_hash: "main_0",
        frame_id: 0,
        func_name: name,
        is_highlighted: true,
        is_zombie: false,
        is_parent: false,
        parent_frame_id_list: [],
        ordered_varnames: ["x"],
        encoded_locals: { x: index + 1 },
        locals_attrs: { x: { type: "int" } },
        ...frameLabels,
      }],
    })),
  };
}

describe("stack frame headers during playback", () => {
  let container: HTMLElement;

  function render(names: string[], labels = {}) {
    return new ExecutionVisualizer(container.id, traceWithHeaders(names, labels), {
      lang: "java",
      jumpToEnd: true,
      hideCode: true,
      disableHeapNesting: true,
    });
  }

  beforeEach(() => {
    document.body.innerHTML = '<div id="frame-headers"></div>';
    container = document.getElementById("frame-headers")!;
  });

  afterEach(() => { document.body.innerHTML = ""; });

  it("updates the same frame's header and values when moving backward and forward", () => {
    const visualizer = render(["main:3", "main:4"]);
    const frame = container.querySelector('[data-frame_id="0"]')!;
    const expectState = (step: number, header: string, value: string) => {
      visualizer.renderStep(step);
      expect(container.querySelector('[data-frame_id="0"]')).toBe(frame);
      expect(frame.querySelector(".stackFrameHeader")?.textContent).toBe(header);
      expect(frame.querySelector(".stackFrameVar")?.textContent).toBe("x");
      expect(frame.querySelector(".stackFrameValue")?.textContent).toBe(value);
    };

    // Rendering starts at the final step, matching per-step image export.
    expectState(1, "main:4", "2");
    expectState(0, "main:3", "1");
    expectState(1, "main:4", "2");
    expectState(0, "main:3", "1");
  });

  it.each([
    {
      names: ["<lambda>:3", "<lambda>:4"],
      expected: ["λ:3", "λ:4"],
      labels: {},
    },
    {
      names: ["method<img/onerror=alert(1)>:3", "method<b>:4"],
      expected: ["method<img/onerror=alert(1)>:3", "method<b>:4"],
      labels: {},
    },
    {
      names: ["parent:3", "parent:4"],
      expected: ["f0: parent:3 [parent=f9]", "f0: parent:4 [parent=f9]"],
      labels: { is_parent: true, parent_frame_id_list: [9] },
    },
  ])("preserves formatted header text during playback: $names", ({ names, expected, labels }) => {
    const visualizer = render(names, labels);
    for (const step of [1, 0, 1]) {
      visualizer.renderStep(step);
      expect(container.querySelector('[data-frame_id="0"] .stackFrameHeader')?.textContent)
        .toBe(expected[step]);
      expect(container.querySelector("img, b, script, [onerror]")).toBeNull();
    }
  });
});
