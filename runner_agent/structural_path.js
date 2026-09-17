element => {
  const scopes = [];
  while (element && element.nodeType === 1) {
    const root = element.getRootNode();
    const parts = [];
    let current = element;
    while (current && current.nodeType === 1) {
      const tag = current.tagName.toLowerCase();
      if (!/^[a-z][a-z0-9-]*$/.test(tag)) return null;
      let index = 1;
      for (let sibling = current.previousElementSibling; sibling; sibling = sibling.previousElementSibling) {
        if (sibling.tagName === current.tagName) index++;
      }
      parts.unshift(`${tag}:nth-of-type(${index})`);
      if (parts.length > 40) return null;
      current = current.parentElement;
    }
    scopes.unshift({kind: scopes.length ? 'shadow' : 'target', css: parts.join(' > ')});
    if (scopes.length > 16) return null;
    if (root instanceof ShadowRoot) {
      if (root.mode !== 'open') return null;
      element = root.host;
    } else break;
  }
  return scopes;
}
