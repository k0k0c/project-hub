"use strict";

const backupsState = {
  loading: false,
  busy: false,
  error: "",
  backups: [],
  restoreCopies: [],
  jobs: [],
  catalogLoaded: false,
  preview: null,
  selectedFile: null,
  root: null,
  pollTimer: null,
  polling: false,
  jobRequest: null, lastRestore: null, backupHome:'', detailId:'', handledResults:new Set(),uploadRequest:null,
  page: 1, historyPage: 1, pageSize: 20, sort: "createdAt", direction: "desc", pagination: null, capabilities: {},
};

const backupApi = async (options = {}) => {
  const response = await fetch(options.url || "/api/v1/backups", {
    cache: "no-store",
    ...options,
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
  });
  let body = null;
  try { body = await response.json(); } catch (_) { /* handled below */ }
  if (!response.ok) {const error=new Error(body?.error || (globalThis.HubI18n?.t?.("backups.8684ae415a8d") ?? "Не удалось выполнить операцию с резервной копией"));error.status=response.status;throw error;}
  return body || {};
};

const backupDate = value => {
  if (!value) return "—";
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Intl.DateTimeFormat((globalThis.HubI18n?.locale==='en'?'en-GB':'ru-RU'), {dateStyle: "medium", timeStyle: "short"}).format(time) : String(value);
};
const backupSize = value => {
  if (globalThis.backupStatus?.formatSize) return globalThis.backupStatus.formatSize(value);
  const bytes = Number(value);
  if (value==null || value==='' || !Number.isFinite(bytes) || bytes < 0) return "—";
  const scale=bytes>=1024**3 ? 1024**3 : bytes>=1024**2 ? 1024**2 : 1024;
  const english=globalThis.HubI18n?.locale==='en',units=english ? ['KB','MB','GB'] : ['КБ','МБ','ГБ'];
  const number=new Intl.NumberFormat(english ? 'en-GB' : 'ru-RU',{maximumFractionDigits:1});
  return `${bytes>0 && bytes/scale<0.1 ? '<'+number.format(0.1) : number.format(bytes/scale)} ${units[scale===1024 ? 0 : scale===1024**2 ? 1 : 2]}`;
};
const backupError = error => (globalThis.HubI18n?.error?.(error) ?? error?.message) || (globalThis.HubI18n?.t?.("backups.2d55ddef0ce5") ?? "Неизвестная ошибка");

function backupBusy(buttons, busy) {
  buttons.forEach(button => { if (button) button.disabled = busy; });
}
function backupEnableControls(root) {
  if (!root) return;
  root.querySelectorAll("[data-backup-create], [data-backup-restore], [data-backup-delete]").forEach(button => { button.disabled = !!backupsState.jobRequest; });
  const upload = root.querySelector("[data-backup-upload]");
  if (upload) upload.disabled = !backupsState.selectedFile || Boolean(backupsState.jobRequest);
  const retry = root.querySelector('[data-backup-retry]');if (retry) retry.hidden = !backupsState.jobRequest;
  globalThis.backupStatus?.afterRender?.();
}

const backupJobPhase = {preparing: (globalThis.HubI18n?.t?.("backups.5ea5c68f20d4") ?? "Подготовка"), snapshot: (globalThis.HubI18n?.t?.("backups.fd2517f93c21") ?? "Снимок данных"), compressing: (globalThis.HubI18n?.t?.("backups.9d075c6c6973") ?? "Сжатие"), verifying: (globalThis.HubI18n?.t?.("backups.e56a412d1285") ?? "Проверка"), restoring: (globalThis.HubI18n?.t?.("backups.844267b67b7e") ?? "Восстановление")};
const backupJobActive = job => job && (job.status === "queued" || job.status === "running");
function backupJobText(job) {
  if (!job) return "";
  if (globalThis.backupStatus?.description) return globalThis.backupStatus.description(job);
  const progress = job.progress || {};
  const completed = Number(progress.completed);
  const total = Number(progress.total);
  const counter = Number.isFinite(completed) && Number.isFinite(total) && total > 1 ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("backups.ffc7bd0bca35",{v0:(Math.max(0, completed)),v1:(total)}) : ` · ${Math.max(0, completed)} из ${total}`) : "";
  const sourcePhase = ['restore-copy','upload-complete','inspect-folder','inspect-copy','import-folder'].includes(job.action) && job.phase === 'snapshot' ? backupLabel('sourceCopy', 'Подготовка данных источника') : '';
  const phase = sourcePhase || (job.phase === 'deleting' ? backupLabel('deleting', 'Удаление') : job.phase === 'waiting' ? backupLabel('waiting', 'Ожидание другой операции') : backupJobPhase[job.phase] || (globalThis.HubI18n?.t?.("backups.822d93cab5c7") ?? "Операция"));
  const elapsed = job.startedAt ? Math.max(0, Math.round((Date.now() - Date.parse(job.startedAt)) / 1000)) : 0;
  return `${phase}${counter}${elapsed ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("backups.ef95ffda901b",{v0:(elapsed)}) : ` · ${elapsed} с`) : ""}`;
}
function backupJobRows() {
  return backupsState.jobs.filter(backupJobActive).map(job => {
    const terminal = job.status === "succeeded" ? (globalThis.HubI18n?.t?.("backups.b459ff8f254e") ?? "Завершено") : job.status === "failed" ? (globalThis.HubI18n?.t?.("backups.bf22dfeeba8b") ?? "Ошибка") : job.status === "interrupted" ? (globalThis.HubI18n?.t?.("backups.b3ce53956234") ?? "Прервано") : backupJobText(job);
    const error = job.error ? `<span class="backup-job-error">${escape(job.error)}</span>` : "";
    return `<p class="backup-job" data-backup-job="${escape(job.id || "")}" role="status"><strong>${escape(backupActionLabel(job.action))}</strong><span>${escape(terminal)}</span>${error}</p>`;
  }).join("");
}

function backupPreview(preview) {
  if (!preview) return "";
  const version = preview.formatVersion ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("backups.06e1f1d51266",{v0:(escape(`${preview.formatVersion.major}.${preview.formatVersion.minor}`))}) : `Формат ${escape(`${preview.formatVersion.major}.${preview.formatVersion.minor}`)}`) : (globalThis.HubI18n?.t?.("backups.1d8b8e7f21aa") ?? "Формат неизвестен");
  const projects = Array.isArray(preview.projects) ? preview.projects : [];
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("backups.aaca6cc1758d",{v0:(version),v1:(escape(String(preview.files ?? 0))),v2:(escape(backupSize(preview.totalBytes))),v3:(escape(backupDate(preview.createdAt))),v4:(projects.length ? `<ul class="backup-project-list">${projects.map(project => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("backups.7c0cc70f040a",{v0:(escape(project.name || project.id || (globalThis.HubI18n?.t?.("backups.f45edf006851") ?? "Проект"))),v1:(escape(String(project.tasks ?? 0))),v2:(escape(String(project.journalEvents ?? 0)))}) : `<li><strong>${escape(project.name || project.id || (globalThis.HubI18n?.t?.("backups.f45edf006851") ?? "Проект"))}</strong><span>${escape(String(project.tasks ?? 0))} задач · ${escape(String(project.journalEvents ?? 0))} событий журнала</span></li>`)).join("")}</ul>` : (globalThis.HubI18n?.t?.("backups.fc4d428a1b96") ?? '<p class="caption">Проекты в архиве не указаны.</p>'))}) : `<section class="backup-preview" aria-label="Предварительный просмотр резервной копии"><div class="section-head"><h3>Предварительный просмотр</h3><span class="caption">${version}</span></div><p>${escape(String(preview.files ?? 0))} файлов · ${escape(backupSize(preview.totalBytes))} · создана ${escape(backupDate(preview.createdAt))}</p>${projects.length ? `<ul class="backup-project-list">${projects.map(project => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("backups.7c0cc70f040a",{v0:(escape(project.name || project.id || (globalThis.HubI18n?.t?.("backups.f45edf006851") ?? "Проект"))),v1:(escape(String(project.tasks ?? 0))),v2:(escape(String(project.journalEvents ?? 0)))}) : `<li><strong>${escape(project.name || project.id || (globalThis.HubI18n?.t?.("backups.f45edf006851") ?? "Проект"))}</strong><span>${escape(String(project.tasks ?? 0))} задач · ${escape(String(project.journalEvents ?? 0))} событий журнала</span></li>`)).join("")}</ul>` : (globalThis.HubI18n?.t?.("backups.fc4d428a1b96") ?? '<p class="caption">Проекты в архиве не указаны.</p>')}</section>`);
}


const backupLabel = (key, fallback) => globalThis.HubI18n?.t?.('backupAdmin.'+key, fallback) || fallback;
function backupPagination(kind) {
  const meta = backupsState.pagination?.[kind];
  const total = meta?.total ?? (kind === 'backups' ? backupsState.backups.length : backupsState.jobs.filter(job=>!backupJobActive(job)).length);
  const pages = meta?.pages ?? Math.max(1, Math.ceil(total/backupsState.pageSize));
  const page = meta?.page ?? (kind === 'backups' ? backupsState.page : backupsState.historyPage);
  return `<div class="admin-pagination"><span>${escape(backupLabel('page','Страница'))} ${page} / ${pages} · ${total}</span><div><button type="button" data-backup-page="${kind}" data-page="${page-1}" ${page<=1 || backupsState.loading?'disabled':''}>${escape(backupLabel('previous','Назад'))}</button><button type="button" data-backup-page="${kind}" data-page="${page+1}" ${page>=pages || backupsState.loading?'disabled':''}>${escape(backupLabel('next','Далее'))}</button></div></div>`;
}
function backupVisibleRows(kind) {
  const rows = kind === 'backups' ? backupsState.backups : backupsState.jobs.filter(job=>!backupJobActive(job));
  if (backupsState.pagination) return rows;
  const page = kind === 'backups' ? backupsState.page : backupsState.historyPage;
  return rows.slice((page-1)*backupsState.pageSize,page*backupsState.pageSize);
}
function backupRow(item) {
  const path=item.path || (backupsState.backupHome ? `${backupsState.backupHome.replace(/[\\/]$/,'')}/${item.name}` : '');
  return `<tr data-ui-key="backup-${escape(item.id)}"><td><strong>${escape(item.name || backupLabel('archive','Архив'))}</strong>${path?`<div>${globalThis.HubLocalFiles?.pathLink(path,'backups',{reveal:true}) || `<code class="storage-path">${escape(path)}</code>`}</div>`:''}</td><td>${escape(backupDate(item.createdAt))}</td><td>${escape(backupSize(item.size))}</td><td>${escape(String(item.projects?.length ?? 0))}</td><td><span class="projects-badge">${escape(backupLabel(item.verified===false?'unverified':'verified',item.verified===false?'Не проверен':'Проверен'))}</span></td><td><div class="admin-row-actions"><button type="button" data-backup-details="${escape(item.id)}">${escape(backupLabel('details','Подробности'))}</button><a class="icon-button" href="/api/v1/backups/download?id=${encodeURIComponent(item.id)}" download title="${escape(backupLabel('download','Скачать'))}" aria-label="${escape(backupLabel('download','Скачать'))}">${uiIcon('download')}</a><button type="button" data-backup-restore="${escape(item.id)}">${escape(backupLabel('restore','Восстановить…'))}</button>${backupsState.capabilities?.deleteArchive ? `<button type="button" data-backup-delete="${escape(item.id)}" title="${escape(backupLabel('delete','Удалить'))}">${uiIcon('delete')}</button>` : ''}</div></td></tr>`;
}
function backupActionLabel(action) { return backupLabel(action, ({create:'Создание архива','restore-copy':'Восстановление копии','import-folder':'Импорт папки','upgrade-copy':'Обновление формата','upload-complete':'Проверка загрузки','delete-archive':'Удаление архива','delete-copy':'Удаление копии'})[action] || action); }
function backupHistory() {
  if (globalThis.backupStatus?.history) return globalThis.backupStatus.history('all');
  const rows=backupVisibleRows('history');
  if (!rows.length) return '';
  return `<details class="admin-history" data-ui-key="backup-history"><summary>${escape(backupLabel('history','История операций'))}</summary><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>${escape(backupLabel('operation','Операция'))}</th><th>${escape(backupLabel('date','Дата'))}</th><th>${escape(backupLabel('result','Результат'))}</th></tr></thead><tbody>${rows.map(job=>`<tr data-ui-key="history-${escape(job.id)}"><td><a href="${escape(globalThis.backupStatus?.operationLink(job) || `#projects/backups/operation/${encodeURIComponent(job.id)}`)}">${escape(backupActionLabel(job.action))}</a></td><td>${escape(backupDate(job.finishedAt || job.createdAt))}</td><td>${escape(backupLabel(job.status,job.status==='succeeded'?'Завершено':job.status==='interrupted'?'Прервано':'Ошибка'))}${job.error?`<p class="caption">${escape(backupError({message:job.error}))}</p>`:''}</td></tr>`).join('')}</tbody></table></div>${backupPagination('history')}</details>`;
}
function backupsPage({embedded=false}={}) {
  const headings=['archive','date','size','projects','verification','actions'];
  const labels=['Архив','Дата','Размер','Проекты','Проверка','Действия'];
  const selectedProject=typeof activeProject==='string' ? activeProject : '';
  const parts=(globalThis.location?.hash || '').replace(/^#/,'').split('/');
  backupsState.detailId='';
  if(parts[0]==='projects' && parts[1]==='backups' && parts[2]==='operation')try{backupsState.detailId=decodeURIComponent(parts[3] || '');}catch(_){backupsState.detailId='';}
  return `${embedded?'':`<div class="page-head"><h1>${escape(backupLabel('title','Резервные копии'))}</h1></div>`}<section id="backups-page" class="backups-page" aria-label="${escape(backupLabel('title','Резервные копии'))}"><section class="admin-panel"><div class="backup-panel-head"><div><h2>${escape(backupLabel('title','Резервные копии'))}</h2><p class="caption">${escape(backupLabel('activeScope','Архив включает данные всех проектов. После проверки ZIP откроется предварительный просмотр; рабочие данные изменятся только после подтверждения.'))}</p>${backupsState.backupHome?`<p>${globalThis.HubLocalFiles?.pathLink(backupsState.backupHome,'backups') || `<code class="storage-path">${escape(backupsState.backupHome)}</code>`}</p>`:''}</div><div class="projects-actions"><button type="button" data-backup-refresh>${escape(backupLabel('refresh','Обновить'))}</button><button class="primary" type="button" data-backup-create>${uiIcon('plus')}<span>${escape(backupLabel('createButton','Создать копию'))}</span></button></div></div><p class="backup-status" role="status" data-backup-status></p><p role="status" data-local-files-status></p><button type="button" data-backup-retry data-operation-retry="${escape(backupsState.jobRequest?.payload?.requestId || '')}" ${backupsState.jobRequest?'':'hidden'}>${escape(backupLabel('retry','Повторить операцию'))}</button>${backupsState.detailId?globalThis.backupStatus?.details(backupsState.detailId) || '':''}${backupJobRows()}<div class="backup-table-toolbar"><label>${escape(backupLabel('sort','Сортировка'))}<select data-backup-sort>${[['createdAt:desc','newest','Сначала новые'],['createdAt:asc','oldest','Сначала старые'],['size:desc','largest','По размеру'],['name:asc','name','По названию']].map(([value,key,label])=>`<option value="${value}" ${value===backupsState.sort+':'+backupsState.direction?'selected':''}>${escape(backupLabel(key,label))}</option>`).join('')}</select></label><label>${escape(backupLabel('perPage','На странице'))}<select data-backup-size>${[10,20,50,100].map(size=>`<option ${backupsState.pageSize===size?'selected':''}>${size}</option>`).join('')}</select></label></div><div class="admin-table-wrap"><table class="admin-table"><thead><tr>${headings.map((key,index)=>`<th>${escape(backupLabel(key,labels[index]))}</th>`).join('')}</tr></thead><tbody>${backupVisibleRows('backups').map(backupRow).join('') || `<tr><td colspan="6">${escape(backupLabel(backupsState.loading?'loading':'empty',backupsState.loading?'Загрузка…':'Резервных копий пока нет.'))}</td></tr>`}</tbody></table></div>${backupPagination('backups')}${backupHistory()}</section><section class="admin-panel backup-upload" id="backup-zip-import"><h2>${escape(backupLabel('restoreZip','Восстановить из ZIP'))}</h2><p class="caption">${escape(backupLabel('importUploadHelp','Выберите ZIP-архив Project Hub. После загрузки и проверки сразу откроется предварительный просмотр источника. Данные применятся только после подтверждения; исходный ZIP сохранится.'))}</p><div class="backup-upload-row"><input type="file" accept=".zip,application/zip" data-backup-file hidden aria-label="${escape(backupLabel('file','Файл резервной копии'))}"><button type="button" data-backup-choose>${escape(backupLabel('choose','Выбрать файл'))}</button><span class="caption" data-backup-filename>${escape(backupsState.selectedFile?.name || backupLabel('noFile','Файл не выбран'))}</span><button type="button" data-backup-upload data-operation-retry="${escape(backupsState.uploadRequest?.body?.requestId || '')}" ${backupsState.selectedFile && !backupsState.busy?'':'disabled'}>${uiIcon('upload')}<span>${escape(backupLabel('verifyUpload','Загрузить и проверить'))}</span></button></div><progress data-backup-progress max="100" value="0" hidden></progress><div data-backup-preview>${backupPreview(backupsState.preview)}</div></section></section>`;
}
function backupDetails(item, opener) {
  if (!globalThis.document?.createElement) return;
  const dialog=document.createElement('dialog');dialog.className='projects-dialog';dialog.setAttribute('aria-label',backupLabel('details','Подробности'));
  dialog.innerHTML=`<header><h2>${escape(backupLabel('details','Подробности'))}</h2><button type="button" aria-label="${escape(backupLabel('close','Закрыть'))}">×</button></header><div class="projects-dialog-body"><h3>${escape(item.name)}</h3><dl class="projects-details"><dt>SHA-256</dt><dd><code>${escape(item.sha256)}</code></dd><dt>${escape(backupLabel('date','Дата'))}</dt><dd>${escape(backupDate(item.createdAt))}</dd><dt>${escape(backupLabel('size','Размер'))}</dt><dd>${escape(backupSize(item.size))}</dd></dl>${backupPreview({createdAt:item.createdAt,projects:item.projects,totalBytes:item.size})}</div>`;
  dialog.querySelector('button').addEventListener('click',()=>dialog.close());dialog.addEventListener('close',()=>{dialog.remove();if(opener?.isConnected)opener.focus({preventScroll:true});});
  document.body.append(dialog);dialog.showModal();
}

async function loadBackups(root) {
  backupsState.loading = true; backupsState.error = "";
  try {
    const data = await backupApi({url:`/api/v1/backups?page=${backupsState.page}&pageSize=${backupsState.pageSize}&historyPage=${backupsState.historyPage}&sort=${backupsState.sort}&direction=${backupsState.direction}`});
    backupsState.pagination = data.pagination || null; backupsState.capabilities = data.capabilities || {};
    backupsState.backupHome = data.backupHome || backupsState.backupHome;
    if (data.pagination) {backupsState.page = data.pagination.backups.page; backupsState.historyPage = data.pagination.history.page;}
    backupsState.backups = Array.isArray(data.backups) ? data.backups : [];
    if (!data.pagination) {
      backupsState.backups.sort((a,b)=>{const left=a[backupsState.sort]??'',right=b[backupsState.sort]??'';return (typeof left==='number'?left-right:String(left).localeCompare(String(right)))*(backupsState.direction==='desc'?-1:1);});
      backupsState.page=Math.min(backupsState.page,Math.max(1,Math.ceil(backupsState.backups.length/backupsState.pageSize)));
    }
    backupsState.restoreCopies = Array.isArray(data.restoreCopies) ? data.restoreCopies : [];
    backupsState.jobs = Array.isArray(data.jobs) ? data.jobs : [];
    for (const job of backupsState.jobs) {globalThis.backupStatus?.acknowledge(job);if(job.status==='succeeded')backupApplyResult(job, false, false);}
  } catch (error) { backupsState.error = backupError(error); }
  finally { backupsState.loading = false; backupsState.catalogLoaded = true; renderBackupPanel(root); startBackupPolling(root); }
}

function renderBackupPanel(root) {
  if (!root || root.isConnected === false) return;
  const fileInput = root.querySelector("[data-backup-file]");
  const active = globalThis.document?.activeElement;
  const activeInside = active && (active === root || root.contains?.(active));
  const focusState = activeInside ? {
    selector: active === fileInput ? "[data-backup-file]" : active.id ? `#${CSS.escape(active.id)}` : null,
    start: Number.isFinite(active.selectionStart) ? active.selectionStart : null,
    end: Number.isFinite(active.selectionEnd) ? active.selectionEnd : null,
    direction: active.selectionDirection,
  } : null;
  const scrollState = {top: root.scrollTop, left: root.scrollLeft};
  const pageScroll = {x: globalThis.scrollX, y: globalThis.scrollY};
  const page = backupsPage();
  const start = page.indexOf('<section id="backups-page"');
  const openEnd = page.indexOf(">", start) + 1;
  const end = page.lastIndexOf("</section>");
  const html = start >= 0 && openEnd > start && end > openEnd ? page.slice(openEnd, end) : "";
  if (window.HubLiveUI) window.HubLiveUI.patch(root, html);
  else root.innerHTML = html;
  const renderedFileInput = root.querySelector("[data-backup-file]");
  if (fileInput && renderedFileInput && renderedFileInput !== fileInput) renderedFileInput.replaceWith?.(fileInput);
  backupsState.root = root;
  const status = root.querySelector("[data-backup-status]");
  if (status) status.textContent = backupsState.error;
  bindBackups(root);
  globalThis.HubLocalFiles?.bind(root);
  root.scrollTop = scrollState.top; root.scrollLeft = scrollState.left;
  if (Number.isFinite(pageScroll.x) && Number.isFinite(pageScroll.y)) globalThis.scrollTo?.(pageScroll.x, pageScroll.y);
  if (focusState?.selector) {
    const next = root.querySelector(focusState.selector);
    next?.focus?.({preventScroll:true});
    if (focusState.start != null && next?.setSelectionRange)
      try { next.setSelectionRange(focusState.start, focusState.end, focusState.direction); } catch { /* File/non-text control. */ }
  }
  globalThis.backupStatus?.afterRender();
}

function backupRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().replaceAll("-", "");
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`.padEnd(32, "0").slice(0, 32);
}

function backupMergeJob(job) {
  if (!job?.id) return;
  backupsState.jobs = [job, ...backupsState.jobs.filter(item => item.id !== job.id)].sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")));
  globalThis.backupStatus?.acknowledge(job);
}

function backupApplyResult(job, navigate = false, updateCatalog = navigate) {
  if(job.id && backupsState.handledResults.has(job.id)) {
    const copyId = job.result?.copyId || job.result?.id;
    if (navigate && (job.action === 'restore-copy' || job.action === 'upload-complete') && copyId && globalThis.location) globalThis.location.hash = `projects/data/import/${encodeURIComponent(copyId)}`;
    return;
  }
  if(job.id)backupsState.handledResults.add(job.id);
  if (!updateCatalog) return;
  const result = job.result || {};
  if (job.action === "upload-complete" && result.preview) {
    backupsState.preview = result.preview;
    backupsState.backups = [{id: result.id, name: result.name || result.preview.name || (globalThis.HubI18n?.t?.("backups.5445f25984ee") ?? "Загруженная копия"), size: result.size ?? result.preview.totalBytes, createdAt: result.preview.createdAt, sha256: result.sha256, projects: result.preview.projects || []}, ...backupsState.backups.filter(item => item.id !== result.id)];
  }
  if (job.action === "restore-copy" && result.path) {
    const createdAt=job.finishedAt || job.createdAt || '';
    if(!backupsState.lastRestore?.createdAt || !createdAt || createdAt>=backupsState.lastRestore.createdAt)backupsState.lastRestore = {path:result.sourcePath || '', copyId:result.copyId || result.id, projectCount:result.projectCount,createdAt,operationId:job.id};
    backupsState.restoreCopies = [{path: result.path, projectCount: result.projectCount, active: result.active}, ...backupsState.restoreCopies.filter(copy => copy.path !== result.path)];
  }
  if (navigate && (job.action === 'restore-copy' || job.action === 'upload-complete')) {
    const copyId = result.copyId || result.id;
    if (copyId && globalThis.location) globalThis.location.hash = `projects/data/import/${encodeURIComponent(copyId)}`;
  }
}

async function pollBackupJob(job, root) {
  if (!backupJobActive(job) || backupsState.polling) return;
  backupsState.polling = true;
  try {
    const data = await backupApi({url: `/api/v1/backups?job=${encodeURIComponent(job.id)}`});
    const updated = data.job || data;
    backupMergeJob(updated);
    if (updated.status === "succeeded") backupApplyResult(updated, false, true);
    renderBackupPanel(backupsState.root);
  } catch (error) {
    backupsState.error = backupError(error);
    renderBackupPanel(backupsState.root);
  } finally {
    backupsState.polling = false;
    startBackupPolling(root || backupsState.root);
  }
}

function startBackupPolling(root) {
  const active = backupsState.jobs.filter(backupJobActive);
  if (!active.length) { if (backupsState.pollTimer) { clearTimeout(backupsState.pollTimer); backupsState.pollTimer = null; } return; }
  if (backupsState.pollTimer) return;
  const tick = async () => {
    backupsState.pollTimer = null;
    for (const job of backupsState.jobs.filter(backupJobActive)) await pollBackupJob(job, root);
    startBackupPolling(root);
  };
  backupsState.pollTimer = setTimeout(tick, 1000);
}

async function startBackupJob(body, root) {
  if (backupsState.jobRequest && JSON.stringify(backupsState.jobRequest.body) !== JSON.stringify(body)) throw Error(backupLabel('pending','Повторите неподтверждённую операцию перед новым действием.'));
  const selectedProject=typeof activeProject==='string' ? activeProject : '';
  const request = backupsState.jobRequest || {body:{...body}, payload:{...body, background:true, requestId:body.requestId || backupRequestId(),origin:{section:'backups',...(selectedProject?{project:selectedProject}:{})}}};
  backupsState.jobRequest = request;
  globalThis.backupStatus?.begin(request.payload);
  let data;
  try {data = await backupApi({method: "POST", body: JSON.stringify(request.payload)});}catch(error){if(error.status && error.status<500){backupsState.jobRequest=null;globalThis.backupStatus?.reject(request.payload,error);}else globalThis.backupStatus?.uncertain(request.payload);throw error;}
  const job = data.job || data;
  if (!job?.id || !['queued','running','succeeded','failed','interrupted'].includes(job.status) || job.requestId && job.requestId !== request.payload.requestId) {globalThis.backupStatus?.uncertain(request.payload);throw Error(backupLabel('invalidAck','Сервер не подтвердил операцию. Повторите тот же запрос.'));}
  backupsState.jobRequest = null;
  globalThis.backupStatus?.acknowledge(job,request.payload);
  backupMergeJob(job);
  renderBackupPanel(root);
  startBackupPolling(root);
  await pollBackupJob(job, root);
  while (backupJobActive(backupsState.jobs.find(item => item.id === job.id))) await new Promise(resolve => setTimeout(resolve, 250));
  const completed = backupsState.jobs.find(item => item.id === job.id) || job;
  if (completed.status !== "succeeded") throw new Error(completed.error || (completed.status === "interrupted" ? (globalThis.HubI18n?.t?.("backups.ac6138440bed") ?? "Операция прервана") : (globalThis.HubI18n?.t?.("backups.bc926c10eea6") ?? "Операция завершилась с ошибкой")));
  backupApplyResult(completed, true);
  await loadBackups(backupsState.root || root);
  return completed.result || {};
}

function arrayBufferBase64(buffer) {
  const bytes = new Uint8Array(buffer); let result = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) result += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  return btoa(result);
}

async function uploadBackup(file, root, progress) {
  const selectedProject=typeof activeProject==='string' ? activeProject : '';
  if(backupsState.uploadRequest && backupsState.uploadRequest.file!==file)throw Error(backupLabel('pending','Повторите неподтверждённую операцию перед новым действием.'));
  const body=backupsState.uploadRequest?.body || {action:'upload-start',name:file.name,size:file.size,requestId:backupRequestId(),origin:{section:'backups',...(selectedProject?{project:selectedProject}:{})}};
  backupsState.uploadRequest={file,body};
  globalThis.backupStatus?.begin(body);
  let started;
  try{started=await backupApi({method:'POST',body:JSON.stringify(body)});}catch(error){if(error.status && error.status<500){backupsState.uploadRequest=null;globalThis.backupStatus?.reject(body,error);}else globalThis.backupStatus?.uncertain(body);throw error;}
  if(typeof started?.id!=='string' || !started.id || Number(started.offset || 0)<0 || Number(started.offset || 0)>file.size){globalThis.backupStatus?.uncertain(body);throw Error(backupLabel('invalidAck','Сервер не подтвердил операцию. Повторите тот же запрос.'));}
  let offset = Number(started.offset) || 0; const id = started.id;
  const uploadRow={id,requestId:body.requestId,workflowId:`upload:${id}`,action:'upload-start',status:'running',phase:'upload',createdAt:new Date().toISOString(),startedAt:started.startedAt || new Date().toISOString(),origin:body.origin,progress:{completed:offset,total:file.size,unit:'bytes'}};
  globalThis.backupStatus?.acknowledge(uploadRow,body);
  try {
    while (offset < file.size) {
      const end = Math.min(offset + 512 * 1024, file.size);
      const data = arrayBufferBase64(await file.slice(offset, end).arrayBuffer());
      const result = await backupApi({method: "POST", body: JSON.stringify({action: "upload-chunk", id, offset, data})});
      offset = Number(result.offset);
      if (!Number.isFinite(offset) || offset <= 0) throw new Error((globalThis.HubI18n?.t?.("backups.9981620cf186") ?? "Сервер вернул некорректную позицию загрузки"));
      progress.value = file.size ? Math.round(offset / file.size * 100) : 100;
      const current=backupsState.root?.querySelector('[data-backup-progress]');if(current){current.hidden=false;current.value=progress.value;}
      uploadRow.progress.completed=offset;globalThis.backupStatus?.acknowledge({...uploadRow},body);
    }
  } catch (error) {
    try { await backupApi({method: "POST", body: JSON.stringify({action: "upload-abort", id})}); } catch (_) { /* preserve the original upload error */ }
    globalThis.backupStatus?.acknowledge({...uploadRow,status:'failed',phase:'complete',error:backupError(error)},body);
    backupsState.uploadRequest=null;
    throw error;
  }
  globalThis.backupStatus?.acknowledge({...uploadRow,status:'succeeded',phase:'complete'},body);
  backupsState.uploadRequest=null;
  // Verification owns the completed upload from here, including an unknown
  // acknowledgement. Never abort files that an accepted worker may be reading.
  await startBackupJob({action: "upload-complete", id}, root);
}

async function bindBackups(root = document.querySelector("#backups-page")) {
  if (!root) return;
  backupsState.root = root;
  if (root.dataset.backupsBound !== "true") {
    root.dataset.backupsBound = "true";
    root.addEventListener("change", event => {
      if (event.target.matches('[data-backup-sort],[data-backup-size]')) {
        if (event.target.matches('[data-backup-sort]')) [backupsState.sort,backupsState.direction] = event.target.value.split(':');
        else backupsState.pageSize = Number(event.target.value);
        backupsState.page = 1;backupsState.historyPage = 1;awaitCatalog();return;
      }
      if (!event.target.matches("[data-backup-file]")) return;
      backupsState.selectedFile = event.target.files?.[0] || null;
      const uploadButton = root.querySelector("[data-backup-upload]");
      if (uploadButton) uploadButton.disabled = !backupsState.selectedFile || backupsState.busy;
      const filename = root.querySelector('[data-backup-filename]');if (filename) filename.textContent = backupsState.selectedFile?.name || backupLabel('noFile','Файл не выбран');
    });
    function awaitCatalog() { if (!backupsState.loading) void loadBackups(root); }
    root.addEventListener("click", async event => {
      const refresh = event.target.closest('[data-backup-refresh]');if (refresh) {awaitCatalog();return;}
      const choose = event.target.closest('[data-backup-choose]');if (choose) {root.querySelector('[data-backup-file]')?.click?.();return;}
      const details = event.target.closest('[data-backup-details]');if (details) {const item=backupsState.backups.find(item=>item.id===details.dataset.backupDetails);if(item)backupDetails(item,details);return;}
      const page = event.target.closest('[data-backup-page]');if (page) {backupsState[page.dataset.backupPage==='history'?'historyPage':'page']=Number(page.dataset.page);awaitCatalog();return;}
      const remove = event.target.closest('[data-backup-delete]'), retry = event.target.closest('[data-backup-retry]');
      if ((remove || retry) && !backupsState.busy) {
        const item = remove && backupsState.backups.find(row=>row.id===remove.dataset.backupDelete);
        if (remove && (!item || !window.confirm(backupLabel('confirmDelete','Удалить этот архив? Активные данные и восстановленные копии сохранятся.')))) return;
        const body = retry ? backupsState.jobRequest?.body : {action:'delete-archive',id:item.id,expected:item.sha256,confirmed:true,requestId:backupRequestId()};
        if (!body) return;
        backupsState.busy=true;
        try {await startBackupJob(body,root);}catch(error){backupsState.error=backupError(error);renderBackupPanel(root);}finally{backupsState.busy=false;backupEnableControls(root);}return;
      }
      const createButton = event.target.closest("[data-backup-create]");
      const uploadButton = event.target.closest("[data-backup-upload]");
      const restoreButton = event.target.closest("[data-backup-restore]");
      if ((!createButton && !uploadButton && !restoreButton) || backupsState.busy) return;
      const status = root.querySelector("[data-backup-status]");
      if (createButton) {
        backupsState.busy = true; backupBusy([createButton], true); status.textContent = (globalThis.HubI18n?.t?.("backups.f3cdac14ba62") ?? "Создание копии…");
        try { await startBackupJob({action: "create"}, root); }
        catch (error) { status.textContent = backupError(error); createButton.disabled = false; }
        finally { backupsState.busy = false; backupEnableControls(root); }
        return;
      }
      if (uploadButton) {
        if (!backupsState.selectedFile) return;
        const progress = root.querySelector("[data-backup-progress]");
        backupsState.busy = true; backupBusy([uploadButton, root.querySelector("[data-backup-create]")], true); progress.hidden = false; progress.value = 0; status.textContent = (globalThis.HubI18n?.t?.("backups.e1db9d47f0fc") ?? "Загрузка копии…");
        try { await uploadBackup(backupsState.selectedFile, root, progress); root.querySelector("[data-backup-status]").textContent = (globalThis.HubI18n?.t?.("backups.e90cecc2e2ac") ?? "Копия загружена и проверена."); }
        catch (error) { root.querySelector("[data-backup-status]").textContent = backupError(error); uploadButton.disabled = false; }
        finally { backupsState.busy = false; backupEnableControls(root); }
        return;
      }
      const item = backupsState.backups.find(candidate => candidate.id === restoreButton.dataset.backupRestore); if (!item) return;
      backupsState.busy = true; backupBusy([restoreButton], true); status.textContent = (globalThis.HubI18n?.t?.("backups.b90f3c9aaa87") ?? "Восстановление копии…");
      try {
        const result = await startBackupJob({action: "restore-copy", id: item.id, expectedSha256: item.sha256, confirmed: true}, root);
        renderBackupPanel(root); root.querySelector("[data-backup-status]").textContent = backupLabel('sourcePreview','Проверка завершена. Открыт предварительный просмотр источника.');
      } catch (error) { root.querySelector("[data-backup-status]").textContent = backupError(error); restoreButton.disabled = false; }
      finally { backupsState.busy = false; backupEnableControls(root); }
    });
  }
  if (!backupsState.catalogLoaded && !backupsState.loading) await loadBackups(root);
  else startBackupPolling(root);
}

window.backupsPage = backupsPage;
window.bindBackups = bindBackups;
window.addEventListener?.('hub-language-changed', () => { const root = document.querySelector('#backups-page'); if (root) renderBackupPanel(root); });

globalThis.HubI18n?.onChange?.(()=>{Object.assign(backupJobPhase,{preparing: (globalThis.HubI18n?.t?.("backups.5ea5c68f20d4") ?? "Подготовка"), snapshot: (globalThis.HubI18n?.t?.("backups.fd2517f93c21") ?? "Снимок данных"), compressing: (globalThis.HubI18n?.t?.("backups.9d075c6c6973") ?? "Сжатие"), verifying: (globalThis.HubI18n?.t?.("backups.e56a412d1285") ?? "Проверка"), restoring: (globalThis.HubI18n?.t?.("backups.844267b67b7e") ?? "Восстановление")});});
