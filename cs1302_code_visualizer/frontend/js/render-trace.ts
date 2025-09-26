// Python Tutor: https://github.com/pgbovine/OnlinePythonTutor/
// Copyright (C) Philip Guo (philip@pgbovine.net)
// LICENSE: https://github.com/pgbovine/OnlinePythonTutor/blob/master/LICENSE.txt

import { ExecutionVisualizer } from './pytutor';

$(document).ready(function() {
  let frontendOptions = {
    "jumpToEnd": true,
    "hideCode": true,
    "disableHeapNesting": true,
    "lang": "java",
  };

  const urlParams = new URLSearchParams(window.location.search);
  const tracePath = urlParams.get("tracePath");

  fetch("file://" + tracePath).then(r => r.json()).then(trace => {
    var myViz = new ExecutionVisualizer('visualizerDiv', trace, frontendOptions);

    document.fonts.addEventListener("loadingdone", () => {
      Array
        .from(document.querySelectorAll("#dataViz .heapObject"))
        .filter((element) => element.querySelector(".typeLabel").textContent.includes("String instance"))
        .forEach((element) => {
          element.querySelector(".instKey").remove();
          element.querySelector<HTMLElement>(".instVal").style.setProperty("border-color", "transparent", "important")
        });

      myViz.redrawConnectors();
      let screenshotReadyIndicator = document.createElement("div");
      screenshotReadyIndicator.id = "screenshotReadyIndicator";
      screenshotReadyIndicator.style.position = "absolute";
      screenshotReadyIndicator.style.opacity = "0";
      document.body.appendChild(screenshotReadyIndicator);
    });
  })
});
