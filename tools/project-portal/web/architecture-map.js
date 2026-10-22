/* Progressive architecture maps: authored component hierarchy and local facts. */
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const modes = {structure:(globalThis.HubI18n?.t?.("architecture-map.816655bd716f") ?? 'Структура'),neighbors:(globalThis.HubI18n?.t?.("architecture-map.79e484b1f467") ?? 'Все связи'),interfaces:(globalThis.HubI18n?.t?.("architecture-map.8a89b9398cca") ?? 'Интерфейсы'),inheritance:(globalThis.HubI18n?.t?.("architecture-map.2167fe553fee") ?? 'Наследование'),dependencies:(globalThis.HubI18n?.t?.("architecture-map.9af957b361ca") ?? 'Зависимости')};
  const inset=56;
  function specialTopology(edge) {
    if(!edge||!edge.source||!edge.target)return false;
    const source=edge.source(),target=edge.target();
    if(!source.length||!target.length||source.id()===target.id())return true;
    return source.ancestors().contains(target)||target.ancestors().contains(source);
  }
  const icons={FolderTree:'M3 3h6v4H3z M3 13h6v4H3z M15 9h6v4h-6z M6 7v6 M9 5h3v6h3',Box:'m12 3 9 5-9 5-9-5 9-5 M3 8v9l9 5 9-5V8 M12 13v9',LogIn:'M15 3h5v18h-5 M3 12h12 m-4-4 4 4-4 4',Workflow:'M3 3h6v6H3z M15 15h6v6h-6z M9 6h6v12 M9 18h6',Folder:'M3 5h6l2 2h10v13H3z',FileCode:'M14 2H4v20h16V8z M14 2v6h6 M9 13l-3 3 3 3 m6-6 3 3-3 3',Braces:'M8 3H5v6l-2 3 2 3v6h3 M16 3h3v6l2 3-2 3v6h-3',Plug:'M9 3v4 M15 3v4 M7 7h10v5a5 5 0 0 1-10 0z M12 17v4',Layers:'m12 3 10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5'};
  const icon=name=>`<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${icons[name]||icons.Box}"/></svg>`;
  const scope = v => JSON.stringify([v.selected,v.filters.graphMode,v.filters.component,v.filters.type,v.filters.entry,v.filters.audience,v.filters.section,v.filters.componentContext,!!v.filters.includeSubsystems]);
  function branches(v) {
    v.branchMaps ||= new Map();
    if(v.branchRevision !== v.context?.revision){v.branchMaps.clear();v.branchRevision=v.context?.revision;}
    const id=scope(v);if(!v.branchMaps.has(id))v.branchMaps.set(id,new Map());
    return v.branchMaps.get(id);
  }
  function componentIndex(v) {
    return new Map((v.componentItems||[]).filter(n=>!n.removed).map(n=>[n.id,n]));
  }
  function parentId(node,components) {
    if(node.type==='component')return components.has(node.parent)?node.parent:null;
    if(components.has(node.component))return node.component;
    const id='component:'+node.component;return components.has(id)?id:null;
  }
  function model(v,base) {
    if(v.filters.graphMode==='matrix')return base;
    const expanded=branches(v),components=componentIndex(v),nodes=new Map(),edges=new Map();
    for(const node of base.nodes){
      // Overview starts at subsystems; finer levels are explicitly expanded.
      if(v.filters.graphMode==='overview'&&node.type==='component'&&node.parent&&components.has(node.parent)&&node.id!==v.selected)continue;
      nodes.set(node.id,node);
    }
    for(const edge of base.relations)edges.set(edge.id,edge);
    for(const branch of expanded.values()){
      for(const node of branch.nodes)nodes.set(node.id,node);
      for(const edge of branch.relations)edges.set(edge.id,edge);
    }
    const participants=new Set(nodes.keys()),parents=new Map();
    if(v.filters.groupComponents!==false&&v.filters.groupBy!=='none'){
      for(const node of [...nodes.values()]){
        let current=node,seen=new Set([node.id]);
        while(current){
          const parent=parentId(current,components);
          if(!parent||seen.has(parent))break;
          let ancestor=parent,cycle=new Set([current.id]);
          while(ancestor&&!cycle.has(ancestor)){cycle.add(ancestor);ancestor=parentId(components.get(ancestor)||{},components);}
          if(ancestor)break;
          seen.add(parent);parents.set(current.id,parent);nodes.set(parent,components.get(parent));current=components.get(parent);
        }
      }
    }
    if(v.filters.groupBy==='types'){
      const labels={class:(globalThis.HubI18n?.t?.("architecture-map.a860280b008e") ?? 'Классы'),interface:(globalThis.HubI18n?.t?.("architecture-map.8a89b9398cca") ?? 'Интерфейсы'),record:'Records',enum:'Enums',file:(globalThis.HubI18n?.t?.("architecture-map.9088ca9c0de9") ?? 'Файлы'),external:(globalThis.HubI18n?.t?.("architecture-map.a90984e26197") ?? 'Внешние типы')};
      for(const node of [...nodes.values()]){
        if(!Object.hasOwn(labels,node.type))continue;
        const parent=parents.get(node.id),id='ui:group:'+JSON.stringify([parent||'',node.type]);
        if(!nodes.has(id))nodes.set(id,{id,kind:'entity',type:'group',title:labels[node.type],provenance:'presentation'});
        if(parent)parents.set(id,parent);parents.set(node.id,id);
      }
    }
    const view=v.drafts?.get(v.selected)?.item,groups=base.presentationGroups||view?.presentationGroups||[],prefix='ui:map-group:'+(view?.id||base.id||v.selected)+':';
    // These categories belong to this map only. Canonical subsystem ownership
    // stays available to other maps and research queries.
    for(const group of groups){const id=prefix+group.id;nodes.set(id,{...group,id,kind:'entity',type:'group',mapGroup:true,provenance:'presentation'});}
    for(const group of groups){const id=prefix+group.id;if(group.parent)parents.set(id,prefix+group.parent);for(const member of group.nodeIds||[])if(nodes.has(member))parents.set(member,id);}
    const visible=[...nodes.values()],ids=new Set(nodes.keys());
    return {...base,nodes:visible,relations:[...edges.values()].filter(edge=>ids.has(edge.from)&&ids.has(edge.to)),parents,contextFrames:new Set([...ids].filter(id=>!participants.has(id))),
      expanded:new Set([...expanded.values()].map(branch=>branch.root)),branches:expanded};
  }
  function project(v,full){
    const r=v.research||{},parents=full.parents||new Map(),byId=new Map(full.nodes.map(n=>[n.id,n]));
    const scopeId=v.selected||'';
    if(r.groupScope!==scopeId){r.groupScope=scopeId;r.collapsedGroups=new Set(full.nodes.filter(n=>n.mapGroup).map(n=>n.id));}
    const collapsed=r.collapsedGroups||new Set(),representatives=new Map(),memberCounts=new Map();
    for(const node of full.nodes){let current=node.id,representative=current;const seen=new Set();
      while(current&&!seen.has(current)){seen.add(current);if(collapsed.has(current)&&byId.has(current))representative=current;current=parents.get(current);}
      representatives.set(node.id,representative);if(representative!==node.id)memberCounts.set(representative,(memberCounts.get(representative)||0)+1);
    }
    const nodes=full.nodes.filter(n=>representatives.get(n.id)===n.id).map(n=>collapsed.has(n.id)?{...n,collapsed:true,memberCount:memberCounts.get(n.id)||0}:n),ids=new Set(nodes.map(n=>n.id)),edges=new Map();
    for(const edge of full.relations){const from=representatives.get(edge.from),to=representatives.get(edge.to);if(!from||!to||from===to&&edge.from!==edge.to)continue;
      if(from===edge.from&&to===edge.to){edges.set(edge.id,edge);continue;}
      const id='ui:aggregate:'+JSON.stringify([from,to,edge.type]);let aggregate=edges.get(id);
      if(!aggregate){aggregate={id,kind:'relation',type:edge.type,from,to,count:0,provenance:'presentation',aggregate:true,evidence:[]};edges.set(id,aggregate);}
      aggregate.count+=Number(edge.count)||1;aggregate.evidence.push(...(edge.evidence||[]).slice(0,Math.max(0,8-aggregate.evidence.length)));
    }
    return {...full,nodes,relations:[...edges.values()],parents:new Map([...parents].filter(([id,parent])=>ids.has(id)&&ids.has(parent))),collapsedGroups:collapsed};
  }
  async function page(request,args,offset,revision) {
    const result=await request('search',{...args,offset,limit:100});
    if(result.revision!==revision)throw Error((globalThis.HubI18n?.t?.("architecture-map.5063fb21091b") ?? 'Знания обновились во время раскрытия. Обновите карту.'));
    if(result.more&&(!Number.isInteger(result.next)||result.next<=offset))throw Error((globalThis.HubI18n?.t?.("architecture-map.6505c4b50881") ?? 'Неполная страница связей: обновите карту.'));
    return {items:result.items,continuation:result.more?{args,next:result.next}:null};
  }
  async function readItems(request,ids,revision) {
    const items=[];
    for(let offset=0;offset<ids.length;offset+=30){
      // Current reads are indexed; the final context check rejects any write
      // during the expansion, avoiding historical replay for each endpoint.
      const group=await Promise.all(ids.slice(offset,offset+30).map(id=>request('read',{id})));
      items.push(...group.filter(n=>n.kind==='entity'&&!n.removed));
    }
    return items;
  }
  async function availability(v,id,request,base){
    const revision=v.context?.revision,node=base.nodes.find(n=>n.id===id);
    if(!node||node.type==='group')return {};
    v.branchCapabilities||=new Map();const key=JSON.stringify([revision,id]);
    if(v.branchCapabilities.has(key))return v.branchCapabilities.get(key);
    const pending=(async()=>{
      const result=await request('search',{kind:'relation',endpoint:id,limit:100});
      if(result.revision!==revision)throw Error((globalThis.HubI18n?.t?.("architecture-map.4844531fbfed") ?? 'Знания обновились. Обновите карту.'));
      const types=new Set(result.items.filter(e=>!e.removed).map(e=>e.type));
      if(result.more){
        const additional=await Promise.all(['contains','extends','implements','inherits','inheritance','uses','imports','depends-on'].filter(type=>!types.has(type)).map(async type=>{const p=await request('search',{kind:'relation',endpoint:id,type,limit:1});if(p.revision!==revision)throw Error((globalThis.HubI18n?.t?.("architecture-map.4844531fbfed") ?? 'Знания обновились. Обновите карту.'));if(p.items.some(e=>!e.removed))types.add(type);}));
      }
      let structure=result.items.some(e=>!e.removed&&e.type==='contains'&&e.from===id);
      if(node.type==='component'){
        structure=[...componentIndex(v).values()].some(n=>n.parent===id);
        if(!structure){const p=await request('search',{kind:'entity',component:node.component||id,limit:1});if(p.revision!==revision)throw Error((globalThis.HubI18n?.t?.("architecture-map.4844531fbfed") ?? 'Знания обновились. Обновите карту.'));structure=p.items.some(n=>!n.removed);}
      }
      const inherited=['extends','implements','inherits','inheritance'].some(type=>types.has(type));
      const interfaces=new Set(base.nodes.filter(n=>n.type==='interface').map(n=>n.id));
      const hasInterfaces=types.has('implements')||result.items.some(e=>e.type!=='contains'&&(interfaces.has(e.from)||interfaces.has(e.to)));
      return {structure,neighbors:[...types].some(type=>type!=='contains'),interfaces:hasInterfaces||result.more,inheritance:inherited,dependencies:['uses','imports','depends-on'].some(type=>types.has(type))};
    })();
    v.branchCapabilities.set(key,pending);
    while(v.branchCapabilities.size>100)v.branchCapabilities.delete(v.branchCapabilities.keys().next().value);
    try{return await pending;}catch(error){v.branchCapabilities.delete(key);throw error;}
  }
  async function expand(v,id,mode,request,base,more=false) {
    if(!Object.hasOwn(modes,mode))mode='neighbors';
    const revision=v.context?.revision,scopeId=scope(v),set=branches(v),identifier=JSON.stringify([id,mode]);
    const previous=set.get(identifier);
    if(previous&&(!more||!previous.continuation.length))return previous;
    const root=base.nodes.find(n=>n.id===id);if(!root||root.type==='group')return null;
    const components=componentIndex(v);let nodes=[],relations=[],continuation=[];
    const take=async(args,offset=0)=>{const result=await page(request,args,offset,revision);if(result.continuation)continuation.push(result.continuation);return result.items;};
    if(previous){
      const results=await Promise.all(previous.continuation.map(cursor=>take(cursor.args,cursor.next)));
      for(let i=0;i<results.length;i++)(previous.continuation[i].args.kind==='entity'?nodes:relations).push(...results[i]);
    }
    if(mode==='structure'&&root.type==='component'){
      if(!previous)nodes=[...components.values()].filter(n=>n.parent===id);
      if(!previous&&!nodes.length){
        const component=root.component||id;
        nodes=await take({kind:'entity',component});
      }
      nodes=nodes.filter(n=>n.kind==='entity'&&!n.removed&&n.type!=='file'&&n.type!=='external');
      const ids=new Set([id,...nodes.map(n=>n.id),...(previous?.nodes||[]).map(n=>n.id)]);
      if(!previous)relations=await take({kind:'relation',endpoint:id});
      // Read relationships of the visible participants only. Membership is
      // expressed by frames; no component-to-class edges are invented.
      for(let offset=0;offset<nodes.length;offset+=20){
        const childPages=await Promise.all(nodes.slice(offset,offset+20).map(n=>take({kind:'relation',...(n.type==='component'?{type:'depends-on'}:{}),endpoint:n.id})));
        relations.push(...childPages.flat());
      }
      relations=relations.filter(e=>ids.has(e.from)&&ids.has(e.to)&&!e.removed);
    }else{
      const types=mode==='structure'?['contains']:mode==='inheritance'?['extends','implements','inherits','inheritance']:
        mode==='dependencies'?['uses','imports','depends-on']:null;
      if(!previous)relations=types?(await Promise.all(types.map(type=>take({kind:'relation',type,endpoint:id})))).flat():await take({kind:'relation',endpoint:id});
      relations=relations.filter(e=>!e.removed&&(mode==='structure'?e.type==='contains'&&e.from===id:e.type!=='contains'));
      const ids=[...new Set(relations.flatMap(e=>[e.from,e.to]))].filter(target=>target!==id);
      const known=new Map([...base.nodes,...(previous?.nodes||[]),...components.values()].map(n=>[n.id,n]));
      nodes=ids.filter(target=>known.has(target)).map(target=>known.get(target));
      nodes.push(...await readItems(request,ids.filter(target=>!known.has(target)),revision));
      if(mode==='interfaces'){
        const interfaces=new Set([root,...nodes].filter(n=>n.type==='interface').map(n=>n.id));
        relations=relations.filter(e=>interfaces.has(e.from)||interfaces.has(e.to));
        const endpoints=new Set(relations.flatMap(e=>[e.from,e.to]));nodes=nodes.filter(n=>endpoints.has(n.id));
      }
    }
    const fresh=await request('context');
    if(fresh.revision!==revision||v.context?.revision!==revision||scope(v)!==scopeId)throw Error((globalThis.HubI18n?.t?.("architecture-map.cdf15ee8b7c8") ?? 'Карта изменилась во время раскрытия. Повторите действие в текущем представлении.'));
    const branch={root:id,mode,nodes:[...new Map([...(previous?.nodes||[]),...nodes].map(n=>[n.id,n])).values()],relations:[...new Map([...(previous?.relations||[]),...relations].map(e=>[e.id,e])).values()],continuation,revision};
    set.set(identifier,branch);return branch;
  }
  function collapse(v,id,base) {
    const set=branches(v),removed=new Set([id]);let change=true;
    while(change){
      change=false;
      for(const [key,branch] of set){
        if(!removed.has(branch.root))continue;
        set.delete(key);change=true;
        const retained=new Set([...base.nodes.map(n=>n.id),...([...set.values()].flatMap(b=>b.nodes.map(n=>n.id)))]);
        for(const node of branch.nodes)if(!retained.has(node.id))removed.add(node.id);
      }
    }
  }
  function tree(v) {
    const components=componentIndex(v),seen=new Set(),opened=v.filters.treeFolders||{},query=String(v.filters.query||'').toLocaleLowerCase(),matches=n=>!query||[n.title,n.id,n.source?.path].some(value=>String(value||'').toLocaleLowerCase().includes(query)),included=new Set();
    for(const node of components.values())if(matches(node)){let id=node.id;const trail=new Set();while(id&&!trail.has(id)){trail.add(id);included.add(id);id=components.get(id)?.parent;}}
    const link=(node,mode,image)=>`<button class="k-tree-row" data-k-tree-id="${esc(node.id)}" data-k-tree-mode="${mode}" title="${esc(node.title)}"${v.selected===node.id?' aria-current="page"':''}>${icon(image)}<span>${esc(node.title)}</span></button>`;
    const folder=(id,title,body)=>`<details data-k-tree-folder="${esc(id)}"${opened[id]!==false?' open':''}><summary>${icon('Folder')}<span>${esc(title)}</span></summary><div>${body}</div></details>`;
    function row(node,trail){
      if(trail.has(node.id)||seen.has(node.id)||!included.has(node.id))return '';seen.add(node.id);
      const children=[...components.values()].filter(n=>n.parent===node.id),next=new Set([...trail,node.id]);
      const button=link(node,'components','Box');
      return children.length?`<details data-k-tree-folder="${esc(node.id)}"${opened[node.id]!==false?' open':''}><summary>${button}</summary><div>${children.map(n=>row(n,next)).join('')}</div></details>`:button;
    }
    const roots=[...components.values()].filter(n=>!components.has(n.parent));
    const hierarchy=roots.map(n=>row(n,new Set())).join('')+[...components.values()].filter(n=>!seen.has(n.id)).map(n=>row(n,new Set())).join('');
    const entries=(v.entryItems||[]).filter(n=>n.type!=='file'&&matches(n)),scenarios=(v.scenarios||[]).filter(matches);
    function grouped(items,prefix,image){
      const groups=new Map();
      for(const item of items){
        let component=components.get(item.component)||components.get('component:'+item.component),trail=new Set();
        while(component?.parent&&components.has(component.parent)&&!trail.has(component.id)){trail.add(component.id);component=components.get(component.parent);}
        const id=component?.id||'';if(!groups.has(id))groups.set(id,{component,items:[]});groups.get(id).items.push(item);
      }
      return [...groups].map(([id,group])=>{const body=group.items.map(n=>link(n,'neighborhood',image)).join('');return group.component?folder(prefix+id,group.component.title,body):body;}).join('');
    }
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("architecture-map.b00acac941e6",{v0:(icon('FolderTree')),v1:(hierarchy||(globalThis.HubI18n?.t?.("architecture-map.d3b6e144bd94") ?? '<p class="k-empty">Компоненты пока не заданы.</p>')),v2:(grouped(entries,'entries:','LogIn')||(globalThis.HubI18n?.t?.("architecture-map.df1338e4ab59") ?? '<small>Сканер не обнаружил точки входа.</small>')),v3:(grouped(scenarios,'scenarios:','Workflow')||(globalThis.HubI18n?.t?.("architecture-map.1085e74899e5") ?? '<small>Сценариев пока нет.</small>'))}) : `<nav class="k-architecture-tree" aria-label="Дерево архитектуры"><button class="k-tree-row" data-k-tree-mode="overview" data-k-tree-id="">${icon('FolderTree')}<span>Обзор проекта</span></button><h3>Подсистемы</h3>${hierarchy||(globalThis.HubI18n?.t?.("architecture-map.d3b6e144bd94") ?? '<p class="k-empty">Компоненты пока не заданы.</p>')}<h3>Точки входа</h3>${grouped(entries,'entries:','LogIn')||(globalThis.HubI18n?.t?.("architecture-map.df1338e4ab59") ?? '<small>Сканер не обнаружил точки входа.</small>')}<h3>Сценарии</h3>${grouped(scenarios,'scenarios:','Workflow')||(globalThis.HubI18n?.t?.("architecture-map.1085e74899e5") ?? '<small>Сценариев пока нет.</small>')}</nav>`);
  }
  function fileTree(v,items,{reveal=false,lazy=false}={}) {
    const PAGE=200,root={folders:new Map(),files:new Map(),other:[]};
    for(const item of items){const path=item.source?.path||(item.type==='file'?item.title:'');if(!path){root.other.push(item);continue;}const parts=String(path).replace(/\\/g,'/').split('/').filter(Boolean),name=parts.pop();let branch=root;for(const part of parts){if(!branch.folders.has(part))branch.folders.set(part,{folders:new Map(),files:new Map(),other:[]});branch=branch.folders.get(part);}if(!branch.files.has(name))branch.files.set(name,[]);branch.files.get(name).push(item);}
    const selectionPath=()=>v.canvasInspect?.source?.path?.replace(/\\/g,'/')||items.find(n=>n.id===(v.canvasItem||v.selected))?.source?.path?.replace(/\\/g,'/')||'',contents=new Map();
    const row=(item,name)=>`<a class="k-file-row${item.id===(v.canvasItem||v.selected)?' selected':''}" data-k-select="${esc(item.id)}" href="#architecture/${encodeURIComponent(item.id)}" title="${esc(item.title||item.id)}">${icon(item.type==='file'?'FileCode':item.type==='interface'?'Plug':'Braces')}<span>${esc(name||item.title||item.id)}</span><small>${esc({class:(globalThis.HubI18n?.t?.("architecture-map.51cdccb8236d") ?? 'класс'),interface:(globalThis.HubI18n?.t?.("architecture-map.03d139991c66") ?? 'интерфейс'),record:'record',enum:'enum',external:(globalThis.HubI18n?.t?.("architecture-map.9841fec2a184") ?? 'внешний тип'),component:(globalThis.HubI18n?.t?.("architecture-map.b3a84f87fd83") ?? 'компонент')}[item.type]||'')}</small></a>`;
    const placeholder=path=>(globalThis.HubI18n?.t ? globalThis.HubI18n.t("architecture-map.8c4077fe995d",{v0:(esc(path))}) : `<small class="k-file-lazy" data-k-file-lazy="${esc(path)}">Откройте папку для загрузки содержимого</small>`);
    const more=(path,offset,total)=>offset<total?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("architecture-map.646b8c230681",{v0:(esc(path)),v1:(offset),v2:(total-offset)}) : `<button type="button" class="k-file-more" data-k-file-more="${esc(path)}" data-k-file-offset="${offset}">Показать ещё (${total-offset})</button>`):'';
    function renderFile(nodes,full,offset=0){const file=nodes.find(n=>n.type==='file'),types=nodes.filter(n=>n.type!=='file').sort((x,y)=>String(x.title).localeCompare(String(y.title)));const limit=reveal?types.length:offset+PAGE,visible=types.slice(0,limit),selected=types.find(n=>n.id===(v.canvasItem||v.selected));if(selected&&!visible.includes(selected))visible.push(selected);const body=visible.map(n=>row(n)).join('')+more(full,limit,types.length);contents.set(full,(next=0)=>renderFile(nodes,full,next).body);return {file,types,body};}
    function render(branch,path='',offset=0){
      const selectedPath=selectionPath(),opened=v.filters.fileFolders||{};
      const entries=[...branch.folders].map(([name,child])=>({name,kind:'folder',child})).concat([...branch.files].map(([name,nodes])=>({name,kind:'file',nodes}))).sort((a,b)=>a.name.localeCompare(b.name));
      const limit=reveal?entries.length:offset+PAGE;let visible=entries.slice(0,limit);const selectedName=selectedPath.startsWith(path?path+'/':'')?selectedPath.slice(path?path.length+1:0).split('/')[0]:'';if(!reveal&&selectedName&&!visible.some(e=>e.name===selectedName)){const selected=entries.find(e=>e.name===selectedName);if(selected)visible=[...visible,selected];}
      const html=visible.map(entry=>{const full=path?path+'/'+entry.name:entry.name;if(entry.kind==='folder'){const isOpen=reveal||(opened[full]??(!v.filters.fileTreeCollapsed&&selectedPath.startsWith(full+'/')));contents.set(full,(next=0)=>render(entry.child,full,next));const body=lazy&&!isOpen?placeholder(full):render(entry.child,full,0);return `<details data-k-file-folder="${esc(full)}"${isOpen?' open':''}><summary data-r-directory="${esc(full)}">${icon('Folder')}<span>${esc(entry.name)}</span></summary><div>${body}</div></details>`;}const rendered=renderFile(entry.nodes,full,0),isOpen=reveal||(opened[full]??(!v.filters.fileTreeCollapsed&&selectedPath===full));return rendered.types.length?`<details data-k-file-folder="${esc(full)}"${isOpen?' open':''}><summary>${rendered.file?row(rendered.file,entry.name):`${icon('FileCode')}<span>${esc(entry.name)}</span>`}</summary><div>${lazy&&!isOpen?placeholder(full):rendered.body}</div></details>`:entry.nodes.map(n=>row(n,entry.name)).join('');}).join('')+more(path,limit,entries.length);contents.set(path,(next=0)=>render(branch,path,next));return html;
    }
    const misc=root.other.length?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("architecture-map.f9ec1711a797",{v0:(root.other.map(n=>row(n)).join(''))}) : `<details data-k-file-folder="@non-files"><summary>Компоненты и внешние типы</summary><div>${root.other.map(n=>row(n)).join('')}</div></details>`):'';v.__fileTreeCache={contents,root,items};return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("architecture-map.e05bf0b073b1",{v0:(render(root)+misc||(globalThis.HubI18n?.t?.("architecture-map.9da4e12912ef") ?? '<p class="k-empty">Исходников в этом представлении нет.</p>'))}) : `<nav class="k-file-tree" aria-label="Дерево исходников">${render(root)+misc||(globalThis.HubI18n?.t?.("architecture-map.9da4e12912ef") ?? '<p class="k-empty">Исходников в этом представлении нет.</p>')}</nav>`);
  }
  function hydrateFolder(v,details,offset=0,force=false){const path=details?.dataset?.kFileFolder??'',fill=v.__fileTreeCache?.contents?.get(path);if(!fill||!details)return false;const target=details.matches?.('.k-file-tree')?details:[...details.children].find(node=>node.tagName==='DIV');if(!target||(!force&&!offset&&!target.firstElementChild?.matches?.('[data-k-file-lazy]')))return false;target.innerHTML=fill(offset);return true;}
  function revealFile(v,pane,sourcePath){
    const path=sourcePath?.replace(/\\/g,'/'),tree=pane?.querySelector?.('.k-file-tree');if(!path||!tree||!v.__fileTreeCache)return false;
    let parent=tree;
    const parts=path.split('/');
    for(let i=1;i<=parts.length;i++){
      const prefix=parts.slice(0,i).join('/'),find=()=>[...parent.querySelectorAll('[data-k-file-folder]')].find(n=>n.dataset.kFileFolder===prefix);
      let folder=find();
      if(!folder){hydrateFolder(v,parent,0,true);folder=find();}
      // Files without declared symbols are rows rather than expandable nodes.
      if(!folder)return i===parts.length;
      folder.open=true;hydrateFolder(v,folder);parent=folder;
    }
    return true;
  }
  let engine=null;
  async function elkLayout(cy,done,isCurrent) {
    if(typeof window.ELK!=='function')throw Error((globalThis.HubI18n?.t?.("architecture-map.6e68361171c6") ?? 'ELK не загружен'));
    engine ||= new window.ELK({workerUrl:'/vendor/elk-worker.min.js'});
    const nodeMap=new Map(),root={id:'architecture-root',children:[],edges:[],layoutOptions:{
      'elk.algorithm':'layered','elk.direction':'RIGHT','elk.edgeRouting':'ORTHOGONAL',
      'elk.json.edgeCoords':'ROOT',
      'elk.hierarchyHandling':'INCLUDE_CHILDREN','elk.randomSeed':'1','elk.spacing.nodeNode':'48',
      'elk.layered.spacing.nodeNodeBetweenLayers':'90','elk.layered.spacing.edgeEdgeBetweenLayers':'20',
      'elk.layered.considerModelOrder.strategy':'NODES_AND_EDGES','elk.padding':'[top=48,left=32,bottom=32,right=32]'}};
    const sorted=cy.nodes().sort((a,b)=>a.id().localeCompare(b.id()));
    for(const n of sorted){const box=n.boundingBox({includeLabels:false,includeOverlays:false});nodeMap.set(n.id(),{id:n.id(),...(!n.isParent()?{width:box.w,height:box.h}:{}),children:[],edges:[],layoutOptions:{'elk.padding':`[top=${inset},left=${inset},bottom=${inset},right=${inset}]`}});}
    for(const n of sorted){const parent=n.parent().id();(nodeMap.get(parent)||root).children.push(nodeMap.get(n.id()));}
    for(const e of cy.edges().sort((a,b)=>a.id().localeCompare(b.id()))){
      if(specialTopology(e))continue;
      root.edges.push({id:e.id(),sources:[e.source().id()],targets:[e.target().id()]});
    }
    const graph=await engine.layout(root);if(!isCurrent())return;
    const routes=new Map();
    function visit(node,x=0,y=0){
      const px=x+(node.x||0),py=y+(node.y||0),element=cy.getElementById(node.id);
      if(element.length&&!element.isParent()){element.position('x',px+node.width/2);element.position('y',py+node.height/2);}
      // ELK otherwise uses the lowest common ancestor's coordinates even when
      // an edge is stored at the JSON root. Request ROOT and retain every
      // linked section of the simple source-to-target route.
      for(const edge of node.edges||[]){const points=sectionPoints(edge);if(points)routes.set(edge.id,points);}
      for(const child of node.children||[])visit(child,px,py);
    }
    cy.batch(()=>visit(graph));
    const margin=Math.max(64,Math.max(graph.width||0,graph.height||0)*.05),x=graph.x||0,y=graph.y||0;
    for(const edge of root.edges){
      const points=routes.get(edge.id);
      if(!points)throw Error((globalThis.HubI18n?.t?.("architecture-map.9784a23a2a03") ?? 'ELK: не построен маршрут ')+edge.id);
      if(!Number.isFinite(graph.width)||!Number.isFinite(graph.height)||points.some(p=>p.x<x-margin||p.y<y-margin||p.x>x+graph.width+margin||p.y>y+graph.height+margin))throw Error((globalThis.HubI18n?.t?.("architecture-map.044237bb788d") ?? 'ELK: геометрия маршрута выходит за границы модели · ')+edge.id);
    }
    cy.knowledgeRoutes=routes;done();
  }
  function sectionPoints(edge){
    const sections=edge.sections||[],byId=new Map(sections.map(s=>[s.id,s]));
    const starts=sections.filter(s=>(edge.sources||[]).includes(s.incomingShape)||!(s.incomingSections||[]).length);
    if(starts.length!==1)return null;
    const result=[],seen=new Set();let section=starts[0];
    while(section&&!seen.has(section.id)){
      seen.add(section.id);
      for(const point of [section.startPoint,...(section.bendPoints||[]),section.endPoint]){
        if(!point||!Number.isFinite(point.x)||!Number.isFinite(point.y))return null;
        const previous=result.at(-1);if(!previous||previous.x!==point.x||previous.y!==point.y)result.push({x:point.x,y:point.y});
      }
      const next=section.outgoingSections||[];if(next.length>1)return null;
      section=next.length?byId.get(next[0]):null;
    }
    return seen.size===sections.length&&result.length>1?result:null;
  }
  const routeGeometry=new WeakMap();
  const routeNear=(a,b)=>Math.abs(a-b)<1e-7;
  function borderPortAt(position,width,height,point) {
    const box={x1:position.x-width/2,x2:position.x+width/2,y1:position.y-height/2,y2:position.y+height/2};
    const dx=point.x-position.x,dy=point.y-position.y;
    if(!Number.isFinite(dx)||!Number.isFinite(dy)||(!dx&&!dy))return {x:position.x,y:box.y1};
    const scale=Math.max(Math.abs(dx)/(width/2||1),Math.abs(dy)/(height/2||1));
    return {x:position.x+dx/scale,y:position.y+dy/scale};
  }
  function borderPort(node,point) {return borderPortAt(node.position(),node.outerWidth(),node.outerHeight(),point);}
  function simplifyRoute(points) {
    const result=[];
    for(const p of points){
      const previous=result.at(-1);if(previous&&routeNear(p.x,previous.x)&&routeNear(p.y,previous.y))continue;
      result.push({...p});
      // Remove the entire old terminal run, including a reversal. Keeping
      // its obsolete knees makes a rounded corner turn into a narrow spike.
      while(result.length>2){const [a,b,c]=result.slice(-3);
        if(!(routeNear(a.x,b.x)&&routeNear(b.x,c.x))&&!(routeNear(a.y,b.y)&&routeNear(b.y,c.y)))break;
        result.splice(result.length-2,1);
      }
    }
    return result;
  }
  function routeDirection(a,b) {return Math.abs(b.x-a.x)>=Math.abs(b.y-a.y)?{x:Math.sign(b.x-a.x),y:0}:{x:0,y:Math.sign(b.y-a.y)};}
  function terminalRoute(points,original,sourceBox,targetBox) {
    const s=points[0],t=points.at(-1),out=routeDirection(original[0],original[1]),incoming=routeDirection(original.at(-1),original.at(-2));
    const dot=(a,b,d)=>(b.x-a.x)*d.x+(b.y-a.y)*d.y;
    const directions=path=>path.length>1&&dot(path[0],path[1],out)>1e-7&&dot(path.at(-1),path.at(-2),incoming)>1e-7;
    const intersects=(a,b,r)=>routeNear(a.x,b.x)?a.x>r.x1+1e-7&&a.x<r.x2-1e-7&&Math.max(a.y,b.y)>r.y1+1e-7&&Math.min(a.y,b.y)<r.y2-1e-7:
      a.y>r.y1+1e-7&&a.y<r.y2-1e-7&&Math.max(a.x,b.x)>r.x1+1e-7&&Math.min(a.x,b.x)<r.x2-1e-7;
    const clear=path=>path.slice(1).every((p,i)=>![sourceBox,targetBox].some(r=>intersects(path[i],p,r)));
    const orthogonal=path=>path.slice(1).every((p,i)=>routeNear(p.x,path[i].x)||routeNear(p.y,path[i].y));
    // Move the endpoint knees with their ports, while retaining the inner
    // ELK channels. Replacing a many-bend route with a single long terminal
    // segment packs fan-in edges into a band at their common destination.
    if(original.length>=6){
      const retained=original.map(p=>({...p})),last=retained.length-2;
      retained[0]={...s};retained[retained.length-1]={...t};
      if(out.x){
        retained[1]={x:original[1].x+s.x-original[0].x,y:s.y};
        if(routeNear(original[1].x,original[2].x))retained[2].x=retained[1].x;
      }else{
        retained[1]={x:s.x,y:original[1].y+s.y-original[0].y};
        if(routeNear(original[1].y,original[2].y))retained[2].y=retained[1].y;
      }
      if(incoming.x){
        retained[last]={x:original[last].x+t.x-original.at(-1).x,y:t.y};
        if(routeNear(original[last].x,original[last-1].x))retained[last-1].x=retained[last].x;
      }else{
        retained[last]={x:t.x,y:original[last].y+t.y-original.at(-1).y};
        if(routeNear(original[last].y,original[last-1].y))retained[last-1].y=retained[last].y;
      }
      const repaired=simplifyRoute(retained);
      if(orthogonal(repaired)&&directions(repaired)&&clear(repaired))return repaired;
    }
    if(orthogonal(points)&&directions(points)&&clear(points))return points;
    // Once a port crosses its old lane, reconnect this edge outside the two
    // endpoint boxes. Other edges keep their lanes; no global layout runs.
    const gap=24,a={x:s.x+out.x*gap,y:s.y+out.y*gap},b={x:t.x+incoming.x*gap,y:t.y+incoming.y*gap};
    const candidates=[ [s,a,{x:b.x,y:a.y},b,t], [s,a,{x:a.x,y:b.y},b,t] ];
    const interior=original.slice(1,-1);
    const xs=[...new Set(interior.map(p=>p.x))].slice(0,12).concat((a.x+b.x)/2,Math.min(sourceBox.x1,targetBox.x1)-gap,Math.max(sourceBox.x2,targetBox.x2)+gap);
    const ys=[...new Set(interior.map(p=>p.y))].slice(0,12).concat((a.y+b.y)/2,Math.min(sourceBox.y1,targetBox.y1)-gap,Math.max(sourceBox.y2,targetBox.y2)+gap);
    for(const x of xs)candidates.push([s,a,{x,y:a.y},{x,y:b.y},b,t]);
    for(const y of ys)candidates.push([s,a,{x:a.x,y},{x:b.x,y},b,t]);
    const routes=candidates.map(simplifyRoute).filter(path=>orthogonal(path)&&directions(path));
    const length=path=>path.slice(1).reduce((sum,p,i)=>sum+Math.abs(p.x-path[i].x)+Math.abs(p.y-path[i].y),0);
    // If a moved compound crosses its old trunk, several generic candidates
    // can be collision-free.  Choosing only the shortest one collapses
    // distinct ELK lanes onto the same midpoint.  Prefer the candidate whose
    // interior bends remain closest to the old trunk, then use length as the
    // deterministic tie-breaker.
    const trunkDistance=path=>{
      const current=path.slice(1,-1),baseline=original.slice(1,-1);
      if(!current.length||!baseline.length)return current.length===baseline.length?0:1e9;
      const nearest=(point,points)=>Math.min(...points.map(other=>Math.abs(point.x-other.x)+Math.abs(point.y-other.y)));
      return current.reduce((sum,point)=>sum+nearest(point,baseline),0)+
        baseline.reduce((sum,point)=>sum+nearest(point,current),0);
    };
    // Overlapping cards may have no collision-free connection, but still
    // retain finite orthogonal geometry with outward terminal directions.
    return (routes.filter(clear).length?routes.filter(clear):routes)
      .sort((a,b)=>trunkDistance(a)-trunkDistance(b)||length(a)-length(b))[0]||points;
  }
  function movedRoute(original,source,target,sourceBox,targetBox) {
    const movement={x:source.x-original.startSource.x,y:source.y-original.startSource.y},other={x:target.x-original.startTarget.x,y:target.y-original.startTarget.y};
    const near=(a,b)=>Math.abs(a-b)<1e-7,clean=value=>near(value,0)?0:value;
    // Shared motion is relative to this gesture, even if a previous gesture
    // already moved one endpoint independently. Shift the stable ELK trunk.
    if(near(movement.x,other.x)&&near(movement.y,other.y)){
      const dx=clean(movement.x-original.shift.x),dy=clean(movement.y-original.shift.y);
      if(dx||dy){
        original.points=original.points.map(p=>({x:p.x+dx,y:p.y+dy}));
        for(const anchor of [original.source,original.target]){anchor.x+=dx;anchor.y+=dy;}
      }
      original.shift=movement;
    }
    const points=original.points,ds={x:clean(source.x-original.source.x),y:clean(source.y-original.source.y)},dt={x:clean(target.x-original.target.x),y:clean(target.y-original.target.y)};
    if(!ds.x&&!ds.y&&!dt.x&&!dt.y)return points;
    // A translated group retains all of its internal lanes and bends.
    if(ds.x===dt.x&&ds.y===dt.y)return points.map(p=>({x:p.x+ds.x,y:p.y+ds.y}));
    const s={x:points[0].x+ds.x,y:points[0].y+ds.y},t={x:points.at(-1).x+dt.x,y:points.at(-1).y+dt.y};
    if(points.length===2){
      const horizontal=points[0].y===points[1].y,channel=horizontal?(points[0].x+points[1].x)/2:(points[0].y+points[1].y)/2;
      return terminalRoute(simplifyRoute(horizontal?[s,{x:channel,y:s.y},{x:channel,y:t.y},t]:[s,{x:s.x,y:channel},{x:t.x,y:channel},t]),points,sourceBox,targetBox);
    }
    const first=points[1],last=points.at(-2);
    // Keep the ELK trunk fixed. Only reconnect moved ports orthogonally to
    // the original first/last bend; never reroute unrelated participants.
    const lead=points[0].y===first.y?{x:first.x,y:s.y}:{x:s.x,y:first.y};
    const tail=points.at(-1).y===last.y?{x:last.x,y:t.y}:{x:t.x,y:last.y};
    return terminalRoute(simplifyRoute([s,lead,...points.slice(1,-1),tail,t]),points,sourceBox,targetBox);
  }
  function finishRoutes(cy,edges=cy.edges()) {
    const geometry=routeGeometry.get(cy);if(!geometry||geometry.routes!==cy.knowledgeRoutes)return;
    for(const edge of edges){const original=geometry.edges.get(edge.id());if(!original)continue;
      original.startSource={...edge.source().position()};original.startTarget={...edge.target().position()};original.shift={x:0,y:0};
      original.basePoints=original.points.map(p=>({...p}));original.source={...edge.source().position()};original.target={...edge.target().position()};
    }
  }
  function routeEdges(cy,style,edges=cy.edges()) {
    if(!cy.knowledgeRoutes)return;
    // Cytoscape updates compound centres lazily from their children. Resolve
    // all bounds before reading any port/centre, outside the style batch.
    // Otherwise the first edge observes yesterday's centre and today's size.
    cy.nodes().forEach(node=>{node.outerWidth();node.outerHeight();});
    let geometry=routeGeometry.get(cy);
    if(geometry?.routes!==cy.knowledgeRoutes){geometry={routes:cy.knowledgeRoutes,edges:new Map()};routeGeometry.set(cy,geometry);}
    cy.batch(()=>{for(const edge of edges){
      const id=edge.id();let points=cy.knowledgeRoutes.get(id);if(!points||points.length<2)continue;
      if(specialTopology(edge))continue;
      const projected=points.map(p=>({...p}));projected[0]=borderPort(edge.source(),projected[0]);projected[projected.length-1]=borderPort(edge.target(),projected.at(-1));
      let original=geometry.edges.get(id);
      if(!original||original.rendered!==points){original={points:projected,basePoints:projected.map(p=>({...p})),source:{...edge.source().position()},target:{...edge.target().position()},startSource:{...edge.source().position()},startTarget:{...edge.target().position()},shift:{x:0,y:0},rendered:points};geometry.edges.set(id,original);}
      const box=node=>{const p=node.position(),w=node.outerWidth()/2,h=node.outerHeight()/2;return {x1:p.x-w,x2:p.x+w,y1:p.y-h,y2:p.y+h};};
      const baseline=original.basePoints.map(p=>({x:p.x+original.shift.x,y:p.y+original.shift.y})),sourcePosition=edge.source().position(),targetPosition=edge.target().position(),resized=baseline.map(p=>({...p}));
      resized[0]=borderPortAt(original.source,edge.source().outerWidth(),edge.source().outerHeight(),resized[0]);resized[resized.length-1]=borderPortAt(original.target,edge.target().outerWidth(),edge.target().outerHeight(),resized.at(-1));
      const working={...original,points:resized,source:{...original.source},target:{...original.target},shift:{...original.shift}};
      points=movedRoute(working,sourcePosition,targetPosition,box(edge.source()),box(edge.target()));
      // Changing compound bounds can shift a port along its border without
      // moving the centre. Reconnect both terminals to the retained trunk;
      // otherwise a resize leaves a diagonal segment in an orthogonal route.
      const sourceBox=box(edge.source()),targetBox=box(edge.target()),start=points[0],end=points.at(-1);
      const outward=(p,b)=>{const sides=[[Math.abs(p.x-b.x1),{x:-1,y:0}],[Math.abs(p.x-b.x2),{x:1,y:0}],[Math.abs(p.y-b.y1),{x:0,y:-1}],[Math.abs(p.y-b.y2),{x:0,y:1}]];return sides.sort((a,b)=>a[0]-b[0])[0][1];};
      const out=outward(start,sourceBox),incoming=outward(end,targetBox),first=points[1],last=points.at(-2);
      const lead=out.x?{x:first.x,y:start.y}:{x:start.x,y:first.y},tail=incoming.x?{x:last.x,y:end.y}:{x:end.x,y:last.y};
      // Keep the retained ELK interior as the fallback baseline. A synthetic
      // four-point baseline makes every incoming edge rank against the same
      // endpoint midpoint after a compound target crosses its old trunks.
      points=terminalRoute(simplifyRoute([start,lead,...points.slice(1,-1),tail,end]),points,sourceBox,targetBox);
      original.source=working.source;original.target=working.target;original.shift=working.shift;original.points=points;
      cy.knowledgeRoutes.set(id,points);original.rendered=points;
      if(!['taxi','round-taxi'].includes(style))continue;
      let s=points[0],t=points.at(-1),distanceMode='endpoints';
      // Touching ports can coincide even when their node centres differ.
      // Use that nondegenerate baseline to retain the orthogonal detour.
      if(routeNear(s.x,t.x)&&routeNear(s.y,t.y)){s=edge.source().position();t=edge.target().position();distanceMode='node-position';}
      const dx=t.x-s.x,dy=t.y-s.y,squared=dx*dx+dy*dy,length=Math.sqrt(squared);
      if(!Number.isFinite(length)||length<1e-7){
        // A coincident port has no projection baseline. Clear all old manual
        // geometry rather than displaying the previous route in a new place.
        for(const [property,value] of Object.entries({'source-endpoint':'outside-to-node','target-endpoint':'outside-to-node','edge-distances':'intersection','curve-style':style==='round-taxi'?'round-taxi':'taxi','segment-weights':'0.5','segment-distances':'0','segment-radii':'0'}))edge.style(property,value);
        continue;
      }
      const weights=[],distances=[];
      for(const p of points.slice(1,-1)){weights.push(((p.x-s.x)*dx+(p.y-s.y)*dy)/squared);distances.push(((p.y-s.y)*dx-(p.x-s.x)*dy)/length);}
      const endpoint=(node,p)=>`${(p.x-node.position('x'))/node.outerWidth()*100}% ${(p.y-node.position('y'))/node.outerHeight()*100}%`;
      edge.style('source-endpoint',endpoint(edge.source(),points[0]));edge.style('target-endpoint',endpoint(edge.target(),points.at(-1)));
      edge.style('edge-distances',distanceMode);
      edge.style('curve-style',weights.length?(style==='round-taxi'?'round-segments':'segments'):'straight');
      if(weights.length){edge.style('segment-weights',weights.join(' '));edge.style('segment-distances',distances.join(' '));edge.style('segment-radii','16');}
    }});
  }
  window.ArchitectureMap={inset,modes,branches,model,project,availability,expand,collapse,tree,fileTree,hydrateFolder,revealFile,elkLayout,routeEdges,finishRoutes,special:specialTopology};

globalThis.HubI18n?.onChange?.(()=>{Object.assign(modes,{structure:(globalThis.HubI18n?.t?.("architecture-map.816655bd716f") ?? 'Структура'),neighbors:(globalThis.HubI18n?.t?.("architecture-map.79e484b1f467") ?? 'Все связи'),interfaces:(globalThis.HubI18n?.t?.("architecture-map.8a89b9398cca") ?? 'Интерфейсы'),inheritance:(globalThis.HubI18n?.t?.("architecture-map.2167fe553fee") ?? 'Наследование'),dependencies:(globalThis.HubI18n?.t?.("architecture-map.9af957b361ca") ?? 'Зависимости')});});
})();
