/** Browser benchmark shared by the baseline and implementation. Times are ms. */
async function runRoutingBenchmark({caseNames, routingPolicy = 'historical',
  hardware = 'not recorded', assetRevision = 'not recorded', includeTransitions = true,
  onProgress} = {}, initializationMode = 'policy-switch') {
  if (!['historical','independent','shared'].includes(routingPolicy)) throw new Error(`Unknown routing policy: ${routingPolicy}`);
  if (window.routingBenchmarkActive) throw new Error('A routing benchmark is already running on this page');
  const startedAt = new Date().toISOString();
  window.routingBenchmarkActive = true;
  let restoreInitialization = () => {};
  try {
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
  const fanIn = (count, groups = 1) => {
    const trace = structuredClone(base), state = trace.trace[0];
    state.heap = {}; state.heap_attrs = {};
    const frame = state.stack_to_render[0];
    frame.encoded_locals = {}; frame.locals_attrs = {}; frame.ordered_varnames = [];
    for (let group = 0; group < groups; group++) {
      state.heap[1000+group] = ['INSTANCE', 'Node', ['value', group]];
      state.heap_attrs[1000+group] = {type:['int']};
    }
    for (let i = 0; i < count; i++) {
      const name = `alias${i}`;
      frame.ordered_varnames.push(name);
      frame.encoded_locals[name] = ['REF',1000+i%groups];
      frame.locals_attrs[name] = {type:'Node',final:false};
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
  cases.push(['fan-in-12',fanIn(12),{}],['fan-in-48',fanIn(48),{}],
    ['many-groups-12x4',fanIn(48,12),{}]);
  for (const name of caseNames??[]) {
    if (!cases.some(([known])=>known===name)) throw new Error(`Unknown benchmark case: ${name}`);
  }
  const summarize = values => {
    const sorted = [...values].sort((a,b)=>a-b);
    return {samples:values.length,median:sorted[Math.floor(sorted.length/2)],
      p95:sorted[Math.min(sorted.length-1,Math.ceil(sorted.length*.95)-1)],max:sorted.at(-1)};
  };
  const results = [], transitions = [];
  window.routingBenchmarkResults = results;
  window.routingBenchmarkTransitions = transitions;
  const progress = (name, phase, details = {}) => {
    const state={status:'running',routingPolicy,initializationMode,name,phase,completedCases:results.length,
      results,transitions,...details};
    window.routingBenchmarkProgress=state;
    if (onProgress) onProgress(state);
  };
  const managerOf = () => instance.visualizer.dataViz.jsPlumbInstance;
  const initialized = new WeakSet();
  const initialization = {mode:initializationMode,initializedManagers:0,emptyManagers:0};
  if (initializationMode === 'initial-policy') {
    // Bootstrap only discovers the bundled manager class. It contributes no
    // geometry, routes, plans, or manager instance to the measured creations.
    progress(null,'initial-policy-bootstrap');
    window.instance?.destroy();
    window.instance = reviewCreate({lang:'java',trace:base,element:document.getElementById('diagram')});
    const prototype = Object.getPrototypeOf(managerOf());
    const originalConnect = prototype.connect;
    if (typeof originalConnect !== 'function' || typeof prototype.setReferenceRoutingPolicy !== 'function') {
      throw new Error('This build cannot initialize an internal routing policy before the first connection');
    }
    instance.destroy();
    window.instance = undefined;
    const diagram = document.getElementById('diagram');
    prototype.connect = function (...args) {
      if (this.container === diagram || diagram.contains(this.container)) {
        if (!initialized.has(this)) {
          if (this.connections.length !== 0) throw new Error('Initial policy selection was late');
          this.setReferenceRoutingPolicy(routingPolicy);
          if (this.referenceRoutingPolicy !== routingPolicy) throw new Error('Initial policy selection failed');
          initialized.add(this);
          initialization.initializedManagers++;
        }
      }
      return originalConnect.apply(this,args);
    };
    restoreInitialization = () => { prototype.connect = originalConnect; };
  }
  const configure = () => {
    const manager = managerOf();
    if (initializationMode === 'initial-policy') {
      if (!initialized.has(manager) && manager.connections.length === 0) {
        // No references have been routed in an empty scene. Retain the setter's
        // work inside the measured creation instead of silently skipping it.
        manager.setReferenceRoutingPolicy(routingPolicy);
        initialized.add(manager);
        initialization.emptyManagers++;
      }
      if (!initialized.has(manager) || manager.referenceRoutingPolicy !== routingPolicy) {
        throw new Error('A nonempty manager missed initial policy selection');
      }
      return manager;
    }
    if (typeof manager.setReferenceRoutingPolicy === 'function') {
      manager.setReferenceRoutingPolicy(routingPolicy);
    } else if (routingPolicy !== 'historical') {
      throw new Error(`This build does not support internal routing policy ${routingPolicy}`);
    }
    return manager;
  };
  const planSummary = manager => {
    const plan = manager.referenceSharingPlan;
    return plan ? {baselineValid:plan.baselineValid,accepted:plan.accepted,profilesTried:plan.profilesTried,
      groups:plan.groups?.map(group=>({id:group.id,targetKey:group.targetKey,kind:group.kind,
        members:group.members?.length})),diagnostics:plan.diagnostics} : null;
  };
  const signature = manager => JSON.stringify(manager.connections.map(connection => ({
    source:connection.sourceId.replace(/^v\d+__/,''),
    target:connection.targetId.replace(/^v\d+__/,''),
    path:connection.pathElement.getAttribute('d'),head:connection.arrowElement.getAttribute('points'),
  })).sort((a,b)=>a.source.localeCompare(b.source)));
  for (const [name,trace,options] of cases) {
    if (caseNames && !caseNames.includes(name)) continue;
    let phase='fresh-layout';
    progress(name,phase,{sample:0,samples:6});
    try {
    const layout = [];
    for (let n=0;n<6;n++) {
      window.instance?.destroy();
      const start = performance.now();
      window.instance = reviewCreate({lang:'java',trace,element:document.getElementById('diagram'),options});
      configure();
      await document.fonts.ready;
      instance.redrawConnectors();
      layout.push(performance.now()-start);
      progress(name,phase,{sample:n+1,samples:6});
    }
    phase='warm-repaint';
    progress(name,phase);
    const manager = managerOf();
    for (let n=0;n<5;n++) manager.repaintEverything();
    const repaint = [], stepping=[];
    phase='repaint-and-redraw';
    progress(name,phase,{sample:0,samples:40});
    for (let n=0;n<40;n++) {
      let start = performance.now(); manager.repaintEverything(); repaint.push(performance.now()-start);
      start = performance.now(); instance.redrawConnectors(); stepping.push(performance.now()-start);
      if ((n+1)%10===0) progress(name,phase,{sample:n+1,samples:40});
    }
    let reads=0;
    const original=Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect=function(){reads++;return original.call(this);};
    try { manager.repaintEverything(); } finally { Element.prototype.getBoundingClientRect=original; }
    results.push({name,objects:document.querySelectorAll('.heapObject').length,
      references:manager.connections.length,layout:summarize(layout),repaint:summarize(repaint),
      redrawWithValueLayout:summarize(stepping),boundingRectReads:reads,
      samples:{layout,repaint,redrawWithValueLayout:stepping},
      routeGeometry:signature(manager),
      baselineOrdering:manager.routing?.baselineOrdering??null,
      sharing:planSummary(manager)});
    progress(name,'complete');
    } catch(error) {
      results.push({name,phase,error:String(error?.message??error)});
      progress(name,'failed');
    }
  }
  if (includeTransitions) {
    try {
    progress('transitions','setup');
    const trace = fanIn(12,3), initial = trace.trace[0];
    const reassigned = structuredClone(initial);
    reassigned.stack_to_render[0].encoded_locals.alias0 = ['REF',1001];
    const mutated = structuredClone(reassigned);
    mutated.heap[1001][2][1] = 99;
    trace.trace = [initial,reassigned,mutated];
    window.instance?.destroy();
    window.instance = reviewCreate({lang:'java',trace,element:document.getElementById('diagram')});
    configure();
    const visit = index => {
      instance.visualizer.curInstr = index;
      instance.updateOutput();
      configure();
      instance.redrawConnectors();
    };
    for (let n=0;n<5;n++) {visit(1);visit(2);visit(0);}
    for (const [name,from,to] of [['assignment',0,1],['mutation',1,2],['backward',2,1],['direct-restore',2,0]]) {
      progress(name,'state-transition',{sample:0,samples:40});
      const values=[];
      for (let n=0;n<40;n++) {
        visit(from);
        const start=performance.now();visit(to);values.push(performance.now()-start);
      }
      transitions.push({name,latency:summarize(values),samples:values,baselineOrdering:managerOf().routing?.baselineOrdering??null,
        sharing:planSummary(managerOf())});
      progress(name,'complete');
    }
    visit(0);const original=signature(managerOf());
    visit(1);visit(2);visit(0);
    transitions.push({name:'restored-state-paths',equivalent:signature(managerOf())===original});
    const styles=[];
    progress('persistent-color-change-and-restore','style-transition',{sample:0,samples:40});
    for (let n=0;n<40;n++) {
      const manager=managerOf(), connection=manager.connections[0];
      const previous={...connection.paintStyle};
      const start=performance.now();
      connection.setPaintStyle({strokeStyle:'#765432'});
      connection.setPaintStyle(previous);
      styles.push(performance.now()-start);
    }
    transitions.push({name:'persistent-color-change-and-restore',latency:summarize(styles),samples:styles,
      restoredPaths:signature(managerOf())===original,baselineOrdering:managerOf().routing?.baselineOrdering??null,
      sharing:planSummary(managerOf())});
    } catch(error) {
      transitions.push({name:'transition-failure',error:String(error?.message??error)});
      progress('transitions','failed');
    }
  }
  progress(null,'complete',{status:'complete'});
  return {startedAt,completedAt:new Date().toISOString(),browser:navigator.userAgent,viewport:[innerWidth,innerHeight],
    hardware,assetRevision,routingPolicy,initialization,
    assets:[...document.scripts].map(script=>script.src).filter(Boolean),
    method:initializationMode === 'initial-policy'
      ? '6 new public-create layouts with policy selected before each manager first connection; untimed bootstrap discovers manager prototype only; first-connect wrapper and setter work included; font readiness and final redraw included; 5 warmups; 40 repaint and 40 redraw samples; assets warm'
      : '6 new-instance layouts; 5 warmups; 40 repaint and 40 redraw samples; assets warm; public creation initially historical; internal policy switch and final redraw included in layouts',
    transitionMethod:'40 samples per operation after 5 full-state warmup sequences; state update plus redraw; style metric includes change and restoration',
    results,transitions};
  } finally {
    restoreInitialization();
    window.routingBenchmarkActive = false;
  }
}

// Preserve the existing policy-switch measurement. The separate entry point
// measures initialization directly under the selected internal policy.
window.benchmarkRouting = options => runRoutingBenchmark(options,'policy-switch');
window.benchmarkRoutingInitialPolicy = options => runRoutingBenchmark(options,'initial-policy');
