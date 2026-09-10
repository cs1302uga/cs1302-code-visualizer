/**
 * @fileoverview Main entry point for the Code Visualizer module.
 * Provides the unified `create()` factory for initializing visualizers.
 */

import { ExecutionVisualizer } from "./pytutor";

/**
 * Supported execution languages.
 */
export type Lang = "java";

/**
 * Supported visualizer frontend presentation modes.
 */
export type VisualizerType = "pytutor" | "json-pre";

/**
 * Configuration options for visualizer instances.
 */
export interface Options {
  includeTypes?: boolean;
  textualMemoryLabels?: boolean;
  stripTypePrefixes?: string[];
  visualizer?: VisualizerType;
  hideFields?: string[];
  hideVars?: string[];
}

/**
 * Parameters for the CodeVisualizer factory `create()` function.
 */
export interface CreateParams {
  lang: Lang;
  trace: string | object;
  element: HTMLElement;
  options?: Options;
}

/**
 * Common lifecycle interface implemented by visualizer instances.
 */
export interface VisualizerInstance {
  updateOutput?(): void;
  redrawConnectors?(): void;
  destroy?(): void;
  readonly element?: HTMLElement;
}

/**
 * Fallback JSON preformatted code visualizer.
 */
export class JsonPreVisualizer implements VisualizerInstance {
  public readonly element: HTMLElement;
  public readonly preElement: HTMLPreElement;
  public readonly codeElement: HTMLElement;
  private readonly traceData: unknown;

  public constructor(element: HTMLElement, traceData: unknown) {
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

  /**
   * Updates output display.
   */
  public updateOutput(): void {
    this.codeElement.textContent = JSON.stringify(this.traceData, null, 2);
  }

  /**
   * Redraws connectors (no-op for JSON pre view).
   */
  public redrawConnectors(): void {
    // No connectors for JSON pre view
  }

  /**
   * Destroys and cleans up DOM elements.
   */
  public destroy(): void {
    this.element.innerHTML = "";
  }
}

/**
 * Safely decodes a trace payload which may be:
 * 1. A pre-parsed JavaScript object
 * 2. A raw JSON string
 * 3. A base64 data URI (data:application/json;base64,...)
 * 4. A raw base64 string
 *
 * @param trace The input trace payload.
 * @return Decoded trace object.
 */
function decodeTrace(trace: string | object): unknown {
  if (typeof trace === "object" && trace !== null) {
    return trace;
  }

  if (typeof trace === "string") {
    const trimmed = trace.trim();
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      return JSON.parse(trimmed);
    }

    const base64Str = trimmed.replace(/^data:application\/json;base64,/, "");
    try {
      const binaryString = atob(base64Str);
      try {
        // Safe UTF-8 decoding fallback
        const bytes = Uint8Array.from(binaryString, (c) => c.charCodeAt(0));
        return JSON.parse(new TextDecoder().decode(bytes));
      } catch {
        return JSON.parse(binaryString);
      }
    } catch {
      return JSON.parse(trace);
    }
  }

  return trace;
}

/**
 * Factory function creating a code visualizer instance.
 * @param params Initialization options and target DOM element.
 * @return The instantiated visualizer.
 */
export function create({
  lang,
  trace,
  element,
  options,
}: CreateParams): VisualizerInstance {
  const visualizerType: VisualizerType = options?.visualizer ?? "pytutor";
  const decodedTrace = decodeTrace(trace);

  if (visualizerType === "json-pre") {
    return new JsonPreVisualizer(element, decodedTrace);
  }

  // Ensure element has an ID for PyTutor
  let elementId = element.id;
  if (!elementId) {
    elementId = "codevis-" + Math.random().toString(36).substring(2, 9);
    element.id = elementId;
  }

  const frontendOptions = {
    jumpToEnd: true,
    hideCode: true,
    disableHeapNesting: true,
    lang: lang,
    includeTypes: options?.includeTypes ?? true,
    textualMemoryLabels: options?.textualMemoryLabels ?? false,
    stripTypePrefixes: options?.stripTypePrefixes ?? [],
    hideFields: options?.hideFields ?? [],
    hideVars: options?.hideVars ?? [],
  };

  const visualizer = new ExecutionVisualizer(
    elementId,
    decodedTrace,
    frontendOptions
  );

  return {
    updateOutput: () => {
      visualizer.updateOutput();
    },
    redrawConnectors: () => {
      visualizer.redrawConnectors();
    },
    destroy: () => {
      element.innerHTML = "";
    },
    element: element,
  };
}
