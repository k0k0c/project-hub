"""Read-only, optional Codex metadata adapter. No transcripts, inferred liveness or writes."""
import os
from pathlib import Path
import sqlite3
import threading
import time
import json
from contextlib import closing
from functools import cache

IDENTITY_FIELDS=('kind','parentSession','agentPath','agentNickname','agentRole')


def parse_source(source, session=None):
    if source in ('vscode','cli'):
        return dict(kind='agent',parentSession=None,agentPath=None,agentNickname=None,agentRole=None)
    try:
        raw=json.loads(source)
        if not isinstance(raw,dict) or set(raw)!={'subagent'}:return None
        if not isinstance(raw['subagent'],dict) or set(raw['subagent'])!={'thread_spawn'}:return None
        spawn=raw['subagent']['thread_spawn']
        if not isinstance(spawn,dict) or set(spawn)-{'parent_thread_id','depth','agent_path','agent_nickname','agent_role'}:return None
        parent=spawn['parent_thread_id']; depth=spawn['depth']
        if not isinstance(parent,str) or not parent.strip() or parent!=parent.strip() or len(parent)>150 or parent==session:return None
        if type(depth) is not int or not 1<=depth<=32:return None
        fields={k:spawn.get(v) for k,v in [('agentPath','agent_path'),('agentNickname','agent_nickname'),('agentRole','agent_role')]}
        if any(v is not None and (not isinstance(v,str) or not v.strip() or len(v)>300) for v in fields.values()):return None
        return dict(kind='subagent',parentSession=parent,**fields)
    except (ValueError,TypeError,KeyError):return None


def normalized_rows(rows):
    result={}
    for row in rows:
        identity=parse_source(row.get('source'),row['id'])
        if identity:result[row['id']]={**row,**identity}
    invalid=set()
    for sid in result:
        seen=set(); current=sid
        while current in result:
            if current in seen:
                invalid.update(seen);break
            seen.add(current)
            current=result[current]['parentSession']
            if len(seen)>33:
                invalid.update(seen);break
    return {sid:row for sid,row in result.items() if sid not in invalid}


def workspace_key(value):
    value = str(value).replace('/', '\\')
    if value.startswith('\\\\?\\'):
        value = value[4:]
    return value.rstrip('\\').casefold()


class SessionCatalog:
    def __init__(self, database=None, ttl=5):
        # Disposable server/benchmark observations have an explicit home; this
        # affects display discovery only, never verified agent identity.
        self.database = database or Path(os.environ.get('PROJECT_HUB_OBSERVATION_HOME',
            os.environ.get('CODEX_HOME', Path.home() / '.codex'))) / 'state_5.sqlite'
        self.ttl = ttl
        self.cache = {}
        self.lock = threading.Lock()
        self.resolution_cache = {}

    def describe(self, session):
        """Read host identity metadata only; no registration or inferred liveness."""
        try:
            with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.2)) as c:
                c.row_factory=sqlite3.Row
                rows=[dict(r) for r in c.execute('SELECT id,name,cwd,updated_at,archived,source FROM threads')]
            return dict(available=True,session=normalized_rows(rows).get(session))
        except (OSError,sqlite3.Error,ValueError):
            return dict(available=False,session=None)

    def read_project(self, registry, project_id, registered, active_counts, *, include_archived=False):
        """One project policy for discovery and registered sessions; never mutate history."""
        from project_resolution import resolve_project, assignment_for, HubError
        try:
            metadata=registry.catalog.read()
            assignment_for(metadata, '')  # Fail closed when project metadata is unavailable.
            projects=registry.list()['projects']
            signature=json.dumps([{k:p[k] for k in ('id','codex_id','roots','present')} for p in projects],sort_keys=True)
            with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.2)) as c:
                c.row_factory=sqlite3.Row
                rows=[dict(r) for r in c.execute("SELECT id,name,cwd,updated_at,archived,source FROM threads ORDER BY updated_at DESC,id")]
            by_id={r['id']:r for r in rows}
            identities=normalized_rows(rows)
            resolved={}
            from hub_core import git_common
            common_for = cache(git_common)
            def owner(sid,cwd):
                assignment=assignment_for(metadata,sid)
                if not isinstance(cwd,str) or not cwd.strip():
                    if assignment is not None:
                        matches=[p for p in projects if p.get('codex_id')==assignment and p.get('present')]
                        if len(matches)!=1:
                            raise HubError('project_unregistered','Assigned project is unavailable')
                        return matches[0]['id']
                    return None
                key=(assignment,workspace_key(cwd))
                if key not in resolved:
                    cache_key=(signature,)+key
                    with self.lock:
                        cached=self.resolution_cache.get(cache_key)
                    if cached and time.monotonic()-cached[0]<self.ttl:
                        resolved[key]=cached[1]
                        return cached[1]
                    match=resolve_project(projects,cwd,assignment,common_for=common_for)
                    resolved[key]=match[0]['id'] if match else None
                    with self.lock:
                        self.resolution_cache={k:v for k,v in self.resolution_cache.items() if time.monotonic()-v[0]<self.ttl}
                        self.resolution_cache[cache_key]=(time.monotonic(),resolved[key])
                return resolved[key]
            discovered=[]; selected=[]; excluded=0; archived=0
            closed={s['id'] for s in registered if s['state']=='closed'}
            for row in rows:
                if row['id'] not in identities or (not include_archived and (row['archived'] or row['id'] in closed)):continue
                try:pid=owner(row['id'],row['cwd'])
                except HubError:excluded+=1;continue
                if pid==project_id:discovered.append(identities[row['id']])
            for session in registered:
                sid=session['id']; row=by_id.get(sid)
                cwd=row['cwd'] if row else session.get('workspace')
                try:
                    pid=owner(sid,cwd)
                    # MCP actors need no local source folder. Keep their verified
                    # Hub association; host discovery must not fabricate a root.
                    if pid is None and (not isinstance(cwd,str) or not cwd.strip()):
                        recorded=session.get('project')
                        pid=recorded if any(p['id']==recorded for p in projects) else None
                except HubError:pid=None
                history=bool(row and row['archived']) or session['state']=='closed'
                retained=active_counts.get(sid,0)>0
                if pid==project_id and history:archived+=1
                if (pid==project_id and (include_archived or not history)) or retained:
                    identity={k:identities[sid][k] for k in IDENTITY_FIELDS} if sid in identities else {}
                    selected.append(dict(session,**identity,archived=bool(row and row['archived']),
                        currentProject=pid, historical=history or pid!=project_id))
            return dict(available=True,sessions=discovered[:5000],registered=selected,
                        truncated=len(discovered)>5000,archivedCount=archived,unresolvedCount=excluded)
        except (OSError,sqlite3.Error,ValueError,HubError):
            # The host catalog enriches discovery, not the Hub's durable history.
            # Unknown current native ownership must not hide imported records.
            selected=[dict(s,historical=True,currentProject=None) for s in registered
                      if active_counts.get(s['id'],0)>0 or
                      s.get('project')==project_id and (include_archived or s.get('state')!='closed')]
            return dict(available=False,sessions=[],registered=selected,truncated=False,
                        reason='Каталог Codex недоступен: показана сохранённая история Hub')

    def read(self, root, *, include_archived=False):
        key = (workspace_key(root), include_archived)
        with self.lock:
            cached = self.cache.get(key)
            if cached and time.monotonic() - cached[0] < self.ttl:
                return cached[1]
            try:
                connection = sqlite3.connect(self.database.resolve().as_uri() + '?mode=ro', uri=True, timeout=.2)
                try:
                    connection.row_factory = sqlite3.Row
                    columns = {r['name'] for r in connection.execute('PRAGMA table_info(threads)')}
                    if not {'id', 'cwd', 'updated_at', 'archived', 'name', 'source'} <= columns:
                        raise ValueError('Unsupported Codex metadata schema')
                    from project_resolution import resolve_project
                    candidates=[dict(id='standalone',codex_id='standalone',present=True,roots=[root])]
                    all_rows=[dict(r) for r in connection.execute('SELECT id,name,cwd,updated_at,archived,source FROM threads ORDER BY updated_at DESC,id')]
                    rows=[r for r in normalized_rows(all_rows).values() if (include_archived or not r['archived'])
                          and resolve_project(candidates,workspace_key(r['cwd']))]
                    result = dict(available=True, sessions=rows[:5000], truncated=len(rows) > 5000)
                finally:
                    connection.close()
            except (OSError, sqlite3.Error, ValueError):
                result = dict(available=False, sessions=[], truncated=False,
                              reason='Локальный каталог Codex недоступен или его формат изменился')
            self.cache[key] = (time.monotonic(), result)
            return result


CATALOG = SessionCatalog()


def merge_sessions(discovered, registered, names, hook_sessions, active_counts):
    """Discovery does not create participants, renew claims or assert a task is running."""
    rows = {row['id']: dict(id=row['id'], title=names.get(row['id']) or row.get('name'),
                         workspace=row['cwd'], state='unknown', seen=None, task=None,
                         integration='discovered', activeWork=0, updatedAt=row['updated_at'],
                         archived=bool(row.get('archived')), historical=bool(row.get('archived')),
                         **{k:row[k] for k in IDENTITY_FIELDS if k in row}) for row in discovered}
    for session in registered:
        sid = session['id']
        previous = rows.get(sid, {})
        rows[sid] = {**previous, **session, 'title': names.get(sid) or previous.get('title'),
                     'integration': 'hooks' if sid in hook_sessions else 'registered',
                     'activeWork': active_counts.get(sid, 0)}
    return sorted(rows.values(), key=lambda s: (s['integration'] != 'discovered', s.get('seen') or s.get('updatedAt', 0), s['id']), reverse=True)
