"use strict";

(function (global) {
  const state = {paused:false, serverPaused:false, generation:0, timer:null, request:null, operations:[], pending:new Map(), uncertain:false, loaded:false,detailRoute:'', expiryTimer:null, hover:false, notices:new Map(), dismissed:new Set(), closedDetails:new Set(), historyLimits:new Map(), activities:new Map()};
  const storageKey = 'project-hub-operation-requests';
  const uiStorageKey = 'project-hub-operation-ui';
  const successLifetime = 15000;
  const activeStatuses = new Set(['requesting','queued','running','unknown']);
  const terminalStatuses = new Set(['succeeded','failed','interrupted']);
  const mutationSelector = ['[data-hub-mutation]','button[type="submit"]','form button:not([type])','input[type="submit"]',
    '[data-workspace-action="enable"]','[data-settings-action="save"]','[data-settings-action^="reset-"]',
    '[data-agent-instructions-action="save"]','[data-agent-instructions-action="retry"]','[data-hub-instructions-action="save"]','[data-hub-instructions-action^="reset-"]',
    '[data-setting]','[data-setting-column]','[data-backup-create]','[data-backup-restore]','[data-backup-delete]','[data-backup-upload]','[data-backup-retry]',
    '[data-storage-action="apply"]','[data-storage-action="prepare"]','[data-storage-action="recheck"]','[data-storage-action="retry"]',
    '[data-storage-folders-action="apply"]','[data-storage-folders-action="retry"]',
    '[data-project-action="archive"]','[data-project-action="unarchive"]','[data-project-action="delete"]','[data-project-action="recover"]','[data-project-action="retry"]','[data-operation-retry]'].join(',');
  const readonlySelector = '[data-readonly="true"],[data-local-open],[data-local-copy],[data-local-folder]';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const t = (key, ru, en) => global.HubI18n?.t?.(`operations.${key}`, global.HubI18n?.locale === 'en' ? en : ru) || (global.HubI18n?.locale === 'en' ? en : ru);
  const labels = {
    create:['Создание резервной копии','Create backup'], 'upload-complete':['Проверка ZIP','Verify ZIP'],
    'upload-start':['Загрузка ZIP','Upload ZIP'], 'restore-copy':['Подготовка ZIP к восстановлению','Prepare ZIP restore'],
    'import-folder':['Подготовка папки к импорту','Prepare folder import'], 'inspect-folder':['Проверка папки','Inspect folder'],
    'inspect-copy':['Проверка источника импорта','Inspect import source'], 'apply-import':['Применение импорта','Apply import'],
    'change-folders':['Изменение папок хранилища','Change storage folders'], 'upgrade-copy':['Преобразование источника','Convert source'],
    'delete-copy':['Удаление временной подготовки','Delete temporary preparation'], 'delete-archive':['Удаление архива','Delete archive'],
    'project-create':['Создание проекта','Create project'], 'project-update':['Изменение проекта','Update project'],
  };
  const phases = {
    requesting:['Отправка запроса','Sending request'], unknown:['Состояние уточняется','Checking status'],
    waiting:['Ожидание другой операции','Waiting for another operation'], preparing:['Подготовка','Preparing'],
    snapshot:['Подготовка данных источника','Preparing source data'], 'current-backup':['Сохранение резервной копии текущих данных','Saving a backup of current data'], 'source-copy':['Подготовка данных источника','Preparing source data'], 'source-format':['Преобразование старого формата','Converting the older format'], 'import-compatibility':['Проверка совместимости импорта','Checking import compatibility'], 'import-project-files':['Импорт файлов проектов','Importing project files'], 'publication-files':['Публикация файлов','Publishing files'], copying:['Копирование','Copying'],
    compressing:['Сжатие','Compressing'], verifying:['Проверка','Verifying'], inspecting:['Проверка источника','Inspecting source'],
    upload:['Передача файла','Transferring file'],
    restoring:['Подготовка восстановления','Preparing restore'], migrating:['Преобразование формата','Converting format'],
    importing:['Импорт проектов','Importing projects'], publishing:['Применение данных','Applying data'],
    restarting:['Проверка нового запуска','Checking new launch'], rollback:['Возврат прежнего состояния','Restoring previous state'],
    comparing:['Сравнение проектов','Comparing projects'], 'waiting-for-restart':['Ожидание перезапуска','Waiting for restart'],
    stopping:['Остановка сервера','Stopping server'], starting:['Запуск сервера','Starting server'],
    ready:['Готово','Ready'], 'waiting-for-drain':['Ожидание завершения текущих изменений','Waiting for current changes'],
    deleting:['Удаление','Deleting'], 'prepared-source':['Повторное использование подготовленного источника','Reusing prepared source'], 'current-format':['Проверка формата текущих данных','Checking the current data format'], 'current-revision':['Проверка текущей версии','Checking current revision'], 'prepared-candidate':['Проверка подготовленного результата','Checking the prepared result'], 'archive-extraction':['Распаковка архива','Extracting archive'], complete:['Завершено','Completed'],
  };
  const statuses = {requesting:['Отправка запроса','Sending request'],queued:['В очереди','Queued'],running:['Выполняется','Running'],succeeded:['Завершено','Completed'],failed:['Ошибка','Failed'],interrupted:['Прервано','Interrupted'],unknown:['Состояние уточняется','Checking status']};
  const label = (table, key, fallback) => { const pair = table[key]; return pair ? t(key,...pair) : fallback; };
  function phaseLabel(row) {
    const progress=row?.progress || {}, step=progress.step || row?.step;
    if (step && phases[step] && (!progress.phase || progress.phase === row?.phase)) return label(phases, step, '');
    if (row?.phase === 'snapshot') return label(phases, ['inspect-folder','inspect-copy','restore-copy','import-folder','upload-complete'].includes(row.action) ? 'source-copy' : 'current-backup', '');
    return label(phases, row?.phase, '');
  }
  const node = () => global.document?.querySelector?.('#backup-status');
  function persist() {
    try {global.sessionStorage?.setItem(storageKey,JSON.stringify([...state.pending.values()]));} catch (_) { /* Optional session persistence. */ }
  }
  try {
    const saved = JSON.parse(global.sessionStorage?.getItem(storageKey) || '[]');
    if (Array.isArray(saved)) for (const row of saved) if (row?.requestId && row?.action) state.pending.set(row.requestId,{...row,status:'unknown',phase:'unknown'});
  } catch (_) { /* Invalid pending state never overrides the server. */ }
  try {
    const saved = JSON.parse(global.sessionStorage?.getItem(uiStorageKey) || '{}');
    for (const id of saved.dismissed || []) if (typeof id==='string') state.dismissed.add(id);
    for (const id of saved.closedDetails || []) if (typeof id==='string') state.closedDetails.add(id);
    for (const [id, notice] of saved.notices || []) if (typeof id==='string' && Number.isFinite(notice?.until)) state.notices.set(id,{...notice,held:false});
  } catch (_) { /* Visibility preferences never replace server operation state. */ }
  function persistUI() {
    try {
      if(!state.dismissed.size && !state.closedDetails.size && !state.notices.size){global.sessionStorage?.removeItem?.(uiStorageKey);return;}
      global.sessionStorage?.setItem(uiStorageKey,JSON.stringify({dismissed:[...state.dismissed],closedDetails:[...state.closedDetails],notices:[...state.notices]}));
    } catch (_) { /* Optional session persistence. */ }
  }
  function active(row) {return activeStatuses.has(row?.status);}
  function terminal(row) {return terminalStatuses.has(row?.status);}
  function blocking(row) {
    const recovery=row.recovery || row.result?.recovery;
    return Boolean(row.blocking || row.rollback==='failed' || row.recovery?.blocking || row.result?.recovery?.blocking || ['pending','required','failed'].includes(typeof recovery==='string' ? recovery : recovery?.status));
  }
  function sameOperation(left,right) {return left.id===right.id || Boolean(left.requestId && left.requestId===right.requestId);}
  function canRetry(control) {return state.pending.get(control?.dataset?.operationRetry)?.status==='unknown';}
  function allowed(control) {return Boolean(control?.closest?.(readonlySelector) || control?.closest?.('form')?.getAttribute?.('method')?.toLowerCase()==='get' || canRetry(control));}
  function rows() {
    const requests = new Set(state.operations.map(row=>row.requestId));
    return [...state.pending.values()].filter(row=>!requests.has(row.requestId)).concat(state.operations);
  }
  const identity = row => String(row?.id || row?.requestId || '');
  function reconcile(row, previous, observed=false) {
    if (previous && terminal(previous) && active(row)) return previous;
    const progress=row.progress==null ? previous?.progress || {} : {...(previous?.phase===row.phase ? previous?.progress : {}),...row.progress};
    const merged = {...previous,...row,progress};
    if (terminal(merged) && !merged.finishedAt) merged.finishedAt = previous?.finishedAt || (observed || active(previous) ? new Date().toISOString() : merged.updatedAt || merged.createdAt);
    const id=identity(merged);
    if (previous && terminal(previous) && previous.status!==merged.status) state.notices.delete(id);
    const existingNotice=state.notices.get(id),finished=Date.parse(merged.finishedAt || '');
    if (existingNotice && existingNotice.finishedAt!==merged.finishedAt && merged.status==='succeeded' && Number.isFinite(finished) && finished+successLifetime<Date.now() && !existingNotice.held) state.notices.delete(id);
    if (terminal(merged) && !state.notices.has(id)) {
      if (observed && !previous || active(previous) || Number.isFinite(finished) && Date.now()-finished<successLifetime) state.notices.set(id,{until:(active(previous) ? Date.now() : Number.isFinite(finished) ? finished : Date.now())+successLifetime,finishedAt:merged.finishedAt,sticky:merged.status!=='succeeded',held:false});
    }
    return merged;
  }
  function workflow(row) {
    const archive=row.payload?.id || row.result?.id;
    return row.workflowId || (row.action==='upload-start' ? `upload:${row.id}` : row.action==='upload-complete' && archive ? `upload:${archive}` : identity(row));
  }
  function grouped(operations=rows()) {
    const groups=new Map();
    for (const row of operations) {const key=workflow(row);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}
    return [...groups.values()].map(members=>{
      const ordered=[...members].sort((a,b)=>Number(active(b) || blocking(b))-Number(active(a) || blocking(a)) || Number(b.action==='upload-complete')-Number(a.action==='upload-complete') || String(b.finishedAt || b.createdAt || '').localeCompare(String(a.finishedAt || a.createdAt || '')));
      return {...ordered[0],members};
    });
  }
  function noticeVisible(row) {
    if (active(row) || blocking(row)) return true;
    if (state.dismissed.has(identity(row))) return false;
    const notice=state.notices.get(identity(row));
    return Boolean(notice && (notice.sticky || notice.held || notice.until>Date.now()));
  }
  function feedback(id, message) {
    const row=rows().find(row=>identity(row)===id || row.requestId===id);
    return !row || noticeVisible(row) ? message : '';
  }
  function activityFeedback(receipt, text, refresh, scope='') {
    const key=receipt?.actionId || receipt?.id;if(!key)return {text,canDismiss:false};
    const id=`activity:${scope}:${key}`,status=receipt.state || receipt.status;
    const normalized=['done','ready','completed','succeeded'].includes(status) ? 'succeeded' : status==='interrupted' ? 'interrupted' : ['failed','cancelled'].includes(status) ? 'failed' : 'running';
    const previous=state.activities.get(id)?.row;
    const row=reconcile({...receipt,id,status:normalized,finishedAt:receipt.finishedAt || receipt.completedAt},previous,!previous && !receipt.finishedAt && !receipt.completedAt);
    if (receipt.status==='partial' || receipt.displayStatus==='partial') {const notice=state.notices.get(id);if(notice)notice.sticky=true;}
    state.activities.set(id,{row,refresh});
    updateLifetimes(rows().concat([...state.activities.values()].map(value=>value.row)));
    return {text:noticeVisible(row) ? text : '',canDismiss:terminal(row) && !blocking(row),id};
  }
  function baseLink(row) {
    return operationLink(row).replace(/\/operation\/[^/]*$/,'');
  }
  function operationLink(row) {
    const origin = row?.origin || {}, section = origin.section === 'settings' ? 'settings' : origin.section === 'data' ? 'projects/data' : origin.section === 'projects' ? 'projects/projects' : 'projects/backups';
    const project = origin.project ? `?project=${encodeURIComponent(origin.project)}` : (global.location?.search || '');
    return `${project}#${section}/operation/${encodeURIComponent(row?.id || row?.requestId || '')}`;
  }
  function sizeUnit(bytes) {
    return bytes>=1024**3 ? [1024**3,t('gigabytes','ГБ','GB')] : bytes>=1024**2 ? [1024**2,t('megabytes','МБ','MB')] : [1024,t('kilobytes','КБ','KB')];
  }
  function number(value) {
    return new Intl.NumberFormat(global.HubI18n?.locale==='en' ? 'en-GB' : 'ru-RU',{maximumFractionDigits:1}).format(value);
  }
  function sizeNumber(bytes, scale) {return bytes>0 && bytes/scale<0.1 ? `<${number(0.1)}` : number(bytes/scale);}
  function formatSize(value) {
    if (value==null || value==='') return '—';
    const bytes=Number(value);if(!Number.isFinite(bytes) || bytes<0)return '—';
    const [scale,unit]=sizeUnit(bytes);return `${sizeNumber(bytes,scale)} ${unit}`;
  }
  function byteProgress(row) {return row?.progress?.unit==='bytes' || row?.progress?.bytesProcessed!=null || row?.action==='upload-start';}
  function progressText(row) {
    const progress = row?.progress || {}, completed = Number(progress.completed ?? progress.bytesProcessed), total = Number(progress.total ?? progress.totalBytes);
    if (!Number.isFinite(completed) || completed < 0) return '';
    if (byteProgress(row)) {
      if (row.status==='succeeded') return formatSize(completed);
      const [scale,unit]=sizeUnit(Number.isFinite(total) && total>0 ? total : completed);
      return Number.isFinite(total) && total>0 ? `${sizeNumber(completed,scale)} / ${sizeNumber(total,scale)} ${unit}` : formatSize(completed);
    }
    if (!progress.unit && total===1) return '';
    const unit=progress.unit==='files' ? t('files','файлов','files') : progress.unit==='projects' ? t('projects','проектов','projects') : '';
    return `${number(completed)}${Number.isFinite(total) && total>0 ? ` / ${number(total)}` : ''}${unit ? ` ${unit}` : ''}`;
  }
  function elapsed(row) {
    const start=Date.parse(row?.startedAt || ''),end=terminal(row) ? Date.parse(row?.finishedAt || '') : Date.now();
    if (Number.isFinite(start) && Number.isFinite(end)) return Math.max(0,Math.round((end-start)/1000));
    if (row?.elapsed!=null && Number.isFinite(Number(row.elapsed))) return Math.max(0,Math.round(Number(row.elapsed)));
    const created=Date.parse(row?.createdAt || '');
    return Number.isFinite(created) && Number.isFinite(end) ? Math.max(0,Math.round((end-created)/1000)) : null;
  }
  function duration(seconds) {
    if (seconds==null) return '';
    const hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60),rest=seconds%60;
    return [hours ? `${hours} ${t('hours','ч','h')}` : '',minutes ? `${minutes} ${t('minutes','мин','min')}` : '',rest || !hours && !minutes ? `${rest} ${t('seconds','с','s')}` : ''].filter(Boolean).join(' ');
  }
  const results = {
    create:['Резервная копия создана','Backup created'],'upload-start':['Файл передан','File transferred'],'upload-complete':['ZIP загружен и проверен','ZIP uploaded and verified'],
    'restore-copy':['ZIP подготовлен к восстановлению','ZIP prepared for restore'],'import-folder':['Папка подготовлена к импорту','Folder prepared for import'],
    'inspect-folder':['Источник проверен','Source inspected'],'inspect-copy':['Источник проверен','Source inspected'],'apply-import':['Данные применены','Data applied'],
    'change-folders':['Папки изменены','Folders changed'],'upgrade-copy':['Источник преобразован','Source converted'],'delete-copy':['Подготовленный источник удалён','Prepared source deleted'],
    'delete-archive':['Архив удалён','Archive deleted'],'project-create':['Проект создан','Project created'],'project-update':['Проект изменён','Project updated'],
  };
  function completion(row) {
    const result=results[row.action];
    return row.status==='succeeded' && result ? t(`result-${row.action}`,...result) : label(statuses,row.status,t('operation','Операция','Operation'));
  }
  function scopeText(row) {
    if (row.origin?.section === 'before-import' || row.origin?.kind === 'before-import' || row.origin?.origin === 'before-import') return t('beforeImport','Автоматическая копия перед импортом','Automatic backup before import');
    if (row.action==='change-folders') return t('installation','Вся установка','Entire installation');
    if (row.action==='apply-import') return row.payload?.mode==='add' ? t('selectedProjects','Выбранные проекты','Selected projects') : t('allData','Всё хранилище','Entire data store');
    if (['restore-copy','import-folder','inspect-folder','inspect-copy','upgrade-copy','delete-copy'].includes(row.action)) return t('source','Источник импорта','Import source');
    if (row.action?.startsWith('upload-') || row.action==='delete-archive') return t('archive','ZIP-архив','ZIP archive');
    if (!row.action?.startsWith('project-')) return t('allProjects','Все проекты','All projects');
    const project=row.result?.project || {},id=project.id || row.origin?.project;
    const catalog=global.HubProjectsUI?.catalog?.() || global.projectCatalog;
    return project.name || row.origin?.projectName || catalog?.projects?.find?.(project=>project.id===id)?.name || t('project','Проект','Project');
  }
  function rowText(row) {
    const status = completion(row);
    const phase = terminal(row) ? '' : phaseLabel(row);
    const transfer=row.action==='upload-complete' ? rows().find(item=>workflow(item)===workflow(row) && item.action==='upload-start') : null;
    const seconds = elapsed(row), progress = progressText(row) || (transfer ? formatSize(transfer.progress?.total ?? transfer.progress?.totalBytes) : '');
    return [status,phase && phase!==status ? phase : '',duration(seconds),progress].filter(Boolean).join(' · ');
  }
  function conflictRows(row) {return Array.isArray(row?.errorBody?.conflicts) ? row.errorBody.conflicts.filter(value=>value && typeof value==='object') : [];}
  function errorText(row) {
    const conflicts=conflictRows(row);
    if(conflicts.length && conflicts.every(value=>value.type==='ambiguous-global-data')) {
      return t('unrecognizedSharedData','Импорт остановлен: не удалось определить назначение общих данных источника.','Import stopped: some shared source data could not be classified.');
    }
    const raw=typeof row?.error === 'string' ? row.error : row?.error?.message || row?.error?.reason || '';
    if (/WinError\s*32|being used by another process|used by another process/i.test(raw)) return t('pathBusy','Папка занята другим процессом. Закройте приложения, использующие эти данные, и повторите операцию.','The folder is in use by another process. Close applications using these data and retry.');
    return raw;
  }
  function failureDetails(row) {
    const conflicts=conflictRows(row), payload=row.payload || {};
    if(!conflicts.length)return '';
    const labels={'ambiguous-global-data':['Неизвестные общие данные','Unrecognized shared data'],
      'cross-project-link':['Связь между проектами','Cross-project link'],
      'missing-project-reference':['Не найден связанный проект','Referenced project missing'],
      'record-key':['Конфликт записей','Record conflict'],'schema-conflict':['Несовместимая схема','Schema mismatch']};
    const choices=row.action==='apply-import' ? '<p>'+esc(t('importMode','Режим импорта','Import mode'))+': '+esc(payload.mode==='add' ? t('addProjects','Добавление проектов','Add projects') : t('restoreAll','Восстановление хранилища','Restore entire data store'))+'</p>'+
      (Array.isArray(payload.projects) ? '<p>'+esc(t('chosenProjects','Выбранные проекты','Selected projects'))+': <code>'+esc(payload.projects.slice(0,40).join(', '))+'</code></p>' : '')+
      '<p>'+esc(t('customRulesChoice','Общие пользовательские инструкции','Global user instructions'))+': '+esc(payload.includeGlobals ? t('replaceRules','Перенос из источника','Import from source') : t('retainRules','Сохранение действующих','Keep current'))+'</p>' : '';
    const content=conflicts.map(value=>{
      const description=label(labels,value.type,value.message || value.type || t('conflict','Конфликт данных','Data conflict'));
      const context=[value.path,value.database,value.table,value.project,...(Array.isArray(value.requiredProjects)?value.requiredProjects.slice(0,20):[])].filter(item=>typeof item==='string').join(' · ');
      return '<li>'+esc(description)+(context ? ': <code>'+esc(context)+'</code>' : '')+'</li>';
    }).join('');
    return '<div class="hub-operation-failure-details"><h4>'+esc(t('importFailureReasons','Что помешало применению данных','Why data could not be applied'))+'</h4>'+choices+
      (row.action==='apply-import' && !row.publication && !blocking(row) ? '<p>'+esc(t('projectsNotApplied','Проекты не применены. Рабочие данные сохранены.','Projects were not applied. Active data were preserved.'))+'</p>' : '')+
      '<ul class="hub-operation-conflicts">'+content+'</ul></div>';
  }
  function title(row) {return workflow(row).startsWith('upload:') ? t('uploadWorkflow','Загрузка и проверка ZIP','Upload and verify ZIP') : label(labels,row.action,t('operation','Операция','Operation'));}
  function progressHtml(row) {
    if (!active(row)) return '';
    const value=Number(row.progress?.completed ?? row.progress?.bytesProcessed),total=Number(row.progress?.total ?? row.progress?.totalBytes);
    if (!Number.isFinite(value) || !Number.isFinite(total) || total<=0) return `<progress class="hub-operation-progress" aria-label="${esc(t('progress','Ход операции','Operation progress'))}"></progress>`;
    const percent=Math.min(100,Math.max(0,value/total*100));
    return `<progress class="hub-operation-progress" max="100" value="${percent}" aria-label="${esc(t('progress','Ход операции','Operation progress'))}"></progress><span class="hub-operation-percent" aria-hidden="true">${number(Math.min(value<total ? 99.9 : 100,percent))}%</span>`;
  }
  function detailHtml(row, transient=false) {
    if (!row) return `<p role="status">${esc(t('loadingDetails','Сведения об операции загружаются…','Loading operation details…'))}</p>`;
    const result = row.result || {}, recovery = result.recovery || row.recovery || row.rollback, paths = [['sourcePath','import-source'],['path','import-source'],['dataHome','data'],['backupHome','backups']];
    const resultPaths = paths.filter(([key])=>typeof result[key]==='string').map(([key,kind])=>`<p>${global.HubLocalFiles?.pathLink(result[key],result[key]===result.activeHome || key==='dataHome' ? 'data' : /\.zip$/i.test(result[key]) ? 'backups' : kind,{reveal:/\.zip$/i.test(result[key])}) || `<code>${esc(result[key])}</code>`}</p>`).join('');
    const copyId = result.copyId || result.preview?.copyId;
    const recoveryState=typeof recovery==='string' ? recovery : recovery?.status;
    const recoveryText=recoveryState==='succeeded' ? t('restored','Прежние данные и настройки восстановлены','Previous data and settings restored') : recoveryState==='failed' ? t('recoveryRequired','Требуется восстановление; данные сохранены','Recovery required; data preserved') : recoveryState;
    const close=transient ? `<button type="button" data-readonly="true" data-operation-details-close="${esc(identity(row))}">${esc(t('closeDetails','Закрыть подробности','Close details'))}</button>` : `<a href="${esc(baseLink(row))}" data-readonly="true" data-operation-details-close="${esc(identity(row))}">${esc(t('closeDetails','Закрыть подробности','Close details'))}</a>`;
    const wait=Date.parse(row.startedAt || '')-Date.parse(row.createdAt || '');
    const stages=workflow(row).startsWith('upload:') ? rows().filter(item=>workflow(item)===workflow(row)).sort((a,b)=>Number(a.action==='upload-complete')-Number(b.action==='upload-complete')) : [];
    const stageHtml=stages.length>1 ? `<ol class="hub-operation-stages">${stages.map(item=>`<li><strong>${esc(label(labels,item.action,''))}</strong> · ${esc(rowText(item))}</li>`).join('')}</ol>` : '';
    const sourcePreview=['restore-copy','upload-complete'].includes(row.action) && copyId;
    return `<section class="hub-operation-details" data-operation-id="${esc(identity(row))}"><div class="hub-operation-heading"><h3>${esc(title(row))}</h3>${close}</div><p>${esc(rowText(row))}</p>${progressHtml(row)}<p class="caption">${esc(scopeText(row))}</p>${stageHtml}${Number.isFinite(wait) && wait>=1000 ? `<p class="caption">${esc(t('queueTime','Ожидание в очереди','Queue wait'))}: ${esc(duration(Math.round(wait/1000)))}</p>` : ''}${row.origin?.project && row.action?.startsWith('project-') ? `<details class="hub-operation-technical"><summary>${esc(t('technical','Технические сведения','Technical details'))}</summary><code>${esc(row.origin.project)}</code></details>` : ''}${row.waitingFor || row.blockedBy ? `<p>${esc(t('waitingFor','Ожидается завершение другой операции','Waiting for another operation'))}</p>` : ''}${errorText(row) ? `<p class="backup-job-error">${esc(errorText(row))}</p>` : ''}${failureDetails(row)}${recovery ? `<p>${esc(t('recovery','Состояние восстановления','Recovery state'))}: ${esc(recoveryText)}</p>` : ''}${resultPaths}${sourcePreview ? `<p>${esc(t('sourcePreserved','Рабочие данные и исходный архив сохранены.','Active data and the source archive are preserved.'))}</p>` : ''}${copyId ? `<a href="${esc(`${row.origin?.project ? `?project=${encodeURIComponent(row.origin.project)}` : global.location?.search || ''}#projects/data/import/${encodeURIComponent(copyId)}`)}">${esc(t('previewResult','Открыть предварительный просмотр импорта','Open import preview'))}</a>` : ''}${row.status==='succeeded' ? `<p class="caption">${esc(t('success','Сведения об операции доступны в истории операций.','Operation details are available in operation history.'))}</p>` : ''}</section>`;
  }
  function applyReadonly() {
    global.document?.querySelectorAll?.(mutationSelector).forEach(control=>{
      const paused=state.paused && !allowed(control);
      if (paused && !control.disabled) {control.dataset.hubPausedDisabled='true';control.disabled=true;}
      else if (!paused && control.dataset.hubPausedDisabled==='true') {delete control.dataset.hubPausedDisabled;control.disabled=false;}
    });
  }
  function historyBody(section) {
    const operations=grouped().filter(row=>terminal(row) && (section==='all' || (row.origin?.section || 'backups')===section)).sort((a,b)=>String(b.finishedAt || b.createdAt || '').localeCompare(String(a.finishedAt || a.createdAt || '')));
    const limit=state.historyLimits.get(section) || 20;
    if (!operations.length) return `<p class="caption">${esc(t('noHistory','Завершённых операций пока нет.','No completed operations yet.'))}</p>`;
    return `<div class="admin-table-wrap"><table class="admin-table"><thead><tr>${[t('operation','Операция','Operation'),t('date','Дата','Date'),t('result','Результат','Result')].map(value=>`<th>${esc(value)}</th>`).join('')}</tr></thead><tbody>${operations.slice(0,limit).map(row=>{
      const at=Date.parse(row.finishedAt || row.createdAt || '');
      const date=Number.isFinite(at) ? new Intl.DateTimeFormat(global.HubI18n?.locale==='en' ? 'en-GB' : 'ru-RU',{dateStyle:'medium',timeStyle:'short'}).format(at) : '—';
      return `<tr data-ui-key="operation-history-${esc(identity(row))}"><td><a href="${esc(operationLink(row))}">${esc(title(row))}</a><small class="hub-operation-scope">${esc(scopeText(row))}</small></td><td>${esc(date)}</td><td>${esc(rowText(row))}${errorText(row) ? `<p class="backup-job-error">${esc(errorText(row))}</p>` : ''}</td></tr>`;
    }).join('')}</tbody></table></div>${operations.length>limit ? `<button type="button" data-readonly="true" data-operation-history-more="${esc(section)}">${esc(t('moreHistory','Показать ещё','Show more'))}</button>` : ''}`;
  }
  function history(section='all') {
    return `<details class="admin-history hub-operation-history" data-ui-key="operation-history-${esc(section)}"><summary>${esc(t('history','История операций','Operation history'))}</summary><div data-operation-history="${esc(section)}">${historyBody(section)}</div></details>`;
  }
  function updateLifetimes(operations) {
    const now=Date.now(),banner=node();
    const focused=Boolean(banner?.contains?.(global.document?.activeElement));
    const detailIds=[...(global.document?.querySelectorAll?.('[data-operation-details]') || [])].filter(target=>target.dataset.operationTransient!=='true' && !target.closest?.('[hidden]')).map(target=>target.dataset.operationDetails);
    for (const row of operations) {
      const notice=state.notices.get(identity(row));if(!notice || notice.sticky)continue;
      const held=state.hover || focused || detailIds.includes(identity(row));
      if (held && !notice.held && notice.until>now) {notice.remaining=notice.until-now;notice.held=true;}
      else if (!held && notice.held) {notice.until=now+notice.remaining;notice.held=false;}
    }
    if(state.expiryTimer){global.clearTimeout(state.expiryTimer);state.expiryTimer=null;}
    const deadlines=[...state.notices.values()].filter(notice=>!notice.sticky && !notice.held && notice.until>now).map(notice=>notice.until);
    if(deadlines.length)state.expiryTimer=global.setTimeout(()=>notify(),Math.max(1,Math.min(...deadlines)-now));
    persistUI();
  }
  function bannerRow(row) {
    const closable=terminal(row) && !blocking(row) && !row.members?.some(item=>active(item) || blocking(item));
    return `<div class="hub-operation-row" data-operation-status="${esc(row.status)}" data-ui-key="operation-${esc(identity(row))}"><div class="hub-operation-summary"><a href="${esc(operationLink(row))}">${esc(title(row))}</a><span class="hub-operation-scope">${esc(scopeText(row))}</span><span class="hub-operation-description">${esc(rowText(row))}</span>${progressHtml(row)}${errorText(row) ? `<span class="backup-job-error">${esc(errorText(row))}</span>` : ''}${blocking(row) ? `<span class="backup-job-error">${esc(t('recoveryRequired','Требуется восстановление; данные сохранены','Recovery required; data preserved'))}</span>` : ''}</div><div class="hub-operation-actions"><a class="hub-operation-more" href="${esc(operationLink(row))}">${esc(t('details','Подробнее','Details'))}</a>${closable ? `<button type="button" class="hub-operation-dismiss" data-readonly="true" data-operation-dismiss="${esc(identity(row))}" aria-label="${esc(t('dismiss','Закрыть уведомление','Dismiss notification'))}: ${esc(title(row))}" title="${esc(t('dismiss','Закрыть уведомление','Dismiss notification'))}">×</button>` : ''}</div></div>`;
  }
  function render() {
    state.paused=state.serverPaused || state.pending.size>0 || state.operations.some(row=>active(row) || blocking(row));
    const banner = node(), operations = rows();
    updateLifetimes(operations.concat([...state.activities.values()].map(value=>value.row)));
    const visible=grouped(operations).filter(noticeVisible).sort((a,b)=>Number(active(b) || blocking(b))-Number(active(a) || blocking(a)) || String(b.finishedAt || b.createdAt || '').localeCompare(String(a.finishedAt || a.createdAt || '')));
    if (banner) {
      banner.setAttribute?.('aria-label',t('operations','Операции','Operations'));
      banner.hidden = !state.paused && !state.uncertain && !visible.length;
      banner.dataset.writesPaused = String(state.paused);
      const notice = state.paused ? t('paused','Просмотр доступен. Изменения временно приостановлены.','Viewing is available. Changes are temporarily paused.') : '';
      const connection = state.uncertain ? t('reconnecting','Связь потеряна. Состояние операций уточняется; прежняя блокировка сохраняется до ответа сервера.','Connection lost. Checking operation status; the previous write lock remains until the server responds.') : '';
      const announcement=[notice,connection,...visible.map(row=>`${title(row)}: ${completion(row)}${!terminal(row) && phaseLabel(row) ? ` · ${phaseLabel(row)}` : ''}`)].filter(Boolean).join('. ');
      const html = `<p class="hub-operation-announcement" role="status" aria-live="polite" aria-atomic="true">${esc(announcement)}</p>${notice ? `<p class="hub-operation-notice">${esc(notice)}</p>` : ''}${connection ? `<p>${esc(connection)}</p>` : ''}<div class="hub-operation-list">${visible.map(bannerRow).join('')}</div>`;
      if (global.HubLiveUI) global.HubLiveUI.patch(banner,html); else banner.innerHTML=html;
    }
    global.document?.querySelectorAll?.('[data-operation-details]').forEach(target=>{
      const id = target.dataset.operationDetails, row=operations.find(row=>row.id===id || row.requestId===id);
      const transient=target.dataset.operationTransient==='true';
      const hidden=transient && (state.closedDetails.has(id) || row && !noticeVisible(row));
      target.hidden=Boolean(hidden);
      const html = hidden ? '' : detailHtml(row,transient);
      if (global.HubLiveUI) global.HubLiveUI.patch(target,html); else target.innerHTML=html;
    });
    global.document?.querySelectorAll?.('[data-operation-history]').forEach(target=>{
      const html=historyBody(target.dataset.operationHistory);
      if(global.HubLiveUI)global.HubLiveUI.patch(target,html);else target.innerHTML=html;
    });
    applyReadonly();
  }
  function notify() {
    render();
    if (global.CustomEvent) global.dispatchEvent?.(new global.CustomEvent('hub-operations-changed',{detail:{writesPaused:state.paused,operations:rows(),uncertain:state.uncertain}}));
    for(const value of state.activities.values())value.refresh?.();
  }
  function begin(body, origin = body?.origin || {section:'backups'}) {
    if (!body?.requestId) return;
    if (state.operations.some(row=>row.requestId===body.requestId && terminal(row))) return;
    state.generation++;
    state.pending.set(body.requestId,{id:body.requestId,requestId:body.requestId,action:body.action,status:'requesting',phase:'requesting',createdAt:new Date().toISOString(),origin});
    persist();notify();
  }
  function acknowledge(row, body) {
    if (!row?.id) return;
    const requestId = row.requestId || body?.requestId;
    const previous=state.operations.find(item=>item.id===row.id || requestId && item.requestId===requestId);
    if (previous && terminal(previous) && !terminal(row)) return;
    state.generation++;
    if (requestId) state.pending.delete(requestId);
    const merged=reconcile({...row,requestId,payload:row.payload || body || previous?.payload,origin:row.origin || body?.origin || previous?.origin || {section:'backups'}},previous,Boolean(body || active(previous)));
    state.operations=[merged,...state.operations.filter(item=>item.id!==row.id && (!requestId || item.requestId!==requestId))];
    persist();notify();
  }
  function uncertain(body) {
    const row = state.pending.get(body?.requestId);
    if (!row) return;
    state.generation++;row.status='unknown';row.phase='unknown';persist();
    state.uncertain=true;notify();
  }
  function reject(body, error) {
    const row = state.pending.get(body?.requestId);
    if (row) {state.generation++;state.pending.delete(body.requestId);state.operations.unshift(reconcile({...row,status:'failed',phase:'complete',finishedAt:new Date().toISOString(),error:error?.message || String(error)},row,true));persist();}
    notify();
  }
  async function poll() {
    if (state.request) return state.request;
    if (state.timer) {global.clearTimeout(state.timer);state.timer=null;}
    const generation=state.generation;
    state.request = (async()=>{
      try {
        const response = await fetch('/api/v1/backups/status',{cache:'no-store'}), data = await response.json();
        if (!response.ok || typeof data?.writesPaused!=='boolean' || !Array.isArray(data.operations)) throw Error('Invalid operation status');
        // A status snapshot started before a local request or acknowledgement
        // cannot erase that newer state. The next poll will reconcile it.
        if (generation!==state.generation) return;
        const operations=data.operations.map(row=>{
          const previous=state.operations.find(item=>sameOperation(item,row));
          return reconcile(row,previous);
        });
        // Absence from a snapshot is not confirmation that an operation ended.
        for (const previous of state.operations) if (!operations.some(row=>sameOperation(row,previous))) operations.push(previous);
        state.serverPaused=data.writesPaused;state.operations=operations;state.uncertain=false;state.loaded=true;
        for(const row of data.operations) if(row.requestId && (active(row) || terminal(row)))state.pending.delete(row.requestId);
        persist();notify();
      } catch (_) {state.uncertain=true;notify();}
      finally {state.request=null;state.timer=global.setTimeout(poll,2000);}
    })();
    return state.request;
  }
  global.document?.addEventListener?.('submit',event=>{
    if (!state.paused || allowed(event.submitter || event.target) || event.target?.getAttribute?.('method')?.toLowerCase()==='get')return;
    event.preventDefault();event.stopImmediatePropagation();render();
  },true);
  global.document?.addEventListener?.('click',event=>{
    const activity=event.target?.closest?.('[data-activity-dismiss]');
    if(activity){event.preventDefault();dismissActivity(activity.dataset.activityDismiss);return;}
    const control=event.target?.closest?.(mutationSelector);
    if (!state.paused || !control || allowed(control))return;
    event.preventDefault();event.stopImmediatePropagation();render();
  },true);
  global.document?.addEventListener?.('click',event=>{
    const close=event.target?.closest?.('[data-operation-dismiss]');
    if(close){event.preventDefault();dismiss(close.dataset.operationDismiss);return;}
    const detail=event.target?.closest?.('[data-operation-details-close]');
    if(detail){if(detail.tagName!=='A')event.preventDefault();state.closedDetails.add(detail.dataset.operationDetailsClose);persistUI();notify();}
    const more=event.target?.closest?.('[data-operation-history-more]');
    if(more){event.preventDefault();const section=more.dataset.operationHistoryMore;state.historyLimits.set(section,(state.historyLimits.get(section) || 20)+20);render();}
  },true);
  function dismissActivity(id) {
    const row=state.activities.get(id)?.row;if(!terminal(row) || blocking(row))return false;
    state.dismissed.add(id);persistUI();notify();return true;
  }
  function dismiss(id) {
    const row=grouped().find(row=>identity(row)===id);
    if(!row || !terminal(row) || blocking(row) || row.members.some(item=>active(item) || blocking(item)))return false;
    for(const item of row.members)state.dismissed.add(identity(item));
    persistUI();notify();
    const banner=node(),next=!banner?.hidden ? banner?.querySelector?.('.hub-operation-more') : global.document?.querySelector?.('main h1');
    if(next){if(!['A','BUTTON'].includes(next.tagName))next.setAttribute?.('tabindex','-1');next.focus?.({preventScroll:true});}
    return true;
  }
  function details(id,{transient=false}={}) {
    const row=rows().find(row=>row.id===id || row.requestId===id);
    if(transient && (state.closedDetails.has(id) || row && !noticeVisible(row)))return '';
    return `<div data-operation-details="${esc(id)}" data-operation-transient="${transient}" tabindex="-1">${detailHtml(row,transient)}</div>`;
  }
  function afterRender() {
    render();
    const banner=node();
    if(banner && !banner.__operationVisibilityBound){
      banner.__operationVisibilityBound=true;
      banner.addEventListener?.('pointerenter',()=>{state.hover=true;render();});
      banner.addEventListener?.('pointerleave',()=>{state.hover=false;render();});
      banner.addEventListener?.('focusin',()=>render());
      banner.addEventListener?.('focusout',()=>global.setTimeout(render,0));
    }
    const hash=global.location?.hash || '',parts=hash.replace(/^#/,'').split('/'),index=parts.indexOf('operation');
    if(index<0){state.detailRoute='';return;}
    if(state.detailRoute===hash)return;
    let id;try{id=decodeURIComponent(parts[index+1] || '');}catch(_){return;}
    const targets=global.document?.querySelectorAll?.('[data-operation-details]') || [];
    const target=[...targets].find(target=>target.dataset.operationDetails===id && !target.closest?.('[hidden]'));
    if(target){state.detailRoute=hash;target.focus?.({preventScroll:true});target.scrollIntoView?.({block:'start'});}
  }
  global.backupStatus={isPaused:()=>state.paused,refresh:poll,begin,acknowledge,uncertain,reject,operations:rows,operationLink,details,afterRender,description:rowText,title,formatSize,progressText,duration,history,feedback,dismiss,activityFeedback,dismissActivity};
  global.addEventListener?.('hub-language-changed',render);
  render();void poll();
})(typeof window==='undefined'?globalThis:window);
