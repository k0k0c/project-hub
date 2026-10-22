"use strict";
let activeProject = new URLSearchParams(location.search).get('project') || '';
let projectNames = new Map();
function projectApi(path) {
  const url = new URL(path, location.origin);
  if (activeProject) url.searchParams.set('project', activeProject);
  if (url.pathname.startsWith('/api/v1/tasks/')) url.searchParams.set('view', 'ack');
  return url.pathname + url.search;
}
window.projectApi = projectApi;
const $ = (selector, scope = document) => scope.querySelector(selector);
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const labels = {
  planned: (globalThis.HubI18n?.t?.("app.4692f1b33927") ?? "Предстоит"),
  active: (globalThis.HubI18n?.t?.("app.59a28f1b11df") ?? "В работе"),
  queued: (globalThis.HubI18n?.t?.("app.b22a2454bd69") ?? "В очереди"),
  blocked: (globalThis.HubI18n?.t?.("app.5db21586e6b5") ?? "Есть препятствие"),
  done: (globalThis.HubI18n?.t?.("app.b459ff8f254e") ?? "Завершено"),
  cancelled: (globalThis.HubI18n?.t?.("app.23a2a9bfcf74") ?? "Отменено"),
  passed: (globalThis.HubI18n?.t?.("app.be625a64f643") ?? "Пройдено"),
  running: (globalThis.HubI18n?.t?.("app.599ca07b8dd2") ?? "Выполняется"),
  unknown: (globalThis.HubI18n?.t?.("app.8cf46ff28cc1") ?? "Результат неизвестен"),
  failed: (globalThis.HubI18n?.t?.("app.bf22dfeeba8b") ?? "Ошибка"),
  waiting: (globalThis.HubI18n?.t?.("app.89c9e3a11aee") ?? "Ожидает"),
  idle: (globalThis.HubI18n?.t?.("app.f4dff7d22ed4") ?? "Ответ завершён"),
  interrupted: (globalThis.HubI18n?.t?.("app.f7b2f77928af") ?? "Прерван"),
  closed: (globalThis.HubI18n?.t?.("app.32bb1c680f95") ?? "Сессия закрыта"),
};
const kindLabels = {
  "task.created": (globalThis.HubI18n?.t?.("app.756c6c64e23e") ?? "Новая задача"),
  "task.updated": (globalThis.HubI18n?.t?.("app.e97acacf9acf") ?? "Задача обновлена"),
  "task.reopened": (globalThis.HubI18n?.t?.("app.a2a4bf6e680e") ?? "Задача переоткрыта"),
  "task.status_changed": (globalThis.HubI18n?.t?.("app.5e6ee4b48ff8") ?? "Изменён статус задачи"),
  "task.type_changed": (globalThis.HubI18n?.t?.("app.9f1fe6d24245") ?? "Изменён тип задачи"),
  "task.priority_changed": (globalThis.HubI18n?.t?.("app.f72238b65172") ?? "Изменён приоритет задачи"),
  "task.parent_changed": (globalThis.HubI18n?.t?.("app.1344d008de05") ?? "Изменён родитель задачи"),
  "task.linked": (globalThis.HubI18n?.t?.("app.9ae1d1f1c567") ?? "Задачи связаны"),
  "task.unlinked": (globalThis.HubI18n?.t?.("app.6e0b5dcf13c5") ?? "Связь задач удалена"),
  "stage.updated": (globalThis.HubI18n?.t?.("app.50a759ac4169") ?? "Этап обновлён"),
  "stage.created": (globalThis.HubI18n?.t?.("app.46b65269f9fa") ?? "Этап добавлен"),
  "stage.deleted": (globalThis.HubI18n?.t?.("app.d4ec24da0fc5") ?? "Этап удалён из плана"),
  "stage.unlinked": (globalThis.HubI18n?.t?.("app.6b48c0310af5") ?? "Этап отвязан"),
  "stage.transferred": (globalThis.HubI18n?.t?.("app.cf4f5f8f1ec5") ?? "Этап перенесён"),
  "stage.exported": (globalThis.HubI18n?.t?.("app.e12d195ff80e") ?? "Этап перенесён из задачи"),
  "stage.imported": (globalThis.HubI18n?.t?.("app.068026c33a92") ?? "Этап перенесён в задачу"),
  "stage.restored": (globalThis.HubI18n?.t?.("app.d9a99eebd8cb") ?? "Этап восстановлен"),
  "work.started": (globalThis.HubI18n?.t?.("app.fd408eab202b") ?? "Работа начата"),
  "work.completed": (globalThis.HubI18n?.t?.("app.768257912b25") ?? "Шаг завершён"),
  "git.commit": "Git commit",
  "git.push": "Git push",
  "check.started": (globalThis.HubI18n?.t?.("app.69faab6e6901") ?? "Проверка запущена"),
  "check.passed": (globalThis.HubI18n?.t?.("app.7a780b2ed19f") ?? "Проверка пройдена"),
  "check.failed": (globalThis.HubI18n?.t?.("app.1cbcef8251cf") ?? "Проверка не прошла"),
  "check.interrupted": (globalThis.HubI18n?.t?.("app.aef23a5d2d28") ?? "Проверка прервана"),
  "check.unknown": (globalThis.HubI18n?.t?.("app.09a8377bf26f") ?? "Результат проверки неизвестен"),
  "check.corrected": (globalThis.HubI18n?.t?.("app.adc4ed716c1a") ?? "Результат проверки исправлен"),
  finding: (globalThis.HubI18n?.t?.("app.574d43b44984") ?? "Наблюдение"),
  decision: (globalThis.HubI18n?.t?.("app.199d6db958cd") ?? "Решение"),
  note: (globalThis.HubI18n?.t?.("app.1d80e1757a7a") ?? "Запись"),
  'task.transferred': (globalThis.HubI18n?.t?.("app.d230f0ae8043") ?? 'Перенос задачи'),
};
const icons = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  tasks: "M8 5h13 M8 12h13 M8 19h13 M2 5l1 1 2-3 M2 12l1 1 2-3 M2 19l1 1 2-3",
  history: "M4 7a9 9 0 1 1-1 9 M4 2v6h6 M12 7v6l4 2",
  git: "M6 3v18 M6 6h7a4 4 0 1 1 0 8H6 M13 10l5 0 M18 7l3 3-3 3",
  architecture:
    "M9 2h6v5H9z M2 17h6v5H2z M16 17h6v5h-6z M12 7v5H5v5 M12 12h7v5",
  docs: "M4 3h12l4 4v14H4z M15 3v5h5 M8 12h8 M8 16h6",
  checks: "M12 2l8 3v7c0 5-8 10-8 10S4 17 4 12V5z M8 12l3 3 5-6",
  actions: "M5 6l5 6-5 6 M12 18h7",
  projects: "M3 7V4h7l2 3h9v13H3z",
  coordination: "M3 3h18v14H8l-5 4z M7 7h10 M7 11h7",
};
const navigation = [
  ["overview", (globalThis.HubI18n?.t?.("app.7641ad9bafb2") ?? "Обзор проекта")],
  ["tasks", (globalThis.HubI18n?.t?.("app.03cc1c2d5ac2") ?? "Задачи")],
  ["git", "Git"],
  ["coordination", (globalThis.HubI18n?.t?.("app.b5121e526dd9") ?? "Чаты")],
  ["history", (globalThis.HubI18n?.t?.("app.5143a08843c2") ?? "История разработки")],
  ["checks", (globalThis.HubI18n?.t?.("app.bb1b79b14c91") ?? "Проверки")],
  ["settings", (globalThis.HubI18n?.t?.("app.985b5e0f2ccf") ?? "Настройки")],
  ["projects", (globalThis.HubI18n?.t?.("app.5029f02d0a94") ?? "Проекты")],
  ["architecture", (globalThis.HubI18n?.t?.("app.1898e1901dcd") ?? "Архитектура и код")],
  ["docs", (globalThis.HubI18n?.t?.("app.b123be6f8236") ?? "Документация")],
  ["actions", (globalThis.HubI18n?.t?.("app.cad123465b9e") ?? "Действия"), (globalThis.HubI18n?.t?.("app.295bd5ba2d79") ?? "позже")],
];
let state,
  revision = -1,
  coordinationRevision = -1,
  coordinationOffset = 0,
  connected = false,
  loadInFlight,
  refreshAgain = false;
function createTaskDetailLoader({fetcher, getContext, onSuccess, onError}) {
  const requests = new Map(), errors = new Map();
  const key = (project, task, revision) => JSON.stringify([project, task, revision]);
  const current = (project, task, revision) => {
    const context = getContext();
    return context?.project === project && context?.task === task && context?.revision === revision;
  };
  return {
    load(project, task, revision) {
      const requestKey = key(project, task, revision);
      if (errors.has(requestKey)) return null;
      if (requests.has(requestKey)) return requests.get(requestKey);
      let request;
      try { request = Promise.resolve(fetcher(project, task, revision)); }
      catch (error) { request = Promise.reject(error); }
      request = request.then(payload => {
        if (payload?.revision !== undefined && payload.revision !== revision) return null;
        if (current(project, task, revision)) onSuccess(payload?.task || payload, project, task, revision);
        return payload;
      }).catch(error => {
        if (current(project, task, revision)) {
          errors.set(requestKey, error);
          onError(error, project, task, revision);
        }
        throw error;
      }).finally(() => requests.delete(requestKey));
      requests.set(requestKey, request);
      return request;
    },
    error(project, task, revision) { return errors.get(key(project, task, revision)); },
    retry(project, task, revision) { errors.delete(key(project, task, revision)); },
  };
}
function retainTaskDetails(previous, next) {
  if (!previous || !Array.isArray(previous.tasks) || !Array.isArray(next.tasks)) return next;
  const hydrated = new Map(previous.tasks.filter(task => task.detailLoaded || task.detailCached).map(task => [task.id, task]));
  next.tasks = next.tasks.map(task => {
    const detail = hydrated.get(task.id);
    if (!detail) return task;
    const stages = new Map((detail.stages || []).map(stage => [stage.id, stage]));
    return {...detail, ...task, detailCached:true, detailLoaded:detail.detailLoaded === true && previous.revision === next.revision,
      stages:(task.stages || []).map(stage => ({...stages.get(stage.id), ...stage}))};
  });
  return next;
}
const taskDetailLoader = createTaskDetailLoader({
  fetcher: async (project, task) => {
    const response = await fetch(projectApi('/api/tasks/detail?task=' + encodeURIComponent(task)), {cache: 'no-store'});
    const payload = await response.json();
    if (!response.ok) throw Error(payload.error || response.status);
    return payload;
  },
  getContext: () => ({project: activeProject, task: route()[1], revision: state?.revision}),
  onSuccess: (task, project, taskId, detailRevision) => {
    if (!state || state.revision !== detailRevision || activeProject !== project || route()[1] !== taskId) return;
    state.tasks = state.tasks.map(item => item.id === taskId ? {...item, ...task, detailLoaded: true} : item);
    render({preserveScroll: true, background:true});
  },
  onError: (error, project, taskId, detailRevision) => {
    if (activeProject === project && state?.revision === detailRevision && route()[1] === taskId) {
      render({preserveScroll: true, background:true});
    }
  },
});
let taskTab = "plan",
  taskFilter = "all",
  taskTypeFilter = "all",
  taskPriorityFilter = "all",
  taskListSort = new URLSearchParams(location.search).get('taskSort') || "created",
  taskSearch = "",
  taskSort = new URLSearchParams(location.search).get('sort') || "created",
  treeExpanded = new Set(),
  treeStateProject = '',
  historyTask = "",
  historyKind = "",
  historyData = [],
  historyNext = null,
  historyGeneration = 0,
  historyLoading = route()[0] === "history",
  historyError = "",
  gitData = null,
  gitError = "",
  gitGeneration = 0;
const date = (value) =>
  value
    ? new Intl.DateTimeFormat((globalThis.HubI18n?.locale==='en'?'en-GB':'ru-RU'), {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "—";
const clock = (value) =>
  value
    ? new Intl.DateTimeFormat((globalThis.HubI18n?.locale==='en'?'en-GB':'ru-RU'), {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).format(new Date(value))
    : "—";
const dateOnly = (value) =>
  new Intl.DateTimeFormat((globalThis.HubI18n?.locale==='en'?'en-GB':'ru-RU'), {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
const uiIcon = (name) => {
  const names = {check:'Check',play:'Play',pause:'Pause',clock:'Clock',alert:'CircleAlert',
    close:'X',question:'CircleHelp',link:'Link',copy:'Copy',chevron:'ChevronDown',
    edit:'Pencil',plus:'Plus',transfer:'ArrowRightLeft',unlink:'Unlink',delete:'Trash2',
    reopen:'RotateCcw',save:'Save',refresh:'RefreshCw',search:'Search',info:'Info',
    up:'ArrowUp',down:'ArrowDown',left:'ArrowLeft',right:'ArrowRight',columns:'Columns3',
    star:'Star',settings:'Settings',chat:'MessageSquare',expand:'Expand',download:'Download',upload:'Upload',
    file:'File',fileText:'FileText',fileCode:'FileCode2',fileJson:'FileJson2',
    spreadsheet:'FileSpreadsheet',presentation:'Presentation',archive:'FileArchive',
    audio:'FileAudio',video:'FileVideo'};
  const node = lucide.createElement(lucide.icons[names[name] || 'CircleAlert']);
  node.setAttribute('class', 'ui-icon');
  node.setAttribute('aria-hidden', 'true');
  return node.outerHTML;
};
const statusIcons = { done: "check", passed: "check", active: "play", running: "play", interrupted: "pause", unknown: "question", planned: "clock", queued: "clock", blocked: "alert", failed: "alert", cancelled: "close" };
const status = (value) =>
  `<span class="tag ${escape(value)}">${uiIcon(statusIcons[value] || "clock")}<span>${escape(labels[value] || value)}</span></span>`;
const blockerLabels = {technical: (globalThis.HubI18n?.t?.("app.61d077d3515c") ?? 'Техническое препятствие'), user_input: (globalThis.HubI18n?.t?.("app.2ae8bedad7c9") ?? 'Нужен ответ пользователя'), administrative: (globalThis.HubI18n?.t?.("app.067c4b855cc3") ?? 'Проблема учёта')};
function blockerDetail(item) {
  if (item.status !== 'blocked') return '';
  const blocker = item.blocker;
  const label = blockerLabels[blocker?.kind] || labels.blocked;
  const reason = blocker?.reason || item.summary || (globalThis.HubI18n?.t?.("app.60917697d591") ?? 'Причина не указана.');
  const action = blocker?.action || (item.remaining || []).join(' ') || (globalThis.HubI18n?.t?.("app.a699469b575a") ?? 'Уточнить причину и необходимое действие в записи задачи.');
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.51bad52ca4c2",{v0:(escape(label)),v1:(escape(reason)),v2:(escape(action))}) : `<div class="notice blocker-detail"><strong>${escape(label)}</strong><p>Причина: ${escape(reason)}</p><p>Необходимое действие: ${escape(action)}</p></div>`);
}
function planStatus(item) {
  if (item.status !== 'blocked' || !blockerLabels[item.blocker?.kind]) return status(item.status);
  return `<span class="tag blocked" title="${escape(item.blocker.reason + (globalThis.HubI18n?.t?.("app.5e9ea2105d84") ?? ' Необходимое действие: ') + item.blocker.action)}">${uiIcon('alert')}<span>${escape(blockerLabels[item.blocker.kind])}</span></span>`;
}
function taskStatus(task, stage = null, compact = false) {
  const works = (task.currentWorks || []).filter(w => !stage || (w.stageIds || [w.stageId]).includes(stage.id));
  const observed = (stage || task).agentActivity;
  const activity = ['active', 'idle', 'unknown','waiting'].includes(observed?.state) ? observed.state : works.length ? 'active' : 'unknown';
  const text = {active: (globalThis.HubI18n?.t?.("app.36adf77adf8b") ?? 'Агент работает'), idle: (globalThis.HubI18n?.t?.("app.44ee3fe42edd") ?? 'Агент не работает'), unknown: (globalThis.HubI18n?.t?.("app.8dd65a3e6de6") ?? 'Агент: нет данных'),waiting:(globalThis.HubI18n?.t?.("app.05ece6ebda35") ?? 'Агент ожидает')}[activity];
  const detail = activity === 'active' ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.29069a39d68a",{v0:(new Set(works.map(w => w.session)).size)}) : `Активных чатов: ${new Set(works.map(w => w.session)).size}. По последним событиям подключённых агентов.`) : activity === 'idle' ? (globalThis.HubI18n?.t?.("app.a5ed711eb426") ?? 'Нет активного исполнителя. Статус плана не изменён.') : (globalThis.HubI18n?.t?.("app.a2fd6a85723b") ?? 'Недостаточно данных подключённых агентов для определения активности.');
  const activityIcon = activity === 'active' ? 'play' : activity === 'idle' ? 'pause' : 'question';
  return `<span class="task-status-pair">${planStatus(stage || task)}<span class="agent-activity ${activity} ${compact ? 'icon-only' : ''}" title="${escape(text + '. ' + detail)}" aria-label="${escape(text + '. ' + detail)}">${uiIcon(activityIcon)}${compact ? '' : `<span>${text}</span>`}</span></span>`;
}
const taskLink = (task, stage) =>
  `#tasks/${encodeURIComponent(task.id)}${stage ? "/" + encodeURIComponent(stage) : ""}`;
const evidence = (sources) =>
  renderImageEvidence(sources);
const list = (items, completed = false) =>
  items?.length
    ? `<ul class="plain-list ${completed ? "completed" : ""}">${items.map((x) => `<li>${escape(x)}</li>`).join("")}</ul>`
    : `<p class="caption">${completed ? (globalThis.HubI18n?.t?.("app.192d7b945ed0") ?? "Завершённых пунктов пока нет.") : (globalThis.HubI18n?.t?.("app.aa4211d27ae7") ?? "Нет открытых пунктов в этом этапе.")}</p>`;
function stageGitCommit(stage) {
  const commit = stage?.gitCommit;
  const shaValue = commit?.sha || commit?.shortSha;
  if (!commit || !shaValue || commit.status !== 'committed') return '';
  const sha = escape(shaValue);
  const ref = commit.pushed === true && commit.githubUrl ? `<a href="${escape(commit.githubUrl)}" target="_blank" rel="noopener">${sha}</a>` : (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.911177018aa6",{v0:(sha)}) : `<code title="Commit ещё не отправлен в upstream">${sha}</code>`);
  const state = commit.pushed === true ? (globalThis.HubI18n?.t?.("app.4b5140e1977e") ?? 'Commit отправлен') : commit.pushed === false ? (globalThis.HubI18n?.t?.("app.06377ff3551e") ?? 'Локальный commit · не отправлен') : (globalThis.HubI18n?.t?.("app.5e4282c196d5") ?? 'Локальный commit · статус push неизвестен');
  const fileCount = commit.files?.length ?? commit.filesCount;
  return `<div class="git-commit"><span class="git-commit-state committed">${state}</span>${ref}<span>${escape(fileCount ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.7281412dfc9c",{v0:(fileCount)}) : `${fileCount} файлов`) : '')}</span></div>`;
}
function checkpointCommitList(task, stage) {
  const checkpoint = (stage || task)?.gitCheckpoint;
  return [checkpoint, ...(Array.isArray(checkpoint?.commits) ? checkpoint.commits : []), checkpoint?.gitOutcome]
    .filter(commit => commit?.status === 'committed' && (commit.sha || commit.shortSha));
}
function gitCommits(task, stage) {
  const seen = new Set(), commits = [(stage || task)?.gitCommit, ...checkpointCommitList(task, stage)];
  return commits.map(commit => {
    const sha = commit?.sha || commit?.shortSha;
    if (!sha || commit?.status !== 'committed' || seen.has(sha)) return '';
    seen.add(sha);
    return stageGitCommit({gitCommit: commit});
  }).join('');
}
const checkpointRetries = new Set();
function checkpointReason(checkpoint) {
  const outcome = checkpoint.publication?.status === 'pending' ? checkpoint.publication : checkpoint;
  const messages = {
    dirty_baseline: (globalThis.HubI18n?.t?.("app.92e354422366") ?? 'В исходных файлах уже были изменения. Нужна сверка их принадлежности.'),
    baseline_not_in_commit_parent: (globalThis.HubI18n?.t?.("app.bedd87cba2a8") ?? 'Исходные байты отличаются от родителя commit. Нужна сверка содержимого.'),
    completed_bytes_changed: (globalThis.HubI18n?.t?.("app.5186375d369d") ?? 'Файлы изменились после завершения работы. Проверьте новый результат.'),
    candidate_content_changed: (globalThis.HubI18n?.t?.("app.fc6d5ee4c2d1") ?? 'Содержимое кандидата отличается от завершённой работы. Commit остановлен.'),
    coverage_mismatch: (globalThis.HubI18n?.t?.("app.88d0bb2dfa56") ?? 'Commit не подтверждает сохранённый результат работы.'),
    content_corrupt: (globalThis.HubI18n?.t?.("app.9867b0726852") ?? 'Сохранённые байты не прошли проверку целостности.'),
    baseline_corrupt: (globalThis.HubI18n?.t?.("app.beaf13a8004e") ?? 'Исходные байты не прошли проверку целостности.'),
    boundary_missing: (globalThis.HubI18n?.t?.("app.81c0105d30fa") ?? 'Не хватает сохранённой границы содержимого для проверки.'),
    mixed_boundary_versions: (globalThis.HubI18n?.t?.("app.14749befde27") ?? 'Старые и новые границы требуют отдельной сверки.'),
    filesystem_permission_denied: (globalThis.HubI18n?.t?.("app.4548f997188c") ?? 'Операционная система отказала в доступе.'),
    journal_publication_failed: (globalThis.HubI18n?.t?.("app.94e03836b504") ?? 'Результат сохранён; требуется повторить публикацию в Hub.'),
    concurrent_git_change: (globalThis.HubI18n?.t?.("app.3f016922e801") ?? 'HEAD или индекс изменился во время подготовки. Проверьте кандидат.'),
    concurrent_source_change: (globalThis.HubI18n?.t?.("app.70ac4d55a2cf") ?? 'Файлы изменились во время чтения. Повторите проверку.'),
    work_active: (globalThis.HubI18n?.t?.("app.ecdf0424ff95") ?? 'Связанная работа ещё выполняется.'),
    scope_missing: (globalThis.HubI18n?.t?.("app.a95f5932b1f3") ?? 'Нет подтверждённой области изменений для автоматического commit.'),
    index_preexisting: (globalThis.HubI18n?.t?.("app.02fa734016d0") ?? 'В индексе уже есть staged изменения. Нужна ручная сверка.'),
    head_changed: (globalThis.HubI18n?.t?.("app.dc154b7add3e") ?? 'HEAD изменился. Проверьте исходную границу и существующие коммиты.'),
    reserved_scope_committed: (globalThis.HubI18n?.t?.("app.cffac49d11c4") ?? 'Заявленные изменения уже вошли в commit. Согласуйте подтверждённое покрытие.'),
    clean_filter_adapter_required: (globalThis.HubI18n?.t?.("app.fac7576116ea") ?? 'Git использует преобразование содержимого. Нужен проверенный adapter.'),
    batch_baseline_unknown: (globalThis.HubI18n?.t?.("app.bbd6ca978695") ?? 'Для исходных байтов не хватает подтверждённых изменений. Добавьте связанную работу или выполните отдельную сверку.'),
    batch_conflict: (globalThis.HubI18n?.t?.("app.3b1798c79ea9") ?? 'Изменения конфликтуют. Нужен явно разрешённый результат.'),
    batch_parent_changed: (globalThis.HubI18n?.t?.("app.4c13d77e2a92") ?? 'Родитель commit отличается от просмотренного кандидата.'),
    batch_preview_changed: (globalThis.HubI18n?.t?.("app.ed0f7dfb04dd") ?? 'Кандидат изменился. Повторите предварительный просмотр.'),
    batch_revision_changed: (globalThis.HubI18n?.t?.("app.7257774214bb") ?? 'Проект изменился. Повторите предварительный просмотр.'),
    batch_adoption_conflict: (globalThis.HubI18n?.t?.("app.45af8687813d") ?? 'Checkpoint уже имеет другое подтверждённое покрытие.'),
    batch_worker_active: (globalThis.HubI18n?.t?.("app.61ad098f5abc") ?? 'Дождитесь завершения текущей операции checkpoint.'),
    batch_target_unfinished: (globalThis.HubI18n?.t?.("app.fcb285883594") ?? 'Завершите выбранные задачи и этапы перед сверкой.'),
    legacy_boundary_unproven: (globalThis.HubI18n?.t?.("app.ce1001c5e410") ?? 'Старая запись не содержит исходных байтов. Нужна отдельная сверка истории.')
  };
  return messages[outcome.reasonCode] || outcome.reason || (globalThis.HubI18n?.t?.("app.4800516916e2") ?? 'Ожидает проверки');
}
function checkpointStatus(task, stage) {
  return checkpointCommitList(task, stage).map(commit => stageGitCommit({gitCommit: commit})).join('');
}
function checkpointStatusContents(task, stage) {
  const checkpoint = (stage || task).gitCheckpoint;
  if (!checkpoint) return '';
  if (checkpoint.publication?.status === 'pending') {
    const key = JSON.stringify([activeProject,task.id,stage?.id]);
    const label = checkpoint.sha ? (globalThis.HubI18n?.t?.("app.dab03b62d573") ?? 'Commit сохранён; метаданные ожидают публикации') : (globalThis.HubI18n?.t?.("app.4dbbff2ba232") ?? 'Результат Git ожидает публикации');
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.192b0a33be70",{v0:(escape(label)),v1:(escape(checkpoint.publication.reason || '')),v2:(escape(checkpointReason(checkpoint))),v3:(escape(task.id)),v4:(escape(stage?.id || '')),v5:(checkpointRetries.has(key) ? 'disabled' : ''),v6:(uiIcon('refresh'))}) : `<div class="checkpoint-status" role="status"><span>${escape(label)}</span><span class="checkpoint-reason" title="${escape(checkpoint.publication.reason || '')}">${escape(checkpointReason(checkpoint))}</span><button class="icon-button" data-checkpoint-retry="${escape(task.id)}" data-checkpoint-stage="${escape(stage?.id || '')}" title="Повторить публикацию метаданных" aria-label="Повторить публикацию метаданных" ${checkpointRetries.has(key) ? 'disabled' : ''}>${uiIcon('refresh')}</button></div>`);
  }
  if (checkpoint.status === 'committed') return '';
  const names = {pending:(globalThis.HubI18n?.t?.("app.b8c18e728cfe") ?? 'Commit ожидает выполнения'),error:(globalThis.HubI18n?.t?.("app.62491cf7472e") ?? 'Не удалось создать commit'),no_changes:(globalThis.HubI18n?.t?.("app.2fbe37c6b688") ?? 'Изменений для commit нет'),disabled:(globalThis.HubI18n?.t?.("app.4da313bdaf1b") ?? 'Автоматические коммиты выключены')};
  const key = JSON.stringify([activeProject,task.id,stage?.id]);
  const coveredCommits = checkpoint.status === 'no_changes' && Array.isArray(checkpoint.commits)
    ? checkpoint.commits.map(commit => stageGitCommit({gitCommit: commit})).join('') : '';
  const knownCommit = checkpoint.gitOutcome?.status === 'committed' && Boolean(checkpoint.gitOutcome.sha || checkpoint.gitOutcome.shortSha);
  const label = knownCommit ? (globalThis.HubI18n?.t?.("app.c9718a7f757e") ?? 'Commit создан; требуется сверка покрытия') : names[checkpoint.status] || checkpoint.status;
  const diagnostic = [checkpoint.reason, checkpoint.layer, checkpoint.operationId].filter(Boolean).join(' · ');
  return `<div class="checkpoint-status" role="status"><span title="${escape(diagnostic)}">${escape(label)}</span>${checkpoint.reason ? `<span class="checkpoint-reason" title="${escape(diagnostic)}">${escape(checkpointReason(checkpoint))}</span>` : ''}${checkpoint.status === 'error' ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.202d8b0ba9dd",{v0:(escape(task.id)),v1:(escape(stage?.id || '')),v2:(checkpointRetries.has(key) ? 'disabled' : ''),v3:(uiIcon('refresh')),v4:(escape(task.id)),v5:(escape(stage?.id || '')),v6:(checkpointRetries.has(key) ? 'disabled' : ''),v7:(uiIcon('link'))}) : `<button class="icon-button" data-checkpoint-retry="${escape(task.id)}" data-checkpoint-stage="${escape(stage?.id || '')}" title="Повторить checkpoint" aria-label="Повторить checkpoint" ${checkpointRetries.has(key) ? 'disabled' : ''}>${uiIcon('refresh')}</button><button class="icon-button" data-checkpoint-reconcile="${escape(task.id)}" data-checkpoint-stage="${escape(stage?.id || '')}" title="Согласовать существующие коммиты" aria-label="Согласовать существующие коммиты" ${checkpointRetries.has(key) ? 'disabled' : ''}>${uiIcon('link')}</button>`) : ''}</div>${coveredCommits}${knownCommit ? stageGitCommit({gitCommit:checkpoint.gitOutcome}) : ''}`;
}
function batchTargets() {
  return state.tasks.flatMap(task => [
    ...(task.status === 'done' && task.gitCheckpoint?.status === 'error' ? [{task:task.id, title:task.title, checkpoint:task.gitCheckpoint.id}] : []),
    ...(task.stages || []).filter(stage => stage.status === 'done' && stage.gitCheckpoint?.status === 'error')
      .map(stage => ({task:task.id, stage:stage.id, title:task.title + ' · ' + stage.title, checkpoint:stage.gitCheckpoint.id}))
  ]);
}
function openCheckpointBatch(task, stage) {
  if (!activeProject || document.querySelector('[data-checkpoint-dialog]')) return;
  const project = activeProject, candidates = batchTargets();
  const dialog = document.createElement('dialog');
  dialog.className = 'task-editor checkpoint-batch'; dialog.setAttribute('data-checkpoint-dialog', '');
  dialog.setAttribute('aria-label', (globalThis.HubI18n?.t?.("app.c6ebf13052e8") ?? 'Сверка общего Git commit'));
  dialog.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.1fedd22c3995",{v0:(uiIcon('close')),v1:(candidates.map((item,index) => `<label class="edit-field"><span><input type="checkbox" name="target" value="${index}" ${item.task === task && (item.stage || '') === (stage || '') ? 'checked' : ''}> ${escape(item.title)}</span><small>${escape(item.checkpoint)}</small></label>`).join(''))}) : `<form novalidate><header><h2>Сверка общего Git commit</h2><button type="button" class="icon-button" data-close aria-label="Отмена" title="Отмена">${uiIcon('close')}</button></header><div class="editor-fields"><fieldset><legend>Связанные задачи и этапы (до 20)</legend>${candidates.map((item,index) => `<label class="edit-field"><span><input type="checkbox" name="target" value="${index}" ${item.task === task && (item.stage || '') === (stage || '') ? 'checked' : ''}> ${escape(item.title)}</span><small>${escape(item.checkpoint)}</small></label>`).join('')}</fieldset><label class="edit-field"><span>Полный SHA существующего commit (необязательно для подготовки кандидата)</span><input name="commit" spellcheck="false" maxlength="64"></label><label class="edit-field"><span>Основание принадлежности выбранных изменений</span><textarea name="reason" rows="3" maxlength="1200" required></textarea></label><div data-review aria-live="polite"></div></div><p class="editor-error" role="alert"></p><footer><button type="submit">Предварительный просмотр</button><button type="button" data-adopt disabled>Зачесть проверенное покрытие</button></footer></form>`);
  document.body.append(dialog);
  const form = dialog.querySelector('form'), feedback = dialog.querySelector('[role="alert"]');
  const review = dialog.querySelector('[data-review]'), adopt = dialog.querySelector('[data-adopt]');
  let pending = false, preview = null, request = null, next = null, associations = new Map();
  const close = () => { if (!pending) dialog.close(); };
  dialog.querySelector('[data-close]').onclick = close;
  dialog.addEventListener('close', () => dialog.remove(), {once:true});
  dialog.addEventListener('cancel', event => { if (pending) event.preventDefault(); });
  form.addEventListener('input', () => { preview = null; adopt.disabled = true; review.innerHTML = ''; });
  const busy = value => {
    pending = value;
    form.querySelectorAll('input,textarea,button').forEach(element => { element.disabled = value; });
    adopt.disabled = value || !preview?.ready || !request?.commit;
  };
  const call = async body => {
    const response = await fetch('/api/v1/checkpoints/batch?' + new URLSearchParams({project}),
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) { const error = Error(checkpointReason({...data,reason:data.error})); error.diagnostic = data.error; throw error; }
    return data;
  };
  const load = async () => {
    if (!preview?.batchBlob) return;
    const response = await fetch('/api/checkpoints/batch-detail?' + new URLSearchParams({project,blob:preview.batchBlob,section:'steps',offset:next || 0,limit:25}));
    const data = await response.json();
    if (!response.ok) throw Error(data.error || (globalThis.HubI18n?.t?.("app.689e8ab88b93") ?? 'Не удалось прочитать покрытие'));
    const methods = {'exact-content-chain':(globalThis.HubI18n?.t?.("app.2b931a8e72a1") ?? 'Полная цепочка байтов'),'reviewed-disjoint-text-hunks':(globalThis.HubI18n?.t?.("app.3c91fdcbed40") ?? 'Независимые текстовые правки')};
    const record = value => value ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.977c4eb0e763",{v0:(value.mode),v1:(value.size),v2:(value.blob)}) : `${value.mode} · ${value.size} байт · ${value.blob}`) : (globalThis.HubI18n?.t?.("app.a3920e8b6bb3") ?? 'Файл отсутствует');
    const version = (path, side, changeset, text, hash) => `<a href="/api/checkpoints/batch-content?${escape(new URLSearchParams({project,blob:preview.batchBlob,path,side,...(changeset ? {changeset} : {}),...(hash ? {version:hash} : {})}).toString())}" download>${text}</a>`;
    review.querySelector('[data-steps]').insertAdjacentHTML('beforeend', data.items.map(item => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.9276cf1aaaa6",{v0:(escape(item.path)),v1:(escape(methods[item.method] || item.method)),v2:(escape(record(item.before))),v3:(item.before ? version(item.path,'before',null,(globalThis.HubI18n?.t?.("app.535119bf3cc5") ?? 'Скачать'),item.before.blob) : ''),v4:(escape(record(item.after))),v5:(item.after ? version(item.path,'after',null,(globalThis.HubI18n?.t?.("app.535119bf3cc5") ?? 'Скачать'),item.after.blob) : ''),v6:(item.members.map(member => `<li>${escape(associations.get(member.changeset) || member.changeset)}${item.before ? ' · '+version(item.path,'before',member.changeset,(globalThis.HubI18n?.t?.("app.fe3f7b8341dd") ?? 'Исходная версия')) : ''}${item.after ? ' · '+version(item.path,'after',member.changeset,(globalThis.HubI18n?.t?.("app.473ea5a05435") ?? 'Результат работы')) : ''}${member.hunksCount ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.622966d01aab",{v0:(member.hunksCount)}) : ` · текстовых правок: ${member.hunksCount}`) : ''}</li>`).join(''))}) : `<article><h3>${escape(item.path)}</h3><p>${escape(methods[item.method] || item.method)}</p><p>До: <code>${escape(record(item.before))}</code> ${item.before ? version(item.path,'before',null,(globalThis.HubI18n?.t?.("app.535119bf3cc5") ?? 'Скачать'),item.before.blob) : ''}</p><p>После: <code>${escape(record(item.after))}</code> ${item.after ? version(item.path,'after',null,(globalThis.HubI18n?.t?.("app.535119bf3cc5") ?? 'Скачать'),item.after.blob) : ''}</p><ul>${item.members.map(member => `<li>${escape(associations.get(member.changeset) || member.changeset)}${item.before ? ' · '+version(item.path,'before',member.changeset,(globalThis.HubI18n?.t?.("app.fe3f7b8341dd") ?? 'Исходная версия')) : ''}${item.after ? ' · '+version(item.path,'after',member.changeset,(globalThis.HubI18n?.t?.("app.473ea5a05435") ?? 'Результат работы')) : ''}${member.hunksCount ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.622966d01aab",{v0:(member.hunksCount)}) : ` · текстовых правок: ${member.hunksCount}`) : ''}</li>`).join('')}</ul></article>`)).join(''));
    next = data.next;
    review.querySelector('[data-more]').hidden = next == null;
  };
  form.onsubmit = async event => {
    event.preventDefault(); if (pending) return;
    feedback.textContent = ''; preview = null; adopt.disabled = true;
    const targets = [...form.querySelectorAll('[name="target"]:checked')].map(input => {
      const item = candidates[Number(input.value)]; return {task:item.task,...(item.stage ? {stage:item.stage} : {})};
    });
    const commit = form.elements.commit.value.trim().toLowerCase(), reason = form.elements.reason.value.trim();
    if (!targets.length || targets.length > 20 || !reason || (commit && !/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(commit))) {
      feedback.textContent = (globalThis.HubI18n?.t?.("app.ec84dd769ede") ?? 'Выберите 1–20 записей, укажите основание и полный SHA при сверке commit.'); return;
    }
    if (activeProject !== project) { feedback.textContent = (globalThis.HubI18n?.t?.("app.8baa6da45ae2") ?? 'Проект изменился. Откройте сверку заново.'); return; }
    request = {targets,reason,expected:state.revision,...(commit ? {commit} : {})};
    busy(true);
    try {
      preview = await call({...request,action:'preview'}); next = 0;
      if (!preview.ready) {
        review.innerHTML = preview.issues.map(item => `<p>${escape(checkpointReason(item))} <code>${escape(item.checkpoint)}</code></p>`).join('');
      } else {
        review.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.70a54009db3d",{v0:(preview.targets.length),v1:(preview.changesetCount),v2:(preview.pathsCount),v3:(escape(preview.head)),v4:(escape(preview.batchId)),v5:(commit ? (globalThis.HubI18n?.t?.("app.c666e017c034") ?? 'Содержимое commit и ancestry проверены. Зачёт сохранит исходные ID и историю.') : (globalThis.HubI18n?.t?.("app.6f70cfcf70c1") ?? 'Кандидат подготовлен. Создайте commit с обычными hooks через Git, затем проверьте его SHA.'))}) : `<p>Записей: ${preview.targets.length} · changesets: ${preview.changesetCount} · файлов: ${preview.pathsCount}</p><p>Git HEAD: <code>${escape(preview.head)}</code></p><p>Кандидат: <code>${escape(preview.batchId)}</code></p><p>${commit ? (globalThis.HubI18n?.t?.("app.c666e017c034") ?? 'Содержимое commit и ancestry проверены. Зачёт сохранит исходные ID и историю.') : (globalThis.HubI18n?.t?.("app.6f70cfcf70c1") ?? 'Кандидат подготовлен. Создайте commit с обычными hooks через Git, затем проверьте его SHA.')}</p><div data-steps></div><button type="button" data-more hidden>Показать ещё</button>`);
        review.querySelector('[data-more]').onclick = async () => { if (pending) return; busy(true); try { await load(); } catch(error) { feedback.textContent = (globalThis.HubI18n?.error?.(error) ?? error.message); } finally { busy(false); } };
        associations = new Map();
        let offset = 0;
        do {
          const response = await fetch('/api/checkpoints/batch-detail?' + new URLSearchParams({project,blob:preview.batchBlob,section:'changesets',offset,limit:100}));
          const details = await response.json();
          if (!response.ok) throw Error(details.error || (globalThis.HubI18n?.t?.("app.00e950b20155") ?? 'Не удалось прочитать принадлежность изменений'));
          for (const item of details.items) associations.set(item.id, item.associations.map(link => {
            const task = state.tasks.find(task => task.id === link.task), stage = task?.stages?.find(stage => stage.id === link.stage);
            return [task?.title || link.task, stage?.title || link.stage].filter(Boolean).join(' · ');
          }).join('; '));
          offset = details.next;
        } while (offset != null);
        await load();
      }
    } catch(error) { preview = null; feedback.textContent = (globalThis.HubI18n?.error?.(error) ?? error.message); feedback.title = error.diagnostic || ''; }
    finally { busy(false); }
  };
  adopt.onclick = async () => {
    if (pending || !preview?.ready || !request?.commit) return;
    if (activeProject !== project) { feedback.textContent = (globalThis.HubI18n?.t?.("app.8baa6da45ae2") ?? 'Проект изменился. Откройте сверку заново.'); return; }
    busy(true);
    try {
      await call({...request,action:'reconcile',expected:preview.revision,confirmed:preview.batchId});
      if (activeProject === project) await refresh();
      dialog.close();
    } catch(error) { feedback.textContent = (globalThis.HubI18n?.error?.(error) ?? error.message); feedback.title = error.diagnostic || ''; preview = null; }
    finally { busy(false); }
  };
  dialog.showModal();
}
function openCheckpointReconciliation(task, stage) {
  const project = activeProject, expected = state.revision;
  const key = JSON.stringify([project,task,stage || undefined]);
  if (checkpointRetries.has(key) || document.querySelector('[data-checkpoint-dialog]')) return;
  const dialog = document.createElement('dialog');
  dialog.className = 'task-editor';
  dialog.setAttribute('data-checkpoint-dialog', '');
  dialog.setAttribute('aria-label', (globalThis.HubI18n?.t?.("app.046f5286fcb5") ?? 'Согласовать существующие коммиты'));
  dialog.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.28f3a4d7214b",{v0:(uiIcon('close')),v1:(uiIcon('check'))}) : `<form novalidate><header><h2>Согласовать существующие коммиты</h2><button type="button" class="icon-button" data-close title="Отмена" aria-label="Отмена">${uiIcon('close')}</button></header><div class="editor-fields"><label class="edit-field"><span>Полные SHA (1–20), от старого к новому, через пробел или новую строку</span><textarea name="commits" rows="4" required spellcheck="false" aria-describedby="checkpoint-reconcile-error"></textarea></label><label class="edit-field"><span>Причина согласования</span><textarea name="reason" rows="3" required maxlength="1200" aria-describedby="checkpoint-reconcile-error"></textarea></label></div><p class="editor-error" id="checkpoint-reconcile-error" role="alert"></p><footer><button type="submit" class="icon-button" title="Проверить и согласовать" aria-label="Проверить и согласовать">${uiIcon('check')}</button></footer></form>`);
  document.body.append(dialog);
  const form = dialog.querySelector('form'), feedback = dialog.querySelector('[role="alert"]');
  const submit = dialog.querySelector('[type="submit"]'), close = dialog.querySelector('[data-close]');
  let pending = false;
  close.onclick = () => dialog.close();
  dialog.addEventListener('close', () => dialog.remove());
  dialog.addEventListener('cancel', event => { if (pending) event.preventDefault(); });
  form.onsubmit = async event => {
    event.preventDefault();
    if (pending || checkpointRetries.has(key)) return;
    const commits = form.elements.commits.value.trim().split(/\s+/).filter(Boolean);
    const reason = form.elements.reason.value.trim();
    feedback.textContent = '';
    if (!commits.length || commits.length > 20 || commits.some(sha => !/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/i.test(sha))) {
      feedback.textContent = (globalThis.HubI18n?.t?.("app.5d08d0030495") ?? 'Укажите от 1 до 20 полных SHA: 40 или 64 шестнадцатеричных символа каждый.');
      form.elements.commits.focus(); return;
    }
    if (!reason || [...reason].length > 1200) {
      feedback.textContent = (globalThis.HubI18n?.t?.("app.8083fe90255f") ?? 'Укажите причину согласования (от 1 до 1200 символов).');
      form.elements.reason.focus(); return;
    }
    if (activeProject !== project) { feedback.textContent = (globalThis.HubI18n?.t?.("app.ee7c2271562d") ?? 'Проект изменён. Закройте окно и откройте его в нужном проекте.'); return; }
    pending = true; checkpointRetries.add(key);
    submit.disabled = close.disabled = form.elements.commits.disabled = form.elements.reason.disabled = true;
    try {
      const response = await fetch('/api/v1/checkpoints/retry?' + new URLSearchParams({project}), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task,...(stage ? {stage} : {}),expected,commits,reason})});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || (globalThis.HubI18n?.t?.("app.74c071688440") ?? 'Не удалось согласовать коммиты'));
      if (activeProject === project) { state = result; render(); }
      dialog.close();
    } catch (error) { feedback.textContent = (globalThis.HubI18n?.error?.(error) ?? error.message); }
    finally {
      pending = false; checkpointRetries.delete(key);
      submit.disabled = close.disabled = form.elements.commits.disabled = form.elements.reason.disabled = false;
      if (activeProject === project) render();
    }
  };
  dialog.showModal();
}
document.addEventListener("click", async event => {
  const batch = event.target.closest('[data-checkpoint-batch]');
  if (batch) { openCheckpointBatch(batch.dataset.checkpointBatch, batch.dataset.checkpointStage); return; }
  const reconcile = event.target.closest('[data-checkpoint-reconcile]');
  if (reconcile) { openCheckpointReconciliation(reconcile.dataset.checkpointReconcile, reconcile.dataset.checkpointStage); return; }
  const button = event.target.closest('[data-checkpoint-retry]');
  if (!button) return;
  const project = activeProject, task = button.dataset.checkpointRetry, stage = button.dataset.checkpointStage;
  const key = JSON.stringify([project,task,stage || undefined]);
  if (checkpointRetries.has(key)) return;
  const expected = state.revision;
  checkpointRetries.add(key); button.disabled = true;
  try {
    const response = await fetch('/api/v1/checkpoints/retry?' + new URLSearchParams({project}), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task,...(stage ? {stage} : {}),expected})});
    if (!response.ok) { const data = await response.json(); throw Error(data.error || (globalThis.HubI18n?.t?.("app.83ff1b2cdd88") ?? 'Не удалось повторить commit')); }
    if (activeProject === project) await refresh();
  } catch (error) { if (activeProject === project) showError((globalThis.HubI18n?.error?.(error) ?? error.message)); }
  finally { checkpointRetries.delete(key); if (activeProject === project) render(); }
});
function route() {
  return (location.hash.slice(1) || "overview")
    .split("/")
    .map(decodeURIComponent);
}
function title(eyebrow, heading, description, extra = "") {
  return `<div class="page-head"><div><div class="eyebrow">${escape(eyebrow)}</div><h1>${escape(heading)}</h1>${description ? `<p>${escape(description)}</p>` : ""}</div>${extra}</div>`;
}
function stageStrip(task) {
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.bb4b0f5b3375",{v0:(task.stages.filter((x) => x.status === "done").length),v1:(task.stages.length),v2:(task.stages.map((s) => `<span class="${escape(s.status)}" title="${escape(s.title)}: ${escape(labels[s.status])}"></span>`).join(""))}) : `<div class="stage-strip" aria-label="${task.stages.filter((x) => x.status === "done").length} из ${task.stages.length} этапов завершено">${task.stages.map((s) => `<span class="${escape(s.status)}" title="${escape(s.title)}: ${escape(labels[s.status])}"></span>`).join("")}</div>`);
}
function taskCard(task, {tree = false, expanded = true, hasChildren = false} = {}) {
  const aggregate = task.progressAggregate || {done: task.stages.filter((s) => s.status === "done").length, total: task.stages.length, percent: 0};
  const done = aggregate.done;
  const type = {epic: 'Epic', bug: 'Bug', task: 'Task'}[task.type || 'task'];
  const priority = {blocker: 'Blocker', critical: 'Critical', major: 'Major', minor: 'Minor', trivial: 'Trivial'}[task.priority];
  const descendantPriority = {blocker: 'Blocker', critical: 'Critical', major: 'Major', minor: 'Minor', trivial: 'Trivial'}[task.maxDescendantPriority];
  const descendantBadge = task.type === 'epic' && descendantPriority ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.2d6faffbb6c5",{v0:(escape(task.maxDescendantPriority)),v1:(escape(descendantPriority))}) : `<span class="task-priority descendant ${escape(task.maxDescendantPriority)}" title="Максимальный приоритет незавершённых потомков">Потомки: ${escape(descendantPriority)}</span>`) : '';
  const toggle = tree && hasChildren ? `<button class="icon-button tree-toggle" type="button" data-tree-toggle="${escape(task.id)}" aria-expanded="${expanded}" aria-label="${expanded ? (globalThis.HubI18n?.t?.("app.dfaa7a9e8d3a") ?? 'Свернуть дочерние задачи') : (globalThis.HubI18n?.t?.("app.71062d4f854f") ?? 'Развернуть дочерние задачи')}" title="${expanded ? (globalThis.HubI18n?.t?.("app.dfaa7a9e8d3a") ?? 'Свернуть дочерние задачи') : (globalThis.HubI18n?.t?.("app.71062d4f854f") ?? 'Развернуть дочерние задачи')}">${uiIcon('chevron')}</button>` : '';
  const treeClass = tree ? ` tree-card${hasChildren ? ' expandable' : ''}` : '';
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.8c88e727623c",{v0:(treeClass),v1:(toggle),v2:(taskLink(task)),v3:(escape(task.title)),v4:(escape(type)),v5:(priority ? `<span class="task-priority ${escape(task.priority)}">${escape(priority)}</span>` : ''),v6:(descendantBadge),v7:(task.children?.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.8309546a5f0d",{v0:(task.children.length)}) : `<span class="task-type">${task.children.length} дочерн.</span>`) : ''),v8:(taskStatus(task)),v9:(copyControls(task)),v10:(escape(task.summary)),v11:(stageStrip(task)),v12:(done),v13:(aggregate.total),v14:(aggregate.percent),v15:(date(task.createdAt)),v16:(escape(task.createdAt || '')),v17:(compactDate(task.createdAt)),v18:(date(task.updatedAt)),v19:(escape(task.updatedAt || '')),v20:(compactDate(task.updatedAt)),v21:(estimate(task, true))}) : `<article class="task-card panel${treeClass}">${toggle}<div class="task-card-titlebar"><div class="task-card-heading"><a href="${taskLink(task)}"><h3>${escape(task.title)}</h3></a></div><div class="task-card-badges"><div class="task-inline-meta"><span class="task-type">${escape(type)}</span>${priority ? `<span class="task-priority ${escape(task.priority)}">${escape(priority)}</span>` : ''}${descendantBadge}${task.children?.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.8309546a5f0d",{v0:(task.children.length)}) : `<span class="task-type">${task.children.length} дочерн.</span>`) : ''}</div>${taskStatus(task)}</div><div class="task-card-actions">${copyControls(task)}</div></div><div class="task-card-body"><p>${escape(task.summary)}</p>${stageStrip(task)}<div class="task-card-progress-row"><div class="task-meta task-progress-metric"><span>${done} из ${aggregate.total} элементов завершено · ${aggregate.percent}%</span><span class="card-dates"><time title="Создана: ${date(task.createdAt)}" datetime="${escape(task.createdAt || '')}">Созд. ${compactDate(task.createdAt)}</time><time title="Изменена: ${date(task.updatedAt)}" datetime="${escape(task.updatedAt || '')}">Изм. ${compactDate(task.updatedAt)}</time></span></div>${estimate(task, true)}</div></div></article>`);
}
function primaryControl(task) {
  const selected = state?.mainTask?.task === task.id;
  const disabled = ['done', 'cancelled'].includes(task.status);
  return `<button class="icon-button primary-task-toggle ${selected ? 'selected' : ''}" data-primary-task="${escape(task.id)}" aria-label="${selected ? (globalThis.HubI18n?.t?.("app.271f8d3a3d4e") ?? 'Основная задача') : (globalThis.HubI18n?.t?.("app.7f40a27567e9") ?? 'Сделать основной задачей')}" title="${selected ? (globalThis.HubI18n?.t?.("app.271f8d3a3d4e") ?? 'Основная задача') : (globalThis.HubI18n?.t?.("app.7f40a27567e9") ?? 'Сделать основной задачей')}" ${disabled ? 'disabled' : ''}>${uiIcon('star')}</button>`;
}
function copyControls(task, stage, includePrimary = true) {
  const url = new URL(taskLink(task, stage?.id), location.href).href;
  const ref = `${task.title}${stage ? ' / ' + stage.title : ''}\ntask: ${task.id}${stage ? ' · stage: ' + stage.id : ''}\n${url}`;
  const id = stage ? task.id + '/' + stage.id : task.id;
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.f775d86e1ac7",{v0:(!stage && includePrimary ? primaryControl(task) : ''),v1:(escape(ref)),v2:(uiIcon('link')),v3:(escape(ref)),v4:(escape(url)),v5:(escape(id))}) : `<div class="copy-controls">${!stage && includePrimary ? primaryControl(task) : ''}<div class="copy-menu"><button class="icon-button copy-trigger" type="button" data-copy-default="${escape(ref)}" aria-haspopup="menu" aria-expanded="false" aria-label="Скопировать данные" title="Скопировать данные">${uiIcon('link')}</button><div class="copy-menu-options" role="menu"><button type="button" data-copy="${escape(ref)}" role="menuitem">Для чата</button><button type="button" data-copy="${escape(url)}" role="menuitem">Ссылку</button><button type="button" data-copy="${escape(id)}" role="menuitem">ID</button></div></div></div>`);
}
function codexSessionLink(resource, title) {
  return window.HubNativeChats?.link(resource, title) || `<strong class="session-title">${escape(title)}</strong>`;
}
document.addEventListener('click', async event => {
  const button=event.target.closest('[data-copy], [data-copy-default]'); if(!button)return;
  event.preventDefault(); event.stopPropagation();
  let toast=document.getElementById('copy-feedback');
  if(!toast){toast=document.createElement('div');toast.id='copy-feedback';toast.setAttribute('role','status');document.body.append(toast);}
  try { await navigator.clipboard.writeText(button.dataset.copy ?? button.dataset.copyDefault); toast.textContent=(globalThis.HubI18n?.t?.("app.d2d08c715ee6") ?? 'Скопировано'); }
  catch { toast.textContent=(globalThis.HubI18n?.t?.("app.e4f836fc9377") ?? 'Не удалось скопировать. Разрешите доступ к буферу обмена в браузере и повторите.'); }
  toast.hidden=false; clearTimeout(toast.hideTimer); toast.hideTimer=setTimeout(()=>toast.hidden=true,4000);
  if (button.dataset.copyDefault) {
    const menu = button.closest('.copy-menu');
    const open = menu?.classList.toggle('open') || false;
    button.setAttribute('aria-expanded', String(open));
  } else {
    const menu = button.closest('.copy-menu');
    if (menu) {
      menu.classList.remove('open');
      menu.querySelector('.copy-trigger')?.setAttribute('aria-expanded', 'false');
    }
  }
});
document.addEventListener('click', async (event) => {
  const detailRetry = event.target.closest('[data-task-detail-retry]');
  if (detailRetry) {
    event.preventDefault();
    taskDetailLoader.retry(activeProject, detailRetry.dataset.taskDetailRetry, state?.revision);
    render({preserveScroll: true});
    return;
  }
  if (!event.target.closest('.copy-menu')) {
    document.querySelectorAll('.copy-menu.open').forEach(menu => {
      menu.classList.remove('open');
      menu.querySelector('.copy-trigger')?.setAttribute('aria-expanded', 'false');
    });
  }
  const pickerTrigger = event.target.closest('[data-parent-picker-trigger]');
  if (pickerTrigger) {
    const picker = pickerTrigger.closest('[data-parent-picker]');
    const wasOpen = picker.classList.contains('open');
    document.querySelectorAll('.parent-picker.open').forEach(closeParentPicker);
    if (!wasOpen) {
      picker.classList.add('open');
      picker.querySelector('.parent-picker-popover').removeAttribute('hidden');
      pickerTrigger.setAttribute('aria-expanded', 'true');
      picker.querySelector('[data-parent-search]')?.focus();
    }
    return;
  }
  const parentOption = event.target.closest('[data-parent-option]');
  if (parentOption) {
    const picker = parentOption.closest('[data-parent-picker]');
    const taskId = picker.dataset.taskId;
    const buttons = [...picker.querySelectorAll('[data-parent-option]')];
    buttons.forEach(button => { button.disabled = true; });
    try {
      const response = await fetch(projectApi('/api/v1/tasks/update'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task:taskId, expected:state.revision, patch:{parentTask:parentOption.dataset.parentValue || null}})});
      if (!response.ok) throw new Error((await response.json()).error || (globalThis.HubI18n?.t?.("app.dbb0fe6eb358") ?? 'Не удалось изменить родительскую задачу'));
      closeParentPicker(picker);
      await refresh();
    } catch (error) {
      showError((globalThis.HubI18n?.error?.(error) ?? error.message));
      buttons.forEach(button => { button.disabled = false; });
    }
    return;
  }
  if (!event.target.closest('[data-parent-picker]')) {
    document.querySelectorAll('.parent-picker.open').forEach(closeParentPicker);
  }
  const treeToggle = event.target.closest('[data-tree-toggle]');
  if (treeToggle) {
    event.preventDefault();
    event.stopPropagation();
    const id = treeToggle.dataset.treeToggle;
    const expanded = treeToggle.getAttribute('aria-expanded') === 'true';
    if (expanded) treeExpanded.delete(id); else treeExpanded.add(id);
    window.saveTaskTreeState?.();
    replacePreservingScroll('#task-results', taskResults());
    return;
  }
  const reopen = event.target.closest('[data-task-reopen]');
  if (reopen) {
    event.preventDefault();
    reopen.disabled = true;
    try {
      const response = await fetch(projectApi('/api/v1/tasks/reopen'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task:reopen.dataset.taskReopen, expected:state.revision})});
      if (!response.ok) throw new Error((await response.json()).error || (globalThis.HubI18n?.t?.("app.f31562287bf9") ?? 'Не удалось переоткрыть задачу'));
      await refresh();
    } catch (error) { showError((globalThis.HubI18n?.error?.(error) ?? error.message)); reopen.disabled = false; }
    return;
  }
  const close = event.target.closest('[data-task-close]');
  if (close) {
    event.preventDefault();
    if (close.dataset.closeMode === 'manual' && !window.confirm((globalThis.HubI18n?.t?.("app.fecc63060e30") ?? 'Закрыть задачу с возможными незавершёнными дочерними задачами?'))) return;
    close.disabled = true;
    try {
      const response = await fetch(projectApi('/api/v1/tasks/close'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task:close.dataset.taskClose, expected:state.revision, mode:close.dataset.closeMode})});
      if (!response.ok) throw new Error((await response.json()).error || (globalThis.HubI18n?.t?.("app.3895902b27df") ?? 'Не удалось закрыть задачу'));
      await refresh();
    } catch (error) { showError((globalThis.HubI18n?.error?.(error) ?? error.message)); close.disabled = false; }
    return;
  }
  const button = event.target.closest('[data-primary-task]');
  if (!button || button.disabled) return;
  event.preventDefault();
  event.stopPropagation();
  button.disabled = true;
  try {
    const response = await fetch(projectApi('/api/v1/tasks/primary'), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task: button.dataset.primaryTask, expected: state.revision}),
    });
    if (!response.ok) throw new Error((await response.json()).error || (globalThis.HubI18n?.t?.("app.df9579c56e2f") ?? 'Не удалось выбрать основную задачу'));
    await refresh();
  } catch (error) {
    showError((globalThis.HubI18n?.error?.(error) ?? error.message));
    button.disabled = false;
  }
});
function eventTone(event) {
  return event.kind === "task.reopened"
    ? "active"
    : event.kind.endsWith("failed")
    ? "failed"
    : event.kind.endsWith("passed")
      ? "passed"
      : event.kind.endsWith("completed")
        ? "done"
        : event.kind.endsWith("started")
          ? "active"
          : "";
}
function eventTitle(event) {
  if (!event) return '';
  if (event.kind === 'task.updated' && event.title === 'Задача закрыта' &&
      event.patch?.status === 'done' && typeof event.patch.closedManually === 'boolean') {
    return globalThis.HubI18n?.t?.('app.taskClosed') ?? 'Задача закрыта';
  }
  const generatedChanges = {
    'task.reopened': 'Задача переоткрыта', 'task.status_changed': 'Статус задачи изменён',
    'task.type_changed': 'Тип задачи изменён', 'task.priority_changed': 'Приоритет задачи изменён',
    'task.parent_changed': 'Родитель задачи изменён', 'task.linked': 'Связь задач добавлена',
    'task.unlinked': 'Связь задач удалена',
  };
  if ((event.change?.sourceEventId && generatedChanges[event.kind] === event.title) ||
      (event.kind === 'task.updated' && event.title === 'Задача обновлена' && event.id?.startsWith('hub-update-'))) {
    return kindLabels[event.kind] || event.title;
  }
  return event.title;
}
function updateAnnouncement(snapshot = state) {
  const announcement = $('#announcement');
  if (announcement) announcement.textContent = eventTitle(snapshot?.events?.[0]) ||
    (globalThis.HubI18n?.t?.('app.32dbbc1cc1fc') ?? 'Проект загружен');
}
function eventView(event, compact = false) {
  const task = state.tasks.find((t) => t.id === event.taskId);
  const git = event.git && event.git.sha ? (() => {
    const sha = escape(event.git.shortSha || event.git.sha);
    const ref = event.git.pushed === true && event.git.githubUrl ? `<a href="${escape(event.git.githubUrl)}" target="_blank" rel="noopener">${sha}</a>` : (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.911177018aa6",{v0:(sha)}) : `<code title="Commit ещё не отправлен в upstream">${sha}</code>`);
    return `<div class="event-git">${ref}<span>${event.git.pushed === true ? (globalThis.HubI18n?.t?.("app.1ccc694277d6") ?? 'отправлен') : event.git.pushed === false ? (globalThis.HubI18n?.t?.("app.a5560a64af44") ?? 'локальный · не отправлен') : (globalThis.HubI18n?.t?.("app.00e1cf7a6801") ?? 'статус push неизвестен')}</span></div>`;
  })() : '';
  return `<article class="event"><i class="event-marker ${eventTone(event)}" aria-hidden="true"></i><div><div class="event-meta"><time datetime="${escape(event.at)}" title="${escape(event.at)}">${date(event.at)}</time><span>${escape(kindLabels[event.kind] || event.kind)}</span>${task ? `<a href="${taskLink(task, event.stageId)}">${escape(compact ? task.id : task.title)}</a>` : ""}</div><h3>${escape(eventTitle(event))}</h3>${event.detail ? `<p>${escape(event.detail)}</p>` : ""}${git}${evidence(event.evidence)}</div></article>`;
}
function estimate(task, compact = false, parentTask = null) {
  const e = task?.estimate || {};
  const validRange = (low, high, max = Infinity) => Number.isFinite(low) && Number.isFinite(high) && low >= 0 && high >= low && high <= max;
  const percent = validRange(e.percentLow, e.percentHigh, 100);
  const hours = validRange(e.hoursLow, e.hoursHigh);
  const updated = typeof e.updatedAt === 'string' && Number.isFinite(Date.parse(e.updatedAt)) ? e.updatedAt : null;
  const due = task?.progress?.reviewDue === true;
  const known = percent || hours;
  const reasons = {missing: (globalThis.HubI18n?.t?.("app.4cd44f4b1b09") ?? 'Оценка не задана'), legacy: (globalThis.HubI18n?.t?.("app.01559bfe41c1") ?? 'Дата оценки неизвестна'), milestone: (globalThis.HubI18n?.t?.("app.c1cda6c9dfbc") ?? 'После изменения этапа'), interval: (globalThis.HubI18n?.t?.("app.0e21dc5dcf76") ?? 'После периода работы')};
  const freshness = !percent && !hours ? (globalThis.HubI18n?.t?.("app.4cd44f4b1b09") ?? 'Оценка не задана') : due ? (globalThis.HubI18n?.t?.("app.bffe6fd0018b") ?? 'Оценка требует пересмотра') : updated ? (globalThis.HubI18n?.t?.("app.3e996c89b008") ?? 'Оценка обновлена') : (globalThis.HubI18n?.t?.("app.01559bfe41c1") ?? 'Дата оценки неизвестна');
  const reason = due ? reasons[task?.progress?.reason] : '';
  if (compact) {
    const detail = [freshness, updated ? date(updated) : '', reason, e.note].filter(Boolean).join(' · ');
    return `<span class="task-estimate compact ${known ? '' : 'unknown'} ${due ? 'review-due' : ''}" title="${escape(detail)}" aria-label="${escape((globalThis.HubI18n?.t?.("app.85f3a836ee37") ?? 'Готовность: ')+(percent ? e.percentLow+'–'+e.percentHigh+'%' : (globalThis.HubI18n?.t?.("app.769f4277e4c8") ?? 'не оценена'))+(globalThis.HubI18n?.t?.("app.f6263781b038") ?? '; осталось времени агента: ')+(hours ? e.hoursLow+'–'+e.hoursHigh+(globalThis.HubI18n?.t?.("app.602df55a0af1") ?? ' часов') : (globalThis.HubI18n?.t?.("app.bafef38a3b64") ?? 'не оценено'))+'. '+detail)}"><span>${percent ? `<strong>${escape(e.percentLow)}–${escape(e.percentHigh)}<small> %</small></strong>` : (globalThis.HubI18n?.t?.("app.d6fc97062e95") ?? 'Готовность —')}</span><span class="estimate-separator" aria-hidden="true">·</span><span>${hours ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.2b90608b8714",{v0:(escape(e.hoursLow)),v1:(escape(e.hoursHigh))}) : `<strong>${escape(e.hoursLow)}–${escape(e.hoursHigh)} ч</strong> осталось`) : (globalThis.HubI18n?.t?.("app.9eb3d9887d5b") ?? 'Время —')}</span>${due ? '<span class="estimate-review-dot" aria-hidden="true">●</span>' : ''}</span>`;
  }
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.cbc7a8f88a5e",{v0:(compact ? 'compact' : ''),v1:(percent ? `<strong class="estimate-value">${escape(e.percentLow)}–${escape(e.percentHigh)}<small> %</small></strong>` : (globalThis.HubI18n?.t?.("app.7f3ad0d70ecc") ?? '<span class="caption">Оценка не задана</span>')),v2:(hours ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.00e976f55b2f",{v0:(escape(e.hoursLow)),v1:(escape(e.hoursHigh))}) : `<strong class="estimate-hours">${escape(e.hoursLow)}–${escape(e.hoursHigh)} ч</strong>`) : (globalThis.HubI18n?.t?.("app.7f3ad0d70ecc") ?? '<span class="caption">Оценка не задана</span>')),v3:(!compact && percent ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.b552faeabe19",{v0:(e.percentLow),v1:(e.percentHigh),v2:(e.percentLow),v3:(e.percentLow),v4:(e.percentHigh - e.percentLow)}) : `<div class="range-bar" aria-label="Готовность: ${e.percentLow}–${e.percentHigh} процентов"><div class="minimum" style="width:${e.percentLow}%"></div><div class="uncertain" style="left:${e.percentLow}%;width:${e.percentHigh - e.percentLow}%"></div></div>`) : ''),v4:(due ? 'review-due' : ''),v5:(escape(freshness)),v6:(updated ? ` · <time datetime="${escape(updated)}">${date(updated)}</time>` : ''),v7:(reason && reason !== freshness ? ` · ${escape(reason)}` : ''),v8:(!compact && (e.confidence || e.note) ? `<p class="estimate-note">${[e.confidence, e.note].filter(Boolean).map(escape).join(' · ')}</p>` : ''),v9:(parentTask ? 'stage':'task'),v10:(escape(parentTask || task.id)),v11:(escape(parentTask ? task.id : ''))}) : `<div class="task-estimate ${compact ? 'compact' : ''}"><div class="estimate-metrics"><div><span class="estimate-label">Готовность</span>${percent ? `<strong class="estimate-value">${escape(e.percentLow)}–${escape(e.percentHigh)}<small> %</small></strong>` : (globalThis.HubI18n?.t?.("app.7f3ad0d70ecc") ?? '<span class="caption">Оценка не задана</span>')}</div><div><span class="estimate-label">Осталось времени агента</span>${hours ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.00e976f55b2f",{v0:(escape(e.hoursLow)),v1:(escape(e.hoursHigh))}) : `<strong class="estimate-hours">${escape(e.hoursLow)}–${escape(e.hoursHigh)} ч</strong>`) : (globalThis.HubI18n?.t?.("app.7f3ad0d70ecc") ?? '<span class="caption">Оценка не задана</span>')}</div></div>${!compact && percent ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.b552faeabe19",{v0:(e.percentLow),v1:(e.percentHigh),v2:(e.percentLow),v3:(e.percentLow),v4:(e.percentHigh - e.percentLow)}) : `<div class="range-bar" aria-label="Готовность: ${e.percentLow}–${e.percentHigh} процентов"><div class="minimum" style="width:${e.percentLow}%"></div><div class="uncertain" style="left:${e.percentLow}%;width:${e.percentHigh - e.percentLow}%"></div></div>`) : ''}<div class="estimate-freshness ${due ? 'review-due' : ''}">${escape(freshness)}${updated ? ` · <time datetime="${escape(updated)}">${date(updated)}</time>` : ''}${reason && reason !== freshness ? ` · ${escape(reason)}` : ''}</div>${!compact && (e.confidence || e.note) ? `<p class="estimate-note">${[e.confidence, e.note].filter(Boolean).map(escape).join(' · ')}</p>` : ''}</div>`);
}
function currentWorkSummary(tasks) {
  const working = tasks.filter(t => !['done', 'cancelled'].includes(t.status) && t.currentWorks?.length)
    .sort((a, b) => (b.currentWorks[0].updatedAt || '').localeCompare(a.currentWorks[0].updatedAt || ''));
  const sessions = new Set(working.flatMap(t => t.currentWorks.map(w => w.session)));
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.e271550457e6",{v0:(working.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.c74fc1c0104d",{v0:(working.length),v1:(sessions.size)}) : `<span class="activity-note">Задач: ${working.length} · чатов: ${sessions.size}</span>`) : ''),v1:(working.length ? `<div class="current-work-list" data-scroll-key="overview-current-work">${working.map(task => {
    const groups = new Map();
    for (const work of task.currentWorks) {
      const key = (work.stageIds || [work.stageId]).filter(Boolean).join(';');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(work);
    }
    return `<section class="current-work-task"><h3><a href="${taskLink(task)}">${escape(task.title)}</a></h3><ul>${[...groups].map(([stageId, works]) => {
      const stages = stageId.split(';').map(id=>task.stages?.find(s=>s.id===id)).filter(Boolean);
      const phases={planning:(globalThis.HubI18n?.t?.("app.0578705e28be") ?? 'Планирование'),research:(globalThis.HubI18n?.t?.("app.04c325ed529c") ?? 'Исследование'),implementation:(globalThis.HubI18n?.t?.("app.7a1b4177b276") ?? 'Реализация'),review:(globalThis.HubI18n?.t?.("app.bd3a5be11e2a") ?? 'Обзор'),testing:(globalThis.HubI18n?.t?.("app.e56a412d1285") ?? 'Проверка')};
      const descriptions = [...new Set(works.map(w => [phases[w.phase],w.title].filter(Boolean).join(': ')).filter(Boolean))].join(' · ');
      return `<li>${stages.length ? stages.map(stage=>`<a class="current-work-stage" href="${taskLink(task, stage.id)}">${escape(stage.title)}</a>`).join(' · ') : (globalThis.HubI18n?.t?.("app.b3690325224c") ?? '<span class="current-work-stage">Работа по задаче</span>')}<span class="current-work-description" title="${escape(descriptions)}">${escape(descriptions)}</span></li>`;
    }).join('')}</ul></section>`;
  }).join('')}</div>` : (globalThis.HubI18n?.t?.("app.2403bb98af36") ?? '<p class="caption">Нет подтверждённой активной работы чатов.</p>'))}) : `<section class="panel now-panel"><div class="label"><i class="dot"></i>ТЕКУЩАЯ РАБОТА${working.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.c74fc1c0104d",{v0:(working.length),v1:(sessions.size)}) : `<span class="activity-note">Задач: ${working.length} · чатов: ${sessions.size}</span>`) : ''}</div>${working.length ? `<div class="current-work-list" data-scroll-key="overview-current-work">${working.map(task => {
    const groups = new Map();
    for (const work of task.currentWorks) {
      const key = (work.stageIds || [work.stageId]).filter(Boolean).join(';');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(work);
    }
    return `<section class="current-work-task"><h3><a href="${taskLink(task)}">${escape(task.title)}</a></h3><ul>${[...groups].map(([stageId, works]) => {
      const stages = stageId.split(';').map(id=>task.stages?.find(s=>s.id===id)).filter(Boolean);
      const phases={planning:(globalThis.HubI18n?.t?.("app.0578705e28be") ?? 'Планирование'),research:(globalThis.HubI18n?.t?.("app.04c325ed529c") ?? 'Исследование'),implementation:(globalThis.HubI18n?.t?.("app.7a1b4177b276") ?? 'Реализация'),review:(globalThis.HubI18n?.t?.("app.bd3a5be11e2a") ?? 'Обзор'),testing:(globalThis.HubI18n?.t?.("app.e56a412d1285") ?? 'Проверка')};
      const descriptions = [...new Set(works.map(w => [phases[w.phase],w.title].filter(Boolean).join(': ')).filter(Boolean))].join(' · ');
      return `<li>${stages.length ? stages.map(stage=>`<a class="current-work-stage" href="${taskLink(task, stage.id)}">${escape(stage.title)}</a>`).join(' · ') : (globalThis.HubI18n?.t?.("app.b3690325224c") ?? '<span class="current-work-stage">Работа по задаче</span>')}<span class="current-work-description" title="${escape(descriptions)}">${escape(descriptions)}</span></li>`;
    }).join('')}</ul></section>`;
  }).join('')}</div>` : (globalThis.HubI18n?.t?.("app.2403bb98af36") ?? '<p class="caption">Нет подтверждённой активной работы чатов.</p>')}<div class="bottom"><a href="#coordination">Чаты и агенты →</a><span class="activity-note">По состоянию подключённых чатов</span></div></section>`);
}
const priorityRank = {blocker: 5, critical: 4, major: 3, minor: 2, trivial: 1};
const statusRank = {active: 5, blocked: 4, queued: 3, planned: 2, done: 1, cancelled: 0};
function taskProgress(task) {
  const stages = task.stages || [];
  return stages.length ? stages.filter(stage => stage.status === 'done').length / stages.length : 0;
}
function taskCreated(task) { return Date.parse(task.createdAt || task.updatedAt || state.project.baselineAt || 0) || 0; }
function taskUpdated(task) { return Date.parse(task.updatedAt || task.createdAt || state.project.baselineAt || 0) || 0; }
function compareTasks(a, b, sort = taskSort) {
  let result = 0;
  if (sort === 'priority') result = (priorityRank[b.priority] || 0) - (priorityRank[a.priority] || 0);
  else if (sort === 'updated') result = taskUpdated(b) - taskUpdated(a);
  else if (sort === 'created-oldest') result = taskCreated(a) - taskCreated(b);
  else if (sort === 'status') result = (statusRank[b.status] || 0) - (statusRank[a.status] || 0);
  else if (sort === 'progress') result = taskProgress(a) - taskProgress(b);
  else if (sort === 'title') result = a.title.localeCompare(b.title, 'ru');
  else result = taskCreated(b) - taskCreated(a);
  if (result) return result;
  result = taskUpdated(b) - taskUpdated(a);
  return result || a.id.localeCompare(b.id);
}
function sortedTasks(tasks) { return [...tasks].sort(compareTasks); }
function overview() {
  const taskSettings = projectSettings().tasks;
  const overviewTasks = state.tasks.filter(t => !['done', 'cancelled'].includes(t.status)
    && (taskSettings.showEpicsOnOverview || t.type !== 'epic')
    && (taskSettings.showUpcomingOnOverview || !['planned', 'queued'].includes(t.status)));
  const activeTasks = state.tasks.filter((t) => t.status === 'active');
  const selectedTask = state.mainTask?.reason !== 'none' && state.mainTask?.task ? state.tasks.find((t) => t.id === state.mainTask.task) : null;
  const mainTask = selectedTask || (activeTasks.length === 1 ? activeTasks[0] : null);
  const mainReason = {explicit: (globalThis.HubI18n?.t?.("app.114112ae6abc") ?? 'Выбрана явно'), 'largest-active': (globalThis.HubI18n?.t?.("app.edde0234660c") ?? 'Самая объёмная из активных задач'), 'latest-active': (globalThis.HubI18n?.t?.("app.366564006f8e") ?? 'Последняя обновлённая активная задача')}[state.mainTask?.reason] || (mainTask ? (globalThis.HubI18n?.t?.("app.51365a4d6fe9") ?? 'Единственная активная задача') : '');
  const events = state.events.slice(0, 5);
 return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.46b79febee8c",{v0:(title((globalThis.HubI18n?.t?.("app.2590606ceb11") ?? "Рабочее пространство"), state.project.name, (globalThis.HubI18n?.t?.("app.c0f072552cf6") ?? "Разработка, решения и знания о проекте — в одном месте."), (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.6c2c55068dc1",{v0:(state.tasks.filter((t) => t.status === "active").length)}) : `<span class="tag">В работе: ${state.tasks.filter((t) => t.status === "active").length}</span>`))),v1:(overviewTasks.length),v2:(window.ChatActionsUI?.projectControl(state,activeProject) || ""),v3:(taskSort === 'created' ? 'selected' : ''),v4:(taskSort === 'created-oldest' ? 'selected' : ''),v5:(taskSort === 'priority' ? 'selected' : ''),v6:(taskSort === 'updated' ? 'selected' : ''),v7:(taskSort === 'status' ? 'selected' : ''),v8:(taskSort === 'progress' ? 'selected' : ''),v9:(taskSort === 'title' ? 'selected' : ''),v10:(sortedTasks(overviewTasks).map(taskCard)
     .join("") || (globalThis.HubI18n?.t?.("app.eaab2ce5041f") ?? '<div class="empty">Нет текущих задач для отображения</div>')),v11:(mainTask ? `<a href="${taskLink(mainTask)}">${escape(mainTask.title)}</a>` : (globalThis.HubI18n?.t?.("app.f6cf7d01e1ae") ?? 'Основная задача не выбрана')),v12:(mainTask ? `<div class="caption main-task-reason">${escape(mainReason)}</div>${estimate(mainTask)}` : (globalThis.HubI18n?.t?.("app.f883aa0850f0") ?? '<p class="caption">Нет выбранной основной задачи.</p>')),v13:(currentWorkSummary(state.tasks)),v14:(events.map((e) => eventView(e, true)).join("") || (globalThis.HubI18n?.t?.("app.ffa198e57505") ?? '<div class="empty">История начинается с первого события</div>'))}) : `${title((globalThis.HubI18n?.t?.("app.2590606ceb11") ?? "Рабочее пространство"), state.project.name, (globalThis.HubI18n?.t?.("app.c0f072552cf6") ?? "Разработка, решения и знания о проекте — в одном месте."), (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.6c2c55068dc1",{v0:(state.tasks.filter((t) => t.status === "active").length)}) : `<span class="tag">В работе: ${state.tasks.filter((t) => t.status === "active").length}</span>`))}
 <div class="overview-grid"><section><div class="section-head"><div><h2>Текущие задачи<span class="count">${overviewTasks.length}</span></h2>${window.ChatActionsUI?.projectControl(state,activeProject) || ""}<label class="sort-control">Сортировка <select id="overview-task-sort" aria-label="Сортировка задач"><option value="created" ${taskSort === 'created' ? 'selected' : ''}>По дате создания · новые</option><option value="created-oldest" ${taskSort === 'created-oldest' ? 'selected' : ''}>По дате создания · старые</option><option value="priority" ${taskSort === 'priority' ? 'selected' : ''}>По приоритету</option><option value="updated" ${taskSort === 'updated' ? 'selected' : ''}>Недавно обновлённые</option><option value="status" ${taskSort === 'status' ? 'selected' : ''}>По статусу</option><option value="progress" ${taskSort === 'progress' ? 'selected' : ''}>Сначала незавершённые</option><option value="title" ${taskSort === 'title' ? 'selected' : ''}>По названию</option></select></label></div><a href="#tasks">Все задачи →</a></div>${sortedTasks(overviewTasks).map(taskCard)
     .join("") || (globalThis.HubI18n?.t?.("app.eaab2ce5041f") ?? '<div class="empty">Нет текущих задач для отображения</div>')}<div class="notice">Показан подтверждённый срез текущей работы. История портала накапливается с его запуска; более ранние документы будут импортированы отдельно.</div></section><div class="overview-sidebar">
 <section class="panel plan-summary"><div class="eyebrow">Основная задача</div><h3>${mainTask ? `<a href="${taskLink(mainTask)}">${escape(mainTask.title)}</a>` : (globalThis.HubI18n?.t?.("app.f6cf7d01e1ae") ?? 'Основная задача не выбрана')}</h3>${mainTask ? `<div class="caption main-task-reason">${escape(mainReason)}</div>${estimate(mainTask)}` : (globalThis.HubI18n?.t?.("app.f883aa0850f0") ?? '<p class="caption">Нет выбранной основной задачи.</p>')}</section>
 ${currentWorkSummary(state.tasks)}
 <section><div class="section-head"><h2>Последние события</h2><a href="#history">Вся история →</a></div><div class="timeline">${events.map((e) => eventView(e, true)).join("") || (globalThis.HubI18n?.t?.("app.ffa198e57505") ?? '<div class="empty">История начинается с первого события</div>')}</div></section></div></div>
 <div class="project-reserve"><div><h3>Архитектура и код</h3><p>Системы, контракты, зависимости и связи классов.</p><a href="#architecture">Структура будущего раздела →</a></div><div><h3>База знаний</h3><p>Руководства, справочник и исторические документы.</p><a href="#docs">Структура документации →</a></div><div><h3>Действия проекта</h3><p>В будущем — запуски, команды и взаимодействие с агентом.</p><a href="#actions">Предусмотренные расширения →</a></div></div>`);
}
function tasksPage() {
  const options = (values, selected) => values.map(([value, label]) => `<option value="${value}" ${selected === value ? 'selected' : ''}>${label}</option>`).join('');
return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.aa18e745349f",{v0:(title((globalThis.HubI18n?.t?.("app.0578705e28be") ?? "Планирование"), (globalThis.HubI18n?.t?.("app.5484cf6c55b2") ?? "Задачи проекта"), "", (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.86e701904b93",{v0:(uiIcon('plus')),v1:(renderTaskColumnMenu()),v2:(uiIcon('reopen'))}) : `<div class="task-list-tools"><button class="icon-button" data-create-task title="Создать задачу" aria-label="Создать задачу">${uiIcon('plus')}</button>${renderTaskColumnMenu()}<button class="icon-button" data-settings-action="personal-reset" title="Вернуть настройки проекта" aria-label="Вернуть настройки проекта">${uiIcon('reopen')}</button></div>`))),v1:(escape(taskSearch)),v2:(options([['project',(globalThis.HubI18n?.t?.("app.d367c360b8c5") ?? 'Настройки проекта')],['all',(globalThis.HubI18n?.t?.("app.2a013601f9a8") ?? 'Все статусы')],...['active','planned','queued','blocked','done','cancelled'].map(id => [id, labels[id]])], taskFilter)),v3:(options([['all',(globalThis.HubI18n?.t?.("app.19161353d3bf") ?? 'Все типы')],['task','Task'],['bug','Bug'],['epic','Epic']], taskTypeFilter)),v4:(options([['all',(globalThis.HubI18n?.t?.("app.c1c552a44eb7") ?? 'Все приоритеты')],['blocker','Blocker'],['critical','Critical'],['major','Major'],['minor','Minor'],['trivial','Trivial']], taskPriorityFilter)),v5:(options([['created',(globalThis.HubI18n?.t?.("app.10d04c1c3b04") ?? 'По дате создания · новые')],['created-oldest',(globalThis.HubI18n?.t?.("app.461c83c1bd68") ?? 'По дате создания · старые')],['updated',(globalThis.HubI18n?.t?.("app.28c18c8dfd24") ?? 'Недавно обновлённые')],['priority',(globalThis.HubI18n?.t?.("app.8741673244ca") ?? 'По приоритету')],['status',(globalThis.HubI18n?.t?.("app.682ade53d14c") ?? 'По статусу')],['progress',(globalThis.HubI18n?.t?.("app.f2932d892ad9") ?? 'Сначала незавершённые')],['title',(globalThis.HubI18n?.t?.("app.ca87c2180268") ?? 'По названию')]], taskListSort)),v6:(taskResults())}) : `${title((globalThis.HubI18n?.t?.("app.0578705e28be") ?? "Планирование"), (globalThis.HubI18n?.t?.("app.5484cf6c55b2") ?? "Задачи проекта"), "", (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.86e701904b93",{v0:(uiIcon('plus')),v1:(renderTaskColumnMenu()),v2:(uiIcon('reopen'))}) : `<div class="task-list-tools"><button class="icon-button" data-create-task title="Создать задачу" aria-label="Создать задачу">${uiIcon('plus')}</button>${renderTaskColumnMenu()}<button class="icon-button" data-settings-action="personal-reset" title="Вернуть настройки проекта" aria-label="Вернуть настройки проекта">${uiIcon('reopen')}</button></div>`))}<div class="task-filter-bar"><input id="task-search" aria-label="Поиск задач" placeholder="Найти задачу…" value="${escape(taskSearch)}"><label>Статус<select id="task-status-filter" aria-label="Фильтр по статусу">${options([['project',(globalThis.HubI18n?.t?.("app.d367c360b8c5") ?? 'Настройки проекта')],['all',(globalThis.HubI18n?.t?.("app.2a013601f9a8") ?? 'Все статусы')],...['active','planned','queued','blocked','done','cancelled'].map(id => [id, labels[id]])], taskFilter)}</select></label><label>Тип<select id="task-type-filter" aria-label="Фильтр по типу">${options([['all',(globalThis.HubI18n?.t?.("app.19161353d3bf") ?? 'Все типы')],['task','Task'],['bug','Bug'],['epic','Epic']], taskTypeFilter)}</select></label><label>Приоритет<select id="task-priority-filter" aria-label="Фильтр по приоритету">${options([['all',(globalThis.HubI18n?.t?.("app.c1c552a44eb7") ?? 'Все приоритеты')],['blocker','Blocker'],['critical','Critical'],['major','Major'],['minor','Minor'],['trivial','Trivial']], taskPriorityFilter)}</select></label><label>Сортировка<select id="task-list-sort" aria-label="Сортировка задач">${options([['created',(globalThis.HubI18n?.t?.("app.10d04c1c3b04") ?? 'По дате создания · новые')],['created-oldest',(globalThis.HubI18n?.t?.("app.461c83c1bd68") ?? 'По дате создания · старые')],['updated',(globalThis.HubI18n?.t?.("app.28c18c8dfd24") ?? 'Недавно обновлённые')],['priority',(globalThis.HubI18n?.t?.("app.8741673244ca") ?? 'По приоритету')],['status',(globalThis.HubI18n?.t?.("app.682ade53d14c") ?? 'По статусу')],['progress',(globalThis.HubI18n?.t?.("app.f2932d892ad9") ?? 'Сначала незавершённые')],['title',(globalThis.HubI18n?.t?.("app.ca87c2180268") ?? 'По названию')]], taskListSort)}</select></label></div><div id="task-results">${taskResults()}</div>`);
}
function taskResults() {
  const terms = taskSearch.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const entries = state.tasks.map(task => {
    const fields = [];
    const add = (label, value, stage) => {
      if (Array.isArray(value)) value.forEach(v => add(label, v, stage));
      else if (typeof value === 'string' && value) fields.push({label, text:value, stage});
    };
    for (const [key,label] of [['id','ID'],['title',(globalThis.HubI18n?.t?.("app.0918b4ba9268") ?? 'Название')],['summary',(globalThis.HubI18n?.t?.("app.b3680f2cba5f") ?? 'Описание')],['scope',(globalThis.HubI18n?.t?.("app.ac6b4059b527") ?? 'Область')],['acceptance',(globalThis.HubI18n?.t?.("app.08c7c879bcb9") ?? 'Критерии')],['deferred',(globalThis.HubI18n?.t?.("app.5c47a3132778") ?? 'Отложено')]]) add(label,task[key]);
    task.stages.forEach(stage => {
      for (const key of ['id','title','summary','done','remaining']) add((globalThis.HubI18n?.t?.("app.5b23ad899154") ?? 'Этап: ')+stage.title,stage[key],stage.id);
    });
    const corpus = task.searchText != null ? String(task.searchText).toLocaleLowerCase() : fields.map(f => f.text).join('\n').toLocaleLowerCase();
    return {task, fields:fields.filter(f => terms.some(t => f.text.toLocaleLowerCase().includes(t))), found:terms.every(t => corpus.includes(t))};
  }).filter(e => e.found && (taskFilter === 'all' || (taskFilter === 'project' ? projectSettings().tasks.showCompleted || !['done', 'cancelled'].includes(e.task.status) : e.task.status === taskFilter)) && (taskTypeFilter === 'all' || (e.task.type || 'task') === taskTypeFilter) && (taskPriorityFilter === 'all' || (e.task.priority || '') === taskPriorityFilter)).sort((a, b) => compareTasks(a.task, b.task, taskListSort));
  const context = field => {
    const index = Math.min(...terms.map(t => field.text.toLocaleLowerCase().indexOf(t)).filter(i => i >= 0));
    const start = Math.max(0,index-45), text = (start?'…':'')+field.text.slice(start,start+180)+(field.text.length>start+180?'…':'');
    return `<li><a href="${taskLink(field.task,field.stage)}">${escape(field.label)}</a>: ${escape(text)}</li>`;
  };
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.0a43343e62ab",{v0:(entries.length)}) : `<p class="caption" role="status">Найдено задач: ${entries.length}. Поиск по ID, описанию, области, критериям и всем этапам плана. Все слова запроса; содержимое вложенных файлов не включено.</p>`) + (entries.length ? taskTree(entries, terms, context) : (globalThis.HubI18n?.t?.("app.437b587555eb") ?? '<div class="empty">Задачи не найдены. Измените запрос или фильтр.</div>'));
}
function taskTree(entries, terms, context) {
  return renderTaskTable(entries, terms, context);
}
function taskSearchCorpus(task) {
  const values = [];
  const add = value => {
    if (Array.isArray(value)) value.forEach(add);
    else if (value && typeof value === 'object') Object.values(value).forEach(add);
    else if (value !== null && value !== undefined) values.push(String(value));
  };
  add([task.id, task.title, task.summary, task.status, labels[task.status], task.type, task.priority, task.parentTask, task.scope, task.acceptance, task.deferred]);
  (task.stages || []).forEach(stage => add([stage.id, stage.title, stage.summary, stage.done, stage.remaining]));
  (task.sources || []).forEach(source => add([source.label, source.path]));
  return values.join(' ').toLocaleLowerCase();
}
function parentPickerOptions(task, query = '') {
  const normalized = query.trim().toLocaleLowerCase();
  const current = task.parentTask || '';
  const candidates = state.tasks
    .filter(candidate => candidate.id !== task.id)
    .filter(candidate => !normalized || taskSearchCorpus(candidate).includes(normalized))
    .sort((a, b) => a.title.localeCompare(b.title, 'ru'));
  const root = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.48c8ac6482ec",{v0:(current ? '' : 'selected'),v1:(!current)}) : `<button type="button" class="parent-picker-option ${current ? '' : 'selected'}" role="option" aria-selected="${!current}" data-parent-option data-parent-value=""><span class="parent-picker-option-title">Проект</span><span class="parent-picker-option-meta">Верхний уровень проекта</span></button>`);
  const options = candidates.map(candidate => `<button type="button" class="parent-picker-option ${current === candidate.id ? 'selected' : ''}" role="option" aria-selected="${current === candidate.id}" data-parent-option data-parent-value="${escape(candidate.id)}"><span class="parent-picker-option-title">${escape(candidate.title)}</span><span class="parent-picker-option-meta">${escape(candidate.id)} · ${escape(labels[candidate.status] || candidate.status || (globalThis.HubI18n?.t?.("app.f877c25535e8") ?? 'Статус не задан'))}</span></button>`).join('');
  return root + (options || (globalThis.HubI18n?.t?.("app.53b1f18878b8") ?? '<p class="parent-picker-empty">Ничего не найдено</p>'));
}
function parentPicker(task) {
  const selected = state.tasks.find(candidate => candidate.id === task.parentTask);
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.ca6479685a1e",{v0:(escape(task.id)),v1:(escape(selected?.title || (globalThis.HubI18n?.t?.("app.f45edf006851") ?? 'Проект'))),v2:(uiIcon('chevron')),v3:(parentPickerOptions(task))}) : `<div class="parent-picker" data-parent-picker data-task-id="${escape(task.id)}"><span class="parent-picker-label">Родитель</span><button type="button" class="parent-picker-trigger" data-parent-picker-trigger aria-haspopup="listbox" aria-expanded="false"><span>${escape(selected?.title || (globalThis.HubI18n?.t?.("app.f45edf006851") ?? 'Проект'))}</span>${uiIcon('chevron')}</button><div class="parent-picker-popover" hidden><input type="search" class="parent-picker-search" data-parent-search placeholder="Поиск по названию, ID, описанию…" aria-label="Поиск родительской задачи"><div class="parent-picker-options" role="listbox" aria-label="Родительская задача">${parentPickerOptions(task)}</div></div></div>`);
}
function closeParentPicker(picker) {
  if (!picker) return;
  picker.classList.remove('open');
  picker.querySelector('.parent-picker-popover')?.setAttribute('hidden', '');
  picker.querySelector('[data-parent-picker-trigger]')?.setAttribute('aria-expanded', 'false');
}
function taskPage(id, stageId) {
  const task = state.tasks.find((t) => t.id === id);
  if (!task)
    return title(
      (globalThis.HubI18n?.t?.("app.03cc1c2d5ac2") ?? "Задачи"),
      (globalThis.HubI18n?.t?.("app.52aff16cc8d3") ?? "Задача не найдена"),
      (globalThis.HubI18n?.t?.("app.7868efec7dc2") ?? "Ссылка может относиться к другому проекту."),
    );
  if (activeProject && task.detailLoaded === false) {
    const detailError = taskDetailLoader.error(activeProject, id, state.revision);
    if (!detailError) taskDetailLoader.load(activeProject, id, state.revision)?.catch(() => {});
    if (!task.detailCached) return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.a897fcf89ee4",{v0:(detailError ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.b27f5d7fdd22",{v0:(escape(detailError)),v1:(escape(id))}) : `<p role="alert">Не удалось загрузить подробности: ${escape(detailError)}</p><button type="button" class="icon-button" data-task-detail-retry="${escape(id)}" title="Повторить загрузку подробностей задачи" aria-label="Повторить загрузку подробностей задачи">Повторить</button>`) : (globalThis.HubI18n?.t?.("app.9735f335cac3") ?? '<p>Получаем полное описание и этапы.</p>'))}) : `<section class="panel" role="status"><h1>Загрузка задачи…</h1>${detailError ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.b27f5d7fdd22",{v0:(escape(detailError)),v1:(escape(id))}) : `<p role="alert">Не удалось загрузить подробности: ${escape(detailError)}</p><button type="button" class="icon-button" data-task-detail-retry="${escape(id)}" title="Повторить загрузку подробностей задачи" aria-label="Повторить загрузку подробностей задачи">Повторить</button>`) : (globalThis.HubI18n?.t?.("app.9735f335cac3") ?? '<p>Получаем полное описание и этапы.</p>')}</section>`);
  }
  const stage =
    task.stages.find((s) => s.id === stageId) ||
    task.stages.find((s) => s.status === "active") ||
    task.stages[0];
  const taxonomy = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.7c23346f735c",{v0:(escape(task.id)),v1:(task.type === 'task' || !task.type ? 'selected' : ''),v2:(task.type === 'bug' ? 'selected' : ''),v3:(task.type === 'epic' ? 'selected' : ''),v4:(escape(task.id)),v5:(!task.priority ? 'selected' : ''),v6:([['blocker','Blocker'],['critical','Critical'],['major','Major'],['minor','Minor'],['trivial','Trivial']].map(([value,label]) => `<option value="${value}" ${task.priority === value ? 'selected' : ''}>${label}</option>`).join('')),v7:(parentPicker(task))}) : `<div class="task-edit-controls"><label><span>Тип</span><select data-task-edit="type" data-task-id="${escape(task.id)}"><option value="task" ${task.type === 'task' || !task.type ? 'selected' : ''}>Task</option><option value="bug" ${task.type === 'bug' ? 'selected' : ''}>Bug</option><option value="epic" ${task.type === 'epic' ? 'selected' : ''}>Epic</option></select></label><label><span>Приоритет</span><select data-task-edit="priority" data-task-id="${escape(task.id)}"><option value="" ${!task.priority ? 'selected' : ''}>Не задан</option>${[['blocker','Blocker'],['critical','Critical'],['major','Major'],['minor','Minor'],['trivial','Trivial']].map(([value,label]) => `<option value="${value}" ${task.priority === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>${parentPicker(task)}</div>`);
  const children = (task.children || []).map(childId => state.tasks.find(candidate => candidate.id === childId)).filter(Boolean);
  const aggregate = task.progressAggregate || {done: task.stages.filter(s => s.status === 'done').length, total: task.stages.length, percent: 0};
  const descendantPriority = {blocker: 'Blocker', critical: 'Critical', major: 'Major', minor: 'Minor', trivial: 'Trivial'}[task.maxDescendantPriority];
  const prioritySummary = task.type === 'epic' && descendantPriority ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.2d6faffbb6c5",{v0:(escape(task.maxDescendantPriority)),v1:(escape(descendantPriority))}) : `<span class="task-priority descendant ${escape(task.maxDescendantPriority)}" title="Максимальный приоритет незавершённых потомков">Потомки: ${escape(descendantPriority)}</span>`) : '';
  const lifecycleControls = ['done', 'cancelled'].includes(task.status)
    ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.61c9cc4e8502",{v0:(escape(task.id)),v1:(uiIcon('reopen'))}) : `<div class="task-actions"><button class="icon-button" data-task-reopen="${escape(task.id)}" title="Переоткрыть задачу" aria-label="Переоткрыть задачу">${uiIcon('reopen')}</button></div>`)
    : (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.aa3c6e6c7b23",{v0:(escape(task.id)),v1:(uiIcon('check')),v2:(task.completion?.autoEligible ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.570b05a5bffa",{v0:(escape(task.id)),v1:(uiIcon('save'))}) : `<button class="icon-button" data-task-close="${escape(task.id)}" data-close-mode="auto" title="Закрыть после проверки завершения" aria-label="Закрыть автоматически">${uiIcon('save')}</button>`) : '')}) : `<div class="task-actions"><button class="icon-button" data-task-close="${escape(task.id)}" data-close-mode="manual" title="Закрыть задачу" aria-label="Закрыть задачу">${uiIcon('check')}</button>${task.completion?.autoEligible ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.570b05a5bffa",{v0:(escape(task.id)),v1:(uiIcon('save'))}) : `<button class="icon-button" data-task-close="${escape(task.id)}" data-close-mode="auto" title="Закрыть после проверки завершения" aria-label="Закрыть автоматически">${uiIcon('save')}</button>`) : ''}</div>`);
  const createdAt = task.createdAt || state.project.baselineAt;
  const updatedAt = task.updatedAt || createdAt;
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.4ac9f6556887",{v0:(stageLocationNotice(task, stageId)),v1:(activeProject ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.0ffa7950dd60",{v0:(escape(task.id)),v1:(uiIcon('transfer'))}) : `<button class="icon-button" data-transfer-task="${escape(task.id)}" title="Перенести задачу в проект" aria-label="Перенести в проект…">${uiIcon('transfer')}</button>`) : ''),v2:(taskStatus(task)),v3:(primaryControl(task)),v4:(copyControls(task, null, false)),v5:(title((globalThis.HubI18n?.t?.("app.bedc429e0f61") ?? "Задача / ") + task.id, task.title, task.summary)),v6:(aggregate.done),v7:(aggregate.total),v8:(aggregate.percent),v9:(date(createdAt)),v10:(date(updatedAt)),v11:(prioritySummary),v12:(estimate(task, true)),v13:(blockerDetail(task)),v14:(gitCommits(task)),v15:(""),v16:(taxonomy),v17:(escape(task.id)),v18:(uiIcon('edit')),v19:(lifecycleControls),v20:(children.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.131ce75c0d14",{v0:(children.map(child => `<a href="${taskLink(child)}"><strong>${escape(child.title)}</strong><span>${escape(({epic:'Epic',bug:'Bug',task:'Task'}[child.type || 'task']))} · ${escape(child.status)}</span></a>`).join(''))}) : `<section class="panel child-task-list"><h2>Дочерние задачи</h2>${children.map(child => `<a href="${taskLink(child)}"><strong>${escape(child.title)}</strong><span>${escape(({epic:'Epic',bug:'Bug',task:'Task'}[child.type || 'task']))} · ${escape(child.status)}</span></a>`).join('')}</section>`) : ''),v21:([
    ["plan", (globalThis.HubI18n?.t?.("app.d3482ce5cf86") ?? "План и зависимости")],
    ["scope", (globalThis.HubI18n?.t?.("app.eaf501117cbe") ?? "Объём и приёмка")],
    ["history", (globalThis.HubI18n?.t?.("app.080c85caded8") ?? "История задачи")],
    ["chats", (globalThis.HubI18n?.t?.("app.b5121e526dd9") ?? "Чаты")],
  ]
    .map(
      ([key, label]) =>
        `<button role="tab" aria-selected="${taskTab === key}" data-task-tab="${key}" class="${taskTab === key ? "selected" : ""}">${label}</button>`,
    )
    .join("")),v22:(window.ChatActionsUI?.render(task, null, activeProject) || ""),v23:(taskTab === "plan" ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.fdf6e2780c02",{v0:(escape(task.id)),v1:(uiIcon('plus')),v2:(task.stages.map((s, i) => `<div class="stage-item ${s === stage ? "selected" : ""}"><a class="stage-item-link" href="${taskLink(task, s.id)}" ${s === stage ? 'aria-current="step"' : ""}><span class="stage-number">${String(i + 1).padStart(2, "0")}</span><div class="stage-item-content"><h3>${escape(s.title)}</h3><div class="stage-item-meta">${planStatus(s)}</div></div></a><div class="stage-item-actions">${taskStatus(task,s,true)}${copyControls(task, s, false)}</div></div>`).join("")),v3:(stage ? stageDetail(task, stage) : (globalThis.HubI18n?.t?.("app.10ce6a1e0485") ?? '<div class="empty">Этапы ещё не добавлены</div>')),v4:(archivedStages(task)),v5:(taskRelations(task))}) : `<div class="section-head"><h2>Этапы</h2><button class="icon-button" data-edit-stage="" data-task-id="${escape(task.id)}" title="Добавить этап" aria-label="Добавить этап">${uiIcon('plus')}</button></div><div class="task-layout"><div><div class="panel stage-list" data-scroll-key="task-stage-list">${task.stages.map((s, i) => `<div class="stage-item ${s === stage ? "selected" : ""}"><a class="stage-item-link" href="${taskLink(task, s.id)}" ${s === stage ? 'aria-current="step"' : ""}><span class="stage-number">${String(i + 1).padStart(2, "0")}</span><div class="stage-item-content"><h3>${escape(s.title)}</h3><div class="stage-item-meta">${planStatus(s)}</div></div></a><div class="stage-item-actions">${taskStatus(task,s,true)}${copyControls(task, s, false)}</div></div>`).join("")}</div><p class="caption" style="margin-top:12px">Этапы имеют разный объём. Полоска этапов показывает их состояние, а не процент затраченного времени.</p></div>${stage ? stageDetail(task, stage) : (globalThis.HubI18n?.t?.("app.10ce6a1e0485") ?? '<div class="empty">Этапы ещё не добавлены</div>')}</div>${archivedStages(task)}${taskRelations(task)}`) : ""),v24:(taskTab === "scope" ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.65862e59e21a",{v0:(list(task.scope)),v1:(list(task.acceptance)),v2:(list(task.deferred))}) : `<div class="two-columns"><section class="panel stage-detail"><h2>Входит в задачу</h2><div class="detail-section">${list(task.scope)}</div><div class="detail-section"><h3>Критерии завершения</h3>${list(task.acceptance)}</div></section><section><h2>Отдельные будущие этапы</h2><div class="detail-section">${list(task.deferred)}</div><div class="notice">Эти пункты сохранены в плане развития, но не входят в критерии завершения текущей задачи.</div></section></div>`) : ""),v25:(["plan", "scope"].includes(taskTab) ? taskSources(task) : ""),v26:(taskTab === "chats" ? taskChats(task) : ""),v27:(taskTab === "history"
     ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.b0ecb4a83f13",{v0:(state.events
           .filter((e) => e.taskId === task.id)
           .map((e) => eventView(e))
           .join("") ||
         (globalThis.HubI18n?.t?.("app.c00e3f714250") ?? '<div class="empty">В недавней ленте нет событий этой задачи. Полная история доступна по ссылке ниже.</div>')),v1:(encodeURIComponent(task.id))}) : `<div id="task-history" class="timeline">${state.events
           .filter((e) => e.taskId === task.id)
           .map((e) => eventView(e))
           .join("") ||
         (globalThis.HubI18n?.t?.("app.c00e3f714250") ?? '<div class="empty">В недавней ленте нет событий этой задачи. Полная история доступна по ссылке ниже.</div>')}</div><a href="#history/${encodeURIComponent(task.id)}">Открыть полную историю этой задачи →</a>`)
     : "")}) : `${stageLocationNotice(task, stageId)}<div class="task-top-actions"><a class="back" href="#tasks">← Все задачи</a>${activeProject ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.0ffa7950dd60",{v0:(escape(task.id)),v1:(uiIcon('transfer'))}) : `<button class="icon-button" data-transfer-task="${escape(task.id)}" title="Перенести задачу в проект" aria-label="Перенести в проект…">${uiIcon('transfer')}</button>`) : ''}<div class="task-page-status">${taskStatus(task)}</div><div class="task-page-actions">${primaryControl(task)}${copyControls(task, null, false)}</div></div><div class="task-heading">${title((globalThis.HubI18n?.t?.("app.bedc429e0f61") ?? "Задача / ") + task.id, task.title, task.summary)}</div><div class="task-compact-summary" aria-label="Сводка задачи"><div class="summary-line"><span>${aggregate.done} / ${aggregate.total} элементов завершено · ${aggregate.percent}%</span><span>Создана: ${date(createdAt)}</span><span>Обновление: ${date(updatedAt)}</span>${prioritySummary}</div>${estimate(task, true)}</div>${blockerDetail(task)}${gitCommits(task)}<div class="task-controls-row">${taxonomy}<button class="icon-button" data-edit-task="${escape(task.id)}" title="Редактировать задачу" aria-label="Редактировать задачу">${uiIcon('edit')}</button>${lifecycleControls}</div>${children.length ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.131ce75c0d14",{v0:(children.map(child => `<a href="${taskLink(child)}"><strong>${escape(child.title)}</strong><span>${escape(({epic:'Epic',bug:'Bug',task:'Task'}[child.type || 'task']))} · ${escape(child.status)}</span></a>`).join(''))}) : `<section class="panel child-task-list"><h2>Дочерние задачи</h2>${children.map(child => `<a href="${taskLink(child)}"><strong>${escape(child.title)}</strong><span>${escape(({epic:'Epic',bug:'Bug',task:'Task'}[child.type || 'task']))} · ${escape(child.status)}</span></a>`).join('')}</section>`) : ''}<div class="tabs" role="tablist" aria-label="Содержание задачи">${[
    ["plan", (globalThis.HubI18n?.t?.("app.d3482ce5cf86") ?? "План и зависимости")],
    ["scope", (globalThis.HubI18n?.t?.("app.eaf501117cbe") ?? "Объём и приёмка")],
    ["history", (globalThis.HubI18n?.t?.("app.080c85caded8") ?? "История задачи")],
    ["chats", (globalThis.HubI18n?.t?.("app.b5121e526dd9") ?? "Чаты")],
  ]
    .map(
      ([key, label]) =>
        `<button role="tab" aria-selected="${taskTab === key}" data-task-tab="${key}" class="${taskTab === key ? "selected" : ""}">${label}</button>`,
    )
    .join("")}</div>
${window.ChatActionsUI?.render(task, null, activeProject) || ""}
 ${taskTab === "plan" ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.fdf6e2780c02",{v0:(escape(task.id)),v1:(uiIcon('plus')),v2:(task.stages.map((s, i) => `<div class="stage-item ${s === stage ? "selected" : ""}"><a class="stage-item-link" href="${taskLink(task, s.id)}" ${s === stage ? 'aria-current="step"' : ""}><span class="stage-number">${String(i + 1).padStart(2, "0")}</span><div class="stage-item-content"><h3>${escape(s.title)}</h3><div class="stage-item-meta">${planStatus(s)}</div></div></a><div class="stage-item-actions">${taskStatus(task,s,true)}${copyControls(task, s, false)}</div></div>`).join("")),v3:(stage ? stageDetail(task, stage) : (globalThis.HubI18n?.t?.("app.10ce6a1e0485") ?? '<div class="empty">Этапы ещё не добавлены</div>')),v4:(archivedStages(task)),v5:(taskRelations(task))}) : `<div class="section-head"><h2>Этапы</h2><button class="icon-button" data-edit-stage="" data-task-id="${escape(task.id)}" title="Добавить этап" aria-label="Добавить этап">${uiIcon('plus')}</button></div><div class="task-layout"><div><div class="panel stage-list" data-scroll-key="task-stage-list">${task.stages.map((s, i) => `<div class="stage-item ${s === stage ? "selected" : ""}"><a class="stage-item-link" href="${taskLink(task, s.id)}" ${s === stage ? 'aria-current="step"' : ""}><span class="stage-number">${String(i + 1).padStart(2, "0")}</span><div class="stage-item-content"><h3>${escape(s.title)}</h3><div class="stage-item-meta">${planStatus(s)}</div></div></a><div class="stage-item-actions">${taskStatus(task,s,true)}${copyControls(task, s, false)}</div></div>`).join("")}</div><p class="caption" style="margin-top:12px">Этапы имеют разный объём. Полоска этапов показывает их состояние, а не процент затраченного времени.</p></div>${stage ? stageDetail(task, stage) : (globalThis.HubI18n?.t?.("app.10ce6a1e0485") ?? '<div class="empty">Этапы ещё не добавлены</div>')}</div>${archivedStages(task)}${taskRelations(task)}`) : ""}
${taskTab === "scope" ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.65862e59e21a",{v0:(list(task.scope)),v1:(list(task.acceptance)),v2:(list(task.deferred))}) : `<div class="two-columns"><section class="panel stage-detail"><h2>Входит в задачу</h2><div class="detail-section">${list(task.scope)}</div><div class="detail-section"><h3>Критерии завершения</h3>${list(task.acceptance)}</div></section><section><h2>Отдельные будущие этапы</h2><div class="detail-section">${list(task.deferred)}</div><div class="notice">Эти пункты сохранены в плане развития, но не входят в критерии завершения текущей задачи.</div></section></div>`) : ""}
${["plan", "scope"].includes(taskTab) ? taskSources(task) : ""}
${taskTab === "chats" ? taskChats(task) : ""}
 ${taskTab === "history"
     ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.b0ecb4a83f13",{v0:(state.events
           .filter((e) => e.taskId === task.id)
           .map((e) => eventView(e))
           .join("") ||
         (globalThis.HubI18n?.t?.("app.c00e3f714250") ?? '<div class="empty">В недавней ленте нет событий этой задачи. Полная история доступна по ссылке ниже.</div>')),v1:(encodeURIComponent(task.id))}) : `<div id="task-history" class="timeline">${state.events
           .filter((e) => e.taskId === task.id)
           .map((e) => eventView(e))
           .join("") ||
         (globalThis.HubI18n?.t?.("app.c00e3f714250") ?? '<div class="empty">В недавней ленте нет событий этой задачи. Полная история доступна по ссылке ниже.</div>')}</div><a href="#history/${encodeURIComponent(task.id)}">Открыть полную историю этой задачи →</a>`)
     : ""}`);
}
function stageDetail(task, stage) {
  const deps = stage.dependsOn || [];
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.ef21c3b741ba",{v0:(escape(stage.title)),v1:(taskStatus(task, stage)),v2:(copyControls(task, stage, false)),v3:(escape(stage.id)),v4:(escape(task.id)),v5:(uiIcon('edit')),v6:(escape(task.id)),v7:(escape(stage.id)),v8:(uiIcon('transfer')),v9:(escape(task.id)),v10:(escape(stage.id)),v11:(uiIcon('unlink')),v12:(escape(task.id)),v13:(escape(stage.id)),v14:(uiIcon('delete')),v15:(escape(stage.summary)),v16:(estimate(stage,true,task.id)),v17:(blockerDetail(stage)),v18:(gitCommits(task, stage)),v19:(''),v20:(stageTransferHistory(stage)),v21:(deps.length
      ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.499d700a4876",{v0:(deps
          .map((id) => {
            const dependency = task.stages.find((s) => s.id === id);
            return `<a class="dependency" href="${taskLink(task, id)}">${escape(dependency?.title || id)}</a>`;
          })
          .join(
            "",
          ))}) : `<div class="detail-section"><h3>Зависит от</h3>${deps
          .map((id) => {
            const dependency = task.stages.find((s) => s.id === id);
            return `<a class="dependency" href="${taskLink(task, id)}">${escape(dependency?.title || id)}</a>`;
          })
          .join(
            "",
          )}<p class="caption">Зависимости показывают порядок завершения; независимые части могут внедряться раньше.</p></div>`)
      : ""),v22:(list(stage.done, true)),v23:(list(stage.remaining)),v24:(stage.evidence?.length ? evidence(stage.evidence) : (globalThis.HubI18n?.t?.("app.5a02cab07ff0") ?? '<p class="caption">Результаты будут добавлены по мере проверки.</p>')),v25:((window.ChatActionsUI?.render(task, stage, activeProject) || "") + (window.TaskLaunchesUI?.render(task, stage, activeProject) || ""))}) : `<section class="panel stage-detail"><div class="title-row"><h2>${escape(stage.title)}</h2></div><div class="stage-detail-actions">${taskStatus(task, stage)}${copyControls(task, stage, false)}<button class="icon-button" data-edit-stage="${escape(stage.id)}" data-task-id="${escape(task.id)}" title="Редактировать этап" aria-label="Редактировать этап">${uiIcon('edit')}</button><button class="icon-button" data-stage-operation="transfer" data-task-id="${escape(task.id)}" data-stage-id="${escape(stage.id)}" title="Перенести этап" aria-label="Перенести этап">${uiIcon('transfer')}</button><button class="icon-button" data-stage-operation="unlink" data-task-id="${escape(task.id)}" data-stage-id="${escape(stage.id)}" title="Отвязать этап" aria-label="Отвязать этап">${uiIcon('unlink')}</button><button class="icon-button" data-stage-operation="delete" data-task-id="${escape(task.id)}" data-stage-id="${escape(stage.id)}" title="Удалить этап из текущего плана, сохранив историю" aria-label="Удалить этап">${uiIcon('delete')}</button></div><p>${escape(stage.summary)}</p>${estimate(stage,true,task.id)}${blockerDetail(stage)}${gitCommits(task, stage)}${stageTransferHistory(stage)}${deps.length
      ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.499d700a4876",{v0:(deps
          .map((id) => {
            const dependency = task.stages.find((s) => s.id === id);
            return `<a class="dependency" href="${taskLink(task, id)}">${escape(dependency?.title || id)}</a>`;
          })
          .join(
            "",
          ))}) : `<div class="detail-section"><h3>Зависит от</h3>${deps
          .map((id) => {
            const dependency = task.stages.find((s) => s.id === id);
            return `<a class="dependency" href="${taskLink(task, id)}">${escape(dependency?.title || id)}</a>`;
          })
          .join(
            "",
          )}<p class="caption">Зависимости показывают порядок завершения; независимые части могут внедряться раньше.</p></div>`)
      : ""}<div class="detail-section"><h3>Реализовано</h3>${list(stage.done, true)}</div><div class="detail-section"><h3>До завершения</h3>${list(stage.remaining)}</div><div class="detail-section"><h3>Доказательства и исходники</h3>${stage.evidence?.length ? evidence(stage.evidence) : (globalThis.HubI18n?.t?.("app.5a02cab07ff0") ?? '<p class="caption">Результаты будут добавлены по мере проверки.</p>')}</div>${window.ChatActionsUI?.render(task, stage, activeProject) || ""}${window.TaskLaunchesUI?.render(task, stage, activeProject) || ""}</section>`);
}
function historyPage() {
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.ee76f1e88f14",{v0:(title((globalThis.HubI18n?.t?.("app.4611f243b206") ?? "Журнал проекта"), (globalThis.HubI18n?.t?.("app.5143a08843c2") ?? "История разработки"), (globalThis.HubI18n?.t?.("app.8a7fe9bd38e0") ?? "События сохраняются между сессиями. Время ниже — время записи в журнал, с локальным часовым поясом браузера."))),v1:(state.tasks.map((t) => `<option value="${escape(t.id)}" ${historyTask === t.id ? "selected" : ""}>${escape(t.title)}</option>`).join("")),v2:(historyKind === "task" ? "selected" : ""),v3:(historyKind === "check" ? "selected" : ""),v4:(historyKind === "decision" ? "selected" : ""),v5:(historyKind === "finding" ? "selected" : ""),v6:(historyKind === "git" ? "selected" : ""),v7:(state.eventCount),v8:(historyRows()),v9:(historyNext ? "" : "hidden"),v10:(uiIcon('clock'))}) : `${title((globalThis.HubI18n?.t?.("app.4611f243b206") ?? "Журнал проекта"), (globalThis.HubI18n?.t?.("app.5143a08843c2") ?? "История разработки"), (globalThis.HubI18n?.t?.("app.8a7fe9bd38e0") ?? "События сохраняются между сессиями. Время ниже — время записи в журнал, с локальным часовым поясом браузера."))}<div class="toolbar"><select id="history-task" aria-label="Задача"><option value="">Все задачи</option>${state.tasks.map((t) => `<option value="${escape(t.id)}" ${historyTask === t.id ? "selected" : ""}>${escape(t.title)}</option>`).join("")}</select><select id="history-kind" aria-label="Тип события"><option value="">Все события</option><option value="task" ${historyKind === "task" ? "selected" : ""}>Изменения задач</option><option value="check" ${historyKind === "check" ? "selected" : ""}>Проверки</option><option value="decision" ${historyKind === "decision" ? "selected" : ""}>Решения</option><option value="finding" ${historyKind === "finding" ? "selected" : ""}>Наблюдения</option><option value="git" ${historyKind === "git" ? "selected" : ""}>Git</option></select><span class="caption">Всего событий в ленте: ${state.eventCount}</span></div><div id="history-list">${historyRows()}</div><button class="icon-button" id="history-more" title="Более ранние события" aria-label="Более ранние события" ${historyNext ? "" : "hidden"}>${uiIcon('clock')}</button><div class="notice">Более ранняя документация ещё не перенесена. Её импорт сохранит исходные даты, происхождение и отметку актуальности; он не будет выдавать старые записи за новые события.</div>`);
}
function historyRows() {
  const loading = historyLoading && !historyData.length
    ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.cb52ad320244",{v0:(uiIcon("clock"))}) : `<div class="history-loading" role="status" aria-live="polite">${uiIcon("clock")}<span>Загрузка истории разработки…</span></div>`)
    : "";
  if (historyLoading && !historyData.length) return loading;
  if (historyError && !historyData.length) {
    return `${loading}<div class="empty">${escape(historyError)}</div>`;
  }
  let day = "";
  const filtered = historyData.filter(
    (e) => !historyKind || e.kind.startsWith(historyKind),
  );
  return loading + (
    filtered
      .map((e) => {
        const current = dateOnly(e.at),
          heading =
            day !== current
              ? `<div class="history-date">${escape(current)}</div>`
              : "";
        day = current;
        return heading + eventView(e);
      })
      .join("") ||
    (globalThis.HubI18n?.t?.("app.9e7ac0d3c378") ?? '<div class="empty">Нет событий выбранного типа на загруженной странице.</div>')
  );
}
async function loadHistory(more = false, preserve = false) {
  const project = activeProject, domain = state?.revision;
  const generation = ++historyGeneration;
  historyLoading = true;
  historyError = "";
  if (!more && !preserve) {
    historyData = [];
    historyNext = null;
  }
  replacePreservingScroll("#history-list", historyRows());
  const q = new URLSearchParams({ limit: "40" });
  if (historyTask) q.set("task", historyTask);
  if (historyKind) q.set("kind", historyKind);
  if (more && historyNext) q.set("before", historyNext);
  try {
    const cache = loadHistory.cache ||= new Map();
    const key = JSON.stringify([project, domain, q.toString()]);
    let pending = cache.get(key);
    if (!pending) {
      pending = get("/api/history?" + q);
      cache.set(key, pending);
      while (cache.size > 16) cache.delete(cache.keys().next().value);
      pending.catch(() => { if (cache.get(key) === pending) cache.delete(key); });
    }
    const data = await pending;
    if (data.revision !== undefined && data.revision !== domain && cache.get(key) === pending) cache.delete(key);
    if (generation !== historyGeneration || project !== activeProject || route()[0] !== "history") return;
    if (preserve && historyData.length) {
      historyData = [
        ...new Map(
          [...data.events, ...historyData].map((e) => [e.seq, e]),
        ).values(),
      ].sort((a, b) => b.seq - a.seq);
    } else {
      historyData = more ? [...historyData, ...data.events] : data.events;
      historyNext = data.next;
    }
    replacePreservingScroll("#history-list", historyRows());
    $("#history-more").hidden = !historyNext;
  } catch (error) {
    if (generation !== historyGeneration || route()[0] !== "history") return;
    historyError = (globalThis.HubI18n?.t?.("app.8b9f32ff1d0c") ?? "История не загрузилась: ") + (globalThis.HubI18n?.error?.(error) ?? error.message);
    showError(historyError);
  } finally {
    if (generation !== historyGeneration || route()[0] !== "history") return;
    historyLoading = false;
    replacePreservingScroll("#history-list", historyRows());
    const moreButton = $("#history-more");
    if (moreButton) moreButton.hidden = !historyNext;
  }
}
function checksPage() {
  return renderChecksPage();
}
function architecturePage() {
  if (window.KnowledgeUI) return window.KnowledgeUI.page('architecture', {project:activeProject,projectApi,showError,route,projectSettings:projectSettings().architecture});
  return (globalThis.HubI18n?.t?.("app.de55e0ce203b") ?? '<div class="notice">Не удалось загрузить интерфейс архитектуры. Обновите страницу.</div>');
}
function future(name, description, path) {
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.07f3a94e18f6",{v0:(escape(name)),v1:(escape(description)),v2:(escape(path))}) : `<article class="future-item"><h3>${escape(name)}</h3><p>${escape(description)}</p><small>${escape(path)} · следующий этап</small></article>`);
}
function docsPage() {
  if (window.KnowledgeUI) return window.KnowledgeUI.page('docs', {project:activeProject,projectApi,showError,route});
  return (globalThis.HubI18n?.t?.("app.49a07b4ad542") ?? '<div class="notice">Не удалось загрузить интерфейс документации. Обновите страницу.</div>');
}
function actionsPage() {
  const caption = globalThis.HubI18n?.t?.('actions.placeholder') ?? 'Будущие действия проекта появятся в этом разделе.';
  return `${title(globalThis.HubI18n?.t?.('app.a4bba03c40fd') ?? 'Управление', globalThis.HubI18n?.t?.('app.9c41ac662be1') ?? 'Действия проекта', caption, status('planned'))}<div class="notice">${escape(caption)}</div>`;
}

let diagnosticSearch = '', diagnosticArchive = null, archiveLoading = false, archiveError = '';
function chatText(ru, en) { return globalThis.HubI18n?.locale === 'en' ? en : ru; }
function agentName(s) {
  if (s.chatIdentity === 'unreported') return chatText('Сеанс без данных чата', 'Session without chat details');
  const leaf = s.agentPath?.split('/').filter(Boolean).at(-1)?.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
  return s.title || s.agentNickname || leaf || chatText('Чат без названия', 'Untitled chat');
}

function gitCommitLine(commit) {
  const task = state.tasks.find((item) => item.id === commit.taskId);
  const target = task ? `<a href="${taskLink(task, commit.stageId)}">${escape(task.title)}${commit.stageTitle ? ` · ${escape(commit.stageTitle)}` : ''}</a>` : (globalThis.HubI18n?.t?.("app.2a3f3aa25255") ?? '<span class="git-unassigned">Не привязан к задаче</span>');
  const sha = commit.githubUrl ? `<a class="git-sha" href="${escape(commit.githubUrl)}" target="_blank" rel="noopener">${escape(commit.shortSha || commit.sha)}</a>` : `<code class="git-sha">${escape(commit.shortSha || commit.sha)}</code>`;
  return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.66370ad36c08",{v0:(sha),v1:(escape(commit.message || (globalThis.HubI18n?.t?.("app.933714518c05") ?? 'Без сообщения'))),v2:(target),v3:(commit.fileCount || 0),v4:(escape(commit.at || '')),v5:(date(commit.at))}) : `<article class="git-commit-row"><div>${sha}<strong>${escape(commit.message || (globalThis.HubI18n?.t?.("app.933714518c05") ?? 'Без сообщения'))}</strong></div><div class="git-commit-meta">${target}<span>${commit.fileCount || 0} файлов</span><time datetime="${escape(commit.at || '')}">${date(commit.at)}</time></div></article>`);
}
function gitCheckpointIssues() {
  return state.tasks.flatMap(task => [{task}, ...(task.stages || []).map(stage => ({task, stage}))]).map(({task, stage}) => {
    const checkpoint = (stage || task).gitCheckpoint;
    if (!checkpoint || (!['error','pending'].includes(checkpoint.status) && checkpoint.publication?.status !== 'pending')) return '';
    const content = checkpointStatusContents(task, stage);
    if (!content) return '';
    const batch = checkpoint.status === 'error' && (stage || task).status === 'done'
      ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.aa2800795b9a",{v0:(escape(task.id)),v1:(escape(stage?.id || '')),v2:(uiIcon('link'))}) : `<button class="icon-button" data-checkpoint-batch="${escape(task.id)}" data-checkpoint-stage="${escape(stage?.id || '')}" title="Просмотреть общий commit и связанные задачи" aria-label="Сверить общий commit">${uiIcon('link')}</button>`)
      : '';
    return `<article class="git-checkpoint-issue"><h3>${escape(stage ? `${task.title} · ${stage.title}` : task.title)}</h3>${content}${batch}</article>`;
  }).join('');
}
function gitPage() {
  if (!gitData) return `${title((globalThis.HubI18n?.t?.("app.de5da87fcdc5") ?? "Контроль версий"), "Git", gitError ? (globalThis.HubI18n?.t?.("app.34ac78100648") ?? "Не удалось загрузить сводку") : (globalThis.HubI18n?.t?.("app.8f22932473df") ?? "Загрузка сводки репозитория…"))}<div class="${gitError ? 'empty' : 'loading'}">${gitError ? escape(gitError) : (globalThis.HubI18n?.t?.("app.a2ee2c776fb8") ?? 'Получение данных Git…')}</div>`;
  const repo = gitData.repository || {};
  if (!repo.available) return `${title((globalThis.HubI18n?.t?.("app.de5da87fcdc5") ?? "Контроль версий"), "Git", (globalThis.HubI18n?.t?.("app.91582e6e3be6") ?? "Состояние контроля версий недоступно"))}<div class="notice">${escape((repo.reason ? (globalThis.HubI18n?.error?.(repo.reason) ?? repo.reason) : '') || (globalThis.HubI18n?.t?.("app.00b50534ae90") ?? 'Репозиторий не найден'))}</div>`;
  const summary = gitData.summary || {}, github = repo.github || {};
  const links = github.repository ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.a932dbaeb95e",{v0:(escape(github.repository)),v1:(escape(github.branch)),v2:(escape(github.compare))}) : `<a href="${escape(github.repository)}" target="_blank" rel="noopener">Репозиторий</a> · <a href="${escape(github.branch)}" target="_blank" rel="noopener">Ветка</a> · <a href="${escape(github.compare)}" target="_blank" rel="noopener">Сравнить</a>`) : (repo.remote ? `<span>Remote: ${escape(repo.remote)}</span>` : (globalThis.HubI18n?.t?.("app.c3d002eb262e") ?? '<span>Remote не задан</span>'));
  const push = repo.upstream && (repo.ahead || 0) > 0 ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.ff1e06390a03",{v0:(uiIcon('up'))}) : `<button class="icon-button" type="button" data-git-push title="Отправить push…" aria-label="Отправить push…">${uiIcon('up')}</button>`) : '';
  const tasks = (gitData.tasks || []).map((task) => {
    const stateLabel = {local:(globalThis.HubI18n?.t?.("app.cc4b566d3740") ?? 'Незакомичено'), committed:(globalThis.HubI18n?.t?.("app.ca5510a1d6eb") ?? 'Есть commit'), mixed:(globalThis.HubI18n?.t?.("app.84fb6f4571ba") ?? 'Смешанное')}[task.association] || (globalThis.HubI18n?.t?.("app.c7951fd569fc") ?? 'Изменения');
    const latest = task.latestCommit ? `<code>${escape(task.latestCommit.shortSha || task.latestCommit.sha)}</code>` : '—';
    const taskRecord = state.tasks.find((item) => item.id === task.taskId);
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.c5f5c695e20b",{v0:(taskRecord ? taskLink(taskRecord) : '#git'),v1:(escape(task.title || task.taskId)),v2:(escape(stateLabel)),v3:(task.localFiles),v4:(task.commitFiles),v5:(task.commitCount),v6:(latest)}) : `<a class="git-task-row" href="${taskRecord ? taskLink(taskRecord) : '#git'}"><strong>${escape(task.title || task.taskId)}</strong><span>${escape(stateLabel)}</span><span>${task.localFiles} локал. · ${task.commitFiles} в commit</span><span>${task.commitCount} commit</span><span>${latest}</span></a>`);
  }).join('');
  const unassigned = gitData.unassigned || {};
  const unassignedNotice = (unassigned.localFiles || unassigned.ambiguousFiles || unassigned.commits) ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.4a7a419f9e98",{v0:(unassigned.localFiles || 0),v1:(unassigned.ambiguousFiles || 0),v2:(unassigned.commits || 0)}) : `<div class="git-unassigned-panel"><strong>Без однозначной привязки</strong><span>${unassigned.localFiles || 0} локал. файлов · ${unassigned.ambiguousFiles || 0} неоднозначных · ${unassigned.commits || 0} commit</span></div>`) : '';
  const commits = (gitData.commits || []).slice(0, 30).map(gitCommitLine).join('') || (globalThis.HubI18n?.t?.("app.1fb78a04ea9e") ?? '<div class="empty">Commit-ов пока нет.</div>');
  const checkpointIssues = gitCheckpointIssues();
  const pushes = ((gitData.pushes || []).map((event) => { const related = (event.git?.commits || []).map((commit) => commit.taskId ? `${commit.shortSha || commit.sha}: ${commit.taskId}` : (commit.shortSha || commit.sha)).join(' · '); return `<article class="git-commit-row"><div><strong>${escape(event.title || 'Push')}</strong></div><div class="git-commit-meta"><span>${escape(event.detail || (globalThis.HubI18n?.t?.("app.0302a26a55bd") ?? 'Push записан в журнал'))}${related ? ` · ${escape(related)}` : ''}</span><time datetime="${escape(event.at || '')}">${date(event.at)}</time></div></article>`; }).join('') || (globalThis.HubI18n?.t?.("app.8a93262b7e96") ?? '<div class="empty">Push-события появятся после записи push в журнал Project Hub.</div>'));
  const page = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.fd3e2fd84c00",{v0:(title((globalThis.HubI18n?.t?.("app.de5da87fcdc5") ?? "Контроль версий"), "Git", (globalThis.HubI18n?.t?.("app.b3e5d6cb14bf") ?? "Состояние репозитория в терминах задач и их изменений."), `<div class="git-page-actions">${links}${push}</div>`)),v1:(escape(repo.root || '—')),v2:(escape(repo.branch || '—')),v3:(repo.dirty ? 'git-dirty' : 'git-clean'),v4:(repo.dirty ? (globalThis.HubI18n?.t?.("app.b1364c306301") ?? 'Есть изменения') : (globalThis.HubI18n?.t?.("app.62b4ba5080df") ?? 'Чисто')),v5:(summary.affectedTasks || 0),v6:(summary.changedFiles || 0),v7:(summary.commits || 0),v8:(repo.upstream ? `${repo.ahead || 0} / ${repo.behind || 0}` : '—'),v9:(repo.upstream ? (globalThis.HubI18n?.t?.("app.a0c5c733407a") ?? 'впереди / позади') : (globalThis.HubI18n?.t?.("app.b720b25482d6") ?? 'upstream не задан')),v10:(tasks || (globalThis.HubI18n?.t?.("app.3dc796f8bc4d") ?? '<div class="empty">Нет изменений, однозначно связанных с задачами.</div>')),v11:(unassignedNotice),v12:(commits),v13:(pushes)}) : `${title((globalThis.HubI18n?.t?.("app.de5da87fcdc5") ?? "Контроль версий"), "Git", (globalThis.HubI18n?.t?.("app.b3e5d6cb14bf") ?? "Состояние репозитория в терминах задач и их изменений."), `<div class="git-page-actions">${links}${push}</div>`)}<section class="git-repository-head"><div><span class="caption">Репозиторий</span><strong>${escape(repo.root || '—')}</strong></div><div><span class="caption">Ветка</span><strong>${escape(repo.branch || '—')}</strong></div><div><span class="caption">Состояние</span><strong class="${repo.dirty ? 'git-dirty' : 'git-clean'}">${repo.dirty ? (globalThis.HubI18n?.t?.("app.b1364c306301") ?? 'Есть изменения') : (globalThis.HubI18n?.t?.("app.62b4ba5080df") ?? 'Чисто')}</strong></div></section><section class="git-kpis"><div><span>Затронуто задач</span><strong>${summary.affectedTasks || 0}</strong></div><div><span>Локальные файлы</span><strong>${summary.changedFiles || 0}</strong></div><div><span>Commit-ов</span><strong>${summary.commits || 0}</strong></div><div><span>Синхронизация</span><strong>${repo.upstream ? `${repo.ahead || 0} / ${repo.behind || 0}` : '—'}</strong><small>${repo.upstream ? (globalThis.HubI18n?.t?.("app.a0c5c733407a") ?? 'впереди / позади') : (globalThis.HubI18n?.t?.("app.b720b25482d6") ?? 'upstream не задан')}</small></div></section><section class="git-section"><div class="section-head"><h2>Изменения по задачам</h2><span class="caption">Только сводка, без diff и полного списка файлов</span></div><div class="git-task-list">${tasks || (globalThis.HubI18n?.t?.("app.3dc796f8bc4d") ?? '<div class="empty">Нет изменений, однозначно связанных с задачами.</div>')}</div>${unassignedNotice}</section><section class="git-section"><div class="section-head"><h2>Последние commit</h2><span class="caption">Привязка берётся из Project Hub trailers</span></div><div class="git-commit-list">${commits}</div></section><section class="git-section"><div class="section-head"><h2>Последние push</h2></div><div class="git-commit-list">${pushes}</div></section>`);
  return page + (checkpointIssues ? `<section class="git-section git-checkpoint-diagnostics"><div class="section-head"><h2>${globalThis.HubI18n?.locale==='en'?'Commit diagnostics':'Диагностика коммитов'}</h2></div>${checkpointIssues}</section>` : '');
}
function diagnosticAge(seen) {
  if (!seen) return (globalThis.HubI18n?.t?.("app.df43550f208b") ?? 'Нет наблюдений');
  const minutes = Math.max(0, Math.floor((Date.now()/1000 - seen)/60));
  return minutes < 1 ? (globalThis.HubI18n?.t?.("app.d1c36b299130") ?? 'Менее минуты назад') : minutes < 60 ? minutes+(globalThis.HubI18n?.t?.("app.59b9a2f87cfa") ?? ' мин назад') : date(new Date(seen*1000).toISOString());
}
function diagnosticTechnical(s) {
  const rows = [
    [(globalThis.HubI18n?.t?.("app.299c345725ff") ?? 'ID чата'),s.id],
    [(globalThis.HubI18n?.t?.("app.56e46960c104") ?? 'Источник'),(globalThis.HubI18n?.t?.("app.044a08ad2434") ?? 'Каталог Codex и события Hub')],
    [(globalThis.HubI18n?.t?.("app.9e8b5b2cf2ed") ?? 'Последнее состояние'),s.state || 'unknown'],
    [(globalThis.HubI18n?.t?.("app.b7e50daf5ad8") ?? 'Время наблюдения'),s.seen ? date(new Date(s.seen*1000).toISOString()) : (globalThis.HubI18n?.t?.("app.76848548e29c") ?? 'Нет данных')],
    [(globalThis.HubI18n?.t?.("app.7cdfa59e6f79") ?? 'Путь агента'),s.agentPath],
    [(globalThis.HubI18n?.t?.("app.bae15d9c380b") ?? 'Псевдоним'),s.agentNickname],
    [(globalThis.HubI18n?.t?.("app.bf5423fe8102") ?? 'Рабочая папка'),s.workspace]
  ];
  if (Array.isArray(s.hubActors) && s.hubActors.length) rows.push([chatText('Связанные участники Hub','Linked Hub actors'),JSON.stringify(s.hubActors)]);
  return '<details class="diagnostic-technical" data-key="technical-'+escape(s.id)+(globalThis.HubI18n?.t?.("app.b2e8508d15f0") ?? '"><summary>Технические данные</summary><dl>')+
    rows.filter(([,v])=>v).map(([k,v])=>'<dt>'+escape(k)+'</dt><dd>'+escape(v)+'</dd>').join('')+'</dl></details>';
}
function diagnosticChat(s, members, depth = 0) {
  const children = depth >= 12 ? [] : members.filter(c=>c.parentSession===s.id && c.id!==s.id);
  const linkedTasks = new Map();
  for (const task of (Array.isArray(s.taskLinks) ? s.taskLinks : state.tasks.filter(t=>t.participatingSessions?.includes(s.id)).map(t=>({id:t.id,title:t.title})))) {
    if (task?.id) linkedTasks.set(task.id, {...task, stages:[]});
  }
  for (const link of (s.stageLinks || [])) {
    if (!link?.task) continue;
    const task = linkedTasks.get(link.task) || {...state.tasks.find(item=>item.id===link.task),id:link.task,title:state.tasks.find(item=>item.id===link.task)?.title || link.task,stages:[]};
    task.stages.push(link);
    linkedTasks.set(link.task, task);
  }
  const related = [...linkedTasks.values()];
  const lastObserved = Math.max(s.lastActivityAt || 0, s.seen || 0, s.updatedAt || 0, s.lastRelatedAt || 0);
  const observedAt = lastObserved ? new Date(lastObserved*1000).toISOString() : null;
  const activity = observedAt ? '<time datetime="' + escape(observedAt) + '" title="' + escape(date(observedAt)) + '">' + escape(diagnosticAge(lastObserved)) + (Math.floor(Math.max(0, Date.now()/1000-lastObserved)/60)<60 ? ' · ' + escape(date(observedAt)) : '') + '</time>' : '<span>' + escape(chatText('Нет данных об активности', 'No activity recorded')) + '</span>';
  return '<details class="diagnostic-chat '+(depth?'diagnostic-child':'')+'" data-key="chat-'+escape(s.id)+'" '+(route()[1]===s.id||children.some(c=>c.id===route()[1])?'open':'')+'>'+
    '<summary><span class="diagnostic-name">'+escape(agentName(s))+(s.parentSession?'<small>'+escape(chatText('Участник родительского чата','Participant in parent chat'))+(s.agentRole?' · '+escape(s.agentRole):'')+'</small>':'')+(children.length?'<small>'+escape(chatText('Участники: ','Participants: '))+children.length+'</small>':'')+'</span>'+
    '<span class="caption chat-activity">'+activity+'</span></summary>'+
    '<div class="diagnostic-body"><div class="diagnostic-links">'+chatCodexLink(s,members)+'</div>'+
    '<section class="chat-task-links"><strong>'+escape(chatText('Связанные задачи','Linked tasks'))+'</strong>'+(related.length?related.map(t=>'<div class="chat-task-group"><a href="'+taskLink(t)+'">'+escape(t.title||t.id)+'</a>'+(t.stages.length?'<div class="chat-stage-links">'+t.stages.map(link=>'<a href="'+taskLink({id:link.task},link.stage)+'">'+escape(link.title||link.stage)+'</a>').join('')+'</div>':'')+'</div>').join(''):'<span class="caption">'+escape(chatText('Связи с задачами не зарегистрированы.','No task links recorded.'))+'</span>')+'</section>'+
    '<p class="caption">'+(s.contextOnly?(globalThis.HubI18n?.t?.("app.97db5772d6db") ?? 'Родительский чат участника задачи. '):s.historical?(globalThis.HubI18n?.t?.("app.ef305dc5b654") ?? 'Историческая запись. '):'')+(s.parentSession?(globalThis.HubI18n?.t?.("app.49ade5ea8e40") ?? 'Подагент работал внутри родительского чата. '):'')+(globalThis.HubI18n?.t?.("app.ef4192cac8bc") ?? 'Текущее выполнение не подтверждено.</p>')+
    (s.lastRelatedAt?(globalThis.HubI18n?.t?.("app.3951a00db6d1") ?? '<p class="caption">Последняя запись по задаче: ')+escape(date(new Date(s.lastRelatedAt*1000).toISOString()))+'</p>':'')+
    (children.length?(globalThis.HubI18n?.t?.("app.7add60b3df59") ?? '<div class="chat-participants-label">Агенты, работавшие в чате</div><div class="diagnostic-children">')+children.map(c=>diagnosticChat(c,members,depth+1)).join('')+'</div>':'')+
    diagnosticTechnical(s)+'</div></details>';
}
function chatCodexLink(s, members = []) {
  let target = s.openSession || s.id, current = s, visited = new Set([s.id]);
  if (!s.openSession) while (current.parentSession && !visited.has(current.parentSession)) {
    target = current.parentSession;
    visited.add(target);
    current = members.find(row=>row.id===target) || {};
  }
  const source = members.find(row=>row.id===target) || s;
  const client = String(source.nativeChat?.client || '').toLowerCase();
  const provider = ({codex:'Codex',cursor:'Cursor','claude-code':'Claude Code','claude_code':'Claude Code'})[client] || source.nativeChat?.client;
  const parentTarget = Boolean(s.parentSession && target !== s.id);
  const label = provider ? (parentTarget ? chatText('Открыть родительский чат в ' + provider, 'Open parent chat in ' + provider) : chatText('Открыть в ' + provider, 'Open in ' + provider)) : chatText('Открыть чат', 'Open chat');
  if (!source.nativeChat?.openUri) return '<span class="chat-open-unavailable" role="note">' + escape(source.chatIdentity === 'unreported' ? chatText('Приложение ещё не сообщило название или адрес этого чата.','The app has not provided a title or address for this chat yet.') : chatText('Приложение не предоставило ссылку для открытия этого чата.','The app did not provide a link to open this chat.')) + '</span>';
  const linked = codexSessionLink(source.nativeChat, label);
  if (linked.includes('<a ')) return linked;
  return '<span class="chat-open-unavailable" role="note">' + escape(chatText('Открытие недоступно: ссылка от приложения не прошла проверку безопасности.','Opening is unavailable: the app link did not pass the safety check.')) + '</span>';
}
let chatsData = null, chatsLoading = false, chatsError = '', chatsGeneration = 0, chatsViewKey = '';
function chatsContext() {
  const [page, id] = route();
  if (page === 'coordination') return {task:null, query:diagnosticSearch};
  if (page === 'tasks' && id && taskTab === 'chats') return {task:id, query:''};
  return null;
}
function chatsKey(context = chatsContext()) {
  return context ? JSON.stringify([activeProject, context.task, context.query]) : '';
}
function chatsHistoryView() {
  if (chatsViewKey !== chatsKey()) return (globalThis.HubI18n?.t?.("app.262ccea54a08") ?? '<p role="status">Загрузка чатов…</p>');
  const members = chatsData?.sessions || [], ids = new Set(members.map(s=>s.id));
  const roots = members.filter(s=>!s.parentSession || !ids.has(s.parentSession));
  const warnings = [...(chatsData?.warnings || []), ...(chatsData?.discovery?.available===false ? [chatsData.discovery.reason || (globalThis.HubI18n?.t?.("app.d7a3c3b07cea") ?? 'Каталог Codex недоступен.')] : [])];
  if (chatsData?.discovery?.truncated) warnings.push((globalThis.HubI18n?.t?.("app.cf2b4f4de8fd") ?? 'Каталог ограничен 5000 записями; более старые чаты без сохраненных связей Hub могут отсутствовать.'));
  return warnings.map(w=>'<p class="notice" role="status">'+escape(globalThis.HubI18n?.error?.(w) ?? w)+'</p>').join('')+
    (roots.map(s=>diagnosticChat(s,members)).join('') || (!chatsLoading && !chatsError ? '<div class="empty">'+(chatsData?.task?(globalThis.HubI18n?.t?.("app.3716a2b2d4ad") ?? 'Сохраненных связей с чатами пока нет. Обсуждения без записи работы или автора события не привязаны к задаче.'):(globalThis.HubI18n?.t?.("app.f399a4d4ed88") ?? 'Чаты не найдены.'))+'</div>' : ''))+
    (chatsLoading?(globalThis.HubI18n?.t?.("app.262ccea54a08") ?? '<p role="status">Загрузка чатов…</p>'):'')+
    (chatsError?'<p role="alert">'+escape(chatsError)+(globalThis.HubI18n?.t?.("app.1cc60d66f193") ?? '</p><button class="icon-button" data-chats-retry title="Повторить загрузку" aria-label="Повторить загрузку">')+uiIcon('refresh')+'</button>':'')+
    (chatsData?.next != null?(globalThis.HubI18n?.t?.("app.c47ae8612b44") ?? '<button class="icon-button" data-chats-more title="Показать ещё чаты" aria-label="Показать ещё чаты" ')+(chatsLoading?'disabled':'')+'>'+uiIcon('plus')+'</button>':'');
}
function taskChats(task) {
  return (globalThis.HubI18n?.t?.("app.6b66cab9fbe4") ?? '<section class="diagnostic-section task-chats"><div class="section-head"><h2>Чаты задачи</h2><button class="icon-button" data-chats-retry title="Обновить чаты" aria-label="Обновить чаты">')+uiIcon('refresh')+(globalThis.HubI18n?.t?.("app.45f803221317") ?? '</button></div><p class="caption">Обсуждение, планирование и работа по сохраненным связям задачи. Участники сгруппированы по родительскому чату.</p><div id="chats-history-content">')+chatsHistoryView()+'</div></section>';
}
async function loadChats(more = false) {
  const context = chatsContext(), key = chatsKey(context);
  if (!context || (chatsLoading && key===chatsViewKey)) return;
  const generation = ++chatsGeneration;
  if (!more || key!==chatsViewKey) chatsData = null;
  const offset = more ? chatsData?.next : 0;
  if (offset == null) return;
  chatsViewKey = key; chatsLoading = true; chatsError = '';
  render({background:true});
  const params = new URLSearchParams({offset:String(offset),limit:'25'});
  if (context.task) params.set('task',context.task);
  if (context.query) params.set('q',context.query);
  try {
    const result = await get('/api/chats?'+params);
    if (generation!==chatsGeneration || key!==chatsKey()) return;
    chatsData = more && chatsData ? {...result,sessions:[...chatsData.sessions,...result.sessions]} : result;
  } catch(error) {
    if (generation===chatsGeneration && key===chatsKey()) chatsError = (globalThis.HubI18n?.t?.("app.ca545f32f926") ?? 'Не удалось загрузить чаты: ')+(globalThis.HubI18n?.error?.(error) ?? error.message);
  } finally {
    if (generation===chatsGeneration) { chatsLoading = false; render({background:true}); }
  }
}
function syncChatsView() {
  const key = chatsKey();
  if (!key && chatsViewKey) {
    chatsGeneration++; chatsLoading = false; chatsViewKey = ''; chatsData = null; chatsError = '';
  }
  if (key && key!==chatsViewKey) loadChats();
}
function archiveView() {
  if (archiveLoading) return (globalThis.HubI18n?.t?.("app.4a055a905b03") ?? '<p role="status">Загрузка архива…</p>');
  if (archiveError) return '<p role="alert">'+escape(archiveError)+(globalThis.HubI18n?.t?.("app.0baf9497afd4") ?? '</p><button class="icon-button" id="diagnostic-archive-retry" title="Повторить" aria-label="Повторить">')+uiIcon('refresh')+'</button>';
  if (!diagnosticArchive) return '';
  const entries = [...(diagnosticArchive.attempts||[]).map(a=>({title:a.title||(globalThis.HubI18n?.t?.("app.542d994bd853") ?? 'Попытка резервирования'),data:a})),
    ...(diagnosticArchive.team?.work||diagnosticArchive.work||[]).map(w=>({title:w.title||(globalThis.HubI18n?.t?.("app.32aa642b0ee5") ?? 'Запись работы'),data:w}))];
  return (globalThis.HubI18n?.t?.("app.f4c588f63d10") ?? '<p class="caption">Исторические записи. Не являются текущими блокировками.</p>')+
    (entries.map((e,i)=>'<details class="diagnostic-technical" data-key="archive-'+coordinationOffset+'-'+i+'"><summary>'+escape(e.title)+'</summary><pre>'+escape(JSON.stringify(e.data,null,2))+'</pre></details>').join('')||(globalThis.HubI18n?.t?.("app.879f9de30b05") ?? '<p class="muted">Записей нет.</p>'))+
    '<div class="diagnostic-links">'+(coordinationOffset?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.499c191d5485",{v0:(uiIcon('left'))}) : `<button class="icon-button" data-archive-page="previous" title="Предыдущие" aria-label="Предыдущие">${uiIcon('left')}</button>`):'')+
    (diagnosticArchive.more?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.35c51618fc23",{v0:(uiIcon('right'))}) : `<button class="icon-button" data-archive-page="next" title="Следующие" aria-label="Следующие">${uiIcon('right')}</button>`):'')+'</div>';
}
function coordinationPage() {
  const c=state.coordination||{};
  const problem=!c.available?c.reason||(globalThis.HubI18n?.t?.("app.089609cd6038") ?? 'Диагностические данные недоступны'):c.discovery?.available===false?c.discovery.reason||(globalThis.HubI18n?.t?.("app.e2bd047ec63a") ?? 'Каталог Codex недоступен'):null;
  return title('', (globalThis.HubI18n?.t?.("app.b5121e526dd9") ?? 'Чаты'), (globalThis.HubI18n?.t?.("app.c2630799a363") ?? 'История обсуждений и работы по задачам проекта.'))+
    (globalThis.HubI18n?.t?.("app.977e2e697b1a") ?? '<section class="diagnostic-health"><div><span class="caption">Связь с порталом</span><strong id="diagnostic-connection">')+(connected?(globalThis.HubI18n?.t?.("app.105fe2f786c3") ?? 'Подключено'):(globalThis.HubI18n?.t?.("app.0cf96d40d24c") ?? 'Переподключение…'))+'</strong></div>'+
    (globalThis.HubI18n?.t?.("app.5d591011174d") ?? '<div><span class="caption">Каталог Codex</span><strong>')+(c.discovery?.available?(globalThis.HubI18n?.t?.("app.d81568b864c8") ?? 'Доступен'):(globalThis.HubI18n?.t?.("app.6f596994f824") ?? 'Нет актуальных данных'))+'</strong></div>'+
    (globalThis.HubI18n?.t?.("app.bc85cf0314d1") ?? '<div><span class="caption">Данные получены</span><strong>')+escape(clock(state.serverTime))+'</strong></div></section>'+
    (problem?'<p class="notice" role="status">'+escape(problem)+'</p>':'')+
    `<section class="diagnostic-section chat-history"><div class="section-head"><div><h2>${escape(chatText('История чатов','Chat history'))}</h2><p class="caption">${escape(chatText('Поиск по сохранённым чатам и связанным задачам. Активность показывает последнее наблюдение, а не текущее выполнение.','Search saved chats and linked tasks. Activity shows the last observation, not current execution.'))}</p></div><div class="chat-history-controls"><input id="diagnostic-search" type="search" aria-label="${escape(chatText('Поиск чатов','Search chats'))}" placeholder="${escape(chatText('Поиск чатов или задач','Search chats or tasks'))}" value="${escape(diagnosticSearch)}"><button class="icon-button" data-chats-retry title="${escape(chatText('Обновить историю чатов','Refresh chat history'))}" aria-label="${escape(chatText('Обновить историю чатов','Refresh chat history'))}">${uiIcon('refresh')}</button></div></div><div id="chats-history-content">`+chatsHistoryView()+'</div></section>'+
    (globalThis.HubI18n?.t?.("app.5d4294815184") ?? '<details class="diagnostic-archive" data-key="diagnostic-archive"><summary>Технический архив</summary><div id="diagnostic-archive-content">')+archiveView()+'</div></details>';
}
async function loadDiagnosticArchive() {
  if (archiveLoading) return;
  const project=activeProject, offset=coordinationOffset;
  archiveLoading=true; archiveError='';
  const repaint=()=>replacePreservingScroll('#diagnostic-archive-content', archiveView());
  repaint();
  try { const result=await get('/api/diagnostics/archive?offset='+offset); if(project===activeProject&&offset===coordinationOffset) diagnosticArchive=result; }
  catch(e) { if(project===activeProject) archiveError=(globalThis.HubI18n?.t?.("app.d66afda7ef30") ?? 'Не удалось загрузить архив: ')+e.message; }
  finally { archiveLoading=false; repaint(); }
}
document.addEventListener('toggle', e=>{
  if(e.target.matches?.('details[data-key="diagnostic-archive"]')&&e.target.open&&!diagnosticArchive&&!archiveLoading&&!archiveError) loadDiagnosticArchive();
},true);
let pendingLiveRender = null, liveRenderTimer = null, interactionUntil = 0;
let scrollRestoreGeneration = 0;
function liveRenderKey() {
  return JSON.stringify([activeProject, location.hash]);
}
function hasLiveInteraction() {
  const active = document.activeElement;
  return Date.now() < interactionUntil || Boolean(
    (active?.closest('input, select, textarea, [contenteditable="true"], [role="combobox"], [role="listbox"], [role="menu"]') && !active.closest('[hidden], [inert]')) ||
    document.querySelector('[aria-haspopup][aria-expanded="true"], dialog[open], details[open] input, details[open] select, details[open] textarea')
  );
}
function shouldDeferLiveRender() {
  if (!window.HubLiveUI) return hasLiveInteraction();
  const active = document.activeElement;
  // Mounted text fields can receive independent status updates. Native option
  // pickers and open custom menus retain their current option list until close.
  return Date.now() < interactionUntil || Boolean(
    active?.closest('select, [role="combobox"], [role="listbox"], [role="menu"]') ||
    document.querySelector('[aria-haspopup][aria-expanded="true"]')
  );
}
function flushLiveRender() {
  liveRenderTimer = null;
  if (!pendingLiveRender) return;
  if (pendingLiveRender !== liveRenderKey()) { pendingLiveRender = null; return; }
  if (!shouldDeferLiveRender()) render({background: true});
  else if (Date.now() < interactionUntil) scheduleLiveRenderFlush();
}
function scheduleLiveRenderFlush() {
  clearTimeout(liveRenderTimer);
  liveRenderTimer = setTimeout(flushLiveRender, Math.max(0, interactionUntil - Date.now()) + 1);
}
// Keep native controls and custom popovers mounted until the interaction ends.
// State still updates; only the latest background paint is deferred.
for (const name of ['focusout', 'change', 'click', 'keydown', 'toggle', 'close']) {
  document.addEventListener(name, scheduleLiveRenderFlush, true);
}
for (const name of ['wheel', 'touchmove', 'pointerdown', 'pointerup', 'keydown']) {
  document.addEventListener(name, () => {
    scrollRestoreGeneration++;
    interactionUntil = Date.now() + 150;
    scheduleLiveRenderFlush();
  }, {capture: true, passive: true});
}
document.addEventListener('scroll', () => {
  interactionUntil = Date.now() + 150;
  if (pendingLiveRender) scheduleLiveRenderFlush();
}, {capture: true, passive: true});
function captureScrollPositions() {
  const positions = new Map([['window', { top: window.scrollY, left: window.scrollX }]]);
  document.querySelectorAll('[data-scroll-key]').forEach((node) => {
    positions.set(node.dataset.scrollKey, { top: node.scrollTop, left: node.scrollLeft });
  });
  return positions;
}
function restoreScrollPositions(positions) {
  if (!positions) return;
  const generation = ++scrollRestoreGeneration;
  const restore = () => {
    if (generation !== scrollRestoreGeneration) return;
    const viewport = positions.get('window');
    if (viewport) window.scrollTo({ top: viewport.top, left: viewport.left, behavior: 'instant' });
    document.querySelectorAll('[data-scroll-key]').forEach((node) => {
      const value = positions.get(node.dataset.scrollKey);
      if (value) { node.scrollTop = value.top; node.scrollLeft = value.left; }
    });
  };
  restore();
  requestAnimationFrame(() => {
    restore();
    requestAnimationFrame(restore);
  });
}
function replacePreservingScroll(selector, html) {
  const positions = captureScrollPositions();
  const node = $(selector);
  if (!node) return;
  if (window.HubLiveUI) window.HubLiveUI.patch(node, html);
  else node.innerHTML = html;
  restoreScrollPositions(positions);
}
function renderNavigation(navPage, id) {
  if ($("#navigation").dataset.page !== navPage) {
    const html = navigation.map(([key, label, soon]) =>
      `${key === "architecture" ? '<div class="nav-separator"></div>' : ""}<a id="nav-${key}" href="#${key}" aria-label="${escape(label)}" data-label="${escape(label)}" class="${navPage === key ? "active" : ""}" ${navPage === key ? 'aria-current="page"' : ""}>${key === 'settings' ? uiIcon('settings') : `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[key]}"/></svg>`}<span>${label}</span>${soon ? `<small class="soon">${soon}</small>` : ""}</a>`).join("");
    if (window.HubLiveUI) window.HubLiveUI.patch($("#navigation"), html);
    else $("#navigation").innerHTML = html;
    $("#navigation").dataset.page = navPage;
  }
  $("#breadcrumb").textContent = (navPage === 'projects' ? (globalThis.HubI18n?.t?.("app.e0d097d35e6e") ?? 'Хранилище / ') : (globalThis.HubI18n?.t?.("app.06382c114a63") ?? 'Проект / ')) +
    (navigation.find(n => n[0] === navPage)?.[1] || (globalThis.HubI18n?.t?.("app.bd3a5be11e2a") ?? 'Обзор')) + (id && navPage === 'tasks' ? ' / ' + id : '');
}
function projectsPage() {
  return window.HubProjectsUI?.page() || '';
}
function bindProjectsPage() {
  window.HubProjectsUI?.afterRender();
  window.HubStorageUI?.afterRender();
  bindBackups();
}
function render({ preserveScroll = true, background = false, localeChange = false } = {}) {
  window.HubRuntimeUI?.afterRender();
  if (!state) {
    const page = navigation.some(n => n[0] === route()[0]) ? route()[0] : 'overview';
    renderNavigation(page);
    if (page === 'projects') {
      if (!$('#projects-manager')) $('#content').innerHTML = projectsPage();
      bindProjectsPage();
    } else if (page === 'settings') {
      if (background && window.HubLiveUI) window.HubLiveUI.patch($('#content'), settingsPage());
      else $('#content').innerHTML = settingsPage();
    } else $('#content').innerHTML = (globalThis.HubI18n?.t?.("app.2cce607ef7ae") ?? '<div class="page-head"><div><h1>Проект не подключён</h1><p>Откройте раздел <a href="#projects">«Проекты»</a>, чтобы добавить проект или перенести данные. Затем выберите проект в верхнем меню.</p></div></div>');
    window.HubRuntimeUI?.afterRender();
    window.HubSettingsUI?.afterRender();
    window.HubVersionControlUI?.afterRender();
    window.HubAgentProvidersUI?.afterRender();
    window.HubConnectionsUI?.afterRender();
    window.HubLocalFiles?.bind();
    window.backupStatus?.afterRender();
    return;
  }
  if (background && shouldDeferLiveRender()) {
    pendingLiveRender = liveRenderKey();
    scheduleLiveRenderFlush();
    updateFreshness();
    return;
  }
  pendingLiveRender = null;
  const scrollPositions = preserveScroll ? captureScrollPositions() : null;
  const [page, id, stage] = route();
  const navPage = navigation.some((x) => x[0] === page) ? page : "overview";
  const activeId = document.activeElement?.id,
    selection = activeId && document.activeElement.selectionStart,
    selectionEnd = activeId && document.activeElement.selectionEnd,
    selectionDirection = activeId && document.activeElement.selectionDirection;
  renderNavigation(navPage, id);
  if (navPage === 'architecture' && window.HubAssets &&
      (!window.ArchitectureMap || !window.ArchitectureCanvas)) {
    const project = activeProject;
    $('#content').innerHTML = (globalThis.HubI18n?.t?.("app.fb6caad2dda8") ?? '<p role="status">Загрузка раздела…</p>');
    window.HubAssets.ensureArchitecture().then(() => {
      if (activeProject === project && route()[0] === 'architecture') render();
    }).catch(error => {
      if (activeProject === project && route()[0] === 'architecture') showError((globalThis.HubI18n?.error?.(error) ?? error.message));
    });
    return;
  }
  const openDetails = [
    ...document.querySelectorAll("details[open][data-key]"),
  ].map((x) => x.dataset.key);
  window.HubSettingsUI?.beforeRender();
  const renderers = {
    overview,
    tasks: () => (id ? taskPage(id, stage) : tasksPage()),
    git: gitPage,
    history: historyPage,
    checks: checksPage,
    architecture: architecturePage,
    docs: docsPage,
    actions: actionsPage,
    coordination: coordinationPage,
    settings: settingsPage,
    projects: projectsPage,
  };
  // Keep task filters mounted during live updates. Replacing the select
  // element closes a native dropdown even when its focus is restored.
  if (!localeChange && navPage === "tasks" && !id && $("#task-results")) {
    replacePreservingScroll("#task-results", taskResults());
    const statusSelect = $('#task-status-filter');
    if (statusSelect) statusSelect.value = taskFilter;
    const sortSelect = $('#task-list-sort');
    if (sortSelect) sortSelect.value = taskListSort;
  } else if (navPage === 'projects' && $('#projects-manager')) {
    // A storage operation survives unrelated project/SSE updates.
  } else if (['docs','architecture'].includes(navPage) && document.querySelector('.knowledge-root')?.dataset.kProject === String(activeProject) && document.querySelector('.knowledge-root')?.dataset.kMode === navPage) {
    // Knowledge drafts and selection survive unrelated task/SSE refreshes.
  } else {
    if (preserveScroll && window.HubLiveUI) window.HubLiveUI.patch($('#content'), renderers[navPage](), {preserveInputs:background});
    else $("#content").innerHTML = renderers[navPage]();
  }
  openDetails.forEach((key) => {
    const d = [...document.querySelectorAll("details[data-key]")].find(
      (x) => x.dataset.key === key,
    );
    if (d) d.open = true;
  });
  if (activeId) {
    const input = document.getElementById(activeId);
    input?.focus({ preventScroll: true });
    if (typeof selection === "number" && input?.setSelectionRange)
      try { input.setSelectionRange(selection, selectionEnd, selectionDirection); } catch { /* Non-text control. */ }
  }
  restoreScrollPositions(scrollPositions);
  window.HubSettingsUI?.afterRender();
  window.HubVersionControlUI?.afterRender();
  window.HubAgentProvidersUI?.afterRender();
  window.HubConnectionsUI?.afterRender();
  window.HubRuntimeUI?.afterRender();
  if (navPage === 'projects') bindProjectsPage();
  window.HubLocalFiles?.bind();
  window.backupStatus?.afterRender();
  window.KnowledgeUI?.afterRender({project:activeProject,projectApi,showError,route});
  window.ChatActionsUI?.afterRender({project:activeProject,route,render,state,refresh});
  window.TaskLaunchesUI?.afterRender({project:activeProject,route,render,state,refresh,renderEvidence:evidence});
  updateFreshness();
  if (typeof syncChatsView === 'function') syncChatsView();
}
function updateFreshness() {
  if (!state) return;
  document.querySelectorAll('[data-diagnostic-age]').forEach(n => { n.textContent=diagnosticAge(Number(n.dataset.diagnosticAge)); });
  const age = state.lastEventAt
    ? Math.max(
        0,
        Math.floor((Date.now() - new Date(state.lastEventAt)) / 60000),
      )
    : 0;
  $("#freshness").textContent =
    (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.3b669c4b247a",{v0:(state.lastEventAt ? clock(state.lastEventAt) : (globalThis.HubI18n?.t?.("app.b8dbb45818c4") ?? "ещё нет")),v1:(age ? " · " + age + (globalThis.HubI18n?.t?.("app.59b9a2f87cfa") ?? " мин назад") : ""),v2:(state.eventCount)}) : `Последнее событие: ${state.lastEventAt ? clock(state.lastEventAt) : (globalThis.HubI18n?.t?.("app.b8dbb45818c4") ?? "ещё нет")}${age ? " · " + age + (globalThis.HubI18n?.t?.("app.59b9a2f87cfa") ?? " мин назад") : ""} · событий: ${state.eventCount}`);
  $("#freshness").title =
    (globalThis.HubI18n?.t?.("app.8f014b0c85c8") ?? "Состояние связи относится к серверу портала. Последнее событие показывает публикацию агентом, а не подтверждает его непрерывную активность.");
}
function setConnection(value) {
  connected = value;
  const diagnostic=$('#diagnostic-connection');
  if(diagnostic) diagnostic.textContent=value?(globalThis.HubI18n?.t?.("app.105fe2f786c3") ?? 'Подключено'):(globalThis.HubI18n?.t?.("app.0430a7ea834a") ?? 'Связь потеряна');
  const node = $("#connection");
  node.className = "live-indicator " + (value ? "connected" : "offline");
  node.querySelector("span").textContent = value
    ? (globalThis.HubI18n?.t?.("app.5b8e4f8d9441") ?? "Обновляется в реальном времени")
    : (globalThis.HubI18n?.t?.("app.1205ee9c3d92") ?? "Связь потеряна · переподключение");
}
function showError(message) {
  $("#alert").hidden = false;
  $("#alert").textContent = globalThis.HubI18n?.error?.(message) ?? message;
}
async function get(url) {
  const response = await fetch(projectApi(url), { cache: "no-store" });
  if (!response.ok)
    throw Error((await response.json()).error || response.status);
  return response.json();
}
async function loadGit() {
  const generation = ++gitGeneration, project = activeProject;
  gitError = "";
  try {
    const data = await get("/api/git");
    if (generation !== gitGeneration || project !== activeProject || route()[0] !== "git") return;
    gitData = data;
    render({preserveScroll: true, background: true});
  } catch (error) {
    if (generation === gitGeneration && project === activeProject && route()[0] === "git") {
      gitError = (globalThis.HubI18n?.t?.("app.c263b1efab35") ?? "Git-сводка не загрузилась: ") + (globalThis.HubI18n?.error?.(error) ?? error.message);
      showError(gitError);
      render({preserveScroll: true, background: true});
    }
  }
}
async function refresh() {
  if (!activeProject && !state) { render({background: true}); return; }
  if (loadInFlight) {
    refreshAgain = true;
    return loadInFlight;
  }
  loadInFlight = (async () => {
    const project = activeProject;
    const startupGit = !state && route()[0] === "git" ? loadGit() : null;
    try {
      const next = await get(activeProject ? "/api/tasks/summary" : "/api/state?view=portal");
      if (project !== activeProject) return;
      if (activeProject) retainTaskDetails(state, next);
      const nextCoordination = JSON.stringify([next.coordination?.revision, next.coordination?.titlesRevision, next.coordination?.available, next.coordination?.reason, next.relationsRevision, Math.floor(Date.now()/60000)]);
      const settingsChanged = JSON.stringify(next.settings) !== JSON.stringify(state?.settings);
      const changed = next.revision !== revision || nextCoordination !== coordinationRevision || settingsChanged;
      state = next;
      if (route()[0] === 'settings') void window.HubVersionControlUI?.refresh?.(activeProject);
      if (settingsChanged) restoreUiState();
      if (historyTask && !(route()[0] === 'history' && route()[1]) && !state.tasks.some(t => t.id === historyTask)) {
        historyTask = '';
        saveUiState(['history', 'task']);
      }
      $('#project-name').textContent = state.project.name;
      const currentRoute = route();
      const redirect = currentRoute[0] === 'tasks' && next.redirects?.[currentRoute[1]];
      if (redirect && !next.tasks.some(t => t.id === currentRoute[1])) {
        const url = new URL(location.href); url.searchParams.set('project', redirect.project);
        location.replace(url.href); return;
      }
      document.title = (next.project.name || (globalThis.HubI18n?.t?.("app.f45edf006851") ?? 'Проект')) + ' · Project Hub';
      revision = next.revision;
      coordinationRevision = nextCoordination;
      $("#alert").hidden = true;
      if (changed) {
        if (!(route()[0] === 'settings' && (settingsDraft().dirty || settingsDraft().busy))) render({background: true});
        if (route()[0] === "history") await loadHistory(false, true);
        if (route()[0] === "git" && !startupGit) loadGit();
        updateAnnouncement(next);
      }
    } catch (error) {
      showError((globalThis.HubI18n?.t?.("app.5516fff043c1") ?? "Не удалось обновить проект: ") + (globalThis.HubI18n?.error?.(error) ?? error.message));
      setConnection(false);
    } finally {
      loadInFlight = null;
      if (refreshAgain) {
        refreshAgain = false;
        await refresh();
      }
    }
  })();
  return loadInFlight;
}
async function pushGit() {
  if (!window.confirm((globalThis.HubI18n?.t?.("app.c69306bcbd49") ?? 'Отправить текущую ветку в удалённый репозиторий?'))) return;
  const button = document.querySelector('[data-git-push]');
  if (button) button.disabled = true;
  try {
    const response = await fetch(projectApi('/api/git/push'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({confirm:true})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || (globalThis.HubI18n?.t?.("app.cd044157f115") ?? 'Push не выполнен'));
    await refresh();
    if (route()[0] === "git") await loadGit();
    if (result.eventRecorded === false) {
      showError((globalThis.HubI18n?.t?.("app.07d3f125d958") ?? 'Push выполнен, но запись в историю не сохранена: ') + (result.eventWarning || (globalThis.HubI18n?.t?.("app.923dd22a6da8") ?? 'ошибка журнала')));
    }
  } catch (error) {
    showError((globalThis.HubI18n?.error?.(error) ?? error.message));
    if (button) button.disabled = false;
  }
}
document.addEventListener("click", (event) => {
  if (event.target.closest('[data-chats-more]')) loadChats(true);
  if (event.target.closest('[data-chats-retry]')) loadChats();
  if (event.target.closest('[data-git-push]')) pushGit();
  const transferButton = event.target.closest('[data-transfer-task]');
  if (transferButton) openTransfer(transferButton.dataset.transferTask);
  if(event.target.closest('#diagnostic-archive-retry')) loadDiagnosticArchive();
  const coordinationPageButton = event.target.closest('[data-archive-page]');
  if (coordinationPageButton) {
    coordinationOffset = Math.max(0, coordinationOffset + (coordinationPageButton.dataset.archivePage === 'next' ? 50 : -50));
    diagnosticArchive=null;
    loadDiagnosticArchive();
  }
  const filter = event.target.closest("[data-task-filter]");
  if (filter) {
    taskFilter = filter.dataset.taskFilter;
    render();
  }
  const tab = event.target.closest("[data-task-tab]");
  if (tab) {
    taskTab = tab.dataset.taskTab;
    render();
  }
  if (event.target.closest("#history-more")) loadHistory(true);
});
document.addEventListener("input", (event) => {
  if(event.target.id==='diagnostic-search') { diagnosticSearch=event.target.value; render(); }
  if (event.target.id === "task-search") {
    taskSearch = event.target.value;
    replacePreservingScroll("#task-results", taskResults());
  }
});
document.addEventListener('input', event => {
  const search = event.target.closest('[data-parent-search]');
  if (!search) return;
  const picker = search.closest('[data-parent-picker]');
  const task = state.tasks.find(candidate => candidate.id === picker.dataset.taskId);
  if (task) picker.querySelector('.parent-picker-options').innerHTML = parentPickerOptions(task, search.value);
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  const search = event.target.closest('[data-parent-search]');
  if (!search) return;
  closeParentPicker(search.closest('[data-parent-picker]'));
});
document.addEventListener("change", async (event) => {
  if (event.target.id === "history-task") {
    historyTask = event.target.value;
    loadHistory();
  }
  if (event.target.id === "history-kind") {
    historyKind = event.target.value;
    loadHistory();
  }
  if (event.target.id === 'overview-task-sort') {
    taskSort = event.target.value;
    const url = new URL(location.href); url.searchParams.set('sort', taskSort); history.replaceState(null, '', url.href); render({preserveScroll: true});
  }
  if (event.target.id === 'task-status-filter') {
    taskFilter = event.target.value;
    replacePreservingScroll('#task-results', taskResults());
  }
  if (event.target.id === 'task-type-filter') {
    taskTypeFilter = event.target.value;
    replacePreservingScroll('#task-results', taskResults());
  }
  if (event.target.id === 'task-priority-filter') {
    taskPriorityFilter = event.target.value;
    replacePreservingScroll('#task-results', taskResults());
  }
  if (event.target.id === 'task-list-sort') {
    taskListSort = event.target.value;
    const url = new URL(location.href); url.searchParams.set('taskSort', taskListSort); history.replaceState(null, '', url.href);
    replacePreservingScroll('#task-results', taskResults());
  }
  const edit = event.target.closest('[data-task-edit]');
  if (edit) {
    const patch = {[edit.dataset.taskEdit]: edit.value || null};
    try {
      const response = await fetch(projectApi('/api/v1/tasks/update'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task:edit.dataset.taskId, expected:state.revision, patch})});
      if (!response.ok) throw new Error((await response.json()).error || (globalThis.HubI18n?.t?.("app.f79e3043429e") ?? 'Не удалось обновить задачу'));
      await refresh();
    } catch (error) { showError((globalThis.HubI18n?.error?.(error) ?? error.message)); }
  }
});
window.addEventListener("hashchange", event => {
  const [page, id] = route();
  const previous = new URL(event.oldURL).hash.slice(1).split('/').map(decodeURIComponent);
  const sameTask = page === 'tasks' && Boolean(id) && previous[0] === 'tasks' && previous[1] === id;
  // A different stage is detail selection inside the same task, not a new page.
  scrollRestoreGeneration++;
  historyGeneration++;
  if (page === "history") {
    historyTask = id || historyTask;
    historyData = [];
    historyNext = null;
    historyLoading = true;
    historyError = "";
  }
  if (page === "tasks") taskTab = "plan";
  render({ preserveScroll: sameTask });
  if (state && page === "history") loadHistory();
  if (state && page === "git") { gitData = null; loadGit(); }
  if (!sameTask) window.scrollTo({ top: 0, behavior: "instant" });
});
if (route()[0] === "history") historyTask = route()[1] || "";
let stream;
let projectCatalogGeneration = 0;
async function loadProjects(initial = false) {
  const project = activeProject, generation = ++projectCatalogGeneration;
  const response = await fetch('/api/v1/projects', {cache:'no-store'}).catch(error => {
    if (!activeProject) setConnection(false);
    throw error;
  });
  if (!response.ok) {
    if (!activeProject) setConnection(false);
    throw Error((globalThis.HubI18n?.t?.("app.48d28a7c49a4") ?? 'Каталог проектов недоступен'));
  }
  const catalog = await response.json();
  if (project !== activeProject || generation !== projectCatalogGeneration) return false;
  if (!activeProject) {
    connected = true;
    $('#connection').className = 'live-indicator connected';
    $('#connection span').textContent = (globalThis.HubI18n?.t?.("app.60e51bb9d667") ?? 'Сервер доступен');
    $('#freshness').textContent = (globalThis.HubI18n?.t?.("app.4429fb918450") ?? 'Проект не выбран');
  }
  catalog.projects = (catalog.projects || []).filter(p => !p.deleted);
  const selectable = catalog.projects.filter(p => !p.archived);
  projectNames = new Map(catalog.projects.map(project => [project.id, project.name]));
  if (catalog.legacy) return true;
  const options = $('#project-options');
  $('#project-discovery').textContent = catalog.discovery.available ? '' : (globalThis.HubI18n?.t?.("app.d291fc05692e") ?? 'Каталог Codex недоступен · сохранённый список');
  if (!selectable.length && !catalog.projects.some(p => p.id === activeProject)) {
    options.textContent = (globalThis.HubI18n?.t?.("app.b4e73f30261b") ?? 'Подключённых проектов пока нет');
    activeProject = null; state = null;
    document.title = 'Project Hub';
    stream?.close();
    const url = new URL(location.href); url.searchParams.delete('project'); history.replaceState(null, '', url);
    $('#project-name').textContent = (globalThis.HubI18n?.t?.("app.51e140267931") ?? 'Выбрать проект');
    render();
    return false;
  }
  if (!activeProject) {
    activeProject = selectable.find(p => p.present)?.id || selectable[0].id;
    const url = new URL(location.href);
    url.searchParams.set('project', activeProject);
    history.replaceState(null, '', url);
    if (!initial) await startProject();
  }
  options.innerHTML = selectable.map(p => {
    const url = new URL(location.href);
    url.searchParams.set('project', p.id);
    url.hash = 'overview';
    return `<a href="${escape(url.href)}" ${p.id === activeProject ? 'aria-current="true"' : ''}>${escape(p.name)}${p.present ? '' : (globalThis.HubI18n?.t?.("app.3a2222fbb114") ?? ' · сохранённая история')}</a>`;
  }).join('') || (globalThis.HubI18n?.t?.("app.b4e73f30261b") ?? 'Подключённых проектов пока нет');
  const selected = catalog.projects.find(p => p.id === activeProject);
  $('#project-name').textContent = selected?.name || (globalThis.HubI18n?.t?.("app.51e140267931") ?? 'Выбрать проект');
  if (selected) {
    document.title = selected.name + ' · Project Hub';
    if (state?.project) state.project.name = selected.name;
  }
  if (!catalog.projects.some(p => p.id === activeProject)) {
    activeProject = null; state = null; stream?.close();
    document.title = 'Project Hub';
    const url = new URL(location.href); url.searchParams.delete('project'); history.replaceState(null, '', url);
    render();
    return false;
  }
  return true;
}
window.addEventListener('hub-projects-changed', () => {
  loadProjects().catch(error => { $('#project-discovery').textContent = (globalThis.HubI18n?.error?.(error) ?? error.message); });
});
window.addEventListener('hub-language-changed', () => {
  $('#navigation').dataset.page = '';
  render({background:true, localeChange:true});
  setConnection(connected);
  updateAnnouncement();
  updateFreshness();
  loadProjects(true).catch(error => { $('#project-discovery').textContent = (globalThis.HubI18n?.error?.(error) ?? error.message); });
});
document.addEventListener('click', event => {
  if (!$('#project-picker').contains(event.target)) $('#project-picker').open = false;
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && $('#project-picker').open) {
    $('#project-picker').open = false;
    $('#project-picker summary').focus();
  }
});
function refreshFromEvent(event) {
  try {
    const hint = JSON.parse(event.data);
    if (Object.hasOwn(hint, 'knowledgeRevision')) window.KnowledgeUI?.notify?.(activeProject, hint.knowledgeRevision);
    if (state && ['revision','coordinationRevision','titlesRevision','settingsRevision','relationsRevision'].every(key=>Object.hasOwn(hint,key)) &&
        hint.revision === state.revision && hint.coordinationRevision === (state.coordination?.revision ?? 0) &&
        hint.titlesRevision === (state.coordination?.titlesRevision ?? '') && hint.settingsRevision === (state.settings?.revision ?? null) &&
        hint.relationsRevision === (state.relationsRevision ?? null)) return;
  } catch { /* Older or malformed hints still require a fresh read. */ }
  refresh();
}
let streamRetryTimer = null, streamRetryDelay = 1000;
function scheduleStreamRetry(project, current) {
  if (project !== activeProject || stream !== current || streamRetryTimer !== null) return;
  const delay = streamRetryDelay;
  streamRetryDelay = Math.min(streamRetryDelay * 2, 10000);
  streamRetryTimer = setTimeout(() => {
    streamRetryTimer = null;
    if (project !== activeProject || stream !== current) return;
    current.close?.();
    openStream(project);
  }, delay);
}
function openStream(project) {
  if (project !== activeProject) return;
  const current = new EventSource(projectApi('/api/events'));
  stream = current;
  current.onopen = () => {
    if (project !== activeProject || stream !== current) return;
    streamRetryDelay = 1000;
    if (streamRetryTimer !== null) { clearTimeout(streamRetryTimer); streamRetryTimer = null; }
    setConnection(true);
  };
  current.onerror = () => {
    if (project !== activeProject || stream !== current) return;
    setConnection(false);
    if (current.readyState === EventSource.CLOSED) scheduleStreamRetry(project, current);
  };
  current.addEventListener('revision', refreshFromEvent);
}
async function startProject() {
  const project = activeProject;
  restoreUiState();
  await refresh();
  if (project !== activeProject) return;
  openStream(project);
}
document.addEventListener('DOMContentLoaded', async () => {
  try {
    if (activeProject) {
      // An explicit project is validated by its state endpoint. Discovery only
      // fills the picker and must not serialize the initial project/Git reads.
      await Promise.all([
        loadProjects(true).catch(error => { $('#project-discovery').textContent = (globalThis.HubI18n?.error?.(error) ?? error.message); }),
        startProject(),
      ]);
    } else if (await loadProjects(true)) await startProject();
  } catch (error) { showError((globalThis.HubI18n?.error?.(error) ?? error.message)); }
  finally {
    setInterval(() => loadProjects().catch(e => { $('#project-discovery').textContent = e.message; }), 10000);
  }
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
setInterval(updateFreshness, 15000);

const transferDialog = document.createElement('dialog');
transferDialog.className = 'transfer-dialog';
transferDialog.setAttribute('aria-label',(globalThis.HubI18n?.t?.("app.d230f0ae8043") ?? 'Перенос задачи'));
document.body.append(transferDialog);
async function openTransfer(taskId) {
  if (transferDialog.open) return;
  transferDialog.innerHTML = (globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.124976c21333",{v0:(uiIcon('close'))}) : `<h2>Перенос задачи</h2><p>Загрузка проектов…</p><button class="icon-button" data-close title="Закрыть" aria-label="Закрыть">${uiIcon('close')}</button>`);
  transferDialog.querySelector('[data-close]').onclick=()=>transferDialog.close();
  transferDialog.showModal();
  try {
    const catalog=await (await fetch('/api/v1/projects')).json();
    const options=catalog.projects.filter(p=>p.id!==activeProject && p.present);
    if (!transferDialog.open) return;
    transferDialog.innerHTML=(globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.beac0e65f6ef",{v0:(options.map(p=>`<option value="${escape(p.id)}">${escape(p.name)}</option>`).join('')),v1:(options.length?(globalThis.HubI18n?.t?.("app.f2a39ce40b34") ?? 'Выберите проект и проверьте перенос.'):(globalThis.HubI18n?.t?.("app.a534013716e3") ?? 'Других локальных проектов пока нет.')),v2:(options.length?'':'disabled'),v3:(uiIcon('transfer')),v4:(uiIcon('close'))}) : `<h2>Перенос задачи</h2><p>Задача сохранит план, историю и связи с чатами. Чаты и исходные файлы останутся на месте.</p><label>Целевой проект <select id="transfer-target">${options.map(p=>`<option value="${escape(p.id)}">${escape(p.name)}</option>`).join('')}</select></label><p id="transfer-details" role="status">${options.length?(globalThis.HubI18n?.t?.("app.f2a39ce40b34") ?? 'Выберите проект и проверьте перенос.'):(globalThis.HubI18n?.t?.("app.a534013716e3") ?? 'Других локальных проектов пока нет.')}</p><div><button class="icon-button" id="transfer-submit" title="Проверить перенос" aria-label="Проверить перенос" ${options.length?'':'disabled'}>${uiIcon('transfer')}</button> <button class="icon-button" data-close title="Отмена" aria-label="Отмена">${uiIcon('close')}</button></div>`);
    transferDialog.querySelector('[data-close]').onclick=()=>transferDialog.close();
    const select=$('#transfer-target'),button=$('#transfer-submit'),details=$('#transfer-details');
    let preview=null,request=null;
    const setTransferLabel = text => { button.title=text; button.setAttribute('aria-label',text); };
    select.onchange=()=>{preview=null;request=null;setTransferLabel((globalThis.HubI18n?.t?.("app.0ce20bfaf5c6") ?? 'Проверить перенос'));details.textContent=(globalThis.HubI18n?.t?.("app.588f9296246f") ?? 'Проверьте перенос в выбранный проект.');};
    button.onclick=async()=>{
      button.disabled=true;select.disabled=true;
      const committing=!!preview;
      try {
        const payload={source:activeProject,target:select.value,task:taskId};
        if (committing) Object.assign(payload,{expected:preview.revision,request});
        const response=await fetch('/api/v1/tasks/transfer'+(committing?'':'/preview'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        const result=await response.json();if(!response.ok)throw Error(result.error);
        if(committing){const url=new URL(location.href);url.searchParams.set('project',result.target);location.assign(url.href);return;}
        preview=result;request=crypto.randomUUID();
        details.textContent=(globalThis.HubI18n?.t ? globalThis.HubI18n.t("app.f6ca337ab735",{v0:(result.title),v1:(result.stages),v2:(result.events)}) : `«${result.title}»: ${result.stages} этапов, ${result.events} событий. История сохранится; ссылки на исходные файлы сохранят прежний проект.`);
        setTransferLabel((globalThis.HubI18n?.t?.("app.6fca7296b32d") ?? 'Подтвердить перенос'));
      } catch(error){details.textContent=(globalThis.HubI18n?.error?.(error) ?? error.message);preview=null;request=null;setTransferLabel((globalThis.HubI18n?.t?.("app.0ce20bfaf5c6") ?? 'Проверить перенос'));}
      finally{button.disabled=false;select.disabled=false;}
    };
  } catch(error){transferDialog.querySelector('p').textContent=(globalThis.HubI18n?.error?.(error) ?? error.message);}
}

globalThis.HubI18n?.onChange?.(()=>{Object.assign(labels,{
  planned: (globalThis.HubI18n?.t?.("app.4692f1b33927") ?? "Предстоит"),
  active: (globalThis.HubI18n?.t?.("app.59a28f1b11df") ?? "В работе"),
  queued: (globalThis.HubI18n?.t?.("app.b22a2454bd69") ?? "В очереди"),
  blocked: (globalThis.HubI18n?.t?.("app.5db21586e6b5") ?? "Есть препятствие"),
  done: (globalThis.HubI18n?.t?.("app.b459ff8f254e") ?? "Завершено"),
  cancelled: (globalThis.HubI18n?.t?.("app.23a2a9bfcf74") ?? "Отменено"),
  passed: (globalThis.HubI18n?.t?.("app.be625a64f643") ?? "Пройдено"),
  running: (globalThis.HubI18n?.t?.("app.599ca07b8dd2") ?? "Выполняется"),
  unknown: (globalThis.HubI18n?.t?.("app.8cf46ff28cc1") ?? "Результат неизвестен"),
  failed: (globalThis.HubI18n?.t?.("app.bf22dfeeba8b") ?? "Ошибка"),
  waiting: (globalThis.HubI18n?.t?.("app.89c9e3a11aee") ?? "Ожидает"),
  idle: (globalThis.HubI18n?.t?.("app.f4dff7d22ed4") ?? "Ответ завершён"),
  interrupted: (globalThis.HubI18n?.t?.("app.f7b2f77928af") ?? "Прерван"),
  closed: (globalThis.HubI18n?.t?.("app.32bb1c680f95") ?? "Сессия закрыта"),
});Object.assign(kindLabels,{
  "task.created": (globalThis.HubI18n?.t?.("app.756c6c64e23e") ?? "Новая задача"),
  "task.updated": (globalThis.HubI18n?.t?.("app.e97acacf9acf") ?? "Задача обновлена"),
  "task.reopened": (globalThis.HubI18n?.t?.("app.a2a4bf6e680e") ?? "Задача переоткрыта"),
  "task.status_changed": (globalThis.HubI18n?.t?.("app.5e6ee4b48ff8") ?? "Изменён статус задачи"),
  "task.type_changed": (globalThis.HubI18n?.t?.("app.9f1fe6d24245") ?? "Изменён тип задачи"),
  "task.priority_changed": (globalThis.HubI18n?.t?.("app.f72238b65172") ?? "Изменён приоритет задачи"),
  "task.parent_changed": (globalThis.HubI18n?.t?.("app.1344d008de05") ?? "Изменён родитель задачи"),
  "task.linked": (globalThis.HubI18n?.t?.("app.9ae1d1f1c567") ?? "Задачи связаны"),
  "task.unlinked": (globalThis.HubI18n?.t?.("app.6e0b5dcf13c5") ?? "Связь задач удалена"),
  "stage.updated": (globalThis.HubI18n?.t?.("app.50a759ac4169") ?? "Этап обновлён"),
  "stage.created": (globalThis.HubI18n?.t?.("app.46b65269f9fa") ?? "Этап добавлен"),
  "stage.deleted": (globalThis.HubI18n?.t?.("app.d4ec24da0fc5") ?? "Этап удалён из плана"),
  "stage.unlinked": (globalThis.HubI18n?.t?.("app.6b48c0310af5") ?? "Этап отвязан"),
  "stage.transferred": (globalThis.HubI18n?.t?.("app.cf4f5f8f1ec5") ?? "Этап перенесён"),
  "stage.exported": (globalThis.HubI18n?.t?.("app.e12d195ff80e") ?? "Этап перенесён из задачи"),
  "stage.imported": (globalThis.HubI18n?.t?.("app.068026c33a92") ?? "Этап перенесён в задачу"),
  "stage.restored": (globalThis.HubI18n?.t?.("app.d9a99eebd8cb") ?? "Этап восстановлен"),
  "work.started": (globalThis.HubI18n?.t?.("app.fd408eab202b") ?? "Работа начата"),
  "work.completed": (globalThis.HubI18n?.t?.("app.768257912b25") ?? "Шаг завершён"),
  "git.commit": "Git commit",
  "git.push": "Git push",
  "check.started": (globalThis.HubI18n?.t?.("app.69faab6e6901") ?? "Проверка запущена"),
  "check.passed": (globalThis.HubI18n?.t?.("app.7a780b2ed19f") ?? "Проверка пройдена"),
  "check.failed": (globalThis.HubI18n?.t?.("app.1cbcef8251cf") ?? "Проверка не прошла"),
  "check.interrupted": (globalThis.HubI18n?.t?.("app.aef23a5d2d28") ?? "Проверка прервана"),
  "check.unknown": (globalThis.HubI18n?.t?.("app.09a8377bf26f") ?? "Результат проверки неизвестен"),
  "check.corrected": (globalThis.HubI18n?.t?.("app.adc4ed716c1a") ?? "Результат проверки исправлен"),
  finding: (globalThis.HubI18n?.t?.("app.574d43b44984") ?? "Наблюдение"),
  decision: (globalThis.HubI18n?.t?.("app.199d6db958cd") ?? "Решение"),
  note: (globalThis.HubI18n?.t?.("app.1d80e1757a7a") ?? "Запись"),
  'task.transferred': (globalThis.HubI18n?.t?.("app.d230f0ae8043") ?? 'Перенос задачи'),
});navigation.splice(0,navigation.length,...[
  ["overview", (globalThis.HubI18n?.t?.("app.7641ad9bafb2") ?? "Обзор проекта")],
  ["tasks", (globalThis.HubI18n?.t?.("app.03cc1c2d5ac2") ?? "Задачи")],
  ["git", "Git"],
  ["coordination", (globalThis.HubI18n?.t?.("app.b5121e526dd9") ?? "Чаты")],
  ["history", (globalThis.HubI18n?.t?.("app.5143a08843c2") ?? "История разработки")],
  ["checks", (globalThis.HubI18n?.t?.("app.bb1b79b14c91") ?? "Проверки")],
  ["settings", (globalThis.HubI18n?.t?.("app.985b5e0f2ccf") ?? "Настройки")],
  ["projects", (globalThis.HubI18n?.t?.("app.5029f02d0a94") ?? "Проекты")],
  ["architecture", (globalThis.HubI18n?.t?.("app.1898e1901dcd") ?? "Архитектура и код")],
  ["docs", (globalThis.HubI18n?.t?.("app.b123be6f8236") ?? "Документация")],
  ["actions", (globalThis.HubI18n?.t?.("app.cad123465b9e") ?? "Действия"), (globalThis.HubI18n?.t?.("app.295bd5ba2d79") ?? "позже")],
]);Object.assign(blockerLabels,{technical: (globalThis.HubI18n?.t?.("app.61d077d3515c") ?? 'Техническое препятствие'), user_input: (globalThis.HubI18n?.t?.("app.2ae8bedad7c9") ?? 'Нужен ответ пользователя'), administrative: (globalThis.HubI18n?.t?.("app.067c4b855cc3") ?? 'Проблема учёта')});});
