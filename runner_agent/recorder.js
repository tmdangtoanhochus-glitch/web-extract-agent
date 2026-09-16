// Structural locators only: do not read input values, text or attributes.
(() => {
  if (window.__runnerRecorderInstalled) return;
  window.__runnerRecorderInstalled = true;
  let previousInput = null;
  const locator = element => {
    const parts = [];
    while (element && element.nodeType === 1) {
      const tag = element.tagName.toLowerCase();
      if (!/^[a-z][a-z0-9-]*$/.test(tag)) return null;
      let index = 1;
      let sibling = element.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === element.tagName) index++;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(`${tag}:nth-of-type(${index})`);
      element = element.parentElement;
      if (parts.length > 40) return null;
    }
    return parts.join(' > ');
  };
  const emit = (event, action) => {
    if (!event.isTrusted || window !== window.top) return;
    const element = event.target;
    if (!(element instanceof Element) || element.getRootNode() !== document) return;
    // File inputs and stateful check/radio controls require manual authoring.
    if (element instanceof HTMLInputElement &&
        ['file', 'checkbox', 'radio', 'hidden'].includes(element.type)) return;
    if (action === 'click' && ['INPUT', 'TEXTAREA', 'SELECT', 'OPTION'].includes(element.tagName)) return;
    if (action === 'fill') {
      if (previousInput === element) return;
      previousInput = element;
    } else previousInput = null;
    const css = locator(element);
    if (css) window.runnerRecordEvent({action, locator: css}).catch(() => {});
  };
  document.addEventListener('click', event => emit(event, 'click'), true);
  document.addEventListener('input', event => {
    if (['INPUT', 'TEXTAREA'].includes(event.target.tagName)) emit(event, 'fill');
  }, true);
  document.addEventListener('change', event => {
    if (event.target.tagName === 'SELECT') emit(event, 'select');
  }, true);
})();
