/* Documentation spaces and folder navigation; knowledge editing/history stay shared. */
(() => {
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const roles={user:[(globalThis.HubI18n?.t?.("documentation.06655b56cf0b") ?? 'Руководство пользователя'),(globalThis.HubI18n?.t?.("documentation.034b492e4ba1") ?? 'Работа с приложением, интерфейсом и основными возможностями.')],developer:[(globalThis.HubI18n?.t?.("documentation.ea439cac732e") ?? 'Разработка приложения'),(globalThis.HubI18n?.t?.("documentation.a9fc98b0ca15") ?? 'Устройство проекта, сборка, архитектурные решения и сопровождение.')],'template-author':[(globalThis.HubI18n?.t?.("documentation.a9d2a180afe2") ?? 'Создание шаблонов'),(globalThis.HubI18n?.t?.("documentation.7f4c1e45323c") ?? 'Форматы, приёмы и примеры для авторов шаблонов.')],'extension-developer':[(globalThis.HubI18n?.t?.("documentation.a2441abc4213") ?? 'Расширения и API'),(globalThis.HubI18n?.t?.("documentation.cb392104b887") ?? 'Интеграции, собственные компоненты и публичные контракты.')]};
  const roleIcons={user:'BookOpen',developer:'Code2','template-author':'Blocks','extension-developer':'Puzzle'};
  const staticIcons={BookOpen:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M2 4.5A2.5 2.5 0 0 1 4.5 2H20v18H4.5A2.5 2.5 0 0 0 2 22z"/><path d="M2 4.5v15A2.5 2.5 0 0 1 4.5 17H20M7 6h8M7 10h8"/></svg>',Code2:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"/></svg>',Blocks:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',Puzzle:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20 13v6a2 2 0 0 1-2 2h-6v-3a2 2 0 1 0-4 0v3H6a2 2 0 0 1-2-2v-4h3a2 2 0 1 0 0-4H4V7a2 2 0 0 1 2-2h4v3a2 2 0 1 0 4 0V5h4a2 2 0 0 1 2 2v4h-3a2 2 0 1 0 0 4z"/></svg>',Folder:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',FileText:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/></svg>'};
  function icon(name,className='') { try { if(window.lucide?.createElement&&window.lucide.icons?.[name]&&typeof document!=='undefined'){const node=window.lucide.createElement(window.lucide.icons[name]);node.setAttribute('class',`d-icon ${className}`.trim());node.setAttribute('aria-hidden','true');return node.outerHTML;} } catch (_) {} return (staticIcons[name]||staticIcons.FileText).replace('<svg ','<svg class="d-icon '+esc(className)+'" '); }
  const label=role=>roles[role]?.[0]||String(role||(globalThis.HubI18n?.t?.("documentation.44dfbcf5bf47") ?? 'Общие материалы')).replace(/[_-]/g,' ');
  const docs=v=>v.documentIndex||v.items||[];
  const item=v=>v.drafts?.get(v.selected)?.item||docs(v).find(d=>d.id===v.selected);
  const space=v=>item(v)?.kind==='document'?(item(v).audience||'general'):v.filters.audience||'';
  const folder=d=>String(d.section||(globalThis.HubI18n?.t?.("documentation.44dfbcf5bf47") ?? 'Общие материалы')).split('/').map(x=>x.trim()).filter(Boolean);
  const href=id=>'#docs/'+encodeURIComponent(id);
  const pageCount=count=>`${count} ${count%100>=11&&count%100<=14?(globalThis.HubI18n?.t?.("documentation.e3ed53c75f0a") ?? 'страниц'):count%10===1?(globalThis.HubI18n?.t?.("documentation.2db15581e092") ?? 'страница'):count%10>=2&&count%10<=4?(globalThis.HubI18n?.t?.("documentation.91fc35f12d86") ?? 'страницы'):(globalThis.HubI18n?.t?.("documentation.e3ed53c75f0a") ?? 'страниц')}`;
  function spaces(v) {return [...new Set([...Object.keys(roles),...(v.context?.policy?.audiences||[]),...docs(v).map(d=>d.audience||'general')])];}
  function heading(v) {
    const markup=(globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.e58aaa8fe15c",{v0:(v.returnArchitecture?.project===v.project?(globalThis.HubI18n?.t?.("documentation.75a3e50649e6") ?? '<button data-k-action="return-architecture">Вернуться к архитектуре</button>'):''),v1:(icon('FilePlus2')),v2:(icon('SlidersHorizontal'))}) : `<header class="k-heading d-heading"><div><small>БАЗА ЗНАНИЙ ПРОЕКТА</small><h1>Документация</h1><p>Материалы проекта, собранные по разделам и папкам.</p></div><div class="k-actions">${v.returnArchitecture?.project===v.project?(globalThis.HubI18n?.t?.("documentation.75a3e50649e6") ?? '<button data-k-action="return-architecture">Вернуться к архитектуре</button>'):''}<button class="d-primary-action" data-k-action="new-doc">${icon('FilePlus2')}<span>Создать страницу</span></button><button class="d-tool-trigger" data-k-action="tools">${icon('SlidersHorizontal')}<span>Инструменты</span></button></div></header>`);
    const caption=globalThis.HubI18n?.t?.('research.documentationTitle')??'Исследование документации';
    return markup.replace('</div></header>',`<button data-d-research>${icon('Search')}<span>${esc(caption)}</span></button></div></header>`);
  }
  async function ensureIndex(v,request) {
    if(v.documentIndexRevision===v.context?.revision)return;
    const revision=v.context?.revision,items=[];let offset=0;
    do {
      const page=await request('search',{kind:'document',offset,limit:200});
      if(page.revision!==revision)throw Error((globalThis.HubI18n?.t?.("documentation.25fc2dbdfc0e") ?? 'Документация обновилась во время загрузки дерева. Обновите раздел.'));
      items.push(...page.items);
      if(!page.more)break;
      if(!Number.isInteger(page.next)||page.next<=offset)throw Error((globalThis.HubI18n?.t?.("documentation.1fcb33f2ea02") ?? 'Сервер не подтвердил следующую страницу документации.'));
      offset=page.next;
    }while(true);
    v.documentIndex=items;v.documentIndexRevision=revision;
  }
  function toolbar(v) {
    const current=space(v);
    const collapsed=Boolean(v.filters.docsTreeCollapsed);
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.820010d672b1",{v0:(icon('Library')),v1:(current?`<span aria-hidden="true">/</span><strong>${esc(label(current))}</strong>`:''),v2:(icon('Search')),v3:(esc(v.filters.query)),v4:(current?`<button class="d-tree-toggle" type="button" data-d-tree-collapse aria-expanded="${collapsed?'false':'true'}">${collapsed?(globalThis.HubI18n?.t?.("documentation.c4251841204f") ?? 'Показать содержание'):(globalThis.HubI18n?.t?.("documentation.9c260c534671") ?? 'Скрыть содержание')}</button>`:'')}) : `<div class="d-toolbar"><nav class="d-breadcrumb" aria-label="Навигация документации"><button data-d-home>${icon('Library')}<span>Документация</span></button>${current?`<span aria-hidden="true">/</span><strong>${esc(label(current))}</strong>`:''}</nav><label class="d-search">${icon('Search')}<span class="k-sr-only">Поиск страниц</span><input type="search" data-k-filter="query" value="${esc(v.filters.query)}" placeholder="Найти страницу"></label>${current?`<button class="d-tree-toggle" type="button" data-d-tree-collapse aria-expanded="${collapsed?'false':'true'}">${collapsed?(globalThis.HubI18n?.t?.("documentation.c4251841204f") ?? 'Показать содержание'):(globalThis.HubI18n?.t?.("documentation.9c260c534671") ?? 'Скрыть содержание')}</button>`:''}</div>`);
  }
  function catalog(v) {
    const current=space(v),query=String(v.filters.query||'').toLocaleLowerCase(),matches=new Set((v.items||[]).map(d=>d.id));
    const pages=docs(v).filter(d=>(d.audience||'general')===current&&(!query||matches.has(d.id)));
    const tree={folders:new Map(),pages:[]};
    for(const page of pages){let branch=tree;for(const part of folder(page)){if(!branch.folders.has(part))branch.folders.set(part,{folders:new Map(),pages:[]});branch=branch.folders.get(part);}branch.pages.push(page);}
    const activeFolder=folder(item(v)||{}).join('/');
    const countPages=branch=>branch.pages.length+[...branch.folders.values()].reduce((sum,child)=>sum+countPages(child),0);
    const formatLabel=page=>page.format==='html'||page.htmlBundle?'HTML':'Markdown';
    const formatMeta=page=>[page.documentDate,page.versionLabel].filter(Boolean);
    const pageSort=(a,b)=>{
      const ad=a.documentDate||'',bd=b.documentDate||'';
      if(ad!==bd&&(ad||bd))return bd.localeCompare(ad);
      return String(a.title||'').localeCompare(String(b.title||''),'ru');
    };
    function render(branch,path='') {
      return [...branch.folders].sort(([a],[b])=>a.localeCompare(b,'ru')).map(([name,child])=>{
        const full=path?path+'/'+name:name;
        const hasFolderState=Array.isArray(v.filters.docsOpenFolders),opened=hasFolderState?v.filters.docsOpenFolders.includes(full):activeFolder===full||activeFolder.startsWith(full+'/');
        return `<details data-d-folder="${esc(full)}"${opened?' open':''}><summary data-d-folder-toggle="${esc(full)}">${icon('Folder')}<span>${esc(name)}</span><small>${countPages(child)}</small></summary><div>${render(child,full)}</div></details>`;
      }).join('')+branch.pages.sort(pageSort).map(page=>`<a class="d-page${page.id===v.selected?' selected':''}" href="${href(page.id)}" data-k-select="${esc(page.id)}"${page.id===v.selected?' aria-current="page"':''}><span class="d-page-title">${esc(page.title)}</span><small class="d-page-meta"><span class="d-format-indicator">${formatLabel(page)}</span>${formatMeta(page).map(value=>`<span>${esc(value)}</span>`).join('')}${['historical','archived','draft'].includes(page.status)?`<span>${esc({historical:(globalThis.HubI18n?.t?.("documentation.947a1802ee02") ?? 'Исторический материал'),archived:(globalThis.HubI18n?.t?.("documentation.3c54b5e783ef") ?? 'Архив'),draft:(globalThis.HubI18n?.t?.("documentation.65fd24f1cb37") ?? 'Черновик')}[page.status])}</span>`:''}</small></a>`).join('');
    }
    const collapsed=Boolean(v.filters.docsTreeCollapsed);
    if(collapsed)return '';
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.cae672528b90",{v0:(pages.length),v1:(render(tree)||'<div class="d-tree-empty">'+icon('FileText')+(globalThis.HubI18n?.t?.("documentation.9f6ceee42652") ?? '<p>В этом разделе пока нет страниц.</p></div>')),v2:(v.more&&query?(globalThis.HubI18n?.t?.("documentation.084be15d17d3") ?? '<button data-k-action="more">Показать ещё результаты поиска</button>'):''),v3:(icon('Plus'))}) : `<aside class="d-tree" aria-label="Дерево документации"><div class="d-tree-heading"><span>Содержание</span><span>${pages.length}</span></div>${render(tree)||'<div class="d-tree-empty">'+icon('FileText')+(globalThis.HubI18n?.t?.("documentation.9f6ceee42652") ?? '<p>В этом разделе пока нет страниц.</p></div>')}${v.more&&query?(globalThis.HubI18n?.t?.("documentation.084be15d17d3") ?? '<button data-k-action="more">Показать ещё результаты поиска</button>'):''}<button class="d-tree-add" data-k-action="new-doc">${icon('Plus')}<span>Создать страницу</span></button></aside>`);
  }
  function cards(v) {
    return `<div class="d-spaces">${spaces(v).map(role=>{
      const count=docs(v).filter(d=>(d.audience||'general')===role).length;
      return `<button class="d-space-card d-space-${esc(role)}" data-d-space="${esc(role)}"><span class="d-space-icon" aria-hidden="true">${icon(roleIcons[role]||'BookOpen')}</span><span class="d-space-copy"><strong>${esc(label(role))}</strong><span>${esc(roles[role]?.[1]||(globalThis.HubI18n?.t?.("documentation.14f5c2357859") ?? 'Статьи и справочные материалы этого раздела.'))}</span></span><small>${count?pageCount(count):(globalThis.HubI18n?.t?.("documentation.71a2340f1e8a") ?? 'Пока пусто')}</small><span class="d-card-arrow" aria-hidden="true">${icon('ArrowUpRight')}</span></button>`;
    }).join('')}</div>`;
  }
  function layout(v,panel) {
    const current=space(v);
    if(!current&&!v.selected&&!v.filters.query)return toolbar(v)+cards(v);
    if(!current&&v.filters.query)return toolbar(v)+(globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.0724bc2b537a",{v0:((v.items||[]).map(d=>`<a href="${href(d.id)}" data-k-select="${esc(d.id)}"><strong>${esc(d.title)}</strong><small>${esc(label(d.audience))} / ${esc(d.section||(globalThis.HubI18n?.t?.("documentation.44dfbcf5bf47") ?? 'Общие материалы'))}</small><p>${esc(d.excerpt||'')}</p></a>`).join('')||(globalThis.HubI18n?.t?.("documentation.1d08f51a14cd") ?? '<p>Ничего не найдено.</p>')),v1:(v.more?(globalThis.HubI18n?.t?.("documentation.5c068ebab74e") ?? '<button data-k-action="more">Показать ещё</button>'):'')}) : `<section class="d-search-results" aria-label="Результаты поиска">${(v.items||[]).map(d=>`<a href="${href(d.id)}" data-k-select="${esc(d.id)}"><strong>${esc(d.title)}</strong><small>${esc(label(d.audience))} / ${esc(d.section||(globalThis.HubI18n?.t?.("documentation.44dfbcf5bf47") ?? 'Общие материалы'))}</small><p>${esc(d.excerpt||'')}</p></a>`).join('')||(globalThis.HubI18n?.t?.("documentation.1d08f51a14cd") ?? '<p>Ничего не найдено.</p>')}${v.more?(globalThis.HubI18n?.t?.("documentation.5c068ebab74e") ?? '<button data-k-action="more">Показать ещё</button>'):''}</section>`);
    const selected=item(v),content=v.selected?withoutDuplicateTitle(panel,selected):(globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.10abcc119778",{v0:(esc(label(current))),v1:(esc(roles[current]?.[1]||(globalThis.HubI18n?.t?.("documentation.0bdd6f589e66") ?? 'Выберите страницу в дереве слева.'))),v2:(pageCount(docs(v).filter(d=>(d.audience||'general')===current).length))}) : `<article class="k-inspector d-space-overview"><h2>${esc(label(current))}</h2><p>${esc(roles[current]?.[1]||(globalThis.HubI18n?.t?.("documentation.0bdd6f589e66") ?? 'Выберите страницу в дереве слева.'))}</p><p>${pageCount(docs(v).filter(d=>(d.audience||'general')===current).length)}</p><button data-k-action="new-doc">Создать страницу</button></article>`);
    const htmlPage=selected?.format==='html'||selected?.htmlBundle,collapsed=Boolean(v.filters.docsTreeCollapsed),width=Math.max(180,Math.min(720,Number(v.filters.docsTreeWidth)||310));
    return toolbar(v)+(globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.728fb7f05b1f",{v0:(collapsed?' d-space-layout-tree-collapsed':''),v1:(width),v2:(catalog(v)),v3:(collapsed?'':(globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.d344c2fa72de",{v0:(width)}) : `<div class="d-tree-splitter" role="separator" tabindex="0" aria-orientation="vertical" aria-label="Ширина содержания" aria-valuemin="180" aria-valuemax="720" aria-valuenow="${width}"></div>`)),v4:(htmlPage?' d-html-page':''),v5:(icon('FolderOpen')),v6:(esc(label(current))),v7:(selected?' / '+folder(selected).map(esc).join(' / '):''),v8:(content)}) : `<div class="d-space-layout${collapsed?' d-space-layout-tree-collapsed':''}" style="--d-tree-width:${width}px">${catalog(v)}${collapsed?'':(globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.d344c2fa72de",{v0:(width)}) : `<div class="d-tree-splitter" role="separator" tabindex="0" aria-orientation="vertical" aria-label="Ширина содержания" aria-valuemin="180" aria-valuemax="720" aria-valuenow="${width}"></div>`)}<main class="d-document${htmlPage?' d-html-page':''}"><nav class="d-page-breadcrumb" aria-label="Расположение страницы">${icon('FolderOpen')}<span>${esc(label(current))}${selected?' / '+folder(selected).map(esc).join(' / '):''}</span></nav>${content}</main></div>`);
  }
  function handleClick(v,event,api) {
    if(v.mode!=='docs')return false;
    if(event.target.closest('[data-d-research]')){
      event.preventDefault();
      const document=item(v);
      void window.HubResearchRequests?.openDocumentation({project:v.project,objectId:document?.kind==='document'?document.id:'project:'+v.project,revision:v.context.revision,title:document?.title||(globalThis.HubI18n?.t?.('research.projectDocuments')??'Документация проекта')});
      return true;
    }
    const folderToggle=event.target.closest('[data-d-folder-toggle]');
    if(folderToggle){const details=folderToggle.parentElement,folderId=folderToggle.dataset.dFolderToggle;v.filters.docsOpenFolders=Array.isArray(v.filters.docsOpenFolders)?v.filters.docsOpenFolders.slice():[];const index=v.filters.docsOpenFolders.indexOf(folderId),nextOpen=!details.open;if(nextOpen&&index<0)v.filters.docsOpenFolders.push(folderId);else if(!nextOpen&&index>=0)v.filters.docsOpenFolders.splice(index,1);api.persist();return true;}
    const collapse=event.target.closest('[data-d-tree-collapse]');
    if(collapse){v.filters.docsTreeCollapsed=!v.filters.docsTreeCollapsed;api.persist();api.draw();return true;}
    const home=event.target.closest('[data-d-home]'),target=event.target.closest('[data-d-space]');
    if(!home&&!target)return false;
    event.preventDefault();api.select('');v.filters.audience=target?.dataset.dSpace||'';v.filters.section='';v.filters.type='';v.filters.query='';v.editing=false;
    history.replaceState(null,'','#docs');api.persist();api.draw();api.refresh();return true;
  }
  function bindResize(v,root,api) {
    const clamp=(value,container)=>Math.max(180,Math.min(Math.min(720,Math.max(180,container-368)),value));
    let drag=null;
    const layout=()=>root.querySelector('.d-space-layout:not(.d-space-layout-tree-collapsed)');
    const apply=(value,persist)=>{const pane=layout();if(!pane)return;const container=pane.getBoundingClientRect().width,maxWidth=Math.min(720,Math.max(180,container-368)),width=clamp(value,container);v.filters.docsTreeWidth=width;pane.style.setProperty('--d-tree-width',`${width}px`);const grip=pane.querySelector('.d-tree-splitter');grip?.setAttribute('aria-valuemax',String(maxWidth));grip?.setAttribute('aria-valuenow',String(width));if(persist)api.persist();};
    const move=event=>{if(drag)apply(drag.width+event.clientX-drag.x,false);};
    const stop=()=>{if(!drag)return;document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',stop);document.removeEventListener('pointercancel',stop);document.body.style.userSelect=drag.userSelect;api.persist();drag=null;};
    const down=event=>{const grip=event.target.closest?.('.d-tree-splitter');if(!grip||!root.contains(grip))return;const pane=layout();if(!pane)return;event.preventDefault();drag={x:event.clientX,width:Number(v.filters.docsTreeWidth)||310,userSelect:document.body.style.userSelect};grip.setPointerCapture?.(event.pointerId);document.body.style.userSelect='none';document.addEventListener('pointermove',move);document.addEventListener('pointerup',stop);document.addEventListener('pointercancel',stop);};
    const key=event=>{if(!event.target.closest?.('.d-tree-splitter'))return;const current=Number(v.filters.docsTreeWidth)||310;if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();apply(current+(event.key==='ArrowLeft'?-20:20),true);}else if(event.key==='Home'||event.key==='End'){event.preventDefault();apply(event.key==='Home'?180:720,true);}};
    root.addEventListener('pointerdown',down);root.addEventListener('keydown',key);apply(Number(v.filters.docsTreeWidth)||310,false);
    return ()=>{stop();root.removeEventListener('pointerdown',down);root.removeEventListener('keydown',key);};
  }
  function editorMetadata(v,document) {
    const kinds={tutorial:(globalThis.HubI18n?.t?.("documentation.deefab96a5ba") ?? 'Учебный материал'),'how-to':(globalThis.HubI18n?.t?.("documentation.b6dc320f8c16") ?? 'Инструкция'),reference:(globalThis.HubI18n?.t?.("documentation.0a2f5a04fddd") ?? 'Справочник'),explanation:(globalThis.HubI18n?.t?.("documentation.1cd33df9055d") ?? 'Объяснение')},states={draft:(globalThis.HubI18n?.t?.("documentation.65fd24f1cb37") ?? 'Черновик'),current:(globalThis.HubI18n?.t?.("documentation.a5088f0fe34c") ?? 'Актуальная'),historical:(globalThis.HubI18n?.t?.("documentation.6dcf44c7f692") ?? 'Историческая'),archived:(globalThis.HubI18n?.t?.("documentation.3c54b5e783ef") ?? 'Архив')};
    const options=(values,selected)=>Object.entries(values).map(([id,name])=>`<option value="${esc(id)}"${id===selected?' selected':''}>${esc(name)}</option>`).join('');
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("documentation.bb38f42f08a3",{v0:(spaces(v).map(id=>`<option value="${esc(id)}"${id===document.audience?' selected':''}>${esc(label(id))}</option>`).join('')),v1:(esc(document.section||'')),v2:(options(kinds,document.type)),v3:(options(states,document.status))}) : `<label>Раздел документации<select data-k-field="audience">${spaces(v).map(id=>`<option value="${esc(id)}"${id===document.audience?' selected':''}>${esc(label(id))}</option>`).join('')}</select></label><label>Папка<input data-k-field="section" value="${esc(document.section||'')}" placeholder="Например: Разработка / Сборка"></label><label>Формат<select data-k-field="type">${options(kinds,document.type)}</select></label><label>Состояние<select data-k-field="status">${options(states,document.status)}</select></label>`);
  }
  function plainMarkup(value) { return String(value||'').replace(/<[^>]*>/g,'').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/\s+/g,' ').trim(); }
  function withoutDuplicateTitle(panel,document) {
    const firstLine=String(document?.markdown||'').match(/^\s*#(?!#)\s+(.+?)\s*#?\s*(?:\r?\n|$)/);
    if(!firstLine||plainMarkup(firstLine[1])!==String(document.title||'').trim())return panel;
    return panel.replace(/(<div class="k-markdown">)\s*<h1\b[^>]*>([\s\S]*?)<\/h1>/,(_match,start,heading)=>plainMarkup(heading)===String(document.title||'').trim()?start:start+_match.slice(start.length));
  }
  window.DocumentationUI={heading,ensureIndex,toolbar,catalog,layout,handleClick,bindResize,editorMetadata,label};

globalThis.HubI18n?.onChange?.(()=>{Object.assign(roles,{user:[(globalThis.HubI18n?.t?.("documentation.06655b56cf0b") ?? 'Руководство пользователя'),(globalThis.HubI18n?.t?.("documentation.034b492e4ba1") ?? 'Работа с приложением, интерфейсом и основными возможностями.')],developer:[(globalThis.HubI18n?.t?.("documentation.ea439cac732e") ?? 'Разработка приложения'),(globalThis.HubI18n?.t?.("documentation.a9fc98b0ca15") ?? 'Устройство проекта, сборка, архитектурные решения и сопровождение.')],'template-author':[(globalThis.HubI18n?.t?.("documentation.a9d2a180afe2") ?? 'Создание шаблонов'),(globalThis.HubI18n?.t?.("documentation.7f4c1e45323c") ?? 'Форматы, приёмы и примеры для авторов шаблонов.')],'extension-developer':[(globalThis.HubI18n?.t?.("documentation.a2441abc4213") ?? 'Расширения и API'),(globalThis.HubI18n?.t?.("documentation.cb392104b887") ?? 'Интеграции, собственные компоненты и публичные контракты.')]});});
})();
