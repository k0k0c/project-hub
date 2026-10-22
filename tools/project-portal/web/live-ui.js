"use strict";
// Update data in the mounted page. Stable controls keep their DOM identity,
// native file selections, listeners, scroll positions and text selection.
window.HubLiveUI = (() => {
  const keys = ['id','data-ui-key','data-scroll-key','data-key','data-agent-answer',
    'data-project-id','data-project-form','data-task-id','data-stage-id','data-review-select',
    'data-k-id','data-k-field','data-k-filter','data-k-policy','data-k-paths',
    'data-setting','data-setting-column','name'];
  let generation = 0;
  for (const event of ['wheel','touchmove','pointerdown','keydown'])
    document.addEventListener(event, () => generation++, {capture:true,passive:true});
  function key(node) {
    if (node.nodeType !== 1) return null;
    for (const attr of keys) if (node.hasAttribute(attr)) {
      const value = node.getAttribute(attr);
      if (value || ['checkbox','radio'].includes(node.type)) return `${node.nodeName}:${attr}:${value}${['checkbox','radio'].includes(node.type) ? ':'+node.value : ''}`;
    }
    return null;
  }
  function address(root, node) {
    if (!node || !root.contains(node)) return null;
    const parts = [];
    for (; node !== root; node = node.parentNode) {
      const siblings = [...node.parentNode.childNodes], id = key(node);
      parts.unshift({key:id,index:siblings.indexOf(node),type:node.nodeType,tag:node.nodeName});
    }
    return parts;
  }
  function resolve(root, parts) {
    if (!parts) return null;
    let node = root;
    for (const part of parts) {
      const children = [...node.childNodes];
      node = part.key ? children.find(child => key(child) === part.key) : children[part.index];
      if (!node || node.nodeType !== part.type || node.nodeName !== part.tag) return null;
    }
    return node;
  }
  function capture(root) {
    const active = document.activeElement;
    const focus = root.contains(active) ? {node:active,path:address(root,active),
      start:active.selectionStart,end:active.selectionEnd,direction:active.selectionDirection} : null;
    const scroll = [root,...root.querySelectorAll('*')].filter(n => n.scrollTop || n.scrollLeft)
      .map(node => ({node,path:address(root,node),top:node.scrollTop,left:node.scrollLeft}));
    const selected = window.getSelection?.();
    const selection = selected?.rangeCount && !selected.isCollapsed && root.contains(selected.anchorNode) && root.contains(selected.focusNode)
      ? {anchor:selected.anchorNode,anchorPath:address(root,selected.anchorNode),anchorOffset:selected.anchorOffset,
          focus:selected.focusNode,focusPath:address(root,selected.focusNode),focusOffset:selected.focusOffset} : null;
    return {focus,scroll,selection,top:window.scrollY,left:window.scrollX,generation};
  }
  function restore(root, saved) {
    if (!saved || saved.generation !== generation) return;
    const attached = (node,path) => root.contains(node) ? node : resolve(root,path);
    if (saved.focus) {
      const f = saved.focus, node = attached(f.node,f.path);
      // Do not reclaim focus after an intentional move by another control.
      if (node && (document.activeElement === f.node || !f.node.isConnected || document.activeElement === document.body)) {
        if (document.activeElement !== node) node.focus?.({preventScroll:true});
        if (typeof f.start === 'number' && node.setSelectionRange)
          try { node.setSelectionRange(f.start,f.end,f.direction); } catch { /* Non-text controls. */ }
      }
    }
    if (saved.selection) {
      const s = saved.selection, a = attached(s.anchor,s.anchorPath), b = attached(s.focus,s.focusPath);
      if (a && b) try { window.getSelection()?.setBaseAndExtent(a,s.anchorOffset,b,s.focusOffset); } catch { /* Changed text. */ }
    }
    for (const s of saved.scroll) {
      const node = attached(s.node,s.path);
      if (node) { node.scrollTop = s.top; node.scrollLeft = s.left; }
    }
    window.scrollTo?.({top:saved.top,left:saved.left,behavior:'instant'});
  }
  function compatible(a,b) { return a.nodeType === b.nodeType && a.nodeName === b.nodeName && key(a) === key(b) && (a.nodeName !== 'INPUT' || a.type === b.type); }
  function update(node, next, preserveInputs) {
    if (node.nodeType !== 1) {
      if (node.nodeValue !== next.nodeValue) node.nodeValue = next.nodeValue;
      return;
    }
    const control = node.matches('input,textarea,select'), file = node.matches('input[type="file"]');
    const value = control ? node.value : null, checked = node.checked;
    const open = node.matches('details') ? node.open : null;
    for (const attr of [...node.attributes]) if (!next.hasAttribute(attr.name)) node.removeAttribute(attr.name);
    for (const attr of [...next.attributes]) if (node.getAttribute(attr.name) !== attr.value) node.setAttribute(attr.name,attr.value);
    // A user's contenteditable island owns its children until explicitly saved.
    if (!(preserveInputs && node.isContentEditable)) children(node,next,preserveInputs);
    if (open !== null) node.open = open;
    if (control && !file) {
      node.value = preserveInputs ? value : next.value;
      if (node.matches('input[type="checkbox"],input[type="radio"]')) node.checked = preserveInputs && !next.disabled ? checked : next.checked;
    }
  }
  function children(root,next,preserveInputs) {
    const remaining = [...root.childNodes];
    let cursor = root.firstChild;
    for (const child of [...next.childNodes]) {
      const id = key(child);
      const old = id ? remaining.find(n => compatible(n,child)) :
        (remaining.includes(cursor) && compatible(cursor,child) ? cursor : remaining.find(n => compatible(n,child)));
      if (old) {
        remaining.splice(remaining.indexOf(old),1);
        if (old !== cursor) root.insertBefore(old,cursor);
        update(old,child,preserveInputs);
        cursor = old.nextSibling;
      } else {
        const added = child.cloneNode(true);
        root.insertBefore(added,cursor);
      }
    }
    for (const node of remaining) node.remove();
  }
  function patch(root, html, {preserveInputs=true,preserveState=true}={}) {
    if (!root) return;
    const saved = preserveState ? capture(root) : null;
    const template = document.createElement('template');
    template.innerHTML = html;
    children(root,template.content,preserveInputs);
    restore(root,saved);
    if (saved) requestAnimationFrame(() => { restore(root,saved); requestAnimationFrame(() => restore(root,saved)); });
  }
  return {capture,restore,patch};
})();
