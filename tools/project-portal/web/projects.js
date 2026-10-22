"use strict";

/* The project manager is deliberately independent of the project task view. */
(function (global) {
  const view = {
    root: null, envelope: null, loading: false, busy: false, error: '', catalogError: '', message: '', feedbackId:'',
    loaded: false, pollTimer: null, requestSequence: 0, drafts: new Map(), dirtyForms: new Set(), renameConflicts: new Set(), pendingMutation: null,
    pendingOperationId: null, pendingStatus: '', pendingDraftKey: null, detailId: '', reloadAfterLoad: false,
    terminalRequests: new Set(), terminalOperations: new Set(), operationRefreshRequested: false,
  };

  const fallbackText = {
    title: (globalThis.HubI18n?.t?.("projects.5029f02d0a94") ?? 'Проекты'), intro: (globalThis.HubI18n?.t?.("projects.4c171d1a6b7d") ?? 'Управляйте проектами Hub и при необходимости связывайте их с папкой исходного кода.'),
    add: (globalThis.HubI18n?.t?.("projects.a84d90bc78b3") ?? 'Добавить проект'), name: (globalThis.HubI18n?.t?.("projects.720a7014d17b") ?? 'Название проекта'), folder: (globalThis.HubI18n?.t?.("projects.e4c87de262c0") ?? 'Папка кода (необязательно)'),
    folderHelp: (globalThis.HubI18n?.t?.("projects.802588148bf9") ?? 'Укажите абсолютный путь, если проект связан с локальной рабочей папкой.'),
    save: (globalThis.HubI18n?.t?.("projects.49ed84ac6492") ?? 'Создать проект'), refresh: (globalThis.HubI18n?.t?.("projects.603e460bf59c") ?? 'Обновить'), empty: (globalThis.HubI18n?.t?.("projects.741d221b924c") ?? 'Проектов пока нет.'),
    loading: (globalThis.HubI18n?.t?.("projects.4767b9a38d5e") ?? 'Загрузка проектов…'), unavailable: (globalThis.HubI18n?.t?.("projects.9b0f38818a0a") ?? 'Не удалось загрузить проекты'),
    oldSchema: (globalThis.HubI18n?.t?.("projects.3dfbbddd5a77") ?? 'Управление отключено для этой версии каталога. Перенесите данные совместимым архивом, затем обновите каталог.'),
    rename: (globalThis.HubI18n?.t?.("projects.194306e20807") ?? 'Переименовать'), open: (globalThis.HubI18n?.t?.("projects.e4e6c1fa1cfc") ?? 'Открыть проект'), archive: (globalThis.HubI18n?.t?.("projects.1137508af8ff") ?? 'Архивировать'), unarchive: (globalThis.HubI18n?.t?.("projects.d314390d1ef9") ?? 'Вернуть из архива'),
    remove: (globalThis.HubI18n?.t?.("projects.be99b1361201") ?? 'Удалить'), recover: (globalThis.HubI18n?.t?.("projects.76f55a988f8a") ?? 'Восстановить'), deleted: (globalThis.HubI18n?.t?.("projects.0bfb4a497412") ?? 'Удалённые проекты'),
    archived: (globalThis.HubI18n?.t?.("projects.34886925697b") ?? 'В архиве'), active: (globalThis.HubI18n?.t?.("projects.a87a4b39c304") ?? 'Активен'), noFolder: (globalThis.HubI18n?.t?.("projects.200d4d17ae3e") ?? 'Папка кода не указана'),
    saved: (globalThis.HubI18n?.t?.("projects.4dd96a79b884") ?? 'Изменения сохранены.'), created: (globalThis.HubI18n?.t?.("projects.6be220f7d990") ?? 'Проект создан.'), invalidName: (globalThis.HubI18n?.t?.("projects.0c92833cda5f") ?? 'Введите название проекта.'),
    pending: (globalThis.HubI18n?.t?.("projects.e548e8f4d639") ?? 'Предыдущее изменение не подтверждено. Повторите его перед новым действием.'), repeat: (globalThis.HubI18n?.t?.("projects.f2cca80a5b4b") ?? 'Повторить последнее изменение'),
    conflict: (globalThis.HubI18n?.t?.("projects.49bfd3c3a0e3") ?? 'Проект изменён другим клиентом. Нажмите «Обновить», сравните значения и повторите сохранение.'),
    invalidFolder: (globalThis.HubI18n?.t?.("projects.5ffce33f9766") ?? 'Путь к папке должен быть абсолютным.'), retry: (globalThis.HubI18n?.t?.("projects.abc1ae6ffc4a") ?? 'Повторите действие.'),
  };
  function text(key, fallback, english = fallback) {
    const value = global.HubI18n?.locale === 'en' ? english : fallback;
    try { return global.HubI18n?.t?.(`projects.${key}`, value) || value; } catch (_) { return value; }
  }
  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }
  function requestId() {
    const raw = global.crypto?.randomUUID?.();
    if (raw) return raw.replace(/-/g, '');
    view.requestSequence += 1;
    return `${Date.now().toString(16)}${view.requestSequence.toString(16)}`.padStart(32, '0').slice(-32);
  }
  function connected(root = view.root) { return root && root.isConnected !== false; }
  function managementDisabled() { return view.envelope?.schemaVersion === 1; }
  function projectRows() { return Array.isArray(view.envelope?.projects) ? view.envelope.projects : []; }
  function statusText() { return view.error || view.catalogError || (global.backupStatus?.feedback ? global.backupStatus.feedback(view.feedbackId,view.message) : view.message) || ''; }
  function projectRoots(project) {
    return Array.isArray(project.roots) && project.roots.length ? project.roots : [text('noFolder', fallbackText.noFolder)];
  }
  function draft(key, defaults = {}) { return view.drafts.get(key) || defaults; }
  const mutationStorageKey = 'project-hub-project-mutation';
  function persistMutation() {
    try {
      if (!view.pendingMutation) {global.sessionStorage?.removeItem(mutationStorageKey); return;}
      global.sessionStorage?.setItem(mutationStorageKey, JSON.stringify({body:view.pendingMutation,
        operationId:view.pendingOperationId, status:view.pendingStatus, draftKey:view.pendingDraftKey,
        draft:view.drafts.get(view.pendingDraftKey)}));
    } catch (_) { /* Session persistence is optional. */ }
  }
  try {
    const saved = JSON.parse(global.sessionStorage?.getItem(mutationStorageKey) || 'null');
    if (saved?.body && ['create','update'].includes(saved.body.action) && /^[0-9a-f]{32}$/.test(saved.body.requestId)) {
      view.pendingMutation = saved.body; view.pendingOperationId = saved.operationId || null;
      view.pendingStatus = saved.operationId ? saved.status || 'running' : 'unknown';
      view.pendingDraftKey = saved.draftKey || null;
      if (saved.draft && view.pendingDraftKey) {view.drafts.set(view.pendingDraftKey,saved.draft); view.dirtyForms.add(view.pendingDraftKey);}
    }
  } catch (_) { /* Invalid saved state never starts a request. */ }
  function canRetryMutation() { return Boolean(view.pendingMutation && (!view.pendingOperationId || view.pendingStatus === 'unknown')); }
  function detailRouteId() {
    const parts = (global.location?.hash || '').replace(/^#/,'').split('/');
    if (parts[0] !== 'projects' || parts[1] !== 'projects' || parts[2] !== 'operation') return '';
    try {return decodeURIComponent(parts[3] || '');} catch (_) {return '';}
  }
  function mutationStatusControls() {
    const retry = canRetryMutation() ? ` <button type="button" class="projects-retry" data-project-action="retry" data-operation-retry="${esc(view.pendingMutation.requestId)}">${esc(text('repeat', fallbackText.repeat))}</button>` : '';
    const project = view.pendingMutation?.project;
    const href = `${project ? `?project=${encodeURIComponent(project)}` : global.location?.search || ''}#projects/projects/operation/${encodeURIComponent(view.pendingOperationId || '')}`;
    return retry + (view.pendingOperationId ? ` <a href="${esc(href)}">${esc(text('operationDetails', 'Подробнее об операции', 'Operation details'))}</a>` : '');
  }
  function formKey(form) { return form.dataset.projectForm === 'create' ? 'create' : `rename:${form.dataset.projectId}`; }
  function captureForm(form) {
    const key = formKey(form), value = {};
    for (const name of ['name', 'root']) value[name] = form.elements?.namedItem?.(name)?.value ?? '';
    if (form.dataset.projectRevision != null) value.revision = form.dataset.projectRevision;
    view.drafts.set(key, value); view.dirtyForms.add(key);
    if (key === view.pendingDraftKey) persistMutation();
  }
  function renameForm(project, disabled) {
    const values = draft(`rename:${project.id}`, {name: project.name || ''});
    return `<form class="projects-rename" data-project-form="rename" data-project-id="${esc(project.id)}" data-project-revision="${esc(values.revision ?? project.revision ?? '')}"><label><span>${esc(text('name', fallbackText.name))}</span><input name="name" value="${esc(values.name)}" required maxlength="240" ${disabled ? 'disabled' : ''}></label><button class="primary" type="submit" ${disabled ? 'disabled' : ''}>${esc(text('rename', fallbackText.rename))}</button></form>`;
  }
  let selectedTab = 'projects', modal = null, modalTab = 'general', opener = null;
  function modalContent() {
    if (!modal) return '';
    const disabled = managementDisabled() || view.busy || !!view.pendingMutation;
    const project = projectRows().find(row => row.id === modal.project);
    const heading = modal.kind === 'create' ? text('add', fallbackText.add) : project?.name || '';
    let body = '';
    if (modal.kind === 'create') {
      const values = draft('create', {name:'', root:''});
      body = `<form class="projects-create" data-project-form="create"><div class="projects-form-grid"><label><span>${esc(text('name', fallbackText.name))}</span><input name="name" value="${esc(values.name)}" maxlength="240" required autofocus ${disabled ? 'disabled' : ''}></label><label><span>${esc(text('folder', fallbackText.folder))}</span><div class="hub-folder-field"><input id="project-create-folder" name="root" value="${esc(values.root)}" ${disabled ? 'disabled' : ''}>${global.HubLocalFiles?.chooser('workspace','#project-create-folder',disabled) || ''}</div><small>${esc(text('folderHelp', fallbackText.folderHelp))}</small></label></div><footer><button class="primary" type="submit" data-hub-mutation ${disabled ? 'disabled' : ''}>${esc(text('save', fallbackText.save))}</button><button type="button" data-project-action="close">${esc(text('cancel', 'Отмена'))}</button></footer></form>`;
    } else if (modalTab === 'code' && project) body = global.HubWorkspacesUI?.card(project, {expanded:true}) || '';
    else if (project) body = `<p class="caption">${esc(text('generalHelp', 'Название используется в Hub. Изменения сохраняют историю проекта.'))}</p>${renameForm(project, disabled)}<dl class="projects-details"><dt>${esc(text('identifier', 'Идентификатор'))}</dt><dd><code>${esc(project.id)}</code></dd><dt>${esc(text('state', 'Состояние'))}</dt><dd>${esc(project.deleted ? text('deleted', fallbackText.deleted) : project.archived ? text('archived', fallbackText.archived) : text('active', fallbackText.active))}</dd></dl>`;
    const tabs = modal.kind === 'configure' ? `<nav class="projects-tabs" aria-label="${esc(text('projectSettings', 'Настройки проекта'))}">${['general','code'].map(tab => `<button type="button" data-project-dialog-tab="${tab}" aria-pressed="${modalTab === tab}">${esc(text(tab, ({general:'Общие',code:'Папки кода'})[tab]))}</button>`).join('')}</nav>` : '';
    const currentDialog = view.root?.querySelector?.('#project-editor');
    return `<dialog class="projects-dialog" id="project-editor" aria-labelledby="project-editor-title" ${currentDialog?.isConnected && currentDialog.open ? 'open' : ''}><header><div><small>${esc(text('projectSettings', 'Настройки проекта'))}</small><h2 id="project-editor-title">${esc(heading)}</h2></div><button type="button" data-project-action="close" aria-label="${esc(text('close', 'Закрыть'))}">×</button></header>${tabs}<div class="projects-dialog-body" data-scroll-key="project-editor-body">${body}<p class="projects-status" role="status">${esc(statusText())}${mutationStatusControls()}</p></div></dialog>`;
  }
  function projectCard(project) {
    const deleted = Boolean(project.deleted), archived = Boolean(project.archived);
    const disabled = managementDisabled() || view.busy || view.pendingMutation;
    const action = (name, label) => `<button type="button" class="projects-action" data-hub-mutation data-project-action="${name}" data-project-id="${esc(project.id)}" ${disabled ? 'disabled' : ''}>${esc(label)}</button>`;
    return `<article class="projects-card${deleted ? ' is-deleted' : ''}" data-project-id="${esc(project.id)}" data-project-deleted="${deleted ? 'true' : 'false'}">
      <div class="projects-card-heading"><div><h3>${esc(project.name || project.id)}</h3><span class="projects-badge">${esc(deleted ? text('deleted', fallbackText.deleted) : archived ? text('archived', fallbackText.archived) : text('active', fallbackText.active))}</span></div><details class="projects-menu"><summary aria-label="${esc(text('actions', 'Действия проекта'))}">⋯</summary><div>${archived ? action('unarchive', text('unarchive', fallbackText.unarchive)) : action('archive', text('archive', fallbackText.archive))}${deleted ? action('recover', text('recover', fallbackText.recover)) : action('delete', text('remove', fallbackText.remove))}</div></details></div>
      <p class="projects-meta">${esc(text('code', 'Папки кода'))} · ${esc(String(project.roots?.length || 0))}</p><ul class="projects-roots">${projectRoots(project).map(root => `<li title="${esc(root)}">${project.roots?.includes(root) && global.HubLocalFiles ? global.HubLocalFiles.pathLink(root,'workspace',{project:project.id}) : esc(root)}</li>`).join('')}</ul>
      <div class="projects-card-footer">${deleted ? action('recover', text('recover', fallbackText.recover)) : `<a class="projects-open" href="?project=${encodeURIComponent(project.id)}#overview">${esc(text('open', fallbackText.open))}</a><button type="button" data-project-action="configure" data-project-id="${esc(project.id)}">${esc(text('configure', 'Настроить'))}</button>`}</div>
    </article>`;
  }
  function content() {
    const rows = projectRows(), disabled = managementDisabled() || view.busy || view.pendingMutation;
    const active = rows.filter(project => !project.deleted), deleted = rows.filter(project => project.deleted);
    const cards = active.length ? active.map(projectCard).join('') : `<p class="projects-empty">${esc(text('empty', fallbackText.empty))}</p>`;
    const deletedCards = deleted.length ? `<section class="projects-deleted"><h3>${esc(text('deleted', fallbackText.deleted))}</h3>${deleted.map(projectCard).join('')}</section>` : '';
    return `<div class="projects-section-head"><p class="caption">${esc(text('intro', fallbackText.intro))}</p><div class="projects-actions"><button type="button" data-project-action="refresh" ${view.loading ? 'disabled' : ''}>${esc(text('refresh', fallbackText.refresh))}</button><button type="button" class="primary" data-project-action="create" ${disabled ? 'disabled' : ''}>${esc(text('add', fallbackText.add))}</button></div></div>
      ${managementDisabled() ? `<aside class="projects-notice" role="note"><strong>${esc(text('upgradeNeeded', 'Нужен совместимый формат данных'))}</strong><p>${esc(text('oldSchemaImportHelp', 'Управление отключено для прежнего формата данных. В разделе «Данные Hub» проверьте источник и импортируйте его в рабочую папку. Преобразование выполняется во временной копии; исходные данные сохранятся.'))}</p><button type="button" data-project-tab="data">${esc(text('data', 'Данные Hub'))}</button></aside>` : ''}
      <p class="projects-status" role="status" aria-live="polite">${esc(view.loading && !view.envelope ? text('loading', fallbackText.loading) : statusText())}${mutationStatusControls()}</p>
      ${detailRouteId() ? global.backupStatus?.details(detailRouteId()) || '' : ''}
      <section class="projects-list"><div class="projects-card-grid">${cards}</div></section>${deletedCards}${global.backupStatus?.history?.('projects') || ''}${modalContent()}`;
  }
  function render(root = view.root, {background = false} = {}) {
    if (!connected(root)) return;
    if (background && view.dirtyForms.size) return;
    if (background && global.document?.activeElement && root.contains?.(global.document.activeElement)) return;
    if (global.HubLiveUI) global.HubLiveUI.patch(root, content(), {preserveInputs:false});
    else root.innerHTML = content();
    global.HubWorkspacesUI?.afterRender(root);
    global.HubLocalFiles?.bind(root);global.backupStatus?.afterRender();
    const dialog = root.querySelector?.('#project-editor');
    if (modal && dialog && !dialog.open) {
      dialog.showModal?.();
      if (!dialog.__projectsDialogBound) {dialog.__projectsDialogBound = true; dialog.addEventListener('cancel', event => {event.preventDefault(); closeModal();});}
    }
  }
  function closeModal() {
    if (view.busy) return;
    view.root?.querySelector?.('#project-editor')?.close?.();
    modal = null; render(); opener?.focus?.({preventScroll:true});
  }
  function switchTab(tab, root = global.document?.querySelector?.('#projects-admin')) {
    if (!root || !['projects','data','backups'].includes(tab)) return;
    selectedTab = tab;
    root.querySelectorAll?.('[data-project-pane]').forEach(node => {node.hidden = node.dataset.projectPane !== tab;});
    root.querySelectorAll?.('[data-project-tab]').forEach(node => {if (node.getAttribute?.('role') === 'tab') {node.setAttribute('aria-selected', String(node.dataset.projectTab === tab));node.tabIndex = node.dataset.projectTab === tab ? 0 : -1;}});
  }
  async function jsonResponse(response) {
    let body = {};
    try { body = await response.json(); } catch (_) { body = {}; }
    if (!response.ok) {
      const error = Error(body.code === 'project_revision_conflict' ? text('conflict', fallbackText.conflict) : body.error || `${response.status || ''} ${text('retry', fallbackText.retry)}`.trim());
      error.code = body.code; error.status = response.status; throw error;
    }
    return body;
  }
  async function loadCatalog({silent = false, rebaseConflicts = false, refreshAfterCurrent = false} = {}) {
    if (view.loading) {if (refreshAfterCurrent) view.reloadAfterLoad = true; return;}
    view.loading = true; if (!silent) view.error = ''; if (!silent) render();
    try {
      const response = await fetch('/api/v1/projects?includeDeleted=true', {cache: 'no-store'});
      const body = await jsonResponse(response);
      if (!Array.isArray(body.projects) || body.schemaVersion == null) throw Error((globalThis.HubI18n?.t?.("projects.f0cf5da54e37") ?? 'Некорректный каталог проектов'));
      view.envelope = body; view.loaded = true; view.catalogError = '';
      if (rebaseConflicts) for (const id of view.renameConflicts) {
        const project = body.projects.find(row => row.id === id), value = view.drafts.get(`rename:${id}`);
        if (project && value) value.revision = project.revision;
        view.renameConflicts.delete(id);
      }
    } catch (error) { view.catalogError = (globalThis.HubI18n?.error?.(error) ?? error.message) || text('unavailable', fallbackText.unavailable); }
    finally {
      view.loading = false; render(view.root, {background: silent});
      if (view.reloadAfterLoad) {view.reloadAfterLoad = false; void loadCatalog({silent:true});}
    }
  }
  function validProject(project, body) {
    return project && typeof project.id === 'string' && project.id.trim() &&
      typeof project.name === 'string' && project.name.trim() && Array.isArray(project.roots) &&
      project.roots.every(root => typeof root === 'string') && Number.isSafeInteger(project.revision) &&
      project.revision >= 1 && (body.action !== 'update' || project.id === body.project);
  }
  function clearMutation() {
    view.pendingMutation = null; view.pendingOperationId = null; view.pendingStatus = ''; view.pendingDraftKey = null;
    persistMutation();
  }
  async function finishMutation(row) {
    const body = view.pendingMutation;
    if (!body || row.requestId !== body.requestId || view.terminalRequests.has(body.requestId)) return;
    const project = row.result?.project, succeeded = row.status === 'succeeded';
    if (succeeded && !validProject(project, body)) {
      view.pendingStatus = 'unknown'; persistMutation();
      view.error = text('57b13a4ae07c', 'Сервер не вернул проект', 'The server did not return the project'); render(); return;
    }
    view.terminalRequests.add(body.requestId); view.terminalOperations.add(row.id);
    const draftKey = view.pendingDraftKey;
    clearMutation();view.feedbackId=row.id;
    if (succeeded) {
      if (draftKey) {view.drafts.delete(draftKey); view.dirtyForms.delete(draftKey);}
      view.error = ''; view.message = body.action === 'create' ? text('created', fallbackText.created) : text('saved', fallbackText.saved);
      if (body.action === 'create' && modal?.kind === 'create') modal = {kind:'configure',project:project.id};
      try { if (typeof global.CustomEvent === 'function') global.dispatchEvent?.(new global.CustomEvent('hub-projects-changed', {detail:{project,action:body.action}})); } catch (_) { /* Optional browser event API. */ }
    } else {
      const conflict = row.errorBody?.code === 'project_revision_conflict';
      if (conflict && body.patch?.name != null) view.renameConflicts.add(body.project);
      view.message = ''; view.error = conflict ? text('conflict', fallbackText.conflict) :
        (typeof row.error === 'string' ? row.error : row.error?.message) || text('retry', fallbackText.retry);
    }
    render(); await loadCatalog({silent:true,refreshAfterCurrent:true}); return succeeded ? project : undefined;
  }
  function handleOperations(event) {
    const rows = event?.detail?.operations || global.backupStatus?.operations?.() || [];
    const body = view.pendingMutation;
    const row = body && rows.find(item => item.requestId === body.requestId || view.pendingOperationId && item.id === view.pendingOperationId);
    if (row && ['queued','running','succeeded','failed','interrupted'].includes(row.status)) {
      view.pendingOperationId = row.id; view.pendingStatus = row.status; persistMutation();
      if (['succeeded','failed','interrupted'].includes(row.status)) void finishMutation({...row,requestId:body.requestId});
      else {view.error = ''; view.message = text('operationPending', 'Изменение выполняется. Ход операции показан вверху.', 'Changes are in progress. Follow the operation status above.'); render();}
    }
    let reload = false;
    for (const item of rows) if (['project-create','project-update'].includes(item.action) &&
        ['succeeded','failed','interrupted'].includes(item.status) && !view.terminalOperations.has(item.id)) {
      view.terminalOperations.add(item.id);
      if (item !== row) reload = true;
    }
    if (reload) void loadCatalog({silent:true,refreshAfterCurrent:true});
  }
  async function mutate(body, draftKey = null) {
    if (view.busy) return;
    if (global.backupStatus?.begin && body.background !== true) body = {...body,background:true,
      origin:{section:'projects',...(body.action === 'update' ? {project:body.project} : {})}};
    const effectiveDraftKey = draftKey || (body.action === 'create' ? 'create' :
      body.action === 'update' && Object.hasOwn(body.patch || {}, 'name') ? `rename:${body.project}` : null);
    if (view.pendingMutation && JSON.stringify(view.pendingMutation) !== JSON.stringify(body)) {
      view.error = text('pending', fallbackText.pending); render(); return;
    }
    view.busy = true; view.error = ''; view.message = '';view.feedbackId='';
    view.pendingMutation = body; view.pendingDraftKey = effectiveDraftKey; view.pendingStatus = 'requesting'; persistMutation();
    const operationBody = {...body,action:`project-${body.action}`};
    if (body.background === true) global.backupStatus?.begin(operationBody);
    render();
    try {
      let response;
      try { response = await fetch('/api/v1/projects', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); }
      catch (firstError) {
        if (view.terminalRequests.has(body.requestId)) return;
        // Keep the same request ID: the server can safely replay an unknown outcome.
        try { response = await fetch('/api/v1/projects', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); }
        catch (secondError) { throw secondError; }
      }
      let result;
      try {
        if (view.terminalRequests.has(body.requestId)) return;
        result = await jsonResponse(response);
        if (view.terminalRequests.has(body.requestId)) return;
        if (body.background === true) {
          const operation = result?.operation;
          if (!operation || typeof operation.id !== 'string' || !operation.id || operation.requestId !== body.requestId ||
              operation.action !== operationBody.action || !['queued','running','succeeded','failed','interrupted'].includes(operation.status)) {
            throw Error(text('invalidOperation', 'Сервер не подтвердил операцию. Повторите запрос, чтобы уточнить результат.', 'The server did not confirm the operation. Retry the request to check its result.'));
          }
          view.pendingOperationId = operation.id; view.pendingStatus = operation.status; persistMutation();
          global.backupStatus?.acknowledge(operation,operationBody);
          if (['succeeded','failed','interrupted'].includes(operation.status)) return await finishMutation(operation);
          view.message = text('operationPending', 'Изменение выполняется. Ход операции показан вверху.', 'Changes are in progress. Follow the operation status above.');
          void global.backupStatus?.refresh?.(); return;
        }
        if (!validProject(result?.project, body)) throw Error(text('57b13a4ae07c', 'Сервер не вернул проект', 'The server did not return the project'));
      } catch (error) {
        if (view.terminalRequests.has(body.requestId)) return;
        // A malformed successful response or 5xx leaves the server outcome unknown.
        // A 4xx is a confirmed rejection and can be safely discarded.
        if (!response || response.status >= 500 || response.ok) {view.pendingMutation = body; view.pendingStatus = 'unknown'; persistMutation();}
        else clearMutation();
        if (error.code === 'project_revision_conflict' && body.patch?.name != null) view.renameConflicts.add(body.project);
        throw error;
      }
      clearMutation();
      if (effectiveDraftKey) { view.drafts.delete(effectiveDraftKey); view.dirtyForms.delete(effectiveDraftKey); }
      view.message = body.action === 'create' ? text('created', fallbackText.created) : text('saved', fallbackText.saved);
      try { if (typeof global.CustomEvent === 'function') global.dispatchEvent?.(new global.CustomEvent('hub-projects-changed', {detail:{project:result.project, action:body.action}})); } catch (_) { /* Optional browser event API. */ }
      await loadCatalog({silent: true});
      return result.project;
    } catch (error) {
      if (view.terminalRequests.has(body.requestId)) return;
      if (view.pendingMutation) {view.pendingStatus = 'unknown'; persistMutation();}
      if (body.background === true) {
        if (error.status >= 400 && error.status < 500) global.backupStatus?.reject(operationBody,error);
        else {global.backupStatus?.uncertain(operationBody); void global.backupStatus?.refresh?.();}
      }
      view.error = (globalThis.HubI18n?.error?.(error) ?? error.message) || text('retry', fallbackText.retry); throw error;
    }
    finally { view.busy = false; render(); }
  }
  function formValue(form, name) { return form?.elements?.namedItem(name)?.value?.trim() || ''; }
  function absoluteFolder(value) { return !value || value.startsWith('/') || /^[A-Za-z]:[\\/]/.test(value); }
  async function submit(form) {
    if (managementDisabled()) return;
    modal = {kind:form.dataset.projectForm === 'create' ? 'create' : 'configure', project:form.dataset.projectId}; modalTab = 'general';
    if (form.dataset.projectForm === 'create') {
      const name = formValue(form, 'name'), root = formValue(form, 'root');
      if (!name) { view.error = text('invalidName', fallbackText.invalidName); render(); return; }
      if (!absoluteFolder(root)) { view.error = text('invalidFolder', fallbackText.invalidFolder); render(); return; }
      const result = await mutate({action:'create', name, roots:root ? [root] : [], requestId:requestId()}, 'create');
      if (result) {modal = {kind:'configure', project:result.id}; render();}
      return;
    }
    const project = projectRows().find(row => row.id === form.dataset.projectId), name = formValue(form, 'name');
    if (!project || !name) { view.error = text('invalidName', fallbackText.invalidName); render(); return; }
    const values = draft(`rename:${project.id}`, {revision:form.dataset.projectRevision});
    const capturedRevision = values.revision ?? form.dataset.projectRevision;
    const expected = capturedRevision !== '' && capturedRevision != null && Number.isFinite(Number(capturedRevision)) ? Number(capturedRevision) : project.revision;
    await mutate({action:'update', project:project.id, patch:{name}, expected, requestId:requestId()}, `rename:${project.id}`);
  }
  async function action(element) {
    const name = element.dataset.projectAction;
    if (name === 'close') {closeModal(); return;}
    if (['create','configure'].includes(name)) {
      if (view.busy) return;
      opener = element; modal = {kind:name, project:element.dataset.projectId}; modalTab = 'general'; view.message = ''; view.error = ''; render(); return;
    }
    if (name === 'refresh') return loadCatalog({rebaseConflicts:true});
    if (name === 'retry' && canRetryMutation()) return mutate(view.pendingMutation);
    const project = projectRows().find(row => row.id === element.dataset.projectId);
    if (!project || managementDisabled()) return;
    const patch = ({archive:{archived:true}, unarchive:{archived:false}, delete:{deleted:true}, recover:{deleted:false}})[name];
    if (patch && (name !== 'delete' || global.confirm?.(text('confirmDelete', 'Удалить проект из активного списка? Его история сохранится, проект можно восстановить.')))) await mutate({action:'update', project:project.id, patch, expected:project.revision, requestId:requestId()});
  }
  function bind(root) {
    if (root.dataset.projectsBound === 'true') return;
    root.dataset.projectsBound = 'true';
    root.addEventListener('input', event => { const form = event.target.closest?.('[data-project-form]'); if (form) captureForm(form); });
    root.addEventListener('submit', event => { const form = event.target.closest?.('[data-project-form]'); if (!form) return; event.preventDefault(); captureForm(form); return submit(form).catch(() => {}); });
    root.addEventListener('click', event => {
      const tab = event.target.closest?.('[data-project-dialog-tab]');
      if (tab?.dataset.projectDialogTab) {if (!view.busy && ['general','code'].includes(tab.dataset.projectDialogTab)) {modalTab = tab.dataset.projectDialogTab; render();} return;}
      const button = event.target.closest?.('[data-project-action]'); if (button) return action(button).catch(() => {});
    });
  }
  function schedulePoll(root) {
    if (view.pollTimer != null) return;
    view.pollTimer = setTimeout(async () => {
      view.pollTimer = null;
      if (!connected(root) || view.root !== root) return;
      await loadCatalog({silent:true});
      schedulePoll(root);
    }, 5000);
  }
  function afterRender(root) {
    root = root || global.document?.querySelector?.('#projects-manager');
    if (!root) return;
    if (view.root !== root && view.pollTimer != null) { clearTimeout(view.pollTimer); view.pollTimer = null; }
    const sameRoot = view.root === root, detailId = detailRouteId(), routeChanged = view.detailId !== detailId;
    view.detailId = detailId;
    view.root = root; bind(root); if (!sameRoot || routeChanged) render(root);
    const shell = global.document?.querySelector?.('#projects-admin');
    if (shell && !shell.__projectsShellBound) {
      shell.__projectsShellBound = true;
      shell.addEventListener('click', event => {const tab = event.target.closest?.('[data-project-tab]');if (tab?.dataset.projectTab) {switchTab(tab.dataset.projectTab, shell);if(global.location && tab.tagName!=='A')global.location.hash=`projects/${tab.dataset.projectTab}`;}});
      shell.addEventListener('keydown', event => {
        const tab = event.target.closest?.('[role="tab"][data-project-tab]');if (!tab || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        const tabs = [...shell.querySelectorAll('[role="tab"][data-project-tab]')], index = tabs.indexOf(tab);
        const next = tabs[event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];
        event.preventDefault(); switchTab(next.dataset.projectTab, shell);if(global.location)global.location.hash=`projects/${next.dataset.projectTab}`;next.focus();
      });
    }
    const hashParts=(global.location?.hash || '').replace(/^#/,'').split('/');
    if(hashParts[0]==='projects' && ['projects','data','backups'].includes(hashParts[1]))selectedTab=hashParts[1];
    switchTab(selectedTab, shell);
    global.backupStatus?.afterRender?.();
    handleOperations();
    if (global.backupStatus?.refresh && (routeChanged || view.pendingMutation && !view.operationRefreshRequested)) {
      view.operationRefreshRequested = true; void global.backupStatus.refresh();
    }
    if (!view.loaded && !view.loading) void loadCatalog();
    schedulePoll(root);
  }
  global.HubProjectsUI = {page: () => `<section id="projects-admin" class="projects-admin"><header class="projects-head"><div><div class="eyebrow">PROJECT HUB</div><h1 id="projects-manager-title">${esc(text('title', fallbackText.title))}</h1><p>${esc(text('adminIntro', 'Управляйте проектами, папками кода, данными и резервными копиями.'))}</p></div><a href="#settings/agents">${esc(text('agentConnections', 'Агенты и подключения'))}</a></header><nav class="projects-tabs" role="tablist" aria-label="${esc(text('title', fallbackText.title))}">${['projects','data','backups'].map(tab=>`<button type="button" role="tab" id="projects-tab-${tab}" aria-controls="projects-pane-${tab}" aria-selected="${selectedTab===tab}" data-project-tab="${tab}" tabindex="${selectedTab===tab?0:-1}">${esc(text(tab,({projects:'Проекты',data:'Данные Hub',backups:'Резервные копии'})[tab]))}</button>`).join('')}</nav><div role="tabpanel" id="projects-pane-projects" aria-labelledby="projects-tab-projects" data-project-pane="projects" ${selectedTab==='projects'?'':'hidden'}><section id="projects-manager" class="projects-page">${content()}</section></div><div role="tabpanel" id="projects-pane-data" aria-labelledby="projects-tab-data" data-project-pane="data" ${selectedTab==='data'?'':'hidden'}>${global.HubStorageUI?.page() || ''}</div><div role="tabpanel" id="projects-pane-backups" aria-labelledby="projects-tab-backups" data-project-pane="backups" ${selectedTab==='backups'?'':'hidden'}>${global.backupsPage?.({embedded:true}) || ''}</div></section>`, afterRender,selectTab:switchTab,catalog:()=>view.envelope};
  global.addEventListener?.('hub-language-changed', () => render(view.root, true));
  global.addEventListener?.('hub-operations-changed', handleOperations);

globalThis.HubI18n?.onChange?.(()=>{Object.assign(fallbackText,{
    title: (globalThis.HubI18n?.t?.("projects.5029f02d0a94") ?? 'Проекты'), intro: (globalThis.HubI18n?.t?.("projects.4c171d1a6b7d") ?? 'Управляйте проектами Hub и при необходимости связывайте их с папкой исходного кода.'),
    add: (globalThis.HubI18n?.t?.("projects.a84d90bc78b3") ?? 'Добавить проект'), name: (globalThis.HubI18n?.t?.("projects.720a7014d17b") ?? 'Название проекта'), folder: (globalThis.HubI18n?.t?.("projects.e4c87de262c0") ?? 'Папка кода (необязательно)'),
    folderHelp: (globalThis.HubI18n?.t?.("projects.802588148bf9") ?? 'Укажите абсолютный путь, если проект связан с локальной рабочей папкой.'),
    save: (globalThis.HubI18n?.t?.("projects.49ed84ac6492") ?? 'Создать проект'), refresh: (globalThis.HubI18n?.t?.("projects.603e460bf59c") ?? 'Обновить'), empty: (globalThis.HubI18n?.t?.("projects.741d221b924c") ?? 'Проектов пока нет.'),
    loading: (globalThis.HubI18n?.t?.("projects.4767b9a38d5e") ?? 'Загрузка проектов…'), unavailable: (globalThis.HubI18n?.t?.("projects.9b0f38818a0a") ?? 'Не удалось загрузить проекты'),
    oldSchema: (globalThis.HubI18n?.t?.("projects.3dfbbddd5a77") ?? 'Управление отключено для этой версии каталога. Перенесите данные совместимым архивом, затем обновите каталог.'),
    rename: (globalThis.HubI18n?.t?.("projects.194306e20807") ?? 'Переименовать'), open: (globalThis.HubI18n?.t?.("projects.e4e6c1fa1cfc") ?? 'Открыть проект'), archive: (globalThis.HubI18n?.t?.("projects.1137508af8ff") ?? 'Архивировать'), unarchive: (globalThis.HubI18n?.t?.("projects.d314390d1ef9") ?? 'Вернуть из архива'),
    remove: (globalThis.HubI18n?.t?.("projects.be99b1361201") ?? 'Удалить'), recover: (globalThis.HubI18n?.t?.("projects.76f55a988f8a") ?? 'Восстановить'), deleted: (globalThis.HubI18n?.t?.("projects.0bfb4a497412") ?? 'Удалённые проекты'),
    archived: (globalThis.HubI18n?.t?.("projects.34886925697b") ?? 'В архиве'), active: (globalThis.HubI18n?.t?.("projects.a87a4b39c304") ?? 'Активен'), noFolder: (globalThis.HubI18n?.t?.("projects.200d4d17ae3e") ?? 'Папка кода не указана'),
    saved: (globalThis.HubI18n?.t?.("projects.4dd96a79b884") ?? 'Изменения сохранены.'), created: (globalThis.HubI18n?.t?.("projects.6be220f7d990") ?? 'Проект создан.'), invalidName: (globalThis.HubI18n?.t?.("projects.0c92833cda5f") ?? 'Введите название проекта.'),
    pending: (globalThis.HubI18n?.t?.("projects.e548e8f4d639") ?? 'Предыдущее изменение не подтверждено. Повторите его перед новым действием.'), repeat: (globalThis.HubI18n?.t?.("projects.f2cca80a5b4b") ?? 'Повторить последнее изменение'),
    conflict: (globalThis.HubI18n?.t?.("projects.49bfd3c3a0e3") ?? 'Проект изменён другим клиентом. Нажмите «Обновить», сравните значения и повторите сохранение.'),
    invalidFolder: (globalThis.HubI18n?.t?.("projects.5ffce33f9766") ?? 'Путь к папке должен быть абсолютным.'), retry: (globalThis.HubI18n?.t?.("projects.abc1ae6ffc4a") ?? 'Повторите действие.'),
  });});
})(typeof window !== 'undefined' ? window : globalThis);
