/* THROWAWAY PROTOTYPE. Three compact layouts on one route, ?variant=A|B|C.
 * Snapshot fixtures model the linked course pages. This is not feature implementation.
 */
const variants = {
  A: {name:'A · Narrow', width:24, gap:12},
  B: {name:'B · Medium, aligned', width:32, gap:18, height:19, extraRightPadding:8, aligned:true},
  C: {name:'C · Wide', width:40, gap:24},
  default: {name:'Default · strings on the heap'},
  inline: {name:'Inline · literal inside the value box'},
};
const keys = Object.keys(variants);
const $ = id => document.getElementById(id);
const ref = id => ['REF', id];
// String tokens retain identity in the default view; inline/compact duplicate values.
const str = (value, id = value) => ({string:value, identity:id});
const field = (name, type, value) => ({name,type,value});
function object(type, fields) { return {type,fields}; }
function list(kind, values, base, capacity=5) {
  const heap = {};
  if (kind === 'ArrayBasedList') {
    heap[base] = object(kind,[field('size','int',values.length),field('array','String[]',ref(base+1))]);
    heap[base+1] = {type:'String[]',elements:[...values,...Array(Math.max(0,capacity-values.length)).fill(null)]};
  } else {
    heap[base] = object(kind,[field('size','int',values.length),field('head','Node',values.length?ref(base+1):null)]);
    values.forEach((value,i)=>heap[base+i+1]=object('Node',[
      field('item','String',value), field('next','Node',i+1<values.length?ref(base+i+2):null),
    ]));
  }
  return heap;
}
const groceries = ['Cheese','Milk','Bread','Ice Cream'].map(value=>str(value));
const scenarios = {
  nodes: () => ({
    description:'The introductory Node chain: Cheese → Bread → Milk. Each item stays inside its Node; next references retain their existing arrows.',
    code:'Node head = new Node("Cheese");\nhead.setNext(new Node("Bread"));\nhead.getNext().setNext(new Node("Milk"));',
    locals:[field('head','Node',ref(10))],
    heap:{10:object('Node',[field('item','String',str('Cheese')),field('next','Node',ref(11))]),
      11:object('Node',[field('item','String',str('Bread')),field('next','Node',ref(12))]),
      12:object('Node',[field('item','String',str('Milk')),field('next','Node',null)])},
  }),
  cycle: () => {
    const scenario=scenarios.nodes();
    scenario.description='Additional fixture: Cheese → Bread → Milk → Cheese. The last Node points back to head, forming a three-node cycle.';
    scenario.code+='\nhead.getNext().getNext().setNext(head);';
    scenario.heap[12].fields.find(f=>f.name==='next').value=ref(10);
    return scenario;
  },
  links: () => ({description:'List interface variable backed by LinkBasedList, after four insertions.',
    code:'List myList = new LinkBasedList();\nmyList.add(0, "Bread");\nmyList.add(0, "Cheese");\nmyList.add(1, "Milk");\nmyList.add(3, "Ice Cream");',
    locals:[field('myList','List',ref(10))],heap:list('LinkBasedList',groceries,10)}),
  array: () => ({description:'List interface variable backed by ArrayBasedList. Four occupied components and one unused null component.',
    code:'List myList = new ArrayBasedList();\nmyList.add(0, "Bread");\nmyList.add(0, "Cheese");\nmyList.add(1, "Milk");\nmyList.add(3, "Ice Cream");',
    locals:[field('myList','List',ref(10))],heap:list('ArrayBasedList',groceries,10)}),
  removed: () => ({description:'Both implementations after removing Cheese: Milk, Bread, Ice Cream. The array retains capacity five.',
    code:'// Each list previously contained Cheese, Milk, Bread, Ice Cream.\narrayList.remove(0);\nlinkList.remove(0);',
    locals:[field('arrayList','List',ref(10)),field('linkList','List',ref(20))],
    heap:{...list('ArrayBasedList',groceries.slice(1),10),...list('LinkBasedList',groceries.slice(1),20)}}),
  empty: () => ({description:'After clear(): five null array components, a null head, and size zero in both lists. No compact arrows should appear.',
    code:'arrayList.clear();\nlinkList.clear();',
    locals:[field('arrayList','List',ref(10)),field('linkList','List',ref(20))],
    heap:{...list('ArrayBasedList',[],10),...list('LinkBasedList',[],20)}}),
  shared: () => ({description:'Additional fixture: one String is shared by a stack variable, two Node items, and two array components. Default shows identity; compact repeats the literal.',
    code:'String shared = new String("Milk");\nNode head = new Node(shared);\nhead.setNext(new Node(shared));\nString[] items = { shared, shared, null };',
    locals:[field('shared','String',str('Milk','shared')),field('head','Node',ref(10)),field('items','String[]',ref(20))],
    heap:{10:object('Node',[field('item','String',str('Milk','shared')),field('next','Node',ref(11))]),
      11:object('Node',[field('item','String',str('Milk','shared')),field('next','Node',null)]),
      20:{type:'String[]',elements:[str('Milk','shared'),str('Milk','shared'),null]}}}),
  long: () => {
    const long = str('Extra creamy vanilla ice cream with chocolate sprinkles');
    const values = [str(''),str('A'),long,str('Say "hello"')];
    return {description:'Additional fixture: full, unwrapped strings in the stack and both list implementations. Includes an empty string, a single character, embedded quotes, and unused capacity.',
      code:'String label = "Extra creamy vanilla ice cream with chocolate sprinkles";\n// Both lists contain: "", "A", label, "Say \\"hello\\"".',
      locals:[field('label','String',long),field('arrayList','List',ref(10)),field('linkList','List',ref(20))],
      heap:{...list('ArrayBasedList',values,10),...list('LinkBasedList',values,20)}};
  },
};

function traceFor(scenario, style) {
  const heap={}, attrs={}, ids=new Map(); let next=1000;
  function encode(value) {
    if (!value || !Object.hasOwn(value,'string')) return value;
    if (style !== 'default') return value.string;
    if (!ids.has(value.identity)) {
      const id=next++; ids.set(value.identity,id);
      heap[id]=['INSTANCE','String',['___NO_LABEL!___',value.string]];
      attrs[id]={type:'java.lang.String'};
    }
    return ref(ids.get(value.identity));
  }
  Object.entries(scenario.heap).forEach(([id,obj])=>{
    heap[id]=obj.elements ? ['LIST',...obj.elements.map(encode)]
      : ['INSTANCE',obj.type,...obj.fields.map(f=>[f.name,encode(f.value)])];
    attrs[id]={type:obj.elements?obj.type:obj.fields.map(f=>f.type)};
  });
  const frame={func_name:'main',frame_id:1,unique_hash:'main_1',is_parent:false,is_zombie:false,is_highlighted:true,parent_frame_id_list:[],
    ordered_varnames:scenario.locals.map(f=>f.name),
    encoded_locals:Object.fromEntries(scenario.locals.map(f=>[f.name,encode(f.value)])),
    locals_attrs:Object.fromEntries(scenario.locals.map(f=>[f.name,{type:f.type}]))};
  return {code:scenario.code,trace:[{line:1,event:'step_line',func_name:'main',stack_to_render:[frame],globals:{},ordered_globals:[],heap,heap_attrs:attrs,stdout:'',stderr:''}]};
}

function triangleHead(x,y) {
  return `${x},${y} ${x-6},${y-3} ${x-6},${y+3}`;
}

function referenceValues(root,scenario) {
  // Recover compact strings' identities from the equivalent heap-string trace.
  const step=traceFor(scenario,'default').trace[0];
  const assign=(cell,value)=>{
    if (cell && Array.isArray(value) && value[0]==='REF') cell.dataset.prototypeRef=value[1];
  };
  root.querySelectorAll('.stackFrameValue').forEach((cell,index)=>{
    assign(cell,step.stack_to_render[0].encoded_locals[scenario.locals[index]?.name]);
  });
  root.querySelectorAll('.heapObject[data-object-id]').forEach(element=>{
    const object=step.heap[element.dataset.objectId];
    if (object[0]==='LIST') {
      element.querySelectorAll('.listElt').forEach((cell,index)=>assign(cell,object[index+1]));
    } else {
      const fields=new Map(object.slice(2));
      element.querySelectorAll('.instEntry').forEach(row=>{
        assign(row.querySelector('.instVal'),fields.get(row.querySelector('.keyObj')?.textContent));
      });
    }
  });
}

function compact(root, variant) {
  root.style.setProperty('--prototype-box',variant.width+'px');
  root.style.setProperty('--prototype-gap',variant.gap+'px');
  if (variant.aligned) root.style.setProperty('--prototype-height',variant.height+'px');
  // Measure native contents before changing any row's layout.
  const literals=[...root.querySelectorAll('.stringObj')];
  const widths=new Map();
  const cells=variant.aligned?[...root.querySelectorAll('td.instVal,td.stackFrameValue,td.listElt')].map(cell=>{
    const table=cell.closest('table');
    const literal=cell.querySelector(':scope > .stringObj');
    const style=getComputedStyle(cell);
    const padding=parseFloat(style.paddingLeft)+parseFloat(style.paddingRight);
    const border=parseFloat(style.borderLeftWidth)+parseFloat(style.borderRightWidth);
    const range=document.createRange(); range.selectNodeContents(cell);
    let contentWidth=!literal && cell.textContent.trim()?range.getBoundingClientRect().width:0;
    if (cell.dataset.prototypeRef) {
      const measure=document.createElement('span'); measure.textContent=cell.dataset.prototypeRef;
      cell.append(measure); contentWidth=measure.getBoundingClientRect().width; measure.remove();
    }
    widths.set(table,Math.max(widths.get(table)||variant.width,Math.ceil(contentWidth+padding+border)));
    return {cell,table,literal};
  }):[];
  root.classList.toggle('prototype-aligned',!!variant.aligned);
  widths.forEach((width,table)=>{
    width+=variant.extraRightPadding;
    widths.set(table,width);
    table.style.setProperty('--prototype-box',width+'px');
  });
  cells.forEach(({cell,literal})=>{
    if (literal) return;
    cell.classList.add('prototype-value-cell');
    const box=document.createElement('div'); box.className='prototype-box prototype-value-box';
    if (cell.dataset.prototypeRef) {
      box.classList.add('prototype-reference-box');
      cell.querySelector('div').textContent=cell.dataset.prototypeRef;
    }
    box.append(...cell.childNodes); cell.append(box);
  });
  literals.forEach(literal=>{
    const cell=literal.parentElement;
    if (!cell.matches('.instVal,.stackFrameValue,.listElt')) return;
    cell.classList.add('prototype-string-cell');
    const pair=document.createElement('span'); pair.className='prototype-pair';
    const box=document.createElement('span'); box.className='prototype-box';
    if (variant.aligned) {
      box.classList.add('prototype-reference-box'); box.textContent=cell.dataset.prototypeRef;
    } else box.setAttribute('aria-hidden','true');
    const width=widths.get(cell.closest('table'))||variant.width;
    const end=width+variant.gap-3, start=variant.aligned?width-8:width/2;
    // B uses the same clean triangle for string and non-string references.
    const head=variant.aligned?triangleHead(end,10):`${end},10 ${end-5},6.5 ${end-2.25},10 ${end-5},13.5`;
    const shaftEnd=variant.aligned?end-6:end;
    pair.innerHTML=`<svg class="prototype-arrow" width="${end+1}" viewBox="0 0 ${end+1} 20" aria-hidden="true"><path d="M${start} 10 H${shaftEnd}" fill="none" stroke-width="1"/><circle cx="${start}" cy="10" r="3"/><polygon points="${head}"/></svg>`;
    pair.prepend(box); cell.append(pair); pair.append(literal);
  });
}

function horizontalReferenceExits(instance) {
  // Prototype-only instance overrides: inset source dots 8 px from right borders,
  // and delay the first bend until 4 px inside the enclosing right border.
  const manager=instance.visualizer.dataViz.jsPlumbInstance;
  const returns=manager.connections.filter(connection=>{
    const source=connection.source[0]?.closest('.heapObject');
    const target=connection.target[0]?.closest('.heapObject');
    return source && target && target.getBoundingClientRect().left<=source.getBoundingClientRect().left;
  });
  if (returns.length) {
    // Reserve space for the external return lanes inside the scrollable panel.
    manager.container.style.paddingBottom=(32+returns.length*12)+'px';
    manager.container.style.paddingRight=(24+returns.length*12)+'px';
  }
  manager.connections.forEach(connection=>{
    const source=connection.source[0];
    const valueBox=source?.closest('.prototype-value-box');
    if (!valueBox) return;
    const enclosure=source.closest('.instTbl,.listTbl,.stackFrame');
    if (!enclosure) return;
    const originalUpdate=connection.update.bind(connection);
    connection.update=()=>{
      originalUpdate();
      const origin=manager.container.getBoundingClientRect();
      const box=valueBox.getBoundingClientRect();
      const x1=box.right-8-origin.left;
      const y1=box.top+box.height/2-origin.top;
      connection.dotElement.setAttribute('cx',x1);
      connection.dotElement.setAttribute('cy',y1);
      const [x2,y2]=connection.arrowElement.getAttribute('points').split(' ')[0].split(',').map(Number);
      const exit=Math.max(x1,enclosure.getBoundingClientRect().right-origin.left-4);
      const shaftEnd=x2-6;
      const bend=shaftEnd>=exit?(shaftEnd-exit)/2:40;
      let route=`M ${x1} ${y1} H ${exit} C ${exit+bend} ${y1} ${shaftEnd-bend} ${y2} ${shaftEnd} ${y2}`;
      const lane=returns.indexOf(connection);
      if (lane!==-1) {
        const objects=[...manager.container.querySelectorAll('.heapObject')].map(e=>e.getBoundingClientRect()).filter(r=>r.width && r.height);
        const enclosureRect=enclosure.getBoundingClientRect();
        const targetRect=connection.target[0].getBoundingClientRect();
        const crossed=objects.filter(r=>r.right>=targetRect.left && r.left<=enclosureRect.right);
        const bottom=Math.max(...crossed.map(r=>r.bottom))-origin.top+24+lane*12;
        const right=enclosureRect.right-origin.left+16+lane*12;
        const left=targetRect.left-origin.left-20-lane*12;
        const radius=8;
        route=`M ${x1} ${y1} H ${exit} C ${right} ${y1} ${right} ${y1} ${right} ${y1+radius}`
          +` V ${bottom-radius} Q ${right} ${bottom} ${right-radius} ${bottom}`
          +` H ${left+radius} Q ${left} ${bottom} ${left} ${bottom-radius}`
          +` V ${y2+radius} Q ${left} ${y2} ${left+radius} ${y2} H ${shaftEnd}`;
        connection.pathElement.dataset.prototypeReturn='true';
      }
      connection.pathElement.setAttribute('d',route);
      connection.arrowElement.setAttribute('points',triangleHead(x2,y2));
      connection.pathElement.dataset.prototypeSource=connection.sourceId;
    };
  });
}

let instances=[], serial=0;
async function render() {
  const generation=++serial;
  document.body.dataset.ready='false';
  instances.forEach(i=>i.destroy()); instances=[];
  const scenario=scenarios[$('example').value]();
  const selected=$('variant').value;
  const theme=$('theme').value;
  document.body.dataset.theme=theme;
  $('scenario').textContent=scenario.description;
  $('code').textContent=scenario.code;
  $('panels').replaceChildren();
  const params=new URLSearchParams({variant:selected,example:$('example').value,orientation:$('orientation').value,theme});
  if ($('compare').checked) params.set('compare','all');
  history.replaceState(null,'','?'+params);
  for (const key of $('compare').checked?keys:[selected]) {
    const variant=variants[key];
    const article=document.createElement('article');
    const title=document.createElement('h2'); title.textContent=variant.name;
    const head=document.createElement('div'); head.className='panel-header'; head.append(title);
    const description=document.createElement('p');
    description.textContent=variant.width?`${variant.width+(variant.extraRightPadding||0)} px ${variant.aligned?'minimum shared box width':'value box'} · ${variant.gap} px box-to-literal gap · ${variant.aligned?'19 px height; both borders aligned':'20 px height'}`
      :key==='default'?'Existing renderer · inline_strings=False':'Existing renderer · inline_strings=True';
    head.append(description);
    const scroll=document.createElement('div'); scroll.className='scroll';
    const root=document.createElement('div'); root.className='diagram'; root.id=`prototype-${generation}-${key}`;
    scroll.append(root);
    const metrics=document.createElement('p'); metrics.className='metrics';
    article.append(head,scroll,metrics); $('panels').append(article);
    const instance=CodeVisualizer.create({lang:'java',trace:traceFor(scenario,key),element:root,
      options:{theme,arrayOrientation:$('orientation').value,stripTypePrefixes:['java.lang.']}});
    instances.push(instance);
    await document.fonts.ready;
    if (generation!==serial) return;
    if (variant.aligned) {
      referenceValues(root,scenario);
      root.querySelectorAll('.heapObject[data-object-id]').forEach(element=>{
        const id=element.dataset.objectId;
        const object=scenario.heap[id];
        const label=element.querySelector(':scope > .typeLabel');
        if (object && label) label.textContent=`${object.type}@${id}`
          +(object.elements?` (length ${object.elements.length})`:'');
      });
    }
    if (variant.width) compact(root,variant);
    if (variant.aligned) horizontalReferenceExits(instance);
    instance.redrawConnectors();
    const elements=[...root.querySelectorAll('.stackFrame,.heapObject,._svg_connector path')];
    const rects=elements.map(e=>e.getBoundingClientRect()).filter(r=>r.width>0 && r.height>0);
    const width=Math.ceil(Math.max(...rects.map(r=>r.right))-Math.min(...rects.map(r=>r.left)));
    const height=Math.ceil(Math.max(...rects.map(r=>r.bottom))-Math.min(...rects.map(r=>r.top)));
    metrics.textContent=`Diagram bounds: ${width} × ${height} px · ${root.querySelectorAll('.prototype-pair').length} compact string references · 100% scale; scroll horizontally if needed`;
  }
  document.body.dataset.ready='true';
}
function cycle(delta) {
  $('variant').value=keys[(keys.indexOf($('variant').value)+delta+keys.length)%keys.length]; render();
}
const initial=new URLSearchParams(location.search);
for (const id of ['variant','example','orientation','theme']) {
  const value=initial.get(id);
  if ([...$(id).options].some(o=>o.value===value)) $(id).value=value;
  $(id).addEventListener('change',render);
}
$('compare').checked=initial.get('compare')==='all'; $('compare').addEventListener('change',render);
$('previous').onclick=()=>cycle(-1); $('next').onclick=()=>cycle(1);
document.addEventListener('keydown',event=>{
  if (event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
  if (event.key==='ArrowLeft'||event.key==='ArrowRight') {
    event.preventDefault(); event.stopImmediatePropagation(); cycle(event.key==='ArrowRight'?1:-1);
  }
},true);
window.addEventListener('resize',()=>instances.forEach(i=>i.redrawConnectors()));
window.prototype={render,traceFor,scenarios,variants};
render();
