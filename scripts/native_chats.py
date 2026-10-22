"""Optional external conversation resources, separate from Hub actor identity."""
import hashlib
import json
import re
import time
from urllib.parse import parse_qsl, quote, urlsplit

from agent_bindings import BindingError, text
from task_transfer import barrier


UUID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', re.I)
PRIVATE_PARAMETERS = {'token', 'accesstoken', 'idtoken', 'refreshtoken', 'bearertoken',
                      'apikey', 'authorization', 'password', 'secret', 'clientsecret',
                      'credential', 'credentials', 'signature', 'sig',
                      'xamzsignature', 'xgoogsignature'}


def open_uri(value):
    value = text(value, 'chat URL', 2000)
    parsed = urlsplit(value)
    if parsed.username or parsed.password or any(c in value for c in ('\\', '"', '<', '>')):
        raise BindingError('invalid_chat', 'Use a supported conversation URL without credentials')
    try:
        parsed.port
    except ValueError:
        raise BindingError('invalid_chat', 'Use a valid conversation URL port') from None
    for parameters in (parsed.query, parsed.fragment.rsplit('?', 1)[-1]):
        if any(re.sub(r'[^a-z0-9]', '', key.casefold()) in PRIVATE_PARAMETERS
               for key, _ in parse_qsl(parameters, keep_blank_values=True)):
            raise BindingError('invalid_chat', 'Keep private credentials out of conversation URLs')
    if parsed.scheme == 'codex' and parsed.netloc == 'threads' and UUID.fullmatch(parsed.path.lstrip('/')) and not parsed.query and not parsed.fragment:
        return value
    if parsed.scheme == 'https' and parsed.hostname:
        return value
    if parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1'):
        return value
    raise BindingError('invalid_chat', 'Use HTTPS, local HTTP, or a documented Codex conversation link')


def template_uri(template, native_id):
    template = text(template, 'chat URL template', 2000)
    markers = ('{nativeId}', '$nativeId')
    if sum(template.count(marker) for marker in markers) != 1:
        raise BindingError('invalid_chat', 'Use one nativeId placeholder in the conversation URL template')
    marker = next(marker for marker in markers if marker in template)
    parsed = urlsplit(template)
    if marker in parsed.scheme or marker in parsed.netloc:
        raise BindingError('invalid_chat', 'Keep the conversation URL origin fixed')
    return open_uri(template.replace(marker, quote(text(native_id, 'native chat ID', 256), safe='')))


def normalize(value, *, client=None, provenance='client-reported', uri_template=None):
    allowed = {'client', 'clientInstance', 'host', 'nativeId', 'openUri', 'title', 'model'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise BindingError('invalid_chat', 'Use bounded native chat identity and an optional source URL')
    result = {key: text(item, key, 2000 if key == 'openUri' else 256)
              for key, item in value.items() if item is not None}
    if 'client' not in result and client:
        result['client'] = text(client, 'client', 80)
    if not result.get('client') or not (result.get('nativeId') or result.get('openUri')):
        raise BindingError('invalid_chat', 'Supply the client and a native ID or source URL')
    if result.get('openUri'):
        result['openUri'] = open_uri(result['openUri'])
    documented = result['client'].casefold() in ('codex', 'codex-desktop')
    if not result.get('openUri') and uri_template and result.get('nativeId'):
        result['openUri'] = template_uri(uri_template, result['nativeId'])
    elif not result.get('openUri') and documented and UUID.fullmatch(result.get('nativeId', '')):
        result['openUri'] = 'codex://threads/' + result['nativeId']
    result.update(provenance=provenance, verificationState='client-reported',
                  openingDocumented=bool(documented and result.get('openUri', '').startswith('codex://threads/')))
    return result


def setup(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS native_chat_resources(
        id TEXT PRIMARY KEY,body TEXT NOT NULL,updated REAL NOT NULL)''')
    connection.execute('''CREATE TABLE IF NOT EXISTS native_chat_links(
        resource TEXT NOT NULL REFERENCES native_chat_resources(id),project TEXT NOT NULL,
        task TEXT NOT NULL,stage TEXT NOT NULL,actor TEXT NOT NULL,updated REAL NOT NULL,
        PRIMARY KEY(resource,project,task,stage,actor))''')


def register(registry, project, actor, value, *, task=None, stage=None, client=None):
    resource = normalize(value, client=client)
    if task is not None:
        context = registry.store(project).task_context(task)['tasks']
        if not context or stage and not any(item['id'] == stage for item in context[0].get('stages', [])):
            raise BindingError('invalid_chat_relation', 'Choose an existing task and stage in this project')
    elif stage is not None:
        raise BindingError('invalid_chat_relation', 'A stage requires its task')
    identity = [resource['client'], resource.get('clientInstance'), resource.get('host'),
                resource.get('nativeId') or resource['openUri']]
    key = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()
    with barrier(registry), registry.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        try:
            setup(connection)
            previous = connection.execute('SELECT body FROM native_chat_resources WHERE id=?', (key,)).fetchone()
            if previous:
                # A later call may omit optional metadata. It must not erase the
                # last known title or address of the same native conversation.
                resource = {**json.loads(previous['body']), **resource}
            connection.execute('INSERT INTO native_chat_resources VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,updated=excluded.updated',
                               (key, json.dumps(resource, ensure_ascii=False), time.time()))
            connection.execute('INSERT INTO native_chat_links VALUES(?,?,?,?,?,?) ON CONFLICT(resource,project,task,stage,actor) DO UPDATE SET updated=excluded.updated',
                               (key, project, task or '', stage or '', actor, time.time()))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return dict(resource, resourceId=key)


def linked(registry, project):
    with registry.connect() as connection:
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='native_chat_links'").fetchone()
        if not exists:
            return []
        rows = connection.execute('''SELECT r.id,r.body,l.task,l.stage,l.actor,l.updated
            FROM native_chat_links l JOIN native_chat_resources r ON r.id=l.resource
            WHERE l.project=? ORDER BY l.updated DESC''', (project,)).fetchall()
    return [dict(resource=json.loads(row['body']), resourceId=row['id'], task=row['task'] or None,
                 stage=row['stage'] or None, actor=row['actor'], updated=row['updated']) for row in rows]


def for_actor(registry, project, actor):
    """Reuse only an unambiguous resource already reported by this conversation."""
    with registry.connect() as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='native_chat_links'").fetchone():
            return None
        rows = connection.execute('''SELECT DISTINCT r.id,r.body FROM native_chat_links l
            JOIN native_chat_resources r ON r.id=l.resource WHERE l.project=? AND l.actor=?''',
            (project, actor)).fetchall()
    return json.loads(rows[0]['body']) if len(rows) == 1 else None
