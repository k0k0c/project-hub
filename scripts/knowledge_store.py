"""Project-scoped knowledge in the existing registry database, with immutable history."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import difflib
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

KINDS = {'document', 'entity', 'relation', 'view'}
DEFAULT_POLICY = dict(audiences=['user', 'developer'], sections=[], components=[], entrypoints=[],
                      scanRoots=[], updateMode='manual', reviewMode='significant', maxFiles=10000,
                      excludeDirectories=[], descriptionLimit=800, maxFileBytes=2000000, intervalSeconds=60)
_SETUP_LOCK = threading.Lock()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class KnowledgeError(ValueError):
    def __init__(self, code, message, status=409, **details):
        super().__init__(message)
        self.status = status
        self.body = dict(error=code, message=message, **details)


class KnowledgeStore:
    def __init__(self, registry, project):
        self.registry, self.project = registry, project
        from backup_session import active
        if active(registry) is not None:
            # All schemas and project metadata were prepared before the lease.
            # A cold HTTP worker must not attempt CREATE/INSERT during copying.
            with registry.connect() as c:
                row = c.execute('SELECT roots FROM spaces WHERE id=?', (project,)).fetchone()
                if row is None:
                    raise KnowledgeError('unknown_project', 'Select a registered project', 404)
                self.roots = [Path(p).resolve() for p in json.loads(row['roots'])]
            self.data = registry.home / 'projects' / project / 'knowledge'
            return
        with _SETUP_LOCK:
            if not getattr(registry, '_knowledge_schema_ready', False):
                with registry.connect() as c:
                    c.executescript('''
                        CREATE TABLE IF NOT EXISTS knowledge_meta(project TEXT PRIMARY KEY,revision INTEGER NOT NULL,policy TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS knowledge_items(project TEXT NOT NULL,id TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(project,id));
                        CREATE INDEX IF NOT EXISTS knowledge_kind ON knowledge_items(project,kind,id);
                        CREATE INDEX IF NOT EXISTS knowledge_type ON knowledge_items(project,kind,json_extract(body,'$.type'));
                        CREATE INDEX IF NOT EXISTS knowledge_component ON knowledge_items(project,kind,json_extract(body,'$.component'));
                        CREATE INDEX IF NOT EXISTS knowledge_parent ON knowledge_items(project,kind,json_extract(body,'$.parent'));
                        CREATE INDEX IF NOT EXISTS knowledge_from ON knowledge_items(project,json_extract(body,'$.from'),kind);
                        CREATE INDEX IF NOT EXISTS knowledge_to ON knowledge_items(project,json_extract(body,'$.to'),kind);
                        CREATE TABLE IF NOT EXISTS knowledge_changes(project TEXT NOT NULL,revision INTEGER NOT NULL,key TEXT NOT NULL,request_hash TEXT NOT NULL,at TEXT NOT NULL,actor TEXT NOT NULL,task TEXT,stage TEXT,reason TEXT NOT NULL,operations TEXT NOT NULL,PRIMARY KEY(project,revision),UNIQUE(project,key));
                        CREATE TABLE IF NOT EXISTS knowledge_jobs(project TEXT NOT NULL,id TEXT NOT NULL,state TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(project,id));
                        CREATE TABLE IF NOT EXISTS knowledge_imports(project TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(project,id));
                        CREATE TABLE IF NOT EXISTS knowledge_outbox(project TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,error TEXT,PRIMARY KEY(project,revision));
                        CREATE TABLE IF NOT EXISTS knowledge_reviews(project TEXT NOT NULL,task TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(project,task));
                    ''')
                    if 'code_revision' not in {r['name'] for r in c.execute('PRAGMA table_info(knowledge_changes)')}:
                        c.execute("ALTER TABLE knowledge_changes ADD COLUMN code_revision TEXT NOT NULL DEFAULT '{}'")
                    for row in c.execute("SELECT project,id,body FROM knowledge_jobs WHERE state IN ('queued','running')").fetchall():
                        interrupted=json.loads(row['body']); interrupted.update(state='interrupted',error='Server restarted before job acknowledgement',finishedAt=now())
                        c.execute('UPDATE knowledge_jobs SET state=?,body=? WHERE project=? AND id=?',('interrupted',canonical(interrupted),row['project'],row['id']))
                registry._knowledge_schema_ready = True
        with registry.connect() as c:
            row = c.execute('SELECT roots FROM spaces WHERE id=?', (project,)).fetchone()
            if row is None:
                raise KnowledgeError('unknown_project', 'Select a registered project', 404)
            self.roots = [Path(p).resolve() for p in json.loads(row['roots'])]
            c.execute('INSERT OR IGNORE INTO knowledge_meta VALUES(?,0,?)', (project, canonical(DEFAULT_POLICY)))
        self.data = registry.home / 'projects' / project / 'knowledge'

    def context(self):
        with self.registry.connect() as c:
            row = c.execute('SELECT * FROM knowledge_meta WHERE project=?', (self.project,)).fetchone()
            counts = {r['kind']: r['count'] for r in c.execute('SELECT kind,COUNT(*) AS count FROM knowledge_items WHERE project=? GROUP BY kind', (self.project,))}
            jobs = [json.loads(r['body']) for r in c.execute('SELECT body FROM knowledge_jobs WHERE project=? ORDER BY rowid DESC LIMIT 3', (self.project,))]
            pending=c.execute('SELECT COUNT(*) FROM knowledge_outbox WHERE project=?',(self.project,)).fetchone()[0]
            reviews=[json.loads(r[0]) for r in c.execute('SELECT body FROM knowledge_reviews WHERE project=? ORDER BY rowid DESC LIMIT 5',(self.project,))]
            overview_row = c.execute('SELECT body FROM knowledge_items WHERE project=? AND id=?',
                                     (self.project, 'project:' + self.project)).fetchone()
        for job in jobs:
            diagnostics=job.get('diagnostics',[])
            job['diagnostics']=diagnostics[:20]
            if len(diagnostics)>20: job['diagnosticsMore']=len(diagnostics)-20
        for review in reviews:
            for field in ('affectedEntities','affectedDocuments'):
                values=review.get(field,[]); review[field+'Count']=len(values); review[field]=values[:20]
            review['reason']=str(review.get('reason',''))[:1200]
        access = self.workspace_access()
        overview = json.loads(overview_row['body']) if overview_row else None
        overview = (dict(id=overview['id'], title=overview['title'], description=overview.get('description', ''),
                        revision=row['revision'])
                    if overview and overview.get('kind') == 'entity' and overview.get('type') == 'project' else None)
        return dict(project=self.project, revision=row['revision'], policy=json.loads(row['policy']), counts=counts, jobs=jobs,
                    **({'projectOverview': overview} if overview else {}),
                    rootRefs=[dict(id=str(i),prefix='' if i==0 else f'@roots/{i}/',available=str(i) in access['available']) for i in range(len(self.roots))],
                    workspaceRevision=access['signature'],
                    publicationPending=pending,reviews=reviews,
                    capabilities=dict(documents=True, authoredModel=True, scan=bool(access['available']), methods=False,
                        workspaceConfigured=bool(self.roots),
                        documentFormats=['markdown','html'], htmlBundles=True,
                        languages={'python': 'types', 'java': 'types-with-local-jdk', 'other': 'file-inventory'},
                        research=True, researchModel='on-demand-fragments',
                        operations=['search','read','history','changeset','scan','job','import-preview','import-read','import-apply','impact','restore','export','research-capabilities','research-object','research','research-result','research-cancel','research-history','research-save','research-providers']))

    def search(self, query='', kind=None, offset=0, limit=100, type=None, component=None, entrypoint=None, endpoint=None):
        if kind is not None and kind not in KINDS:
            raise KnowledgeError('invalid_kind', 'Unknown knowledge kind', 400)
        offset, limit = max(0, int(offset)), max(1, min(200, int(limit)))
        where, args = 'project=?', [self.project]
        if kind:
            where += ' AND kind=?'; args.append(kind)
        if query:
            where += " AND body LIKE ? ESCAPE '\\'"
            args.append('%' + str(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')[:200] + '%')
        for field,value in [('type',type),('component',component)]:
            if value is not None:
                where+=' AND json_extract(body,\'$.'+field+'\')=?'; args.append(value)
        if entrypoint is not None:
            where+=' AND json_extract(body,\'$.entrypoint\')=?'; args.append(1 if entrypoint in (True,'true','1') else 0)
        if endpoint is not None:
            # Resolve candidates by two indexed endpoint lookups before kind/
            # type filters. SQLite may otherwise choose the broad type index
            # for an OR predicate and parse every relationship's JSON twice.
            where+=" AND id IN (SELECT id FROM knowledge_items WHERE project=? AND json_extract(body,'$.from')=? UNION SELECT id FROM knowledge_items WHERE project=? AND json_extract(body,'$.to')=?)"
            args.extend([self.project,endpoint,self.project,endpoint])
        with self.registry.connect() as c:
            c.execute('BEGIN')
            total = c.execute('SELECT COUNT(*) FROM knowledge_items WHERE '+where, args).fetchone()[0]
            rows = c.execute("SELECT body FROM knowledge_items WHERE "+where+" ORDER BY kind,CASE WHEN json_extract(body,'$.type')='component' THEN 0 WHEN json_extract(body,'$.entrypoint')=1 THEN 1 WHEN json_extract(body,'$.type') IN ('class','interface','record','enum') THEN 2 WHEN json_extract(body,'$.type')='file' THEN 4 ELSE 3 END,id LIMIT ? OFFSET ?", (*args,limit+1,offset)).fetchall()
            revision = c.execute('SELECT revision FROM knowledge_meta WHERE project=?', (self.project,)).fetchone()[0]
            c.commit()
        items = [json.loads(r[0]) for r in rows[:limit]]
        # Listing does not transmit every article's complete text.
        for item in items:
            if item['kind'] == 'document':
                item['excerpt'] = (item.get('description','') if item.get('format')=='html' else item.get('markdown',''))[:300]
                item.pop('markdown', None)
        # Bound one page by bytes as well as count for local HTTP/MCP transports.
        while len(items)>1 and len(canonical(items).encode('utf-8'))>180000: items.pop()
        more=len(rows)>len(items)
        return dict(revision=revision, items=items, total=total, more=more, next=offset+len(items) if more else None)

    def source_tree(self, query='', component=None, offset=0, limit=5000, mode='sources'):
        """Compact source inventory; one indexed read, no repeated total/sort."""
        if mode not in ('sources','navigation'):raise KnowledgeError('invalid_arguments','Unknown inventory mode',400)
        offset, limit = max(0, int(offset)), max(1, min(5000, int(limit)))
        where, args = "project=? AND kind='entity' AND json_extract(body,'$.source.path') IS NOT NULL", [self.project]
        if mode=='navigation':where="project=? AND (kind='view' OR kind='entity' AND (json_extract(body,'$.type')='component' OR json_extract(body,'$.entrypoint')=1))"
        if query:
            where += " AND body LIKE ? ESCAPE '\\'"
            args.append('%' + str(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')[:200] + '%')
        if component is not None:
            where += " AND json_extract(body,'$.component')=?"; args.append(component)
        with self.registry.connect() as c:
            c.execute('BEGIN')
            rows = c.execute("SELECT json_object('id',id,'kind',kind,'title',json_extract(body,'$.title'),'type',json_extract(body,'$.type'),'component',json_extract(body,'$.component'),'parent',json_extract(body,'$.parent'),'entrypoint',json_extract(body,'$.entrypoint'),'viewType',json_extract(body,'$.viewType'),'source',json_extract(body,'$.source')) FROM knowledge_items WHERE " + where + ' ORDER BY id LIMIT ? OFFSET ?', (*args, limit + 1, offset)).fetchall()
            revision = c.execute('SELECT revision FROM knowledge_meta WHERE project=?', (self.project,)).fetchone()[0]
            c.commit()
        more = len(rows) > limit
        return dict(revision=revision, items=[json.loads(r[0]) for r in rows[:limit]], more=more, next=offset+limit if more else None)

    def read(self, identifier, revision=None):
        with self.registry.connect() as c:
            if revision is None:
                row = c.execute('SELECT body FROM knowledge_items WHERE project=? AND id=?', (self.project,identifier)).fetchone()
                item = json.loads(row[0]) if row else None
            else:
                current=c.execute('SELECT revision FROM knowledge_meta WHERE project=?',(self.project,)).fetchone()[0]
                if not 0<=int(revision)<=current: raise KnowledgeError('revision_missing','Knowledge snapshot does not exist',404)
                item = None
                for row in c.execute('SELECT operations FROM knowledge_changes WHERE project=? AND revision<=? ORDER BY revision', (self.project,int(revision))):
                    for op in json.loads(row[0]):
                        if op.get('id',op.get('item',{}).get('id')) == identifier:
                            item = op.get('item') if op['op']=='put' else None
        if item is None:
            raise KnowledgeError('item_missing', 'Knowledge item not present in this revision', 404)
        return item

    def history(self, identifier=None, offset=0, limit=30):
        offset, limit = max(0,int(offset)), min(100,max(1,int(limit)))
        with self.registry.connect() as c:
            rows=c.execute('SELECT * FROM knowledge_changes WHERE project=? ORDER BY revision DESC LIMIT ? OFFSET ?',
                           (self.project, min(100,max(1,int(limit)))+1,max(0,int(offset)))).fetchall()
        result=[]; consumed=0
        for row in rows[:limit]:
            item=dict(row); ops=json.loads(item.pop('operations'))
            if identifier and not any(o.get('id',o.get('item',{}).get('id'))==identifier for o in ops):
                consumed+=1; continue
            item.pop('request_hash'); item['changed']=[o.get('id',o.get('item',{}).get('id')) for o in ops[:200]]
            item['changedCount']=len(ops); item['changedMore']=len(ops)>200
            item['reason']=item['reason'][:3000]
            item['codeRevision']=json.loads(item.pop('code_revision','{}'))
            if result and len(canonical(result+[item]).encode('utf-8'))>180000: break
            result.append(item)
            consumed+=1
        more=len(rows)>consumed
        return dict(items=result,more=more,next=offset+consumed if more else None)

    @staticmethod
    def validate_item(item):
        if not isinstance(item,dict) or item.get('kind') not in KINDS or not isinstance(item.get('id'),str) or not re.fullmatch(r'[\w:./-]{1,180}',item['id']):
            raise KnowledgeError('invalid_item','Items need a stable id and document/entity/relation/view kind',400)
        if len(canonical(item).encode()) > 180_000:
            raise KnowledgeError('item_too_large','An item may contain at most 180 KB',400)
        for key in ('title','description','markdown','type','audience','section'):
            if key in item and not isinstance(item[key],str): raise KnowledgeError('invalid_item',key+' must be text',400)
        if len(item.get('title',''))>300:
            raise KnowledgeError('invalid_item','Use a title of at most 300 characters',400)
        if item['kind'] in {'document','entity','view'} and not item.get('title','').strip():
            raise KnowledgeError('invalid_item','A title is required',400)
        if item['kind']=='relation' and not all(isinstance(item.get(k),str) and item[k] for k in ('from','to','type')):
            raise KnowledgeError('invalid_item','Relations need from/to/type',400)
        if item['kind']=='entity' and any(k in item for k in ('methods','parameters','variables')):
            raise KnowledgeError('unsupported_detail','The architecture stores type relationships, not methods/variables',400)
        if len(item.get('description','')) > 12000:
            raise KnowledgeError('description_too_long','Put long explanations in linked documents',400)
        if item.get('provenance') not in (None,'authored','static','runtime','inferred'):
            raise KnowledgeError('invalid_provenance','Unknown relation provenance',400)
        if 'entityRefs' in item and (not isinstance(item['entityRefs'],list) or not all(isinstance(x,str) for x in item['entityRefs'])):
            raise KnowledgeError('invalid_links','entityRefs must be an array of IDs',400)
        for field in ('documentRefs','sources','evidence'):
            if field in item and not isinstance(item[field],list):
                raise KnowledgeError('invalid_item',field+' must be an array',400)
        for field in ('sources','evidence'):
            for source in item.get(field,[]):
                if not isinstance(source,dict) or not isinstance(source.get('path'),str) or len(source['path'])>1000:
                    raise KnowledgeError('invalid_source','Source/evidence needs a bounded path',400)
                if 'hash' in source and (not isinstance(source['hash'],str) or not re.fullmatch('[a-f0-9]{64}',source['hash'])):
                    raise KnowledgeError('invalid_source','Expected a source content hash',400)
                if not isinstance(source.get('assets',[]),list): raise KnowledgeError('invalid_source','assets must be an array',400)
                for asset in source.get('assets',[]):
                    if not isinstance(asset,dict) or not isinstance(asset.get('hash'),str) or not re.fullmatch('[a-f0-9]{64}',asset['hash']) or not isinstance(asset.get('name'),str):
                        raise KnowledgeError('invalid_source','Asset needs a hash/name',400)
        if item['kind']=='document':
            from knowledge_html import validate_bundle
            validate_bundle(item)
            for field in ('documentDate','versionLabel','versionGroup','dateBasis'):
                if field in item and item[field] is not None and (not isinstance(item[field],str) or len(item[field])>500):
                    raise KnowledgeError('invalid_item',field+' must be bounded text',400)
            if item.get('documentDate') and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',item['documentDate']):
                raise KnowledgeError('invalid_item','documentDate must use YYYY-MM-DD',400)
            asset_hashes={asset['hash'] for source in item.get('sources',[]) for asset in source.get('assets',[])}
            if set(re.findall(r'knowledge-asset:([a-f0-9]{64})',item.get('markdown','')))-asset_hashes:
                raise KnowledgeError('invalid_source','Document asset tokens must have preserved source assets',400)
        if 'documentRefs' in item and not all(isinstance(x,str) for x in item['documentRefs']):
            raise KnowledgeError('invalid_links','documentRefs must contain document IDs',400)
        if 'source' in item and (not isinstance(item['source'],dict) or not isinstance(item['source'].get('path'),str)):
            raise KnowledgeError('invalid_source','source must be a path/evidence object',400)
        for field in ('nodeIds','orderedEdges'):
            if field in item and (not isinstance(item[field],list) or not all(isinstance(x,str) for x in item[field])):
                raise KnowledgeError('invalid_links',field+' must contain IDs',400)
        if 'presentationGroups' in item:
            if item['kind'] != 'view' or item.get('viewType') != 'research':
                raise KnowledgeError('invalid_groups','Groups belong to a research view',400)
            groups=item['presentationGroups']
            if not isinstance(groups,list) or len(groups)>512:
                raise KnowledgeError('invalid_groups','Use at most 512 map groups',400)
            by_id={}; members=set(); allowed=set(item.get('nodeIds',[]))
            for group in groups:
                if (not isinstance(group,dict) or set(group)-{'id','title','parent','nodeIds','description'} or
                    not isinstance(group.get('id'),str) or not re.fullmatch(r'[\w.-]{1,80}',group['id']) or group['id'] in by_id or
                    not isinstance(group.get('title'),str) or not 1<=len(group['title'].strip())<=300 or
                    not isinstance(group.get('description',''),str) or len(group.get('description',''))>12000 or
                    not isinstance(group.get('nodeIds',[]),list) or not all(isinstance(x,str) for x in group.get('nodeIds',[])) or
                    ('parent' in group and not isinstance(group['parent'],str))):
                    raise KnowledgeError('invalid_groups','Map groups need unique local IDs and bounded titles',400)
                owned=group.get('nodeIds',[])
                if len(set(owned))!=len(owned) or set(owned)-allowed or members.intersection(owned):
                    raise KnowledgeError('invalid_groups','Each grouped node must belong to the view and have one direct group',400)
                members.update(owned);by_id[group['id']]=group
            checked=set()
            for identifier in by_id:
                trail=set(); current=identifier
                while current and current not in checked:
                    if current not in by_id or current in trail:
                        raise KnowledgeError('invalid_groups','Map group parents must form an acyclic local hierarchy',400)
                    trail.add(current);current=by_id[current].get('parent','')
                checked.update(trail)
        if 'visibility' in item and item['visibility'] not in ('internal','public-approved'):
            raise KnowledgeError('invalid_item','Visibility must be internal or public-approved',400)
        if item['kind']=='document' and item.get('status','draft') not in ('draft','current','historical','archived'):
            raise KnowledgeError('invalid_item','Unknown document status',400)
        return item

    def changeset(self, expected, key, operations, reason, actor='local-user', task=None, stage=None, validate_only=False, policy=None, code_revision=None, _scan=False, _research=False):
        if not isinstance(expected,int) or isinstance(expected,bool) or not isinstance(key,str) or not 1<=len(key)<=160 or not isinstance(reason,str) or not reason.strip() or len(reason)>3000:
            raise KnowledgeError('invalid_changeset','Expected knowledge revision, idempotency key and reason are required',400)
        if not isinstance(operations,list) or len(operations) > (50000 if _scan or _research else 500):
            raise KnowledgeError('invalid_changeset','At most 500 authored operations per changeset',400)
        if policy is not None: self.validate_policy(policy)
        if policy is not None and any(int(ref)>=len(self.roots) for ref in policy.get('scanRoots',[])):
            raise KnowledgeError('invalid_policy','scanRoots must select registered rootRefs',400)
        if code_revision is not None and (not isinstance(code_revision,dict) or len(canonical(code_revision))>3000):
            raise KnowledgeError('invalid_changeset','code_revision must be a bounded object',400)
        request=dict(expected=expected,operations=operations,reason=reason,actor=actor,task=task,stage=stage,policy=policy,code_revision=code_revision)
        request_hash=hashlib.sha256(canonical(request).encode()).hexdigest()
        with self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                prior=c.execute('SELECT revision,request_hash FROM knowledge_changes WHERE project=? AND key=?',(self.project,key)).fetchone()
                if prior:
                    if prior['request_hash']!=request_hash: raise KnowledgeError('idempotency_conflict','Key already used with different content')
                    c.rollback(); return dict(revision=prior['revision'],replayed=True)
                current=c.execute('SELECT revision FROM knowledge_meta WHERE project=?',(self.project,)).fetchone()[0]
                if current!=expected: raise KnowledgeError('revision_conflict','Refresh/reconcile before resubmitting',revision=current)
                items={r['id']:json.loads(r['body']) for r in c.execute('SELECT id,body FROM knowledge_items WHERE project=?',(self.project,))}
                seen=set()
                for operation in operations:
                    if not isinstance(operation,dict) or operation.get('op') not in ('put','delete'):
                        raise KnowledgeError('invalid_operation','Use put/delete operations',400)
                    identifier=operation.get('id') if operation['op']=='delete' else self.validate_item(operation.get('item'))['id']
                    if not isinstance(identifier,str) or not re.fullmatch(r'[\w:./-]{1,180}',identifier):
                        raise KnowledgeError('invalid_operation','Delete needs a valid item ID',400)
                    if identifier in seen: raise KnowledgeError('duplicate_operation','One operation per item',400)
                    seen.add(identifier)
                    if operation['op']=='delete': items.pop(identifier,None)
                    else:
                        for source in operation['item'].get('sources',[]):
                            for content_hash in ([source['hash']] if source.get('hash') else [])+[x['hash'] for x in source.get('assets',[])]:
                                try: self.read_blob(content_hash)
                                except (OSError,KnowledgeError) as error: raise KnowledgeError('invalid_source','Referenced immutable source/asset missing',400) from error
                        if operation['item'].get('format')=='html':
                            from knowledge_html import content
                            for file in operation['item']['htmlBundle']['files']: content(self,operation['item'],file['path'])
                        items[identifier]=operation['item']
                for item in items.values():
                    if item['kind']=='relation' and (item['from'] not in items or item['to'] not in items):
                        raise KnowledgeError('dangling_relation','Relation endpoints must exist',400,id=item['id'])
                    if any(ref not in items or items[ref]['kind']=='document' for ref in item.get('entityRefs',[])):
                        raise KnowledgeError('dangling_document_link','Linked architecture item missing',400,id=item['id'])
                    if any(ref not in items or items[ref]['kind']!='document' for ref in item.get('documentRefs',[])):
                        raise KnowledgeError('dangling_document_link','Linked document missing',400,id=item['id'])
                    for field,kind in [('nodeIds','entity'),('orderedEdges','relation')]:
                        if any(ref not in items or items[ref]['kind']!=kind for ref in item.get(field,[])):
                            raise KnowledgeError('dangling_view','View references a missing/wrong item',400,id=item['id'])
                if validate_only:
                    c.rollback(); return dict(valid=True,revision=current,operations=len(operations))
                if policy is not None:
                    self.validate_policy(policy)
                    c.execute('UPDATE knowledge_meta SET policy=? WHERE project=?',(canonical(policy),self.project))
                for op in operations:
                    if op['op']=='delete': c.execute('DELETE FROM knowledge_items WHERE project=? AND id=?',(self.project,op['id']))
                    else:
                        item=op['item']; c.execute('INSERT INTO knowledge_items VALUES(?,?,?,?) ON CONFLICT(project,id) DO UPDATE SET kind=excluded.kind,body=excluded.body',
                                                   (self.project,item['id'],item['kind'],canonical(item)))
                revision=current+1
                revision_context=code_revision
                if revision_context is None:
                    latest=c.execute("SELECT body FROM knowledge_jobs WHERE project=? AND state IN ('ready','partial') ORDER BY rowid DESC LIMIT 1",(self.project,)).fetchone()
                    revision_context=dict(fingerprint=json.loads(latest[0]).get('fingerprint'),basis='last-successful-scan') if latest else dict(basis='source-revision-unavailable')
                c.execute('INSERT INTO knowledge_changes(project,revision,key,request_hash,at,actor,task,stage,reason,operations,code_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(self.project,revision,key,request_hash,now(),actor,task,stage,reason,canonical(operations),canonical(revision_context)))
                if task:
                    payload=dict(id='knowledge-'+self.project+'-'+str(revision),kind='note',taskId=task,title='Знания: версия '+str(revision),detail=reason+' · '+canonical(revision_context),actor=actor,
                                 evidence=[dict(path='knowledge/revision/'+str(revision)+'/document/'+op['item']['id'],label=op['item']['title']) for op in operations if op['op']=='put' and op['item']['kind']=='document'])
                    if stage: payload['stageId']=stage
                    payload=self.publication_payload(payload)
                    c.execute('INSERT INTO knowledge_outbox VALUES(?,?,?,NULL)',(self.project,revision,canonical(payload)))
                c.execute('UPDATE knowledge_meta SET revision=? WHERE project=?',(revision,self.project))
                c.commit()
                return dict(revision=revision,changed=len(operations),replayed=False,
                            sources=[dict(path='knowledge/document/'+op['item']['id'],label=op['item']['title']) for op in operations if op['op']=='put' and op['item']['kind']=='document'])
            except BaseException:
                c.rollback(); raise

    @staticmethod
    def validate_policy(policy):
        if not isinstance(policy,dict) or set(policy)-set(DEFAULT_POLICY):
            raise KnowledgeError('invalid_policy','Unknown knowledge policy field',400)
        for key in ('audiences','sections','components','entrypoints','excludeDirectories','scanRoots'):
            if not isinstance(policy.get(key,[]),list): raise KnowledgeError('invalid_policy',key+' must be an array',400)
        if len(canonical(policy).encode('utf-8'))>40000 or len(policy.get('components',[]))>100:
            raise KnowledgeError('invalid_policy','Policy exceeds the compact project configuration limit',400)
        if policy.get('updateMode','manual') not in ('manual','on-demand','background'):
            raise KnowledgeError('invalid_policy','Invalid updateMode',400)
        if policy.get('reviewMode','significant') not in ('significant','manual'):
            raise KnowledgeError('invalid_policy','Invalid reviewMode',400)
        for key,minimum,maximum in [('maxFiles',1,20000),('maxFileBytes',1024,8000000),('descriptionLimit',1,1200),('intervalSeconds',30,86400)]:
            value=policy.get(key,DEFAULT_POLICY[key])
            if not isinstance(value,int) or isinstance(value,bool) or not minimum<=value<=maximum:
                raise KnowledgeError('invalid_policy',key+' outside permitted bounds',400)
        for key in ('audiences','sections','entrypoints','excludeDirectories'):
            if len(policy.get(key,[]))>1000 or not all(isinstance(x,str) and 0<len(x)<=300 for x in policy.get(key,[])):
                raise KnowledgeError('invalid_policy',key+' must contain bounded strings',400)
        if len(policy.get('scanRoots',[]))>100 or not all(isinstance(x,str) and re.fullmatch(r'[0-9]{1,4}',x) for x in policy.get('scanRoots',[])):
            raise KnowledgeError('invalid_policy','scanRoots must contain rootRef IDs; empty selects all',400)
        parents = {}
        for component in policy.get('components',[]):
            if not isinstance(component,dict) or not all(isinstance(component.get(k),str) and component[k] for k in ('id','title')) or not isinstance(component.get('paths',[]),list):
                raise KnowledgeError('invalid_policy','Components need id/title/paths',400)
            if component['id'].startswith('code:') or not re.fullmatch(r'[\w:./-]{1,180}',component['id']):
                raise KnowledgeError('invalid_policy','Component ID conflicts with generated namespace',400)
            if component['id'] in parents:
                raise KnowledgeError('invalid_policy','Component IDs must be unique',400)
            parent = component.get('parent')
            if parent is not None and not isinstance(parent,str):
                raise KnowledgeError('invalid_policy','Component parent must be a component ID',400)
            parents[component['id']] = parent
            if len(component['title'])>300 or not isinstance(component.get('description',''),str) or len(component.get('description',''))>1200 or len(component.get('paths',[]))>100:
                raise KnowledgeError('invalid_policy','Component title/description/paths exceed permitted bounds',400)
            if not all(isinstance(x,str) and 0<len(x)<=300 and not Path(x).is_absolute() and '..' not in Path(x).parts for x in component.get('paths',[])):
                raise KnowledgeError('invalid_policy','Component paths must be project-relative prefixes',400)
        for identifier in parents:
            seen = {identifier}
            parent = parents[identifier]
            while parent is not None:
                if parent not in parents:
                    raise KnowledgeError('invalid_policy','Component parent does not exist',400)
                if parent in seen:
                    raise KnowledgeError('invalid_policy','Component hierarchy must not contain cycles',400)
                seen.add(parent)
                parent = parents[parent]

    def workspace_access(self):
        from project_workspaces import local_access
        return local_access(self.registry, self.project, self.roots)

    def source_location(self, path):
        if not self.roots:
            raise KnowledgeError('workspace_required','Connect a code workspace to read source files',409)
        if not isinstance(path,str) or not path or Path(path).is_absolute() or '..' in Path(path).parts:
            raise KnowledgeError('unsafe_source','Use a project-relative path',400)
        index=0
        base=self.roots[index]
        if path.startswith('@roots/'):
            match=re.fullmatch(r'@roots/([1-9][0-9]*)/(.+)',path)
            if not match or int(match[1])>=len(self.roots): raise KnowledgeError('unsafe_source','Unknown registered root reference',400)
            index=int(match[1]);base=self.roots[index]; path=match[2]
        if str(index) not in self.workspace_access()['available']:
            raise KnowledgeError('workspace_unavailable','The source workspace is disabled, missing or inaccessible',409)
        source=base/path
        if not source.resolve().is_relative_to(base) or any(p in {'.git','.codex','.agents'} for p in Path(path).parts):
            raise KnowledgeError('unsafe_source','Source outside permitted project tree',400)
        return base,source

    def source_path(self,path): return self.source_location(path)[1]

    def source_read(self, identifier, offset=0, limit=12000):
        """Bounded current text of a scanned file, verified against its stored hash."""
        item = self.read(identifier)
        source = item.get('source', {})
        if item.get('type') != 'file' or not item.get('generatedBy') or item.get('removed') or not re.fullmatch('[0-9a-f]{64}', source.get('hash', '')):
            raise KnowledgeError('source_not_scanned', 'Read a registered scanned file', 409)
        path = self.source_path(source['path'])
        from project_workspaces import no_reparse, WorkspaceError
        try:
            no_reparse(path)
            with path.open('rb') as stream:
                data = stream.read(8_000_001)
            if len(data)>8_000_000 or hashlib.sha256(data).hexdigest()!=source['hash']:
                raise KnowledgeError('source_changed', 'Source changed; refresh the scan before reading', 409)
            text = data.decode('utf-8-sig')
        except (OSError, UnicodeError, WorkspaceError) as error:
            raise KnowledgeError('source_unavailable', 'Scanned source is unavailable', 409) from error
        offset, limit = max(0, int(offset)), max(1, min(12000, int(limit)))
        return dict(id=identifier, path=source['path'], hash=source['hash'], offset=offset,
                    text=text[offset:offset+limit], more=offset+limit<len(text),
                    next=offset+limit if offset+limit<len(text) else None)

    def blob(self, content):
        identifier=hashlib.sha256(content).hexdigest()
        path=self.data/'blobs'/identifier[:2]/identifier
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_name(identifier+'.'+uuid.uuid4().hex+'.tmp')
            try:
                with temporary.open('wb') as stream:
                    stream.write(content); stream.flush()
                    import os
                    os.fsync(stream.fileno())
                import os
                os.replace(temporary,path)
            finally: temporary.unlink(missing_ok=True)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=identifier:
            raise KnowledgeError('blob_corrupt','Stored source hash mismatch',500)
        return identifier

    def read_blob(self, identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9]{64}',identifier):
            raise KnowledgeError('invalid_blob','Expected a content hash',400)
        path=self.data/'blobs'/identifier[:2]/identifier
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=identifier:
            raise KnowledgeError('blob_corrupt','Stored source hash mismatch',500)
        return content

    def import_preview(self, paths):
        if not isinstance(paths,list) or not 1<=len(paths)<=50:
            raise KnowledgeError('invalid_import','Select 1–50 Markdown/text/HTML sources',400)
        candidates=[]
        with self.registry.connect() as c:
            known_hashes={item.get('importHash'):item['id'] for row in c.execute("SELECT body FROM knowledge_items WHERE project=? AND kind='document'",(self.project,))
                          for item in [json.loads(row[0])] if item.get('importHash')}
        for relative in paths:
            source_root,path=self.source_location(relative)
            if path.suffix.lower() in ('.html','.htm'):
                from knowledge_html import snapshot, content
                bundle,fingerprint,title,description,missing,external=snapshot(self,source_root,path)
                identifier='doc:source:'+hashlib.sha256(relative.encode()).hexdigest()[:24]
                try: current=self.read(identifier)
                except KnowledgeError as error:
                    if error.body['error']!='item_missing': raise
                    current=None
                entry=next(f for f in bundle['files'] if f['path']==bundle['entry'])
                assets=[dict(hash=f['hash'],name=f['path'].split('/')[-1],original=f['path']) for f in bundle['files'] if f['path']!=bundle['entry']]
                item=dict(id=identifier,kind='document',format='html',title=title,description=description,
                    markdown='',htmlBundle=bundle,audience='developer',section='Imported',status='draft',visibility='internal',
                    entityRefs=[],sources=[dict(path=relative,hash=entry['hash'],assets=assets)],importHash=fingerprint,
                    missingAssets=missing,missingLinks=[],externalResources=external)
                action='duplicate' if current is None and fingerprint in known_hashes else 'create' if current is None else 'unchanged' if current.get('importHash')==fingerprint else 'review'
                # Preserve authored classification on reimport; only source content is replaced after review.
                if current:
                    for field in ('title','description','audience','section','status','visibility','type','entityRefs','documentRefs','documentDate','dateBasis','versionLabel','versionGroup'):
                        if field in current: item[field]=current[field]
                self.validate_item(item)
                old=content(self,current).decode('utf-8-sig') if current and current.get('format')=='html' else current.get('markdown','') if current else ''
                text=content(self,item).decode('utf-8-sig')
                diff=''.join(difflib.unified_diff(old.splitlines(True),text.splitlines(True))) if current else ''
                if current and current.get('htmlBundle')!=bundle: diff+='\nBundle assets changed:\n'+canonical(bundle)
                known_hashes[fingerprint]=known_hashes.get(fingerprint,identifier)
                candidates.append(dict(action=action,item=item,diff=diff))
                continue
            if path.suffix.lower() not in ('.md','.markdown','.txt'): raise KnowledgeError('unsupported_import','Only Markdown/text/HTML import is supported',400)
            data=path.read_bytes()
            if len(data)>128000: raise KnowledgeError('source_too_large','Source exceeds 128 KB',400)
            try: text=data.decode('utf-8-sig')
            except UnicodeDecodeError as error: raise KnowledgeError('source_encoding','Import requires UTF-8 text',400) from error
            identifier='doc:source:'+hashlib.sha256(relative.encode()).hexdigest()[:24]
            try: current=self.read(identifier)
            except KnowledgeError: current=None
            assets=[]; missing=[]; missing_links=[]
            for target in re.findall(r'!\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)',text):
                if re.match(r'^[a-zA-Z]+:|^//|^#',target): continue
                local=(path.parent/target).resolve()
                if not local.is_relative_to(source_root) or not local.is_file(): missing.append(target); continue
                asset_bytes=local.read_bytes()
                if len(asset_bytes)>20_000_000: missing.append(target); continue
                asset=self.blob(asset_bytes)
                assets.append(dict(original=target,hash=asset,name=local.name))
                text=text.replace(']('+target+')','](knowledge-asset:'+asset+')')
            for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)',text):
                if not re.match(r'^https?://|^#',target): missing_links.append(target)
            if re.search(r'!INCLUDE|\{\{\s*include|\{%\s*include',text,re.I): missing_links.append('Includes require explicit review/import')
            source_hash=self.blob(data)
            title=next((line.lstrip('#').strip() for line in text.splitlines() if line.startswith('# ')),path.stem)[:300]
            item=dict(id=identifier,kind='document',title=title,markdown=text,audience='developer',section='Imported',
                status='draft',visibility='internal',entityRefs=[],sources=[dict(path=relative,hash=source_hash,assets=assets)],
                importHash=source_hash,missingAssets=missing,missingLinks=sorted(set(missing_links)))
            action='duplicate' if current is None and source_hash in known_hashes else 'create' if current is None else 'unchanged' if current.get('importHash')==source_hash else 'review'
            self.validate_item(item)
            known_hashes[source_hash]=known_hashes.get(source_hash,identifier)
            candidates.append(dict(action=action,item=item,diff=''.join(difflib.unified_diff(current.get('markdown','').splitlines(True),text.splitlines(True))) if current else ''))
        identifier=uuid.uuid4().hex
        record=dict(id=identifier,revision=self.context()['revision'],items=candidates,createdAt=now())
        with self.registry.connect() as c: c.execute('INSERT INTO knowledge_imports VALUES(?,?,?)',(self.project,identifier,canonical(record)))
        return record

    def import_read(self, identifier, index=0, field='markdown', offset=0, limit=12000):
        if field not in ('markdown','html','source','diff') or index<0 or offset<0:
            raise KnowledgeError('invalid_import','Use a candidate index and source/markdown/html/diff field',400)
        with self.registry.connect() as c:
            row=c.execute('SELECT body FROM knowledge_imports WHERE project=? AND id=?',(self.project,identifier)).fetchone()
        if not row: raise KnowledgeError('preview_missing','Create an import preview first',404)
        preview=json.loads(row[0])
        if index>=len(preview['items']): raise KnowledgeError('candidate_missing','Candidate index is outside this preview',404)
        candidate=preview['items'][index]; item=candidate['item']
        if field=='diff': text=candidate.get('diff','')
        elif item.get('format')=='html':
            from knowledge_html import content
            text=content(self,item).decode('utf-8-sig')
        else: text=item.get('markdown','')
        limit=min(12000,max(1,limit)); end=offset+limit
        return dict(identifier=identifier,index=index,revision=preview['revision'],id=item['id'],title=item['title'],action=candidate['action'],field=field,
                    text=text[offset:end],more=end<len(text),next=end if end<len(text) else None)

    def import_apply(self, identifier, expected, key, actor='local-user', task=None, stage=None, selections=None, metadata=None):
        with self.registry.connect() as c:
            row=c.execute('SELECT body FROM knowledge_imports WHERE project=? AND id=?',(self.project,identifier)).fetchone()
        if not row: raise KnowledgeError('preview_missing','Create an import preview first',404)
        preview=json.loads(row[0]); selections=selections or []
        if not isinstance(selections,list) or not all(isinstance(x,str) for x in selections): raise KnowledgeError('invalid_import','selections must contain candidate IDs',400)
        metadata={} if metadata is None else metadata
        allowed={'title','description','audience','section','type','status','visibility','entityRefs','documentRefs','documentDate','dateBasis','versionLabel','versionGroup'}
        if not isinstance(metadata,dict) or any(not isinstance(value,dict) or set(value)-allowed for value in metadata.values()):
            raise KnowledgeError('invalid_import','metadata maps candidate IDs to supported document classification fields',400)
        ids={x['item']['id'] for x in preview['items']}
        if set(metadata)-ids or set(selections)-ids: raise KnowledgeError('invalid_import','Unknown candidate ID',400)
        ops=[dict(op='put',item=dict(x['item'],**metadata.get(x['item']['id'],{}))) for x in preview['items'] if x['action']=='create' or x['action'] in ('review','duplicate') and x['item']['id'] in selections]
        return self.changeset(expected,key,ops,'Import preview '+identifier,actor,task,stage)

    def restore(self, identifier, revision, expected, key, actor='local-user', task=None, stage=None):
        item=self.read(identifier,revision)
        return self.changeset(expected,key,[dict(op='put',item=item)],'Restore '+identifier+' from revision '+str(revision),actor,task,stage)

    def impact(self, paths=None, change=None, task=None, stage=None, record=False):
        paths=paths or []; change=change or {}
        if not isinstance(paths,list) or not all(isinstance(p,str) for p in paths):
            raise KnowledgeError('invalid_impact','paths must be an array of project-relative paths',400)
        if not isinstance(change,dict): raise KnowledgeError('invalid_impact','change must be an object',400)
        if len(canonical(change).encode('utf-8'))>8000 or len(paths)>200 or any(len(p)>1000 for p in paths):
            raise KnowledgeError('invalid_impact','Impact assessment exceeds bounded input',400)
        structural=bool(change.get('structure') or change.get('contracts'))
        behavioral=bool(change.get('behavior') or change.get('userWorkflow'))
        cosmetic=bool(change.get('cosmetic')) and not structural and not behavioral
        with self.registry.connect() as c:
            rows=[json.loads(r[0]) for r in c.execute('SELECT body FROM knowledge_items WHERE project=?',(self.project,))]
        entities=[x['id'] for x in rows if x['kind']=='entity' and x.get('source',{}).get('path') in paths]
        docs=[x['id'] for x in rows if x['kind']=='document' and (set(x.get('entityRefs',[])) & set(entities) or any(s.get('path') in paths for s in x.get('sources',[])))]
        result=dict(architecture='review-required' if structural else 'no-impact' if cosmetic or change.get('noStructuralImpact') else 'check-on-scan',
                    documentation='review-required' if structural or behavioral else 'no-impact' if cosmetic else 'assess-behavior',
                    affectedEntities=entities[:200],affectedDocuments=docs[:200],
                    reason=change.get('reason','Facts are refreshed by local scan; agent assesses behavior/semantics, not every edit.'),
                    revision=self.context()['revision'])
        if record:
            if not task or not change.get('reason'): raise KnowledgeError('invalid_impact','Recorded impact requires task and reason',400)
            result.update(task=task,stage=stage,at=now(),change=change,
                          state='resolved' if change.get('knowledgeUpdated') or result['architecture']==result['documentation']=='no-impact' else 'review-needed')
            with self.registry.connect() as c:
                c.execute('INSERT INTO knowledge_reviews VALUES(?,?,?) ON CONFLICT(project,task) DO UPDATE SET body=excluded.body',(self.project,task,canonical(result)))
        return result

    def flush_publication(self):
        """Retry the supported journal API after the knowledge transaction commits."""
        if not hasattr(self.registry,'store'): return
        with self.registry.connect() as c:
            rows=[dict(r) for r in c.execute('SELECT revision,payload FROM knowledge_outbox WHERE project=? ORDER BY revision LIMIT 20',(self.project,))]
        for row in rows:
            try:
                payload=self.publication_payload(json.loads(row['payload']))
                # Repairs previously queued oversized records without changing the immutable knowledge history.
                with self.registry.connect() as c: c.execute('UPDATE knowledge_outbox SET payload=? WHERE project=? AND revision=?',(canonical(payload),self.project,row['revision']))
                self.registry.store(self.project).record(payload)
                with self.registry.connect() as c: c.execute('DELETE FROM knowledge_outbox WHERE project=? AND revision=?',(self.project,row['revision']))
            except Exception as error:
                with self.registry.connect() as c: c.execute('UPDATE knowledge_outbox SET error=? WHERE project=? AND revision=?',(str(error)[:500],self.project,row['revision']))
                break

    @staticmethod
    def publication_payload(payload):
        payload=dict(payload)
        # The task journal has a stricter event envelope than knowledge history.
        # Keep author provenance in knowledge_changes and readable journal detail.
        actor=payload.pop('actor',None)
        detail=payload.get('detail','')
        if actor is not None: detail='Автор: '+str(actor)+' · '+detail
        payload['detail']=detail[:3000]
        evidence=[dict(x,label=x.get('label','')[:200]) for x in payload.get('evidence',[])]
        count=len(evidence); payload['evidence']=evidence[:100]
        while payload['evidence'] and len(canonical(payload).encode('utf-8'))>45000: payload['evidence'].pop()
        if len(payload['evidence'])<count:
            payload['detail']+=' · Показано '+str(len(payload['evidence']))+' из '+str(count)+' документов; полный состав в истории знаний.'
        return payload

    def start_scan(self, actor='local-user', task=None, stage=None):
        if not self.roots:
            raise KnowledgeError('workspace_required','Connect a code workspace before scanning architecture',409)
        access = self.workspace_access()
        if not access['available']:
            raise KnowledgeError('workspace_unavailable','An enabled accessible source workspace is required',409)
        with _SETUP_LOCK:
            if not hasattr(self.registry,'_knowledge_executor'):
                self.registry._knowledge_executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='knowledge-scan')
        with self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            active=c.execute("SELECT body FROM knowledge_jobs WHERE project=? AND state IN ('queued','running') AND COALESCE(json_extract(body,'$.kind'),'scan')='scan' ORDER BY rowid DESC LIMIT 1",(self.project,)).fetchone()
            if active:
                c.rollback(); return json.loads(active[0])
            identifier=uuid.uuid4().hex
            job=dict(id=identifier,state='queued',createdAt=now(),actor=actor,task=task,stage=stage,workspaceRevision=access['signature'])
            c.execute('INSERT INTO knowledge_jobs VALUES(?,?,?,?)',(self.project,identifier,'queued',canonical(job)))
            c.commit()
        self.registry._knowledge_executor.submit(self._scan_job,job)
        return job

    def job(self, identifier):
        with self.registry.connect() as c:
            row=c.execute('SELECT body FROM knowledge_jobs WHERE project=? AND id=?',(self.project,identifier)).fetchone()
        if not row: raise KnowledgeError('job_missing','Unknown scan job',404)
        return json.loads(row[0])

    def _scan_job(self, job):
        from knowledge_scan import scan
        def save():
            with self.registry.connect() as c:
                c.execute('UPDATE knowledge_jobs SET state=?,body=? WHERE project=? AND id=?',(job['state'],canonical(job),self.project,job['id']))
        job.update(state='running',startedAt=now()); save()
        cache_path=self.data/'scan-cache.json'
        try:
            try: prior=json.loads(cache_path.read_text(encoding='utf-8'))
            except (OSError,ValueError): prior={}
            policy=self.context()['policy']
            access=self.workspace_access()
            job.setdefault('workspaceRevision', access['signature'])
            selected=[(i,root) for i,root in enumerate(self.roots) if str(i) in access['available'] and (not policy.get('scanRoots') or str(i) in policy['scanRoots'])]
            if job.get('workspaceRevision') != access['signature'] or set(policy.get('scanRoots',[]))-access['available']:
                raise KnowledgeError('workspace_changed','Source workspaces changed or became unavailable; refresh before scanning',409)
            if not selected or any(int(ref)>=len(self.roots) for ref in policy.get('scanRoots',[])):
                raise KnowledgeError('scan_roots_missing','Configured scanRoots are no longer registered',400)
            def all_roots(cache):
                candidates=[scan(root,policy,cache,path_prefix='' if i==0 else f'@roots/{i}/') for i,root in selected]
                combined=dict(candidates[0])
                for field in ('entities','relations'): combined[field]=list({x['id']:x for candidate in candidates for x in candidate[field]}.values())
                combined['diagnostics']=[x for candidate in candidates for x in candidate['diagnostics']][:100]
                combined['cache']={k:v for candidate in candidates for k,v in candidate['cache'].items()}
                combined['counts']={k:sum(x['counts'][k] for x in candidates) for k in candidates[0]['counts']}
                combined['capabilities']={}
                for candidate in candidates:
                    for language,values in candidate['capabilities'].items():
                        combined['capabilities'][language]=sorted(set(combined['capabilities'].get(language,[])+values))
                combined['fingerprint']=hashlib.sha256(canonical([x['fingerprint'] for x in candidates]).encode()).hexdigest()
                combined['status']='ready' if all(x['status']=='ready' for x in candidates) else 'partial'
                return combined
            result=all_roots(prior)
            heads=[]
            from version_control import source_revision
            for _,root in selected:
                heads.append(source_revision(root))
            # Java parses from source paths; verify content and inventory again so
            # a concurrent edit cannot publish facts against the wrong hashes.
            verified=all_roots(result['cache'])
            if verified['fingerprint']!=result['fingerprint']:
                job.update(state='stale',finishedAt=now(),error='Source changed during scan; retry refresh')
                save(); return
            # Optimistic apply can reconcile a concurrent authored edit without losing it.
            for attempt in range(3):
                context=self.context()
                if context['policy']!=policy or context['workspaceRevision'] != job['workspaceRevision']:
                    job.update(state='stale',finishedAt=now(),error='Policy or source workspaces changed during scan; retry refresh')
                    save(); return
                with self.registry.connect() as c:
                    existing={r['id']:json.loads(r['body']) for r in c.execute('SELECT id,body FROM knowledge_items WHERE project=?',(self.project,))}
                generated={x['id']:x for x in result['entities']+result['relations']}
                ops=[]
                for identifier,item in generated.items():
                    old=existing.get(identifier,{})
                    for field in ('description','documentRefs','layout','reviewedAgainst'):
                        if field in old: item[field]=old[field]
                    if old!=item: ops.append(dict(op='put',item=item))
                for identifier,item in existing.items():
                    if item.get('generatedBy') and identifier not in generated and not item.get('removed'):
                        path=item.get('source',{}).get('path')
                        source_ref=str(int(path.split('/')[1])) if isinstance(path,str) and re.match(r'^@roots/[1-9][0-9]*/',path) else '0' if path else None
                        if source_ref is not None and source_ref not in {str(i) for i,_ in selected}:
                            if item.get('analysisStatus')!='unavailable':ops.append(dict(op='put',item=dict(item,analysisStatus='unavailable')))
                            continue
                        # Missing facts from a failed/partial parse are not evidence of deletion.
                        if result['status']=='ready': ops.append(dict(op='put',item=dict(item,removed=True)))
                        elif item.get('analysisStatus')!='stale': ops.append(dict(op='put',item=dict(item,analysisStatus='stale')))
                try:
                    receipt=self.changeset(context['revision'],'scan:'+job['id'],ops,'Refresh shallow source architecture',job['actor'],job.get('task'),job.get('stage'),code_revision=dict(fingerprint=result['fingerprint'],heads=heads,rootRefs=[str(i) for i,_ in selected],basis='local-source-scan'),_scan=True) if ops else dict(revision=context['revision'],changed=0,unchanged=True)
                    break
                except KnowledgeError as error:
                    if error.body['error']!='revision_conflict' or attempt==2: raise
            from project_portal import atomic_write
            cache_path.parent.mkdir(parents=True,exist_ok=True)
            atomic_write(cache_path,canonical(result.pop('cache')))
            job.update(state=result['status'],finishedAt=now(),receipt=receipt,**{k:result[k] for k in ('capabilities','diagnostics','counts','fingerprint')})
        except Exception as error:
            job.update(state='failed',finishedAt=now(),error=str(error)[:500])
        save()
        self.flush_publication()

    def export(self, public=False):
        with self.registry.connect() as c:
            items=[json.loads(r[0]) for r in c.execute('SELECT body FROM knowledge_items WHERE project=? ORDER BY id',(self.project,))]
        documents=[x for x in items if x['kind']=='document' and (not public or x.get('visibility')=='public-approved')]
        if public:
            # Fail closed rather than copying private includes/assets or internal identifiers.
            for item in documents:
                if item.get('format')=='html': raise KnowledgeError('public_dependency','Executable HTML documents are internal export only',400,id=item['id'])
                if item.get('entityRefs') or item.get('sources') or re.search(r'!\[|<[^>]+>|\]\((?!https?://|#)|(?m:^\s*\[[^\]]+\]:\s*(?!https?://|#))',item.get('markdown','')):
                    raise KnowledgeError('public_dependency','Public export requires reviewed self-contained articles',400,id=item['id'])
            exported=[dict(id='article-'+hashlib.sha256(canonical(dict(title=x['title'],markdown=x.get('markdown',''))).encode()).hexdigest()[:24],title=x['title'],markdown=x.get('markdown','')) for x in documents]
            exported=list({x['id']:x for x in exported}.values())
        else: exported=items
        return dict(schemaVersion=1,**({} if public else dict(project=self.project,revision=self.context()['revision'])),public=public,
                    items=exported,manifest=[dict(id=x['id'],hash=hashlib.sha256(canonical(x).encode()).hexdigest()) for x in exported])

    def export_bundle(self, public=False):
        """Portable Markdown/HTML/JSON/assets from preserved snapshots."""
        import io
        import zipfile
        snapshot=self.export(public)
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            def write(path,content):
                entry=zipfile.ZipInfo(path,date_time=(1980,1,1,0,0,0)); entry.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(entry,content)
            write('knowledge.json',canonical(snapshot))
            assets=set()
            for item in snapshot['items']:
                if item.get('kind','document')!='document': continue
                if item.get('format')=='html':
                    from knowledge_html import content
                    prefix='documents/'+hashlib.sha256(item['id'].encode()).hexdigest()[:24]+'/'
                    for file in item['htmlBundle']['files']: write(prefix+file['path'],content(self,item,file['path']))
                    continue
                if 'markdown' not in item: continue
                text=item['markdown']
                for source in item.get('sources',[]):
                    for asset in source.get('assets',[]):
                        identifier=asset['hash']; assets.add(identifier)
                        text=text.replace('knowledge-asset:'+identifier,'../assets/'+identifier)
                # Hash filenames avoid path traversal and cross-platform invalid names.
                write('documents/'+hashlib.sha256(item['id'].encode()).hexdigest()[:24]+'.md',text)
            for identifier in sorted(assets): write('assets/'+identifier,self.read_blob(identifier))
            write('README.txt','Project Hub portable knowledge snapshot. knowledge.json preserves IDs and links; documents/ contains Markdown files and HTML bundles with their relative asset paths. Public export contains only explicitly approved, self-contained Markdown articles.\n')
        return output.getvalue()

    def backup(self):
        with self.registry.connect() as c:
            # One SQLite read transaction defines a consistent knowledge snapshot.
            c.execute('BEGIN')
            meta=dict(c.execute('SELECT revision,policy FROM knowledge_meta WHERE project=?',(self.project,)).fetchone())
            items=[json.loads(r[0]) for r in c.execute('SELECT body FROM knowledge_items WHERE project=? ORDER BY id',(self.project,))]
            changes=[dict(r) for r in c.execute('SELECT * FROM knowledge_changes WHERE project=? ORDER BY revision',(self.project,))]
            c.commit()
        hashes=set()
        for item in items:
            for source in item.get('sources',[]):
                if source.get('hash'): hashes.add(source['hash'])
                hashes.update(asset['hash'] for asset in source.get('assets',[]))
        for change in changes:
            for op in json.loads(change['operations']):
                for source in op.get('item',{}).get('sources',[]):
                    if source.get('hash'): hashes.add(source['hash'])
                    hashes.update(asset['hash'] for asset in source.get('assets',[]))
        # The same CAS also stores opaque task artifacts and their descriptors.
        # Knowledge-only reachability must never drop task/stage or historical
        # versions. Include verified published blobs; task journals are backed
        # up independently by the project data backup.
        hashes.update(path.name for path in (self.data / 'blobs').glob('*/*')
                      if path.is_file() and re.fullmatch(r'[a-f0-9]{64}', path.name))
        from artifact_store import inspect_descriptor, descriptor_manifest
        artifact_descriptors = descriptor_manifest(self)
        from git_batch_store import manifest
        git_batches = manifest(self)
        for identifier in artifact_descriptors:
            item = inspect_descriptor(self.read_blob(identifier))
            if item['contentHash'] not in hashes or (item.get('previous') is not None and item['previous'] not in artifact_descriptors):
                raise KnowledgeError('blob_corrupt', 'Artifact version history is incomplete', 500)
            if len(self.read_blob(item['contentHash'])) != item['size']:
                raise KnowledgeError('blob_corrupt', 'Artifact content size mismatch', 500)
            if item.get('previous') is not None and inspect_descriptor(self.read_blob(item['previous']))['artifactId'] != item['artifactId']:
                raise KnowledgeError('blob_corrupt', 'Artifact version ID mismatch', 500)
        return dict(schemaVersion=1,project=self.project,meta=meta,items=items,changes=changes,
                    artifactDescriptors=artifact_descriptors,
                    gitBatches=git_batches,
                    blobs={h:base64.b64encode(self.read_blob(h)).decode() for h in sorted(hashes)})

    def restore_backup(self, backup):
        if not isinstance(backup,dict) or backup.get('schemaVersion')!=1 or not isinstance(backup.get('items'),list) or not isinstance(backup.get('changes'),list) or not isinstance(backup.get('blobs'),dict):
            raise KnowledgeError('invalid_backup','Invalid knowledge backup',400)
        try:
            meta=backup['meta']; self.validate_policy(json.loads(meta['policy']))
            if not isinstance(meta['revision'],int) or meta['revision']<0: raise ValueError('Invalid revision')
            restored={}; keys=set(); needed=set()
            def inspect_item(item):
                self.validate_item(item)
                for source in item.get('sources',[]):
                    if source.get('hash'): needed.add(source['hash'])
                    needed.update(x['hash'] for x in source.get('assets',[]))
            for revision,row in enumerate(backup['changes'],1):
                if row['revision']!=revision or row['key'] in keys: raise ValueError('History must be consecutive with unique keys')
                keys.add(row['key'])
                for op in json.loads(row['operations']):
                    if op['op']=='put': inspect_item(op['item']); restored[op['item']['id']]=op['item']
                    elif op['op']=='delete': restored.pop(op['id'],None)
                    else: raise ValueError('Invalid history operation')
            current={}
            for item in backup['items']:
                inspect_item(item)
                if item['id'] in current: raise ValueError('Duplicate current item')
                current[item['id']]=item
            if len(backup['changes'])!=meta['revision'] or current!=restored: raise ValueError('Current items do not match immutable history')
            for item in current.values():
                if item['kind']=='relation' and (item['from'] not in current or item['to'] not in current): raise ValueError('Dangling restored relationship')
                if any(x not in current for x in item.get('entityRefs',[])+item.get('documentRefs',[])): raise ValueError('Dangling restored link')
            if needed-set(backup['blobs']): raise ValueError('Required source/assets absent')
            contents={identifier:base64.b64decode(encoded,validate=True) for identifier,encoded in backup['blobs'].items()}
            if any(hashlib.sha256(content).hexdigest()!=identifier for identifier,content in contents.items()): raise ValueError('Blob hash mismatch')
            from artifact_store import inspect_descriptor
            descriptors = backup.get('artifactDescriptors', [])
            if not isinstance(descriptors, list) or any(not isinstance(identifier, str) for identifier in descriptors) or descriptors != sorted(set(descriptors)):
                raise ValueError('Invalid artifact descriptor manifest')
            for identifier in descriptors:
                item = inspect_descriptor(contents[identifier])
                if len(contents[item['contentHash']]) != item['size']: raise ValueError('Artifact content size mismatch')
                if item.get('previous') is not None and item['previous'] not in descriptors: raise ValueError('Artifact history is incomplete')
                if item.get('previous') is not None and inspect_descriptor(contents[item['previous']])['artifactId'] != item['artifactId']:
                    raise ValueError('Artifact version ID mismatch')
            from git_batch_store import inspect
            git_batches = backup.get('gitBatches', [])
            if not isinstance(git_batches, list) or any(not isinstance(identifier, str) for identifier in git_batches) or git_batches != sorted(set(git_batches)):
                raise ValueError('Invalid Git batch registry manifest')
            for identifier in git_batches:
                if not re.fullmatch(r'[a-f0-9]{64}', identifier):
                    raise ValueError('Invalid Git batch reference')
                inspect(contents[identifier], contents.__getitem__)
            for item in list(current.values())+[op['item'] for change in backup['changes'] for op in json.loads(change['operations']) if op['op']=='put']:
                if item.get('format')=='html' and any(len(contents[f['hash']])!=f['size'] for f in item['htmlBundle']['files']): raise ValueError('HTML manifest file size mismatch')
        except (KeyError,TypeError,ValueError) as error:
            raise KnowledgeError('invalid_backup',str(error)[:300],400) from error
        for content in contents.values(): self.blob(content)
        from artifact_store import register_descriptor
        for identifier in descriptors: register_descriptor(self, identifier)
        from git_batch_store import register
        for identifier in git_batches: register(self, identifier)
        with self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                if c.execute('SELECT revision FROM knowledge_meta WHERE project=?',(self.project,)).fetchone()[0]!=0 or c.execute('SELECT 1 FROM knowledge_items WHERE project=?',(self.project,)).fetchone():
                    raise KnowledgeError('restore_not_empty','Restore requires an empty knowledge destination')
                for item in backup['items']:
                    c.execute('INSERT INTO knowledge_items VALUES(?,?,?,?)',(self.project,item['id'],item['kind'],canonical(item)))
                for row in backup['changes']:
                    c.execute('INSERT INTO knowledge_changes(project,revision,key,request_hash,at,actor,task,stage,reason,operations,code_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(self.project,row['revision'],row['key'],row['request_hash'],row['at'],row['actor'],row.get('task'),row.get('stage'),row['reason'],row['operations'],row.get('code_revision','{}')))
                c.execute('UPDATE knowledge_meta SET revision=?,policy=? WHERE project=?',(meta['revision'],meta['policy'],self.project))
                c.commit()
            except BaseException: c.rollback(); raise
        return dict(revision=meta['revision'],items=len(backup['items']),blobs=len(backup['blobs']))


def execute(registry, project, action, args=None, actor='local-user'):
    allowed={'context':set(), 'search':{'query','kind','offset','limit','type','component','entrypoint','endpoint'}, 'source-tree':{'query','component','offset','limit','mode'}, 'source-read':{'id','offset','limit'}, 'read':{'id','revision'},
             'subsystem-plan':{'expected','operation','identifier','patch','key','reason','task','stage'},
             'history':{'id','offset','limit'}, 'changeset':{'expected','key','operations','reason','task','stage','validate_only','policy','code_revision'},
             'scan':{'task','stage'}, 'job':{'id'}, 'import-preview':{'paths'}, 'import-read':{'identifier','index','field','offset','limit'},
             'import-apply':{'identifier','expected','key','task','stage','selections','metadata'},
             'restore':{'id','revision','expected','key','task','stage'}, 'impact':{'paths','change','task','stage','record'}, 'export':{'public'},
             'backup':set(), 'restore-backup':{'backup'},
             'research-capabilities':{'id'}, 'research-object':{'id'}, 'research':{'query','task','stage'},
             'research-result':{'id','offset','limit'}, 'research-cancel':{'id'}, 'research-history':{'offset','limit'},'research-save':{'expected','key','title','nodeIds','edgeIds','presentationGroups','resultId'},'research-providers':set()}
    args={} if args is None else args
    if not isinstance(action,str) or action not in allowed or not isinstance(args,dict) or set(args)-allowed[action]:
        raise KnowledgeError('invalid_arguments','Unknown action or argument',400)
    from backup_session import active
    reads = {'context', 'search', 'source-tree', 'source-read', 'read', 'history', 'job', 'import-read',
             'research-capabilities', 'research-object', 'research-result', 'research-history', 'research-providers'}
    if active(registry) is not None and action not in reads:
        raise KnowledgeError('backup_in_progress', 'A backup snapshot is being copied; retry the change shortly', 423, retryable=True)
    required={'read':{'id'},'source-read':{'id'},'job':{'id'},'changeset':{'expected','key','operations','reason'},
              'subsystem-plan':{'expected','operation','identifier','key','reason'},
              'import-preview':{'paths'},'import-read':{'identifier'},'import-apply':{'identifier','expected','key'},
              'restore':{'id','revision','expected','key'},'restore-backup':{'backup'},
              'research':{'query'},'research-capabilities':{'id'},'research-object':{'id'},'research-result':{'id'},'research-cancel':{'id'},'research-save':{'expected','key','title','nodeIds','edgeIds'}}
    if required.get(action,set())-set(args): raise KnowledgeError('invalid_arguments','Required argument missing',400)
    for field in ('offset','limit','revision','index'):
        if field in args:
            if isinstance(args[field],bool) or not (isinstance(args[field],int) or isinstance(args[field],str) and re.fullmatch('-?[0-9]+',args[field])):
                raise KnowledgeError('invalid_arguments',field+' must be an integer',400)
            args[field]=int(args[field])
    for field in ('id','identifier','task','stage','kind','type','component','endpoint') + (() if action=='research' else ('query',)):
        if field in args and (not isinstance(args[field],str) or len(args[field])>180):
            raise KnowledgeError('invalid_arguments',field+' must be bounded text',400)
    for field in ('public','record','validate_only'):
        if field in args and not isinstance(args[field],bool): raise KnowledgeError('invalid_arguments',field+' must be boolean',400)
    store=KnowledgeStore(registry,project)
    if action == 'subsystem-plan':
        from subsystem_actions import plan_subsystem
        args = dict(args)
        args['action'] = args.pop('operation')
        return plan_subsystem(store, **args)
    if action.startswith('research'):
        import knowledge_research as research
        if action=='research': return research.start(store,actor=actor,**args)
        if action=='research-object': return research.read_object(store,args['id'])
        if action=='research-capabilities': return research.capabilities(store,args['id'])
        if action=='research-result': return research.result(store,args['id'],args.get('offset',0),args.get('limit',100))
        if action=='research-cancel': return research.cancel(store,args['id'])
        if action=='research-history': return research.history(store,**args)
        if action=='research-providers': return research.provider_info(store)
        if action=='research-save': return research.save_map(store,actor=actor,**args)
    if action=='context': return store.context()
    if action=='search': return store.search(**args)
    if action=='source-tree': return store.source_tree(**args)
    if action=='source-read': return store.source_read(args['id'],args.get('offset',0),args.get('limit',12000))
    if action=='read': return store.read(args['id'],args.get('revision'))
    if action=='history': return store.history(args.get('id'),int(args.get('offset',0)),int(args.get('limit',30)))
    if action=='changeset':
        result=store.changeset(actor=actor,**args); store.flush_publication(); return result
    if action=='scan': return store.start_scan(actor=actor,**args)
    if action=='job': return store.job(args['id'])
    if action=='import-preview': return store.import_preview(args['paths'])
    if action=='import-read': return store.import_read(**args)
    if action=='import-apply':
        result=store.import_apply(actor=actor,**args); store.flush_publication(); return result
    if action=='restore':
        result=store.restore(actor=actor,identifier=args['id'],revision=args['revision'],expected=args['expected'],key=args['key'],task=args.get('task'),stage=args.get('stage')); store.flush_publication(); return result
    if action=='impact': return store.impact(**args)
    if action=='export': return store.export(**args)
    if action=='backup': return store.backup()
    if action=='restore-backup': return store.restore_backup(args['backup'])
    raise KnowledgeError('unknown_action','Unknown knowledge action',400)


def watch(registry, stopping):
    """Opt-in local refresh. No agent invocation or polling on normal projects."""
    due={}
    while not stopping.wait(5):
        try:
            from backup_session import active
            if active(registry) is not None:
                continue
            with registry.connect() as c:
                if not c.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_meta'").fetchone(): continue
                projects=[(r['project'],json.loads(r['policy'])) for r in c.execute('SELECT project,policy FROM knowledge_meta')]
            import time
            for project,policy in projects:
                KnowledgeStore(registry,project).flush_publication()
                if policy.get('updateMode')!='background' or time.monotonic()<due.get(project,0): continue
                due[project]=time.monotonic()+policy.get('intervalSeconds',60)
                KnowledgeStore(registry,project).start_scan(actor='local-background')
        except (OSError,ValueError):
            # A later pass may recover; individual jobs retain parse diagnostics.
            continue
