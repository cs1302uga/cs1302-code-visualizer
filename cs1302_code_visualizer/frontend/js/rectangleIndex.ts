/** Immutable broad-phase index. Exact geometry remains the caller's decision. */
import type { Rect } from "./referenceRouting";

interface Entry<T> { value: T; rect: Rect }
interface Node<T> { rect: Rect; entries?: Entry<T>[]; left?: Node<T>; right?: Node<T> }

// Inclusive bounds deliberately retain boundary contacts and zero-area queries.
const touches=(a:Rect,b:Rect)=>a.left<=b.right&&a.right>=b.left&&a.top<=b.bottom&&a.bottom>=b.top;

export class RectangleIndex<T> {
  private root?: Node<T>;

  constructor(values: readonly T[], rect: (value:T)=>Rect) {
    const build=(entries:Entry<T>[]):Node<T>|undefined=>{
      if(!entries.length)return undefined;
      const box={left:Infinity,top:Infinity,right:-Infinity,bottom:-Infinity};
      for(const {rect:r} of entries) {
        box.left=Math.min(box.left,r.left);box.top=Math.min(box.top,r.top);
        box.right=Math.max(box.right,r.right);box.bottom=Math.max(box.bottom,r.bottom);
      }
      if(entries.length<=8)return {rect:box,entries};
      const horizontal=box.right-box.left>=box.bottom-box.top;
      entries.sort((a,b)=>horizontal ? (a.rect.left+a.rect.right)-(b.rect.left+b.rect.right) :
        (a.rect.top+a.rect.bottom)-(b.rect.top+b.rect.bottom));
      const mid=entries.length>>1;
      return {rect:box,left:build(entries.slice(0,mid)),right:build(entries.slice(mid))};
    };
    this.root=build(values.map(value=>({value,rect:rect(value)})));
  }

  some(query: Rect, test: (value:T)=>boolean): boolean {
    const visit=(node:Node<T>|undefined):boolean=>{
      if(!node||!touches(node.rect,query))return false;
      if(node.entries)return node.entries.some(e=>touches(e.rect,query)&&test(e.value));
      return visit(node.left)||visit(node.right);
    };
    return visit(this.root);
  }
}
