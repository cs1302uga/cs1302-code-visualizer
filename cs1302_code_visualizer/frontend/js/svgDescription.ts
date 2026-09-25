/** Describe the rendered state, so filtering and presentation have one authority. */
export interface DescriptionSection {
  heading: string;
  items: string[];
}

export interface SvgDescription {
  summary: string;
  sections: DescriptionSection[];
}

function visible(element: Element): boolean {
  for (let current: Element | null = element; current; current = current.parentElement) {
    const style = getComputedStyle(current);
    if (style.display === "none" || style.opacity === "0") return false;
  }
  return getComputedStyle(element).visibility !== "hidden";
}

function words(element: Element | null): string {
  if (!element || !visible(element)) return "";
  const reference = element.getAttribute("data-reference-target");
  if (reference !== null) return `reference to object ${reference}`;
  if (element.classList.contains("stringObj")) return element.textContent ?? "";
  return Array.from(element.childNodes, node => node instanceof Element
    ? words(node) : (node.textContent ?? "").replace(/\s+/g, " ")).join(" ").trim();
}

/** Each object is listed once; references never recursively expand the heap. */
export function describeSvg(root: HTMLElement): SvgDescription {
  if (root.tagName === "PRE") {
    return { summary: "JSON trace view", sections: [{ heading: "Trace", items: [root.innerText ?? root.textContent ?? ""] }] };
  }
  const frames = Array.from(root.querySelectorAll(".stackFrame,.zombieStackFrame")).filter(visible);
  const objects = Array.from(root.querySelectorAll(".heapObject[data-object-id]")).filter(visible);
  const sections: DescriptionSection[] = [];
  for (const frame of frames) {
    const items = Array.from(frame.querySelectorAll(".stackFrameVarTable tr"))
      .filter(visible).map(row => `${words(row.querySelector(".stackFrameVar"))}: ${words(row.querySelector(".stackFrameValue"))}`);
    sections.push({ heading: `Stack frame: ${words(frame.querySelector(".stackFrameHeader"))}`, items });
  }
  const seen = new Set<string>();
  for (const object of objects) {
    const id = object.getAttribute("data-object-id")!;
    if (seen.has(id)) continue;
    seen.add(id);
    const owned = (selector: string) => Array.from(object.querySelectorAll(selector))
      .filter(element => element.closest(".heapObject") === object && visible(element));
    const items = owned(".instEntry,.classEntry,.dictEntry").map(row => row.children.length === 1
      ? words(row.children[0]) : `${words(row.children[0])}: ${words(row.children[1])}`);
    const indices = owned(".listHeader,.tupleHeader");
    owned(".listElt,.tupleElt,.stackElt,.queueElt,.setElt").forEach((cell, index) => {
      items.push(`Index ${indices[index] ? words(indices[index]) : index}: ${words(cell)}`);
    });
    // Strings, boxed primitives, and other leaf objects have no field rows.
    if (!items.length) {
      for (const child of Array.from(object.children)) {
        if (!child.classList.contains("typeLabel")) {
          const value = words(child);
          if (value) items.push(value);
        }
      }
    }
    sections.push({ heading: `Heap object ${id}: ${words(object.querySelector(":scope > .typeLabel"))}`, items });
  }
  return {
    summary: `Java program memory state. ${frames.length} stack frame${frames.length === 1 ? "" : "s"}; ${seen.size} heap object${seen.size === 1 ? "" : "s"}.`,
    sections,
  };
}
