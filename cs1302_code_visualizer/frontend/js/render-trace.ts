/**
 * @fileoverview Browser entry point for rendering trace files directly from URL parameters.
 */

import $ from "jquery";
import { ExecutionVisualizer } from "./pytutor";
import { JsonPreVisualizer, VisualizerInstance } from "./CodeVisualizer";

document.addEventListener("DOMContentLoaded", () => {
  const urlParams = new URLSearchParams(window.location.search);
  const tracePath = urlParams.get("tracePath");
  const visualizer = urlParams.get("visualizer") || "pytutor";
  const includeTypes = urlParams.get("includeTypes")?.toLowerCase() !== "false";
  const textMemoryLabels =
    urlParams.get("textMemoryLabels")?.toLowerCase() !== "false";
  let stripTypePrefixes: string[] = [];
  try {
    const maybePrefixArray = JSON.parse(
      urlParams.get("stripTypePrefixes") || "[]"
    );
    if (Array.isArray(maybePrefixArray)) {
      stripTypePrefixes = maybePrefixArray;
    }
  } catch (_unusedError) {
    // stripTypePrefixes URL parameter is optional or may not be valid JSON
  }

  fetch("file://" + tracePath)
    .then((r) => r.json())
    .then((trace) => {
      const vizTarget = document.getElementById("visualizerDiv")!;
      let myViz: VisualizerInstance | ExecutionVisualizer;

      if (visualizer === "json-pre") {
        myViz = new JsonPreVisualizer(vizTarget, trace);
        (window as any).optFrontend = myViz;

        const screenshotReadyIndicator = document.createElement("div");
        screenshotReadyIndicator.id = "screenshotReadyIndicator";
        screenshotReadyIndicator.style.position = "absolute";
        screenshotReadyIndicator.style.opacity = "0";
        document.body.appendChild(screenshotReadyIndicator);
      } else {
        const frontendOptions = {
          jumpToEnd: true,
          hideCode: true,
          disableHeapNesting: true,
          lang: "java",
          includeTypes: includeTypes,
          textualMemoryLabels: textMemoryLabels,
          stripTypePrefixes: stripTypePrefixes,
        };

        myViz = new ExecutionVisualizer(
          "visualizerDiv",
          trace,
          frontendOptions
        );

        const notifyReady = () => {
          if (myViz && typeof (myViz as any).redrawConnectors === "function") {
            (myViz as any).redrawConnectors();
          }
          (window as any).optFrontend = myViz;

          const screenshotReadyIndicator = document.createElement("div");
          screenshotReadyIndicator.id = "screenshotReadyIndicator";
          screenshotReadyIndicator.style.position = "absolute";
          screenshotReadyIndicator.style.opacity = "0";
          document.body.appendChild(screenshotReadyIndicator);
        };

        setTimeout(notifyReady, 50);
      }
    });
});
