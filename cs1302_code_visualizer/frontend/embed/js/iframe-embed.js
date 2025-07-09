/*

Online Python Tutor
https://github.com/pgbovine/OnlinePythonTutor/

Copyright (C) 2010-2013 Philip J. Guo (philip@pgbovine.net)

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

*/


// Pre-reqs:
// - pytutor.js
// - jquery.ba-bbq.min.js
// - opt-frontend-common.js
// should all be imported BEFORE this file


var myVisualizer = null; // singleton ExecutionVisualizer instance


function NOP() {};


$(document).ready(function() {
  var queryStrOptions = getQueryStringOptions();

  var preseededCode = queryStrOptions.preseededCode;
  var pyState = queryStrOptions.pyState;
  var verticalStackBool = (queryStrOptions.verticalStack == 'true');
  var heapPrimitivesBool = (queryStrOptions.heapPrimitives == 'true');
  var drawParentPointerBool = (queryStrOptions.drawParentPointers == 'true');
  var textRefsBool = (queryStrOptions.textRefs == 'true');
  var showOnlyOutputsBool = (queryStrOptions.showOnlyOutputs == 'true');
  var cumModeBool = (queryStrOptions.cumulativeState == 'true');

  var codeDivWidth = undefined;
  var codeDivWidth = 350;
  var cdw = $.bbq.getState('codeDivWidth');
  var cdw = $.bbq.getState('width');
  if (cdw) {
    codeDivWidth = Number(cdw);
  }

  var codeDivHeight = undefined;
  var cdh = $.bbq.getState('codeDivHeight');
  if (cdh) {
    codeDivHeight = Number(cdh);
  }


  var startingInstruction = queryStrOptions.preseededCurInstr;
  if (!startingInstruction) {
    startingInstruction = 0;
  }

  var backend_script = null;
  if (pyState == '2') {
      backend_script = python2_backend_script;
  }
  else if (pyState == '3') {
      backend_script = python3_backend_script;
  }
  else if (pyState == '2crazy') {
      backend_script = python2crazy_backend_script;
  }


  // David Pritchard's code for resizeContainer option ...
  var resizeContainer = ($.bbq.getState('resizeContainer') == 'true');
    
  if (resizeContainer) {
      function findContainer() {
        try {
          var ifs = window.top.document.getElementsByTagName("iframe");
          for(var i = 0, len = ifs.length; i < len; i++)  {
              var f = ifs[i];
              var fDoc = f.contentDocument || f.contentWindow.document;
              if(fDoc === document)   {
                  return f;
              }
          }
        } catch (e) {
          // ignore SecurityError
        }
      }
      
      var container = findContainer();
      
      function resizeContainerNow() {
        $(container).height($("html").height());
      };
  }

  // set up all options in a JS object
  var backendOptionsObj = {cumulative_mode: cumModeBool,
                           heap_primitives: heapPrimitivesBool,
                           show_only_outputs: showOnlyOutputsBool,
                           py_crazy_mode: (pyState == '2crazy'),
                           origin: 'iframe-embed.js'};

  var frontendOptionsObj = {startingInstruction: startingInstruction,
                            embeddedMode: true,
                            verticalStack: verticalStackBool,
                            disableHeapNesting: true,
                            drawParentPointers: drawParentPointerBool,
                            textualMemoryLabels: textRefsBool,
                            showOnlyOutputs: showOnlyOutputsBool,
                            executeCodeWithRawInputFunc: executeCodeWithRawInput,
                            heightChangeCallback: (resizeContainer ? resizeContainerNow : NOP),

                            // undocumented experimental modes:
                            pyCrazyMode: (pyState == '2crazy'),
                            highlightLines: typeof $.bbq.getState("highlightLines") !== "undefined",
                            codeDivWidth: codeDivWidth,
                            codeDivHeight: codeDivHeight,
                           }

window.seleniumRunHook = function(dataFromBackend) {
  let frontendOptionsObj = {
    startingInstruction: undefined,
    embeddedMode: true,
    verticalStack: verticalStackBool,
    disableHeapNesting: true,
    drawParentPointers: drawParentPointerBool,
    textualMemoryLabels: textRefsBool,
    showOnlyOutputs: showOnlyOutputsBool,
    executeCodeWithRawInputFunc: executeCodeWithRawInput,
    heightChangeCallback: (resizeContainer ? resizeContainerNow : NOP),

    // undocumented experimental modes:
    pyCrazyMode: (pyState == '2crazy'),
    highlightLines: typeof $.bbq.getState("highlightLines") !== "undefined",
    codeDivWidth: codeDivWidth,
    codeDivHeight: codeDivHeight,
  };

  let outputDiv = "vizDiv";

  dataFromBackend = JSON.parse(dataFromBackend);
  var trace = dataFromBackend.trace;
  // cut off any jvm cleanup after main returns
  trace.length = trace.findIndex((t) => t.event === "return" && t.func_name === "main");

  // don't enter visualize mode if there are killer errors:
  if (!trace ||
      (trace.length == 0) ||
      (trace[trace.length - 1].event == 'uncaught_exception')) {

    if (trace.length == 1) {
      return (trace[0].exception_msg);
    }
    else if (trace[trace.length - 1].exception_msg) {
      return (trace[trace.length - 1].exception_msg);
    }
    else {
      return "Unknown error.";
    }
  }

  // skip to last trace state
  frontendOptionsObj.jumpToEnd = true;
  // don't show code on the side
  frontendOptionsObj.hideCode = true;

  // fail-soft to prevent running off of the end of trace
  if (frontendOptionsObj.startingInstruction >= trace.length) {
    frontendOptionsObj.startingInstruction = 0;
  }
  myVisualizer = new ExecutionVisualizer(outputDiv, dataFromBackend, frontendOptionsObj);
}


  function executeCode(forceStartingInstr) {
    let indicatorElement = document.createElement("div")
    indicatorElement.id = "indicatorElement";
    indicatorElement.hidden = true;
    document.body.appendChild(indicatorElement);
    return;
    if (forceStartingInstr) {
      frontendOptionsObj.startingInstruction = forceStartingInstr;
    }
    executePythonCode(preseededCode,
                      backend_script, backendOptionsObj,
                      frontendOptionsObj,
                      'vizDiv',
                      function() { // success
/*                          if (serverReply.stdin != "") {
                              var stdinHTML = '<div id="stdinWrap">stdin:<pre id="stdinShow" style="border:1px solid gray"></pre></div>';
                              $('#dataViz').append(stdinHTML);
                              $("#stdinShow").html(serverReply.stdin);
                          }*/
                          if ($.bbq.getState('rightStdout')) {
                              $("#progOutputs").prependTo("#dataViz");
                          };
                          if (resizeContainer)
                              resizeContainerNow();
                      }, 
                      NOP);
  }


  function executeCodeFromScratch() {
    // reset these globals
    rawInputLst = [];
    executeCode();
  }

  function executeCodeWithRawInput(rawInputStr, curInstr) {
    // set some globals
    rawInputLst.push(rawInputStr);
    executeCode(curInstr);
  }


  // log a generic AJAX error handler
  $(document).ajaxError(function() {
    alert("Ugh, Online Python Tutor server error :(");
  });


  // redraw connector arrows on window resize
  $(window).resize(function() {
    myVisualizer.redrawConnectors();
  });

  executeCodeFromScratch(); // finally, execute code and display visualization


});

