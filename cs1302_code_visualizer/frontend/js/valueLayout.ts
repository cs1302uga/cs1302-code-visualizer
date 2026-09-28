import { ARROW_LENGTH, SOURCE_INSET, SOURCE_RADIUS, arrowTriangle } from "./connectorGeometry";
import { paint } from "./theme";

const valueCellSelector = 'td.instVal,td.classVal,td.dictVal,td.stackFrameValue,td.listElt,td.tupleElt,td.stackElt,td.queueElt,td.setElt';

/** Create a value surface at render time; compound objects keep their own layout. */
export function createValueBox(cell: HTMLElement): HTMLElement {
  if (!cell.matches(valueCellSelector)) return cell;
  cell.classList.add('value-cell');
  const box = document.createElement('span');
  box.className = 'value-box';
  cell.append(box);
  return box;
}

/** Shared value-box layout, measured before connector routing. */
export function layoutValueBoxes(root: HTMLElement): void {
  const cells = Array.from(root.querySelectorAll<HTMLElement>(valueCellSelector));
  const widths = new Map<Element, number>();
  for (const cell of cells) {
    const box = cell.querySelector<HTMLElement>(':scope > .value-box, :scope > .compact-string > .value-box');
    if (!box) continue;
    box.style.width = 'max-content';
    const range = document.createRange();
    range.selectNodeContents(box);
    const width = Math.max(40, Math.ceil(range.getBoundingClientRect?.().width || 0) + 22);
    const table = cell.closest('table')!;
    widths.set(table, Math.max(widths.get(table) ?? 40, width));
  }
  for (const cell of cells) {
    const box = cell.querySelector<HTMLElement>(':scope > .value-box, :scope > .compact-string > .value-box');
    if (box) box.style.width = `${widths.get(cell.closest('table')!) ?? 40}px`;
    const arrow = cell.querySelector<SVGSVGElement>('.compact-string-arrow');
    if (box && arrow) {
      const width = widths.get(cell.closest('table')!) ?? 40;
      const tip = width + 15;
      arrow.setAttribute('width', String(tip + 1));
      arrow.querySelector('path')!.setAttribute('d', `M ${width - SOURCE_INSET} 9.5 H ${tip - ARROW_LENGTH}`);
      arrow.querySelector('circle')!.setAttribute('cx', String(width - SOURCE_INSET));
      arrow.querySelector('polygon')!.setAttribute('points', arrowTriangle(tip, 9.5));
    }
  }
}

/** Render compact strings with DOM text nodes so literals cannot inject markup. */
export function renderCompactString(cell: HTMLElement, id: string, literal: string, textOnly: boolean): void {
  cell.dataset.referenceTarget = id;
  cell.classList.add("value-cell");
  const pair = document.createElement('span');
  pair.className = 'compact-string';
  const box = document.createElement('span');
  box.className = 'value-box';
  box.textContent = id;
  const text = document.createElement('span');
  text.className = 'stringObj';
  text.textContent = JSON.stringify(literal);
  pair.append(box, text);
  if (!textOnly) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('compact-string-arrow');
    svg.setAttribute('height', '19');
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = '<path fill="none" stroke-width="1"/><circle cy="9.5" r="3"/><polygon/>';
    svg.querySelector("path")!.setAttribute("stroke", paint("arrow"));
    svg.querySelector("circle")!.setAttribute("fill", paint("arrow"));
    svg.querySelector("circle")!.setAttribute("r", String(SOURCE_RADIUS));
    svg.querySelector("polygon")!.setAttribute("fill", paint("arrow"));
    pair.append(svg);
  }
  cell.append(pair);
}
