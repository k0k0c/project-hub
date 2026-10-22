/* Universal knowledge views. All user content is escaped or sanitized. */
(() => {
  'use strict';
  const views = new Map(), PAGE = 50, MAX_ITEMS = 200, DOC_LINK_PAGE = 20;
  const DOC_TYPES = ['tutorial','how-to','reference','explanation'];
  const CAMERA_ENGINE = 'cytoscape-3.33.1';
  const ROUTING_VERSION = 'automatic-ports-7';
  const COMPOUND_INSET=window.ArchitectureMap?.inset||56;
  let mounted = null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const copy = value => JSON.parse(JSON.stringify(value));
  const key = () => 'ui:' + (window.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2));
  const link = (mode, id) => '#' + mode + '/' + encodeURIComponent(id);
  const taskHref = (task, stage) => '#tasks/' + encodeURIComponent(task) + (stage ? '/' + encodeURIComponent(stage) : '');
  const lines = text => String(text || '').split(/\n|,/).map(x => x.trim()).filter(Boolean);
  const icon = name => window.lucide?.icons?.[name] ? window.lucide.createElement(window.lucide.icons[name],{'aria-hidden':'true',width:16,height:16,'stroke-width':1.6}).outerHTML : '';
  function saved(project, mode) {
    try { return JSON.parse(localStorage.getItem('knowledge:' + project + ':' + mode) || '{}'); }
    catch (_) { return {}; }
  }
  function view(project, mode, options={}) {
    const identifier = JSON.stringify([project, mode]);
    if (!views.has(identifier)) {
      const prior = saved(project, mode);
      if(prior.cameraEngine!==CAMERA_ENGINE)delete prior.viewport;
      if(mode==='architecture'&&prior.filters){if(prior.researchVersion!==1){delete prior.filters.catalogWidth;delete prior.filters.inspectorWidth;}prior.filters.componentContext='subsystems';prior.filters.hiddenTypes=[];prior.filters.groupBy='components';delete prior.filters.edgeStyle;delete prior.filters.type;delete prior.filters.component;delete prior.filters.entry;}
      if(prior.filters?.graphMode==='matrix'){prior.filters.graphMode='components';prior.filters.presentation='matrix';}
      if(prior.filters?.graphMode==='catalog'){prior.filters.graphMode='neighborhood';prior.filters.browser='catalog';}
      if(mode==='architecture'&&prior.routingVersion!==ROUTING_VERSION){delete prior.positions;delete prior.routes;delete prior.cameraKey;if(prior.filters)prior.filters.componentContext='auto';}
      views.set(identifier, {project, mode, selected: prior.selected || '',
        filters: {query:'', audience:'', section:'', type:'', component:'', entry:'', graphMode:'overview', listMode:'graph', browser:'structure', followSelection:true, presentation:'map', componentContext:'auto', codeLimit:PAGE, includeSubsystems:false, ...prior.filters,layout:'elk'},
        viewport: {x:Number.isFinite(prior.viewport?.x)?prior.viewport.x:0,y:Number.isFinite(prior.viewport?.y)?prior.viewport.y:0,
          scale:Number.isFinite(prior.viewport?.scale)?Math.min(4,Math.max(.01,prior.viewport.scale)):1}, items:[], relations:[], scenarios:[], drafts:new Map(),
        context:null, architectureSettings:options.projectSettings||{}, next:null, loading:false, error:'', notice:'', sequence:0, detailSequence:0, linkSequence:0, linkedEntities:new Map(),cameraInitialized:!!prior.viewport,
        cameraKey:typeof prior.cameraKey==='string'?prior.cameraKey:'',positionCache:new Map(Array.isArray(prior.positions)?prior.positions.filter(entry=>Array.isArray(entry)&&entry.length===2&&typeof entry[0]==='string').slice(-8):[]),canvasSelection:[],returnArchitecture:prior.returnArchitecture||null,
        routeCache:new Map(Array.isArray(prior.routes)?prior.routes.slice(-8):[]),navigatorScroll:{},history:null, historical:null, comparison:null, comparing:false, imports:null, policyDraft:null, busy:false, panel:'', initialized:false});
    }
    return views.get(identifier);
  }
  function persist(v) {
    clearTimeout(v.cameraPersistTimer);
    try { localStorage.setItem('knowledge:' + v.project + ':' + v.mode,
      JSON.stringify({researchVersion:1,selected:v.selected,filters:v.filters,viewport:v.viewport,cameraEngine:CAMERA_ENGINE,routingVersion:ROUTING_VERSION,cameraKey:v.cameraKey,positions:[...v.positionCache].slice(-8),routes:[...(v.routeCache||[])].slice(-8),returnArchitecture:v.returnArchitecture})); } catch (_) { /* storage is optional */ }
  }
  function graphState(v) { return copy({selected:v.selected,filters:v.filters,viewport:v.viewport,cameraKey:v.cameraKey,researchCanvas:v.researchCanvas||null,researchOwnership:window.KnowledgeResearch?.snapshot(v)}); }
  function recordGraph(v) {
    if(v.mode!=='architecture'||v.navigating)return;
    v.navigation ||= []; v.navigationIndex ??= -1;
    const state=graphState(v);
    if(JSON.stringify(v.navigation[v.navigationIndex])===JSON.stringify(state))return;
    v.navigation=v.navigation.slice(0,v.navigationIndex+1);v.navigation.push(state);
    if(v.navigation.length>40)v.navigation.shift();
    v.navigationIndex=v.navigation.length-1;
  }
  function updateGraphViewport(v) {
    if(v.mode==='architecture'&&v.navigation?.[v.navigationIndex]){v.navigation[v.navigationIndex].viewport=copy(v.viewport);v.navigation[v.navigationIndex].cameraKey=v.cameraKey;v.navigation[v.navigationIndex].filters=copy(v.filters);}
  }
  async function navigateGraph(v, delta) {
    const index=(v.navigationIndex??-1)+delta;
    if(!v.navigation||index<0||index>=v.navigation.length)return;
    clearTimeout(mounted.debounce);mounted.queryEditing=false;
    destroyGraph();
    const state=copy(v.navigation[index]);v.navigating=true;
    selectItem(v,state.selected);v.researchCanvas=state.researchCanvas;window.KnowledgeResearch?.restore(v,state.researchOwnership);v.filters=state.filters;v.viewport=state.viewport;v.cameraKey=state.cameraKey||'';v.scopeRevealRequested=true;
    v.navigationIndex=index;v.navigating=false;mounted.selection=v.selected;
    persist(v);history.replaceState(null,'',link(v.mode,v.selected));await refresh(v);
  }
  function routeId(mode, options) {
    const route = typeof options.route === 'function' ? options.route() : options.route;
    const parts = Array.isArray(route) ? route : String(route || location.hash).replace(/^#/, '').split('/');
    if (parts[0] !== mode || !parts[1]) return null;
    try { return decodeURIComponent(parts.slice(1).join('/')); } catch (_) { return null; }
  }
  function selectItem(v, identifier) {
    if(v.selected===identifier)return;
    if(v.mode==='architecture'){
      v.researchCanvas=null;v.researchLoading=false;
      if(v.research)window.KnowledgeResearch?.restore(v,null);
    }
    v.selected=identifier;v.detailSequence++;v.historical=null;v.history=null;v.restoreRequest=null;
    v.canvasSelection=[];v.canvasItem='';v.canvasInspect=null;v.canvasStats=null;v.canvasGroupStats=null;v.canvasCapabilities=null;
    v.comparison=null;v.comparing=false;
    v.linkSequence++;v.linkedEntities=new Map();v.docLinks=null;
    v.linkedDocs=[];v.linkedDocsMore=false;v.neighbors=[];v.relations=[];v.relationsMore=false;
  }
  function page(mode, options = {}) {
    mode = mode === 'architecture' ? 'architecture' : 'docs';
    const v = view(options.project || '', mode, options), selected = routeId(mode, options);
    recordGraph(v);
    if (selected !== null) {selectItem(v,selected);recordGraph(v);}
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.af449a23b672",{v0:(esc(v.project)),v1:(mode),v2:(mode==='architecture'?' data-k-workspace="true"':''),v3:(mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.0d9ff4991685") ?? '<h1 class="k-sr-only">Архитектура</h1>'):mode==='docs'&&window.DocumentationUI?.heading?window.DocumentationUI.heading(v):(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.45304fd2fb18",{v0:(mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.0d9ff4991685") ?? '<h1 class="k-sr-only">Архитектура</h1>'):(globalThis.HubI18n?.t?.("knowledge.167db73910d5") ?? '<small>БАЗА ЗНАНИЙ ПРОЕКТА</small><h1>Документация</h1><p>Статьи для пользователей и разработчиков, связанные с моделью проекта.</p>')),v1:(mode==='docs'&&v.returnArchitecture?.project===v.project?(globalThis.HubI18n?.t?.("knowledge.75a3e50649e6") ?? '<button data-k-action="return-architecture">Вернуться к архитектуре</button>'):''),v2:(mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.d2e91eaa411a") ?? '<details class="k-tools"><summary>Инструменты</summary><div class="k-actions">'):''),v3:(mode === 'docs' ? (globalThis.HubI18n?.t?.("knowledge.64d06d2da38b") ?? '<button data-k-action="new-doc">Новая статья</button><button data-k-action="import">Импорт</button>') : (globalThis.HubI18n?.t?.("knowledge.743dbd652f40") ?? '<button data-k-action="scan">Сканировать</button><button data-k-action="new-view">Новый сценарий</button>')),v4:(mode==='architecture'?'</div></details>':'')}) : `<header class="k-heading"><div>${mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.0d9ff4991685") ?? '<h1 class="k-sr-only">Архитектура</h1>'):(globalThis.HubI18n?.t?.("knowledge.167db73910d5") ?? '<small>БАЗА ЗНАНИЙ ПРОЕКТА</small><h1>Документация</h1><p>Статьи для пользователей и разработчиков, связанные с моделью проекта.</p>')}</div>
      <div class="k-actions">${mode==='docs'&&v.returnArchitecture?.project===v.project?(globalThis.HubI18n?.t?.("knowledge.75a3e50649e6") ?? '<button data-k-action="return-architecture">Вернуться к архитектуре</button>'):''}<button data-k-action="refresh">Обновить</button>${mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.d2e91eaa411a") ?? '<details class="k-tools"><summary>Инструменты</summary><div class="k-actions">'):''}<button data-k-action="policy">Настройки</button>
      ${mode === 'docs' ? (globalThis.HubI18n?.t?.("knowledge.64d06d2da38b") ?? '<button data-k-action="new-doc">Новая статья</button><button data-k-action="import">Импорт</button>') : (globalThis.HubI18n?.t?.("knowledge.743dbd652f40") ?? '<button data-k-action="scan">Сканировать</button><button data-k-action="new-view">Новый сценарий</button>')}
      <button data-k-action="export">Экспорт ZIP</button><button data-k-action="export-public" title="Только ранее согласованные публичные, самостоятельные статьи">Публичный ZIP</button><button data-k-action="backup">Резервная копия</button>${mode==='architecture'?'</div></details>':''}</div></header>`))}) : `<section class="knowledge-root" data-k-project="${esc(v.project)}" data-k-mode="${mode}"${mode==='architecture'?' data-k-workspace="true"':''}>
      ${mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.0d9ff4991685") ?? '<h1 class="k-sr-only">Архитектура</h1>'):mode==='docs'&&window.DocumentationUI?.heading?window.DocumentationUI.heading(v):(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.45304fd2fb18",{v0:(mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.0d9ff4991685") ?? '<h1 class="k-sr-only">Архитектура</h1>'):(globalThis.HubI18n?.t?.("knowledge.167db73910d5") ?? '<small>БАЗА ЗНАНИЙ ПРОЕКТА</small><h1>Документация</h1><p>Статьи для пользователей и разработчиков, связанные с моделью проекта.</p>')),v1:(mode==='docs'&&v.returnArchitecture?.project===v.project?(globalThis.HubI18n?.t?.("knowledge.75a3e50649e6") ?? '<button data-k-action="return-architecture">Вернуться к архитектуре</button>'):''),v2:(mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.d2e91eaa411a") ?? '<details class="k-tools"><summary>Инструменты</summary><div class="k-actions">'):''),v3:(mode === 'docs' ? (globalThis.HubI18n?.t?.("knowledge.64d06d2da38b") ?? '<button data-k-action="new-doc">Новая статья</button><button data-k-action="import">Импорт</button>') : (globalThis.HubI18n?.t?.("knowledge.743dbd652f40") ?? '<button data-k-action="scan">Сканировать</button><button data-k-action="new-view">Новый сценарий</button>')),v4:(mode==='architecture'?'</div></details>':'')}) : `<header class="k-heading"><div>${mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.0d9ff4991685") ?? '<h1 class="k-sr-only">Архитектура</h1>'):(globalThis.HubI18n?.t?.("knowledge.167db73910d5") ?? '<small>БАЗА ЗНАНИЙ ПРОЕКТА</small><h1>Документация</h1><p>Статьи для пользователей и разработчиков, связанные с моделью проекта.</p>')}</div>
      <div class="k-actions">${mode==='docs'&&v.returnArchitecture?.project===v.project?(globalThis.HubI18n?.t?.("knowledge.75a3e50649e6") ?? '<button data-k-action="return-architecture">Вернуться к архитектуре</button>'):''}<button data-k-action="refresh">Обновить</button>${mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.d2e91eaa411a") ?? '<details class="k-tools"><summary>Инструменты</summary><div class="k-actions">'):''}<button data-k-action="policy">Настройки</button>
      ${mode === 'docs' ? (globalThis.HubI18n?.t?.("knowledge.64d06d2da38b") ?? '<button data-k-action="new-doc">Новая статья</button><button data-k-action="import">Импорт</button>') : (globalThis.HubI18n?.t?.("knowledge.743dbd652f40") ?? '<button data-k-action="scan">Сканировать</button><button data-k-action="new-view">Новый сценарий</button>')}
      <button data-k-action="export">Экспорт ZIP</button><button data-k-action="export-public" title="Только ранее согласованные публичные, самостоятельные статьи">Публичный ZIP</button><button data-k-action="backup">Резервная копия</button>${mode==='architecture'?'</div></details>':''}</div></header>`)}
      <div data-k-body><p role="status">Загрузка знаний…</p></div></section>`);
  }
  function active(v) { return mounted?.view === (v.snapshotOwner||v) && mounted.root.isConnected; }
  async function request(v, action, args = {}, write = false) {
    if (!active(v)) throw Error((globalThis.HubI18n?.t?.("knowledge.4cf0a635e9c1") ?? 'Представление проекта изменилось'));
    // Pin the requested project even if the parent's projectApi closes over a
    // newer active project while an earlier async operation is completing.
    const path = '/api/v1/knowledge' + (write ? '' : '?' + new URLSearchParams({action,...args}));
    const url = new URL(mounted.options.projectApi ? mounted.options.projectApi(path) : path, location.origin);
    url.searchParams.set('project', v.project);
    const response = await fetch(url.pathname + url.search, write ? {
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,args}),signal:mounted.controller.signal
    } : {signal:mounted.controller.signal});
    const result = await response.json();
    if (!response.ok) { const error = Error(result.message || result.error || (globalThis.HubI18n?.t?.("knowledge.fce0fa9e02e8") ?? 'Ошибка загрузки знаний')); error.code=result.error; error.status=response.status; throw error; }
    return result;
  }
  function fail(v, error) {
    if (!active(v) || error.name === 'AbortError') return;
    v.error = (globalThis.HubI18n?.error?.(error) ?? error.message);
    if(v.snapshotOwner)return;
    if (error.code === 'revision_conflict') v.error += (globalThis.HubI18n?.t?.("knowledge.5b80bfbe7398") ?? '. Черновик сохранён. Сверьте историю и текущую версию перед повторным сохранением.');
    mounted.options.showError?.(v.error); draw(v);
  }
  async function fetchRelations(v, endpoint = '', overview = false) {
    const base={kind:'relation',limit:100,...(endpoint?{endpoint}:{})};
    const search=args=>endpoint?searchGraphPages(v,args):request(v,'search',args);
    if(endpoint&&v.filters.graphMode==='neighborhood'&&v.drafts.get(endpoint)?.item.type==='component')
      return search({...base,type:'depends-on'});
    if(v.filters.graphMode==='inheritance') {
      // Uses/contains edges cannot consume inheritance's first-page budget.
      const pages=await Promise.all(['extends','implements'].map(type=>search({...base,type})));
      return {items:[...new Map(pages.flatMap(page=>page.items).map(item=>[item.id,item])).values()],
        more:pages.some(page=>page.more)};
    }
    if(overview&&v.filters.graphMode==='overview')return request(v,'search',{...base,type:'depends-on',query:''});
    return search({...base,...(endpoint?{}:{query:''})});
  }
  async function navigationPages(v,revision){
    const owner=v.snapshotOwner||v;
    owner.navigationRequests||=new Map();
    if(owner.navigationCatalog?.revision===revision)return owner.navigationCatalog;
    if(owner.navigationRequests.has(revision))return owner.navigationRequests.get(revision);
    const loading=(async()=>{let page,offset=0;const items=[];
      do{page=await request(v,'source-tree',{mode:'navigation',limit:5000,offset});
        if(page.revision!==revision)throw Error((globalThis.HubI18n?.t?.("knowledge.704d20d7e887") ?? 'Каталог изменился во время загрузки. Перечитайте данные.'));
        items.push(...page.items);offset=page.next;
      }while(page.more&&offset!=null);
      const index={revision,components:items.filter(n=>n.type==='component'),entries:items.filter(n=>n.entrypoint),scenarios:items.filter(n=>n.kind==='view')};
      if(!owner.navigationCatalog||owner.navigationCatalog.revision<=revision)owner.navigationCatalog=index;
      return index;
    })();owner.navigationRequests.set(revision,loading);
    try{return await loading;}finally{owner.navigationRequests.delete(revision);}
  }
  async function searchGraphPages(v,args,maxItems=Infinity) {
    let page=await request(v,'search',{...args,limit:Math.min(args.limit||PAGE,maxItems)});const revision=page.revision,items=[...page.items],seen=new Set();
    while(page.more&&page.next!=null&&!seen.has(page.next)&&items.length<maxItems){
      seen.add(page.next);const next=await request(v,'search',{...args,offset:page.next,limit:Math.min(args.limit||PAGE,maxItems-items.length)});
      if(next.revision!==revision)return {items,revision,more:true};
      items.push(...next.items);page=next;
    }
    return {items:[...new Map(items.map(item=>[item.id,item])).values()],revision,more:page.more};
  }
  async function readGraphItems(v,ids) {
    const items=[];
    for(let offset=0;offset<ids.length;offset+=PAGE){
      if(!active(v))return items;
      items.push(...await Promise.all(ids.slice(offset,offset+PAGE).map(id=>request(v,'read',{id}))));
    }
    return items;
  }
  function componentLevel(v) {
    const parent=v.componentItems?.find(item=>item.id===v.selected)?.id||null;
    const children=(v.componentItems||[]).filter(item=>(item.parent||null)===parent);
    return !children.length&&parent&&v.filters.graphMode==='components'?[v.componentItems.find(item=>item.id===parent)]:children;
  }
  async function loadComponentLevel(v) {
    const nodes=componentLevel(v),cacheKey=JSON.stringify([v.context.revision,nodes.map(node=>node.id)]);
    v.componentCache ||= new Map();
    if(v.componentCache.has(cacheKey))return v.componentCache.get(cacheKey);
    const pages=await Promise.all(nodes.map(node=>searchGraphPages(v,{kind:'relation',type:'depends-on',endpoint:node.id,limit:100})));
    const ids=new Set(nodes.map(node=>node.id)),edges=[...new Map(pages.flatMap(page=>page.items).filter(edge=>ids.has(edge.from)&&ids.has(edge.to)).map(edge=>[edge.id,edge])).values()];
    const result={items:edges,more:pages.some(page=>page.more),
      mixed:pages.some(page=>page.revision!==v.context.revision)};
    if(!result.mixed){v.componentCache.set(cacheKey,result);if(v.componentCache.size>8)v.componentCache.delete(v.componentCache.keys().next().value);}
    return result;
  }
  async function refresh(v, append = false) {
    if(v.mode!=='architecture')return refreshData(v,append);
    const generation=++v.sequence,selection=v.selected,filters=copy(v.filters),previousRevision=v.context?.revision,reveal=v.scopeRevealRequested||v.loadedSelection!==v.selected;
    const state=canvasState(v);
    const keepCanvas=!!mounted.cy&&v.loadedSelection===selection;
    v.loading=true;v.error='';v.analysisNotice=(globalThis.HubI18n?.t?.("knowledge.8335d13aa801") ?? 'Перечитываем данные…');if(!keepCanvas)draw(v);
    // All loaders write into a private snapshot. A superseded request can never
    // publish partial facts, inspector data, caches or camera into the workspace.
    const snapshot={...v,snapshotOwner:v,filters,drafts:new Map(v.drafts),loading:false,sequence:0,
      detailSequence:0,refreshAgain:false,branchMaps:new Map(v.branchMaps||[]),componentCache:new Map(v.componentCache||[])};
    try{
      // The research canvas already has its own indexed composition query.
      // Do not prepare the legacy neighbourhood and then discard it again.
      if(window.KnowledgeResearch&&selection){
        const [context,selected]=await Promise.all([request(v,'context'),request(v,selection.startsWith('research:')?'research-object':'read',{id:selection})]);
        if(!active(v)||v.sequence!==generation||v.selected!==selection)return;
        if(selected.kind!=='view'){
          const reuse=v.initialized&&v.context?.revision===context.revision;
          const index=reuse?null:await navigationPages(v,context.revision);
          // Update the loaded facts by ID so newly authored ownership appears
          // on an explored map too. Language-server-only symbols stay intact.
          const loaded=new Map();
          if(v.researchCanvas&&!reuse){
            const nodes=v.researchCanvas.nodes.filter(n=>!n.id.startsWith('research:')&&n.provenance!=='presentation');
            for(let offset=0;offset<nodes.length;offset+=PAGE){
              const values=await Promise.all(nodes.slice(offset,offset+PAGE).map(async n=>{try{return await request(v,'read',{id:n.id});}catch(error){if(error.code==='item_missing')return n;throw error;}}));
              for(const n of values)loaded.set(n.id,n);
            }
            const finalContext=await request(v,'context');
            if(finalContext.revision!==context.revision)throw Object.assign(Error((globalThis.HubI18n?.t?.("knowledge.3dbb7364509e") ?? 'Знания изменились во время загрузки.')),{code:'knowledge_refresh_race',revision:finalContext.revision});
          }
          if(!active(v)||v.sequence!==generation||v.selected!==selection)return;
          v.context=context;v.listRevision=context.revision;v.initialized=true;v.loadedSelection=selection;v.loading=false;v.analysisNotice=(globalThis.HubI18n?.t?.("knowledge.81b79f68e5ba") ?? 'Данные перечитаны · версия ')+context.revision;
          if(index){v.scenarios=index.scenarios;v.componentItems=index.components;v.entryItems=index.entries;}
          if(!v.drafts.get(selection)?.dirty)v.drafts.set(selection,{item:selected,expected:context.revision,dirty:false});
          if(loaded.size){v.researchCanvas={...v.researchCanvas,nodes:v.researchCanvas.nodes.map(n=>loaded.get(n.id)||n)};window.KnowledgeResearch.rebase?.(v,loaded);if(loaded.has(v.canvasItem))v.canvasInspect=loaded.get(v.canvasItem);}
          v.research.capabilities.clear();
          if(!v.researchCanvas)await window.KnowledgeResearch.open(v,selection,selected);
          else draw(v,state&&state.owner===selection?{...state,relayout:state.identity!==graphKey(v)}:null);
          scheduleJob(v);return;
        }
      }
      if(selection&&!v.drafts.get(selection)?.dirty){
        const selected=await request(v,selection.startsWith('research:')?'research-object':'read',{id:selection});
        if(selected.type==='file'&&filters.graphMode==='inheritance')filters.graphMode='neighborhood';
        if(selected.type==='component'&&filters.graphMode==='overview')filters.graphMode='components';
        else if(selected.type!=='component'&&filters.graphMode==='overview')filters.graphMode='neighborhood';
        snapshot.drafts.set(selection,{item:selected,expected:v.context?.revision,dirty:false});
        if(selected.kind==='view'){filters.graphMode='neighborhood';filters.presentation='map';}
      }
      await refreshData(snapshot,append);
      if(snapshot.error)throw Error(snapshot.error);
      if(!active(v)||v.sequence!==generation||v.selected!==selection)return;
      if(!selection&&snapshot.componentItems?.length){filters.graphMode='components';filters.componentContext='subsystems';const level=await loadComponentLevel(snapshot);snapshot.relations=level.items;snapshot.componentPartial=level.more||level.mixed;}
      if(snapshot.drafts.get(selection)?.item.kind==='view'){filters.graphMode='neighborhood';filters.presentation='map';}
      if(filters.graphMode==='components'&&filters.componentContext==='auto'&&snapshot.componentItems?.some(n=>n.id===selection))filters.componentContext=snapshot.componentItems.some(n=>n.parent===selection)?'subsystems':'code';
      if(filters.graphMode==='components'&&filters.componentContext==='code'&&snapshot.componentItems?.some(n=>n.id===selection)){
        const ids=new Set([selection]);
        if(filters.includeSubsystems){let changed=true;while(changed){changed=false;for(const n of snapshot.componentItems)if(ids.has(n.parent)&&!ids.has(n.id)){ids.add(n.id);changed=true;}}}
        const pages=[];let budget=Math.max(PAGE,Number(filters.codeLimit)||PAGE);
        for(const component of ids){if(budget<=0){pages.push({items:[],more:true,revision:snapshot.context.revision});break;}const page=await searchGraphPages(snapshot,{kind:'entity',component,limit:PAGE},budget);pages.push(page);budget-=page.items.length;}
        const nodes=[...new Map(pages.flatMap(p=>p.items).filter(n=>n.type!=='component').map(n=>[n.id,n])).values()];
        const nodeIds=new Set(nodes.map(n=>n.id));
        const edges=await Promise.all(nodes.map(n=>searchGraphPages(snapshot,{kind:'relation',endpoint:n.id,limit:100})));
        snapshot.scopedCode={nodes,relations:[...new Map(edges.flatMap(p=>p.items).filter(e=>nodeIds.has(e.from)&&nodeIds.has(e.to)).map(e=>[e.id,e])).values()]};
        snapshot.componentPartial=pages.some(p=>p.more)||edges.some(p=>p.more);
        if([...pages,...edges].some(p=>p.revision!==snapshot.context.revision))throw Error((globalThis.HubI18n?.t?.("knowledge.8022d3c480b2") ?? 'Знания изменились во время загрузки кода. Перечитайте данные.'));
      }else snapshot.scopedCode=null;
      if(selection&&(snapshot.drafts.get(selection)?.item.type!=='component'||filters.componentContext==='code'))filters.presentation='map';
      const finalContext=await request(v,'context');
      if(finalContext.revision!==snapshot.context?.revision||snapshot.listRevision!==snapshot.context?.revision)throw Error((globalThis.HubI18n?.t?.("knowledge.55196a79d6de") ?? 'Знания изменились во время загрузки. Перечитайте данные.'));
      if(!active(v)||v.sequence!==generation||v.selected!==selection)return;
      v.research?.capabilities.clear();
      const {snapshotOwner,sequence,detailSequence,navigationCatalog,navigationRequests,filters:loadedFilters,...data}=snapshot;
      Object.assign(v,data);v.sequence=generation;v.detailSequence++;v.loading=false;
      v.filters.graphMode=filters.graphMode;
      v.filters.componentContext=filters.componentContext;
      v.filters.presentation=filters.presentation;
      if(filters.graphMode==='components'&&!v.scopedCode)v.filters.hiddenTypes=[];
      if(reveal)revealScope(v);v.scopeRevealRequested=false;
      v.analysisNotice=previousRevision===v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.2ea741451018") ?? 'Данные перечитаны · без изменений'):(globalThis.HubI18n?.t?.("knowledge.81b79f68e5ba") ?? 'Данные перечитаны · версия ')+v.context.revision;
      if(window.KnowledgeResearch&&selection&&!v.researchCanvas&&v.drafts.get(selection)?.item.kind!=='view'){await window.KnowledgeResearch.open(v,selection);scheduleJob(v);return;}
      draw(v,state&&state.identity===graphKey(v)?state:state&&state.owner===selection?{...state,relayout:true}:null);scheduleJob(v);
    }catch(error){if(active(v)&&v.sequence===generation){v.loading=false;if(keepCanvas&&error.code==='knowledge_refresh_race'){queueKnowledgeRefresh(v,error.revision);return;}v.initialized=false;fail(v,error);}}
  }
  async function refreshData(v, append = false) {
    if (v.loading) { v.refreshAgain = true; return; }
    const generation = ++v.sequence;
    const filterKey = JSON.stringify([v.filters.query,v.filters.type,v.filters.component,v.filters.entry,v.filters.graphMode,v.selected]);
    const searchArgs={kind:v.mode === 'docs' ? 'document' : 'entity',query:v.mode==='architecture'?'':v.filters.query,offset:append ? v.next : 0,limit:PAGE};
    if(v.filters.type)searchArgs.type=v.filters.type;
    if(v.mode==='architecture'&&v.filters.component)searchArgs.component=v.filters.component;
    if(v.mode==='architecture'&&v.filters.entry)searchArgs.entrypoint='true';
    v.loading = true; v.error = ''; draw(v);
    let selectedRelations=null;
    try {
      const [context, result] = await Promise.all([
        request(v, 'context'), request(v, 'search', searchArgs)
      ]);
      if (!active(v) || generation !== v.sequence) return;
      if (filterKey !== JSON.stringify([v.filters.query,v.filters.type,v.filters.component,v.filters.entry,v.filters.graphMode,v.selected])) {v.refreshAgain=true;return;}
      if (append && v.listRevision !== result.revision) throw Error((globalThis.HubI18n?.t?.("knowledge.50159167929f") ?? 'Список изменился между страницами. Обновите его перед продолжением.'));
      v.context=context; v.listRevision=result.revision;
      v.items=(append ? [...v.items,...result.items] : result.items).slice(0,MAX_ITEMS);
      v.next=result.next; v.more=result.more;v.total=result.total;
      if(v.mode==='docs'&&window.DocumentationUI){await window.DocumentationUI.ensureIndex(v,(action,args)=>request(v,action,args));if(!active(v)||generation!==v.sequence)return;}
      if (v.mode === 'architecture') {
        const [relations, scenarios, components, entries] = await Promise.all([
          ['components','matrix'].includes(v.filters.graphMode)?Promise.resolve({items:[],more:false}):fetchRelations(v,v.filters.graphMode==='overview'?'':v.selected,true),
          ...['scenarios','components','entries'].map(key=>navigationPages(v,context.revision).then(index=>({items:index[key],more:false}))) ]);
        if (!active(v) || generation !== v.sequence) return;
        if (filterKey !== JSON.stringify([v.filters.query,v.filters.type,v.filters.component,v.filters.entry,v.filters.graphMode,v.selected])) {v.refreshAgain=true;return;}
        v.relations=relations.items; v.relationsMore=relations.more; v.scenarios=scenarios.items;
        v.componentItems=components.items.filter(n=>n.kind==='entity'&&n.type==='component');v.componentsMore=components.more;
        v.entryItems=entries.items;
        if(v.filters.browser==='catalog')await loadCatalogTree(v);
        if(['components','matrix'].includes(v.filters.graphMode)){
          const level=await loadComponentLevel(v);
          if(!active(v)||generation!==v.sequence||filterKey!==JSON.stringify([v.filters.query,v.filters.type,v.filters.component,v.filters.entry,v.filters.graphMode,v.selected]))return;
          const parent=v.componentItems.find(item=>item.id===v.selected)?.id||null;
          v.relations=level.items;v.relationsMore=level.more||level.mixed;v.componentPartial=level.more||level.mixed||components.more;
          selectedRelations={items:v.relations,more:v.relationsMore};
        }
        else if(v.filters.graphMode!=='overview'&&v.selected)selectedRelations=relations;
      }
      v.initialized=true;
      if (v.selected && !v.drafts.get(v.selected)?.dirty) await loadItem(v,v.selected,false,selectedRelations);
      else if(v.mode==='docs'&&v.drafts.get(v.selected))await resolveDocLinks(v,v.drafts.get(v.selected).item);
      scheduleJob(v);
    } catch (error) { fail(v,error); }
    finally {
      if (active(v) && generation === v.sequence) {
        v.loading=false; draw(v);
        if (v.refreshAgain) { v.refreshAgain=false; refresh(v); }
      }
    }
  }
  async function loadItem(v, identifier, redraw = true, preparedRelations = null) {
    const generation=++v.detailSequence;
    try {
      const item=await request(v,v.mode==='architecture'&&identifier.startsWith('research:')?'research-object':'read',{id:identifier});
      if (!active(v) || generation!==v.detailSequence || identifier!==v.selected) return;
      v.loadedSelection = identifier;
      if (!v.drafts.get(identifier)?.dirty) v.drafts.set(identifier,{item,expected:v.context?.revision,dirty:false});
      v.historical=null; v.history=null;v.comparison=null;v.comparing=false;
      if(v.mode==='docs')await resolveDocLinks(v,v.drafts.get(identifier).item);
      if (v.mode==='architecture') {
        if (item.kind==='view'&&!['components','matrix','inheritance'].includes(v.filters.graphMode)) {
          const nodes=await readGraphItems(v,item.nodeIds||[]);
          const edges=await readGraphItems(v,item.orderedEdges||[]);
          if (!active(v) || generation!==v.detailSequence) return;
          v.neighbors=nodes.filter(x=>x?.kind==='entity');v.relations=edges.filter(x=>x?.kind==='relation');v.relationsMore=false;
          v.linkedDocs=[];await resolveArchitectureLabels(v,item,generation);if(redraw)draw(v);return;
        }
        const [relations, docs]=await Promise.all([preparedRelations?Promise.resolve(preparedRelations):fetchRelations(v,identifier),
          request(v,'search',{kind:'document',query:identifier,limit:PAGE})]);
        if (!active(v) || generation!==v.detailSequence || identifier!==v.selected) return;
        v.relations=relations.items.filter(r=>(['components','matrix'].includes(v.filters.graphMode)||r.from===identifier || r.to===identifier)&&
          !(v.filters.graphMode==='neighborhood'&&['class','interface','record','enum'].includes(item.type)&&r.type==='contains'));
        v.relationsMore=relations.more; v.linkedDocs=docs.items.filter(d=>(d.entityRefs || []).includes(identifier));
        v.linkedDocsMore=docs.more;
        // Read only the endpoints of this bounded local neighborhood. No
        // recursive graph traversal or whole-project download is performed.
        const known=new Set([...v.items,...(v.componentItems||[])].map(x=>x.id));
        const missing=[...new Set(v.relations.flatMap(r=>[r.from,r.to]))].filter(id=>!known.has(id));
        const endpoints=await readGraphItems(v,missing);
        if (!active(v) || generation!==v.detailSequence) return;
        v.neighbors=endpoints.filter(Boolean);
        await resolveArchitectureLabels(v,item,generation);
      }
      if (redraw) draw(v);
    } catch (error) { fail(v,error); }
  }
  const docLinkIds=item=>[...new Set((item.entityRefs||[]).filter(id=>typeof id==='string'&&id))];
  const docLinkKey=(v,item)=>JSON.stringify([item.id,docLinkIds(item),v.context?.revision]);
  function docLinkState(v,item) {
    const signature=docLinkKey(v,item),prior=v.docLinks;
    if(prior?.signature===signature)return prior;
    const ids=docLinkIds(item),reuse=prior?.identifier===item.id&&prior.revision===v.context?.revision;
    v.linkedEntities=reuse?new Map(ids.filter(id=>v.linkedEntities.get(id)?.state!=='loading'&&v.linkedEntities.has(id)).map(id=>[id,v.linkedEntities.get(id)])):new Map();
    return v.docLinks={identifier:item.id,signature,ids,revision:v.context?.revision,expanded:prior?.identifier===item.id&&prior.expanded,loading:false,promise:null};
  }
  function documentLinksContent(v,item) {
    const ids=docLinkIds(item),state=v.docLinks?.signature===docLinkKey(v,item)?v.docLinks:null;
    if(!ids.length)return '';
    const expanded=!!state?.expanded,visible=expanded?ids.filter(id=>v.linkedEntities.has(id)&&v.linkedEntities.get(id).state!=='loading'):ids.slice(0,DOC_LINK_PAGE);
    const errors=visible.some(id=>v.linkedEntities.get(id)?.state==='error');
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.74398e178599",{v0:(ids.length),v1:(visible.map(id=>`<a href="${link('architecture',id)}" title="${esc(id)}">${entityLinkLabel(v,id)}</a>`).join('')),v2:(ids.length>DOC_LINK_PAGE||errors?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.14873adeacfd",{v0:(visible.length),v1:(ids.length),v2:(state?.loading?(globalThis.HubI18n?.t?.("knowledge.49fe8defe86d") ?? ' · Загружаются названия…'):''),v3:(ids.length>DOC_LINK_PAGE?`<button data-k-action="${expanded?'doc-links-collapse':'doc-links-all'}"${!expanded&&state?.loading?' disabled':''}>${expanded?(globalThis.HubI18n?.t?.("knowledge.36c25d9ffcfd") ?? 'Свернуть'):(globalThis.HubI18n?.t?.("knowledge.29beefeb2b7e") ?? 'Показать все')}</button>`:''),v4:(errors?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.46d6bd5a21e3",{v0:(state?.loading?' disabled':'')}) : `<button data-k-action="doc-links-retry"${state?.loading?' disabled':''}>Повторить загрузку названий</button>`):'')}) : `<div class="d-link-controls"><span role="status">${visible.length} из ${ids.length}${state?.loading?(globalThis.HubI18n?.t?.("knowledge.49fe8defe86d") ?? ' · Загружаются названия…'):''}</span>${ids.length>DOC_LINK_PAGE?`<button data-k-action="${expanded?'doc-links-collapse':'doc-links-all'}"${!expanded&&state?.loading?' disabled':''}>${expanded?(globalThis.HubI18n?.t?.("knowledge.36c25d9ffcfd") ?? 'Свернуть'):(globalThis.HubI18n?.t?.("knowledge.29beefeb2b7e") ?? 'Показать все')}</button>`:''}${errors?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.46d6bd5a21e3",{v0:(state?.loading?' disabled':'')}) : `<button data-k-action="doc-links-retry"${state?.loading?' disabled':''}>Повторить загрузку названий</button>`):''}</div>`):'')}) : `<strong>Архитектура <small>(${ids.length})</small></strong>${visible.map(id=>`<a href="${link('architecture',id)}" title="${esc(id)}">${entityLinkLabel(v,id)}</a>`).join('')}
      ${ids.length>DOC_LINK_PAGE||errors?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.14873adeacfd",{v0:(visible.length),v1:(ids.length),v2:(state?.loading?(globalThis.HubI18n?.t?.("knowledge.49fe8defe86d") ?? ' · Загружаются названия…'):''),v3:(ids.length>DOC_LINK_PAGE?`<button data-k-action="${expanded?'doc-links-collapse':'doc-links-all'}"${!expanded&&state?.loading?' disabled':''}>${expanded?(globalThis.HubI18n?.t?.("knowledge.36c25d9ffcfd") ?? 'Свернуть'):(globalThis.HubI18n?.t?.("knowledge.29beefeb2b7e") ?? 'Показать все')}</button>`:''),v4:(errors?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.46d6bd5a21e3",{v0:(state?.loading?' disabled':'')}) : `<button data-k-action="doc-links-retry"${state?.loading?' disabled':''}>Повторить загрузку названий</button>`):'')}) : `<div class="d-link-controls"><span role="status">${visible.length} из ${ids.length}${state?.loading?(globalThis.HubI18n?.t?.("knowledge.49fe8defe86d") ?? ' · Загружаются названия…'):''}</span>${ids.length>DOC_LINK_PAGE?`<button data-k-action="${expanded?'doc-links-collapse':'doc-links-all'}"${!expanded&&state?.loading?' disabled':''}>${expanded?(globalThis.HubI18n?.t?.("knowledge.36c25d9ffcfd") ?? 'Свернуть'):(globalThis.HubI18n?.t?.("knowledge.29beefeb2b7e") ?? 'Показать все')}</button>`:''}${errors?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.46d6bd5a21e3",{v0:(state?.loading?' disabled':'')}) : `<button data-k-action="doc-links-retry"${state?.loading?' disabled':''}>Повторить загрузку названий</button>`):''}</div>`):''}`);
  }
  function updateDocumentLinks(v,item) {
    if(!active(v)||v.selected!==item.id)return;
    const nav=mounted.root.querySelector('[data-k-doc-links]');
    if(!nav||nav.dataset.kDocLinks!==item.id){draw(v);return;}
    const focused=document.activeElement,action=nav.contains(focused)?focused?.dataset?.kAction:null;
    nav.innerHTML=documentLinksContent(v,item);nav.hidden=!docLinkIds(item).length;
    if(action){const next=nav.querySelector(`[data-k-action="${action}"]`)||nav.querySelector('[data-k-action]');next?.focus({preventScroll:true});}
  }
  async function resolveDocLinks(v,item) {
    if(!active(v)||item.id!==v.selected)return;
    const state=docLinkState(v,item);
    if(state.promise)return state.promise;
    const current=()=>active(v)&&v.docLinks===state&&v.selected===state.identifier&&docLinkKey(v,v.drafts.get(v.selected)?.item||item)===state.signature;
    const missing=()=>state.ids.slice(0,state.expanded?state.ids.length:DOC_LINK_PAGE).filter(id=>!v.linkedEntities.has(id));
    if(!missing().length){updateDocumentLinks(v,item);return;}
    state.loading=true;
    state.promise=(async()=>{
      try {
        while(current()){
          const ids=missing().slice(0,DOC_LINK_PAGE);if(!ids.length)break;
          ids.forEach(id=>v.linkedEntities.set(id,{state:'loading'}));updateDocumentLinks(v,item);
          const results=await Promise.all(ids.map(async id=>{
            try {const entity=await request(v,'read',{id});return [id,entity.kind!=='document'?{state:'ready',title:entity.title||entity.description||entity.type||id,removed:entity.removed}:{state:'missing'}];}
            catch(error){return [id,{state:error.code==='item_missing'?'missing':'error'}];}
          }));
          if(!current())return;
          results.forEach(([id,entry])=>v.linkedEntities.set(id,entry));updateDocumentLinks(v,item);
        }
      } finally {state.loading=false;state.promise=null;if(current())updateDocumentLinks(v,item);}
    })();
    return state.promise;
  }
  function entityLinkLabel(v,id) {
    const known=[...v.items,...(v.neighbors||[]),...(v.componentItems||[]),...(v.linkedDocs||[]),...(v.scenarios||[]),...[...v.drafts.values()].map(draft=>draft.item)].find(item=>item.id===id);
    if(known?.title)return esc(known.title);
    const entry=v.linkedEntities.get(id);
    if(entry?.state==='ready')return esc(entry.title)+(entry.removed?(globalThis.HubI18n?.t?.("knowledge.3a75c55e3d45") ?? ' · источник отсутствует'):'');
    if(!entry)return esc(id);
    return (v.mode==='docs'?esc(id)+' · ':'')+(entry.state==='missing'?(globalThis.HubI18n?.t?.("knowledge.3a0c21e12958") ?? 'элемент недоступен'):entry.state==='error'?(globalThis.HubI18n?.t?.("knowledge.046741ca6cc6") ?? 'название не удалось загрузить'):(globalThis.HubI18n?.t?.("knowledge.417f2145edf5") ?? 'название загружается'));
  }
  async function resolveArchitectureLabels(v,item,generation) {
    const known=new Set([...v.items,...(v.neighbors||[]),...(v.componentItems||[]),...(v.linkedDocs||[]),...[...v.drafts.values()].map(d=>d.item)].map(node=>node.id));
    const ids=[...new Set([...(item.documentRefs||[]),...v.relations.flatMap(edge=>[edge.from,edge.to])])].filter(id=>!known.has(id)).slice(0,20);
    const labels=await Promise.all(ids.map(async id=>{try{const found=await request(v,'read',{id});return [id,{state:'ready',title:found.title||(globalThis.HubI18n?.t?.("knowledge.8085a5fb0275") ?? 'Название не указано')}];}catch(_){return [id,{state:'missing'}];}}));
    if(active(v)&&generation===v.detailSequence&&item.id===v.selected)v.linkedEntities=new Map(labels);
  }
  function filtered(v) {
    return v.items.filter(item => !item.removed &&
      (!v.filters.audience || item.audience===v.filters.audience) &&
      (!v.filters.section || item.section===v.filters.section) &&
      (!v.filters.type || item.type===v.filters.type) &&
      (!v.filters.component || item.component===v.filters.component || item.id===v.filters.component) &&
      (!v.filters.entry || item.entrypoint));
  }
  function selectOptions(values, selected, first) {
    return `<option value="">${esc(first)}</option>` + [...new Set(values.filter(Boolean))].map(value=>
      `<option value="${esc(value)}"${value===selected?' selected':''}>${esc(value)}</option>`).join('');
  }
  function componentName(v,id) {
    const components=new Map((v.context?.policy?.components||[]).map(item=>[item.id,item])),names=[],seen=new Set();let component=components.get(id);
    if(!component)return id;
    while(component&&!seen.has(component.id)){seen.add(component.id);names.unshift(component.title||component.id);component=components.get(component.parent);}
    return names.join(' / ');
  }
  function toolbar(v) {
    if(v.mode==='architecture')return '';
    if(window.DocumentationUI)return window.DocumentationUI.toolbar(v);
    const policy=v.context?.policy||{};
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.276a86fcfe31",{v0:(esc(v.filters.query)),v1:(selectOptions([...(policy.audiences||[]),...v.items.map(x=>x.audience)],v.filters.audience,(globalThis.HubI18n?.t?.("knowledge.d6e3403bd0aa") ?? 'Все аудитории'))),v2:(selectOptions([...(policy.sections||[]),...v.items.map(x=>x.section)],v.filters.section,(globalThis.HubI18n?.t?.("knowledge.0ff4708ef6e1") ?? 'Все разделы'))),v3:(selectOptions(DOC_TYPES,v.filters.type,(globalThis.HubI18n?.t?.("knowledge.19161353d3bf") ?? 'Все типы')))}) : `<div class="k-filters"><label>Поиск<input data-k-filter="query" type="search" value="${esc(v.filters.query)}" placeholder="Название, текст, идентификатор"></label><label>Аудитория<select data-k-filter="audience">${selectOptions([...(policy.audiences||[]),...v.items.map(x=>x.audience)],v.filters.audience,(globalThis.HubI18n?.t?.("knowledge.d6e3403bd0aa") ?? 'Все аудитории'))}</select></label><label>Раздел<select data-k-filter="section">${selectOptions([...(policy.sections||[]),...v.items.map(x=>x.section)],v.filters.section,(globalThis.HubI18n?.t?.("knowledge.0ff4708ef6e1") ?? 'Все разделы'))}</select></label><label>Тип статьи<select data-k-filter="type">${selectOptions(DOC_TYPES,v.filters.type,(globalThis.HubI18n?.t?.("knowledge.19161353d3bf") ?? 'Все типы'))}</select></label></div>`);
  }
  function markdown(v, item) {
    const text=String(item.markdown || '').replace(/knowledge-asset:([a-f0-9]{64})/g, (_,hash)=> {
      const asset=(item.sources||[]).flatMap(s=>s.assets||[]).find(a=>a.hash===hash);
      return '/api/v1/knowledge/blob?' + new URLSearchParams({project:v.project,hash,name:asset?.name || 'asset'});
    });
    if (!window.marked || !window.DOMPurify) return `<pre>${esc(text)}</pre>`;
    const clean=window.DOMPurify.sanitize(window.marked.parse(text), {FORBID_TAGS:['style','form','iframe','object','embed'],FORBID_ATTR:['style','srcset']});
    // DOMPurify protects HTML; separately restrict remote/active image loads.
    const template=document.createElement('template'); template.innerHTML=clean;
    template.content.querySelectorAll('img').forEach(img=> {
      const src=img.getAttribute('src') || '';
      if (!src.startsWith('/api/v1/knowledge/blob?')) { img.replaceWith(document.createTextNode((globalThis.HubI18n?.t?.("knowledge.3fc61fe31ce8") ?? '[Изображение: ') + (img.getAttribute('alt') || src) + ']')); return; }
      const url=new URL(src,location.origin);
      if (url.searchParams.get('project')!==v.project || !/^[a-f0-9]{64}$/.test(url.searchParams.get('hash')||'')) img.remove();
      else { img.loading='lazy'; img.alt=img.alt || (globalThis.HubI18n?.t?.("knowledge.6eaac5b9d719") ?? 'Изображение документа'); }
    });
    template.content.querySelectorAll('a').forEach(a=> {
      const href=a.getAttribute('href') || '';
      if (/^(javascript|data|vbscript):/i.test(href)) a.removeAttribute('href');
      if (/^https?:/i.test(href)) { a.rel='noopener noreferrer'; a.target='_blank'; }
    });
    return template.innerHTML;
  }
  function catalog(v) {
    if(v.mode==='architecture'&&window.KnowledgeResearch)return window.KnowledgeResearch.catalog(v);
    if(v.mode==='docs'&&window.DocumentationUI)return window.DocumentationUI.catalog(v);
    if(v.mode==='architecture'&&window.ArchitectureMap){
      const browser=v.filters.browser||'structure',onGraph=browser==='graph',items=onGraph?graphModel(v).nodes:v.catalogTreeItems||[];
      return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.817f8931e5f0",{v0:(v.filters.listCollapsed?' k-collapsed':''),v1:(esc(browser)),v2:(v.filters.followSelection!==false),v3:(icon('LocateFixed')||'◎'),v4:(!v.filters.listCollapsed),v5:(v.filters.listCollapsed?(globalThis.HubI18n?.t?.("knowledge.c7c7a551079f") ?? 'Развернуть список'):(globalThis.HubI18n?.t?.("knowledge.8a9ef47f4ae1") ?? 'Свернуть список')),v6:(v.filters.listCollapsed?(globalThis.HubI18n?.t?.("knowledge.e342569d2132") ?? 'Развернуть навигатор'):(globalThis.HubI18n?.t?.("knowledge.16592fbe4452") ?? 'Свернуть навигатор')),v7:(icon(v.filters.listCollapsed?'PanelLeftOpen':'PanelLeftClose')),v8:(v.busy||(v.context?.jobs||[]).some(j=>['queued','running'].includes(j.state))?' disabled':''),v9:(icon('Activity')||(globalThis.HubI18n?.t?.("knowledge.ca285db3dd75") ?? 'Состояние')),v10:(icon('SlidersHorizontal')||(globalThis.HubI18n?.t?.("knowledge.4e90074f740b") ?? 'Инструменты')),v11:(analysisStatus(v)),v12:(browser==='structure'?(globalThis.HubI18n?.t?.("knowledge.b99e520d31ad") ?? 'Поиск структуры'):(globalThis.HubI18n?.t?.("knowledge.57319ddc7170") ?? 'Поиск исходников')),v13:(esc(v.filters.query)),v14:(browser==='catalog'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.37f0b3f35e34",{v0:(v.filters.discoveryScope!=='subsystem'?' selected':''),v1:(v.filters.discoveryScope==='subsystem'?' selected':''),v2:(!(v.drafts.get(v.selected)?.item.type==='component'||v.drafts.get(v.selected)?.item.component)?' disabled':'')}) : `<label>Область поиска<select data-k-discovery-scope><option value="project"${v.filters.discoveryScope!=='subsystem'?' selected':''}>В проекте</option><option value="subsystem"${v.filters.discoveryScope==='subsystem'?' selected':''}${!(v.drafts.get(v.selected)?.item.type==='component'||v.drafts.get(v.selected)?.item.component)?' disabled':''}>Собственный код подсистемы</option></select></label>`):''),v15:([['structure',(globalThis.HubI18n?.t?.("knowledge.816655bd716f") ?? 'Структура')],['catalog',(globalThis.HubI18n?.t?.("knowledge.550ed2eaf608") ?? 'Исходники')]].map(([id,title])=>`<button data-k-browser="${id}" aria-pressed="${browser===id}">${title}</button>`).join('')),v16:(architectureContext(v,true)),v17:(browser==='structure'?window.ArchitectureMap.tree(v):`<div class="k-count">${onGraph?items.length+(globalThis.HubI18n?.t?.("knowledge.caeb528f480b") ?? ' элементов текущей схемы'):v.catalogTreeLoading?(globalThis.HubI18n?.t?.("knowledge.c71a57df05f3") ?? 'Загрузка дерева…'):items.length+(globalThis.HubI18n?.t?.("knowledge.ec508b15b9bd") ?? ' элементов')+(v.filters.query?(globalThis.HubI18n?.t?.("knowledge.f1a36a3637b0") ?? ' · результаты поиска'):(globalThis.HubI18n?.t?.("knowledge.ffe2244ab9fb") ?? ' · весь проект'))}</div>${window.ArchitectureMap.fileTree(v,items)}`)}) : `<aside class="k-catalog${v.filters.listCollapsed?' k-collapsed':''}" data-k-browser-mode="${esc(browser)}" aria-label="Навигатор архитектуры"><header class="k-catalog-head"><h2>Навигатор</h2><button data-k-action="follow-selection" aria-pressed="${v.filters.followSelection!==false}" title="Следить за выбором на схеме" aria-label="Следить за выбором на схеме">${icon('LocateFixed')||'◎'}</button><button data-k-action="toggle-list" aria-expanded="${!v.filters.listCollapsed}" aria-label="${v.filters.listCollapsed?(globalThis.HubI18n?.t?.("knowledge.c7c7a551079f") ?? 'Развернуть список'):(globalThis.HubI18n?.t?.("knowledge.8a9ef47f4ae1") ?? 'Свернуть список')}" title="${v.filters.listCollapsed?(globalThis.HubI18n?.t?.("knowledge.e342569d2132") ?? 'Развернуть навигатор'):(globalThis.HubI18n?.t?.("knowledge.16592fbe4452") ?? 'Свернуть навигатор')}">${icon(v.filters.listCollapsed?'PanelLeftOpen':'PanelLeftClose')}</button></header><div class="k-navigator-actions"><button data-k-action="refresh">Перечитать данные</button><button data-k-action="scan"${v.busy||(v.context?.jobs||[]).some(j=>['queued','running'].includes(j.state))?' disabled':''}>Сканировать исходники</button><button data-k-action="diagnostics" aria-label="Состояние анализа">${icon('Activity')||(globalThis.HubI18n?.t?.("knowledge.ca285db3dd75") ?? 'Состояние')}</button><button data-k-action="tools" aria-label="Инструменты">${icon('SlidersHorizontal')||(globalThis.HubI18n?.t?.("knowledge.4e90074f740b") ?? 'Инструменты')}</button></div><div class="k-analysis-status" data-k-analysis-status role="status">${analysisStatus(v)}</div><label class="k-navigator-search">${browser==='structure'?(globalThis.HubI18n?.t?.("knowledge.b99e520d31ad") ?? 'Поиск структуры'):(globalThis.HubI18n?.t?.("knowledge.57319ddc7170") ?? 'Поиск исходников')}<input type="search" data-k-filter="query" value="${esc(v.filters.query)}" placeholder="Название или путь"></label>${browser==='catalog'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.37f0b3f35e34",{v0:(v.filters.discoveryScope!=='subsystem'?' selected':''),v1:(v.filters.discoveryScope==='subsystem'?' selected':''),v2:(!(v.drafts.get(v.selected)?.item.type==='component'||v.drafts.get(v.selected)?.item.component)?' disabled':'')}) : `<label>Область поиска<select data-k-discovery-scope><option value="project"${v.filters.discoveryScope!=='subsystem'?' selected':''}>В проекте</option><option value="subsystem"${v.filters.discoveryScope==='subsystem'?' selected':''}${!(v.drafts.get(v.selected)?.item.type==='component'||v.drafts.get(v.selected)?.item.component)?' disabled':''}>Собственный код подсистемы</option></select></label>`):''}<small data-k-follow-status></small><div class="k-browser-tabs" role="group" aria-label="Содержимое навигатора">${[['structure',(globalThis.HubI18n?.t?.("knowledge.816655bd716f") ?? 'Структура')],['catalog',(globalThis.HubI18n?.t?.("knowledge.550ed2eaf608") ?? 'Исходники')]].map(([id,title])=>`<button data-k-browser="${id}" aria-pressed="${browser===id}">${title}</button>`).join('')}</div>${architectureContext(v,true)}${browser==='structure'?window.ArchitectureMap.tree(v):`<div class="k-count">${onGraph?items.length+(globalThis.HubI18n?.t?.("knowledge.caeb528f480b") ?? ' элементов текущей схемы'):v.catalogTreeLoading?(globalThis.HubI18n?.t?.("knowledge.c71a57df05f3") ?? 'Загрузка дерева…'):items.length+(globalThis.HubI18n?.t?.("knowledge.ec508b15b9bd") ?? ' элементов')+(v.filters.query?(globalThis.HubI18n?.t?.("knowledge.f1a36a3637b0") ?? ' · результаты поиска'):(globalThis.HubI18n?.t?.("knowledge.ffe2244ab9fb") ?? ' · весь проект'))}</div>${window.ArchitectureMap.fileTree(v,items)}`}</aside>`);
    }
    const onGraph=v.mode==='architecture'&&v.filters.listMode!=='catalog'&&v.filters.graphMode!=='catalog',items=onGraph?graphModel(v).nodes:filtered(v);
    const group=item=>item.type==='component'?(globalThis.HubI18n?.t?.("knowledge.1e8466ebebaf") ?? 'Компоненты'):item.entrypoint?(globalThis.HubI18n?.t?.("knowledge.8d6e25aa7b88") ?? 'Точки входа'):item.type==='interface'?(globalThis.HubI18n?.t?.("knowledge.8a89b9398cca") ?? 'Интерфейсы'):item.type==='file'?(globalThis.HubI18n?.t?.("knowledge.823384848ecc") ?? 'Файлы / модули'):item.type==='external'?(globalThis.HubI18n?.t?.("knowledge.e04215953573") ?? 'Внешние зависимости'):(globalThis.HubI18n?.t?.("knowledge.1e8f1ab7f1a6") ?? 'Классы / типы');
    let previous='';
    return `<aside class="k-catalog${v.mode==='architecture'&&v.filters.listCollapsed?' k-collapsed':''}" aria-label="${v.mode==='docs'?(globalThis.HubI18n?.t?.("knowledge.279e6b2bd1dc") ?? 'Статьи'):(globalThis.HubI18n?.t?.("knowledge.371783c09a6a") ?? 'Элементы модели')}">
      ${v.mode==='architecture'?`<button data-k-action="toggle-list" aria-expanded="${!v.filters.listCollapsed}" aria-label="${v.filters.listCollapsed?(globalThis.HubI18n?.t?.("knowledge.c7c7a551079f") ?? 'Развернуть список'):(globalThis.HubI18n?.t?.("knowledge.8a9ef47f4ae1") ?? 'Свернуть список')}">${v.filters.listCollapsed?'☰':(globalThis.HubI18n?.t?.("knowledge.8a9ef47f4ae1") ?? 'Свернуть список')}</button>`:''}
      ${v.mode==='architecture'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9d59fec28e78",{v0:(onGraph?' selected':''),v1:(!onGraph?' selected':''),v2:(onGraph?(globalThis.HubI18n?.t?.("knowledge.4bc69b378182") ?? 'Элементы текущего представления'):(globalThis.HubI18n?.t?.("knowledge.331ed8173c2c") ?? 'Все элементы архитектурной базы; поиск по проекту'))}) : `<label>Список<select data-k-filter="listMode"><option value="graph"${onGraph?' selected':''}>На схеме</option><option value="catalog"${!onGraph?' selected':''}>Весь каталог</option></select></label><p>${onGraph?(globalThis.HubI18n?.t?.("knowledge.4bc69b378182") ?? 'Элементы текущего представления'):(globalThis.HubI18n?.t?.("knowledge.331ed8173c2c") ?? 'Все элементы архитектурной базы; поиск по проекту')}</p>`):''}
      <div class="k-count">${onGraph?items.length+(globalThis.HubI18n?.t?.("knowledge.af3de774e2fe") ?? ' элементов на схеме'):(globalThis.HubI18n?.t?.("knowledge.978b2791fbea") ?? 'Показано ')+items.length+(Number.isFinite(v.total)?(globalThis.HubI18n?.t?.("knowledge.e029cc4b39ce") ?? ' из ')+v.total+(globalThis.HubI18n?.t?.("knowledge.7dc34e0efdfc") ?? ' результатов'):(globalThis.HubI18n?.t?.("knowledge.7dc34e0efdfc") ?? ' результатов'))}</div>
      ${[...items].sort((a,b)=>v.mode==='architecture'?group(a).localeCompare(group(b),'ru'):0).map(item=>{const heading=v.mode==='architecture'&&group(item)!==previous?`<h3 class="k-list-group">${esc(group(item))}</h3>`:'';previous=group(item);return heading+`<a class="k-item${item.id===v.selected?' selected':''}" href="${link(v.mode,item.id)}" data-k-select="${esc(item.id)}" title="${esc(nodeLabel(item).full)}"${item.id===v.selected?' aria-current="true"':''}><strong>${esc(v.mode==='architecture'?nodeLabel(item).rows.join(''):item.title)}</strong><small>${esc(v.mode==='docs' ? [item.audience,item.section,item.type,item.status].filter(Boolean).join(' · ') : [nodeTypes[item.type]||item.type,componentName(v,item.component),item.entrypoint?(globalThis.HubI18n?.t?.("knowledge.2b4beceac80f") ?? 'Точка входа'):''].filter(Boolean).join(' · '))}</small>${v.mode==='docs'?`<span>${esc(item.excerpt || '')}</span>`:''}</a>`;}).join('') || `<p class="k-empty">${onGraph?(globalThis.HubI18n?.t?.("knowledge.e869f114154d") ?? 'На текущей схеме элементов нет. Откройте весь каталог или измените представление.'):(globalThis.HubI18n?.t?.("knowledge.e65877f5393d") ?? 'Ничего не найдено. Измените поиск или фильтры.')}</p>`}
      ${!onGraph&&v.more ? v.items.length<MAX_ITEMS ? (globalThis.HubI18n?.t?.("knowledge.5c068ebab74e") ?? '<button data-k-action="more">Показать ещё</button>') : (globalThis.HubI18n?.t?.("knowledge.ca522d14614c") ?? '<p>Показано максимум 200 элементов. Уточните поиск.</p>') : ''}</aside>`;
  }
  function historyPanel(v,id=v.selected) {
    if ((v.historyId||v.selected)!==id || !v.history) return '';
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.94736024ec51",{v0:(v.history.items.map(row=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.dbbc3ea46098",{v0:(row.revision),v1:(esc(id)),v2:(row.revision),v3:(esc(row.at)),v4:(esc(row.reason)),v5:(row.task?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9cbeea5e736c",{v0:(taskHref(row.task,row.stage)),v1:(esc(row.task)),v2:(row.stage?' / '+esc(row.stage):'')}) : `<a href="${taskHref(row.task,row.stage)}">Задача ${esc(row.task)}${row.stage?' / '+esc(row.stage):''}</a>`):(globalThis.HubI18n?.t?.("knowledge.be1848bcacd3") ?? '<small>Задача не привязана</small>')),v6:(codeBasis(row.codeRevision))}) : `<div><button data-k-revision="${row.revision}" data-k-role-id="${esc(id)}">Версия ${row.revision}</button><span>${esc(row.at)} · ${esc(row.reason)}
      ${row.task?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9cbeea5e736c",{v0:(taskHref(row.task,row.stage)),v1:(esc(row.task)),v2:(row.stage?' / '+esc(row.stage):'')}) : `<a href="${taskHref(row.task,row.stage)}">Задача ${esc(row.task)}${row.stage?' / '+esc(row.stage):''}</a>`):(globalThis.HubI18n?.t?.("knowledge.be1848bcacd3") ?? '<small>Задача не привязана</small>')}${codeBasis(row.codeRevision)}</span></div>`)).join('') || (globalThis.HubI18n?.t?.("knowledge.25f6d93e8d3c") ?? '<p>В этой странице истории изменений элемента нет.</p>')),v1:(v.history.more?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.48c6b08159e4",{v0:(esc(id))}) : `<button data-k-action="history-more" data-k-role-id="${esc(id)}">Следующая страница истории</button>`):'')}) : `<section class="k-history"><h3>История изменений</h3>${v.history.items.map(row=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.dbbc3ea46098",{v0:(row.revision),v1:(esc(id)),v2:(row.revision),v3:(esc(row.at)),v4:(esc(row.reason)),v5:(row.task?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9cbeea5e736c",{v0:(taskHref(row.task,row.stage)),v1:(esc(row.task)),v2:(row.stage?' / '+esc(row.stage):'')}) : `<a href="${taskHref(row.task,row.stage)}">Задача ${esc(row.task)}${row.stage?' / '+esc(row.stage):''}</a>`):(globalThis.HubI18n?.t?.("knowledge.be1848bcacd3") ?? '<small>Задача не привязана</small>')),v6:(codeBasis(row.codeRevision))}) : `<div><button data-k-revision="${row.revision}" data-k-role-id="${esc(id)}">Версия ${row.revision}</button><span>${esc(row.at)} · ${esc(row.reason)}
      ${row.task?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9cbeea5e736c",{v0:(taskHref(row.task,row.stage)),v1:(esc(row.task)),v2:(row.stage?' / '+esc(row.stage):'')}) : `<a href="${taskHref(row.task,row.stage)}">Задача ${esc(row.task)}${row.stage?' / '+esc(row.stage):''}</a>`):(globalThis.HubI18n?.t?.("knowledge.be1848bcacd3") ?? '<small>Задача не привязана</small>')}${codeBasis(row.codeRevision)}</span></div>`)).join('') || (globalThis.HubI18n?.t?.("knowledge.25f6d93e8d3c") ?? '<p>В этой странице истории изменений элемента нет.</p>')}
      ${v.history.more?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.48c6b08159e4",{v0:(esc(id))}) : `<button data-k-action="history-more" data-k-role-id="${esc(id)}">Следующая страница истории</button>`):''}</section>`);
  }
  function codeBasis(revision) {
    const basis=revision?.basis, labels={'local-source-scan':(globalThis.HubI18n?.t?.("knowledge.d251b7ad835a") ?? 'Локальное сканирование исходников'),'last-successful-scan':(globalThis.HubI18n?.t?.("knowledge.8e999ca1c071") ?? 'Последнее успешное сканирование; текущий код может отличаться'),'source-revision-unavailable':(globalThis.HubI18n?.t?.("knowledge.3a3a46f973da") ?? 'Версия исходного кода неизвестна')};
    const heads=Array.isArray(revision?.heads)?revision.heads:[];
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.26f492f8ca0c",{v0:(esc(labels[basis]||basis||(globalThis.HubI18n?.t?.("knowledge.3a3a46f973da") ?? 'Версия исходного кода неизвестна'))),v1:(revision?.fingerprint?`<br>Fingerprint: <code>${esc(revision.fingerprint)}</code>`:(globalThis.HubI18n?.t?.("knowledge.e8bff9ea4928") ?? '<br>Fingerprint неизвестен')),v2:(heads.length?`<br>Git HEAD: ${heads.map((head,index)=>(globalThis.HubI18n?.t?.("knowledge.1add7a6d5db1") ?? 'корень ')+(index+1)+' — '+(head?esc(head):(globalThis.HubI18n?.t?.("knowledge.5aea9d7ced44") ?? 'неизвестен'))).join('; ')}`:(globalThis.HubI18n?.t?.("knowledge.bcdad090ec18") ?? '<br>Git HEAD неизвестен'))}) : `<small class="k-code-basis">Основание: ${esc(labels[basis]||basis||(globalThis.HubI18n?.t?.("knowledge.3a3a46f973da") ?? 'Версия исходного кода неизвестна'))}${revision?.fingerprint?`<br>Fingerprint: <code>${esc(revision.fingerprint)}</code>`:(globalThis.HubI18n?.t?.("knowledge.e8bff9ea4928") ?? '<br>Fingerprint неизвестен')}${heads.length?`<br>Git HEAD: ${heads.map((head,index)=>(globalThis.HubI18n?.t?.("knowledge.1add7a6d5db1") ?? 'корень ')+(index+1)+' — '+(head?esc(head):(globalThis.HubI18n?.t?.("knowledge.5aea9d7ced44") ?? 'неизвестен'))).join('; ')}`:(globalThis.HubI18n?.t?.("knowledge.bcdad090ec18") ?? '<br>Git HEAD неизвестен')}</small>`);
  }
  function incompleteSources(item) {
    const problems=[['missingAssets',(globalThis.HubI18n?.t?.("knowledge.3839403cd19a") ?? 'Не найдены изображения')],['missingLinks',(globalThis.HubI18n?.t?.("knowledge.57db5f2d9642") ?? 'Неполные ссылки на исходники')]];
    return problems.map(([field,label])=> {
      const values=Array.isArray(item[field])?item[field]:[];
      return values.length?`<p class="k-warning">${label}: ${esc(values.slice(0,20).map(value=>typeof value==='string'?value:value.target||value.path||JSON.stringify(value)).join(', '))}${values.length>20?(globalThis.HubI18n?.t?.("knowledge.c3f30b16faf5") ?? ' · и ещё ')+(values.length-20):''}</p>`:'';
    }).join('');
  }
  function debtNotice(v) {
    const context=v.context;if(!context)return '';
    const pending=Number(context.publicationPending)||0, reviews=(context.reviews||[]).filter(review=>review.state==='review-needed');
    if(!pending&&!reviews.length)return '';
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.00451de0e1c6",{v0:(pending?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.baf50f7afde0",{v0:(pending)}) : `<p class="k-warning" role="status">Публикация в журнал задачи ожидает доставки: ${pending}. Сохранённые знания доступны; подтверждение связи с задачей ещё не доставлено.</p>`):''),v1:(reviews.map(review=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.53883d4251fd",{v0:(taskHref(review.task,review.stage)),v1:(esc(review.task)),v2:(review.stage?' / '+esc(review.stage):''),v3:(esc(review.reason||(globalThis.HubI18n?.t?.("knowledge.bffdeff3432b") ?? 'Причина не указана')))}) : `<p class="k-warning">Требуется сверка знаний: <a href="${taskHref(review.task,review.stage)}">${esc(review.task)}${review.stage?' / '+esc(review.stage):''}</a> · ${esc(review.reason||(globalThis.HubI18n?.t?.("knowledge.bffdeff3432b") ?? 'Причина не указана'))}</p>`)).join(''))}) : `<section class="k-debt" aria-label="Незавершённое согласование знаний">${pending?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.baf50f7afde0",{v0:(pending)}) : `<p class="k-warning" role="status">Публикация в журнал задачи ожидает доставки: ${pending}. Сохранённые знания доступны; подтверждение связи с задачей ещё не доставлено.</p>`):''}
      ${reviews.map(review=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.53883d4251fd",{v0:(taskHref(review.task,review.stage)),v1:(esc(review.task)),v2:(review.stage?' / '+esc(review.stage):''),v3:(esc(review.reason||(globalThis.HubI18n?.t?.("knowledge.bffdeff3432b") ?? 'Причина не указана')))}) : `<p class="k-warning">Требуется сверка знаний: <a href="${taskHref(review.task,review.stage)}">${esc(review.task)}${review.stage?' / '+esc(review.stage):''}</a> · ${esc(review.reason||(globalThis.HubI18n?.t?.("knowledge.bffdeff3432b") ?? 'Причина не указана'))}</p>`)).join('')}</section>`);
  }
  function documentPanel(v, draft) {
    const item=draft.item, historical=v.historical;
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.3190d4ec9899",{v0:(item.format==='html'?' d-html-page':''),v1:(esc(item.title)),v2:(v.editing?(globalThis.HubI18n?.t?.("knowledge.b39f2a07ba06") ?? 'Читать'):(globalThis.HubI18n?.t?.("knowledge.59792556fd06") ?? 'Редактировать')),v3:(incompleteSources(item)),v4:(draft.dirty?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.6670eeccd58b",{v0:(draft.expected),v1:(draft.expected!==v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.e749fd121ab4") ?? ' · знания проекта обновились; требуется сверка'):'')}) : `<p class="k-warning">Несохранённый черновик · основан на версии ${draft.expected}${draft.expected!==v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.e749fd121ab4") ?? ' · знания проекта обновились; требуется сверка'):''}</p>`):''),v5:(v.editing?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.f29d21c0e8f4",{v0:(esc(item.title)),v1:(window.DocumentationUI?.editorMetadata?window.DocumentationUI.editorMetadata(v,item):(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.c665b809de48",{v0:(esc(item.audience||'')),v1:((v.context?.policy?.audiences||[]).map(x=>`<option value="${esc(x)}">`).join('')),v2:(esc(item.section||'')),v3:(selectOptions(DOC_TYPES,item.type,(globalThis.HubI18n?.t?.("knowledge.a68feb74138f") ?? 'Не классифицирована'))),v4:(['draft','current','historical','archived'].map(x=>`<option${item.status===x?' selected':''}>${x}</option>`).join(''))}) : `<label>Аудитория<input data-k-field="audience" list="k-audiences" value="${esc(item.audience||'')}"><datalist id="k-audiences">${(v.context?.policy?.audiences||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist></label>
      <label>Раздел<input data-k-field="section" value="${esc(item.section||'')}"></label>
      <label>Тип статьи<select data-k-field="type">${selectOptions(DOC_TYPES,item.type,(globalThis.HubI18n?.t?.("knowledge.a68feb74138f") ?? 'Не классифицирована'))}</select></label>
      <label>Статус<select data-k-field="status">${['draft','current','historical','archived'].map(x=>`<option${item.status===x?' selected':''}>${x}</option>`).join('')}</select></label>`)),v2:(esc((item.entityRefs||[]).join(', '))),v3:(item.format==='html'?(globalThis.HubI18n?.t?.("knowledge.ef0141cc3a49") ?? '<p>HTML и зависимости обновляются через импорт исходника с проверкой изменений. Здесь редактируются название, раздел и статус.</p>'):`<label>Markdown<textarea data-k-field="markdown" rows="18">${esc(item.markdown||'')}</textarea></label>`),v4:(v.busy?' disabled':''),v5:(v.preview?(globalThis.HubI18n?.t?.("knowledge.0a2a4b837761") ?? 'Скрыть'):(globalThis.HubI18n?.t?.("knowledge.1e5bec3aab1c") ?? 'Показать'))}) : `<div class="k-editor"><label>Заголовок<input data-k-field="title" value="${esc(item.title)}"></label><div class="k-editor-meta">
      ${window.DocumentationUI?.editorMetadata?window.DocumentationUI.editorMetadata(v,item):(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.c665b809de48",{v0:(esc(item.audience||'')),v1:((v.context?.policy?.audiences||[]).map(x=>`<option value="${esc(x)}">`).join('')),v2:(esc(item.section||'')),v3:(selectOptions(DOC_TYPES,item.type,(globalThis.HubI18n?.t?.("knowledge.a68feb74138f") ?? 'Не классифицирована'))),v4:(['draft','current','historical','archived'].map(x=>`<option${item.status===x?' selected':''}>${x}</option>`).join(''))}) : `<label>Аудитория<input data-k-field="audience" list="k-audiences" value="${esc(item.audience||'')}"><datalist id="k-audiences">${(v.context?.policy?.audiences||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist></label>
      <label>Раздел<input data-k-field="section" value="${esc(item.section||'')}"></label>
      <label>Тип статьи<select data-k-field="type">${selectOptions(DOC_TYPES,item.type,(globalThis.HubI18n?.t?.("knowledge.a68feb74138f") ?? 'Не классифицирована'))}</select></label>
      <label>Статус<select data-k-field="status">${['draft','current','historical','archived'].map(x=>`<option${item.status===x?' selected':''}>${x}</option>`).join('')}</select></label>`)}</div>
      <label>Связанные элементы архитектуры (ID через запятую)<input data-k-field="entityRefs" value="${esc((item.entityRefs||[]).join(', '))}"></label>
      ${item.format==='html'?(globalThis.HubI18n?.t?.("knowledge.ef0141cc3a49") ?? '<p>HTML и зависимости обновляются через импорт исходника с проверкой изменений. Здесь редактируются название, раздел и статус.</p>'):`<label>Markdown<textarea data-k-field="markdown" rows="18">${esc(item.markdown||'')}</textarea></label>`}
      <div class="k-actions"><button data-k-action="save"${v.busy?' disabled':''}>Сохранить новую версию</button><button data-k-action="preview">${v.preview?(globalThis.HubI18n?.t?.("knowledge.0a2a4b837761") ?? 'Скрыть'):(globalThis.HubI18n?.t?.("knowledge.1e5bec3aab1c") ?? 'Показать')} предпросмотр</button><button data-k-action="discard">Загрузить сохранённую версию</button></div></div>`):''),v6:(!v.editing||v.preview?item.format==='html'&&window.HtmlDocuments?window.HtmlDocuments.render(item,v.project,draft.expected??v.context?.revision):`<div class="k-markdown">${markdown(v,item)}</div>`:''),v7:(esc(item.id)),v8:(docLinkIds(item).length?'':' hidden'),v9:(documentLinksContent(v,item)),v10:(historyPanel(v)),v11:(historical?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.51864059642a",{v0:(historical.revision),v1:(historical.item.format==='html'&&window.HtmlDocuments?window.HtmlDocuments.render(historical.item,v.project,historical.revision):`<div class="k-markdown">${markdown(v,historical.item)}</div>`),v2:(v.comparing?' disabled':''),v3:(v.comparing?(globalThis.HubI18n?.t?.("knowledge.3506391e9a3d") ?? 'Загрузка текущей статьи…'):(globalThis.HubI18n?.t?.("knowledge.c0bd2cf14b30") ?? 'Сравнить с текущей')),v4:(comparisonPanel(v))}) : `<section class="k-historical"><h3>Просмотр версии ${historical.revision}</h3>${historical.item.format==='html'&&window.HtmlDocuments?window.HtmlDocuments.render(historical.item,v.project,historical.revision):`<div class="k-markdown">${markdown(v,historical.item)}</div>`}<div class="k-actions"><button data-k-action="compare"${v.comparing?' disabled':''}>${v.comparing?(globalThis.HubI18n?.t?.("knowledge.3506391e9a3d") ?? 'Загрузка текущей статьи…'):(globalThis.HubI18n?.t?.("knowledge.c0bd2cf14b30") ?? 'Сравнить с текущей')}</button><button data-k-action="restore">Восстановить как новую версию</button></div>${comparisonPanel(v)}</section>`):'')}) : `<article class="k-inspector${item.format==='html'?' d-html-page':''}"><div class="k-inspector-head"><h2>${esc(item.title)}</h2><button data-k-action="history">История</button>
      <button data-k-action="edit">${v.editing?(globalThis.HubI18n?.t?.("knowledge.b39f2a07ba06") ?? 'Читать'):(globalThis.HubI18n?.t?.("knowledge.59792556fd06") ?? 'Редактировать')}</button></div>
      ${incompleteSources(item)}
      ${draft.dirty?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.6670eeccd58b",{v0:(draft.expected),v1:(draft.expected!==v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.e749fd121ab4") ?? ' · знания проекта обновились; требуется сверка'):'')}) : `<p class="k-warning">Несохранённый черновик · основан на версии ${draft.expected}${draft.expected!==v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.e749fd121ab4") ?? ' · знания проекта обновились; требуется сверка'):''}</p>`):''}
      ${v.editing?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.f29d21c0e8f4",{v0:(esc(item.title)),v1:(window.DocumentationUI?.editorMetadata?window.DocumentationUI.editorMetadata(v,item):(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.c665b809de48",{v0:(esc(item.audience||'')),v1:((v.context?.policy?.audiences||[]).map(x=>`<option value="${esc(x)}">`).join('')),v2:(esc(item.section||'')),v3:(selectOptions(DOC_TYPES,item.type,(globalThis.HubI18n?.t?.("knowledge.a68feb74138f") ?? 'Не классифицирована'))),v4:(['draft','current','historical','archived'].map(x=>`<option${item.status===x?' selected':''}>${x}</option>`).join(''))}) : `<label>Аудитория<input data-k-field="audience" list="k-audiences" value="${esc(item.audience||'')}"><datalist id="k-audiences">${(v.context?.policy?.audiences||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist></label>
      <label>Раздел<input data-k-field="section" value="${esc(item.section||'')}"></label>
      <label>Тип статьи<select data-k-field="type">${selectOptions(DOC_TYPES,item.type,(globalThis.HubI18n?.t?.("knowledge.a68feb74138f") ?? 'Не классифицирована'))}</select></label>
      <label>Статус<select data-k-field="status">${['draft','current','historical','archived'].map(x=>`<option${item.status===x?' selected':''}>${x}</option>`).join('')}</select></label>`)),v2:(esc((item.entityRefs||[]).join(', '))),v3:(item.format==='html'?(globalThis.HubI18n?.t?.("knowledge.ef0141cc3a49") ?? '<p>HTML и зависимости обновляются через импорт исходника с проверкой изменений. Здесь редактируются название, раздел и статус.</p>'):`<label>Markdown<textarea data-k-field="markdown" rows="18">${esc(item.markdown||'')}</textarea></label>`),v4:(v.busy?' disabled':''),v5:(v.preview?(globalThis.HubI18n?.t?.("knowledge.0a2a4b837761") ?? 'Скрыть'):(globalThis.HubI18n?.t?.("knowledge.1e5bec3aab1c") ?? 'Показать'))}) : `<div class="k-editor"><label>Заголовок<input data-k-field="title" value="${esc(item.title)}"></label><div class="k-editor-meta">
      ${window.DocumentationUI?.editorMetadata?window.DocumentationUI.editorMetadata(v,item):(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.c665b809de48",{v0:(esc(item.audience||'')),v1:((v.context?.policy?.audiences||[]).map(x=>`<option value="${esc(x)}">`).join('')),v2:(esc(item.section||'')),v3:(selectOptions(DOC_TYPES,item.type,(globalThis.HubI18n?.t?.("knowledge.a68feb74138f") ?? 'Не классифицирована'))),v4:(['draft','current','historical','archived'].map(x=>`<option${item.status===x?' selected':''}>${x}</option>`).join(''))}) : `<label>Аудитория<input data-k-field="audience" list="k-audiences" value="${esc(item.audience||'')}"><datalist id="k-audiences">${(v.context?.policy?.audiences||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist></label>
      <label>Раздел<input data-k-field="section" value="${esc(item.section||'')}"></label>
      <label>Тип статьи<select data-k-field="type">${selectOptions(DOC_TYPES,item.type,(globalThis.HubI18n?.t?.("knowledge.a68feb74138f") ?? 'Не классифицирована'))}</select></label>
      <label>Статус<select data-k-field="status">${['draft','current','historical','archived'].map(x=>`<option${item.status===x?' selected':''}>${x}</option>`).join('')}</select></label>`)}</div>
      <label>Связанные элементы архитектуры (ID через запятую)<input data-k-field="entityRefs" value="${esc((item.entityRefs||[]).join(', '))}"></label>
      ${item.format==='html'?(globalThis.HubI18n?.t?.("knowledge.ef0141cc3a49") ?? '<p>HTML и зависимости обновляются через импорт исходника с проверкой изменений. Здесь редактируются название, раздел и статус.</p>'):`<label>Markdown<textarea data-k-field="markdown" rows="18">${esc(item.markdown||'')}</textarea></label>`}
      <div class="k-actions"><button data-k-action="save"${v.busy?' disabled':''}>Сохранить новую версию</button><button data-k-action="preview">${v.preview?(globalThis.HubI18n?.t?.("knowledge.0a2a4b837761") ?? 'Скрыть'):(globalThis.HubI18n?.t?.("knowledge.1e5bec3aab1c") ?? 'Показать')} предпросмотр</button><button data-k-action="discard">Загрузить сохранённую версию</button></div></div>`):''}
      ${!v.editing||v.preview?item.format==='html'&&window.HtmlDocuments?window.HtmlDocuments.render(item,v.project,draft.expected??v.context?.revision):`<div class="k-markdown">${markdown(v,item)}</div>`:''}
      <nav class="k-links" data-k-doc-links="${esc(item.id)}" aria-label="Связанная архитектура"${docLinkIds(item).length?'':' hidden'}>${documentLinksContent(v,item)}</nav>
      ${historyPanel(v)}${historical?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.51864059642a",{v0:(historical.revision),v1:(historical.item.format==='html'&&window.HtmlDocuments?window.HtmlDocuments.render(historical.item,v.project,historical.revision):`<div class="k-markdown">${markdown(v,historical.item)}</div>`),v2:(v.comparing?' disabled':''),v3:(v.comparing?(globalThis.HubI18n?.t?.("knowledge.3506391e9a3d") ?? 'Загрузка текущей статьи…'):(globalThis.HubI18n?.t?.("knowledge.c0bd2cf14b30") ?? 'Сравнить с текущей')),v4:(comparisonPanel(v))}) : `<section class="k-historical"><h3>Просмотр версии ${historical.revision}</h3>${historical.item.format==='html'&&window.HtmlDocuments?window.HtmlDocuments.render(historical.item,v.project,historical.revision):`<div class="k-markdown">${markdown(v,historical.item)}</div>`}<div class="k-actions"><button data-k-action="compare"${v.comparing?' disabled':''}>${v.comparing?(globalThis.HubI18n?.t?.("knowledge.3506391e9a3d") ?? 'Загрузка текущей статьи…'):(globalThis.HubI18n?.t?.("knowledge.c0bd2cf14b30") ?? 'Сравнить с текущей')}</button><button data-k-action="restore">Восстановить как новую версию</button></div>${comparisonPanel(v)}</section>`):''}</article>`);
  }
  function changedFragment(previous, current) {
    const before=String(previous||''),after=String(current||'');
    const oldLines=before?before.split(/\r?\n/):[],newLines=after?after.split(/\r?\n/):[];
    let prefix=0,suffix=0;
    while(prefix<oldLines.length&&prefix<newLines.length&&oldLines[prefix]===newLines[prefix])prefix++;
    while(suffix<oldLines.length-prefix&&suffix<newLines.length-prefix&&oldLines[oldLines.length-1-suffix]===newLines[newLines.length-1-suffix])suffix++;
    const old=oldLines.slice(prefix,oldLines.length-suffix),next=newLines.slice(prefix,newLines.length-suffix);
    let trimmed=false;
    const bounded=rows=>rows.slice(0,200).map((text,index)=> {
      if(text.length>500)trimmed=true;
      return {line:prefix+index+1,text:text.slice(0,500)+(text.length>500?'…':'')};
    });
    const removed=bounded(old),added=bounded(next);
    return {unchanged:!old.length&&!next.length,removed,added,oldTotal:old.length,newTotal:next.length,
      omitted:Math.max(0,old.length-200)+Math.max(0,next.length-200),trimmed};
  }
  function comparisonPanel(v) {
    const comparison=v.comparison;if(!comparison)return '';
    const diff=comparison.diff;
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.3f35bec5c245",{v0:(comparison.revision),v1:(comparison.html?(globalThis.HubI18n?.t?.("knowledge.fe7436fc4c35") ?? 'Сравниваются пути, хеши и размеры файлов комплекта HTML. '):''),v2:(diff.unchanged?`<p role="status">${comparison.html?(globalThis.HubI18n?.t?.("knowledge.b38e5d504a3a") ?? 'Изменений комплекта HTML нет.'):(globalThis.HubI18n?.t?.("knowledge.0f8b9405fb4c") ?? 'Изменений текста нет.')}</p>`:(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.ef5d6a7314f0",{v0:(diff.oldTotal),v1:(diff.newTotal),v2:(diff.removed.map(row=>`<span class="k-diff-removed">− ${row.line}: ${esc(row.text)}</span>`).join('')||(globalThis.HubI18n?.t?.("knowledge.327245a6954f") ?? '<span>Удалённых строк нет.</span>')),v3:(diff.added.map(row=>`<span class="k-diff-added">+ ${row.line}: ${esc(row.text)}</span>`).join('')||(globalThis.HubI18n?.t?.("knowledge.a1ba7ce4d3e9") ?? '<span>Добавленных строк нет.</span>'))}) : `<p>Строк в прежнем фрагменте: ${diff.oldTotal}; в текущем: ${diff.newTotal}.</p><div class="k-diff-columns"><section><h5>Прежняя версия</h5><pre>${diff.removed.map(row=>`<span class="k-diff-removed">− ${row.line}: ${esc(row.text)}</span>`).join('')||(globalThis.HubI18n?.t?.("knowledge.327245a6954f") ?? '<span>Удалённых строк нет.</span>')}</pre></section><section><h5>Текущая сохранённая</h5><pre>${diff.added.map(row=>`<span class="k-diff-added">+ ${row.line}: ${esc(row.text)}</span>`).join('')||(globalThis.HubI18n?.t?.("knowledge.a1ba7ce4d3e9") ?? '<span>Добавленных строк нет.</span>')}</pre></section></div>`)),v3:(diff.omitted||diff.trimmed?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.2177df655ea8",{v0:(diff.omitted?(globalThis.HubI18n?.t?.("knowledge.643a931a8530") ?? ' Не показано строк: ')+diff.omitted+'.':''),v1:(diff.trimmed?(globalThis.HubI18n?.t?.("knowledge.0daa819a26c8") ?? ' Длинные строки сокращены.'):'')}) : `<p class="k-warning">Сравнение ограничено 200 строками каждой версии и 500 символами строки.${diff.omitted?(globalThis.HubI18n?.t?.("knowledge.643a931a8530") ?? ' Не показано строк: ')+diff.omitted+'.':''}${diff.trimmed?(globalThis.HubI18n?.t?.("knowledge.0daa819a26c8") ?? ' Длинные строки сокращены.'):''}</p>`):'')}) : `<section class="k-diff"><h4>Изменённый фрагмент: версия ${comparison.revision} → сохранённая текущая статья</h4>
      <p>${comparison.html?(globalThis.HubI18n?.t?.("knowledge.fe7436fc4c35") ?? 'Сравниваются пути, хеши и размеры файлов комплекта HTML. '):''}Общие начало и конец опущены. Несохранённый черновик исключён из сравнения.</p>
      ${diff.unchanged?`<p role="status">${comparison.html?(globalThis.HubI18n?.t?.("knowledge.b38e5d504a3a") ?? 'Изменений комплекта HTML нет.'):(globalThis.HubI18n?.t?.("knowledge.0f8b9405fb4c") ?? 'Изменений текста нет.')}</p>`:(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.ef5d6a7314f0",{v0:(diff.oldTotal),v1:(diff.newTotal),v2:(diff.removed.map(row=>`<span class="k-diff-removed">− ${row.line}: ${esc(row.text)}</span>`).join('')||(globalThis.HubI18n?.t?.("knowledge.327245a6954f") ?? '<span>Удалённых строк нет.</span>')),v3:(diff.added.map(row=>`<span class="k-diff-added">+ ${row.line}: ${esc(row.text)}</span>`).join('')||(globalThis.HubI18n?.t?.("knowledge.a1ba7ce4d3e9") ?? '<span>Добавленных строк нет.</span>'))}) : `<p>Строк в прежнем фрагменте: ${diff.oldTotal}; в текущем: ${diff.newTotal}.</p><div class="k-diff-columns"><section><h5>Прежняя версия</h5><pre>${diff.removed.map(row=>`<span class="k-diff-removed">− ${row.line}: ${esc(row.text)}</span>`).join('')||(globalThis.HubI18n?.t?.("knowledge.327245a6954f") ?? '<span>Удалённых строк нет.</span>')}</pre></section><section><h5>Текущая сохранённая</h5><pre>${diff.added.map(row=>`<span class="k-diff-added">+ ${row.line}: ${esc(row.text)}</span>`).join('')||(globalThis.HubI18n?.t?.("knowledge.a1ba7ce4d3e9") ?? '<span>Добавленных строк нет.</span>')}</pre></section></div>`)}
      ${diff.omitted||diff.trimmed?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.2177df655ea8",{v0:(diff.omitted?(globalThis.HubI18n?.t?.("knowledge.643a931a8530") ?? ' Не показано строк: ')+diff.omitted+'.':''),v1:(diff.trimmed?(globalThis.HubI18n?.t?.("knowledge.0daa819a26c8") ?? ' Длинные строки сокращены.'):'')}) : `<p class="k-warning">Сравнение ограничено 200 строками каждой версии и 500 символами строки.${diff.omitted?(globalThis.HubI18n?.t?.("knowledge.643a931a8530") ?? ' Не показано строк: ')+diff.omitted+'.':''}${diff.trimmed?(globalThis.HubI18n?.t?.("knowledge.0daa819a26c8") ?? ' Длинные строки сокращены.'):''}</p>`):''}</section>`);
  }
  function fullGraphModel(v) {
    if(v.researchCanvas){return window.ArchitectureMap?window.ArchitectureMap.model(v,v.researchCanvas):v.researchCanvas;}
    const original=baseGraphModel(v),scenario=v.drafts.get(v.selected)?.item.kind==='view',hidden=new Set(scenario?[]:v.filters.hiddenTypes||[]),hiddenEdges=new Set(scenario?[]:v.filters.hiddenRelations||[]),direction=scenario?'all':v.filters.edgeDirection||'all',anchor=v.filters.edgeAnchor||v.selected,visibleEdge=e=>!hiddenEdges.has(e.type)&&(direction==='all'||direction==='incoming'&&e.to===anchor||direction==='outgoing'&&e.from===anchor),base={nodes:original.nodes.filter(n=>!hidden.has(n.type)),relations:original.relations.filter(visibleEdge)},model=window.ArchitectureMap?window.ArchitectureMap.model(v,base):base;
    // Compound frames already encode ownership. Drawing the same contains fact
    // again creates duplicate frame-to-child links without adding information.
    const ancestor=(a,b)=>{const seen=new Set();while(model.parents?.has(b)&&!seen.has(b)){seen.add(b);b=model.parents.get(b);if(a===b)return true;}return false;};
    const frames=new Set(model.parents?.values()||[]),nodes=model.nodes.filter(n=>!hidden.has(n.type)||frames.has(n.id)),ids=new Set(nodes.map(n=>n.id));
    return {...model,nodes,relations:model.relations.filter(e=>ids.has(e.from)&&ids.has(e.to)&&visibleEdge(e)&&(e.type!=='contains'||!ancestor(e.from,e.to)))};
  }
  function graphModel(v){const model=fullGraphModel(v);return window.ArchitectureMap?.project?window.ArchitectureMap.project(v,model):model;}
  function revealScope(v){
    const item=v.drafts.get(v.selected)?.item,components=new Map((v.componentItems||[]).map(n=>[n.id,n])),seen=new Set();
    v.filters.treeFolders={...v.filters.treeFolders};v.filters.fileFolders={...v.filters.fileFolders};
    let current=item?.type==='component'?components.get(item.parent):components.get(item?.component)||components.get('component:'+item?.component);
    let root=current;
    while(current&&!seen.has(current.id)){seen.add(current.id);v.filters.treeFolders[current.id]=true;root=current;current=components.get(current.parent);}
    if(root&&item?.kind==='view')v.filters.treeFolders['scenarios:'+root.id]=true;
    if(root&&item?.entrypoint)v.filters.treeFolders['entries:'+root.id]=true;
    const path=String(item?.source?.path||'').replace(/\\/g,'/').split('/').filter(Boolean);let prefix='';
    for(const part of path){prefix=prefix?prefix+'/'+part:part;v.filters.fileFolders[prefix]=true;}
  }
  function canvasMatches(v,nodes=graphModel(v).nodes){const query=String(v.filters.canvasQuery||'').trim().toLocaleLowerCase();return nodes.filter(n=>!query||[n.title,n.id,n.source?.path].some(value=>String(value||'').toLocaleLowerCase().includes(query)));}
  function applyCanvasSearch(v,cy){if(!cy||cy.destroyed())return;const matches=new Set(canvasMatches(v).map(n=>n.id)),query=String(v.filters.canvasQuery||'').trim();cy.nodes().forEach?.(n=>n.toggleClass?.('k-find-match',!!query&&matches.has(n.id())));}
  function participants(v,model=graphModel(v)){return window.ArchitectureMap?.fileTree(v,canvasMatches(v,model.nodes),{reveal:!!String(v.filters.canvasQuery||'').trim()})||'';}
  function analysisStatus(v){return `<span>${esc(v.analysisNotice||(globalThis.HubI18n?.t?.("knowledge.2a9e8f177200") ?? 'Версия знаний: ')+(v.context?.revision??'…'))}</span>${jobNotice(v)}`;}
  function updateAnalysisStatus(v){
    if(!active(v)||v.snapshotOwner)return;
    const status=mounted.root.querySelector('[data-k-analysis-status]');if(status)status.innerHTML=analysisStatus(v);
    const scanning=(v.context?.jobs||[]).some(j=>['queued','running'].includes(j.state));
    for(const button of mounted.root.querySelectorAll('[data-k-action="scan"]'))button.disabled=scanning||v.busy;
  }
  function navigatorStamp(v){
    const f=v.filters,r=v.research;
    return {locale:window.HubI18n?.locale,items:v.catalogTreeItems,components:v.componentItems,entries:v.entryItems,maps:v.scenarios,
      token:JSON.stringify([v.mode,r?.tab,f.browser,v.context?.revision,f.query,f.listCollapsed,f.followSelection,f.fileTreeExpanded,f.fileTreeCollapsed,f.fileFolders,f.treeExpanded,f.treeFolders,f.discoveryScope,v.catalogTreeLoading,r?.mapLimit,r?.entryLimit,[...r?.treeLimits||[]],r?.tab==='canvas'?graphKey(v):''])};
  }
  function rememberNavigator(v){v.navigatorStamp=navigatorStamp(v);}
  function scheduleNavigatorPersist(v){
    clearTimeout(v.navigatorPersistTimer);
    v.navigatorPersistTimer=setTimeout(()=>{v.navigatorPersistTimer=null;rememberNavigator(v);persist(v);},120);
  }
  function unchangedNavigator(v){const a=v.navigatorStamp,b=navigatorStamp(v);return a&&Object.keys(b).every(key=>a[key]===b[key]);}
  function renderNavigator(v){
    if(!active(v))return;
    const old=mounted.root.querySelector('.k-catalog'),focused=document.activeElement,editing=old?.contains?.(focused)&&focused?.dataset?.kFilter==='query',start=focused?.selectionStart,end=focused?.selectionEnd;
    if(old)old.outerHTML=catalog(v);
    restoreNavigatorScroll(v,mounted.root);followNavigator(v);rememberNavigator(v);
    if(editing){const input=mounted.root.querySelector('[data-k-filter="query"]');input?.focus({preventScroll:true});if(typeof start==='number')input?.setSelectionRange?.(start,end);}
  }
  function architectureContext(v,navigator=false){
    const item=v.drafts.get(v.selected)?.item,isComponent=item?.type==='component',scenario=item?.kind==='view',canInherit=['class','interface','record','enum','external'].includes(item?.type),pair=v.filters.graphMode==='neighborhood'&&v.filters.focusTarget,title=pair?(globalThis.HubI18n?.t?.("knowledge.81397fca9c28") ?? 'Зависимости: ')+(item?.title||v.selected)+' → '+(v.componentItems?.find(n=>n.id===v.filters.focusTarget)?.title||v.filters.focusTarget):item?.title;
    if(!navigator)return `<div class="k-scope-controls"><strong>${esc(title||(globalThis.HubI18n?.t?.("knowledge.300e04b815b8") ?? 'Подсистемы проекта'))}</strong>${scenario||pair||v.selected&&(!isComponent||v.filters.componentContext==='code')?'':(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.2d13aa62f660",{v0:([['map',(globalThis.HubI18n?.t?.("knowledge.2751c9100018") ?? 'Карта')],['matrix',(globalThis.HubI18n?.t?.("knowledge.fd5f99d60d33") ?? 'Матрица')]].map(([id,title])=>`<button data-k-presentation="${id}" aria-pressed="${v.filters.presentation===id}">${title}</button>`).join(''))}) : `<div role="group" aria-label="Отображение тех же фактов">${[['map',(globalThis.HubI18n?.t?.("knowledge.2751c9100018") ?? 'Карта')],['matrix',(globalThis.HubI18n?.t?.("knowledge.fd5f99d60d33") ?? 'Матрица')]].map(([id,title])=>`<button data-k-presentation="${id}" aria-pressed="${v.filters.presentation===id}">${title}</button>`).join('')}</div>`)}</div>`;
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.c938986dac19",{v0:(esc(title||(globalThis.HubI18n?.t?.("knowledge.7641ad9bafb2") ?? 'Обзор проекта'))),v1:(isComponent?[['subsystems',(globalThis.HubI18n?.t?.("knowledge.77091052e9ae") ?? 'Подсистемы')],['code',(globalThis.HubI18n?.t?.("knowledge.1b3a63b288a4") ?? 'Код')]].map(([id,title])=>`<button data-k-component-context="${id}" aria-pressed="${v.filters.componentContext===id}">${title}</button>`).join(''):scenario?(globalThis.HubI18n?.t?.("knowledge.55dd51a0372b") ?? '<span>Авторский сценарий · только сохранённые участники и связи</span>'):v.selected?(canInherit?[['neighborhood',(globalThis.HubI18n?.t?.("knowledge.7840c9a54c7b") ?? 'Связи')],['inheritance',(globalThis.HubI18n?.t?.("knowledge.2167fe553fee") ?? 'Наследование')]]:[['neighborhood',(globalThis.HubI18n?.t?.("knowledge.7840c9a54c7b") ?? 'Связи')]]).map(([id,title])=>`<button data-k-projection="${id}" aria-pressed="${v.filters.graphMode===id}">${title}</button>`).join(''):''),v2:(isComponent&&v.filters.componentContext==='code'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.be8cdd9f4c82",{v0:(v.filters.includeSubsystems?' checked':'')}) : `<label><input type="checkbox" data-k-include-subsystems${v.filters.includeSubsystems?' checked':''}>Включить код подсистем</label>`):'')}) : `<div class="k-scope-controls"><strong>${esc(title||(globalThis.HubI18n?.t?.("knowledge.7641ad9bafb2") ?? 'Обзор проекта'))}</strong><div role="group" aria-label="Содержимое выбранного раздела">${isComponent?[['subsystems',(globalThis.HubI18n?.t?.("knowledge.77091052e9ae") ?? 'Подсистемы')],['code',(globalThis.HubI18n?.t?.("knowledge.1b3a63b288a4") ?? 'Код')]].map(([id,title])=>`<button data-k-component-context="${id}" aria-pressed="${v.filters.componentContext===id}">${title}</button>`).join(''):scenario?(globalThis.HubI18n?.t?.("knowledge.55dd51a0372b") ?? '<span>Авторский сценарий · только сохранённые участники и связи</span>'):v.selected?(canInherit?[['neighborhood',(globalThis.HubI18n?.t?.("knowledge.7840c9a54c7b") ?? 'Связи')],['inheritance',(globalThis.HubI18n?.t?.("knowledge.2167fe553fee") ?? 'Наследование')]]:[['neighborhood',(globalThis.HubI18n?.t?.("knowledge.7840c9a54c7b") ?? 'Связи')]]).map(([id,title])=>`<button data-k-projection="${id}" aria-pressed="${v.filters.graphMode===id}">${title}</button>`).join(''):''}</div>${isComponent&&v.filters.componentContext==='code'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.be8cdd9f4c82",{v0:(v.filters.includeSubsystems?' checked':'')}) : `<label><input type="checkbox" data-k-include-subsystems${v.filters.includeSubsystems?' checked':''}>Включить код подсистем</label>`):''}</div>`);
  }
  function followNavigator(v){
    if(!active(v)||v.snapshotOwner||v.mode!=='architecture'||v.revealingNavigator)return;
    const following=v.filters.followSelection!==false&&v.canvasItem&&v.canvasSelection?.length===1&&v.canvasInspect?.type!=='group';
    if(following){
      let changed=false;
      if(v.filters.browser==='catalog'){
        const path=v.canvasInspect?.source?.path?.replace(/\\/g,'/');
        if(path){v.filters.fileFolders||={};const parts=path.split('/');for(let i=1;i<=parts.length;i++){const folder=parts.slice(0,i).join('/');if(v.filters.fileFolders[folder]!==true){v.filters.fileFolders[folder]=true;changed=true;}}}
      }else if(v.filters.browser==='structure'){
        const byId=new Map((v.componentItems||[]).map(n=>[n.id,n])),seen=new Set();let n=byId.get(v.canvasItem);v.filters.treeFolders||={};
        while(n&&!seen.has(n.id)){seen.add(n.id);if(v.filters.treeFolders[n.id]!==true){v.filters.treeFolders[n.id]=true;changed=true;}n=byId.get(n.parent);}
      }
      if(changed){
        const pane=mounted.root.querySelector('.k-catalog');
        const revealed=v.filters.browser==='catalog'&&window.ArchitectureMap?.revealFile?.(v,pane,v.canvasInspect?.source?.path);
        if(!revealed){v.revealingNavigator=true;try{renderNavigator(v);}finally{v.revealingNavigator=false;}}
        rememberNavigator(v);persist(v);
      }
    }
    for(const pane of [mounted.root.querySelector('.k-catalog'),mounted.root.querySelector('[data-k-participants]')]){
    const mode=pane?.dataset?.kBrowserMode||v.filters.browser;if(!pane?.querySelectorAll||!['catalog','graph','structure'].includes(mode)||v.research?.tab==='maps'&&pane.matches?.('.k-catalog'))continue;
    const rows=[...pane.querySelectorAll('[data-k-select],[data-r-open]')],idOf=row=>row.dataset.kSelect??row.dataset.rOpen;
    // LSP symbols may have a different ID from the shallow scanner's symbol.
    // Prefer an exact identity, then the same declaration, then its source file.
    const path=v.canvasInspect?.source?.path?.replace(/\\/g,'/'),items=v.catalogTreeItems||[];
    const related=items.filter(n=>path&&n.source?.path?.replace(/\\/g,'/')===path);
    const fallback=related.find(n=>n.type===v.canvasInspect?.type&&n.title===v.canvasInspect?.title)||related.find(n=>n.type==='file');
    const row=rows.find(row=>idOf(row)===(v.canvasItem||v.selected))||(['catalog','graph'].includes(mode)&&fallback?rows.find(row=>idOf(row)===fallback.id):null);
    for(const entry of rows){const selected=entry===row;entry.classList.toggle('selected',selected);if(entry.dataset.rOpen!==undefined){if(selected)entry.setAttribute('aria-current','page');else entry.removeAttribute('aria-current');}}
    if(!following||(mode==='catalog'&&!path))continue;
    const status=pane.querySelector('[data-k-follow-status]');
    if(status)status.textContent=row?'':mode==='structure'?(globalThis.HubI18n?.t?.("knowledge.c574eab0ea66") ?? 'Выбранная подсистема отсутствует в дереве архитектуры.'):(globalThis.HubI18n?.t?.("knowledge.cde256fd0d5f") ?? 'Выбранный элемент отсутствует в текущем списке исходников.');
    if(!row)continue;
    for(let parent=row.parentElement;parent&&parent!==pane;parent=parent.parentElement)if(parent.tagName==='DETAILS'){parent.open=true;const folder=parent.dataset.kFileFolder;if(folder){v.filters.fileFolders||={};v.filters.fileFolders[folder]=true;}}
    const scroller=pane.querySelector('.r-tree')||pane,b=row.getBoundingClientRect(),p=scroller.getBoundingClientRect();
    if(b.top<p.top)scroller.scrollTop-=p.top-b.top;else if(b.bottom>p.bottom)scroller.scrollTop+=b.bottom-p.bottom;
    captureNavigatorScroll(v,mounted.root);
    }
  }
  function baseGraphModel(v) {
    if(v.scopedCode)return v.scopedCode;
    let nodes=filtered(v), relations=v.relations.filter(r=>!r.removed);
    if(['components','matrix'].includes(v.filters.graphMode)) {
      nodes=componentLevel(v);const ids=new Set(nodes.map(node=>node.id));
      return {nodes,relations:relations.filter(edge=>edge.type==='depends-on'&&ids.has(edge.from)&&ids.has(edge.to))};
    }
    const item=v.drafts.get(v.selected)?.item;
    if(v.filters.graphMode==='neighborhood'&&item?.type==='component'&&v.filters.focusTarget){
      const ids=new Set([v.selected,v.filters.focusTarget]);
      return {nodes:[...new Map([item,...(v.neighbors||[]),...(v.componentItems||[])].map(n=>[n.id,n])).values()].filter(n=>ids.has(n.id)),relations:relations.filter(e=>e.from===v.selected&&e.to===v.filters.focusTarget&&e.type==='depends-on')};
    }

    if(v.filters.graphMode==='neighborhood'&&['class','interface','record','enum'].includes(item?.type))
      relations=relations.filter(r=>r.type!=='contains');
    if(v.filters.graphMode==='neighborhood'&&item?.type==='component')
      relations=relations.filter(r=>r.type==='depends-on');
    if (item?.kind==='view'&&!['components','matrix','inheritance'].includes(v.filters.graphMode)) {
      nodes=v.neighbors||[];
      const order=new Map((item.orderedEdges||[]).map((id,index)=>[id,index]));
      relations=relations.filter(r=>order.has(r.id)).sort((a,b)=>order.get(a.id)-order.get(b.id));
      const ids=new Set(nodes.map(x=>x.id));
      return {nodes,relations:relations.filter(r=>ids.has(r.from)&&ids.has(r.to))};
    }
    if (v.filters.graphMode==='overview') {
      const coarse=nodes.filter(node=>node.type==='component'||node.entrypoint||node.id===v.selected);
      if(item?.kind==='entity'&&!coarse.some(node=>node.id===item.id))coarse.push(item);
      if(coarse.length)nodes=coarse;
      // With no configured/discovered components or entry points, keep a
      // bounded first page visible rather than inventing overview nodes.
    }
    if (v.selected && v.filters.graphMode!=='overview') {
      const ids=new Set([v.selected,...relations.flatMap(r=>[r.from,r.to])]);
      nodes=[...new Map([...nodes,...(v.neighbors||[]),...(v.drafts.get(v.selected)?[v.drafts.get(v.selected).item]:[])].map(x=>[x.id,x])).values()].filter(x=>x.kind==='entity'&&ids.has(x.id));
    }
    if (v.filters.graphMode==='inheritance') {
      relations=relations.filter(r=>['extends','implements','inherits','inheritance'].includes(r.type));
      const ids=new Set(relations.flatMap(r=>[r.from,r.to])); nodes=nodes.filter(x=>ids.has(x.id)||x.id===v.selected);
    }
    const ids=new Set(nodes.map(x=>x.id));
    return {nodes,relations:relations.filter(r=>ids.has(r.from)&&ids.has(r.to))};
  }
  function wrapLabel(text,max){
    const rows=[];
    for(const word of String(text).trim().split(/\s+/u).filter(Boolean)){
      if(word.length>max){for(let i=0;i<word.length;i+=max)rows.push(word.slice(i,i+max));continue;}
      const previous=rows.at(-1);if(previous&&previous.length+1+word.length<=max)rows[rows.length-1]=previous+' '+word;else rows.push(word);
    }
    return rows.length?rows:[''];
  }
  function nodeLabel(node) {
    const full=String(node.title||node.source?.path||node.id);
    const name=node.type==='file'?String(node.source?.path||full).split(/[\\/]/).pop():full;
    return {title:name,rows:wrapLabel(name,25),full:[full,node.source?.path].filter(Boolean).filter((x,i,a)=>a.indexOf(x)===i).join(' · ')};
  }
  function metadataImage(rows,width,height){
    if(!rows.length)return '';
    const safe=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
    const y=height-18;
    const text=rows.map((row,index)=>`<text x="${width/2}" y="${y+index*12}" text-anchor="middle" font-family="Arial" font-size="${row.size||10}" fill="${row.color||'#b8c4d2'}">${safe(row.text||row)}</text>`).join('');
    return `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${text}</svg>`)}`;
  }
  const nodeTypes={component:(globalThis.HubI18n?.t?.("knowledge.626cda060f0c") ?? 'Компонент'),class:(globalThis.HubI18n?.t?.("knowledge.1711aecef486") ?? 'Класс'),record:'Record',enum:'Enum',interface:(globalThis.HubI18n?.t?.("knowledge.517c6d91fcdb") ?? 'Интерфейс'),file:(globalThis.HubI18n?.t?.("knowledge.59dbfe54b48f") ?? 'Файл / модуль'),external:(globalThis.HubI18n?.t?.("knowledge.acba5467afc6") ?? 'Внешний тип'),method:(globalThis.HubI18n?.t?.("knowledge.5fcca1576ab8") ?? 'Метод'),function:(globalThis.HubI18n?.t?.("knowledge.859538119171") ?? 'Функция'),field:(globalThis.HubI18n?.t?.("knowledge.f1707b7e1d2b") ?? 'Поле'),property:(globalThis.HubI18n?.t?.("knowledge.80a7359dec79") ?? 'Свойство'),variable:(globalThis.HubI18n?.t?.("knowledge.c89453017f3e") ?? 'Переменная'),symbol:(globalThis.HubI18n?.t?.("knowledge.bbfa955ec6bd") ?? 'Символ'),module:(globalThis.HubI18n?.t?.("knowledge.730c934a0cfd") ?? 'Модуль'),namespace:(globalThis.HubI18n?.t?.("knowledge.5e0d0bcd16a7") ?? 'Пространство имён')};
  const nodeColors={class:{fill:'#284b70',border:'#80b9ea'},interface:{fill:'#246353',border:'#79d6b4'},enum:{fill:'#80552a',border:'#e8b668'},record:{fill:'#5c427f',border:'#c5a2eb'},component:{fill:'#683f68',border:'#d29bcf'},file:{fill:'#3d6470',border:'#95c5cf'},external:{fill:'#753f4b',border:'#db96a7'},method:{fill:'#345978',border:'#90c4ec'},function:{fill:'#345978',border:'#90c4ec'},field:{fill:'#556246',border:'#bbce92'},property:{fill:'#556246',border:'#bbce92'},variable:{fill:'#556246',border:'#bbce92'},symbol:{fill:'#525c69',border:'#b4bfce'},module:{fill:'#3d6470',border:'#95c5cf'},namespace:{fill:'#683f68',border:'#d29bcf'}};
  const edgeTypes={extends:(globalThis.HubI18n?.t?.("knowledge.07eff7a5fe5a") ?? 'наследует'),implements:(globalThis.HubI18n?.t?.("knowledge.b01b27086c3f") ?? 'реализует'),inherits:(globalThis.HubI18n?.t?.("knowledge.07eff7a5fe5a") ?? 'наследует'),inheritance:(globalThis.HubI18n?.t?.("knowledge.07eff7a5fe5a") ?? 'наследует'),uses:(globalThis.HubI18n?.t?.("knowledge.59b57383b7a6") ?? 'использует'),imports:(globalThis.HubI18n?.t?.("knowledge.6f8b2ff0c656") ?? 'импортирует'),contains:(globalThis.HubI18n?.t?.("knowledge.63e6e06421c4") ?? 'содержит'),'depends-on':(globalThis.HubI18n?.t?.("knowledge.1e6a94ec5b45") ?? 'зависит'),'via-files':(globalThis.HubI18n?.t?.("knowledge.076e6114c122") ?? 'цепочка через файлы'),starts:(globalThis.HubI18n?.t?.("knowledge.626701c599c3") ?? 'запускает'),initializes:(globalThis.HubI18n?.t?.("knowledge.dd2284e8a057") ?? 'инициализирует'),reads:(globalThis.HubI18n?.t?.("knowledge.db207c22cbe2") ?? 'читает'),calls:(globalThis.HubI18n?.t?.("knowledge.c63642bdab51") ?? 'вызывает')};
  function edgeRoute() {return 'round-taxi';}
  function edgeRoutingStyle() {
    return {'source-endpoint':'outside-to-node','target-endpoint':'outside-to-node','edge-distances':'intersection',
      'curve-style':'round-taxi','taxi-direction':'auto','taxi-turn':'50%','taxi-turn-min-distance':30,'taxi-radius':16};
  }
  async function loadCatalogTree(v) {
    const identityOf=()=>JSON.stringify([v.context?.revision,v.filters.query,v.filters.discoveryScope==='subsystem'?(v.drafts.get(v.selected)?.item.type==='component'?v.selected:v.drafts.get(v.selected)?.item.component||''):'']);
    const identity=identityOf(),[revision,query,scope]=JSON.parse(identity);
    if(v.catalogTreeKey===identity)return;
    v.catalogTreeRequests||=new Map();
    if(v.catalogTreeRequests.has(identity))return v.catalogTreeRequests.get(identity);
    v.catalogTreeLoading=true;v.catalogTreeLoadingKey=identity;
    const loading=(async()=>{
      const items=[];let page,offset=0;
      do{
        page=await request(v,'source-tree',{limit:5000,offset,query,...(scope?{component:scope}:{})});
        if(!active(v)||identity!==identityOf())return;
        if(page.revision!==revision)throw Error((globalThis.HubI18n?.t?.("knowledge.907677552b02") ?? 'Исходники обновились во время загрузки дерева. Обновите раздел.'));
        items.push(...page.items);offset=page.next;
      }while(page.more&&offset!=null);
      v.catalogTreeItems=items;v.catalogTreeKey=identity;
    })();
    v.catalogTreeRequests.set(identity,loading);
    try{return await loading;}finally{v.catalogTreeRequests.delete(identity);if(v.catalogTreeLoadingKey===identity)v.catalogTreeLoading=false;}
  }
  function applyEdgeRouting(v,cy) {
    if(!cy||cy.destroyed())return;
    cy.batch(()=>{for(const [property,value] of Object.entries(edgeRoutingStyle(v)))cy.edges().style(property,value);});
    window.ArchitectureMap?.routeEdges(cy,edgeRoute(v));
    cy.knowledgeSpecial?.render?.();
  }
  function graphKey(v) {const model=graphModel(v);return JSON.stringify([ROUTING_VERSION,v.context?.revision,v.filters.graphMode,v.selected,v.filters.componentContext,!!v.filters.includeSubsystems,model.nodes.map(n=>JSON.stringify([n.id,model.parents?.get(n.id)||'',nodeLabel(n).full])).sort(),model.relations.map(r=>JSON.stringify([r.id,r.from,r.to,r.type])).sort()]);}
  function hasDirectedCycle(model) {
    const incoming=new Map(model.nodes.map(node=>[node.id,0])),outgoing=new Map(model.nodes.map(node=>[node.id,[]]));
    for(const edge of model.relations){if(!incoming.has(edge.from)||!incoming.has(edge.to))continue;incoming.set(edge.to,incoming.get(edge.to)+1);outgoing.get(edge.from).push(edge.to);}
    const queue=[...incoming].filter(([,degree])=>degree===0).map(([id])=>id);let count=0;
    for(let i=0;i<queue.length;i++){count++;for(const target of outgoing.get(queue[i])){incoming.set(target,incoming.get(target)-1);if(incoming.get(target)===0)queue.push(target);}}
    return count<model.nodes.length;
  }
  function cyElements(v) {
    const model=graphModel(v),names=new Map(model.nodes.map(node=>[node.id,nodeLabel(node).full]));
    const scenario=!['components','matrix','inheritance'].includes(v.filters.graphMode)&&v.drafts.get(v.selected)?.item.kind==='view'&&model.nodes.length<=12;
    const labelCache=v.__labelMeasureCache||=new Map();let measureContext=v.__labelMeasureContext;
    if(!measureContext){try{const canvas=document.createElement?.('canvas');measureContext=canvas?.getContext?.('2d')||null;}catch(_){measureContext=null;}v.__labelMeasureContext=measureContext;}
    const measuredWidth=(text,font)=>{const key=font+'|'+text;if(labelCache.has(key))return labelCache.get(key);let width=text.length*font*.58;if(measureContext){measureContext.font=font+'px Arial';width=measureContext.measureText(text).width;}labelCache.set(key,width);if(labelCache.size>8000)labelCache.delete(labelCache.keys().next().value);return width;};
    const wrapMeasured=(text,maxWidth,font)=>{const words=String(text).trim().split(/\s+/u).filter(Boolean),rows=[];for(const word of words){let parts=[word];if(measuredWidth(word,font)>maxWidth){parts=[];let part='';for(const char of word){if(part&&measuredWidth(part+char,font)>maxWidth){parts.push(part);part='';}part+=char;}if(part)parts.push(part);}for(const part of parts){const previous=rows.at(-1);if(previous&&measuredWidth(previous+' '+part,font)<=maxWidth)rows[rows.length-1]=previous+' '+part;else rows.push(part);}}return rows.length?rows:[''];};
    return [...model.nodes.map(node=>{const name=nodeLabel(node),width=scenario?125:node.type==='component'?160:195,font=scenario?13:node.type==='component'?14:12,title=wrapMeasured(name.title,Math.max(90,width-24),font),
      component=(v.context?.policy?.components||[]).find(component=>component.id===node.component),leaf=String(component?.title||node.component||''),limit=scenario?16:24,
      compactComponent=leaf.length>limit?leaf.slice(0,limit)+'…':leaf,
      subtitleRows=[{text:(node.mapGroup?(globalThis.HubI18n?.t?.("knowledge.41f780fdee89") ?? 'Категория'):nodeTypes[node.type]||node.type||node.kind)+(node.collapsed?' · '+node.memberCount+(globalThis.HubI18n?.t?.("knowledge.66093b0d8d76") ?? ' внутри'):'')+(node.entrypoint?(globalThis.HubI18n?.t?.("knowledge.c4e344b6fb32") ?? ' · вход'):''),size:10,color:'#b8c4d2'},...(compactComponent?[{text:compactComponent,size:9,color:'#91a0b2'}]:[])];
      const compact=node.type==='component',lineHeight=scenario?18:compact?16:18,metaHeight=scenario?12:compact?10:12,padding=scenario?24:compact?18:24;
      const height=Math.max(scenario?68:compact?54:72,(title.length*lineHeight+subtitleRows.length*metaHeight)+padding),metadata=metadataImage(subtitleRows,width,height);
      return {group:'nodes',data:{id:node.id,label:title.join('\n'),metadataImage:metadata,full:name.full,type:node.type||'other',...(model.parents?.has(node.id)?{parent:model.parents.get(node.id)}:{}),width,font,
      height,active:node.id===v.selected?1:0},classes:[node.id===v.selected?'active':'',[...v.research?.running?.values()||[]].some(j=>j.id===node.id&&j.epoch===v.research.epoch)?'k-researching':''].filter(Boolean).join(' ')};}),
      ...model.relations.map(relation=>({group:'edges',data:{id:relation.id,source:relation.from,target:relation.to,
        label:(edgeTypes[relation.type]||relation.type)+(Number.isFinite(relation.count)?' · '+relation.count:''),countLabel:Number.isFinite(relation.count)?String(relation.count):'',type:relation.type,provenance:relation.provenance||'unknown',
        full:[names.get(relation.from),edgeTypes[relation.type]||relation.type,names.get(relation.to),Number.isFinite(relation.count)?relation.count+(globalThis.HubI18n?.t?.("knowledge.762c7823d566") ?? ' статических связей'):'',relation.provenance||(globalThis.HubI18n?.t?.("knowledge.c21b646d2d82") ?? 'происхождение не указано'),
        (relation.evidence||[]).map(e=>e.path+':'+(e.line||1)).join(', ')].join(' · ')},classes:relation.id===v.filters.focusRelation?'active':''}))];
  }
  function cyLayout(v,fallback=false) {
    const model=graphModel(v),authored=!['components','matrix','inheritance'].includes(v.filters.graphMode)&&v.drafts.get(v.selected)?.item.kind==='view',scenario=authored&&model.nodes.length<=12;
    const compound=!!model.parents?.size;
    if(!fallback&&typeof window.ELK==='function'&&window.ArchitectureMap?.elkLayout)return {name:'elk'};
    if(compound&&typeof window.cytoscapeFcose==='function')return {name:'fcose',quality:'proof',fit:false,animate:false,randomize:false,packComponents:false,tile:true,numIter:1200,nodeRepulsion:()=>8000,idealEdgeLength:()=>130,nodeDimensionsIncludeLabels:true,tilingPaddingVertical:36,tilingPaddingHorizontal:36,tilingCompareBy:(a,b)=>String(a).localeCompare(String(b))};
    if(!model.relations.length)return {name:'grid',fit:false,animate:false,avoidOverlap:true,spacingFactor:1.15,nodeDimensionsIncludeLabels:true};
    const degrees=new Map(model.nodes.map(node=>[node.id,0]));for(const edge of model.relations){degrees.set(edge.from,(degrees.get(edge.from)||0)+1);degrees.set(edge.to,(degrees.get(edge.to)||0)+1);}
    const force=v.filters.layout==='cose'||(v.filters.layout!=='breadthfirst'&&!authored&&v.filters.graphMode!=='inheritance'&&(hasDirectedCycle(model)||[...degrees.values()].some(degree=>degree>8)));
    if(force&&typeof window.cytoscapeFcose==='function')return {name:'fcose',quality:'proof',fit:false,animate:false,randomize:false,packComponents:false,tile:true,numIter:1200,nodeRepulsion:()=>8000,idealEdgeLength:()=>130,nodeDimensionsIncludeLabels:true,tilingPaddingVertical:36,tilingPaddingHorizontal:36,tilingCompareBy:(a,b)=>String(a).localeCompare(String(b))};
    return force?{name:'cose',fit:false,animate:false,randomize:false,numIter:400,nodeRepulsion:()=>6000,idealEdgeLength:()=>100,nodeDimensionsIncludeLabels:true}:
      {name:'breadthfirst',directed:true,fit:false,animate:false,avoidOverlap:true,spacingFactor:1.6,padding:30,
        nodeDimensionsIncludeLabels:true,...(scenario?{transform:(_node,position)=>({x:position.y,y:position.x})}:{})};
  }
  const cyStyle=[
    {selector:'node',style:{label:'data(label)','text-wrap':'wrap','text-max-width':180,'font-family':'Arial','font-size':'data(font)','text-valign':'center','text-halign':'center','text-margin-y':-8,
      'background-image':'data(metadataImage)','background-fit':'contain','background-clip':'node',color:'#e0e5ec','background-color':'#222a35','border-color':'#6ea6d8','border-width':1,shape:'round-rectangle',width:'data(width)',height:'data(height)',padding:8,'min-zoomed-font-size':8}},
    ...Object.entries(nodeColors).map(([type,color])=>({selector:`node[type="${type}"]`,style:{'background-color':color.fill,'border-color':color.border}})),
    {selector:'node[type="component"]',style:{'border-width':2,padding:4}},
    {selector:'node:parent',style:{label:'','background-image':'none','font-size':15,'background-color':'#30273c','background-opacity':.18,'border-color':'#7f7398','border-width':1,'border-style':'solid',padding:COMPOUND_INSET,'compound-sizing-wrt-labels':'exclude'}},
    {selector:'node[type="group"]',style:{'border-color':'#687887','border-style':'dashed','background-color':'#202932','background-opacity':.2}},
    {selector:'node[type="interface"]',style:{'border-style':'dashed'}},
    {selector:'node[type="external"]',style:{'border-style':'dotted'}},
    {selector:'node.k-find-match',style:{'border-color':'#42e3d1','background-blacken':-.15}},
    {selector:'node.active',style:{'border-width':3,'border-color':'#d7a756'}},
    {selector:'node.k-researching',style:{'overlay-color':'#69b8f1','overlay-opacity':.22,'overlay-padding':7,'border-style':'dashed'}},
    {selector:'edge',style:{label:'data(countLabel)','curve-style':'bezier','control-point-step-size':55,'target-arrow-shape':'triangle','line-color':'#6ea6d8','target-arrow-color':'#6ea6d8',
      width:1.5,'font-size':10,color:'#d4dce7','text-background-color':'#161c24','text-background-opacity':1,'text-background-padding':2,'text-rotation':'autorotate','min-zoomed-font-size':9}},
    {selector:'edge[provenance="authored"],edge[type="starts"],edge[type="initializes"],edge[type="reads"]',style:{'line-color':'#d7a756','target-arrow-color':'#d7a756'}},
    {selector:'edge[type="extends"],edge[type="implements"],edge[type="inherits"],edge[type="inheritance"]',style:{'line-color':'#5eb6a2','target-arrow-color':'#5eb6a2'}},
    {selector:'edge[type="contains"]',style:{'line-color':'#b49cde','target-arrow-color':'#b49cde'}},
    {selector:'edge[type="uses"],edge[type="depends-on"]',style:{'line-color':'#6ea6d8','target-arrow-color':'#6ea6d8'}},
    {selector:'edge[type="imports"]',style:{'line-color':'#ce8fb8','target-arrow-color':'#ce8fb8','line-style':'dotted','target-arrow-shape':'vee'}},
    {selector:'edge[type="implements"]',style:{'line-style':'dashed','target-arrow-shape':'triangle','target-arrow-fill':'hollow'}},
    {selector:'edge[type="extends"],edge[type="inherits"],edge[type="inheritance"]',style:{'target-arrow-shape':'triangle','target-arrow-fill':'hollow'}},
    {selector:'edge[provenance="authored"]',style:{'line-style':'dashed'}},
    {selector:'edge.active,edge:selected,edge.hover',style:{label:'data(label)',width:3,'font-size':13,'text-background-opacity':1}},
    {selector:'node:selected',style:{'border-color':'#f1c578','border-width':3}},
    {selector:'edge.viewport-motion',style:{visibility:'hidden'}},
    {selector:'core',style:{'selection-box-color':'#80bfff','selection-box-opacity':.16,'selection-box-border-color':'#80bfff','selection-box-border-width':1}}];
  function captureCamera(v, cy) {
    if(!cy||cy.destroyed())return;
    if(cy.knowledgePending||cy.knowledgeOwner!==undefined&&cy.knowledgeOwner!==v.selected)return;
    if(cy.nodes?.().length===0)return;
    const pan=cy.pan();v.viewport={x:pan.x,y:pan.y,scale:cy.zoom()};v.cameraInitialized=true;v.cameraKey=cy.knowledgeKey||v.cameraKey;
    updateGraphViewport(v);scheduleGraphOverlays(v,cy);clearTimeout(v.cameraPersistTimer);v.cameraPersistTimer=setTimeout(()=>persist(v),120);
  }
  function positionGroupLabels(cy){
    if(!cy?.nodes||cy.destroyed())return;
    cy.knowledgeLabels||=window.ArchitectureCanvas?.groupLabels(cy,mounted?.root.querySelector('[data-k-group-labels]'),esc);
    cy.knowledgeLabels?.render();
  }
  function scheduleGraphOverlays(v,cy,invalidate=false){
    if(invalidate)cy.knowledgeLabels?.invalidate();
    if(cy.knowledgeOverlayFrame)return;
    const callback=()=>{cy.knowledgeOverlayFrame=null;if(active(v)&&mounted.cy===cy&&!cy.destroyed()){positionGroupLabels(cy);positionNodeActions(v,cy);}};
    cy.knowledgeOverlayFrame=(window.requestAnimationFrame||((fn)=>setTimeout(fn,16)))(callback);
  }
  function flushGraphRoutes(v,cy,edges) {
    if(cy.knowledgeRouteFrame)(window.cancelAnimationFrame||clearTimeout)(cy.knowledgeRouteFrame);
    cy.knowledgeRouteFrame=null;
    const pending=cy.knowledgeRoutePending;cy.knowledgeRoutePending=null;
    if(active(v)&&mounted.cy===cy&&!cy.destroyed())window.ArchitectureMap?.routeEdges(cy,edgeRoute(v),pending?pending.union(edges||cy.collection()):edges||cy.collection());
  }
  function scheduleGraphRoutes(v,cy,node) {
    const edges=node.union(node.descendants()).connectedEdges();
    cy.knowledgeRoutePending=cy.knowledgeRoutePending?cy.knowledgeRoutePending.union(edges):edges;
    if(!cy.knowledgeRouteFrame)cy.knowledgeRouteFrame=(window.requestAnimationFrame||((fn)=>setTimeout(fn,16)))(()=>flushGraphRoutes(v,cy));
  }
  function canvasMotion(cy){
    if(!cy.knowledgeDense)return;
    if(!cy.knowledgeMotionTimer)cy.edges().addClass('viewport-motion');
    clearTimeout(cy.knowledgeMotionTimer);cy.knowledgeMotionTimer=setTimeout(()=>{cy.knowledgeMotionTimer=null;if(!cy.destroyed())cy.edges().removeClass('viewport-motion');},140);
  }
  function destroyGraph() {
    if(!mounted?.cy)return;
    const cy=mounted.cy;captureCamera(mounted.view,cy);persist(mounted.view);mounted.cyResize?.disconnect();
    mounted.cyGestures?.();mounted.cyGestures=null;cy.knowledgeSpecial?.();clearTimeout(cy.knowledgeMotionTimer);
    if(cy.knowledgeOverlayFrame)(window.cancelAnimationFrame||clearTimeout)(cy.knowledgeOverlayFrame);
    if(cy.knowledgeRouteFrame)(window.cancelAnimationFrame||clearTimeout)(cy.knowledgeRouteFrame);
    cy.destroy();mounted.cy=null;mounted.cyResize=null;
  }
  function savePositions(v,cy) {
    if(!cy?.nodes||cy.destroyed()||cy.knowledgePending)return;
    const positions=cy.nodes().map(node=>({id:node.id(),x:node.position('x'),y:node.position('y')})).filter(point=>Number.isFinite(point.x)&&Number.isFinite(point.y));
    v.positionCache.set(cy.knowledgeKey,positions);while(v.positionCache.size>8)v.positionCache.delete(v.positionCache.keys().next().value);
    v.routeCache||=new Map();if(cy.knowledgeRoutes)v.routeCache.set(cy.knowledgeKey,copy([...cy.knowledgeRoutes]));else v.routeCache.delete(cy.knowledgeKey);
    for(const id of v.routeCache.keys())if(!v.positionCache.has(id))v.routeCache.delete(id);
    persist(v);
  }
  function inspectorItem(v,item) {
    if(!item)return item;
    const draft=v.drafts.get(item.id);
    // Canvas nodes and navigator rows are projections. Authored fields come
    // from the same revisioned record, regardless of the selection surface.
    if(!draft||!draft.dirty&&draft.expected!==v.context?.revision)return item;
    const resolved={...item,...draft.item};
    for(const field of ['collapsed','memberCount'])if(Object.hasOwn(item,field))resolved[field]=item[field];
    return resolved;
  }
  async function readInspectorItem(v,item) {
    if(!item||item.type==='group'||item.provenance==='presentation')return item;
    const revision=v.context?.revision,draft=v.drafts.get(item.id);
    if(draft&&(draft.dirty||draft.expected===revision))return inspectorItem(v,item);
    v.inspectorRequests ||= new Map();
    const key=JSON.stringify([revision,item.id]);
    if(!v.inspectorRequests.has(key)){
      const pending=request(v,'research-object',{id:item.id}).then(record=>{
        if(active(v)&&v.context?.revision===revision&&!v.drafts.get(item.id)?.dirty)
          v.drafts.set(item.id,{item:record,expected:revision,dirty:false});
        return record;
      }).finally(()=>v.inspectorRequests.delete(key));
      v.inspectorRequests.set(key,pending);
    }
    await v.inspectorRequests.get(key);
    return inspectorItem(v,item);
  }
  function updateInspector(v) {
    if(!active(v))return;
    const panel=mounted.root.querySelector('.k-inspector-container'),selected=v.canvasInspect||v.drafts.get(v.selected)?.item;
    if(panel)panel.innerHTML=v.canvasStats?selectionInspector(v):selected?inspectorContent(v,selected,selected.id===v.selected?v.drafts.get(v.selected):null):!v.selected&&window.HubSubsystems?window.HubSubsystems.projectInspector(v,text=>markdown(v,{markdown:text})):emptyInspector();
    observeRoleDescription(v);
  }
  function updateCanvasSelection(v,cy,element) {
    if(!active(v)||mounted.cy!==cy)return;
    v.canvasSelection=cy.elements(':selected').map(element=>element.id());
    element||=cy.elements(':selected').last();
    const id=element?.length?element.id():'';
    const model=graphModel(v),item=inspectorItem(v,model.nodes.find(node=>node.id===id)||model.relations.find(edge=>edge.id===id));
    const stats=window.ArchitectureCanvas?.selectionStats(model,v.canvasSelection);
    v.canvasGroupStats=(element?.isParent?.()||item?.collapsed)&&v.canvasSelection.length===1&&item?.type==='component'?window.ArchitectureCanvas.selectionStats(fullGraphModel(v),[id]):null;
    v.canvasStats=stats&&(v.canvasSelection.length>1||element?.isParent?.()&&item?.type!=='component'&&item?.type!=='group')?stats:null;
    v.canvasItem=v.canvasSelection.length>1?'':id;v.canvasInspect=item||null;
    followNavigator(v);
    const status=mounted.root.querySelector('[data-k-canvas-selection]');
    if(status){status.hidden=!id&&!v.canvasStats;status.textContent=v.canvasStats?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.e10f9577fbb7",{v0:(stats.selectedCount),v1:(stats.nodeCount),v2:(stats.internalCount)}) : `Выбрано: ${stats.selectedCount} · участников: ${stats.nodeCount} · внутренних связей: ${stats.internalCount}`):item?.kind==='relation'||item?.from?cyElements(v).find(edge=>edge.data.id===id)?.data.full||(globalThis.HubI18n?.t?.("knowledge.a6d95dc59740") ?? 'Связь выбрана'):
      [item?.title,nodeTypes[item?.type]||item?.type,componentName(v,item?.component),String(item?.description||'').slice(0,140)].filter(Boolean).join(' · ');}
    positionNodeActions(v,cy);
    scheduleGraphOverlays(v,cy,true);
    if(!v.canvasStats&&element?.isNode?.()&&window.ArchitectureMap){
      const id=element.id(),revision=v.context?.revision;
      window.ArchitectureMap.availability(v,id,(action,args)=>request(v,action,args),graphModel(v)).then(available=>{
        if(!active(v)||mounted.cy!==cy||v.canvasItem!==id||v.context?.revision!==revision)return;
        v.canvasCapabilities={id,revision,available};positionNodeActions(v,cy);
      }).catch(error=>{if(active(v)&&mounted.cy===cy)mounted.options.showError?.((globalThis.HubI18n?.error?.(error) ?? error.message));});
    }
    if(inspectorVisible(v))updateInspector(v);
    if(!v.canvasStats&&element?.isNode?.()&&item&&item.type!=='group'){
      const revision=v.context?.revision;
      readInspectorItem(v,item).then(record=>{
        if(!active(v)||mounted.cy!==cy||v.canvasItem!==id||v.canvasStats||v.context?.revision!==revision)return;
        v.canvasInspect=record;followNavigator(v);if(inspectorVisible(v))updateInspector(v);
      }).catch(error=>{if(active(v)&&mounted.cy===cy&&v.canvasItem===id&&v.context?.revision===revision)fail(v,error);});
    }
  }
  function positionNodeActions(v,cy){
    const actions=mounted?.root.querySelector('[data-k-node-actions]');if(!actions||!cy||cy.destroyed())return;
    const context=mounted.root.querySelector('.r-context');
    if(context){
      const menuId=context.dataset.rMenuId;
      if(context.dataset.rMenuScope==='canvas'){actions.hidden=true;return;}
      if(!menuId||menuId!==(v.canvasItem||'')||!cy.getElementById(menuId).length){window.KnowledgeResearch?.closeMenu?.(v);}
      else {actions.hidden=true;return;}
    }
    const node=cy.getElementById(v.canvasItem||'');if(!node.length||!node.isNode()){actions.hidden=true;return;}
    const box=node.renderedBoundingBox(),container=mounted.root.querySelector('[data-k-cy]');
    actions.hidden=false;const width=actions.offsetWidth||260;actions.style.left=Math.max(4,Math.min(cy.width()-width-4,box.x2-width))+'px';actions.style.top=Math.max(0,Math.min(cy.height()-32,box.y1-32))+(container?.offsetTop||0)+'px';
    const available=v.canvasCapabilities?.id===node.id()&&v.canvasCapabilities.revision===v.context?.revision?v.canvasCapabilities.available:null;
    const open=actions.querySelector('[data-k-action="open-canvas"]');if(open)open.disabled=node.data('type')==='group';
    const expanded=window.ArchitectureMap?.branches(v);
    for(const button of actions.querySelectorAll('[data-k-branch-mode]')){const mode=button.dataset.kBranchMode;button.disabled=!available?.[mode];button.setAttribute('aria-pressed',String(expanded?.has(JSON.stringify([node.id(),mode]))||false));button.title=(window.ArchitectureMap.modes[mode]||mode)+(available?available[mode]?(globalThis.HubI18n?.t?.("knowledge.53f0369a4be0") ?? ' · раскрыть в текущей карте'):(globalThis.HubI18n?.t?.("knowledge.429a75ba54f0") ?? ' · нет доступных элементов'):(globalThis.HubI18n?.t?.("knowledge.5a6b3316471d") ?? ' · проверка доступности'));}
    const collapse=actions.querySelector('[data-k-action="collapse-branch"]');if(collapse)collapse.disabled=!graphModel(v).expanded?.has(node.id());
    const more=actions.querySelector('[data-k-action="more-branch"]');if(more)more.hidden=!window.ArchitectureMap?.branches(v).get(JSON.stringify([node.id(),v.filters.expandMode||'structure']))?.continuation.length;
  }
  async function expandCanvas(v,mode,more=false){
    if(!window.ArchitectureMap||!v.canvasItem||v.expanding)return;
    v.expanding=true;const id=v.canvasItem,selection=[...v.canvasSelection],owner=v.selected,generation=v.sequence,cy=mounted.cy;
    try{await window.ArchitectureMap.expand(v,id,mode,(action,args)=>request(v,action,args),graphModel(v),more);if(!active(v)||v.selected!==owner||v.sequence!==generation||mounted.cy!==cy)return;const state=canvasState(v);state.anchor=id;state.anchorScreen={...cy.getElementById(id).renderedPosition()};state.relayout=true;v.canvasItem=id;v.canvasSelection=selection;draw(v,state);const node=mounted.cy?.getElementById(id);if(node?.length){node.select();updateCanvasSelection(v,mounted.cy,node);}positionNodeActions(v,mounted.cy);}
    finally{v.expanding=false;}
  }
  function canvasState(v) {
    const cy=mounted?.cy;if(!cy||cy.destroyed())return null;
    const pan=cy.pan();
    const pending=!!cy.knowledgePending;
    return {owner:v.selected,camera:{x:pan.x,y:pan.y,scale:cy.zoom()},anchor:v.canvasItem,anchorScreen:v.canvasItem?{...cy.getElementById(v.canvasItem).renderedPosition()}:null,identity:cy.knowledgeKey,
      layoutPending:pending,routes:pending?null:(cy.knowledgeRoutes?copy([...cy.knowledgeRoutes]):null),
      positions:pending?new Map():new Map(cy.nodes().map(node=>[node.id(),{...node.position()}]))};
  }
  function focusCanvas(v) {
    const cy=mounted?.cy;if(!cy)return;
    sizeGraph(mounted.root.querySelector('[data-k-cy]'));cy.resize();
    const selected=cy.elements(':selected');cy.fit(selected.length?selected:undefined,40);
    if(selected.length&&cy.zoom()>1.5){cy.zoom(1.5);cy.center(selected);}captureCamera(v,cy);
  }
  function openCanvasItem(v,id) {
    const item=graphModel(v).nodes.find(node=>node.id===id);
    if(item?.type==='group'){focusCanvas(v);return;}
    chooseGraphItem(v,id,{graphMode:item?.type==='component'?'components':'neighborhood'});
  }
  function sizeGraph(container) {
    if(mounted?.root.dataset.kWorkspace==='true'){if(container?.style)container.style.height='';return;}
    if(!container?.getBoundingClientRect||!Number.isFinite(window.innerHeight))return;
    const top=container.getBoundingClientRect().top,available=Math.max(80,Math.floor(window.innerHeight-Math.max(0,top)-24));
    const height=available+'px';if(container.style.height!==height)container.style.height=height;
  }
  function clearCardOverlaps(cy) {
    if(cy.nodes().length<2)return;
    const cards=cy.nodes().map(node=>({node,position:{...node.position()},box:{...node.boundingBox({includeLabels:true,includeOverlays:false,useCache:false})}}));
    const gap=24;
    function compact(axis) {
      const other=axis==='x'?'y':'x',placed=[];
      // Move only colliding cards along one axis. Forbidden intervals avoid
      // iterative/random nudging and preserve the solver's other coordinate.
      for(const card of [...cards].sort((a,b)=>a.position[axis]-b.position[axis]||a.position[other]-b.position[other]||a.node.id().localeCompare(b.node.id()))){
        const min=card.box[axis+'1']-card.position[axis],max=card.box[axis+'2']-card.position[axis];
        const intervals=placed.filter(previous=>card.box[other+'1']<previous.box[other+'2']+gap&&previous.box[other+'1']<card.box[other+'2']+gap)
          .map(previous=>[previous.box[axis+'1']-max-gap,previous.box[axis+'2']-min+gap]).sort((a,b)=>a[0]-b[0]);
        let coordinate=card.position[axis];
        for(const [start,end] of intervals)if(coordinate>start&&coordinate<end)coordinate=end;
        const delta=coordinate-card.position[axis],position={...card.position,[axis]:coordinate},box={...card.box,[axis+'1']:card.box[axis+'1']+delta,[axis+'2']:card.box[axis+'2']+delta};
        placed.push({...card,position,box});
      }
      const width=Math.max(...placed.map(card=>card.box.x2))-Math.min(...placed.map(card=>card.box.x1)),height=Math.max(...placed.map(card=>card.box.y2))-Math.min(...placed.map(card=>card.box.y1));
      return {placed,fit:Math.min(Math.max(1,cy.width()-64)/width,Math.max(1,cy.height()-64)/height)};
    }
    const horizontal=compact('x'),vertical=compact('y'),best=horizontal.fit>=vertical.fit?horizontal:vertical;
    cy.batch(()=>best.placed.forEach(card=>{card.node.position('x',card.position.x);card.node.position('y',card.position.y);}));
  }
  function layoutGraph(v,cy,positions=null,camera=null,{preserveCamera=false,focusIds=[],liveCamera=false,fallback=false,anchor='',anchorScreen=null}={}) {
    sizeGraph(mounted.root.querySelector('[data-k-cy]'));cy.resize();
    const sequence=cy.knowledgeLayoutSequence=(cy.knowledgeLayoutSequence||0)+1;
    cy.knowledgePending=true;
    const container=mounted.root.querySelector('[data-k-cy]');if(container?.classList){container.classList.add('k-layout-pending');container.setAttribute('aria-busy','true');}
    const bounds={x1:0,y1:0,w:Math.max(1,cy.width()),h:Math.max(1,cy.height())};
    const options=positions?{name:'preset',positions,fit:false,animate:false}:cyLayout(v,fallback);
    const isCurrent=()=>active(v)&&mounted.cy===cy&&!cy.destroyed()&&cy.knowledgeLayoutSequence===sequence;
    const complete=()=>{
      if(!isCurrent())return;
      cy.resize();if(cy.batch)applyEdgeRouting(v,cy);
      if(liveCamera){const pan=cy.pan();camera={x:pan.x,y:pan.y,scale:cy.zoom()};}
      if(camera)cy.viewport({zoom:camera.scale,pan:{x:camera.x,y:camera.y}});
      const focus=focusIds.length?cy.collection(focusIds.flatMap(id=>[...cy.getElementById(id)])):null;
      const focused=anchor&&cy.getElementById(anchor);
      if(focused?.length&&anchorScreen){const p=focused.position();cy.viewport({zoom:cy.zoom(),pan:{x:anchorScreen.x-p.x*cy.zoom(),y:anchorScreen.y-p.y*cy.zoom()}});}
      else if(focus?.length)cy.center(focus);
      const box=cy.nodes().renderedBoundingBox(),offscreen=box&&(box.x2<0||box.y2<0||box.x1>cy.width()||box.y1>cy.height());
      if(!preserveCamera&&(!camera||offscreen)&&cy.nodes().length)cy.fit(undefined,32);
      cy.knowledgePending=false;
      if(container?.classList){container.classList.remove('k-layout-pending');container.setAttribute('aria-busy','false');}
      cy.knowledgeSpecial?.render?.();captureCamera(v,cy);savePositions(v,cy);positionNodeActions(v,cy);v.autoLayout=false;
      const caption=mounted.root.querySelector('[data-k-layout-active]');
      if(caption)caption.textContent=(globalThis.HubI18n?.t?.("knowledge.cc3c43686b46") ?? 'Активная компоновка: ')+({cose:(globalThis.HubI18n?.t?.("knowledge.0ddc55cb308d") ?? 'Силовая · резерв'),fcose:(globalThis.HubI18n?.t?.("knowledge.6ca68f51df2c") ?? 'fCoSE · резерв'),elk:(globalThis.HubI18n?.t?.("knowledge.a9a5abbd358c") ?? 'ELK · направленная'),grid:(globalThis.HubI18n?.t?.("knowledge.aa0cba195e50") ?? 'Сетка · резерв'),breadthfirst:(globalThis.HubI18n?.t?.("knowledge.21b98c7366e8") ?? 'Направленная · резерв')})[positions?cyLayout(v).name:options.name];
    };
    if(options.name==='elk'){
      window.ArchitectureMap.elkLayout(cy,complete,isCurrent).catch(error=>{if(!isCurrent())return;v.notice=(globalThis.HubI18n?.t?.("knowledge.da614ce8c1e0") ?? 'ELK недоступен: выполнено резервное размещение. ')+(globalThis.HubI18n?.error?.(error) ?? error.message);layoutGraph(v,cy,null,camera,{preserveCamera,focusIds,liveCamera,fallback:true,anchor,anchorScreen});});
      return;
    }
    if(!positions)cy.knowledgeRoutes=null;
    // Layout bounds are a target for centers, not a clipping frame for cards.
    // Enforce full-card clearance before fitting the completed graph.
    if(!positions)options.boundingBox=bounds;
    if(!positions){
      const elements=cy.elements().sort((a,b)=>a.id().localeCompare(b.id()));
      cy.layout({name:'grid',eles:elements.nodes(),boundingBox:bounds,fit:false,animate:false,avoidOverlap:true}).run();
      options.eles=elements;
    }
    const layout=cy.layout(options);
    layout.one('layoutstop',()=>{
      if(!active(v)||mounted.cy!==cy||cy.destroyed()||cy.knowledgeLayoutSequence!==sequence)return;
      if(!positions&&options.name==='cose')clearCardOverlaps(cy);
      complete();
    });
    layout.run();
  }
  function mountGraph(v,state=null) {
    if(!active(v)||v.mode!=='architecture'||!v.initialized||v.loading||v.researchLoading||v.filters.presentation==='matrix')return;
    const container=mounted.root.querySelector('[data-k-cy]');if(!container)return;
    sizeGraph(container);
    if(typeof window.cytoscape!=='function'){container.textContent=(globalThis.HubI18n?.t?.("knowledge.4a7433f8440e") ?? 'Граф недоступен: Cytoscape.js не загружен. Используйте доступный список элементов.');return;}
    const identity=graphKey(v),elements=cyElements(v),nodeIds=new Set(graphModel(v).nodes.map(node=>node.id)),savedPositions=v.positionCache.get(identity),validPositions=Array.isArray(savedPositions)&&savedPositions.length===nodeIds.size&&new Set(savedPositions.map(point=>point.id)).size===nodeIds.size&&savedPositions.every(point=>nodeIds.has(point.id)&&Number.isFinite(point.x)&&Number.isFinite(point.y)),
      saved=validPositions?Object.fromEntries(savedPositions.map(point=>[point.id,{x:point.x,y:point.y}])):null,
      restore=v.cameraInitialized&&v.cameraKey===identity,camera=copy(v.viewport);
    const cy=window.cytoscape({container,elements,style:[...cyStyle,{selector:'edge',style:edgeRoutingStyle(v)}],layout:{name:'preset',fit:false,animate:false},minZoom:.01,maxZoom:4,
      boxSelectionEnabled:true,selectionType:'single',autoungrabify:true,userPanningEnabled:false,
      hideEdgesOnViewport:elements.length>500,zoom:1,pan:{x:0,y:0}});
    cy.knowledgeKey=identity;
    cy.knowledgeOwner=v.selected;
    const statePositions=state?.identity===identity&&!state.layoutPending&&state.positions instanceof Map?state.positions:null;
    const stateComplete=!!statePositions&&[...nodeIds].every(id=>{const point=statePositions.get(id);return point&&Number.isFinite(point.x)&&Number.isFinite(point.y);});
    const positions=state?.relayout?null:state?(stateComplete?Object.fromEntries(statePositions):null):saved;
    if(state?.identity===identity&&state.routes)cy.knowledgeRoutes=new Map(state.routes);
    else if(!state&&positions&&v.routeCache?.has(identity))cy.knowledgeRoutes=new Map(copy(v.routeCache.get(identity)));
    mounted.cy=cy;applyCanvasSearch(v,cy);
    cy.knowledgeSpecial=window.ArchitectureRouting?.mount(cy,container,{select:edge=>{cy.elements(':selected').unselect();edge.select();updateCanvasSelection(v,cy,edge);},hover:(edge,on)=>{if(on)edge.addClass('hover');else edge.removeClass('hover');}});
    cy.knowledgeDense=elements.length>500;
    mounted.cyGestures=window.ArchitectureCanvas?.bind(cy,container,{motion:()=>canvasMotion(cy)});
    const stableAnchorScreen=state?.layoutPending?null:state?.anchorScreen;
    layoutGraph(v,cy,positions,state?.resetCamera?null:state?.camera||(restore?camera:null),{preserveCamera:!!state&&!state?.resetCamera,anchor:state?.anchor||'',anchorScreen:stableAnchorScreen,focusIds:state?.anchor&&!stableAnchorScreen?[state.anchor]:[]});
    if(cy.getElementById)for(const id of v.canvasSelection||[]){const node=cy.getElementById(id);if(node.length)node.select();}
    if(v.filters.focusRelation&&!v.canvasSelection?.length){const relation=cy.getElementById?.(v.filters.focusRelation);if(relation?.length){relation.select();updateCanvasSelection(v,cy,relation);}}
    cy.on('pan zoom',()=>{if(active(v)&&mounted.cy===cy)captureCamera(v,cy);});
    cy.on('select unselect',()=>{if(cy.knowledgeSelectionPending)return;cy.knowledgeSelectionPending=true;Promise.resolve().then(()=>{cy.knowledgeSelectionPending=false;if(active(v)&&mounted.cy===cy&&!cy.destroyed())updateCanvasSelection(v,cy);});});
    cy.on('tap','node',event=>{
      if(!active(v)||mounted.cy!==cy)return;
      updateCanvasSelection(v,cy,event.target);
    });
    cy.on('cxttap',event=>{if(event.target!==cy||!active(v)||mounted.cy!==cy)return;const rect=container.getBoundingClientRect(),point=event.renderedPosition;window.KnowledgeResearch?.canvasMenu(v,rect.left+point.x,rect.top+point.y);});
    cy.on('cxttap','node',event=>{if(!active(v)||mounted.cy!==cy)return;cy.elements(':selected').unselect();event.target.select();updateCanvasSelection(v,cy,event.target);const node=graphModel(v).nodes.find(n=>n.id===event.target.id()),rect=container.getBoundingClientRect(),point=event.renderedPosition||event.target.renderedPosition();if(node)window.KnowledgeResearch?.menu(v,node,rect.left+point.x,rect.top+point.y);});
    cy.on('dbltap','node',event=>{if(active(v)&&mounted.cy===cy)openCanvasItem(v,event.target.id());});
    cy.on('tap','edge',event=>{if(active(v)&&mounted.cy===cy)updateCanvasSelection(v,cy,event.target);});
    cy.on('mouseover','edge',event=>event.target.addClass('hover'));cy.on('mouseout','edge',event=>event.target.removeClass('hover'));
    cy.on('dragfree','node',event=>{if(active(v)&&mounted.cy===cy){const edges=event.target.union(event.target.descendants()).connectedEdges();flushGraphRoutes(v,cy,edges);window.ArchitectureMap?.finishRoutes(cy,edges);savePositions(v,cy);}});
    cy.on('position','node',event=>{if(active(v)&&mounted.cy===cy){scheduleGraphRoutes(v,cy,event.target);scheduleGraphOverlays(v,cy,true);}});
    cy.on('tap',event=>{if(event.target===cy&&!event.originalEvent?.shiftKey&&!event.originalEvent?.ctrlKey&&!event.originalEvent?.metaKey){cy.elements(':selected').unselect();updateCanvasSelection(v,cy);}});
    if(v.canvasSelection?.length)updateCanvasSelection(v,cy);
    if(window.ResizeObserver){mounted.cyResize=new window.ResizeObserver(()=>{if(active(v)&&mounted.cy===cy&&!cy.destroyed()){sizeGraph(container);cy.resize();scheduleGraphOverlays(v,cy);}});mounted.cyResize.observe(container);}
  }
  function chooseGraphItem(v,id,filterPatch=null) {
    v.scopeRevealRequested=true;v.researchCanvas=null;v.researchLoading=false;if(v.research){v.research.epoch++;v.research.branches.clear();v.research.baseline=null;v.research.scenarioBase=null;v.research.pinned.clear();}
    captureCamera(v,mounted.cy);recordGraph(v);
    if(v.mode==='architecture'&&v.selected!==id){v.filters.componentContext=v.filters.scopeContexts?.[id]||'auto';v.filters.codeLimit=PAGE;v.filters.hiddenTypes=[];v.filters.hiddenRelations=[];v.filters.edgeDirection='all';v.filters.edgeAnchor='';v.filters.canvasQuery='';v.filters.presentation='map';}
    v.filters.focusTarget='';v.filters.focusRelation='';selectItem(v,id);if(filterPatch)Object.assign(v.filters,filterPatch);mounted.selection=v.selected;
    if(v.mode==='architecture'&&v.filters.graphMode==='overview'&&id)v.filters.graphMode='neighborhood';
    recordGraph(v);persist(v);history.replaceState(null,'',link(v.mode,v.selected));
    if(v.mode==='architecture')refresh(v);
    else if(v.drafts.get(v.selected)?.dirty)draw(v);else loadItem(v,v.selected);
  }
  function componentScope(v) {
    const parent=v.componentItems?.find(item=>item.id===v.selected),count=(v.componentItems||[]).filter(item=>(item.parent||null)===(parent?.id||null)).length;
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.5e9803acc9ba",{v0:(parent?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.570d9d15a675",{v0:(esc(parent.parent||'')),v1:(esc(parent.title))}) : `<button data-k-select="${esc(parent.parent||'')}">На уровень выше</button><strong>${esc(parent.title)}</strong>`):''),v1:(parent&&!count?(globalThis.HubI18n?.t?.("knowledge.53d64437fb81") ?? 'Состав подсистемы · типы из исходников.'):(globalThis.HubI18n?.t?.("knowledge.3f60c862ebc1") ?? 'Прямые дочерние компоненты: ')+count+'.')}) : `<nav class="k-component-scope"><button data-k-action="component-root">Корневые компоненты</button>${parent?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.570d9d15a675",{v0:(esc(parent.parent||'')),v1:(esc(parent.title))}) : `<button data-k-select="${esc(parent.parent||'')}">На уровень выше</button><strong>${esc(parent.title)}</strong>`):''}<span>${parent&&!count?(globalThis.HubI18n?.t?.("knowledge.53d64437fb81") ?? 'Состав подсистемы · типы из исходников.'):(globalThis.HubI18n?.t?.("knowledge.3f60c862ebc1") ?? 'Прямые дочерние компоненты: ')+count+'.'}</span></nav>`);
  }
  function matrix(v) {
    const graph=graphModel(v),model={...graph,nodes:graph.nodes.filter(n=>!graph.contextFrames?.has(n.id))},edges=new Map();for(const edge of model.relations){const key=JSON.stringify([edge.from,edge.to]),prior=edges.get(key);edges.set(key,prior?{...prior,count:(Number.isFinite(prior.count)?prior.count:1)+(Number.isFinite(edge.count)?edge.count:1)}:edge);}
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.da28bc8d8b81",{v0:(v.componentPartial?(globalThis.HubI18n?.t?.("knowledge.9abed7b54a44") ?? '<p class="k-warning">Матрица неполная: достигнут предел связей или версии данных различаются. ? — отсутствие связи не подтверждено.</p>'):''),v1:(model.nodes.map(node=>`<th scope="col"><button data-k-select="${esc(node.id)}">${esc(node.title)}</button></th>`).join('')),v2:(model.nodes.map(source=>`<tr><th scope="row"><button data-k-select="${esc(source.id)}">${esc(source.title)}</button></th>${model.nodes.map(target=>{const edge=edges.get(JSON.stringify([source.id,target.id]));return `<td>${source.id===target.id?'—':edge?`<button data-k-matrix-from="${esc(source.id)}" data-k-matrix-to="${esc(target.id)}" data-k-matrix-edge="${esc(edge.id)}" aria-label="${esc(source.title+(globalThis.HubI18n?.t?.("knowledge.059cdac0d09f") ?? ' зависит от ')+target.title+' · '+(Number.isFinite(edge.count)?edge.count:(globalThis.HubI18n?.t?.("knowledge.90c8cf35ae10") ?? 'число не указано'))+(globalThis.HubI18n?.t?.("knowledge.762c7823d566") ?? ' статических связей'))}">${Number.isFinite(edge.count)?edge.count:(globalThis.HubI18n?.t?.("knowledge.747f78e5a0be") ?? 'есть')}</button>`:v.componentPartial?'?':'0'}</td>`;}).join('')}</tr>`).join('')),v3:(!model.nodes.length?(globalThis.HubI18n?.t?.("knowledge.04b22be55b12") ?? '<p>На этом уровне дочерних компонентов нет. Выберите уровень выше или локальные связи.</p>'):'')}) : `<section class="k-matrix-panel"><p>Строка — источник, столбец — зависимость. Число — статические связи из синтаксиса, не количество вызовов. Выберите ячейку для локального графа.</p>${v.componentPartial?(globalThis.HubI18n?.t?.("knowledge.9abed7b54a44") ?? '<p class="k-warning">Матрица неполная: достигнут предел связей или версии данных различаются. ? — отсутствие связи не подтверждено.</p>'):''}<div class="k-matrix-scroll"><table><caption>Связи текущей выборки</caption><thead><tr><th scope="col">Источник ↓ / зависимость →</th>${model.nodes.map(node=>`<th scope="col"><button data-k-select="${esc(node.id)}">${esc(node.title)}</button></th>`).join('')}</tr></thead><tbody>${model.nodes.map(source=>`<tr><th scope="row"><button data-k-select="${esc(source.id)}">${esc(source.title)}</button></th>${model.nodes.map(target=>{const edge=edges.get(JSON.stringify([source.id,target.id]));return `<td>${source.id===target.id?'—':edge?`<button data-k-matrix-from="${esc(source.id)}" data-k-matrix-to="${esc(target.id)}" data-k-matrix-edge="${esc(edge.id)}" aria-label="${esc(source.title+(globalThis.HubI18n?.t?.("knowledge.059cdac0d09f") ?? ' зависит от ')+target.title+' · '+(Number.isFinite(edge.count)?edge.count:(globalThis.HubI18n?.t?.("knowledge.90c8cf35ae10") ?? 'число не указано'))+(globalThis.HubI18n?.t?.("knowledge.762c7823d566") ?? ' статических связей'))}">${Number.isFinite(edge.count)?edge.count:(globalThis.HubI18n?.t?.("knowledge.747f78e5a0be") ?? 'есть')}</button>`:v.componentPartial?'?':'0'}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div>${!model.nodes.length?(globalThis.HubI18n?.t?.("knowledge.04b22be55b12") ?? '<p>На этом уровне дочерних компонентов нет. Выберите уровень выше или локальные связи.</p>'):''}</section>`);
  }
  function inspectorVisible(v) {
    return v.filters.inspectorCollapsed===false;
  }
  function updateRoleDescription(v){
    const panel=mounted?.root?.querySelector?.('.k-role-description'),button=mounted?.root?.querySelector?.('.k-role-more');
    if(!panel||!button)return;
    const id=button.dataset.kRoleId,expanded=!!v.roleExpanded?.[id];
    let probe=panel.cloneNode?.(true),overflow=false;
    const host=panel.parentElement||panel.parentNode;
    if(probe&&host){probe.classList.remove('is-expanded');probe.style.cssText='position:absolute;visibility:hidden;pointer-events:none;width:'+panel.getBoundingClientRect().width+'px;';host.append(probe);overflow=probe.scrollHeight>probe.clientHeight+1;probe.remove();}
    else overflow=panel.scrollHeight>panel.clientHeight+1;
    if(expanded&&!overflow){v.roleExpanded[id]=false;panel.classList.remove('is-expanded');}
    button.hidden=!overflow;button.textContent=expanded&&overflow?(globalThis.HubI18n?.t?.("knowledge.36c25d9ffcfd") ?? 'Свернуть'):(globalThis.HubI18n?.t?.("knowledge.c6826c783794") ?? 'Показать ещё');
  }
  function observeRoleDescription(v){
    mounted?.roleResize?.disconnect?.();mounted.roleResize=null;
    updateRoleDescription(v);
    const panel=mounted?.root?.querySelector?.('.k-role-description');
    if(panel&&window.ResizeObserver){mounted.roleResize=new window.ResizeObserver(()=>{if(!mounted.roleMeasure){mounted.roleMeasure=true;const run=()=>{mounted.roleMeasure=false;if(active(v))updateRoleDescription(v);};(window.requestAnimationFrame||setTimeout)(run);}});mounted.roleResize.observe(panel);}
  }
  function chartFilters(v){
    if(v.drafts.get(v.selected)?.item.kind==='view')return '';
    const base=baseGraphModel(v),componentLevel=v.filters.graphMode==='components'&&!v.scopedCode,types=componentLevel?[]:[...new Set(base.nodes.map(n=>n.type))].filter(id=>nodeTypes[id]),anchor=base.nodes.find(n=>n.id===(v.filters.edgeAnchor||v.canvasItem||v.selected));
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.602dc9c88c0e",{v0:(types.length?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.4e94a7dab9af",{v0:(types.map(id=>`<label><input type="checkbox" data-k-visible-type="${id}"${(v.filters.hiddenTypes||[]).includes(id)?'':' checked'}>${nodeTypes[id]}</label>`).join(''))}) : `<fieldset><legend>Типы участников текущей карты</legend>${types.map(id=>`<label><input type="checkbox" data-k-visible-type="${id}"${(v.filters.hiddenTypes||[]).includes(id)?'':' checked'}>${nodeTypes[id]}</label>`).join('')}</fieldset>`):''),v1:([...new Set(base.relations.map(e=>e.type))].map(id=>`<label><input type="checkbox" data-k-visible-relation="${esc(id)}"${(v.filters.hiddenRelations||[]).includes(id)?'':' checked'}>${esc(edgeTypes[id]||id)}</label>`).join('')),v2:(anchor?(globalThis.HubI18n?.t?.("knowledge.be9b64fcd3b4") ?? ' относительно ')+esc(anchor.title):(globalThis.HubI18n?.t?.("knowledge.920c27c1a0d4") ?? ' · выберите участника на схеме')),v3:(esc(anchor?.id||'')),v4:([['all',(globalThis.HubI18n?.t?.("knowledge.215816bf4210") ?? 'Все')],['incoming',(globalThis.HubI18n?.t?.("knowledge.5a198abc4c76") ?? 'Входящие')],['outgoing',(globalThis.HubI18n?.t?.("knowledge.8b2983ada1b3") ?? 'Исходящие')]].map(([id,title])=>`<option value="${id}"${(v.filters.edgeDirection||'all')===id?' selected':''}${!anchor&&id!=='all'?' disabled':''}>${title}</option>`).join(''))}) : `${types.length?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.4e94a7dab9af",{v0:(types.map(id=>`<label><input type="checkbox" data-k-visible-type="${id}"${(v.filters.hiddenTypes||[]).includes(id)?'':' checked'}>${nodeTypes[id]}</label>`).join(''))}) : `<fieldset><legend>Типы участников текущей карты</legend>${types.map(id=>`<label><input type="checkbox" data-k-visible-type="${id}"${(v.filters.hiddenTypes||[]).includes(id)?'':' checked'}>${nodeTypes[id]}</label>`).join('')}</fieldset>`):''}<fieldset><legend>Связи текущей карты</legend>${[...new Set(base.relations.map(e=>e.type))].map(id=>`<label><input type="checkbox" data-k-visible-relation="${esc(id)}"${(v.filters.hiddenRelations||[]).includes(id)?'':' checked'}>${esc(edgeTypes[id]||id)}</label>`).join('')}</fieldset><label>Направление${anchor?(globalThis.HubI18n?.t?.("knowledge.be9b64fcd3b4") ?? ' относительно ')+esc(anchor.title):(globalThis.HubI18n?.t?.("knowledge.920c27c1a0d4") ?? ' · выберите участника на схеме')}<select data-k-edge-direction data-k-edge-anchor="${esc(anchor?.id||'')}">${[['all',(globalThis.HubI18n?.t?.("knowledge.215816bf4210") ?? 'Все')],['incoming',(globalThis.HubI18n?.t?.("knowledge.5a198abc4c76") ?? 'Входящие')],['outgoing',(globalThis.HubI18n?.t?.("knowledge.8b2983ada1b3") ?? 'Исходящие')]].map(([id,title])=>`<option value="${id}"${(v.filters.edgeDirection||'all')===id?' selected':''}${!anchor&&id!=='all'?' disabled':''}>${title}</option>`).join('')}</select></label><button data-k-action="reset-filters">Сбросить фильтры</button>`);
  }
  function filterCount(v){return (v.filters.hiddenTypes?.length||0)+(v.filters.hiddenRelations?.length||0)+(v.filters.edgeDirection&&v.filters.edgeDirection!=='all'?1:0);}
  function chartFilterMenu(v){return v.drafts.get(v.selected)?.item.kind==='view'?'':(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.6a4da0ccebfc",{v0:(filterCount(v)?' ('+filterCount(v)+')':''),v1:(chartFilters(v))}) : `<details class="k-graph-info" data-k-filters-menu><summary>Фильтры${filterCount(v)?' ('+filterCount(v)+')':''}</summary><div class="k-info-content k-view-options">${chartFilters(v)}</div></details>`);}
  function graph(v) {
    if(v.loading||v.researchLoading||!v.initialized)return '<section class="k-graph-panel k-graph-wait" role="status" aria-busy="true">'+(v.error?(globalThis.HubI18n?.t?.("knowledge.9caf0bf93bd8") ?? 'Не удалось открыть раздел. Перечитайте данные.'):(globalThis.HubI18n?.t?.("knowledge.c18afab9e18b") ?? 'Подготавливаем выбранный раздел…'))+'</section>';
    if (v.filters.graphMode==='catalog') return '';
    if(window.KnowledgeResearch)return window.KnowledgeResearch.graph(v,graphModel(v),inspectorVisible(v));
    const model=graphModel(v),loaded=window.ArchitectureMap?.model(v,baseGraphModel(v))||baseGraphModel(v),participantsCount=m=>m.nodes.filter(n=>!m.contextFrames?.has(n.id)&&n.type!=='group').length,frames=model.nodes.length-participantsCount(model);
    const information=(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.27f2e5537850",{v0:(Object.entries(nodeTypes).map(([type,title])=>`<span data-k-type="${type}" style="--k-node-fill:${nodeColors[type].fill};--k-node-border:${nodeColors[type].border}">${title}</span>`).join('')),v1:(model.relations.length),v2:(v.relationsMore?(globalThis.HubI18n?.t?.("knowledge.6b958a8a9791") ?? '<p class="k-warning">Связи получены не полностью. Обновите данные или уточните выбранный элемент.</p>'):''),v3:(cyElements(v).filter(element=>element.group==='edges').map(element=>`<p>${esc(element.data.full)}</p>`).join('')||(globalThis.HubI18n?.t?.("knowledge.09f88cd01006") ?? '<p>Связей в этом представлении нет.</p>'))}) : `<details class="k-graph-info"><summary>Легенда</summary><div class="k-info-content"><div class="k-graph-legend" aria-label="Легенда графа">${Object.entries(nodeTypes).map(([type,title])=>`<span data-k-type="${type}" style="--k-node-fill:${nodeColors[type].fill};--k-node-border:${nodeColors[type].border}">${title}</span>`).join('')}<span>Цвет карточки — тип объекта. У интерфейса пунктирная рамка, у внешнего типа — точечная. Выбор отмечен золотой рамкой.</span><span>Стрелка — направление связи; сплошная — факт из кода, пунктирная — авторская связь.</span></div><div class="k-graph-legend"><span data-k-edge="inheritance">Наследование / реализация</span><span data-k-edge="dependency">Использование / зависимость</span><span data-k-edge="imports">Импорт</span><span data-k-edge="contains">Содержит</span><span data-k-edge="action">Авторская связь / действие</span><span>Подписи связи показаны при выборе или наведении.</span></div></div></details>
      <details class="k-graph-info k-graph-relations"><summary>Связи (${model.relations.length})</summary><div class="k-info-content">${v.relationsMore?(globalThis.HubI18n?.t?.("knowledge.6b958a8a9791") ?? '<p class="k-warning">Связи получены не полностью. Обновите данные или уточните выбранный элемент.</p>'):''}${cyElements(v).filter(element=>element.group==='edges').map(element=>`<p>${esc(element.data.full)}</p>`).join('')||(globalThis.HubI18n?.t?.("knowledge.09f88cd01006") ?? '<p>Связей в этом представлении нет.</p>')}</div></details>`);
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.fa67bcc61ea0",{v0:(architectureContext(v)),v1:(!(v.navigationIndex>0)?' disabled':''),v2:(icon('ArrowLeft')||'←'),v3:(!(v.navigationIndex<v.navigation?.length-1)?' disabled':''),v4:(icon('ArrowRight')||'→'),v5:(icon('Maximize')),v6:(icon('Focus')),v7:(icon('ArrowUpRight')),v8:(icon('Network')),v9:(inspectorVisible(v)),v10:(icon('PanelRight')),v11:(icon('SlidersHorizontal')),v12:(!v.filters.groupBy||v.filters.groupBy==='components'?' selected':''),v13:(v.filters.groupBy==='types'?' selected':''),v14:(v.filters.groupBy==='none'?' selected':''),v15:(({cose:(globalThis.HubI18n?.t?.("knowledge.8570951c0e20") ?? 'Силовая'),fcose:(globalThis.HubI18n?.t?.("knowledge.16f1d7d50ee2") ?? 'fCoSE · вложенная'),elk:(globalThis.HubI18n?.t?.("knowledge.a9a5abbd358c") ?? 'ELK · направленная'),grid:(globalThis.HubI18n?.t?.("knowledge.17859e5e0a99") ?? 'Сетка · нет связей'),breadthfirst:(globalThis.HubI18n?.t?.("knowledge.301b1e213147") ?? 'Направленная')})[cyLayout(v).name]),v16:(chartFilterMenu(v)),v17:(information),v18:(model.nodes.length),v19:(esc(v.filters.canvasQuery||'')),v20:(canvasMatches(v,model.nodes).length),v21:(model.nodes.length),v22:(participants(v,model)),v23:(v.scopedCode&&v.componentPartial?(globalThis.HubI18n?.t?.("knowledge.002864e2866d") ?? '<button data-k-action="more-code">Ещё код</button><span class="k-warning">Показана часть кода</span>'):''),v24:(participantsCount(loaded)),v25:(participantsCount(model)),v26:(frames?' · '+frames+(globalThis.HubI18n?.t?.("knowledge.d9d36a4e0f95") ?? ' рамок'):''),v27:(model.relations.length),v28:(Object.entries(window.ArchitectureMap?.modes||{structure:(globalThis.HubI18n?.t?.("knowledge.816655bd716f") ?? 'Структура')}).map(([id,title])=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.49230ba6f344",{v0:(id),v1:(title),v2:(title),v3:(icon(({structure:'FolderTree',neighbors:'Network',interfaces:'Plug',inheritance:'GitBranch',dependencies:'ArrowRightLeft'})[id])||title)}) : `<button data-k-action="expand-direct" data-k-branch-mode="${id}" aria-label="Раскрыть: ${title}" title="${title}" disabled>${icon(({structure:'FolderTree',neighbors:'Network',interfaces:'Plug',inheritance:'GitBranch',dependencies:'ArrowRightLeft'})[id])||title}</button>`)).join('')),v29:(icon('Focus')||'◎'),v30:(icon('ArrowUpRight')||'↗'),v31:(icon('Minus')||'−'),v32:(['components','matrix'].includes(v.filters.graphMode)?componentScope(v):''),v33:(v.filters.presentation==='matrix'||v.filters.graphMode==='matrix'?matrix(v):(globalThis.HubI18n?.t?.("knowledge.db92aca77ded") ?? '<div class="k-graph" data-k-cy role="group" aria-label="Граф архитектуры. Для выбора клавиатурой используйте список На схеме."><div class="k-group-labels" data-k-group-labels aria-hidden="true"></div></div>'))}) : `<section class="k-graph-panel">${architectureContext(v)}<div class="k-actions k-graph-tools"><div class="k-tool-group" role="group" aria-label="Навигация"><button data-k-action="graph-back" aria-label="Назад по графу" title="Назад"${!(v.navigationIndex>0)?' disabled':''}>${icon('ArrowLeft')||'←'}</button><button data-k-action="graph-forward" aria-label="Вперёд по графу" title="Вперёд"${!(v.navigationIndex<v.navigation?.length-1)?' disabled':''}>${icon('ArrowRight')||'→'}</button><button data-k-action="zoom-out" aria-label="Уменьшить">−</button><button data-k-action="zoom-in" aria-label="Увеличить">+</button></div><div class="k-tool-group" role="group" aria-label="Управление картой"><button data-k-action="fit" aria-label="Вписать все отображаемые узлы">${icon('Maximize')}Вписать всё</button><button data-k-action="focus" title="F — вписать выбранные узлы; без выбора — всё">${icon('Focus')}Фокус</button><button data-k-action="open-canvas">${icon('ArrowUpRight')}Открыть выбранное</button><button data-k-action="auto-layout">${icon('Network')}Автокомпоновка</button></div><button data-k-action="toggle-inspector" aria-label="Панель сведений" aria-expanded="${inspectorVisible(v)}">${icon('PanelRight')}Сведения</button><details class="k-graph-info"><summary>${icon('SlidersHorizontal')}Вид</summary><div class="k-info-content k-view-options"><p>Размещение: ELK · ортогональное</p><p>Связи: ортогональные со скруглением. Вложенные связи и петли — фиксированная компактная кривая.</p><label>Группировка<select data-k-group-by aria-label="Группировка"><option value="components"${!v.filters.groupBy||v.filters.groupBy==='components'?' selected':''}>Компоненты</option><option value="types"${v.filters.groupBy==='types'?' selected':''}>Компоненты и типы</option><option value="none"${v.filters.groupBy==='none'?' selected':''}>Без рамок</option></select></label><small data-k-layout-active>Активная компоновка: ${({cose:(globalThis.HubI18n?.t?.("knowledge.8570951c0e20") ?? 'Силовая'),fcose:(globalThis.HubI18n?.t?.("knowledge.16f1d7d50ee2") ?? 'fCoSE · вложенная'),elk:(globalThis.HubI18n?.t?.("knowledge.a9a5abbd358c") ?? 'ELK · направленная'),grid:(globalThis.HubI18n?.t?.("knowledge.17859e5e0a99") ?? 'Сетка · нет связей'),breadthfirst:(globalThis.HubI18n?.t?.("knowledge.301b1e213147") ?? 'Направленная')})[cyLayout(v).name]}</small></div></details>${chartFilterMenu(v)}${information}<details class="k-graph-info k-participants-menu" data-k-participants-menu><summary>На схеме (${model.nodes.length})</summary><div class="k-info-content k-participants-tree" data-k-participants data-k-browser-mode="graph"><label class="k-navigator-search">Найти на схеме<input data-k-find-on-map value="${esc(v.filters.canvasQuery||'')}" placeholder="Название или путь"></label><small data-k-find-count>${canvasMatches(v,model.nodes).length} совпадений · ${model.nodes.length} участников</small><small data-k-follow-status></small><div data-k-participant-rows>${participants(v,model)}</div></div></details>${v.scopedCode&&v.componentPartial?(globalThis.HubI18n?.t?.("knowledge.002864e2866d") ?? '<button data-k-action="more-code">Ещё код</button><span class="k-warning">Показана часть кода</span>'):''}<span class="k-graph-count">Загружено ${participantsCount(loaded)} · показано ${participantsCount(model)} узлов${frames?' · '+frames+(globalThis.HubI18n?.t?.("knowledge.d9d36a4e0f95") ?? ' рамок'):''} · ${model.relations.length} связей</span></div><p data-k-canvas-selection role="status" hidden></p><div class="k-node-actions" data-k-node-actions hidden>${Object.entries(window.ArchitectureMap?.modes||{structure:(globalThis.HubI18n?.t?.("knowledge.816655bd716f") ?? 'Структура')}).map(([id,title])=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.49230ba6f344",{v0:(id),v1:(title),v2:(title),v3:(icon(({structure:'FolderTree',neighbors:'Network',interfaces:'Plug',inheritance:'GitBranch',dependencies:'ArrowRightLeft'})[id])||title)}) : `<button data-k-action="expand-direct" data-k-branch-mode="${id}" aria-label="Раскрыть: ${title}" title="${title}" disabled>${icon(({structure:'FolderTree',neighbors:'Network',interfaces:'Plug',inheritance:'GitBranch',dependencies:'ArrowRightLeft'})[id])||title}</button>`)).join('')}<button data-k-action="focus" aria-label="Фокус на выбранном узле" title="Фокус на выбранном узле · F">${icon('Focus')||'◎'}</button><button data-k-action="open-canvas" aria-label="Открыть выбранный узел" title="Открыть выбранный узел">${icon('ArrowUpRight')||'↗'}</button><button data-k-action="more-branch" aria-label="Показать ещё связи" title="Загрузить следующую часть ветви" hidden>Ещё</button><button data-k-action="collapse-branch" aria-label="Свернуть ветку" title="Свернуть ветку">${icon('Minus')||'−'}</button></div>
      ${['components','matrix'].includes(v.filters.graphMode)?componentScope(v):''}
      ${v.filters.presentation==='matrix'||v.filters.graphMode==='matrix'?matrix(v):(globalThis.HubI18n?.t?.("knowledge.db92aca77ded") ?? '<div class="k-graph" data-k-cy role="group" aria-label="Граф архитектуры. Для выбора клавиатурой используйте список На схеме."><div class="k-group-labels" data-k-group-labels aria-hidden="true"></div></div>')}
      </section>`);
  }
  function inspectorContent(v,item,draft=null){
    item=inspectorItem(v,item);
    draft ||= v.drafts.get(item.id);
    const known=new Map(graphModel(v).nodes.map(n=>[n.id,n]));
    const name=id=>known.has(id)?esc(known.get(id).title||nodeLabel(known.get(id)).rows.join('')):entityLinkLabel(v,id);
    const relations=(draft&&item.id===v.selected?v.relations:graphModel(v).relations).filter(r=>r.from===item.id||r.to===item.id);
    const documents=new Map((item.documentRefs||[]).map(id=>[id,{id,title:null}]));
    if(item.id===v.selected)for(const doc of v.linkedDocs||[])documents.set(doc.id,doc);
    const section=(title,body)=>`<section class="k-inspector-section"><h3>${title}</h3>${body}</section>`;
    const relationGroup=(title,outgoing)=>{
      const rows=relations.filter(r=>outgoing?r.from===item.id:r.to===item.id);
      if(!rows.length)return '';
      return section(`${title} <span>${rows.length}</span>`,rows.map(r=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.99c15c690078",{v0:(esc(r.id)),v1:(esc(r.type)),v2:(esc(edgeTypes[r.type]||r.type)),v3:(icon('ArrowUpRight')),v4:(esc(outgoing?r.to:r.from)),v5:(link('architecture',outgoing?r.to:r.from)),v6:(name(outgoing?r.to:r.from)),v7:((r.evidence||[]).length?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.72369a5ce90f",{v0:(r.evidence.map(e=>`<p class="k-source">${esc(e.path)}:${esc(e.line||1)}</p>`).join(''))}) : `<details class="k-evidence"><summary>Исходные строки</summary>${r.evidence.map(e=>`<p class="k-source">${esc(e.path)}:${esc(e.line||1)}</p>`).join('')}</details>`):'')}) : `<div class="k-relation-row"><button data-k-select="${esc(r.id)}" title="Открыть описание связи"><span class="k-relation-kind" data-k-edge="${esc(r.type)}">${esc(edgeTypes[r.type]||r.type)}</span>${icon('ArrowUpRight')}</button><a data-k-select="${esc(outgoing?r.to:r.from)}" href="${link('architecture',outgoing?r.to:r.from)}">${name(outgoing?r.to:r.from)}</a>${(r.evidence||[]).length?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.72369a5ce90f",{v0:(r.evidence.map(e=>`<p class="k-source">${esc(e.path)}:${esc(e.line||1)}</p>`).join(''))}) : `<details class="k-evidence"><summary>Исходные строки</summary>${r.evidence.map(e=>`<p class="k-source">${esc(e.path)}:${esc(e.line||1)}</p>`).join('')}</details>`):''}</div>`)).join(''));
    };
    const html=(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.af968b8e9faf",{v0:(esc(item.title||nodeTypes[item.type]||item.type)),v1:(icon('X')),v2:(esc(item.type||item.kind)),v3:(esc(nodeTypes[item.type]||edgeTypes[item.type]||(item.kind==='view'?(globalThis.HubI18n?.t?.("knowledge.a5e51710d3c8") ?? 'Сценарий'):item.type))),v4:(item.provenance==='static'||item.source?(globalThis.HubI18n?.t?.("knowledge.4649615d4cdd") ?? 'Из исходников'):item.provenance==='presentation'?(globalThis.HubI18n?.t?.("knowledge.a97550017e68") ?? 'Группировка'):(globalThis.HubI18n?.t?.("knowledge.f83d147689b5") ?? 'Авторская модель')),v5:(item.entrypoint?(globalThis.HubI18n?.t?.("knowledge.00ddbc8b35e1") ?? '<span>Точка входа</span>'):''),v6:(item.component?section((globalThis.HubI18n?.t?.("knowledge.626cda060f0c") ?? 'Компонент'),`<p>${esc(componentName(v,item.component))}</p>`):''),v7:(item.source?section((globalThis.HubI18n?.t?.("knowledge.0b5267f774e0") ?? 'Исходник'),`<p class="k-source">${esc(item.source.path)}:${esc(item.source.line||1)}</p>${item.source.hash?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.7920665774c5",{v0:(esc(item.source.hash))}) : `<details class="k-evidence"><summary>Версия файла</summary><p class="k-source">${esc(item.source.hash)}</p></details>`):''}`):''),v8:(item.removed?(globalThis.HubI18n?.t?.("knowledge.d25ea8172e59") ?? '<p class="k-warning">Источник отсутствует в последнем сканировании.</p>'):''),v9:(item.analysisStatus==='stale'?(globalThis.HubI18n?.t?.("knowledge.a11835c117d5") ?? '<p class="k-warning">Исходники изменились. Обновите анализ.</p>'):''),v10:(item.resolution==='unresolved'?(globalThis.HubI18n?.t?.("knowledge.60d3cb70767b") ?? '<p class="k-warning">Внешняя или неоднозначная зависимость.</p>'):''),v11:(draft?.dirty?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.49107b030f7e",{v0:(draft.expected!==v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.0a9c723d632a") ?? ' · версия знаний изменилась'):'')}) : `<p class="k-warning">Есть несохранённые изменения${draft.expected!==v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.0a9c723d632a") ?? ' · версия знаний изменилась'):''}.</p>`):''),v12:((()=>{const role=String(item.description||(globalThis.HubI18n?.t?.("knowledge.4f875695055b") ?? 'Описание пока не добавлено.')),expanded=!!v.roleExpanded?.[item.id],hasRole=!!item.description,roleDraft=draft||v.drafts.get(item.id);return section((globalThis.HubI18n?.t?.("knowledge.f8e60bc2a232") ?? 'Роль в проекте'),`<p class="k-role-description${expanded?' is-expanded':''}">${esc(role)}</p>${hasRole?`<button class="k-role-more" data-k-action="toggle-role-description" data-k-role-id="${esc(item.id)}">${expanded?(globalThis.HubI18n?.t?.("knowledge.36c25d9ffcfd") ?? 'Свернуть'):(globalThis.HubI18n?.t?.("knowledge.c6826c783794") ?? 'Показать ещё')}</button>`:''}${roleDraft?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.3d7716c98a08",{v0:(esc(item.id)),v1:(icon('SquarePen')),v2:(roleDraft.dirty?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.807ec017e240",{v0:(esc(item.id)),v1:(v.busy?' disabled':''),v2:(icon('Save'))}) : `<button data-k-action="save" data-k-role-id="${esc(item.id)}"${v.busy?' disabled':''}>${icon('Save')}Сохранить *</button>`):''),v3:(esc(item.id)),v4:(icon('History'))}) : `<div class="k-actions"><button data-k-action="edit-role-description" data-k-role-id="${esc(item.id)}">${icon('SquarePen')}Изменить</button>${roleDraft.dirty?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.807ec017e240",{v0:(esc(item.id)),v1:(v.busy?' disabled':''),v2:(icon('Save'))}) : `<button data-k-action="save" data-k-role-id="${esc(item.id)}"${v.busy?' disabled':''}>${icon('Save')}Сохранить *</button>`):''}<button data-k-action="history" data-k-role-id="${esc(item.id)}">${icon('History')}История</button></div>`):''}`)})()),v13:(item.kind==='relation'?section((globalThis.HubI18n?.t?.("knowledge.bc0c40581492") ?? 'Направление'),`<nav class="k-links"><a data-k-select="${esc(item.from)}" href="${link('architecture',item.from)}">${name(item.from)}</a><span>→ ${esc(edgeTypes[item.type]||item.type)} →</span><a data-k-select="${esc(item.to)}" href="${link('architecture',item.to)}">${name(item.to)}</a></nav>`)+section((globalThis.HubI18n?.t?.("knowledge.f74456ae7d60") ?? 'Доказательства'),(item.evidence||[]).map(e=>`<p class="k-source">${esc(e.path)}:${esc(e.line||1)}</p>`).join('')||(globalThis.HubI18n?.t?.("knowledge.5014a1bdc8f3") ?? '<p class="k-empty">Исходные строки не указаны.</p>')):''),v14:(item.kind==='view'&&draft?section((globalThis.HubI18n?.t?.("knowledge.a5e51710d3c8") ?? 'Сценарий'),(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.0c99d07cf18f",{v0:(esc(item.title)),v1:(esc(item.viewType||'scenario')),v2:(esc((item.nodeIds||[]).join(', '))),v3:(esc((item.orderedEdges||[]).join(', '))),v4:(v.relations.map(r=>`<li><a data-k-select="${esc(r.from)}" href="${link('architecture',r.from)}">${name(r.from)}</a> → ${esc(edgeTypes[r.type]||r.type)} → <a data-k-select="${esc(r.to)}" href="${link('architecture',r.to)}">${name(r.to)}</a></li>`).join(''))}) : `<label>Название<input data-k-field="title" value="${esc(item.title)}"></label><label>Тип представления<input data-k-field="viewType" value="${esc(item.viewType||'scenario')}"></label><label>Узлы (ID)<textarea data-k-field="nodeIds" rows="2">${esc((item.nodeIds||[]).join(', '))}</textarea></label><label>Порядок связей (ID)<textarea data-k-field="orderedEdges" rows="2">${esc((item.orderedEdges||[]).join(', '))}</textarea></label><ol class="k-flow">${v.relations.map(r=>`<li><a data-k-select="${esc(r.from)}" href="${link('architecture',r.from)}">${name(r.from)}</a> → ${esc(edgeTypes[r.type]||r.type)} → <a data-k-select="${esc(r.to)}" href="${link('architecture',r.to)}">${name(r.to)}</a></li>`).join('')}</ol>`)):''),v15:(''),v16:(section((globalThis.HubI18n?.t?.("knowledge.b123be6f8236") ?? 'Документация'),(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.fed3ab900107",{v0:([...documents.values()].map(d=>`<a data-k-open-doc="${esc(d.id)}" href="${link('docs',d.id)}">${icon('BookOpen')}${d.title?esc(d.title):entityLinkLabel(v,d.id)}</a>`).join('')||(globalThis.HubI18n?.t?.("knowledge.aceb6c1af609") ?? '<p class="k-empty">Связанных статей пока нет.</p>'))}) : `<nav class="k-links" aria-label="Связанные документы">${[...documents.values()].map(d=>`<a data-k-open-doc="${esc(d.id)}" href="${link('docs',d.id)}">${icon('BookOpen')}${d.title?esc(d.title):entityLinkLabel(v,d.id)}</a>`).join('')||(globalThis.HubI18n?.t?.("knowledge.aceb6c1af609") ?? '<p class="k-empty">Связанных статей пока нет.</p>')}</nav>`))),v17:(relationGroup((globalThis.HubI18n?.t?.("knowledge.56fe4b0b5653") ?? 'Исходящие связи'),true)),v18:(relationGroup((globalThis.HubI18n?.t?.("knowledge.2391e3a2188b") ?? 'Входящие связи'),false)),v19:(item.type==='component'&&v.canvasGroupStats?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.f113dbe6c689",{v0:(v.canvasGroupStats.nodeCount),v1:(v.canvasGroupStats.internalCount),v2:(v.canvasGroupStats.incomingCount),v3:(v.canvasGroupStats.outgoingCount)}) : `<details class="k-inspector-section"><summary>Состав подсистемы на текущей карте · ${v.canvasGroupStats.nodeCount} узлов</summary><p>${v.canvasGroupStats.internalCount} внутренних связей · ${v.canvasGroupStats.incomingCount} входящих · ${v.canvasGroupStats.outgoingCount} исходящих</p></details>`):''),v20:(draft?historyPanel(v,item.id):''),v21:(draft&&v.historical&&v.historical.item.id===item.id?section((globalThis.HubI18n?.t?.("knowledge.553f67d234e4") ?? 'Историческая версия ')+v.historical.revision,(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9714ca3171b8",{v0:(esc(JSON.stringify(v.historical.item,null,2)))}) : `<pre>${esc(JSON.stringify(v.historical.item,null,2))}</pre><button data-k-action="restore">Восстановить как новую версию</button>`)):'')}) : `<article class="k-inspector"><header class="k-selection-header"><h2>${esc(item.title||nodeTypes[item.type]||item.type)}</h2><button data-k-action="toggle-inspector" aria-label="Закрыть панель сведений" title="Закрыть панель сведений">${icon('X')}</button></header><div class="k-item-meta"><span data-k-type="${esc(item.type||item.kind)}">${esc(nodeTypes[item.type]||edgeTypes[item.type]||(item.kind==='view'?(globalThis.HubI18n?.t?.("knowledge.a5e51710d3c8") ?? 'Сценарий'):item.type))}</span><span>${item.provenance==='static'||item.source?(globalThis.HubI18n?.t?.("knowledge.4649615d4cdd") ?? 'Из исходников'):item.provenance==='presentation'?(globalThis.HubI18n?.t?.("knowledge.a97550017e68") ?? 'Группировка'):(globalThis.HubI18n?.t?.("knowledge.f83d147689b5") ?? 'Авторская модель')}</span>${item.entrypoint?(globalThis.HubI18n?.t?.("knowledge.00ddbc8b35e1") ?? '<span>Точка входа</span>'):''}</div>
      ${item.component?section((globalThis.HubI18n?.t?.("knowledge.626cda060f0c") ?? 'Компонент'),`<p>${esc(componentName(v,item.component))}</p>`):''}
      ${item.source?section((globalThis.HubI18n?.t?.("knowledge.0b5267f774e0") ?? 'Исходник'),`<p class="k-source">${esc(item.source.path)}:${esc(item.source.line||1)}</p>${item.source.hash?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.7920665774c5",{v0:(esc(item.source.hash))}) : `<details class="k-evidence"><summary>Версия файла</summary><p class="k-source">${esc(item.source.hash)}</p></details>`):''}`):''}
      ${item.removed?(globalThis.HubI18n?.t?.("knowledge.d25ea8172e59") ?? '<p class="k-warning">Источник отсутствует в последнем сканировании.</p>'):''}${item.analysisStatus==='stale'?(globalThis.HubI18n?.t?.("knowledge.a11835c117d5") ?? '<p class="k-warning">Исходники изменились. Обновите анализ.</p>'):''}${item.resolution==='unresolved'?(globalThis.HubI18n?.t?.("knowledge.60d3cb70767b") ?? '<p class="k-warning">Внешняя или неоднозначная зависимость.</p>'):''}
      ${draft?.dirty?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.49107b030f7e",{v0:(draft.expected!==v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.0a9c723d632a") ?? ' · версия знаний изменилась'):'')}) : `<p class="k-warning">Есть несохранённые изменения${draft.expected!==v.context?.revision?(globalThis.HubI18n?.t?.("knowledge.0a9c723d632a") ?? ' · версия знаний изменилась'):''}.</p>`):''}
      ${(()=>{const role=String(item.description||(globalThis.HubI18n?.t?.("knowledge.4f875695055b") ?? 'Описание пока не добавлено.')),expanded=!!v.roleExpanded?.[item.id],hasRole=!!item.description,roleDraft=draft||v.drafts.get(item.id);return section((globalThis.HubI18n?.t?.("knowledge.f8e60bc2a232") ?? 'Роль в проекте'),`<p class="k-role-description${expanded?' is-expanded':''}">${esc(role)}</p>${hasRole?`<button class="k-role-more" data-k-action="toggle-role-description" data-k-role-id="${esc(item.id)}">${expanded?(globalThis.HubI18n?.t?.("knowledge.36c25d9ffcfd") ?? 'Свернуть'):(globalThis.HubI18n?.t?.("knowledge.c6826c783794") ?? 'Показать ещё')}</button>`:''}${roleDraft?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.3d7716c98a08",{v0:(esc(item.id)),v1:(icon('SquarePen')),v2:(roleDraft.dirty?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.807ec017e240",{v0:(esc(item.id)),v1:(v.busy?' disabled':''),v2:(icon('Save'))}) : `<button data-k-action="save" data-k-role-id="${esc(item.id)}"${v.busy?' disabled':''}>${icon('Save')}Сохранить *</button>`):''),v3:(esc(item.id)),v4:(icon('History'))}) : `<div class="k-actions"><button data-k-action="edit-role-description" data-k-role-id="${esc(item.id)}">${icon('SquarePen')}Изменить</button>${roleDraft.dirty?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.807ec017e240",{v0:(esc(item.id)),v1:(v.busy?' disabled':''),v2:(icon('Save'))}) : `<button data-k-action="save" data-k-role-id="${esc(item.id)}"${v.busy?' disabled':''}>${icon('Save')}Сохранить *</button>`):''}<button data-k-action="history" data-k-role-id="${esc(item.id)}">${icon('History')}История</button></div>`):''}`)})()}
      ${item.kind==='relation'?section((globalThis.HubI18n?.t?.("knowledge.bc0c40581492") ?? 'Направление'),`<nav class="k-links"><a data-k-select="${esc(item.from)}" href="${link('architecture',item.from)}">${name(item.from)}</a><span>→ ${esc(edgeTypes[item.type]||item.type)} →</span><a data-k-select="${esc(item.to)}" href="${link('architecture',item.to)}">${name(item.to)}</a></nav>`)+section((globalThis.HubI18n?.t?.("knowledge.f74456ae7d60") ?? 'Доказательства'),(item.evidence||[]).map(e=>`<p class="k-source">${esc(e.path)}:${esc(e.line||1)}</p>`).join('')||(globalThis.HubI18n?.t?.("knowledge.5014a1bdc8f3") ?? '<p class="k-empty">Исходные строки не указаны.</p>')):''}
      ${item.kind==='view'&&draft?section((globalThis.HubI18n?.t?.("knowledge.a5e51710d3c8") ?? 'Сценарий'),(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.0c99d07cf18f",{v0:(esc(item.title)),v1:(esc(item.viewType||'scenario')),v2:(esc((item.nodeIds||[]).join(', '))),v3:(esc((item.orderedEdges||[]).join(', '))),v4:(v.relations.map(r=>`<li><a data-k-select="${esc(r.from)}" href="${link('architecture',r.from)}">${name(r.from)}</a> → ${esc(edgeTypes[r.type]||r.type)} → <a data-k-select="${esc(r.to)}" href="${link('architecture',r.to)}">${name(r.to)}</a></li>`).join(''))}) : `<label>Название<input data-k-field="title" value="${esc(item.title)}"></label><label>Тип представления<input data-k-field="viewType" value="${esc(item.viewType||'scenario')}"></label><label>Узлы (ID)<textarea data-k-field="nodeIds" rows="2">${esc((item.nodeIds||[]).join(', '))}</textarea></label><label>Порядок связей (ID)<textarea data-k-field="orderedEdges" rows="2">${esc((item.orderedEdges||[]).join(', '))}</textarea></label><ol class="k-flow">${v.relations.map(r=>`<li><a data-k-select="${esc(r.from)}" href="${link('architecture',r.from)}">${name(r.from)}</a> → ${esc(edgeTypes[r.type]||r.type)} → <a data-k-select="${esc(r.to)}" href="${link('architecture',r.to)}">${name(r.to)}</a></li>`).join('')}</ol>`)):''}
      ${''}
      ${section((globalThis.HubI18n?.t?.("knowledge.b123be6f8236") ?? 'Документация'),(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.fed3ab900107",{v0:([...documents.values()].map(d=>`<a data-k-open-doc="${esc(d.id)}" href="${link('docs',d.id)}">${icon('BookOpen')}${d.title?esc(d.title):entityLinkLabel(v,d.id)}</a>`).join('')||(globalThis.HubI18n?.t?.("knowledge.aceb6c1af609") ?? '<p class="k-empty">Связанных статей пока нет.</p>'))}) : `<nav class="k-links" aria-label="Связанные документы">${[...documents.values()].map(d=>`<a data-k-open-doc="${esc(d.id)}" href="${link('docs',d.id)}">${icon('BookOpen')}${d.title?esc(d.title):entityLinkLabel(v,d.id)}</a>`).join('')||(globalThis.HubI18n?.t?.("knowledge.aceb6c1af609") ?? '<p class="k-empty">Связанных статей пока нет.</p>')}</nav>`))}
      ${relationGroup((globalThis.HubI18n?.t?.("knowledge.56fe4b0b5653") ?? 'Исходящие связи'),true)}${relationGroup((globalThis.HubI18n?.t?.("knowledge.2391e3a2188b") ?? 'Входящие связи'),false)}
      ${item.type==='component'&&v.canvasGroupStats?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.f113dbe6c689",{v0:(v.canvasGroupStats.nodeCount),v1:(v.canvasGroupStats.internalCount),v2:(v.canvasGroupStats.incomingCount),v3:(v.canvasGroupStats.outgoingCount)}) : `<details class="k-inspector-section"><summary>Состав подсистемы на текущей карте · ${v.canvasGroupStats.nodeCount} узлов</summary><p>${v.canvasGroupStats.internalCount} внутренних связей · ${v.canvasGroupStats.incomingCount} входящих · ${v.canvasGroupStats.outgoingCount} исходящих</p></details>`):''}${draft?historyPanel(v,item.id):''}${draft&&v.historical&&v.historical.item.id===item.id?section((globalThis.HubI18n?.t?.("knowledge.553f67d234e4") ?? 'Историческая версия ')+v.historical.revision,(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9714ca3171b8",{v0:(esc(JSON.stringify(v.historical.item,null,2)))}) : `<pre>${esc(JSON.stringify(v.historical.item,null,2))}</pre><button data-k-action="restore">Восстановить как новую версию</button>`)):''}</article>`);
    const actions=v.mode==='architecture'?(window.KnowledgeResearch?.actions(v,item)||'')+(window.HubSubsystems?.actions(v,item)||''):'';
    return html.replace(/<\/article>$/,actions+'</article>');
  }
  function emptyInspector(){
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.ee42062e1734",{v0:(icon('X'))}) : `<header class="k-selection-header"><h2>Сведения</h2><button data-k-action="toggle-inspector" aria-label="Закрыть панель сведений">${icon('X')}</button></header><div class="k-empty">Выберите узел или связь, чтобы увидеть роль, исходник и связанные статьи.</div>`);
  }
  function selectionInspector(v){
    const stats=v.canvasStats;if(!stats)return emptyInspector();
    const counts=(values,labels)=>`<dl class="k-selection-counts">${Object.entries(values).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).map(([type,count])=>`<dt>${esc(labels[type]||type)}</dt><dd>${count}</dd>`).join('')||(globalThis.HubI18n?.t?.("knowledge.d13620cdf7c1") ?? '<dt>Нет</dt><dd>0</dd>')}</dl>`;
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.ea6fb5a1eb23",{v0:(stats.selectedCount),v1:(icon('X')),v2:(icon('Focus')),v3:(stats.nodeCount),v4:(stats.groupCount),v5:(counts(stats.types,nodeTypes)),v6:(stats.components),v7:(stats.entrypoints),v8:(stats.sourceCount),v9:(stats.selectedRelationCount?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.752103b7f5e6",{v0:(stats.selectedRelationCount),v1:(counts(stats.selectedRelationTypes,edgeTypes))}) : `<section class="k-inspector-section"><h3>Выбранные связи · ${stats.selectedRelationCount}</h3>${counts(stats.selectedRelationTypes,edgeTypes)}</section>`):''),v10:(stats.internalCount),v11:(counts(stats.internalTypes,edgeTypes)),v12:(stats.aggregateCount!==null?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.ec3824dc268e",{v0:(stats.aggregateCount)}) : `<p>В агрегированных рёбрах: ${stats.aggregateCount} статических отношений исходников.</p>`):''),v13:(stats.incomingCount),v14:(counts(stats.incomingTypes,edgeTypes)),v15:(stats.outgoingCount),v16:(counts(stats.outgoingTypes,edgeTypes))}) : `<article class="k-inspector k-multi-selection"><header class="k-selection-header"><h2>Выбрано ${stats.selectedCount} элементов</h2><button data-k-action="toggle-inspector" aria-label="Закрыть панель сведений">${icon('X')}</button></header>
      <div class="k-actions"><button data-k-action="focus">${icon('Focus')}Вписать выбор</button><button data-k-action="clear-selection">Снять выбор</button></div>
      <section class="k-inspector-section"><h3>Состав выбора</h3><p>${stats.nodeCount} узлов · ${stats.groupCount} групп по типам</p>${counts(stats.types,nodeTypes)}<p>${stats.components} подсистем · ${stats.entrypoints} точек входа · ${stats.sourceCount} узлов с исходником</p></section>
      ${stats.selectedRelationCount?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.752103b7f5e6",{v0:(stats.selectedRelationCount),v1:(counts(stats.selectedRelationTypes,edgeTypes))}) : `<section class="k-inspector-section"><h3>Выбранные связи · ${stats.selectedRelationCount}</h3>${counts(stats.selectedRelationTypes,edgeTypes)}</section>`):''}
      <section class="k-inspector-section"><h3>Связи внутри выбора · ${stats.internalCount}</h3>${counts(stats.internalTypes,edgeTypes)}${stats.aggregateCount!==null?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.ec3824dc268e",{v0:(stats.aggregateCount)}) : `<p>В агрегированных рёбрах: ${stats.aggregateCount} статических отношений исходников.</p>`):''}</section>
      <section class="k-inspector-section"><h3>Связи с остальной картой</h3><details><summary>Входящие · ${stats.incomingCount}</summary>${counts(stats.incomingTypes,edgeTypes)}</details><details><summary>Исходящие · ${stats.outgoingCount}</summary>${counts(stats.outgoingTypes,edgeTypes)}</details></section>
      <p class="k-selection-note">Группы включают загруженное содержимое; каждый узел и связь учитываются один раз. Статистика относится к текущей карте. Узлы и группы размещаются автоматически; кнопка «Компоновка» обновляет их расположение. Правая кнопка мыши перемещает камеру.</p></article>`);
  }
  function architecturePanel(v,draft){
    const routeItem=['components','matrix'].includes(v.filters.graphMode)&&draft?.item.type!=='component'?null:draft?.item;
    const selected=v.canvasInspect&&graphModel(v).nodes.concat(graphModel(v).relations).some(n=>n.id===v.canvasInspect.id)?v.canvasInspect:routeItem;
    return `<div class="k-architecture-main">${graph(v)}<aside class="k-inspector-container${inspectorVisible(v)?'':' is-collapsed'}">${v.loading?emptyInspector():v.canvasStats?selectionInspector(v):selected?inspectorContent(v,selected,selected.id===routeItem?.id?draft:null):!v.selected&&window.HubSubsystems?window.HubSubsystems.projectInspector(v,text=>markdown(v,{markdown:text})):emptyInspector()}</aside></div>`;
  }
  function dialog(v,content,label){return `<div class="k-dialog-backdrop" data-k-dialog-backdrop><section class="k-auxiliary" role="dialog" aria-modal="true" aria-label="${esc(label)}" tabindex="-1">${content}</section></div>`;}
  function auxiliary(v) {
    if(v.panel==='role-description'){
      const draft=v.drafts.get(v.roleEditId||v.selected),item=draft?.item;
      if(!item)return '';
      return dialog(v,(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.ae309a1ed58e",{v0:(icon('X')),v1:(esc(item.description||'')),v2:(v.busy?' disabled':''),v3:(icon('Save')),v4:(draft.dirty?' *':'')}) : `<header class="k-inspector-head"><h2>Роль в проекте</h2><button data-k-action="close-panel" aria-label="Закрыть">${icon('X')}Закрыть</button></header><label>Описание<textarea id="k-description" data-k-field="description" maxlength="12000" rows="7" placeholder="Коротко опишите назначение элемента">${esc(item.description||'')}</textarea></label><div class="k-actions"><button class="k-primary" data-k-action="save-description"${v.busy?' disabled':''}>${icon('Save')}Сохранить${draft.dirty?' *':''}</button><button data-k-action="close-panel">Отмена</button></div>`),(globalThis.HubI18n?.t?.("knowledge.b373a5d81881") ?? 'Изменить роль в проекте'));
    }
    if(v.mode==='architecture'&&window.KnowledgeResearch?.state(v).dialog)return window.KnowledgeResearch.auxiliary(v);
    if(v.panel==='diagnostics')return dialog(v,(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.423fbd33023a",{v0:(icon('X')),v1:(v.context?.revision??'…'),v2:(v.loading?(globalThis.HubI18n?.t?.("knowledge.aae8a7b9edfb") ?? ' · Загрузка…'):''),v3:(jobNotice(v)),v4:(debtNotice(v)),v5:(v.context?capabilitiesNotice(v):(globalThis.HubI18n?.t?.("knowledge.a3e01ea25a8a") ?? '<p>Загрузка…</p>'))}) : `<header class="k-inspector-head"><h2>Состояние анализа</h2><button data-k-action="close-panel" aria-label="Закрыть">${icon('X')}Закрыть</button></header><div class="k-status">Версия знаний: ${v.context?.revision??'…'}${v.loading?(globalThis.HubI18n?.t?.("knowledge.aae8a7b9edfb") ?? ' · Загрузка…'):''}</div>${jobNotice(v)}${debtNotice(v)}<h3>Покрытие сканера</h3>${v.context?capabilitiesNotice(v):(globalThis.HubI18n?.t?.("knowledge.a3e01ea25a8a") ?? '<p>Загрузка…</p>')}`),(globalThis.HubI18n?.t?.("knowledge.bfdf0e3a0585") ?? 'Состояние анализа'));
    if(v.panel==='tools')return dialog(v,(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.b3e305d6ff4a",{v0:(v.mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.74c31d8580c2") ?? 'архитектуры'):(globalThis.HubI18n?.t?.("knowledge.cfbb85a2a060") ?? 'документации')),v1:(icon('X')),v2:(v.mode==='architecture'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9e51ec957ada",{v0:(icon('Languages'))}) : `<button data-r-action="providers">${icon('Languages')}<strong>Языковые провайдеры</strong><small>Подключённые языки и настройка сервера</small></button>`):''),v3:((v.mode==='architecture'?[['scan','ScanLine',(globalThis.HubI18n?.t?.("knowledge.8fbe51c7cdda") ?? 'Сканировать исходники'),(globalThis.HubI18n?.t?.("knowledge.ee7885b161a7") ?? 'Обновить факты локального анализа')],['new-view','Workflow',(globalThis.HubI18n?.t?.("knowledge.6b3110d5a472") ?? 'Новый сценарий'),(globalThis.HubI18n?.t?.("knowledge.6a7450a24a0a") ?? 'Сохранить смысловую последовательность')]]:[['new-doc','FilePlus',(globalThis.HubI18n?.t?.("knowledge.9d5fecb3d309") ?? 'Создать страницу'),(globalThis.HubI18n?.t?.("knowledge.0981c73c8915") ?? 'Добавить статью в выбранный раздел')],['import','FolderInput',(globalThis.HubI18n?.t?.("knowledge.ad317ef5316b") ?? 'Импортировать статьи'),(globalThis.HubI18n?.t?.("knowledge.3115c8dce126") ?? 'Предпросмотр Markdown и текста')]]).concat([['policy','Settings2',(globalThis.HubI18n?.t?.("knowledge.9271ccf19216") ?? 'Настройки знаний'),(globalThis.HubI18n?.t?.("knowledge.932059352b8e") ?? 'Компоненты, точки входа и правила анализа')],['export','Download',(globalThis.HubI18n?.t?.("knowledge.1f67cc552aef") ?? 'Экспорт ZIP'),(globalThis.HubI18n?.t?.("knowledge.9149d8d7ee7d") ?? 'Документация и архитектурные факты')],['export-public','Globe',(globalThis.HubI18n?.t?.("knowledge.b00a2d5a1f74") ?? 'Публичный ZIP'),(globalThis.HubI18n?.t?.("knowledge.0a2e2121f639") ?? 'Только согласованные публичные статьи')],['backup','Archive',(globalThis.HubI18n?.t?.("knowledge.9eb508eda2fc") ?? 'Резервная копия'),(globalThis.HubI18n?.t?.("knowledge.0c0cb4d8201a") ?? 'Полная копия базы знаний')]]).map(([action,name,title,description])=>`<button data-k-action="${action}">${icon(name)}<strong>${title}</strong><small>${description}</small></button>`).join(''))}) : `<header class="k-inspector-head"><h2>Инструменты ${v.mode==='architecture'?(globalThis.HubI18n?.t?.("knowledge.74c31d8580c2") ?? 'архитектуры'):(globalThis.HubI18n?.t?.("knowledge.cfbb85a2a060") ?? 'документации')}</h2><button data-k-action="close-panel" aria-label="Закрыть" title="Закрыть">${icon('X')}</button></header><div class="k-tool-grid">${v.mode==='architecture'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.9e51ec957ada",{v0:(icon('Languages'))}) : `<button data-r-action="providers">${icon('Languages')}<strong>Языковые провайдеры</strong><small>Подключённые языки и настройка сервера</small></button>`):''}${(v.mode==='architecture'?[['scan','ScanLine',(globalThis.HubI18n?.t?.("knowledge.8fbe51c7cdda") ?? 'Сканировать исходники'),(globalThis.HubI18n?.t?.("knowledge.ee7885b161a7") ?? 'Обновить факты локального анализа')],['new-view','Workflow',(globalThis.HubI18n?.t?.("knowledge.6b3110d5a472") ?? 'Новый сценарий'),(globalThis.HubI18n?.t?.("knowledge.6a7450a24a0a") ?? 'Сохранить смысловую последовательность')]]:[['new-doc','FilePlus',(globalThis.HubI18n?.t?.("knowledge.9d5fecb3d309") ?? 'Создать страницу'),(globalThis.HubI18n?.t?.("knowledge.0981c73c8915") ?? 'Добавить статью в выбранный раздел')],['import','FolderInput',(globalThis.HubI18n?.t?.("knowledge.ad317ef5316b") ?? 'Импортировать статьи'),(globalThis.HubI18n?.t?.("knowledge.3115c8dce126") ?? 'Предпросмотр Markdown и текста')]]).concat([['policy','Settings2',(globalThis.HubI18n?.t?.("knowledge.9271ccf19216") ?? 'Настройки знаний'),(globalThis.HubI18n?.t?.("knowledge.932059352b8e") ?? 'Компоненты, точки входа и правила анализа')],['export','Download',(globalThis.HubI18n?.t?.("knowledge.1f67cc552aef") ?? 'Экспорт ZIP'),(globalThis.HubI18n?.t?.("knowledge.9149d8d7ee7d") ?? 'Документация и архитектурные факты')],['export-public','Globe',(globalThis.HubI18n?.t?.("knowledge.b00a2d5a1f74") ?? 'Публичный ZIP'),(globalThis.HubI18n?.t?.("knowledge.0a2e2121f639") ?? 'Только согласованные публичные статьи')],['backup','Archive',(globalThis.HubI18n?.t?.("knowledge.9eb508eda2fc") ?? 'Резервная копия'),(globalThis.HubI18n?.t?.("knowledge.0c0cb4d8201a") ?? 'Полная копия базы знаний')]]).map(([action,name,title,description])=>`<button data-k-action="${action}">${icon(name)}<strong>${title}</strong><small>${description}</small></button>`).join('')}</div>`),(globalThis.HubI18n?.t?.("knowledge.4e90074f740b") ?? 'Инструменты'));
    if (v.panel==='policy') return dialog(v,(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.543cdba16383",{v0:(icon('X')),v1:(v.context?.policy?.components?.length||0),v2:(v.context?.policy?.entrypoints?.length||0),v3:(esc((v.context?.policy?.sections||[]).join(' · ')||(globalThis.HubI18n?.t?.("knowledge.9d9561c0bf9f") ?? 'Пока не заданы'))),v4:(icon('Code')),v5:(esc(v.policyDraft || JSON.stringify(v.context?.policy||{},null,2))),v6:(v.busy?' disabled':''),v7:(icon('Save'))}) : `<header class="k-inspector-head"><h2>Настройки знаний</h2><button data-k-action="close-panel">${icon('X')}Закрыть</button></header><p>Правила анализа и структура разделов этого проекта. Изменения правил применяются при следующем сканировании.</p><dl class="k-policy-summary"><dt>Компоненты</dt><dd>${v.context?.policy?.components?.length||0}</dd><dt>Точки входа</dt><dd>${v.context?.policy?.entrypoints?.length||0}</dd><dt>Разделы документации</dt><dd>${esc((v.context?.policy?.sections||[]).join(' · ')||(globalThis.HubI18n?.t?.("knowledge.9d9561c0bf9f") ?? 'Пока не заданы'))}</dd></dl><details><summary>${icon('Code')}Редактировать правила анализа</summary><p>Компоненты задают смысловые блоки и пути исходников. Точки входа задают начало обзора. Исключённые каталоги не сканируются.</p><label>Конфигурация проекта<textarea data-k-policy rows="12" spellcheck="false">${esc(v.policyDraft || JSON.stringify(v.context?.policy||{},null,2))}</textarea></label><button data-k-action="save-policy"${v.busy?' disabled':''}>${icon('Save')}Сохранить настройки</button></details>`),(globalThis.HubI18n?.t?.("knowledge.9271ccf19216") ?? 'Настройки знаний'));
    if (v.panel==='import') return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.e3b9f87518c5",{v0:(esc(v.importPaths||'')),v1:(v.busy?' disabled':''),v2:(v.imports?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.8f568f9af4e0",{v0:(esc(v.imports.id)),v1:(v.imports.revision),v2:(v.imports.items.map(row=>`<article><h3>${esc(row.item.title)} · ${esc(row.action)}</h3><p>${esc(row.item.sources?.[0]?.path)}</p>${row.action==='review'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.28d1d87dba87",{v0:(esc(row.item.id)),v1:(v.importSelections?.has(row.item.id)?' checked':''),v2:(esc(row.diff))}) : `<label class="k-check"><input type="checkbox" data-k-import-select="${esc(row.item.id)}"${v.importSelections?.has(row.item.id)?' checked':''}>Применить проверенное обновление</label><pre>${esc(row.diff)}</pre>`):''}${incompleteSources(row.item)}<details><summary>${row.item.format==='html'?(globalThis.HubI18n?.t?.("knowledge.be9e952a96bf") ?? 'HTML-комплект'):(globalThis.HubI18n?.t?.("knowledge.4f0548d13284") ?? 'Статья')}</summary>${row.item.format==='html'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.79475f6362fd",{v0:(esc(row.item.description||'')),v1:(row.item.htmlBundle?.files?.length||0),v2:(row.item.externalResources?.length?(globalThis.HubI18n?.t?.("knowledge.e3991bad15d9") ?? '<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>'):'')}) : `<p>${esc(row.item.description||'')}</p><p>Сохранено файлов: ${row.item.htmlBundle?.files?.length||0}. Просмотр доступен после импорта.</p>${row.item.externalResources?.length?(globalThis.HubI18n?.t?.("knowledge.e3991bad15d9") ?? '<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>'):''}`):`<div class="k-markdown">${markdown(v,row.item)}</div>`}</details></article>`).join('')),v3:(v.busy?' disabled':'')}) : `<p>Предпросмотр ${esc(v.imports.id)} · версия ${v.imports.revision}. Новые статьи будут добавлены. Обновления существующих статей требуют выбора.</p>${v.imports.items.map(row=>`<article><h3>${esc(row.item.title)} · ${esc(row.action)}</h3><p>${esc(row.item.sources?.[0]?.path)}</p>${row.action==='review'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.28d1d87dba87",{v0:(esc(row.item.id)),v1:(v.importSelections?.has(row.item.id)?' checked':''),v2:(esc(row.diff))}) : `<label class="k-check"><input type="checkbox" data-k-import-select="${esc(row.item.id)}"${v.importSelections?.has(row.item.id)?' checked':''}>Применить проверенное обновление</label><pre>${esc(row.diff)}</pre>`):''}${incompleteSources(row.item)}<details><summary>${row.item.format==='html'?(globalThis.HubI18n?.t?.("knowledge.be9e952a96bf") ?? 'HTML-комплект'):(globalThis.HubI18n?.t?.("knowledge.4f0548d13284") ?? 'Статья')}</summary>${row.item.format==='html'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.79475f6362fd",{v0:(esc(row.item.description||'')),v1:(row.item.htmlBundle?.files?.length||0),v2:(row.item.externalResources?.length?(globalThis.HubI18n?.t?.("knowledge.e3991bad15d9") ?? '<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>'):'')}) : `<p>${esc(row.item.description||'')}</p><p>Сохранено файлов: ${row.item.htmlBundle?.files?.length||0}. Просмотр доступен после импорта.</p>${row.item.externalResources?.length?(globalThis.HubI18n?.t?.("knowledge.e3991bad15d9") ?? '<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>'):''}`):`<div class="k-markdown">${markdown(v,row.item)}</div>`}</details></article>`).join('')}<button data-k-action="import-apply"${v.busy?' disabled':''}>Применить проверенный импорт</button>`):'')}) : `<section class="k-auxiliary"><h2>Импорт Markdown / HTML / текста</h2><label>Относительные пути (по одному в строке)<textarea data-k-paths rows="4">${esc(v.importPaths||'')}</textarea></label><button data-k-action="import-preview"${v.busy?' disabled':''}>Подготовить предпросмотр</button><button data-k-action="close-panel">Закрыть</button>
      ${v.imports?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.8f568f9af4e0",{v0:(esc(v.imports.id)),v1:(v.imports.revision),v2:(v.imports.items.map(row=>`<article><h3>${esc(row.item.title)} · ${esc(row.action)}</h3><p>${esc(row.item.sources?.[0]?.path)}</p>${row.action==='review'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.28d1d87dba87",{v0:(esc(row.item.id)),v1:(v.importSelections?.has(row.item.id)?' checked':''),v2:(esc(row.diff))}) : `<label class="k-check"><input type="checkbox" data-k-import-select="${esc(row.item.id)}"${v.importSelections?.has(row.item.id)?' checked':''}>Применить проверенное обновление</label><pre>${esc(row.diff)}</pre>`):''}${incompleteSources(row.item)}<details><summary>${row.item.format==='html'?(globalThis.HubI18n?.t?.("knowledge.be9e952a96bf") ?? 'HTML-комплект'):(globalThis.HubI18n?.t?.("knowledge.4f0548d13284") ?? 'Статья')}</summary>${row.item.format==='html'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.79475f6362fd",{v0:(esc(row.item.description||'')),v1:(row.item.htmlBundle?.files?.length||0),v2:(row.item.externalResources?.length?(globalThis.HubI18n?.t?.("knowledge.e3991bad15d9") ?? '<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>'):'')}) : `<p>${esc(row.item.description||'')}</p><p>Сохранено файлов: ${row.item.htmlBundle?.files?.length||0}. Просмотр доступен после импорта.</p>${row.item.externalResources?.length?(globalThis.HubI18n?.t?.("knowledge.e3991bad15d9") ?? '<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>'):''}`):`<div class="k-markdown">${markdown(v,row.item)}</div>`}</details></article>`).join('')),v3:(v.busy?' disabled':'')}) : `<p>Предпросмотр ${esc(v.imports.id)} · версия ${v.imports.revision}. Новые статьи будут добавлены. Обновления существующих статей требуют выбора.</p>${v.imports.items.map(row=>`<article><h3>${esc(row.item.title)} · ${esc(row.action)}</h3><p>${esc(row.item.sources?.[0]?.path)}</p>${row.action==='review'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.28d1d87dba87",{v0:(esc(row.item.id)),v1:(v.importSelections?.has(row.item.id)?' checked':''),v2:(esc(row.diff))}) : `<label class="k-check"><input type="checkbox" data-k-import-select="${esc(row.item.id)}"${v.importSelections?.has(row.item.id)?' checked':''}>Применить проверенное обновление</label><pre>${esc(row.diff)}</pre>`):''}${incompleteSources(row.item)}<details><summary>${row.item.format==='html'?(globalThis.HubI18n?.t?.("knowledge.be9e952a96bf") ?? 'HTML-комплект'):(globalThis.HubI18n?.t?.("knowledge.4f0548d13284") ?? 'Статья')}</summary>${row.item.format==='html'?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.79475f6362fd",{v0:(esc(row.item.description||'')),v1:(row.item.htmlBundle?.files?.length||0),v2:(row.item.externalResources?.length?(globalThis.HubI18n?.t?.("knowledge.e3991bad15d9") ?? '<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>'):'')}) : `<p>${esc(row.item.description||'')}</p><p>Сохранено файлов: ${row.item.htmlBundle?.files?.length||0}. Просмотр доступен после импорта.</p>${row.item.externalResources?.length?(globalThis.HubI18n?.t?.("knowledge.e3991bad15d9") ?? '<p>Внешние ресурсы заблокированы в изолированном просмотре.</p>'):''}`):`<div class="k-markdown">${markdown(v,row.item)}</div>`}</details></article>`).join('')}<button data-k-action="import-apply"${v.busy?' disabled':''}>Применить проверенный импорт</button>`):''}</section>`);
    return '';
  }
  function jobNotice(v) {
    const jobs=(v.context?.jobs||[]).filter(j=>j.kind!=='research'),ongoing=jobs.find(job=>['queued','running'].includes(job.state)),latest=jobs.find(job=>!['queued','running'].includes(job.state));
    const selected=[ongoing,latest].filter(Boolean);
    const labels={queued:(globalThis.HubI18n?.t?.("knowledge.ef9743554af1") ?? 'ожидает запуска'),running:(globalThis.HubI18n?.t?.("knowledge.bd280ebe5bda") ?? 'выполняется'),ready:(globalThis.HubI18n?.t?.("knowledge.5f9b6607de24") ?? 'завершено'),partial:(globalThis.HubI18n?.t?.("knowledge.de2280e6a5a0") ?? 'завершено с ограничениями'),failed:(globalThis.HubI18n?.t?.("knowledge.44d4090ae9e4") ?? 'ошибка'),interrupted:(globalThis.HubI18n?.t?.("knowledge.a13c37d406f5") ?? 'прервано'),stale:(globalThis.HubI18n?.t?.("knowledge.2f41c01eefa1") ?? 'исходники изменились')};
    const counts={files:(globalThis.HubI18n?.t?.("knowledge.7e1ad316f1c8") ?? 'файлов'),types:(globalThis.HubI18n?.t?.("knowledge.69b406975445") ?? 'типов'),parsed:(globalThis.HubI18n?.t?.("knowledge.9f0347ed213d") ?? 'файлов разобрано'),reused:(globalThis.HubI18n?.t?.("knowledge.857dc0885665") ?? 'файлов без изменений')};
    return selected.map(job=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.cecac946bcac",{v0:(['failed','partial','interrupted','stale'].includes(job.state)?' k-warning':''),v1:(esc(labels[job.state]||job.state)),v2:(job.counts?`<span class="k-scan-counts">${Object.entries(counts).filter(([field])=>Number.isFinite(job.counts[field])).map(([field,label])=>`${label}: ${job.counts[field]}`).join(' · ')}</span>`:''),v3:(job.finishedAt?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.e57bedc663c1",{v0:(esc(job.finishedAt))}) : `<small>Завершено: ${esc(job.finishedAt)}</small>`):''),v4:(job.error?`<p>${esc(job.error)}</p>`:''),v5:(job.state==='stale'?(globalThis.HubI18n?.t?.("knowledge.711307095bed") ?? '<p>Исходники или политика изменились во время сканирования; повторите обновление.</p>'):''),v6:(job.diagnostics?.length?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.fadbaebe858b",{v0:(job.diagnostics.length),v1:(job.diagnostics.slice(0,20).map(d=>`<p>${esc(d.path)} · ${esc(d.message)}</p>`).join(''))}) : `<details><summary>Ограничения / диагностика (${job.diagnostics.length})</summary>${job.diagnostics.slice(0,20).map(d=>`<p>${esc(d.path)} · ${esc(d.message)}</p>`).join('')}</details>`):'')}) : `<div class="k-job${['failed','partial','interrupted','stale'].includes(job.state)?' k-warning':''}" role="status"><strong>Сканирование: ${esc(labels[job.state]||job.state)}</strong>${job.counts?`<span class="k-scan-counts">${Object.entries(counts).filter(([field])=>Number.isFinite(job.counts[field])).map(([field,label])=>`${label}: ${job.counts[field]}`).join(' · ')}</span>`:''}${job.finishedAt?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.e57bedc663c1",{v0:(esc(job.finishedAt))}) : `<small>Завершено: ${esc(job.finishedAt)}</small>`):''}${job.error?`<p>${esc(job.error)}</p>`:''}${job.state==='stale'?(globalThis.HubI18n?.t?.("knowledge.711307095bed") ?? '<p>Исходники или политика изменились во время сканирования; повторите обновление.</p>'):''}${job.diagnostics?.length?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.fadbaebe858b",{v0:(job.diagnostics.length),v1:(job.diagnostics.slice(0,20).map(d=>`<p>${esc(d.path)} · ${esc(d.message)}</p>`).join(''))}) : `<details><summary>Ограничения / диагностика (${job.diagnostics.length})</summary>${job.diagnostics.slice(0,20).map(d=>`<p>${esc(d.path)} · ${esc(d.message)}</p>`).join('')}</details>`):''}</div>`)).join('');
  }
  function capabilitiesNotice(v) {
    const capabilities=v.context.jobs?.find(job=>job.capabilities)?.capabilities||v.context.capabilities?.languages||{};
    const titles={python:'Python',java:'Java',other:(globalThis.HubI18n?.t?.("knowledge.ff17c05a6302") ?? 'Другие языки'),javascript:'JavaScript',typescript:'TypeScript'};
    return Object.entries(capabilities).map(([language,value])=> {
      const details=Array.isArray(value)?value:String(value).split(',');
      const types=details.some(x=>['types','interfaces','declared-inheritance','types-with-local-jdk'].includes(x));
      return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.aeeb48c2d323",{v0:(esc(titles[language]||language)),v1:(types?(globalThis.HubI18n?.t?.("knowledge.2d42bdaac217") ?? 'файлы, классы и объявленные связи типов'):(globalThis.HubI18n?.t?.("knowledge.dab0b47de1d8") ?? 'инвентаризация файлов; подробные связи типов не извлекаются')),v2:(details.includes('entrypoints')?(globalThis.HubI18n?.t?.("knowledge.f7c42e060eb5") ?? ' и точки входа'):''),v3:(details.includes('types-with-local-jdk')?(globalThis.HubI18n?.t?.("knowledge.586a82dbf5c4") ?? ' при доступном локальном JDK; фактическое покрытие показывает последнее сканирование'):'')}) : `<p><strong>${esc(titles[language]||language)}:</strong> ${types?(globalThis.HubI18n?.t?.("knowledge.2d42bdaac217") ?? 'файлы, классы и объявленные связи типов'):(globalThis.HubI18n?.t?.("knowledge.dab0b47de1d8") ?? 'инвентаризация файлов; подробные связи типов не извлекаются')}${details.includes('entrypoints')?(globalThis.HubI18n?.t?.("knowledge.f7c42e060eb5") ?? ' и точки входа'):''}${details.includes('types-with-local-jdk')?(globalThis.HubI18n?.t?.("knowledge.586a82dbf5c4") ?? ' при доступном локальном JDK; фактическое покрытие показывает последнее сканирование'):''}. Методы и динамические вызовы не анализируются.</p>`);
    }).join('')||(globalThis.HubI18n?.t?.("knowledge.a36142871b6f") ?? '<p>Возможности адаптеров пока не получены. Запустите сканирование.</p>');
  }
  function captureNavigatorScroll(v,root) {
    if(v.mode!=='architecture'||!root?.isConnected)return;
    const participants=root.querySelector('[data-k-participants]');if(participants?.closest?.('details')?.open)v.navigatorScroll.participants={top:participants.scrollTop,left:participants.scrollLeft};
    const catalog=root.querySelector('.k-catalog'),mode=catalog?.dataset.kBrowserMode,pane=catalog?.querySelector?.('.r-tree')||catalog;if(!mode)return;
    const previous=mounted?.navigatorScroll;
    const top=pane.scrollTop,left=pane.scrollLeft;
    // A short/loading list may clamp a restored offset. Keep the requested
    // position until the user scrolls, so the next data redraw can restore it.
    if(previous?.pane===pane&&previous.top===top&&previous.left===left)return;
    v.navigatorScroll[mode]={top,left};mounted.navigatorScroll={pane,top,left};
  }
  function restoreNavigatorScroll(v,root) {
    if(v.mode!=='architecture')return;
    const catalog=root.querySelector('.k-catalog'),mode=catalog?.dataset.kBrowserMode,pane=catalog?.querySelector?.('.r-tree')||catalog;if(!mode)return;
    const position=v.navigatorScroll[mode];
    if(position){pane.scrollTop=position.top;pane.scrollLeft=position.left;}
    mounted.navigatorScroll={pane,top:pane.scrollTop,left:pane.scrollLeft};
  }
  function draw(v,state=null) {
    if (!active(v)||v.snapshotOwner) return;
    if(v.__researchHost)window.KnowledgeResearch?.closeMenu?.(v);
    if(!state&&v.cameraInitialized&&mounted.cy&&mounted.cy.knowledgeKey===graphKey(v))state=canvasState(v);
    captureNavigatorScroll(v,mounted.root);
    const previousPanel=v.mode==='architecture'?mounted.root.querySelector('.k-graph-panel'):null;
    const previousNavigator=v.mode==='architecture'?mounted.root.querySelector('.k-catalog'):null;
    const retainNavigator=!!previousNavigator&&unchangedNavigator(v);
    const waiting=v.loading||v.researchLoading;
    const retainGraph=!!previousPanel&&!!mounted.cy&&(waiting||mounted.cy.knowledgeKey===graphKey(v)&&!state?.relayout);
    window.KnowledgeWorkspace?.dispose(mounted.root);if(!retainGraph)destroyGraph();
    const root=mounted.root, focus=document.activeElement;
    const savedUi=window.HubLiveUI?.capture(root);
    const field=root.contains(focus) ? ['kField','kFilter','kPolicy','kPaths'].find(name=>focus?.dataset?.[name]!==undefined) : null;
    const focusValue=field ? focus.dataset[field] : null, start=focus?.selectionStart, end=focus?.selectionEnd;
    const draft=v.drafts.get(v.selected);
    const documentContent=v.mode==='docs'?(draft?documentPanel(v,draft):(globalThis.HubI18n?.t?.("knowledge.e0f7cfbbb6eb") ?? '<article class="k-empty"><h2>Выберите статью</h2><p>Создайте документ или подготовьте импорт существующего Markdown.</p></article>')):null;
    const content=v.mode==='docs'&&window.DocumentationUI?window.DocumentationUI.layout(v,documentContent):
      `${v.mode==='docs'?toolbar(v):(window.KnowledgeResearch?.service(v)||'')}<div class="k-layout">${retainNavigator?'<aside data-k-navigator-slot></aside>':catalog(v)}${v.mode==='docs'?documentContent:architecturePanel(v,draft)}</div>`;
    const html=`${v.error?`<p class="k-warning" role="alert">${esc(v.error)}</p>`:''}${v.notice?`<p role="status">${esc(v.notice)}</p>`:''}
      ${v.mode==='architecture'?'':(globalThis.HubI18n?.t ? globalThis.HubI18n.t("knowledge.c9bf2e79c3ef",{v0:(v.context?.revision ?? '…'),v1:(v.loading?(globalThis.HubI18n?.t?.("knowledge.aae8a7b9edfb") ?? ' · Загрузка…'):''),v2:(v.busy?(globalThis.HubI18n?.t?.("knowledge.d34b06e43b75") ?? ' · Сохранение…'):'')}) : `<div class="k-status" role="status">Версия знаний: ${v.context?.revision ?? '…'}${v.loading?(globalThis.HubI18n?.t?.("knowledge.aae8a7b9edfb") ?? ' · Загрузка…'):''}${v.busy?(globalThis.HubI18n?.t?.("knowledge.d34b06e43b75") ?? ' · Сохранение…'):''}</div>`)}
      ${v.context&&v.listRevision!==v.context.revision?(globalThis.HubI18n?.t?.("knowledge.88946f395190") ?? '<p class="k-warning">Список и контекст получены из разных версий. Обновите перед редактированием.</p>'):''}
      ${v.mode==='architecture'?'':debtNotice(v)}${modalAuxiliary(v)}${content}`;
    const body=root.querySelector('[data-k-body]'),oldLayout=root.querySelector('.k-layout'),oldMain=root.querySelector('.k-architecture-main');
    // Leave the potentially thousands-row navigator attached to the document.
    // Reattaching retained rows still rebuilds the browser accessibility tree.
    const incremental=previousNavigator&&oldLayout&&oldMain&&document.createElement;
    const renderRoot=incremental?document.createElement('div'):root;
    if(incremental)renderRoot.innerHTML=html;
    else if(window.HubLiveUI&&v.mode==='docs')window.HubLiveUI.patch(body,html,{preserveInputs:false});
    else body.innerHTML=html;
    if(retainNavigator&&!incremental)root.querySelector('[data-k-navigator-slot]')?.replaceWith(previousNavigator);
    // Keep the viewport frame mounted. Dialogs, status and navigator updates
    // reuse its renderer; a changed graph replaces only the graph contents.
    const nextPanel=previousPanel&&renderRoot.querySelector('.k-graph-panel');
    if(nextPanel){
      if(!waiting){
        previousPanel.className=nextPanel.className;
        for(const name of ['role','aria-label']){const value=nextPanel.getAttribute(name);if(value===null)previousPanel.removeAttribute(name);else previousPanel.setAttribute(name,value);}
        const children=[...nextPanel.children].map(child=>{
          const stable=child.matches('.r-graph-toolbar,.r-canvas-caption')?previousPanel.querySelector(child.matches('.r-graph-toolbar')?'.r-graph-toolbar':'.r-canvas-caption'):null;
          if(stable){if(stable.innerHTML!==child.innerHTML)stable.innerHTML=child.innerHTML;return stable;}
          if(retainGraph)return previousPanel.querySelector(child.matches('[data-k-cy]')?'[data-k-cy]':child.matches('[data-k-node-actions]')?'[data-k-node-actions]':child.matches('[data-k-canvas-selection]')?'[data-k-canvas-selection]':':not(*)')||child;
          return child;
        });
        // Cytoscape observes removal of its container from this panel. Even
        // removing and reinserting the same element destroys its renderer.
        if(!retainGraph)previousPanel.replaceChildren(...children);
      }
      nextPanel.replaceWith(previousPanel);previousPanel.classList.toggle('r-refreshing',!!waiting);previousPanel.setAttribute('aria-busy',String(!!waiting));
      if(waiting){const status=previousPanel.querySelector('[data-r-research-status]');if(status){status.hidden=false;status.textContent=(globalThis.HubI18n?.t?.("knowledge.4e41077fa07f") ?? 'Открываем раздел · ')+(draft?.item.title||(globalThis.HubI18n?.t?.("knowledge.d04f6d2cd09a") ?? 'Получаем данные…'));}}
    }
    if(incremental){
      const nextLayout=renderRoot.querySelector('.k-layout'),nextMain=renderRoot.querySelector('.k-architecture-main');
      if(!retainNavigator)previousNavigator.replaceWith(nextLayout.querySelector('.k-catalog'));
      oldMain.replaceWith(nextMain);
      for(const child of [...body.children])if(child!==oldLayout)child.remove();
      for(const child of [...renderRoot.children])if(child!==nextLayout)body.insertBefore(child,oldLayout);
    }
    if (field) {
      const attr=field.replace(/[A-Z]/g,c=>'-'+c.toLowerCase());
      const target=[...root.querySelectorAll('[data-'+attr+']')].find(el=>el.dataset[field]===focusValue);
      if (target) { target.focus({preventScroll:true}); if (typeof start==='number' && target.setSelectionRange && !['number','checkbox'].includes(target.type)) { try { target.setSelectionRange(start,end); } catch (_) {} } }
    }
    if(v.mode==='architecture')window.KnowledgeResearch?.mounted(v);
    window.KnowledgeWorkspace?.mount(root,v);if(!retainGraph)mountGraph(v,state);
    observeRoleDescription(v);
    restoreNavigatorScroll(v,root);
    if(!v.loading)followNavigator(v);
    if(v.mode==='architecture')rememberNavigator(v);
    root.__knowledgeCy=mounted.cy;
    window.HubLiveUI?.restore(root,savedUi);
    if(v.mode==='architecture')window.HubSubsystems?.mount(v,subsystemHost(v));
  }
  function subsystemHost(v){return {root:()=>mounted.root,request:(a,b,w)=>request(v,a,b,w),refresh:()=>refresh(v),draw:()=>draw(v),openResearch:options=>window.KnowledgeResearch?.openAgentDialog(v,options)};}
  function modalAuxiliary(v){const html=auxiliary(v);if(!html||html.startsWith('<div class="k-dialog-backdrop"'))return html;return dialog(v,html.replace(/^<section class="k-auxiliary">/,'').replace(/<\/section>$/,''),v.panel==='policy'?(globalThis.HubI18n?.t?.("knowledge.9271ccf19216") ?? 'Настройки знаний'):(globalThis.HubI18n?.t?.("knowledge.bce74bf988d4") ?? 'Импорт статей'));}
  function viewport(v) {
    updateGraphViewport(v);
    if(active(v)&&mounted.cy)mounted.cy.viewport({pan:{x:v.viewport.x,y:v.viewport.y},zoom:v.viewport.scale});
    persist(v);
  }
  async function save(v,id=v.selected) {
    const draft=v.drafts.get(id); if (!draft || v.busy) return;
    draft.request ||= {expected:draft.expected,key:key(),operations:[{op:'put',item:copy(draft.item)}],reason:'Edit '+draft.item.kind+' '+draft.item.id};
    v.busy=true; draw(v);
    try {
      const result=await request(v,'changeset',draft.request,true);
      if (!active(v)) return;
      draft.expected=result.revision; draft.dirty=false; draft.request=null; v.notice=(globalThis.HubI18n?.t?.("knowledge.bc6976f996ab") ?? 'Сохранена версия ')+result.revision;
      await refresh(v);
    } catch (error) { fail(v,error); }
    finally { v.busy=false; if (active(v)) draw(v); }
  }
  async function mutation(v, action, args) {
    if (v.busy) return null;
    v.busy=true; v.error=''; draw(v);
    try { const result=await request(v,action,args,true); if (!active(v)) return null; return result; }
    catch (error) { fail(v,error); return null; }
    finally { v.busy=false; if (active(v)) draw(v); }
  }
  async function action(v, name, target) {
    if(['doc-links-all','doc-links-collapse','doc-links-retry'].includes(name)){
      const item=v.drafts.get(v.selected)?.item;if(v.mode!=='docs'||!item)return;
      const state=docLinkState(v,item);
      if(name==='doc-links-retry'){for(const [id,entry] of v.linkedEntities)if(entry.state==='error')v.linkedEntities.delete(id);}
      else state.expanded=name==='doc-links-all';
      updateDocumentLinks(v,item);await resolveDocLinks(v,item);return;
    }
    if(name==='expand-branch'){await expandCanvas(v,v.filters.expandMode||'structure');return;}
    if(name==='expand-direct'){v.filters.expandMode=target.dataset.kBranchMode;persist(v);await expandCanvas(v,v.filters.expandMode);return;}
    if(name==='more-code'){v.filters.codeLimit=(Number(v.filters.codeLimit)||PAGE)+PAGE;v.autoLayout=false;await refresh(v);return;}
    if(name==='more-branch'){await expandCanvas(v,v.filters.expandMode||'structure',true);return;}
    if(name==='collapse-branch'){if(window.ArchitectureMap&&v.canvasItem){const id=v.canvasItem,state=canvasState(v);window.ArchitectureMap.collapse(v,id,baseGraphModel(v));if(state)state.relayout=true;draw(v,state);const node=mounted.cy?.getElementById(id);if(node?.length){node.select();updateCanvasSelection(v,mounted.cy,node);}}return;}
    if(name==='diagnostics'||name==='tools'){v.panel=name;draw(v);return;}
    if(name==='edit-role-description'){
      const id=target?.dataset?.kRoleId||v.selected,item=(v.canvasInspect?.id===id?v.canvasInspect:null)||v.drafts.get(id)?.item,revision=v.context?.revision;
      if(!item)return;
      try{await readInspectorItem(v,item);}catch(error){if(active(v))fail(v,error);return;}
      if(!active(v)||v.context?.revision!==revision||(v.canvasItem||v.selected)!==id)return;
      v.roleEditId=id;v.panel='role-description';draw(v);return;
    }
    if(name==='toggle-role-description'){const id=target?.dataset?.kRoleId||v.selected;v.roleExpanded||={};v.roleExpanded[id]=!v.roleExpanded[id];draw(v);return;}
    if(name==='toggle-inspector'){v.filters.inspectorCollapsed=inspectorVisible(v);persist(v);draw(v);const node=mounted.cy?.getElementById(v.canvasItem||'');if(node?.length)updateCanvasSelection(v,mounted.cy,node);return;}
    if(name==='return-architecture'){if(v.returnArchitecture?.project===v.project)location.hash=link('architecture',v.returnArchitecture.selected);return;}
    if(name==='focus'){focusCanvas(v);return;}
    if(name==='open-canvas'){if(v.canvasItem)openCanvasItem(v,v.canvasItem);return;}
    if(name==='clear-selection'){if(mounted.cy){mounted.cy.elements(':selected').unselect();updateCanvasSelection(v,mounted.cy);}return;}
    if(name==='auto-layout'){const cy=mounted?.cy;if(cy){const state=canvasState(v),selected=cy.elements(':selected'),single=selected.length===1&&selected[0].isNode(),anchor=single?selected[0].id():'',anchorScreen=single?{...selected[0].renderedPosition()}:null;v.positionCache.delete(cy.knowledgeKey);cy.knowledgeKey=graphKey(v);layoutGraph(v,cy,null,state.camera,{preserveCamera:true,liveCamera:true,anchor,anchorScreen,focusIds:single?[]:selected.map(e=>e.id())});}return;}
    if(name==='reset-filters'){const state=canvasState(v);v.filters.hiddenTypes=[];v.filters.hiddenRelations=[];v.filters.edgeDirection='all';v.filters.edgeAnchor='';persist(v);draw(v,state);return;}
    if(name==='follow-selection'){v.filters.followSelection=v.filters.followSelection===false;persist(v);const button=mounted.root.querySelector('[data-k-action="follow-selection"]');button?.setAttribute('aria-pressed',String(v.filters.followSelection));followNavigator(v);return;}
    if(name==='component-root'){chooseGraphItem(v,'');return;}
    if(name==='toggle-list'){v.filters.listCollapsed=!v.filters.listCollapsed;persist(v);draw(v);return;}
    if(name==='graph-back'||name==='graph-forward')return navigateGraph(v,name==='graph-back'?-1:1);
    if (name==='refresh') return refresh(v);
    if (name==='more') return refresh(v,true);
    if (name==='policy') { v.panel='policy'; v.policyDraft=JSON.stringify(v.context?.policy||{},null,2); v.policyExpected=v.context?.revision; v.policyRequest=null; }
    if (name==='import') { v.panel='import'; }
    if (name==='close-panel') {v.panel='';v.roleEditId='';}
    if (name==='new-doc'||name==='new-view') {
      if (!v.context) return;
      const id=(name==='new-doc'?'doc:':'view:')+key().slice(3), item=name==='new-doc'?
        {id,kind:'document',type:'explanation',title:(globalThis.HubI18n?.t?.("knowledge.15c048a3c028") ?? 'Новая статья'),markdown:'',audience:v.filters.audience||v.context.policy.audiences?.[0]||'',section:v.filters.section||'',status:'draft',visibility:'internal',entityRefs:[]}:
        {id,kind:'view',title:(globalThis.HubI18n?.t?.("knowledge.6b3110d5a472") ?? 'Новый сценарий'),viewType:'scenario',description:'',nodeIds:[],orderedEdges:[],provenance:'authored'};
      recordGraph(v);v.selected=id;recordGraph(v); v.drafts.set(id,{item,expected:v.context.revision,dirty:true}); v.editing=true; v.history=null; v.historical=null; v.linkedDocs=[];
      history.replaceState(null,'',link(v.mode,id)); persist(v);
    }
    if (name==='edit') v.editing=!v.editing;
    if (name==='preview') v.preview=!v.preview;
    if (name==='discard') {
      if (!window.confirm((globalThis.HubI18n?.t?.("knowledge.5c38acb40bab") ?? 'Загрузить сохранённую версию и отменить изменения этого черновика?'))) return;
      v.drafts.delete(v.selected); return loadItem(v,v.selected);
    }
    if (name==='save') return save(v,target?.dataset?.kRoleId||v.selected);
    if (name==='save-description') {const id=v.roleEditId||v.selected;v.panel='';v.roleEditId='';return save(v,id);}
    if (name==='save-policy') {
      try {
        const policy=JSON.parse(v.policyDraft || '{}');
        v.policyRequest ||= {expected:v.policyExpected,key:key(),operations:[],policy,reason:'Update project knowledge policy'};
        const receipt=await mutation(v,'changeset',v.policyRequest);
        if (receipt) {v.panel='';v.policyRequest=null;return refresh(v);}
      } catch (error) { fail(v,error); }
    }
    if (name==='import-preview') {
      const preview=await mutation(v,'import-preview',{paths:String(v.importPaths||'').split('\n').map(x=>x.trim()).filter(Boolean)});
      if (preview) {v.imports=preview;v.importSelections=new Set();v.importRequest=null;}
    }
    if (name==='import-apply' && v.imports) {
      v.importRequest ||= {identifier:v.imports.id,expected:v.imports.revision,key:key(),selections:[...(v.importSelections||[])]};
      const result=await mutation(v,'import-apply',v.importRequest);
      if (result) {v.panel='';v.imports=null;v.importRequest=null;return refresh(v);}
    }
    if (name==='history'||name==='history-more') {
      const id=target?.dataset?.kRoleId||(name==='history-more'?v.historyId:null)||v.selected, generation=++v.detailSequence;v.historyId=id;
      try {
        const result=await request(v,'history',{id,offset:name==='history-more'?v.history?.next||0:0,limit:20});
        if (active(v)&&id===v.historyId&&generation===v.detailSequence) v.history=name==='history-more'?{...result,items:[...(v.history?.items||[]),...result.items]}:result;
      } catch(error) {fail(v,error);}
    }
    if(name==='compare'&&v.historical?.item.kind==='document') {
      if(v.comparing)return;
      const historical=v.historical,id=v.selected,generation=++v.detailSequence;
      v.comparing=true;v.comparison=null;draw(v);
      try {
        // Read the actual saved article, never the potentially dirty draft.
        const current=await request(v,'read',{id});
        if(active(v)&&generation===v.detailSequence&&id===v.selected&&v.historical===historical) {
          const html=historical.item.format==='html'||current.format==='html';
          const text=item=>html?window.HtmlDocuments.comparisonText(item):item.markdown;
          v.comparison={revision:historical.revision,html,diff:changedFragment(text(historical.item),text(current))};
        }
      } catch(error){fail(v,error);}
      finally {if(active(v)&&generation===v.detailSequence){v.comparing=false;draw(v);}}
    }
    if (name==='restore'&&v.historical) {
      if (v.drafts.get(v.selected)?.dirty&&!window.confirm((globalThis.HubI18n?.t?.("knowledge.0a4ff224e19a") ?? 'Восстановление заменит несохранённый черновик. Продолжить?'))) return;
      v.restoreRequest ||= {id:v.historical.item.id,revision:v.historical.revision,expected:v.context.revision,key:key()};
      const result=await mutation(v,'restore',v.restoreRequest);
      if (result) {v.drafts.delete(v.selected);v.historical=null;v.comparison=null;v.comparing=false;v.restoreRequest=null;v.notice=(globalThis.HubI18n?.t?.("knowledge.0fefa6110ff2") ?? 'Восстановлена новая версия ')+result.revision;return refresh(v);}
    }
    if (name==='scan') {
      if (!v.context) return;
      if(v.busy||(v.context.jobs||[]).some(j=>['queued','running'].includes(j.state))){v.analysisNotice=(globalThis.HubI18n?.t?.("knowledge.a7d7b46ca86e") ?? 'Сканирование уже запущено');updateAnalysisStatus(v);return;}
      v.analysisNotice=(globalThis.HubI18n?.t?.("knowledge.58d124f88027") ?? 'Запрашиваем сканирование…');updateAnalysisStatus(v);
      const result=await mutation(v,'scan',{});
      if (result) {v.context.jobs=[result,...(v.context.jobs||[]).filter(j=>j.id!==result.id)].slice(0,3);v.analysisNotice=(globalThis.HubI18n?.t?.("knowledge.fd540b659be9") ?? 'Сканирование: ')+(result.state==='running'?(globalThis.HubI18n?.t?.("knowledge.bd280ebe5bda") ?? 'выполняется'):(globalThis.HubI18n?.t?.("knowledge.ef9743554af1") ?? 'ожидает запуска'));updateAnalysisStatus(v);scheduleJob(v);}return;
    }
    if (name==='zoom-in'||name==='zoom-out') {v.viewport.scale=Math.min(4,Math.max(.01,v.viewport.scale*(name==='zoom-in'?1.2:1/1.2)));viewport(v);return;}
    if (name==='fit') {if(mounted.cy){sizeGraph(mounted.root.querySelector('[data-k-cy]'));mounted.cy.resize();mounted.cy.fit(undefined,32);captureCamera(v,mounted.cy);}return;}
    if (name==='export'||name==='export-public'||name==='backup') {
      // A browser download streams the portable artifact instead of putting
      // a whole backup/blob collection into an interactive API response.
      const url=new URL('/api/v1/knowledge/download',location.origin);
      url.search=new URLSearchParams({project:v.project,action:name==='backup'?'backup':'export',public:name==='export-public'?'true':'false'}).toString();
      const anchor=document.createElement('a');anchor.href=url.pathname+url.search;
      anchor.download='knowledge-'+v.project+(name==='backup'?'.json':'.zip');anchor.click();
      v.notice=name==='backup'?(globalThis.HubI18n?.t?.("knowledge.e5daf1f62bd8") ?? 'Запрошена резервная копия с историей и вложениями.'):name==='export-public'?(globalThis.HubI18n?.t?.("knowledge.4508afe8b724") ?? 'Запрошен ZIP только из ранее согласованных публичных статей. Внутренние связи и зависимости требуют отдельной проверки сервером.'):(globalThis.HubI18n?.t?.("knowledge.f5ea1454f52a") ?? 'Запрошен переносимый ZIP со статьями и вложениями.');
    }
    if (active(v)) draw(v);
  }
  function scheduleJob(v) {
    if (v.snapshotOwner||!active(v) || document.hidden || mounted.poll || mounted.polling) return;
    const job=(v.context?.jobs||[]).find(j=>j.kind!=='research'&&['queued','running'].includes(j.state)); if (!job) return;
    mounted.poll=setTimeout(async()=> {
      if (!active(v) || document.hidden) {if (mounted?.view===v) mounted.poll=null;return;}
      mounted.poll=null;mounted.polling=true;
      try {
        const result=await request(v,'job',{id:job.id});
        if (!active(v)) return;
        v.context.jobs=v.context.jobs.map(j=>j.id===result.id?result:j);
        if (!['queued','running'].includes(result.state)) await refresh(v); else updateAnalysisStatus(v);
      } catch(error) {fail(v,error);}
      finally {if (mounted?.view===v) {mounted.polling=false;scheduleJob(v);}}
    },1500);
  }
  function bind(v, root) {
    if(v.mode==='architecture'&&window.KnowledgeResearch){
      window.KnowledgeResearch.attach(v,{root:()=>root,active:()=>active(v),model:()=>graphModel(v),facts:()=>fullGraphModel(v),request:(a,b,w)=>request(v,a,b,w),draw:()=>draw(v),setNodeActionsHidden:hidden=>{const actions=root.querySelector('[data-k-node-actions]');if(actions){actions.hidden=hidden;if(!hidden)positionNodeActions(v,mounted.cy);}},resolveItem:item=>inspectorItem(v,item),updateInspector:()=>updateInspector(v),error:e=>{v.researchLoading=false;fail(v,e);},notice:text=>{v.notice=text;},record:()=>recordGraph(v),persist:()=>persist(v),loadSources:()=>loadCatalogTree(v),choose:(id,patch)=>chooseGraphItem(v,id,patch),setSelected:selected=>{window.KnowledgeResearch?.closeMenu?.(v);captureCamera(v,mounted.cy);v.sequence++;v.detailSequence++;v.canvasSelection=[];v.canvasItem='';v.canvasInspect=null;v.canvasStats=null;v.canvasGroupStats=null;selectItem(v,selected.id);v.drafts.set(selected.id,{item:selected,expected:v.context?.revision,dirty:false});mounted.selection=selected.id;v.loading=false;v.filters.graphMode='neighborhood';v.branchMaps?.clear();history.replaceState(null,'',link('architecture',selected.id));persist(v);},markResearch:ids=>{const cy=mounted.cy;if(cy){cy.nodes().removeClass('k-researching');for(const id of ids)cy.getElementById(id).addClass('k-researching');}},redrawLayout:id=>{const continuing=mounted.cy?.knowledgeOwner===v.selected;const state=continuing?canvasState(v)||{}:{resetCamera:true};state.anchor=v.canvasItem||id;const node=continuing&&mounted.cy?.getElementById(state.anchor);if(node?.length)state.anchorScreen={...node.renderedPosition()};state.relayout=true;v.autoLayout=false;draw(v,state);},saveMap:async(title,model,{resultId}={})=>{
        const nodes=model.nodes.filter(n=>n.type!=='group'&&n.provenance!=='presentation'&&!model.contextFrames?.has(n.id)),ids=new Set(nodes.map(n=>n.id)),edges=model.relations.filter(e=>ids.has(e.from)&&ids.has(e.to));
        const groups=model.presentationGroups||v.drafts.get(v.selected)?.item.presentationGroups;const saved=await request(v,'research-save',{expected:v.context.revision,key:key(),title,nodeIds:nodes.map(n=>n.id),edgeIds:edges.map(e=>e.id),...(groups?{presentationGroups:groups}:{}),...(resultId?{resultId}:{})},true);
        const [context,item]=await Promise.all([request(v,'context'),request(v,'read',{id:saved.id})]);if(!active(v))return saved;
        v.context=context;v.listRevision=context.revision;v.scenarios=[item,...(v.scenarios||[]).filter(n=>n.id!==item.id)];v.navigationCatalog=null;renderNavigator(v);
        // Saving this composition changes the DB revision, not its geometry.
        if(mounted.cy&&context.revision===saved.revision)mounted.cy.knowledgeKey=graphKey(v);
        return saved;
      },agentHistory:async(offset=0)=>{const url=new URL(mounted.options.projectApi?mounted.options.projectApi('/api/architecture-agent-history'):'/api/architecture-agent-history',location.origin);url.searchParams.set('project',v.project);url.searchParams.set('offset',offset);url.searchParams.set('limit',20);const response=await fetch(url.pathname+url.search,{signal:mounted.controller.signal}),result=await response.json();if(!response.ok)throw Error(result.message||result.error);return result;},agentInfo:async id=>{const url=new URL(mounted.options.projectApi?mounted.options.projectApi('/api/chat-actions'):'/api/chat-actions',location.origin);url.searchParams.set('project',v.project);url.searchParams.set('task','__research__:'+id);const response=await fetch(url.pathname+url.search,{signal:mounted.controller.signal}),result=await response.json();if(!response.ok)throw Error(result.message||result.error);return result;},agent:async research=>{const url=new URL(mounted.options.projectApi?mounted.options.projectApi('/api/v1/architecture-agent'):'/api/v1/architecture-agent',location.origin);url.searchParams.set('project',v.project);const response=await fetch(url.pathname+url.search,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({research:{operation:'architecture-analyze',objectId:research.id,...(research.providerId?{providerId:research.providerId}:{}),template:research.template,prompt:research.prompt,...(research.scope?{scope:research.scope}:{}),...(research.detailLevel!==undefined?{detailLevel:research.detailLevel||v.architectureSettings?.descriptionDetail||'standard'}:{}),...(research.subsystemLimit!==undefined?{subsystemLimit:research.subsystemLimit}:{}),revision:research.revision??v.context.revision},actionId:research.actionId}),signal:mounted.controller.signal});let result;try{result=await response.json();}catch(_){throw Object.assign(Error(globalThis.HubI18n?.t?.('research.outcomeUnknown')||'Unknown request outcome'),{outcomeUnknown:true});}if(!response.ok)throw Object.assign(Error(result.message||result.error),{outcomeUnknown:response.status>=500});if(result?.actionId!==research.actionId||typeof result.status!=='string')throw Object.assign(Error(globalThis.HubI18n?.t?.('research.outcomeUnknown')||'Unknown request outcome'),{outcomeUnknown:true});return result;}});
      window.KnowledgeResearch.bind(v,root,mounted.controller.signal);
    }
    mounted.menuCleanup=window.ArchitectureCanvas?.bindMenus?.(root);
    if(v.mode==='architecture')root.addEventListener('scroll',event=>{
      const pane=root.querySelector('.k-catalog');
      if(active(v)&&(event.target===pane||event.target===pane?.querySelector?.('.r-tree')))captureNavigatorScroll(v,root);
    },{capture:true,signal:mounted.controller.signal});
    if(v.mode==='architecture')document.addEventListener('keydown',event=>{
      if(active(v)&&(event.code==='KeyF'||event.key?.toLowerCase()==='f')&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.target.isContentEditable&&!event.target.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"])')){event.preventDefault();focusCanvas(v);}
    },{signal:mounted.controller.signal});
    root.addEventListener('click',event=> {
      if(window.HubSubsystems?.handle(v,event,subsystemHost(v)))return;
      if(v.mode==='docs'&&window.DocumentationUI?.handleClick(v,event,{refresh:()=>refresh(v),draw:()=>draw(v),select:id=>selectItem(v,id),persist:()=>persist(v)}))return;
      const moreFiles=event.target.closest('[data-k-file-more]');
      if(moreFiles){event.preventDefault();const details=moreFiles.closest('[data-k-file-folder]')||moreFiles.closest('.k-file-tree');window.ArchitectureMap?.hydrateFolder?.(v,details,Number(moreFiles.dataset.kFileOffset));return;}
      const doc=event.target.closest('[data-k-open-doc]');
      if(doc){event.preventDefault();captureCamera(v,mounted.cy);const docs=view(v.project,'docs');docs.returnArchitecture={project:v.project,selected:v.selected};persist(docs);location.hash=link('docs',doc.dataset.kOpenDoc);return;}
      const cell=event.target.closest('[data-k-matrix-from]');
      if(cell){event.preventDefault();chooseGraphItem(v,cell.dataset.kMatrixFrom,{graphMode:'neighborhood',presentation:'map',focusTarget:cell.dataset.kMatrixTo,focusRelation:cell.dataset.kMatrixEdge});return;}
      const browser=event.target.closest('[data-k-browser]');
      if(browser){event.preventDefault();v.filters.browser=browser.dataset.kBrowser;revealScope(v);persist(v);if(v.filters.browser==='catalog'){loadCatalogTree(v).then(()=>draw(v)).catch(error=>fail(v,error));}draw(v);return;}
      const context=event.target.closest('[data-k-component-context]'),projection=event.target.closest('[data-k-projection]'),presentation=event.target.closest('[data-k-presentation]');
      if(context||projection){event.preventDefault();destroyGraph();recordGraph(v);v.filters.focusTarget='';v.filters.focusRelation='';v.filters.hiddenTypes=[];v.filters.hiddenRelations=[];v.filters.edgeDirection='all';v.filters.edgeAnchor='';v.filters.canvasQuery='';if(context){v.filters.componentContext=context.dataset.kComponentContext;v.filters.scopeContexts||={};v.filters.scopeContexts[v.selected]=v.filters.componentContext;v.filters.graphMode='components';}else v.filters.graphMode=projection.dataset.kProjection;recordGraph(v);persist(v);refresh(v);return;}
      if(presentation){event.preventDefault();v.filters.presentation=presentation.dataset.kPresentation;persist(v);draw(v);return;}
      const tree=event.target.closest('[data-k-tree-id]');
      if(tree){event.preventDefault();chooseGraphItem(v,tree.dataset.kTreeId,{graphMode:tree.dataset.kTreeMode,componentContext:v.filters.scopeContexts?.[tree.dataset.kTreeId]||'auto',presentation:'map',component:'',type:'',query:'',entry:''});return;}
      const selection=event.target.closest('[data-k-select]');
      if(selection&&v.mode==='architecture'&&window.KnowledgeResearch&&window.KnowledgeResearch.state(v).tab==='sources'){event.preventDefault();window.KnowledgeResearch.open(v,selection.dataset.kSelect).catch(error=>fail(v,error));return;}
      if (selection) {
        if(window.ArchitectureMap&&v.mode==='architecture'&&(v.filters.browser==='graph'||selection.closest?.('[data-k-participants]'))&&mounted.cy?.getElementById(selection.dataset.kSelect).length){event.preventDefault();const node=mounted.cy.getElementById(selection.dataset.kSelect),add=event.shiftKey||event.ctrlKey||event.metaKey;if(!add)mounted.cy.elements(':selected').unselect();if(add&&node.selected())node.unselect();else node.select();updateCanvasSelection(v,mounted.cy,node.selected()?node:null);if(!add)focusCanvas(v);return;}
        event.preventDefault();chooseGraphItem(v,selection.dataset.kSelect);return;
      }
      const component=event.target.closest('[data-k-component]');
      if (component) {recordGraph(v);v.filters.component=component.dataset.kComponent;recordGraph(v);persist(v);refresh(v);return;}
      const revision=event.target.closest('[data-k-revision]');
      if (revision) {
        const id=revision.dataset.kRoleId||v.selected,number=Number(revision.dataset.kRevision),generation=++v.detailSequence;
        v.comparison=null;v.comparing=false;
        request(v,'read',{id,revision:number}).then(item=>{if(active(v)&&id===(v.historyId||v.selected)&&generation===v.detailSequence){v.historical={revision:number,item};v.restoreRequest=null;draw(v);}}).catch(error=>fail(v,error));return;
      }
      const button=event.target.closest('[data-k-action]');
      if (button) action(v,button.dataset.kAction,button).catch(error=>fail(v,error));
    });
    root.addEventListener('keydown',event=> {
      if ((event.ctrlKey||event.metaKey)&&event.key==='s'&&v.drafts.get(v.selected)?.dirty) {event.preventDefault();save(v);}
      const tree=event.target.closest?.('.k-architecture-tree');
      if(tree&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
        const rows=[...tree.querySelectorAll('summary,.k-tree-row')].filter(row=>!(row.matches('.k-tree-row')&&row.parentElement.tagName==='SUMMARY')&&row.getClientRects().length),target=event.target.closest('summary,.k-tree-row'),current=target?.parentElement.tagName==='SUMMARY'?target.parentElement:target,index=rows.indexOf(current),folder=current?.closest('details');
        event.preventDefault();
        if(event.key==='ArrowRight'&&current?.tagName==='SUMMARY'&&folder&&!folder.open)folder.open=true;
        else if(event.key==='ArrowLeft'&&folder){if(current?.tagName==='SUMMARY'&&folder.open)folder.open=false;else folder.querySelector('summary')?.focus();}
        else if(event.key==='ArrowRight'&&current?.tagName==='SUMMARY')rows[index+1]?.focus();
        else if(!['ArrowLeft','ArrowRight'].includes(event.key))rows[event.key==='Home'?0:event.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,index+(event.key==='ArrowUp'?-1:1)))]?.focus();
      }
    });
    root.addEventListener('scroll',event=>{if(event.target.matches?.('[data-k-participants]'))v.navigatorScroll.participants={top:event.target.scrollTop,left:event.target.scrollLeft};},true);
    root.addEventListener('toggle',event=>{if(event.target.matches?.('[data-k-participants-menu]')&&event.target.open){const pane=event.target.querySelector('[data-k-participants]'),position=v.navigatorScroll.participants;if(pane&&position){pane.scrollTop=position.top;pane.scrollLeft=position.left;}followNavigator(v);}if(event.target.matches?.('[data-k-filters-menu]')&&event.target.open){const panel=event.target.querySelector('.k-info-content');if(panel)panel.innerHTML=chartFilters(v);}for(const [attribute,setting] of [['kFileFolder','fileFolders'],['kTreeFolder','treeFolders']]){const folder=event.target.dataset?.[attribute];if(folder!==undefined){v.filters[setting]||={};v.filters[setting][folder]=event.target.open;if(setting==='fileFolders'&&event.target.open)window.ArchitectureMap?.hydrateFolder?.(v,event.target);if(setting==='treeFolders'&&event.target.open&&event.target.querySelector(':scope > div > small')){const pane=root.querySelector('.r-tree');if(pane){const temp=document.createElement('div');temp.innerHTML=window.KnowledgeResearch.catalog(v);pane.innerHTML=temp.querySelector('.r-tree').innerHTML;}}scheduleNavigatorPersist(v);}}},true);
    root.addEventListener('submit',event=> {
      window.HubSubsystems?.handle(v,event,subsystemHost(v));
    });
    root.addEventListener('input',event=> {
      window.HubSubsystems?.input(v,event);
      const input=event.target;
      if(input.matches?.('[data-k-find-on-map]')){v.filters.canvasQuery=input.value;applyCanvasSearch(v,mounted.cy);const rows=root.querySelector('[data-k-participant-rows]'),count=root.querySelector('[data-k-find-count]');if(rows)rows.innerHTML=participants(v);if(count)count.textContent=canvasMatches(v).length+(globalThis.HubI18n?.t?.("knowledge.74be9ffaf6e4") ?? ' совпадений · ')+graphModel(v).nodes.length+(globalThis.HubI18n?.t?.("knowledge.b251953efac8") ?? ' участников');followNavigator(v);persist(v);return;}
      if (input.dataset.kField) {const editId=v.panel==='role-description'?(v.roleEditId||v.selected):v.selected,draft=v.drafts.get(editId);if(draft){draft.item[input.dataset.kField]=['entityRefs','nodeIds','orderedEdges'].includes(input.dataset.kField)?lines(input.value):input.value;draft.dirty=true;draft.request=null;if(input.dataset.kField==='entityRefs'){clearTimeout(mounted.linksDebounce);mounted.linksDebounce=setTimeout(()=>{if(active(v))resolveDocLinks(v,draft.item);},300);}}}
      if (input.matches('[data-k-policy]')) {v.policyDraft=input.value;v.policyRequest=null;}
      if (input.matches('[data-k-paths]')) v.importPaths=input.value;
      if (input.dataset.kFilter==='query') {
        v.filters.query=input.value;clearTimeout(mounted.debounce);
        if(v.mode==='architecture'){
          persist(v);
          mounted.debounce=setTimeout(()=>{if(active(v))(v.filters.browser==='structure'?Promise.resolve():loadCatalogTree(v)).then(()=>{
            if(!active(v))return;renderNavigator(v);
          }).catch(error=>fail(v,error));},300);
        }else{mounted.queryEditing=true;mounted.debounce=setTimeout(()=>{if(active(v)){mounted.queryEditing=false;refresh(v);}},300);}
      }
    });

    root.addEventListener('change',event=> {
      const input=event.target;
      if(input.matches?.('[data-k-edge-direction]')){const state=canvasState(v);v.filters.edgeDirection=input.value;v.filters.edgeAnchor=input.value==='all'?'':input.dataset.kEdgeAnchor;persist(v);draw(v,state);return;}
      if(input.matches?.('[data-k-discovery-scope]')){v.filters.discoveryScope=input.value;persist(v);loadCatalogTree(v).then(()=>renderNavigator(v)).catch(error=>fail(v,error));return;}
      if(input.dataset?.kVisibleType||input.dataset?.kVisibleRelation){const state=canvasState(v),field=input.dataset.kVisibleType?'hiddenTypes':'hiddenRelations',id=input.dataset.kVisibleType||input.dataset.kVisibleRelation,hidden=new Set(v.filters[field]||[]);if(input.checked)hidden.delete(id);else hidden.add(id);v.filters[field]=[...hidden];persist(v);draw(v,state);return;}
      if(input.matches?.('[data-k-include-subsystems]')){destroyGraph();recordGraph(v);v.filters.includeSubsystems=input.checked;recordGraph(v);persist(v);refresh(v);return;}
      if(input.matches?.('[data-k-expand-mode]')){v.filters.expandMode=input.value;persist(v);positionNodeActions(v,mounted.cy);return;}
      if(input.matches?.('[data-k-group-by]')){const state=canvasState(v);v.filters.groupBy=input.value;v.filters.groupComponents=true;persist(v);draw(v,state);return;}
      if(input.matches?.('[data-k-group-components]')){const state=canvasState(v);v.filters.groupComponents=input.checked;persist(v);draw(v,state);return;}

      if (input.dataset?.kFilter && input.dataset.kFilter!=='query') {recordGraph(v);v.filters[input.dataset.kFilter]=input.type==='checkbox'?(input.checked?'yes':''):input.value;recordGraph(v);persist(v);if(['type','component','entry','graphMode'].includes(input.dataset.kFilter))refresh(v);else draw(v);}
      if (input.dataset.kImportSelect) {if(input.checked)v.importSelections.add(input.dataset.kImportSelect);else v.importSelections.delete(input.dataset.kImportSelect);v.importRequest=null;}
    });
  }
  function unmount() {
    if(!mounted)return;
    window.HubSubsystems?.dispose(mounted.view);
    captureNavigatorScroll(mounted.view,mounted.root);
    window.KnowledgeWorkspace?.dispose(mounted.root);
    mounted.docsResizeCleanup?.();
    destroyGraph();mounted.menuCleanup?.();mounted.removalObserver?.disconnect();mounted.controller.abort();
    clearTimeout(mounted.poll);clearTimeout(mounted.debounce);clearTimeout(mounted.linksDebounce);clearTimeout(mounted.view.knowledgeRefreshTimer);mounted=null;
  }
  function afterRender(options = {}) {
    const root=document.querySelector('.knowledge-root');
    if (!root || root.dataset.kProject!==(options.project||'')) {unmount();return;}
    if (mounted?.root===root) {
      mounted.options=options;const selected=routeId(mounted.view.mode,options);
      if(selected!==null){recordGraph(mounted.view);selectItem(mounted.view,selected);recordGraph(mounted.view);}
      if(mounted.selection!==mounted.view.selected){mounted.selection=mounted.view.selected;persist(mounted.view);if(mounted.view.mode==='architecture')refresh(mounted.view);else if(mounted.view.drafts.get(mounted.selection)?.dirty)draw(mounted.view);else loadItem(mounted.view,mounted.selection);}
      scheduleJob(mounted.view);return;
    }
    unmount();
    const v=view(root.dataset.kProject,root.dataset.kMode);
    mounted={root,view:v,options,controller:new AbortController(),poll:null,debounce:null,polling:false,selection:v.selected};
    if(window.MutationObserver&&document.body){mounted.removalObserver=new window.MutationObserver(()=>{if(mounted?.root===root&&!root.isConnected)unmount();});mounted.removalObserver.observe(document.body,{childList:true,subtree:true});}
    // A replaced root invalidates responses started for the preceding mount.
    v.sequence++;v.detailSequence++;v.loading=false;v.refreshAgain=false;
    bind(v,root);draw(v);
    mounted.docsResizeCleanup=v.mode==='docs'?window.DocumentationUI?.bindResize?.(v,root,{persist:()=>persist(v)}):null;
    if (!v.initialized) refresh(v);
    else if (v.selected && !v.drafts.get(v.selected)?.dirty &&
             (v.loadedSelection !== v.selected || v.drafts.get(v.selected)?.expected !== v.context?.revision)) {if(v.mode==='architecture')refresh(v);else loadItem(v,v.selected);}
    else if(v.mode==='docs'&&v.drafts.get(v.selected))resolveDocLinks(v,v.drafts.get(v.selected).item);
    scheduleJob(v);
  }
  document.addEventListener('visibilitychange',()=> {
    if (!mounted) return;
    if (document.hidden) {clearTimeout(mounted.poll);mounted.poll=null;}
    else scheduleJob(mounted.view);
  });
  window.addEventListener?.('resize',()=>{if(mounted?.cy){sizeGraph(mounted.root.querySelector('[data-k-cy]'));mounted.cy.resize();}});
  function notify(project, revision) {
    for (const v of views.values()) {
      if (v.project !== project || !v.context || v.context.revision === revision) continue;
      if(v.mode==='architecture'&&active(v)){queueKnowledgeRefresh(v,revision);continue;}
      v.initialized = false;if (active(v)) refresh(v);
    }
  }
  function queueKnowledgeRefresh(v,revision){
    if(Number.isFinite(revision))v.pendingKnowledgeRevision=Math.max(v.pendingKnowledgeRevision||0,revision);
    clearTimeout(v.knowledgeRefreshTimer);
    v.knowledgeRefreshTimer=setTimeout(()=>flushKnowledgeRefresh(v),750);
  }
  async function flushKnowledgeRefresh(v){
    if(!active(v)||!v.pendingKnowledgeRevision)return;
    if(v.context?.revision>=v.pendingKnowledgeRevision){v.pendingKnowledgeRevision=0;return;}
    // Agent changesets may arrive a few seconds apart. Keep the working canvas
    // mounted until that action finishes, then publish one complete snapshot.
    if(v.loading||['requested','accepted','running'].includes(v.research?.agent?.status)){
      clearTimeout(v.knowledgeRefreshTimer);v.knowledgeRefreshTimer=setTimeout(()=>flushKnowledgeRefresh(v),1200);return;
    }
    try{await refresh(v);}finally{
      if(v.context?.revision>=v.pendingKnowledgeRevision)v.pendingKnowledgeRevision=0;
      else if(active(v)&&!v.error)queueKnowledgeRefresh(v,v.pendingKnowledgeRevision);
    }
  }
  async function flushUpdates(project){await Promise.all([...views.values()].filter(v=>v.project===project&&active(v)).map(v=>{clearTimeout(v.knowledgeRefreshTimer);return flushKnowledgeRefresh(v);}));}
  window.KnowledgeUI = {page, afterRender, notify};
  window.KnowledgeUI.flushUpdates=flushUpdates;
  window.addEventListener?.('hub-language-changed', () => { for (const v of views.values()) if (active(v)) draw(v); });

globalThis.HubI18n?.onChange?.(()=>{Object.assign(nodeTypes,{component:(globalThis.HubI18n?.t?.("knowledge.626cda060f0c") ?? 'Компонент'),class:(globalThis.HubI18n?.t?.("knowledge.1711aecef486") ?? 'Класс'),record:'Record',enum:'Enum',interface:(globalThis.HubI18n?.t?.("knowledge.517c6d91fcdb") ?? 'Интерфейс'),file:(globalThis.HubI18n?.t?.("knowledge.59dbfe54b48f") ?? 'Файл / модуль'),external:(globalThis.HubI18n?.t?.("knowledge.acba5467afc6") ?? 'Внешний тип'),method:(globalThis.HubI18n?.t?.("knowledge.5fcca1576ab8") ?? 'Метод'),function:(globalThis.HubI18n?.t?.("knowledge.859538119171") ?? 'Функция'),field:(globalThis.HubI18n?.t?.("knowledge.f1707b7e1d2b") ?? 'Поле'),property:(globalThis.HubI18n?.t?.("knowledge.80a7359dec79") ?? 'Свойство'),variable:(globalThis.HubI18n?.t?.("knowledge.c89453017f3e") ?? 'Переменная'),symbol:(globalThis.HubI18n?.t?.("knowledge.bbfa955ec6bd") ?? 'Символ'),module:(globalThis.HubI18n?.t?.("knowledge.730c934a0cfd") ?? 'Модуль'),namespace:(globalThis.HubI18n?.t?.("knowledge.5e0d0bcd16a7") ?? 'Пространство имён')});Object.assign(edgeTypes,{extends:(globalThis.HubI18n?.t?.("knowledge.07eff7a5fe5a") ?? 'наследует'),implements:(globalThis.HubI18n?.t?.("knowledge.b01b27086c3f") ?? 'реализует'),inherits:(globalThis.HubI18n?.t?.("knowledge.07eff7a5fe5a") ?? 'наследует'),inheritance:(globalThis.HubI18n?.t?.("knowledge.07eff7a5fe5a") ?? 'наследует'),uses:(globalThis.HubI18n?.t?.("knowledge.59b57383b7a6") ?? 'использует'),imports:(globalThis.HubI18n?.t?.("knowledge.6f8b2ff0c656") ?? 'импортирует'),contains:(globalThis.HubI18n?.t?.("knowledge.63e6e06421c4") ?? 'содержит'),'depends-on':(globalThis.HubI18n?.t?.("knowledge.1e6a94ec5b45") ?? 'зависит'),'via-files':(globalThis.HubI18n?.t?.("knowledge.076e6114c122") ?? 'цепочка через файлы'),starts:(globalThis.HubI18n?.t?.("knowledge.626701c599c3") ?? 'запускает'),initializes:(globalThis.HubI18n?.t?.("knowledge.dd2284e8a057") ?? 'инициализирует'),reads:(globalThis.HubI18n?.t?.("knowledge.db207c22cbe2") ?? 'читает'),calls:(globalThis.HubI18n?.t?.("knowledge.c63642bdab51") ?? 'вызывает')});});
})();
