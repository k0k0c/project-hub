"""Durable connection/project mappings, independent of legacy access bindings."""
import json
from pathlib import Path
import time
import uuid
import hashlib

from agent_bindings import BindingError, Connections, fingerprint, text
from task_transfer import barrier


class ProjectBindings:
    def __init__(self, registry):
        self.registry = registry
        self.connections = Connections(registry)

    def setup(self):
        with self.registry.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS agent_project_bindings(
                id TEXT PRIMARY KEY,connection TEXT NOT NULL REFERENCES agent_connections(id),
                project TEXT NOT NULL REFERENCES spaces(id),scope TEXT NOT NULL,scope_key TEXT NOT NULL,
                status TEXT NOT NULL,revision INTEGER NOT NULL,rule_state TEXT NOT NULL,
                rule_path TEXT,client_revision INTEGER,created REAL NOT NULL,updated REAL NOT NULL,
                UNIQUE(connection,scope_key));
                CREATE TABLE IF NOT EXISTS agent_project_binding_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,binding TEXT NOT NULL,revision INTEGER NOT NULL,
                action TEXT NOT NULL,body TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS agent_project_sessions(
                connection TEXT NOT NULL,session TEXT NOT NULL,binding TEXT NOT NULL,
                project TEXT NOT NULL,revision INTEGER NOT NULL,
                PRIMARY KEY(connection,session,binding));
                CREATE TABLE IF NOT EXISTS agent_project_moves(
                id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,binding TEXT NOT NULL,body TEXT);''')
            if 'body' not in {row['name'] for row in c.execute('PRAGMA table_info(agent_project_moves)')}:
                c.execute('ALTER TABLE agent_project_moves ADD COLUMN body TEXT')

    @staticmethod
    def scope(value):
        if not isinstance(value, dict) or set(value)-{'root','nativeRef','kind'} or value.get('kind') not in ('workspace','project'):
            raise BindingError('invalid_project_scope','Describe an actual workspace/project with root and/or nativeRef')
        result = dict(kind=value['kind'])
        if value.get('root') is not None:
            root = Path(text(value['root'],'project root',2000))
            if not root.is_absolute() or not root.is_dir():
                raise BindingError('workspace_unavailable','Select an existing absolute project root',409)
            from project_workspaces import no_reparse, WorkspaceError
            try:
                no_reparse(root)
            except WorkspaceError as error:
                raise BindingError('workspace_unavailable','Project root contains links or reparse points',409) from error
            result['root'] = str(root.resolve())
        if value.get('nativeRef') is not None:
            result['nativeRef'] = text(value['nativeRef'],'native project reference',256)
        if not set(result)-{'kind'}:
            raise BindingError('invalid_project_scope','A root or native project reference is required')
        return result

    def available(self):
        with self.registry.connect() as c:
            return bool(c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_project_bindings'").fetchone())

    @staticmethod
    def public(row):
        value = dict(row)
        value['scope'] = json.loads(value['scope'])
        value['bindingId'] = value['id']
        value['ruleState'] = value.pop('rule_state')
        value['rulePath'] = value.pop('rule_path')
        value['clientRevision'] = value.pop('client_revision')
        value.pop('scope_key')
        return value

    def list(self, connection):
        if not self.available(): return []
        with self.registry.connect() as c:
            rows = c.execute('SELECT * FROM agent_project_bindings WHERE connection=? ORDER BY created,id',(connection,)).fetchall()
        return [self._with_pending(self.public(row)) for row in rows]

    def _with_pending(self, value):
        with self.registry.connect() as c:
            row=c.execute('''SELECT m.* FROM agent_project_moves m
                LEFT JOIN project_requests r ON r.id=m.id
                WHERE m.binding=? AND r.id IS NULL LIMIT 1''',(value['id'],)).fetchone()
            if row:
                body=json.loads(row['body']) if 'body' in row.keys() and row['body'] else None
                child=hashlib.sha256((row['id']+':workspace').encode()).hexdigest()[:32]
                committed=bool(c.execute('SELECT 1 FROM project_requests WHERE id=?',(child,)).fetchone())
                value['pendingRelocation']=dict(requestId=row['id'],recoverable=body is not None,
                    workspaceCommitted=committed,arguments=body.get('arguments') if body else None)
        return value

    def read(self, connection, identifier):
        identifier = text(identifier,'project binding ID')
        if not self.available():
            raise BindingError('project_binding_missing','Project binding is unavailable',404)
        with self.registry.connect() as c:
            row = c.execute('SELECT * FROM agent_project_bindings WHERE id=? AND connection=?',(identifier,connection)).fetchone()
        if row is None:
            raise BindingError('project_binding_missing','Project binding is unavailable for this connection',404)
        return self._with_pending(self.public(row))

    def history(self, connection, identifier):
        self.read(connection,identifier)
        with self.registry.connect() as c:
            rows = c.execute('SELECT * FROM agent_project_binding_events WHERE binding=? ORDER BY id DESC LIMIT 100',(identifier,)).fetchall()
        return [dict(row,body=json.loads(row['body'])) for row in rows]

    def ensure_ready(self, connection, identifier):
        if self.read(connection,identifier).get('pendingRelocation'):
            raise BindingError('project_relocation_pending','Resume the original relocation request before using or changing this binding',409)

    def resume(self, connection, arguments):
        if set(arguments)!={'bindingId','requestId'}:
            raise BindingError('invalid_project_binding','Resume requires bindingId and the original requestId')
        with barrier(self.registry):
            self._active_connection(connection)
            self.setup()
            self.read(connection,arguments['bindingId'])
            with self.registry.connect() as c:
                move=c.execute('SELECT * FROM agent_project_moves WHERE id=? AND binding=?',
                               (arguments['requestId'],arguments['bindingId'])).fetchone()
                if move is None or not move['body']:
                    raise BindingError('project_relocation_unrecoverable','The original relocation arguments are unavailable; preserve the reservation for reconciliation',409)
                payload=json.loads(move['body'])
                if (fingerprint(payload)!=move['request_hash'] or payload.get('connection')!=connection or
                    payload.get('action')!='project-binding.relocate' or
                    payload.get('arguments',{}).get('bindingId')!=arguments['bindingId']):
                    raise BindingError('project_relocation_unrecoverable','Preserve the inconsistent relocation receipt for reconciliation',409)
                _, previous=self.registry._request(c,arguments['requestId'],payload)
            if previous is not None:return previous
            return self.execute(connection,dict(payload['arguments'],action='relocate'))

    def _active_connection(self, connection):
        from connection_capabilities import Profiles
        Profiles(self.registry).binding(connection)
        with self.registry.connect() as c:
            if not c.execute('SELECT 1 FROM agent_connections WHERE id=?',(connection,)).fetchone():
                raise BindingError('global_connection_required','Legacy scoped connections cannot be rebound',409)

    def execute(self, connection, arguments):
        args = dict(arguments)
        action = args.pop('action',None)
        if action=='resume':return self.resume(connection,args)
        if action=='list' and not args: return dict(items=self.list(connection))
        if action in ('read','history','workspaces') and set(args)=={'bindingId'}:
            value = self.read(connection,args['bindingId'])
            if action=='workspaces':
                from project_workspaces import Workspaces
                return dict(binding=value,workspaces=Workspaces(self.registry).catalog(value['project']))
            return dict(binding=value, **(dict(history=self.history(connection,args['bindingId'])) if action=='history' else {}))
        fields = {'resolve':{'scope','project','name','requestId'},'create':{'scope','project','name','requestId'},
            'update':{'bindingId','scope','project','expectedRevision','requestId'},
            'verify':{'bindingId','expectedRevision','requestId','rulePath','status'},
            'relocate':{'bindingId','scope','expectedRevision','expectedProjectRevision','workspaceId','requestId'},
            'repair':{'bindingId','expectedRevision','requestId'},'unbind':{'bindingId','expectedRevision','requestId'}}
        if action not in fields or set(args)-fields[action] or 'requestId' not in args:
            raise BindingError('invalid_project_binding','Use a documented binding operation and requestId')
        self._active_connection(connection)
        scope = self.scope(args['scope']) if 'scope' in args else None
        payload = dict(action='project-binding.'+action,connection=connection,arguments=args)
        with barrier(self.registry):
            self._active_connection(connection)
            self.setup()
            if action=='relocate':
                # The workspace's own durable receipt repairs an interruption
                # before the binding receipt; never perform this nested in the
                # binding's SQLite transaction.
                current=self.read(connection,args.get('bindingId'))
                with self.registry.connect() as existing:
                    move_proof, replay=self.registry._request(existing,args['requestId'],payload)
                    pending=existing.execute('SELECT * FROM agent_project_moves WHERE id=?',(args['requestId'],)).fetchone()
                if replay is not None:return replay
                if pending and (pending['request_hash']!=move_proof or pending['binding']!=current['id']):
                    raise BindingError('project_binding_conflict','Relocation requestId was reused with different changes',409)
                if (type(args.get('expectedRevision')) is not int or args['expectedRevision']!=current['revision'] or
                    type(args.get('expectedProjectRevision')) is not int or current['status']!='active' or scope is None or 'root' not in scope):
                    raise BindingError('project_binding_conflict','Relocation requires the current active binding and new scope root',409)
                from project_workspaces import Workspaces, WorkspaceError
                from project_registry import ProjectRevisionConflict
                child=hashlib.sha256((args['requestId']+':workspace').encode()).hexdigest()[:32]
                try:
                    if not pending:
                        self.ensure_ready(connection,current['id'])
                        catalog=Workspaces(self.registry).catalog(current['project'])
                        selected=next((item for item in catalog['items'] if item['id']==args.get('workspaceId')),None)
                        if not selected or selected['descriptor'].get('root')!=current['scope'].get('root'):
                            raise BindingError('project_scope_mismatch','Relocate the registered workspace belonging to this binding',409)
                        with self.registry.connect() as reservation:
                            reservation.execute('INSERT INTO agent_project_moves(id,request_hash,binding,body) VALUES(?,?,?,?)',
                                                (args['requestId'],move_proof,current['id'],json.dumps(payload)))
                            reservation.commit()
                    Workspaces(self.registry).change(current['project'],'relocate',expected=args.get('expectedProjectRevision'),
                        request_id=child,workspace=args.get('workspaceId'),root=scope['root'])
                except (WorkspaceError,ProjectRevisionConflict) as error:
                    # A rejected workspace transaction made no change. Release
                    # its reservation so refreshed edits can use a new request.
                    # Keep it if a durable child receipt needs parent recovery.
                    with self.registry.connect() as reservation:
                        if not reservation.execute('SELECT 1 FROM project_requests WHERE id=?',(child,)).fetchone():
                            reservation.execute('DELETE FROM agent_project_moves WHERE id=?',(args['requestId'],))
                    raise BindingError('workspace_relocation_conflict','Refresh registered workspaces and project revision before relocating',409) from error
            # Reserve the SQLite writer across discovery and creation so concurrent
            # resolve requests cannot create two projects for the same scope.
            with self.registry.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                proof, old = self.registry._request(c,args['requestId'],payload)
                if old is not None:
                    c.rollback()
                    if old.get('projectCreated'): self.registry.base_store(old['binding']['project'])
                    return old
                identifier = args.get('bindingId')
                row = c.execute('SELECT * FROM agent_project_bindings WHERE id=? AND connection=?',(identifier,connection)).fetchone() if identifier else None
                if identifier and row is None:
                    raise BindingError('project_binding_missing','Unknown project binding',404)
                if action in ('resolve','create'):
                    if scope is None or identifier is not None:
                        raise BindingError('invalid_project_scope','Resolve/create requires a scope, without bindingId')
                    row = c.execute('SELECT * FROM agent_project_bindings WHERE connection=? AND scope_key=?',(connection,fingerprint(scope))).fetchone()
                    if row is not None:
                        self.ensure_ready(connection,row['id'])
                        if args.get('project') and args['project']!=row['project']:
                            raise BindingError('project_binding_conflict','Use revision-checked rebind to change this scope',409)
                        result = dict(binding=self.public(row),created=False,deliberatelyUnbound=row['status']=='unbound')
                        c.execute('INSERT INTO project_requests VALUES(?,?,?)',(args['requestId'],proof,json.dumps(result)))
                        c.commit()
                        return result
                    project = args.get('project')
                    root = scope.get('root')
                    # An opaque native reference can recover an existing mapping,
                    # but a changed root is an explicit revision-checked move.
                    if scope.get('nativeRef'):
                        matches = [item for item in self.list(connection) if item['scope'].get('nativeRef')==scope['nativeRef']]
                        if matches:
                            raise BindingError('project_scope_changed','Native project already has a binding; update its scope by revision',409)
                    if project is None and root:
                        candidates = [p for p in self.connections.projects(dict(scope='global'))
                                      if any(Path(root)==Path(r).resolve() or Path(root).is_relative_to(Path(r).resolve()) for r in p['roots'])]
                        if len(candidates)>1:
                            raise BindingError('project_ambiguous','Several Hub projects contain this root; select the canonical project ID',409)
                        if candidates: project=candidates[0]['id']
                    project_created = False
                    if project is None:
                        if not root:
                            raise BindingError('project_required','An opaque native reference needs an explicit Hub project ID',409)
                        # Equivalent to Registry.create, in this same transaction.
                        # Initialize baseline only after committing the receipt.
                        project = uuid.uuid4().hex
                        name = self.registry._name(args.get('name') or Path(root).name)
                        c.execute('INSERT INTO spaces(id,codex_id,name,roots,present,updated,ownership) VALUES(?,NULL,?,?,1,?,\'hub\')',
                                  (project,name,json.dumps([root]),time.time()))
                        c.execute('INSERT INTO project_workspaces VALUES(?,?,?,?,1,1,?)',
                                  (uuid.uuid4().hex,project,'local',json.dumps(dict(root=root)),time.time()))
                        project_created = True
                    else:
                        selected = self.connections.project(project)
                        if root: self.connections.workspace(selected,root,registry=self.registry)
                    identifier = uuid.uuid4().hex
                    now = time.time()
                    c.execute('INSERT INTO agent_project_bindings VALUES(?,?,?,?,?,\'active\',1,\'needs-repair\',NULL,NULL,?,?)',
                              (identifier,connection,project,json.dumps(scope),fingerprint(scope),now,now))
                    result = dict(created=True,projectCreated=project_created)
                else:
                    if row is None or type(args.get('expectedRevision')) is not int or args['expectedRevision']!=row['revision']:
                        raise BindingError('project_binding_conflict','Refresh the binding and use its current revision',409)
                    if action!='relocate': self.ensure_ready(connection,row['id'])
                    scope = scope or json.loads(row['scope'])
                    project = args.get('project',row['project'])
                    selected = self.connections.project(project) if action!='unbind' else None
                    if scope.get('root') and selected: self.connections.workspace(selected,scope['root'],registry=self.registry)
                    if action=='verify':
                        if args.get('status') not in ('saved','missing','manual'):
                            raise BindingError('invalid_project_binding','Report saved, missing or manual native rule')
                        path = text(args['rulePath'],'native rule path',2000) if args.get('rulePath') else row['rule_path']
                        c.execute('UPDATE agent_project_bindings SET rule_state=?,rule_path=?,client_revision=?,updated=? WHERE id=?',
                                  (args['status'],path,row['revision'] if args['status']=='saved' else None,time.time(),identifier))
                    else:
                        status = 'unbound' if action=='unbind' else 'active'
                        clash = c.execute('SELECT id FROM agent_project_bindings WHERE connection=? AND scope_key=? AND id!=?',
                                          (connection,fingerprint(scope),identifier)).fetchone()
                        if clash: raise BindingError('project_binding_conflict','Another binding owns this scope',409)
                        c.execute('UPDATE agent_project_bindings SET project=?,scope=?,scope_key=?,status=?,revision=revision+1,rule_state=\'needs-repair\',client_revision=NULL,updated=? WHERE id=?',
                                  (project,json.dumps(scope),fingerprint(scope),status,time.time(),identifier))
                    result = dict(created=False)
                value = self.public(c.execute('SELECT * FROM agent_project_bindings WHERE id=?',(identifier,)).fetchone())
                result['binding'] = value
                c.execute('INSERT INTO agent_project_binding_events(binding,revision,action,body,created) VALUES(?,?,?,?,?)',
                          (identifier,value['revision'],action,json.dumps(value),time.time()))
                c.execute('INSERT INTO project_requests VALUES(?,?,?)',(args['requestId'],proof,json.dumps(result)))
                c.commit()
            if result.get('projectCreated'): self.registry.base_store(result['binding']['project'])
            return result

    def validate(self, connection, session, identifier, revision, project, workspace, *, start=False, scope=None):
        self.ensure_ready(connection,identifier)
        value = self.read(connection,identifier)
        if value['status']!='active' or type(revision) is not int or value['revision']!=revision or value['project']!=project:
            raise BindingError('project_binding_conflict','Binding changed or was unbound; refresh before writing',409)
        if start and scope is None:
            raise BindingError('project_scope_required','At startup report the actual current native project scope',409)
        if scope is not None and self.scope(scope)!=value['scope']:
            raise BindingError('project_scope_mismatch','The current native project differs from this rule; resolve its own binding',409)
        if workspace and value['scope'].get('root') and not Path(workspace).resolve().is_relative_to(Path(value['scope']['root'])):
            raise BindingError('project_scope_mismatch','Workspace is outside the bound client project',409)
        with self.registry.connect() as c:
            row = c.execute('SELECT * FROM agent_project_sessions WHERE connection=? AND session=? AND binding=?',
                            (connection,session,identifier)).fetchone()
            if row and row['project']!=project:
                raise BindingError('session_project_changed','A rebound project requires a new conversation session',409)
            if not start and (row is None or row['revision']!=revision):
                raise BindingError('project_context_required','Read hub_context with the current binding before writing',409)
            if start:
                c.execute('INSERT INTO agent_project_sessions VALUES(?,?,?,?,?) ON CONFLICT(connection,session,binding) DO UPDATE SET revision=excluded.revision',
                          (connection,session,identifier,project,revision))
        return value
