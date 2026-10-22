"""Global local agent connections, with preserved legacy project credentials.

Invitation and connection secrets are owned Hub data. Public inventories never
return secrets. Exact retries return the original enrollment receipt.
"""
import hashlib
import json
from pathlib import Path
import secrets
import time
import uuid

from task_transfer import barrier


class BindingError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status
        self.body = dict(error=code, message=message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=True))


def text(value, name, limit=128):
    if not isinstance(value, str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value):
        raise BindingError('invalid_binding', f'{name} must be a nonempty printable string of at most {limit} characters')
    return value.strip()


class Connections:
    def __init__(self, registry):
        registry.require_ready()
        if registry.schema_version != 2:
            raise BindingError('upgrade_required', 'Upgrade an inactive copy before connecting independent agents', 409)
        self.registry = registry

    def setup(self):
        # Setup is an administrative write, never an incidental catalog read.
        with barrier(self.registry), self.registry.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS agent_invitations(
                    id TEXT PRIMARY KEY, project TEXT REFERENCES spaces(id), token_hash TEXT UNIQUE NOT NULL,
                    expires REAL NOT NULL, request_hash TEXT, response TEXT, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS agent_access(
                    binding TEXT PRIMARY KEY REFERENCES client_bindings(id), token_hash TEXT UNIQUE NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS agent_connections(
                    id TEXT PRIMARY KEY, client TEXT NOT NULL, external_id TEXT NOT NULL,
                    metadata TEXT NOT NULL, updated REAL NOT NULL, token_hash TEXT UNIQUE NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0, last_seen REAL,
                    UNIQUE(client,external_id));
            ''')
            columns = {row['name'] for row in c.execute('PRAGMA table_info(agent_invitations)')}
            if 'scope' not in columns:
                c.execute("ALTER TABLE agent_invitations ADD COLUMN scope TEXT NOT NULL DEFAULT 'legacy'")
                c.execute("UPDATE agent_invitations SET scope=CASE WHEN project IS NULL THEN 'new-project' ELSE 'project' END")
            if 'reconnect' not in columns:
                c.execute('ALTER TABLE agent_invitations ADD COLUMN reconnect TEXT')

    def project(self, identifier):
        with self.registry.connect() as c:
            row = c.execute('SELECT * FROM spaces WHERE id=?', (identifier,)).fetchone()
        if row is None or row['deleted'] or not row['present']:
            raise BindingError('project_unavailable', 'Select an available project', 409)
        return self.registry._project(row)

    def invite(self, project=None, *, request_id):
        if project is not None:
            self.project(project)
        self.setup()
        with barrier(self.registry), self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            proof, old = self.registry._request(c, request_id, dict(action='agent.invite', project=project))
            if old is not None:
                c.rollback()
                return old
            identifier, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
            expires = time.time() + 86400
            scope = 'global' if project is None else 'project'
            c.execute('INSERT INTO agent_invitations(id,project,token_hash,expires,scope) VALUES(?,?,?,?,?)',
                      (identifier,project,digest(token),expires,scope))
            result = dict(id=identifier, project=project, scope=scope, token=token, expires=expires)
            c.execute('INSERT INTO project_requests VALUES(?,?,?)', (request_id,proof,json.dumps(result)))
            c.commit()
            return result

    def reconnect(self, identifier, *, request_id):
        identifier = text(identifier, 'connection ID')
        self.setup()
        with barrier(self.registry), self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                proof, old = self.registry._request(c, request_id, dict(action='agent.reconnect', id=identifier))
                if old is not None:
                    c.rollback()
                    return old
                row = c.execute('SELECT id,client,external_id,NULL AS project FROM agent_connections WHERE id=?', (identifier,)).fetchone()
                if row is None:
                    row = c.execute('SELECT id,client,external_id,project FROM client_bindings WHERE id=?', (identifier,)).fetchone()
                if row is None:
                    raise BindingError('connection_missing', 'Unknown connection', 404)
                invite_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
                expires = time.time() + 86400
                scope = 'global' if row['project'] is None else 'project'
                c.execute('INSERT INTO agent_invitations(id,project,token_hash,expires,scope,reconnect) VALUES(?,?,?,?,?,?)',
                          (invite_id,row['project'],digest(token),expires,scope,identifier))
                result = dict(id=invite_id, project=row['project'], scope=scope, token=token,
                              expires=expires, reconnect=identifier, client=row['client'], externalId=row['external_id'])
                c.execute('INSERT INTO project_requests VALUES(?,?,?)', (request_id,proof,json.dumps(result)))
                c.commit()
                return result
            except BaseException:
                c.rollback()
                raise

    def enroll(self, token, client, external_id, *, workspace=None, name=None, roots=None,
               model=None, session=None, chat=None, metadata=None):
        token, client, external_id = text(token,'invitation',128), text(client,'client',80), text(external_id,'externalId')
        request = dict(client=client,externalId=external_id,workspace=workspace,name=name,roots=roots)
        details = self.identity_metadata(model=model, session=session, chat=chat, metadata=metadata)
        if details:
            request['metadata'] = details
        proof = fingerprint(request)
        self.setup()
        with barrier(self.registry):
            with self.registry.connect() as c:
                invite = c.execute('SELECT * FROM agent_invitations WHERE token_hash=?', (digest(token),)).fetchone()
            if invite is None or invite['revoked']:
                raise BindingError('invitation_unavailable', 'Invitation is invalid or revoked', 401)
            if invite['response'] is not None:
                if invite['request_hash'] != proof:
                    raise BindingError('invitation_used', 'Invitation was already used for another connection', 409)
                result = json.loads(invite['response'])
                self.authenticate(result['token'])
                return result
            if invite['expires'] < time.time():
                raise BindingError('invitation_expired', 'Create a new invitation', 401)
            if invite['reconnect']:
                with self.registry.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    try:
                        table = 'agent_connections' if invite['scope'] == 'global' else 'client_bindings'
                        old = c.execute('SELECT * FROM '+table+' WHERE id=?', (invite['reconnect'],)).fetchone()
                        if old is None or old['client'] != client or old['external_id'] != external_id:
                            raise BindingError('reconnect_identity', 'Reuse the invited client and external connection ID', 409)
                        if name is not None or roots is not None or invite['scope'] == 'global' and workspace is not None:
                            raise BindingError('invalid_binding', 'Reconnection preserves the existing scope')
                        identity = dict(json.loads(old['metadata']), **details)
                        credential = secrets.token_urlsafe(32)
                        if table == 'agent_connections':
                            c.execute('UPDATE agent_connections SET token_hash=?,metadata=?,revoked=0,last_seen=NULL,updated=? WHERE id=?',
                                      (digest(credential),json.dumps(identity),time.time(),old['id']))
                        else:
                            if workspace is not None and workspace != identity.get('workspace'):
                                raise BindingError('workspace_scope', 'Reconnection preserves its registered workspace', 409)
                            c.execute('UPDATE client_bindings SET metadata=?,updated=? WHERE id=?',
                                      (json.dumps(identity),time.time(),old['id']))
                            c.execute('UPDATE agent_access SET token_hash=?,revoked=0 WHERE binding=?', (digest(credential),old['id']))
                        result = dict(binding=old['id'], project=invite['project'], scope=invite['scope'],
                                      client=client,externalId=external_id,token=credential,metadata=identity,
                                      nativeIdentity='client-reported')
                        c.execute('UPDATE agent_invitations SET request_hash=?,response=? WHERE id=?',
                                  (proof,json.dumps(result),invite['id']))
                        c.commit()
                        return result
                    except BaseException:
                        c.rollback()
                        raise
            if invite['scope'] == 'global':
                if workspace is not None or name is not None or roots is not None:
                    raise BindingError('invalid_binding', 'A global connection selects its project and workspace on tool calls')
                with self.registry.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    if c.execute('SELECT 1 FROM agent_connections WHERE client=? AND external_id=?',
                                 (client,external_id)).fetchone():
                        raise BindingError('client_already_bound', 'Use a distinct external binding ID for this connection', 409)
                    identifier, credential = uuid.uuid4().hex, secrets.token_urlsafe(32)
                    identity = dict(schemaVersion=2,nativeIdentity='client-reported',**details)
                    c.execute('INSERT INTO agent_connections(id,client,external_id,metadata,updated,token_hash) VALUES(?,?,?,?,?,?)',
                              (identifier,client,external_id,json.dumps(identity),time.time(),digest(credential)))
                    result = dict(binding=identifier,project=None,scope='global',client=client,
                                  externalId=external_id,token=credential,metadata=identity,nativeIdentity='client-reported')
                    c.execute('UPDATE agent_invitations SET request_hash=?,response=? WHERE id=?',
                              (proof,json.dumps(result),invite['id']))
                    c.commit()
                    return result
            if invite['project'] is None:
                # Registration and its stable receipt survive a crash before binding.
                project = self.registry.create(name, roots, request_id=invite['id'])
            else:
                if name is not None or roots is not None:
                    raise BindingError('invalid_binding', 'An existing-project invitation cannot create another project')
                project = self.project(invite['project'])
            workspace = self.workspace(project, workspace, registry=self.registry)
            with self.registry.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute('SELECT 1 FROM client_bindings WHERE client=? AND external_id=?', (client,external_id)).fetchone():
                    raise BindingError('client_already_bound', 'Use a distinct external binding ID for this connection', 409)
                identifier, credential = uuid.uuid4().hex, secrets.token_urlsafe(32)
                metadata = dict(schemaVersion=1,workspace=workspace,nativeIdentity='client-reported',**details)
                c.execute('INSERT INTO client_bindings VALUES(?,?,?,?,?,?)',
                          (identifier,project['id'],client,external_id,json.dumps(metadata),time.time()))
                c.execute('INSERT INTO agent_access VALUES(?,?,0)', (identifier,digest(credential)))
                result = dict(binding=identifier,project=project['id'],client=client,token=credential,
                              workspace=workspace,nativeIdentity='client-reported')
                c.execute('UPDATE agent_invitations SET request_hash=?,response=? WHERE id=?',
                          (proof,json.dumps(result),invite['id']))
                c.commit()
                return result

    @staticmethod
    def identity_metadata(*, model=None, session=None, chat=None, metadata=None):
        """Bounded client assertions; never infer a model or a native chat identity."""
        if metadata is not None and (not isinstance(metadata,dict) or
                set(metadata)-{'model','session','chat','label','clientVersion'}):
            raise BindingError('invalid_binding', 'Use model, session, chat, label or clientVersion metadata; never include credentials')
        result = dict(metadata or {})
        for key,value in (('model',model),('session',session),('chat',chat)):
            if value is not None:
                if key in result and result[key] != value:
                    raise BindingError('invalid_binding', f'Conflicting {key} metadata')
                result[key] = value
        return {key:text(value,key,256 if key in ('model','label') else 128) for key,value in result.items()}

    @staticmethod
    def workspace(project, workspace, *, registry=None):
        if workspace is None:
            return None
        if not isinstance(workspace,str) or not Path(workspace).is_absolute() or not Path(workspace).is_dir():
            raise BindingError('workspace_unavailable', 'Select an existing absolute server workspace', 409)
        from project_workspaces import no_reparse, local_access, WorkspaceError
        try:
            no_reparse(Path(workspace))
        except WorkspaceError as error:
            raise BindingError('workspace_unavailable', 'Select a folder without links or reparse points', 409) from error
        resolved = Path(workspace).resolve()
        available = local_access(registry,project['id'],[Path(root) for root in project['roots']])['available'] if registry else {str(i) for i in range(len(project['roots']))}
        if not any((resolved == Path(root).resolve() or resolved.is_relative_to(Path(root).resolve()))
                   for i,root in enumerate(project['roots']) if str(i) in available):
            raise BindingError('workspace_unregistered', 'Register this code folder in the project before binding it', 409)
        return str(resolved)

    def authenticate(self, token):
        token = text(token, 'connection credential', 128)
        with self.registry.connect() as c:
            tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            row = c.execute('SELECT * FROM agent_connections WHERE token_hash=?',(digest(token),)).fetchone() if 'agent_connections' in tables else None
            global_connection = row is not None
            if row is None and 'agent_access' in tables:
                row = c.execute('''SELECT b.*,a.revoked FROM agent_access a JOIN client_bindings b ON b.id=a.binding
                                   WHERE a.token_hash=?''',(digest(token),)).fetchone()
        if row is None or row['revoked']:
            raise BindingError('connection_unavailable', 'Connection is invalid or revoked', 401)
        binding = dict(row)
        binding['metadata'] = json.loads(binding['metadata'])
        binding['scope'] = 'global' if global_connection else 'project'
        if global_connection:
            binding['project'] = None
        else:
            self.project(binding['project'])
        return binding

    def projects(self, binding):
        if binding.get('scope') != 'global':
            rows = [self.project(binding['project'])]
        else:
            with self.registry.connect() as c:
                rows = [self.registry._project(row) for row in c.execute(
                    'SELECT * FROM spaces WHERE present=1 AND deleted=0 ORDER BY name,id')]
        return [dict(id=row['id'],name=row['name'],roots=row['roots'],archived=bool(row.get('archived')))
                for row in rows]

    def select_project(self, binding, project=None, workspace=None):
        """Resolve only an explicit registered project or an unambiguous workspace."""
        if binding.get('scope') != 'global':
            if project is not None and project != binding['project']:
                raise BindingError('project_unavailable', 'This legacy connection is scoped to one project', 403)
            bound_workspace = binding['metadata'].get('workspace')
            if workspace is not None and workspace != bound_workspace:
                raise BindingError('workspace_scope', 'This legacy connection retains its enrolled workspace', 403)
            return self.project(binding['project']),bound_workspace
        if project is None:
            if workspace is None:
                raise BindingError('project_required', 'Call hub_projects and supply an explicit project on this request', 409)
            candidates = []
            for row in self.projects(binding):
                try:
                    self.workspace(row,workspace,registry=self.registry)
                except BindingError as error:
                    if error.code == 'workspace_unregistered':
                        continue
                    raise
                candidates.append(row['id'])
            if len(candidates) != 1:
                code = 'project_ambiguous' if candidates else 'workspace_unregistered'
                raise BindingError(code, 'Supply an explicit registered project for this workspace', 409)
            project = candidates[0]
        selected = self.project(text(project,'project'))
        return selected,self.workspace(selected,workspace,registry=self.registry)

    def observed_request(self, binding):
        if binding.get('scope') == 'global':
            with self.registry.connect() as c:
                c.execute('UPDATE agent_connections SET last_seen=? WHERE id=? AND revoked=0',
                          (time.time(),binding['id']))

    def catalog(self):
        with self.registry.connect() as c:
            tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'agent_access' not in tables:
                return dict(bindings=[],invitations=[])
            bindings = [dict(r) for r in c.execute('''SELECT b.id,b.project,p.name AS project_name,b.client,b.external_id,b.metadata,b.updated,a.revoked
                          FROM client_bindings b JOIN agent_access a ON a.binding=b.id LEFT JOIN spaces p ON p.id=b.project ORDER BY b.updated DESC''')]
            # Old API analysis runs enrolled one project credential per action.
            # Classify only records proven by both the run and its host-created
            # invitation receipt; a real application called hub-api stays visible.
            internal_bindings, internal_invitations = set(), set()
            if {'api_agent_runs','project_requests','agent_invitations'} <= tables:
                for row in bindings:
                    if row['client'] != 'hub-api' or not c.execute(
                            'SELECT 1 FROM api_agent_runs WHERE project=? AND action_id=?',
                            (row['project'],row['external_id'])).fetchone():
                        continue
                    request_id = digest('api-invite:'+row['external_id'])[:32]
                    request = c.execute('SELECT result FROM project_requests WHERE id=?',(request_id,)).fetchone()
                    if request is None:
                        continue
                    try:
                        invitation_id = json.loads(request['result'])['id']
                        invite = c.execute('SELECT response FROM agent_invitations WHERE id=? AND project=?',
                                           (invitation_id,row['project'])).fetchone()
                        receipt = json.loads(invite['response']) if invite and invite['response'] else {}
                    except (KeyError,TypeError,ValueError):
                        continue
                    if receipt.get('binding') == row['id'] and receipt.get('client') == 'hub-api':
                        internal_bindings.add(row['id']); internal_invitations.add(invitation_id)
            bindings = [row for row in bindings if row['id'] not in internal_bindings]
            for row in bindings:
                row['metadata'] = json.loads(row['metadata'])
                row.update(scope='project',nativeIdentity='client-reported',activity=dict(state='unknown',runningVerified=False))
            if 'agent_connections' in tables:
                for row in c.execute('SELECT id,client,external_id,metadata,updated,revoked,last_seen FROM agent_connections'):
                    item = dict(row)
                    last_seen = item.pop('last_seen')
                    item['metadata'] = json.loads(item['metadata'])
                    item.update(project=None,scope='global',nativeIdentity='client-reported',
                                activity=dict(state='recent-request' if last_seen and time.time()-last_seen<120 and not item['revoked'] else 'unknown',
                                              lastRequest=last_seen,runningVerified=False))
                    bindings.append(item)
            bindings.sort(key=lambda row:row['updated'],reverse=True)
            has_scope = 'scope' in {row['name'] for row in c.execute('PRAGMA table_info(agent_invitations)')}
            scope = 'scope' if has_scope else "CASE WHEN project IS NULL THEN 'new-project' ELSE 'project' END AS scope"
            invitations = [dict(r) for r in c.execute(f'''SELECT id,project,{scope},expires,revoked,response IS NOT NULL AS used
                          FROM agent_invitations ORDER BY rowid DESC LIMIT 100''')]
            invitations = [row for row in invitations if row['id'] not in internal_invitations]
        from connection_capabilities import Profiles
        profiles = Profiles(self.registry)
        for row in bindings:
            row.update(profiles.public(row['id'], binding=row))
        return dict(bindings=bindings,invitations=invitations,projects=self.projects(dict(scope='global')))

    def revoke(self, identifier):
        text(identifier,'connection ID')
        self.setup()
        with barrier(self.registry), self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            changed = c.execute('UPDATE agent_access SET revoked=1 WHERE binding=?',(identifier,)).rowcount
            changed += c.execute('UPDATE agent_connections SET revoked=1 WHERE id=?',(identifier,)).rowcount
            changed += c.execute('UPDATE agent_invitations SET revoked=1 WHERE id=?',(identifier,)).rowcount
            c.commit()
        if not changed:
            raise BindingError('connection_missing','Unknown connection',404)
        return dict(id=identifier,revoked=True)
