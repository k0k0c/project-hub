"use strict";
(function(global){
  const states=new Map();
  const t=key=>global.HubI18n?.t?.('workspaces.'+key)||key;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state=id=>states.get(id)||states.set(id,{items:[],revision:null,management:false,loaded:false,busy:false,pending:null,drafts:new Map(),error:'',open:false}).get(id);
  function card(project,{expanded=false}={}){const s=state(project.id);if(expanded)s.open=true;return `<details class="code-workspaces${expanded?' is-expanded':''}" data-code-workspaces="${esc(project.id)}" data-ui-key="workspaces-${esc(project.id)}" ${s.open?'open':''}><summary>${esc(t('title'))}</summary><div data-workspaces-body>${content(s)}</div></details>`;}
  async function api(project,body){
    const response=await fetch('/api/v1/workspaces?project='+encodeURIComponent(project),{cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
    let value;try{value=await response.json();}catch(_){const error=Error(t('invalidAck'));error.outcomeUnknown=!!body;throw error;}
    if(!response.ok){const error=Error(global.HubI18n?.error?.(value.message||value.error)||t('failed'));error.outcomeUnknown=!!body&&response.status>=500;throw error;}
    if(!value||typeof value!=='object'||Array.isArray(value)){const error=Error(t('invalidAck'));error.outcomeUnknown=!!body;throw error;}
    return value;
  }
  function content(s){
    const disabled=s.busy||!!s.pending||!s.management;
    const rows=s.items.map(item=>`<article class="workspace-card" data-ui-key="workspace-${esc(item.id)}"><div class="workspace-card-head"><code title="${esc(item.descriptor.root||item.id)}">${esc(item.descriptor.root||item.id)}</code><span class="projects-badge">${esc(t(item.enabled?'enabled':'disabled'))}</span></div><div class="workspace-capabilities"><span>${esc(t(item.capabilities?.source?'sourceAvailable':'sourceUnavailable'))}</span><span>${esc(t(item.capabilities?.git?.state==='detected'?'gitDetected':'gitUnavailable'))}</span><span>${esc(t(item.capabilities?.lsp?.state==='not-checked'?'lspNotChecked':'lspUnavailable'))}</span></div><form data-workspace-form="relocate" data-workspace-id="${esc(item.id)}"><label><span>${esc(t('folder'))}</span><input name="workspaceRoot" value="${esc(s.drafts.get(item.id)??item.descriptor.root??'')}" ${disabled||item.kind!=='local'?'disabled':''}></label><button ${disabled||item.kind!=='local'?'disabled':''}>${esc(t('relocate'))}</button></form><button class="workspace-toggle" type="button" data-workspace-action="enable" data-workspace-id="${esc(item.id)}" ${disabled?'disabled':''}>${esc(t(item.enabled?'disable':'enable'))}</button></article>`).join('');
    return `<div class="projects-section-head"><p class="caption">${esc(t('intro'))}</p><button type="button" data-workspace-action="refresh">${esc(t('refresh'))}</button></div>${s.management?'':`<p class="projects-notice">${esc(t('readOnly'))}</p>`}<p role="status">${esc(s.error)}${s.pending?` <button type="button" data-workspace-action="retry" ${s.busy?'disabled':''}>${esc(t('retry'))}</button>`:''}</p><div class="workspace-list">${rows||`<p class="projects-empty">${esc(t('empty'))}</p>`}</div><form class="workspace-add" data-workspace-form="add"><label><span>${esc(t('folder'))}</span><input name="workspaceRoot" value="${esc(s.drafts.get('new')||'')}" required ${disabled?'disabled':''}></label><button ${disabled?'disabled':''}>${esc(t('add'))}</button></form>`;
  }
  function render(root){
    const html=content(state(root.dataset.codeWorkspaces));
    const body=root.querySelector('[data-workspaces-body]');if(!body)return;
    if(global.HubLiveUI)global.HubLiveUI.patch(body,html);else body.innerHTML=html;
    global.backupStatus?.afterRender?.();
  }
  async function read(root){
    const project=root.dataset.codeWorkspaces,s=state(project);
    const value=await api(project);
    if(value.project!==project||!Number.isInteger(value.revision)||!Array.isArray(value.items))throw Error(t('invalidAck'));
    s.items=value.items;s.revision=value.revision;s.management=value.management===true;s.loaded=true;render(root);
  }
  async function mutate(root,payload){
    const project=root.dataset.codeWorkspaces,s=state(project);if(s.busy)return;
    if(s.pending&&JSON.stringify(s.pending)!==JSON.stringify(payload))return;
    s.pending=payload;s.busy=true;s.error=t('working');render(root);
    try{
      const ack=await api(project,payload);
      if(ack.project!==project||!Number.isInteger(ack.revision)||ack.revision<payload.expected||!ack.workspace?.id||!Array.isArray(ack.roots)||payload.workspace&&ack.workspace.id!==payload.workspace||payload.action==='enable'&&ack.workspace.enabled!==payload.enabled){const error=Error(t('invalidAck'));error.outcomeUnknown=true;throw error;}
      const key=payload.workspace||'new';if(s.drafts.get(key)===payload.root){s.drafts.delete(key);if(key==='new'){const input=root.querySelector('[data-workspace-form="add"] input');if(input)input.value='';}}
      s.pending=null;s.error=t('saved');await read(root);
    }catch(error){if(!error.outcomeUnknown&&!(error instanceof TypeError))s.pending=null;s.error=global.HubI18n?.error?.(error)||t('failed');}
    finally{s.busy=false;render(root);}
  }
  function afterRender(scope=global.document){
    const roots=scope.matches?.('[data-code-workspaces]')?[scope]:[...scope.querySelectorAll('[data-code-workspaces]')];
    for(const root of roots){
      const project=root.dataset.codeWorkspaces,s=state(project);
      if(!root.__workspacesBound){
        root.__workspacesBound=true;
        root.addEventListener('toggle',()=>{s.open=root.open;if(root.open)void read(root).catch(error=>{s.error=global.HubI18n?.error?.(error)||t('failed');render(root);});});
        root.addEventListener('input',event=>{if(event.target.name==='workspaceRoot'){const form=event.target.closest('[data-workspace-form]');if(form)s.drafts.set(form.dataset.workspaceId||'new',event.target.value);}});
        root.addEventListener('submit',event=>{const form=event.target;if(!form.matches('[data-workspace-form]'))return;event.preventDefault();if(!s.management||s.busy||s.pending)return;const body={project,action:form.dataset.workspaceForm,root:form.elements.namedItem('workspaceRoot').value.trim(),expected:s.revision,requestId:global.crypto.randomUUID().replace(/-/g,'')};if(form.dataset.workspaceId)body.workspace=form.dataset.workspaceId;void mutate(root,Object.freeze(body));});
        root.addEventListener('click',event=>{const button=event.target.closest('[data-workspace-action]');if(!button)return;event.preventDefault();const action=button.dataset.workspaceAction;if(action==='refresh'){void read(root).catch(error=>{s.error=global.HubI18n?.error?.(error)||t('failed');render(root);});return;}if(action==='retry'){if(s.pending)void mutate(root,s.pending);return;}if(!s.management||s.busy||s.pending)return;const item=s.items.find(item=>item.id===button.dataset.workspaceId);if(item&&action==='enable')void mutate(root,Object.freeze({project,action:'enable',workspace:item.id,enabled:!item.enabled,expected:s.revision,requestId:global.crypto.randomUUID().replace(/-/g,'')}));});
      }
      if(s.open)root.open=true;render(root);
      if(s.open && !s.loaded && !root.__initialRead){root.__initialRead=true;void read(root).catch(error=>{s.error=global.HubI18n?.error?.(error)||t('failed');render(root);});}
    }
  }
  global.HubWorkspacesUI={card,afterRender};
  global.HubI18n?.onChange?.(()=>afterRender());
})(typeof window==='undefined'?globalThis:window);
