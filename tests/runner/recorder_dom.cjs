// Synthetic DOM harness: no browser profile, network, page content or credentials.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
class Root {
  constructor() { this.listeners = {}; this.children = []; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  querySelectorAll() { return this.children.flatMap(e => [e, ...e.querySelectorAll()]); }
}
class Element extends Root {
  constructor(tag, root) {
    super(); this.tagName = tag.toUpperCase(); this.root = root;
    this.nodeType = 1; this.isConnected = true; this.parentElement = null;
    this.previousElementSibling = null;
  }
  getRootNode() { return this.root; }
  closest() { return null; }
  attachShadow(options) { const root = new ShadowRoot(this, options.mode); if (options.mode === 'open') this.shadowRoot = root; return root; }
}
class ShadowRoot extends Root { constructor(host, mode) { super(); this.host = host; this.mode = mode; } }
class HTMLInputElement extends Element {
  constructor(type, root) { super('input', root); this.type = type; this.checked = false; }
  get value() { throw Error('Value must never be read'); }
  get files() { throw Error('Files must never be read'); }
}
const document = new Root();
document.body = null;
const sent = [];
const window = {runnerRecordEvent: payload => { sent.push(payload); return Promise.resolve(null); }};
const sandbox = {document, window, Element, HTMLInputElement, ShadowRoot,
  MutationObserver: class { observe() {} }, clearTimeout, setTimeout};
const context = vm.createContext(sandbox);
const base = path.join(__dirname, '../../runner_agent');
vm.runInContext('window.__runnerStructuralPath = (' + fs.readFileSync(path.join(base, 'structural_path.js'), 'utf8') + ')', context);
vm.runInContext(fs.readFileSync(path.join(base, 'recorder.js'), 'utf8'), context);
const emit = (root, type, element, trusted = true) => {
  const event = {isTrusted: trusted, composedPath: () => [element]};
  root.listeners[type](event); return event;
};
const host = new Element('app-root', document);
const shadow = host.attachShadow({mode: 'open'});
const input = new HTMLInputElement('file', shadow);
emit(shadow, 'change', input);
assert.equal(sent.length, 1);
assert.equal(sent[0].action, 'upload');
assert.deepEqual(JSON.parse(sent[0].locator.slice('runner-scope:'.length)), [
  {kind: 'shadow', css: 'app-root:nth-of-type(1)'}, {kind: 'target', css: 'input:nth-of-type(1)'}]);
assert.deepEqual(Object.keys(sent[0]).sort(), ['action', 'locator']);
input.type = 'checkbox'; input.checked = true;
const event = emit(document, 'change', input);
shadow.listeners.change(event); // Composed event delivered to both roots must not duplicate.
assert.equal(sent.length, 2); assert.equal(sent[1].action, 'check');
input.checked = false; emit(shadow, 'change', input);
assert.equal(sent[2].action, 'uncheck');
input.type = 'radio'; input.checked = true; emit(shadow, 'change', input);
assert.equal(sent[3].action, 'check');
emit(shadow, 'change', input, false); assert.equal(sent.length, 4);
const closed = host.attachShadow({mode: 'closed'});
assert.equal(closed.listeners.change, undefined);
assert.equal(window.__runnerStructuralPath(new HTMLInputElement('text', closed)), null);
// Ant Design evidence: identify a fillable trigger and a single visible popup, never read labels.
const ant = new HTMLInputElement('text', document);
const selector = {querySelectorAll: () => [ant]};
ant.closest = name => name === '.ant-select' ? selector : null;
const option = new Element('div', document);
option.closest = name => name === '.ant-select-item-option' ? option : null;
const popup = {getClientRects: () => [1], contains: item => item === option};
document.querySelectorAll = name => name === '.ant-select-dropdown' ? [popup] : [];
emit(document, 'click', ant);
emit(document, 'click', option);
assert.equal(sent[4].widget, 'antd_select');
assert.equal(sent[5].widget, 'antd_option');
assert.equal(sent[5].related_locator, sent[4].locator);
assert.equal(sent[5].action, 'click');
// Input buttons do not fire change; recording must preserve their trusted clicks.
for (const root of [document, shadow]) {
  for (const type of ['button', 'submit', 'reset', 'image']) {
    const button = new HTMLInputElement(type, root);
    const before = sent.length;
    const click = emit(document, 'click', button);
    if (root === shadow) shadow.listeners.click(click);
    assert.equal(sent.length, before + 1);
    assert.equal(sent[before].action, 'click');
    assert.deepEqual(Object.keys(sent[before]).sort(), ['action', 'locator']);
    assert.equal(sent[before].locator.startsWith('runner-scope:'), root === shadow);
    emit(root, 'click', button, false);
    assert.equal(sent.length, before + 1);
  }
}
// Native data controls still record only input/change, never a duplicate click.
for (const type of ['text', 'password', 'file', 'checkbox', 'radio', 'hidden']) {
  const before = sent.length;
  emit(document, 'click', new HTMLInputElement(type, document));
  assert.equal(sent.length, before);
}
// Every input reaches the shared receiver, including returning from another frame.
const repeated = new HTMLInputElement('text', document);
const beforeTyping = sent.length;
emit(document, 'input', repeated);
emit(document, 'input', repeated);
assert.equal(sent.length, beforeTyping + 2);
assert.deepEqual(sent[beforeTyping], sent[beforeTyping + 1]);
console.log('recorder synthetic DOM checks passed');
