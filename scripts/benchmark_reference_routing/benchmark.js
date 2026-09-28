/** Browser benchmark shared by the baseline and implementation. Times are ms. */
window.benchmarkRouting = async function () {
  await document.fonts.load('400 10px Recursive');
  await document.fonts.ready;
  const base = await fetch('fixtures/later-node.json').then(r => r.json());
  const dense = count => {
    const trace = structuredClone(base), state = trace.trace[0];
    state.heap = {}; state.heap_attrs = {};
    const frame = state.stack_to_render[0];
    frame.encoded_locals = {}; frame.locals_attrs = {}; frame.ordered_varnames = [];
    for (let i = 0; i < count; i++) {
      const id = 1000+i;
      state.heap[id] = ['INSTANCE', 'Node', ['value', i],
        ['next', ['REF',1000+(i+1)%count]], ['other', ['REF',1000+(i+7)%count]]];
      state.heap_attrs[id] = {type:['int','Node','Node']};
      if (i%4===0) {
        const name = `n${i}`;
        frame.ordered_varnames.push(name); frame.encoded_locals[name]=['REF',id];
        frame.locals_attrs[name]={type:'Node',final:false};
      }
    }
    return trace;
  };
  const arrays = await fetch('fixtures/arrays.json').then(r => r.json());
  const cases = [
    ['later-node-compact',base,{stringStyle:'compact'}],
    ['arrays-default',arrays,{}],
    ['dense-24',dense(24),{}],
    ['dense-48',dense(48),{}],
  ];
  for (const [name,style] of [['later-node','default'],['later-node','inline'],['aliases','default'],
    ['cycle','default'],['self-loop','default'],['fields','default'],['arrays','compact']]) {
    cases.splice(cases.length-2,0,[`${name}-${style}`,
      await fetch(`fixtures/${name}.json`).then(r=>r.json()),{stringStyle:style}]);
  }
  const summarize = values => {
    const sorted = [...values].sort((a,b)=>a-b);
    return {samples:values.length,median:sorted[Math.floor(sorted.length/2)],
      p95:sorted[Math.min(sorted.length-1,Math.ceil(sorted.length*.95)-1)],max:sorted.at(-1)};
  };
  const results = [];
  for (const [name,trace,options] of cases) {
    const layout = [];
    for (let n=0;n<6;n++) {
      window.instance?.destroy();
      const start = performance.now();
      window.instance = reviewCreate({lang:'java',trace,element:document.getElementById('diagram'),options});
      await document.fonts.ready;
      instance.redrawConnectors();
      layout.push(performance.now()-start);
    }
    const manager = instance.visualizer.dataViz.jsPlumbInstance;
    for (let n=0;n<5;n++) manager.repaintEverything();
    const repaint = [], stepping=[];
    for (let n=0;n<40;n++) {
      let start = performance.now(); manager.repaintEverything(); repaint.push(performance.now()-start);
      start = performance.now(); instance.redrawConnectors(); stepping.push(performance.now()-start);
    }
    let reads=0;
    const original=Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect=function(){reads++;return original.call(this);};
    try { manager.repaintEverything(); } finally { Element.prototype.getBoundingClientRect=original; }
    results.push({name,objects:document.querySelectorAll('.heapObject').length,
      references:manager.connections.length,layout:summarize(layout),repaint:summarize(repaint),
      redrawWithValueLayout:summarize(stepping),boundingRectReads:reads});
  }
  return {browser:navigator.userAgent,viewport:[innerWidth,innerHeight],
    method:'6 new-instance layouts; 5 warmups; 40 repaint and 40 redraw samples; assets warm',results};
};
