(() => {
  const dialog = document.createElement('dialog');
  dialog.className = 'artifact-viewer';
  dialog.setAttribute('aria-label', (globalThis.HubI18n?.t?.("viewer.e05b680c08a7") ?? 'Просмотр результата'));
  const interfaceMarkup = () => (globalThis.HubI18n?.t ? globalThis.HubI18n.t("viewer.e31df58dc58a",{v0:(uiIcon('close')),v1:(uiIcon('search')),v2:(uiIcon('refresh')),v3:(uiIcon('info')),v4:(uiIcon('left')),v5:(uiIcon('right'))}) : `<header><div><small>РЕЗУЛЬТАТ ПРОВЕРКИ / ДОКУМЕНТ</small><h2 id="artifact-name"></h2></div><button class="icon-button" id="artifact-close" aria-label="Закрыть просмотр" title="Закрыть просмотр">${uiIcon('close')}</button></header>
    <div class="artifact-controls"><input id="artifact-search" type="search" placeholder="Поиск по файлу" aria-label="Поиск по файлу"><select id="artifact-level" aria-label="Уровень лога"><option value="">Все уровни</option><option>ERROR</option><option>WARN</option><option>INFO</option><option>DEBUG</option><option>TRACE</option></select><button class="icon-button" id="artifact-find" title="Найти" aria-label="Найти">${uiIcon('search')}</button><button class="icon-button" id="artifact-refresh" title="Обновить" aria-label="Обновить">${uiIcon('refresh')}</button><label><input id="artifact-wrap" type="checkbox" checked> Перенос строк</label><a id="artifact-raw" target="_blank" rel="noopener">Исходный текст</a></div>
    <div class="artifact-source"><div class="artifact-source-row"><label>Версия <select id="artifact-source-mode"><option value="current">Текущий файл</option><option value="archive">Архив</option></select></label><button class="icon-button" id="artifact-source-toggle" type="button" aria-expanded="false" aria-controls="artifact-provenance" aria-label="Сведения об источнике" title="Сведения об источнике">${uiIcon('info')}</button><span id="artifact-metadata"></span><span id="artifact-status" role="status"></span></div><p id="artifact-provenance" hidden></p></div>
    <div class="artifact-main"><nav id="artifact-toc" aria-label="Оглавление"></nav><div id="artifact-body" tabindex="0"></div></div><footer><button class="icon-button" id="artifact-prev" title="Предыдущая страница" aria-label="Предыдущая страница">${uiIcon('left')}</button><button class="icon-button" id="artifact-next" title="Следующая страница" aria-label="Следующая страница">${uiIcon('right')}</button></footer>`);
  dialog.innerHTML = interfaceMarkup();
  document.body.append(dialog);
  globalThis.HubI18n?.bindTemplate?.(dialog, interfaceMarkup);
  globalThis.HubI18n?.onChange?.(() => dialog.setAttribute('aria-label', globalThis.HubI18n.t("viewer.e05b680c08a7")));
  const el = id => dialog.querySelector('#artifact-' + id);
  function expandSource(expanded) {
    el('source-toggle').setAttribute('aria-expanded', String(expanded));
    el('provenance').hidden = !expanded;
  }
  el('source-toggle').onclick = () => expandSource(el('provenance').hidden);
  function showMetadata(text) {
    const lines = text ? text.split('\n').length : 0;
    el('metadata').textContent = (markdown ? 'Markdown' : language || (globalThis.HubI18n?.t?.("viewer.3091aca226ef") ?? 'Текст')) + ' · ' + lines.toLocaleString('ru') + (globalThis.HubI18n?.t?.("viewer.3494826f9512") ?? ' строк');
  }
  let path = '', mode = 'current', markdown = false, isLog = false, language = '', controller, generation = 0, cursors = [{}], page = 0, next, query = '', level = '';
  function showSource(source) {
    el('source-mode').disabled=source.kind==='artifact';
    el('source-mode').options[0].textContent=(globalThis.HubI18n?.t?.("viewer.73bd5dbb84f5") ?? 'Текущий файл')+(source.currentAvailable?'':(globalThis.HubI18n?.t?.("viewer.08f9276429ab") ?? ' — недоступен'));
    el('source-mode').options[1].textContent=(globalThis.HubI18n?.t?.("viewer.3c54b5e783ef") ?? 'Архив')+(source.archiveAvailable?'':(globalThis.HubI18n?.t?.("viewer.08f9276429ab") ?? ' — недоступен'));
    const kind=source.kind==='artifact'?(globalThis.HubI18n?.t?.("viewer.26880b14605e") ?? 'Сохранённая версия'):source.kind==='archive'?(globalThis.HubI18n?.t?.("viewer.3c54b5e783ef") ?? 'Архив'):(globalThis.HubI18n?.t?.("viewer.73bd5dbb84f5") ?? 'Текущий файл');
    const details=[kind+(source.available?'':(globalThis.HubI18n?.t?.("viewer.08f9276429ab") ?? ' — недоступен')), (globalThis.HubI18n?.t?.("viewer.e180df6170c8") ?? 'Исходный проект: ')+(source.sourceProject || source.projectRoot || (globalThis.HubI18n?.t?.("viewer.f250ed099246") ?? 'не указан')), (globalThis.HubI18n?.t?.("viewer.03fb8ea87dd6") ?? 'Путь: ')+source.path];
    if(source.projectRoot)details.push((globalThis.HubI18n?.t?.("viewer.00d10c9b1342") ?? 'Корень проекта: ')+source.projectRoot);
    if(source.resolvedPath)details.push((globalThis.HubI18n?.t?.("viewer.eed27cb94cd7") ?? 'Файл: ')+source.resolvedPath);
    if(source.version)details.push((globalThis.HubI18n?.t?.("viewer.06629efecaad") ?? 'Версия: ')+source.version);
    if(source.modifiedAt)details.push((globalThis.HubI18n?.t?.("viewer.b7292c143b9f") ?? 'Изменён файл: ')+source.modifiedAt);
    el('provenance').textContent=details.join('\n');
    el('provenance').classList.toggle('source-unavailable',!source.available);
    el('raw').hidden=!source.available;
    el('raw').textContent=source.kind==='artifact'?(globalThis.HubI18n?.t?.("viewer.71ad39a4e9fd") ?? 'Скачать оригинал'):(globalThis.HubI18n?.t?.("viewer.290773056a2d") ?? 'Исходный текст');
    if(source.available)el('raw').href=window.projectApi((source.kind==='artifact'?'/api/artifact?':'/api/evidence?')+new URLSearchParams({path,mode}));
    else el('raw').removeAttribute('href');
  }
  const languages={java:'java',js:'javascript',mjs:'javascript',ts:'typescript',tsx:'typescript',jsx:'javascript',py:'python',json:'json',xml:'xml',html:'xml',css:'css',sql:'sql',sh:'bash',bash:'bash',ps1:'powershell',c:'c',h:'c',cpp:'cpp',hpp:'cpp',cs:'csharp',yml:'yaml',yaml:'yaml',properties:'properties',gradle:'groovy'};
  const matches=document.createElement('span');matches.id='artifact-matches';matches.setAttribute('role','status');
  const previousMatch=document.createElement('button');previousMatch.innerHTML=uiIcon('up');previousMatch.className='icon-button';previousMatch.title=(globalThis.HubI18n?.t?.("viewer.bff46c40e8c2") ?? 'Предыдущее совпадение');previousMatch.setAttribute('aria-label',previousMatch.title);
  const nextMatch=document.createElement('button');nextMatch.innerHTML=uiIcon('down');nextMatch.className='icon-button';nextMatch.title=(globalThis.HubI18n?.t?.("viewer.7a5ce21fed83") ?? 'Следующее совпадение');nextMatch.setAttribute('aria-label',nextMatch.title);
  dialog.querySelector('.artifact-controls').append(previousMatch,nextMatch,matches);
  let matchIndex=-1;
  const MAX_HIGHLIGHT_CHARS=200000, MAX_MATCHES=1000;
  let matchLimitReached=false, markedCount=0;
  function moveMatch(delta){const list=el('body').querySelectorAll('mark[data-search-match]');if(!list.length)return;matchIndex=(matchIndex+delta+list.length)%list.length;list.forEach(m=>m.classList.remove('current-match'));list[matchIndex].classList.add('current-match');list[matchIndex].scrollIntoView({block:'center'});matches.textContent=`${matchIndex+1} / ${list.length}${isLog?(globalThis.HubI18n?.t?.("viewer.45dd15b006e0") ?? ' на странице'):''}`;}
  previousMatch.onclick=()=>moveMatch(-1);nextMatch.onclick=()=>moveMatch(1);
  function highlightMatches(){
    if(!query)return;
    const walker=document.createTreeWalker(el('body'),NodeFilter.SHOW_TEXT),nodes=[];
    let text='';while(walker.nextNode()){const node=walker.currentNode;nodes.push({node,start:text.length});text+=node.textContent;}
    const lower=text.toLocaleLowerCase(),needle=query.toLocaleLowerCase(),ranges=[];
    let at=0;while((at=lower.indexOf(needle,at))!==-1){if(ranges.length===MAX_MATCHES){matchLimitReached=true;break;}ranges.push({start:at,end:at+query.length});at+=query.length;}
    let cursor=0;
    for(const {node,start} of nodes){
      const value=node.textContent,end=start+value.length,fragment=document.createDocumentFragment();let position=0;
      while(cursor<ranges.length && ranges[cursor].end<=start)cursor++;
      for(let i=cursor;i<ranges.length && ranges[i].start<end;i++){
        const range=ranges[i],left=Math.max(start,range.start)-start,right=Math.min(end,range.end)-start;
        fragment.append(document.createTextNode(value.slice(position,left)));
        const mark=document.createElement('mark');mark.textContent=value.slice(left,right);if(range.start>=start)mark.dataset.searchMatch='';fragment.append(mark);position=right;
      }
      if(position){fragment.append(document.createTextNode(value.slice(position)));node.replaceWith(fragment);}
    }
  }
  el('close').onclick = () => dialog.close();
  dialog.addEventListener('close', () => { controller?.abort(); generation++; expandSource(false); });
  el('wrap').onchange = () => el('body').classList.toggle('no-wrap', !el('wrap').checked);
  async function response(url, signal, asJson) {
    const r = await fetch(window.projectApi(url), {signal, cache:'no-store'});
    if (!r.ok) { let message = 'HTTP ' + r.status; try { message = (await r.json()).error || message; } catch {} throw Error(message); }
    return asJson ? r.json() : r.text();
  }
  function markText(parent, text) {
    if (!query) { parent.append(document.createTextNode(text)); return; }
    let start = 0, index;
    const lower = text.toLocaleLowerCase(), needle = query.toLocaleLowerCase();
    while ((index = lower.indexOf(needle, start)) !== -1) {
      if(markedCount===MAX_MATCHES){matchLimitReached=true;break;}markedCount++;
      parent.append(document.createTextNode(text.slice(start,index)));
      const mark = document.createElement('mark'); mark.dataset.searchMatch=''; mark.textContent=text.slice(index,index+query.length); parent.append(mark); start=index+query.length;
    }
    parent.append(document.createTextNode(text.slice(start)));
  }
  function renderMarkdown(text) {
    el('body').innerHTML = DOMPurify.sanitize(marked.parse(text), {
      USE_PROFILES:{html:true}, FORBID_TAGS:['img','style','form','input','button','iframe','audio','video'], FORBID_ATTR:['style','id','name']
    });
    el('toc').replaceChildren();
    el('body').querySelectorAll('h1,h2,h3').forEach(heading => {
      const button=document.createElement('button'); button.textContent=heading.textContent;
      button.className=heading.tagName.toLowerCase(); button.onclick=()=>heading.scrollIntoView({block:'start',behavior:'smooth'}); el('toc').append(button);
    });
    el('body').querySelectorAll('a').forEach(link => {
      const href=link.getAttribute('href') || '';
      if (href.startsWith('#')) {
        link.onclick=e=>{e.preventDefault(); const name=decodeURIComponent(href.slice(1)); [...el('body').querySelectorAll('h1,h2,h3,h4')].find(h=>h.textContent.toLowerCase().replace(/[^\p{L}\p{N} -]/gu,'').replace(/ /g,'-')===name)?.scrollIntoView();};
      } else if (/^https?:\/\//i.test(href)) { link.target='_blank'; link.rel='noopener noreferrer'; }
      else if (href && !/^[a-z][a-z\d+.-]*:|^\/\//i.test(href)) {
        link.onclick=e=>{ e.preventDefault(); const resolved=new URL(href,'https://hub.local/'+path); open(decodeURIComponent(resolved.pathname.slice(1)),mode); };
      } else { link.removeAttribute('href'); }
    });
    el('body').querySelectorAll('pre code').forEach(code=>hljs.highlightElement(code));
    highlightMatches();
  }
  async function load() {
    if (/^(?:hub-source\/[^/]+\/)?hub-artifact\/[a-f0-9]{64}\//.test(path)) {
      mode='current';el('source-mode').value=mode;
    }
    controller?.abort(); controller=new AbortController(); const run=++generation;
    let sourceKnown=false;
    el('metadata').textContent='';
    el('status').textContent=(globalThis.HubI18n?.t?.("viewer.db491ef5033f") ?? 'Загрузка…'); el('next').disabled=el('prev').disabled=true;
    matches.textContent=''; previousMatch.disabled=nextMatch.disabled=true;
    matchLimitReached=false;markedCount=0;
    el('body').replaceChildren(); el('toc').replaceChildren();
    el('provenance').textContent=(globalThis.HubI18n?.t?.("viewer.4701c6618f9a") ?? 'Проверка источника…');el('provenance').classList.remove('source-unavailable');
    el('raw').hidden=true;el('raw').removeAttribute('href');
    el('source-mode').options[0].textContent=(globalThis.HubI18n?.t?.("viewer.73bd5dbb84f5") ?? 'Текущий файл');el('source-mode').options[1].textContent=(globalThis.HubI18n?.t?.("viewer.3c54b5e783ef") ?? 'Архив');
    try {
      const sourceParams=new URLSearchParams({path,mode});
      let data, source;
      if (typeof isImagePath === 'function' && isImagePath(path)) {
        dialog.close();openImageDialog(path,mode);return;
      }
      try {
        const params = isLog ? new URLSearchParams({path,mode,search:query,level,...cursors[page]}) : sourceParams;
        data=await response((isLog?'/api/log?':'/api/document?')+params,controller.signal,true);
        source=data.source;
      } catch (error) {
        if (error.name==='AbortError' || run!==generation) throw error;
        // Successful document/log responses already carry source provenance.
        // Fetch it separately only to explain unavailable files and archives.
        source=await response('/api/source?'+sourceParams,controller.signal,true);
        if(run!==generation)return;sourceKnown=true;showSource(source);
        if (source.available && !source.image && !(source.kind==='artifact' && !source.textPreviewAvailable)) throw error;
      }
      if(run!==generation)return;sourceKnown=true;showSource(source);
      if(source.image){dialog.close();openImageDialog(path,mode);return;}
      if(source.kind==='artifact' && !source.textPreviewAvailable){el('status').textContent=(globalThis.HubI18n?.t?.("viewer.ec9799f58d28") ?? 'Предпросмотр этого формата недоступен. Скачайте оригинал.');return;}
      if(!source.available){el('status').textContent=(mode==='current'?(globalThis.HubI18n?.t?.("viewer.85d6f365a958") ?? 'Текущий файл недоступен.'):(globalThis.HubI18n?.t?.("viewer.72493200f71b") ?? 'Архив недоступен.'))+(mode==='current' && source.archiveAvailable?(globalThis.HubI18n?.t?.("viewer.6c82309d10a9") ?? ' Выберите «Архив», чтобы открыть сохранённую копию.'):'');return;}
      if (markdown) {
        if(run!==generation)return;showSource(data.source);const text=data.text;renderMarkdown(text);showMetadata(text);
        el('status').textContent=text.length.toLocaleString('ru')+(globalThis.HubI18n?.t?.("viewer.6ed48a8b7992") ?? ' символов · поиск по всему документу');
      } else if (!isLog) {
        if(run!==generation)return;showSource(data.source);const text=data.text;
        const pre=document.createElement('pre'),code=document.createElement('code');code.textContent=text;pre.append(code);el('body').append(pre);
        if(text.length<=MAX_HIGHLIGHT_CHARS && language && hljs.getLanguage(language)){code.className='language-'+language;hljs.highlightElement(code);}
        highlightMatches();showMetadata(text);
        el('status').textContent=(globalThis.HubI18n?.t?.("viewer.4a2100cda048") ?? 'Поиск по всему документу');
        if(language && text.length>MAX_HIGHLIGHT_CHARS)el('status').textContent+=(globalThis.HubI18n?.t?.("viewer.a39c29b5ee8f") ?? ' · подсветка синтаксиса отключена для большого файла (более 200 000 символов)');
      } else {
        if(run!==generation)return;showSource(data.source);
        el('metadata').textContent=(globalThis.HubI18n?.t?.("viewer.b3ccc59590ee") ?? 'Лог · ')+data.rows.length.toLocaleString('ru')+(globalThis.HubI18n?.t?.("viewer.7eb8ace9b2c2") ?? ' строк на странице');
        for(const row of data.rows){const div=document.createElement('div');div.className='log-line log-'+row.level.toLowerCase();const number=document.createElement('span');number.className='log-number';number.textContent=row.line;const content=document.createElement('code');markText(content,row.text);div.append(number,content);el('body').append(div);}
        next=data.more ? {offset:data.next,line:data.line,previous:data.previous,version:data.version} : null;
        el('status').textContent=(globalThis.HubI18n?.t ? globalThis.HubI18n.t("viewer.ac4099041126",{v0:(page+1),v1:(data.rows.length),v2:(Math.round(data.next/Math.max(data.size,1)*100)),v3:(data.rows.length?'':(globalThis.HubI18n?.t?.("viewer.c6ccb12e93d2") ?? ' · совпадений в этом фрагменте нет')),v4:(data.rows.some(r=>r.continued)?(globalThis.HubI18n?.t?.("viewer.1f59f34f93ed") ?? ' · длинные строки разбиты на фрагменты'):'')}) : `Страница ${page+1} · ${data.rows.length} строк · просмотрено до ${Math.round(data.next/Math.max(data.size,1)*100)}% файла${data.rows.length?'':(globalThis.HubI18n?.t?.("viewer.c6ccb12e93d2") ?? ' · совпадений в этом фрагменте нет')}${data.rows.some(r=>r.continued)?(globalThis.HubI18n?.t?.("viewer.1f59f34f93ed") ?? ' · длинные строки разбиты на фрагменты'):''}`);
        el('next').disabled=!next; el('prev').disabled=page===0;
      }
      matchIndex=-1;const count=el('body').querySelectorAll('mark[data-search-match]').length;
      if(matchLimitReached)el('status').textContent+=(globalThis.HubI18n?.t?.("viewer.a64bbaf6eac4") ?? ' · показаны первые 1 000 совпадений; уточните запрос');
      matches.textContent=query ? (globalThis.HubI18n?.t ? globalThis.HubI18n.t("viewer.5084779772c5",{v0:(count),v1:(isLog?(globalThis.HubI18n?.t?.("viewer.45dd15b006e0") ?? ' на странице'):'')}) : `${count} совпадений${isLog?(globalThis.HubI18n?.t?.("viewer.45dd15b006e0") ?? ' на странице'):''}`) : '';
      previousMatch.disabled=nextMatch.disabled=!count;
      if (count) moveMatch(1);else el('body').scrollTop=0;
    }catch(error){if(error.name!=='AbortError' && run===generation){if(!sourceKnown)el('provenance').textContent=(globalThis.HubI18n?.t?.("viewer.43262aa7a4eb") ?? 'Не удалось проверить источник.');el('status').textContent=(globalThis.HubI18n?.error?.(error) ?? error.message).startsWith('Source exceeds preview limit')?(globalThis.HubI18n?.t?.("viewer.44f7045db1ff") ?? 'Файл превышает лимит встроенного просмотра (4 МБ). Откройте его в редакторе проекта.'):(globalThis.HubI18n?.t?.("viewer.5765af8408a4") ?? 'Не удалось открыть: ')+(globalThis.HubI18n?.error?.(error) ?? error.message);el('prev').disabled=page===0;}}
  }
  function reset(){query=el('search').value;level=el('level').value;cursors=[{}];page=0;load();}
  function open(source,sourceMode='current'){const defaults=typeof projectSettings==='function'?projectSettings().viewer:{wrapLines:true,showSourceDetails:false};el('wrap').checked=defaults.wrapLines;el('body').classList.toggle('no-wrap',!defaults.wrapLines);expandSource(defaults.showSourceDetails);path=source;mode=sourceMode==='archive'?'archive':'current';el('source-mode').value=mode;markdown=/\.(md|markdown)$/i.test(path);isLog=/\.(log|out|err)(\.\d+)?$/i.test(path);language=languages[path.split('.').pop().toLowerCase()]||'';el('name').textContent=path;el('body').classList.toggle('markdown-body',!isLog);el('toc').hidden=!markdown;el('level').hidden=!isLog;el('next').hidden=el('prev').hidden=!isLog;el('search').placeholder=isLog?(globalThis.HubI18n?.t?.("viewer.45a466a3dfac") ?? 'Поиск по логу; «Далее» продолжает сканирование'):(globalThis.HubI18n?.t?.("viewer.4a2100cda048") ?? 'Поиск по всему документу');el('search').value='';el('level').value='';if(!dialog.open)dialog.showModal();reset();}
  el('source-mode').onchange=()=>{mode=el('source-mode').value;reset();};
  el('find').onclick=el('refresh').onclick=reset;el('level').onchange=reset;
  el('search').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();reset();}};
  el('next').onclick=()=>{if(next){cursors[++page]=next;load();}};
  el('prev').onclick=()=>{if(page){page--;load();}};
  document.addEventListener('click',event=>{const link=event.target.closest('a[href^="/api/evidence?"]');if(!link||dialog.contains(link)||event.ctrlKey||event.metaKey||event.shiftKey)return;const params=new URL(link.href).searchParams;if(params.get('preview')==='html')return;event.preventDefault();open(params.get('path'));});
})();
