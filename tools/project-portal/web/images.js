"use strict";
const IMAGE_EXTENSIONS = ['jpg','jpeg','jfif','png','apng','gif','webp','avif','bmp','ico','tif','tiff','heic','heif','svg'];
const isImagePath = path => IMAGE_EXTENSIONS.includes(String(path || '').split('.').pop().toLowerCase());
const isArtifactPath = path => /^(?:hub-source\/[^/]+\/)?hub-artifact\/[a-f0-9]{64}\//.test(String(path || ''));
function sourceFormat(path) {
  const extension = String(path || '').split('/').pop().split('.').pop().toLowerCase();
  const formats = [
    [['html','htm'], 'HTML', 'fileCode'],
    [['md','markdown','mdown'], 'Markdown', 'fileText'],
    [['txt','text'], (globalThis.HubI18n?.t?.("images.3091aca226ef") ?? 'Текст'), 'fileText'],
    [['log','out','err'], (globalThis.HubI18n?.t?.("images.e7e104355790") ?? 'Лог'), 'fileText'],
    [['pdf'], 'PDF', 'fileText'],
    [['doc','docx','odt','rtf'], extension.toUpperCase(), 'fileText'],
    [['xls','xlsx','ods','csv','tsv'], extension.toUpperCase(), 'spreadsheet'],
    [['ppt','pptx','odp'], extension.toUpperCase(), 'presentation'],
    [['json','jsonl','ndjson'], extension.toUpperCase(), 'fileJson'],
    [['yaml','yml','xml','toml','ini','properties'], extension.toUpperCase(), 'fileCode'],
    [['js','mjs','cjs','jsx','ts','tsx','css','py','java','sql','sh','bash','ps1','bat','cmd','c','h','cpp','hpp','cs','go','rs','rb','php','vue','svelte','kt','kts','swift','tex'], extension.toUpperCase(), 'fileCode'],
    [['zip','7z','rar','tar','gz','bz2','xz'], extension.toUpperCase(), 'archive'],
    [['mp3','wav','ogg','flac','m4a','aac'], extension.toUpperCase(), 'audio'],
    [['mp4','webm','mov','avi','mkv'], extension.toUpperCase(), 'video'],
  ];
  const match = formats.find(([extensions]) => extensions.includes(extension));
  return match ? {label:match[1], icon:match[2], html:match[1] === 'HTML'}
    : {label:/\.[^.\/]+$/.test(path) ? extension.toUpperCase() : (globalThis.HubI18n?.t?.("images.f242456b2273") ?? 'Файл'), icon:'file', html:false};
}
function sourceUrl(path) {
  const params = new URLSearchParams({path});
  if (sourceFormat(path).html) params.set('preview', 'html');
  return projectApi((isArtifactPath(path) ? '/api/artifact?' : '/api/evidence?') + params);
}
function uniqueImageSources(sources) {
  const paths = new Set();
  return (sources || []).filter(source => source?.path && !paths.has(source.path) && paths.add(source.path));
}
function taskImageSources(task) {
  return uniqueImageSources([...(task?.sources || []), ...(task?.stages || []).flatMap(stage => stage.evidence || [])]);
}
function imageUrl(path, preview = 'thumbnail', mode = 'current', project) {
  const params = new URLSearchParams({path, mode, preview});
  if (project !== undefined) params.set('project', project);
  return project === undefined ? projectApi('/api/image?' + params) : '/api/image?' + params;
}
function renderImageEvidence(sources) {
  const items = uniqueImageSources(sources);
  const documents = items.filter(source => !isImagePath(source.path));
  const images = items.filter(source => isImagePath(source.path));
  return `<div class="evidence">${documents.map(source => {
    const format = sourceFormat(source.path);
    return `<a href="${escape(sourceUrl(source.path))}" target="_blank" rel="noopener" title="${escape(format.label + ' · ' + source.path)}">${uiIcon(format.icon)}<span class="source-format">${escape(format.label)}</span><span>${escape(source.label || source.path)}</span></a>`;
  }).join('')}</div>${images.length ? `<div class="image-gallery">${images.map(source => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("images.ea39db0332cf",{v0:(escape(source.path)),v1:(escape(source.path)),v2:(escape(imageUrl(source.path))),v3:(escape(source.label || source.path))}) : `<button type="button" class="image-tile" data-image-path="${escape(source.path)}" title="${escape(source.path)}"><img src="${escape(imageUrl(source.path))}" alt="" loading="lazy"><span class="image-failure" hidden>Предпросмотр недоступен</span><span>${escape(source.label || source.path)}</span></button>`)).join('')}</div>` : ''}`;
}
document.addEventListener('error', event => {
  const img = event.target;
  if (img.matches?.('.image-tile img')) {
    const url = new URL(img.src, location.href);
    if (url.searchParams.get('mode') === 'current') {
      url.searchParams.set('mode', 'archive');
      img.parentElement.dataset.imageMode = 'archive';
      img.src = url.href;
      return;
    }
    img.hidden = true;
    img.parentElement.querySelector('.image-failure').hidden = false;
  }
}, true);

let imageDialog;
function openImageDialog(path, mode = 'current', gallery = []) {
  if (isArtifactPath(path)) mode = 'current';
  const images = uniqueImageSources(gallery).filter(source => isImagePath(source.path))
    .map(source => ({path:source.path, mode:source.mode || 'current'}));
  let index = images.findIndex(source => source.path === path);
  if (index < 0) { images.push({path, mode}); index = images.length - 1; }
  images[index].mode = mode;
  if (!imageDialog) {
    imageDialog = document.createElement('dialog');
    imageDialog.className = 'image-dialog';
    document.body.append(imageDialog);
  }
  const dialog = imageDialog, opener = document.activeElement, project = activeProject;
  let generation = 0;
  dialog.setAttribute('aria-label', path);
  dialog.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("images.52dc053311e4",{v0:(uiIcon('expand')),v1:(uiIcon('download')),v2:(uiIcon('close')),v3:(uiIcon('left')),v4:(uiIcon('right'))}) : `<header><strong></strong><select aria-label="Версия источника"><option value="current">Текущий файл</option><option value="archive">Архив</option></select><button type="button" class="icon-button" data-zoom aria-label="Масштаб 1:1 предпросмотра" title="Масштаб 1:1 предпросмотра" aria-pressed="false">${uiIcon('expand')}</button><a class="icon-button" data-download download title="Скачать оригинал" aria-label="Скачать оригинал">${uiIcon('download')}</a><button type="button" class="icon-button" data-close title="Закрыть" aria-label="Закрыть">${uiIcon('close')}</button></header><p class="image-status" role="status"></p><div class="image-viewer"><button type="button" class="icon-button image-nav" data-image-prev aria-label="Предыдущее изображение" title="Предыдущее изображение" disabled>${uiIcon('left')}</button><div class="image-viewport" tabindex="0" aria-label="Изображение"></div><button type="button" class="icon-button image-nav" data-image-next aria-label="Следующее изображение" title="Следующее изображение" disabled>${uiIcon('right')}</button></div><details><summary>Источник</summary><pre data-provenance></pre></details>`);
  dialog.querySelector('strong').textContent = path;
  const viewport = dialog.querySelector('.image-viewport'), status = dialog.querySelector('.image-status');
  const selector = dialog.querySelector('select'), zoom = dialog.querySelector('[data-zoom]');
  const previous = dialog.querySelector('[data-image-prev]'), next = dialog.querySelector('[data-image-next]');
  selector.value = mode;
  zoom.onclick = () => {
    const original = viewport.classList.toggle('original-size');
    zoom.setAttribute('aria-pressed', String(original));
    zoom.title = original ? (globalThis.HubI18n?.t?.("images.078683788cb3") ?? 'Вписать в окно') : (globalThis.HubI18n?.t?.("images.a784c7e776fe") ?? 'Масштаб 1:1 предпросмотра');
    zoom.setAttribute('aria-label', zoom.title);
  };
  dialog.querySelector('[data-close]').onclick = () => dialog.close();
  dialog.onclose = () => { generation++; viewport.replaceChildren(); if (opener?.isConnected) opener.focus(); };
  async function load() {
    const path = images[index].path, run = ++generation, selectedMode = selector.value;
    dialog.setAttribute('aria-label', path);
    dialog.querySelector('strong').textContent = path;
    previous.disabled = index === 0;
    next.disabled = index === images.length - 1;
    selector.disabled = isArtifactPath(path);
    viewport.replaceChildren(); status.textContent = (globalThis.HubI18n?.t?.("images.db491ef5033f") ?? 'Загрузка…');
    const download = dialog.querySelector('[data-download]');
    download.href = imageUrl(path, 'original', selectedMode, project);
    const provenance = dialog.querySelector('[data-provenance]');
    provenance.textContent = path;
    const img = document.createElement('img');
    img.alt = path;
    img.fetchPriority = 'high';
    img.onload = () => { if (run === generation) status.textContent = `${img.naturalWidth} × ${img.naturalHeight}`; };
    img.onerror = () => { if (run === generation) { img.remove(); status.textContent = (globalThis.HubI18n?.t?.("images.148de878a9dc") ?? 'Не удалось открыть изображение. Скачайте оригинал.'); } };
    viewport.append(img);
    img.src = imageUrl(path, 'full', selectedMode, project);
    try {
      const params = new URLSearchParams({path, mode:selectedMode, project});
      const response = await fetch('/api/source?' + params);
      if (!response.ok) throw Error((globalThis.HubI18n?.t?.("images.c0368b861259") ?? 'Не удалось проверить источник'));
      const source = await response.json();
      if (run !== generation) return;
      selector.disabled = source.kind === 'artifact';
      if (source.kind === 'artifact') {
        selector.value = 'current';
        download.href = '/api/artifact?' + new URLSearchParams({path, project});
      }
      provenance.textContent = JSON.stringify(source, null, 2);
      if (!source.available || source.image?.previewAvailable === false || (source.kind === 'artifact' && !source.image)) {
        img.remove();
        status.textContent = !source.available
          ? (globalThis.HubI18n?.t?.("images.f9aa8240d753") ?? 'Источник недоступен. Можно проверить другую версию.')
          : (globalThis.HubI18n?.t?.("images.ec9799f58d28") ?? 'Предпросмотр этого формата недоступен. Скачайте оригинал.');
      }
    } catch (error) { if (run === generation) provenance.textContent = `${path}\n${(globalThis.HubI18n?.error?.(error) ?? error.message)}`; }
  }
  function navigate(step) {
    const target = index + step;
    if (target < 0 || target >= images.length) return;
    index = target;
    selector.value = isArtifactPath(images[index].path) ? 'current' : images[index].mode;
    viewport.classList.remove('original-size');
    zoom.setAttribute('aria-pressed', 'false');
    zoom.title = (globalThis.HubI18n?.t?.("images.a784c7e776fe") ?? 'Масштаб 1:1 предпросмотра');
    zoom.setAttribute('aria-label', zoom.title);
    return load();
  }
  previous.onclick = () => navigate(-1);
  next.onclick = () => navigate(1);
  selector.onchange = () => { images[index].mode = selector.value; return load(); };
  if (!dialog.open) dialog.showModal();
  load();
}
document.addEventListener('click', event => {
  const tile = event.target.closest('[data-image-path]');
  if (tile) {
    const gallery = tile.closest('.image-gallery, [data-source-rows]');
    const images = [...(gallery?.querySelectorAll('[data-image-path]') || [])]
      .filter(item => !item.disabled)
      .map(item => ({path:item.dataset.imagePath, mode:item.dataset.imageMode || 'current'}));
    openImageDialog(tile.dataset.imagePath, tile.dataset.imageMode || 'current', images);
  }
});

function mountImageUploads(dialog, task, stageMode, project) {
  dialog.disposeImageUploads?.();
  const form = dialog.querySelector('form'), sources = form.querySelector('[data-sources]');
  const rows = sources.querySelector('[data-source-rows]');
  const panel = document.createElement('div');
  panel.className = 'image-upload-panel';
  panel.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("images.da2da5c8e24d",{}) : `<label class="edit-field"><span>Добавить файлы</span><input type="file" multiple aria-label="Добавить файлы"></label><div class="image-upload-list"></div>`);
  sources.append(panel);
  const input = panel.querySelector('input'), pending = panel.querySelector('.image-upload-list');
  let uploading = false, saving = false, closed = false;
  function sync() {
    form.querySelector('[type=submit]').disabled = uploading || saving;
    input.disabled = uploading || saving;
    form.querySelector('[data-editor-reload]').disabled = uploading || saving;
    sources.disabled = saving;
  }
  function appendSource(source, preview) {
    if (![...rows.querySelectorAll('[data-source-path]')].some(input => input.value.trim() === source.path)) {
      rows.insertAdjacentHTML('beforeend', sourceRow(source));
      previewRow(rows.lastElementChild);
      if (preview?.content && /^image\/(png|jpeg|gif|webp|avif|bmp|x-icon|svg\+xml)$/.test(preview.mime)) {
        const button = rows.lastElementChild.querySelector('[data-image-path]');
        const img = button?.querySelector('img');
        if (img) {
          img.src = 'data:' + preview.mime + ';base64,' + preview.content;
          img.hidden = false;
          button.querySelector('.image-failure').hidden = true;
          button.removeAttribute('data-image-path');
          button.disabled = true;
          button.title = source.label || source.path;
        }
      }
    }
  }
  function previewRow(row) {
    if (row.querySelector('[data-image-path]')) return;
    const path = row.querySelector('[data-source-path]').value.trim();
    if (!isImagePath(path)) return;
    row.insertAdjacentHTML('beforeend', (globalThis.HubI18n?.t ? globalThis.HubI18n.t("images.b59d4dceb7a9",{v0:(escape(path)),v1:(escape(path)),v2:(escape(imageUrl(path, 'thumbnail', 'current', project)))}) : `<button class="image-tile editor-image-preview" type="button" data-image-path="${escape(path)}" aria-label="Открыть изображение: ${escape(path)}"><img alt="" src="${escape(imageUrl(path, 'thumbnail', 'current', project))}"><span class="image-failure" hidden>Предпросмотр недоступен</span></button>`));
  }
  rows.querySelectorAll('[data-source-row]').forEach(previewRow);
  if (stageMode) {
    const choices = taskImageSources(task).filter(source => isImagePath(source.path));
    if (choices.length) {
      const chooser = document.createElement('details');
      chooser.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("images.1a84729fe0eb",{v0:(choices.length),v1:(choices.map((source, index) => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("images.6580c1c7c01c",{v0:(index),v1:(escape(source.path)),v2:(escape(imageUrl(source.path, 'thumbnail', 'current', project))),v3:(escape(source.label || source.path))}) : `<button class="image-tile" type="button" data-reuse="${index}" title="Добавить: ${escape(source.path)}"><img alt="" loading="lazy" src="${escape(imageUrl(source.path, 'thumbnail', 'current', project))}"><span class="image-failure" hidden>Предпросмотр недоступен</span><span>${escape(source.label || source.path)}</span></button>`)).join(''))}) : `<summary>Изображения задачи (${choices.length})</summary><div class="image-gallery">${choices.map((source, index) => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("images.6580c1c7c01c",{v0:(index),v1:(escape(source.path)),v2:(escape(imageUrl(source.path, 'thumbnail', 'current', project))),v3:(escape(source.label || source.path))}) : `<button class="image-tile" type="button" data-reuse="${index}" title="Добавить: ${escape(source.path)}"><img alt="" loading="lazy" src="${escape(imageUrl(source.path, 'thumbnail', 'current', project))}"><span class="image-failure" hidden>Предпросмотр недоступен</span><span>${escape(source.label || source.path)}</span></button>`)).join('')}</div>`);
      chooser.onclick = event => { const button = event.target.closest('[data-reuse]'); if (button) appendSource(choices[Number(button.dataset.reuse)]); };
      panel.append(chooser);
    }
  }
  input.onchange = async () => {
    const files = [...input.files];
    input.value = ''; uploading = true; sync();
    for (const file of files) {
      if (closed) break;
      const item = document.createElement('div');
      item.className = 'image-upload-item';
      item.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("images.644afc727de8",{v0:(uiIcon('close'))}) : `<span></span><small role="status"></small><button type="button" class="icon-button" title="Удалить" aria-label="Удалить">${uiIcon('close')}</button>`);
      item.querySelector('span').textContent = file.name;
      const status = item.querySelector('small');
      let removed = false;
      item.querySelector('button').onclick = () => { removed = true; item.remove(); };
      pending.append(item);
      try {
        if (file.size > 20 * 1024 * 1024) throw Error((globalThis.HubI18n?.t?.("images.e526f22f58a1") ?? 'Размер файла превышает 20 МиБ'));
        status.textContent = (globalThis.HubI18n?.t?.("images.db491ef5033f") ?? 'Загрузка…');
        const content = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(',')[1]);
          reader.onerror = () => reject(Error((globalThis.HubI18n?.t?.("images.9985b0ad9602") ?? 'Не удалось прочитать файл')));
          reader.readAsDataURL(file);
        });
        if (closed || removed) continue;
        const result = await editorRequest('/api/v1/artifacts/upload', {name:file.name, content}, project);
        if (closed || removed) continue;
        if (!result.source?.path) throw Error((globalThis.HubI18n?.t?.("images.6ed906faa964") ?? 'Сервер не вернул ссылку на файл'));
        appendSource(result.source, result.preview);
        item.remove();
      } catch (error) { if (!closed && !removed) status.textContent = (globalThis.HubI18n?.error?.(error) ?? error.message); }
    }
    uploading = false;
    if (!closed) sync();
  };
  function dispose() {
    closed = true;
    dialog.removeEventListener('close', onClose);
  }
  function onClose() { if (!dialog.open) dispose(); }
  dialog.disposeImageUploads = dispose;
  dialog.addEventListener('close', onClose);
  return {busy:() => uploading || saving, setSaving(value) { saving = value; if (!closed) sync(); }};
}
