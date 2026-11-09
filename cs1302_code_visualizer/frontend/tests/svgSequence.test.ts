import { describe, expect, it } from 'vitest';
import { createSequencePlayer } from '../js/svgSequence';

describe('shared SVG sequence', () => {
  it('seeks both ways, reuses unchanged nodes, and restores text, style, routes and removals', () => {
    const tag = (s: string) => `{http://www.w3.org/2000/svg}${s}`;
    const manifest = {version: 1, nodes: [
      [tag('text'), [['x', '1']], ['before < &']],
      [tag('path'), [['d', 'M0 0L1 1'], ['stroke', 'red']], []],
      [tag('svg'), [['viewBox', '0 0 10 10']], [0, 1]],
      [tag('path'), [['d', 'M1 1L8 8'], ['stroke', 'blue']], []],
      [tag('svg'), [['viewBox', '0 0 10 10']], [0, 3, 0]],
      [tag('text'), [['y', '2']], ['after']],
      [tag('svg'), [['viewBox', '0 0 20 20']], [5]],
    ], frames: [2, 4, 6]};
    const host = document.createElement('div');
    const player = createSequencePlayer(host, manifest);
    player.seek(0);
    const original = player.serialize();
    const text = host.querySelector('text');
    player.seek(1);
    expect(host.querySelector('text')).toBe(text);
    expect(host.querySelectorAll('text')).toHaveLength(2);
    expect(host.querySelector('path')?.getAttribute('stroke')).toBe('blue');
    expect(host.querySelector('path')?.getAttribute('d')).toBe('M1 1L8 8');
    player.seek(2);
    expect(host.querySelector('text')?.hasAttribute('x')).toBe(false);
    expect(host.textContent).toBe('after');
    expect(host.querySelector('path')).toBeNull();
    for (let i = 0; i < 100; i++) { player.seek(1); player.seek(2); }
    expect(host.querySelectorAll('*')).toHaveLength(2);
    player.seek(0);
    expect(player.serialize()).toBe(original);
    expect(() => player.seek(-1)).toThrow(RangeError);
    expect(() => player.seek(3)).toThrow(RangeError);
    expect(() => player.seek(0.5)).toThrow(RangeError);
  });
});
