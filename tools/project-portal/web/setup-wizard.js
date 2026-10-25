"use strict";

/* The setup window owns its DOM; task-view refreshes never replace its inputs. */
(function (global) {
  const words = {
    title:['Мастер подключения','Connection wizard'], open:['Открыть мастер','Open wizard'], resume:['Продолжить настройку','Resume setup'],
    entry:['Подключите приложение и настройте запросы к модели.','Connect an application and configure model requests.'],
    saved:['Прогресс сохранён. Можно продолжить с текущего шага.','Progress is saved. Resume from your current step.'],
    finished:['Настройка завершена. Можно подключить ещё приложение.','Setup is complete. You can connect another application.'],
    loading:['Загрузка состояния…','Loading setup…'], working:['Сохранение…','Saving…'], next:['Далее','Next'], back:['Назад','Back'],
    later:['Позже','Later'], finish:['Открыть портал','Open portal'], close:['Закрыть и продолжить позже','Close and resume later'],
    reference:['Позже:','Find this later:'], newTab:['в новой вкладке','in a new tab'],
    general:['Настройки → Общие','Settings → General'], apps:['Настройки → Агенты и подключения → Приложения','Settings → Agents and connections → Applications'],
    models:['Настройки → Агенты и подключения → Запросы к моделям','Settings → Agents and connections → Model requests'],
    projects:['Проекты','Projects'], controlRef:['Настройки → Агенты и подключения → Приложения → Codex → Управление из Hub','Settings → Agents and connections → Applications → Codex → Control from Hub'],
    start:['Начало','Start'], application:['Приложение','Application'], modelSection:['Модели','Models'], modelRequests:['Запросы к моделям','Model requests'], modelCheck:['Проверка модели','Model check'], chats:['Чаты Codex','Codex chats'], result:['Результат','Result'],
    copyTitle:['Скопируйте инструкцию','Copy the instructions'], copyHelp:['Отправьте этот текст в приложение.','Send this text to the application.'],
    welcome:['Настроим Project Hub','Set up Project Hub'], welcomeHelp:['Подключите приложение, в котором работаете с AI.','Connect the application where you work with AI.'],
    welcomeApp:['Подключите Codex или другое приложение','Connect Codex or another application'], welcomeAppHelp:['Передайте приглашение в чат нужного проекта.','Send the invitation to a chat in the intended project.'],
    welcomeProject:['Проект появится автоматически','Your project appears automatically'], welcomeProjectHelp:['Hub создаст проект или найдёт уже существующий.','Hub creates the project or finds the existing one.'],
    welcomeModel:['Выберите модель · по желанию','Choose a model · optional'], welcomeModelHelp:['Для самостоятельных исследований из Hub.','For independent research from Hub.'],
    again:['Что настроим дальше?','What would you like to set up?'], againHelp:['Рабочие подключения и проекты сохранятся.','Existing connections and projects are preserved.'],
    addApp:['Подключить ещё приложение','Connect another application'], inspect:['Проверить подключение','Check connection'], manual:['Проект вручную','Manual project'],
    appTitle:['Какое приложение подключаем?','Which application are you connecting?'], appHelp:['Выберите вариант подключения.','Choose how to connect.'], other:['Другое приложение','Another application'],
    codexHelp:['Поддерживается · запуск чатов из Hub','Supported · start chats from Hub'], otherHelp:['MCP · без запуска чатов из Hub','MCP · no chats started from Hub'],
    otherNotice:['Для другого приложения нужна поддержка MCP по HTTP. Открытие чатов из Hub для него не поддерживается.','Another application needs HTTP MCP support. Starting its chats from Hub is not supported.'],
    inviteTitle:['Передайте приглашение в чат','Send the invitation to a chat'], inviteHelp:['Отправьте текст в чат нужного проекта. Hub создаст проект или найдёт существующий.','Send the text to a chat in the intended project. Hub creates or finds that project.'],
    createInvite:['Создать приглашение','Create invitation'], newInvite:['Создать новое приглашение','Create a new invitation'], copy:['Скопировать текст','Copy instructions'], copied:['Текст скопирован. Передайте его в чат проекта.','Instructions copied. Send them to the project chat.'],
    copyFallback:['Не удалось скопировать. Выделите ссылку и скопируйте её вручную.','Copy failed. Select the link and copy it manually.'],
    invitePending:['Ждём подключения и сведений о проекте.','Waiting for the application and project details.'],
    inviteUsed:['Приглашение использовано. Проверьте результат подключения.','Invitation used. Check the connection result.'],
    inviteExpired:['Приглашение истекло. Создайте новое.','Invitation expired. Create a new one.'],
    inviteRevoked:['Приглашение отозвано. Создайте новое.','Invitation revoked. Create a new one.'],
    inviteMissing:['Если вы уже отправили приглашение, проверьте подключение. Для повторного копирования создайте новое.','If you already sent the invitation, check the connection. To copy a link again, create a new invitation.'],
    link:['Ссылка-приглашение','Invitation link'], recover:['Восстановить доступ','Restore access'],
    verifyTitle:['Проверим подключение','Check the connection'], verifyHelp:['Доступ приложения и создание проекта проверяются отдельно.','Application access and project creation are checked separately.'],
    access:['Доступ к инструментам','Tool access'], rules:['Постоянные правила','Persistent instructions'], project:['Проект в Hub','Project in Hub'],
    confirmed:['Подтверждён','Confirmed'], waiting:['Ждём запрос','Waiting for a request'], reported:['Сообщено: сохранены','Reported as saved'], unknown:['Не сообщено','Not reported'],
    notFound:['Не определён','Not identified'], chooseProject:['Выберите проект','Choose a project'], refresh:['Обновить проверку','Refresh checks'],
    newChat:['Запрос в новый чат','New-chat instructions'], freshConfirmed:['Загрузка правил в новом чате подтверждена.','Instruction loading in a new chat is confirmed.'],
    freshPending:['Проверку правил в новом чате можно выполнить позже.','You can verify instruction loading in a new chat later.'],
    projectAutomatic:['Проект уже в Hub. Ручное добавление пропустим.','The project is in Hub. Manual creation will be skipped.'],
    projectMissing:['Если проект не определён, дальше можно повторить проверку или добавить его вручную.','If the project is missing, you can check again or add it manually later.'],
    existingConnection:['Существующее подключение','Existing connection'], pickConnection:['Выберите подключение для проверки','Choose a connection to check'],
    chatgptTitle:['Подключите ChatGPT','Connect ChatGPT'], chatgptHelp:['Hub сможет выполнять исследования через ваш аккаунт, пока портал запущен.','Hub can run research through your account while the portal is running.'],
    optional:['По желанию','Optional'], signIn:['Войти через ChatGPT','Sign in with ChatGPT'], authOpen:['Открыть страницу входа','Open sign-in page'],
    authPending:['Вход открыт в другой вкладке. Вернитесь сюда после авторизации.','Sign-in opened in another tab. Return here after authorizing.'],
    account:['Аккаунт','Account'], model:['Модель','Model'], chooseModel:['Выберите модель','Choose a model'],
    authCheck:['Проверить авторизацию и модели','Verify sign-in and models'], authNotReady:['Авторизация или список моделей ещё не подтверждены.','Sign-in or the model list is not yet verified.'],
    connected:['Подключено','Connected'], saveModel:['Сохранить и использовать','Save and use'], useModel:['Использовать','Use connection'],
    modelProbe:['Проверить модель','Probe model'], modelImpact:['Проверка отправит запрос по лимиту подписки или тарифу сервиса.','A probe uses your subscription allowance or the service tariff.'],
    passed:['Ответ получен','Response received'], notChecked:['Сохранено · не проверено','Saved · not checked'], failed:['Проверка не прошла. Подробности доступны в настройках.','The check failed. Details are available in settings.'],
    probeUnknown:['Результат запроса неизвестен. Обновите его статус перед новой проверкой.','The request outcome is unknown. Refresh its status before another probe.'],
    probeStatus:['Обновить статус запроса','Refresh request status'], apiTitle:['Добавьте API-ключ','Add an API key'],
    apiHelp:['Это альтернативный способ или ещё один сервис для запросов Hub.','Use this as an alternative or an additional service for Hub requests.'],
    apiAlready:['Подключение с API-ключом уже есть. Можно использовать его или добавить другое.','An API-key connection already exists. Use it or add another.'],
    addKey:['Добавить другое подключение','Add another connection'], protocol:['Сервис / протокол','Service / protocol'], compatible:['Совместимый с OpenAI','OpenAI compatible'],
    keyTitle:['Сохраните подключение к модели','Save the model connection'], keyHelp:['Ключ хранится в закрытых настройках Hub. В прогресс мастера он не записывается.','The key is stored in private Hub settings, never in wizard progress.'],
    endpoint:['Адрес сервиса · необязательно','Service address · optional'], key:['API-ключ','API key'], direct:['Напрямую','Direct'], system:['Системная сеть / прокси','System network / proxy'], network:['Сеть','Network'],
    endpointDefault:['Стандартный адрес сервиса','Default service address'], modelPlaceholder:['Имя модели у выбранного сервиса','Model name at the selected service'],
    controlTitle:['Запускайте задачи из Hub','Start tasks from Hub'], controlHelp:['Для создания чатов в Codex нужен отдельный локальный адаптер.','Creating Codex chats requires a separate local adapter.'],
    adapter:['Адаптер Codex','Codex adapter'], configured:['Настроен','Configured'], missingAdapter:['Не подключён','Not connected'], reply:['Ответ из тестового чата','Reply from a test chat'],
    controlPrompt:['Запрос для настройки Codex','Codex setup instructions'], controlTest:['Проверить управление','Test chat control'],
    controlImpact:['Проверка создаст отдельный чат в выбранном проекте Codex и отправит тестовое сообщение.','The check creates a separate chat in the selected Codex project and sends a test message.'],
    controlMissing:['Передайте запрос в Codex и выберите разрешённые папки. Затем обновите проверку.','Send the instructions to Codex and choose allowed folders. Then refresh the checks.'],
    noControl:['Для этого приложения чаты из Hub не поддерживаются.','Starting chats from Hub is not supported for this application.'],
    projectTitle:['Проект уже в Hub','The project is in Hub'], projectHelp:['Повторно создавать его не требуется.','There is no need to create it again.'],
    projectSelectHelp:['У приложения несколько проектов. Выберите нужный; существующие проекты сохранятся.','The application has multiple projects. Choose the intended one; existing projects are preserved.'],
    projectNoneTitle:['Проект не определён','Project not identified'], projectNoneHelp:['Проверьте подключение из чата нужного проекта или добавьте проект вручную.','Check setup from the intended project chat, or add the project manually.'],
    retryProject:['Проверить ещё раз','Check again'], addManual:['Добавить вручную','Add manually'], manualTitle:['Создайте отдельный проект','Create a separate project'],
    manualHelp:['Для исследований и задач без среды разработки или при неудачном создании из чата.','For research and tasks without a development environment, or if creation from a chat failed.'],
    projectName:['Название проекта','Project name'], folder:['Папка исходников · необязательно','Source folder · optional'], folderChoose:['Выбрать папку','Choose folder'], folderLater:['Для исследований папка исходников не нужна.','Research does not require a source folder.'], createProject:['Создать проект','Create project'],
    manualSaved:['Проект добавлен в Hub. Привязку приложения можно завершить из чата проекта.','Project added to Hub. Complete the application binding from its project chat.'],
    resultTitle:['Можно начинать работу','Ready to get started'], resultHelp:['Показаны сохранённые настройки и фактические результаты проверок.','Saved settings and actual check results are shown below.'],
    deferred:['Можно настроить позже','Can be configured later'], appCount:['Подключено приложений: {count}','Connected applications: {count}'],
    projectCount:['Проектов в Hub: {count}','Projects in Hub: {count}'], checked:['Проверено','Verified'],
    connectionRevoked:['Доступ этого приложения отозван. Можно восстановить его отдельным приглашением.','Access for this application was revoked. Restore it with a separate invitation.'],
    retry:['Повторить тот же запрос','Retry the same request'], error:['Не удалось выполнить действие. Обновите состояние или повторите запрос.','The action could not be completed. Refresh the state or retry the request.'],
    uncertain:['Ответ не получен. Состояние изменения пока неизвестно; повтор использует тот же запрос.','No response was received. The outcome is unknown; retrying uses the same request.'],
    conflict:['Настройка изменена в другой вкладке. Состояние обновлено; проверьте текущий шаг.','Setup changed in another tab. The state has been refreshed; review this step.'],
    blocked:['Сейчас выполняется другая операция хранения. Повторите действие позже.','A storage operation is in progress. Try again later.'],
    unavailable:['Мастер временно недоступен. Попробуйте открыть его снова.','The wizard is temporarily unavailable. Try opening it again.'],
    inviteInstructions:['Подключи Project Hub по приглашению: {url}. Сохрани постоянные правила приложения, проверь доступ к инструментам Hub и создай или найди в Hub проект текущего чата. Сообщи отдельно результат подключения и привязки проекта.','Connect Project Hub using this invitation: {url}. Save the application-wide instructions, verify Hub tool access, and create or find this chat’s project in Hub. Report the application connection and project binding separately.'],
    freshInstructions:['В новом чате проекта проверь подключение Project Hub: прочитай постоянные инструкции, получи каталог инструментов, выполни hub_instructions и hub_context с действительной привязкой текущего проекта. Сообщи проверку загрузки правил через persistentInstructions.loadVerified только после фактической проверки.','In a new project chat, verify Project Hub: read persistent instructions, discover the tools, and call hub_instructions and hub_context using the current project’s actual binding. Report persistentInstructions.loadVerified only after verifying that instructions loaded.'],
    controlInstructions:['Подключи локальный адаптер Codex к Project Hub {origin}, используя существующее подключение {connection}. Сначала уточни разрешённые папки проектов. Сохрани настройки адаптера в Hub и сообщи результат. Не запускай тестовый чат: проверку обмена я запущу отдельно в мастере.','Connect the local Codex adapter to Project Hub at {origin}, using existing connection {connection}. First confirm allowed project folders. Save the adapter settings in Hub and report the result. Do not start a test chat; I will run that check separately in the wizard.'],
  };
  const view = {envelope:null, initPromise:null, dialog:null, open:false, busy:false, pending:null, error:'', notice:'',
    catalog:{bindings:[],projects:[]}, providers:{items:[],default:'none'}, accounts:[], attempt:null,
    invitationUrl:'', fields:{}, root:null, addApi:false, timer:null, focus:null, readsFailed:false, probe:null, copyText:''};
  const esc = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const t=(key,params={})=>String(words[key]?.[global.HubI18n?.locale==='en'?1:0]||key).replace(/\{(\w+)\}/g,(_,k)=>String(params[k]??''));
  const id=()=>String(global.crypto?.randomUUID?.()||`${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`).replace(/-/g,'').padEnd(32,'0').slice(0,32);
  const progress=()=>view.envelope?.progress||{step:'welcome',application:'codex'};
  const oauth=item=>item?.authentication?.method==='chatgpt_oauth';
  const bindings=()=>Array.isArray(view.catalog.bindings)?view.catalog.bindings:[];
  const connection=()=>bindings().find(row=>row.id===(view.envelope?.invitation?.connectionId||progress().connectionId));
  const projectBindings=()=>{const row=connection();return (row?.projectBindings||[]).filter(b=>b.status==='active'&&!b.pendingRelocation);};
  const projectChoices=()=>{const row=connection(),ids=new Set(projectBindings().map(b=>b.project));if(row?.project)ids.add(row.project);return (view.catalog.projects||[]).filter(p=>ids.has(p.id));};
  const selectedProject=()=>{const p=progress(),choices=projectChoices();if(p.projectId&&(p.standalone||p.manualProject))return (view.catalog.projects||[]).find(row=>row.id===p.projectId);return choices.find(row=>row.id===p.projectId)||(choices.length===1?choices[0]:null);};
  const activeProvider=()=>view.providers.items.find(item=>item.id===(progress().providerId||view.providers.default));
  const providerFor=kind=>{const selected=activeProvider();return selected&&oauth(selected)===(kind==='oauth')?selected:view.providers.items.find(item=>oauth(item)===(kind==='oauth'));};
  const account=()=>view.accounts.find(a=>a.id===(view.fields.accountId||progress().accountId||providerFor('oauth')?.authentication?.accountId))||view.accounts.find(a=>a.status==='connected'&&a.planUsageEnabled)||view.accounts[0];
  const accountModels=()=>Array.isArray(account()?.models)?account().models:[];
  const chosenModel=()=>{const value=view.fields.model??progress().model??providerFor('oauth')?.model;return accountModels().some(m=>m.slug===value)?value:accountModels()[0]?.slug||'';};
  const observed=()=>!!connection()&&!connection().revoked&&connection().capabilities?.mcp?.state==='verified';
  const isCodex=()=>connection()?.client==='codex'||connection()?.profile?.host==='codex';
  const canControl=()=>isCodex()&&!connection()?.revoked&&connection()?.controlStatus?.canTest===true;
  const controlPassed=()=>isCodex()&&!connection()?.revoked&&connection()?.features?.callback?.state==='verified';
  const modelPassed=item=>item?.availability?.status==='available';
  const probeUnresolved=item=>['checking','outcome_unknown'].includes(item?.availability?.status)||view.probe?.id===item?.id&&['running','outcome_unknown','interrupted'].includes(view.probe?.status);
  const modelStatus=item=>modelPassed(item)?'passed':probeUnresolved(item)?'probeUnknown':!item?.availability?.status||['not_checked','settings_changed'].includes(item.availability.status)?'notChecked':'failed';
  function route(){
    const p=progress(),apiKey=p.step==='api-key'||view.addApi?['api-key']:[],project=!selectedProject()||p.step==='projects'?['projects']:[];
    if(p.standalone)return ['welcome','projects','chatgpt','api',...apiKey,'finish'];
    if(p.additional)return ['welcome','app','invite','verify',...(p.application==='codex'?['control']:[]),...project,'finish'];
    return ['welcome','app','invite','verify','chatgpt','api',...apiKey,...(p.application==='codex'?['control']:[]),...project,'finish'];
  }
  async function request(url,body){
    let response,value;
    try { response=await global.fetch(url,{cache:'no-store',credentials:'same-origin',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})}); }
    catch(_){throw Object.assign(Error(t('uncertain')),{uncertain:!!body});}
    try { value=await response.json(); } catch(_){throw Object.assign(Error(t('uncertain')),{uncertain:!!body});}
    if(!response.ok)throw Object.assign(Error(t(response.status===409?'conflict':response.status===423?'blocked':'error')),{code:value?.error,status:response.status,uncertain:!!body&&response.status>=500});
    if(!value||typeof value!=='object'||Array.isArray(value))throw Object.assign(Error(t('uncertain')),{uncertain:!!body});
    return value;
  }
  function validEnvelope(value){if(value.schemaVersion!==1||!Number.isInteger(value.revision)||!value.progress||typeof value.progress.step!=='string')throw Error(t('unavailable'));return value;}
  async function save(patch){
    const body={action:'save',expected:view.envelope.revision,requestId:id(),patch};
    try { view.envelope=validEnvelope(await request('/api/v1/setup-wizard',body)); }
    catch(error){
      if(error.status===409){view.envelope=validEnvelope(await request('/api/setup-wizard'));if(Object.entries(patch).every(([k,v])=>progress()[k]===v))return;}
      throw error;
    }
  }
  async function perform(operation){
    view.pending=operation;
    try {
      const value=await request(operation.url,operation.body);
      if(!operation.valid(value))throw Object.assign(Error(t('uncertain')),{uncertain:true});
      view.pending=null;await operation.done(value);
    } catch(error){if(!error.uncertain||operation.retrySafe===false)view.pending=null;throw error;}
  }
  async function refresh(){
    const results=await Promise.allSettled([request('/api/setup-wizard'),request('/api/connections'),request('/api/agent-providers'),request('/api/chatgpt-auth'),request('/api/projects')]);
    if(results[0].status==='fulfilled')view.envelope=validEnvelope(results[0].value);else throw results[0].reason;
    view.readsFailed=results.slice(1).some(item=>item.status==='rejected');
    if(results[1].status==='fulfilled'&&Array.isArray(results[1].value.bindings))view.catalog=results[1].value;
    if(results[2].status==='fulfilled'&&Array.isArray(results[2].value.items))view.providers=results[2].value;
    if(results[3].status==='fulfilled'&&Array.isArray(results[3].value.accounts))view.accounts=results[3].value.accounts;
    if(results[4].status==='fulfilled'&&Array.isArray(results[4].value.projects))view.catalog.projects=results[4].value.projects;
    if(progress().probeRequestId){try{view.probe=await request('/api/agent-providers?requestId='+encodeURIComponent(progress().probeRequestId));}catch(_){view.readsFailed=true;}}
    const p=progress(),patch={},row=connection(),project=selectedProject();
    if(view.envelope.invitation?.connectionId&&p.connectionId!==view.envelope.invitation.connectionId)patch.connectionId=view.envelope.invitation.connectionId;
    if(project&&p.projectId!==project.id)patch.projectId=project.id;
    if(p.authAttemptId){
      try {view.attempt=await request('/api/chatgpt-auth?attemptId='+encodeURIComponent(p.authAttemptId));if(view.attempt.status==='completed'&&view.attempt.accountId&&p.accountId!==view.attempt.accountId)patch.accountId=view.attempt.accountId;}catch(_){view.attempt=null;}
    }
    if(Object.keys(patch).length)await save(patch);
    if(row?.revoked)view.notice=t('connectionRevoked');
    updateEntry();
  }
  async function run(fn){
    if(view.busy)return;view.busy=true;view.error='';view.notice='';render();
    try {await fn();}catch(error){view.error=error.message||t('error');}
    finally {view.busy=false;render();schedule();}
  }
  async function init(){
    if(view.initPromise)return view.initPromise;
    view.initPromise=(async()=>{
      try {
        view.envelope=validEnvelope(await request('/api/setup-wizard'));
        if(view.envelope.autoEligible){
          const body={action:'claim',expected:view.envelope.revision,requestId:id()};
          try {view.envelope=validEnvelope(await request('/api/v1/setup-wizard',body));if(view.envelope.claimed)await open(false);}
          catch(error){if(error.status===409)view.envelope=validEnvelope(await request('/api/setup-wizard'));else throw error;}
        }
      }catch(error){view.error=error.message||t('unavailable');}
      updateEntry();
    })();return view.initPromise;
  }
  function heading(title,help,kicker='optional'){return `<div class="setup-step-heading"><span>${esc(t(kicker))}</span><h2 id="setup-step-title">${esc(t(title))}</h2><p>${esc(t(help))}</p></div>`;}
  function button(action,label,primary=false,disabled=false){return `<button type="button" data-setup-action="${action}" class="${primary?'primary':''}" ${disabled||view.busy||(view.pending&&action!=='retry')?'disabled':''}>${esc(t(label))}</button>`;}
  function row(label,value,good=false){return `<div class="setup-row"><span>${esc(t(label))}</span><strong class="${good?'setup-good':''}" aria-label="${esc(value)}">${esc(value)}</strong></div>`;}
  function field(name,label,input){return `<label class="setup-field"><span>${esc(t(label))}</span>${input}</label>`;}
  function input(name,value='',type='text',placeholder=''){return `<input data-setup-field="${name}" name="${name}" type="${type}" value="${esc(value)}" ${placeholder?`placeholder="${esc(t(placeholder))}"`:''} ${type==='password'?'autocomplete="new-password"':'maxlength="160"'} ${view.busy||view.pending?'disabled':''}>`;}
  function select(name,options,value){return `<select data-setup-field="${name}" name="${name}" ${view.busy||view.pending?'disabled':''}>${options.map(([id,label])=>`<option value="${esc(id)}" ${id===value?'selected':''}>${esc(label)}</option>`).join('')}</select>`;}
  const actions=html=>`<div class="setup-step-actions">${html}</div>`;
  const help=key=>`<p class="setup-help">${esc(t(key))}</p>`;
  function safeAuthPath(){const attempt=view.attempt;const path=attempt?.attemptId?'/auth/chatgpt/authorize?attemptId='+encodeURIComponent(attempt.attemptId):'';return attempt?.status==='pending'&&/^[a-f0-9]{32}$/.test(attempt.attemptId)&&(!attempt.authorizePath||attempt.authorizePath===path)?path:'';}
  function modelTools(item){
    if(!item)return '';
    return row('model',item.model,modelPassed(item))+row('modelCheck',t(modelStatus(item)),modelPassed(item))+
      (probeUnresolved(item)?actions(button('probe-status','probeStatus',true))+help('probeUnknown'):actions(button('probe','modelProbe',true))+help('modelImpact'));
  }
  function content(){
    const p=progress(),rowConnection=connection(),project=selectedProject(),configured=bindings().filter(r=>!r.revoked),apiItem=providerFor('api'),oauthItem=providerFor('oauth');
    if(view.copyText)return heading('copyTitle','copyHelp','application')+`<p class="setup-copy-text">${esc(view.copyText)}</p>`;
    if(p.step==='welcome')return heading(configured.length?'again':'welcome',configured.length?'againHelp':'welcomeHelp','start')+
      (configured.length?row('application',t('appCount',{count:configured.length}),true)+row('projects',t('projectCount',{count:(view.catalog.projects||[]).length}),true)+actions(button('add-app','addApp',true)+button('choose-connection','inspect')):
      `<div class="setup-purpose"><strong>${esc(t('welcomeApp'))}</strong><p>${esc(t('welcomeAppHelp'))}</p></div><div class="setup-purpose"><strong>${esc(t('welcomeProject'))}</strong><p>${esc(t('welcomeProjectHelp'))}</p></div><div class="setup-purpose"><strong>${esc(t('welcomeModel'))}</strong><p>${esc(t('welcomeModelHelp'))}</p></div>`);
    if(p.step==='app')return heading('appTitle','appHelp','application')+`<div class="setup-application-choices">${[['codex','Codex','codexHelp'],['other',t('other'),'otherHelp']].map(([value,label,description])=>`<button type="button" data-setup-application="${value}" aria-pressed="${p.application===value}" ${view.busy||view.pending?'disabled':''}><strong>${esc(label)}</strong><small>${esc(t(description))}</small></button>`).join('')}</div>`+help('otherNotice');
    if(p.step==='invite'){
      const state=view.envelope.invitation?.state,hasLink=!!view.invitationUrl,used=state==='used',bad=['expired','revoked','missing'].includes(state);
      return heading('inviteTitle','inviteHelp','application')+(hasLink?field('invitation','link',`<input data-setup-invitation readonly value="${esc(view.invitationUrl)}" aria-label="${esc(t('link'))}">`):'')+
        help(used?'inviteUsed':state==='expired'?'inviteExpired':state==='revoked'?'inviteRevoked':p.invitationId?(hasLink?'invitePending':'inviteMissing'):'inviteHelp')+
        actions(hasLink&&!bad&&!used?button('copy-invite','copy',true):button('invite',p.invitationId?'newInvite':'createInvite',true))+
        (hasLink&&!bad&&!used?help('invitePending'):'');
    }
    if(p.step==='verify'){
      const instructions=rowConnection?.profile?.persistentInstructions;
      if(view.fields.chooseConnection)return heading('pickConnection','verifyHelp','application')+field('connectionId','existingConnection',select('connectionId',[['',t('pickConnection')],...configured.map(item=>[item.id,item.client||t('other')])],p.connectionId||''));
      if(rowConnection?.revoked)return heading('verifyTitle','connectionRevoked','application')+actions(button('recover','recover',true));
      return heading('verifyTitle','verifyHelp','application')+row('access',t(observed()?'confirmed':'waiting'),observed())+
        row('rules',t(instructions?.status==='saved'?'reported':'unknown'),instructions?.status==='saved')+row('project',project?.name||t(projectChoices().length>1?'chooseProject':'notFound'),!!project)+
        actions(button('refresh','refresh',true)+button('fresh-chat','newChat',false,!rowConnection))+
        help(project?'projectAutomatic':'projectMissing')+help(instructions?.loadVerified===true?'freshConfirmed':'freshPending');
    }
    if(p.step==='chatgpt'){
      const auth=account(),models=accountModels(),valid=auth?.status==='connected'&&auth.planUsageEnabled===true;
      const existing=oauthItem&&oauthItem.authentication?.accountId===auth?.id&&oauthItem.model===chosenModel();
      return heading('chatgptTitle','chatgptHelp')+(auth?field('accountId','account',select('accountId',view.accounts.map(a=>[a.id,a.label||a.email||t('account')]),auth.id)):'')+
        (valid&&models.length?field('model','model',select('model',models.map(item=>[item.slug,item.display_name||item.name||item.slug]),chosenModel())):
          field('networkMode','network',select('networkMode',[['direct',t('direct')],['system',t('system')]],view.fields.networkMode||p.networkMode||'direct')))+
        (view.attempt?.status==='pending'?help('authPending')+`<a href="${esc(safeAuthPath())}" target="_blank" rel="noopener noreferrer">${esc(t('authOpen'))} ↗</a>`:
          actions(valid&&models.length?button(existing?'use-oauth':'save-oauth',existing?'useModel':'saveModel',true)+(existing?button(probeUnresolved(oauthItem)?'probe-status':'probe-oauth',probeUnresolved(oauthItem)?'probeStatus':'modelProbe'):''):button('sign-in','signIn',true)))+
        (!valid&&auth&&view.attempt?.status!=='pending'?actions(button('auth-models','authCheck')):'')+(valid&&!models.length?actions(button('auth-models','authCheck'))+help('authNotReady'):'')+
        (existing?help(probeUnresolved(oauthItem)?'probeUnknown':'modelImpact')+(modelPassed(oauthItem)?help('passed'):''):'');
    }
    if(p.step==='api')return heading('apiTitle','apiHelp')+(apiItem&&!view.addApi?row('model',apiItem.model,modelPassed(apiItem))+help('apiAlready')+actions(button('use-api','useModel',true)+button('add-api','addKey')):
      field('providerKind','protocol',select('providerKind',[['responses','OpenAI Responses'],['anthropic','Anthropic'],['gemini','Gemini'],['chat',t('compatible')]],view.fields.providerKind||p.providerKind||'responses'))+
      field('model','model',input('model',view.fields.apiModel??(p.providerKind?p.model:'')??'','text','modelPlaceholder')));
    if(p.step==='api-key'){
      if(!view.addApi&&p.providerId&&apiItem?.id===p.providerId)return heading('keyTitle','keyHelp')+modelTools(apiItem);
      return heading('keyTitle','keyHelp')+field('endpoint','endpoint',input('endpoint',view.fields.endpoint||'','url','endpointDefault'))+
        `<div class="setup-form-grid">${field('apiKey','key',input('apiKey',view.fields.apiKey||'','password'))}${field('networkMode','network',select('networkMode',[['direct',t('direct')],['system',t('system')]],view.fields.networkMode||p.networkMode||'direct'))}</div>`+
        actions(button('save-api','saveModel',true,!view.fields.apiKey));
    }
    if(p.step==='control'&&rowConnection&&!isCodex())return heading('controlTitle','noControl')+actions(button('refresh','refresh'));
    if(p.step==='control')return heading('controlTitle','controlHelp')+row('adapter',t(rowConnection?.control?.hasCredential?'configured':'missingAdapter'),!!rowConnection?.control?.hasCredential)+row('reply',t(controlPassed()?'passed':'notChecked'),controlPassed())+
      (canControl()?actions(button('control-test','controlTest',true)+button('refresh','refresh'))+help('controlImpact'):
        actions(button('control-prompt','controlPrompt',true,!rowConnection)+button('refresh','refresh'))+help('controlMissing'));
    if(p.step==='projects'){
      if(project)return heading('projectTitle','projectHelp','projects')+row('project',project.name,true)+help(p.manualProject?'manualSaved':'projectAutomatic');
      if(projectChoices().length>1&&!p.manualProject)return heading('chooseProject','projectSelectHelp','projects')+field('projectId','project',select('projectId',[['',t('chooseProject')],...projectChoices().map(item=>[item.id,item.name])],p.projectId||''));
      if(!p.manualProject&&!p.standalone)return heading('projectNoneTitle','projectNoneHelp','projects')+actions(button('refresh','retryProject',true)+button('manual-project','addManual'));
      return heading('manualTitle','manualHelp','projects')+field('manualProjectName','projectName',input('manualProjectName',view.fields.manualProjectName||p.manualProjectName||''))+
        field('root','folder',`<div class="setup-folder-control">${input('root',view.root??p.manualProjectRoot??'')}${button('folder','folderChoose')}</div>`)+help('folderLater')+
        actions(button('create-project','createProject',true,!(view.fields.manualProjectName||p.manualProjectName||'').trim()));
    }
    const provider=activeProvider();
    return heading('resultTitle','resultHelp','result')+row('application',rowConnection?.client||t('appCount',{count:configured.length}),observed())+
      row('modelRequests',provider?`${provider.name} · ${t(modelStatus(provider))}`:t('deferred'),modelPassed(provider))+
      row('chats',t(p.application!=='codex'?'noControl':controlPassed()?'passed':'deferred'),controlPassed())+row('project',project?.name||t('notFound'),!!project)+actions(button('add-app','addApp'));
  }
  function reference(){const p=progress(),row=connection(),base=global.location?.pathname||'/';const data=p.step==='projects'?['projects','#projects']:['chatgpt','api','api-key'].includes(p.step)?['models','#settings/agents/models']:p.step==='control'?['controlRef',row?`#settings/agents/apps/${encodeURIComponent(row.id)}/control`:'#settings/agents/apps']:['app','invite','verify'].includes(p.step)?['apps','#settings/agents/apps']:['general','#settings'];return `<a href="${esc(base+data[1])}" target="_blank" rel="noopener noreferrer" aria-label="${esc(t(data[0])+', '+t('newTab'))}">${esc(t(data[0]))} ↗</a>`;}
  function entry(){return `<section class="card setup-entry" data-setup-entry><div><h2>${esc(t('title'))}</h2><p>${esc(t('entry'))}</p><p data-setup-entry-status>${esc(view.error&&!view.envelope?t('unavailable'):progress().completed?t('finished'):progress().started?t('saved'):'')}</p></div><button type="button" class="primary" data-setup-open>${esc(t(progress().started&&!progress().completed?'resume':'open'))}</button></section>`;}
  function updateEntry(){global.document?.querySelectorAll?.('[data-setup-entry]').forEach(node=>{const status=node.querySelector('[data-setup-entry-status]'),button=node.querySelector('[data-setup-open]');if(status)status.textContent=view.error&&!view.envelope?t('unavailable'):progress().completed?t('finished'):progress().started?t('saved'):'';if(button)button.textContent=t(progress().started&&!progress().completed?'resume':'open');});}
  function render(){
    updateEntry();if(!view.open||!view.dialog)return;
    const p=progress(),steps=route(),index=steps.indexOf(p.step),current=['app','invite','verify'].includes(p.step)?'app':['api','api-key','chatgpt'].includes(p.step)?'chatgpt':p.step;
    const html=`<header class="setup-header"><strong>${esc(t('title'))}</strong><span>${Math.max(1,index+1)} / ${steps.length}</span><button type="button" data-setup-action="close" aria-label="${esc(t('close'))}" ${view.busy?'disabled':''}>×</button></header><div class="setup-body"><nav class="setup-navigation" aria-label="${esc(t('title'))}">${[['start','welcome'],['application','app'],['modelSection','chatgpt'],['chats','control'],['projects','projects'],['result','finish']].map(([label,step],i)=>`<button type="button" data-setup-step="${step}" ${step===current?'aria-current="step"':''} ${view.busy||view.pending||(step==='control'&&(p.application!=='codex'||p.standalone))||(p.additional&&step==='chatgpt')||(p.standalone&&step==='app')?'disabled':''}><span>${i+1}</span>${esc(t(label))}</button>`).join('')}</nav><main class="setup-content" data-ui-key="${esc(p.step)}">${content()}</main></div><footer class="setup-footer"><div class="setup-reference">${esc(t('reference'))} ${reference()}</div><p class="setup-feedback" ${view.error?'role="alert"':'role="status"'}>${esc(view.error||view.notice||(view.busy?t('working'):view.readsFailed?t('unavailable'):''))}</p><div class="setup-navigation-actions">${p.step!=='welcome'?button('back','back'):''}<span></span>${view.pending?button('retry','retry',true):p.step==='welcome'?button('standalone','manual'):p.step!=='finish'?button('skip','later'):''}${button('next',p.step==='finish'?'finish':'next',true,p.step==='verify'&&!observed()||p.step==='invite'&&!p.invitationId||p.step==='api'&&(view.addApi||!providerFor('api'))&&!(view.fields.apiModel||p.providerKind&&p.model))}</div></footer>`;
    if(global.HubLiveUI?.patch)global.HubLiveUI.patch(view.dialog,html,{preserveInputs:false});else view.dialog.innerHTML=html;
    const key=view.dialog.querySelector('[data-setup-field="apiKey"]');if(key&&key.value!==(view.fields.apiKey||''))key.value=view.fields.apiKey||'';
  }
  function schedule(){if(view.timer!=null)global.clearTimeout?.(view.timer);view.timer=null;if(view.open&&['invite','verify','chatgpt','control'].includes(progress().step))view.timer=global.setTimeout?.(()=>{view.timer=null;if(!view.busy&&!view.pending)void run(refresh);else schedule();},5000);}
  async function open(manual=true){
    if(manual)await init();
    if(!view.envelope){view.initPromise=null;await init();if(!view.envelope)return;}
    if(view.open)return;
    if(manual)await refresh();
    view.focus=global.document?.activeElement;view.open=true;
    if(!view.dialog){view.dialog=global.document.createElement('dialog');view.dialog.id='hub-setup-wizard';view.dialog.setAttribute('aria-labelledby','setup-step-title');view.dialog.className='setup-wizard';global.document.body.appendChild(view.dialog);view.dialog.addEventListener('click',click);view.dialog.addEventListener('input',changeInput);view.dialog.addEventListener('change',changeField);view.dialog.addEventListener('cancel',event=>{event.preventDefault();if(!view.busy)close();});}
    if(manual&&progress().completed)await save({step:'welcome',additional:false,standalone:false});
    render();view.dialog.showModal();global.document.documentElement.classList?.add('setup-wizard-open');await run(refresh);
  }
  function close(){if(view.busy)return;view.open=false;view.fields.apiKey='';view.copyText='';view.dialog?.close();if(view.timer!=null)global.clearTimeout?.(view.timer);view.timer=null;global.document.documentElement.classList?.remove('setup-wizard-open');view.focus?.focus?.();updateEntry();}
  async function copy(text){try{if(!global.navigator?.clipboard?.writeText)throw Error();await global.navigator.clipboard.writeText(text);view.notice=t('copied');}catch(_){view.copyText=text;view.notice=t('copyFallback');}}
  async function invite(reconnect=false){const payload={action:reconnect?'reconnect':'invite',...(reconnect?{id:connection().id}:{}),requestId:id()};await perform({url:'/api/v1/connections',body:payload,valid:r=>typeof r.id==='string'&&typeof r.url==='string'&&Number.isFinite(r.expires),done:async r=>{const url=new URL(r.url,global.location.origin),current=new URL(global.location.origin),loopback=['localhost','127.0.0.1','[::1]'];if(url.origin!==current.origin&&!(url.protocol==='http:'&&current.protocol==='http:'&&loopback.includes(url.hostname)&&loopback.includes(current.hostname)&&url.port===current.port)||!/^\/connect\/[A-Za-z0-9_-]+$/.test(url.pathname)||url.search||url.hash||url.username||url.password)throw Error(t('error'));view.invitationUrl=new URL(url.pathname,current.origin).href;await save({invitationId:r.id,connectionId:'',projectId:'',step:'invite'});await refresh();}});}
  async function saveProvider(kind){
    const p=progress(),auth=account(),payload={action:kind==='oauth'?'save-chatgpt':'save',expected:view.providers.revision,requestId:id(),name:kind==='oauth'?'ChatGPT':`${view.fields.providerKind||p.providerKind||'responses'} · ${p.model||view.fields.apiModel}`,
      ...(kind==='oauth'?{accountId:auth.id,model:chosenModel(),networkMode:view.fields.networkMode||p.networkMode||'direct'}:{provider:view.fields.providerKind||p.providerKind||'responses',model:p.model||view.fields.apiModel,endpoint:view.fields.endpoint||'',apiKey:view.fields.apiKey||'',networkMode:view.fields.networkMode||p.networkMode||'direct'})};
    await perform({url:'/api/v1/agent-providers',body:payload,valid:r=>r.saved===true&&r.requestId===payload.requestId&&typeof r.id==='string',done:async r=>{view.fields.apiKey='';view.addApi=false;await save({providerId:r.id,...(kind==='oauth'?{accountId:auth.id,model:payload.model}:{})});await refresh();}});
  }
  async function useProvider(item){if(!item)return;const payload={action:'select',id:item.id,expected:view.providers.revision,requestId:id()};await perform({url:'/api/v1/agent-providers',body:payload,valid:r=>r.saved===true&&r.id===item.id&&r.requestId===payload.requestId,done:async()=>{await save({providerId:item.id});await refresh();}});}
  async function probe(item){if(!item||probeUnresolved(item))return;const payload={action:'probe',id:item.id,expected:view.providers.revision,requestId:id()};await save({probeRequestId:payload.requestId,providerId:item.id});await perform({url:'/api/v1/agent-providers',body:payload,valid:r=>r.id===item.id&&r.requestId===payload.requestId&&r.kind==='model-probe',done:async r=>{view.probe=r;view.notice=t(r.status==='completed'?'passed':r.status==='outcome_unknown'?'probeUnknown':'failed');await refresh();}});}
  async function startAuth(){
    let popup;try{popup=global.open?.('about:blank','_blank');if(popup)popup.opener=null;}catch(_){}
    const payload={action:'start',requestId:id(),networkMode:view.fields.networkMode||progress().networkMode||'direct',...(account()?.id?{accountId:account().id}:{})};
    await perform({url:'/api/v1/chatgpt-auth',body:payload,valid:r=>typeof r.attemptId==='string'&&r.authorizePath==='/auth/chatgpt/authorize?attemptId='+encodeURIComponent(r.attemptId),done:async r=>{view.attempt=r;await save({authAttemptId:r.attemptId});if(popup&&!popup.closed)popup.location.replace(safeAuthPath());}}).catch(error=>{if(!error.uncertain)popup?.close?.();throw error;});
  }
  async function navigate(step){await save({step});view.error='';view.notice='';}
  async function click(event){
    const app=event.target.closest?.('[data-setup-application]');if(app){if(!view.busy&&!view.pending&&progress().application!==app.dataset.setupApplication)await run(async()=>{view.invitationUrl='';view.copyText='';await save({application:app.dataset.setupApplication,connectionId:'',invitationId:'',projectId:''});});return;}
    const step=event.target.closest?.('[data-setup-step]');if(step&&!step.disabled){await run(()=>navigate(step.dataset.setupStep));return;}
    const button=event.target.closest?.('[data-setup-action]');if(!button||button.disabled)return;const action=button.dataset.setupAction;if(action==='close'){close();return;}if(view.busy)return;
    if(action==='sign-in'){await run(startAuth);return;}
    await run(async()=>{
      const p=progress();
      if(view.copyText&&(action==='next'||action==='back'||action==='skip')){view.copyText='';return;}
      if(action==='retry'&&view.pending){await perform(view.pending);return;}
      if(view.pending)return;
      if(action==='invite'){await invite();return;}
      if(action==='recover'&&connection()?.revoked){await invite(true);return;}
      if(action==='copy-invite'){await copy(t('inviteInstructions',{url:view.invitationUrl}));return;}
      if(action==='refresh'){await refresh();return;}
      if(action==='fresh-chat'){await copy(t('freshInstructions'));return;}
      if(action==='control-prompt'){await copy(t('controlInstructions',{origin:global.location.origin,connection:connection()?.id||''}));return;}
      if(action==='control-test'){
        if(!canControl())return;const row=connection(),binding=projectBindings().find(b=>b.project===selectedProject()?.id),routed=row.profile?.capabilities?.createChat?.projectRouting===true;
        if(routed&&!binding)throw Error(t('chooseProject'));
        await perform({url:'/api/v1/connections',body:{action:'test',id:row.id,...(binding?{bindingId:binding.id}:{})},retrySafe:false,valid:r=>r.id===row.id&&Array.isArray(r.tests),done:async()=>{await refresh();view.notice=t(controlPassed()?'passed':'notChecked');}});return;
      }
      if(action==='add-app'){view.invitationUrl='';view.fields={};await save({step:'app',application:'codex',additional:true,standalone:false,manualProject:false,completed:false,connectionId:'',invitationId:'',projectId:''});return;}
      if(action==='choose-connection'){const rows=bindings().filter(r=>!r.revoked);view.fields.chooseConnection=rows.length>1;await save({step:'verify',connectionId:rows[0]?.id||'',invitationId:'',additional:false});return;}
      if(action==='standalone'){view.fields={};view.root=null;await save({manualProjectRoot:'',step:'projects',standalone:true,additional:false,manualProject:true,projectId:'',manualProjectName:''});return;}
      if(action==='manual-project'){await save({manualProject:true,projectId:''});return;}
      if(action==='folder'){const root=await global.HubLocalFiles?.chooseFolder('workspace',view.root??p.manualProjectRoot??'');if(root){view.root=root;await save({manualProjectRoot:root});}return;}
      if(action==='create-project'){
        const payload={action:'create',name:(view.fields.manualProjectName||p.manualProjectName||'').trim(),roots:(view.root??p.manualProjectRoot)?[view.root??p.manualProjectRoot]:[],requestId:id()};
        await perform({url:'/api/v1/projects',body:payload,valid:r=>typeof r.project?.id==='string'&&r.project.name===payload.name,done:async r=>{await save({projectId:r.project.id,manualProject:true,manualProjectName:payload.name});await refresh();if(typeof global.CustomEvent==='function')global.dispatchEvent?.(new global.CustomEvent('hub-projects-changed',{detail:{project:r.project,action:'create'}}));}});return;
      }
      if(action==='auth-models'){const auth=account();if(!auth)return;await request('/api/v1/chatgpt-auth',{action:'models',accountId:auth.id,requestId:id()});await refresh();return;}
      if(action==='save-oauth'){await saveProvider('oauth');return;}
      if(action==='use-oauth'){await useProvider(providerFor('oauth'));return;}
      if(action==='use-api'){await useProvider(providerFor('api'));return;}
      if(action==='add-api'){view.addApi=true;view.fields.apiModel='';return;}
      if(action==='save-api'){await saveProvider('api');return;}
      if(action==='probe'||action==='probe-oauth'){await probe(action==='probe-oauth'?providerFor('oauth'):activeProvider());return;}
      if(action==='probe-status'){const item=p.step==='chatgpt'?providerFor('oauth'):activeProvider(),requestId=item?.availability?.requestId||p.probeRequestId;if(requestId){view.probe=await request('/api/agent-providers?requestId='+encodeURIComponent(requestId));view.notice=t(view.probe.status==='completed'?'passed':['outcome_unknown','running','interrupted'].includes(view.probe.status)?'probeUnknown':'failed');await refresh();}return;}
      if(action==='next'||action==='skip'){
        if(p.step==='finish'){await save({completed:true,step:'finish'});view.busy=false;close();return;}
        if(p.step==='api'&&action==='next'&&(view.addApi||!providerFor('api'))){await save({step:'api-key',providerKind:view.fields.providerKind||p.providerKind||'responses',model:view.fields.apiModel||p.model||''});return;}
        if(p.step==='api'&&action==='skip')view.addApi=false;
        const steps=route(),index=steps.indexOf(p.step);await navigate(steps[Math.min(steps.length-1,index+1)]);return;
      }
      if(action==='back'){const steps=route();await navigate(steps[Math.max(0,steps.indexOf(p.step)-1)]);}
    });
  }
  function changeInput(event){const input=event.target.closest?.('[data-setup-field]');if(!input)return;const key=input.dataset.setupField;if(key==='root')view.root=input.value;else if(key==='model'&&progress().step==='api')view.fields.apiModel=input.value;else view.fields[key]=input.value;const create=view.dialog.querySelector('[data-setup-action="create-project"]');if(create)create.disabled=!(view.fields.manualProjectName||'').trim();const saveKey=view.dialog.querySelector('[data-setup-action="save-api"]');if(saveKey)saveKey.disabled=!view.fields.apiKey;const next=view.dialog.querySelector('[data-setup-action="next"]');if(next&&progress().step==='api')next.disabled=!(view.fields.apiModel||'').trim();}
  async function changeField(event){const input=event.target.closest?.('[data-setup-field]');if(!input||view.busy||view.pending)return;changeInput(event);const key=input.dataset.setupField;if(['manualProjectName','root'].includes(key)){await run(()=>save({[key==='root'?'manualProjectRoot':key]:input.value}));return;}if(['accountId','connectionId','projectId'].includes(key))await run(async()=>{await save({[key]:input.value});if(key==='connectionId'){view.fields.chooseConnection=false;await save({application:isCodex()?'codex':'other'});}});}
  global.HubSetupWizardUI={entry,open:()=>open(true),init,refresh:()=>run(refresh)};
  global.document?.addEventListener?.('click',event=>{if(event.target.closest?.('[data-setup-open]'))void open(true).catch(error=>{view.error=error.message;updateEntry();});});
  global.document?.addEventListener?.('DOMContentLoaded',()=>void init());
  global.addEventListener?.('focus',()=>{if(view.open&&!view.busy&&!view.pending)void run(refresh);});
  global.HubI18n?.onChange?.(()=>{render();updateEntry();});
})(typeof window==='undefined'?globalThis:window);
