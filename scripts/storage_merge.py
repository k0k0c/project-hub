"""Build a verified import candidate without modifying either input home.

The caller supplies consistent, normalized snapshots and owns the writer barrier
and publication lifecycle. This module never initializes ProjectRegistry, opens
source workspaces, enrolls a client, or changes native configuration. Additions
are whole projects identified by their permanent IDs; shared records are carried
only through explicit project references or SQLite foreign keys.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass, field
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from hub_backup import BackupError, DATABASES, _connect, _files, digest, inventory
from project_workspaces import no_reparse
from runtime_diagnostics import record, resources


# These are installation identities and credentials, including legacy bindings.
# Source registrations must never become active as a consequence of an import.
CONNECTION_TABLES = frozenset({
    'client_bindings', 'agent_invitations', 'agent_access', 'agent_connections',
    'agent_provider_settings', 'agent_provider_requests', 'connection_profiles',
    'connection_controls', 'connection_probes', 'project_requests',
})
GLOBAL_TABLES = frozenset({'agent_instruction_settings'})
META_TABLES = frozenset({'registry_meta', 'registry_upgrade', 'meta'})
DERIVED_TABLES = frozenset({
    'read_model_heads', 'read_model_file_proofs', 'read_model_tasks',
    'read_model_task_graph', 'read_model_events', 'read_model_event_metadata',
    'read_model_sources', 'read_model_views', 'read_model_hints',
    'read_model_details', 'read_model_view_cursors', 'read_model_changes',
    'read_model_generation', 'observation_cache', 'prepared_source_images',
})
PROJECT_FIELDS = frozenset({
    'project', 'projectId', 'project_id', 'originProject', 'sourceProject',
    'targetProject', 'ownerProject', 'batchProject',
})
TRANSFER_FIELDS = frozenset({'origin', 'owner', 'source', 'target'})
HASH = re.compile(r'[a-f0-9]{64}\Z')
PROTECTED_DIRECTORIES = frozenset({'private', 'connections', 'native-client'})
# These files describe the local installation/session rather than project data.
# Add imports retain the active home's copies; replace-all still uses the source
# home as its base and therefore keeps its existing full-replacement behavior.
LOCAL_METADATA_FILES = frozenset({'coordination/migration-roots.json', 'language-servers.json', 'ui-preferences.json'})


class MergeError(BackupError):
    def __init__(self, message, *, code='storage_import_conflict', conflicts=()):
        super().__init__(message)
        self.code = code
        self.status = 409
        self.conflicts = list(conflicts)
        self.body = dict(error=code, message=message, conflicts=self.conflicts)


def _quoted(name):
    return '"' + name.replace('"', '""') + '"'


def _encoded(value):
    if isinstance(value, bytes):
        return {'sqliteBlob': base64.b64encode(value).decode('ascii')}
    if isinstance(value, (list, tuple)):
        return [_encoded(item) for item in value]
    if isinstance(value, dict):
        return {key: _encoded(item) for key, item in value.items()}
    return value


def _canonical(value):
    return json.dumps(_encoded(value), sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False)


def _hash(value):
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False,
                               separators=(',', ':'), allow_nan=False)
    result = hashlib.sha256()
    for chunk in encoder.iterencode(_encoded(value)):
        result.update(chunk.encode('utf-8'))
    return result.hexdigest()


def _problem(problem_type, message, **details):
    return dict(type=problem_type, message=message, **details)


def _generated_file(name):
    return (name.startswith(('prepared-sources/', 'view-locks/')) or
            name.startswith('.local/api-agent-runs/') and name.endswith('.lock'))


def _protected_file(name):
    return name.split('/', 1)[0] in PROTECTED_DIRECTORIES


def _instruction_file(name):
    return name.startswith('instructions/')


@dataclass
class _Table:
    name: str
    sql: str
    columns: tuple
    foreign_keys: tuple
    unique: tuple
    objects: tuple
    rows: list = field(default_factory=list)
    lookups: dict = field(default_factory=dict)

    @property
    def names(self):
        return tuple(column[1] for column in self.columns)

    @property
    def primary(self):
        return tuple(column[1] for column in sorted(self.columns, key=lambda c: c[5]) if column[5])

    @property
    def writable(self):
        return tuple(column[1] for column in self.columns if len(column) < 7 or not column[6])

    @property
    def signature(self):
        return dict(columns=self.columns, foreignKeys=self.foreign_keys, unique=self.unique)


@dataclass(eq=False)
class _Row:
    table: _Table
    values: dict
    anchors: set = field(default_factory=set)
    references: set = field(default_factory=set)
    parents: list = field(default_factory=list)
    shared: bool = False

    def label(self):
        fields = self.table.primary or tuple(self.values)[:1]
        return {name: self.values[name] for name in fields}


@dataclass
class _Database:
    name: str
    tables: dict
    sequences: dict
    views: tuple = ()
    event_ids: dict = field(default_factory=dict)
    project_events: dict = field(default_factory=lambda: defaultdict(list))


@dataclass
class _Home:
    path: Path
    projects: dict
    schemas: dict
    files: dict
    proofs: dict
    databases: dict
    instructions: dict
    instruction_location: dict
    issues: list = field(default_factory=list)
    dependencies: dict = field(default_factory=lambda: defaultdict(set))
    components: dict = field(default_factory=dict)
    fingerprints: dict = field(default_factory=dict)
    logical_revision: str = ''


def _read_database(path, name):
    tables, sequences = {}, {}
    with _connect(path) as connection:
        connection.row_factory = sqlite3.Row
        views = tuple(tuple(row) for row in connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='view' ORDER BY name"))
        for master in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"):
            table_name, sql = master['name'], master['sql']
            if table_name == 'sqlite_sequence':
                sequences = {row[0]: row[1] for row in connection.execute('SELECT name,seq FROM sqlite_sequence')
                             if row[0] not in DERIVED_TABLES}
            if table_name.startswith('sqlite_'):
                continue
            if sql and sql.lstrip().upper().startswith('CREATE VIRTUAL TABLE'):
                raise MergeError('Импорт этого расширения требует совместимого обработчика.',
                                 conflicts=[_problem('unsupported-table',
                                     'Виртуальную таблицу нельзя безопасно перенести обычным объединением записей.',
                                     database=name, table=table_name)])
            columns = tuple(tuple(row) for row in connection.execute('PRAGMA table_xinfo(' + _quoted(table_name) + ')'))
            foreign_keys = tuple(tuple(row) for row in connection.execute('PRAGMA foreign_key_list(' + _quoted(table_name) + ')'))
            unique = []
            for index in connection.execute('PRAGMA index_list(' + _quoted(table_name) + ')'):
                if index[2]:
                    keys = tuple(tuple(row) for row in connection.execute('PRAGMA index_xinfo(' + _quoted(index[1]) + ')') if row[5])
                    # Keep the full key/collation and partial-index contract in
                    # compatibility proofs. SQLite validates expressions later.
                    unique.append((keys, bool(index[4])))
            objects = tuple((row['type'], row['name'], row['sql']) for row in connection.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY name",
                (table_name,)))
            table = _Table(table_name, sql, columns, foreign_keys, tuple(sorted(unique, key=_canonical)), objects)
            # Read-model/cache tables are disposable projections.  Their schema
            # and SQLite objects still participate in compatibility checks, but
            # loading their rows can materialize large BLOB caches from both
            # homes before the merge logic discards them.
            if table_name not in DERIVED_TABLES:
                record('import.table_read_started', database=name, table=table_name, resources=resources())
                table.rows = [_Row(table, dict(row)) for row in connection.execute('SELECT * FROM ' + _quoted(table_name))]
                record('import.table_read_finished', database=name, table=table_name,
                       count=len(table.rows), resources=resources())
            tables[table_name] = table
    result = _Database(name, tables, sequences, views)
    if name == DATABASES[1] and 'events' in tables:
        for row in tables['events'].rows:
            result.event_ids[row.values['seq']] = row.values['id']
            result.project_events[row.values['project']].append(row)
    return result


def _json_values(row):
    for name, value in row.values.items():
        if name not in {'body', 'payload', 'result', 'operations', 'descriptor', 'policy', 'metadata', 'roots', 'response', 'evidence'}:
            continue
        if isinstance(value, str) and value.lstrip().startswith(('{', '[')):
            try:
                yield json.loads(value)
            except ValueError as error:
                raise MergeError('Повреждена сохранённая запись. Проверьте исходное хранилище.',
                                 conflicts=[_problem('invalid-record', 'Сохранённая запись содержит повреждённые данные.',
                                                     table=row.table.name, record=row.label(), field=name)]) from error


def _references(value, project_ids):
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in PROJECT_FIELDS and isinstance(item, str) and item:
                result.add(item)
            elif key in TRANSFER_FIELDS and isinstance(item, str) and item in project_ids:
                result.add(item)
            result.update(_references(item, project_ids))
    elif isinstance(value, list):
        for item in value:
            result.update(_references(item, project_ids))
    elif isinstance(value, str) and value.startswith('hub-source/'):
        parts = value.split('/', 2)
        if len(parts) == 3 and parts[1]:
            result.add(parts[1])
    return result


def _find(table, columns, values):
    columns = tuple(columns)
    if columns not in table.lookups:
        table.lookups[columns] = {tuple(row.values.get(column) for column in columns): row for row in table.rows}
    return table.lookups[columns].get(tuple(values))


def _classify(database, project_ids):
    tables = database.tables
    for name, table in tables.items():
        if name in DERIVED_TABLES or name in META_TABLES:
            continue
        for row in table.rows:
            if name in ('spaces', 'projects'):
                row.anchors = {row.values['id']}
                row.references = set(row.anchors)
            else:
                row.anchors = {value for key, value in row.values.items()
                               if key in PROJECT_FIELDS and isinstance(value, str) and value}
                if name in ('task_owners', 'task_transfers', 'completion_checkpoints'):
                    row.anchors.update(value for key, value in row.values.items()
                                       if key in TRANSFER_FIELDS and isinstance(value, str) and value)
                row.references = set(row.anchors)
                for value in _json_values(row):
                    row.references.update(_references(value, project_ids))
                if name == 'stage_transactions':
                    row.anchors.update(row.references)
                elif not row.anchors and name not in CONNECTION_TABLES | GLOBAL_TABLES:
                    # An explicit project field in a JSON delivery/extension is
                    # an ownership declaration, unlike an arbitrary string.
                    row.anchors.update(row.references)
    for name, table in tables.items():
        if name in DERIVED_TABLES or name in META_TABLES:
            continue
        for row in table.rows:
            groups = defaultdict(list)
            for foreign in table.foreign_keys:
                groups[foreign[0]].append(foreign)
            for foreign in groups.values():
                foreign.sort(key=lambda part: part[1])
                target = tables.get(foreign[0][2])
                if target is None:
                    continue  # inventory already rejects a missing FK parent.
                source_columns = [part[3] for part in foreign]
                target_columns = [part[4] for part in foreign]
                if any(column is None for column in target_columns):
                    target_columns = target.primary
                values = [row.values.get(column) for column in source_columns]
                if any(value is None for value in values):
                    continue
                parent = _find(target, target_columns, values)
                if parent is not None:
                    row.parents.append(parent)
            extras = []
            if name == 'task_transfers':
                extras.append(('task_owners', 'uid', row.values.get('uid')))
            if database.name == DATABASES[1]:
                if name in ('events', 'resource_attempts'):
                    extras.extend((('sessions', 'id', row.values.get('session')),
                                   ('work', 'id', row.values.get('work'))))
                if name == 'session_agents':
                    extras.append(('sessions', 'id', row.values.get('parent')))
                if name == 'receipts':
                    for value in _json_values(row):
                        if isinstance(value, dict):
                            extras.extend((('work', 'id', value.get('work')),
                                           ('events', 'seq', value.get('revision'))))
            for target_name, column, value in extras:
                if target_name in tables and value is not None:
                    parent = _find(tables[target_name], [column], [value])
                    if parent is not None and parent is not row and parent not in row.parents:
                        row.parents.append(parent)
    # Forward ownership for child records first. Unscoped parent resources
    # then acquire consumers (native chats and explicit extension resources).
    rows = [row for name, table in tables.items() if name not in DERIVED_TABLES | META_TABLES | GLOBAL_TABLES
            for row in table.rows]
    changed = True
    while changed:
        changed = False
        for row in rows:
            refs = row.references | set().union(*(parent.references for parent in row.parents))
            anchors = row.anchors or set().union(*(parent.anchors for parent in row.parents))
            if refs != row.references or anchors != row.anchors:
                row.references, row.anchors = refs, anchors
                changed = True
    for row in rows:
        for parent in row.parents:
            if not parent.anchors and parent.table.name not in CONNECTION_TABLES | META_TABLES | GLOBAL_TABLES:
                parent.shared = True
    changed = True
    while changed:
        changed = False
        for row in rows:
            for parent in row.parents:
                if parent.shared:
                    anchors = parent.anchors | row.anchors
                    if anchors != parent.anchors:
                        parent.anchors = anchors
                        changed = True
            if not row.anchors:
                anchors = set().union(*(parent.anchors for parent in row.parents))
                if anchors:
                    row.anchors = anchors
                    changed = True


def _instructions(home):
    location_file = home / 'instructions/location.json'
    location = json.loads(location_file.read_text(encoding='utf-8-sig')) if location_file.exists() else {}
    if not isinstance(location, dict):
        raise MergeError('Повреждены сведения о сохранённых инструкциях.')
    if location and location.get('kind') != 'project-hub-user-skill-v1':
        raise MergeError('Неподдерживаемый формат сохранённых инструкций.')
    root = Path(location['root']) if location.get('root') else home / 'instructions/project-hub-user'
    if not root.is_absolute():
        raise MergeError('Папка сохранённых инструкций должна быть указана полным путём.')
    # A candidate may already name its final publication location. Its own
    # bundled content remains authoritative during offline validation.
    bundled = home / 'instructions/project-hub-user'
    if bundled.exists():
        root = bundled
    if not root.exists():
        if location:
            raise MergeError('Сохранённые инструкции отсутствуют. Используйте полную резервную копию.')
        return {}, location
    no_reparse(root)
    files = _files(root, data_home=False)
    marker = files.get('.project-hub-owned.json')
    if not marker or 'SKILL.md' not in files:
        raise MergeError('Не подтверждена принадлежность сохранённых инструкций Hub.')
    owner = json.loads(marker.read_text(encoding='utf-8-sig'))
    if not isinstance(owner, dict) or owner.get('kind') != 'project-hub-user-skill-v1':
        raise MergeError('Сохранённые инструкции принадлежат другому приложению.')
    return files, location


def _normal_row(database, row):
    values = dict(row.values)
    if database.name != DATABASES[1]:
        return values
    events = database.tables.get('events')
    by_seq = database.event_ids
    if row.table.name == 'events':
        values['seq'] = values['id']
    elif row.table.name == 'work' and values.get('revision') in by_seq:
        values['revision'] = by_seq[values['revision']]
    elif row.table.name == 'sessions' and events:
        values['last_cursor'] = sorted(event.values['id'] for event in database.project_events[values['project']]
                                      if event.values['seq'] <= values.get('last_cursor', 0))
    elif row.table.name == 'receipts':
        value = json.loads(values['result'])
        if isinstance(value, dict) and value.get('revision') in by_seq:
            value['revision'] = by_seq[value['revision']]
            values['result'] = _canonical(value)
    for foreign in row.table.foreign_keys:
        if foreign[2] == 'events' and foreign[4] == 'seq' and values.get(foreign[3]) in by_seq:
            values[foreign[3]] = by_seq[values[foreign[3]]]
    return values


def _load_home(path):
    home = Path(path).expanduser().resolve()
    no_reparse(path)
    if not home.is_dir() or (home / 'INCOMPLETE').exists() or (home.parent / 'INCOMPLETE').exists():
        raise MergeError('Выберите полностью подготовленное хранилище Hub.')
    files = _files(home)
    projects, schemas = inventory(home)
    if schemas['registry'] != 2 or schemas.get('coordination', 2) != 2:
        raise MergeError('Перед импортом преобразуйте старый формат во временной копии.', code='storage_upgrade_required')
    databases = {name: _read_database(home / name, name) for name in DATABASES if (home / name).exists()}
    registry = databases[DATABASES[0]]
    pending = registry.tables.get('registry_upgrade')
    if pending and any(row.values['state'] == 'pending' for row in pending.rows):
        raise MergeError('Преобразование исходного хранилища ещё не завершено.')
    instructions, instruction_location = _instructions(home)
    result = _Home(home, {project['id']: project for project in projects}, schemas, files,
                   {name: digest(file) for name, file in files.items()}, databases, instructions, instruction_location)
    project_ids = set(result.projects)
    if len({pid.casefold() for pid in project_ids}) != len(project_ids):
        result.issues.append(_problem('path-alias', 'Постоянные идентификаторы проектов задают совпадающие папки.'))
    if len({name.casefold() for name in files}) != len(files):
        result.issues.append(_problem('path-alias', 'В хранилище находятся неоднозначные пути файлов.'))
    for database in databases.values():
        _classify(database, project_ids)
        for name, _ in database.views:
            result.issues.append(_problem('unsupported-schema-object',
                'Принадлежность представления базы данных проектам неизвестна. Нужен совместимый обработчик импорта.',
                database=database.name, view=name))
    for name in files:
        if name.startswith('projects/'):
            parts = name.split('/', 2)
            if len(parts) != 3 or parts[1] not in project_ids:
                result.issues.append(_problem('unregistered-project-data',
                    'Данные проекта отсутствуют в каталоге. Проверьте исходное хранилище.', path=name))
    for pid in sorted(project_ids):
        components = {'files': {name.split('/', 2)[2]: proof for name, proof in result.proofs.items()
                               if name.startswith('projects/' + pid + '/') and not _generated_file(name)}}
        for database in databases.values():
            for name, table in database.tables.items():
                if name in CONNECTION_TABLES | META_TABLES | DERIVED_TABLES | GLOBAL_TABLES:
                    continue
                relevant = [row for row in table.rows if pid in row.anchors]
                if relevant:
                    components[database.name + '/' + name] = dict(schema=table.signature,
                        rows=sorted((_normal_row(database, row) for row in relevant), key=_canonical))
                    for row in relevant:
                        result.dependencies[pid].update(row.references - {pid})
        for name in ('project.json', 'project-settings.json', 'source-file-aliases.json'):
            file = files.get('projects/' + pid + '/' + name)
            if file:
                result.dependencies[pid].update(_references(json.loads(file.read_text(encoding='utf-8-sig')), project_ids) - {pid})
        journal = files.get('projects/' + pid + '/events.jsonl')
        if journal:
            with journal.open(encoding='utf-8-sig') as stream:
                for line in stream:
                    if line.strip():
                        result.dependencies[pid].update(_references(json.loads(line), project_ids) - {pid})
        hashed_components = {}
        for area, value in components.items():
            record('import.fingerprint', projectId=pid, area=area, resources=resources())
            hashed_components[area] = _hash(value)
        result.components[pid] = hashed_components
        result.fingerprints[pid] = _hash(result.components[pid])
        missing = result.dependencies[pid] - project_ids
        if missing:
            result.issues.append(_problem('missing-project-reference',
                'Связанные данные ссылаются на отсутствующий проект.', project=pid, requiredProjects=sorted(missing)))
    _validate_content(result)
    # Logical revisions survive SQLite backup/checkpoint and portable relocation
    # of the owned instruction root. Cache refreshes are not user writes.
    file_proofs = {name: proof for name, proof in result.proofs.items()
                   if name not in DATABASES and not _generated_file(name) and
                   not name.startswith('instructions/project-hub-user/') and name != 'instructions/location.json'}
    if instruction_location:
        location = dict(instruction_location)
        location.pop('root', None)
        location.pop('packageRoot', None)
        file_proofs['instructions/location.json'] = _hash(location)
    for name, file in instructions.items():
        file_proofs['instructions/project-hub-user/' + name] = digest(file)
    logical_sql = {}
    for name, database in databases.items():
        logical_sql[name] = {table_name: dict(sql=table.sql, schema=table.signature,
            rows=sorted((row.values for row in table.rows), key=_canonical),
            objects=[obj for obj in table.objects if not obj[1].startswith('read_generation_')])
            for table_name, table in database.tables.items() if table_name not in DERIVED_TABLES}
        logical_sql[name]['sequences'] = database.sequences
        logical_sql[name]['views'] = database.views
    result.logical_revision = _hash(dict(files=file_proofs, databases=logical_sql))
    return result


def _validate_content(home):
    """Validate immutable project assets directly, without a writable adapter."""
    from artifact_store import inspect_descriptor, parse as parse_artifact
    assets = {}
    for pid in home.projects:
        prefix = 'projects/' + pid + '/knowledge/'
        blobs, descriptors = {}, {}
        for name, file in home.files.items():
            if name.startswith(prefix + 'blobs/') and HASH.fullmatch(file.name):
                expected = prefix + 'blobs/' + file.name[:2] + '/' + file.name
                if name != expected or home.proofs[name] != file.name:
                    raise MergeError('Не совпадает контрольная сумма сохранённого вложения.',
                                     conflicts=[_problem('invalid-blob', 'Вложение повреждено.', project=pid, path=name)])
                blobs[file.name] = file
            elif name.startswith(prefix + 'artifact-descriptors/'):
                if not HASH.fullmatch(file.name) or file.read_bytes() != (file.name + '\n').encode('ascii'):
                    raise MergeError('Повреждён каталог сохранённых артефактов.')
                descriptors[file.name] = None
        for identifier in descriptors:
            if identifier not in blobs:
                raise MergeError('Отсутствует описание сохранённого артефакта.')
            item = inspect_descriptor(blobs[identifier].read_bytes())
            content = blobs.get(item['contentHash'])
            if content is None or content.stat().st_size != item['size']:
                raise MergeError('Отсутствует содержимое сохранённого артефакта.')
            descriptors[identifier] = item
        for item in descriptors.values():
            previous = item.get('previous')
            if previous is not None and (previous not in descriptors or
                                         descriptors[previous]['artifactId'] != item['artifactId']):
                raise MergeError('История сохранённого артефакта неполна.')
        assets[pid] = blobs, descriptors

    def validate_references(value, project, key=None):
        if isinstance(value, dict):
            origin = value.get('sourceProject', project)
            for field, item in value.items():
                validate_references(item, origin, field)
            if value.get('kind') == 'document':
                blobs = assets[project][0]
                for source in value.get('sources', []):
                    needed = ([source['hash']] if source.get('hash') else []) + [asset['hash'] for asset in source.get('assets', [])]
                    if any(identifier not in blobs for identifier in needed):
                        raise MergeError('Документ ссылается на отсутствующее вложение.')
        elif isinstance(value, list):
            for item in value:
                validate_references(item, project, key)
        elif isinstance(value, str) and key in ('path', 'snapshot', 'evidence'):
            if value.startswith('hub-source/'):
                parts = value.split('/', 2)
                if len(parts) == 3:
                    project, value = parts[1], parts[2]
            if value.startswith('hub-artifact/'):
                identifier, name = parse_artifact(value)
                descriptors = assets.get(project, ({}, {}))[1]
                if identifier not in descriptors or descriptors[identifier]['name'] != name:
                    raise MergeError('Связанные данные ссылаются на отсутствующий артефакт.')

    for pid in home.projects:
        values = []
        for name in ('project.json', 'source-file-aliases.json'):
            file = home.files.get('projects/' + pid + '/' + name)
            if file:
                values.append(json.loads(file.read_text(encoding='utf-8-sig')))
        journal = home.files.get('projects/' + pid + '/events.jsonl')
        if journal:
            with journal.open(encoding='utf-8-sig') as stream:
                values.extend(json.loads(line) for line in stream if line.strip())
        registry = home.databases[DATABASES[0]]
        for table_name in ('knowledge_items', 'knowledge_changes', 'knowledge_imports'):
            table = registry.tables.get(table_name)
            if table:
                for row in table.rows:
                    if row.values.get('project') == pid:
                        values.extend(_json_values(row))
        coordination = home.databases.get(DATABASES[1])
        if coordination:
            for name in ('work', 'plan_outbox', 'events'):
                table = coordination.tables.get(name)
                if table:
                    for row in table.rows:
                        if row.values.get('project') == pid:
                            values.extend(_json_values(row))
                            if name == 'work' and row.values.get('evidence'):
                                validate_references(json.loads(row.values['evidence']), pid, 'evidence')
        for value in values:
            validate_references(value, pid)


def revision(home):
    """Authoritative logical revision; independent of WAL, caches and root relocation."""
    return _load_home(home).logical_revision


def verified_source(home, expected):
    """Validate an owned prepared input before touching the active data home."""
    loaded = _load_home(Path(home))
    if loaded.logical_revision != expected:
        raise MergeError('Подготовленный источник изменился. Откройте предварительный просмотр ещё раз.',
                         code='storage_revision_conflict')
    return loaded


def _global_changes(active, incoming):
    changes = []
    for name in sorted(set(active.proofs) | set(incoming.proofs)):
        if (name in DATABASES or name.startswith('projects/') or _instruction_file(name) or _generated_file(name)
                or _protected_file(name) or active.proofs.get(name) == incoming.proofs.get(name)):
            continue
        kind = 'local-metadata' if name in LOCAL_METADATA_FILES else 'unknown'
        changes.append(dict(area='file', path=name, kind=kind,
                            current=name in active.proofs, incoming=name in incoming.proofs))
    def instruction_proofs(home):
        proofs = {name: proof for name, proof in home.proofs.items() if _instruction_file(name) and
                  not name.startswith('instructions/project-hub-user/') and name != 'instructions/location.json'}
        proofs.update({'instructions/project-hub-user/' + name: digest(file) for name, file in home.instructions.items()})
        if home.instruction_location:
            value = {key: item for key, item in home.instruction_location.items() if key not in ('root', 'packageRoot')}
            proofs['instructions/location.json'] = _hash(value)
        return proofs
    before, after = instruction_proofs(active), instruction_proofs(incoming)
    if before != after:
        changes.append(dict(area='instructions', kind='instructions', current=bool(before), incoming=bool(after)))
    for db_name, database in incoming.databases.items():
        current = active.databases.get(db_name)
        for name, table in database.tables.items():
            if name in CONNECTION_TABLES | META_TABLES | DERIVED_TABLES:
                continue
            rows = [row.values for row in table.rows if not row.anchors]
            previous = current.tables.get(name) if current else None
            before = [row.values for row in previous.rows if not row.anchors] if previous else []
            if rows and sorted(rows, key=_canonical) != sorted(before, key=_canonical):
                kind = 'settings' if name in GLOBAL_TABLES else 'shared' if db_name == DATABASES[1] and name == 'receipts' else 'unknown'
                changes.append(dict(area='database', database=db_name, table=name, kind=kind,
                                    currentRows=len(before), incomingRows=len(rows)))
    return changes


def _preview(active, incoming):
    projects, conflicts, same_names = [], list(incoming.issues), []
    conflicts.extend(dict(problem, modes=['add']) for problem in active.issues)
    for pid, project in sorted(incoming.projects.items()):
        before, after = active.fingerprints.get(pid), incoming.fingerprints[pid]
        status = 'new' if before is None else 'identical' if before == after else 'conflict'
        differences = [area for area in sorted(set(active.components.get(pid, {})) | set(incoming.components[pid]))
                       if active.components.get(pid, {}).get(area) != incoming.components[pid].get(area)]
        row = dict(project, status=status, currentFingerprint=before, incomingFingerprint=after,
                   differences=differences, dependencies=sorted(incoming.dependencies[pid]))
        if status == 'conflict':
            row['resolutions'] = ['keep-current', 'replace', 'cancel']
            conflicts.append(_problem('project-id', 'В хранилищах находятся разные версии одного проекта.',
                                      project=pid, differences=differences, resolutions=row['resolutions']))
        projects.append(row)
        for other_id, other in active.projects.items():
            if other_id != pid and project['name'].casefold() == other['name'].casefold():
                same_names.append(dict(name=project['name'], currentProject=other_id, incomingProject=pid))
    global_changes = _global_changes(active, incoming)
    for change in global_changes:
        if change['kind'] == 'unknown' and (change.get('incoming') or change.get('incomingRows')):
            conflicts.append(_problem('ambiguous-global-data',
                'Принадлежность общих данных проектам неизвестна. Для их переноса используйте полное восстановление.',
                modes=['add'], **change))
    # Show obvious record/key conflicts for new projects before the user chooses
    # any replacement. Differing existing versions retain their explicit choice.
    new = incoming.projects.keys() - active.projects.keys()
    conflicts.extend(dict(problem, modes=['add']) for problem in _dependency_conflicts(
        active, incoming, new, set(), active.projects.keys() | new, 'add'))
    desired, tables, schema_conflicts = _desired(active, incoming, new, set(), 'add', False)
    if schema_conflicts:
        conflicts.extend(dict(problem, modes=['add']) for problem in schema_conflicts)
    else:
        materialized, _, record_conflicts = _materialize_rows(desired, tables, incoming, 'add')
        conflicts.extend(dict(problem, modes=['add']) for problem in record_conflicts + _validate_rows(materialized, tables))
    registry = active.databases[DATABASES[0]]
    for name in ('client_bindings', 'agent_invitations'):
        table = registry.tables.get(name)
        if table:
            missing = {row.values['project'] for row in table.rows if row.values.get('project') and
                       row.values['project'] not in incoming.projects}
            if missing:
                conflicts.append(_problem('native-connection-project',
                    'Действующее подключение связано с проектом, которого нет в источнике полного восстановления.',
                    modes=['replace-all'], table=name, requiredProjects=sorted(missing)))
    return dict(activeHome=str(active.path), incomingHome=str(incoming.path),
                activeRevision=active.logical_revision, incomingRevision=incoming.logical_revision,
                storageSchemas=incoming.schemas, projects=projects, conflicts=conflicts,
                sameNames=same_names, globalChanges=global_changes,
                protectedTables=sorted(CONNECTION_TABLES), totalBytes=sum(file.stat().st_size for file in incoming.files.values()))


def preview(active, incoming):
    """Read-only comparison. Source formats must already be normalized to v2."""
    return _preview(_load_home(active), _load_home(incoming))


def _selection(active, incoming, mode, projects, resolutions):
    if mode not in ('add', 'replace-all'):
        raise MergeError('Выберите добавление проектов или полное восстановление.', code='invalid_storage_import')
    if projects is not None and (not isinstance(projects, (list, tuple, set)) or
                                 any(not isinstance(pid, str) for pid in projects) or len(set(projects)) != len(projects)):
        raise MergeError('Выберите проекты по их постоянным идентификаторам.', code='invalid_storage_import')
    chosen = set(incoming.projects if projects is None else projects)
    if not chosen <= incoming.projects.keys():
        raise MergeError('В исходном хранилище отсутствует выбранный проект.', code='invalid_storage_import')
    resolutions = {} if resolutions is None else resolutions
    if not isinstance(resolutions, dict) or not resolutions.keys() <= chosen:
        raise MergeError('Разрешения конфликтов должны относиться к выбранным проектам.', code='invalid_storage_import')
    if mode == 'replace-all':
        if (projects is not None and chosen != incoming.projects.keys()) or resolutions:
            raise MergeError('Полное восстановление включает все проекты исходного хранилища.', code='invalid_storage_import')
        return chosen, set(active.projects) & chosen, set(), set()
    imported, replaced, kept, skipped, conflicts = set(), set(), set(), set(), []
    aliases = {'keep': 'keep-current', 'replace-project': 'replace', 'skip': 'skip-identical'}
    for pid in sorted(chosen):
        decision = aliases.get(resolutions.get(pid), resolutions.get(pid))
        if decision not in (None, 'keep-current', 'replace', 'skip-identical', 'cancel'):
            raise MergeError('Неизвестный способ разрешения конфликта проекта.', code='invalid_storage_import')
        if pid not in active.projects:
            if decision not in (None, 'replace'):
                raise MergeError('Для нового проекта выберите добавление или снимите выбор.', code='invalid_storage_import')
            imported.add(pid)
        elif active.fingerprints[pid] == incoming.fingerprints[pid]:
            skipped.add(pid)
        elif decision == 'keep-current':
            kept.add(pid)
        elif decision == 'replace':
            imported.add(pid)
            replaced.add(pid)
        else:
            conflicts.append(_problem('project-id', 'Выберите, какую версию проекта сохранить.',
                                      project=pid, resolutions=['keep-current', 'replace', 'cancel']))
    if conflicts:
        raise MergeError('Разрешите конфликты выбранных проектов перед импортом.', conflicts=conflicts)
    return imported, replaced, kept, skipped


def _dependency_conflicts(active, incoming, imported, replaced, final_ids, mode):
    conflicts = []
    for pid in imported:
        for required in incoming.dependencies[pid]:
            if required not in final_ids:
                conflicts.append(_problem('project-dependency', 'Для выбранного проекта нужны данные связанного проекта.',
                                          project=pid, requiredProject=required))
            elif required not in imported and incoming.fingerprints.get(required) != active.fingerprints.get(required):
                conflicts.append(_problem('project-dependency-version',
                    'Версия связанного проекта отличается. Добавьте его в выбор и разрешите конфликт.',
                    project=pid, requiredProject=required))
    if mode == 'add':
        for pid in active.projects.keys() - replaced:
            for required in active.dependencies[pid] & replaced:
                if active.fingerprints[required] != incoming.fingerprints[required]:
                    conflicts.append(_problem('retained-project-dependency',
                        'Сохраняемый проект связан с заменяемой версией. Проверьте и импортируйте связанный набор вместе.',
                        project=pid, requiredProject=required))
    return conflicts


def _desired(active, incoming, imported, replaced, mode, import_globals):
    """Return records and schema origins; all effects remain in memory."""
    desired, tables, conflicts = {}, {}, []
    preserved = CONNECTION_TABLES | (frozenset() if import_globals else GLOBAL_TABLES)
    for name in set(active.databases) | set(incoming.databases):
        current, source = active.databases.get(name), incoming.databases.get(name)
        base = source if mode == 'replace-all' else current
        tables[name] = dict(base.tables) if base else {}
        selected = defaultdict(list)
        if current:
            for table_name, table in current.tables.items():
                if table_name in DERIVED_TABLES:
                    continue
                for row in table.rows:
                    retain = table_name in preserved or mode == 'add' and table_name not in GLOBAL_TABLES and (
                        table_name in META_TABLES or not row.anchors
                        or bool(row.anchors) and not row.anchors & replaced
                        or row.shared and bool(row.anchors - replaced))
                    if retain:
                        selected[table_name].append((row, current))
                if table_name in preserved:
                    tables[name][table_name] = table
        if source:
            for table_name, table in source.tables.items():
                if table_name in DERIVED_TABLES | preserved:
                    continue
                for row in table.rows:
                    include = (mode == 'replace-all' or bool(row.anchors & imported) or
                               table_name in META_TABLES and base is None or
                               import_globals and table_name in GLOBAL_TABLES or
                               name == DATABASES[1] and table_name == 'receipts' and not row.anchors and bool(imported))
                    if include:
                        selected[table_name].append((row, source))
                if selected.get(table_name) and table_name not in tables[name]:
                    tables[name][table_name] = table
        for table_name, entries in selected.items():
            target = tables[name][table_name]
            for row, _ in entries:
                if row.table.signature != target.signature:
                    conflicts.append(_problem('schema-conflict',
                        'Формат связанных записей отличается. Преобразуйте временные копии совместимой версией Hub.',
                        database=name, table=table_name, projects=sorted(row.anchors)))
                if row.table.sql.lstrip().upper().startswith('CREATE VIRTUAL TABLE'):
                    conflicts.append(_problem('unsupported-table', 'Импорт этого расширения требует совместимого обработчика.',
                                              database=name, table=table_name))
        desired[name] = selected
    return desired, tables, conflicts


def _materialize_rows(desired, tables, incoming, mode):
    """Append coordination sequences; permanent IDs and durable payloads stay intact."""
    result, mapping, conflicts = {}, {}, []
    for db_name, selected in desired.items():
        def source_origin(origin):
            return origin is incoming.databases.get(db_name)
        sequence = {}
        if db_name == DATABASES[1]:
            events = selected.get('events', [])
            current = {row.values['id']: row for row, origin in events if origin is not None and
                       not source_origin(origin)}
            source_database = incoming.databases.get(db_name)
            all_source_events = source_database.tables.get('events') if source_database else None
            # Stored delivery IDs contain their original sequence. Appended
            # future work must not reuse a number from either source history.
            top = max([row.values['seq'] for row in current.values()] +
                      ([row.values['seq'] for row in all_source_events.rows] if all_source_events else []) +
                      [source_database.sequences.get('events', 0) if source_database else 0])
            source_entries = sorted(((row, origin) for row, origin in events if source_origin(origin)),
                                    key=lambda pair: pair[0].values['seq'])
            for row, origin in source_entries:
                old = row.values['seq']
                previous = current.get(row.values['id'])
                if previous:
                    if _normal_row(origin, row) != _normal_row(next(db for rec, db in events if rec is previous), previous):
                        conflicts.append(_problem('record-id', 'Постоянный идентификатор события занят другой записью.',
                                                  database=db_name, table='events', record={'id': row.values['id']}))
                    sequence[old] = previous.values['seq']
                elif mode == 'replace-all' or not current:
                    sequence[old] = old
                else:
                    top += 1
                    sequence[old] = top
            if all_source_events:
                for row in all_source_events.rows:
                    if row.values['seq'] not in sequence and row.values['id'] in current:
                        sequence[row.values['seq']] = current[row.values['id']].values['seq']
            mapping = {str(old): new for old, new in sequence.items() if old != new}
        materialized = {}
        for table_name, entries in selected.items():
            table = tables[db_name][table_name]
            rows, primary_keys, unkeyed = [], {}, {}
            for row, origin in entries:
                values = dict(row.values)
                if db_name == DATABASES[1] and source_origin(origin):
                    if table_name == 'events':
                        values['seq'] = sequence[values['seq']]
                    elif table_name == 'work' and values.get('revision'):
                        old = values['revision']
                        if old not in sequence:
                            conflicts.append(_problem('coordination-sequence', 'Версия работы ссылается на отсутствующее событие.',
                                                      database=db_name, table=table_name, record=row.label()))
                        else:
                            values['revision'] = sequence[old]
                    elif table_name == 'sessions':
                        source_events = origin.tables.get('events')
                        old_cursor = values.get('last_cursor', 0)
                        acknowledged = [event.values['seq'] for event in source_events.rows
                                        if event.values['project'] == values['project'] and event.values['seq'] <= old_cursor] if source_events else []
                        values['last_cursor'] = max((sequence[seq] for seq in acknowledged if seq in sequence), default=0)
                    elif table_name == 'receipts':
                        value = json.loads(values['result'])
                        if isinstance(value, dict) and value.get('revision') in sequence:
                            value['revision'] = sequence[value['revision']]
                            values['result'] = _canonical(value)
                        elif isinstance(value, dict) and value.get('revision'):
                            conflicts.append(_problem('coordination-sequence',
                                'Сохранённый результат ссылается на отсутствующее событие.',
                                database=db_name, table=table_name, record=row.label()))
                    for foreign in table.foreign_keys:
                        if foreign[2] == 'events' and foreign[4] == 'seq' and values.get(foreign[3]) is not None:
                            old = row.values[foreign[3]]
                            if old in sequence:
                                values[foreign[3]] = sequence[old]
                            else:
                                conflicts.append(_problem('coordination-sequence',
                                    'Связанная запись ссылается на отсутствующее событие.',
                                    database=db_name, table=table_name, record=row.label()))
                primary = tuple(values[column] for column in table.primary) if table.primary else None
                if primary is not None and primary in primary_keys:
                    if primary_keys[primary] != values:
                        conflicts.append(_problem('record-id', 'Идентификатор общей записи занят другими данными.',
                                                  database=db_name, table=table_name, record=row.label(), projects=sorted(row.anchors)))
                    continue
                if primary is None:
                    key = _canonical(values)
                    occurrence = unkeyed.setdefault(key, dict(values=values, current=0, incoming=0))
                    occurrence['incoming' if source_origin(origin) else 'current'] += 1
                    continue
                if primary is not None:
                    primary_keys[primary] = values
                rows.append(values)
            for occurrence in unkeyed.values():
                rows.extend(dict(occurrence['values']) for _ in range(max(occurrence['current'], occurrence['incoming'])))
            materialized[table_name] = rows
        result[db_name] = materialized
    return result, mapping, conflicts


def _validate_rows(rows, tables):
    conflicts = []
    for db_name, catalog in tables.items():
        database = rows.get(db_name, {})
        for name, table in catalog.items():
            values = database.get(name, [])
            for keys, partial in table.unique:
                columns = [part[2] for part in keys]
                if partial or any(column is None for column in columns):
                    continue  # The isolated SQLite candidate validates these.
                seen = {}
                for row in values:
                    key = tuple(row[column] for column in columns)
                    if any(value is None for value in key):
                        continue
                    # Respect SQLite's built-in NOCASE collation for unique keys.
                    key = tuple(value.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))
                                if isinstance(value, str) and part[4] == 'NOCASE' else value
                                for value, part in zip(key, keys))
                    if key in seen:
                        conflicts.append(_problem('unique-record', 'Общая привязка или идентификатор заняты другой записью.',
                                                  database=db_name, table=name, fields=columns))
                        break
                    seen[key] = row
            groups = defaultdict(list)
            for foreign in table.foreign_keys:
                groups[foreign[0]].append(foreign)
            for foreign in groups.values():
                foreign.sort(key=lambda part: part[1])
                target_name = foreign[0][2]
                target = catalog.get(target_name)
                target_columns = [part[4] for part in foreign]
                if target and any(column is None for column in target_columns):
                    target_columns = target.primary
                valid = {tuple(row.get(column) for column in target_columns) for row in database.get(target_name, [])}
                for row in values:
                    key = tuple(row.get(part[3]) for part in foreign)
                    if not any(value is None for value in key) and key not in valid:
                        conflicts.append(_problem('missing-record-dependency',
                            'Сохраняемой записи нужны данные, которых нет в выбранном результате.',
                            database=db_name, table=name, parentTable=target_name,
                            nativeConnection=name in CONNECTION_TABLES))
                        break
    return conflicts


def _copy_files(home, stage, report):
    for completed, (name, original) in enumerate(sorted(home.files.items()), 1):
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in DATABASES:
            with _connect(original) as source, closing(sqlite3.connect(target)) as copied:
                source.backup(copied)
        else:
            shutil.copyfile(original, target)
            if digest(target) != home.proofs[name] or digest(original) != home.proofs[name]:
                raise MergeError('Исходные данные изменились во время подготовки. Повторите проверку.')
        report('copying', completed, len(home.files))


def _write_databases(stage, desired, tables, mode, import_globals):
    for db_name, catalog in tables.items():
        path = stage / db_name
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('PRAGMA foreign_keys=OFF')
            connection.execute('BEGIN IMMEDIATE')
            try:
                # Offline editing must not execute extension triggers against
                # protected credentials or unrelated project rows.
                triggers = list(connection.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='trigger'"))
                for name, _, _ in triggers:
                    connection.execute('DROP TRIGGER ' + _quoted(name))
                existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                # Current connection/settings schemas may be newer than the
                # source's. Rebuild preserved tables from their current schema.
                rebuilt = set()
                if mode == 'replace-all':
                    preserved = CONNECTION_TABLES | (frozenset() if import_globals else GLOBAL_TABLES)
                    for name in preserved & existing & catalog.keys():
                        connection.execute('DROP TABLE ' + _quoted(name))
                        existing.remove(name)
                        rebuilt.add(name)
                new = []
                for name, table in catalog.items():
                    if name not in existing:
                        connection.execute(table.sql)
                        new.append(table)
                for name in catalog:
                    connection.execute('DELETE FROM ' + _quoted(name))
                for name, values in desired.get(db_name, {}).items():
                    table = catalog[name]
                    columns = table.writable
                    statement = ('INSERT INTO ' + _quoted(name) + '(' + ','.join(map(_quoted, columns)) + ') VALUES(' +
                                 ','.join('?' for _ in columns) + ')')
                    connection.executemany(statement, [tuple(row[column] for column in columns) for row in values])
                if 'read_model_generation' in catalog:
                    connection.execute('INSERT INTO read_model_generation VALUES(1,0)')
                for table in new:
                    for kind, _, sql in table.objects:
                        if kind == 'index':
                            connection.execute(sql)
                for _, owner, sql in triggers:
                    if owner not in rebuilt:
                        connection.execute(sql)
                for table in new:
                    for kind, _, sql in table.objects:
                        if kind == 'trigger':
                            connection.execute(sql)
                if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise MergeError('Связи в подготовленном хранилище неполны. Проверьте выбор проектов.')
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')


def _install_instructions(home, stage, published):
    directory = stage / 'instructions'
    if directory.exists():
        shutil.rmtree(directory)
    for name, source in home.files.items():
        if _instruction_file(name) and not name.startswith('instructions/project-hub-user/'):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for name, source in home.instructions.items():
        target = directory / 'project-hub-user' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        proof = digest(source)
        shutil.copyfile(source, target)
        if digest(target) != proof or digest(source) != proof:
            raise MergeError('Сохранённые инструкции изменились во время подготовки. Повторите проверку.')
    if home.instruction_location:
        value = dict(home.instruction_location)
        value['root'] = str(published / 'instructions/project-hub-user')
        value.pop('packageRoot', None)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'location.json').write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def rebase_instructions(candidate, published_home):
    """Rebase only the copied instruction location before offline publication."""
    candidate, published = Path(candidate).resolve(), Path(published_home).resolve()
    no_reparse(candidate)
    location = candidate / 'instructions/location.json'
    if not location.is_file():
        return
    if not (candidate / 'instructions/project-hub-user/.project-hub-owned.json').is_file():
        raise MergeError('Подготовленное хранилище не содержит принадлежащих Hub инструкций.')
    value = json.loads(location.read_text(encoding='utf-8-sig'))
    value['root'] = str(published / 'instructions/project-hub-user')
    value.pop('packageRoot', None)
    location.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def build_candidate(active, incoming, output, mode='add', projects=None, resolutions=None, *,
                    import_globals=False, expected_active=None, expected_incoming=None,
                    published_home=None, progress=None, incoming_snapshot=None):
    """Create a new inactive data directory, or leave output absent on failure.

    `projects=None` selects every incoming project. Identical IDs are skipped;
    differing IDs require `resolutions={id: 'keep-current' | 'replace'}`. An
    explicit `import_globals=True` imports source settings and instructions in
    either mode; otherwise current global settings and instructions are retained.
    Connection tables and native data always remain current. expected_* are
    logical preview revisions.
    """
    destination = Path(output).expanduser().resolve()
    no_reparse(output)
    active_home = _load_home(active)
    incoming_home = incoming_snapshot if incoming_snapshot is not None else _load_home(incoming)
    if incoming_home.path != Path(incoming).expanduser().resolve():
        raise MergeError('Проверенный источник не соответствует выбранной папке.', code='invalid_storage_import')
    for source in (active_home.path, incoming_home.path):
        if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
            raise MergeError('Подготовьте результат в новой отдельной папке.', code='invalid_storage_import')
    if destination.exists() or active_home.path == incoming_home.path or active_home.path.is_relative_to(incoming_home.path) or incoming_home.path.is_relative_to(active_home.path):
        raise MergeError('Исходное, рабочее и подготовленное хранилища должны находиться в отдельных папках.', code='invalid_storage_import')
    if not isinstance(import_globals, bool):
        raise MergeError('Явно выберите, импортировать ли общие настройки и инструкции.', code='invalid_storage_import')
    if expected_active is not None and expected_active != active_home.logical_revision:
        raise MergeError('Рабочие данные изменились после проверки. Повторите предварительный просмотр.', code='storage_revision_conflict')
    if expected_incoming is not None and expected_incoming != incoming_home.logical_revision:
        raise MergeError('Исходные данные изменились после проверки. Повторите предварительный просмотр.', code='storage_revision_conflict')
    imported, replaced, kept, skipped = _selection(active_home, incoming_home, mode, projects, resolutions)
    final_ids = set(incoming_home.projects) if mode == 'replace-all' else set(active_home.projects) | imported
    conflicts = list(incoming_home.issues)
    if len({pid.casefold() for pid in final_ids}) != len(final_ids):
        conflicts.append(_problem('path-alias', 'Выбранные проекты задают совпадающие папки данных.'))
    if mode == 'add':
        conflicts.extend(active_home.issues)
        conflicts.extend(row for row in _preview(active_home, incoming_home)['conflicts'] if row['type'] == 'ambiguous-global-data')
    conflicts.extend(_dependency_conflicts(active_home, incoming_home, imported, replaced, final_ids, mode))
    desired, tables, schema_conflicts = _desired(active_home, incoming_home, imported, replaced, mode, import_globals)
    conflicts.extend(schema_conflicts)
    if conflicts:
        raise MergeError('Выбранные данные нельзя импортировать без неполных или конфликтующих связей.', conflicts=conflicts)
    materialized, mapping, record_conflicts = _materialize_rows(desired, tables, incoming_home, mode)
    conflicts.extend(record_conflicts)
    conflicts.extend(_validate_rows(materialized, tables))
    if conflicts:
        raise MergeError('Выбранные данные нельзя импортировать без неполных или конфликтующих связей.', conflicts=conflicts)

    def report(phase, completed=0, total=0, **context):
        if progress is not None:
            progress(dict(phase=phase, completed=completed, total=total, **context))

    report('preparing')
    destination.parent.mkdir(parents=True, exist_ok=True)
    base = incoming_home if mode == 'replace-all' else active_home
    with tempfile.TemporaryDirectory(prefix='.hub-merge-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'data'
        stage.mkdir()
        _copy_files(base, stage, report)
        if mode == 'add':
            project_files = sum(name.startswith('projects/' + pid + '/')
                                for pid in imported for name in incoming_home.files)
            copied_files = 0
            report('copying', 0, project_files, unit='files', step='import-project-files')
            for pid in sorted(imported):
                directory = stage / 'projects' / pid
                if directory.exists():
                    shutil.rmtree(directory)
                for name, original in incoming_home.files.items():
                    if name.startswith('projects/' + pid + '/'):
                        target = stage / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(original, target)
                        if digest(target) != incoming_home.proofs[name] or digest(original) != incoming_home.proofs[name]:
                            raise MergeError('Исходный проект изменился во время подготовки. Повторите проверку.')
                        copied_files += 1
                        report('copying', copied_files, project_files, unit='files',
                               step='import-project-files', currentFile=name)
        else:
            # Native secrets normally live outside the data home. Recognized
            # installation-owned trees in an older home also remain current.
            for name in PROTECTED_DIRECTORIES:
                directory = stage / name
                if directory.exists():
                    shutil.rmtree(directory)
            for name, original in active_home.files.items():
                if _protected_file(name):
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(original, target)
                    if digest(target) != active_home.proofs[name]:
                        raise MergeError('Действующие подключения изменились во время подготовки.')
        report('merging')
        try:
            _write_databases(stage, materialized, tables, mode, import_globals)
        except sqlite3.Error as error:
            raise MergeError('Не удалось согласовать связанные записи. Проверьте конфликты и формат источника.',
                             conflicts=[_problem('database-contract', 'Связанные записи нарушают ограничения базы данных.',
                                                 detail=str(error)[:200])]) from error
        _install_instructions(incoming_home if import_globals else active_home,
                              stage, Path(published_home).resolve() if published_home is not None else destination)
        report('verifying')
        candidate = _load_home(stage)
        if candidate.issues or set(candidate.projects) != final_ids:
            raise MergeError('Подготовленное хранилище не соответствует выбранному набору проектов.', conflicts=candidate.issues)
        for pid in final_ids:
            expected = incoming_home if pid in imported else active_home
            if candidate.fingerprints[pid] != expected.fingerprints[pid]:
                raise MergeError('Связанные данные проекта изменились при подготовке. Импорт отменён.',
                                 conflicts=[_problem('candidate-project-mismatch',
                                     'Подготовленный проект не совпадает с выбранной версией.', project=pid)])
        for name, database in active_home.databases.items():
            for table_name, table in database.tables.items():
                if table_name in CONNECTION_TABLES or not import_globals and table_name in GLOBAL_TABLES:
                    actual = candidate.databases.get(name)
                    actual_table = actual.tables.get(table_name) if actual else None
                    if not actual_table or sorted((row.values for row in actual_table.rows), key=_canonical) != sorted((row.values for row in table.rows), key=_canonical):
                        raise MergeError('Подготовка изменила сохраняемые подключения или общие настройки. Импорт отменён.')
        if revision(active_home.path) != active_home.logical_revision or revision(incoming_home.path) != incoming_home.logical_revision:
            raise MergeError('Данные изменились во время подготовки. Повторите предварительный просмотр.', code='storage_revision_conflict')
        # No partially built output is exposed. Original inputs and all their
        # content remain available even when verification or rename fails.
        if destination.exists():
            raise MergeError('Папка назначения появилась во время подготовки. Выберите другую папку.')
        stage.rename(destination)
    report('prepared', 1, 1)
    return dict(path=str(destination), active=False, mode=mode, projectCount=len(candidate.projects),
                projects=[candidate.projects[pid] for pid in sorted(candidate.projects)],
                storageSchemas=candidate.schemas, activeRevision=active_home.logical_revision,
                incomingRevision=incoming_home.logical_revision, candidateRevision=candidate.logical_revision,
                added=sorted(imported - replaced), replaced=sorted(replaced), kept=sorted(kept),
                skipped=sorted(skipped), removed=sorted(active_home.projects.keys() - final_ids),
                importedGlobals=import_globals, sequenceRemapping=mapping)
