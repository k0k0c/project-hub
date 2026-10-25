/* Explicit user closure of recorded work; does not stop a running application. */
(() => {
  'use strict';
  const tr = (ru, en) => globalThis.HubI18n?.locale === 'en' ? en : ru;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const url = (path, project, extra = {}) => path + '?' + new URLSearchParams({project, ...extra});
  async function request(path, body) {
    const response = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {cache:'no-store'});
    const value = await response.json();
    if (!response.ok) throw Object.assign(new Error(value.message || value.error || String(response.status)), {code:value.error});
    return value;
  }
  function render(task, project) {
    return `<button type="button" data-reconcile-task="${esc(task.id)}" data-reconcile-project="${esc(project)}">${tr('Согласовать записи работы', 'Reconcile work records')}</button>`;
  }
  async function open(project, task) {
    if (document.querySelector('[data-work-reconciliation]')) return;
    const dialog = document.createElement('dialog');
    dialog.className = 'task-editor'; dialog.setAttribute('data-work-reconciliation', '');
    dialog.setAttribute('aria-label', tr('Согласовать записи работы', 'Reconcile work records'));
    dialog.innerHTML = `<form><header><h2>${tr('Согласовать записи работы', 'Reconcile work records')}</h2><button type="button" data-close>${tr('Закрыть','Close')}</button></header><div class="editor-fields"><p>${tr('Закройте только принятую или отменённую работу. Исходный участник, история и Git-границы сохранятся. Этап завершается отдельно.', 'Close only accepted or cancelled work. Its original participant, history and Git boundaries are retained. Complete the stage separately.')}</p><label class="edit-field"><span>${tr('Запись работы','Work record')}</span><select name="work"></select></label><p data-previous></p><button type="button" data-more hidden>${tr('Показать ещё','Show more')}</button><label class="edit-field"><span>${tr('Итог','Outcome')}</span><select name="status"><option value="done">${tr('Результат принят','Result accepted')}</option><option value="cancelled">${tr('Работа отменена','Work cancelled')}</option></select></label><label class="edit-field"><span>${tr('Причина согласования','Reconciliation reason')}</span><textarea name="reason" required maxlength="1200" rows="2"></textarea></label><label class="edit-field"><span>${tr('Результат или причина отмены','Result or cancellation reason')}</span><textarea name="result" required maxlength="1600" rows="3"></textarea></label><label data-active hidden><input name="interrupt" type="checkbox">${tr('Я согласовал прерывание этой активной работы. Закрытие записи освобождает её резервирование, но не останавливает приложение.', 'I have coordinated interruption of this active work. Closing the record releases its reservation but does not stop the application.')}</label><p role="alert"></p></div><footer><button type="button" data-reload>${tr('Обновить записи','Reload records')}</button><button type="submit" disabled>${tr('Подтвердить согласование','Confirm reconciliation')}</button></footer></form>`;
    document.body.append(dialog); dialog.showModal();
    const observation = document.createElement('p'); observation.className = 'caption'; observation.style.overflowWrap = 'anywhere';
    dialog.querySelector('[data-previous]').after(observation);
    const form = dialog.querySelector('form'), alert = dialog.querySelector('[role="alert"]');
    const submit = dialog.querySelector('[type="submit"]'), close = dialog.querySelector('[data-close]');
    const reload = dialog.querySelector('[data-reload]'), more = dialog.querySelector('[data-more]');
    let records = [], next = 0, selected = null, pending = false, savedRequest = null, stale = false;
    const freezeFields = frozen => form.querySelectorAll('input,select,textarea').forEach(field => { field.disabled = frozen; });
    function select() {
      selected = records[Number(form.elements.work.value)] || null; savedRequest = null; stale = false;
      freezeFields(false);
      form.elements.reason.value = ''; form.elements.result.value = ''; form.elements.interrupt.checked = false;
      dialog.querySelector('[data-active]').hidden = selected?.status !== 'active';
      dialog.querySelector('[data-previous]').textContent = selected?.result || '';
      observation.textContent = selected ? [tr('Запись','Record')+': '+selected.id, tr('Участник','Participant')+': '+selected.session,
        tr('Ревизия','Revision')+': '+selected.revision, selected.checkpoint, ...(selected.evidence || [])].filter(Boolean).join(' · ') : '';
      form.elements.status.value = selected?.status === 'active' ? 'cancelled' : 'done';
      submit.disabled = !selected;
    }
    async function load(append = false) {
      if (pending) return;
      pending = true; submit.disabled = true; selected = null; savedRequest = null; alert.textContent = '';
      try {
        const data = await request(url('/api/work-reconciliation', project, {task, offset:append ? next : 0}));
        if (!dialog.isConnected) return;
        records = append ? [...records, ...data.work] : data.work; next = data.next;
        form.elements.work.innerHTML = records.map((item, i) => `<option value="${i}">${esc(item.title)} · ${item.status === 'active' ? tr('Активна','Active') : tr('Ожидает','Waiting')}</option>`).join('');
        more.hidden = !data.more; select();
        if (!records.length) alert.textContent = tr('Открытых записей нет.','There are no open records.');
      } catch (error) { alert.textContent = error.message; }
      finally { pending = false; }
    }
    close.onclick = () => { if (!pending) dialog.close(); };
    dialog.addEventListener('close', () => dialog.remove());
    dialog.addEventListener('cancel', event => { if (pending) event.preventDefault(); });
    reload.onclick = () => load(); more.onclick = () => load(true); form.elements.work.onchange = select;
    form.onsubmit = async event => {
      event.preventDefault();
      if (pending || !selected || stale) return;
      if (new URL(location.href).searchParams.get('project') !== project) { alert.textContent = tr('Выбран другой проект. Откройте окно в нужной задаче.', 'The project changed. Reopen the dialog in the intended task.'); return; }
      if (!savedRequest) {
        if (!form.elements.reason.value.trim() || !form.elements.result.value.trim() || (selected.status === 'active' && !form.elements.interrupt.checked)) { alert.textContent = tr('Укажите причину, результат и подтвердите прерывание активной работы.', 'Supply a reason, result and confirmation for interrupting active work.'); return; }
        savedRequest = {work:selected.id, revision:selected.revision, owner:selected.session, observedStatus:selected.status,
          status:form.elements.status.value, reason:form.elements.reason.value.trim(), result:form.elements.result.value.trim(),
          interruptActive:form.elements.interrupt.checked, confirmed:selected.id + ':' + selected.revision};
      }
      pending = true; submit.disabled = true; reload.disabled = true; close.disabled = true;
      more.disabled = true; freezeFields(true);
      try {
        const receipt = await request(url('/api/v1/work-reconciliation', project), savedRequest);
        if (receipt.planSync !== 'saved') throw new Error(tr('Результат сохранён; публикация ожидается. Повторите тот же запрос.', 'The result is saved; publication is pending. Repeat the same request.'));
        window.dispatchEvent(new CustomEvent('hub-work-reconciled')); dialog.close();
      } catch (error) {
        stale = ['revision_conflict','work_closed','work_project_mismatch'].includes(error.code);
        alert.textContent = error.message + (stale ? tr(' Обновите записи перед новым решением.', ' Reload records before a new decision.') : tr(' Повтор отправит тот же запрос.', ' A retry sends the same request.'));
      } finally { pending = false; submit.disabled = stale; reload.disabled = false; close.disabled = false; more.disabled = false; }
    };
    await load();
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-reconcile-task]');
    if (button) open(button.dataset.reconcileProject, button.dataset.reconcileTask);
  });
  window.WorkReconciliationUI = {render, open};
})();
