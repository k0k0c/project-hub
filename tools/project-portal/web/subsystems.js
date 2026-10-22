"use strict";
(function (global) {
  const t = key => global.HubI18n?.t?.(`subsystems.${key}`) || key;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = name => global.lucide?.icons?.[name] ? global.lucide.createElement(global.lucide.icons[name],{'aria-hidden':'true',width:16,height:16,'stroke-width':1.6}).outerHTML : '';
  let mounted = null;
  function state(v) { return v.subsystemEditor ||= {open:false, draft:null, confirm:null, pending:null, busy:false, message:''}; }
  function project(v) { return {id:'project:'+v.project, type:'project', title:t('projectOverview')}; }
  function button(v,action,label,id='',extra='',image='') {
    const s=state(v), disabled=s.busy || !!s.pending && !['resume','retry','close'].includes(action);
    return `<button type="button" data-subsystem-action="${action}" data-subsystem-id="${esc(id)}" ${extra}${disabled?' disabled':''}>${image?icon(image):''}<span>${esc(t(label))}</span></button>`;
  }
  function actions(v,selected,{menu=false}={}) {
    if (!v.context || v.mode!=='architecture') return '';
    const root=selected?.type==='project', component=(v.context.policy.components||[]).find(c=>c.id===selected?.id);
    if(!root&&!component)return '';
    const id=component?.id||'', extra=menu?'role="menuitem"':'', add=(action,label,image='')=>button(v,action,label,id,extra,image);
    const body=root?add('overview','overview','Sparkles')+add('first-level','firstLevel','Sparkles')+add('new','create','Plus'):
      add('edit','editSubsystem')+add('new','createChild','Plus')+add('analyze','analyze','Sparkles')+add('remove','remove');
    const resume=state(v).pending?add('resume','retry'):'';
    return menu?`<div class="r-label">${esc(t(root?'projectActions':'subsystemActions'))}</div>${body}${resume}`:
      `<section class="k-inspector-section subsystem-actions" data-ui-key="subsystem-actions"><h3>${esc(t(root?'projectActions':'subsystemActions'))}</h3>${body}${resume}</section>`;
  }
  function projectInspector(v,renderDescription) {
    const overview=v.context?.projectOverview,description=typeof overview?.description==='string'?overview.description.trim():'';
    const body=description?`<div class="k-markdown">${renderDescription?renderDescription(description):description.split(/\n\s*\n/u).map(paragraph=>`<p>${esc(paragraph).replace(/\n/gu,'<br>')}</p>`).join('')}</div>`: `<p>${esc(t('intro'))}</p>`;
    return `<article class="k-inspector subsystem-project"><header class="k-inspector-head"><h2>${esc(t('projectOverview'))}</h2></header>${body}${actions(v,project(v))}</article>`;
  }
  function dialogContent(v) {
    const s=state(v), d=s.draft, components=v.context.policy.components||[], disabled=s.busy||!!s.pending;
    const label=d?t(d.action==='create'?'create':'editSubsystem'):t({overview:'overview','first-level':'firstLevel',analyze:'analyze',remove:'remove'}[s.action]||'subsystemActions');
    const target=components.find(c=>c.id===s.targetId)?.title||t('projectOverview');
    const header=`<header><div><small>${esc(target)}</small><h2 id="subsystem-dialog-title">${esc(label)}</h2></div>${button(v,'close','close','','aria-label="'+esc(t('close'))+'"')}</header>`;
    const status=`<p class="subsystem-status" role="status" aria-live="polite"${s.message?'':' hidden'}>${esc(s.message)}</p>`;
    const footer=body=>`<footer>${body}</footer>`;
    if(d){
      // Exclude the complete descendant chain, not just the edited node.
      const excluded=new Set([d.id]);let added=true;
      while(added){added=false;for(const c of components)if(excluded.has(c.parent)&&!excluded.has(c.id)){excluded.add(c.id);added=true;}}
      return `${header}<form data-subsystem-form data-ui-key="subsystem-editor"><div class="subsystem-dialog-body" data-scroll-key="subsystem-dialog-body"><p class="subsystem-hint">${esc(t(d.action==='create'?'createHelp':'editHelp'))}</p><fieldset${disabled?' disabled':''}><div class="subsystem-fields"><label>${esc(t('title'))}<input name="subsystemTitle" value="${esc(d.title)}" required maxlength="300" autocomplete="off" autofocus></label><label>${esc(t('parent'))}<select name="subsystemParent"><option value="">${esc(t('topLevel'))}</option>${components.filter(c=>!excluded.has(c.id)).map(c=>`<option value="${esc(c.id)}" ${c.id===d.parent?'selected':''}>${esc(c.title)}</option>`).join('')}</select></label></div><label>${esc(t('description'))}<textarea name="subsystemDescription" rows="4" maxlength="1200">${esc(d.description)}</textarea></label><label>${esc(t('paths'))}<textarea name="subsystemPaths" rows="4" spellcheck="false" placeholder="src/">${esc(d.paths)}</textarea></label><p class="subsystem-hint">${esc(t('pathsHelp'))}</p></fieldset>${status}</div>${footer(s.pending?button(v,'retry','retry'):`<button type="submit" class="subsystem-primary"${disabled?' disabled':''}>${esc(t('save'))}</button>`+button(v,'close','cancel'))}</form>`;
    }
    const confirmation=s.confirm?`<p>${esc(t('removeConfirm'))}</p>`:'';
    return `${header}<div class="subsystem-dialog-body" data-scroll-key="subsystem-dialog-body">${confirmation}${status}</div>${footer(s.confirm?button(v,'confirm','confirmRemove','','class="subsystem-danger"')+button(v,'close','cancel'):s.pending?button(v,'retry','retry'):button(v,'close','close'))}`;
  }
  function dispose(v) {
    if(mounted?.v!==v)return;
    const old=mounted;mounted=null;old.node.remove();
  }
  function mount(v,host) {
    const s=state(v);
    if(!global.document?.createElement)return;
    if(mounted?.v!==v&&mounted)dispose(mounted.v);
    if(!s.open){
      const trigger=mounted?.trigger;dispose(v);
      if(trigger?.isConnected)trigger.focus({preventScroll:true});
      else if(s.returnAction){
        const buttons=[...host.root().querySelectorAll('[data-subsystem-action]')];
        const replacement=buttons.find(n=>n.dataset.subsystemAction===s.returnAction&&n.dataset.subsystemId===s.targetId)||
          [...host.root().querySelectorAll('[data-r-open],[data-k-select]')].find(n=>(n.dataset.rOpen??n.dataset.kSelect)===(s.targetId||''));
        replacement?.focus({preventScroll:true});
      }
      s.returnAction=null;return;
    }
    if(!mounted){
      const node=global.document.createElement('dialog');node.className='subsystem-dialog';node.setAttribute('aria-labelledby','subsystem-dialog-title');
      mounted={v,node,host,trigger:s.trigger||global.document.activeElement};s.trigger=null;global.document.body.append(node);
      node.addEventListener('click',event=>handle(v,event,mounted?.host||host));
      node.addEventListener('submit',event=>handle(v,event,mounted?.host||host));
      for(const type of ['input','change'])node.addEventListener(type,event=>input(v,event));
      node.addEventListener('cancel',event=>{event.preventDefault();if(!s.busy){s.open=false;host.draw();}});
      node.addEventListener('close',()=>{if(mounted?.node===node){s.open=false;host.draw();}});
      node.innerHTML=dialogContent(v);node.showModal();return;
    }
    mounted.host=host;
    if(global.HubLiveUI)global.HubLiveUI.patch(mounted.node,dialogContent(v),{preserveInputs:false});
    else mounted.node.innerHTML=dialogContent(v);
  }
  function input(v,event) {
    const d=state(v).draft, name=event.target?.name;
    const fields={subsystemTitle:'title',subsystemParent:'parent',subsystemPaths:'paths',subsystemDescription:'description'};
    if(d && fields[name]){d[fields[name]]=event.target.value;if(name==='subsystemDescription')d.descriptionDirty=true;}
  }
  async function save(v,host,action,id,patch,expected) {
    const s=state(v);if(s.busy)return;
    s.busy=true;s.message=t('working');host.draw();
    try {
      if(!s.pending) {
        const result=await host.request('subsystem-plan',{expected:expected ?? s.draft?.expected ?? v.context.revision,operation:action,identifier:id,patch,key:'subsystem:'+global.crypto.randomUUID(),reason:t('changeReason')},true);
        if(!result?.request || !Array.isArray(result.request.operations) || !Number.isInteger(result.request.expected))throw Error(t('failed'));
        s.pending=result.request;
      }
      await host.request('changeset',s.pending,true);
      s.pending=null;s.draft=null;s.message=t('saved');await host.refresh();
    } catch(error) {
      // Retain the exact changeset until read-back or retry confirms its receipt.
      if(error.status>=400&&error.status<500)s.pending=null;
      s.message=global.HubI18n?.error?.(error) || t('failed');
    } finally {s.busy=false;host.draw();}
  }
  function handle(v,event,host) {
    if(v.mode!=='architecture')return false;
    const form=event.type==='submit' && event.target.matches?.('[data-subsystem-form]');
    const button=event.type==='click' && event.target.closest?.('[data-subsystem-action]');
    if(!form && !button)return false;
    event.preventDefault();const s=state(v);
    if(s.busy)return true;
    if(button?.dataset?.subsystemAction==='close'){s.open=false;host.draw();return true;}
    if(button?.dataset?.subsystemAction==='resume'){s.trigger=button;s.returnAction='resume';s.open=true;host.draw();return true;}
    if(form&&s.pending)return true;
    if(form){const d=s.draft;void save(v,host,d.action,d.id,{title:d.title,parent:d.parent||null,paths:d.paths.split(/\r?\n/).map(x=>x.trim()).filter(Boolean),...(d.action==='create'||d.descriptionDirty?{description:d.description}:{})});return true;}
    let action=button.dataset.subsystemAction,id=button.dataset.subsystemId, confirmed=null;
    if(!s.open){s.trigger=button.closest?.('.r-context')||typeof button.focus!=='function'?global.document?.activeElement:button;}
    if(action==='retry'){void save(v,host);return true;}
    if(s.pending)return true;
    if(['overview','first-level','analyze'].includes(action)){
      const root=action!=='analyze',target=root?project(v):(v.context.policy.components||[]).find(c=>c.id===id);
      if(!target||!host.openResearch)return true;
      s.confirm=null;s.open=false;s.message='';
      void host.openResearch({id:root?'project:'+v.project:id,template:action==='first-level'?'decompose':'explain',title:target.title,selected:target});
      return true;
    }
    if(action==='cancel-confirm'){s.confirm=null;s.open=false;host.draw();return true;}
    if(action==='confirm'){
      if(!s.confirm)return true;
      confirmed=s.confirm;action=confirmed.action;id=confirmed.id;s.confirm=null;
    }else if(action==='remove'){
      s.action=action;s.targetId=id||'';s.returnAction=action;s.open=true;s.draft=null;s.message='';
      if(v.research)v.research.dialog=null;v.panel='';
      s.confirm={action,id,expected:v.context.revision};host.draw();return true;
    }else s.confirm=null;
    if(action==='cancel'){s.draft=null;s.message='';s.open=false;host.draw();return true;}
    if(action==='new'){s.action=action;s.targetId=id||'';s.returnAction=action;s.open=true;s.message='';s.draft={action:'create',id:'subsystem:'+global.crypto.randomUUID(),title:'',parent:id||'',paths:'',description:'',expected:v.context.revision};if(v.research)v.research.dialog=null;v.panel='';host.draw();return true;}
    const component=(v.context.policy.components||[]).find(c=>c.id===id);
    if(action==='edit' && component){s.action=action;s.targetId=id;s.returnAction=action;s.open=true;s.message='';s.draft={action:'update',id,title:component.title,parent:component.parent||'',paths:(component.paths||[]).join('\n'),description:component.description||'',expected:v.context.revision};if(v.research)v.research.dialog=null;v.panel='';host.draw();return true;}
    if(action==='remove' && component){void save(v,host,'remove',id,{},confirmed.expected);return true;}
    return true;
  }
  global.HubSubsystems={actions,project,projectInspector,dialogContent,mount,dispose,input,handle};
})(typeof window==='undefined'?globalThis:window);
