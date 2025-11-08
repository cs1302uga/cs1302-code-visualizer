import { ExecutionVisualizer } from "./pytutor";

type Lang = "java";

interface Options {
  includeTypes: boolean;
  textualMemoryLabels: boolean;
  stripTypePrefixes: string[];
}

interface CreateParams {
  lang: Lang;
  trace: `data:application/json;base64,${string}`;
  element: HTMLElement;
  options: Options;
}

export function create({
  lang,
  trace,
  element,
  options,
}: CreateParams): ExecutionVisualizer {
  let pyTutorOptions = {
    lang: lang,
    includeTypes: options.includeTypes ?? false,
    textualMemoryLabels: options.textualMemoryLabels ?? false,
    jumpToEnd: true,
    hideCode: true,
    disableHeapNesting: true,
  };

  // TODO error handling
  let decodedTrace = JSON.parse(
    atob(trace.replace(/^data:application\/json;base64,/, "")),
  );

  let viz = new ExecutionVisualizer(
    element.id, // TODO is this safe?
    decodedTrace,
    pyTutorOptions,
  );

  viz.updateOutput();

  return viz;
}
