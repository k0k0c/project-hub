"use strict";

// Local actions run on the Hub server's computer, where these paths exist.
(function (global) {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text = (key, ru, en) => global.HubI18n?.t?.(`localFiles.${key}`, global.HubI18n?.locale === 'en' ? en : ru) || (global.HubI18n?.locale === 'en' ? en : ru);
  async function request(body) {
    const response = await fetch('/api/v1/local-files', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), cache:'no-store'});
    const value = await response.json();
    if (!response.ok) throw Error(value?.error || text('failed','Не удалось открыть папку. Вы можете скопировать путь.','Could not open the folder. You can copy its path.'));
    return value;
  }
  async function chooseFolder(kind, path = '') {
    const value = await request({action:'choose-folder',kind,...(path ? {path} : {})});
    if (value?.cancelled) return null;
    if (typeof value?.path !== 'string' || !value.path) throw Error(text('invalidPath','Сервер не вернул путь к папке.','The server did not return a folder path.'));
    return value.path;
  }
  async function openFolder(kind, path, project, reveal = false) {
    const value = await request({action:'open-folder',kind,...(path ? {path} : {}),...(project ? {project} : {}),...(reveal ? {reveal:true} : {})});
    if (value?.opened !== true) throw Error(text('failed','Не удалось открыть папку. Вы можете скопировать путь.','Could not open the folder. You can copy its path.'));
    return value;
  }
  function pathLink(path, kind, {project, reveal = false, copy = true} = {}) {
    if (!path) return '—';
    const title = reveal ? text('reveal','Показать в папке на компьютере сервера','Show in a folder on the server computer') : text('open','Открыть папку на компьютере сервера','Open the folder on the server computer');
    return `<span class="hub-local-path"><button type="button" class="hub-path-link" data-local-open="${esc(kind)}" data-path="${esc(path)}" ${project ? `data-project="${esc(project)}"` : ''} ${reveal ? 'data-reveal="true"' : ''} title="${esc(title)}"><code>${esc(path)}</code></button>${copy ? `<button type="button" class="hub-path-copy" data-local-copy="${esc(path)}" aria-label="${esc(text('copy','Скопировать путь','Copy path'))}">${esc(text('copyShort','Копировать','Copy'))}</button>` : ''}</span>`;
  }
  function chooser(kind, target, disabled = false) {
    return `<button type="button" data-local-folder="${esc(kind)}" data-local-target="${esc(target)}" ${disabled ? 'disabled' : ''}>${esc(text('choose','Выбрать папку…','Choose folder…'))}</button>`;
  }
  function feedback(button, message) {
    const scope = button.closest?.('section,form,dialog') || global.document;
    let status = scope?.querySelector?.('[data-local-files-status]');
    if (!status && global.document?.createElement && scope?.append) {
      status = global.document.createElement('p'); status.dataset.localFilesStatus = 'true'; status.setAttribute('role','status'); status.className = 'caption hub-local-feedback'; scope.append(status);
    }
    if (status) status.textContent = message;
  }
  async function handle(event) {
    const button = event.target.closest?.('[data-local-folder],[data-local-open],[data-local-copy]');
    if (!button || button.disabled) return;
    event.preventDefault();
    button.disabled = true;
    try {
      if (button.dataset.localCopy != null) {
        if (!global.navigator?.clipboard?.writeText) throw Error(text('copyUnavailable','Копирование недоступно. Выделите путь и скопируйте его вручную.','Copy is unavailable. Select the path and copy it manually.'));
        await global.navigator.clipboard.writeText(button.dataset.localCopy);
        feedback(button, text('copied','Путь скопирован.','Path copied.'));
      } else if (button.dataset.localOpen) {
        await openFolder(button.dataset.localOpen, button.dataset.path, button.dataset.project, button.dataset.reveal === 'true');
        feedback(button, '');
      } else {
        const scope = button.closest?.('form,section,dialog') || global.document;
        const field = scope?.querySelector?.(button.dataset.localTarget) || global.document?.querySelector?.(button.dataset.localTarget);
        const path = await chooseFolder(button.dataset.localFolder, field?.value || '');
        if (path != null && field) {
          field.value = path;
          if (global.Event && field.dispatchEvent) {field.dispatchEvent(new global.Event('input',{bubbles:true})); field.dispatchEvent(new global.Event('change',{bubbles:true}));}
          field.focus?.();
        }
      }
    } catch (error) { feedback(button, global.HubI18n?.error?.(error) || error.message); }
    finally { button.disabled = false; }
  }
  function bind(root = global.document) {
    if (!root?.querySelectorAll) return;
    // Existing workspace forms use several names for a server-side directory.
    root.querySelectorAll('input[name="root"],input[name="workspaceRoot"],input[name="workspacePath"],input[name="sourcePath"],input[data-workspace-path]').forEach(field => {
      const form = field.closest?.('form');
      if (!form || field.dataset.localPickerBound || form.querySelector?.('[data-local-folder]')) return;
      field.dataset.localPickerBound = 'true';
      if (!field.id) field.id = `hub-local-folder-${++bind.sequence}`;
      field.insertAdjacentHTML?.('afterend', chooser('workspace',`#${field.id}`,field.disabled));
    });
    root.querySelectorAll('.workspace-card-head > code[title]').forEach(code=>{
      const path=code.textContent, project=code.closest?.('[data-code-workspaces]')?.dataset.codeWorkspaces;
      if(path && code.insertAdjacentHTML){code.insertAdjacentHTML('beforebegin',pathLink(path,'workspace',{project}));code.remove?.();}
    });
  }
  bind.sequence = 0;
  global.document?.addEventListener?.('click', handle);
  global.HubLocalFiles = {chooseFolder,openFolder,pathLink,chooser,bind};
  if(global.MutationObserver && global.document?.body){
    const observer=new global.MutationObserver(records=>{if(records.some(record=>record.addedNodes?.length))bind();});
    observer.observe(global.document.body,{childList:true,subtree:true});
  }
})(typeof window === 'undefined' ? globalThis : window);
