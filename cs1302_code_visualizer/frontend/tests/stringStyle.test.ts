import { beforeEach, describe, expect, it } from 'vitest';
import { create } from '../js/CodeVisualizer';
import { prepareStringTrace, validateStringStyle } from '../js/stringStyle';

const trace: any = { code: 'Node head;', trace: [{ event: 'step_line', line: 1,
  globals: {}, ordered_globals: [], heap: {
    1: ['INSTANCE', 'Node', ['item', ['REF', 3]], ['next', ['REF', 2]]],
    2: ['INSTANCE', 'Node', ['item', ['REF', 3]], ['next', ['REF', 1]]],
    3: ['INSTANCE', 'String', ['___NO_LABEL!___', 'Milk']],
    4: ['LIST', ['REF', 3], null, ['REF', 3]],
  }, heap_attrs: { 4: { type: 'String[]' } },
  stack_to_render: [{ func_name: 'main', frame_id: 0, unique_hash: 'main',
    is_highlighted: true, parent_frame_id_list: [], ordered_varnames: ['head', 'items', 's'],
    encoded_locals: { head: ['REF', 1], items: ['REF', 4], s: ['REF', 3] },
    locals_attrs: { head: { type: 'Node' }, items: { type: 'String[]' }, s: { type: 'String' } },
  }],
}] };
let root: HTMLDivElement;
beforeEach(() => { document.body.innerHTML = ''; root = document.createElement('div'); document.body.append(root); });

describe('string presentation', () => {
  it.each(['default', 'compact', 'inline'] as const)('renders %s without mutating the canonical trace', style => {
    const original = JSON.stringify(trace);
    const view = create({ lang: 'java', trace, element: root, options: { stringStyle: style } });
    expect(JSON.stringify(trace)).toBe(original);
    expect(root.querySelectorAll('.heapObject')).toHaveLength(style === 'default' ? 4 : 3);
    expect(root.querySelectorAll('.compact-string')).toHaveLength(style === 'compact' ? 5 : 0);
    expect(root.querySelectorAll('.compact-string-arrow')).toHaveLength(style === 'compact' ? 5 : 0);
    if (style === 'compact') {
      expect([...root.querySelectorAll('.compact-string > .value-box')].map(e => e.textContent)).toEqual(Array(5).fill('3'));
    }
    expect(root.querySelector('.heapObject[data-object-id="1"] > .typeLabel')?.textContent).toBe('Node@1');
    expect(root.querySelector('.heapObject[data-object-id="4"] > .typeLabel')?.textContent).toBe('String[]@4 (length 3)');
    view.destroy?.();
  });
  it('honors text-only references and hidden declared types', () => {
    create({ lang: 'java', trace, element: root,
      options: { stringStyle: 'compact', textualMemoryLabels: true, includeTypes: false } });
    expect(root.querySelectorAll('.compact-string-arrow,._svg_connector')).toHaveLength(0);
    expect(root.querySelectorAll('.compact-string')).toHaveLength(5);
    expect(root.textContent).toContain('Node@1');
  });
  it('rejects identity loss only in value positions, allows inline and preserves char tags', () => {
    const legacy = structuredClone(trace);
    legacy.trace[0].stack_to_render[0].encoded_locals.s = 'Milk' as any;
    for (const style of ['compact', 'default'] as const) {
      expect(() => prepareStringTrace(legacy, style)).toThrow('Regenerate');
    }
    expect(() => prepareStringTrace(legacy, 'inline')).not.toThrow();
    legacy.trace[0].stack_to_render[0].encoded_locals.s = ['CHAR-LITERAL', 'x'];
    expect(() => prepareStringTrace(legacy, 'default')).not.toThrow();
  });
  it('escapes empty, quoted and markup-like strings safely', () => {
    const special = structuredClone(trace);
    special.trace[0].heap[3][2][1] = '</span>\n"x"';
    create({ lang: 'java', trace: special, element: root, options: { stringStyle: 'compact' } });
    expect(root.querySelector('.compact-string > .stringObj')?.textContent).toBe(JSON.stringify('</span>\n"x"'));
  });
  it('rejects invalid styles', () => {
    expect(() => validateStringStyle('bad')).toThrow('stringStyle');
  });
  it.each(['compact', 'inline', 'default'] as const)('rebuilds %s strings through forward/backward steps', style => {
    const changing = structuredClone(trace);
    const second = structuredClone(changing.trace[0]);
    second.line = 2;
    second.heap[3][2][1] = '';
    changing.trace.push(second);
    const view = create({lang: 'java', trace: changing, element: root, options: {stringStyle: style}});
    for (const [method, expected] of [['stepBack', 'Milk'], ['stepForward', '""'], ['stepBack', 'Milk']]) {
      view.visualizer[method]();
      expect(root.textContent).toContain(expected);
      expect(root.querySelectorAll('.compact-string')).toHaveLength(style === 'compact' ? 5 : 0);
      expect(root.querySelectorAll('.value-box .value-box')).toHaveLength(0);
    }
  });
  it('preserves modern char values while rejecting modern inlined strings', () => {
    const modern: any = { code: 'char c;', steps: [{ line: 1, callStack: [
      {methodName: 'main', locals: [{name: 'c', type: 'char', value: 'x'}]}
    ], heap: {} }] };
    const view = create({lang: 'java', trace: modern, element: root});
    expect(root.textContent).toContain("'x'");
    view.destroy?.();
    modern.steps[0].callStack[0].locals[0].type = 'String';
    expect(() => create({lang: 'java', trace: modern, element: root})).toThrow('Regenerate');
  });

});
