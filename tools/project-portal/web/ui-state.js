"use strict";
// Personal, origin-wide preference. Project defaults and resize never rewrite it.
const hubMenuPreferenceKey = 'project-hub-menu:v1';
let hubMenuPreference = 'auto', hubMenuStorageWarning = '';
try {
  const saved = localStorage.getItem(hubMenuPreferenceKey);
  if (saved === 'compact') hubMenuPreference = saved;
} catch { hubMenuStorageWarning = (globalThis.HubI18n?.t?.("ui-state.7b66a8d552a0") ?? 'Выбор меню действует до закрытия страницы: хранилище браузера недоступно.'); }
function applyHubMenuPreference() {
  if (document.documentElement) document.documentElement.dataset.hubMenu = hubMenuPreference;
}
function hubMenuStatus() {
  if (hubMenuStorageWarning) return hubMenuStorageWarning;
  const narrow = typeof window !== 'undefined' && window.matchMedia?.('(max-width:760px)').matches;
  return narrow ? (globalThis.HubI18n?.t?.("ui-state.b1d1fc1eb78f") ?? 'Сейчас: иконки из-за ширины окна. Ваш выбор сохранён.') : hubMenuPreference === 'compact'
    ? (globalThis.HubI18n?.t?.("ui-state.eb75c10712a5") ?? 'Сейчас: только иконки. Выбор сохранён.') : (globalThis.HubI18n?.t?.("ui-state.bde59ece1110") ?? 'Сейчас: полное меню. Выбор сохранён.');
}
function updateHubMenuStatus() {
  const status = document.getElementById?.('menu-preference-status');
  if (status) status.textContent = hubMenuStatus();
}
applyHubMenuPreference();
if (typeof window !== 'undefined') window.matchMedia?.('(max-width:760px)').addEventListener('change', updateHubMenuStatus);
document.addEventListener('change', event => {
  if (event.target.id !== 'setting-menu-mode') return;
  hubMenuPreference = event.target.value === 'compact' ? 'compact' : 'auto';
  try { localStorage.setItem(hubMenuPreferenceKey, hubMenuPreference); hubMenuStorageWarning = ''; }
  catch { hubMenuStorageWarning = (globalThis.HubI18n?.t?.("ui-state.7b66a8d552a0") ?? 'Выбор меню действует до закрытия страницы: хранилище браузера недоступно.'); }
  applyHubMenuPreference();
  updateHubMenuStatus();
});
if (typeof window !== 'undefined' && window.addEventListener) window.addEventListener('storage', event => {
  if (event.key !== hubMenuPreferenceKey && event.key !== null) return;
  hubMenuPreference = event.newValue === 'compact' ? 'compact' : 'auto';
  applyHubMenuPreference();
  const select = document.getElementById('setting-menu-mode');
  if (select) select.value = hubMenuPreference;
});
function readUiState(project) {
  try {
    const value = JSON.parse(localStorage.getItem(`project-hub-ui:v1:${project}`) || '{}');
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch { return {}; }
}
function restoreUiState() {
  const saved = readUiState(activeProject);
  const defaults = typeof projectSettings === 'function' ? projectSettings().tasks : {};
  const choice = (value, options, fallback) => options.includes(value) ? value : fallback;
  const text = value => typeof value === 'string' ? value.slice(0, 2000) : '';
  const sorts = ['created', 'created-oldest', 'updated', 'priority', 'status', 'progress', 'title'];
  const url = new URLSearchParams(location.search);
  taskFilter = choice(saved.tasks?.status, ['all', 'active', 'planned', 'queued', 'blocked', 'done', 'cancelled'], defaults.showCompleted === false ? 'project' : 'all');
  taskTypeFilter = choice(saved.tasks?.type, ['all', 'task', 'bug', 'epic'], 'all');
  taskPriorityFilter = choice(saved.tasks?.priority, ['all', 'blocker', 'critical', 'major', 'minor', 'trivial'], 'all');
  taskSearch = text(saved.tasks?.search);
  taskListSort = choice(url.get('taskSort') ?? saved.tasks?.sort, sorts, defaults.sort || 'created');
  taskSort = choice(url.get('sort') ?? saved.overview?.sort, sorts, defaults.overviewSort || 'created');
  historyTask = route()[0] === 'history' && route()[1] ? route()[1] : text(saved.history?.task);
  historyKind = choice(saved.history?.kind, ['', 'task', 'check', 'decision', 'finding', 'git'], '');
  diagnosticSearch = text(saved.diagnostics?.search);
}
function saveUiState(field) {
  try {
    const values = {
      tasks: {status: taskFilter, type: taskTypeFilter, priority: taskPriorityFilter, search: taskSearch, sort: taskListSort},
      overview: {sort: taskSort}, history: {task: historyTask, kind: historyKind}, diagnostics: {search: diagnosticSearch},
    };
    const saved = readUiState(activeProject);
    if (field) {
      const [section, key] = field;
      saved[section] = {...saved[section], [key]: values[section][key]};
      if (section === 'tasks' && key === 'status' && taskFilter === 'project') delete saved.tasks.status;
    }
    localStorage.setItem(`project-hub-ui:v1:${activeProject}`, JSON.stringify(field ? saved : values));
  } catch { /* Browser storage is optional. */ }
}
for (const name of ['input', 'change']) document.addEventListener(name, event => {
  const fields = {'task-search':['tasks','search'], 'task-status-filter':['tasks','status'], 'task-type-filter':['tasks','type'], 'task-priority-filter':['tasks','priority'], 'task-list-sort':['tasks','sort'], 'overview-task-sort':['overview','sort'], 'history-task':['history','task'], 'history-kind':['history','kind'], 'diagnostic-search':['diagnostics','search']};
  if (fields[event.target.id]) saveUiState(fields[event.target.id]);
});

function resetProjectListPreferences() {
  const saved = readUiState(activeProject);
  delete saved.tasks; delete saved.overview;
  try {
    localStorage.setItem(`project-hub-ui:v1:${activeProject}`, JSON.stringify(saved));
    localStorage.removeItem(`project-hub-task-columns:${activeProject}`);
  } catch { /* Storage is optional. */ }
  const url = new URL(location.href);
  url.searchParams.delete('sort'); url.searchParams.delete('taskSort');
  history.replaceState(null, '', url);
  restoreUiState();
  document.querySelector('#task-results')?.closest('main')?.replaceChildren();
  render();
}


// Dialog resource updates may replace the whole dialog or just its content.
// Remember actual user scroll events, not clamped offsets from loading paints.
if (typeof window !== 'undefined') window.HubDialogScroll = (() => {
  const selector='dialog,[role="dialog"],.k-auxiliary',positions=new Map(),restored=new WeakMap();
  const key=dialog=>dialog.dataset?.dialogScrollKey||dialog.id||dialog.getAttribute?.('aria-label')||dialog.className||'dialog';
  const owner=node=>node?.closest?.(selector);
  const isOpen=dialog=>dialog.nodeName?.toLowerCase()!=='dialog'||dialog.open===true;
  const forget=dialog=>{positions.delete(key(dialog));restored.delete(dialog);for(const node of dialog.querySelectorAll?.('*')||[])restored.delete(node);};
  function path(dialog,node){
    if(node===dialog)return '$';
    if(node.dataset?.scrollKey)return 'scroll:'+node.dataset.scrollKey;
    if(node.id)return 'id:'+node.id;
    if(node.getAttribute?.('name'))return 'name:'+node.getAttribute('name');
    const parts=[];for(let child=node;child&&child!==dialog;child=child.parentElement){const parent=child.parentElement;if(!parent)return null;parts.unshift([...parent.children].indexOf(child));}return 'path:'+parts.join('.');
  }
  function remember(node){
    const dialog=owner(node);if(!dialog||!isOpen(dialog))return;
    const applied=restored.get(node);if(applied&&applied.top===node.scrollTop&&applied.left===node.scrollLeft)return;
    restored.delete(node);const id=key(dialog),name=path(dialog,node);if(!name)return;
    if(!positions.has(id))positions.set(id,new Map());positions.get(id).set(name,{top:node.scrollTop,left:node.scrollLeft});
    while(positions.size>32)positions.delete(positions.keys().next().value);
  }
  function resolve(dialog,name){
    if(name==='$')return dialog;
    const nodes=[...dialog.querySelectorAll('*')];
    if(name.startsWith('id:'))return nodes.find(n=>n.id===name.slice(3));
    if(name.startsWith('name:'))return nodes.find(n=>n.getAttribute?.('name')===name.slice(5));
    if(name.startsWith('scroll:'))return nodes.find(n=>n.dataset?.scrollKey===name.slice(7));
    let node=dialog;for(const index of name.slice(5).split('.'))node=node?.children?.[Number(index)];return node;
  }
  function restore(root=document){
    const dialogs=[...root.querySelectorAll(selector)].filter(isOpen),active=new Set(dialogs.map(key));
    for(const dialog of dialogs)for(const [name,position] of positions.get(key(dialog))||[]){const node=resolve(dialog,name);if(!node)continue;node.scrollTop=position.top;node.scrollLeft=position.left;restored.set(node,{top:node.scrollTop,left:node.scrollLeft});}
    // Closing a dialog starts the next explicit opening at the top. A resource
    // replacement in one mutation batch retains the same stable dialog key.
    for(const id of positions.keys())if(!active.has(id))positions.delete(id);
  }
  document.addEventListener('scroll',event=>remember(event.target),{capture:true,passive:true});
  document.addEventListener('close',event=>{const dialog=owner(event.target);if(dialog&&!isOpen(dialog))forget(dialog);},true);
  let scheduled=false;
  const schedule=()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;restore();});};
  if(typeof MutationObserver!=='undefined'){
    const observe=()=>{if(!document.body)return;new MutationObserver(records=>{
      for(const record of records)if(record.type==='attributes'&&record.attributeName==='open'&&record.target.nodeName?.toLowerCase()==='dialog'&&(record.oldValue!==null||!isOpen(record.target)))forget(record.target);
      if(records.some(record=>owner(record.target)||[...(record.addedNodes||[]),...(record.removedNodes||[])].some(node=>node.matches?.(selector)||node.querySelector?.(selector))))schedule();
    }).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open'],attributeOldValue:true});};
    if(document.body)observe();else document.addEventListener('DOMContentLoaded',observe,{once:true});
  }
  return {remember,restore};
})();
