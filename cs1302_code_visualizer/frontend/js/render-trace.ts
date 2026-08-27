// Python Tutor: https://github.com/pgbovine/OnlinePythonTutor/
// Copyright (C) Philip Guo (philip@pgbovine.net)
// LICENSE: https://github.com/pgbovine/OnlinePythonTutor/blob/master/LICENSE.txt

import { ExecutionVisualizer } from "./pytutor";
import { JsonPreVisualizer } from "./CodeVisualizer";

$(document).ready(function () {
  const urlParams = new URLSearchParams(window.location.search);
  const tracePath = urlParams.get("tracePath");
  const visualizer = urlParams.get("visualizer") || "pytutor";
  const includeTypes = urlParams.get("includeTypes")?.toLowerCase() !== "false";
  const textMemoryLabels =
    urlParams.get("textMemoryLabels")?.toLowerCase() !== "false";
  let stripTypePrefixes: string[] = [];
  try {
    let maybePrefixArray = JSON.parse(urlParams.get("stripTypePrefixes") || "[]");
    if (Array.isArray(maybePrefixArray)) {
      stripTypePrefixes = maybePrefixArray;
    }
  } catch (e) {}

  fetch("file://" + tracePath)
    .then((r) => r.json())
    .then((trace) => {
      const vizTarget = document.getElementById("visualizerDiv")!;
      let myViz: any;

      if (visualizer === "json-pre") {
        myViz = new JsonPreVisualizer(vizTarget, trace);
        (window as any).optFrontend = myViz;

        let screenshotReadyIndicator = document.createElement("div");
        screenshotReadyIndicator.id = "screenshotReadyIndicator";
        screenshotReadyIndicator.style.position = "absolute";
        screenshotReadyIndicator.style.opacity = "0";
        document.body.appendChild(screenshotReadyIndicator);
      } else {
        let frontendOptions = {
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
          frontendOptions,
        );

        const notifyReady = () => {
          if (myViz.redrawConnectors) {
            myViz.redrawConnectors();
          }
          (window as any).optFrontend = myViz;

          if (!document.getElementById("screenshotReadyIndicator")) {
            let screenshotReadyIndicator = document.createElement("div");
            screenshotReadyIndicator.id = "screenshotReadyIndicator";
            screenshotReadyIndicator.style.position = "absolute";
            screenshotReadyIndicator.style.opacity = "0";
            document.body.appendChild(screenshotReadyIndicator);
          }
        };

        if (document.fonts) {
          document.fonts.addEventListener("loadingdone", notifyReady);
        }
        setTimeout(notifyReady, 100);
      }
    });
});
