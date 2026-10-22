"""Whole-project import preservation on disposable, independent data homes."""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry
from plugin_api import ServerHub
from knowledge_store import KnowledgeStore
from artifact_store import publish, resolve
from agent_bindings import Connections
from hub_backup import BackupError, _files, create_archive, digest, restore_copy
from hub_instructions import Instructions
from native_chats import register as register_chat, linked as linked_chats
from project_settings import read_settings, update_settings
from storage_merge import MergeError, _hash, _read_database, build_candidate, preview, revision, rebase_instructions


class StorageMergeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hub-storage-merge-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registries = []

    def home(self, name, projects=()):
        registry = ProjectRegistry(self.root / name, standalone=True)
        self.registries.append(registry)
        self.addCleanup(registry.close_connection_pool)
        with registry.connect() as connection:
            for pid, title in projects:
                connection.execute('''INSERT INTO spaces(id,codex_id,name,roots,present,updated,ownership)
                                      VALUES(?,NULL,?,'[]',1,10,'hub')''', (pid, title))
        for pid, _ in projects:
            registry.base_store(pid)
        return registry

    def task(self, registry, pid, title='Initial work'):
        store = registry.store(pid)
        tid = 'task-' + pid
        store.record(dict(kind='task.created', taskId=tid, title=title,
            patch=dict(title=title, status='active', createdBy=dict(project=pid, session='chat-' + pid),
                       stages=[dict(id='stage-1', title='First stage', status='planned')])))
        store.record(dict(kind='note', taskId=tid, title='Historical note', detail='Saved original history'))
        return store, tid

    def rich_project(self, registry, pid, title='Initial work'):
        store, tid = self.task(registry, pid, title)
        knowledge = KnowledgeStore(registry, pid)
        knowledge.changeset(0, 'document-' + pid, [dict(op='put', item=dict(id='doc:guide', kind='document',
            title='Guide', body='Original document'))], 'Keep the original', task=tid)
        knowledge.changeset(1, 'document-update-' + pid, [dict(op='put', item=dict(id='doc:guide', kind='document',
            title='Guide', body='Revised document')),
            dict(op='put', item=dict(id='component:main', kind='entity', type='component', title='Main component'))],
            'Preserve document versions and architecture', task=tid)
        first = publish(store, 'résultat.txt', b'first artifact version')
        store.record(dict(kind='task.updated', taskId=tid, title='Register the first immutable version',
                          patch=dict(sources=[first['source']])))
        latest = publish(store, 'résultat.txt', b'second artifact version', previous=first['source']['path'])
        store.record(dict(kind='task.updated', taskId=tid, title='Attach immutable versions',
                          patch=dict(sources=[first['source'], latest['source']])))
        register_chat(registry, pid, 'saved-actor', dict(client='example-agent', nativeId='native-chat-' + pid),
                      task=tid, stage='stage-1')
        hub = ServerHub(registry)
        with hub.connect() as connection:
            connection.execute('INSERT INTO projects VALUES(?,NULL,NULL)', (pid,))
            connection.execute('''INSERT INTO sessions(id,project,workspace,state,seen,task)
                                  VALUES(?,?,NULL,'idle',20,?)''', ('session-' + pid, pid, tid))
            connection.execute('''INSERT INTO work(id,project,session,task,title,status,revision,created,updated)
                                  VALUES(?,?,?,?,?,'done',0,20,21)''',
                               ('work-' + pid, pid, 'session-' + pid, tid, 'Saved result'))
            sequence = connection.execute('''INSERT INTO events(id,project,session,kind,work,at,body)
                                             VALUES(?,?,?,'work.done',?,21,'{"result":"Done"}')''',
                                          ('event-' + pid, pid, 'session-' + pid, 'work-' + pid)).lastrowid
            connection.execute('UPDATE work SET revision=? WHERE id=?', (sequence, 'work-' + pid))
            connection.execute('UPDATE sessions SET last_cursor=? WHERE id=?', (sequence, 'session-' + pid))
            connection.execute('INSERT INTO claims VALUES(?,\'guide.txt\',\'read\')', ('work-' + pid,))
            connection.execute('INSERT INTO work_stages VALUES(?,\'stage-1\')', ('work-' + pid,))
            connection.execute('INSERT INTO work_stage_links VALUES(?,\'stage-1\')', ('work-' + pid,))
            connection.execute('INSERT INTO session_agents VALUES(?,\'native-parent\',\'agent/reviewer\',\'Review\',\'reviewer\')',
                               ('session-' + pid,))
            connection.execute('INSERT INTO receipts VALUES(?,\'original-request-hash\',?)',
                               ('receipt-' + pid, json.dumps(dict(work='work-' + pid, revision=sequence, status='done'))))
            payload = dict(id='pending-note-' + pid, kind='note', taskId=tid, title='Pending delivery', detail='Keep delivery exactly')
            connection.execute('INSERT INTO plan_outbox VALUES(?,?,?)', (payload['id'], pid, json.dumps(payload)))
        data = registry.home / 'projects' / pid
        (data / 'opaque-history.bin').write_bytes(b'\x00saved opaque project data\xff')
        settings_store = registry.base_store(pid)
        update_settings(settings_store, {'viewer': {'showSourceDetails': True}}, read_settings(settings_store)['revision'])
        return latest['source']['path']

    def globals(self, registry, label):
        with registry.connect() as connection:
            connection.execute('CREATE TABLE agent_instruction_settings(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL)')
            connection.execute('INSERT INTO agent_instruction_settings VALUES(1,?)',
                               (json.dumps(dict(text=label, history=[dict(previousText='Previous rules')])),))
        instructions = Instructions(registry.home)
        external = self.root / ('client-' + label) / 'skills/project-hub-user'
        original = instructions.initialize(external)
        instructions.update(original['revision'], dict(userInstructions='User preference ' + label))
        (external / 'helper.txt').write_text('Owned companion ' + label, encoding='utf-8')
        (external / 'runtime').mkdir()
        (external / 'runtime/helper.txt').write_text('Owned nested companion', encoding='utf-8')
        return external

    def connections(self, registry, label, project=None):
        Connections(registry).setup()
        with registry.connect() as connection:
            connection.execute('''INSERT INTO agent_connections(id,client,external_id,metadata,updated,token_hash)
                                  VALUES(?,\'example-client\',?,\'{}\',20,?)''', (label, 'external-' + label, 'secret-' + label))
            connection.execute('CREATE TABLE agent_provider_settings(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL)')
            connection.execute('INSERT INTO agent_provider_settings VALUES(1,?)',
                               (json.dumps(dict(version=1, default='none', items=[], fixtureLabel=label)),))
            connection.execute('CREATE TABLE connection_profiles(binding TEXT PRIMARY KEY,body TEXT NOT NULL,revision TEXT NOT NULL,updated REAL NOT NULL)')
            connection.execute('INSERT INTO connection_profiles VALUES(?,\'{}\',\'profile-revision\',20)', (label,))
            if project:
                connection.execute('INSERT INTO client_bindings VALUES(?,?,\'legacy-client\',?,\'{}\',20)',
                                   ('legacy-' + label, project, 'legacy-external-' + label))
                connection.execute('INSERT INTO agent_access VALUES(?,?,0)', ('legacy-' + label, 'legacy-secret-' + label))
        private = registry.home / 'private/provider-credentials.json'
        private.parent.mkdir()
        private.write_text('private-' + label, encoding='utf-8')

    def rows(self, home, table, database='registry.sqlite3'):
        with closing(sqlite3.connect(Path(home) / database)) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute('SELECT * FROM "' + table + '" ORDER BY rowid')]

    def proofs(self, home):
        return {name: digest(file) for name, file in _files(home).items()}

    def clone(self, registry, name):
        destination = self.root / name
        destination.mkdir()
        for path_name, original in _files(registry.home).items():
            target = destination / path_name
            target.parent.mkdir(parents=True, exist_ok=True)
            if path_name in ('registry.sqlite3', 'coordination/coordination.sqlite3'):
                with closing(sqlite3.connect(original)) as source, closing(sqlite3.connect(target)) as copied:
                    source.backup(copied)
            else:
                shutil.copyfile(original, target)
        return destination

    def test_add_preserves_full_project_content_histories_chat_links_and_current_globals(self):
        current = self.home('current', [('north', 'Same title')])
        source = self.home('source', [('south', 'Same title')])
        current_artifact = self.rich_project(current, 'north')
        source_artifact = self.rich_project(source, 'south')
        current_skill = self.globals(current, 'current')
        source_skill = self.globals(source, 'source')
        self.connections(current, 'current')
        self.connections(source, 'source')
        before_current, before_source = self.proofs(current.home), self.proofs(source.home)
        comparison = preview(current.home, source.home)
        self.assertEqual('new', comparison['projects'][0]['status'])
        self.assertEqual([dict(name='Same title', currentProject='north', incomingProject='south')], comparison['sameNames'])
        self.assertFalse(comparison['conflicts'])
        output = self.root / 'candidate'
        result = build_candidate(current.home, source.home, output, expected_active=comparison['activeRevision'],
                                 expected_incoming=comparison['incomingRevision'])
        self.assertFalse(result['active'])
        self.assertEqual(['south'], result['added'])
        self.assertEqual({'north', 'south'}, {row['id'] for row in self.rows(output, 'spaces')})
        for registry, pid in ((current, 'north'), (source, 'south')):
            originals = {name: proof for name, proof in self.proofs(registry.home).items() if name.startswith('projects/' + pid + '/')}
            actual = {name: proof for name, proof in self.proofs(output).items() if name.startswith('projects/' + pid + '/')}
            self.assertEqual(originals, actual)
            for name in ('knowledge_items', 'knowledge_changes', 'knowledge_meta', 'native_chat_links'):
                self.assertEqual([row for row in self.rows(registry.home, name) if row.get('project') == pid],
                                 [row for row in self.rows(output, name) if row.get('project') == pid])
        for table in ('claims', 'work_stages', 'work_stage_links', 'session_agents', 'plan_outbox'):
            self.assertEqual(self.rows(current.home, table, 'coordination/coordination.sqlite3') +
                             self.rows(source.home, table, 'coordination/coordination.sqlite3'),
                             self.rows(output, table, 'coordination/coordination.sqlite3'))
        self.assertEqual(self.rows(current.home, 'agent_connections'), self.rows(output, 'agent_connections'))
        self.assertEqual(self.rows(current.home, 'agent_provider_settings'), self.rows(output, 'agent_provider_settings'))
        self.assertEqual(self.rows(current.home, 'connection_profiles'), self.rows(output, 'connection_profiles'))
        self.assertEqual(self.rows(current.home, 'agent_instruction_settings'), self.rows(output, 'agent_instruction_settings'))
        self.assertEqual('private-current', (output / 'private/provider-credentials.json').read_text())
        self.assertEqual((current_skill / 'SKILL.md').read_bytes(), (output / 'instructions/project-hub-user/SKILL.md').read_bytes())
        self.assertEqual(before_current, self.proofs(current.home))
        self.assertEqual(before_source, self.proofs(source.home))
        self.assertEqual('Owned companion source', (source_skill / 'helper.txt').read_text())
        self.assertEqual(str(output / 'instructions/project-hub-user'), json.loads((output / 'instructions/location.json').read_text())['root'])
        # Read the published candidate through actual domain adapters after all
        # preservation assertions; startup may refresh derived caches/outboxes.
        candidate = ProjectRegistry(output, standalone=True)
        self.addCleanup(candidate.close_connection_pool)
        for pid, reference in (('north', current_artifact), ('south', source_artifact)):
            self.assertEqual(b'second artifact version', resolve(candidate.store(pid), reference)[1])
            self.assertEqual('doc:guide', KnowledgeStore(candidate, pid).read('doc:guide')['id'])
            self.assertEqual('native-chat-' + pid, linked_chats(candidate, pid)[0]['resource']['nativeId'])

    def test_add_rebases_local_event_counters_and_their_references(self):
        current = self.home('current', [('north', 'North')])
        source = self.home('source', [('south', 'South')])
        self.rich_project(current, 'north')
        self.rich_project(source, 'south')
        output = self.root / 'candidate'
        result = build_candidate(current.home, source.home, output)
        events = self.rows(output, 'events', 'coordination/coordination.sqlite3')
        self.assertEqual(['event-north', 'event-south'], [row['id'] for row in events])
        self.assertEqual(2, len({row['seq'] for row in events}))
        imported_sequence = next(row['seq'] for row in events if row['id'] == 'event-south')
        self.assertGreater(imported_sequence, 1)
        self.assertEqual(imported_sequence, next(row['revision'] for row in self.rows(output, 'work', 'coordination/coordination.sqlite3') if row['id'] == 'work-south'))
        self.assertEqual(imported_sequence, next(row['last_cursor'] for row in self.rows(output, 'sessions', 'coordination/coordination.sqlite3') if row['id'] == 'session-south'))
        receipt = next(row for row in self.rows(output, 'receipts', 'coordination/coordination.sqlite3') if row['id'] == 'receipt-south')
        self.assertEqual(imported_sequence, json.loads(receipt['result'])['revision'])
        self.assertEqual({'1': imported_sequence}, result['sequenceRemapping'])
        self.assertEqual('identical', next(row for row in preview(output, source.home)['projects'] if row['id'] == 'south')['status'])

    def test_identical_ids_are_skipped_and_different_ids_require_a_whole_project_choice(self):
        current = self.home('current', [('same', 'Shared')])
        self.rich_project(current, 'same')
        source_home = self.clone(current, 'source')
        self.assertEqual('identical', preview(current.home, source_home)['projects'][0]['status'])
        output = self.root / 'identical'
        result = build_candidate(current.home, source_home, output)
        self.assertEqual(['same'], result['skipped'])
        self.assertEqual((current.home / 'projects/same/events.jsonl').read_bytes(), (output / 'projects/same/events.jsonl').read_bytes())
        source = ProjectRegistry(source_home, standalone=True)
        self.addCleanup(source.close_connection_pool)
        source.store('same').record(dict(kind='note', taskId='task-same', title='Additional source history', detail='Changed snapshot'))
        self.assertEqual('conflict', preview(current.home, source.home)['projects'][0]['status'])
        with self.assertRaises(MergeError) as caught:
            build_candidate(current.home, source.home, self.root / 'unresolved')
        self.assertEqual('project-id', caught.exception.conflicts[0]['type'])
        self.assertFalse((self.root / 'unresolved').exists())
        kept = self.root / 'kept'
        build_candidate(current.home, source.home, kept, resolutions={'same': 'keep-current'})
        self.assertEqual((current.home / 'projects/same/events.jsonl').read_bytes(), (kept / 'projects/same/events.jsonl').read_bytes())
        replaced = self.root / 'replaced'
        result = build_candidate(current.home, source.home, replaced, resolutions={'same': 'replace'})
        self.assertEqual(['same'], result['replaced'])
        self.assertEqual((source.home / 'projects/same/events.jsonl').read_bytes(), (replaced / 'projects/same/events.jsonl').read_bytes())
        self.assertEqual(self.rows(source.home, 'knowledge_changes'), self.rows(replaced, 'knowledge_changes'))

    def test_explicit_global_import_changes_rules_but_preserves_current_connections(self):
        current = self.home('current')
        source = self.home('source', [('south', 'South')])
        self.task(source, 'south')
        self.globals(current, 'current')
        source_skill = self.globals(source, 'source')
        self.connections(current, 'current')
        self.connections(source, 'source')
        output = self.root / 'candidate'
        result = build_candidate(current.home, source.home, output, import_globals=True)
        self.assertTrue(result['importedGlobals'])
        self.assertEqual(self.rows(source.home, 'agent_instruction_settings'), self.rows(output, 'agent_instruction_settings'))
        self.assertEqual((source_skill / 'SKILL.md').read_bytes(), (output / 'instructions/project-hub-user/SKILL.md').read_bytes())
        self.assertEqual(self.rows(current.home, 'agent_connections'), self.rows(output, 'agent_connections'))

    def test_replace_all_keeps_current_native_state_and_restores_all_other_data(self):
        current = self.home('current', [('shared', 'Current'), ('removed', 'Removed')])
        source = self.home('source', [('shared', 'Source'), ('added', 'Added')])
        self.rich_project(current, 'shared')
        self.task(current, 'removed')
        self.rich_project(source, 'shared', 'Source work')
        self.task(source, 'added')
        self.connections(current, 'current', 'shared')
        self.connections(source, 'source', 'shared')
        self.globals(current, 'current')
        source_skill = self.globals(source, 'source')
        with source.connect() as connection:
            connection.execute('CREATE TABLE opaque_global(id TEXT PRIMARY KEY,body TEXT)')
            connection.execute('INSERT INTO opaque_global VALUES(\'original-id\',\'Saved opaque record\')')
        (source.home / 'future-extension.json').write_text('{"preserved":true}', encoding='utf-8')
        output = self.root / 'candidate'
        current_proofs, source_proofs = self.proofs(current.home), self.proofs(source.home)
        result = build_candidate(current.home, source.home, output, mode='replace-all', import_globals=True)
        self.assertEqual(['removed'], result['removed'])
        self.assertEqual({'shared', 'added'}, {row['id'] for row in self.rows(output, 'spaces')})
        self.assertFalse((output / 'projects/removed').exists())
        for table in ('agent_connections', 'client_bindings', 'agent_access', 'agent_provider_settings', 'connection_profiles'):
            self.assertEqual(self.rows(current.home, table), self.rows(output, table))
        self.assertEqual(self.rows(source.home, 'opaque_global'), self.rows(output, 'opaque_global'))
        self.assertEqual(self.rows(source.home, 'agent_instruction_settings'), self.rows(output, 'agent_instruction_settings'))
        self.assertEqual('private-current', (output / 'private/provider-credentials.json').read_text())
        self.assertEqual((source_skill / 'SKILL.md').read_bytes(), (output / 'instructions/project-hub-user/SKILL.md').read_bytes())
        self.assertEqual('{"preserved":true}', (output / 'future-extension.json').read_text())
        self.assertEqual(current_proofs, self.proofs(current.home))
        self.assertEqual(source_proofs, self.proofs(source.home))
        self.assertEqual({}, result['sequenceRemapping'])

    def test_replace_all_imports_global_settings_and_instructions_only_with_explicit_opt_in(self):
        current = self.home('current', [('north', 'Current')])
        source = self.home('source', [('south', 'Source')])
        self.task(current, 'north')
        self.task(source, 'south')
        current_skill = self.globals(current, 'current')
        source_skill = self.globals(source, 'source')
        # Retaining current globals also retains their schema when the source
        # was written before a settings extension was introduced.
        with current.connect() as connection:
            connection.execute("ALTER TABLE agent_instruction_settings ADD COLUMN installation_note TEXT NOT NULL DEFAULT 'Current schema'")
        self.connections(current, 'current')
        self.connections(source, 'source')
        before_current, before_source = self.proofs(current.home), self.proofs(source.home)
        for import_globals in (False, True):
            with self.subTest(import_globals=import_globals):
                output = self.root / ('opt-in' if import_globals else 'default')
                result = build_candidate(current.home, source.home, output, mode='replace-all',
                                         import_globals=import_globals)
                chosen = source if import_globals else current
                skill = source_skill if import_globals else current_skill
                self.assertIs(result['importedGlobals'], import_globals)
                self.assertEqual({'south'}, {row['id'] for row in self.rows(output, 'spaces')})
                self.assertFalse((output / 'projects/north').exists())
                self.assertEqual((source.home / 'projects/south/events.jsonl').read_bytes(),
                                 (output / 'projects/south/events.jsonl').read_bytes())
                self.assertEqual(self.rows(chosen.home, 'agent_instruction_settings'),
                                 self.rows(output, 'agent_instruction_settings'))
                for name in ('SKILL.md', 'helper.txt', 'runtime/helper.txt'):
                    self.assertEqual((skill / name).read_bytes(), (output / 'instructions/project-hub-user' / name).read_bytes())
                self.assertEqual(str(output / 'instructions/project-hub-user'),
                                 json.loads((output / 'instructions/location.json').read_text())['root'])
                for table in ('agent_connections', 'client_bindings', 'agent_invitations', 'agent_access',
                              'agent_provider_settings', 'connection_profiles'):
                    self.assertEqual(self.rows(current.home, table), self.rows(output, table))
                self.assertEqual('private-current', (output / 'private/provider-credentials.json').read_text())
        self.assertEqual(before_current, self.proofs(current.home))
        self.assertEqual(before_source, self.proofs(source.home))

    def test_replace_all_reports_a_current_legacy_connection_to_a_removed_project(self):
        current = self.home('current', [('north', 'North')])
        source = self.home('source', [('south', 'South')])
        self.connections(current, 'current', 'north')
        comparison = preview(current.home, source.home)
        self.assertTrue(any(row['type'] == 'native-connection-project' for row in comparison['conflicts']))
        with self.assertRaises(MergeError) as caught:
            build_candidate(current.home, source.home, self.root / 'candidate', mode='replace-all')
        self.assertTrue(any(row['type'] == 'missing-record-dependency' and row.get('nativeConnection') for row in caught.exception.conflicts))
        self.assertFalse((self.root / 'candidate').exists())
        self.assertEqual('legacy-secret-current', self.rows(current.home, 'agent_access')[0]['token_hash'])

    def test_partial_selection_requires_transfer_and_evidence_dependencies(self):
        current = self.home('current')
        source = self.home('source', [('north', 'North'), ('south', 'South')])
        north_store, north_task = self.task(source, 'north')
        self.task(source, 'south')
        source_evidence = publish(north_store, 'guide.txt', b'Original cross-project guidance')['source']
        north_store.record(dict(kind='task.updated', taskId=north_task, title='Register shared guidance',
                                patch=dict(sources=[source_evidence])))
        with source.connect() as connection:
            owner = connection.execute('SELECT uid FROM task_owners WHERE origin=\'north\' AND task=\'task-north\'').fetchone()[0]
            connection.execute('UPDATE task_owners SET owner=\'south\' WHERE uid=?', (owner,))
            body = dict(uid=owner, source='north', target='south', task='task-north')
            connection.execute('INSERT INTO task_transfers VALUES(?, ?,\'north\',\'south\',\'2026-01-01T00:00:00Z\',\'fixture-user\',?)',
                               ('transfer-original-id', owner, json.dumps(body)))
        source.store('south').record(dict(kind='note', taskId='task-south', title='Cross-project evidence',
            evidence=[dict(source_evidence, sourceProject='north')]))
        comparison = preview(current.home, source.home)
        south = next(row for row in comparison['projects'] if row['id'] == 'south')
        self.assertIn('north', south['dependencies'])
        with self.assertRaises(MergeError) as caught:
            build_candidate(current.home, source.home, self.root / 'partial', projects=['south'])
        self.assertTrue(any(row.get('requiredProject') == 'north' for row in caught.exception.conflicts))
        output = self.root / 'complete'
        build_candidate(current.home, source.home, output, projects=['north', 'south'])
        self.assertEqual(self.rows(source.home, 'task_owners'), self.rows(output, 'task_owners'))
        self.assertEqual(self.rows(source.home, 'task_transfers'), self.rows(output, 'task_transfers'))
        candidate = ProjectRegistry(output, standalone=True)
        self.addCleanup(candidate.close_connection_pool)
        self.assertEqual(b'Original cross-project guidance',
                         candidate.store('south').evidence('hub-source/north/' + source_evidence['path']))

    def test_selected_project_can_reuse_an_identical_existing_dependency(self):
        current = self.home('current', [('north', 'North')])
        north_store, north_task = self.task(current, 'north')
        source_evidence = publish(north_store, 'history.md', b'Registered historical evidence')['source']
        north_store.record(dict(kind='task.updated', taskId=north_task, title='Register historical evidence',
                                patch=dict(sources=[source_evidence])))
        source_home = self.clone(current, 'source')
        source = ProjectRegistry(source_home, standalone=True)
        self.addCleanup(source.close_connection_pool)
        with source.connect() as connection:
            connection.execute('INSERT INTO spaces(id,name,roots,present,updated,ownership) VALUES(\'south\',\'South\',\'[]\',1,10,\'hub\')')
        self.task(source, 'south')
        # North retains its task and evidence ownership. A document may link
        # its source provenance without transferring that task to South.
        provenance = dict(source_evidence, sourceProject='north')
        knowledge = KnowledgeStore(source, 'south')
        knowledge.changeset(0, 'shared-history', [dict(op='put', item=dict(
            id='doc:shared-history', kind='document', title='Referenced history',
            markdown='The historical artifact remains owned by the source project.', sources=[provenance]))],
            'Link the unchanged source project', task='task-south')
        knowledge.flush_publication()
        comparison = preview(current.home, source.home)
        self.assertEqual('identical', next(row for row in comparison['projects'] if row['id'] == 'north')['status'])
        self.assertIn('north', next(row for row in comparison['projects'] if row['id'] == 'south')['dependencies'])
        output = self.root / 'candidate'
        result = build_candidate(current.home, source.home, output, projects=['south'])
        self.assertEqual(['south'], result['added'])
        self.assertEqual({'north', 'south'}, {row['id'] for row in self.rows(output, 'spaces')})
        candidate = ProjectRegistry(output, standalone=True)
        self.addCleanup(candidate.close_connection_pool)
        self.assertEqual(provenance, KnowledgeStore(candidate, 'south').read('doc:shared-history')['sources'][0])
        self.assertEqual(b'Registered historical evidence',
                         candidate.store('north').evidence(source_evidence['path']))

    def test_known_fk_extensions_and_duplicate_unkeyed_history_are_preserved(self):
        current = self.home('current')
        source = self.home('source', [('south', 'South')])
        with source.connect() as connection:
            connection.execute('CREATE TABLE project_notes(id TEXT PRIMARY KEY,space TEXT NOT NULL REFERENCES spaces(id),body TEXT)')
            connection.execute('INSERT INTO project_notes VALUES(\'note-original-id\',\'south\',\'Keep this record\')')
            connection.execute('CREATE TABLE repeated_history(project TEXT,detail TEXT)')
            connection.executemany('INSERT INTO repeated_history VALUES(\'south\',?)', [('Repeated event',), ('Repeated event',)])
        output = self.root / 'candidate'
        build_candidate(current.home, source.home, output)
        self.assertEqual(self.rows(source.home, 'project_notes'), self.rows(output, 'project_notes'))
        self.assertEqual(2, len(self.rows(output, 'repeated_history')))

    def test_unknown_shared_data_and_record_identity_collisions_are_visible_before_publication(self):
        current = self.home('current', [('north', 'North')])
        source = self.home('source', [('south', 'South')])
        with source.connect() as connection:
            connection.execute('CREATE TABLE ambiguous_records(id TEXT PRIMARY KEY,body TEXT)')
            connection.execute('INSERT INTO ambiguous_records VALUES(\'unknown\',\'Preserve but do not guess ownership\')')
        comparison = preview(current.home, source.home)
        conflict = next(row for row in comparison['conflicts'] if row['type'] == 'ambiguous-global-data')
        self.assertEqual('unknown', conflict['kind'])
        self.assertEqual('registry.sqlite3', conflict['database'])
        self.assertEqual('ambiguous_records', conflict['table'])
        with self.assertRaises(MergeError):
            build_candidate(current.home, source.home, self.root / 'ambiguous')
        self.assertFalse((self.root / 'ambiguous').exists())
        with source.connect() as connection:
            connection.execute('DROP TABLE ambiguous_records')
            connection.execute('UPDATE spaces SET codex_id=\'same-client-project\'')
        with current.connect() as connection:
            connection.execute('UPDATE spaces SET codex_id=\'same-client-project\'')
        self.assertTrue(any(row['type'] == 'unique-record' for row in preview(current.home, source.home)['conflicts']))
        with self.assertRaises(MergeError) as caught:
            build_candidate(current.home, source.home, self.root / 'identity-collision')
        self.assertTrue(any(row['type'] == 'unique-record' for row in caught.exception.conflicts))

    def test_known_local_metadata_is_retained_from_current_home_on_add(self):
        current = self.home('current')
        source = self.home('source', [('south', 'South')])
        names = ('coordination/migration-roots.json', 'language-servers.json', 'ui-preferences.json')
        for name in names:
            for home, value in ((current.home, 'current-'), (source.home, 'source-')):
                path = home / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value + name, encoding='utf-8')
        before_source = self.proofs(source.home)

        comparison = preview(current.home, source.home)
        self.assertFalse(any(row['type'] == 'ambiguous-global-data' for row in comparison['conflicts']))
        self.assertEqual(set(names), {row['path'] for row in comparison['globalChanges']})
        self.assertTrue(all(row['kind'] == 'local-metadata' for row in comparison['globalChanges']))
        output = self.root / 'candidate'
        build_candidate(current.home, source.home, output)
        for name in names:
            self.assertEqual('current-' + name, (output / name).read_text(encoding='utf-8'))
        self.assertEqual(before_source, self.proofs(source.home))
        # The actual legacy archive also contains files absent from the active
        # installation. Adding projects must not activate that metadata, even
        # when the user elects to import their global instruction settings.
        for name in names:
            (current.home / name).unlink()
        without_active_metadata = self.root / 'candidate-without-active-metadata'
        build_candidate(current.home, source.home, without_active_metadata, import_globals=True)
        for name in names:
            self.assertFalse((without_active_metadata / name).exists())
        self.assertEqual(before_source, self.proofs(source.home))

    def test_unknown_root_file_and_real_link_remain_rejected(self):
        current = self.home('current')
        source = self.home('source', [('south', 'South')])
        unknown = source.home / 'unknown-local.json'
        unknown.write_text('{}', encoding='utf-8')
        self.assertTrue(any(row['type'] == 'ambiguous-global-data' and row['path'] == 'unknown-local.json'
                            for row in preview(current.home, source.home)['conflicts']))
        with self.assertRaises(MergeError):
            build_candidate(current.home, source.home, self.root / 'unknown-file')
        link = source.home / 'linked-local.json'
        try:
            link.symlink_to(unknown)
        except OSError:
            self.skipTest('symbolic links unavailable on this Windows fixture')
        with self.assertRaises(BackupError):
            preview(current.home, source.home)

    def test_unknown_sqlite_views_are_reported_without_silently_dropping_the_extension(self):
        current = self.home('current')
        source = self.home('source', [('south', 'South')])
        with source.connect() as connection:
            connection.execute('CREATE VIEW extension_catalog AS SELECT id,name FROM spaces')
        before = self.proofs(source.home)
        comparison = preview(current.home, source.home)
        self.assertTrue(any(row['type'] == 'unsupported-schema-object' for row in comparison['conflicts']))
        for mode in ('add', 'replace-all'):
            with self.assertRaises(MergeError):
                build_candidate(current.home, source.home, self.root / mode, mode=mode)
            self.assertFalse((self.root / mode).exists())
        self.assertEqual(before, self.proofs(source.home))

    def test_revision_survives_sqlite_backup_owned_instruction_relocation_and_read_caches(self):
        current = self.home('current', [('north', 'North')])
        self.rich_project(current, 'north')
        self.globals(current, 'current')
        archive = self.root / 'snapshot.zip'
        create_archive(current, archive)
        original = revision(current.home)
        copied = Path(restore_copy(archive, self.root / 'restored', digest(archive))['path'])
        self.assertEqual(original, revision(copied))
        with current.connect() as connection:
            connection.execute('DELETE FROM read_model_views')
            connection.execute('UPDATE read_model_generation SET generation=generation+100')
        self.assertEqual(original, revision(current.home))
        current.store('north').record(dict(kind='note', taskId='task-north', title='New authoritative history'))
        self.assertNotEqual(original, revision(current.home))

    def test_read_database_skips_derived_cache_rows_but_keeps_durable_rows(self):
        source = self.home('source', [('south', 'South')])
        queries = []
        with source.connect() as connection:
            connection.execute('CREATE TABLE observation_cache(id INTEGER PRIMARY KEY, payload BLOB)')
            connection.execute('CREATE INDEX fixturecache_idx ON observation_cache(payload)')
            connection.execute('INSERT INTO observation_cache VALUES(1, ?)', (b'x' * 1024 * 1024,))
        expected_spaces = self.rows(source.home, 'spaces')

        import storage_merge
        real_connect = storage_merge._connect

        class TracedConnect:
            def __enter__(self):
                self.context = real_connect(source.home / 'registry.sqlite3')
                self.connection = self.context.__enter__()
                self.connection.set_trace_callback(queries.append)
                return self.connection

            def __exit__(self, *args):
                return self.context.__exit__(*args)

        with patch('storage_merge._connect', return_value=TracedConnect()):
            database = _read_database(source.home / 'registry.sqlite3', 'registry.sqlite3')

        self.assertEqual([], database.tables['observation_cache'].rows)
        self.assertEqual(expected_spaces, [row.values for row in database.tables['spaces'].rows])
        self.assertIn(('index', 'fixturecache_idx', 'CREATE INDEX fixturecache_idx ON observation_cache(payload)'),
                      database.tables['observation_cache'].objects)
        self.assertFalse(any('FROM "observation_cache"' in query for query in queries))

    def test_hash_streaming_preserves_canonical_json_digest(self):
        value = {
            'unicode': 'Привет 🌍',
            'blob': b'\x00\xff',
            'list': [1, -2, 3.5, None, True],
            'nested': {'z': 'é', 'a': 0},
        }
        # Captured from SHA-256 of the original canonical JSON bytes.
        self.assertEqual('ee4d922c1d84b0fc2617dbc99c591cf61e8c054d32f93e2df4c80baf737b32a3',
                         _hash(value))

    def test_expected_revisions_changed_inputs_failed_copy_and_unsafe_destinations_leave_sources_intact(self):
        current = self.home('current')
        source = self.home('source', [('south', 'South')])
        comparison = preview(current.home, source.home)
        self.task(source, 'south')
        before_current, before_source = self.proofs(current.home), self.proofs(source.home)
        with self.assertRaises(MergeError) as caught:
            build_candidate(current.home, source.home, self.root / 'stale', expected_incoming=comparison['incomingRevision'])
        self.assertEqual('storage_revision_conflict', caught.exception.code)
        with self.assertRaises(MergeError):
            build_candidate(current.home, source.home, source.home / 'inside')
        with patch('storage_merge.shutil.copyfile', side_effect=OSError('Fixture disk full')):
            with self.assertRaises(OSError):
                build_candidate(current.home, source.home, self.root / 'failed-copy')
        self.assertFalse((self.root / 'failed-copy').exists())
        self.assertFalse(list(self.root.glob('.hub-merge-*')))
        self.assertEqual(before_current, self.proofs(current.home))
        self.assertEqual(before_source, self.proofs(source.home))

    def test_damaged_cas_is_rejected_and_rebasing_does_not_write_native_instructions(self):
        current = self.home('current')
        source = self.home('source', [('south', 'South')])
        reference = self.rich_project(source, 'south')
        original_skill = self.globals(source, 'source')
        output = self.root / 'candidate'
        build_candidate(current.home, source.home, output, import_globals=True)
        native_before = (original_skill / 'SKILL.md').read_bytes()
        rebase_instructions(output, current.home)
        self.assertEqual(str(current.home / 'instructions/project-hub-user'), json.loads((output / 'instructions/location.json').read_text())['root'])
        self.assertEqual(native_before, (original_skill / 'SKILL.md').read_bytes())
        identifier = reference.split('/')[1]
        blob = source.home / 'projects/south/knowledge/blobs' / identifier[:2] / identifier
        blob.write_bytes(b'Corrupted descriptor bytes')
        with self.assertRaises(MergeError):
            preview(current.home, source.home)

    def test_old_schema_is_rejected_without_migrating_the_input(self):
        current = self.home('current')
        source = self.home('source')
        with source.connect() as connection:
            connection.execute('UPDATE registry_meta SET version=1')
        original = self.proofs(source.home)
        with self.assertRaises(MergeError) as caught:
            build_candidate(current.home, source.home, self.root / 'candidate')
        self.assertEqual('storage_upgrade_required', caught.exception.code)
        self.assertEqual(original, self.proofs(source.home))


if __name__ == '__main__':
    unittest.main()
