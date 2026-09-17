// Return structural paths only. Never read text, values, URLs, or attributes.
() => {
  const allowed = new Set('html body div span form section main header footer nav article aside ul ol li table thead tbody tfoot tr td th label fieldset legend p a button input textarea select option h1 h2 h3 h4 h5 h6'.split(' '));
  const candidates = [];
  let truncated = false;
  for (const element of document.querySelectorAll('input,textarea,select,button,a')) {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (!rect.width || !rect.height || style.visibility !== 'visible' || style.display === 'none') continue;
    const parts = [];
    let valid = true;
    for (let node = element; node; node = node.parentElement) {
      const tag = node.tagName.toLowerCase();
      if (!allowed.has(tag) || parts.length >= 40) { valid = false; break; }
      let index = 1;
      for (let sibling = node.previousElementSibling; sibling; sibling = sibling.previousElementSibling) {
        if (sibling.tagName === node.tagName) index++;
      }
      parts.unshift(`${tag}:nth-of-type(${index})`);
    }
    if (!valid) continue;
    if (candidates.length >= 100) { truncated = true; break; }
    const selector = parts.join(' > ');
    if (selector.length > 2000) continue;
    candidates.push({id: `c${candidates.length + 1}`, selector, kind: element.tagName.toLowerCase()});
  }
  return {schema_version: 1, candidates, truncated};
}
