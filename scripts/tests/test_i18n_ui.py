"""Exercise the shipped locale catalog, engine and selected real UI consumers."""
import subprocess
import unittest
from pathlib import Path


WEB = Path(__file__).resolve().parents[2] / 'tools' / 'project-portal' / 'web'

HARNESS = r'''
const assert = require('assert'), fs = require('fs'), path = require('path'), vm = require('vm');
const web = process.argv[1], scenario = process.argv[2];
const read = name => fs.readFileSync(path.join(web, name), 'utf8');
const revision = 'a'.repeat(64), nextRevision = 'b'.repeat(64);
class Node {
  constructor(dataset={}, text='') { this.dataset=dataset; this.textContent=text; this.attributes={}; this.value=''; }
  setAttribute(name,value) { this.attributes[name]=value; }
}
function context(initial='ru') {
  const known = new Node({i18n:'shell.projects'},'Проекты');
  const label = new Node({i18nLabel:'shell.chooseProject'});
  const initialLabel = new Node({i18nInitial:'shell.connecting'},'Подключение…');
  const userText = new Node({},'Проект пользователя <имя> & {v0}');
  const userInput = new Node(); userInput.value='Несохранённый черновик <b> & $&';
  const replies=[], calls=[], events=[], listeners=new Map();
  const global={
    console, Intl, URL, URLSearchParams, location:{search:'',origin:'http://127.0.0.1:8769'},
    document:{documentElement:{dataset:{hubLocale:initial}},
      querySelectorAll(selector){return selector==='[data-i18n]' ? [known] : selector==='[data-i18n-label]' ? [label] : selector==='[data-i18n-initial]' ? [initialLabel] : [];},
      querySelector(){return null;}},
    fetch:async(url,options={})=>{
      calls.push({url,options}); assert.ok(replies.length,'unexpected network request');
      const reply=replies.shift(); if(reply instanceof Error) throw reply;
      return {ok:reply.ok!==false,json:async()=>{if(reply.invalidJson)throw Error('invalid JSON');return reply.body;}};
    },
    CustomEvent:class {constructor(type){this.type=type;}},
    dispatchEvent(event){events.push(event);for(const fn of listeners.get(event.type)||[])fn(event);},
    addEventListener(type,fn){if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(fn);},
    setTimeout(){return 1;},clearTimeout(){},window:null
  };
  global.window=global; vm.createContext(global);
  vm.runInContext(read('locale-catalog.js'),global,{filename:'locale-catalog.js'});
  vm.runInContext(read('i18n.js'),global,{filename:'i18n.js'});
  return {global,known,label,initialLabel,userText,userInput,replies,calls,events};
}
function appConstants(global) {
  const source=read('app.js');
  function between(start,end) {
    const begin=source.indexOf(start), finish=source.indexOf(end,begin+start.length);
    assert.ok(begin>=0 && finish>begin,'real app constant boundary changed: '+start);
    return source.slice(begin,finish);
  }
  const blocker=source.match(/^const blockerLabels = .*;\r?$/m);
  assert.ok(blocker,'real blockerLabels declaration missing');
  const callbackStart=source.indexOf('globalThis.HubI18n?.onChange?.(');
  assert.ok(callbackStart>=0,'real app language callback missing');
  // Run declarations and their real registered refresh callback, without
  // bootstrapping unrelated network polling, dialogs or application state.
  const bounded=between('const labels = {','const kindLabels = {')+
    between('const kindLabels = {','const icons = {')+
    between('const navigation = [','let state,')+blocker[0]+'\n'+source.slice(callbackStart);
  vm.runInContext(bounded,global,{filename:'app.js (static interface constants and language callback)'});
  vm.runInContext('globalThis.references = {labels,kindLabels,navigation,blockerLabels};',global);
  return ()=>JSON.parse(vm.runInContext('JSON.stringify({labels,kindLabels,navigation,blockerLabels})',global));
}
function templateDom(h) {
  let selection=null;
  class DomNode {
    constructor(type=1, name='div', value='') { this.nodeType=type;this.nodeName=name.toUpperCase();this.childNodes=[];this.attributes={};this.parentNode=null;this.isConnected=true;this._value=value;this.value='';this.selectionStart=0;this.selectionEnd=0;this.writes=0; }
    get nodeValue() { return this.nodeType===3 ? this._value : null; }
    set nodeValue(value) {
      this._value=value;
      // Assigning a selected text node can adjust the browser's live Range.
      // Restoration must use HubLiveUI's real (root, snapshot) contract.
      if(selection?.anchorNode===this) {selection.anchorOffset=0;selection.focusOffset=0;}
    }
    setAttribute(name,value) {this.attributes[name]=String(value);}
    getAttribute(name) {return Object.hasOwn(this.attributes,name)?this.attributes[name]:null;}
    hasAttribute(name) {return Object.hasOwn(this.attributes,name);}
    append(node) {node.parentNode=this;this.childNodes.push(node);}
    set innerHTML(html) {this.writes++;this.childNodes=parse(html).childNodes;this.childNodes.forEach(child=>child.parentNode=this);}
    get textContent() {return this.nodeType===3?this.nodeValue:this.childNodes.map(child=>child.textContent).join('');}
    set textContent(value) {this.childNodes=[];if(value)this.append(new DomNode(3,'#text',value));}
    querySelector(selector) {
      const find=node=>node.nodeType===1 && node.getAttribute('id')===selector.slice(1) ? node : node.childNodes.map(find).find(Boolean);
      return find(this);
    }
  }
  function parse(html) {
    const root=new DomNode(11,'#document-fragment'), stack=[root];
    for(const token of String(html).match(/<[^>]+>|[^<]+/g)||[]) {
      if(token.startsWith('</')) {stack.pop();continue;}
      if(token.startsWith('<')) {
        const match=token.match(/^<([\w-]+)([\s\S]*?)\/?\s*>$/);
        assert.ok(match,'unsupported fixture markup token '+token);
        const node=new DomNode(1,match[1]);
        for(const attr of match[2].matchAll(/([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) node.setAttribute(attr[1],attr[2]??attr[3]??attr[4]??'');
        stack[stack.length-1].append(node);
        if(!/^(input|br|hr|img|meta|link)$/i.test(match[1]) && !token.endsWith('/>')) stack.push(node);
      } else stack[stack.length-1].append(new DomNode(3,'#text',token));
    }
    assert.equal(stack.length,1,'fixture markup tree is unbalanced');return root;
  }
  h.global.document.createElement=name=>name==='template' ? {
    content:null,set innerHTML(html){this.content=parse(html);}
  } : new DomNode(1,name);
  return {DomNode,parse,get selection(){return selection;},set selection(value){selection=value;}};
}
const scenarios = {
  backendCapabilityReasons() {
    const h=context('ru'), g=h.global, source=read('app.js');
    vm.runInContext(source.slice(source.indexOf('function gitPage('),source.indexOf('function diagnosticAge('))+
      source.slice(source.indexOf('function chatsHistoryView('),source.indexOf('function taskChats(')),g);
    const userTitle='Observation is being prepared <user title>';
    Object.assign(g,{escape:x=>String(x??'').replaceAll('<','&lt;').replaceAll('>','&gt;'),title:()=>'',
      chatsViewKey:'fixture',chatsKey:()=> 'fixture',chatsLoading:false,chatsError:'',
      diagnosticChat:s=>'<article>'+g.escape(s.title)+'</article>',
      chatsData:{sessions:[{id:'user',title:userTitle}],warnings:['Observation is being prepared'],
        discovery:{available:false,reason:'No Hub observations have been recorded'}},
      gitData:{repository:{available:false,reason:'Connect a code workspace to use Git'}}});
    const before=JSON.stringify([g.chatsData,g.gitData]);
    for(const locale of ['ru','en','ru']) {
      g.HubI18n.apply(locale);
      const html=g.chatsHistoryView();
      for(const key of ['app.observationPending','app.observationEmpty'])
        assert.ok(html.includes('<p class="notice" role="status">'+g.HubLocaleCatalog[key][locale]+'</p>'));
      assert.ok(html.includes(g.escape(userTitle)),'chat title must remain user content');
      assert.ok(g.gitPage().includes('<div class="notice">'+g.HubLocaleCatalog['app.gitWorkspaceRequired'][locale]+'</div>'));
      assert.equal(JSON.stringify([g.chatsData,g.gitData]),before,'render mutated backend snapshots');
    }
    g.gitData.repository.reason='';
    assert.ok(g.gitPage().includes(g.HubLocaleCatalog['app.00b50534ae90'].ru),'missing reason lost its fallback');
  },
  systemEventTitles() {
    const h=context('en'), g=h.global, source=read('app.js');appConstants(g);
    vm.runInContext(source.slice(source.indexOf('function eventTitle('),source.indexOf('function estimate(',source.indexOf('function eventTitle('))),g);
    const original={id:'hub-close-fixture',kind:'task.updated',title:'Задача закрыта',patch:{status:'done',closedManually:false},taskId:'fixture',detail:'Результат пользователя <не переводить>'};
    const before=JSON.stringify(original), announcement={textContent:''};
    Object.assign(g,{$:()=>announcement,state:{tasks:[{id:'fixture',title:'Название пользователя'}]},escape:x=>String(x??'').replaceAll('<','&lt;').replaceAll('>','&gt;'),date:()=>'',taskLink:()=> '#task',evidence:()=>'',eventTone:()=>'',next:{events:[original]}});
    g.updateAnnouncement(g.next);assert.equal(announcement.textContent,'Task closed');
    const html=g.eventView(original);assert.ok(html.includes('<h3>Task closed</h3>'));
    assert.ok(html.includes('Название пользователя'));assert.ok(html.includes('Результат пользователя &lt;не переводить&gt;'));
    assert.equal(JSON.stringify(original),before);
    for(const patch of [{status:'active',closedManually:false},{status:'done'}, {status:'done',closedManually:'false'}])assert.equal(g.eventTitle({...original,patch}),original.title);
    assert.equal(g.eventTitle({...original,title:'Мой отчёт'}),'Мой отчёт');
    assert.equal(g.eventTitle({...original,kind:'note'}),original.title);
    assert.equal(g.eventTitle({kind:'task.created',title:'Задача закрыта'}),'Задача закрыта');
    assert.equal(g.eventTitle({kind:'task.reopened',title:'Задача переоткрыта',change:{sourceEventId:'source'}}),'Task reopened');
    assert.equal(g.eventTitle({kind:'task.reopened',title:'Задача переоткрыта'}),'Задача переоткрыта');
    g.HubI18n.apply('ru');g.updateAnnouncement(g.next);assert.equal(announcement.textContent,'Задача закрыта');
  },
  announcementLanguageSwitch() {
    const h=context('en'), g=h.global, source=read('app.js');appConstants(g);
    vm.runInContext(source.slice(source.indexOf('function eventTitle('),source.indexOf('function eventView(')),g);
    const announcement={textContent:''},navigation={dataset:{page:'settings'}};
    Object.assign(g,{$:selector=>selector==='#navigation'?navigation:announcement,
      state:{events:[]},connected:true,render(){},setConnection(){},updateFreshness(){},loadProjects:()=>Promise.resolve()});
    const start=source.indexOf("window.addEventListener('hub-language-changed'");
    vm.runInContext(source.slice(start,source.indexOf("document.addEventListener('click'",start)),g);
    g.updateAnnouncement();assert.equal(announcement.textContent,'Project loaded');
    for(const [event,english,russian] of [
      [null,'Project loaded','Проект загружен'],
      [{kind:'task.updated',title:'Задача закрыта',patch:{status:'done',closedManually:true}},'Task closed','Задача закрыта'],
      [{kind:'note',title:'Пользовательский результат'},'Пользовательский результат','Пользовательский результат'],
    ]) {
      g.state.events=event?[event]:[];g.updateAnnouncement();
      const before=JSON.stringify(g.state.events);
      g.HubI18n.apply('ru');assert.equal(announcement.textContent,russian);
      g.HubI18n.apply('en');assert.equal(announcement.textContent,english);
      assert.equal(JSON.stringify(g.state.events),before);
    }
  },
  catalog() {
    const {global}=context('en'), entries=Object.entries(global.HubLocaleCatalog);
    assert.ok(entries.length>1000,'shipped catalog not loaded');
    const placeholders=text=>Array.from(text.matchAll(/\{(\w+)\}/g),match=>match[1]).sort();
    for(const [key,item] of entries) {
      assert.equal(typeof item.en,'string',key+' lacks English');
      assert.ok(item.en.trim(),key+' has empty English');
      assert.ok(!/[А-Яа-яЁё]/.test(item.en),key+' still contains Cyrillic: '+item.en);
      assert.deepEqual(placeholders(item.en),placeholders(item.ru),key+' changes interpolation parameters');
    }
    for(const filename of fs.readdirSync(web).filter(name=>name.endsWith('.js') && name!=='locale-catalog.js')) {
      for(const match of read(filename).matchAll(/HubI18n(?:\?\.|\.)t(?:\?\.)?\(\s*["']([^"']+)["']\s*(?=[,)])/g)) {
        assert.ok(Object.hasOwn(global.HubLocaleCatalog,match[1]),filename+' references absent interface message '+match[1]);
      }
    }
    for(const [filename,prefix] of [['workspaces.js','workspaces.'],['subsystems.js','subsystems.'],['agent-providers.js','provider.']]) {
      for(const match of read(filename).matchAll(/\bt\(\s*["']([^"']+)["']\s*(?=[,)])/g)) {
        assert.ok(Object.hasOwn(global.HubLocaleCatalog,prefix+match[1]),filename+' references absent interface message '+prefix+match[1]);
      }
    }
  },
  interpolation() {
    const {global}=context('en'), catalog=global.HubLocaleCatalog;
    const [key,item]=Object.entries(catalog).find(([key,item])=>key.startsWith('app.') && item.en.includes('{v0}') && item.en.includes('{v1}'));
    assert.ok(key,'no real parameterized app message found');
    const values={v0:'Проект {v1} <tag attr="значение">& $& $` $\'\n',v1:'<strong>Работа & {v0}</strong>',v2:'Пользователь'};
    const expected=item.en.replace(/\{(\w+)\}/g,(all,name)=>Object.hasOwn(values,name)?values[name]:all);
    const actual=global.HubI18n.t(key,values);
    assert.equal(actual,expected,'user data or markup was changed or recursively interpolated');
    assert.deepEqual(Buffer.from(actual,'utf8'),Buffer.from(expected,'utf8'),'UTF-8 parameter bytes changed');
    assert.equal(global.HubI18n.t('projects.missingNamedKey','Свой проект <i>данные</i>'),'Свой проект <i>данные</i>','explicit fallback was replaced with a key');
  },
  interfaceSwitch() {
    const h=context('en'), api=h.global.HubI18n, before=[h.userText.textContent,h.userInput.value];
    assert.equal(api.locale,'en');assert.equal(h.global.document.documentElement.lang,'en');
    assert.equal(h.known.textContent,h.global.HubLocaleCatalog['shell.projects'].en);
    assert.equal(h.initialLabel.textContent,h.global.HubLocaleCatalog['shell.connecting'].en,'initial status was not English before app boot');
    let changes=0;api.onChange(()=>changes++);
    api.apply('ru');
    assert.equal(h.known.textContent,h.global.HubLocaleCatalog['shell.projects'].ru);
    assert.equal(h.label.attributes['aria-label'],h.global.HubLocaleCatalog['shell.chooseProject'].ru);
    assert.equal(h.global.document.documentElement.lang,'ru');
    assert.equal(changes,1);assert.equal(h.events[0].type,'hub-language-changed');
    assert.deepEqual([h.userText.textContent,h.userInput.value],before,'language switch mutated user content');
    api.apply('ru');assert.equal(changes,1);assert.equal(h.events.length,1,'unchanged locale dispatched a change');
    assert.throws(()=>api.apply('xx'));assert.equal(api.locale,'ru');
  },
  appBootAndRefresh() {
    const h=context('en'), snapshot=appConstants(h.global), api=h.global.HubI18n;
    const initial=snapshot();
    assert.equal(initial.labels.active,h.global.HubLocaleCatalog['app.59a28f1b11df'].en);
    assert.equal(initial.navigation[0][1],h.global.HubLocaleCatalog['app.7641ad9bafb2'].en);
    assert.ok(!/[А-Яа-яЁё]/.test(JSON.stringify(initial)),'static app labels were initialized in Russian');
    api.apply('ru');const russian=snapshot();
    assert.equal(russian.labels.active,h.global.HubLocaleCatalog['app.59a28f1b11df'].ru);
    assert.equal(russian.kindLabels['task.created'],h.global.HubLocaleCatalog['app.756c6c64e23e'].ru);
    assert.equal(russian.navigation[0][1],h.global.HubLocaleCatalog['app.7641ad9bafb2'].ru);
    assert.equal(russian.blockerLabels.technical,h.global.HubLocaleCatalog['app.61d077d3515c'].ru);
    assert.equal(vm.runInContext('references.labels===labels && references.kindLabels===kindLabels && references.navigation===navigation && references.blockerLabels===blockerLabels',h.global),true,'language callback invalidates held references');
    api.apply('en');assert.deepEqual(snapshot(),initial,'real callback failed to restore static labels');
    const html=read('index.html');
    for(const filename of ['locale-catalog.js','i18n.js','app.js']) {
      const tag=html.match(new RegExp('<script[^>]+src="/'+filename.replace('.', '\\.')+'"[^>]*>'));
      assert.ok(tag && /\bdefer\b/.test(tag[0]),filename+' must execute in document order after parsing');
    }
    assert.ok(html.indexOf('src="/locale-catalog.js"')<html.indexOf('src="/i18n.js"'));
    assert.ok(html.indexOf('src="/i18n.js"')<html.indexOf('src="/app.js"'),'app loads before saved locale is applied');
  },
  projectsFallback() {
    const h=context('en');
    assert.ok(!Object.hasOwn(h.global.HubLocaleCatalog,'projects.title'),'named-key fallback case no longer exercises an absent key');
    vm.runInContext(read('projects.js'),h.global,{filename:'projects.js'});
    const english=h.global.HubProjectsUI.page();
    assert.ok(english.includes('Projects') && english.includes('Add project'),'real project page did not use translated fallback values');
    assert.ok(!/projects\.[a-zA-Z0-9]+/.test(english),'unknown named projects key displayed');
    assert.ok(!/[А-Яа-яЁё]/.test(english),'real project page English fallback remained Russian');
    h.global.HubI18n.apply('ru');assert.ok(h.global.HubProjectsUI.page().includes('Проекты'));
    h.global.HubI18n.apply('en');assert.equal(h.global.HubProjectsUI.page(),english,'project fallback constants failed to refresh');
  },
  async preferenceFailures() {
    const failures=[{ok:false,body:{language:'en',revision:nextRevision}},
      {ok:false,body:{error:'preferences_conflict'}},{body:null},{body:{}},{body:[]},
      {body:{language:'en',revision:1}},{body:{language:'en',revision:'short'}},
      {body:{language:'invalid',revision:nextRevision}},{invalidJson:true},new Error('network unavailable')];
    for(const failure of failures) {
      const h=context('ru'), api=h.global.HubI18n;
      h.replies.push({body:{language:'ru',revision}});await api.load();
      let changes=0;api.onChange(()=>changes++);
      h.replies.push(failure);await assert.rejects(()=>api.save('en'));
      assert.equal(api.locale,'ru','failed/malformed save switched locale');
      assert.equal(changes,0);assert.equal(h.events.length,0);
      const payload=JSON.parse(h.calls[1].options.body);
      assert.deepEqual(payload,{language:'en',expected:revision});
      const conflict=failure.body?.error==='preferences_conflict';
      if(conflict) h.replies.push({body:{language:'ru',revision:nextRevision}});
      h.replies.push({body:{language:'en',revision:nextRevision}});await api.save('en');
      const posts=h.calls.filter(call=>call.options.method==='POST');
      assert.equal(JSON.parse(posts[1].options.body).expected,conflict?nextRevision:revision,'retry did not preserve or refresh the authoritative preference revision');
      assert.equal(api.locale,'en');assert.equal(changes,1);
    }
    for(const body of [null,{},[],{language:'en',revision:'bad'}]) {
      const h=context('ru');h.replies.push({body});
      await assert.rejects(()=>h.global.HubI18n.load());assert.equal(h.global.HubI18n.locale,'ru');
    }
  },
  async wrongLanguageAcknowledgement() {
    const h=context('ru'), api=h.global.HubI18n;
    h.replies.push({body:{language:'ru',revision}});await api.load();
    h.replies.push({body:{language:'ru',revision:nextRevision}});
    await assert.rejects(()=>api.save('en'),'an ACK for another language cannot confirm the requested save');
    assert.equal(api.locale,'ru');
    h.replies.push({body:{language:'en',revision:nextRevision}});await api.save('en');
    assert.equal(JSON.parse(h.calls[2].options.body).expected,revision,'wrong-language ACK replaced the valid revision');
  },
  templatePreservesViewerState() {
    const h=context('ru'), dom=templateDom(h), source=read('viewer.js');
    const begin=source.indexOf('const dialog = '), end=source.indexOf('  dialog.innerHTML = interfaceMarkup();');
    assert.ok(begin>=0 && end>begin,'real viewer skeleton factory boundary changed');
    h.global.uiIcon=name=>'<svg><path d="'+name+'"></path></svg>';
    vm.runInContext(source.slice(begin,end)+'\nglobalThis.viewerRoot=dialog;globalThis.viewerMarkup=interfaceMarkup;',h.global,{filename:'viewer.js (real interface skeleton factory)'});
    const root=h.global.viewerRoot, markup=h.global.viewerMarkup;
    root.innerHTML=markup();
    h.global.HubI18n.bindTemplate(root,markup);
    const dialogCallback=source.match(/^\s*globalThis\.HubI18n\?\.onChange\?\.\(.*dialog\.setAttribute.*\r?$/m);
    assert.ok(dialogCallback,'real viewer dialog accessibility callback missing');
    vm.runInContext(dialogCallback[0],h.global,{filename:'viewer.js (real dialog accessibility callback)'});
    const originalText=[], originalAttributes=[];
    function rememberSkeleton(node) {
      if(node.nodeType===3 && node.nodeValue.trim())originalText.push(node);
      if(node.nodeType===1)for(const attr of ['aria-label','title','placeholder'])if(node.hasAttribute(attr))originalAttributes.push([node,attr]);
      node.childNodes.forEach(rememberSkeleton);
    }
    rememberSkeleton(root);
    const close=root.querySelector('#artifact-close'), search=root.querySelector('#artifact-search'),
      body=root.querySelector('#artifact-body'), name=root.querySelector('#artifact-name'), toc=root.querySelector('#artifact-toc');
    const heading=root.childNodes[0].childNodes[0].childNodes[0].childNodes[0];
    assert.equal(heading.nodeType,3,'real viewer title text path changed');
    const userDocument='Документ пользователя <b>данные & {v0}</b>', userName='Мой документ — не переводить';
    body.textContent=userDocument;name.textContent=userName;toc.textContent='Содержание пользовательского файла';
    search.value='Введённый поиск';search.selectionStart=2;search.selectionEnd=9;
    const file=new dom.DomNode(1,'input');file.setAttribute('type','file');file.files=[{name:'Отчёт.pdf'}];root.append(file);
    const files=file.files;
    h.global.document.activeElement=search;
    dom.selection={anchorNode:heading,focusNode:heading,anchorOffset:2,focusOffset:6};
    const captured=dom.selection;
    let captures=0, restores=0;
    h.global.HubLiveUI={
      capture(target){assert.equal(target,root);captures++;return {focus:h.global.document.activeElement,start:search.selectionStart,end:search.selectionEnd,range:{...dom.selection}};},
      restore(target,saved){assert.equal(target,root,'bindTemplate must pass root to HubLiveUI.restore');assert.ok(saved,'missing captured viewer state');restores++;h.global.document.activeElement=saved.focus;search.selectionStart=saved.start;search.selectionEnd=saved.end;Object.assign(dom.selection,saved.range);}
    };
    const beforeWrites=root.writes, closeIdentity=close, searchIdentity=search;
    h.global.HubI18n.apply('en');
    const expected=dom.parse(markup()), expectedClose=expected.querySelector('#artifact-close'), expectedSearch=expected.querySelector('#artifact-search');
    assert.equal(close.getAttribute('aria-label'),expectedClose.getAttribute('aria-label'));
    assert.equal(close.getAttribute('title'),expectedClose.getAttribute('title'));
    assert.equal(search.getAttribute('placeholder'),expectedSearch.getAttribute('placeholder'));
    assert.ok(!/[А-Яа-яЁё]/.test(heading.nodeValue),'existing skeleton text did not switch to English');
    for(const node of originalText)assert.ok(!/[А-Яа-яЁё]/.test(node.nodeValue),'an original viewer text label remained Russian');
    for(const [node,attr] of originalAttributes)assert.ok(!/[А-Яа-яЁё]/.test(node.getAttribute(attr)),'an original viewer accessibility attribute remained Russian');
    assert.equal(body.textContent,userDocument,'document content in an originally empty slot was translated');
    assert.equal(name.textContent,userName);assert.equal(toc.textContent,'Содержание пользовательского файла');
    assert.equal(search.value,'Введённый поиск');assert.equal(file.files,files);
    assert.equal(root.writes,beforeWrites,'language switch replaced the viewer root content');
    assert.equal(root.querySelector('#artifact-close'),closeIdentity);assert.equal(root.querySelector('#artifact-search'),searchIdentity);
    assert.equal(h.global.document.activeElement,search);assert.equal(search.selectionStart,2);assert.equal(search.selectionEnd,9);
    assert.equal(dom.selection,captured);assert.equal(dom.selection.anchorNode,heading);assert.equal(dom.selection.anchorOffset,2);assert.equal(dom.selection.focusOffset,6);
    assert.equal(captures,1);assert.equal(restores,1);
    // A replacement at the original label path belongs to the new content,
    // rather than being a fresh translation target for an old binding.
    const parent=heading.parentNode, replacement=new dom.DomNode(3,'#text','Добавленные пользователем данные');
    replacement.parentNode=parent;parent.childNodes[0]=replacement;heading.isConnected=false;
    h.global.HubI18n.apply('ru');
    assert.equal(replacement.nodeValue,'Добавленные пользователем данные');assert.equal(body.textContent,userDocument);
  },
  subscriberFailureIsIsolated() {
    const h=context('ru'), errors=[];h.global.console={error:(...args)=>errors.push(args)};
    let later=0;
    h.global.HubI18n.onChange(()=>{throw Error('a detached interface panel');});
    h.global.HubI18n.onChange(()=>later++);
    assert.doesNotThrow(()=>h.global.HubI18n.apply('en'));
    assert.equal(h.global.HubI18n.locale,'en');assert.equal(later,1);
    assert.equal(h.events.length,1);assert.equal(h.events[0].type,'hub-language-changed');
    assert.equal(errors.length,1,'subscriber failure was not reported');
  }
};
Promise.resolve().then(()=>scenarios[scenario]()).catch(error=>{console.error(error);process.exitCode=1;});
'''


class I18nUiTest(unittest.TestCase):
    def run_scenario(self, scenario):
        result = subprocess.run(
            ['node', '-e', HARNESS, str(WEB), scenario],
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_catalog_english_and_parameter_contracts(self):
        self.run_scenario('catalog')

    def test_system_event_titles_and_footer_preserve_user_content(self):
        self.run_scenario('systemEventTitles')

    def test_language_event_refreshes_announcement_without_state_reload(self):
        self.run_scenario('announcementLanguageSwitch')

    def test_backend_capability_reasons_translate_without_changing_chat_content(self):
        self.run_scenario('backendCapabilityReasons')

    def test_parameter_user_data_and_markup_are_preserved(self):
        self.run_scenario('interpolation')

    def test_language_switch_changes_only_known_interface_nodes(self):
        self.run_scenario('interfaceSwitch')

    def test_saved_english_boot_and_real_app_constants_refresh(self):
        self.run_scenario('appBootAndRefresh')

    def test_real_projects_named_key_fallback_and_refresh(self):
        self.run_scenario('projectsFallback')

    def test_failed_or_malformed_preferences_do_not_switch_language(self):
        self.run_scenario('preferenceFailures')

    def test_wrong_language_acknowledgement_is_not_a_success(self):
        self.run_scenario('wrongLanguageAcknowledgement')

    def test_bound_real_viewer_template_preserves_user_content_and_dom_state(self):
        self.run_scenario('templatePreservesViewerState')

    def test_subscriber_failure_does_not_abort_later_updates_or_event(self):
        self.run_scenario('subscriberFailureIsIsolated')


if __name__ == '__main__':
    unittest.main()
