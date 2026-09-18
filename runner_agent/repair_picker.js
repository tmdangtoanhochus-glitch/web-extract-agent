// Capture only structural CSS: no input values, text or attributes.
(() => {
  if (window.__runnerRepairInstalled) return;
  window.__runnerRepairInstalled = true;
  let hovered = null;
  document.addEventListener('pointerover', event => {
    if (event.isTrusted) hovered = event.target;
  }, true);
  document.addEventListener('keydown', event => {
    if (!event.isTrusted || !event.ctrlKey || !event.altKey || event.code !== 'KeyL') return;
    if (window !== window.top || !(hovered instanceof Element) ||
        hovered.getRootNode() !== document || !hovered.isConnected) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    let element = hovered;
    const parts = [];
    while (element && element.nodeType === 1) {
      const tag = element.tagName.toLowerCase();
      if (!/^[a-z][a-z0-9-]*$/.test(tag)) return;
      let index = 1;
      let sibling = element.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === element.tagName) index++;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(`${tag}:nth-of-type(${index})`);
      if (parts.length > 40) return;
      element = element.parentElement;
    }
    window.__runnerRepairTarget = hovered;
    window.runnerRepairPick({locator: parts.join(' > ')}).catch(() => {});
  }, true);
})();
