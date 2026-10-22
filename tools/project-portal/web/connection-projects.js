"use strict";
(function(global) {
  const views = new Map();
  const ru = {
    title:'Проекты в приложении и Hub', intro:'В каком проекте Hub агент учитывает работу из открытого проекта приложения.',
    project:'Проект в Hub', clientProject:'Проект в приложении', rule:'Правило проекта', action:'Действие',
    empty:'Добавьте проект в разделе «Проекты», затем подключите его учёт в приложении.', manage:'Управлять', connect:'Подключить',
    notConnected:'Ещё не подключён', active:'Учёт включён', unbound:'Учёт отключён', saved:'Клиент сообщил о сохранении',
    pending:'Ожидает обновления в приложении', missing:'Правило отсутствует', manual:'Ожидает установки в приложении',
    unknown:'Нет подтверждения клиента', folder:'Папка проекта в приложении', native:'ID проекта в приложении',
    rulesCurrent:'Клиент сообщил актуальную версию общих правил.', rulesOld:'Клиент ещё не подтвердил текущую версию общих правил.',
    auto:'Обычно достаточно открыть чат в нужном проекте приложения. Агент подключит учёт, если проект определяется однозначно.',
    folders:'Папки исходников и внешние ресурсы настраиваются только в разделе «Проекты».', openProjects:'Открыть проекты',
    scopeHelp:'Показанная папка или ID определяют открытый проект приложения. Это не дополнительный проект Hub и не список ресурсных папок.',
    manageTitle:'Учёт проекта', repair:'Запросить обновление правила', repairHelp:'Hub сохраняет запрос. Правило в приложении обновит сам агент при следующем обращении.',
    history:'История подключения проекта', historyEmpty:'История пуста.', close:'Закрыть',
    disconnectTitle:'Отключить автоматический учёт', disconnectHelp:'Новые чаты этого проекта не будут автоматически подключаться к Hub. Существующие задачи и история сохраняются.',
    disconnect:'Отключить учёт в приложении', confirmDisconnect:'Отключить автоматический учёт этого проекта? Задачи и история сохранятся.',
    reconnect:'Снова включить учёт', confirmReconnect:'Снова включить учёт этого проекта? Агент обновит правило при следующем обращении.',
    prepare:'Подключение проекта', connectHelp:'Используется основная папка, уже зарегистрированная в Hub. Источники и внешние ресурсы не меняются.',
    loading:'Загрузка основной папки…', noFolder:'Основная папка не задана. Настройте её в разделе «Проекты» или откройте проект в приложении и передайте агенту приглашение.',
    failed:'Не удалось получить сведения о папке. Повторите подключение.', connectAction:'Включить учёт проекта',
    movePending:'Перенос папки прерван. Работа по этому подключению приостановлена.', moveResume:'Продолжить перенос',
    moveUnavailable:'Исходные аргументы переноса не сохранены. Требуется восстановление по диагностике.',
    previous:'Назад', next:'Далее', legacy:'Это подключение ограничено одним проектом. Его существующие настройки сохранены.', more:'Другие проекты приложения'
  };
  const en = {
    title:'Projects in the application and Hub', intro:'Where work from an open application project is recorded in Hub.',
    project:'Project in Hub',clientProject:'Project in the application',rule:'Project rule',action:'Action',
    empty:'Add a project in Projects, then connect its tracking in the application.',manage:'Manage',connect:'Connect',notConnected:'Not connected yet',
    active:'Tracking enabled',unbound:'Tracking disabled',saved:'Client reported saved',pending:'Waiting for an application update',missing:'Rule missing',manual:'Client installation pending',unknown:'Not confirmed by the client',
    folder:'Project directory in the application',native:'Application project ID',rulesCurrent:'The client reports current shared rules.',rulesOld:'The client has not confirmed the current shared rules.',
    auto:'Usually, open a chat in the application project. The agent connects tracking when the project can be identified unambiguously.',
    folders:'Source folders and external resources are configured only in Projects.',openProjects:'Open Projects',scopeHelp:'The folder or ID identifies the open application project. It is neither another Hub project nor a list of resource folders.',
    manageTitle:'Project tracking',repair:'Request a rule update',repairHelp:'Hub saves the request. The agent updates the application rule on its next request.',history:'Project connection history',historyEmpty:'No history.',close:'Close',
    disconnectTitle:'Disable automatic tracking',disconnectHelp:'New chats in this project will not automatically connect to Hub. Existing tasks and history are preserved.',disconnect:'Disable tracking in the application',confirmDisconnect:'Disable automatic tracking for this project? Tasks and history will be preserved.',
    reconnect:'Enable tracking again',confirmReconnect:'Enable tracking for this project again? The agent will update the rule on its next request.',
    prepare:'Connect a project',connectHelp:'Uses the primary folder already registered in Hub. Source folders and external resources are unchanged.',loading:'Loading the primary folder…',
    noFolder:'No primary folder is configured. Set it in Projects, or open the project in the application and give the agent an invitation.',failed:'Could not load folder details. Try connecting again.',connectAction:'Enable project tracking',
    movePending:'Directory relocation was interrupted. Work through this connection is paused.',moveResume:'Resume relocation',moveUnavailable:'The original relocation arguments were not saved. Diagnostic recovery is required.',
    previous:'Previous',next:'Next',legacy:'This connection is limited to one project. Its existing settings have been preserved.',more:'Other application projects'
  };
  const t=key=>(global.HubI18n?.locale==='en'?en:ru)[key]||key;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state=id=>views.get(id)||views.set(id,{page:0,selected:null,connect:null,root:'',loading:false,error:'',history:new Map()}).get(id);
  const requestId=()=>global.crypto.randomUUID().replaceAll('-','');
  const button=(text,action,row,binding='',extra='')=>`<button type="button" data-binding-action="${action}" data-owner="${esc(row.id)}" data-binding="${esc(binding)}" ${extra}>${esc(text)}</button>`;
  const ruleLabel=b=>t(b.ruleState==='needs-repair'?'pending':(['saved','missing','manual'].includes(b.ruleState)?b.ruleState:'unknown'));
  const primaryBinding=(bindings,project)=>bindings.find(b=>b.project===project&&b.status==='active')||bindings.find(b=>b.project===project);
  function dialog(row,projects,blocked) {
    const s=state(row.id),b=(row.projectBindings||[]).find(item=>item.id===s.selected);
    const disabled=blocked||row.revoked?'disabled':'';
    if(s.connect) {
      const project=projects.find(item=>item.id===s.connect);
      return `<dialog class="connection-project-dialog" data-project-dialog aria-labelledby="connection-project-dialog-title"><div class="section-head"><h3 id="connection-project-dialog-title">${esc(t('prepare'))}: ${esc(project?.name||s.connect)}</h3>${button(t('close'),'close',row)}</div><p>${esc(t('connectHelp'))}</p><dl><dt>${esc(t('project'))}</dt><dd>${esc(project?.name||s.connect)}</dd><dt>${esc(t('folder'))}</dt><dd><code>${esc(s.root||'—')}</code></dd></dl><p role="status">${esc(s.error||(s.loading?t('loading'):!s.root?t('noFolder'):t('repairHelp')))}</p><p>${esc(t('folders'))} <a href="#projects">${esc(t('openProjects'))}</a></p>${button(t('connectAction'),'confirm-connect',row,'',disabled||!s.root||s.loading?'disabled':'')}</dialog>`;
    }
    if(!b)return '';
    const history=s.history.get(b.id);
    return `<dialog class="connection-project-dialog" data-project-dialog aria-labelledby="connection-project-dialog-title"><div class="section-head"><h3 id="connection-project-dialog-title">${esc(t('manageTitle'))}: ${esc(projects.find(p=>p.id===b.project)?.name||b.project)}</h3>${button(t('close'),'close',row)}</div><dl><dt>${esc(t('project'))}</dt><dd>${esc(projects.find(p=>p.id===b.project)?.name||b.project)}</dd><dt>${esc(t('folder'))}</dt><dd><code>${esc(b.scope?.root||'—')}</code></dd>${b.scope?.nativeRef?`<dt>${esc(t('native'))}</dt><dd><code>${esc(b.scope.nativeRef)}</code></dd>`:''}<dt>${esc(t('rule'))}</dt><dd>${esc(ruleLabel(b))}${b.rulePath?`<small><code>${esc(b.rulePath)}</code></small>`:''}</dd></dl><p>${esc(t('scopeHelp'))}</p><div class="actions">${button(t(b.status==='unbound'?'reconnect':'repair'),b.status==='unbound'?'reconnect':'repair',row,b.id,disabled)}${button(t('history'),'history',row,b.id,blocked?'disabled':'')}</div><p>${esc(t('repairHelp'))}</p><p>${esc(t('folders'))} <a href="#projects">${esc(t('openProjects'))}</a></p>${history?`<details open><summary>${esc(t('history'))}</summary><pre>${esc(JSON.stringify(history,null,2))}</pre></details>`:''}${b.pendingRelocation?`<div class="connection-move-pending"><p>${esc(t('movePending'))}</p>${b.pendingRelocation.recoverable?button(t('moveResume'),'resume',row,b.id,disabled):`<p>${esc(t('moveUnavailable'))}</p>`}</div>`:''}${b.status==='active'?`<details><summary>${esc(t('disconnectTitle'))}</summary><p>${esc(t('disconnectHelp'))}</p>${button(t('disconnect'),'unbind',row,b.id,disabled)}</details>`:''}</dialog>`;
  }
  function render(row,projects=[],blocked=false) {
    const s=state(row.id),bindings=row.projectBindings||[],items=[...projects];
    for(const b of bindings)if(!items.some(p=>p.id===b.project))items.push({id:b.project,name:b.project});
    if(row.scope!=='global')return `<p>${esc(t('legacy'))}</p><p>${esc(row.project_name||row.project||'')}</p>`;
    const count=6;s.page=Math.min(s.page,Math.max(0,Math.ceil(items.length/count)-1));
    const rows=items.slice(s.page*count,(s.page+1)*count).map(p=>{
      const b=primaryBinding(bindings,p.id);
      return `<tr><td>${esc(p.name||p.id)}</td><td>${b?`<code>${esc(b.scope?.root||b.scope?.nativeRef||'—')}</code><small>${esc(t(b.status==='active'?'active':'unbound'))}</small>`:esc(t('notConnected'))}</td><td>${b?esc(ruleLabel(b)):'—'}</td><td>${b?button(t('manage'),'manage',row,b.id):button(t('connect'),'connect',row,'',`data-project="${esc(p.id)}" ${blocked||row.revoked?'disabled':''}`)}</td></tr>`;
    }).join('');
    const extra=bindings.filter(b=>primaryBinding(bindings,b.project)!==b);
    return `<section class="connection-projects"><h3>${esc(t('title'))}</h3><p>${esc(t('intro'))}</p><p>${esc(t(row.instructionsCurrent?'rulesCurrent':'rulesOld'))}</p>${items.length?`<div class="connection-table-wrap"><table><thead><tr><th>${esc(t('project'))}</th><th>${esc(t('clientProject'))}</th><th>${esc(t('rule'))}</th><th>${esc(t('action'))}</th></tr></thead><tbody>${rows}</tbody></table></div>`:`<p>${esc(t('empty'))}</p>`}${extra.length?`<details><summary>${esc(t('more'))}</summary>${extra.map(b=>`<p>${esc(projects.find(p=>p.id===b.project)?.name||b.project)} · <code>${esc(b.scope?.root||b.scope?.nativeRef||'—')}</code> ${button(t('manage'),'manage',row,b.id)}</p>`).join('')}</details>`:''}${items.length>count?`<div class="connection-pagination"><span>${s.page*count+1}–${Math.min(items.length,(s.page+1)*count)} / ${items.length}</span>${button(t('previous'),'previous',row,'',s.page?'':'disabled')}${button(t('next'),'next',row,'',(s.page+1)*count>=items.length?'disabled':'')}</div>`:''}<p>${esc(t('auto'))}</p><p>${esc(t('folders'))} <a href="#projects">${esc(t('openProjects'))}</a></p>${dialog(row,projects,blocked)}</section>`;
  }
  async function click(target,rows,mutate,refresh=()=>{}) {
    const row=rows.find(item=>item.id===target.dataset.owner);if(!row)return;
    const s=state(row.id),action=target.dataset.bindingAction;
    if(action==='close'){s.selected=null;s.connect=null;refresh();return;}
    if(action==='previous'||action==='next'){s.page=Math.max(0,s.page+(action==='next'?1:-1));refresh();return;}
    if(action==='manage'){s.selected=target.dataset.binding;s.connect=null;refresh();return;}
    if(action==='connect'){
      if(row.revoked)return;
      const project=target.dataset.project;s.connect=project;s.selected=null;s.root='';s.error='';s.loading=true;refresh();
      try{
        const response=await global.fetch('/api/v1/workspaces?project='+encodeURIComponent(project),{cache:'no-store'}),value=await response.json();
        if(!response.ok||value.project!==project||!Array.isArray(value.items))throw Error(t('failed'));
        const primary=value.items.find(item=>String(item.descriptor?.rootRef)==='0'&&item.kind==='local'&&item.enabled);
        if(s.connect===project)s.root=primary?.descriptor?.root||'';
      }catch(_){if(s.connect===project)s.error=t('failed');}
      finally{if(s.connect===project)s.loading=false;refresh();}return;
    }
    if(action==='confirm-connect'){
      if(row.revoked||s.loading||!s.root||!s.connect)return;
      return mutate({action:'project-binding',id:row.id,operation:{action:'resolve',project:s.connect,scope:{kind:'workspace',root:s.root},requestId:requestId()}},'project-binding');
    }
    const b=(row.projectBindings||[]).find(item=>item.id===target.dataset.binding);if(!b)return;
    if(action==='unbind'&&!global.confirm?.(t('confirmDisconnect')))return;
    if(action==='reconnect'&&!global.confirm?.(t('confirmReconnect')))return;
    if(!['repair','unbind','history','resume','reconnect'].includes(action))return;
    const operation={action:action==='reconnect'?'repair':action,bindingId:b.id};
    if(action==='resume'){if(!b.pendingRelocation?.recoverable)return;operation.requestId=b.pendingRelocation.requestId;}
    else if(action!=='history'){if(row.revoked)return;operation.expectedRevision=b.revision;operation.requestId=requestId();}
    return mutate({action:'project-binding',id:row.id,operation},'project-binding');
  }
  function afterRender(root){
    root?.querySelectorAll?.('[data-project-dialog]').forEach(dialog=>{if(!dialog.open)dialog.showModal?.();if(!dialog.__hubProjectDialogBound){dialog.__hubProjectDialogBound=true;dialog.addEventListener('cancel',()=>{for(const s of views.values()){s.selected=null;s.connect=null;}});}});
  }
  global.HubConnectionProjects={render,click,afterRender,ack(result){const b=result.binding;if(!b)return;const s=state(b.connection);if(result.history)s.history.set(b.id,result.history);if(s.connect&&b.project===s.connect){s.connect=null;s.selected=b.id;}}};
})(window);
