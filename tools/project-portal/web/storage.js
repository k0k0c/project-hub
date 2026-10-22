"use strict";

// Every import publishes into the active data folder; a source is never activated.
(function (global) {
  const state = {root:null,catalog:null,preview:null,path:'',sourcePath:'',mode:'add',selected:new Set(),resolutions:{},includeGlobals:false,confirmed:false,busy:false,message:'',pending:new Map(),handled:new Set(),timer:null,detailId:'',feedbackId:'',importId:'',sourceRequestId:''};
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const copy = (ru,en) => global.HubI18n?.locale==='en' ? en : ru;
  const t = (key,ru,en) => global.HubI18n?.t?.(`storage.${key}`,copy(ru,en)) || copy(ru,en);
  const requestId = () => global.crypto?.randomUUID?.().replace(/-/g,'') || `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`.padEnd(32,'0').slice(0,32);
  const active = row => ['queued','running','requesting','unknown'].includes(row?.status);
  const pathLink = (path,kind) => global.HubLocalFiles?.pathLink(path,kind==='import-source' && /\.zip$/i.test(path || '') ? 'backups' : kind,{reveal:kind==='import-source' && /\.zip$/i.test(path || '')}) || `<code class="storage-path">${esc(path || '—')}</code>`;
  const persistenceKey='project-hub-storage-requests';
  function persist() {try {global.sessionStorage?.setItem(persistenceKey,JSON.stringify([...state.pending.values()]));}catch(_){/* Optional persistence. */}}
  try {const saved=JSON.parse(global.sessionStorage?.getItem(persistenceKey)||'[]');if(Array.isArray(saved))for(const request of saved)if(request?.body?.requestId)state.pending.set(request.body.requestId,request);}catch(_){/* Invalid drafts are ignored. */}
  function checkedPreview(value) {
    if(!value || typeof value.path!=='string' || typeof value.revision!=='string' || !Array.isArray(value.projects) || !value.storageSchemas)throw Error(t('failed','Не удалось проверить источник.','Could not inspect the source.'));
    return value;
  }
  function comparison() {
    const rows=state.preview?.comparison?.projects || [];
    return (state.preview?.projects || []).map(project=>{
      const compared=rows.find(row=>row.id===project.id) || {};
      return {...project,...compared,exists:compared.exists===true || ['identical','different','conflict'].includes(compared.status),identical:compared.identical===true || compared.status==='identical'};
    });
  }
  function setPreview(value,copyId) {
    const preview={...checkedPreview(value),...(copyId ? {copyId} : {})};
    state.preview=preview;state.sourcePath=preview.sourcePath || state.sourcePath || preview.path;
    state.selected=new Set(preview.projects.map(project=>project.id));
    state.resolutions=Object.fromEntries(comparison().filter(project=>project.exists).map(project=>[project.id,project.identical?'skip':'keep']));
    state.includeGlobals=false;state.confirmed=false;state.message=t('ready','Источник проверен. Выберите, какие данные применить.','Source checked. Choose which data to apply.');
  }
  function currentProjects() {return state.preview?.comparison?.currentProjects || state.catalog?.projects || [];}
  function summary() {
    const projects=comparison(), current=currentProjects(), replacingAll=state.mode==='replace-all';
    const selected=projects.filter(project=>replacingAll || state.selected.has(project.id));
    const replaced=replacingAll ? current.filter(project=>projects.some(source=>source.id===project.id)) : selected.filter(project=>project.exists && state.resolutions[project.id]==='replace');
    const added=selected.filter(project=>!project.exists);
    const removed=replacingAll ? current.filter(project=>!projects.some(source=>source.id===project.id)) : [];
    const skipped=replacingAll ? [] : projects.filter(project=>!state.selected.has(project.id) || project.exists && state.resolutions[project.id]!=='replace');
    return {selected,replaced,added,removed,skipped};
  }
  function projectNames(rows) {return rows.length ? rows.map(project=>esc(project.name || project.id)).join(', ') : '—';}
  function summaryHtml() {
    const result=summary(), all=state.mode==='replace-all';
    return `<section class="storage-import-summary" data-ui-key="storage-import-summary"><h4>${esc(t('expectedResult','Результат применения','Expected result'))}</h4><dl class="projects-details"><dt>${esc(t('destination','Назначение','Destination'))}</dt><dd>${pathLink(state.catalog?.activeHome,'data')}</dd><dt>${esc(t('addedProjects','Добавятся проекты','Projects added'))}</dt><dd>${projectNames(result.added)}</dd><dt>${esc(t('replacedProjects','Заменятся проекты','Projects replaced'))}</dt><dd>${projectNames(result.replaced)}</dd>${all ? `<dt>${esc(t('removedProjects','Удалятся из рабочего набора','Removed from active data'))}</dt><dd>${projectNames(result.removed)}</dd>` : `<dt>${esc(t('keptProjects','Сохранятся без изменений','Kept unchanged'))}</dt><dd>${projectNames(result.skipped)}</dd>`}<dt>${esc(t('globalData','Общие инструкции и их настройки','Global instructions and their settings'))}</dt><dd>${esc(state.includeGlobals ? t('replaceGlobals','Будут заменены данными источника','Will be replaced by source instructions and settings') : t('keepGlobals','Сохранятся действующие','Current instructions and settings will be retained'))}</dd></dl><p class="caption">${esc(t('preserveSource','Исходная папка или ZIP сохранятся. Привязки папок кода сохраняются; исходники не копируются. Действующие подключения агентов и настройки запуска сохраняются.','The source folder or ZIP is preserved. Code-folder links are retained; source files are not copied. Current agent connections and launch settings are retained.'))}</p><p class="storage-replacement-notice">${esc(t('safetyBackup','После подтверждения Hub сохранит одну резервную копию текущих данных, подготовит проверенный результат и кратко перезапустит сервер по тому же адресу.','After confirmation, Hub saves one backup of current data, prepares a verified result, and briefly restarts the server at the same address.'))}</p>${all || result.replaced.length ? `<p class="storage-replacement-notice">${esc(t('replacementScope','Выбранные проекты заменяются целиком вместе с задачами, историей, документами и вложениями.','Selected projects are replaced with their tasks, history, documents and attachments.'))}</p>` : ''}</section>`;
  }
  function previewHtml() {
    const preview=state.preview;if(!preview)return '';
    const projects=comparison(),all=state.mode==='replace-all',result=summary();
    const conflicts=preview.comparison?.conflicts || [];
    const disabled=state.busy ? 'disabled' : '';
    const sameNames=conflicts.filter(row=>['name','same-name','same_name','name-match'].includes(row.type || row.kind));
    return `<section class="admin-panel storage-preview" data-ui-key="storage-preview"><div class="projects-section-head"><h3>${esc(t('preview','Предварительный просмотр импорта','Import preview'))}</h3><div class="projects-actions"><button type="button" data-storage-action="recheck" ${disabled}>${esc(t('recheck','Проверить источник снова','Inspect source again'))}</button><button type="button" data-storage-action="dismiss">${esc(t('close','Закрыть','Close'))}</button></div></div><dl class="projects-details"><dt>${esc(t('source','Источник','Source'))}</dt><dd>${pathLink(preview.sourcePath || state.sourcePath || preview.path,'import-source')}</dd><dt>${esc(t('format','Формат данных','Data format'))}</dt><dd>${esc(preview.storageSchemas.registry)}</dd><dt>${esc(t('volume','Объём данных','Data size'))}</dt><dd>${esc(global.backupStatus?.formatSize ? global.backupStatus.formatSize(preview.totalBytes) : '—')}</dd></dl><fieldset class="storage-import-modes" ${disabled}><legend>${esc(t('mode','Как применить данные','How to apply data'))}</legend><label><input type="radio" name="storage-mode" value="add" ${!all?'checked':''}><span><strong>${esc(t('addProjects','Добавить проекты','Add projects'))}</strong><small>${esc(t('addHelp','Выберите проекты из источника. Остальные текущие проекты сохранятся.','Choose source projects. Other current projects are retained.'))}</small></span></label><label><input type="radio" name="storage-mode" value="replace-all" ${all?'checked':''}><span><strong>${esc(t('restoreAll','Восстановить всё хранилище','Restore the entire data store'))}</strong><small>${esc(t('restoreAllHelp','Полный снимок источника заменит рабочие данные. Общие настройки и инструкции переносятся по отдельному выбору.','The full source snapshot replaces active data. Global settings and instructions are imported only if you select them.'))}</small></span></label></fieldset><ul class="storage-projects storage-select-projects">${projects.map(project=>`<li data-import-project="${esc(project.id)}"><label><input type="checkbox" data-storage-project="${esc(project.id)}" ${all || state.selected.has(project.id)?'checked':''} ${all || state.busy?'disabled':''}><span><strong>${esc(project.name || project.id)}</strong><small>${esc(project.tasks ?? 0)} ${esc(t('tasks','задач','tasks'))} · <code>${esc(project.id)}</code></small></span></label><div>${project.exists ? `<span class="projects-badge">${esc(project.identical ? t('identical','Данные совпадают','Data is identical') : t('idConflict','Совпадает идентификатор','Matching identifier'))}</span>${!all ? `<select aria-label="${esc(t('conflictResolution','Решение конфликта','Conflict resolution'))}: ${esc(project.name || project.id)}" data-storage-resolution="${esc(project.id)}" ${disabled}><option value="keep" ${state.resolutions[project.id]==='keep'?'selected':''}>${esc(t('keepCurrent','Оставить текущий','Keep current'))}</option><option value="replace" ${state.resolutions[project.id]==='replace'?'selected':''}>${esc(t('replaceSource','Заменить данными источника','Replace with source'))}</option><option value="skip" ${state.resolutions[project.id]==='skip'?'selected':''}>${esc(t('skipProject','Пропустить','Skip'))}</option></select>` : ''}` : `<span class="projects-badge">${esc(t('newProject','Новый проект','New project'))}</span>`}</div></li>`).join('')}</ul>${sameNames.length ? `<p class="projects-notice">${esc(t('sameNameNotice','В источнике и текущих данных есть одноимённые проекты с разными идентификаторами. Они останутся отдельными проектами.','Source and current data contain projects with the same name and different identifiers. They remain separate projects.'))}</p>` : ''}${conflicts.filter(row=>!sameNames.includes(row)).some(row=>row.type==='cross-project-link' || row.kind==='cross-project-link') ? `<p class="projects-notice">${esc(t('linksNotice','Источник содержит связи между проектами. Hub проверит полноту выбранного набора перед применением.','The source contains links between projects. Hub checks the selected set before applying it.'))}</p>` : ''}<label class="storage-global-choice"><input type="checkbox" data-storage-globals ${state.includeGlobals?'checked':''} ${disabled}><span>${esc(t('importGlobals','Импортировать пользовательские инструкции Hub','Import Hub user instructions'))}<small>${esc(t('importGlobalsHelp','Общие правила Hub и их сохранённые настройки заменят действующие для всей установки. Настройки выбранных проектов переносятся вместе с проектами. Подключения агентов и параметры запуска сохраняются.','Hub-wide rules and their saved settings replace the current ones across this installation. Selected project settings move with their projects. Agent connections and launch parameters are preserved.'))}</small></span></label>${summaryHtml()}${preview.copyId ? `<label class="storage-import-confirm"><input type="checkbox" data-storage-confirm ${state.confirmed?'checked':''} ${disabled}><span>${esc(all ? t('confirmAll','Я подтверждаю замену всех рабочих данных, включая перечисленные проекты, и указанный выбор инструкций Hub.','I confirm replacing all active data, including the listed projects, and the displayed Hub instruction choice.') : t('confirmAdd','Я проверил выбор проектов, решения конфликтов и инструкций Hub.','I have reviewed the selected projects, conflict resolutions and Hub instructions.'))}</span></label><button type="button" class="primary" data-storage-action="apply" ${state.busy || !state.confirmed || !all && !result.selected.length?'disabled':''}>${esc(all ? t('applyAll','Восстановить всё хранилище','Restore the entire data store') : t('applyAdd','Применить выбранные проекты','Apply selected projects'))}</button>` : `<p class="caption">${esc(t('sourcePreparing','Источник будет подготовлен автоматически после проверки.','The source is prepared automatically after inspection.'))}</p>`}</section>`;
  }
  function content() {
    const catalog=state.catalog, preparations=catalog?.copies || [];
    return `<section class="admin-panel"><div class="projects-section-head"><div><h2>${esc(t('activeStorage','Рабочие данные Hub','Active Hub data'))}</h2><p class="caption">${esc(t('activeHelp','Все проекты этой установки используют одну папку данных. Импорт применяется в эту папку.','All projects in this installation use one data folder. Imports are applied to this folder.'))}</p></div><button type="button" data-storage-action="refresh">${esc(t('refresh','Обновить','Refresh'))}</button></div><dl class="projects-details"><dt>${esc(t('folder','Папка данных Hub','Hub data folder'))}</dt><dd>${pathLink(catalog?.activeHome,'data')}</dd><dt>${esc(t('backupFolder','Папка резервных копий','Backup folder'))}</dt><dd>${pathLink(catalog?.backupHome,'backups')}</dd><dt>${esc(t('projects','Проекты','Projects'))}</dt><dd>${esc(catalog?.projectCount ?? '—')}</dd></dl><a href="#settings">${esc(t('folderSettings','Изменить папки в общих настройках','Change folders in General settings'))}</a><p role="status" data-ui-key="storage-status">${esc(global.backupStatus?.feedback ? global.backupStatus.feedback(state.feedbackId,state.message) : state.message)}</p>${[...state.pending.values()].filter(request=>request.uncertain).map(request=>`<button type="button" data-storage-action="retry" data-operation-retry="${esc(request.body.requestId)}" data-request-id="${esc(request.body.requestId)}">${esc(t('retry','Проверить и повторить тот же запрос','Check and retry the same request'))}</button>`).join('')}${state.detailId ? global.backupStatus?.details(state.detailId) || '' : state.feedbackId ? global.backupStatus?.details(state.feedbackId,{transient:true}) || '' : ''}</section><section class="admin-panel"><h2>${esc(t('importFolder','Импортировать из папки','Import from a folder'))}</h2><p class="caption">${esc(t('importFolderHelp','Выберите прежнюю папку данных Hub. Проверка автоматически создаст подготовленный источник и предварительный просмотр; рабочие данные изменятся только после подтверждения импорта.','Choose an earlier Hub data folder. Inspection and preparation preserve the source; active data changes only after you confirm the import.'))}</p><form data-storage-form data-readonly="true"><label><span>${esc(t('sourceFolder','Исходная папка данных','Source data folder'))}</span><div class="hub-folder-field"><input id="storage-import-folder" name="path" value="${esc(state.path)}" required ${state.busy?'disabled':''}>${global.HubLocalFiles?.chooser('import','#storage-import-folder',state.busy) || ''}</div></label><button type="submit" ${state.busy?'disabled':''}>${esc(t('inspect','Проверить и показать проекты','Inspect and show projects'))}</button><p role="status" data-local-files-status></p></form><p><a href="#projects/backups">${esc(t('restoreZip','Восстановить из ZIP','Restore from ZIP'))}</a></p></section>${previewHtml()}${global.backupStatus?.history?.('data') || ''}<section class="admin-panel"><h2>${esc(t('preparations','Подготовленные источники','Prepared sources'))}</h2><p class="caption">${esc(t('preparationsHelp','Здесь находятся проверяемые временные копии источников. Они не являются рабочими хранилищами. Откройте источник, чтобы выбрать режим и проекты для импорта.','These are temporary source copies used for inspection. Open a source to choose an import mode and projects.'))}</p><div class="admin-table-wrap"><table class="admin-table"><thead><tr>${['source','date','projects','actions'].map(key=>`<th>${esc(t(key,({source:'Источник',date:'Дата',projects:'Проекты',actions:'Действия'})[key],({source:'Source',date:'Date',projects:'Projects',actions:'Actions'})[key]))}</th>`).join('')}</tr></thead><tbody>${preparations.filter(item=>!item.active).map(item=>`<tr data-ui-key="storage-copy-${esc(item.id)}"><td>${esc(item.name || t(item.origin==='folder-import'?'folderImport':'backupSource',item.origin==='folder-import'?'Папка данных':'ZIP-архив',item.origin==='folder-import'?'Data folder':'ZIP archive'))}</td><td>${esc(item.createdAt ? new Date(item.createdAt).toLocaleString(global.HubI18n?.locale==='en'?'en-GB':'ru-RU') : '—')}</td><td>${esc(item.projectCount ?? '—')}</td><td><button type="button" data-storage-action="inspect-copy" data-copy-id="${esc(item.id)}" ${state.busy?'disabled':''}>${esc(t('openPreview','Предварительный просмотр','Preview'))}</button></td></tr>`).join('') || `<tr><td colspan="4">${esc(t('noPreparations','Подготовленных источников пока нет.','No prepared sources yet.'))}</td></tr>`}</tbody></table></div></section>`;
  }
  function render() {
    if(!state.root || state.root.isConnected===false)return;
    if(global.HubLiveUI)global.HubLiveUI.patch(state.root,content());else state.root.innerHTML=content();
    global.HubLocalFiles?.bind(state.root);global.backupStatus?.afterRender();
  }
  async function api(body,url='/api/v1/storage') {
    let response;
    try {response=await fetch(url,{cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});}catch(error){error.outcomeUnknown=!!body;throw error;}
    let value;try{value=await response.json();}catch(error){error.outcomeUnknown=!!body;throw error;}
    if(!response.ok || !value || typeof value!=='object' || Array.isArray(value)){const error=Error(value?.error || t('failed','Не удалось выполнить операцию.','Could not complete the operation.'));error.outcomeUnknown=!!body && (response.status>=500 || response.ok);throw error;}
    return value;
  }
  async function handleResult(row,request) {
    if(!row || active(row) || state.handled.has(row.id))return;
    state.handled.add(row.id);if(request){state.pending.delete(request.body.requestId);persist();}
    const sourceAction=['inspect-folder','inspect-copy','import-folder','restore-copy'].includes(row.action);
    if(sourceAction && state.sourceRequestId && row.requestId!==state.sourceRequestId)return;
    if(row.status!=='succeeded'){state.message=row.error?.message || row.error || t('failed','Операция завершилась с ошибкой.','The operation failed.');return;}
    const result=row.result || {};
    if(result.preview)setPreview({...result.preview,comparison:result.preview.comparison || result.comparison},result.copyId || request?.body?.id);
    if(row.action==='import-folder' && result.copyId && !result.preview)await start({action:'inspect-copy',id:result.copyId});
    if(row.action==='apply-import'){state.preview=null;state.confirmed=false;state.message=t('applied','Данные применены в рабочую папку Hub. Сервер кратко перезапустился; источник сохранён.','Data applied to the active Hub folder. The source is preserved.');await load(false);void global.refresh?.();}
  }
  async function load(process=true) {
    state.catalog=await api();
    if(process){
      const rows=[...(state.catalog.jobs || []),...(state.catalog.lifecycle?.operations || []),...(global.backupStatus?.operations() || [])];
      for(const request of [...state.pending.values()]){const row=rows.find(row=>row.requestId===request.body.requestId);if(row)await handleResult(row,request);}
    }
    render();
  }
  async function start(body,url='/api/v1/storage') {
    if(!body.requestId){
      const duplicate=[...state.pending.values()].find(request=>request.body.action===body.action && (body.id ? request.body.id===body.id : request.body.path===body.path));
      if(duplicate){state.feedbackId=duplicate.id || duplicate.body.requestId;state.message=t('workingServer','Операция принята сервером. Состояние показано над страницей.','The server accepted the operation. Its status is shown above the page.');render();return;}
    }
    const selectedProject=typeof activeProject==='string' ? activeProject : global.activeProject;
    const origin=body.origin || {section:'data',...(selectedProject ? {project:selectedProject} : {})};
    body={...body,background:true,requestId:body.requestId || requestId(),origin};
    if(['inspect-folder','inspect-copy','import-folder'].includes(body.action))state.sourceRequestId=body.requestId;
    if(['inspect-folder','inspect-copy'].includes(body.action))state.preview=null;
    const request=state.pending.get(body.requestId) || {body,url};state.pending.set(body.requestId,request);persist();
    state.feedbackId=body.requestId;state.busy=true;state.message=t('working','Запрос отправляется…','Sending request…');global.backupStatus?.begin(body);render();
    try {
      const value=await api(body,url),row=value.operation || value.job;
      if(!row?.id || !['queued','running','succeeded','failed','interrupted'].includes(row.status) || row.requestId && row.requestId!==body.requestId){const error=Error(t('invalidAck','Сервер не подтвердил операцию. Повторите тот же запрос.','The server did not confirm the operation. Retry the same request.'));error.outcomeUnknown=true;throw error;}
      request.uncertain=false;request.id=row.id;if(body.action==='apply-import')state.confirmed=false;persist();global.backupStatus?.acknowledge(row,body);state.feedbackId=row.id;
      await handleResult(row,request);state.message=active(row)?t('workingServer','Операция принята сервером. Состояние показано над страницей.','The server accepted the operation. Its status is shown above the page.'):state.message;
      void global.backupStatus?.refresh();
    }catch(error){
      if(error.outcomeUnknown){request.uncertain=true;persist();global.backupStatus?.uncertain(body);}else{state.pending.delete(body.requestId);persist();global.backupStatus?.reject(body,error);}
      state.message=global.HubI18n?.error?.(error) || error.message;
    }finally{state.busy=false;render();}
  }
  async function action(name,button) {
    if(name==='dismiss'){state.preview=null;state.confirmed=false;render();return;}
    if(name==='refresh'){await load();void global.backupStatus?.refresh();return;}
    if(state.busy)return;
    if(name==='retry'){const request=state.pending.get(button.dataset.requestId);if(request)await start(request.body,request.url);return;}
    if([...state.pending.values()].some(request=>request.uncertain)){state.message=t('pending','Результат предыдущего запроса не подтверждён. Проверьте и повторите тот же запрос.','The previous request is not confirmed. Check and retry the same request.');render();return;}
    if(name==='inspect-copy'){await start({action:'inspect-copy',id:button.dataset.copyId});return;}
    if(name==='recheck' && state.preview){
      const original=state.preview.sourceKind==='folder' || state.preview.sourceKind==='zip' ? state.preview.sourcePath : '';
      await start(original && state.preview.sourceKind==='folder' ? {action:'inspect-folder',path:original} : state.preview.copyId ? {action:'inspect-copy',id:state.preview.copyId} : {action:'inspect-folder',path:original || state.sourcePath || state.preview.path});
      return;
    }
    if(name==='apply' && state.preview?.copyId && state.confirmed){
      if([...state.pending.values()].some(request=>request.body.action==='apply-import')){state.message=t('workingServer','Операция принята сервером. Состояние показано над страницей.','The server accepted the operation. Its status is shown above the page.');render();return;}
      const result=summary(),all=state.mode==='replace-all';
      await start({action:'apply-import',id:state.preview.copyId,expected:state.preview.revision,mode:state.mode,projects:all ? comparison().map(project=>project.id) : [...state.selected],resolutions:{...state.resolutions},includeGlobals:state.includeGlobals,expectedActive:state.preview.comparison?.activeRevision,confirmed:true});
    }
  }
  function readRoute() {
    const parts=(global.location?.hash || '').replace(/^#/,'').split('/');
    state.detailId='';
    if(parts[0]!=='projects' || parts[1]!=='data')return;
    if(parts[2]==='operation')try{state.detailId=decodeURIComponent(parts[3] || '');}catch(_){state.detailId='';}
    if(parts[2]==='import' && parts[3]){
      let id;try{id=decodeURIComponent(parts[3]);}catch(_){return;}
      if(state.importId!==id){state.importId=id;void start({action:'inspect-copy',id});}
    }
  }
  function afterRender(root=global.document?.querySelector?.('#storage-manager')) {
    if(!root)return;state.root=root;
    if(!root.dataset.storageBound){
      root.dataset.storageBound='true';
      root.addEventListener('input',event=>{if(event.target.name==='path')state.path=event.target.value;});
      root.addEventListener('change',event=>{
        const target=event.target;
        if(target.name==='storage-mode'){state.mode=target.value;state.confirmed=false;}
        else if(target.dataset.storageProject){if(target.checked)state.selected.add(target.dataset.storageProject);else state.selected.delete(target.dataset.storageProject);state.confirmed=false;}
        else if(target.dataset.storageResolution){state.resolutions[target.dataset.storageResolution]=target.value;state.confirmed=false;}
        else if(target.hasAttribute?.('data-storage-globals')){state.includeGlobals=target.checked;state.confirmed=false;}
        else if(target.hasAttribute?.('data-storage-confirm'))state.confirmed=target.checked;
        else return;render();
      });
      root.addEventListener('submit',event=>{if(!event.target.matches?.('[data-storage-form]'))return;event.preventDefault();if(state.busy)return;if([...state.pending.values()].some(request=>request.uncertain)){state.message=t('pending','Результат предыдущего запроса не подтверждён. Проверьте и повторите тот же запрос.','The previous request is not confirmed. Check and retry the same request.');render();return;}state.sourcePath=state.path.trim();void start({action:'inspect-folder',path:state.sourcePath});});
      root.addEventListener('click',event=>{const button=event.target.closest?.('[data-storage-action]');if(button)void action(button.dataset.storageAction,button).catch(error=>{state.message=error.message;render();});});
    }
    readRoute();void load().catch(error=>{state.message=error.message;render();});
    if(state.timer)global.clearTimeout(state.timer);
    const poll=()=>{state.timer=global.setTimeout(async()=>{if(state.root!==root || root.isConnected===false)return;try{await load();}catch(_){if(state.pending.size)state.message=t('reconnecting','Состояние операции уточняется. Повторная проверка продолжится после восстановления связи.','Checking operation status. Polling will continue when the connection returns.');render();}poll();},1500);};poll();
  }
  global.HubStorageUI={page:()=>`<section id="storage-manager" class="projects-page">${content()}</section>`,afterRender,openPrepared:async id=>{state.importId=id;await start({action:'inspect-copy',id});},preview:value=>{setPreview(value,value.copyId);render();},summary};
  global.addEventListener?.('hub-operations-changed',event=>{void (async()=>{for(const request of [...state.pending.values()]){const row=event.detail?.operations?.find(row=>row.requestId===request.body.requestId);if(row)await handleResult(row,request);}render();})();});
  global.HubI18n?.onChange?.(render);
})(typeof window==='undefined'?globalThis:window);
