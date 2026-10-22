"use strict";
const checksViews = new Map();
const checkStatuses = {running: (globalThis.HubI18n?.t?.("checks.599ca07b8dd2") ?? 'Выполняется'), passed: (globalThis.HubI18n?.t?.("checks.be625a64f643") ?? 'Пройдено'), failed: (globalThis.HubI18n?.t?.("checks.bf22dfeeba8b") ?? 'Ошибка'), interrupted: (globalThis.HubI18n?.t?.("checks.f7b2f77928af") ?? 'Прерван'), unknown: (globalThis.HubI18n?.t?.("checks.8cf46ff28cc1") ?? 'Результат неизвестен')};
function checkRunStatus(run) {
  if (Object.hasOwn(checkStatuses, run.status)) return run.status;
  const kind = String(run.kind || '').replace(/^check\./, '');
  return kind === 'started' ? 'running' : Object.hasOwn(checkStatuses, kind) ? kind : 'unknown';
}
function checkRuns(events) {
  const runs = new Map();
  for (const [index, event] of (events || []).entries()) {
    const key = JSON.stringify([event.originProject || '', event.runId || event.id || `legacy-${index}`]);
    const previous = runs.get(key);
    // Newest-first events: retain terminal results when an older start is present.
    if (!previous || (checkRunStatus(previous) === 'running' && checkRunStatus(event) !== 'running')) runs.set(key, event);
  }
  return [...runs.values()];
}
function checksView() {
  let view = checksViews.get(activeProject);
  if (!view) {
    view = {runs: [], total: 0, generation: 0, loading: false, error: '', signature: null, filters: {profile: '', status: '', task: ''}};
    checksViews.set(activeProject, view);
  }
  return view;
}
function checksSignature() {
  return JSON.stringify([state.checkCount, state.checks]);
}
async function loadChecks(view = checksView()) {
  const project = activeProject, generation = ++view.generation;
  view.signature = checksSignature();
  view.loading = true; view.error = '';
  let offset = 0, events = [], pageRevision;
  try {
    while (offset !== null) {
      const response = await fetch('/api/v1/checks?' + new URLSearchParams({project, offset, limit: 50}));
      if (!response.ok) throw Error((globalThis.HubI18n?.t?.("checks.4e16d382b4fe") ?? 'Не удалось загрузить историю проверок'));
      const page = await response.json();
      if (generation !== view.generation) return;
      if (!Array.isArray(page.runs) || !Number.isInteger(page.total) || page.total < 0 ||
          (page.next !== null && (!Number.isInteger(page.next) || page.next <= offset))) throw Error((globalThis.HubI18n?.t?.("checks.bfe951d9051a") ?? 'Некорректная страница истории проверок'));
      if (offset === 0) pageRevision = page.revision;
      else if (pageRevision !== page.revision) throw Error((globalThis.HubI18n?.t?.("checks.a8d1a8317560") ?? 'История изменилась во время загрузки. Обновите список'));
      events.push(...page.runs);
      view.runs = checkRuns(events); view.total = page.total;
      offset = page.next;
      if (activeProject === project && route()[0] === 'checks') render({background: true});
    }
  } catch (error) {
    if (generation === view.generation) view.error = (globalThis.HubI18n?.error?.(error) ?? error.message);
  } finally {
    if (generation === view.generation) {
      view.loading = false;
      if (activeProject === project && route()[0] === 'checks') render({background: true});
    }
  }
}
function checkTime(value) {
  return value && Number.isFinite(Date.parse(value)) ? `<time datetime="${escape(value)}" title="${escape(value)}">${date(value)}</time>` : '<span>—</span>';
}
function checkDuration(run) {
  let ms = run.durationMs;
  if (ms == null && run.startedAt && run.finishedAt) ms = Date.parse(run.finishedAt) - Date.parse(run.startedAt);
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '—';
  const seconds = Math.floor(ms / 1000);
  return seconds < 60 ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("checks.120d7a6383b4",{v0:(seconds)}) : `${seconds} с`) : (globalThis.HubI18n?.t ? globalThis.HubI18n.t("checks.bc272e0cea15",{v0:(Math.floor(seconds / 60)),v1:(seconds % 60)}) : `${Math.floor(seconds / 60)} мин ${seconds % 60} с`);
}
function checkTaskLink(run) {
  if (!run.taskId) return (globalThis.HubI18n?.t?.("checks.a8c7a7d05c94") ?? '<span class="caption">Без задачи</span>');
  const task = (state.tasks || []).find(item => item.id === run.taskId);
  const stage = task?.stages?.find(item => item.id === run.stageId);
  const hash = taskLink({id: run.taskId}, run.stageId);
  const href = run.ownerProject && run.ownerProject !== activeProject ? '?' + new URLSearchParams({project: run.ownerProject}) + hash : hash;
  return `<a href="${escape(href)}" title="${escape(run.taskId + (run.stageId ? '/' + run.stageId : ''))}">${escape(task?.title || run.taskId)}${run.stageId ? ' / ' + escape(stage?.title || run.stageId) : ''}</a>`;
}
function checkRunRow(run, index, baseline = false) {
  const value = baseline ? (Object.hasOwn(checkStatuses, run.status) ? run.status : 'unknown') : checkRunStatus(run);
  const fields = [
    [(globalThis.HubI18n?.t?.("checks.66842329abcf") ?? 'ID запуска'), run.runId || run.id], [(globalThis.HubI18n?.t?.("checks.1d80e1757a7a") ?? 'Запись'), baseline ? (globalThis.HubI18n?.t?.("checks.be8ee1152065") ?? 'Начальный срез') : run.legacy ? (globalThis.HubI18n?.t?.("checks.5fa57ef4ba8c") ?? 'Историческая запись') : (globalThis.HubI18n?.t?.("checks.d5e8c111c915") ?? 'Зарегистрированный запуск')], [(globalThis.HubI18n?.t?.("checks.29de0472de7c") ?? 'Профиль / версия'), [run.profile, run.profileVersion].filter(x => x != null).join(' / ')],
    [(globalThis.HubI18n?.t?.("checks.64e9e8a8b277") ?? 'Команда (argv)'), Array.isArray(run.command) ? JSON.stringify(run.command) : null],
    [(globalThis.HubI18n?.t?.("checks.a2cb4dde2ce6") ?? 'Область проверки'), Array.isArray(run.scope) ? run.scope.join('\n') : null],
    [(globalThis.HubI18n?.t?.("checks.58fed910e73e") ?? 'Ревизия'), run.revision == null ? null : JSON.stringify(run.revision, null, 2)],
    [(globalThis.HubI18n?.t?.("checks.5960fc2fec3e") ?? 'Код выхода'), run.exitCode],
    ...(run.correction ? [[(globalThis.HubI18n?.t?.("checks.6f1924c288de") ?? 'Причина исправления'), run.correction.reason], [(globalThis.HubI18n?.t?.("checks.1b3ef3ff3360") ?? 'Предыдущая запись'), run.correction.expectedEvent]] : []),
  ];
  const projects = [[(globalThis.HubI18n?.t?.("checks.ff6cb3b265db") ?? 'Исходный проект'), run.originProject], [(globalThis.HubI18n?.t?.("checks.d36a133fd3fa") ?? 'Проект-владелец'), run.ownerProject], [(globalThis.HubI18n?.t?.("checks.da69491c9290") ?? 'Проект запуска'), run.launchProject]];
  const projectFields = projects.map(([label, id]) => {
    const name = id && typeof projectNames !== 'undefined' ? projectNames.get(id) : null;
    return `<div><dt>${label}</dt><dd title="${escape(id || '')}">${escape(id ? name || (globalThis.HubI18n?.t?.("checks.dcc30b47bd1e") ?? 'Проект недоступен') : '—')}</dd></div>`;
  }).join('');
  const key = JSON.stringify(['check', activeProject, baseline, run.originProject, run.runId || run.id || index]);
return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("checks.47ea8d60f8ce",{v0:(escape(key)),v1:(uiIcon('chevron')),v2:(status(value)),v3:(escape(run.title || (globalThis.HubI18n?.t?.("checks.e56a412d1285") ?? 'Проверка'))),v4:(checkTaskLink(run)),v5:(escape(run.profile || '—')),v6:(checkTime(Object.hasOwn(run, 'startedAt') ? run.startedAt : run.at)),v7:(checkTime(run.finishedAt)),v8:(escape(checkDuration(run))),v9:(run.summary || run.detail ? `<p>${escape(run.summary || run.detail)}</p>` : ''),v10:(fields.map(([label, value]) => `<div><dt>${label}</dt><dd><pre>${escape(value == null || value === '' ? '—' : value)}</pre></dd></div>`).join('')),v11:(projectFields),v12:(evidence(run.evidence))}) : `<details class="checks-run" data-key="${escape(key)}"><summary><span class="checks-expand">${uiIcon('chevron')}</span>${status(value)}<span class="checks-run-heading"><strong>${escape(run.title || (globalThis.HubI18n?.t?.("checks.e56a412d1285") ?? 'Проверка'))}</strong>${checkTaskLink(run)}</span><span class="checks-time checks-profile"><small>Профиль</small><span>${escape(run.profile || '—')}</span></span><span class="checks-time"><small>Начало</small>${checkTime(Object.hasOwn(run, 'startedAt') ? run.startedAt : run.at)}</span><span class="checks-time"><small>Завершение</small>${checkTime(run.finishedAt)}</span><span class="checks-time"><small>Длительность</small>${escape(checkDuration(run))}</span></summary><div class="checks-detail">${run.summary || run.detail ? `<p>${escape(run.summary || run.detail)}</p>` : ''}<dl>${fields.map(([label, value]) => `<div><dt>${label}</dt><dd><pre>${escape(value == null || value === '' ? '—' : value)}</pre></dd></div>`).join('')}${projectFields}</dl>${evidence(run.evidence)}</div></details>`);
}
function filteredCheckRuns(view) {
  const f = view.filters;
  return view.runs.filter(run => (!f.profile || run.profile === f.profile) && (!f.status || checkRunStatus(run) === f.status) && (!f.task || run.taskId === f.task));
}
function renderChecksPage() {
  const view = checksView();
  if (view.signature === null) {
    view.runs = checkRuns(state.checks || (state.events || []).filter(e => e.kind.startsWith('check.')));
    view.total = state.checkCount || view.runs.length;
  }
  if (view.signature !== checksSignature()) void loadChecks(view);
  const options = (key, label, values) => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("checks.b8232ffae9b1",{v0:(key),v1:(label),v2:(key),v3:(key),v4:(values.map(([id, text]) => `<option value="${escape(id)}" ${view.filters[key] === id ? 'selected' : ''}>${escape(text)}</option>`).join(''))}) : `<label for="checks-${key}">${label}<select id="checks-${key}" data-checks-filter="${key}"><option value="">Все</option>${values.map(([id, text]) => `<option value="${escape(id)}" ${view.filters[key] === id ? 'selected' : ''}>${escape(text)}</option>`).join('')}</select></label>`);
  const choices = key => [...new Set([...view.runs.map(run => run[key]), view.filters[key === 'taskId' ? 'task' : key]].filter(Boolean))].sort().map(value => [value, key === 'taskId' ? (state.tasks || []).find(task => task.id === value)?.title || value : value]);
  const runs = filteredCheckRuns(view);
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("checks.a7f9938c7e3e",{v0:(title((globalThis.HubI18n?.t?.("checks.43c696001243") ?? 'Качество'), (globalThis.HubI18n?.t?.("checks.bb1b79b14c91") ?? 'Проверки'), '')),v1:(options('profile', (globalThis.HubI18n?.t?.("checks.359497aff53e") ?? 'Профиль'), choices('profile'))),v2:(options('status', (globalThis.HubI18n?.t?.("checks.225077c6d479") ?? 'Статус'), Object.entries(checkStatuses))),v3:(options('task', (globalThis.HubI18n?.t?.("checks.b9ce27191d40") ?? 'Задача'), choices('taskId'))),v4:(view.loading ? 'disabled' : ''),v5:(uiIcon('refresh')),v6:(view.loading ? (globalThis.HubI18n?.t?.("checks.7d7e6c8ac615") ?? 'Загрузка… · ') : ''),v7:(view.runs.length),v8:(view.total),v9:(runs.length),v10:(view.error ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("checks.e716a9b6a00a",{v0:(escape(view.error))}) : `<p role="alert" class="checks-error">${escape(view.error)}. Показана доступная часть истории.</p>`) : ''),v11:(view.loading),v12:(runs.map((run, i) => checkRunRow(run, i)).join('') || `<p class="caption">${view.loading ? (globalThis.HubI18n?.t?.("checks.8ce7a2e82e67") ?? 'Загрузка запусков…') : (globalThis.HubI18n?.t?.("checks.9bd8481f4216") ?? 'Запусков по выбранным условиям нет.')}</p>`),v13:((state.project.checks || []).map((run, i) => checkRunRow(run, i, true)).join('') || (globalThis.HubI18n?.t?.("checks.12948425bb26") ?? '<p class="caption">Начальный срез не зарегистрирован.</p>'))}) : `${title((globalThis.HubI18n?.t?.("checks.43c696001243") ?? 'Качество'), (globalThis.HubI18n?.t?.("checks.bb1b79b14c91") ?? 'Проверки'), '')}<section class="checks-page" aria-label="История проверок"><div class="checks-toolbar">${options('profile', (globalThis.HubI18n?.t?.("checks.359497aff53e") ?? 'Профиль'), choices('profile'))}${options('status', (globalThis.HubI18n?.t?.("checks.225077c6d479") ?? 'Статус'), Object.entries(checkStatuses))}${options('task', (globalThis.HubI18n?.t?.("checks.b9ce27191d40") ?? 'Задача'), choices('taskId'))}<button class="icon-button" type="button" data-checks-refresh title="Обновить историю проверок" aria-label="Обновить историю проверок" ${view.loading ? 'disabled' : ''}>${uiIcon('refresh')}</button></div><p class="checks-count" role="status">${view.loading ? (globalThis.HubI18n?.t?.("checks.7d7e6c8ac615") ?? 'Загрузка… · ') : ''}Загружено ${view.runs.length} из ${view.total} · По фильтрам: ${runs.length}</p>${view.error ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("checks.e716a9b6a00a",{v0:(escape(view.error))}) : `<p role="alert" class="checks-error">${escape(view.error)}. Показана доступная часть истории.</p>`) : ''}<div class="checks-runs" aria-busy="${view.loading}">${runs.map((run, i) => checkRunRow(run, i)).join('') || `<p class="caption">${view.loading ? (globalThis.HubI18n?.t?.("checks.8ce7a2e82e67") ?? 'Загрузка запусков…') : (globalThis.HubI18n?.t?.("checks.9bd8481f4216") ?? 'Запусков по выбранным условиям нет.')}</p>`}</div></section><section class="checks-baseline"><div class="section-head"><h2>Подтверждённый начальный срез</h2><span class="caption">До запуска журнала</span></div>${(state.project.checks || []).map((run, i) => checkRunRow(run, i, true)).join('') || (globalThis.HubI18n?.t?.("checks.12948425bb26") ?? '<p class="caption">Начальный срез не зарегистрирован.</p>')}</section>`);
}
document.addEventListener('change', event => {
  const key = event.target.dataset.checksFilter;
  if (!['profile', 'status', 'task'].includes(key)) return;
  checksView().filters[key] = event.target.value;
  render();
});
document.addEventListener('click', event => {
  if (!event.target.closest('[data-checks-refresh]')) return;
  void loadChecks(); render();
});

globalThis.HubI18n?.onChange?.(()=>{Object.assign(checkStatuses,{running: (globalThis.HubI18n?.t?.("checks.599ca07b8dd2") ?? 'Выполняется'), passed: (globalThis.HubI18n?.t?.("checks.be625a64f643") ?? 'Пройдено'), failed: (globalThis.HubI18n?.t?.("checks.bf22dfeeba8b") ?? 'Ошибка'), interrupted: (globalThis.HubI18n?.t?.("checks.f7b2f77928af") ?? 'Прерван'), unknown: (globalThis.HubI18n?.t?.("checks.8cf46ff28cc1") ?? 'Результат неизвестен')});});
