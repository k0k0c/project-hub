"use strict";
const compactDate = value => value && Number.isFinite(Date.parse(value)) ? new Intl.DateTimeFormat((globalThis.HubI18n?.locale==='en'?'en-GB':'ru-RU'),{day:'2-digit',month:'2-digit',year:'2-digit'}).format(new Date(value)) : '—';
const taskEditor = document.createElement('dialog');
let taskEditorGeneration = 0;
taskEditor.className = 'task-editor';
document.body.append(taskEditor);
const editField = (name, label, value = '', kind = 'text') => `<label class="edit-field"><span>${escape(label)}</span>${kind === 'textarea' ? `<textarea name="${name}" rows="4">${escape(value)}</textarea>` : `<input name="${name}" type="${kind}" value="${escape(value)}" ${name === 'title' ? 'required maxlength="240"' : ''} ${kind === 'number' ? 'min="0" step="any"' : ''}>`}</label>`;
const editSelect = (name, label, values, selected) => `<label class="edit-field"><span>${escape(label)}</span><select name="${name}">${values.map(([value, text]) => `<option value="${escape(value)}" ${value === (selected ?? '') ? 'selected' : ''}>${escape(text)}</option>`).join('')}</select></label>`;
const sourceRow = source => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.2a7b89b16a0d",{v0:(escape(JSON.stringify(source))),v1:(escape(source.label || '')),v2:(escape(source.path || '')),v3:(uiIcon('close'))}) : `<div class="editor-source-row" data-source-row data-original="${escape(JSON.stringify(source))}"><input aria-label="Название источника" data-source-label value="${escape(source.label || '')}"><input aria-label="Путь источника" data-source-path required value="${escape(source.path || '')}"><button class="icon-button" type="button" data-remove-row title="Удалить источник" aria-label="Удалить источник">${uiIcon('close')}</button></div>`);
const relationNames = {'related':(globalThis.HubI18n?.t?.("task-editor.73c25b59c4b3") ?? 'Связана с'),'blocks':(globalThis.HubI18n?.t?.("task-editor.806bc5f8787d") ?? 'Блокирует'),'blocked-by':(globalThis.HubI18n?.t?.("task-editor.844c7f4197a7") ?? 'Зависит от'),'duplicates':(globalThis.HubI18n?.t?.("task-editor.ab91970691f9") ?? 'Дублирует'),'duplicated-by':(globalThis.HubI18n?.t?.("task-editor.1538ca66cb3e") ?? 'Дублируется задачей')};
function taskSources(task) {
  task = {...task, sources: taskImageSources(task)};
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.b4832aa2f471",{v0:(escape(task.id)),v1:(uiIcon('edit')),v2:(task.sources?.length ? evidence(task.sources) : (globalThis.HubI18n?.t?.("task-editor.08e7807a3694") ?? '<p class="caption">Нет прикреплённых источников.</p>'))}) : `<section class="task-sources" aria-label="Источники всей задачи"><div class="section-head"><h2>Источники задачи</h2><button class="icon-button" data-edit-task="${escape(task.id)}" title="Редактировать источники задачи" aria-label="Редактировать источники задачи">${uiIcon('edit')}</button></div>${task.sources?.length ? evidence(task.sources) : (globalThis.HubI18n?.t?.("task-editor.08e7807a3694") ?? '<p class="caption">Нет прикреплённых источников.</p>')}</section>`);
}
function stageLocationNotice(task, stageId) {
  if (!stageId || task.stages.some(s=>s.id===stageId)) return '';
  const archived = [...(task.archivedStages || [])].reverse().find(s=>s.id===stageId);
  if (!archived) return '';
  const target = archived.lifecycle?.targetTask;
  return `<p class="notice">${target ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.bd1f919d87e4",{v0:(taskLink({id:target},stageId)),v1:(escape(archived.title))}) : `Этап перенесён: <a href="${taskLink({id:target},stageId)}">${escape(archived.title)}</a>`) : (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.21841f48f3b2",{v0:(escape(archived.title))}) : `Этап исключён из плана: ${escape(archived.title)}. Он доступен в архиве этапов ниже.`)}</p>`;
}
function stageTransferHistory(stage) {
  if (!stage.transfers?.length) return '';
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.c1a85153671e",{v0:(stage.transfers.map(move=>`<p class="caption"><a href="${taskLink({id:move.fromTask},stage.id)}">${escape(move.fromTask)}</a> → <a href="${taskLink({id:move.toTask},stage.id)}">${escape(move.toTask)}</a> · ${date(move.at)}</p>`).join('')),v1:(stage.history?.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.5cf85684a13a",{v0:(stage.history.length),v1:(stage.history.map(e=>eventView(e,true)).join(''))}) : `<details><summary>Предыдущие события (${stage.history.length})</summary>${stage.history.map(e=>eventView(e,true)).join('')}</details>`) : '')}) : `<div class="detail-section"><h3>Переносы этапа</h3>${stage.transfers.map(move=>`<p class="caption"><a href="${taskLink({id:move.fromTask},stage.id)}">${escape(move.fromTask)}</a> → <a href="${taskLink({id:move.toTask},stage.id)}">${escape(move.toTask)}</a> · ${date(move.at)}</p>`).join('')}${stage.history?.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.5cf85684a13a",{v0:(stage.history.length),v1:(stage.history.map(e=>eventView(e,true)).join(''))}) : `<details><summary>Предыдущие события (${stage.history.length})</summary>${stage.history.map(e=>eventView(e,true)).join('')}</details>`) : ''}</div>`);
}
function taskRelations(task) {
  const links = task.relations || task.links || [];
  if (!links.length) return '';
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.37a583fd779e",{v0:(links.map(link=>{
    const target = state.tasks.find(t=>t.id===link.target && (!link.project || link.project===activeProject));
    const url = new URL(location.href); url.hash = 'tasks/' + encodeURIComponent(link.target);
    if (link.project) url.searchParams.set('project',link.project);
    return `<a href="${escape(url.href)}">${escape(relationNames[link.type] || link.type)}: ${escape(target?.title || link.title || link.target)}${link.project && link.project!==activeProject ? ' · '+escape(link.project) : ''}</a>`;
  }).join(''))}) : `<section class="task-relations"><h2>Связи задач</h2><div class="relation-list">${links.map(link=>{
    const target = state.tasks.find(t=>t.id===link.target && (!link.project || link.project===activeProject));
    const url = new URL(location.href); url.hash = 'tasks/' + encodeURIComponent(link.target);
    if (link.project) url.searchParams.set('project',link.project);
    return `<a href="${escape(url.href)}">${escape(relationNames[link.type] || link.type)}: ${escape(target?.title || link.title || link.target)}${link.project && link.project!==activeProject ? ' · '+escape(link.project) : ''}</a>`;
  }).join('')}</div></section>`);
}
const linkRow = link => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.dc60222a34e1",{v0:(Object.entries(relationNames).map(([id,label]) => `<option value="${id}" ${link.type === id ? 'selected' : ''}>${label}</option>`).join('')),v1:(escape(link.target || '')),v2:(escape(link.project || '')),v3:(uiIcon('close'))}) : `<div class="editor-link-row" data-link-row><select aria-label="Тип связи" data-link-type>${Object.entries(relationNames).map(([id,label]) => `<option value="${id}" ${link.type === id ? 'selected' : ''}>${label}</option>`).join('')}</select><input aria-label="ID связанной задачи" data-link-target required value="${escape(link.target || '')}" list="editor-task-ids"><input aria-label="Проект связанной задачи" data-link-project value="${escape(link.project || '')}" placeholder="Текущий проект"><button class="icon-button" type="button" data-remove-row title="Удалить связь" aria-label="Удалить связь">${uiIcon('close')}</button></div>`);
async function editorRequest(path, body, project) {
  const url = new URL(path, location.origin); url.searchParams.set('project', project);
  const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw Object.assign(Error(result.error || (globalThis.HubI18n?.t?.("task-editor.9225d5afe8c2") ?? 'Не удалось сохранить изменения')), {status:response.status});
  return result;
}
const editorEqual = (left, right) => {
  const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])) : value;
  return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
};
function editorDefaults(value, stageMode) {
  const base = {title:value.title || '', summary:value.summary || '', status:value.status || 'planned'};
  if (stageMode) return {...base,evidence:value.evidence || [],done:value.done || [],remaining:value.remaining || [],dependsOn:value.dependsOn || []};
  const estimate = {confidence:value.estimate?.confidence || '',note:value.estimate?.note || ''};
  for (const key of ['percentLow','percentHigh','hoursLow','hoursHigh']) if (value.estimate?.[key] != null) estimate[key] = value.estimate[key];
  return {...base,sources:value.sources || [],scope:value.scope || [],acceptance:value.acceptance || [],deferred:value.deferred || [],type:value.type || 'task',priority:value.priority || null,parentTask:value.parentTask || null,weight:value.weight ?? null,links:value.links || [],estimate};
}
async function saveEditorPatch(path, body, project, original) {
  try { return await editorRequest(path,body,project); }
  catch (error) {
    // Only a definite revision conflict is safe to retry. A lost response may
    // already have committed the write and must not generate a duplicate.
    if (error.status !== 409 || !body.patch) throw error;
    const url = new URL('/api/state',location.origin); url.searchParams.set('project',project);
    const response = await fetch(url,{cache:'no-store'});
    if (!response.ok) throw error;
    const latest = await response.json(), task = latest.tasks.find(item=>item.id===body.task);
    const current = body.stage ? task?.stages.find(item=>item.id===body.stage) : task;
    if (!current || Object.keys(body.patch).some(key=>!editorEqual(current[key],original[key]))) {
      throw Error((globalThis.HubI18n?.t?.("task-editor.0491c5c90e80") ?? 'Изменяемые поля уже обновлены другим участником. Черновик сохранён в форме; сверьте его с актуальными данными.'));
    }
    return editorRequest(path,{...body,expected:latest.revision},project);
  }
}
function openTaskEditor(taskId, stageId, stageMode = false) {
  if (taskEditor.open) return;
  const generation = ++taskEditorGeneration;
  const task = state.tasks.find(t => t.id === taskId);
  const stage = stageMode && task?.stages.find(s => s.id === stageId);
  const value = (stageMode ? stage : task) || {};
  const baseline = editorDefaults(value,stageMode);
  const originalSources = value[stageMode ? 'evidence' : 'sources'] || [];
  const originalLinks = task?.links || [];
  const expected = state.revision, project = activeProject;
  const ownsOpening = () => generation === taskEditorGeneration && taskEditor.open && activeProject === project;
  const heading = stageMode ? (stage ? (globalThis.HubI18n?.t?.("task-editor.49bdb952ae6a") ?? 'Редактировать этап') : (globalThis.HubI18n?.t?.("task-editor.a5422c3ac740") ?? 'Добавить этап')) : (task ? (globalThis.HubI18n?.t?.("task-editor.7910256282a4") ?? 'Редактировать задачу') : (globalThis.HubI18n?.t?.("task-editor.c759b93d6794") ?? 'Создать задачу'));
  taskEditor.setAttribute('aria-label', heading);
  const statuses = Object.entries(labels).filter(([id]) => ['planned','active','queued','blocked','done','cancelled'].includes(id));
  const estimateValue = task?.estimate || {};
  taskEditor.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.84a0629361d5",{v0:(heading),v1:(uiIcon('close')),v2:(editField('title',(globalThis.HubI18n?.t?.("task-editor.0918b4ba9268") ?? 'Название'),value.title)),v3:(editField('summary',(globalThis.HubI18n?.t?.("task-editor.b3680f2cba5f") ?? 'Описание'),value.summary,'textarea')),v4:(editSelect('status',(globalThis.HubI18n?.t?.("task-editor.225077c6d479") ?? 'Статус'), stageMode ? statuses : statuses.filter(([id]) => !['done'].includes(id) || value.status === id),value.status || 'planned')),v5:(!stageMode ? editSelect('type',(globalThis.HubI18n?.t?.("task-editor.d4a6795c199f") ?? 'Тип'),[['task','Task'],['bug','Bug'],['epic','Epic']],task?.type || 'task') + editSelect('priority',(globalThis.HubI18n?.t?.("task-editor.0e5ac36d3f46") ?? 'Приоритет'),[['',(globalThis.HubI18n?.t?.("task-editor.a402b3d034fb") ?? 'Не задан')],['blocker','Blocker'],['critical','Critical'],['major','Major'],['minor','Minor'],['trivial','Trivial']],task?.priority) + editSelect('parentTask',(globalThis.HubI18n?.t?.("task-editor.757b4e4eafa9") ?? 'Родитель'),[['',(globalThis.HubI18n?.t?.("task-editor.f45edf006851") ?? 'Проект')],...state.tasks.filter(t=>t.id!==taskId).map(t=>[t.id,t.title])],task?.parentTask) + editField('weight',(globalThis.HubI18n?.t?.("task-editor.54f9272ea6c7") ?? 'Вес'),task?.weight ?? '', 'number') : ''),v6:(stageMode ? editField('done',(globalThis.HubI18n?.t?.("task-editor.e078c61c3e49") ?? 'Реализовано'), (stage?.done || []).join('\n'),'textarea') + editField('remaining',(globalThis.HubI18n?.t?.("task-editor.a70b093aeac4") ?? 'До завершения'),(stage?.remaining || []).join('\n'),'textarea') + (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.dfb54a72a0bd",{v0:(task.stages.filter(s=>s.id!==stageId).map(s=>`<label class="editor-check"><input type="checkbox" name="dependsOn" value="${escape(s.id)}" ${(stage?.dependsOn||[]).includes(s.id)?'checked':''}>${escape(s.title)}</label>`).join(''))}) : `<fieldset><legend>Зависимости</legend>${task.stages.filter(s=>s.id!==stageId).map(s=>`<label class="editor-check"><input type="checkbox" name="dependsOn" value="${escape(s.id)}" ${(stage?.dependsOn||[]).includes(s.id)?'checked':''}>${escape(s.title)}</label>`).join('')}</fieldset>`) : ['scope','acceptance','deferred'].map((key,i)=>editField(key,[(globalThis.HubI18n?.t?.("task-editor.808c04fe8a46") ?? 'Объём'),(globalThis.HubI18n?.t?.("task-editor.f2e1315d11b6") ?? 'Критерии приёмки'),(globalThis.HubI18n?.t?.("task-editor.5c47a3132778") ?? 'Отложено')][i],(task?.[key] || []).join('\n'),'textarea')).join('')),v7:(stageMode ? (globalThis.HubI18n?.t?.("task-editor.64be6f12a479") ?? 'Доказательства этапа') : (globalThis.HubI18n?.t?.("task-editor.7dc4dce82a5d") ?? 'Источники задачи')),v8:(originalSources.map(sourceRow).join('')),v9:(uiIcon('plus')),v10:(!stageMode ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.8c40e748bc44",{v0:(state.tasks.filter(t=>t.id!==taskId).map(t=>`<option value="${escape(t.id)}">${escape(t.title)}</option>`).join('')),v1:(originalLinks.map(linkRow).join('')),v2:(uiIcon('plus')),v3:(editField('percentLow',(globalThis.HubI18n?.t?.("task-editor.191e582cc7b3") ?? 'Готовность от, %'),estimateValue.percentLow ?? '', 'number')),v4:(editField('percentHigh',(globalThis.HubI18n?.t?.("task-editor.16b15ae023c0") ?? 'Готовность до, %'),estimateValue.percentHigh ?? '', 'number')),v5:(editField('hoursLow',(globalThis.HubI18n?.t?.("task-editor.659b1867b759") ?? 'Осталось от, ч'),estimateValue.hoursLow ?? '', 'number')),v6:(editField('hoursHigh',(globalThis.HubI18n?.t?.("task-editor.4cbb84f93d9a") ?? 'Осталось до, ч'),estimateValue.hoursHigh ?? '', 'number')),v7:(editField('confidence',(globalThis.HubI18n?.t?.("task-editor.5fdfd02a080e") ?? 'Уверенность'),estimateValue.confidence)),v8:(editField('note',(globalThis.HubI18n?.t?.("task-editor.e39bc7fb376c") ?? 'Обоснование'),estimateValue.note,'textarea'))}) : `<fieldset><legend>Связи</legend><datalist id="editor-task-ids">${state.tasks.filter(t=>t.id!==taskId).map(t=>`<option value="${escape(t.id)}">${escape(t.title)}</option>`).join('')}</datalist><div data-link-rows>${originalLinks.map(linkRow).join('')}</div><button class="icon-button" type="button" data-add-link title="Добавить связь" aria-label="Добавить связь">${uiIcon('plus')}</button></fieldset><fieldset><legend>Оценка</legend><div class="editor-grid">${editField('percentLow',(globalThis.HubI18n?.t?.("task-editor.191e582cc7b3") ?? 'Готовность от, %'),estimateValue.percentLow ?? '', 'number')}${editField('percentHigh',(globalThis.HubI18n?.t?.("task-editor.16b15ae023c0") ?? 'Готовность до, %'),estimateValue.percentHigh ?? '', 'number')}${editField('hoursLow',(globalThis.HubI18n?.t?.("task-editor.659b1867b759") ?? 'Осталось от, ч'),estimateValue.hoursLow ?? '', 'number')}${editField('hoursHigh',(globalThis.HubI18n?.t?.("task-editor.4cbb84f93d9a") ?? 'Осталось до, ч'),estimateValue.hoursHigh ?? '', 'number')}</div>${editField('confidence',(globalThis.HubI18n?.t?.("task-editor.5fdfd02a080e") ?? 'Уверенность'),estimateValue.confidence)}${editField('note',(globalThis.HubI18n?.t?.("task-editor.e39bc7fb376c") ?? 'Обоснование'),estimateValue.note,'textarea')}</fieldset>`) : ''),v11:(uiIcon('refresh')),v12:(uiIcon('close')),v13:(uiIcon('save'))}) : `<form><header><h2>${heading}</h2><button class="icon-button" type="button" data-editor-close title="Закрыть" aria-label="Закрыть">${uiIcon('close')}</button></header><div class="editor-fields">${editField('title',(globalThis.HubI18n?.t?.("task-editor.0918b4ba9268") ?? 'Название'),value.title)}${editField('summary',(globalThis.HubI18n?.t?.("task-editor.b3680f2cba5f") ?? 'Описание'),value.summary,'textarea')}<div class="editor-grid">${editSelect('status',(globalThis.HubI18n?.t?.("task-editor.225077c6d479") ?? 'Статус'), stageMode ? statuses : statuses.filter(([id]) => !['done'].includes(id) || value.status === id),value.status || 'planned')}${!stageMode ? editSelect('type',(globalThis.HubI18n?.t?.("task-editor.d4a6795c199f") ?? 'Тип'),[['task','Task'],['bug','Bug'],['epic','Epic']],task?.type || 'task') + editSelect('priority',(globalThis.HubI18n?.t?.("task-editor.0e5ac36d3f46") ?? 'Приоритет'),[['',(globalThis.HubI18n?.t?.("task-editor.a402b3d034fb") ?? 'Не задан')],['blocker','Blocker'],['critical','Critical'],['major','Major'],['minor','Minor'],['trivial','Trivial']],task?.priority) + editSelect('parentTask',(globalThis.HubI18n?.t?.("task-editor.757b4e4eafa9") ?? 'Родитель'),[['',(globalThis.HubI18n?.t?.("task-editor.f45edf006851") ?? 'Проект')],...state.tasks.filter(t=>t.id!==taskId).map(t=>[t.id,t.title])],task?.parentTask) + editField('weight',(globalThis.HubI18n?.t?.("task-editor.54f9272ea6c7") ?? 'Вес'),task?.weight ?? '', 'number') : ''}</div>
  ${stageMode ? editField('done',(globalThis.HubI18n?.t?.("task-editor.e078c61c3e49") ?? 'Реализовано'), (stage?.done || []).join('\n'),'textarea') + editField('remaining',(globalThis.HubI18n?.t?.("task-editor.a70b093aeac4") ?? 'До завершения'),(stage?.remaining || []).join('\n'),'textarea') + (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.dfb54a72a0bd",{v0:(task.stages.filter(s=>s.id!==stageId).map(s=>`<label class="editor-check"><input type="checkbox" name="dependsOn" value="${escape(s.id)}" ${(stage?.dependsOn||[]).includes(s.id)?'checked':''}>${escape(s.title)}</label>`).join(''))}) : `<fieldset><legend>Зависимости</legend>${task.stages.filter(s=>s.id!==stageId).map(s=>`<label class="editor-check"><input type="checkbox" name="dependsOn" value="${escape(s.id)}" ${(stage?.dependsOn||[]).includes(s.id)?'checked':''}>${escape(s.title)}</label>`).join('')}</fieldset>`) : ['scope','acceptance','deferred'].map((key,i)=>editField(key,[(globalThis.HubI18n?.t?.("task-editor.808c04fe8a46") ?? 'Объём'),(globalThis.HubI18n?.t?.("task-editor.f2e1315d11b6") ?? 'Критерии приёмки'),(globalThis.HubI18n?.t?.("task-editor.5c47a3132778") ?? 'Отложено')][i],(task?.[key] || []).join('\n'),'textarea')).join('')}
  <fieldset data-sources><legend>${stageMode ? (globalThis.HubI18n?.t?.("task-editor.64be6f12a479") ?? 'Доказательства этапа') : (globalThis.HubI18n?.t?.("task-editor.7dc4dce82a5d") ?? 'Источники задачи')}</legend><div data-source-rows>${originalSources.map(sourceRow).join('')}</div><button class="icon-button" type="button" data-add-source title="Добавить источник" aria-label="Добавить источник">${uiIcon('plus')}</button></fieldset>
  ${!stageMode ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.8c40e748bc44",{v0:(state.tasks.filter(t=>t.id!==taskId).map(t=>`<option value="${escape(t.id)}">${escape(t.title)}</option>`).join('')),v1:(originalLinks.map(linkRow).join('')),v2:(uiIcon('plus')),v3:(editField('percentLow',(globalThis.HubI18n?.t?.("task-editor.191e582cc7b3") ?? 'Готовность от, %'),estimateValue.percentLow ?? '', 'number')),v4:(editField('percentHigh',(globalThis.HubI18n?.t?.("task-editor.16b15ae023c0") ?? 'Готовность до, %'),estimateValue.percentHigh ?? '', 'number')),v5:(editField('hoursLow',(globalThis.HubI18n?.t?.("task-editor.659b1867b759") ?? 'Осталось от, ч'),estimateValue.hoursLow ?? '', 'number')),v6:(editField('hoursHigh',(globalThis.HubI18n?.t?.("task-editor.4cbb84f93d9a") ?? 'Осталось до, ч'),estimateValue.hoursHigh ?? '', 'number')),v7:(editField('confidence',(globalThis.HubI18n?.t?.("task-editor.5fdfd02a080e") ?? 'Уверенность'),estimateValue.confidence)),v8:(editField('note',(globalThis.HubI18n?.t?.("task-editor.e39bc7fb376c") ?? 'Обоснование'),estimateValue.note,'textarea'))}) : `<fieldset><legend>Связи</legend><datalist id="editor-task-ids">${state.tasks.filter(t=>t.id!==taskId).map(t=>`<option value="${escape(t.id)}">${escape(t.title)}</option>`).join('')}</datalist><div data-link-rows>${originalLinks.map(linkRow).join('')}</div><button class="icon-button" type="button" data-add-link title="Добавить связь" aria-label="Добавить связь">${uiIcon('plus')}</button></fieldset><fieldset><legend>Оценка</legend><div class="editor-grid">${editField('percentLow',(globalThis.HubI18n?.t?.("task-editor.191e582cc7b3") ?? 'Готовность от, %'),estimateValue.percentLow ?? '', 'number')}${editField('percentHigh',(globalThis.HubI18n?.t?.("task-editor.16b15ae023c0") ?? 'Готовность до, %'),estimateValue.percentHigh ?? '', 'number')}${editField('hoursLow',(globalThis.HubI18n?.t?.("task-editor.659b1867b759") ?? 'Осталось от, ч'),estimateValue.hoursLow ?? '', 'number')}${editField('hoursHigh',(globalThis.HubI18n?.t?.("task-editor.4cbb84f93d9a") ?? 'Осталось до, ч'),estimateValue.hoursHigh ?? '', 'number')}</div>${editField('confidence',(globalThis.HubI18n?.t?.("task-editor.5fdfd02a080e") ?? 'Уверенность'),estimateValue.confidence)}${editField('note',(globalThis.HubI18n?.t?.("task-editor.e39bc7fb376c") ?? 'Обоснование'),estimateValue.note,'textarea')}</fieldset>`) : ''}</div><p class="editor-error" role="alert" hidden></p><footer><button class="icon-button" type="button" data-editor-reload title="Загрузить актуальные данные" aria-label="Загрузить актуальное">${uiIcon('refresh')}</button><button class="icon-button" type="button" data-editor-close title="Отмена" aria-label="Отмена">${uiIcon('close')}</button><button class="icon-button" type="submit" title="Сохранить" aria-label="Сохранить">${uiIcon('save')}</button></footer></form>`);
  const imageUploads = typeof mountImageUploads === 'function' ? mountImageUploads(taskEditor, task, stageMode, project) : null;
  taskEditor.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    if (imageUploads?.busy()) return;
    const form = event.currentTarget, data = new FormData(form);
    const lines = name => String(data.get(name) || '').split('\n').map(x=>x.trim()).filter(Boolean);
    const patch = {title:String(data.get('title')).trim(),summary:String(data.get('summary') || ''),status:data.get('status')};
    patch[stageMode ? 'evidence' : 'sources'] = [...form.querySelectorAll('[data-source-row]')].map((row,i)=>({...JSON.parse(row.dataset.original || '{}'),label:row.querySelector('[data-source-label]').value.trim(),path:row.querySelector('[data-source-path]').value.trim()}));
    if (stageMode) Object.assign(patch,{done:lines('done'),remaining:lines('remaining'),dependsOn:data.getAll('dependsOn')});
    else {
      Object.assign(patch,{scope:lines('scope'),acceptance:lines('acceptance'),deferred:lines('deferred'),type:data.get('type'),priority:data.get('priority') || null,parentTask:data.get('parentTask') || null,weight:data.get('weight') === '' ? null : Number(data.get('weight'))});
      patch.links = [...form.querySelectorAll('[data-link-row]')].map(row=>{const link={type:row.querySelector('[data-link-type]').value,target:row.querySelector('[data-link-target]').value.trim()};const projectId=row.querySelector('[data-link-project]').value.trim();if(projectId)link.project=projectId;return link;});
      const estimate = {confidence:String(data.get('confidence') || ''),note:String(data.get('note') || '')};
      for (const key of ['percentLow','percentHigh','hoursLow','hoursHigh']) if (data.get(key) !== '') estimate[key] = Number(data.get(key));
      patch.estimate = estimate;
    }
    const submit = form.querySelector('[type=submit]'), error = form.querySelector('.editor-error');
    if (task && !stageMode || stageMode && stage) {
      for (const key of Object.keys(patch)) {
        if (editorEqual(patch[key],baseline[key])) delete patch[key];
      }
    }
    submit.disabled = true; error.hidden = true;
    imageUploads?.setSaving(true);
    try {
      if ((task && !stageMode || stage) && !Object.keys(patch).length) { taskEditor.close(); return; }
      const path = stageMode ? `/api/v1/stages/${stage ? 'update' : 'create'}` : `/api/v1/tasks/${task ? 'update' : 'create'}`;
      const body = stageMode ? (stage ? {task:taskId,stage:stageId,patch,expected} : {task:taskId,stage:patch,expected}) : (task ? {task:taskId,patch,expected} : {task:patch,expected});
      const result = body.patch ? await saveEditorPatch(path,body,project,value) : await editorRequest(path,body,project);
      if (!ownsOpening()) { if (activeProject === project) await refresh(); return; }
      taskEditor.close(); await refresh();
      if (generation !== taskEditorGeneration || activeProject !== project) return;
      if (result.createdTask) location.hash = taskLink({id:result.createdTask});
      else if (result.createdStage) location.hash = taskLink(task,result.createdStage);
    } catch (e) { if (ownsOpening()) { error.textContent=e.message; error.hidden=false; } }
    finally { if (generation === taskEditorGeneration) { submit.disabled=false; imageUploads?.setSaving(false); } }
  };
  taskEditor.querySelector('[data-editor-reload]').onclick = async () => {
    if (!confirm((globalThis.HubI18n?.t?.("task-editor.d8f00c9cbb5f") ?? 'Загрузить актуальные данные и заменить несохранённый черновик?'))) return;
    await refresh(); if (!ownsOpening()) return; taskEditor.close(); openTaskEditor(taskId,stageId,stageMode);
  };
  taskEditor.showModal();
}
taskEditor.addEventListener('click', event => {
  if(event.target.closest('[data-editor-close]')) taskEditor.close();
  if(event.target.closest('[data-add-source]')) taskEditor.querySelector('[data-source-rows]').insertAdjacentHTML('beforeend',sourceRow({}));
  if(event.target.closest('[data-add-link]')) taskEditor.querySelector('[data-link-rows]').insertAdjacentHTML('beforeend',linkRow({}));
  event.target.closest('[data-remove-row]')?.parentElement.remove();
});
document.addEventListener('click', event => {
  const edit = event.target.closest('[data-edit-task]'), stage = event.target.closest('[data-edit-stage]');
  if(edit) openTaskEditor(edit.dataset.editTask);
  if(stage) openTaskEditor(stage.dataset.taskId,stage.dataset.editStage,true);
  if(event.target.closest('[data-create-task]')) openTaskEditor();
});
const stageOperationDialog = document.createElement('dialog');
stageOperationDialog.className = 'task-editor';
document.body.append(stageOperationDialog);
function archivedStages(task) {
  const archived = (task.archivedStages || []).filter(s=>['deleted','unlinked'].includes(s.lifecycle?.action) && !s.lifecycle?.restoredAt);
  if (!archived.length) return '';
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.d0bac5ddfa12",{v0:(escape(task.id)),v1:(archived.length),v2:(archived.map(s=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.e5aa7d194937",{v0:(escape(s.title)),v1:(escape(task.id)),v2:(escape(s.id)),v3:(uiIcon('reopen'))}) : `<div class="section-head"><span>${escape(s.title)}</span><button class="icon-button" data-stage-operation="restore" data-task-id="${escape(task.id)}" data-stage-id="${escape(s.id)}" title="Восстановить этап" aria-label="Восстановить этап">${uiIcon('reopen')}</button></div>`)).join(''))}) : `<details class="task-sources" data-key="archived-${escape(task.id)}"><summary>Удалённые и отвязанные этапы (${archived.length})</summary>${archived.map(s=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.e5aa7d194937",{v0:(escape(s.title)),v1:(escape(task.id)),v2:(escape(s.id)),v3:(uiIcon('reopen'))}) : `<div class="section-head"><span>${escape(s.title)}</span><button class="icon-button" data-stage-operation="restore" data-task-id="${escape(task.id)}" data-stage-id="${escape(s.id)}" title="Восстановить этап" aria-label="Восстановить этап">${uiIcon('reopen')}</button></div>`)).join('')}</details>`);
}
function openStageOperation(taskId, stageId, operation) {
  const task = state.tasks.find(t=>t.id===taskId);
  const stage = task?.stages.find(s=>s.id===stageId) || [...(task?.archivedStages || [])].reverse().find(s=>s.id===stageId);
  if (!stage || stageOperationDialog.open) return;
  const expected=state.revision, project=activeProject;
  const heading = {transfer:(globalThis.HubI18n?.t?.("task-editor.af445a2529bf") ?? 'Перенести этап'),unlink:(globalThis.HubI18n?.t?.("task-editor.28eb49abfd00") ?? 'Отвязать этап'),delete:(globalThis.HubI18n?.t?.("task-editor.d9dc2e9ec238") ?? 'Удалить этап'),restore:(globalThis.HubI18n?.t?.("task-editor.082b457a5d09") ?? 'Восстановить этап')}[operation];
  stageOperationDialog.setAttribute('aria-label',heading);
  stageOperationDialog.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.ee0d0cb307c3",{v0:(heading),v1:(uiIcon('close')),v2:(escape(stage.title)),v3:(escape(task.title)),v4:(operation==='transfer' ? editSelect('target',(globalThis.HubI18n?.t?.("task-editor.3d5e38a2e21b") ?? 'Целевая задача'),state.tasks.filter(t=>t.id!==taskId && !['done','cancelled'].includes(t.status)).map(t=>[t.id,t.title]),'') + (globalThis.HubI18n?.t?.("task-editor.51a532fee76c") ?? '<label class="editor-check"><input type="checkbox" name="includeDependencies">Перенести всю связанную группу зависимостей</label>') : `<p>${operation==='restore' ? (globalThis.HubI18n?.t?.("task-editor.d9c9b8aa6dcf") ?? 'Этап вернётся в текущий план.') : (globalThis.HubI18n?.t?.("task-editor.0423c010b948") ?? 'Этап будет исключён из текущего плана. История и доказательства сохранятся; этап можно восстановить.')}</p>`),v5:(operation!=='restore' ? editField('reason',(globalThis.HubI18n?.t?.("task-editor.442e7ad54796") ?? 'Причина'),'','textarea') : ''),v6:(uiIcon('close')),v7:(heading),v8:(heading),v9:(uiIcon(operation==='transfer' ? 'transfer' : operation==='restore' ? 'reopen' : operation==='delete' ? 'delete' : 'unlink'))}) : `<form><header><h2>${heading}</h2><button class="icon-button" type="button" data-operation-close title="Закрыть" aria-label="Закрыть">${uiIcon('close')}</button></header><div class="editor-fields"><strong>${escape(stage.title)}</strong><p class="caption">${escape(task.title)}</p>${operation==='transfer' ? editSelect('target',(globalThis.HubI18n?.t?.("task-editor.3d5e38a2e21b") ?? 'Целевая задача'),state.tasks.filter(t=>t.id!==taskId && !['done','cancelled'].includes(t.status)).map(t=>[t.id,t.title]),'') + (globalThis.HubI18n?.t?.("task-editor.51a532fee76c") ?? '<label class="editor-check"><input type="checkbox" name="includeDependencies">Перенести всю связанную группу зависимостей</label>') : `<p>${operation==='restore' ? (globalThis.HubI18n?.t?.("task-editor.d9c9b8aa6dcf") ?? 'Этап вернётся в текущий план.') : (globalThis.HubI18n?.t?.("task-editor.0423c010b948") ?? 'Этап будет исключён из текущего плана. История и доказательства сохранятся; этап можно восстановить.')}</p>`}${operation!=='restore' ? editField('reason',(globalThis.HubI18n?.t?.("task-editor.442e7ad54796") ?? 'Причина'),'','textarea') : ''}</div><p class="editor-error" role="alert" hidden></p><footer><button class="icon-button" type="button" data-operation-close title="Отмена" aria-label="Отмена">${uiIcon('close')}</button><button class="icon-button" type="submit" title="${heading}" aria-label="${heading}">${uiIcon(operation==='transfer' ? 'transfer' : operation==='restore' ? 'reopen' : operation==='delete' ? 'delete' : 'unlink')}</button></footer></form>`);
  stageOperationDialog.querySelector('form').onsubmit = async event => {
    event.preventDefault(); const form=event.currentTarget, data=new FormData(form), submit=form.querySelector('[type=submit]'), error=form.querySelector('.editor-error');
    const body={task:taskId,stage:stageId,expected};
    if(operation!=='restore')body.reason=String(data.get('reason')||'');
    if(operation==='transfer')body.target=data.get('target');
    if(operation==='transfer')body.includeDependencies=data.get('includeDependencies')==='on';
    submit.disabled=true; error.hidden=true;
    try { await editorRequest('/api/v1/stages/'+operation,body,project); stageOperationDialog.close(); await refresh(); }
    catch(e) {error.textContent=e.message;error.hidden=false;}
    finally {submit.disabled=false;}
  };
  const dependencyToggle = stageOperationDialog.querySelector('[name=includeDependencies]');
  if (dependencyToggle) {
    const selected = new Set([stageId]);
    let count;
    do {
      count = selected.size;
      for (const item of task.stages) {
        if (selected.has(item.id) || (item.dependsOn || []).some(id=>selected.has(id))) {
          selected.add(item.id); (item.dependsOn || []).forEach(id=>selected.add(id));
        }
      }
    } while (selected.size !== count);
    const preview = document.createElement('p'); preview.className='caption'; preview.hidden=true;
    preview.textContent = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("task-editor.5da81c850483",{v0:(selected.size)}) : `Этапов в группе: ${selected.size}. `) + task.stages.filter(s=>selected.has(s.id)).map(s=>s.title).join('; ');
    dependencyToggle.closest('label').after(preview);
    dependencyToggle.onchange=()=>{preview.hidden=!dependencyToggle.checked;};
  }
  stageOperationDialog.showModal();
}
stageOperationDialog.addEventListener('click', event=>{if(event.target.closest('[data-operation-close]'))stageOperationDialog.close();});
document.addEventListener('click', event=>{const b=event.target.closest('[data-stage-operation]');if(b)openStageOperation(b.dataset.taskId,b.dataset.stageId,b.dataset.stageOperation);});

globalThis.HubI18n?.onChange?.(()=>{Object.assign(relationNames,{'related':(globalThis.HubI18n?.t?.("task-editor.73c25b59c4b3") ?? 'Связана с'),'blocks':(globalThis.HubI18n?.t?.("task-editor.806bc5f8787d") ?? 'Блокирует'),'blocked-by':(globalThis.HubI18n?.t?.("task-editor.844c7f4197a7") ?? 'Зависит от'),'duplicates':(globalThis.HubI18n?.t?.("task-editor.ab91970691f9") ?? 'Дублирует'),'duplicated-by':(globalThis.HubI18n?.t?.("task-editor.1538ca66cb3e") ?? 'Дублируется задачей')});});
