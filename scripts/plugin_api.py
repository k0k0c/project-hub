"""Server-owned MCP execution, serialized with ownership changes."""
import json
import hashlib
from copy import deepcopy
from functools import cache
from pathlib import Path
import re
import sys
import sqlite3

PLUGIN = Path(__file__).resolve().parents[1]/'tools/project-portal/plugins/project-hub/scripts'
if str(PLUGIN) not in sys.path: sys.path.insert(0,str(PLUGIN))
from hub_core import Hub, HubError, canonical, git_common, overlaps, workspace_root, hook_actor
from hub_plugin import Mcp, hook
from task_transfer import barrier
from project_settings import SettingsError
from git_changesets import ChangesetError
from git_integration import GitIntegrationError


class ServerHub(Hub):
    def verified_read_binding(self, session, cwd):
        """Revalidate an existing binding without a task-journal writer lock.

        Pure reads do not create bindings or reconcile a changed assignment.
        Those cases fall back to the normal serialized lifecycle path.
        """
        from project_resolution import resolve_project
        selected = resolve_project(self.registry.list()['projects'], cwd, self.assigned_project)
        if selected is None or self.assigned_project != self.registry.catalog.assigned_project(session):
            return False
        project, _ = selected
        with self.connect() as c:
            row = c.execute('SELECT project,workspace FROM sessions WHERE id=?', (session,)).fetchone()
            root = c.execute('SELECT root,git_common FROM projects WHERE id=?', (project['id'],)).fetchone()
            binding = row is not None and c.execute('SELECT 1 FROM workspace_bindings WHERE project=? AND root=?',
                                                    (project['id'],row['workspace'])).fetchone()
        return (row is not None and row['project'] == project['id'] and root is not None
                and root[0] == canonical(Path(project['roots'][0]).resolve())
                and root[1] == self._git_common(Path(project['roots'][0]).resolve()) and binding
                and Path(cwd).resolve().is_relative_to(Path(row['workspace']).resolve()))

    def git_boundary_store(self, project):
        # Reuse the project's existing CAS and backup, including after transfer.
        from artifact_store import cas
        return cas(self.registry.store(project))

    def freeze_git_boundary(self, work):
        from git_integration import decode_snapshot, encode_snapshot
        from git_changesets import capture, canonical, validate_boundary
        snapshot = decode_snapshot(work['git_snapshot'])
        reference = snapshot.get('contentBoundary')
        if not reference or snapshot.get('contentAfter') or snapshot.get('contentAfterError'):
            return work['git_snapshot']
        try:
            store = self.git_boundary_store(reference['project'])
            before = validate_boundary(json.loads(store.read_blob(reference['blob'])))
            after = capture(snapshot['root'], before['scope'], store.blob)
            if any(before[key] != after[key] for key in ('repositoryId', 'worktreeId', 'scope')):
                raise ValueError('Completed content belongs to another worktree')
            snapshot['contentAfter'] = dict(schemaVersion=1, project=reference['project'], blob=store.blob(canonical(after)))
        except (OSError, ValueError, KeyError) as error:
            snapshot['contentAfterError'] = dict(reason=str(error), reasonCode=getattr(error, 'reason_code', 'boundary_capture_failed'), layer='changeset')
        return encode_snapshot(snapshot)

    @staticmethod
    def root_prefix(root):
        return '@roots/' + hashlib.sha256(canonical(root).encode()).hexdigest()[:16] + '/'

    def __init__(self, registry, session=None, *, resolve_host=True):
        registry.require_ready()
        super().__init__(registry.home/'coordination')
        self.registry=registry
        self.new_schema_version = registry.schema_version
        self.connection_factory=registry.coordination_connect
        if resolve_host and session and not registry.catalog.read()['available']:
            raise HubError('project_metadata_unavailable','Codex project metadata unavailable; retry before changing session ownership')
        self.assigned_project=registry.catalog.assigned_project(session) if resolve_host and session else None
        self.store_factory=registry.store
        self._locations = {}
        # One tool execution verifies each canonical Git boundary once. A new
        # API call creates a fresh verifier; no cross-request identity TTL.
        self._git_common = cache(git_common)
        # Schema setup is process initialization, not work for every tool call.
        # A replaced database or an unsupported version still revalidates it.
        with registry.hub_schema_lock:
            identity = (self.db.stat().st_dev, self.db.stat().st_ino) if self.db.exists() else None
            ready = identity is not None and getattr(registry, '_hub_schema_identity', None) == identity
            if ready:
                with self.connect() as c:
                    row = c.execute('SELECT version FROM meta').fetchone()
                    if row is None or row[0] not in (1, 2):
                        raise HubError('schema_version', 'Unsupported coordination database; not modified')
            else:
                self.setup()
                with self.transaction() as c:
                    c.execute('CREATE TABLE IF NOT EXISTS workspace_bindings(project TEXT,root TEXT,PRIMARY KEY(project,root))')
                info = self.db.stat()
                registry._hub_schema_identity = (info.st_dev, info.st_ino)

    def locate(self, cwd):
        from project_resolution import resolve_project
        projects = self.registry.list()['projects']
        key = json.dumps([canonical(cwd), self.assigned_project, projects], sort_keys=True)
        if key in self._locations:
            return deepcopy(self._locations[key])
        selected=resolve_project(projects,cwd,self.assigned_project)
        if selected is None:return None
        project,matched_root=selected
        resolved=Path(cwd).resolve()
        # Keep the project's authoritative root stable across aliases and worktrees.
        root=Path(project['roots'][0]).resolve()
        row=dict(id=project['id'],root=canonical(root),git_common=self._git_common(root))
        inside=resolved==matched_root or matched_root in resolved.parents
        same_git=not inside and self._git_common(resolved) and self._git_common(resolved)==self._git_common(matched_root)
        effective_root=workspace_root(cwd,dict(row,root=canonical(matched_root))) if inside or same_git else canonical(root)
        with self.connect() as c:
            saved = c.execute('SELECT root,git_common FROM projects WHERE id=?',(row['id'],)).fetchone()
            bound = c.execute('SELECT 1 FROM workspace_bindings WHERE project=? AND root=?',
                              (row['id'],effective_root)).fetchone()
        if saved is None or tuple(saved) != (row['root'],row['git_common']) or not bound:
            if getattr(self,'defer_outbox_for_read',False):
                raise HubError('project_metadata_changed','Workspace binding changed during plan read; retry')
            with self.transaction() as c:
                c.execute('INSERT INTO projects VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET root=excluded.root,git_common=excluded.git_common',
                          (row['id'],row['root'],row['git_common']))
                c.execute('INSERT OR IGNORE INTO workspace_bindings VALUES (?,?)',(row['id'],effective_root))
        guard_roots=[(str(root),'')]
        guard_roots += [(str(Path(r).resolve()),self.root_prefix(r)) for r in project['roots'][1:]]
        if same_git:
            prefix='' if matched_root==root else self.root_prefix(matched_root)
            guard_roots.append((effective_root,prefix))
        # Prefer the most specific attached root when folders are nested.
        guard_roots.sort(key=lambda item:len(Path(item[0]).parts),reverse=True)
        result = dict(row,workspace_root=effective_root,guard_roots=guard_roots)
        self._locations[key] = deepcopy(result)
        return result

    def context(self, session, *args, **kwargs):
        settings = self.settings(session)
        result=super().context(session,*args,**kwargs)
        if not args or args[0] is None:
            result['team']=self.agent_context(session)
        with self.connect() as c:
            row=self.session(c,session)
            workspace=row['workspace']
        project=self.locate(workspace)
        if project:
            result['workspace']=dict(primaryRoot=project['root'],workspaceRoot=workspace,
                roots=[dict(path=r,claimPrefix=p) for r,p in project['guard_roots']])
        # Context links use ownership metadata, not task bodies or journal
        # events. Reconcile indexes once, then borrow one SQL metadata snapshot.
        self.registry.read_models.ensure_all()
        with self.registry.connect() as c:
            c.execute('BEGIN')
            owners=[dict(r) for r in c.execute('SELECT * FROM task_owners ORDER BY rowid')]
            transfers=[dict(r) for r in c.execute('SELECT rowid AS seq,* FROM task_transfers ORDER BY rowid')]
            c.commit()
        with self.connect() as c:
            links=c.execute('SELECT DISTINCT project,task FROM work WHERE session=? LIMIT 51',(session,)).fetchall()
            transitions=c.execute("SELECT body FROM events WHERE session=? AND project=? AND kind='session.project_changed' ORDER BY seq DESC LIMIT 5",(session,result.get('project',row['project']))).fetchall()
        result['taskLinks']=[dict(workProject=p,task=t,currentTaskProjects=sorted({o['owner'] for o in owners
            if o['task']==t and (p in (o['origin'],o['owner']) or any(x['uid']==o['uid'] and p in (x['source'],x['target']) for x in transfers))})) for p,t in links[:50]]
        result['taskLinksMore']=len(links)>50
        result['projectChanges']=[json.loads(r[0]) for r in transitions]
        result['projectSettings'] = settings
        for item in result.get('own',[]):
            with self.connect() as c:
                w=c.execute('SELECT project FROM work WHERE id=?',(item['id'],)).fetchone()
            item['project']=w[0]
            if w[0]!=row['project'] and item['status'] in ('active','waiting'):
                item['requiredAction']='Finish or cancel this work in its original project; its claims do not authorize edits in the new project'
        return result

    def conflicts(self, c, project, names, mode='write', own=None):
        result=super().conflicts(c,project,names,mode,own)
        seen={row['id'] for row in result}
        # Claims in different roots/projects can still designate the same file
        # (nested saved roots or canonical aliases). Compare their physical paths.
        with self.registry.connect() as registry_db:
            roots={r['id']:json.loads(r['roots']) for r in registry_db.execute('SELECT id,roots FROM spaces')}
        for binding in c.execute('SELECT project,root FROM workspace_bindings'):
            roots.setdefault(binding['project'],[]).append(binding['root'])
        # This snapshot belongs only to this conflict check. Repeated paths and
        # claims must not spawn Git for every pair; the next check reads afresh.
        common_for = cache(git_common)
        @cache
        def physical(pid, name):
            if name.startswith('resource:'):return []
            if name.startswith('@roots/'):
                return [canonical(Path(root)/name[len(self.root_prefix(root)):]).replace('\\','/')
                        for root in roots.get(pid,[]) if name.startswith(self.root_prefix(root))]
            candidates=roots.get(pid,[])
            if not candidates:return []
            primary=candidates[0]
            common=common_for(primary)
            candidates=[r for r in candidates if canonical(r)==canonical(primary) or (common and common_for(r)==common)]
            return [canonical(Path(root)/name).replace('\\','/') for root in candidates]
        requested=[p for name in names for p in physical(project,name)]
        for row in c.execute("""SELECT w.id,w.title,w.task,w.session,w.status,w.project,c.name,c.mode,
                s.seen AS ownerSeen,ws.stage FROM claims c JOIN work w ON w.id=c.work
                JOIN sessions s ON s.id=w.session LEFT JOIN work_stages ws ON ws.work=w.id
                WHERE w.status IN ('active','waiting')"""):
            if row['id']==own or row['id'] in seen or (mode=='read' and row['mode']=='read'):continue
            if any(overlaps(a,b) for a in requested for b in physical(row['project'],row['name'])):
                from work_scope import describe
                result.append(describe(c, dict(row)));seen.add(row['id'])
        return result

    def ensure_session(self, session, cwd):
        self.reconcile_session(session,cwd)
        result=super().ensure_session(session,cwd)
        # Use the catalog beside the configured project metadata. Isolated
        # registries must never read the user's production session database.
        catalog_path = getattr(self.registry.catalog, 'path', None)
        if catalog_path is None:
            return result
        from codex_session_catalog import SessionCatalog
        metadata=SessionCatalog(catalog_path.parent/'state_5.sqlite').describe(session)
        row=metadata.get('session') or {}
        if row.get('kind')=='subagent' and row.get('parentSession') and row['parentSession']!=session:
            with self.connect() as c:
                recorded = c.execute('SELECT 1 FROM session_agents WHERE session=?',(session,)).fetchone()
            if not recorded and not getattr(self,'defer_outbox_for_read',False):
                with self.transaction() as c:
                    # Relationships are advisory and enrolled by the lifecycle,
                    # never by an already verified pure plan read.
                    c.execute('INSERT OR IGNORE INTO session_agents VALUES (?,?,?,?,?)',
                        (session,row['parentSession'],row.get('agentPath'),row.get('agentNickname'),row.get('agentRole')))
        return result

    def settings(self, session, patch=None, expected=None, reset=None):
        from project_settings import read_settings, update_settings, SettingsError
        with self.connect() as c:
            project = self.session(c, session)['project']
        store = self.registry.base_store(project)
        try:
            if patch is not None and reset is not None:
                raise SettingsError('invalid_settings', 'Use patch OR reset with expected settings revision')
            if patch is None and reset is None and expected is None:
                return read_settings(store)
            return update_settings(store, patch, expected, actor=session, reset=reset)
        except SettingsError as error:
            raise HubError(error.code, str(error)) from error

    def checkpoint(self, session, task, expected, stage=None, commits=None, reason=None):
        from completion_policy import retry_checkpoint
        with self.connect() as c:
            project = self.session(c, session)['project']
        result = retry_checkpoint(self.registry, project, task, expected, stage, commits, reason, actor=session)
        return dict(checkpoint=result['checkpoint'], revision=result['revision'])

    def git_batch(self, session, **args):
        from completion_policy import checkpoint_batch, batch_details
        with self.connect() as c:
            current = self.session(c, session)
        action = args.pop('action', 'preview')
        if action == 'details':
            return batch_details(self.registry, current['project'], **args)
        return checkpoint_batch(self.registry, current['project'], actor=session,
                                root=current['workspace'], action=action, **args)

    def review(self, session, action, **args):
        from hub_project_review import summary, read_scope, page, publish_review, publish_estimates
        with self.connect() as c:
            project = self.session(c, session)['project']
        if action == 'summary':
            reference = args.pop('scopeRef', None)
            if reference:
                action_id = args.pop('actionId', None)
                with self.registry.connect() as c:
                    receipt = c.execute('SELECT thread_id,response FROM codex_chat_actions WHERE project=? AND action_id=?',
                                        (project, action_id)).fetchone()
                if not receipt or receipt['thread_id'] != session or json.loads(receipt['response']).get('scopeRef') != reference:
                    raise HubError('scope_unowned', 'Read only your own action scope')
                return page(read_scope(self.registry, project, reference, action_id), args.get('offset', 0))
            return summary(self.registry, project, **args)
        if action == 'propose':
            return publish_review(self.registry, project, session, args['actionId'], args['work'],
                                  args['expected'], args['proposals'])
        if action == 'estimate':
            return publish_estimates(self.registry, project, session, args['actionId'], args['work'],
                                     args['expected'], args['estimates'])
        raise HubError('invalid_review_action', 'Select summary, propose or estimate')

    def authorize_tool(self, session, name, args):
        """Enforce the latest explicit service intent without changing native permissions."""
        from hub_project_review import INTENTS, read_scope
        with self.registry.connect() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='codex_chat_actions'").fetchone():
                return
            action=c.execute('SELECT project,response FROM codex_chat_actions WHERE thread_id=? ORDER BY created DESC,action_id DESC LIMIT 1',
                             (session,)).fetchone()
        if not action:
            return
        response=json.loads(action['response'])
        if response.get('intent') not in INTENTS:
            return
        if name in ('hub_context','hub_memory','hub_migration_preview','hub_notice','hub_wait','hub_review'):
            return
        if name=='hub_plan' and set(args)<={'task','expected'}:
            return
        if name=='hub_settings' and not args:
            return
        if name=='hub_git_batch' and args.get('action') in ('preview','details'):
            return
        if name=='hub_knowledge' and (args.get('action') in ('context','search','source-tree','source-read','research-object','read','history','job','import-read','export') or
                (args.get('action')=='impact' and not args.get('args',{}).get('record'))):
            return
        frozen=read_scope(self.registry,action['project'],response['scopeRef'],response['actionId'])
        allowed={row['task']:set(row['stages']) for row in frozen['scope']['tasks']}
        if name=='hub_begin':
            stages=args.get('stages') if 'stages' in args else [args['stage']] if args.get('stage') else []
            if (args.get('mode')=='read' and args.get('phase') in ('planning','research','review') and
                    args.get('task') in allowed and isinstance(stages,list) and all(isinstance(stage,str) and
                    stage in allowed[args['task']] for stage in stages)):
                return
        if name=='hub_report' and not args.get('stage_status') and args.get('phase','review') in ('planning','research','review'):
            from work_scope import stages_for
            with self.connect() as c:
                work=c.execute('SELECT * FROM work WHERE id=? AND session=? AND project=?',
                               (args.get('work'),session,action['project'])).fetchone()
                if (work and work['task'] in allowed and work['phase'] in ('planning','research','review') and
                        set(stages_for(c,work['id']))<=allowed[work['task']] and not c.execute(
                        "SELECT 1 FROM claims WHERE work=? AND mode='write'",(work['id'],)).fetchone()):
                    return
        if name=='hub_check' and args.get('task') in allowed:
            return
        raise HubError('service_read_only','This explicit service action permits scoped read work, review proposals and requested estimate metadata only')

    def check(self, session, **args):
        from check_runs import ingest
        with self.connect() as c:
            project = self.session(c, session)['project']
        return ingest(self.registry, project, args)

    def reconcile_session(self, session, cwd):
        project=self.locate(cwd)
        if self.assigned_project != self.registry.catalog.assigned_project(session):
            raise HubError('project_metadata_changed','Codex assignment changed during request; retry')
        with self.connect() as c:
            old=c.execute('SELECT project FROM sessions WHERE id=?',(session,)).fetchone()
        if old is None or project and old[0] == project['id']:
            # An unchanged binding needs no SQLite writer reservation. Cold
            # session creation remains in ensure_session's lifecycle path.
            return
        with self.transaction() as c:
            old=c.execute('SELECT project FROM sessions WHERE id=?',(session,)).fetchone()
            if old and (not project or old[0]!=project['id']):
                if not project or not self.assigned_project:
                    raise HubError('session_project','Project changed without explicit Codex assignment; restore metadata before writing')
                retained=c.execute("SELECT id FROM work WHERE session=? AND status IN ('active','waiting')",(session,)).fetchall()
                change=dict(previousProject=old[0],currentProject=project['id'],retainedWork=[r[0] for r in retained[:20]],retainedWorkCount=len(retained),tasksMoved=False)
                c.execute('UPDATE sessions SET project=?,workspace=?,last_cursor=0 WHERE id=?',
                          (project['id'],workspace_root(cwd,project),session))
                for pid in (old[0],project['id']):
                    self.emit(c,pid,session,'session.project_changed',change)

    def report(self, session, **args):
        with self.connect() as c:
            current=self.session(c,session)['project']
            work=c.execute('SELECT project,session FROM work WHERE id=?',(args.get('work'),)).fetchone()
        if work and work['session']==session and work['project']!=current:
            if args.get('status','done') not in ('done','cancelled') or args.get('evidence'):
                raise HubError('work_project_mismatch','Work remains in its original project. Finish/cancel with its revision and no new file evidence, or restore the chat assignment.',workProject=work['project'],currentProject=current)
        return super().report(session,**args)

    def validate_report_evidence(self, evidence, project):
        pattern = re.compile(r'knowledge/(?:revision/[0-9]+/)?document/(?P<identifier>[\w:./-]{1,180})\Z')
        store = self.registry.store(project)
        filesystem = []
        for path in evidence:
            if path.startswith(('hub-artifact/', 'hub-source/')):
                try:
                    info = store.source_info(path)
                    if info.get('kind') == 'artifact' and info.get('available'):
                        continue
                except (OSError, ValueError) as error:
                    if path.startswith('hub-artifact/'):
                        raise HubError('invalid_evidence', 'Artifact evidence must reference a registered immutable source') from error
            if not path.startswith('knowledge/'):
                filesystem.append(path)
                continue
            match = pattern.fullmatch(path)
            if not match or any(part in ('', '.', '..') for part in match['identifier'].split('/')):
                raise HubError('invalid_evidence', 'Invalid knowledge document evidence path')
            try:
                info = store.source_info(path)
                if info.get('kind') != 'knowledge' or not info.get('available'):
                    raise ValueError('Knowledge document is unavailable')
            except (OSError, ValueError, KeyError) as error:
                raise HubError('invalid_evidence', 'Knowledge evidence must reference a registered document') from error
        super().validate_report_evidence(filesystem, project)

    def require_task_context(self, session, task):
        with self.connect() as c:
            project=self.session(c,session)['project']
        if self.registry.store(project).task_context(task)['tasks']:return
        locations=[p['id'] for p in self.registry.list()['projects'] if p['present'] and p['id']!=project
                   and task in {t['id'] for t in self.tasks(p['id'])}]
        if locations:
            raise HubError('task_project_mismatch','Task belongs to another project. Select that project for this operation or transfer the task explicitly; moving the chat does not move it.',currentProject=project,taskProjects=locations,task=task)

    def attach_image(self, session, task, path, expected, stage=None, label=None):
        from image_sources import image_info, read_image
        if not isinstance(path, str) or not path or not isinstance(expected, (int, str)):
            raise ValueError('Image attachment requires path and current revision')
        if label is not None and (not isinstance(label, str) or not label.strip() or len(label) > 240):
            raise ValueError('Image label must contain 1-240 characters')
        with self.connect() as c:
            project = self.session(c, session)['project']
        self.require_task_context(session, task)
        store = self.registry.store(project)
        state = store.snapshot()
        if state['revision'] != expected:
            raise ValueError('Task changed; refresh before writing')
        current = next((t for t in state['tasks'] if t['id'] == task), None)
        if current is None:
            raise ValueError('Unknown task')
        target = next((s for s in current['stages'] if s['id'] == stage), None) if stage else None
        if stage is not None and target is None:
            raise ValueError('Unknown stage')
        resolved = store.evidence_path(path) if path.startswith('hub-source/') else store.resolve_path(path)
        read_image(resolved, 'original')
        source = dict(path=path, label=label or resolved.name)
        sources = list(current.get('sources', []))
        if not any(s['path'] == path for s in sources):
            sources.append(source)
        patch = dict(sources=sources)
        event = dict(kind='task.updated', taskId=task, title='Image attached')
        previous = current
        if target is not None:
            evidence = list(target.get('evidence', []))
            if not any(s['path'] == path for s in evidence):
                evidence.append(source)
            patch = dict(evidence=evidence)
            event.update(kind='stage.updated', stageId=stage)
            previous = target
        if any(previous.get(key) != value for key, value in patch.items()):
            store.record(dict(event, patch=patch), expected_revision=expected)
        return dict(task=task, stage=stage, source=source, image=image_info(resolved), revision=store.snapshot()['revision'])

    def attach_artifact(self, session, task, path, expected, stage=None, label=None, roles=None, previous=None):
        from artifact_store import publish, resolve, ROLES, MAX_BYTES
        if not isinstance(path, str) or not path or not isinstance(expected, (int, str)):
            raise ValueError('Artifact attachment requires path and current revision')
        if label is not None and (not isinstance(label, str) or not label.strip() or len(label) > 240):
            raise ValueError('Artifact label must contain 1-240 characters')
        if roles is not None and (not isinstance(roles, list) or any(not isinstance(role, str) or role not in ROLES for role in roles)):
            raise ValueError('Invalid artifact roles')
        with self.connect() as c:
            project = self.session(c, session)['project']
        self.require_task_context(session, task)
        store = self.registry.store(project)
        state = store.snapshot()
        if state['revision'] != expected:
            raise ValueError('Task changed; refresh before writing')
        current = next((t for t in state['tasks'] if t['id'] == task), None)
        if current is None:
            raise ValueError('Unknown task')
        target = next((s for s in current['stages'] if s['id'] == stage), None) if stage else None
        if stage is not None and target is None:
            raise ValueError('Unknown stage')
        relative = path
        origin = store
        if path.startswith('hub-source/'):
            origin, relative = store.evidence_origin(path)
        if relative.startswith('hub-artifact/'):
            item, _ = resolve(origin, relative)
            if previous is not None or (roles is not None and sorted(set(roles)) != item['roles']):
                raise ValueError('Existing immutable artifact metadata cannot be replaced; publish a new version')
            source = dict(path=path, label=label or item['name'])
        else:
            resolved = origin.resolve_path(relative)
            if not resolved.is_file() or resolved.stat().st_size > MAX_BYTES:
                raise ValueError('Artifact must be an ordinary file of at most 20 MiB')
            content = resolved.read_bytes()
            result = publish(store, resolved.name, content, roles=roles, previous=previous,
                             provenance='project-source:' + path)
            if resolved.read_bytes() != content:
                raise ValueError('Source changed while capturing artifact')
            item, source = result['artifact'], dict(result['source'], label=label or resolved.name)
        field, owner = ('evidence', target) if target is not None else ('sources', current)
        sources = list(owner.get(field, []))
        if not any(source['path'] == row['path'] for row in sources):
            sources.append(source)
            event = dict(kind='stage.updated' if target is not None else 'task.updated', taskId=task,
                         title='Artifact attached', patch={field: sources})
            if target is not None:
                event['stageId'] = stage
            store.record(event, expected_revision=expected)
        return dict(task=task, stage=stage, source=source, artifact=item, revision=store.snapshot()['revision'])

    def tasks(self, project):
        store = self.store_factory(project)
        return (store.memory_tasks() if hasattr(store, 'memory_tasks') else store.memory_snapshot())['tasks']

    def knowledge(self, session, action, args=None):
        from knowledge_store import execute, KnowledgeError
        with self.connect() as c:
            project = self.session(c, session)['project']
        if isinstance(args, dict) and args.get('task'):
            self.require_task_context(session, args['task'])
        try:
            result=execute(self.registry, project, action, args, actor=session)
            if action=='import-preview':
                result=dict(id=result['id'],revision=result['revision'],createdAt=result['createdAt'],compact=True,
                            items=[dict(index=i,id=x['item']['id'],title=x['item']['title'],action=x['action'],
                                        format=x['item'].get('format','markdown'),missingAssets=len(x['item'].get('missingAssets',[])),missingLinks=len(x['item'].get('missingLinks',[])),externalResources=len(x['item'].get('externalResources',[])))
                                   for i,x in enumerate(result['items'])],
                            nextAction='import-read',readArgs=dict(identifier=result['id'],index=0,field='source',offset=0,limit=12000))
            elif action=='export':
                from urllib.parse import urlencode
                result=dict(schemaVersion=result['schemaVersion'],public=result['public'],compact=True,
                            itemsCount=len(result['items']),download='/api/v1/knowledge/download?'+urlencode(dict(project=project,action='export',public=str(result['public']).lower())))
            if len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>220000:
                raise KnowledgeError('response_too_large','Use bounded pages or the HTTP/CLI download for this knowledge response',400)
            return result
        except KnowledgeError as error:
            raise HubError(error.body['error'], str(error), **{k:v for k,v in error.body.items() if k not in ('error','message')}) from error


def compact_write_ack(tool, result):
    """Return write receipts without echoing the submitted check or event history."""
    if tool == 'hub_check' and isinstance(result, dict) and 'run' in result:
        fields = ('id', 'runId', 'task', 'taskId', 'stage', 'stageId', 'status',
                  'originProject', 'ownerProject', 'launchProject', 'at', 'correction')
        return dict(result, run={key: value for key, value in result['run'].items() if key in fields})
    if tool == 'hub_report' and isinstance(result, dict):
        fields = ('work', 'revision', 'status', 'planSync', 'message', 'stageCompletionDeferred',
                  'gitCheckpoint', 'gitCommit', 'progressHint')
        return {key: value for key, value in result.items() if key in fields}
    return result


def _notice_dependencies(hub, session):
    with hub.connect() as c:
        project=hub.session(c,session)['project']
    state=hub.registry.store(project).memory_tasks()
    return {task['id']:[link['target'] for link in task.get('links',[])
                        if link.get('type')=='blocked-by' and isinstance(link.get('target'),str)
                        and (link.get('project') or project)==project]
            for task in state.get('tasks',[])}


def call(registry, body):
    if (isinstance(body, dict) and body.get('tool') == 'hook'
            and isinstance(body.get('arguments'), dict)
            and body['arguments'].get('hook_event_name') in ('PreToolUse', 'PostToolUse')):
        raw = body['arguments']
        if raw.get('session_id') != body.get('session') or raw.get('cwd') != body.get('cwd'):
            return {}
        # Existing storage only: no catalog refresh, session reconciliation or barrier.
        try:
            if registry is not None:
                registry.require_ready()
            return hook(Hub(registry.home/'coordination'), raw)
        except Exception:
            return {}
    registry.require_ready()
    if (not isinstance(body,dict) or set(body) - {'cwd','session','tool','arguments','noticeAfter'} or
            not {'cwd','session','tool','arguments'} <= set(body)):
        raise ValueError('Invalid plugin request fields')
    notice_after=body.get('noticeAfter',0)
    if isinstance(notice_after,bool) or not isinstance(notice_after,int) or notice_after<0:
        raise ValueError('Invalid notice cursor')
    for key,limit in (('cwd',4096),('session',150),('tool',80)):
        if not isinstance(body[key],str) or not 0<len(body[key])<=limit:raise ValueError('Invalid '+key)
    if not Path(body['cwd']).is_absolute():raise ValueError('Absolute workspace required')
    if body['tool']=='hook':
        raw=body['arguments']
        if not isinstance(raw,dict) or raw.get('session_id')!=body['session'] or raw.get('cwd')!=body['cwd']:
            raise ValueError('Hook identity mismatch')
        raw=hook_actor(raw)
        body={**body,'session':raw['session_id'],'arguments':raw}
    # Never hold the ownership barrier during a long poll.
    if body['tool']=='hub_wait':
        if not isinstance(body['arguments'],dict):raise ValueError('Invalid arguments')
        if body['arguments'].get('seconds',0)!=0:raise ValueError('Use client-side polling for waits')
    if body['tool']=='hub_notice':
        from hub_notices import wait, setup
        args=body['arguments']
        if (not isinstance(args,dict) or set(args)-{'after','seconds'} or 'after' not in args or
                isinstance(args.get('seconds',0),bool) or not isinstance(args.get('seconds',0),int) or
                not 0<=args.get('seconds',0)<=45):
            raise HubError('invalid_arguments','Use after and optional seconds=0–45')
        # Verify identity/project under the barrier, release it before waiting.
        with barrier(registry):
            hub=ServerHub(registry,body['session'])
            hub.ensure_session(body['session'],body['cwd'])
            setup(hub)
            dependencies=_notice_dependencies(hub,body['session'])
        return wait(hub,body['session'],args['after'],args.get('seconds',0),dependencies=dependencies)
    from contextlib import nullcontext
    read_plan = body['tool'] == 'hub_plan' and isinstance(body['arguments'], dict) and set(body['arguments']) <= {'task','expected'}
    hub = ServerHub(registry, body['session']) if read_plan else None
    if hub is not None and hub.verified_read_binding(body['session'], body['cwd']):
        if body['arguments'].get('task'):
            hub.require_task_context(body['session'], body['arguments']['task'])
    else:
        with barrier(registry):
            hub=ServerHub(registry,body['session'])
            hub.reconcile_session(body['session'],body['cwd'])
            if body['tool']=='hook':
                return hook(hub,body['arguments'],remind=False)
            if body['tool'] in ('hub_begin','hub_plan') and isinstance(body['arguments'],dict) and body['arguments'].get('task'):
                hub.ensure_session(body['session'],body['cwd'])
                hub.require_task_context(body['session'],body['arguments']['task'])
    # Pure reads with a current registered binding never acquire a global writer
    # lock; cold identities and mutations retain the existing lifecycle path.
    if read_plan:
        with hub.connect() as c:
            pending = c.execute('SELECT 1 FROM plan_outbox LIMIT 1').fetchone()
        lifecycle_pending = next((hub.home / 'outbox').glob('*.json'), None)
        # Deliver already queued work through the serialized lifecycle. A new
        # item arriving after this check remains durable for the next call.
        read_plan = pending is None and lifecycle_pending is None
        hub.defer_outbox_for_read = read_plan
    with nullcontext() if read_plan else barrier(registry):
        try:
            result = Mcp(hub,body['cwd'],body['session']).call(body['tool'],body['arguments'])
            result=compact_write_ack(body['tool'],result)
            if body['tool'] in ('hub_context','hub_begin','hub_report') and isinstance(result,dict):
                try:
                    from hub_notices import wait,refresh_all
                    dependencies=_notice_dependencies(hub,body['session'])
                    if body['tool'] in ('hub_begin','hub_report'):
                        with hub.connect() as c:
                            project=hub.session(c,body['session'])['project']
                        refresh_all(hub,{project:dependencies},project=project)
                    result['parallelNotices']=wait(hub,body['session'],notice_after,0,
                                                  max_bytes=1500,dependencies=dependencies)
                except (OSError,ValueError,sqlite3.Error,HubError):
                    result['parallelNotices']=dict(unavailable=True,description='Advisory notices unavailable; continue work')
            return result
        except SettingsError as error:
            raise HubError(error.code, str(error)) from error
        except (ChangesetError, GitIntegrationError) as error:
            raise HubError(error.reason_code, str(error), reasonCode=error.reason_code, layer=error.layer,
                           operationId=getattr(error, 'operation_id', None)) from error
