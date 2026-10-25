"use strict";
const settingsDefaults = {
  git: {autoCommit: false, commitOn: 'stage-and-task'},
  tasks: {columns: ['title', 'type', 'priority', 'status', 'progress', 'estimate', 'created', 'updated', 'actions'], sort: 'created', overviewSort: 'created', showCompleted: true, showEpicsOnOverview: false, showUpcomingOnOverview: true},
  viewer: {wrapLines: true, showSourceDetails: false},
  architecture: {model: '', depth: 1, representation: 'symbols', agentSummaries: true, descriptionDetail: 'standard'},
};
const settingsDrafts = new Map();
const versionControlState = {project:'',loading:false,loaded:false,error:'',value:null,token:0};
function versionControlText(ru,en) { return globalThis.HubI18n?.locale === 'en' ? en : ru; }
function versionControlStatus(value) {
  if (!value) return versionControlText('Неизвестно','Unknown');
  if (value.available === true) return versionControlText('Доступен','Available');
  return ({no_repository:versionControlText('Репозиторий не найден','Repository not found'),client_unavailable:versionControlText('Клиент Git недоступен','Git client unavailable'),repository_unavailable:versionControlText('Репозиторий недоступен','Repository unavailable'),workspace_required:versionControlText('Нужна папка проекта','Project folder required'),workspace_unavailable:versionControlText('Папка проекта недоступна','Project folder unavailable')}[value.status] || versionControlText('Неизвестно','Unknown'));
}
function versionControlPanel(controls='') {
  const entry=versionControlState, value=entry.project===activeProject?entry.value:null, provider=value?.provider;
  const providerLabel=provider==='git'?'Git':provider===null?versionControlText('Git не обнаружен','Git not detected'):versionControlText('Неизвестно','Unknown');
  const clientLabel=value?.client?.available===true?versionControlText('Клиент Git доступен','Git client available'):value?.client?.available===false?versionControlText('Клиент Git недоступен','Git client unavailable'):versionControlText('Статус клиента неизвестен','Client status unknown');
  const detail=entry.loading?versionControlText('Загрузка сведений о контроле версий…','Loading version-control details…'):entry.error?versionControlText('Не удалось загрузить сведения о контроле версий.','Could not load version-control details.'):versionControlText('Задачи и документы работают и без контроля версий. Сейчас поддерживается Git.','Tasks and documents work without version control. Git is currently supported.');
  return `<section class="card version-control-settings" data-version-control-status="${escape(value?.status || 'unknown')}"><div class="section-head"><div><h2>${versionControlText('Контроль версий','Version control')}</h2><p class="muted">${detail}</p></div><span class="scope">${versionControlStatus(value)}</span></div><div class="information"><p>${versionControlText('Система:','System:')} <strong>${providerLabel}</strong></p><p>${versionControlText('Клиент Git:','Git client:')} <strong>${clientLabel}</strong></p><p>${versionControlText('Папка исходников:','Source folder:')} <code>${escape(value?.workspaceRoot || '—')}</code></p><p>${versionControlText('Папка репозитория:','Repository folder:')} <code>${escape(value?.repositoryRoot || '—')}</code></p></div><button type="button" data-version-control-refresh ${entry.loading?'disabled':''}>${versionControlText('Обновить сведения','Refresh details')}</button>${controls}</section>`;
}
async function loadVersionControl(project, force=false) {
  if (!project || (versionControlState.loading && versionControlState.project===project) || (!force && versionControlState.loaded && versionControlState.project===project)) return;
  const token=++versionControlState.token;versionControlState.project=project;versionControlState.value=null;versionControlState.loaded=false;versionControlState.loading=true;versionControlState.error='';
  try { const response=await fetch('/api/version-control?project='+encodeURIComponent(project),{cache:'no-store'}); const value=await response.json(); if(!response.ok || !value || typeof value!=='object')throw Error('version control unavailable'); if(token!==versionControlState.token || activeProject!==project)return; versionControlState.value=value;versionControlState.loaded=true; }
  catch(error){if(token===versionControlState.token && activeProject===project){versionControlState.value=null;versionControlState.loaded=true;versionControlState.error=error.message || 'version control unavailable';}}
  finally{if(token===versionControlState.token){versionControlState.loading=false;if(typeof route==='function'&&route()[0]==='settings')render({background:true});}}
}
globalThis.HubVersionControlUI={afterRender(){if(typeof route==='function'&&route()[0]==='settings'&&!route()[1])void loadVersionControl(activeProject);},refresh(project){return loadVersionControl(project,true);},panel:versionControlPanel};
document.addEventListener('click', event => {
  if(event.target.closest?.('[data-version-control-refresh]')) void loadVersionControl(activeProject,true);
});
function persistSettingsDraft(project, draft) {
  try {
    const key = `project-hub-settings-draft:${project}`;
    if (draft.dirty) sessionStorage.setItem(key, JSON.stringify({value:draft.value, expected:draft.expected, dirty:true}));
    else sessionStorage.removeItem(key);
  } catch { /* Storage is optional. */ }
}
function projectSettings(envelope = state?.settings) {
  return Object.fromEntries(Object.entries(settingsDefaults).map(([section, defaults]) => [section, {...defaults, ...envelope?.settings?.[section]}]));
}
function settingsDraft() {
  const envelope = state?.settings;
  let draft = settingsDrafts.get(activeProject);
  if (!draft) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(`project-hub-settings-draft:${activeProject}`) || 'null');
      if (saved?.dirty && saved.expected != null && saved.value?.git && saved.value?.tasks && saved.value?.viewer) {
        draft = {value:projectSettings({settings:saved.value}), expected:saved.expected, dirty:true, busy:false, message:''}; settingsDrafts.set(activeProject, draft);
      }
    } catch { /* Ignore invalid drafts. */ }
  }
  if (!draft || (!draft.dirty && !draft.busy && draft.expected !== envelope?.revision)) {
    draft = {value: projectSettings(), expected: envelope?.revision, dirty: false, busy: false, message: ''};
    settingsDrafts.set(activeProject, draft);
  }
  return draft;
}
function settingsButton(action, icon, label, disabled = false) {
  return `<button type="button" data-settings-action="${action}" ${disabled ? 'disabled' : ''}>${uiIcon(icon)}<span>${label}</span></button>`;
}
function settingsActions(draft) {
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.86338d9df854",{v0:(escape(draft.message || (draft.dirty?(globalThis.HubI18n?.t?.("settings.3f2236e45f36") ?? 'Есть несохранённые изменения проекта'):(globalThis.HubI18n?.t?.("settings.65867175d00e") ?? 'Проектные настройки без изменений')))),v1:(draft.busy||!draft.dirty?'disabled':''),v2:(!draft.dirty||draft.busy||draft.expected==null?'disabled':'')}) : `<div class="actions settings-actions"><span class="status" role="status" id="settings-status">${escape(draft.message || (draft.dirty?(globalThis.HubI18n?.t?.("settings.3f2236e45f36") ?? 'Есть несохранённые изменения проекта'):(globalThis.HubI18n?.t?.("settings.65867175d00e") ?? 'Проектные настройки без изменений')))}</span><button type="button" data-settings-action="cancel" ${draft.busy||!draft.dirty?'disabled':''}>Отменить</button><button class="primary" type="button" data-settings-action="save" ${!draft.dirty||draft.busy||draft.expected==null?'disabled':''}>Сохранить настройки проекта</button></div>`);
}
function settingsAuditRow(entry) {
  const sections = {git:'Git', tasks:(globalThis.HubI18n?.t?.("settings.03cc1c2d5ac2") ?? 'Задачи'), viewer:(globalThis.HubI18n?.t?.("settings.891b41a9523b") ?? 'Просмотр документов'), architecture:(globalThis.HubI18n?.t?.("settings.1898e1901dcd") ?? 'Архитектура и код')};
  const timestamp = entry.at || '';
  const formatted = Number.isFinite(Date.parse(timestamp))
    ? new Intl.DateTimeFormat((globalThis.HubI18n?.locale==='en'?'en-GB':'ru-RU'), {dateStyle:'short', timeStyle:'short'}).format(new Date(timestamp))
    : (globalThis.HubI18n?.t?.("settings.732063f16e43") ?? 'Дата не указана');
  const actor = entry.actor === 'local-user' ? (globalThis.HubI18n?.t?.("settings.2a5c42af7c00") ?? 'Пользователь') : entry.actor || (globalThis.HubI18n?.t?.("settings.033a80284b24") ?? 'Автор не указан');
  const affected = (entry.sections || []).map(section => sections[section]).filter(Boolean).join(', ');
  return `<li><time datetime="${escape(timestamp)}" title="${escape(timestamp)}">${escape(formatted)}</time><span class="settings-audit-actor">${escape(actor)}</span><span>${escape(affected || (globalThis.HubI18n?.t?.("settings.d367c360b8c5") ?? 'Настройки проекта'))}</span></li>`;
}
function settingsHeader(section='') {
  const header = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.f84257068b68",{v0:(settingsTabs(false,['architecture','agents','instructions'].includes(section)?(section==='instructions'?'agents':section):''))}) : `<div class="eyebrow">PROJECT HUB</div><h1>Настройки</h1><p class="intro">Параметры проекта, ваш интерфейс и правила работы с Hub.</p>${settingsTabs(false,['architecture','agents','instructions'].includes(section)?(section==='instructions'?'agents':section):'')}`);
  return header + (!section ? globalThis.HubSetupWizardUI?.entry?.() || '' : '');
}
let interfaceLanguageBusy = false, interfaceLanguageMessage = '';
function interfaceSettingsPanel() {
  const language = globalThis.HubI18n?.locale || 'ru';
  const panel = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.a74dbbb4f108",{v0:(interfaceLanguageBusy?'disabled':''),v1:(language==='ru'?'selected':''),v2:(language==='en'?'selected':''),v3:(escape(interfaceLanguageMessage))}) : `<section class="card"><div class="section-head"><div><h2>Язык Project Hub</h2><p class="muted">Общий язык интерфейса этой установки. Тексты задач, документов и других данных не переводятся.</p></div><span class="scope">Интерфейс Hub</span></div><div class="field"><label for="hub-interface-language">Язык интерфейса</label><select id="hub-interface-language" ${interfaceLanguageBusy?'disabled':''}><option value="ru" ${language==='ru'?'selected':''}>Русский</option><option value="en" ${language==='en'?'selected':''}>Английский</option></select><p role="status">${escape(interfaceLanguageMessage)}</p></div></section>`);
  return panel + storageFolderSettingsPanel() + (globalThis.HubRuntimeUI?.card() || '');
}

const storageFolderSettings = {loaded:false,loading:false,value:null,dataHome:'',backupHome:'',dirty:false,busy:false,message:'',preview:null,pending:null,operationId:'',handled:new Set()};
const storageFolderDraftKey='project-hub-folder-settings-draft';
try {
  const saved=JSON.parse(globalThis.sessionStorage?.getItem(storageFolderDraftKey) || 'null');
  if(saved && typeof saved.dataHome==='string' && typeof saved.backupHome==='string')Object.assign(storageFolderSettings,{dataHome:saved.dataHome,backupHome:saved.backupHome,dirty:Boolean(saved.dirty),pending:saved.pending?.requestId?saved.pending:null,operationId:saved.operationId || ''});
}catch(_){/* A malformed session draft never changes server configuration. */}
function persistStorageFolderDraft() {
  const entry=storageFolderSettings;
  try {globalThis.sessionStorage?.setItem(storageFolderDraftKey,JSON.stringify({dataHome:entry.dataHome,backupHome:entry.backupHome,dirty:entry.dirty,pending:entry.pending,operationId:entry.operationId}));}catch(_){/* Session storage is optional. */}
}
function folderSettingsText(key,ru,en) {
  const fallback = globalThis.HubI18n?.locale === 'en' ? en : ru;
  return globalThis.HubI18n?.t?.(`folderSettings.${key}`,fallback) || fallback;
}
function storageFolderSettingsPanel() {
  const entry=storageFolderSettings, disabled=entry.busy || Boolean(entry.pending) || !entry.loaded || entry.value?.available===false;
  const path=(value,kind)=>globalThis.HubLocalFiles?.pathLink(value,kind) || `<code>${escape(value || '—')}</code>`;
  const operationParts=(globalThis.location?.hash || '').replace(/^#/,'').split('/');
  const explicitDetails=operationParts[0]==='settings' && operationParts[1]==='operation';
  let detailId=explicitDetails ? '' : entry.operationId;
  if(operationParts[0]==='settings' && operationParts[1]==='operation')try{detailId=decodeURIComponent(operationParts[2] || '');}catch(_){detailId='';}
  return `<section class="card hub-folder-settings" id="hub-folder-settings"><div class="section-head"><div><h2>${folderSettingsText('title','Хранилище и резервные копии','Storage and backups')}</h2><p class="muted">${folderSettingsText('scope','Папки относятся ко всей установке Hub. Выбор папки заполняет поле; изменение применяется отдельным действием.','These folders apply to the entire Hub installation. Choosing a folder fills the field; a separate action applies the change.')}</p></div><span class="scope">${folderSettingsText('installation','Вся установка','Entire installation')}</span></div><form data-storage-folders data-operation-form><div class="field"><div><label for="hub-data-folder">${folderSettingsText('data','Папка данных Hub','Hub data folder')}</label><p>${folderSettingsText('dataHelp','Все проекты, задачи, история, документы и вложения этой установки','All projects, tasks, history, documents and attachments in this installation')}</p></div><div><div class="hub-folder-field"><input type="text" id="hub-data-folder" name="dataHome" value="${escape(entry.dataHome)}" required ${disabled?'disabled':''}>${globalThis.HubLocalFiles?.chooser('data','#hub-data-folder',disabled) || ''}</div>${path(entry.value?.dataHome,'data')}</div></div><div class="field"><div><label for="hub-backup-folder">${folderSettingsText('backups','Папка резервных копий','Backup folder')}</label><p>${folderSettingsText('backupHelp','Архивы для восстановления. Они хранятся отдельно от рабочих данных','Archives for recovery. They are stored separately from active data')}</p></div><div><div class="hub-folder-field"><input type="text" id="hub-backup-folder" name="backupHome" value="${escape(entry.backupHome)}" required ${disabled?'disabled':''}>${globalThis.HubLocalFiles?.chooser('backups','#hub-backup-folder',disabled) || ''}</div>${path(entry.value?.backupHome,'backups')}</div></div><p class="muted">${folderSettingsText('serverComputer','Выбор и открытие папок выполняются на компьютере сервера Hub. При недоступном файловом менеджере вы можете скопировать путь.','Folder selection and opening run on the Hub server computer. If its file manager is unavailable, you can copy the path.')}</p>${entry.value?.available===false?`<p class="notice">${folderSettingsText('unavailable','Изменение папок недоступно в этом режиме запуска. Фактические пути показаны в сведениях о сервере.','Folder changes are unavailable in this launch mode. Server details show the active paths.')}</p>`:''}<p role="status" data-storage-folders-status>${escape(globalThis.backupStatus?.feedback ? globalThis.backupStatus.feedback(entry.pending?.requestId || entry.operationId,entry.message) : entry.message)}</p><p role="status" data-local-files-status></p>${entry.preview?`<section class="storage-import-summary"><h3>${folderSettingsText('review','Проверьте изменение папок','Review folder changes')}</h3><dl class="projects-details"><dt>${folderSettingsText('data','Папка данных Hub','Hub data folder')}</dt><dd><code>${escape(entry.preview.dataHome || entry.dataHome)}</code></dd><dt>${folderSettingsText('backups','Папка резервных копий','Backup folder')}</dt><dd><code>${escape(entry.preview.backupHome || entry.backupHome)}</code></dd></dl><p>${folderSettingsText('moveHelp','Hub проверит назначение, скопирует согласованный снимок данных, сохранит прежнюю папку и проверит новый запуск. При ошибке прежние данные и настройки будут восстановлены. Непустое назначение не перезаписывается.','Hub checks the destination, copies a consistent data snapshot, preserves the old folder and checks the new launch. Errors restore the previous data and settings. A nonempty destination is never overwritten.')}</p><p>${folderSettingsText('archivesRemain','Существующие архивы останутся в прежней папке. Следующие резервные копии сохранятся в выбранную папку; прежние архивы не удаляются.','Existing archives remain in their previous folder. Future backups use the selected folder; earlier archives are not deleted.')}</p><button type="button" class="primary" data-storage-folders-action="apply" ${entry.busy?'disabled':''}>${folderSettingsText('apply','Применить изменение папок','Apply folder changes')}</button><button type="button" data-storage-folders-action="dismiss">${folderSettingsText('cancel','Отменить','Cancel')}</button></section>`:`<button type="submit" ${disabled || !entry.dirty?'disabled':''}>${folderSettingsText('check','Проверить изменение папок','Check folder changes')}</button>`}${entry.pending?`<button type="button" data-storage-folders-action="retry" data-operation-retry="${escape(entry.pending.requestId)}" ${entry.busy?'disabled':''}>${folderSettingsText('retry','Проверить и повторить тот же запрос','Check and retry the same request')}</button>`:''}</form>${detailId ? globalThis.backupStatus?.details(detailId,{transient:!explicitDetails}) || '' : ''}${globalThis.backupStatus?.history?.('settings') || ''}</section>`;
}
function patchStorageFolderSettings() {
  const root=document.getElementById?.('hub-folder-settings');if(!root)return;
  const html=storageFolderSettingsPanel();
  const body=html.slice(html.indexOf('>')+1,html.lastIndexOf('</section>'));
  if(globalThis.HubLiveUI)globalThis.HubLiveUI.patch(root,body);else root.innerHTML=body;
  globalThis.backupStatus?.afterRender();
}
async function storageFoldersApi(body) {
  let response;try{response=await fetch('/api/v1/storage',{cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});}catch(error){error.outcomeUnknown=!!body;throw error;}
  let value;try{value=await response.json();}catch(error){error.outcomeUnknown=!!body;throw error;}
  if(!response.ok){const error=Error(value.error || folderSettingsText('failed','Не удалось изменить папки.','Could not change folders.'));error.outcomeUnknown=!!body && response.status>=500;throw error;}
  return value;
}
async function loadStorageFolderSettings() {
  const entry=storageFolderSettings;if(entry.loading)return;entry.loading=true;
  try{
    const result=await storageFoldersApi(),value=result.folderSettings;
    if(!value || typeof value.dataHome!=='string' || typeof value.backupHome!=='string')throw Error(folderSettingsText('invalid','Сервер не вернул настройки папок.','The server did not return folder settings.'));
    entry.value=value;entry.loaded=true;
    if(!entry.dirty){entry.dataHome=value.dataHome;entry.backupHome=value.backupHome;}
  }catch(error){entry.message=globalThis.HubI18n?.error?.(error) || error.message;}
  finally{entry.loading=false;patchStorageFolderSettings();}
}
async function submitStorageFolders(apply=false,retry=false) {
  const entry=storageFolderSettings;if(entry.busy || entry.pending && !retry)return;
  const uuid=globalThis.crypto?.randomUUID?.().replace(/-/g,'') || `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`.padEnd(32,'0').slice(0,32);
  const body=retry && entry.pending ? entry.pending : {action:'change-folders',dataHome:entry.dataHome.trim(),backupHome:entry.backupHome.trim(),confirmed:apply,requestId:uuid,origin:{section:'settings'}};
  if(apply && !retry && !window.confirm(folderSettingsText('confirm','Применить показанные папки? Прежняя папка данных и существующие архивы сохранятся.','Apply the shown folders? The previous data folder and existing archives are preserved.')))return;
  entry.busy=true;entry.message='';if(body.confirmed){entry.pending=body;persistStorageFolderDraft();globalThis.backupStatus?.begin(body);}patchStorageFolderSettings();
  try{
    const result=await storageFoldersApi(body);
    if(!body.confirmed){
      const preview=result.preview || result.validation;
      if(!preview || preview.valid===false)throw Error(folderSettingsText('invalidPreview','Сервер не подтвердил допустимость выбранных папок.','The server did not confirm that the selected folders are valid.'));
      entry.preview={...preview,dataHome:body.dataHome,backupHome:body.backupHome};
    }else{
      if(!result.operation?.id || !['queued','running','succeeded','failed','interrupted'].includes(result.operation.status) || result.operation.requestId && result.operation.requestId!==body.requestId){const error=Error(folderSettingsText('invalidAck','Сервер не подтвердил операцию. Повторите тот же запрос.','The server did not confirm the operation. Retry the same request.'));error.outcomeUnknown=true;throw error;}
      entry.pending=null;entry.operationId=result.operation.id;entry.preview=null;entry.dirty=false;globalThis.backupStatus?.acknowledge(result.operation,body);void globalThis.backupStatus?.refresh();
    }
  }catch(error){
    entry.message=globalThis.HubI18n?.error?.(error) || error.message;
    if(body.confirmed && error.outcomeUnknown){entry.pending=body;globalThis.backupStatus?.uncertain(body);}else if(body.confirmed){entry.pending=null;globalThis.backupStatus?.reject(body,error);}
  }finally{entry.busy=false;persistStorageFolderDraft();patchStorageFolderSettings();}
}
document.addEventListener('input',event=>{
  if(!event.target.closest?.('[data-storage-folders]') || !['dataHome','backupHome'].includes(event.target.name))return;
  storageFolderSettings[event.target.name]=event.target.value;storageFolderSettings.dirty=true;storageFolderSettings.preview=null;storageFolderSettings.message='';
  persistStorageFolderDraft();
  const form=event.target.closest('[data-storage-folders]'),button=form.querySelector('button[type="submit"]');if(button)button.disabled=storageFolderSettings.busy;
});
document.addEventListener('submit',event=>{if(!event.target.matches?.('[data-storage-folders]'))return;event.preventDefault();void submitStorageFolders();});
document.addEventListener('click',event=>{
  const button=event.target.closest?.('[data-storage-folders-action]');if(!button || !['dismiss','apply','retry'].includes(button.dataset?.storageFoldersAction))return;
  if(button.dataset.storageFoldersAction==='dismiss'){storageFolderSettings.preview=null;patchStorageFolderSettings();}
  else void submitStorageFolders(true,button.dataset.storageFoldersAction==='retry');
});
globalThis.addEventListener?.('hub-operations-changed',event=>{
  for(const row of event.detail?.operations || []){
    if(row.action!=='change-folders' || !['succeeded','failed','interrupted'].includes(row.status) || storageFolderSettings.handled.has(row.id) || row.id!==storageFolderSettings.operationId && row.requestId!==storageFolderSettings.pending?.requestId)continue;
    storageFolderSettings.handled.add(row.id);storageFolderSettings.pending=null;
    if(row.status==='succeeded'){storageFolderSettings.dirty=false;storageFolderSettings.preview=null;storageFolderSettings.message=folderSettingsText('saved','Папки применены. Прежние данные и архивы сохранены.','Folder changes applied. Previous data and archives are preserved.');void loadStorageFolderSettings();void globalThis.HubRuntimeUI?.refresh?.();}
    else storageFolderSettings.message=row.error?.message || row.error || folderSettingsText('failed','Не удалось изменить папки.','Could not change folders.');
    persistStorageFolderDraft();patchStorageFolderSettings();
  }
});
document.addEventListener('change', async event => {
  if (event.target.id !== 'hub-interface-language' || interfaceLanguageBusy) return;
  const language = event.target.value;
  interfaceLanguageBusy = true; interfaceLanguageMessage = '';
  try {
    await window.HubI18n.save(language);
    interfaceLanguageMessage = window.HubI18n.t('i18n.saved');
  } catch (error) { interfaceLanguageMessage = (globalThis.HubI18n?.error?.(error) ?? error.message); }
  finally {
    interfaceLanguageBusy = false;
    if (route()[0] === 'settings') render({background:true});
  }
});
function settingsPage() {
  if (typeof route === 'function' && ['agents','instructions'].includes(route()[1])) return agentConnectionsSettingsPage();
  if (typeof route === 'function' && route()[1] === 'architecture') return architectureSettingsPage();
  if (!state) return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.f9b7aff3a66f",{v0:(settingsHeader()),v1:(interfaceSettingsPanel())}) : `<div class="settings-page settings-design">${settingsHeader()}${interfaceSettingsPanel()}<p>Для настройки проекта добавьте его в разделе «Проекты».</p></div>`);
  const draft=settingsDraft(),value=draft.value,history=state?.settings?.history||[];
  const menu=typeof hubMenuPreference==='string'?hubMenuPreference:'auto';
  const vcsAvailable=versionControlState.project===activeProject && versionControlState.loaded && !versionControlState.loading && !versionControlState.error && versionControlState.value?.available===true;
  const sorts=[['created',(globalThis.HubI18n?.t?.("settings.10d04c1c3b04") ?? 'По дате создания · новые')],['created-oldest',(globalThis.HubI18n?.t?.("settings.461c83c1bd68") ?? 'По дате создания · старые')],['updated',(globalThis.HubI18n?.t?.("settings.28c18c8dfd24") ?? 'Недавно обновлённые')],['priority',(globalThis.HubI18n?.t?.("settings.8741673244ca") ?? 'По приоритету')],['status',(globalThis.HubI18n?.t?.("settings.682ade53d14c") ?? 'По статусу')],['progress',(globalThis.HubI18n?.t?.("settings.f2932d892ad9") ?? 'Сначала незавершённые')],['title',(globalThis.HubI18n?.t?.("settings.ca87c2180268") ?? 'По названию')]];
  const sortOptions=key=>sorts.map(([id,label])=>`<option value="${id}" ${value.tasks[key]===id?'selected':''}>${label}</option>`).join('');
  const commitOptions=[['stage-and-task',(globalThis.HubI18n?.t?.("settings.59ea9ad3a2d7") ?? 'При завершении этапа и задачи')],['stage',(globalThis.HubI18n?.t?.("settings.1edc55352500") ?? 'При завершении этапа')],['task',(globalThis.HubI18n?.t?.("settings.9f018a1d67a2") ?? 'При завершении задачи')]].map(([id,label])=>`<option value="${id}" ${value.git.commitOn===id?'selected':''}>${label}</option>`).join('');
  const page = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.ffee6084558f",{v0:(escape(activeProject)),v1:(settingsHeader()),v2:(interfaceSettingsPanel()),v3:(menu==='auto'?'selected':''),v4:(menu==='compact'?'selected':''),v5:(escape(typeof hubMenuStatus==='function'?hubMenuStatus():'')),v6:(draft.busy || draft.expected==null?'disabled':''),v7:(value.git.autoCommit?'checked':''),v8:(!value.git.autoCommit?'disabled':''),v9:(commitOptions),v10:(sortOptions('sort')),v11:(value.tasks.showCompleted?'checked':''),v12:(taskTableColumns.map(([id,label])=>`<label class="check"><input type="checkbox" id="setting-column-${id}" data-setting-column="${id}" ${value.tasks.columns.includes(id)?'checked':''} ${id==='title'?'disabled':''}><span>${label}</span></label>`).join('')),v13:(sortOptions('overviewSort')),v14:(value.tasks.showUpcomingOnOverview?'checked':''),v15:(value.tasks.showEpicsOnOverview?'checked':''),v16:(value.viewer.wrapLines?'checked':''),v17:(value.viewer.showSourceDetails?'checked':''),v18:(settingsActions(draft)),v19:(history.length?`<ol class="settings-history">${history.slice(-10).reverse().map(settingsAuditRow).join('')}</ol>`:(globalThis.HubI18n?.t?.("settings.504edf34b123") ?? '<p class="history">Изменений пока нет.</p>')),v20:(['git','tasks','viewer'].map(id=>settingsButton('reset-'+id,'reopen',{git:(globalThis.HubI18n?.t?.("settings.171ad2031275") ?? 'Сбросить Git'),tasks:(globalThis.HubI18n?.t?.("settings.f37fd0df5592") ?? 'Сбросить задачи'),viewer:(globalThis.HubI18n?.t?.("settings.0427f52ddb36") ?? 'Сбросить просмотр документов')}[id],draft.busy)).join(''))}) : `<div class="settings-page settings-design" data-settings-project="${escape(activeProject)}">${settingsHeader()}${interfaceSettingsPanel()}
<section class="card"><div class="section-head"><div><h2>Ваш интерфейс</h2><p class="muted">Вид Hub на этом устройстве</p></div><span class="scope">Лично · этот браузер</span></div>
<div class="field"><div><label for="setting-menu-mode">Основное меню</label><p id="menu-help">При узком окне меню всегда показывает иконки. На широком экране можно оставить этот же вид.</p></div><div><select id="setting-menu-mode" aria-describedby="menu-help menu-preference-status"><option value="auto" ${menu==='auto'?'selected':''}>Автоматически</option><option value="compact" ${menu==='compact'?'selected':''}>Только иконки</option></select><p id="menu-preference-status" role="status">${escape(typeof hubMenuStatus==='function'?hubMenuStatus():'')}</p></div></div>
<p>Чтобы вернуть подписи на широком экране, выберите «Автоматически».</p></section>
<fieldset class="settings-project-fields" ${draft.busy || draft.expected==null?'disabled':''}>
<section class="card"><div class="section-head"><h2>Контрольные точки Git</h2><span class="scope">Проект · Project Hub</span></div>
<div class="field"><div><label for="setting-git-autoCommit">Автоматические коммиты</label><p id="git-help">Сохранять проверенные изменения при завершении работы. Настройка действует для агентов этого проекта.</p></div><label class="check"><input id="setting-git-autoCommit" data-setting="git.autoCommit" type="checkbox" ${value.git.autoCommit?'checked':''} ${vcsAvailable?'':'disabled'} aria-describedby="git-help"><span>Создавать коммиты</span></label></div>
<div class="field"><div><label for="setting-git-commitOn">Когда создавать коммит</label><p>Выберите момент сохранения завершённого результата.</p></div><select id="setting-git-commitOn" data-setting="git.commitOn" ${!value.git.autoCommit||!vcsAvailable?'disabled':''}>${commitOptions}</select></div>
<details><summary>Что входит в контрольную точку</summary><p>Только проверенные изменения в области работы. Публикация в удалённый репозиторий требует отдельного действия.</p></details></section>
<div class="two"><section class="card"><div class="section-head"><h2>Список задач</h2><span class="scope">Проект</span></div>
<div class="field"><label for="setting-tasks-sort">Сортировка по умолчанию</label><p>Применяется, пока вы не выбрали личный порядок в списке.</p><select id="setting-tasks-sort" data-setting="tasks.sort">${sortOptions('sort')}</select></div>
<label class="check"><input id="setting-tasks-showCompleted" data-setting="tasks.showCompleted" type="checkbox" ${value.tasks.showCompleted?'checked':''}><span>Показывать завершённые и отменённые<small>Общий стартовый вид списка задач.</small></span></label>
<details><summary>Столбцы списка</summary><div class="checks">${taskTableColumns.map(([id,label])=>`<label class="check"><input type="checkbox" id="setting-column-${id}" data-setting-column="${id}" ${value.tasks.columns.includes(id)?'checked':''} ${id==='title'?'disabled':''}><span>${label}</span></label>`).join('')}</div></details>
<details><summary>Ваши настройки списка</summary><p>Личный выбор в таблице имеет приоритет над значениями проекта.</p><button type="button" data-settings-action="personal-reset">Вернуть настройки проекта для списка и обзора</button></details></section>
<section class="card"><div class="section-head"><h2>Обзор проекта</h2><span class="scope">Проект</span></div><p>Блок «Текущие задачи» на главной странице.</p>
<div class="field"><label for="setting-tasks-overviewSort">Сортировка по умолчанию</label><p>Порядок незавершённых задач на обзоре.</p><select id="setting-tasks-overviewSort" data-setting="tasks.overviewSort">${sortOptions('overviewSort')}</select></div>
<label class="check"><input id="setting-tasks-showUpcomingOnOverview" data-setting="tasks.showUpcomingOnOverview" type="checkbox" ${value.tasks.showUpcomingOnOverview?'checked':''}><span>Показывать предстоящие задачи<small>Запланированные задачи и очередь.</small></span></label><br><label class="check"><input id="setting-tasks-showEpicsOnOverview" data-setting="tasks.showEpicsOnOverview" type="checkbox" ${value.tasks.showEpicsOnOverview?'checked':''}><span>Показывать эпики<small>Крупные направления рядом с обычными задачами.</small></span></label></section></div>
<section class="card" style="margin-top:16px"><div class="section-head"><h2>Просмотр документов</h2><span class="scope">Значения проекта</span></div>
<div class="field"><div><label for="setting-viewer-wrapLines">Перенос строк</label><p>Длинные строки подстраиваются под ширину просмотрщика.</p></div><label class="check"><input id="setting-viewer-wrapLines" data-setting="viewer.wrapLines" type="checkbox" ${value.viewer.wrapLines?'checked':''}><span>Переносить строки</span></label></div>
<div class="field"><div><label for="setting-viewer-showSourceDetails">Сведения об источнике</label><p>Показывать происхождение документа при открытии.</p></div><label class="check"><input id="setting-viewer-showSourceDetails" data-setting="viewer.showSourceDetails" type="checkbox" ${value.viewer.showSourceDetails?'checked':''}><span>Показывать сведения</span></label></div></section>
</fieldset>${settingsActions(draft)}<div><details data-key="settings-history"><summary>Последние изменения проекта</summary>${history.length?`<ol class="settings-history">${history.slice(-10).reverse().map(settingsAuditRow).join('')}</ol>`:(globalThis.HubI18n?.t?.("settings.504edf34b123") ?? '<p class="history">Изменений пока нет.</p>')}</details><details data-key="settings-reset"><summary>Восстановить значения из комплекта</summary>${['git','tasks','viewer'].map(id=>settingsButton('reset-'+id,'reopen',{git:(globalThis.HubI18n?.t?.("settings.171ad2031275") ?? 'Сбросить Git'),tasks:(globalThis.HubI18n?.t?.("settings.f37fd0df5592") ?? 'Сбросить задачи'),viewer:(globalThis.HubI18n?.t?.("settings.0427f52ddb36") ?? 'Сбросить просмотр документов')}[id],draft.busy)).join('')}</details></fieldset> </div>`);
  const controls = `<div class="field"><div><label for="setting-git-autoCommit">${versionControlText('Автоматические коммиты','Automatic commits')}</label><p id="git-help">${versionControlText('Сохранять проверенные изменения при завершении работы. Без доступного репозитория настройка сохраняется, но коммиты не создаются.','Save verified changes when work completes. The preference is preserved while the repository is unavailable; no commits are created.')}</p></div><label class="check"><input id="setting-git-autoCommit" data-setting="git.autoCommit" type="checkbox" ${value.git.autoCommit?'checked':''} ${vcsAvailable?'':'disabled'} aria-describedby="git-help"><span>${versionControlText('Создавать коммиты','Create commits')}</span></label></div><div class="field"><div><label for="setting-git-commitOn">${versionControlText('Когда создавать коммит','When to create a commit')}</label><p>${versionControlText('Только проверенные изменения в области работы. Публикация в удалённый репозиторий выполняется отдельно.','Only verified changes within the reserved work scope. Publishing to a remote repository is a separate action.')}</p></div><select id="setting-git-commitOn" data-setting="git.commitOn" ${!value.git.autoCommit||!vcsAvailable?'disabled':''}>${commitOptions}</select></div>`;
  // Replace the legacy translated Git card by its stable control ID. Keep the
  // existing locale templates for the unrelated project preferences.
  const controlAt=page.indexOf('id="setting-git-autoCommit"');
  const sectionAt=page.lastIndexOf('<section', controlAt), endAt=page.indexOf('</section>',controlAt);
  return sectionAt>=0 && endAt>=0 ? page.slice(0,sectionAt)+versionControlPanel(controls)+page.slice(endAt+10) : page;
}
function settingsCopy(ru, en) { return globalThis.HubI18n?.locale === 'en' ? en : ru; }
function agentSettingsSection() {
  const parts = typeof route === 'function' ? route() : [];
  if (parts[1] === 'instructions') return 'rules';
  return ['apps','models','rules'].includes(parts[2]) ? parts[2] : 'apps';
}
function agentConnectionsSettingsPage() {
  const section = agentSettingsSection(), parts = typeof route === 'function' ? route() : [];
  const connectionId = parts[3] || '';
  const navigation = [['apps',settingsCopy('Приложения','Applications')],['models',settingsCopy('Запросы к моделям','Model requests')],['rules',settingsCopy('Правила работы','Work rules')]];
  const content = section === 'models' ? globalThis.HubAgentProvidersUI?.card() || ''
    : section === 'rules' ? hubModernInstructionsPage()
    : globalThis.HubConnectionsUI?.page({connectionId,tab:parts[4] || 'status'}) || '';
  return `<div class="settings-page settings-design agent-settings-page">${settingsHeader('agents')}<div class="agent-settings-layout"><nav class="agent-settings-nav" aria-label="${settingsCopy('Настройки агентов','Agent settings')}">${navigation.map(([id,label])=>`<a href="#settings/agents/${id}" ${id===section?'aria-current="page"':''}>${label}</a>`).join('')}<p>${settingsCopy('Настройки этой установки Hub. Привязки к проектам управляются отдельно.','Settings for this Hub installation. Project bindings are managed separately.')}</p></nav><div class="agent-settings-content">${content}</div></div></div>`;
}
function architectureSettingsPage() {
  const header = settingsHeader('architecture');
  if (!state) return `<div class="settings-page settings-design">${header}<section class="card"><h2>${settingsCopy('Проект не выбран', 'No project selected')}</h2><p>${settingsCopy('Параметры описаний и представления кода относятся к конкретному проекту. Добавьте или выберите проект, чтобы изменить их.', 'Description and code-view preferences belong to a project. Add or select a project to edit them.')}</p><a href="#projects">${settingsCopy('Открыть проекты', 'Open Projects')}</a></section></div>`;
  const draft = settingsDraft(), value = draft.value.architecture;
  const details = [['brief',settingsCopy('Кратко','Brief')],['standard',settingsCopy('Стандартно','Standard')],['detailed',settingsCopy('Подробно','Detailed')]];
  const select = (key, choices) => `<select id="setting-architecture-${key}" data-setting="architecture.${key}">${choices.map(([id,label])=>`<option value="${id}" ${value[key]===id?'selected':''}>${label}</option>`).join('')}</select>`;
  return `<div class="settings-page settings-design" data-settings-project="${escape(activeProject)}">${header}<fieldset class="settings-project-fields" ${draft.busy||draft.expected==null?'disabled':''}><section class="card"><div class="section-head"><h2>${settingsCopy('Описания архитектуры','Architecture descriptions')}</h2><span class="scope">${settingsCopy('Проект','Project')}</span></div><div class="field"><div><label for="setting-architecture-descriptionDetail">${settingsCopy('Подробность описания','Description detail')}</label><p>${settingsCopy('Выберите объём объяснения для проекта и его подсистем. Эта настройка не выбирает модель.', 'Choose the level of detail for the project and its subsystems. This preference does not select a model.')}</p></div>${select('descriptionDetail',details)}</div><label class="check"><input type="checkbox" id="setting-architecture-agentSummaries" data-setting="architecture.agentSummaries" ${value.agentSummaries?'checked':''}><span>${settingsCopy('Запрашивать объяснения у модели','Request explanations from the model')}<small>${settingsCopy('Используется настроенный API-провайдер. Статический анализ исходников выполняется отдельно.', 'Uses the configured API provider. Static source analysis runs separately.')}</small></span></label></section><section class="card"><h2>${settingsCopy('Представление кода','Code view')}</h2><div class="field"><div><label for="setting-architecture-representation">${settingsCopy('Группировка элементов','Element grouping')}</label><p>${settingsCopy('Показывайте символы самостоятельно или внутри файлов, которым они принадлежат.', 'Show symbols independently or within the files that contain them.')}</p></div>${select('representation',[['symbols',settingsCopy('Символы','Symbols')],['symbols-in-files',settingsCopy('Символы и файлы','Symbols and files')]])}</div></section>${settingsActions(draft)}</fieldset></div>`;
}
let hubModernWorkflow = null, hubModernWorkflowAttempted = false, hubModernWorkflowEnvelope = null, hubModernWorkflowError = false;
const hubAgentInstructions = {envelope:null, text:'', expected:null, dirty:false, loading:false, attempted:false, busy:false, message:'', pending:null};
function restoreAgentInstructionsDraft() {
  try {
    const saved = JSON.parse(sessionStorage.getItem('project-hub-agent-instructions-draft') || 'null');
    if (saved?.dirty && typeof saved.text === 'string' && saved.expected != null) {
      let pending = null;
      if (typeof saved.pending?.body === 'string') {
        const payload = JSON.parse(saved.pending.body);
        if (payload.expected === saved.expected && payload.text === saved.text && saved.pending.text === saved.text) pending = {body:saved.pending.body,text:saved.pending.text};
      }
      Object.assign(hubAgentInstructions, {text:saved.text, expected:saved.expected, dirty:true, pending});
    }
  } catch { /* Storage is optional. */ }
}
restoreAgentInstructionsDraft();
function persistAgentInstructionsDraft() {
  try {
    if (hubAgentInstructions.dirty) sessionStorage.setItem('project-hub-agent-instructions-draft', JSON.stringify({text:hubAgentInstructions.text, expected:hubAgentInstructions.expected, dirty:true, ...(hubAgentInstructions.pending?{pending:hubAgentInstructions.pending}:{})}));
    else sessionStorage.removeItem('project-hub-agent-instructions-draft');
  } catch { /* The draft remains in memory. */ }
}
function isAgentSettingsRoute() { return typeof route === 'function' && route()[0] === 'settings' && ['agents','instructions'].includes(route()[1]) && agentSettingsSection() === 'rules'; }
function hubModernInstructionsPage() {
  const entry = {...hubAgentInstructions, expected:hubAgentInstructions.envelope?hubAgentInstructions.expected:null};
  const blocked = entry.busy || entry.loading || !!entry.pending;
  const status = entry.message || (entry.loading ? settingsCopy('Загрузка ваших правил…','Loading your rules…') : entry.dirty ? settingsCopy('Есть несохранённые дополнения','There are unsaved additions') : '');
  const original = hubModernWorkflow == null
    ? `<p>${settingsCopy('Загрузка инструкции…','Loading instructions…')}</p>`
    : hubModernWorkflowError ? `<p role="status">${settingsCopy('Не удалось загрузить инструкцию. Нажмите «Обновить», чтобы повторить загрузку.', 'Could not load the instructions. Click Refresh to retry.')}</p>` : hubInstructionMarkdown(hubModernWorkflow);
  const base = hubModernWorkflowEnvelope?.baseWorkflow;
  return `<div id="hub-modern-instructions" class="agent-work-rules"><section class="card"><div class="section-head"><div><h2>${settingsCopy('Правила работы агента','Agent work rules')}</h2><p>${settingsCopy('Приглашение передаёт полный текст правил и сохранённые дополнения. Правила обращены к агенту; их исходный язык и формулировки сохраняются.', 'An invitation provides the full rules and saved additions. The rules address the agent; their original language and wording are preserved.')}</p></div><span class="scope">${settingsCopy('Установка Hub','Hub installation')}</span></div><details data-agent-rules-details="effective"><summary>${settingsCopy('Полная инструкция для агента — оригинальный текст','Complete agent instructions — original text')}</summary>${original}${hubModernWorkflow!=null&&!hubModernWorkflowError?`<button type="button" data-agent-instructions-action="copy">${settingsCopy('Скопировать полную инструкцию','Copy the full instructions')}</button>`:''}</details>${typeof base==='string'&&base!==hubModernWorkflow?`<details data-agent-rules-details="base"><summary>${settingsCopy('Исходные правила без ваших дополнений','Original rules without your additions')}</summary>${hubInstructionMarkdown(base)}</details>`:''}<p class="agent-rules-consent">${settingsCopy('Постоянные правила в приложении сохраняются только с вашего явного согласия. До записи агент должен показать полный текст, точный файл назначения и область действия: один проект или всё приложение. Токен Hub и другие ключи в эти правила не включаются.', 'Persistent rules in the application are saved only with your explicit consent. Before writing, the agent must show the full text, exact destination file and scope: one project or the whole application. The Hub token and other credentials are excluded from these rules.')}</p><p>${settingsCopy('Если приложение не умеет настраивать себя, скопируйте инструкцию и настройте MCP вручную по подсказкам агента. Проверка нового чата показывает, доступны ли подключение и правила за пределами текущей беседы.', 'If the application cannot configure itself, copy the instructions and configure MCP manually using the agent’s guidance. Checking a new chat shows whether the connection and rules are available beyond the current conversation.')}</p></section><section class="card agent-custom-rules"><div class="section-head"><div><h2>${settingsCopy('Ваши дополнения к правилам','Your additional rules')}</h2><p id="agent-instructions-help">${settingsCopy('Эти дополнения хранятся в Hub и передаются с будущими приглашениями. Сохранение здесь не записывает файлы в клиенте. Уже подключённому агенту передайте обновлённые правила и подтвердите их назначение в приложении.', 'These additions are stored in Hub and supplied with future invitations. Saving here does not write client files. Give the updated rules to an already connected agent and confirm their destination in the application.')}</p></div><button type="button" data-agent-instructions-action="refresh" ${blocked?'disabled':''}>${settingsCopy('Обновить','Refresh')}</button></div><label for="hub-agent-instructions-text">${settingsCopy('Текст дополнений для агента','Additional instructions for the agent')}</label><textarea id="hub-agent-instructions-text" data-agent-instructions-text rows="12" maxlength="24000" aria-describedby="agent-instructions-help" ${blocked||!entry.envelope?'disabled':''}>${escape(entry.text)}</textarea><div class="actions"><p role="status" id="agent-instructions-status">${escape(status)}${entry.pending?` ${settingsCopy('Результат сохранения неизвестен. Повторите тот же запрос для подтверждения.','The save outcome is unknown. Retry the same request to confirm it.')}`:''}</p>${entry.pending?`<button type="button" data-agent-instructions-action="retry" ${entry.busy?'disabled':''}>${settingsCopy('Повторить сохранение','Retry saving')}</button>`:''}<button type="button" data-agent-instructions-action="cancel" ${blocked||!entry.dirty?'disabled':''}>${settingsCopy('Отменить дополнения','Discard additions')}</button><button type="button" data-agent-instructions-action="save" ${blocked||!entry.dirty||entry.expected==null||entry.text.length>24000?'disabled':''}>${settingsCopy('Сохранить дополнения в Hub','Save additions in Hub')}</button></div></section></div>`;
}
async function loadModernWorkflow() {
  if (hubModernWorkflowAttempted) return;
  hubModernWorkflowAttempted = true;
  try {
    const response = await fetch('/api/agent-workflow', {cache:'no-store'}), body = await response.json();
    if (!response.ok || typeof body.workflow !== 'string') throw Error('workflow unavailable');
    hubModernWorkflow = body.workflow; hubModernWorkflowEnvelope = body; hubModernWorkflowError = false;
  } catch { hubModernWorkflowError = true; hubModernWorkflow = settingsCopy('Не удалось загрузить инструкцию. Нажмите «Обновить», чтобы повторить загрузку.', 'Could not load the instructions. Click Refresh to retry.'); }
  if (isAgentSettingsRoute()) render({background:true});
}
async function loadAgentInstructions(force=false) {
  const entry = hubAgentInstructions;
  if (entry.loading || entry.busy || (!force && entry.attempted)) return;
  entry.loading = true; entry.attempted = true;
  try {
    const response = await fetch('/api/agent-instructions', {cache:'no-store'}), body = await response.json();
    if (!response.ok || typeof body?.text !== 'string' || typeof body?.revision !== 'string' || !body.revision) throw Error(settingsCopy('Не удалось загрузить ваши правила. Нажмите «Обновить», чтобы повторить.', 'Could not load your rules. Click Refresh to retry.'));
    entry.envelope = body;
    if (!entry.dirty && !entry.pending) { entry.text = body.text; entry.expected = body.revision; entry.message = ''; }
    else if (entry.expected !== body.revision) entry.message = settingsCopy('Правила изменились. Черновик сохранён; отмените его, чтобы прочитать актуальную версию.', 'The rules changed. Your draft is preserved; discard it to read the current version.');
  } catch { entry.message = settingsCopy('Не удалось загрузить ваши правила. Нажмите «Обновить», чтобы повторить.', 'Could not load your rules. Click Refresh to retry.'); }
  finally { entry.loading = false; if (isAgentSettingsRoute()) render({background:true}); }
}
async function submitAgentInstructions(retry=false) {
  const entry = hubAgentInstructions;
  if (entry.busy || entry.loading || (!retry && (entry.pending || !entry.envelope)) || (retry && !entry.pending) || entry.expected==null || entry.text.length>24000 || !entry.dirty) return;
  const operation = retry ? entry.pending : {body:JSON.stringify({expected:entry.expected,text:entry.text}),text:entry.text};
  entry.busy = true; entry.message = ''; if (isAgentSettingsRoute()) render({background:true});
  try {
    let response;
    try { response = await fetch('/api/agent-instructions', {method:'POST',headers:{'Content-Type':'application/json'},body:operation.body}); }
    catch { throw Object.assign(Error(settingsCopy('Не удалось подтвердить сохранение. Черновик сохранён.', 'Could not confirm saving. Your draft is preserved.')),{uncertain:true}); }
    let body; try { body = await response.json(); } catch { /* A missing acknowledgment remains uncertain. */ }
    if (!response.ok) throw Object.assign(Error(settingsCopy('Дополнения не сохранены. Черновик сохранён; обновите правила, чтобы проверить изменения.', 'The additions were not saved. Your draft is preserved; refresh the rules to check changes.')),{uncertain:response.status>=500});
    if (typeof body?.revision !== 'string' || !body.revision || body?.text !== operation.text) throw Object.assign(Error(settingsCopy('Сервер не подтвердил текст дополнений.', 'The server did not confirm the additions.')),{uncertain:true});
    entry.envelope = body; entry.text = body.text; entry.expected = body.revision; entry.dirty = false; entry.pending = null;
    entry.message = settingsCopy('Дополнения сохранены в Hub', 'Additions saved in Hub');
    hubModernWorkflowAttempted = false; await loadModernWorkflow();
  } catch (error) { entry.message = globalThis.HubI18n?.error?.(error) ?? error.message; if (error.uncertain || retry) entry.pending = operation; }
  finally { entry.busy = false; persistAgentInstructionsDraft(); if (isAgentSettingsRoute()) render({background:true}); }
}
document.addEventListener('input', event => {
  if (!event.target.matches?.('[data-agent-instructions-text]')) return;
  const entry = hubAgentInstructions;
  if (entry.busy || entry.loading || entry.pending || !entry.envelope) return;
  entry.text = event.target.value; entry.dirty = entry.text !== entry.envelope.text; entry.message = ''; persistAgentInstructionsDraft();
  const status = document.getElementById('agent-instructions-status');
  if (status) status.textContent = entry.text.length>24000 ? settingsCopy('Не более 24000 символов.', 'Use no more than 24000 characters.') : entry.dirty ? settingsCopy('Есть несохранённые дополнения','There are unsaved additions') : '';
  const save = document.querySelector('[data-agent-instructions-action="save"]'), cancel = document.querySelector('[data-agent-instructions-action="cancel"]');
  if (save) save.disabled = !entry.dirty || entry.text.length>24000 || entry.expected==null;
  if (cancel) cancel.disabled = !entry.dirty;
});
document.addEventListener('click', async event => {
  const button = event.target.closest?.('[data-agent-instructions-action]'), action = button?.dataset.agentInstructionsAction;
  if (!action) return;
  const entry = hubAgentInstructions;
  if (action === 'copy') {
    if (hubModernWorkflow == null || hubModernWorkflowError) return;
    try { await navigator.clipboard.writeText(hubModernWorkflow); button.textContent = settingsCopy('Скопировано','Copied'); }
    catch { const reader = button.closest('details'), content = reader?.querySelector('.hub-markdown') || reader?.querySelector('pre'); if (content) { const selection = globalThis.getSelection?.(), range = document.createRange?.(); if (selection && range) { range.selectNodeContents(content); selection.removeAllRanges(); selection.addRange(range); } } button.textContent = settingsCopy('Скопируйте текст вручную','Copy the text manually'); }
    return;
  }
  if (action === 'save') return submitAgentInstructions();
  if (action === 'retry') return submitAgentInstructions(true);
  if (entry.busy || entry.loading || entry.pending) return;
  if (action === 'cancel') { entry.dirty = false; entry.text = entry.envelope?.text || ''; entry.expected = entry.envelope?.revision ?? null; persistAgentInstructionsDraft(); }
  if (action === 'refresh' || action === 'cancel') { hubModernWorkflowAttempted = false; await Promise.allSettled([loadAgentInstructions(true),loadModernWorkflow()]); }
});
async function submitSettings(reset) {
  const project = activeProject, draft = settingsDraft();
  if (draft.busy || draft.expected == null) return;
  if (reset && !window.confirm((globalThis.HubI18n?.t?.("settings.e9e52973f0b7") ?? 'Сбросить настройки раздела? Несохранённые изменения остальных разделов останутся.'))) return;
  const body = reset ? {expected: draft.expected, reset} : {expected: draft.expected, patch: draft.value};
  draft.busy = true; draft.message = (globalThis.HubI18n?.t?.("settings.bd97450c8556") ?? 'Сохранение…'); render();
  try {
    const response = await fetch('/api/v1/settings?' + new URLSearchParams({project}), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const envelope = await response.json();
    if (!response.ok) throw Error(response.status === 409 ? (globalThis.HubI18n?.t?.("settings.212f81ce441d") ?? 'Настройки изменены другим участником. Черновик сохранён. Отмените изменения, чтобы загрузить актуальную версию.') : envelope.error || (globalThis.HubI18n?.t?.("settings.6e7ee8b60e28") ?? 'Не удалось сохранить настройки'));
    if (envelope.revision == null || !envelope.settings) throw Error((globalThis.HubI18n?.t?.("settings.9b88b36adc35") ?? 'Сервер не вернул подтверждённую версию настроек'));
    if (reset) {
      draft.value[reset] = projectSettings(envelope)[reset];
      draft.dirty = JSON.stringify(draft.value) !== JSON.stringify(projectSettings(envelope));
    } else { draft.value = projectSettings(envelope); draft.dirty = false; }
    draft.expected = envelope.revision; draft.message = (globalThis.HubI18n?.t?.("settings.2fe8f2fd7243") ?? 'Сохранено');
    if (activeProject === project) { state.settings = envelope; restoreUiState(); }
  } catch (error) { draft.message = (globalThis.HubI18n?.error?.(error) ?? error.message); }
  finally { draft.busy = false; persistSettingsDraft(project, draft); if (activeProject === project && route()[0] === 'settings') render(); }
}
document.addEventListener('change', event => {
  if (!event.target.closest('.settings-page')) return;
  const input = event.target, draft = settingsDraft();
  if (input.dataset.setting) {
    const [section,key] = input.dataset.setting.split('.');
    draft.value[section][key] = input.type === 'checkbox' ? input.checked : input.value;
  } else if (input.dataset.settingColumn) {
    draft.value.tasks.columns = taskTableColumns.map(([id]) => id).filter(id => id === 'title' || (id === input.dataset.settingColumn ? input.checked : draft.value.tasks.columns.includes(id)));
  } else return;
  draft.dirty = true; draft.message = ''; persistSettingsDraft(activeProject, draft); render();
});

function settingsTabs(instructions,section='') {
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.515308926562",{v0:(!instructions&&!section?'aria-current="page"':''),v1:(section==='architecture'?'aria-current="page"':''),v3:(section==='agents'||instructions?'aria-current="page"':'')}) : `<nav class="tabs settings-tabs" aria-label="Разделы настроек"><a href="#settings" ${!instructions&&!section?'aria-current="page"':''}>Общие</a><a href="#settings/agents" ${section==='agents'||instructions?'aria-current="page"':''}>Агенты и подключения</a><a href="#settings/architecture" ${section==='architecture'?'aria-current="page"':''}>Архитектура и код</a></nav>`);
}
const hubInstructions = new Map();
const hubEditableBlocks = new Set(['userInstructions']);
function hubInstructionEntry(project = activeProject) {
  if (!hubInstructions.has(project)) {
    let saved;
    try { saved = JSON.parse(sessionStorage.getItem(`project-hub-instructions-draft:${project}`) || 'null'); } catch { /* Optional storage. */ }
    const patch = {};
    for (const [id, value] of Object.entries(saved?.patch || {})) {
      if (hubEditableBlocks.has(id) && typeof value === 'string' && value.length <= 24000) patch[id] = value;
    }
    hubInstructions.set(project, {envelope:null, attempted:false, loading:false, busy:false, message:'', patch, expected:saved?.expected ?? null});
  }
  return hubInstructions.get(project);
}
function persistHubInstructions(project, entry) {
  try {
    const key = `project-hub-instructions-draft:${project}`;
    if (Object.keys(entry.patch).length) sessionStorage.setItem(key, JSON.stringify({patch:entry.patch, expected:entry.expected}));
    else sessionStorage.removeItem(key);
  } catch { /* Draft still survives navigation in memory. */ }
}
function isHubInstructionsRoute(project) {
  return activeProject === project && route()[0] === 'settings' && route()[1] === 'instructions';
}
async function loadHubInstructions(project = activeProject) {
  const entry = hubInstructionEntry(project);
  if (entry.loading || entry.busy) return;
  entry.loading = true; entry.attempted = true;
  try {
    const response = await fetch('/api/v1/instructions?' + new URLSearchParams({project}), {cache:'no-store'});
    const envelope = await response.json();
    if (!response.ok) throw Error(envelope.error || (globalThis.HubI18n?.t?.("settings.78c949187e3f") ?? 'Не удалось загрузить инструкции'));
    if (envelope.schemaVersion !== 1 || !Array.isArray(envelope.rules) || envelope.revision == null) throw Error((globalThis.HubI18n?.t?.("settings.533466a205ce") ?? 'Неполный реестр инструкций'));
    entry.envelope = envelope;
    if (!Object.keys(entry.patch).length) entry.expected = envelope.revision;
    entry.message = Object.keys(entry.patch).length && entry.expected !== envelope.revision
      ? (globalThis.HubI18n?.t?.("settings.d28910a6f3ed") ?? 'Инструкции обновились. Черновик сохранён; отмените его перед редактированием актуальной версии.') : '';
  } catch (error) { entry.message = (globalThis.HubI18n?.error?.(error) ?? error.message); }
  finally { entry.loading = false; if (isHubInstructionsRoute(project)) render(); }
}
function hubInstructionMarkdown(value) {
  const source = typeof value === 'string' ? value : JSON.stringify(value ?? '', null, 2);
  if (typeof window !== 'undefined' && window.marked?.parse && window.DOMPurify?.sanitize) {
    const header = source.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
    const metadata = header ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.51d84a54f6ca",{v0:(escape(header[0]))}) : `<details><summary>Технические данные файла инструкции</summary><p>Имя и описание, по которым Codex находит эту инструкцию (skill).</p><pre>${escape(header[0])}</pre></details>`) : '';
    const rendered = window.marked.parse(header ? source.slice(header[0].length) : source)
      .replace(/<(\/?)(h)([1-6])\b/g, (_, slash, tag, level) => `<${slash}${tag}${Math.min(6, Number(level) + 3)}`);
    return `${metadata}<div class="hub-markdown">${window.DOMPurify.sanitize(rendered, {
      USE_PROFILES:{html:true}, FORBID_TAGS:['img','style','form','input','button','iframe','audio','video','svg','math'],
      FORBID_ATTR:['style','id','name'],
    })}</div>`;
  }
  return `<pre>${escape(source)}</pre>`;
}
const hubInstructionTopics = [['rules',(globalThis.HubI18n?.t?.("settings.b785b445b5f9") ?? 'Правила работы')],['personal',(globalThis.HubI18n?.t?.("settings.2a02b8618db0") ?? 'Ваши инструкции')],['architecture',(globalThis.HubI18n?.t?.("settings.ba20d82574c7") ?? 'Архитектура Hub')],['capabilities',(globalThis.HubI18n?.t?.("settings.cbe4edc37a8b") ?? 'Возможности агента и MCP')],['scripts',(globalThis.HubI18n?.t?.("settings.c5c4b74842ed") ?? 'Скрипты')],['hooks',(globalThis.HubI18n?.t?.("settings.e81c0b681b79") ?? 'Обработчики событий (hooks)')],['extensions',(globalThis.HubI18n?.t?.("settings.ba1b8e9001a2") ?? 'Расширения')],['history',(globalThis.HubI18n?.t?.("settings.9d444769c920") ?? 'История изменений')]];
// Human explanations are separate from the original agent-facing API contracts.
const hubToolGuide = {
  hub_context:[(globalThis.HubI18n?.t?.("settings.1b6f19b18874") ?? 'Контекст и память'),(globalThis.HubI18n?.t?.("settings.c00786a1e7d0") ?? 'Узнать состояние проекта и текущей работы'),(globalThis.HubI18n?.t?.("settings.d2aa1396bc9e") ?? 'Помогает агенту определить проект и свой чат, увидеть активную работу и продолжить её с правильного места.')],
  hub_memory:[(globalThis.HubI18n?.t?.("settings.1b6f19b18874") ?? 'Контекст и память'),(globalThis.HubI18n?.t?.("settings.1e5c53555ca3") ?? 'Найти прошлые решения и результаты'),(globalThis.HubI18n?.t?.("settings.01308b446882") ?? 'Ищет записанные задачи, решения и подтверждающие материалы. Позволяет использовать накопленную память проекта.')],
  hub_notice:[(globalThis.HubI18n?.t?.("settings.1b6f19b18874") ?? 'Контекст и память'),(globalThis.HubI18n?.t?.("settings.cd0033d62fed") ?? 'Узнать о связанной параллельной работе'),(globalThis.HubI18n?.t?.("settings.94314ad074c1") ?? 'Показывает уведомления о других работах над той же задачей, зависимостями или файлами. Это повод согласовать действия; уведомление не доказывает, что другой чат сейчас выполняется.')],
  hub_wait:[(globalThis.HubI18n?.t?.("settings.1b6f19b18874") ?? 'Контекст и память'),(globalThis.HubI18n?.t?.("settings.0fb7dd4e5900") ?? 'Подождать изменения состояния'),(globalThis.HubI18n?.t?.("settings.c2b857c37cf8") ?? 'Коротко ожидает обновление Hub, когда продолжение зависит от внешнего события. Не запускает модель и не завершает задачу.')],
  hub_task:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.c759b93d6794") ?? 'Создать задачу'),(globalThis.HubI18n?.t?.("settings.1b0b17b09c32") ?? 'Записывает цель, область работы и критерии готовности. План с этапами добавляется отдельно.')],
  hub_task_update:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.792d77df43de") ?? 'Уточнить карточку задачи'),(globalThis.HubI18n?.t?.("settings.a16539c066ac") ?? 'Обновляет согласованные сведения о задаче и ссылки на материалы, сохраняя историю изменений.')],
  hub_task_link:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.1087c6787019") ?? 'Связать задачи'),(globalThis.HubI18n?.t?.("settings.501568838b62") ?? 'Записывает зависимости, связанные задачи и дубли. Помогает понять, что блокирует продолжение.')],
  hub_task_close:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.5f15cc9fd262") ?? 'Закрыть выполненную задачу'),(globalThis.HubI18n?.t?.("settings.7270fc0ad914") ?? 'Завершает задачу после проверки критериев готовности. Окончание ответа агента само по себе задачу не закрывает.')],
  hub_plan:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.d2904d49a032") ?? 'Вести план и решения'),(globalThis.HubI18n?.t?.("settings.ca1ff376088e") ?? 'Читает и обновляет этапы, оставшиеся требования, оценки и принятые решения.')],
  hub_begin:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.17361531e10f") ?? 'Зарегистрировать начало работы'),(globalThis.HubI18n?.t?.("settings.5a90877991e8") ?? 'Связывает работу агента с задачей и этапом, указывает затрагиваемые файлы. Hub сообщает о возможных пересечениях с другими работами.')],
  hub_report:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.e8856cb6b0cb") ?? 'Сохранить результат работы'),(globalThis.HubI18n?.t?.("settings.d0e8c88fe175") ?? 'Записывает выводы, проверки и подтверждающие материалы в выбранный этап. Завершение работы и закрытие всей задачи — отдельные действия.')],
  hub_review:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.57a1092aa6cf") ?? 'Предложить пересмотр задач'),(globalThis.HubI18n?.t?.("settings.2b535b660547") ?? 'Публикует обоснованные предложения по актуальности, готовности и оценке задач. Пользователь выбирает, какие предложения применить.')],
  hub_knowledge:[(globalThis.HubI18n?.t?.("settings.9f2b7f773977") ?? 'Документы и материалы'),(globalThis.HubI18n?.t?.("settings.57b16e9ea6e5") ?? 'Вести документацию и архитектуру'),(globalThis.HubI18n?.t?.("settings.dd51eec1c806") ?? 'Ищет и сохраняет статьи, описания компонентов и связи. Анализ исходников показывает доступные статические факты; смысл и порядок работы объясняет агент с опорой на доказательства.')],
  hub_image:[(globalThis.HubI18n?.t?.("settings.9f2b7f773977") ?? 'Документы и материалы'),(globalThis.HubI18n?.t?.("settings.a9923d24c38c") ?? 'Прикрепить изображение'),(globalThis.HubI18n?.t?.("settings.249be5ebe83d") ?? 'Добавляет иллюстрацию или снимок экрана к задаче либо этапу, чтобы результат можно было проверить.')],
  hub_artifact:[(globalThis.HubI18n?.t?.("settings.9f2b7f773977") ?? 'Документы и материалы'),(globalThis.HubI18n?.t?.("settings.75e19526737d") ?? 'Сохранить файл результата'),(globalThis.HubI18n?.t?.("settings.d4d7b8873998") ?? 'Регистрирует документы и другие файлы, сохраняет их версии и прикрепляет к задаче.')],
  hub_check:[(globalThis.HubI18n?.t?.("settings.4f3fecc2e553") ?? 'Проверки и Git'),(globalThis.HubI18n?.t?.("settings.dee1e9cbda79") ?? 'Записать запуск и итог проверки'),(globalThis.HubI18n?.t?.("settings.22ceccb464e9") ?? 'Показывает, какая проверка выполнялась и чем завершилась. Набор проверок определяется правилами проекта.')],
  hub_checkpoint:[(globalThis.HubI18n?.t?.("settings.4f3fecc2e553") ?? 'Проверки и Git'),(globalThis.HubI18n?.t?.("settings.1aef4ef5a1e2") ?? 'Проверить контрольную точку'),(globalThis.HubI18n?.t?.("settings.de50ce48095d") ?? 'Читает состояние сохранения результата в Git и помогает повторить незавершённую публикацию без потери исходных сведений.')],
  hub_git_batch:[(globalThis.HubI18n?.t?.("settings.4f3fecc2e553") ?? 'Проверки и Git'),(globalThis.HubI18n?.t?.("settings.6ee5541e8e9a") ?? 'Согласовать общий коммит'),(globalThis.HubI18n?.t?.("settings.76d2705ac5ab") ?? 'Помогает проверить вклад нескольких работ в общий коммит и связать его с их результатами. Просмотр и согласование через API сами не создают коммит.')],
  hub_settings:[(globalThis.HubI18n?.t?.("settings.985b5e0f2ccf") ?? 'Настройки'),(globalThis.HubI18n?.t?.("settings.8b02e5780b9b") ?? 'Прочитать или изменить настройки проекта'),(globalThis.HubI18n?.t?.("settings.62ba96d60a5e") ?? 'Работает с настройками задач, просмотра, архитектуры и Git. Изменения выполняются по запросу пользователя.')],
  hub_migration_preview:[(globalThis.HubI18n?.t?.("settings.985b5e0f2ccf") ?? 'Настройки'),(globalThis.HubI18n?.t?.("settings.7417fe797284") ?? 'Посмотреть предложение по старым задачам'),(globalThis.HubI18n?.t?.("settings.9fd9b362a777") ?? 'Готовит предварительный разбор старых записей перед изменением их структуры; просмотр не меняет задачи.')],
};
function hubInstructionTopic() {
  const topic = typeof route === 'function' ? route()[2] : '';
  return hubInstructionTopics.some(([id])=>id===topic) ? topic : 'rules';
}
function hubInstructionsPage() {
  const entry = hubInstructionEntry();
  const nativeWorkflow = (globalThis.HubI18n?.t?.('settings.nativeWorkflow') ?? '<section class="card" id="hub-native-workflow"><h2>Постоянные правила для агента</h2><p>В разделе <a href="#settings/agents">«Агенты и подключения»</a> создайте универсальное приглашение и передайте ссылку агенту. Он получит правила работы с Hub и инструкции подключения.</p><p>Сохраните правила как постоянную инструкцию в приложении агента. Затем откройте новый чат и проверьте, что агент читает правило, выбирает зарегистрированный проект, видит его через hub_context и записывает задачу и этап.</p><p>Храните доступ приватно, отдельно от исходников и текста правил. Независимое подключение MCP не требует плагина Codex, skills или обработчиков событий. Разрешения и подтверждения доверия задаёт приложение агента.</p></section>');
  const legacyBoundary = content => `<div class="hub-instructions" data-instructions-project="${escape(activeProject)}">${nativeWorkflow}<details class="card" data-key="hub-legacy-codex"><summary>${globalThis.HubI18n?.t?.('settings.legacyCodexTitle') ?? 'Прежнее подключение Codex через плагин'}</summary><p>${globalThis.HubI18n?.t?.('settings.legacyCodexHelp') ?? 'Этот необязательный раздел относится к прежнему плагину Codex: его пользовательской инструкции, скриптам и обработчикам событий. Редактор меняет только файл этого подключения; постоянные правила независимого подключения редактируются в приложении агента.'}</p>${content}</details></div>`;
  if (!entry.attempted) void loadHubInstructions();
  const envelope = entry.envelope;
  const button = (action, text, disabled = false) => `<button type="button" data-hub-instructions-action="${escape(action)}" ${disabled ? 'disabled' : ''}>${escape(text)}</button>`;
  const actions = `${button('reload',(globalThis.HubI18n?.t?.("settings.603e460bf59c") ?? 'Обновить'),entry.loading || entry.busy)}${button('cancel',(globalThis.HubI18n?.t?.("settings.4c8faff3287b") ?? 'Отменить черновик'),entry.loading || entry.busy || !Object.keys(entry.patch).length)}`;
  if (!envelope) return legacyBoundary(`<div class="settings-page hub-instructions"><div class="settings-actions">${actions}<span role="status">${escape(entry.message || (globalThis.HubI18n?.t?.("settings.66f7961fe72c") ?? 'Загрузка инструкций…'))}</span></div></div>`);
  const disabled = !envelope.initialized || entry.busy || entry.loading;
  const resetDisabled = envelope.restoreAllowed === false || entry.busy || entry.loading || entry.expected == null;
  const text = value => escape(typeof value === 'string' ? value : JSON.stringify(value ?? '', null, 2));
  const pre = value => `<pre>${text(value)}</pre>`;
  const cards = (items, body) => (items || []).map(item => `<article class="hub-instruction-card">${body(item)}</article>`).join('') || (globalThis.HubI18n?.t?.("settings.7da5d5b236a8") ?? '<p class="caption">В этой версии плагина записей пока нет.</p>');
  const topic = hubInstructionTopic();
  const ruleCards = (personal) => cards(envelope.rules.filter(rule => hubEditableBlocks.has(rule.id) === personal), rule => {
    const editable = rule.editable && rule.kind === 'editable' && hubEditableBlocks.has(rule.id);
    const effective = entry.patch[rule.id] ?? rule.effective;
    const blockId = `instruction-${encodeURIComponent(String(rule.id))}`;
    const blockHeading = personal ? (globalThis.HubI18n?.t?.('settings.0eb2ff1d7dbf') ?? 'Ваши правила для агента') : (globalThis.HubI18n?.t?.('settings.3d5467394606') ?? 'Полный текст встроенной инструкции');
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.21f031d04f0c",{v0:(text(blockId)),v1:(personal?(globalThis.HubI18n?.t?.("settings.0eb2ff1d7dbf") ?? 'Ваши правила для агента'):(globalThis.HubI18n?.t?.("settings.3d5467394606") ?? 'Полный текст встроенной инструкции')),v2:(personal?'personal':'rules'),v3:(encodeURIComponent(String(rule.id))),v4:(text(blockHeading)),v5:(rule.defaultChanged ? (globalThis.HubI18n?.t?.("settings.60b183be6472") ?? '<p class="hub-instruction-notice">В новой версии плагина изменился начальный шаблон. Ваши инструкции сохранены. Восстановление заменит их новым шаблоном.</p>') : ''),v6:(editable && entry.editing ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.6756a6827773",{v0:(text(rule.id)),v1:(disabled ? 'disabled' : ''),v2:(text(effective)),v3:(button('read',(globalThis.HubI18n?.t?.("settings.56b44d4aec51") ?? 'Вернуться к чтению')))}) : `<label>Локальная инструкция<textarea id="hub-personal-editor" data-hub-instruction-block="${text(rule.id)}" maxlength="24000" rows="18" ${disabled ? 'disabled' : ''}>${text(effective)}</textarea></label><p class="caption">До 24000 символов. Черновик сохраняется при переходе между темами.</p>${button('read',(globalThis.HubI18n?.t?.("settings.56b44d4aec51") ?? 'Вернуться к чтению'))}`) : (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.7f241919fadb",{v0:(hubInstructionMarkdown(effective)),v1:(editable?button('edit',(globalThis.HubI18n?.t?.("settings.c40f8f14593d") ?? 'Редактировать мои инструкции'),disabled):'')}) : `<div class="hub-agent-instruction" role="region" aria-label="Текст инструкции для агента"><div class="hub-agent-instruction-label">Текст инструкции для агента</div><p class="hub-agent-instruction-help">Этот текст обращён к агенту и задаёт правила его работы.</p>${hubInstructionMarkdown(effective)}</div>${editable?button('edit',(globalThis.HubI18n?.t?.("settings.c40f8f14593d") ?? 'Редактировать мои инструкции'),disabled):''}`)),v7:(editable?button('reset-'+rule.id,envelope.initialized?(globalThis.HubI18n?.t?.("settings.13ab90ea8a41") ?? 'Восстановить начальные инструкции'):(globalThis.HubI18n?.t?.("settings.7b8fa76ce23c") ?? 'Создать мои инструкции из шаблона'),resetDisabled):''),v8:(editable && effective !== rule.default ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.6127558540b1",{v0:(text(rule.id)),v1:(hubInstructionMarkdown(rule.default))}) : `<details data-key="instruction-default-${text(rule.id)}"><summary>Начальный шаблон для восстановления</summary><p>Этот текст поставляется с установленной версией плагина. Кнопка восстановления заменит им ваши инструкции.</p>${hubInstructionMarkdown(rule.default)}</details>`) : ''),v9:(text(rule.id)),v10:(text(rule.source))}) : `<h3 id="${text(blockId)}">${personal?(globalThis.HubI18n?.t?.("settings.0eb2ff1d7dbf") ?? 'Ваши правила для агента'):(globalThis.HubI18n?.t?.("settings.3d5467394606") ?? 'Полный текст встроенной инструкции')} <a class="hub-block-link" href="#settings/instructions/${personal?'personal':'rules'}/${encodeURIComponent(String(rule.id))}" aria-label="Ссылка на блок ${text(blockHeading)}">#</a></h3>${rule.defaultChanged ? (globalThis.HubI18n?.t?.("settings.60b183be6472") ?? '<p class="hub-instruction-notice">В новой версии плагина изменился начальный шаблон. Ваши инструкции сохранены. Восстановление заменит их новым шаблоном.</p>') : ''}
      ${editable && entry.editing ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.6756a6827773",{v0:(text(rule.id)),v1:(disabled ? 'disabled' : ''),v2:(text(effective)),v3:(button('read',(globalThis.HubI18n?.t?.("settings.56b44d4aec51") ?? 'Вернуться к чтению')))}) : `<label>Локальная инструкция<textarea id="hub-personal-editor" data-hub-instruction-block="${text(rule.id)}" maxlength="24000" rows="18" ${disabled ? 'disabled' : ''}>${text(effective)}</textarea></label><p class="caption">До 24000 символов. Черновик сохраняется при переходе между темами.</p>${button('read',(globalThis.HubI18n?.t?.("settings.56b44d4aec51") ?? 'Вернуться к чтению'))}`) : (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.7f241919fadb",{v0:(hubInstructionMarkdown(effective)),v1:(editable?button('edit',(globalThis.HubI18n?.t?.("settings.c40f8f14593d") ?? 'Редактировать мои инструкции'),disabled):'')}) : `<div class="hub-agent-instruction" role="region" aria-label="Текст инструкции для агента"><div class="hub-agent-instruction-label">Текст инструкции для агента</div><p class="hub-agent-instruction-help">Этот текст обращён к агенту и задаёт правила его работы.</p>${hubInstructionMarkdown(effective)}</div>${editable?button('edit',(globalThis.HubI18n?.t?.("settings.c40f8f14593d") ?? 'Редактировать мои инструкции'),disabled):''}`)}
      ${editable?button('reset-'+rule.id,envelope.initialized?(globalThis.HubI18n?.t?.("settings.13ab90ea8a41") ?? 'Восстановить начальные инструкции'):(globalThis.HubI18n?.t?.("settings.7b8fa76ce23c") ?? 'Создать мои инструкции из шаблона'),resetDisabled):''}
      ${editable && effective !== rule.default ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.6127558540b1",{v0:(text(rule.id)),v1:(hubInstructionMarkdown(rule.default))}) : `<details data-key="instruction-default-${text(rule.id)}"><summary>Начальный шаблон для восстановления</summary><p>Этот текст поставляется с установленной версией плагина. Кнопка восстановления заменит им ваши инструкции.</p>${hubInstructionMarkdown(rule.default)}</details>`) : ''}
      <details data-key="instruction-source-${text(rule.id)}"><summary>Где хранится файл инструкции</summary><p>${text(rule.source)}</p></details>`);
  });
  const capabilities = cards(envelope.skills, item => `<h3>${text(item.title || item.id)}</h3>${hubInstructionMarkdown(item.description)}`);
  const toolGroups = new Map();
  for (const tool of envelope.tools || []) {
    const group = hubToolGuide[tool.name]?.[0] || (globalThis.HubI18n?.t?.("settings.f44ac1fa3391") ?? 'Другие инструменты');
    if (!toolGroups.has(group)) toolGroups.set(group, []);
    toolGroups.get(group).push(tool);
  }
  const tools = [...toolGroups].map(([group,items])=>`<details data-key="instruction-tools-${text(group)}"><summary>${text(group)} · ${items.length}</summary>${cards(items,item=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.62c12739878b",{v0:(text(hubToolGuide[item.name]?.[1] || item.name)),v1:(text(hubToolGuide[item.name]?.[2] || (globalThis.HubI18n?.t?.("settings.8b28511c0138") ?? 'Дополнительный инструмент этой версии плагина. Его контракт приведён ниже.'))),v2:(text(item.name)),v3:(hubInstructionMarkdown(item.description))}) : `<h3>${text(hubToolGuide[item.name]?.[1] || item.name)}</h3><p>${text(hubToolGuide[item.name]?.[2] || (globalThis.HubI18n?.t?.("settings.8b28511c0138") ?? 'Дополнительный инструмент этой версии плагина. Его контракт приведён ниже.'))}</p><p class="caption">Имя MCP: <code>${text(item.name)}</code></p><details><summary>Технический контракт для агента · оригинал</summary>${hubInstructionMarkdown(item.description)}</details>`))}</details>`).join('');
  const scripts = cards(envelope.scripts, item => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.21ae8fa35c65",{v0:(text(item.name)),v1:(hubInstructionMarkdown(item.description)),v2:(text(item.runtime)),v3:(item.settings?.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.f9ee30d64af8",{v0:(pre(item.settings))}) : `<details><summary>Параметры</summary>${pre(item.settings)}</details>`) : '')}) : `<h3><code>${text(item.name)}</code></h3>${hubInstructionMarkdown(item.description)}<p class="caption">Среда: ${text(item.runtime)}</p>${item.settings?.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.f9ee30d64af8",{v0:(pre(item.settings))}) : `<details><summary>Параметры</summary>${pre(item.settings)}</details>`) : ''}`));
  const hookTitles = {SessionStart:(globalThis.HubI18n?.t?.("settings.6fce73381227") ?? 'Начало чата'),UserPromptSubmit:(globalThis.HubI18n?.t?.("settings.46e8c9653b32") ?? 'Новый запрос пользователя'),PreToolUse:(globalThis.HubI18n?.t?.("settings.0489ec79f603") ?? 'Перед редактированием файла'),Stop:(globalThis.HubI18n?.t?.("settings.1c5ce8dc1111") ?? 'Окончание ответа'),Interrupt:(globalThis.HubI18n?.t?.("settings.e78898a57f66") ?? 'Прерывание работы'),SessionEnd:(globalThis.HubI18n?.t?.("settings.fac655680a19") ?? 'Закрытие сессии')};
  const hooks = cards(envelope.hooks, item => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.8e85d7823619",{v0:(text(hookTitles[item.event] || item.event)),v1:(hubInstructionMarkdown(item.description)),v2:(text(item.event)),v3:(text(item.requiredFor)),v4:(text(item.timeout)),v5:(text(item.matcher || (globalThis.HubI18n?.t?.("settings.f3370066eb26") ?? 'Все подходящие события'))),v6:([[(globalThis.HubI18n?.t?.("settings.8b372c12c268") ?? 'Команда'),item.command],[(globalThis.HubI18n?.t?.("settings.e9b0d8467738") ?? 'Команда Windows'),item.commandWindows]].filter(([,command]) => command).map(([label,command]) => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.ff0335cacf78",{v0:(label),v1:(text(command)),v2:(label)}) : `<label>${label}<textarea class="hub-hook-command" readonly rows="3">${text(command)}</textarea><button type="button" data-hub-copy-command>${label}: копировать</button></label>`)).join(''))}) : `<h3>${text(hookTitles[item.event] || item.event)}</h3>${hubInstructionMarkdown(item.description)}<details><summary>Настройка обработчика · ${text(item.event)}</summary><p>Обработчик включён в плагин. Эта справка не проверяет, разрешён ли его запуск в Codex и сработал ли он в вашем чате.</p><p class="caption">Назначение: ${text(item.requiredFor)} · Ограничение времени: ${text(item.timeout)} с · Фильтр инструментов: ${text(item.matcher || (globalThis.HubI18n?.t?.("settings.f3370066eb26") ?? 'Все подходящие события'))}</p>${[[(globalThis.HubI18n?.t?.("settings.8b372c12c268") ?? 'Команда'),item.command],[(globalThis.HubI18n?.t?.("settings.e9b0d8467738") ?? 'Команда Windows'),item.commandWindows]].filter(([,command]) => command).map(([label,command]) => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.ff0335cacf78",{v0:(label),v1:(text(command)),v2:(label)}) : `<label>${label}<textarea class="hub-hook-command" readonly rows="3">${text(command)}</textarea><button type="button" data-hub-copy-command>${label}: копировать</button></label>`)).join('')}</details>`));
  const hookRecovery = envelope.hookRecovery?.hooks && typeof envelope.hookRecovery.hooks === 'object' && !Array.isArray(envelope.hookRecovery.hooks)
    ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.9daf41cd2710",{v0:(text(JSON.stringify(envelope.hookRecovery, null, 2)))}) : `<details class="hub-hook-recovery"><summary>JSON для восстановления hooks</summary><p>Импорт JSON и подтверждение доверия к hooks выполняет пользователь в Codex. Портал не изменяет существующие или чужие hooks. Копирование не подтверждает доставку или срабатывание.</p><label>Конфигурация с путями этой установки<textarea class="hub-hook-command" readonly rows="10">${text(JSON.stringify(envelope.hookRecovery, null, 2))}</textarea><button type="button" data-hub-copy-command data-hub-copy-hooks>Скопировать JSON hooks</button></label></details>`) : '';
  const optionalHookRecovery = envelope.optionalHookRecovery?.hooks && typeof envelope.optionalHookRecovery.hooks === 'object' && !Array.isArray(envelope.optionalHookRecovery.hooks)
    ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.caaa12293dba",{v0:(text(envelope.optionalHookRecovery.description)),v1:(text(JSON.stringify({hooks:envelope.optionalHookRecovery.hooks}, null, 2)))}) : `<article class="hub-instruction-card hub-hook-optional"><h3>Дополнительное ожидание уведомлений</h3><p>${text(envelope.optionalHookRecovery.description)}</p><p>Добавьте обработчик к существующим настройкам событий вручную, не заменяя всю конфигурацию. Портал не включает его автоматически. Обработчик не возобновляет бездействующий чат; эта справка не проверяет разрешение на запуск и фактическое срабатывание в Codex.</p><details><summary>Конфигурация дополнительного обработчика (JSON)</summary><label>Фрагмент для добавления<textarea class="hub-hook-command" readonly rows="10">${text(JSON.stringify({hooks:envelope.optionalHookRecovery.hooks}, null, 2))}</textarea><button type="button" data-hub-copy-command data-hub-copy-optional-hooks>Скопировать JSON обработчика</button></label></details></article>`) : '';
  const extensions = cards(envelope.extensions, item => `<h3>${text(item.title || item.id)}</h3><p class="caption">${text(({supported:(globalThis.HubI18n?.t?.("settings.8bcf365638c3") ?? 'Доступно сейчас'),proposed:(globalThis.HubI18n?.t?.("settings.a9592df53cd1") ?? 'Предложение для будущих версий')})[item.status] || item.status)}</p>${hubInstructionMarkdown(item.description)}`);
  const nativeScope = envelope.scope === 'codex-user'
    ? (globalThis.HubI18n?.t?.("settings.49db66ea11d2") ?? 'Эти инструкции не принадлежат отдельному проекту. Они относятся к вашей работе с Hub во всех проектах, добавленных в Project Hub.')
    : (globalThis.HubI18n?.t?.("settings.a89b61029eae") ?? 'Эти инструкции хранятся локально. К каким чатам они применяются, зависит от расположения файла в Codex.');
  const scopeNotice = envelope.nativeDiscovery === true
    ? (globalThis.HubI18n?.t?.("settings.db62a639115e") ?? 'Codex может найти файл как локальную инструкцию (skill). Изменения применяются, когда агент прочитает project-hub-user; сохранение не обновляет уже работающий чат и не гарантирует чтение каждым новым чатом.')
    : (globalThis.HubI18n?.t?.("settings.9a3d8460d4e8") ?? 'Codex пока не находит пользовательскую инструкцию прежнего подключения через плагин. Настройте её расположение для этого подключения. Независимое подключение использует постоянное правило в приложении агента.');
  const initializationNotice = !envelope.initialized
    ? `<p class="hub-instruction-notice">${envelope.restoreAllowed === false
      ? (globalThis.HubI18n?.t?.("settings.1475e8bd0463") ?? 'Пока показан шаблон прежнего плагина Codex. Для его редактора сначала настройте расположение пользовательской инструкции. Для независимого подключения сохраняйте правило в приложении агента.')
      : (globalThis.HubI18n?.t?.("settings.fd8e97b92520") ?? 'Файл пользовательской инструкции прежнего плагина Codex ещё не создан. Для этого подключения нажмите «Создать мои инструкции из шаблона», затем отредактируйте его.')}</p>` : '';
  const intro = {
    rules:(globalThis.HubI18n?.t?.("settings.bf2df2bdfff9") ?? 'Это правила, по которым агент ведёт задачи, сохраняет решения и сообщает о результатах в Project Hub. Они поставляются вместе с плагином Codex, который вы устанавливаете на компьютер. Здесь их можно прочитать, но нельзя изменить: обновлённые правила приходят с новой версией плагина.'),
    personal:(globalThis.HubI18n?.t?.("settings.a8716e2b0e5b") ?? 'Здесь можно дополнить встроенные правила своими предпочтениями: например, как подробно писать отчёты и как выбирать проверки. Ваш текст хранится отдельно от плагина и сохраняется при его обновлении.'),
    architecture:(globalThis.HubI18n?.t?.("settings.8747014bc0b7") ?? 'Этот раздел объясняет устройство Project Hub: как Codex обращается к сервису, где сохраняются данные и почему задачи, инструкции и разрешения имеют разные источники. Ниже — подробности для тех, кто хочет понять техническую сторону.'),
    capabilities:(globalThis.HubI18n?.t?.("settings.1ecfa1a43146") ?? 'Здесь описано, что агент может делать через Hub. Skill — файл с инструкциями для агента. MCP — подключение, через которое агент вызывает инструменты Hub: читает память проекта, ведёт задачи и сохраняет результаты.'),
    scripts:(globalThis.HubI18n?.t?.("settings.1ff884604d12") ?? 'Скрипты — программы внутри плагина. Они соединяют Codex с локальным сервисом, передают события и записывают результаты проверок. Обычно запускать их вручную не нужно; этот список помогает понять их назначение и разобраться с настройкой.'),
    hooks:(globalThis.HubI18n?.t?.("settings.56c7b74b54cc") ?? 'Обработчики событий (hooks) запускаются средствами Codex при начале чата, новом запросе или редактировании. Они помогают Hub наблюдать за работой и напоминать об учёте задач. Инструменты MCP работают отдельно от них.'),
    extensions:(globalThis.HubI18n?.t?.("settings.2008c948b424") ?? 'Project Hub можно дополнять инструкциями, обработчиками событий и другими MCP-подключениями. Здесь показаны доступные способы и их границы. Настройка расширения выполняется отдельно в Codex.'),
    history:(globalThis.HubI18n?.t?.("settings.78600c53dcf8") ?? 'Это последние изменения ваших инструкций: сохранение нового текста и восстановление начального шаблона. История общая для этого файла, а не для выбранного проекта. Обновления плагина и изменения задач сюда не входят.'),
  };
  const historyRows = (envelope.history || []).slice(-10).reverse();
  const sections = {
    rules: () => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.86b7a4e32dfc",{v0:(ruleCards(false))}) : `<details open data-key="instruction-reading"><summary>Прочитать встроенную инструкцию</summary>${ruleCards(false)}</details>`),
    personal: () => `<p>${nativeScope}</p><p>${scopeNotice}</p>${initializationNotice}${ruleCards(true)}`,
    architecture: () => cards(envelope.architecture,item=>`<h3>${text(item.title)}</h3>${hubInstructionMarkdown(item.description)}`),
    capabilities: () => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.ecee8e4ae2fa",{v0:(capabilities),v1:(tools)}) : `${capabilities}<h3>Инструменты по назначению</h3><p>Выберите группу, чтобы узнать доступные действия. Точные имена и исходные контракты пригодятся при настройке MCP.</p>${tools}`),
    scripts: () => scripts,
    hooks: () => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.3c81415ee551",{v0:(hooks),v1:(hookRecovery),v2:(optionalHookRecovery)}) : `${hooks}<h3>Восстановление настройки в Codex</h3><p>Если обработчики отсутствуют, можно скопировать конфигурацию ниже. Добавление и подтверждение доверия выполняются в Codex.</p>${hookRecovery}${optionalHookRecovery}`),
    extensions: () => extensions,
    history: () => historyRows.length ? cards(historyRows,item=>{
      const at = Number.isFinite(Date.parse(item.at)) ? new Intl.DateTimeFormat((globalThis.HubI18n?.locale==='en'?'en-GB':'ru-RU'),{dateStyle:'long',timeStyle:'short'}).format(new Date(item.at)) : (globalThis.HubI18n?.t?.("settings.732063f16e43") ?? 'Дата не указана');
      const actor = item.actor==='local-user' ? (globalThis.HubI18n?.t?.("settings.2a5c42af7c00") ?? 'Пользователь') : (item.actor || (globalThis.HubI18n?.t?.("settings.033a80284b24") ?? 'Автор не указан'));
      return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.69b3ce38020a",{v0:(text(item.at)),v1:(text(at)),v2:(text(actor))}) : `<p><time datetime="${text(item.at)}">${text(at)}</time> · ${text(actor)}</p><p>Изменены ваши инструкции</p>`);
    }) : (globalThis.HubI18n?.t?.("settings.e41c30f724a8") ?? '<p class="history">Вы ещё не сохраняли изменения инструкций через Hub. После первого сохранения или восстановления здесь появится запись.</p>'),
  };
  const metadata = topic==='personal' ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.575848637526",{v0:(scopeNotice),v1:(text(envelope.path))}) : `<details data-key="instruction-technical"><summary>Подключение файла к Codex</summary><p>${scopeNotice}</p><p>Редактор меняет только файл project-hub-user/SKILL.md. Инструкции отдельных проектов и встроенные правила плагина редактируются отдельно.</p><p class="meta">Файл: ${text(envelope.path)}</p></details>`) : '';
  const personalActions = topic==='personal' ? `<div class="actions">${button('cancel',(globalThis.HubI18n?.t?.("settings.4c8faff3287b") ?? 'Отменить черновик'),entry.loading||entry.busy||!Object.keys(entry.patch).length)}${button('save',(globalThis.HubI18n?.t?.("settings.ac34ddab99bb") ?? 'Сохранить мои инструкции'),disabled||!Object.keys(entry.patch).length||entry.expected==null)}</div>` : '';
  const legacyContent = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("settings.d89c25d80ffd",{v0:(escape(activeProject)),v1:(hubInstructionTopics.map(([id,label])=>`<a id="instruction-topic-${id}" href="#settings/instructions/${id}" ${id===topic?'aria-current="page"':''}>${label}${id==='personal'&&Object.keys(entry.patch).length?(globalThis.HubI18n?.t?.("settings.3af931e3e4f4") ?? ' · черновик'):''}</a>`).join('')),v2:(hubInstructionTopics.find(([id])=>id===topic)[1]),v3:(intro[topic]),v4:(sections[topic]()),v5:(personalActions),v6:(text(entry.message || (Object.keys(entry.patch).length?(globalThis.HubI18n?.t?.("settings.382dd64dc0b2") ?? 'Есть несохранённые изменения'):''))),v7:(metadata)}) : `<div class="hub-instructions" data-instructions-project="${escape(activeProject)}"><p class="intro">Справка о работе Project Hub и настройка ваших инструкций для агента. Начните с правил работы; подробное устройство и технические возможности описаны в следующих темах.</p>
    <div class="reader"><nav class="toc" aria-label="Оглавление инструкций"><strong>Содержание</strong>${hubInstructionTopics.map(([id,label])=>`<a id="instruction-topic-${id}" href="#settings/instructions/${id}" ${id===topic?'aria-current="page"':''}>${label}${id==='personal'&&Object.keys(entry.patch).length?(globalThis.HubI18n?.t?.("settings.3af931e3e4f4") ?? ' · черновик'):''}</a>`).join('')}</nav><div class="reader-body"><div class="reader-top"><div><div class="eyebrow">ИНСТРУКЦИИ И ВОЗМОЖНОСТИ HUB</div><h2>${hubInstructionTopics.find(([id])=>id===topic)[1]}</h2></div></div><section id="hub-instruction-topic" tabindex="-1"><p class="hub-topic-intro">${intro[topic]}</p>${sections[topic]()}</section>${personalActions}<p id="hub-instructions-status" class="meta" role="status">${text(entry.message || (Object.keys(entry.patch).length?(globalThis.HubI18n?.t?.("settings.382dd64dc0b2") ?? 'Есть несохранённые изменения'):''))}</p>${metadata}</div></div></div>`);
  return legacyBoundary(legacyContent);
}
async function submitHubInstructions(reset) {
  const project = activeProject, entry = hubInstructionEntry(project);
  if (entry.busy || entry.loading || !entry.envelope || (!entry.envelope.initialized && !reset) || entry.expected == null) return;
  if (reset && entry.envelope.restoreAllowed === false) return;
  if (!reset && (!Object.keys(entry.patch).length || Object.values(entry.patch).some(value => typeof value !== 'string' || value.length > 24000))) return;
  if (reset && !window.confirm(reset === 'all' ? (globalThis.HubI18n?.t?.("settings.11120c1b9cce") ?? 'Заменить ваши инструкции начальным шаблоном из установленной версии плагина? Черновик будет отменён.') : (globalThis.HubI18n?.t?.("settings.faa316985fe5") ?? 'Заменить ваши инструкции начальным шаблоном из установленной версии плагина?'))) return;
  const body = reset ? {expected:entry.expected, reset} : {expected:entry.expected, patch:{...entry.patch}};
  entry.busy = true; entry.message = (globalThis.HubI18n?.t?.("settings.bd97450c8556") ?? 'Сохранение…'); render();
  try {
    const response = await fetch('/api/v1/instructions?' + new URLSearchParams({project}), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const envelope = await response.json();
    if (!response.ok) throw Error(response.status === 409 ? (globalThis.HubI18n?.t?.("settings.fab6d9413525") ?? 'Инструкции изменены другим участником. Черновик сохранён. Отмените черновик, чтобы загрузить актуальные инструкции перед редактированием.') : envelope.error || (globalThis.HubI18n?.t?.("settings.3ad4aed694e1") ?? 'Не удалось сохранить инструкции'));
    if (envelope.schemaVersion !== 1 || !Array.isArray(envelope.rules) || envelope.revision == null) throw Error((globalThis.HubI18n?.t?.("settings.e6470d30d3be") ?? 'Сервер не подтвердил версию инструкций'));
    entry.envelope = envelope; entry.expected = envelope.revision;
    if (!reset || reset === 'all') entry.patch = {};
    else delete entry.patch[reset];
    entry.message = (globalThis.HubI18n?.t?.("settings.1f8e3dc905e9") ?? 'Сохранено в пользовательской инструкции прежнего подключения Codex через плагин. Изменения действуют после чтения файла project-hub-user агентом.');
  } catch (error) { entry.message = (globalThis.HubI18n?.error?.(error) ?? error.message); }
  finally { entry.busy = false; persistHubInstructions(project,entry); if (isHubInstructionsRoute(project)) render(); }
}
document.addEventListener('input', event => {
  const input = event.target, id = input.dataset?.hubInstructionBlock;
  if (!id || !hubEditableBlocks.has(id) || !input.closest('.hub-instructions')) return;
  const entry = hubInstructionEntry(), rule = entry.envelope?.rules.find(rule => rule.id === id);
  if (entry.busy || entry.loading || !entry.envelope?.initialized || !rule?.editable || rule.kind !== 'editable') return;
  if (input.value === rule.effective) delete entry.patch[id];
  else entry.patch[id] = input.value;
  entry.message = input.value.length > 24000 ? (globalThis.HubI18n?.t?.("settings.8e866a91877b") ?? 'Не более 24000 символов в блоке.') : (globalThis.HubI18n?.t?.("settings.382dd64dc0b2") ?? 'Есть несохранённые изменения');
  persistHubInstructions(activeProject,entry);
  const status = document.getElementById('hub-instructions-status');
  if (status) status.textContent = entry.message;
  const save = document.querySelector('[data-hub-instructions-action="save"]');
  if (save) save.disabled = !Object.keys(entry.patch).length || Object.values(entry.patch).some(value => value.length > 24000);
  const cancel = document.querySelector('[data-hub-instructions-action="cancel"]');
  if (cancel) cancel.disabled = !Object.keys(entry.patch).length;
});
document.addEventListener('click', async event => {
  const copy = event.target.closest('[data-hub-copy-command]');
  if (copy) {
    const field = copy.closest('label')?.querySelector('textarea');
    if (!field) return;
    try { await navigator.clipboard.writeText(field.value); copy.textContent = (globalThis.HubI18n?.t?.("settings.d2d08c715ee6") ?? 'Скопировано'); }
    catch { field.focus(); field.select(); copy.textContent = (globalThis.HubI18n?.t?.("settings.d691c834f8d2") ?? 'Выделено: скопируйте вручную'); }
    return;
  }
  const action = event.target.closest('[data-hub-instructions-action]')?.dataset.hubInstructionsAction;
  if (!action) return;
  if (action === 'edit' || action === 'read') {
    const entry = hubInstructionEntry(); entry.editing = action === 'edit'; render();
    document.getElementById(entry.editing ? 'hub-personal-editor' : 'hub-instruction-topic')?.focus({preventScroll:true});
  } else if (action === 'save') await submitHubInstructions();
  else if (action.startsWith('reset-')) await submitHubInstructions(action.slice(6));
  else if (action === 'cancel') {
    const entry = hubInstructionEntry();
    if (entry.busy || entry.loading) return;
    entry.patch = {}; entry.expected = entry.envelope?.revision ?? null;
    persistHubInstructions(activeProject,entry); await loadHubInstructions();
  }
});
document.addEventListener('click', async event => {
  const action = event.target.closest('[data-settings-action]')?.dataset.settingsAction;
  if (!action) return;
  if (action === 'save') await submitSettings();
  else if (action.startsWith('reset-')) await submitSettings(action.slice(6));
  else if (action === 'personal-reset') resetProjectListPreferences();
  else if (action === 'cancel') {
    const project = activeProject, draft = settingsDraft();
    if (draft.busy) return;
    draft.busy = true;
    render();
    try {
      const response = await fetch('/api/v1/settings?' + new URLSearchParams({project}), {cache:'no-store'});
      const envelope = await response.json();
      if (!response.ok) throw Error(envelope.error || (globalThis.HubI18n?.t?.("settings.c265cda8462e") ?? 'Не удалось загрузить настройки'));
      settingsDrafts.delete(project);
      persistSettingsDraft(project, {dirty:false});
      if (activeProject === project) { state.settings = envelope; restoreUiState(); }
    } catch (error) { draft.message = (globalThis.HubI18n?.error?.(error) ?? error.message); }
    finally { draft.busy = false; if (activeProject === project) render(); }
  }
});

// Preserve reader disclosures and editor position across routing and live refreshes.
if (typeof window !== 'undefined') window.HubSettingsUI = {
  beforeRender() {
    const preview = document.querySelector('#settings-request-dialog');
    if (preview) {
      const draft = settingsDrafts.get(preview.closest('[data-settings-project]')?.dataset.settingsProject);
      if (draft) draft.requestPreview = {open:preview.open && route()[0]==='settings' && route()[1]==='architecture', detail:preview.querySelector('select').value};
    }
    const reader = document.querySelector('.hub-instructions[data-instructions-project]');
    if (!reader) return;
    const entry = hubInstructionEntry(reader.dataset.instructionsProject);
    entry.details ??= new Map();
    reader.querySelectorAll('details[data-key]').forEach(detail => entry.details.set(detail.dataset.key, detail.open));
    const editor = reader.querySelector('#hub-personal-editor');
    if (editor) entry.editorScroll = editor.scrollTop;
  },
  afterRender() {
    if (document.getElementById('hub-folder-settings') && !storageFolderSettings.loaded && !storageFolderSettings.loading) void loadStorageFolderSettings();
    globalThis.HubLocalFiles?.bind(document);
    globalThis.backupStatus?.afterRender();
    if (document.getElementById('hub-modern-instructions')) {
      const editor = document.getElementById('hub-agent-instructions-text');
      if (editor && editor.value !== hubAgentInstructions.text) editor.value = hubAgentInstructions.text;
      void loadModernWorkflow(); void loadAgentInstructions();
    }
    if (!state) return;
    if (typeof route === 'function' && route()[0] === 'settings' && route()[1] === 'architecture') {
      const preview = document.getElementById('settings-request-dialog'), saved = settingsDraft().requestPreview;
      if (preview && saved?.open) { preview.querySelector('select').value = saved.detail; preview.showModal(); }
    }
    if (typeof route !== 'function' || route()[0] !== 'settings' || route()[1] !== 'instructions' || document.getElementById('hub-modern-instructions')) return;
    const entry = hubInstructionEntry();
    document.querySelectorAll('.hub-instructions details[data-key]').forEach(detail => {
      if (entry.details?.has(detail.dataset.key)) detail.open = entry.details.get(detail.dataset.key);
    });
    const editor = document.getElementById('hub-personal-editor');
    if (editor && entry.editorScroll != null) editor.scrollTop = entry.editorScroll;
    const key = route().slice(2).join('/');
    if (entry.renderedTopic !== key) {
      entry.renderedTopic = key;
      let block;
      try { block = route()[3] && document.getElementById('instruction-' + encodeURIComponent(route()[3])); } catch { /* Unknown route remains readable. */ }
      const legacy = document.querySelector('[data-key="hub-legacy-codex"]');
      // Explicit legacy topic/block links reveal their destination. The ordinary
      // instructions route leaves the optional section closed on first visit.
      if (legacy && (route()[2] || block)) { legacy.open = true; entry.details ??= new Map(); entry.details.set('hub-legacy-codex', true); }
      const target = legacy && !legacy.open ? document.getElementById('hub-native-workflow') : block || document.getElementById('hub-instruction-topic');
      if (target) { target.tabIndex = -1; target.focus({preventScroll:!block}); if (block) block.scrollIntoView({block:'start'}); }
    }
  },
};

document.addEventListener('click', event => {
  const action = event.target.closest('[data-settings-request]')?.dataset.settingsRequest;
  if (!action) return;
  const dialog = document.getElementById('settings-request-dialog');
  if (!dialog) return;
  if (action === 'open') dialog.showModal();
  else if (action === 'close') dialog.close();
  else if (action === 'apply') {
    const select = document.getElementById('settings-request-detail');
    document.getElementById('settings-request-status').textContent = (globalThis.HubI18n?.t?.("settings.cf4c63120878") ?? 'Пример запроса: ') + select.selectedOptions[0].textContent + (globalThis.HubI18n?.t?.("settings.683eb10b73f7") ?? '. Настройки проекта не изменены.');
  }
});

globalThis.HubI18n?.onChange?.(()=>{hubInstructionTopics.splice(0,hubInstructionTopics.length,...[['rules',(globalThis.HubI18n?.t?.("settings.b785b445b5f9") ?? 'Правила работы')],['personal',(globalThis.HubI18n?.t?.("settings.2a02b8618db0") ?? 'Ваши инструкции')],['architecture',(globalThis.HubI18n?.t?.("settings.ba20d82574c7") ?? 'Архитектура Hub')],['capabilities',(globalThis.HubI18n?.t?.("settings.cbe4edc37a8b") ?? 'Возможности агента и MCP')],['scripts',(globalThis.HubI18n?.t?.("settings.c5c4b74842ed") ?? 'Скрипты')],['hooks',(globalThis.HubI18n?.t?.("settings.e81c0b681b79") ?? 'Обработчики событий (hooks)')],['extensions',(globalThis.HubI18n?.t?.("settings.ba1b8e9001a2") ?? 'Расширения')],['history',(globalThis.HubI18n?.t?.("settings.9d444769c920") ?? 'История изменений')]]);Object.assign(hubToolGuide,{
  hub_context:[(globalThis.HubI18n?.t?.("settings.1b6f19b18874") ?? 'Контекст и память'),(globalThis.HubI18n?.t?.("settings.c00786a1e7d0") ?? 'Узнать состояние проекта и текущей работы'),(globalThis.HubI18n?.t?.("settings.d2aa1396bc9e") ?? 'Помогает агенту определить проект и свой чат, увидеть активную работу и продолжить её с правильного места.')],
  hub_memory:[(globalThis.HubI18n?.t?.("settings.1b6f19b18874") ?? 'Контекст и память'),(globalThis.HubI18n?.t?.("settings.1e5c53555ca3") ?? 'Найти прошлые решения и результаты'),(globalThis.HubI18n?.t?.("settings.01308b446882") ?? 'Ищет записанные задачи, решения и подтверждающие материалы. Позволяет использовать накопленную память проекта.')],
  hub_notice:[(globalThis.HubI18n?.t?.("settings.1b6f19b18874") ?? 'Контекст и память'),(globalThis.HubI18n?.t?.("settings.cd0033d62fed") ?? 'Узнать о связанной параллельной работе'),(globalThis.HubI18n?.t?.("settings.94314ad074c1") ?? 'Показывает уведомления о других работах над той же задачей, зависимостями или файлами. Это повод согласовать действия; уведомление не доказывает, что другой чат сейчас выполняется.')],
  hub_wait:[(globalThis.HubI18n?.t?.("settings.1b6f19b18874") ?? 'Контекст и память'),(globalThis.HubI18n?.t?.("settings.0fb7dd4e5900") ?? 'Подождать изменения состояния'),(globalThis.HubI18n?.t?.("settings.c2b857c37cf8") ?? 'Коротко ожидает обновление Hub, когда продолжение зависит от внешнего события. Не запускает модель и не завершает задачу.')],
  hub_task:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.c759b93d6794") ?? 'Создать задачу'),(globalThis.HubI18n?.t?.("settings.1b0b17b09c32") ?? 'Записывает цель, область работы и критерии готовности. План с этапами добавляется отдельно.')],
  hub_task_update:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.792d77df43de") ?? 'Уточнить карточку задачи'),(globalThis.HubI18n?.t?.("settings.a16539c066ac") ?? 'Обновляет согласованные сведения о задаче и ссылки на материалы, сохраняя историю изменений.')],
  hub_task_link:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.1087c6787019") ?? 'Связать задачи'),(globalThis.HubI18n?.t?.("settings.501568838b62") ?? 'Записывает зависимости, связанные задачи и дубли. Помогает понять, что блокирует продолжение.')],
  hub_task_close:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.5f15cc9fd262") ?? 'Закрыть выполненную задачу'),(globalThis.HubI18n?.t?.("settings.7270fc0ad914") ?? 'Завершает задачу после проверки критериев готовности. Окончание ответа агента само по себе задачу не закрывает.')],
  hub_plan:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.d2904d49a032") ?? 'Вести план и решения'),(globalThis.HubI18n?.t?.("settings.ca1ff376088e") ?? 'Читает и обновляет этапы, оставшиеся требования, оценки и принятые решения.')],
  hub_begin:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.17361531e10f") ?? 'Зарегистрировать начало работы'),(globalThis.HubI18n?.t?.("settings.5a90877991e8") ?? 'Связывает работу агента с задачей и этапом, указывает затрагиваемые файлы. Hub сообщает о возможных пересечениях с другими работами.')],
  hub_report:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.e8856cb6b0cb") ?? 'Сохранить результат работы'),(globalThis.HubI18n?.t?.("settings.d0e8c88fe175") ?? 'Записывает выводы, проверки и подтверждающие материалы в выбранный этап. Завершение работы и закрытие всей задачи — отдельные действия.')],
  hub_review:[(globalThis.HubI18n?.t?.("settings.b0327e91e211") ?? 'Задачи и этапы'),(globalThis.HubI18n?.t?.("settings.57a1092aa6cf") ?? 'Предложить пересмотр задач'),(globalThis.HubI18n?.t?.("settings.2b535b660547") ?? 'Публикует обоснованные предложения по актуальности, готовности и оценке задач. Пользователь выбирает, какие предложения применить.')],
  hub_knowledge:[(globalThis.HubI18n?.t?.("settings.9f2b7f773977") ?? 'Документы и материалы'),(globalThis.HubI18n?.t?.("settings.57b16e9ea6e5") ?? 'Вести документацию и архитектуру'),(globalThis.HubI18n?.t?.("settings.dd51eec1c806") ?? 'Ищет и сохраняет статьи, описания компонентов и связи. Анализ исходников показывает доступные статические факты; смысл и порядок работы объясняет агент с опорой на доказательства.')],
  hub_image:[(globalThis.HubI18n?.t?.("settings.9f2b7f773977") ?? 'Документы и материалы'),(globalThis.HubI18n?.t?.("settings.a9923d24c38c") ?? 'Прикрепить изображение'),(globalThis.HubI18n?.t?.("settings.249be5ebe83d") ?? 'Добавляет иллюстрацию или снимок экрана к задаче либо этапу, чтобы результат можно было проверить.')],
  hub_artifact:[(globalThis.HubI18n?.t?.("settings.9f2b7f773977") ?? 'Документы и материалы'),(globalThis.HubI18n?.t?.("settings.75e19526737d") ?? 'Сохранить файл результата'),(globalThis.HubI18n?.t?.("settings.d4d7b8873998") ?? 'Регистрирует документы и другие файлы, сохраняет их версии и прикрепляет к задаче.')],
  hub_check:[(globalThis.HubI18n?.t?.("settings.4f3fecc2e553") ?? 'Проверки и Git'),(globalThis.HubI18n?.t?.("settings.dee1e9cbda79") ?? 'Записать запуск и итог проверки'),(globalThis.HubI18n?.t?.("settings.22ceccb464e9") ?? 'Показывает, какая проверка выполнялась и чем завершилась. Набор проверок определяется правилами проекта.')],
  hub_checkpoint:[(globalThis.HubI18n?.t?.("settings.4f3fecc2e553") ?? 'Проверки и Git'),(globalThis.HubI18n?.t?.("settings.1aef4ef5a1e2") ?? 'Проверить контрольную точку'),(globalThis.HubI18n?.t?.("settings.de50ce48095d") ?? 'Читает состояние сохранения результата в Git и помогает повторить незавершённую публикацию без потери исходных сведений.')],
  hub_git_batch:[(globalThis.HubI18n?.t?.("settings.4f3fecc2e553") ?? 'Проверки и Git'),(globalThis.HubI18n?.t?.("settings.6ee5541e8e9a") ?? 'Согласовать общий коммит'),(globalThis.HubI18n?.t?.("settings.76d2705ac5ab") ?? 'Помогает проверить вклад нескольких работ в общий коммит и связать его с их результатами. Просмотр и согласование через API сами не создают коммит.')],
  hub_settings:[(globalThis.HubI18n?.t?.("settings.985b5e0f2ccf") ?? 'Настройки'),(globalThis.HubI18n?.t?.("settings.8b02e5780b9b") ?? 'Прочитать или изменить настройки проекта'),(globalThis.HubI18n?.t?.("settings.62ba96d60a5e") ?? 'Работает с настройками задач, просмотра, архитектуры и Git. Изменения выполняются по запросу пользователя.')],
  hub_migration_preview:[(globalThis.HubI18n?.t?.("settings.985b5e0f2ccf") ?? 'Настройки'),(globalThis.HubI18n?.t?.("settings.7417fe797284") ?? 'Посмотреть предложение по старым задачам'),(globalThis.HubI18n?.t?.("settings.9fd9b362a777") ?? 'Готовит предварительный разбор старых записей перед изменением их структуры; просмотр не меняет задачи.')],
});});
