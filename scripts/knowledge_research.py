"""On-demand exploration fragments. Results never mutate the canonical catalog."""
from __future__ import annotations

from collections import deque, OrderedDict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
import threading
import time
import uuid

from knowledge_store import KnowledgeError, canonical, now

_LOCK = threading.Lock()
_NEGOTIATED = {}
_RESULTS = OrderedDict()
_CACHE_VERSION = 3
_RECURSIVE_OPERATIONS = ('incoming-calls','outgoing-calls','base-types','implementations')
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='knowledge-research')
_BROWSE_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='knowledge-browse')
_INHERITANCE = {'extends', 'implements', 'inherits', 'inheritance'}
OPERATIONS = {
    'children': ('Подсистемы следующего уровня', 'Состав без раскрытия всех потомков'),
    'own-code': ('Собственные элементы', 'Код, принадлежащий непосредственно этому разделу'),
    'definitions': ('Определения внутри', 'Содержимое файла или элемента'),
    'outgoing': ('Что использует элемент', 'Исходящие статические связи'),
    'incoming': ('Кто использует элемент', 'Входящие статические связи'),
    'base-types': ('Базовые типы', 'Объявленное наследование и реализация'),
    'implementations': ('Наследники и реализации', 'Обратные связи типов'),
    'path': ('Связь между A и B', 'Кратчайший направленный путь по доступным фактам'),
    'symbols': ('Структура исходника', 'Определения языкового сервера'),
    'definition': ('Перейти к определению', 'Разрешение символа языковым сервером'),
    'references': ('Ссылки на символ', 'Места использования языкового сервера'),
    'incoming-calls': ('Кто вызывает', 'Входящие вызовы языкового сервера'),
    'outgoing-calls': ('Что вызывает', 'Исходящие вызовы языкового сервера'),
}


def setup(store):
    with _LOCK:
        if getattr(store.registry,'_research_schema_ready',False):return
        with store.registry.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS knowledge_research(project TEXT NOT NULL,id TEXT NOT NULL,cache_key TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(project,id))')
            c.execute('CREATE INDEX IF NOT EXISTS knowledge_research_cache ON knowledge_research(project,cache_key)')
            c.execute("CREATE INDEX IF NOT EXISTS knowledge_research_subject ON knowledge_research(project,json_extract(body,'$.query.id'))")
            c.execute('CREATE TABLE IF NOT EXISTS knowledge_research_objects(project TEXT NOT NULL,id TEXT NOT NULL,result TEXT NOT NULL,basis TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(project,id,result))')
        store.registry._research_schema_ready=True


def providers(store):
    """Executables are administrator configuration, never supplied by a web request."""
    path = store.registry.home / 'language-servers.json'
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        configs = value.get('providers', [])
        if not isinstance(configs, list):
            raise ValueError('providers must be a list')
        for config in configs:
            if not isinstance(config, dict) or not isinstance(config.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', config['id']):
                raise ValueError('provider needs an id')
            command = config.get('command')
            if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
                raise ValueError('command must be a nonempty argument array')
            if not isinstance(config.get('languages'), list) or not config['languages'] or not all(isinstance(x,str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',x) for x in config['languages']):
                raise ValueError('languages must be a list')
        return configs
    except (OSError, ValueError) as error:
        raise KnowledgeError('provider_configuration', str(error), 400) from error


def language(item):
    path = item.get('source', {}).get('path', '')
    return item.get('language') or {'.java':'java', '.py':'python', '.ts':'typescript', '.tsx':'typescript', '.js':'javascript', '.cpp':'cpp', '.json':'json'}.get(__import__('pathlib').Path(path).suffix, 'other')


def source_content_hash(store, path, stat=None):
    """Share bounded, metadata-validated byte hashes across research operations."""
    import os
    path=Path(path)
    cache=getattr(store.registry,'_research_source_hashes',None)
    if cache is None:
        with _LOCK:
            cache=getattr(store.registry,'_research_source_hashes',None)
            if cache is None:cache={};store.registry._research_source_hashes=cache
    try:
        stat=path.stat() if os.name=='nt' else stat or path.stat()
        stamp=(stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size,stat.st_ino)
        key=str(path);prior=cache.get(key)
        if prior and prior[0]==stamp:return prior[1]
        value=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(65536),b''):value.update(chunk)
        after=path.stat()
        if stamp==(after.st_mtime_ns,after.st_ctime_ns,after.st_size,after.st_ino):
            with _LOCK:
                if len(cache)>=20000:cache.clear()
                cache[key]=(stamp,value.digest())
        return value.digest()
    except (OSError,ValueError,TypeError):return b'missing-or-unreadable'


def read_object(store, identifier, *, check_fresh=True, basis=None):
    if identifier == 'project:' + store.project:
        try:
            item = store.read(identifier)
            return dict(item, components=store.context()['policy'].get('components', []))
        except KnowledgeError as error:
            if error.body['error'] != 'item_missing':
                raise
        with store.registry.connect() as connection:
            row = connection.execute('SELECT name FROM spaces WHERE id=?', (store.project,)).fetchone()
        return dict(id=identifier, kind='entity', type='project', title=row['name'],
                    components=store.context()['policy'].get('components', []), virtual=True)
    if identifier.startswith('directory:'):
        relative = identifier.removeprefix('directory:')
        if any(part.casefold() in {'.git','.codex','.agents'} for part in Path(relative).parts):
            raise KnowledgeError('unsafe_source','Protected directory is not research scope',400)
        base, physical = store.source_location(relative)
        if not physical.is_dir():
            raise KnowledgeError('item_missing', 'Source directory is unavailable', 404)
        relative = physical.relative_to(base).as_posix()
        return dict(id=identifier, kind='entity', type='directory', title=relative,
                    source={'path': identifier.removeprefix('directory:'), 'line': 1})
    try:
        item = store.read(identifier)
        if check_fresh and item.get('analysisSourceHash'):
            try:
                current = source_content_hash(store,store.source_path(item['source']['path'])).hex()
            except OSError:
                current = None
            if current != item['analysisSourceHash']:
                raise KnowledgeError('stale_object','Файл символа изменился. Обновите определения этого файла.',409)
        return item
    except KnowledgeError as error:
        if error.body['error'] != 'item_missing': raise
    setup(store)
    with store.registry.connect() as c:
        row=c.execute('SELECT body,basis FROM knowledge_research_objects WHERE project=? AND id=? ORDER BY rowid DESC LIMIT 1',(store.project,identifier)).fetchone()
        if not row:
            # Compatibility with fragments created before the object index.
            row=c.execute("SELECT n.value,json_extract(r.body,'$.fingerprint') AS basis FROM knowledge_research r,json_each(r.body,'$.nodes') n WHERE r.project=? AND json_extract(n.value,'$.id')=? ORDER BY r.rowid DESC LIMIT 1",(store.project,identifier)).fetchone()
    if not row: raise KnowledgeError('item_missing','Research object is unavailable',404)
    item=json.loads(row[0])
    if item.get('source'): store.source_location(item['source']['path'])
    if check_fresh:
        if item.get('analysisSourceHash'):
            try:current=source_content_hash(store,store.source_path(item['source']['path'])).hex()
            except OSError:current=None
            if current!=item['analysisSourceHash']:raise KnowledgeError('stale_object','Файл символа изменился. Обновите определения этого файла.',409)
        else:
            current=basis if basis is not None else fingerprint(store)[0]
            if row['basis'] != current: raise KnowledgeError('stale_object','Сохранённый фрагмент устарел. Обновите структуру исходника; это не обязательно означает изменение самого файла.',409)
    return item


def continuation_operations(item):
    """Retain the server traversal action without inventing a symbol kind."""
    recorded=item.get('semanticOperations')
    return [op for op in _RECURSIVE_OPERATIONS if isinstance(recorded,list) and op in recorded]


def capabilities(store, identifier):
    item = read_object(store, identifier,check_fresh=False)
    kind = item.get('type')
    descendants=not item.get('isFinal') and not (language(item)=='java' and kind in {'record','enum'})
    if item['kind'] == 'relation':
        applicable = []
    elif item['kind'] == 'view':
        applicable = []
    elif kind == 'directory':
        applicable = ['own-code']
    elif kind == 'component':
        applicable = ['children', 'own-code', 'outgoing', 'incoming']
    elif kind == 'file':
        applicable = ['definitions', 'outgoing', 'incoming']
    elif kind in {'method','function','field','property','variable','constant','constructor'}:
        applicable = ['incoming']
    elif kind in {'module','namespace','package'} and item.get('source') and language(item)=='java':
        applicable = ['incoming']
    elif kind in {'class','interface','record','enum','type','module','namespace','package'}:
        applicable = ['definitions', 'outgoing', 'incoming']
        # Syntax providers establish type relationships only for these kinds.
        if kind in {'class', 'interface', 'record', 'enum', 'type'}:
            applicable += ['base-types']+(['implementations'] if descendants else [])
    else:
        applicable = ['incoming']
    configs = providers(store)
    configured = next((p for p in configs if language(item) in p['languages']), None)
    operations = [dict(id=op, title=OPERATIONS[op][0], description=OPERATIONS[op][1], provider='catalog', status='available') for op in applicable if not (op=='definitions' and item.get('source') and kind!='file')]
    if item.get('source') and kind != 'directory':
        deep=['symbols'] if kind=='file' else ['incoming'] if kind in {'package','namespace'} and language(item)=='java' else ['definition','incoming']
        if kind in {'class','interface','record','enum','type'} or kind in {'module','namespace','package'} and language(item)!='java':deep.insert(0,'definitions')
        if kind in {'method','function','constructor'}:deep+=['incoming-calls','outgoing-calls']
        if kind in {'class','interface','record','enum','type'}:deep+=['base-types']+(['implementations'] if descendants else [])
        deep += [op for op in continuation_operations(item) if op not in deep]
        negotiated=_NEGOTIATED.get((store.project,configured['id'],canonical(configured))) if configured else None
        for op in deep:
            from knowledge_lsp import LspManager
            supported=negotiated is None or LspManager._supports(negotiated,semantic_operation(op,kind))
            operations.append(dict(id=op,title=OPERATIONS[op][0]+(' · сервер' if op in applicable and op!='definitions' else ''),description=OPERATIONS[op][1],provider=configured['id'] if configured else 'lsp',status=('available' if negotiated else 'prepare') if configured and supported else 'unsupported' if configured else 'unconfigured',reason='Server capability unavailable' if not supported else '' if configured else 'Языковой сервер не настроен'))
    setup(store)
    with store.registry.connect() as c:
        recent=[json.loads(row[0]) for row in c.execute("SELECT body FROM knowledge_research WHERE project=? AND json_extract(body,'$.query.id')=? ORDER BY rowid DESC LIMIT 12",(store.project,identifier))]
    analyses=[dict(operation=r['query']['operation'],provider=r.get('provider',r['query'].get('provider','catalog')),status=r['status'],createdAt=r['createdAt'],nodes=len(r['nodes']),relations=len(r['relations']),fingerprintScope=r.get('fingerprintScope','sources')) for r in recent]
    return dict(id=identifier, language=language(item), operations=operations, analyses=analyses,
                providers=[dict(id=p['id'], languages=p['languages']) for p in configs],
                coverage='Сохранённые факты не доказывают отсутствие связей. Актуальность кэша проверяется автоматически при запуске.')


def semantic_operation(operation,kind):
    return 'symbols' if operation in {'definitions','symbols'} else 'references' if operation=='incoming' else operation


def resolve_source(store,query):
    """Choose by symbol kind and negotiated capability, never by language name."""
    query=dict(query)
    if query.get('provider')!='auto':return query
    query['automatic']=True
    item=read_object(store,query['id'],check_fresh=False)
    kind=item.get('type');op=query['operation']
    config=next((p for p in providers(store) if language(item) in p['languages']),None)
    semantic_ops={'symbols','definition','references','incoming-calls','outgoing-calls','definitions'}
    if kind not in {'component','directory','file'}:semantic_ops|={'incoming','base-types','implementations'}
    semantic_ops.update(continuation_operations(item))
    if item.get('source') and op in semantic_ops and config:
        from knowledge_lsp import LspManager
        negotiated=_NEGOTIATED.get((store.project,config['id'],canonical(config)))
        if negotiated is None or LspManager._supports(negotiated,semantic_operation(op,kind)):
            query['provider']=config['id']
            if semantic_operation(op,kind) in {'symbols','definition','references'}:query['depth']=1
            return query
    if op in {'symbols','definition','references','incoming-calls','outgoing-calls'} or op=='definitions' and kind not in {'component','file','directory'}:
        raise KnowledgeError('semantic_unavailable','Семантический анализ не настроен или сервер не поддерживает это действие. Это не означает отсутствие связей.',400)
    query.update(provider='catalog',catalogOnly=not(op=='path' and (query['id'].startswith('research:') or query.get('target','').startswith('research:'))))
    return query


def validate_query(store, query):
    if not isinstance(query, dict) or set(query) - {'operation','id','target','depth','representation','provider','line','column','catalogOnly','intent'}:
        raise KnowledgeError('invalid_query', 'Unknown research query field', 400)
    query = dict(query)
    if query.get('intent','research') not in {'browse','research'}:
        raise KnowledgeError('invalid_query','Unknown research intent',400)
    if query.get('operation') not in OPERATIONS or not isinstance(query.get('id'), str):
        raise KnowledgeError('invalid_query', 'An operation and an object are required', 400)
    read_object(store, query['id'],check_fresh=False)
    if 'catalogOnly' in query and (not isinstance(query['catalogOnly'],bool) or query['catalogOnly'] and (query.get('provider','catalog')!='catalog' or query['operation'] in {'symbols','definition','references','incoming-calls','outgoing-calls'})):
        raise KnowledgeError('invalid_query','Catalog browsing cannot bypass semantic source validation',400)
    if query['operation'] == 'path':
        if not isinstance(query.get('target'), str):
            raise KnowledgeError('invalid_query', 'Path search requires B', 400)
        read_object(store, query['target'],check_fresh=False)
    depth = query.setdefault('depth', 1)
    if depth != 'all' and (isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 10000):
        raise KnowledgeError('invalid_query', 'Depth must be a positive integer or all', 400)
    if query.setdefault('representation', 'symbols') not in {'symbols','files','symbols-in-files'}:
        raise KnowledgeError('invalid_query', 'Unknown representation', 400)
    for field in ['line', 'column']:
        if field in query and (isinstance(query[field], bool) or not isinstance(query[field], int) or query[field] < 1):
            raise KnowledgeError('invalid_query', field+' must be positive', 400)
    if query['operation'] != 'path' and query['operation'] not in [op['id'] for op in capabilities(store, query['id'])['operations']]:
        raise KnowledgeError('unsupported_operation', 'Operation does not apply to this object', 400)
    return query


def fingerprint(store, *, revision_basis=None):
    """Incremental source content manifest; no Git HEAD-only freshness check."""
    import os
    from knowledge_scan import EXCLUDED, LANGUAGES
    digest=hashlib.sha256()
    with store.registry.connect() as c:
        row=c.execute('SELECT revision,policy FROM knowledge_meta WHERE project=?',(store.project,)).fetchone()
        revision=row['revision'];policy=json.loads(row['policy'])
        sources=[json.loads(row[0]).get('source',{}) for row in c.execute("SELECT body FROM knowledge_items WHERE project=? AND kind='entity' AND json_extract(body,'$.type')='file' ORDER BY id",(store.project,))]
    digest.update(str(revision if revision_basis is None else revision_basis).encode())
    excluded=EXCLUDED|set(policy.get('excludeDirectories',[]))
    descriptors={'pom.xml','build.gradle','build.gradle.kts','settings.gradle','settings.gradle.kts','gradle.properties','package.json','package-lock.json','tsconfig.json','pyproject.toml','compile_commands.json'}
    def content(path,stat=None):
        return source_content_hash(store,path,stat)
    seen=set()
    for index,root in enumerate(store.roots):
        pending=[root]
        while pending:
            directory=pending.pop()
            try:
                with os.scandir(directory) as entries:entries=sorted(entries,key=lambda e:e.name)
            except OSError:
                digest.update(canonical([index,str(directory),'unreadable']).encode());continue
            directories=[]
            for entry in entries:
                if entry.is_symlink() or getattr(entry,'is_junction',lambda:False)():continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in excluded:directories.append(Path(entry.path))
                    continue
                path=Path(entry.path)
                if path.suffix not in LANGUAGES and entry.name not in descriptors:continue
                if not entry.is_file(follow_symlinks=False):continue
                relative=path.relative_to(root).as_posix()
                seen.add(relative if index==0 else f'@roots/{index}/'+relative)
                digest.update(canonical([index,relative]).encode());digest.update(content(path,entry.stat(follow_symlinks=False)))
            pending.extend(reversed(directories))
    # Catalog resources outside the normal language inventory also affect queries.
    for source in sources:
        digest.update(canonical(source).encode())
        path=source.get('path')
        if path and path not in seen:
            try:digest.update(content(store.source_path(path)))
            except (OSError,ValueError,TypeError):digest.update(b'missing-or-unreadable')
    config=store.registry.home/'language-servers.json'
    if config.exists():digest.update(content(config))
    return digest.hexdigest(),revision


def catalog_fingerprint(store):
    """Stored composition depends on its catalog, not a filesystem traversal."""
    with store.registry.connect() as c:
        revision=c.execute('SELECT revision FROM knowledge_meta WHERE project=?',(store.project,)).fetchone()[0]
    return 'catalog:'+str(revision),revision


def catalog_items(store, query, stopped):
    """Indexed frontier reads for stored views, without decoding the whole DB."""
    items={}; aliases={}; truncated=False; deadline=time.monotonic()+30
    with store.registry.connect() as c:
        def read_ids(ids):
            ids=list(set(ids)-items.keys())
            for offset in range(0,len(ids),300):
                batch=ids[offset:offset+300]
                rows=c.execute('SELECT body FROM knowledge_items WHERE project=? AND id IN ('+','.join('?' for _ in batch)+')',(store.project,*batch))
                for row in rows:
                    item=json.loads(row[0]);items[item['id']]=item
        def relations(field,ids):
            result=[];ids=[next((original for original,alias in aliases.items() if alias==i),i) for i in ids]
            for offset in range(0,len(ids),300):
                batch=ids[offset:offset+300]
                rows=c.execute("SELECT body FROM knowledge_items WHERE project=? AND kind='relation' AND json_extract(body,'$."+field+"') IN ("+','.join('?' for _ in batch)+')',(store.project,*batch))
                for row in rows:
                    edge=json.loads(row[0])
                    if edge.get('from') in aliases or edge.get('to') in aliases:
                        edge={**edge,'id':'research:edge:'+hashlib.sha256(canonical([edge['id'],query['id']]).encode()).hexdigest()[:24],'from':aliases.get(edge['from'],edge['from']),'to':aliases.get(edge['to'],edge['to'])}
                    if edge.get('type')=='via-files' and edge.get('pathEdges'):
                        for original in edge.get('via',[])+edge['pathEdges']:items.setdefault(original['id'],original)
                        result.extend(edge['pathEdges'])
                    else:items[edge['id']]=edge;result.append(edge)
            return result
        read_ids([query['id']]);origin=items.get(query['id'])
        if not origin and query['id'].startswith('directory:'):
            origin=read_object(store,query['id'],check_fresh=False)
            # A directory is navigation scope, never an artificial graph node.
            prefix=origin['source']['path'].rstrip('/')+'/'
            rows=c.execute("SELECT body FROM knowledge_items WHERE project=? AND kind='entity' AND substr(json_extract(body,'$.source.path'),1,?)=?",(store.project,len(prefix),prefix))
            for row in rows:
                node=json.loads(row[0]);items[node['id']]=node
            relations('from',list(items))
            return [origin,*items.values()],False
        if not origin and query['id'].startswith('research:'):
            origin=read_object(store,query['id'],check_fresh=False)
            items[origin['id']]=origin
            if origin.get('source') and origin.get('type') in {'class','interface','record','enum','type'}:
                rows=c.execute("SELECT id,body FROM knowledge_items WHERE project=? AND kind='entity' AND json_extract(body,'$.source.path')=? AND json_extract(body,'$.title')=?",(store.project,origin['source']['path'],origin['title']))
                candidates=[json.loads(row['body']) for row in rows if json.loads(row['body']).get('type')==origin['type']]
                if len(candidates)==1:aliases[candidates[0]['id']]=origin['id']
        if not origin:raise KnowledgeError('object_missing','Object no longer exists',404)
        op=query['operation']
        if op in {'children','own-code'}:
            field='parent' if op=='children' else 'component'
            keys={origin['id']} if op=='children' else {origin['id'],origin.get('component',origin['id'])}
            rows=c.execute("SELECT body FROM knowledge_items WHERE project=? AND kind='entity' AND json_extract(body,'$."+field+"') IN ("+','.join('?' for _ in keys)+')',(store.project,*keys))
            for row in rows:
                node=json.loads(row[0]);items[node['id']]=node
            relations('from',[i for i,n in items.items() if n['kind']=='entity'])
        else:
            reverse=op in {'incoming','implementations'};field='to' if reverse else 'from';target='from' if reverse else 'to'
            frontier={origin['id']}
            if origin.get('type')=='file' and op in {'incoming','outgoing'}:
                rows=c.execute("SELECT body FROM knowledge_items WHERE project=? AND kind='entity' AND json_extract(body,'$.source.path')=?",(store.project,origin.get('source',{}).get('path')))
                for row in rows:
                    node=json.loads(row[0]);items[node['id']]=node;frontier.add(node['id'])
            visited=set();depth=0;maximum=10000 if query['depth']=='all' else query['depth']
            transparent_files=query['representation']=='symbols'
            while frontier and depth<maximum:
                if stopped() or time.monotonic()>deadline:truncated=True;break
                layer=frontier;next_frontier=set()
                while layer:
                    if stopped() or time.monotonic()>deadline:truncated=True;break
                    edges=[e for e in relations(field,sorted(layer)) if allows_edge(e,op,items,transparent_files)]
                    visited.update(layer);reached={e[target] for e in edges}-visited;read_ids(reached)
                    reached={i for i in reached if i in items and not items[i].get('removed')}
                    layer={i for i in reached if transparent_files and items[i].get('type')=='file'}
                    next_frontier.update(reached-layer)
                if truncated:break
                frontier=next_frontier-visited;depth+=1
                if op=='path' and query['target'] in items:break
        # Resource representation needs only owners/definitions of reached nodes.
        entity_ids=[i for i,n in items.items() if n['kind']=='entity']
        extra=relations('to',entity_ids) if query['representation']!='symbols' else []
        if origin.get('type')=='file':extra+=relations('from',[origin['id']])
        contains=[e for e in extra if e['type']=='contains']
        read_ids([i for e in contains for i in (e['from'],e['to'])])
    return list(items.values()),truncated


def start(store, query, actor='local-user', task=None, stage=None):
    setup(store)
    query = resolve_source(store,validate_query(store, query))
    # Fingerprinting is done by the worker: HTTP acknowledgment remains fast.
    identifier = uuid.uuid4().hex
    origin=read_object(store,query['id'],check_fresh=False)
    job = dict(id=identifier, kind='research', state='queued', query=query, object={'id':origin['id'],'title':origin['title']}, actor=actor, task=task, stage=stage, createdAt=now(), progress={'visited':0})
    with store.registry.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        count=c.execute("SELECT count(*) FROM knowledge_jobs WHERE project=? AND state IN ('queued','running') AND json_extract(body,'$.kind')='research'",(store.project,)).fetchone()[0]
        if count>=8:
            raise KnowledgeError('research_busy','Eight research jobs are already active; cancel or wait',429)
        c.execute('INSERT INTO knowledge_jobs VALUES(?,?,?,?)', (store.project, identifier, 'queued', canonical(job)))
        c.commit()
    (_BROWSE_POOL if query.get('catalogOnly') or query.get('provider','catalog')=='catalog' and query['operation'] in {'children','own-code','definitions'} else _POOL).submit(run, store, job)
    return job


def cancel(store, identifier):
    with store.registry.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        job = store.job(identifier)
        if job.get('kind') != 'research':
            raise KnowledgeError('invalid_job', 'Only research jobs can be cancelled here', 400)
        if job['state'] in {'queued','running'}:
            job.update(state='cancelled', finishedAt=now())
            c.execute('UPDATE knowledge_jobs SET state=?,body=? WHERE project=? AND id=?', (job['state'],canonical(job),store.project,identifier))
        c.commit()
    return job


def run(store, job):
    def save():
        with store.registry.connect() as c:
            c.execute("UPDATE knowledge_jobs SET state=?,body=? WHERE project=? AND id=? AND state!='cancelled'", (job['state'],canonical(job),store.project,job['id']))
    def stopped():
        return store.job(job['id'])['state'] == 'cancelled'
    try:
        job.update(state='running', startedAt=now()); save()
        query = job['query']
        catalog_only=query.get('provider','catalog')=='catalog' and (query.get('catalogOnly') or query['operation'] in {'children','own-code','definitions'})
        get_basis=catalog_fingerprint if catalog_only else fingerprint
        basis, revision = get_basis(store)
        read_object(store,query['id'],basis=basis,check_fresh=query['operation']!='symbols' and not query.get('automatic'))
        if query['operation']=='path':read_object(store,query['target'],basis=basis)
        cache_query={k:v for k,v in job['query'].items() if k!='intent'}
        cache_key = hashlib.sha256(canonical([_CACHE_VERSION, basis, cache_query]).encode()).hexdigest()
        with store.registry.connect() as c:
            hit = c.execute("SELECT id,body FROM knowledge_research WHERE project=? AND cache_key=? AND (json_extract(body,'$.status') IN ('ready','ok','empty','not-found') OR (json_extract(body,'$.status')='partial' AND json_extract(body,'$.catalogComplete')=1)) ORDER BY rowid DESC LIMIT 1", (store.project,cache_key)).fetchone()
        if hit and query.get('provider','catalog')!='catalog':
            cached=json.loads(hit['body'])
            # Source hashes do not establish language-server index readiness.
            # A negative answer must be retried, rather than staying empty until
            # a different depth bypasses its cache entry after indexing finishes.
            if cached['status']=='empty' or not any(n['id']!=query['id'] and n.get('type')!='file' for n in cached['nodes']):
                hit=None
        if hit and not stopped():
            cached=json.loads(hit['body'])
            limitation=next((d.get('message') for d in cached.get('diagnostics',[]) if isinstance(d,dict) and d.get('code')=='semantic-incomplete'),None)
            job.update(state='done', cached=True, result=hit[0], status=cached['status'], counts={'nodes':len(cached['nodes']),'relations':len(cached['relations'])}, finishedAt=now(),limitation=limitation); save(); return
        if query.get('provider', 'catalog') != 'catalog' or query['operation'] in {'symbols','definition','references','incoming-calls','outgoing-calls'}:
            result = semantic(store, query, stopped, job['progress'],basis=basis)
        else:
            truncated=False
            if catalog_only:items,truncated=catalog_items(store,query,stopped)
            else:
                with store.registry.connect() as c:
                    items = [json.loads(row[0]) for row in c.execute('SELECT body FROM knowledge_items WHERE project=?', (store.project,))]
                    fragments=[json.loads(row[0]) for row in c.execute("SELECT body FROM knowledge_research WHERE project=? AND json_extract(body,'$.fingerprint')=?",(store.project,basis))]
                for fragment in fragments: items.extend(fragment['nodes']+fragment['relations'])
                items=list({item['id']:item for item in items}.values())
            result = explore(items, query, stopped, job['progress'])
            if truncated:result['status']='partial'
            origin=read_object(store,query['id'],check_fresh=False)
            if query.get('automatic') and origin.get('source') and query['operation'] in {'incoming','outgoing','base-types','implementations'}:
                result['catalogComplete']=not truncated and result['status']!='partial'
                result['diagnostics'].append({'code':'semantic-incomplete','message':'Доступны только сохранённые статические факты; пустой результат не доказывает отсутствие семантических связей.'})
                result['status']='partial'
        if stopped(): return
        current, _ = get_basis(store)
        result.update(id=job['id'], query=query, revision=revision, fingerprint=basis, fingerprintScope='catalog' if catalog_only else 'sources', createdAt=now(), stale=current!=basis)
        if current != basis:
            result['status'] = 'stale'
        with store.registry.connect() as c:
            c.execute('INSERT INTO knowledge_research VALUES(?,?,?,?)', (store.project,job['id'],cache_key if current==basis else '',canonical(result)))
            c.executemany('INSERT INTO knowledge_research_objects VALUES(?,?,?,?,?)',[(store.project,n['id'],job['id'],basis,canonical(n)) for n in result['nodes']+result['relations'] if n['id'].startswith('research:')])
        limitation=next((d.get('message') for d in result.get('diagnostics',[]) if isinstance(d,dict) and d.get('code')=='semantic-incomplete'),None)
        job.update(state='done', result=job['id'], status=result['status'], counts={'nodes':len(result['nodes']),'relations':len(result['relations'])}, finishedAt=now(),limitation=limitation); save()
    except Exception as error:
        job.update(state='failed', error=str(error), finishedAt=now()); save()


def expanded_resource_paths(items):
    """Derived display links retain the original facts for subsequent queries."""
    expanded={}
    for item in items:
        if item.get('type')=='via-files' and item.get('pathEdges'):
            for original in item.get('via',[])+item['pathEdges']:
                expanded.setdefault(original['id'],original)
        else:expanded[item['id']]=item
    return list(expanded.values())


def allows_edge(edge, operation, nodes, transparent_files):
    kind=edge['type']
    if operation=='definitions':return kind=='contains'
    if operation in {'base-types','implementations'}:return kind in _INHERITANCE
    if operation in {'incoming','outgoing','path'} and kind=='contains':
        # A reached file's definitions resolve that resource to visible symbols.
        # Never follow symbol ownership backwards as an incoming dependency.
        return transparent_files and operation in {'outgoing','path'} and nodes.get(edge['from'],{}).get('type')=='file'
    return True


def project_resource_paths(nodes, selected, visible, stopped=lambda:False):
    """Hide files while distinguishing a recorded chain from a direct relation."""
    adjacency={}
    for edge in selected.values():adjacency.setdefault(edge['from'],[]).append(edge)
    projected={};deadline=time.monotonic()+30;interrupted=False
    for source in sorted(visible):
        queue=deque([(source,())]);visited_files=set();reached=set()
        while queue:
            if stopped() or time.monotonic()>deadline:interrupted=True;break
            current,path=queue.popleft()
            for edge in sorted(adjacency.get(current,[]),key=lambda e:e['id']):
                target=edge['to'];chain=path+(edge,)
                if target in visible:
                    if not path:projected[edge['id']]=edge
                    elif target!=source and target not in reached:
                        via=[nodes[e['to']] for e in chain[:-1]]
                        identifier='research:path:'+hashlib.sha256(canonical([e['id'] for e in chain]).encode()).hexdigest()[:24]
                        projected_edge=dict(id=identifier,kind='relation',type='via-files',**{'from':source,'to':target},provenance='inferred',
                            description=('Цепочка сохранённых связей через скрытые файлы: '+' → '.join(nodes[i].get('title',i) for i in [source,*[n['id'] for n in via],target]))[:12000],
                            via=via,pathEdges=list(chain),evidence=[evidence for e in chain for evidence in e.get('evidence',[])])
                        if len(canonical(projected_edge).encode())>180000:
                            interrupted=True;continue
                        projected[identifier]=projected_edge
                        reached.add(target)
                elif nodes.get(target,{}).get('type')=='file' and target not in visited_files:
                    visited_files.add(target);queue.append((target,chain))
        if interrupted:break
    return projected,interrupted


def explore(items, query, stopped=lambda:False, progress=None):
    items=expanded_resource_paths(items)
    nodes = {n['id']:n for n in items if n['kind']=='entity' and not n.get('removed')}
    edges = [e for e in items if e['kind']=='relation' and not e.get('removed')]
    origin = nodes.get(query['id'])
    if origin is None:
        raise KnowledgeError('object_missing', 'Object no longer exists', 404)
    op, representation = query['operation'], query['representation']
    visible = {origin['id']}
    selected = {}
    if op in {'children','own-code'}:
        if origin.get('type')=='directory':
            prefix=origin['source']['path'].rstrip('/')+'/'
            visible={n['id'] for n in nodes.values() if n.get('source',{}).get('path','').startswith(prefix)}
        for node in nodes.values():
            if op=='children' and node.get('parent')==origin['id'] or op=='own-code' and node.get('component') in {origin['id'],origin.get('component',origin['id'])} and node['type']!='component':
                visible.add(node['id'])
        selected = {e['id']:e for e in edges if e['from'] in visible and e['to'] in visible and e['type']!='contains'}
    else:
        adjacency = {}
        transparent_files=representation=='symbols'
        for edge in edges:
            if not allows_edge(edge,op,nodes,transparent_files):continue
            reverse = op in {'incoming','implementations'}
            a,b = (edge['to'],edge['from']) if reverse else (edge['from'],edge['to'])
            adjacency.setdefault(a, []).append((b,edge))
        seeds={origin['id']}
        if origin.get('type')=='file' and op in {'incoming','outgoing'}:
            seeds.update(n['id'] for n in nodes.values() if n.get('source',{}).get('path')==origin.get('source',{}).get('path'))
            seeds.update(e['to'] for e in edges if e['from']==origin['id'] and e['type']=='contains')
        visible.update(seeds)
        queue = deque((identifier,0) for identifier in sorted(seeds))
        visited = set(seeds)
        distances={identifier:0 for identifier in seeds}
        previous = {}
        max_depth = len(nodes) if query['depth']=='all' else query['depth']
        deadline = time.monotonic()+30
        interrupted = False
        while queue:
            if stopped() or time.monotonic()>deadline:
                interrupted = True; break
            source,depth = queue.popleft()
            if progress is not None: progress['visited']=len(visited)
            if depth>=max_depth: continue
            for target,edge in sorted(adjacency.get(source,[]), key=lambda pair:pair[1]['id']):
                if target not in nodes: continue
                visible.add(target); selected[edge['id']]=edge
                next_depth=depth+(0 if transparent_files and nodes[target]['type']=='file' else 1)
                if target not in distances or next_depth<distances[target]:
                    distances[target]=next_depth;visited.add(target);previous[target]=(source,edge)
                    if next_depth==depth:queue.appendleft((target,next_depth))
                    else:queue.append((target,next_depth))
            if op=='path' and query['target'] in visited: break
        if op=='path':
            visible={origin['id']};selected={}
            current=query['target']
            while current in previous:
                parent,edge=previous[current];selected[edge['id']]=edge;visible.update([current,parent]);current=parent
    if representation=='symbols':
        # A file is a starting resource. Show its contained definitions and
        # keep evidence in the inspector, not duplicate file/class nodes.
        if origin['type']=='file':
            visible.update(e['to'] for e in edges if e['from']==origin['id'] and e['type']=='contains')
        visible={i for i in visible if nodes[i]['type']!='file'}
        selected,projection_interrupted=project_resource_paths(nodes,selected,visible,stopped)
        interrupted=locals().get('interrupted',False) or projection_interrupted
    elif representation=='files':
        owner={e['to']:e['from'] for e in edges if e['type']=='contains' and nodes.get(e['from'],{}).get('type')=='file'}
        mapped={i:owner.get(i,i) for i in visible};visible=set(mapped.values())
        selected={e['id']:{**e,'from':mapped.get(e['from'],e['from']),'to':mapped.get(e['to'],e['to'])} for e in selected.values() if mapped.get(e['from'],e['from'])!=mapped.get(e['to'],e['to'])}
    else:
        for edge in edges:
            if edge['type']=='contains' and edge['to'] in visible and nodes.get(edge['from'],{}).get('type')=='file':
                visible.add(edge['from']);selected[edge['id']]=edge
    return dict(nodes=[nodes[i] for i in sorted(visible) if i in nodes], relations=[e for e in selected.values() if e['from'] in visible and e['to'] in visible],
                status='partial' if locals().get('interrupted') else 'not-found' if op=='path' and query['target'] not in visited else 'ready', coverage='stored-static-facts',
                diagnostics=['Статические связи из сохранённого анализа. Это не доказательство полного пути выполнения.'],
                found=query['target'] in visited if op=='path' else None)


def semantic(store, query, stopped=lambda:False, progress=None, *, basis=None):
    from knowledge_lsp import manager
    # File structure is the recovery action for an obsolete symbol position.
    # It reads the current file from the beginning, never uses that old position.
    item = read_object(store, query['id'],basis=basis,check_fresh=query['operation']!='symbols' and not query.get('automatic'))
    config = next((p for p in providers(store) if language(item) in p['languages'] and query.get('provider',p['id'])==p['id']), None)
    if not config:
        raise KnowledgeError('provider_unconfigured', 'Configure a language server in language-servers.json', 400)
    source = item.get('source', {})
    if not source.get('path'):
        raise KnowledgeError('source_missing', 'A registered source location is required', 400)
    root, physical = store.source_location(source['path'])
    root_index = store.roots.index(root)
    config_identity=canonical(config)
    config=dict(config)
    workspace=store.data/'language-servers'/str(root_index)/config['id']
    workspace.mkdir(parents=True,exist_ok=True)
    config['command']=[arg.replace('{workspace}',str(workspace)).replace('{root}',str(root)) for arg in config['command']]
    operation=semantic_operation(query['operation'],item.get('type'))
    source_hashes={}
    def source_hash(path):
        path=Path(path)
        if path not in source_hashes:
            content=source_content_hash(store,path)
            if len(content)!=32:raise OSError('Source is unavailable: '+str(path))
            source_hashes[path]=content.hex()
        return source_hashes[path]
    diagnostics=[]
    deadline=time.monotonic()+60
    current_hash=source_hash(physical)
    position_unverified=False
    if query.get('automatic') and not item.get('analysisSourceHash') and item.get('type')!='file':
        declaration_name=re.split(r'[(:]',item['title'])[0].split('.')[-1].strip()
        source_text=physical.read_text(encoding='utf-8-sig').splitlines()
        source_line=source.get('line',1)
        position_unverified=(not 0<source_line<=len(source_text) or not re.search(r'(?<!\w)'+re.escape(declaration_name)+r'(?!\w)',source_text[source_line-1]))
    if query.get('automatic') and query['operation']!='symbols' and (position_unverified or item.get('analysisSourceHash') and item['analysisSourceHash']!=current_hash):
        refreshed=manager.query(root,config,'symbols',physical.relative_to(root).as_posix(),timeout=max(.1,deadline-time.monotonic()),cancelled=stopped)
        matches=[]
        def find(values):
            for value in values:
                if value.get('name','').split(' : ',1)[0]==item['title'].split(' : ',1)[0] and (item.get('symbolKind') is None or value.get('kind')==item['symbolKind']):matches.append(value)
                find(value.get('children',[]))
        find(refreshed.get('results',[]))
        if len(matches)!=1:
            raise KnowledgeError('symbol_refresh_ambiguous','Исходник изменился: сервер не смог однозначно восстановить выбранный символ.',409)
        point=(matches[0].get('selectionRange') or matches[0].get('range'))['start']
        item={**item,'source':{**source,'line':point['line']+1,'column':point['character']+1},'analysisSourceHash':current_hash}
        diagnostics.append({'code':'symbol-refreshed','message':'Положение символа автоматически обновлено по текущему исходнику.'})
    nodes, edges = {item['id']:{**item,'analysisSourceHash':current_hash}}, {}
    source_symbols={}
    source_lines={}
    max_depth=10000 if query['depth']=='all' else query['depth']
    recursive=query['operation'] in _RECURSIVE_OPERATIONS
    queue=deque([(item,0)])
    visited=set()
    status='empty'
    skipped=False
    def add(value, default_path):
        nonlocal skipped
        if not isinstance(value,dict):return None
        target=value.get('from') or value.get('to') or value.get('item') or value
        if 'location' in target:target={**target,**target['location']}
        uri=target.get('uri') or target.get('targetUri') or (default_path.as_uri() if query['operation'] in {'symbols','definitions'} else None)
        if not uri:return None
        parsed=urlparse(uri)
        if parsed.scheme!='file' or parsed.netloc not in {'','localhost'}:
            skipped=True;return None
        raw=unquote(parsed.path)
        if __import__('os').name=='nt':raw=raw.lstrip('/')
        target_path=Path(raw).resolve()
        if not target_path.is_relative_to(root):
            skipped=True;return None
        # Location-only responses (definition/type hierarchy) must not replace
        # an already resolved declaration with a generic file:line participant.
        if target.get('kind') is None and query['operation'] in {'definition','base-types','implementations'}:
            if target_path not in source_symbols:
                answer=manager.query(root,config,'symbols',target_path.relative_to(root).as_posix(),1,1,timeout=max(.1,deadline-time.monotonic()),cancelled=stopped)
                source_symbols[target_path]=answer.get('results',[])
            location=target.get('targetSelectionRange') or target.get('selectionRange') or target.get('range') or {}
            start=location.get('start',{})
            def declaration(values):
                for value in values:
                    selection=value.get('selectionRange') or value.get('range') or value.get('location',{}).get('range',{})
                    if selection.get('start')==start:return value
                    found=declaration(value.get('children',[]))
                    if found:return found
            resolved=declaration(source_symbols[target_path])
            if resolved:target={**target,**resolved}
        location=target.get('selectionRange') or target.get('targetSelectionRange') or target.get('range') or {}
        start=location.get('start',{})
        line,column=start.get('line',0)+1,start.get('character',0)+1
        # Location identity is stable across symbol and call hierarchy labels.
        identifier='research:symbol:'+hashlib.sha256(canonical([target_path.as_uri(),line,column]).encode()).hexdigest()[:24]
        kind={1:'file',5:'class',11:'interface',10:'enum',6:'method',9:'constructor',12:'function',13:'variable',7:'property',8:'field',14:'constant',2:'module',3:'namespace',4:'package',22:'enum-member',23:'type',26:'type-parameter'}.get(target.get('kind'),'symbol')
        final=False
        if language(item)=='java' and kind=='class':
            if target_path not in source_lines:source_lines[target_path]=target_path.read_text(encoding='utf-8-sig').splitlines()
            lines=source_lines[target_path]
            prefix=lines[line-1][:column-1] if 0<line<=len(lines) else ''
            if re.search(r'\brecord\s*$',prefix):kind='record';final=True
            else:
                modifiers=re.search(r'((?:(?:public|protected|private|static|abstract|final|sealed|non-sealed)\s+)*)class\s*$',prefix)
                final=bool(modifiers and 'final' in modifiers[1].split())
        relative=target_path.relative_to(root).as_posix()
        if root_index:relative=f'@roots/{root_index}/'+relative
        title=target.get('name') or target_path.name+':'+str(line)
        if kind in {'method','function','constructor'}:title=title.split(' : ',1)[0]
        node=dict(id=identifier,kind='entity',type=kind,title=title,source={'path':relative,'line':line,'column':column},analysisSourceHash=source_hash(target_path),provenance='language-server',language=language(item),symbolKind=target.get('kind'))
        if final:node['isFinal']=True
        # Keep the selected symbol's identity when a provider returns it again.
        for existing in nodes.values():
            existing_source=existing.get('source',{})
            same_declaration=existing_source.get('path')==relative and existing_source.get('line')==line and existing.get('title')==node['title'] and existing.get('type') in {'class','record','interface','enum'}
            if existing_source==node['source'] or same_declaration:
                identifier=existing['id']
                node={**existing,**node,'id':identifier}
                if target.get('kind') is None:
                    node['title']=existing['title'];node['type']=existing['type']
                break
        if identifier==item['id'] and item.get('type') in {'class','record','interface','enum'}:node['type']=item['type']
        if recursive:
            # A location-only response still provides a valid starting point
            # for the next hierarchy request. Preserve that action in the UI,
            # just as the multi-depth traversal already does internally.
            node['semanticOperations']=[op for op in _RECURSIVE_OPERATIONS if op in continuation_operations(node) or op==query['operation']]
        nodes[identifier]=node
        return node
    def edge(a,b,kind,evidence):
        if a==b:return
        identifier='research:edge:'+hashlib.sha256(canonical([a,b,kind]).encode()).hexdigest()[:24]
        edges[identifier]=dict(id=identifier,kind='relation',type=kind,**{'from':a,'to':b},provenance='language-server',evidence=[evidence])
    def symbols(values,parent,path):
        for value in values:
            node=add(value,path)
            if node:
                edge(parent,node['id'],'contains',node['source'])
                symbols(value.get('children',[]),node['id'],path)
    while queue:
        if stopped() or time.monotonic()>deadline:
            status='partial';diagnostics.append({'code':'bounded-query','message':'Analysis stopped before every reachable element was explored'});break
        current,depth=queue.popleft()
        if current['id'] in visited or depth>=max_depth:continue
        visited.add(current['id'])
        if progress is not None:progress['visited']=len(visited)
        _,path=store.source_location(current['source']['path'])
        line=query.get('line',current['source'].get('line',1)) if depth==0 else current['source'].get('line',1)
        column=query.get('column',current['source'].get('column',1)) if depth==0 else current['source'].get('column',1)
        if column==1 and current.get('type')!='file':
            lines=path.read_text(encoding='utf-8-sig').splitlines()
            name=re.split(r'[(:]',current['title'])[0].split('.')[-1].strip()
            if 0<line<=len(lines) and name and name in lines[line-1]:column=lines[line-1].index(name)+1
        # Timeout is part of the transport config; keep one session key rather
        # than starting a fresh process for each depth. Total time is checked
        # between bounded requests; cancellation never publishes a late result.
        response=manager.query(root,config,operation,path.relative_to(root).as_posix(),line,column,timeout=max(.1,deadline-time.monotonic()),cancelled=stopped)
        if response.get('capabilities'):_NEGOTIATED[(store.project,config['id'],config_identity)]=response['capabilities']
        diagnostics.extend(response.get('diagnostics',[])[:20])
        state=response.get('status','error')
        if state not in {'ok','empty','partial'}:
            status='partial' if edges else state;break
        if state=='partial':status='partial'
        if state=='ok' and status!='partial':status='ok'
        if query['operation'] in {'symbols','definitions'}:
            values=response.get('results',[])
            if query['operation']=='definitions' and current.get('type')!='file':
                matches=[]
                def locate(values):
                    for value in values:
                        location=value.get('selectionRange') or value.get('range') or value.get('location',{}).get('range',{})
                        if location.get('start',{}).get('line')==line-1 and value.get('name','').split('(')[0].strip()==current['title'].split('(')[0].strip():matches.append(value)
                        locate(value.get('children',[]))
                locate(values)
                if matches:values=matches[0].get('children',[])
                else:
                    values=[];status='partial';diagnostics.append({'code':'symbol-scope-unresolved','message':'The selected declaration was not found in the source structure; refresh its location'})
            symbols(values,current['id'],path)
            continue
        for value in response.get('results',[]):
            node=add(value,path)
            if not node:continue
            reverse=operation in {'incoming-calls','references','implementations'}
            a,b=(node['id'],current['id']) if reverse else (current['id'],node['id'])
            kind='calls' if 'calls' in operation else 'extends' if operation in {'base-types','implementations'} else 'definition' if operation=='definition' else 'references'
            evidence=node['source']
            ranges=value.get('fromRanges') if isinstance(value,dict) else None
            if ranges:evidence={**(node['source'] if reverse else current['source']),'line':ranges[0]['start']['line']+1,'column':ranges[0]['start']['character']+1}
            edge(a,b,kind,evidence)
            if recursive:
                if query['representation']=='symbols' and node['type']=='file':queue.appendleft((node,depth))
                else:queue.append((node,depth+1))
    if any(d.get('code')=='call-selection-unresolved' for d in diagnostics if isinstance(d,dict)) and status=='ok':status='partial'
    if skipped:
        status='partial' if status in {'ok','empty'} else status
        diagnostics.append({'code':'external-targets','message':'Some targets are external libraries or outside the registered root; they are not included in this canvas'})
    # Source-resource visibility is explicit. A default symbol view removes
    # file duplication while retaining each symbol's source evidence.
    representation=query['representation']
    if representation=='symbols':
        edges,projection_interrupted=project_resource_paths(nodes,edges,{i for i,n in nodes.items() if n.get('type')!='file'},stopped)
        if projection_interrupted:
            status='partial';diagnostics.append({'code':'bounded-projection','message':'Цепочки через скрытые файлы показаны не полностью; включите файлы или повторите исследование.'})
        nodes={i:n for i,n in nodes.items() if n.get('type')!='file'}
    elif representation=='symbols-in-files':
        for node in list(nodes.values()):
            if node.get('type')=='file':continue
            _,path=store.source_location(node['source']['path'])
            fid='research:file:'+hashlib.sha256(path.as_uri().encode()).hexdigest()[:24]
            nodes.setdefault(fid,dict(id=fid,kind='entity',type='file',title=path.name,source={'path':node['source']['path'],'line':1},provenance='language-server',language=language(item)))
            edge(fid,node['id'],'contains',node['source'])
    elif representation=='files':
        mapping={}
        files={}
        for node in nodes.values():
            _,path=store.source_location(node['source']['path'])
            fid='research:file:'+hashlib.sha256(path.as_uri().encode()).hexdigest()[:24]
            mapping[node['id']]=fid
            files[fid]=dict(id=fid,kind='entity',type='file',title=path.name,source={'path':node['source']['path'],'line':1},provenance='language-server',language=language(item))
        edges={i:{**e,'from':mapping[e['from']],'to':mapping[e['to']]} for i,e in edges.items() if mapping[e['from']]!=mapping[e['to']]}
        nodes=files
    return dict(nodes=list(nodes.values()),relations=[e for e in edges.values() if e['from'] in nodes and e['to'] in nodes],status=status,coverage='language-server-static',diagnostics=diagnostics[-25:],provider=config['id'],visited=len(visited))


def result(store, identifier, offset=0, limit=100):
    setup(store)
    key=(str(store.registry.home),store.project,identifier)
    with _LOCK:
        cached=_RESULTS.get(key)
        if cached:_RESULTS.move_to_end(key)
    if cached:metadata,items=cached
    else:
        with store.registry.connect() as c:
            row=c.execute('SELECT body FROM knowledge_research WHERE project=? AND id=?',(store.project,identifier)).fetchone()
        if not row: raise KnowledgeError('result_missing','Research result is unavailable',404)
        metadata=json.loads(row[0]);items=metadata.pop('nodes')+metadata.pop('relations');metadata.pop('raw',None)
        with _LOCK:
            _RESULTS[key]=(metadata,items)
            while len(_RESULTS)>8:_RESULTS.popitem(last=False)
    body=dict(metadata)
    if offset==0:
        current,_=(catalog_fingerprint if body.get('fingerprintScope')=='catalog' else fingerprint)(store)
        body['stale']=body['fingerprint']!=current
        if body['stale']: body['status']='stale'
    offset=max(0,int(offset));limit=max(1,min(200,int(limit)))
    page=items[offset:offset+limit]
    while len(page)>1 and len(canonical(page).encode())>160000: page.pop()
    return dict(**body,items=page,total=len(items),more=offset+len(page)<len(items),next=offset+len(page))


def history(store, offset=0, limit=50):
    setup(store)
    limit=min(100,max(1,int(limit)));offset=max(0,int(offset))
    with store.registry.connect() as c:
        rows=c.execute("SELECT j.body,n.body AS origin FROM knowledge_jobs j LEFT JOIN knowledge_items n ON n.project=j.project AND n.id=json_extract(j.body,'$.query.id') WHERE j.project=? AND json_extract(j.body,'$.kind')='research' AND coalesce(json_extract(j.body,'$.query.intent'),'research')!='browse' ORDER BY j.rowid DESC LIMIT ? OFFSET ?",(store.project,limit+1,offset)).fetchall()
    items=[]
    for row in rows[:limit]:
        job=json.loads(row[0])
        if not job.get('object') and row['origin']:
            origin=json.loads(row['origin']);job['object']={'id':origin['id'],'title':origin['title']}
        items.append(job)
    return dict(items=items,offset=offset,more=len(rows)>limit,next=offset+len(items))


def save_map(store, expected, key, title, nodeIds, edgeIds, actor='local-user', presentationGroups=None, resultId=None):
    """Persist only server-owned facts; large maps use one atomic revision."""
    if not isinstance(title,str) or not title.strip() or len(title)>300:
        raise KnowledgeError('invalid_map','A bounded map title is required',400)
    for values in [nodeIds,edgeIds]:
        if not isinstance(values,list) or len(values)>25000 or not all(isinstance(i,str) and re.fullmatch(r'[\w:./-]{1,180}',i) for i in values):
            raise KnowledgeError('invalid_map','Map IDs must be bounded arrays',400)
    setup(store)
    basis,revision=fingerprint(store)
    catalog_basis='catalog:'+str(revision)
    with store.registry.connect() as c:
        # Retry must replay the committed save even if its revision changed.
        prior=c.execute('SELECT operations FROM knowledge_changes WHERE project=? AND key=?',(store.project,key)).fetchone()
        canonical_items={};available={};requested=list(dict.fromkeys(nodeIds+edgeIds))
        for offset in range(0,len(requested),400):
            identifiers=requested[offset:offset+400];marks=','.join('?' for _ in identifiers)
            for row in c.execute('SELECT id,body FROM knowledge_items WHERE project=? AND id IN ('+marks+')',(store.project,*identifiers)):
                canonical_items[row['id']]=json.loads(row['body'])
            missing=[i for i in identifiers if i not in canonical_items]
            if not missing:continue
            marks=','.join('?' for _ in missing)
            for row in c.execute('SELECT id,body FROM knowledge_research_objects WHERE project=? AND basis IN (?,?) AND id IN ('+marks+') ORDER BY rowid',(store.project,basis,catalog_basis,*missing)):
                available[row['id']]=json.loads(row['body'])
            legacy=[i for i in missing if i not in available]
            if legacy:
                marks=','.join('?' for _ in legacy)
                # Compatibility only: old fragments had no relation index.
                for field in ('nodes','relations'):
                    for row in c.execute("SELECT n.value FROM knowledge_research r,json_each(r.body,'$."+field+"') n WHERE r.project=? AND json_extract(r.body,'$.fingerprint') IN (?,?) AND json_extract(r.body,'$.status') IN ('ready','ok','empty','partial') AND json_extract(n.value,'$.id') IN ("+marks+") ORDER BY r.rowid",(store.project,basis,catalog_basis,*legacy)):
                        item=json.loads(row[0]);available[item['id']]=item
    wanted=dict(nodeIds=list(dict.fromkeys(nodeIds)),edgeIds=list(dict.fromkeys(edgeIds)),title=title)
    if presentationGroups is not None:
        store.validate_item(dict(id='research:validation',kind='view',viewType='research',title=title,nodeIds=wanted['nodeIds'],presentationGroups=presentationGroups))
        wanted['presentationGroups']=presentationGroups
    if resultId is not None:
        if not isinstance(resultId,str) or not re.fullmatch(r'[\w:./-]{1,180}',resultId):
            raise KnowledgeError('invalid_map','Expected a bounded research result ID',400)
        wanted['resultId']=resultId
    if prior:
        view=json.loads(prior[0])[-1]['item']
        if view.get('saveRequest')!=hashlib.sha256(canonical(wanted).encode()).hexdigest():
            raise KnowledgeError('idempotency_conflict','Map key was used with different content',409)
        return dict(id=view['id'],replayed=True)
    fragment_basis=None
    if resultId is not None:
        page=result(store,resultId,offset=0,limit=200)
        if page.get('stale') or page.get('status') not in ('ready','ok','empty','partial'):
            raise KnowledgeError('stale_map','Selected result is no longer current',409)
        fragment_basis=page['fingerprint'];fragment_ids={n['id'] for n in page['items']};pages=1
        while page.get('more') and pages<300:
            page=result(store,resultId,offset=page['next'],limit=200);fragment_ids.update(n['id'] for n in page['items']);pages+=1
        if page.get('more') or not set(wanted['nodeIds']+wanted['edgeIds']).issubset(fragment_ids):
            raise KnowledgeError('invalid_map','Snapshot must belong to the selected result',400)
    available.update(canonical_items)
    operations=[]
    for identifier,kind in [(i,'entity') for i in wanted['nodeIds']]+[(i,'relation') for i in wanted['edgeIds']]:
        item=available.get(identifier)
        if not item or item['kind']!=kind:
            raise KnowledgeError('stale_map','Some map facts are no longer current; research them again',409,id=identifier)
        if identifier not in canonical_items:
            saved=dict(item)
            if saved.get('provenance')=='language-server':
                saved['provenance']='static';saved['analysisProvider']='language-server'
                if saved.get('source'):
                    saved['analysisSourceHash']=source_content_hash(store,store.source_path(saved['source']['path'])).hex()
            operations.append(dict(op='put',item=saved))
    view=dict(id='research:map:'+uuid.uuid4().hex,kind='view',title=title,viewType='research',nodeIds=wanted['nodeIds'],orderedEdges=wanted['edgeIds'],description='Saved research canvas',provenance='authored',researchBasis={'revision':revision,'fingerprint':basis},saveRequest=hashlib.sha256(canonical(wanted).encode()).hexdigest())
    if presentationGroups is not None: view['presentationGroups']=presentationGroups
    if resultId is not None: view['researchBasis'].update(resultId=resultId,resultFingerprint=fragment_basis)
    operations.append(dict(op='put',item=view))
    if fingerprint(store)[0]!=basis:
        raise KnowledgeError('stale_map','Sources changed while preparing the map; repeat the save',409)
    receipt=store.changeset(expected,key,operations,'Save research map',actor=actor,code_revision={'fingerprint':basis,'basis':'research-source-content'},_research=True)
    return dict(**receipt,id=view['id'])


def provider_info(store):
    return dict(providers=[{'id':p['id'],'languages':p['languages']} for p in providers(store)],configuration=str(store.registry.home/'language-servers.json'),installation='external-configured')
