import { ExecutionVisualizer } from "./pytutor";

export type Lang = "java";
export type VisualizerType = "pytutor" | "json-pre";

export interface Options {
  includeTypes?: boolean;
  textualMemoryLabels?: boolean;
  stripTypePrefixes?: string[];
  visualizer?: VisualizerType;
}

export interface CreateParams {
  lang: Lang;
  trace: `data:application/json;base64,${string}`;
  element: HTMLElement;
  options?: Options;
}

export interface VisualizerInstance {
  updateOutput?(): void;
  redrawConnectors?(): void;
  destroy?(): void;
  readonly element?: HTMLElement;
}

export class JsonPreVisualizer implements VisualizerInstance {
  readonly element: HTMLElement;
  readonly preElement: HTMLPreElement;
  readonly codeElement: HTMLElement;
  private traceData: any;

  constructor(element: HTMLElement, traceData: any) {
    this.element = element;
    this.traceData = traceData;
    this.element.innerHTML = "";

    this.preElement = document.createElement("pre");
    this.codeElement = document.createElement("code");
    this.codeElement.className = "language-json";
    this.codeElement.textContent = JSON.stringify(traceData, null, 2);

    this.preElement.appendChild(this.codeElement);
    this.element.appendChild(this.preElement);
  }

  updateOutput(): void {
    this.codeElement.textContent = JSON.stringify(this.traceData, null, 2);
  }

  redrawConnectors(): void {
    // No connectors for JSON pre view
  }

  destroy(): void {
    this.element.innerHTML = "";
  }
}

export function create({
  lang,
  trace,
  element,
  options,
}: CreateParams): VisualizerInstance {
  const visualizerType = options?.visualizer ?? "pytutor";

  // TODO error handling
  const decodedTrace = JSON.parse(
    atob(trace.replace(/^data:application\/json;base64,/, "")),
  );

  if (visualizerType === "json-pre") {
    return new JsonPreVisualizer(element, decodedTrace);
  }

  const pyTutorOptions = {
    lang: lang,
    includeTypes: options?.includeTypes ?? false,
    textualMemoryLabels: options?.textualMemoryLabels ?? false,
    stripTypePrefixes: options?.stripTypePrefixes ?? [],
    jumpToEnd: true,
    hideCode: true,
    disableHeapNesting: true,
  };

  const viz = new ExecutionVisualizer(
    element.id, // TODO is this safe?
    decodedTrace,
    pyTutorOptions,
  );

  const removeIds = [
    "#vizLayoutTdFirst",
    "#progOutputs",
    "#selectiveHideStatus",
  ];

  removeIds
    .map((rid) => element.querySelector(rid))
    .forEach((rel) => rel?.setAttribute("style", "display: none!important;"));

  viz.updateOutput();

  window.addEventListener("resize", () => {
    viz.redrawConnectors();
  });

  document.addEventListener("DOMContentLoaded", () => {
    viz.redrawConnectors();
  });

  return viz;
}
