/** Immutable broad-phase index. Exact geometry remains the caller's decision. */
import type { Rect } from "./referenceRouting";

interface Entry<T> { value: T; rect: Rect }
interface Node<T> { rect: Rect; entries?: Entry<T>[]; left?: Node<T>; right?: Node<T> }

// Inclusive bounds deliberately retain boundary contacts and zero-area queries.
const touches=(a:Rect,b:Rect)=>a.left<=b.right&&a.right>=b.left&&a.top<=b.bottom&&a.bottom>=b.top;

function someNode<T>(node:Node<T>|undefined,query:Rect,test:(value:T)=>boolean):boolean {
  if(!node||!touches(node.rect,query))return false;
  if(node.entries) {
    for(const entry of node.entries)if(touches(entry.rect,query)&&test(entry.value))return true;
    return false;
  }
  return someNode(node.left,query,test)||someNode(node.right,query,test);
}

function interiorNode<T>(node:Node<T>|undefined,query:Rect):boolean {
  if(!node||query.right<=node.rect.left||query.left>=node.rect.right||
    query.bottom<=node.rect.top||query.top>=node.rect.bottom)return false;
  if(node.entries) {
    for(const {rect:r} of node.entries)if(query.right>r.left&&query.left<r.right&&
      query.bottom>r.top&&query.top<r.bottom)return true;
    return false;
  }
  return interiorNode(node.left,query)||interiorNode(node.right,query);
}

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
    return someNode(this.root,query,test);
  }

  /** Exact interior overlap for rectangles and axis-aligned segment hulls.
   * A zero-width/height query inside a rectangle still intersects its interior;
   * boundary-only contact does not. Diagonal/curved paths need `some` instead.
   */
  intersectsInterior(query:Rect):boolean {
    return interiorNode(this.root,query);
  }
}
