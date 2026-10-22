/* Architecture workspace controls. Loaded after knowledge.js and safe to use on redraws. */
(() => {
  'use strict';
  const MIN_CATALOG = 145, MIN_INSPECTOR = 190, MIN_GRAPH = 260;
  const instances = new WeakMap();

  function number(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  function clampWidth(kind, value, total, other) {
    total = Math.max(0, number(total, 0));
    other = Math.max(0, number(other, 0));
    const minimum = kind === 'catalog' ? MIN_CATALOG : MIN_INSPECTOR;
    const reserve = kind === 'catalog' ? MIN_GRAPH + other : MIN_GRAPH;
    const maximum = Math.max(minimum, total - reserve);
    return Math.round(Math.min(maximum, Math.max(minimum, number(value, minimum))));
  }
  function storageKey(v) { return 'knowledge:' + String(v?.project || '') + ':architecture'; }
  function save(v, catalogWidth, inspectorWidth) {
    const filters = v.filters || (v.filters = {});
    filters.catalogWidth = catalogWidth;
    filters.inspectorWidth = inspectorWidth;
    try {
      const key = storageKey(v), prior = JSON.parse(localStorage.getItem(key) || '{}');
      const storedFilters = prior.filters && typeof prior.filters === 'object' ? prior.filters : {};
      localStorage.setItem(key, JSON.stringify({ ...prior, filters: { ...storedFilters, ...filters } }));
    } catch (_) { /* localStorage is optional */ }
  }
  function readWidths(v) {
    let filters = v.filters || (v.filters = {});
    try {
      const prior = JSON.parse(localStorage.getItem(storageKey(v)) || '{}');
      if (prior.filters && typeof prior.filters === 'object' && (!v.research || prior.researchVersion===1)) filters = { ...prior.filters, ...filters };
    } catch (_) { /* localStorage is optional */ }
    v.filters = filters;
    return { catalog: number(filters.catalogWidth, v.research?258:260), inspector: number(filters.inspectorWidth, v.research?292:250) };
  }
  function cyFor(root, v) {
    return v?.cy || v?.graph || root.__knowledgeCy || root._knowledgeCy || null;
  }
  function resize(root, v) {
    const cy = cyFor(root, v);
    if (!cy || typeof cy.resize !== 'function') return;
    try { if (!cy.destroyed?.()) cy.resize(); } catch (_) { /* graph can disappear during redraw */ }
  }
  function separator(label, kind) {
    const element = document.createElement('button');
    element.type = 'button'; element.className = 'k-workspace-splitter';
    element.dataset.kSplitter = kind; element.setAttribute('role', 'separator');
    element.setAttribute('aria-orientation', 'vertical'); element.setAttribute('aria-label', label);
    element.tabIndex = 0; return element;
  }
  function focusable(dialog) {
    return [...dialog.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')]
      .filter(node => !node.disabled && node.getAttribute('aria-hidden') !== 'true');
  }
  function mountDialogOnly(root) {
    let lastFocus = null;
    const onClick = event => {
      const backdrop = event.target.closest?.('[data-k-dialog-backdrop]');
      if (backdrop && event.target === backdrop) { backdrop.querySelector('[data-k-action="close-panel"],[data-r-action="close-dialog"]')?.click(); return; }
      const dialog = event.target.closest?.('[data-k-dialog-backdrop] [role="dialog"]');
      if (dialog) { lastFocus = document.activeElement; queueMicrotask(() => focusable(dialog)[0]?.focus() || dialog.focus()); }
    };
    const onKey = event => {
      const dialog = root.querySelector('[data-k-dialog-backdrop] [role="dialog"]');
      if (!dialog) return;
      if (event.key === 'Escape') { event.preventDefault(); dialog.querySelector('[data-k-action="close-panel"],[data-r-action="close-dialog"]')?.click(); lastFocus?.focus?.(); return; }
      if (event.key !== 'Tab') return;
      const nodes = focusable(dialog); if (!nodes.length) { event.preventDefault(); dialog.focus(); return; }
      const index = nodes.indexOf(document.activeElement); if (event.shiftKey && index <= 0) { event.preventDefault(); nodes[nodes.length - 1].focus(); } else if (!event.shiftKey && index === nodes.length - 1) { event.preventDefault(); nodes[0].focus(); }
    };
    root.addEventListener('click', onClick); root.addEventListener('keydown', onKey);
    const initialDialog = root.querySelector('[data-k-dialog-backdrop] [role="dialog"]');
    if (initialDialog) { lastFocus = document.activeElement; queueMicrotask(() => focusable(initialDialog)[0]?.focus() || initialDialog.focus()); }
    return () => { root.removeEventListener('click', onClick); root.removeEventListener('keydown', onKey); };
  }
  function mount(root, v) {
    if (!root || !v || !root.querySelector) return () => {};
    dispose(root);
    const layout = root.querySelector('.k-layout'), main = root.querySelector('.k-architecture-main');
    const catalog = layout?.querySelector(':scope > .k-catalog'), inspector = main?.querySelector(':scope > .k-inspector-container');
    if (!layout || !main || !catalog) { const cleanup = mountDialogOnly(root); instances.set(root, cleanup); return cleanup; }
    const widths = readWidths(v), state = { root, v, layout, main, lastFocus: null, dragging: null, dialog: null };
    const inspectorOpen = inspector && !inspector.classList?.contains?.('is-collapsed');
    widths.catalog = clampWidth('catalog', widths.catalog, layout.getBoundingClientRect().width, inspectorOpen ? widths.inspector : 0);
    root.style.setProperty('--k-catalog-width', widths.catalog + 'px');
    widths.inspector = clampWidth('inspector', widths.inspector, main.getBoundingClientRect().width, widths.catalog);
    if (inspectorOpen) main.style.setProperty('--k-inspector-width', widths.inspector + 'px');
    const catalogGrip = separator((globalThis.HubI18n?.t?.("knowledge-workspace.4340f3a1422d") ?? 'Изменить ширину списка элементов'), 'catalog');
    layout.insertBefore(catalogGrip, catalog.nextSibling);
    let inspectorGrip = null;
    if (inspectorOpen) { inspectorGrip = separator((globalThis.HubI18n?.t?.("knowledge-workspace.ba286d542451") ?? 'Изменить ширину панели сведений'), 'inspector'); main.insertBefore(inspectorGrip, inspector); }
    const grips = [catalogGrip, inspectorGrip].filter(Boolean);
    const gripFor = kind => grips.find(grip => grip.dataset.kSplitter === kind);
    const setWidth = (kind, value, commit = true) => {
      const total = (kind === 'catalog' ? layout : main).getBoundingClientRect().width;
      const other = kind === 'catalog' ? (inspectorOpen ? number(state.v.filters.inspectorWidth, widths.inspector) : 0) : number(state.v.filters.catalogWidth, widths.catalog);
      const width = clampWidth(kind, value, total, other);
      state.v.filters[kind === 'catalog' ? 'catalogWidth' : 'inspectorWidth'] = width;
      const container = kind === 'catalog' ? layout : main;
      container.style.setProperty(kind === 'catalog' ? '--k-catalog-width' : '--k-inspector-width', width + 'px');
      const minimum = kind === 'catalog' ? MIN_CATALOG : MIN_INSPECTOR;
      gripFor(kind)?.setAttribute('aria-valuemax', String(Math.max(minimum, total - MIN_GRAPH - (kind === 'catalog' ? other : 0))));
      gripFor(kind)?.setAttribute('aria-valuenow', String(width));
      if (commit) save(state.v, number(state.v.filters.catalogWidth, widths.catalog), number(state.v.filters.inspectorWidth, widths.inspector));
      resize(root, state.v);
    };
    const onPointerMove = event => {
      if (!state.dragging) return;
      const { grip, kind, start, initial } = state.dragging;
      const delta = event.clientX - start;
      setWidth(kind, kind === 'catalog' ? initial + delta : initial - delta, false);
      event.preventDefault();
    };
    const stopDrag = () => { if (state.dragging) { save(state.v, number(state.v.filters.catalogWidth, widths.catalog), number(state.v.filters.inspectorWidth, widths.inspector)); state.dragging.grip.dataset.kDragging = 'false'; state.dragging = null; document.removeEventListener('pointermove', onPointerMove); document.removeEventListener('pointerup', stopDrag); document.removeEventListener('pointercancel', stopDrag); document.body.style.userSelect = ''; } };
    grips.forEach(grip => grip.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      const kind = grip.dataset.kSplitter;
      grip.setPointerCapture?.(event.pointerId); grip.dataset.kDragging = 'true';
      state.dragging = { grip, kind, start: event.clientX, initial: kind === 'catalog' ? catalog.getBoundingClientRect().width : inspector.getBoundingClientRect().width };
      document.addEventListener('pointermove', onPointerMove); document.addEventListener('pointerup', stopDrag); document.addEventListener('pointercancel', stopDrag);
      document.body.style.userSelect = 'none'; event.preventDefault();
    }));
    grips.forEach(grip => grip.addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight','Home'].includes(event.key)) return;
      const kind = grip.dataset.kSplitter, current = number(state.v.filters[kind === 'catalog' ? 'catalogWidth' : 'inspectorWidth'], kind === 'catalog' ? widths.catalog : widths.inspector), step = event.shiftKey ? 40 : 10;
      const value = event.key === 'Home' ? (kind === 'catalog' ? MIN_CATALOG : MIN_INSPECTOR) : current + (event.key === 'ArrowRight' ? step : -step);
      setWidth(kind, value); grip.setAttribute('aria-valuenow', String(number(state.v.filters[kind === 'catalog' ? 'catalogWidth' : 'inspectorWidth'], value))); event.preventDefault();
    }));
    grips.forEach(grip => { const kind = grip.dataset.kSplitter, container = kind === 'catalog' ? layout : main, other = kind === 'catalog' ? widths.inspector : widths.catalog; grip.setAttribute('aria-valuemin', String(kind === 'catalog' ? MIN_CATALOG : MIN_INSPECTOR)); grip.setAttribute('aria-valuemax', String(Math.max(kind === 'catalog' ? MIN_CATALOG : MIN_INSPECTOR, container.getBoundingClientRect().width - MIN_GRAPH - other))); grip.setAttribute('aria-valuenow', String(number(state.v.filters[kind === 'catalog' ? 'catalogWidth' : 'inspectorWidth'], kind === 'catalog' ? widths.catalog : widths.inspector))); });
    const onClick = event => {
      const backdrop = event.target.closest?.('[data-k-dialog-backdrop]');
      if (backdrop && event.target === backdrop) { backdrop.querySelector('[data-k-action="close-panel"],[data-r-action="close-dialog"]')?.click(); return; }
      const dialog = event.target.closest?.('[data-k-dialog-backdrop] [role="dialog"]');
      if (dialog && !state.dialog) { state.dialog = dialog; state.lastFocus = document.activeElement; queueMicrotask(() => focusable(dialog)[0]?.focus() || dialog.focus()); }
    };
    const onKey = event => {
      const dialog = root.querySelector('[data-k-dialog-backdrop] [role="dialog"]');
      if (!dialog) return;
      if (event.key === 'Escape') { event.preventDefault(); dialog.querySelector('[data-k-action="close-panel"],[data-r-action="close-dialog"]')?.click(); state.lastFocus?.focus?.(); state.dialog = null; return; }
      if (event.key !== 'Tab') return;
      const nodes = focusable(dialog); if (!nodes.length) { event.preventDefault(); dialog.focus(); return; }
      const index = nodes.indexOf(document.activeElement); if (event.shiftKey && index <= 0) { event.preventDefault(); nodes[nodes.length - 1].focus(); } else if (!event.shiftKey && index === nodes.length - 1) { event.preventDefault(); nodes[0].focus(); }
    };
    root.addEventListener('click', onClick); root.addEventListener('keydown', onKey);
    const observer = window.MutationObserver ? new MutationObserver(() => { const dialog = root.querySelector('[data-k-dialog-backdrop] [role="dialog"]'); if (dialog && state.dialog !== dialog) { state.dialog = dialog; state.lastFocus ||= document.activeElement; dialog.focus(); } }) : null;
    observer?.observe(root, { childList: true, subtree: true });
    const initialDialog = root.querySelector('[data-k-dialog-backdrop] [role="dialog"]');
    if (initialDialog) { state.dialog = initialDialog; state.lastFocus = document.activeElement; queueMicrotask(() => focusable(initialDialog)[0]?.focus() || initialDialog.focus()); }
    const cleanup = () => { stopDrag(); observer?.disconnect(); root.removeEventListener('click', onClick); root.removeEventListener('keydown', onKey); grips.forEach(grip => grip.remove()); if (document.body.style.userSelect === 'none') document.body.style.userSelect = ''; instances.delete(root); };
    instances.set(root, cleanup); return cleanup;
  }
  function dispose(root) { instances.get(root)?.(); }
  const api = { mount, dispose, clampWidth, MIN_CATALOG, MIN_INSPECTOR, MIN_GRAPH };
  if (typeof window !== 'undefined') window.KnowledgeWorkspace = api;
  if (typeof globalThis !== 'undefined') globalThis.KnowledgeWorkspace = api;
})();
