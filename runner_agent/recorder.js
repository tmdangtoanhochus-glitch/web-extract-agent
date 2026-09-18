// Structural positions and action types only; never read values, filenames or text.
(() => {
  if (window.__runnerRecorderInstalled) return;
  window.__runnerRecorderInstalled = true;
  let hovered = null, toast = null, toastTimer = null;
  let antInput = null;
  const seen = new WeakSet(), roots = new WeakSet();
  const send = payload => window.runnerRecordEvent(payload).then(state => {
    if (!state || !document.body) return;
    if (!toast) {
      toast = document.createElement('div');
      toast.style.cssText = 'position:fixed;top:8px;right:8px;z-index:2147483647;padding:8px;background:#172554;color:white;pointer-events:none;font:14px sans-serif';
      document.body.appendChild(toast);
    }
    toast.textContent = `Recorder: screen ${state.screen} | ${state.paused ? 'PAUSED' : 'recording'} | ${state.accepted ? 'accepted' : 'not recorded'}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast?.remove(); toast = null; }, 2500);
  }).catch(() => {});
  const target = event => event.composedPath()[0];
  const first = event => {
    if (!event.isTrusted || seen.has(event)) return false;
    seen.add(event); return true;
  };
  const encoded = element => {
    const parts = window.__runnerStructuralPath(element);
    return !parts?.length ? null : parts.length === 1 ? parts[0].css : 'runner-scope:' + JSON.stringify(parts);
  };
  const emit = (element, action, extra = {}) => {
    if (!(element instanceof Element) || element === toast) return;
    // Coalesce typing at the shared receiver: another frame may have acted meanwhile.
    const locator = encoded(element);
    if (locator) send({action, locator, ...extra});
  };
  const attach = root => {
    if (roots.has(root)) return;
    roots.add(root);
    root.addEventListener('mouseover', event => {
      if (first(event) && target(event) instanceof Element) hovered = target(event);
    }, true);
    root.addEventListener('keydown', event => {
      if (!first(event) || event.repeat || !event.ctrlKey || !event.altKey) return;
      if (!['KeyN', 'KeyP', 'KeyW', 'KeyA'].includes(event.code)) return;
      event.preventDefault(); event.stopImmediatePropagation();
      if (event.code === 'KeyN' || event.code === 'KeyP') {
        send({control: event.code === 'KeyN' ? 'next_screen' : 'toggle_pause'}); return;
      }
      if (!hovered?.isConnected || hovered === toast) return;
      if (event.code === 'KeyA' && (!['INPUT', 'TEXTAREA', 'SELECT'].includes(hovered.tagName) ||
          (hovered instanceof HTMLInputElement && ['password', 'file', 'checkbox', 'radio', 'hidden'].includes(hovered.type)))) return;
      emit(hovered, event.code === 'KeyW' ? 'wait' : 'read_result_single');
    }, true);
    root.addEventListener('click', event => {
      if (!first(event)) return;
      const element = target(event);
      if (!(element instanceof Element)) return;
      // Fixed component capabilities only: no class string, option text or input value is exported.
      const option = element.closest('.ant-select-item-option');
      if (option && antInput?.isConnected && !antInput.readOnly && !antInput.disabled) {
        const visible = [...document.querySelectorAll('.ant-select-dropdown')].filter(e => e.getClientRects().length);
        const related = encoded(antInput);
        if (visible.length === 1 && visible[0].contains(option) && related) {
          emit(option, 'click', {widget: 'antd_option', related_locator: related});
          antInput = null; return;
        }
      }
      const select = element.closest('.ant-select');
      const candidates = select ? select.querySelectorAll('input') : [];
      if (candidates.length === 1 && !candidates[0].readOnly && !candidates[0].disabled &&
          !['password', 'file', 'hidden'].includes(candidates[0].type)) {
        antInput = candidates[0];
        emit(antInput, 'click', {widget: 'antd_select'}); return;
      }
      antInput = null;
      // Input buttons have no change event: preserve the user's click as an action.
      // Do not read their value (the visible label) or image source.
      if (element instanceof HTMLInputElement && ['button', 'submit', 'reset', 'image'].includes(element.type)) {
        emit(element, 'click'); return;
      }
      if (!(element instanceof Element) || ['INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'LABEL'].includes(element.tagName)) return;
      if (element.closest('label')?.control instanceof HTMLInputElement) return;
      if (element.tagName.includes('-') && !element.shadowRoot) return;
      emit(element, 'click');
    }, true);
    root.addEventListener('input', event => {
      if (!first(event)) return;
      const element = target(event);
      if (element instanceof HTMLInputElement && ['file', 'checkbox', 'radio', 'hidden'].includes(element.type)) return;
      if (['INPUT', 'TEXTAREA'].includes(element.tagName)) emit(element, 'fill');
    }, true);
    root.addEventListener('change', event => {
      if (!first(event)) return;
      const element = target(event);
      if (element instanceof HTMLInputElement) {
        if (element.type === 'file') emit(element, 'upload');
        if (element.type === 'checkbox') emit(element, element.checked ? 'check' : 'uncheck');
        if (element.type === 'radio' && element.checked) emit(element, 'check');
      } else if (element.tagName === 'SELECT') emit(element, 'select');
    }, true);
    const scan = node => {
      if (node instanceof Element && node.shadowRoot) attach(node.shadowRoot);
      for (const element of node.querySelectorAll?.('*') || []) {
        if (element.shadowRoot) attach(element.shadowRoot);
      }
    };
    new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) scan(node);
    }).observe(root, {childList: true, subtree: true});
    scan(root);
  };
  const original = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function(options) {
    const root = original.call(this, options);
    if (options.mode === 'open') attach(root);
    return root;
  };
  attach(document);
})();
