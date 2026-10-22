"""Bounded project memory and plan API; no model calls or transcript ingestion."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import time
from hub_core import HubError, compact, clean_text, bounded

_modules = {}
_snapshots = {}
_UNSET = object()

class Memory:
    def __init__(self, hub, session):
        self.hub, self.session = hub, session
        with hub.connect() as c:
            self.project = hub.session(c, session)['project']
            root = c.execute('SELECT root FROM projects WHERE id=?', (self.project,)).fetchone()[0]
            self.root = Path(root) if root is not None else None
        if hasattr(hub, 'store_factory'):
            self.store = hub.store_factory(self.project)
            return
        if self.root is None:
            raise HubError('workspace_required', 'Connect a code workspace or an independent project store')
        script = self.root / 'scripts/project_portal.py'
        key = (str(script), script.stat().st_mtime_ns)
        if key not in _modules:
            if str(script.parent) not in sys.path:
                sys.path.insert(0, str(script.parent))
            spec = importlib.util.spec_from_file_location('hub_portal_store', script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _modules.clear(); _modules[key] = module
        self.store = _modules[key].Store(self.root)

    def snapshot(self, task=None, *, events=True):
        if not events and task and hasattr(self.store, 'task_context'):
            state = self.store.task_context(task)
        elif not events and hasattr(self.store, 'memory_tasks'):
            state = self.store.memory_tasks()
        else:
            state = getattr(self.store, 'memory_snapshot', self.store.snapshot)()
        self.revision = state['revision']
        self.main_task = state.get('mainTask', dict(task=None, reason='none'))
        return state['tasks'], state['allEvents']

    def progress(self, task=None):
        """Small, demand-driven hint; never schedules a model or changes estimates."""
        tasks, _ = self.snapshot(task, events=False)
        chosen = [t for t in tasks if t['id'] == task] if task else [t for t in tasks if t['status'] == 'active']
        rows = []
        for t in chosen:
            p = t.get('progress', {})
            if task or p.get('active') or t['id'] == self.main_task.get('task'):
                rows.append(dict(task=t['id'], estimate={k:v for k,v in (t.get('estimate') or {}).items()
                                  if k in ('percentLow','percentHigh','hoursLow','hoursHigh','updatedAt')},
                                 reviewDue=p.get('reviewDue', False), reason=p.get('reason')))
        return dict(mainTask=self.main_task, tasks=bounded(rows[:5], 1800),
                    more=len(rows)>5, revision=self.revision,
                    next='When reviewDue, reassess at this checkpoint using hub_plan(estimate=..., expected=revision). No timer or separate model run.')

    def stage(self, task, stage):
        tasks, _ = self.snapshot(task, events=False)
        found = next((s for t in tasks if t['id']==task for s in t['stages'] if s['id']==stage), None)
        if not found:
            raise HubError('stage_missing', 'Create the agreed stage with hub_plan before beginning work')
        return found

    def read(self, query='', task='', ref='', offset=0, limit=6):
        query = clean_text(query, 'query', 200, False)
        if not isinstance(offset, int) or offset < 0:
            raise HubError('invalid_offset', 'Use a nonnegative cursor')
        limit = max(1, min(int(limit), 12))
        if ref.startswith(('source:', 'source-archive:', 'source-version:')):
            expected = ''
            if ref.startswith('source-version:'):
                parts = ref.split(':', 3)
                if len(parts) != 4 or parts[1] not in ('current', 'archive') or not re.fullmatch('[0-9a-f]{64}', parts[2]):
                    raise HubError('invalid_reference', 'Use the returned versionRef for version-pinned reads')
                _, mode, expected, path = parts
            else:
                prefix, path = ref.split(':', 1)
                mode = 'archive' if prefix == 'source-archive' else 'current'
            info = self.store.source_info(path, mode)
            if not info['available']:
                return dict(ref=ref, source=info, text='', next=None,
                            freshness=f'{mode.capitalize()} source unavailable; no substitute was read',
                            archiveRef='source-archive:'+path if info['archiveAvailable'] else None)
            if info.get('image'):
                from image_sources import read_image
                data, _ = read_image(Path(info['resolvedPath']), 'original')
                digest = hashlib.sha256(data).hexdigest()
                if expected and expected != digest:
                    raise HubError('source_changed', 'Source version changed; restart reading from offset 0')
                return dict(ref=ref, source=info, sha256=digest, next=None,
                            versionRef=f'source-version:{mode}:{digest}:{path}',
                            freshness='Image metadata; open the image viewer to inspect pixels')
            if info.get('kind') == 'artifact' and not info.get('textPreviewAvailable'):
                if expected and expected != info['sha256']:
                    raise HubError('source_changed', 'Artifact version changed')
                return dict(ref=ref, source=info, sha256=info['sha256'], next=None,
                            versionRef=f'source-version:{mode}:{info["sha256"]}:{path}',
                            freshness='Immutable artifact; download the original for unsupported previews')
            document = self.store.document(path, mode)
            text, info = document['text'], document['source']
            if expected and expected != info['sha256']:
                raise HubError('source_changed', 'Source version changed; restart reading from offset 0')
            return dict(ref=ref, text=text[offset:offset+4000], next=offset+4000 if offset+4000<len(text) else None,
                        sha256=info['sha256'], source=info,
                        versionRef=f'source-version:{mode}:{info["sha256"]}:{info.get("versionPath",path)}',
                        archiveRef='source-archive:'+path if info['archiveAvailable'] else None,
                        freshness='Immutable knowledge revision' if info.get('kind')=='knowledge' else 'Archived snapshot; not current file contents' if mode == 'archive' else 'Current working file contents; verify historical claims')
        tasks, events = self.snapshot()
        rows = []
        for t in tasks:
            rows.append(dict(ref='task:'+t['id'], task=t['id'], kind='task', title=t['title'], body=t, at=t.get('updatedAt')))
        for e in events:
            rows.append(dict(ref='event:'+str(e['seq']), task=e['taskId'], kind=e['kind'], title=e['title'], body=e, at=e['at']))
        with self.hub.connect() as c:
            for w in c.execute('SELECT * FROM work WHERE project=? ORDER BY updated', (self.project,)):
                w = dict(w); w['evidence'] = json.loads(w['evidence'])
                rows.append(dict(ref='work:'+w['id'], task=w['task'], kind='work.'+w['status'], title=w['title'], body=w, at=w['updated']))
        if ref:
            row = next((r for r in rows if r['ref']==ref and (not task or r['task']==task)), None)
            if not row: raise HubError('memory_missing', 'Reference is not present in this project')
            text = compact(row['body'])
            return dict(ref=ref, text=text[offset:offset+6000], next=offset+6000 if offset+6000<len(text) else None, at=row['at'], freshness='Historical record, not proof of current code behavior')
        terms, found = query.casefold().split(), []
        for r in reversed(rows):
            if task and r['task']!=task: continue
            text = compact(r['body'])
            if not all(term in text.casefold() for term in terms): continue
            pos = max(0,text.casefold().find(terms[0])-100) if terms else 0
            found.append(dict(ref=r['ref'],task=r['task'],kind=r['kind'],title=r['title'],at=r['at'],excerpt=text[pos:pos+650]))
        page = bounded(found[offset:offset+limit],6000)
        return dict(project=self.project,results=page,next=offset+len(page) if offset+len(page)<len(found) else None,journalRevision=getattr(self,'revision',len(events)),coverage='Recorded tasks, stages, decisions, findings, checks and work results; no code/transcript index',freshness='Inspect evidence and relevant code; missing records do not imply missing implementation')

    def plan(self, task, stage='', title='', remaining=None, status='planned', decision='', expected=None, estimate=None, primary=None, blocker=_UNSET):
        if blocker is not _UNSET and (not stage or decision or estimate is not None or primary is not None):
            raise HubError('invalid_plan', 'blocker requires a stage mutation; use hub_task_update for task blockers')
        tasks, events = self.snapshot(task, events=False)
        revision = getattr(self,'revision',len(events))
        t = next((t for t in tasks if t['id']==task),None)
        if not t: raise HubError('task_missing','Choose an existing task')
        if estimate is not None or primary is not None:
            if decision or remaining is not None or status != 'planned' or (stage and primary is not None):
                raise HubError('invalid_plan', 'Update estimate separately from decisions; primary belongs to tasks')
            if expected is None or isinstance(expected, bool) or not isinstance(expected, (str, int)):
                raise HubError('revision_required', 'Read hub_plan(task), then pass its revision as expected')
            patch = {}
            if primary is not None:
                if not isinstance(primary, bool): raise HubError('invalid_primary', 'primary must be true or false')
                if primary and t['status'] in ('done', 'cancelled'):
                    raise HubError('task_closed', 'A completed or cancelled task cannot be primary')
                patch['primary'] = dict(selected=primary, project=self.project)
            if estimate is not None:
                fields = {'percentLow','percentHigh','hoursLow','hoursHigh','confidence','note'}
                if not isinstance(estimate, dict) or set(estimate)-fields or not {'percentLow','percentHigh','confidence','note'} <= set(estimate):
                    raise HubError('invalid_estimate', 'Supply percentLow/percentHigh, confidence, note; remaining hoursLow/hoursHigh are optional as a pair')
                for low, high, maximum in [('percentLow','percentHigh',100), ('hoursLow','hoursHigh',math.inf)]:
                    if low in estimate or high in estimate:
                        a, b = estimate.get(low), estimate.get(high)
                        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (a,b)) or not 0 <= a <= b <= maximum:
                            raise HubError('invalid_estimate', 'Use finite ordered ranges: 0–100 percent and nonnegative remaining hours')
                patch['estimate'] = {k:v for k,v in estimate.items() if k not in ('confidence','note')}
                patch['estimate'].update(confidence=clean_text(estimate['confidence'],'confidence',160),
                                         note=clean_text(estimate['note'],'note',800), updatedBy=self.session)
            if stage and not any(item['id'] == stage for item in t['stages']):
                raise HubError('stage_missing', 'Estimate an existing stage')
            payload = dict(taskId=task, kind='stage.updated' if stage else 'task.updated',
                           title=title or 'Оценка и основная задача: '+t['title'], patch=patch)
            if stage:
                payload['stageId'] = stage
            payload['id'] = 'progress-'+hashlib.sha256(compact([self.session,payload,expected]).encode()).hexdigest()[:24]
            self.store.record(payload, expected_revision=expected)
            hint = self.progress(task)
            return dict(task=task, revision=hint['revision'], mainTask=hint['mainTask'], progressHint=hint)
        if not stage and not decision:
            if len(compact(t))>7000:
                return dict(task=task,title=t['title'],estimate=t.get('estimate'),progress=t.get('progress'),mainTask=self.main_task,
                            revision=revision,stages=[dict(id=s['id'],title=s['title'],status=s['status']) for s in t['stages']][:30],more=True,ref='task:'+task)
            return dict(task=t,revision=revision,mainTask=self.main_task)
        if decision:
            payload=dict(taskId=task,kind='decision',title=clean_text(title,'title',240),detail=clean_text(decision,'decision',1600))
        else:
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',stage): raise HubError('invalid_stage','Use a stable lowercase stage ID')
            old=next((s for s in t['stages'] if s['id']==stage),None)
            patch=dict(title=clean_text(title,'title',240),status=status)
            if blocker is not _UNSET:
                patch['blocker'] = blocker
            if remaining is not None:
                if not isinstance(remaining,list) or len(remaining)>20: raise HubError('invalid_plan','Use up to 20 substantial subpoints')
                patch['remaining']=[clean_text(v,'subpoint',400) for v in remaining]
            # A revision guards the write; it does not select create versus update.
            # Preserve the creation receipt on retries after the stage now exists.
            creation=dict(taskId=task,stageId=stage,kind='stage.created',title=title,patch=patch)
            creation_id='plan-'+hashlib.sha256(compact([self.session,creation,expected]).encode()).hexdigest()[:24]
            created_before=(self.store.event_exists(creation_id) if hasattr(self.store,'event_exists')
                            else any(event['id']==creation_id for event in events))
            kind='stage.created' if old is None or created_before or expected is None else 'stage.updated'
            payload=dict(taskId=task,stageId=stage,kind=kind,title=title,patch=patch)
        payload['id']='plan-'+hashlib.sha256(compact([self.session,payload,expected]).encode()).hexdigest()[:24]
        e=self.store.record(payload,expected_revision=expected)
        self.snapshot(task, events=False)
        return dict(task=task,stage=stage or None,revision=getattr(self,'revision',e['seq']))

    def deliver_activation(self, store, payload):
        """Revalidate a durable signal at delivery; old signals cannot reopen work."""
        with self.hub.connect() as c:
            from work_scope import stages_for
            selected = stages_for(c, payload['workId'])
            row = c.execute("""SELECT w.status,w.task,w.project,w.revision,s.project AS session_project,s.state,s.seen,ws.stage
                FROM work w JOIN sessions s ON s.id=w.session
                JOIN work_stages ws ON ws.work=w.id WHERE w.id=?""",
                (payload['workId'],)).fetchone()
        if (not row or row['status'] != 'active' or row['state'] != 'active'
                or row['task'] != payload['taskId'] or payload['stageId'] not in selected
                or row['project'] != row['session_project']
                or row['project'] != getattr(store, 'project_id', self.project) or row['revision'] != payload['signal']
                or not 0 <= time.time() - row['seen'] <= 15 * 60):
            return
        state = getattr(store, 'memory_snapshot', store.snapshot)()
        task = next((t for t in state['tasks'] if t['id'] == payload['taskId']), None)
        if task is None or task['status'] in ('done', 'cancelled'):
            return
        stage = next((s for s in task['stages'] if s['id'] == payload['stageId']), None)
        if stage is None or stage['status'] not in ('planned', 'active'):
            return
        if stage['status'] == 'planned':
            store.record(dict(id=payload['id']+'-stage', taskId=task['id'], stageId=stage['id'],
                kind='stage.updated', title='Work started: '+stage['title'], patch=dict(status='active')),
                expected_revision=state['revision'])
            state = getattr(store, 'memory_snapshot', store.snapshot)()
        if task['status'] == 'planned':
            store.record(dict(id=payload['id']+'-task', taskId=task['id'], kind='task.updated',
                title='Work started: '+task['title'], patch=dict(status='active')),
                expected_revision=state['revision'])

    def flush_reports(self, work=None):
        report_scope = None
        if work is not None:
            prefixes = ('work-report-' + work + '-', 'stage-report-' + work + '-',
                        'work-activation-' + work + '-')
            report_scope = tuple(value for prefix in prefixes for value in (len(prefix), prefix))
        where = ' OR '.join(['substr(id,1,?)=?'] * 3)
        with self.hub.connect() as c:
            if report_scope is not None:
                # Preserve this work's publication order after an earlier failed delivery.
                pending=c.execute('SELECT id,project,payload FROM plan_outbox WHERE ' + where + ' ORDER BY rowid LIMIT 20', report_scope).fetchall()
            elif getattr(self.hub,'store_factory',None):
                pending=c.execute('SELECT id,project,payload FROM plan_outbox ORDER BY rowid LIMIT 20').fetchall()
            else:
                pending=c.execute('SELECT id,project,payload FROM plan_outbox WHERE project=? ORDER BY rowid LIMIT 20',(self.project,)).fetchall()
        for row in pending:
            store=self.hub.store_factory(row['project']) if getattr(self.hub,'store_factory',None) else self.store
            payload = json.loads(row['payload'])
            if payload.get('activation') is True:
                self.deliver_activation(store, payload)
            else:
                store.record(payload)
            with self.hub.connect() as c: c.execute('DELETE FROM plan_outbox WHERE id=?',(row['id'],))
        if report_scope is not None:
            with self.hub.connect() as c:
                return not c.execute('SELECT 1 FROM plan_outbox WHERE ' + where + ' LIMIT 1', report_scope).fetchone()
