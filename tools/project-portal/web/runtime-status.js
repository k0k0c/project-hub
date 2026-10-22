"use strict";

(() => {
  const state = {value:null, error:'', busy:false, timer:null, bound:false};

  function english() { return globalThis.HubI18n?.locale === 'en'; }
  function text(ru, en) { return english() ? en : ru; }
  function escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  }
  function unknown(value) { return value == null || value === '' ? text('Неизвестно', 'Unknown') : String(value); }
  function valid(value) { return value && typeof value === 'object' && typeof value.running === 'boolean' && Number.isInteger(value.port); }
  function badge(value) {
    const node = document.getElementById('hub-server-indicator');
    if (!node) return;
    if (!valid(value)) {
      node.textContent = text('Состояние сервера неизвестно', 'Server status unknown');
      node.dataset.runtimeState = 'unknown';
      return;
    }
    node.textContent = value.running
      ? text(`Сервер работает · порт ${value.port}`, `Server running · port ${value.port}`)
      : text('Сервер остановлен', 'Server stopped');
    node.dataset.runtimeState = value.running ? 'running' : 'stopped';
  }
  function row(label, value, kind) {
    const contents = kind && value && globalThis.HubLocalFiles ? globalThis.HubLocalFiles.pathLink(value,kind) : escape(unknown(value));
    return `<div class="hub-runtime-row"><dt>${escape(label)}</dt><dd>${contents}</dd></div>`;
  }
  function componentLabel(value) {
    const labels = {server:['Сервер','Server'],supervisor:['Контроль запуска','Runtime supervisor'],
      'request-worker':['Обработка запросов','Request processing'],launcher:['Запуск Hub','Hub launcher'],tray:['Значок сервера','Server icon']};
    return labels[value] ? text(...labels[value]) : value;
  }
  function phaseLabel(value) {
    const labels = {preparing:['Подготовка','Preparation'],verifying:['Проверка данных','Data validation'],
      snapshot:['Подготовка копии','Copy preparation'],migrating:['Преобразование формата','Format conversion'],
      comparing:['Сравнение данных','Data comparison'],upload:['Передача файла','File transfer'],
      restoring:['Подготовка к восстановлению','Restore preparation'],ready:['Завершение','Completion'],
      waiting:['Ожидание','Waiting'],'waiting-for-drain':['Ожидание завершения запросов','Waiting for requests to finish'],
      'waiting-for-restart':['Перезапуск сервера','Server restart']};
    return labels[value] ? text(...labels[value]) : value;
  }
  function incidentReason(incident) {
    if (incident.errorMessage) return incident.errorMessage;
    const labels = {child_exit:['Неожиданное завершение процесса','Unexpected process exit'],
      supervisor_lost:['Остановлен процесс контроля запуска','Runtime supervisor stopped'],
      'request.worker_exit':['Завершилась обработка запросов','Request worker exited'],
      'request.worker_initialization_failed':['Не удалось запустить обработку запросов','Request worker failed to start'],
      'operation.failed':['Ошибка операции','Operation failed'],
      'server.failed':['Ошибка сервера','Server failed'],
      uncaught_exception:['Необработанная ошибка','Unhandled error']};
    const key=incident.reason || incident.event;
    return labels[key] ? text(...labels[key]) : key;
  }
  function diagnosticsBody(value) {
    const diagnostic = value?.diagnostics;
    const incident = diagnostic?.incident;
    const directory = diagnostic?.directory;
    const description = diagnostic?.enabled
      ? text('Журнал сохраняет ошибки, этапы операций и завершение процессов. Он остаётся доступен после остановки сервера.', 'The log keeps errors, operation stages and process exits. It remains available after the server stops.')
      : text('Диагностика недоступна. Запустите сервер через ярлык или команду запуска Hub.', 'Diagnostics are unavailable. Start the server with the Hub shortcut or launch command.');
    let details = '';
    if (incident) {
      details = '<dl class="hub-runtime-details">' +
        row(text('Время события', 'Event time'), incident.time && Number.isFinite(Date.parse(incident.time)) ? new Date(incident.time).toLocaleString(english()?'en-GB':'ru-RU') : incident.time) +
        row(text('Компонент', 'Component'), componentLabel(incident.component)) +
        row(text('Причина', 'Reason'), incidentReason(incident)) +
        (incident.exitCode != null ? row(text('Код выхода', 'Exit code'), String(incident.exitCode) + (incident.exitHex ? ' · ' + incident.exitHex : '')) : '') +
        (incident.operationId ? row(text('Операция', 'Operation'), incident.operationId) : '') +
        (incident.phase ? row(text('Этап', 'Stage'), phaseLabel(incident.phase)) : '') + '</dl>';
      const technical = incident.traceback || incident.previousIncident?.traceback || incident.outputTail;
      if (technical) details += '<details><summary>' + text('Технические подробности', 'Technical details') + '</summary><pre class="hub-runtime-log">' + escape(technical) + '</pre></details>';
    } else {
      details = '<p class="muted">' + text('Ошибок в сохранённом журнале пока нет.', 'No errors have been recorded yet.') + '</p>';
    }
    return '<div class="hub-runtime-diagnostics"><h3>' + text('Диагностика сервера', 'Server diagnostics') + '</h3><p class="muted">' + description + '</p>' +
      (directory ? '<p>' + text('Папка журнала: ', 'Log folder: ') + '<code>' + escape(directory) + '</code></p>' : '') +
      '<p class="muted">' + text('Последнее сохранённое событие может относиться к предыдущему запуску. Потеря связи сама по себе не определяет причину.', 'The last recorded incident may belong to a previous session. A lost connection alone does not identify the cause.') + '</p>' + details +
      (diagnostic?.enabled ? '<a href="/api/runtime/diagnostics" target="_blank" rel="noopener">' + text('Открыть диагностический отчёт', 'Open diagnostic report') + '</a>' : '') + '</div>';
  }
  function cardBody() {
    const value = state.value;
    const running = state.error ? null : valid(value) ? value.running : null;
    const tray = value?.tray || {};
    const explanation = text('Значок отображается, пока сервер работает. Его меню открывает Hub, перезапускает и останавливает сервер. После остановки значок закрывается; ярлык Hub снова запускает сервер. Размещение значка в области уведомлений настраивается средствами системы.', 'The icon is shown while the server runs. Its menu opens Hub, restarts and stops the server. Stopping closes the icon; the Hub shortcut starts the server again. Your operating system controls where the icon appears.');
    const status = state.error || (running === true ? text('Сервер работает', 'Server is running') : running === false ? text('Сервер остановлен', 'Server is stopped') : text('Состояние сервера неизвестно', 'Server status is unknown'));
    const mode = value?.mode === 'installed' ? text('Установка', 'Installed') : value?.mode === 'source' ? text('Исходный код', 'Source') : value?.mode === 'development' ? text('Тестовый сервер', 'Development server') : null;
    return `<div class="section-head"><div><h2>${text('Сервер Project Hub', 'Project Hub server')}</h2><p class="muted">${text('Сведения о сервере и фактически используемых папках.', 'Server details and folders currently in use.')}</p></div><span class="scope">${escape(mode || text('Состояние', 'Status'))}</span></div><div class="hub-runtime-status" role="status">${escape(status)}</div><dl class="hub-runtime-details">${row(text('Состояние', 'Status'), running == null ? null : (running ? text('Работает', 'Running') : text('Остановлен', 'Stopped')))}${row(text('Режим', 'Mode'), mode)}${row(text('Порт', 'Port'), value?.port)}${row(text('Адрес', 'Address'), value?.url)}${row(text('Папка данных', 'Data folder'), value?.dataHome,'data')}${row(text('Папка резервных копий', 'Backup folder'), value?.backupHome,'backups')}${row(text('Папка программы', 'Program folder'), value?.programPath,'program')}${row(text('Значок сервера', 'Server icon'), tray.visible === true ? text('Отображается', 'Shown') : value?.supervised === false ? text('Прямой тестовый запуск', 'Direct development launch') : text('Запускается', 'Starting'))}</dl><p role="status" class="muted" data-local-files-status></p><p class="muted hub-runtime-tray">${escape(explanation)}</p><p class="muted">${text('Для обновления или переустановки запустите установщик Project Hub. Программа сохранит данные и настройки.', 'Run the Project Hub installer to update or reinstall. Your data and settings are preserved.')}</p>${diagnosticsBody(value)}`;
  }
  function card() { return `<section class="card hub-runtime-card" id="hub-runtime-settings">${cardBody()}</section>`; }
  function patch() {
    const node = document.getElementById('hub-runtime-settings');
    if (node && globalThis.HubLiveUI?.patch) globalThis.HubLiveUI.patch(node, cardBody(), {preserveInputs:true});
  }
  async function load() {
    try {
      const response = await fetch('/api/runtime', {cache:'no-store'});
      const value = await response.json();
      if (!response.ok || !valid(value)) throw Error(text('Сервер вернул неполное состояние.', 'The server returned incomplete status.'));
      state.value = value; state.error = ''; badge(value); patch();
    } catch (error) {
      state.error = text('Не удалось получить состояние сервера. Проверьте журнал диагностики.', 'Could not read server status. Check the diagnostic log.');
      badge(null); patch();
    }
  }
  function afterRender() {
    const mounted = document.getElementById('hub-runtime-settings');
    const badgeMounted = document.getElementById('hub-server-indicator');
    if (!mounted && !badgeMounted) return;
    if (!state.timer) { load(); state.timer = setInterval(load, 5000); }
  }
  globalThis.HubRuntimeUI = {card, afterRender, current:() => state.value, refresh:load};
})();
