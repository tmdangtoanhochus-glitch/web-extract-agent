// Structural locators only: do not read input values, text or attributes.
(() => {
  if (window.__runnerRecorderInstalled) return;
  window.__runnerRecorderInstalled = true;
  let previousInput = null;
  let hovered = null;
  let toast = null;
  let toastTimer = null;
  const send = payload => window.runnerRecordEvent(payload).then(state => {
    if (!state || !document.body) return;
    // Fixed local status only. Never copy page text into this overlay.
    if (!toast) {
      toast = document.createElement('div');
      toast.style.cssText = 'position:fixed;top:8px;right:8px;z-index:2147483647;padding:8px;background:#172554;color:white;pointer-events:none;font:14px sans-serif';
      document.body.appendChild(toast);
    }
    toast.textContent = `Recorder: screen ${state.screen} | ${state.paused ? 'PAUSED' : 'recording'} | ${state.accepted ? 'accepted' : 'not recorded'}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast?.remove(); toast = null; }, 2500);
  }).catch(() => {});
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
  document.addEventListener('mouseover', event => {
    if (event.isTrusted && event.target instanceof Element && event.target.getRootNode() === document) hovered = event.target;
  }, true);
  document.addEventListener('keydown', event => {
    if (!event.isTrusted || event.repeat || window !== window.top || !event.ctrlKey || !event.altKey) return;
    if (!['KeyN', 'KeyP', 'KeyW', 'KeyA'].includes(event.code)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    previousInput = null;
    if (event.code === 'KeyN' || event.code === 'KeyP') {
      send({control: event.code === 'KeyN' ? 'next_screen' : 'toggle_pause'});
      return;
    }
    if (!hovered || !hovered.isConnected || hovered === toast || hovered.getRootNode() !== document) return;
    if (event.code === 'KeyA' && (!['INPUT', 'TEXTAREA', 'SELECT'].includes(hovered.tagName) ||
        (hovered instanceof HTMLInputElement && ['password', 'file', 'checkbox', 'radio', 'hidden'].includes(hovered.type)))) return;
    const css = locator(hovered);
    if (css) send({action: event.code === 'KeyW' ? 'wait' : 'read_result_single', locator: css});
  }, true);
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
    if (css) send({action, locator: css});
  };
  document.addEventListener('click', event => emit(event, 'click'), true);
  document.addEventListener('input', event => {
    if (['INPUT', 'TEXTAREA'].includes(event.target.tagName)) emit(event, 'fill');
  }, true);
  document.addEventListener('change', event => {
    if (event.target.tagName === 'SELECT') emit(event, 'select');
  }, true);
})();
