"use strict";
// Historical receipts are readable here; research has its own scoped interface.
(() => {
  const views = new Map();
  let host = null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'})[character]);
  const text = (key, fallback, values) => { let value; try { value = globalThis.HubI18n?.t?.(key, values); } catch (_) {} return !value || value === key ? fallback : value; };
  const message = body => globalThis.HubI18n?.error?.(body?.error || body?.message) ||
    (typeof body?.error === 'string' ? body.error : body?.error?.message || body?.message) ||
    text('research.historyError', 'Не удалось прочитать историю запросов.');
  function view(project, task) {
    const key = JSON.stringify([project, task]);
    if (!views.has(key)) views.set(key, {loaded:false, loading:false, recent:[], error:''});
    return views.get(key);
  }
  function repaint(project, task) {
    if (host?.project === project && host.route()[0] === 'tasks' && host.route()[1] === task)
      host.render({preserveScroll:true});
  }
  async function load(project, task, force = false) {
    const current = view(project, task);
    if (current.loading || (current.loaded && !force)) return;
    current.loading = true;
    current.error = '';
    try {
      const response = await fetch('/api/chat-actions?' + new URLSearchParams({project, task}));
      const body = await response.json();
      if (!response.ok) throw Error(message(body));
      if (!Array.isArray(body?.recent)) throw Error(text('research.historyInvalid', 'Неверный ответ истории запросов.'));
      current.recent = body.recent;
    } catch (error) {
      current.error = globalThis.HubI18n?.error?.(error) || error.message;
    } finally {
      current.loaded = true;
      current.loading = false;
      repaint(project, task);
    }
  }
  function afterRender(context) {
    host = context;
    const [page, task] = context.route();
    if (page === 'tasks' && task && context.project) void load(context.project, task);
  }
  function resultLink(row, project) {
    const match = typeof row.resultRef === 'string' && row.resultRef.match(/^knowledge\/(document|entity|view|relation)\/(.+)$/);
    return match ? ` <a href="/?project=${encodeURIComponent(project)}#${match[1] === 'document' ? 'docs' : 'architecture'}/${encodeURIComponent(match[2])}">${esc(text('provider.openResult', 'Открыть результат'))}</a>` : '';
  }
  const transportKeys = ['requestId','attempt','operation','oauthAction','scheme','host','port','networkMode','effectiveNetworkMode','durationMs','timeoutMs','tlsReason','tlsVerifyCode','parseReason','responseMediaType','responseContentEncoding','responseBodyKind','responseBytes','status','phase','category','httpStatus','providerErrorCode','providerErrorType','upstreamRequestId','retryAfter','outcomeUnknown'];
  function safeDiagnostics(receipt) {
    const base = {actionId:receipt?.actionId, provider:receipt?.provider, model:receipt?.model, contextDigest:receipt?.contextDigest, status:receipt?.status, errorCode:receipt?.error?.code};
    const diagnostics = Array.isArray(receipt?.diagnostics) ? receipt.diagnostics.map(entry => Object.fromEntries(transportKeys.filter(key => entry?.[key] !== undefined).map(key => [key,entry[key]]))) : [];
    return {receipt:base, diagnostics};
  }
  function diagnosticsText(receipt) { return JSON.stringify(safeDiagnostics(receipt), null, 2); }
  function diagnosticsMarkup(receipt) {
    if (!Array.isArray(receipt?.diagnostics) || !receipt.diagnostics.length) return '';
    return `<details class="receipt-diagnostics"><summary>${esc(text('research.diagnostics', 'Показать сведения о передаче'))}</summary><pre>${esc(diagnosticsText(receipt))}</pre><button type="button" data-copy-diagnostics="${esc(receipt?.actionId || '')}">${esc(text('research.copyDiagnostics', 'Копировать диагностические сведения'))}</button></details>`;
  }
  function render(task, stage = null, project = host?.project || '') {
    if (!project) return '';
    const current = view(project, task.id);
    const rows = current.recent.filter(row => !stage || row.stage === stage.id);
    if (!current.error && !rows.length) return '';
    const labels = {
      requested:text('research.requested', 'Запрос сохранён'),
      accepted:text('research.accepted', 'Запрос принят'),
      running:text('research.running', 'Выполняется'),
      completed:text('research.completed', 'Завершено'),
      failed:text('research.failed', 'Ошибка'),
      interrupted:text('research.interrupted', 'Прервано'),
      needs_attention:text('research.needsAttention', 'Требует проверки'),
      outcome_unknown:text('research.outcomeUnknown', 'Результат неизвестен'),
    };
    return `<section class="panel detail-section receipt-history" data-chat-actions-panel><h3>${esc(text('research.history', 'История запросов'))}</h3>
      ${current.error ? `<p role="alert">${esc(current.error)}</p>` : ''}
      <ul>${rows.slice(0, 5).map(row => `<li><strong>${esc(labels[row.status] || row.status)}</strong>${resultLink(row, project)}${row.error ? `<p class="caption">${esc(message(row))}</p>` : ''}${diagnosticsMarkup(row)}</li>`).join('')}</ul>
      <button type="button" data-chat-refresh data-chat-task="${esc(task.id)}" ${current.loading ? 'disabled' : ''}>${esc(text('research.refreshHistory', 'Обновить историю'))}</button></section>`;
  }
  function projectControl(state, project) {
    if (!project) return '';
    const tasks = (state?.tasks || []).filter(task => !['done', 'cancelled'].includes(task.status));
    const groups = {active:new Set(), unknown:new Set(), waiting:new Set()};
    for (const task of tasks) for (const kind of Object.keys(groups))
      for (const id of task.agentSessions?.[kind] || (kind === 'active' ? (task.currentWorks || []).map(work => work.session) : [])) groups[kind].add(id);
    for (const id of groups.active) { groups.unknown.delete(id); groups.waiting.delete(id); }
    for (const id of groups.unknown) groups.waiting.delete(id);
    const activity = groups.active.size ? 'active' : tasks.some(task => task.agentActivity?.state === 'unknown') ? 'unknown' : groups.waiting.size ? 'waiting' : 'idle';
    const label = text('research.projectActivity', `${groups.active.size} чатов работают · ${groups.waiting.size} ожидают · ${groups.unknown.size} без данных`,
      {active:groups.active.size, waiting:groups.waiting.size, unknown:groups.unknown.size});
    return `<span class="agent-activity project-activity ${activity}" title="${esc(text('research.observedActivity', 'По последним событиям подключённых агентов.'))}">${esc(label)}</span>`;
  }
  document.addEventListener('click', event => {
    const refresh = event.target.closest('[data-chat-refresh]');
    if (refresh && host?.project && !refresh.disabled) void load(host.project, refresh.dataset.chatTask, true);
    const copy = event.target.closest('[data-copy-diagnostics]');
    if (copy && host?.project) {
      const current = view(host.project, host.route()?.[1]);
      const receipt = current.recent.find(row => row.actionId === copy.dataset.copyDiagnostics);
      if (!receipt) return;
      const keys = ['requestId','attempt','operation','scheme','host','port','networkMode','effectiveNetworkMode','durationMs','status','phase','category','httpStatus','providerErrorCode','providerErrorType','upstreamRequestId','retryAfter','outcomeUnknown'];
      const safe = {receipt:{actionId:receipt?.actionId,provider:receipt?.provider,model:receipt?.model,contextDigest:receipt?.contextDigest,status:receipt?.status,errorCode:receipt?.error?.code},diagnostics:Array.isArray(receipt?.diagnostics)?receipt.diagnostics.map(entry=>Object.fromEntries(keys.filter(key=>entry?.[key]!==undefined).map(key=>[key,entry[key]]))):[]};
      void globalThis.navigator?.clipboard?.writeText?.(JSON.stringify(safe,null,2));
    }
  });
  window.ChatActionsUI = {afterRender, render, projectControl, load};
})();

// Outbound research never receives task execution, native chat or command options.
(() => {
  const drafts = new Map();
  const terminal = new Set(['completed', 'failed', 'interrupted', 'cancelled']);
  const operations = ['documentation-draft', 'documentation-refresh', 'documentation-review'];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'})[character]);
  const text = (key, fallback) => { let value; try { value = globalThis.HubI18n?.t?.(key); } catch (_) {} return !value || value === key ? fallback : value; };
  const endpoint = (path, project) => path + '?' + new URLSearchParams({project});
  let modal = null;
  const errorText = value => globalThis.HubI18n?.error?.(value) ||
    value?.error?.message || value?.message || value?.error || text('research.requestError', 'Не удалось отправить исследование.');
  const transportKeys = ['requestId','attempt','operation','oauthAction','scheme','host','port','networkMode','effectiveNetworkMode','durationMs','timeoutMs','tlsReason','tlsVerifyCode','parseReason','responseMediaType','responseContentEncoding','responseBodyKind','responseBytes','status','phase','category','httpStatus','providerErrorCode','providerErrorType','upstreamRequestId','retryAfter','outcomeUnknown'];
  function safeDiagnostics(receipt) {
    const base = {actionId:receipt?.actionId, provider:receipt?.provider, model:receipt?.model, contextDigest:receipt?.contextDigest, status:receipt?.status, errorCode:receipt?.error?.code};
    const diagnostics = Array.isArray(receipt?.diagnostics) ? receipt.diagnostics.map(entry => Object.fromEntries(transportKeys.filter(key => entry?.[key] !== undefined).map(key => [key,entry[key]]))) : [];
    return {receipt:base, diagnostics};
  }
  function diagnosticsText(receipt) { return JSON.stringify(safeDiagnostics(receipt), null, 2); }
  function diagnosticsMarkup(receipt) {
    if (!Array.isArray(receipt?.diagnostics) || !receipt.diagnostics.length) return '';
    return `<details class="receipt-diagnostics"><summary>${esc(text('research.diagnostics', 'Показать сведения о передаче'))}</summary><pre>${esc(diagnosticsText(receipt))}</pre><button type="button" data-copy-diagnostics="${esc(receipt?.actionId || '')}">${esc(text('research.copyDiagnostics', 'Копировать диагностические сведения'))}</button></details>`;
  }
  async function providers() {
    const response = await fetch('/api/v1/agent-providers');
    const body = await response.json();
    if (!response.ok || !Array.isArray(body?.items)) throw Error(errorText(body));
    return {...body, items:body.items.filter(item => item.id !== 'codex' &&
      (item.capabilities?.hubResult === true || item.configured === true))};
  }
  function providerField(info, selected, loading = false) {
    if (loading) return `<p role="status">${esc(text('provider.loading', 'Загрузка провайдеров…'))}</p>`;
    const chosen = selected ?? info?.default ?? '';
    const items = info?.items || [];
    return `<label>${esc(text('research.provider', 'Провайдер исследования'))}<select name="providerId" required><option value="">${esc(text('research.selectProvider', 'Выберите провайдера'))}</option>${items.map(item => `<option value="${esc(item.id)}"${item.id === chosen ? ' selected' : ''}>${esc(item.name)} · ${esc(item.model)}</option>`).join('')}</select></label>${items.length ? '' : `<p><a href="#settings/agents">${esc(text('research.configureProvider', 'Подключите провайдера в настройках агентов и подключений.'))}</a></p>`}`;
  }
  async function post(project, payload) {
    const keys = Object.keys(payload || {}).sort().join(',');
    const allowed = new Set(['operation', 'objectId', 'id', 'providerId', 'template', 'prompt', 'revision', 'detailLevel', 'scope']);
    const valid = payload?.action === 'cancel' ? keys === 'action,actionId' : payload?.action === 'new' && keys === 'action,actionId,research' &&
      ['architecture-analyze', ...operations].includes(payload.research?.operation) && Object.keys(payload.research).every(key => allowed.has(key));
    if (!valid) throw Object.assign(Error(text('research.invalidRequest', 'Выберите допустимую область исследования.')), {outcomeUnknown:false});
    const response = await fetch(endpoint('/api/v1/chat-actions', project), {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    let body;
    try { body = await response.json(); }
    catch (_) { throw Object.assign(Error(text('research.outcomeUnknown', 'Результат неизвестен')), {outcomeUnknown:true}); }
    if (!response.ok) throw Object.assign(Error(errorText(body)), {outcomeUnknown:response.status >= 500});
    if (body?.actionId !== payload.actionId || typeof body.status !== 'string')
      throw Object.assign(Error(text('research.outcomeUnknown', 'Результат неизвестен')), {outcomeUnknown:true});
    return body;
  }
  function resultLink(receipt, project) {
    if (receipt?.error || ['failed','outcome_unknown','interrupted','cancelled'].includes(receipt?.status)) return '';
    const match = receipt?.resultRef?.match?.(/^knowledge\/(document|entity|view|relation)\/(.+)$/);
    const link = match ? `<a href="/?project=${encodeURIComponent(project)}#${match[1] === 'document' ? 'docs' : 'architecture'}/${encodeURIComponent(match[2])}">${esc(text('provider.openResult', 'Открыть результат'))}</a>` : '';
    const outcome = globalThis.HubI18n?.apiOutcome?.(receipt);
    return link + (outcome ? `<p>${esc(outcome)}</p>` : '');
  }
  function statusLabel(receipt) {
    const labels = {requested:'requested', accepted:'accepted', running:'running', completed:'completed', failed:'failed', interrupted:'interrupted', cancelled:'cancelled', needs_attention:'needsAttention', outcome_unknown:'outcomeUnknown'};
    return text('research.' + (labels[receipt?.status] || 'outcomeUnknown'), receipt?.status || '');
  }
  function paint(value) {
    if (modal !== value) return;
    const blocked = value.busy || (value.receipt && !terminal.has(value.receipt.status));
    const html = `<header><h2>${esc(text('research.documentationTitle', 'Исследование документации'))}</h2><button type="button" data-research-close aria-label="${esc(text('research.close', 'Закрыть'))}">×</button></header>
      <div class="research-dialog-body" data-scroll-key="research-dialog-body"><p>${esc(value.title)}</p><p>${esc(text('research.documentationScope', 'Исследуйте материалы и исходники проекта. Результат сохраняется отдельным документом с источниками и ограничениями.'))}</p>
      ${value.error ? `<p role="alert">${esc(value.error)}</p>` : ''}
      <form data-research-form>${providerField(value.providers, value.providerId, value.loading)}
      <label>${esc(text('research.purpose', 'Цель исследования'))}<select name="operation">${operations.map(operation => `<option value="${operation}"${operation === value.operation ? ' selected' : ''}>${esc(text('research.' + operation, operation))}</option>`).join('')}</select></label>
      <label>${esc(text('research.question', 'Что нужно выяснить'))}<textarea name="prompt" rows="5" maxlength="6000" required>${esc(value.prompt)}</textarea></label>
      <label>${esc(text('research.detail', 'Подробность ответа'))}<select name="detailLevel">${['brief', 'standard', 'detailed'].map(level => `<option value="${level}"${level === value.detailLevel ? ' selected' : ''}>${esc(text('research.' + level, level))}</option>`).join('')}</select></label>
      <button type="submit"${blocked || value.loading || !value.providers?.items?.length ? ' disabled' : ''}>${esc(text('research.start', 'Начать исследование'))}</button></form>
      ${value.receipt ? `<section aria-live="polite"><p>${esc(statusLabel(value.receipt))}</p>${resultLink(value.receipt, value.project)}${diagnosticsMarkup(value.receipt)}${value.receipt.status === 'outcome_unknown' ? `<p>${esc(text('research.verifyOutcome', 'Обновите статус перед новым запросом.'))}</p>` : ''}</section>` : ''}</div>
      <footer><button type="button" data-research-refresh${value.busy ? ' disabled' : ''}>${esc(text('research.refresh', 'Обновить статус'))}</button>${value.receipt?.transport === 'api' && ['requested', 'accepted', 'running'].includes(value.receipt.status) ? `<button type="button" data-research-cancel${value.busy ? ' disabled' : ''}>${esc(text('research.cancel', 'Отменить исследование'))}</button>` : ''}</footer>`;
    if (window.HubLiveUI?.patch) window.HubLiveUI.patch(value.node, html);
    else value.node.innerHTML = html;
  }
  function close(value) {
    if (value.poll) clearTimeout(value.poll);
    value.node.close();
  }
  async function refresh(value) {
    if (value.busy || modal !== value) return;
    value.error = '';
    try {
      const response = await fetch(endpoint('/api/chat-actions', value.project) + '&' + new URLSearchParams({task:'__research__:' + value.objectId}));
      const body = await response.json();
      if (!response.ok || !Array.isArray(body?.recent)) throw Error(errorText(body));
      const receipt = value.receipt ? body.recent.find(row => row.actionId === value.receipt.actionId) : body.recent[0];
      if (receipt) value.receipt = receipt;
      paint(value);
      if (receipt && ['requested', 'accepted', 'running'].includes(receipt.status)) schedule(value);
      if (receipt && terminal.has(receipt.status)) window.KnowledgeUI?.flushUpdates?.(value.project);
    } catch (error) { value.error = errorText(error); paint(value); }
  }
  function schedule(value) {
    if (value.poll) clearTimeout(value.poll);
    value.poll = setTimeout(() => { value.poll = null; void refresh(value); }, 1500);
  }
  async function openDocumentation(options) {
    if (modal) close(modal);
    const key = JSON.stringify([options.project, options.objectId]);
    const value = drafts.get(key) || {operation:'documentation-draft', prompt:'', detailLevel:'standard', receipt:null};
    Object.assign(value, options, {busy:false, loading:true, error:''});
    drafts.set(key, value);
    const node = document.createElement('dialog');
    node.className = 'research-dialog';
    value.node = node;
    modal = value;
    node.addEventListener('close', () => { node.remove(); if (value.node === node) { if (value.poll) clearTimeout(value.poll); if (modal === value) modal = null; } });
    node.addEventListener('input', event => { if (['prompt', 'operation', 'detailLevel', 'providerId'].includes(event.target.name)) value[event.target.name] = event.target.value; });
    node.addEventListener('change', event => { if (['operation', 'detailLevel', 'providerId'].includes(event.target.name)) value[event.target.name] = event.target.value; });
    node.addEventListener('submit', async event => {
      if (!event.target.matches('[data-research-form]')) return;
      event.preventDefault();
      if (value.busy || value.loading || (value.receipt && !terminal.has(value.receipt.status))) return;
      const form = new FormData(event.target);
      for (const name of ['prompt', 'operation', 'detailLevel', 'providerId']) value[name] = String(form.get(name) || '');
      if (!operations.includes(value.operation) || !value.providers?.items.some(item => item.id === value.providerId) || !value.prompt.trim()) return;
      const actionId = globalThis.crypto.randomUUID();
      value.receipt = {actionId, status:'requested', transport:'api'};
      value.busy = true;
      value.error = '';
      paint(value);
      try {
        value.receipt = await post(value.project, {action:'new', actionId, research:{operation:value.operation, objectId:value.objectId, revision:value.revision, providerId:value.providerId, prompt:value.prompt, detailLevel:value.detailLevel}});
        schedule(value);
      } catch (error) {
        value.error = errorText(error);
        if (error.outcomeUnknown !== false) value.receipt.status = 'outcome_unknown';
        else value.receipt = null;
      } finally { value.busy = false; paint(value); }
    });
    node.addEventListener('click', async event => {
      if (event.target.closest('[data-research-close]')) { close(value); return; }
      if (event.target.closest('[data-research-refresh]')) { void refresh(value); return; }
      const copy = event.target.closest('[data-copy-diagnostics]');
      if (copy) { const receipt = value.receipt || {}; void globalThis.navigator?.clipboard?.writeText?.(diagnosticsText(receipt)); return; }
      if (!event.target.closest('[data-research-cancel]') || value.busy || !value.receipt) return;
      value.busy = true; paint(value);
      try { value.receipt = await post(value.project, {action:'cancel', actionId:value.receipt.actionId}); }
      catch (error) { value.error = errorText(error); }
      finally { value.busy = false; paint(value); }
    });
    document.body.append(node); paint(value); node.showModal();
    try { value.providers = await providers(); value.providerId ??= value.providers.default; }
    catch (error) { value.error = errorText(error); }
    finally { value.loading = false; paint(value); }
    if (modal === value) void refresh(value);
  }
  window.HubResearchRequests = {providers, providerField, post, resultLink, openDocumentation};
  window.addEventListener?.('hub-language-changed', () => { if (modal?.node?.open) paint(modal); });
})();
