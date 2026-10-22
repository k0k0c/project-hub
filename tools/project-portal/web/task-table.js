"use strict";

// Shared classic script: app.js supplies the rendering helpers and tree state.
const taskTableColumns = [
  ['title', (globalThis.HubI18n?.t?.("task-table.b9ce27191d40") ?? 'Задача')], ['summary', (globalThis.HubI18n?.t?.("task-table.b3680f2cba5f") ?? 'Описание')], ['type', (globalThis.HubI18n?.t?.("task-table.d4a6795c199f") ?? 'Тип')],
  ['priority', (globalThis.HubI18n?.t?.("task-table.0e5ac36d3f46") ?? 'Приоритет')], ['children', (globalThis.HubI18n?.t?.("task-table.4db42ea0e429") ?? 'Дочерние')], ['status', (globalThis.HubI18n?.t?.("task-table.9a9f0a0c10e3") ?? 'Статус / агент')],
  ['progress', (globalThis.HubI18n?.t?.("task-table.610d4c2115f6") ?? 'План')], ['estimate', (globalThis.HubI18n?.t?.("task-table.890c6b81731d") ?? 'Оценка / осталось')],
  ['created', (globalThis.HubI18n?.t?.("task-table.0a39fbc65169") ?? 'Создана')], ['updated', (globalThis.HubI18n?.t?.("task-table.3c56cb41be6f") ?? 'Обновлена')], ['actions', (globalThis.HubI18n?.t?.("task-table.cad123465b9e") ?? 'Действия')],
];
let taskTableProject = null;
let taskTableHidden = new Set();
let taskColumnMenuOpen = false;
let taskTableTreeProject = null;
let taskTableColumnsKey = '';

function loadTaskTableColumns() {
  const columns = typeof projectSettings === 'function' ? projectSettings().tasks.columns : null;
  let raw = null;
  try { raw = localStorage.getItem(`project-hub-task-columns:${activeProject}`); } catch { /* Optional storage. */ }
  const key = JSON.stringify([activeProject, columns, raw]);
  if (taskTableColumnsKey === key) return;
  taskTableColumnsKey = key;
  if (taskTableProject !== activeProject) taskColumnMenuOpen = false;
  taskTableProject = activeProject;
  taskTableHidden = new Set(columns ? taskTableColumns.filter(([id]) => id !== 'title' && !columns.includes(id)).map(([id]) => id) : ['summary', 'children']);
  try {
    const saved = JSON.parse(raw || 'null');
    if (Array.isArray(saved)) taskTableHidden = new Set(saved.filter(id =>
      typeof id === 'string' && id !== 'title' && taskTableColumns.some(column => column[0] === id)));
  } catch { /* Storage is optional, including invalid saved JSON. */ }
}

function renderTaskColumnMenu() {
  loadTaskTableColumns();
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-table.6a0cc3e0a931",{v0:(taskColumnMenuOpen ? 'open' : ''),v1:(uiIcon('columns')),v2:(taskTableColumns.map(([id, label]) => `<label><input type="checkbox" data-task-column="${id}" ${taskTableHidden.has(id) ? '' : 'checked'} ${id === 'title' ? 'disabled' : ''}><span>${label}</span></label>`).join(''))}) : `<details class="task-column-menu" data-task-column-menu ${taskColumnMenuOpen ? 'open' : ''}><summary class="icon-button" aria-label="Столбцы таблицы" title="Столбцы таблицы">${uiIcon('columns')}</summary><fieldset class="task-column-options"><legend>Столбцы таблицы</legend>${taskTableColumns.map(([id, label]) => `<label><input type="checkbox" data-task-column="${id}" ${taskTableHidden.has(id) ? '' : 'checked'} ${id === 'title' ? 'disabled' : ''}><span>${label}</span></label>`).join('')}</fieldset></details>`);
}

function captureTaskTableUi() {
  const menu = document.querySelector('[data-task-column-menu]');
  const focus = document.activeElement;
  return {
    project: activeProject,
    open: !!menu?.open,
    focus: menu?.contains(focus) ? (focus.dataset.taskColumn || 'summary') : null,
    scroll: document.querySelector('[data-task-table-scroll]')?.scrollLeft || 0,
  };
}

function restoreTaskTableUi(snapshot) {
  if (!snapshot || snapshot.project !== activeProject) return;
  const menu = document.querySelector('[data-task-column-menu]');
  if (menu) menu.open = taskColumnMenuOpen = snapshot.open;
  const scroller = document.querySelector('[data-task-table-scroll]');
  if (scroller) scroller.scrollLeft = snapshot.scroll;
  if (menu && snapshot.focus) {
    const selector = snapshot.focus === 'summary' ? 'summary' : `[data-task-column="${snapshot.focus}"]`;
    menu.querySelector(selector)?.focus({preventScroll: true});
  }
}

function renderTaskTable(entries, terms, context) {
  loadTaskTableColumns();
  const visible = new Map(entries.map(entry => [entry.task.id, entry]));
  const children = new Map();
  for (const entry of entries) {
    const parent = visible.has(entry.task.parentTask) ? entry.task.parentTask : null;
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(entry);
  }
  const roots = children.get(null) || [];
  if (taskTableTreeProject !== activeProject) {
    taskTableTreeProject = treeStateProject = activeProject;
    treeExpanded = new Set(roots.map(entry => entry.task.id));
    try {
      const saved = JSON.parse(localStorage.getItem(`project-hub-tree:${activeProject}`) || 'null');
      if (Array.isArray(saved)) treeExpanded = new Set(saved.filter(id => typeof id === 'string'));
    } catch { /* Best effort. */ }
  }
  window.saveTaskTreeState = () => {
    try { localStorage.setItem(`project-hub-tree:${activeProject}`, JSON.stringify([...treeExpanded])); } catch { /* Best effort. */ }
  };
  const cell = (id, value, heading = false) => `<${heading ? 'th scope="row"' : 'td'} data-task-cell="${id}" ${taskTableHidden.has(id) ? 'hidden' : ''}>${value}</${heading ? 'th' : 'td'}>`;
  const priority = value => ({blocker: 'Blocker', critical: 'Critical', major: 'Major', minor: 'Minor', trivial: 'Trivial'})[value];
  const stamp = value => value && Number.isFinite(Date.parse(value)) ? `<time datetime="${escape(value)}" title="${escape(value)}">${date(value)}</time>` : '&#8212;';
  const gitObligation = task => {
    const checkpoints = [task.gitCheckpoint, ...(task.stages || []).map(stage => stage.gitCheckpoint)]
      .filter(checkpoint => checkpoint && (checkpoint.status === 'error' || checkpoint.status === 'pending' || checkpoint.publication?.status === 'pending'));
    if (!checkpoints.length) return '';
    const groups = new Map();
    checkpoints.forEach((checkpoint, index) => {
      const key = checkpoint.batchId ? `batch:${checkpoint.batchId}` : `operation:${checkpoint.operationId || checkpoint.id || index}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(checkpoint);
    });
    const label = `Git: ${groups.size}`;
    const reasons = [...groups.values()].map(group => [...new Set(group.map(checkpointReason))].join(' · ')).join('\n');
    return `<a class="task-git-obligation" href="${taskLink(task)}" title="${escape(reasons)}" aria-label="${escape(label + (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-table.b23ba1d01017",{v0:(checkpoints.length),v1:(groups.size)}) : ` · ${checkpoints.length} обязательств, ${groups.size} групп`))}">${escape(label)}</a>`;
  };
  const visited = new Set();
  const rows = [];
  const visit = (entry, depth, hidden) => {
    const task = entry.task;
    if (visited.has(task.id)) return;
    visited.add(task.id);
    const nested = children.get(task.id) || [];
    const expanded = treeExpanded.has(task.id);
    const stages = task.stages || [];
    const done = stages.filter(stage => stage.status === 'done').length;
    const aggregate = task.progressAggregate || {done, total: stages.length, percent: stages.length ? Math.round(done / stages.length * 100) : 0};
    const toggleLabel = expanded ? (globalThis.HubI18n?.t?.("task-table.dfaa7a9e8d3a") ?? 'Свернуть дочерние задачи') : (globalThis.HubI18n?.t?.("task-table.71062d4f854f") ?? 'Развернуть дочерние задачи');
    const toggle = nested.length ? `<button class="icon-button tree-toggle" type="button" data-tree-toggle="${escape(task.id)}" aria-expanded="${expanded}" aria-label="${toggleLabel}" title="${toggleLabel}">${uiIcon('chevron')}</button>` : '<span class="task-table-toggle-spacer"></span>';
    const details = terms.length ? `<ul class="search-context">${(entry.fields || []).slice(0, 3).map(field => context({...field, task})).join('')}</ul>` : '';
    const titleCell = `<div class="task-table-title" style="--task-depth:${Math.min(depth, 12)}">${toggle}<a href="${taskLink(task)}" title="${escape([task.title, task.summary].filter(Boolean).join('\n'))}">${escape(task.title)}</a></div>${details}`;
    const badges = `${priority(task.priority) ? `<span class="task-priority ${escape(task.priority)}">${priority(task.priority)}</span>` : '&#8212;'}${priority(task.maxDescendantPriority) ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-table.2d6faffbb6c5",{v0:(escape(task.maxDescendantPriority)),v1:(priority(task.maxDescendantPriority))}) : `<span class="task-priority descendant ${escape(task.maxDescendantPriority)}" title="Максимальный приоритет незавершённых потомков">Потомки: ${priority(task.maxDescendantPriority)}</span>`) : ''}`;
    const created = task.createdAt || state?.project?.baselineAt;
    rows.push(`<tr data-tree-task="${escape(task.id)}" data-tree-depth="${depth}" ${hidden ? 'hidden' : ''}>${cell('title', titleCell, true)}${cell('summary', `<span class="task-table-summary" title="${escape(task.summary)}">${escape(task.summary)}</span>`)}${cell('type', escape(({epic: 'Epic', bug: 'Bug', task: 'Task'})[task.type || 'task'] || task.type))}${cell('priority', badges)}${cell('children', String(task.children?.length || nested.length || 0))}${cell('status', taskStatus(task, null, true) + gitObligation(task))}${cell('progress', `${stageStrip({...task, stages})}<span>${escape(aggregate.done)} / ${escape(aggregate.total)} · ${escape(aggregate.percent)}%</span>`)}${cell('estimate', estimate(task, true))}${cell('created', stamp(created))}${cell('updated', stamp(task.updatedAt || created))}${cell('actions', copyControls(task))}</tr>`);
    nested.forEach(child => visit(child, depth + 1, hidden || !expanded));
  };
  roots.forEach(entry => visit(entry, 0, false));
  // Keep malformed cycles visible without recursing forever or duplicating rows.
  entries.forEach(entry => { if (!visited.has(entry.task.id)) visit(entry, 0, false); });
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-table.77c8465f46ff",{v0:(taskTableColumns.map(([id, label]) => `<th scope="col" data-task-cell="${id}" ${taskTableHidden.has(id) ? 'hidden' : ''}>${label}</th>`).join('')),v1:(rows.join(''))}) : `<div class="task-table-scroll" data-task-table-scroll data-scroll-key="task-table" tabindex="0" role="region" aria-label="Таблица задач"><table class="task-table"><thead><tr>${taskTableColumns.map(([id, label]) => `<th scope="col" data-task-cell="${id}" ${taskTableHidden.has(id) ? 'hidden' : ''}>${label}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`);
}

document.addEventListener('click', event => {
  const summary = event.target.closest('[data-task-column-menu] > summary');
  if (summary) taskColumnMenuOpen = !summary.parentElement.open;
  else if (!event.target.closest('[data-task-column-menu]')) {
    taskColumnMenuOpen = false;
    document.querySelectorAll('[data-task-column-menu]').forEach(menu => { menu.open = false; });
  }
});
document.addEventListener('change', event => {
  const input = event.target.closest('[data-task-column]');
  if (!input || input.dataset.taskColumn === 'title') return;
  loadTaskTableColumns();
  const id = input.dataset.taskColumn;
  if (!taskTableColumns.some(column => column[0] === id)) return;
  if (input.checked) taskTableHidden.delete(id); else taskTableHidden.add(id);
  try { localStorage.setItem(`project-hub-task-columns:${activeProject}`, JSON.stringify([...taskTableHidden])); } catch { /* Best effort. */ }
  const snapshot = captureTaskTableUi();
  replacePreservingScroll('#task-results', taskResults());
  restoreTaskTableUi(snapshot);
});
document.addEventListener('keydown', event => {
  const menu = event.target.closest('[data-task-column-menu]');
  if (!menu) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    menu.open = taskColumnMenuOpen = false;
    menu.querySelector('summary').focus();
  } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault();
    menu.open = taskColumnMenuOpen = true;
    const inputs = [...menu.querySelectorAll('input:not(:disabled)')];
    const current = inputs.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? inputs.length - 1 : current < 0 ? (event.key === 'ArrowDown' ? 0 : inputs.length - 1) : (current + (event.key === 'ArrowDown' ? 1 : -1) + inputs.length) % inputs.length;
    inputs[next]?.focus();
  }
});
function positionTableCopyMenu(event) {
  const menu = event.target.closest('.task-table .copy-menu');
  if (!menu) return;
  const trigger = menu.querySelector('.copy-trigger'), options = menu.querySelector('.copy-menu-options');
  const rect = trigger.getBoundingClientRect();
  options.style.left = `${Math.max(8, Math.min(rect.right - 170, window.innerWidth - 178))}px`;
  options.style.top = `${rect.bottom + 130 < window.innerHeight ? rect.bottom : Math.max(8, rect.top - 120)}px`;
}
document.addEventListener('pointerover', positionTableCopyMenu);
document.addEventListener('focusin', positionTableCopyMenu);

globalThis.HubI18n?.onChange?.(()=>{taskTableColumns.splice(0,taskTableColumns.length,...[
  ['title', (globalThis.HubI18n?.t?.("task-table.b9ce27191d40") ?? 'Задача')], ['summary', (globalThis.HubI18n?.t?.("task-table.b3680f2cba5f") ?? 'Описание')], ['type', (globalThis.HubI18n?.t?.("task-table.d4a6795c199f") ?? 'Тип')],
  ['priority', (globalThis.HubI18n?.t?.("task-table.0e5ac36d3f46") ?? 'Приоритет')], ['children', (globalThis.HubI18n?.t?.("task-table.4db42ea0e429") ?? 'Дочерние')], ['status', (globalThis.HubI18n?.t?.("task-table.9a9f0a0c10e3") ?? 'Статус / агент')],
  ['progress', (globalThis.HubI18n?.t?.("task-table.610d4c2115f6") ?? 'План')], ['estimate', (globalThis.HubI18n?.t?.("task-table.890c6b81731d") ?? 'Оценка / осталось')],
  ['created', (globalThis.HubI18n?.t?.("task-table.0a39fbc65169") ?? 'Создана')], ['updated', (globalThis.HubI18n?.t?.("task-table.3c56cb41be6f") ?? 'Обновлена')], ['actions', (globalThis.HubI18n?.t?.("task-table.cad123465b9e") ?? 'Действия')],
]);});
