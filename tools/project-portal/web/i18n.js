"use strict";
(function(global) {
  const catalog = global.HubLocaleCatalog || {};
  let locale = global.document?.documentElement?.dataset?.hubLocale === 'en' ? 'en' : 'ru';
  let preference = null;
  const handlers = new Set();
  function format(value, params) {
    return String(value).replace(/\{(\w+)\}/g, (all,key) => Object.hasOwn(params,key) ? String(params[key] ?? '') : all);
  }
  function t(key, params = {}) {
    const item = catalog[key];
    if (!item) return typeof params==='string' ? params : key;
    return format(item[locale] ?? item.en, typeof params==='object' && params ? params : {});
  }
  function error(value) {
    const message = String(value?.message || value?.error || value || '');
    const known = Object.values(catalog).find(item => item.ru === message || item.en === message);
    if (known) return known[locale];
    if (/^(Failed to fetch|NetworkError|Load failed)/.test(message)) return t('i18n.networkError');
    if (locale==='en' && /[А-Яа-яЁё]/.test(message)) return t('i18n.unknownError');
    if (locale==='ru' && /^[A-Za-z].*\s[A-Za-z]/.test(message)) return t('i18n.unknownError');
    return message;
  }
  function apiOutcome(row) {
    if (row?.proposalState==='applied') return t('provider.proposalApplied');
    if (row?.proposalState==='invalid') return t('provider.proposalInvalid');
    if (row?.proposalState==='conflict') return t('provider.proposalConflict');
    return '';
  }
  function shell() {
    const doc=global.document;
    if (!doc) return;
    doc.documentElement.lang=locale;
    doc.querySelectorAll('[data-i18n]').forEach(n=>{n.textContent=t(n.dataset.i18n);});
    doc.querySelectorAll('[data-i18n-label]').forEach(n=>{n.setAttribute('aria-label',t(n.dataset.i18nLabel));});
  }
  function validPreference(body) {
    return body && ['ru','en'].includes(body.language) && typeof body.revision==='string' && /^[a-f0-9]{64}$/.test(body.revision);
  }
  async function load() {
    const response = await fetch('/api/preferences',{cache:'no-store'});
    const body = await response.json();
    if (!response.ok || !validPreference(body)) throw Error(t('i18n.loadError'));
    preference=body;
    apply(body.language);
    return body;
  }
  function apply(language) {
    if (!['ru','en'].includes(language)) throw Error('Unsupported interface language');
    const changed=language!==locale;
    locale=language;shell();
    if (changed) {
      handlers.forEach(handler=>{ try { handler(); } catch (error) { global.console?.error?.('Interface language update failed', error); } });
      global.dispatchEvent?.(new CustomEvent('hub-language-changed'));
    }
  }
  function bindTemplate(root, markup) {
    // Only nodes present in the original interface skeleton are bound. Empty
    // document/content slots and values added later are never translated.
    const template=global.document.createElement('template');
    template.innerHTML=markup();
    const bindings=[];
    function visit(node,path=[]) {
      if (node.nodeType===3 && node.nodeValue.trim()) bindings.push({path,text:true});
      if (node.nodeType===1) for (const attr of ['aria-label','title','placeholder'])
        if (node.hasAttribute(attr)) bindings.push({path,attr});
      [...(node.childNodes||[])].forEach((child,index)=>visit(child,[...path,index]));
    }
    visit(template.content);
    const at=(node,path)=>path.reduce((value,index)=>value?.childNodes?.[index],node);
    const targets=bindings.map(binding=>({...binding,target:at(root,binding.path)}));
    handlers.add(()=>{
      const saved=global.HubLiveUI?.capture?.(root);
      template.innerHTML=markup();
      for (const binding of targets) {
        const value=at(template.content,binding.path), target=binding.target;
        if (!value || !target || target.isConnected===false) continue;
        if (binding.text) target.nodeValue=value.nodeValue;
        else target.setAttribute(binding.attr,value.getAttribute(binding.attr));
      }
      if (saved) global.HubLiveUI.restore(root,saved);
    });
  }
  async function save(language) {
    if (!preference) await load();
    const response = await fetch('/api/v1/preferences',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({language,expected:preference.revision})});
    const body = await response.json();
    if (!response.ok || !validPreference(body) || body.language!==language) {
      const conflict=body?.code==='preferences_conflict'||body?.error==='preferences_conflict';
      if (conflict) preference=null;
      throw Error(t(conflict?'i18n.conflict':'i18n.saveError'));
    }
    preference=body;apply(body.language);
    return body;
  }
  global.HubI18n={t,error,apiOutcome,bindTemplate,load,save,apply,onChange:handler=>handlers.add(handler),get locale(){return locale;},
    date(value,options){return new Intl.DateTimeFormat(locale==='en'?'en-GB':'ru-RU',options).format(new Date(value));}};
  shell();
  global.document?.querySelectorAll('[data-i18n-initial]').forEach(n=>{n.textContent=t(n.dataset.i18nInitial);});
})(typeof window==='undefined'?globalThis:window);
