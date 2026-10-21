#!/usr/bin/env node
/** Evaluation-only routing interventions; production files are never rewritten. */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {createRequire} = require('node:module');
const {performance} = require('node:perf_hooks');
const root = path.resolve(__dirname, '../..');
const frontend = path.join(root, 'cs1302_code_visualizer/frontend');
const sourceRoot = path.join(frontend, 'js');
const frontendRequire = createRequire(path.join(frontend, 'package.json'));
const ts = frontendRequire('typescript');
const {JSDOM} = frontendRequire('jsdom');
const dom = new JSDOM('<!doctype html><html><body></body></html>', {pretendToBeVisual:true});
for (const name of ['window','document','HTMLElement','Element','Node','NodeFilter','DOMRect','Range','SVGElement']) {
  global[name] = name === 'window' ? dom.window : name === 'document' ? dom.window.document : dom.window[name];
}
global.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);

const args = process.argv.slice(2);
const arg = flag => args.includes(flag) ? args[args.indexOf(flag)+1] : undefined;
if (args.includes('--help')) {
  process.stdout.write('Usage: node scripts/benchmark_reference_routing/evaluate-policies.cjs [--out FILE] [--fixtures name,name] [--routing-policy historical|independent]\n');
  process.exit(0);
}
const routingPolicy=arg('--routing-policy')??'historical';
if(!['historical','independent'].includes(routingPolicy))throw new Error('Evaluation routing policy must be historical or independent');
// Freeze source bytes for the whole run even when another agent is editing.
const sourceSnapshot=new Map(fs.readdirSync(sourceRoot).filter(name=>name.endsWith('.ts'))
  .map(name=>{const filename=path.join(sourceRoot,name);return [filename,fs.readFileSync(filename,'utf8')];}));
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const comparator = 'a.a.source[1]-b.a.source[1]||a.a.source[0]-b.a.source[0]||a.a.target.left-b.a.target.left||a.a.target.top-b.a.target.top||';
let intervention = {name:'baseline'};
function replaceOnce(source, anchor, replacement, label) {
  if (source.split(anchor).length !== 2) throw new Error(`Evaluation anchor drift (${label}); update the intervention before comparing results`);
  return source.replace(anchor, replacement);
}
require.extensions['.ts'] = (module, filename) => {
  if(filename.startsWith(sourceRoot+path.sep)&&!sourceSnapshot.has(filename)) {
    throw new Error(`Module appeared after source snapshot: ${filename}; rerun for coherent provenance`);
  }
  let source = sourceSnapshot.get(filename)??fs.readFileSync(filename, 'utf8');
  if (filename === path.join(sourceRoot, 'connectorRouting.ts')) {
    if (intervention.name === 'target-order') {
      source = replaceOnce(source, comparator,
        'a.a.target.left-b.a.target.left||a.a.target.top-b.a.target.top||String(a.a.targetKey).localeCompare(String(b.a.targetKey))||a.a.source[1]-b.a.source[1]||a.a.source[0]-b.a.source[0]||', 'target order');
    }
    if (intervention.name === 'port-order') {
      const anchor = 'a.lane=arrivals.get(a.targetOwner)??0;';
      source = replaceOnce(source, anchor, `${anchor}\n` +
        'const peers=edges.filter(e=>e.a.targetKey===a.targetKey);\n' +
        '(a as any).evaluationPortFraction=(peers.findIndex(e=>e.a===a)+1)/(peers.length+1);', 'port rank');
    }
    if (intervention.name === 'local-priority') {
      const sourceId = JSON.stringify(intervention.sourceId);
      source = replaceOnce(source, comparator,
        `Number(b.c.sourceId===${sourceId})-Number(a.c.sourceId===${sourceId})||${comparator}`, 'local priority');
    }
  }
  if (filename === path.join(sourceRoot, 'referenceRouting.ts')) {
    if (intervention.name === 'port-order') {
      const anchor = '  // Compare against the shortest clear direct/one-bend route across arrivals.';
      source = replaceOnce(source, anchor,
        '  const fraction=(a as any).evaluationPortFraction??.5;\n' +
        '  const portScore=({tip,normal}:{tip:Point;normal:Point})=>\n' +
        '    (normal[0]?Math.abs(tip[1]-(t.top+(t.bottom-t.top)*fraction)):Math.abs(tip[0]-(t.left+(t.right-t.left)*fraction)))+\n' +
        '    .01*(Math.abs(tip[0]-s[0])+Math.abs(tip[1]-s[1]));\n' +
        '  tips.sort((x,y)=>portScore(x)-portScore(y));\n' + anchor, 'port order');
    }
    if (intervention.name === 'straight-first') {
      const anchor = '  // Keep the existing right-first ordering for narrow departure fallbacks.';
      source = replaceOnce(source, anchor,
        '  for(const {tip,normal} of tips) {\n' +
        '    const h=head(tip,normal),e=rear(h);\n' +
        '    if(s[0]!==e[0]&&s[1]!==e[1])continue;\n' +
        '    if((s[0]-e[0])*normal[0]+(s[1]-e[1])*normal[1]<0)continue;\n' +
        '    const direct=polyline([s,e],h,0);\n' +
        '    if(acceptCandidate(direct,strict))return direct;\n' +
        '  }\n' + anchor, 'straight precedence');
    }
  }
  const compiled = ts.transpileModule(source, {fileName:filename, compilerOptions:{
    module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true,
  }});
  module._compile(compiled.outputText, filename);
};

function loadManager(variant) {
  intervention = variant;
  for (const filename of Object.keys(require.cache)) {
    if (filename.startsWith(sourceRoot+path.sep)) delete require.cache[filename];
  }
  return require(path.join(sourceRoot, 'svgConnectors.ts')).SvgConnectorManager;
}

/** Same measured-rectangle seam as frontend/tests/routingFixture.ts, without Vitest. */
function replay(data, Manager, reverse = false) {
  document.body.innerHTML = '<div class="ExecutionVisualizer"><div id="dataViz"></div></div>';
  const container = document.querySelector('.ExecutionVisualizer'), scene = document.getElementById('dataViz');
  const measure = (element, rect) => {element.getBoundingClientRect = () => new DOMRect(rect.x,rect.y,rect.width,rect.height);};
  const region={x:0,y:0,width:data.bounds.right-data.bounds.left,height:data.bounds.bottom-data.bounds.top};
  measure(container,region);measure(scene,region);
  const bodies=new Map();
  for (const shape of data.shapes.filter(s=>s.className==='heapObject'||s.className.includes('stackFrame'))) {
    const owner=document.createElement('div');owner.id=shape.id;owner.className=shape.className;
    scene.append(owner);measure(owner,shape);
    const body=document.createElement('table');body.className=shape.text.startsWith('String[]')?'listTbl':'instTbl';
    owner.append(body);
    const target=data.connectors.find(c=>c.targetId===shape.id)?.targetBody;
    const table=data.shapes.find(t=>t.className.includes('Tbl')&&t.x>=shape.x&&t.x+t.width<=shape.x+shape.width+.1&&
      t.y>=shape.y&&t.y+t.height<=shape.y+shape.height+.1);
    measure(body,target??table??shape);bodies.set(shape.id,body);
  }
  for (const edge of data.connectors) {
    const box=document.createElement('span');box.className='value-box';
    (bodies.get(edge.sourceOwner)??scene).append(box);measure(box,edge.sourceBox);
    const source=document.createElement('div');source.id=edge.sourceId;box.append(source);measure(source,edge.source);
  }
  const texts=new Map();
  for (const text of data.texts) {
    const span=document.createElement('span');span.textContent=text.text;scene.append(span);measure(span,text);
    const rect=new DOMRect(text.x,text.y,text.width,text.height);texts.set(span,rect);texts.set(span.firstChild,rect);
  }
  Range.prototype.getClientRects=function(){const rect=texts.get(this.commonAncestorContainer);return rect?[rect]:[];};
  const manager=new Manager({Container:container});
  manager.beginBatch();
  if (manager.setReferenceRoutingPolicy) manager.setReferenceRoutingPolicy(routingPolicy);
  else if(routingPolicy!=='historical')throw new Error('This source snapshot does not expose controlled routing policy');
  for (const edge of reverse?[...data.connectors].reverse():data.connectors) {
    manager.connect({source:edge.sourceId,target:edge.targetId});
  }
  manager.endBatch();
  return manager;
}

const subtract=(a,b)=>[a[0]-b[0],a[1]-b[1]];
const cross=(a,b)=>a[0]*b[1]-a[1]*b[0];
const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
function pathGeometry(data) {
  const tokens=data.match(/[MLCQ]|[-+]?(?:\d*\.\d+|\d+)(?:e[-+]?\d+)?/gi)??[];
  let i=0,current=[0,0];const segments=[];
  const point=()=>[Number(tokens[i++]),Number(tokens[i++])];
  while(i<tokens.length) {
    const op=tokens[i++];if(op==='M'){current=point();continue;}
    if(!['L','Q','C'].includes(op))throw new Error(`Unsupported path command: ${op}`);
    const controls=[current,...Array.from({length:op==='C'?3:op==='Q'?2:1},point)];
    const samples=[current];
    for(let step=1;step<=(controls.length===2?1:64);step++) {
      const t=step/(controls.length===2?1:64);let layer=controls;
      while(layer.length>1)layer=layer.slice(1).map((p,j)=>[layer[j][0]*(1-t)+p[0]*t,layer[j][1]*(1-t)+p[1]*t]);
      samples.push(layer[0]);
    }
    segments.push({controls,samples});current=controls.at(-1);
  }
  const points=segments.flatMap((segment,index)=>index?segment.samples.slice(1):segment.samples);
  let turnRegions=segments.filter(segment=>segment.controls.length>2).length;
  for(let j=1;j<segments.length;j++) {
    const before=segments[j-1].controls,after=segments[j].controls;
    const u=subtract(before.at(-1),before.at(-2)),v=subtract(after[1],after[0]);
    if(Math.abs(cross(u,v))>1e-5)turnRegions++;
  }
  return {points,turnRegions,length:points.slice(1).reduce((sum,p,j)=>sum+distance(points[j],p),0)};
}

function intersections(left,right) {
  const hits=[];
  for(let i=1;i<left.length;i++)for(let j=1;j<right.length;j++) {
    const a=left[i-1],b=right[j-1],u=subtract(left[i],a),v=subtract(right[j],b),det=cross(u,v);
    if(Math.abs(det)<1e-8)continue;
    const w=subtract(b,a),t=cross(w,v)/det,s=cross(w,u)/det;
    // Count transverse crossings, including vertices introduced by sampling.
    if(t>=0&&t<=1&&s>=0&&s<=1) {
      const hit=[a[0]+t*u[0],a[1]+t*u[1]];
      if(!hits.some(previous=>distance(previous,hit)<.5))hits.push(hit);
    }
  }
  return hits;
}

function snapshot(manager,data) {
  const routes=manager.connections.map(connection=>{
    const d=connection.pathElement.getAttribute('d'),head=connection.arrowElement.getAttribute('points');
    const geometry=pathGeometry(d),tip=head.split(' ')[0].split(',').map(Number);
    return {sourceId:connection.sourceId,targetId:connection.targetId,d,head,
      ...geometry,length:geometry.length+distance(geometry.points.at(-1),tip),crossings:0};
  }).sort((a,b)=>a.sourceId.localeCompare(b.sourceId));
  const crossings=[];
  for(let i=0;i<routes.length;i++)for(let j=i+1;j<routes.length;j++) {
    for(const point of intersections(routes[i].points,routes[j].points)) {
      // Shared same-target terminal contacts are not ordinary crossings.
      const aEnd=routes[i].points.at(-1),bEnd=routes[j].points.at(-1);
      if(routes[i].targetId===routes[j].targetId&&(distance(point,aEnd)<1||distance(point,bEnd)<1))continue;
      crossings.push({sources:[routes[i].sourceId,routes[j].sourceId],point});
      routes[i].crossings++;routes[j].crossings++;
    }
  }
  const textHits=routes.flatMap(route=>data.texts.filter(text=>route.points.some(([x,y])=>
    x>text.x&&x<text.x+text.width&&y>text.y&&y<text.y+text.height)).map(text=>({source:route.sourceId,text:text.text})));
  return {routes,crossings,textHits,baselineValid:manager.referenceSharingPlan?.baselineValid??null,
    baselineOrdering:manager.routing?.baselineOrdering??null,
    totalLength:routes.reduce((sum,route)=>sum+route.length,0),
    totalTurnRegions:routes.reduce((sum,route)=>sum+route.turnRegions,0),
    signature:hash(JSON.stringify(routes.map(({sourceId,targetId,d,head})=>({sourceId,targetId,d,head}))))};
}

function measure(data,variant) {
  const Manager=loadManager(variant),started=performance.now();
  try {
    const first=snapshot(replay(data,Manager),data);
    const elapsedMs=performance.now()-started;
    const reverse=snapshot(replay(data,Manager,true),data);
    return {...first,elapsedMs,insertionOrderEquivalent:first.signature===reverse.signature};
  } catch(error) {return {error:String(error.message),elapsedMs:performance.now()-started};}
}
function compact(result) {
  if(result.error)return result;
  return {...result,routes:result.routes.map(({points,...route})=>route)};
}

function synthetic(name) {
  const straight=name==='synthetic-straight';
  const ys=straight?[50]:[45,85,125,165];
  const shapes=[{id:'frame',className:'stackFrame',x:20,y:20,width:straight?100:110,height:straight?55:170,text:'main'}];
  const targets=straight?[{x:70,y:180,width:80,height:55}]:[
    {x:300,y:30,width:100,height:60},{x:300,y:145,width:100,height:60}];
  targets.forEach((rect,i)=>shapes.push({id:`target${i}`,className:'heapObject',...rect,text:'Node'}));
  const connectors=ys.map((y,i)=>{
    const box={x:80,y:y-10,width:40,height:20},target=straight?0:i%2;
    return {sourceId:`source${i}`,sourceOwner:'frame',targetId:`target${target}`,
      source:box,sourceBox:box,targetBody:targets[target]};
  });
  const texts=targets.map(rect=>({x:rect.x+8,y:rect.y+8,width:30,height:12,text:'Node'}));
  return {bounds:{left:0,top:0,right:460,bottom:280},shapes,connectors,texts};
}

const fixtureDir=path.join(frontend,'tests/fixtures/reference-routing');
const names=arg('--fixtures')?.split(',')??[
  'later-node-compact','later-node-inline','later-node-default','aliases-default',
  'cycle-default','self-loop-default','fields-default','arrays-default','arrays-compact',
  'synthetic-interleaved','synthetic-straight',
];
const report={generatedAt:new Date().toISOString(),node:process.version,routingPolicy,
  method:'Production manager with measured DOM rectangles; evaluation-only in-memory source interventions; source bytes frozen for the run',
  limitations:['No browser/CSS/font/export acceptance; Node elapsed values are not browser budgets.',
    'Curve metrics use 64 samples per curve. Crossings are transverse centerline intersections; turnRegions is a drawing-complexity proxy, not the merger admission bend count.',
    'Sampled text checks supplement the production validator; they do not establish full clearance.',
    'The bounded pass tries at most four source-priority orders, freezes routes outside a local neighborhood on admission, and does not claim optimality.'],
  sourceHashes:Object.fromEntries([...sourceSnapshot].map(([filename,source])=>[path.basename(filename),hash(source)])),results:[]};
for(const name of names) {
  const data=name.startsWith('synthetic-')?synthetic(name):JSON.parse(fs.readFileSync(path.join(fixtureDir,`${name}.json`),'utf8'));
  if(!data.connectors)throw new Error(`${name} is not a measured-manager fixture`);
  const baseline=measure(data,{name:'baseline'});
  const variants=Object.fromEntries(['target-order','port-order','straight-first'].map(policy=>[policy,measure(data,{name:policy})]));
  const local={attempted:0,accepted:false,reason:'baseline failed',trials:[],result:baseline};
  if(!baseline.error) {
    local.reason='no non-degrading local improvement';
    const candidates=[...baseline.routes].sort((a,b)=>b.crossings-a.crossings||b.length-a.length||a.sourceId.localeCompare(b.sourceId)).slice(0,4);
    for(const focused of candidates) {
      const neighbors=new Set([focused.sourceId,...baseline.routes.filter(route=>route.targetId===focused.targetId).map(route=>route.sourceId),
        ...baseline.crossings.filter(c=>c.sources.includes(focused.sourceId)).flatMap(c=>c.sources)]);
      const candidate=measure(data,{name:'local-priority',sourceId:focused.sourceId});local.attempted++;
      if(candidate.error||candidate.textHits.length||!candidate.insertionOrderEquivalent) {
        local.trials.push({sourceId:focused.sourceId,error:candidate.error??'sampled text collision or insertion-order mismatch'});continue;
      }
      const unchangedOutside=candidate.routes.every(route=>neighbors.has(route.sourceId)||baseline.routes.some(original=>
        original.sourceId===route.sourceId&&original.d===route.d&&original.head===route.head));
      const noMemberStretch=candidate.routes.every(route=>baseline.routes.some(original=>original.sourceId===route.sourceId&&
        route.length<=original.length+.01&&route.turnRegions<=original.turnRegions));
      const current=local.result;
      const admitted=unchangedOutside&&noMemberStretch&&candidate.crossings.length<=current.crossings.length&&
        candidate.totalLength<=current.totalLength+.01&&candidate.totalTurnRegions<=current.totalTurnRegions&&
        (candidate.crossings.length<current.crossings.length||candidate.totalLength<current.totalLength-.01||candidate.totalTurnRegions<current.totalTurnRegions);
      local.trials.push({sourceId:focused.sourceId,unchangedOutside,noMemberStretch,admitted,
        crossings:candidate.crossings.length,totalLength:candidate.totalLength,totalTurnRegions:candidate.totalTurnRegions});
      if(admitted) {
        local.accepted=true;local.reason='non-degrading local improvement';local.sourceId=focused.sourceId;local.result=candidate;
      }
    }
  }
  report.results.push({name,fixtureHash:hash(JSON.stringify(data)),baseline:compact(baseline),
    variants:Object.fromEntries(Object.entries(variants).map(([key,value])=>[key,compact(value)])),
    boundedLocal:{...local,result:compact(local.result)}});
}
const output=JSON.stringify(report,null,2)+'\n',destination=arg('--out');
if(destination){fs.mkdirSync(path.dirname(path.resolve(destination)),{recursive:true});fs.writeFileSync(destination,output);}
else process.stdout.write(output);
dom.window.close();
