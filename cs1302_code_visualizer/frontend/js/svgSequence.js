/** Experimental player for trusted, exporter-generated manifests (not arbitrary SVG). */
export function createSequencePlayer(container, manifest) {
  if (manifest.version !== 1 || !manifest.frames.length) throw new Error('Unsupported sequence');
  const doc = container.ownerDocument;
  const identities = new WeakMap();
  function name(expanded) {
    const match = /^\{([^}]+)\}(.+)$/.exec(expanded);
    return match ? [match[1], match[2]] : [null, expanded];
  }
  function reconcile(old, id) {
    if (typeof id === 'string') {
      if (old?.nodeType === 3) {
        if (old.data !== id) old.data = id;
        return old;
      }
      return doc.createTextNode(id);
    }
    if (old && identities.get(old) === id) return old;
    const [tag, attributes, children] = manifest.nodes[id];
    const [namespace, local] = name(tag);
    const element = old?.nodeType === 1 && old.namespaceURI === namespace && old.localName === local
      ? old : doc.createElementNS(namespace, local);
    const desired = new Map(attributes);
    for (const attr of Array.from(element.attributes)) {
      const expanded = attr.namespaceURI ? `{${attr.namespaceURI}}${attr.localName}` : attr.name;
      if (!desired.has(expanded)) element.removeAttributeNS(attr.namespaceURI, attr.localName);
    }
    for (const [key, value] of attributes) {
      const [ns, localName] = name(key);
      if (element.getAttributeNS(ns, localName) !== value) element.setAttributeNS(ns, localName, value);
    }
    children.forEach((child, index) => {
      const previous = element.childNodes[index];
      const updated = reconcile(previous, child);
      if (updated !== previous) {
        if (previous) element.replaceChild(updated, previous);
        else element.append(updated);
      }
    });
    while (element.childNodes.length > children.length) element.lastChild.remove();
    identities.set(element, id);
    return element;
  }
  return {
    seek(index) {
      if (!Number.isInteger(index) || index < 0 || index >= manifest.frames.length) {
        throw new RangeError('Step is outside the sequence');
      }
      const current = container.firstChild;
      const next = reconcile(current, manifest.frames[index]);
      if (next !== current) container.replaceChildren(next);
    },
    serialize() {
      if (!container.firstChild) throw new Error('Select a step before exporting');
      return new XMLSerializer().serializeToString(container.firstChild);
    },
  };
}
