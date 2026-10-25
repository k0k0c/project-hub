"use strict";
(() => {
  const states = new Map(), active = new Set(["dispatching", "dispatch_unknown", "awaiting_ack", "accepted"]); let host = null, modal = null, historyView = null;
  const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const en=()=>globalThis.HubI18n?.locale==="en", tx=(ru,eng)=>en()?eng:ru, key=(p,t,s)=>JSON.stringify([p,t,s||""]);
  const state=(p,t,s)=>{const k=key(p,t,s);if(!states.has(k))states.set(k,{key:k,project:p,task:t,stage:s,loaded:false,loading:false,routes:[],launches:[],chats:null,error:"",postError:"",preferredRoute:null,routeEdited:false,lastRequestId:null,draft:{application:"",route:"",mode:"create",resume:"",prompt:""},pending:null,retryBody:null,poll:null,generation:0});return states.get(k)};
  const err=v=>globalThis.HubI18n?.error?.(v)||v?.error?.message||v?.message||v?.error||tx("Не удалось получить сведения о запуске.","Could not load task launch details.");
  const rid=()=>{const v=globalThis.crypto?.randomUUID?.();return v?v.replace(/-/g,"").slice(0,32):null};
  function safeLink(v){if(typeof v!=="string")return"";if(/^codex:\/\/threads\/[0-9a-f]{8}-[0-9a-f]{4}-[1-7][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v))return v;try{const u=new URL(v);return ["http:","https:"].includes(u.protocol)&&!u.username&&!u.password?u.href:""}catch(_){return""}}
  const routeKey=r=>JSON.stringify([r.connection,r.bindingId]);
  const sameStage=(a,b)=>(a||null)===(b||null);
  const noOpenStages=task=>task?.status==="cancelled"||(task?.stages?.length>0&&task.stages.every(s=>["done","cancelled"].includes(s.status)));
  const route=()=>host?.route?.()||[];
  const modalCurrent=v=>host?.project===v.project&&modal?.value===v&&modal.originRoute===JSON.stringify(route());
  const historyCurrent=v=>host?.project===v.project&&historyView?.value===v;
  const current=v=>modalCurrent(v)||historyCurrent(v);
  function paint(v){
    if(historyCurrent(v))historyView.node.innerHTML=historyContent(historyView.task,v);
    if(!modalCurrent(v))return;
    capture(v);
    const focused=document.activeElement, name=modal.node.contains(focused)?focused?.name:null;
    const start=focused?.selectionStart,end=focused?.selectionEnd;
    modal.content.innerHTML=render(modal.task,modal.stage,v.project);
    const next=name?modal.content.querySelector(name==='mode'?'[name="mode"]:checked':`[name="${name}"]`):null;
    next?.focus({preventScroll:true});
    if(typeof start==='number'&&next?.setSelectionRange)next.setSelectionRange(start,end);
  }
  const label=s=>({dispatching:tx("Отправляется","Dispatching"),dispatch_unknown:tx("Результат отправки неизвестен","Dispatch result unknown"),awaiting_ack:tx("Ожидает подтверждения агента","Awaiting agent acknowledgement"),accepted:tx("Принято","Accepted"),completed:tx("Запуск завершён","Launch completed"),failed:tx("Ошибка","Failed"),interrupted:tx("Прервано","Interrupted"),cancelled:tx("Отменено","Cancelled"),routing_conflict:tx("Маршрут чата не подтверждён","Chat routing not verified"),outcome_unknown:tx("Результат неизвестен","Outcome unknown")}[s]||tx("Неизвестный статус","Unknown status"));
  const at=value=>{if(!value)return "";const d=new Date(typeof value==="number"?value*1000:value);return Number.isNaN(d.getTime())?"":d.toLocaleString(en()?"en-GB":"ru-RU")};
  function evidence(r){
    const items=Array.isArray(r?.result?.evidence)?r.result.evidence:[],registered=host?.renderEvidence?.(items.map(item=>typeof item==="string"?{path:item}:item))||"",source=safeLink(r?.sourceUri);
    const fallback=items.map(safeLink).filter(Boolean).map(url=>'<p><a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(tx("Открыть источник","Open source"))+'</a></p>').join("");
    return (registered||fallback)+(source?'<p><a href="'+esc(source)+'">'+esc(tx("Открыть чат","Open chat"))+'</a></p>':"");
  }
  async function load(v,force=false){if(!current(v)||v.loading||(v.loaded&&!force))return;v.loading=true;v.error="";const g=++v.generation;try{const r=await fetch("/api/task-launches?"+new URLSearchParams({project:v.project,task:v.task})),b=await r.json();if(g!==v.generation||!current(v))return;if(!r.ok||b?.project!==v.project||b?.task!==v.task||!Array.isArray(b?.routes)||!Array.isArray(b?.launches)||("chats"in b&&!Array.isArray(b.chats)))throw Error(err(b));v.routes=b.routes;v.preferredRoute=b.preferredRoute||null;v.launches=b.launches;v.chats=Array.isArray(b.chats)?b.chats:null;v.loaded=true}catch(e){if(g===v.generation){v.loaded=true;v.error=err(e)}}finally{if(g===v.generation){v.loading=false;paint(v);schedule(v)}}}
  function schedule(v){if(v.poll)clearTimeout(v.poll);if(current(v)&&v.launches.some(x=>active.has(x.status)))v.poll=setTimeout(()=>{v.poll=null;void load(v,true)},1500)}
  function capture(v){
    const r=document.querySelector("[data-task-launches]");
    if(!r||r.dataset.project!==v.project||r.dataset.task!==v.task||!sameStage(r.dataset.stage,v.stage))return;
    const application=r.querySelector('[name="application"]'),changed=application&&application.value!==v.draft.application;
    if(changed){v.draft.application=application.value;v.draft.route="";v.routeEdited=true}
    if(!changed){const f=r.querySelector('[name="route"]');if(f)v.draft.route=f.value}
    for(const n of ["prompt","resume"]){const f=r.querySelector(`[name="${n}"]`);if(f)v.draft[n]=f.value}
    const c=r.querySelector('[name="mode"]:checked');if(c)v.draft.mode=c.value;
  }
  function selectDefaults(v){
    const selected=v.routes.find(r=>routeKey(r)===v.draft.route&&(!v.draft.application||r.connection===v.draft.application));
    if(selected){v.draft.application=selected.connection;return}
    v.draft.route="";
    const applications=[...new Set(v.routes.map(r=>r.connection))];
    if(!applications.includes(v.draft.application)){
      v.draft.application=v.routeEdited?"":applications.includes(v.preferredRoute?.connection)?v.preferredRoute.connection:applications.length===1?applications[0]:"";
    }
    const available=v.routes.filter(r=>r.connection===v.draft.application);
    const preferred=!v.routeEdited&&available.find(r=>r.bindingId===v.preferredRoute?.bindingId&&r.connection===v.preferredRoute?.connection);
    const choice=preferred||(available.length===1?available[0]:null);
    if(choice)v.draft.route=routeKey(choice);
  }
  function historyContent(task,v){
    const rows=v.launches.slice(0,8).map(r=>{
      const stage=task.stages?.find(s=>s.id===r.stage);
      const scope=r.stage?tx("Этап: ","Stage: ")+(stage?.title||tx("Этап задачи","Task stage")):tx("Вся задача","Whole task");
      return `<li class="task-launch-row" data-state="${esc(r.status)}"><strong>${esc(label(r.status))}</strong><span class="caption">${esc(scope)}</span>
        <span>${esc(r.apiAcceptedAt?tx("Приложение приняло команду","Application accepted the command")+" · "+at(r.apiAcceptedAt):"")}</span>
        <span>${esc(r.acknowledgedAt?tx("Получение задания подтверждено","Agent acknowledged the assignment")+" · "+at(r.acknowledgedAt):"")}</span>
        <span>${esc(r.finishedAt?(r.status==="completed"?tx("Результат сохранён","Result saved"):tx("Запуск завершён","Launch finished"))+" · "+at(r.finishedAt):"")}</span>
        ${r.nativeVisibility?.state==="verified"?`<span>${esc(tx("Чат найден в проекте приложения","Chat found in the application project"))}</span>`:""}
        ${r.result?.summary?`<div><span class="caption">${esc(tx("Отчёт агента","Agent report"))}</span><p class="task-launch-result">${esc(r.result.summary)}</p></div>`:""}
        ${evidence(r)}${r.error?`<p role="alert">${esc(err(r))}</p>`:""}</li>`;
    }).join("");
    return `<div class="section-head"><h2>${esc(tx("Запуски из Hub","Launches from Hub"))}</h2><button type="button" data-task-launch-history-refresh${v.loading?" disabled":""}>${esc(tx("Обновить","Refresh"))}</button></div>
      <p class="caption">${esc(tx("Последние запуски этой задачи и её этапов. Статус относится к отдельному запуску, а не к готовности задачи.","Recent launches of this task and its stages. Each status describes a launch, not task completion."))}</p>
      ${v.error?`<p role="alert">${esc(v.error)}</p>`:""}
      <ul class="task-launch-history" aria-live="polite">${rows||`<li class="caption">${esc(v.loading||!v.loaded?tx("Загрузка запусков…","Loading launches…"):tx("Запусков из Hub пока нет.","No launches from Hub yet."))}</li>`}</ul>`;
  }
  function renderHistory(task,project=host?.project||""){
    if(!project||!task?.id)return"";
    const v=state(project,task.id,null);
    return `<section class="diagnostic-section" data-task-launch-history-view data-project="${esc(project)}" data-task="${esc(task.id)}">${historyContent(task,v)}</section>`;
  }
  function render(task,stage=null,project=host?.project||""){
    if(!project||!task?.id)return"";
    const v=state(project,task.id,stage?.id);capture(v);selectDefaults(v);
    const sel=v.routes.find(x=>routeKey(x)===v.draft.route),useChats=Array.isArray(v.chats),seenChats=new Set();
    const sourceChats=useChats?[...v.chats].sort((a,b)=>Number(b.origin==="related")-Number(a.origin==="related")):v.launches;
    const rs=sourceChats.filter(x=>x.task===undefined||x.task===v.task).filter(x=>sel?.canContinue&&x.canContinue&&x.nativeId&&x.connection===sel?.connection&&x.bindingId===sel?.bindingId&&(useChats?(x.scope!=="stage"||sameStage(x.stage,stage?.id)):sameStage(x.stage,stage?.id))&&!seenChats.has(x.nativeId)&&seenChats.add(x.nativeId));
    if(!rs.some(x=>x.nativeId===v.draft.resume)&&rs[0])v.draft.resume=rs[0].nativeId;
    const resume=rs.find(x=>x.nativeId===v.draft.resume)||rs[0],mode=v.draft.mode==="continue"&&resume?"continue":"create";
    const applications=[...new Map(v.routes.map(r=>[r.connection,r])).values()];
    const choices=applications.map(r=>`<option value="${esc(r.connection)}"${r.connection===v.draft.application?" selected":""}>${esc(r.application||r.connection)}</option>`).join("");
    const workspaces=v.routes.filter(r=>r.connection===v.draft.application);
    const workspaceChoices=workspaces.map(r=>`<option value="${esc(routeKey(r))}"${routeKey(r)===v.draft.route?" selected":""}>${esc(r.workspace||tx("Проект приложения","Application project"))}</option>`).join("");
    const resumeChoices=rs.map(x=>`<option value="${esc(x.nativeId)}"${x.nativeId===v.draft.resume?" selected":""}>${esc(x.title||x.nativeId)}</option>`).join("");
    const unknown=v.launches.some(x=>x.status==="dispatch_unknown"&&sameStage(x.stage,v.stage));
    const disabled=Boolean(v.pending||v.retryBody||unknown)||(!stage&&noOpenStages(task))||!globalThis.crypto?.randomUUID||!sel||(mode==="create"?!sel.canCreate:!resume);
    const last=v.launches.find(x=>x.requestId===v.lastRequestId);
    const historyLink=`<a href="#tasks/${encodeURIComponent(task.id)}//chats" data-task-launch-history-task="${esc(task.id)}">${esc(tx("Чаты задачи","Task chats"))}</a>`;
    return `<section class="panel task-launches" data-task-launches data-project="${esc(project)}" data-task="${esc(task.id)}" data-stage="${esc(stage?.id||'')}">
      <div class="section-head"><div><h2>${esc(stage?tx("Запустить этап","Launch stage"):tx("Запустить задачу","Launch task"))}</h2>
        <p class="task-launch-scope"><strong>${esc(stage?.title||task.title||task.id)}</strong></p>
        <p class="caption">${esc(stage?tx("Будет запущен только выбранный этап.","Only the selected stage will run."):tx("Агент начнёт или продолжит незавершённые этапы задачи. Завершённые и отменённые этапы пропускаются.","The agent will start or continue unfinished task stages. Completed and cancelled stages are skipped."))}</p>
        <p class="caption">${esc(tx("Запуск выполняется во внешнем приложении и может использовать модель.","The launch runs in an external application and may use a model."))}</p></div></div>
      <p class="caption"><a href="#settings/agents/apps">${esc(tx("Настроить приложения","Configure applications"))}</a></p>
      ${v.postError||v.error?`<p role="alert">${esc(v.postError||v.error)}</p>`:""}
      <form data-task-launch-form>
        <label>${esc(tx("Приложение","Application"))}<select name="application" required><option value="">${esc(tx("Выберите приложение","Choose an application"))}</option>${choices||`<option value="">${esc(tx("Нет доступных приложений","No applications available"))}</option>`}</select></label>
        ${workspaces.length>1?`<label>${esc(tx("Рабочее пространство","Workspace"))}<select name="route" required><option value="">${esc(tx("Выберите рабочее пространство","Choose a workspace"))}</option>${workspaceChoices}</select></label>`:`<input type="hidden" name="route" value="${esc(v.draft.route)}">`}
        <fieldset><legend>${esc(tx("Режим","Mode"))}</legend>
          <label><input type="radio" name="mode" value="create"${mode==="create"?" checked":""}${!sel?.canCreate?" disabled":""}> ${esc(tx("Создать новый чат","Create a new chat"))}</label>
          <label><input type="radio" name="mode" value="continue"${mode==="continue"?" checked":""}${!resume?" disabled":""}> ${esc(tx("Продолжить чат","Continue a chat"))}</label>
          ${mode==="continue"&&resumeChoices?`<label>${esc(tx("Чат для продолжения","Chat to continue"))}<select name="resume">${resumeChoices}</select></label>`:""}</fieldset>
        <label>${esc(tx("Дополнительная инструкция (необязательно)","Additional instruction (optional)"))}<textarea name="prompt" rows="3" maxlength="${promptLimit(stage)}">${esc(v.draft.prompt)}</textarea></label>
        <button type="submit"${disabled?" disabled":""}>${esc(tx("Запустить","Launch"))}</button>
      </form>
      ${!stage&&noOpenStages(task)?`<p class="caption">${esc(task.status==="cancelled"?tx("Задача отменена.","The task is cancelled."):tx("Нет незавершённых этапов для запуска.","There are no unfinished stages to launch."))}</p>`:""}
      ${v.pending?`<p role="status">${esc(tx("Запрос отправляется…","Sending request…"))}</p>`:""}
      ${v.retryBody?`<button type="button" data-task-launch-retry>${esc(tx("Повторить тот же запрос","Retry the exact request"))}</button>`:""}
      ${last?`<p role="status">${esc(tx("Текущий запуск: ","Current launch: ")+label(last.status))}. ${historyLink}</p>`:unknown?`<p role="status">${esc(tx("Результат отправки неизвестен. Проверьте запуск во вкладке «Чаты».","Dispatch result unknown. Inspect the launch in the Chats tab."))} ${historyLink}</p>`:""}
    </section>`;
  }
  // These local API errors are returned before a native dispatch is reserved.
  const rejectedBeforeDispatch=new Set(["project_launcher_unavailable","task_missing","stage_missing","native_chat_busy","native_project_unverified","connection_revoked","connection_unavailable","connection_missing","project_binding_missing","project_relocation_pending","project_binding_conflict","project_binding_unavailable","backup_in_progress","storage_operation_in_progress"]);
  async function post(v,b){
    if(v.pending||v.retryBody)return;v.pending=b;v.generation++;v.loading=false;v.postError="";paint(v);
    try{
      const r=await fetch("/api/v1/connections",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"launch",id:b.connection,request:b.request})}),x=await r.json(),e=x?.envelope;
      if(!r.ok&&r.status>=400&&r.status<500&&rejectedBeforeDispatch.has(x?.error)){v.postError=err(x);return;}
      if(!r.ok||e?.bindingId!==b.request.bindingId||!sameStage(e?.resultDestination?.stage,v.stage)||x?.requestId!==b.request.requestId||e?.connection!==b.connection||e?.project!==v.project||e?.inputs?.task?.id!==v.task)throw Error(tx("Результат неизвестен.","Outcome unknown."));
      v.lastRequestId=b.request.requestId;v.launches.unshift({requestId:b.request.requestId,connection:b.connection,bindingId:b.request.bindingId,task:v.task,stage:v.stage,status:x.status||"dispatch_unknown",...x});v.retryBody=null;
    }catch(e){v.postError=err(e);v.retryBody=b}finally{v.pending=null;paint(v);void load(v,true);schedule(v)}
  }
  const taskScopeInstruction=()=>tx("Выполните существующую задачу целиком. Прочитайте актуальный план через hub_plan. Начните или продолжите только незавершённые этапы, учитывая их порядок, зависимости и текущие препятствия. Пропускайте этапы со статусами done и cancelled; не переоткрывайте их. Если открытых этапов нет, сообщите об этом и не создавайте новую работу.","Execute the existing task as a whole. Read its current plan through hub_plan. Start or continue only unfinished stages, respecting their order, dependencies and current blockers. Skip stages with done or cancelled status; do not reopen them. If there are no open stages, report that and do not create new work.");
  const additionalInstruction=()=>"\n\n"+tx("Дополнительная инструкция пользователя:\n","Additional user instruction:\n");
  const promptLimit=stage=>stage?6000:6000-taskScopeInstruction().length-additionalInstruction().length;
  function submit(v,f){
    if((!v.stage&&noOpenStages(v.taskInfo))||v.pending||v.retryBody||v.launches.some(x=>x.status==="dispatch_unknown"&&sameStage(x.stage,v.stage)))return;
    const r=v.routes.find(x=>routeKey(x)===f.route),m=f.mode==="continue"?"continue":"create",useChats=Array.isArray(v.chats),sourceChats=useChats?v.chats:v.launches;
    const resume=sourceChats.find(x=>(x.task===undefined||x.task===v.task)&&x.canContinue&&x.nativeId&&x.nativeId===f.resume&&x.connection===r?.connection&&x.bindingId===r?.bindingId&&(useChats?(x.scope!=="stage"||sameStage(x.stage,v.stage)):sameStage(x.stage,v.stage))),id=rid();
    if(!id||!r||f.prompt.length>promptLimit(v.stage)||(m==="create"&&!r.canCreate)||(m==="continue"&&!resume))return;
    const q={requestId:id,bindingId:r.bindingId,operation:"task-execute",task:v.task};
    if(v.stage){q.stage=v.stage;if(f.prompt)q.prompt=f.prompt}
    else q.prompt=taskScopeInstruction()+(f.prompt?additionalInstruction()+f.prompt:"");
    if(m==="continue")q.nativeId=resume.nativeId;
    void post(v,{connection:r.connection,request:q});
  }
  function stop(v){v.generation++;v.loading=false;if(v.poll){clearTimeout(v.poll);v.poll=null}}
  function open(task,stage=null,project=host?.project,trigger=null){
    if(!host||!project||!task?.id)return;
    if(modal){const previous=modal;capture(previous.value);if(!historyCurrent(previous.value))stop(previous.value);modal=null;previous.node.close();previous.node.remove()}
    const v=state(project,task.id,stage?.id),node=document.createElement("dialog");v.taskInfo=task;v.lastRequestId=null;if(!v.pending&&!v.retryBody)v.draft.mode="create";
    node.className="task-launch-dialog";node.setAttribute("data-task-launch-dialog","");
    node.setAttribute("aria-label",stage?tx("Запустить этап","Launch stage"):tx("Запустить задачу","Launch task"));
    node.innerHTML=`<button type="button" class="icon-button task-launch-close" data-task-launch-close autofocus aria-label="${esc(tx("Закрыть","Close"))}" title="${esc(tx("Закрыть","Close"))}">×</button><div data-task-launch-content></div>`;
    const value={value:v,node,content:node.querySelector("[data-task-launch-content]"),task,stage,originRoute:JSON.stringify(route())};
    modal=value;
    node.addEventListener("close",()=>{if(modal===value){capture(v);modal=null;if(!historyCurrent(v))stop(v);else schedule(v)}node.remove();if(!modal&&trigger?.isConnected)trigger.focus({preventScroll:true})},{once:true});
    document.body.append(node);paint(v);node.showModal();void load(v,true);
    return node;
  }
  function afterRender(c){
    host=c;
    if(modal&&(modal.value.project!==c.project||modal.originRoute!==JSON.stringify(route())))modal.node.close();
    const node=document.querySelector("[data-task-launch-history-view]"),previous=historyView;
    const task=node?.dataset.project===c.project?c.state?.tasks?.find(t=>t.id===node.dataset.task):null;
    historyView=task?{node,task,value:state(c.project,task.id,null)}:null;
    if(previous&&previous.value!==historyView?.value&&!modalCurrent(previous.value))stop(previous.value);
    if(historyView)void load(historyView.value,previous?.value!==historyView.value);
  }
  document.addEventListener("input",e=>{const r=e.target.closest?.("[data-task-launches]");if(!r)return;const v=states.get(key(r.dataset.project,r.dataset.task,r.dataset.stage));if(v)capture(v)});document.addEventListener("change",e=>{const r=e.target.closest?.("[data-task-launches]");if(!r)return;const v=states.get(key(r.dataset.project,r.dataset.task,r.dataset.stage));if(v){if(["application","route"].includes(e.target.name))v.routeEdited=true;capture(v);paint(v)}});document.addEventListener("submit",e=>{const f=e.target.closest?.("[data-task-launch-form]");if(!f)return;e.preventDefault();const r=f.closest("[data-task-launches]"),v=states.get(key(r.dataset.project,r.dataset.task,r.dataset.stage));if(v)submit(v,{route:f.route.value,mode:f.mode.value,resume:f.resume?.value||"",prompt:f.prompt.value.trim()})});document.addEventListener("click",e=>{
    const history=e.target.closest?.("[data-task-launch-history-task]");
    if(history){e.preventDefault();modal?.node.close();host?.openTaskChats?.(history.dataset.taskLaunchHistoryTask);return}
    if(e.target.closest?.("[data-task-launch-history-refresh]")){if(historyView)void load(historyView.value,true);return}
    const button=e.target.closest?.("[data-task-launch-open]");
    if(button){
      e.preventDefault();e.stopPropagation();
      const task=host?.state?.tasks?.find(t=>t.id===button.dataset.taskLaunchOpen),stage=button.dataset.stageId?task?.stages?.find(s=>s.id===button.dataset.stageId):null;
      if(task&&(!button.dataset.stageId||stage))open(task,stage,host.project,button);
      return;
    }
    if(e.target.closest?.("[data-task-launch-close]")){modal?.node.close();return}
    const b=e.target.closest?.("[data-task-launch-retry]");if(!b)return;
    const r=b.closest("[data-task-launches]"),v=states.get(key(r.dataset.project,r.dataset.task,r.dataset.stage));
    if(v?.retryBody){const body=v.retryBody;v.retryBody=null;void post(v,body)}
  });
  window.addEventListener?.("hub-language-changed",()=>{if(historyView)paint(historyView.value);if(modal){modal.node.setAttribute("aria-label",modal.stage?tx("Запустить этап","Launch stage"):tx("Запустить задачу","Launch task"));paint(modal.value)}});
  window.TaskLaunchesUI={render,renderHistory,afterRender,open,load,safeLink};
})();
