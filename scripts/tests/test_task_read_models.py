"""Derived source registrations retain current ownership and journal integrity."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import CodexProjects, ProjectRegistry
from task_transfer import transfer


class ReadModelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog = self.root / 'catalog.json'
        self.catalog.write_text(json.dumps({'local-projects': {
            name: {'id': name, 'name': name, 'rootPaths': [str(self.root / name)]}
            for name in ('one', 'two')}}), encoding='utf-8')
        self.registry = ProjectRegistry(self.root / 'data', CodexProjects(self.catalog))
        self.ids = {p['name']: p['id'] for p in self.registry.list()['projects']}
        self.view = self.registry.store(self.ids['one'])
        self.view.root.mkdir()
        (self.view.root / 'proof.txt').write_text('proof', encoding='utf-8')
        self.view.record({'kind': 'task.created', 'taskId': 'task', 'title': 'Task',
                          'patch': {'title': 'Task', 'status': 'active', 'stages': [],
                                    'sources': [{'path': 'proof.txt'}]}})

    def test_warm_source_authorization_uses_the_index_without_inventory(self):
        self.assertEqual(b'proof', self.view.evidence('proof.txt'))
        with patch('task_transfer.inventory', side_effect=AssertionError('full inventory is forbidden')):
            for _ in range(5):
                self.assertEqual(b'proof', self.view.evidence('proof.txt'))

    def test_warm_read_model_does_not_resolve_source_root(self):
        models = self.registry.read_models
        with patch('read_models.time.time', return_value=1800000000):
            models.snapshot(self.view, observations=False, summary=True)
            with patch.object(self.registry, 'base_store',
                              side_effect=AssertionError('warm read resolved source root')):
                warm = models.snapshot(self.view, observations=False, summary=True)
            self.assertEqual('Task', warm['tasks'][0]['title'])

            original_base_store = self.registry.base_store
            with patch.object(self.registry, 'base_store', wraps=original_base_store) as base_store:
                self.assertEqual(b'proof', self.view.evidence('proof.txt'))
                self.assertGreaterEqual(base_store.call_count, 1)

    def test_domain_keys_reuse_exact_committed_generation(self):
        models = self.registry.read_models
        owner = self.ids['one']
        domain = models.input_domain_key(owner)
        content = models.domain_key(owner)
        with patch.object(models, 'domain_inputs', side_effect=AssertionError('Repeated dependency scan')):
            self.assertEqual(domain, models.input_domain_key(owner))
            self.assertEqual(content, models.domain_key(owner))
        other = ProjectRegistry(self.root / 'data', CodexProjects(self.catalog))
        other.store(owner).record(dict(kind='note', taskId='task', title='Another process'))
        self.assertNotEqual(domain, models.input_domain_key(owner))
        self.assertNotEqual(content, models.domain_key(owner))
        self.assertEqual(models.domain_digest(models.domain_inputs(owner)), models.input_domain_key(owner))

    def test_domain_generation_covers_direct_dependencies_and_rollback(self):
        models = self.registry.read_models
        owner = self.ids['one']
        models.ensure_all()
        before = models.cached_domain_keys(owner)
        with self.registry.connect() as c:
            generation = c.execute('SELECT generation FROM read_model_generation').fetchone()[0]
            c.execute('BEGIN')
            c.execute('INSERT INTO completion_checkpoints VALUES(?,?,?,?,?,?,?,?,?)',
                      ('rolled-back', owner, owner, 'task', None, 'event', 'now', '{}', 'changed'))
            self.assertGreater(c.execute('SELECT generation FROM read_model_generation').fetchone()[0], generation)
            c.rollback()
            self.assertEqual(generation, c.execute('SELECT generation FROM read_model_generation').fetchone()[0])
        self.assertEqual(before, models.cached_domain_keys(owner))
        statements = [
            ('INSERT INTO completion_checkpoints VALUES(?,?,?,?,?,?,?,?,?)',
             ('checkpoint', owner, owner, 'task', None, 'event', 'now', '{}', 'one')),
            ("UPDATE completion_checkpoints SET result='two' WHERE id='checkpoint'", ()),
            ("DELETE FROM completion_checkpoints WHERE id='checkpoint'", ()),
            ('INSERT INTO task_transfers VALUES(?,?,?,?,?,?,?)',
             ('move', 'uid', owner, self.ids['two'], 'now', 'actor', '{}')),
            ("UPDATE task_transfers SET actor='another' WHERE request='move'", ()),
            ("DELETE FROM task_transfers WHERE request='move'", ()),
            ('INSERT INTO task_owners VALUES(?,?,?,?)', ('extra', owner, 'extra', owner)),
            ("UPDATE task_owners SET owner=? WHERE uid='extra'", (self.ids['two'],)),
            ("DELETE FROM task_owners WHERE uid='extra'", ()),
            ('UPDATE read_model_heads SET seed_hash=? WHERE project=?', (b'changed', owner)),
        ]
        for statement, parameters in statements:
            with self.subTest(statement=statement), self.registry.connect() as c:
                previous = models.cached_domain_keys(owner)
                c.execute(statement, parameters)
                self.assertGreater(c.execute('SELECT generation FROM read_model_generation').fetchone()[0], generation)
                generation = c.execute('SELECT generation FROM read_model_generation').fetchone()[0]
                fresh = models.domain_inputs(owner)
                self.assertEqual((models.domain_digest(fresh), models.content_digest(owner, fresh)),
                                 models.cached_domain_keys(owner))
                self.assertNotEqual(previous, models.cached_domain_keys(owner))

    def test_domain_generation_and_inputs_share_one_sql_snapshot(self):
        import threading
        models = self.registry.read_models
        owner = self.ids['one']
        models.ensure_all()
        before = models.cached_domain_keys(owner)
        models.domain_keys.clear()
        captured = threading.Event()
        changed = threading.Event()
        original = models.domain_inputs
        def inputs(*args, **kwargs):
            captured.set()
            self.assertTrue(changed.wait(5))
            return original(*args, **kwargs)
        errors = []
        def write():
            try:
                self.assertTrue(captured.wait(5))
                with self.registry.connect() as c:
                    c.execute('INSERT INTO completion_checkpoints VALUES(?,?,?,?,?,?,?,?,?)',
                              ('concurrent', owner, owner, 'task', None, 'event', 'now', '{}', 'changed'))
            except BaseException as error:
                errors.append(error)
            finally:
                changed.set()
        thread = threading.Thread(target=write)
        thread.start()
        try:
            with patch.object(models, 'domain_inputs', side_effect=inputs):
                self.assertEqual(before, models.cached_domain_keys(owner))
        finally:
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        self.assertNotEqual(before, models.cached_domain_keys(owner))

    def test_domain_cache_does_not_cross_database_replacement(self):
        import sqlite3
        models = self.registry.read_models
        owner = self.ids['one']
        models.ensure_all()
        before = models.cached_domain_keys(owner)
        replacement = self.root / 'replacement.sqlite3'
        with self.registry.connect() as c:
            generation = c.execute('SELECT generation FROM read_model_generation').fetchone()[0]
            target = sqlite3.connect(replacement, isolation_level=None)
            try:
                c.backup(target)
                target.execute('PRAGMA journal_mode=DELETE')
                target.execute('INSERT INTO completion_checkpoints VALUES(?,?,?,?,?,?,?,?,?)',
                               ('restored', owner, owner, 'task', None, 'event', 'now', '{}', 'changed'))
                # A restored branch can reuse an old generation number.
                target.execute('UPDATE read_model_generation SET generation=?', (generation,))
            finally:
                target.close()
        os.replace(replacement, self.registry.database)
        fresh = models.domain_inputs(owner)
        self.assertNotEqual(before, models.cached_domain_keys(owner))
        self.assertEqual((models.domain_digest(fresh), models.content_digest(owner, fresh)),
                         models.cached_domain_keys(owner))

    def test_ordinary_append_advances_local_detail_revision_without_mutating_origins(self):
        target = self.registry.store(self.ids['two'])
        with patch('read_models.time.time', return_value=1800000000):
            target.record({'kind': 'task.created', 'taskId': 'local', 'title': 'Local',
                           'patch': {'title': 'Local', 'status': 'active', 'stages': []}})
            target.record({'kind': 'task.created', 'taskId': 'localsibling',
                           'title': 'Local sibling',
                           'patch': {'title': 'Local sibling', 'status': 'active', 'stages': []}})
            preview = transfer(self.registry, self.ids['one'], self.ids['two'], 'task', preview=True)
            transfer(self.registry, self.ids['one'], self.ids['two'], 'task',
                     expected=preview['revision'], request='mixed-origin-detail')

            models = self.registry.read_models
            warm = models.snapshot(target, observations=False, summary=True)
            captured = models.views[target.project_id]
            with self.registry.connect() as connection:
                saved = {
                    row['task']: (row['body'], json.loads(row['body']))
                    for row in connection.execute(
                        'SELECT task,body FROM read_model_details WHERE project=?',
                        (target.project_id,))
                }
            self.assertIn('localsibling', saved)
            self.assertIn('task', saved)
            foreign_before = saved['task'][1].get('_sourceRevision')

            target.record({'kind': 'note', 'taskId': 'local', 'title': 'Local append'})
            old_full = models.decode_view(target, captured, observations=False, summary=False,
                                          task=None, tasks_only=False, complete_history=False)
            old_summary = models.decode_view(target, captured, observations=False, summary=True,
                                             task=None, tasks_only=False)
            old_tasks = models.decode_view(target, captured, observations=False, summary=False,
                                           task=None, tasks_only=True)
            old_sibling = models.decode_view(target, captured, observations=False, summary=False,
                                              task='localsibling', tasks_only=False)
            old_foreign = models.decode_view(target, captured, observations=False, summary=False,
                                              task='task', tasks_only=False)
            self.assertNotIn('_originRevisions', old_full)
            self.assertEqual(warm['revision'], old_full['revision'])
            self.assertEqual(warm['revision'], old_summary['revision'])
            self.assertEqual(warm['revision'], old_tasks['revision'])
            self.assertEqual(warm['revision'], old_sibling['revision'])
            self.assertEqual(warm['revision'], old_foreign['revision'])
            expected_revisions = {item['id']: item['_sourceRevision'] for item in warm['tasks']}
            for form in (old_full['tasks'], old_summary['tasks'], old_tasks['tasks'],
                         [old_sibling['task']], [old_foreign['task']]):
                self.assertEqual({item['id']: expected_revisions[item['id']] for item in form},
                                 {item['id']: item['_sourceRevision'] for item in form})
            summary = models.snapshot(target, observations=False, summary=True)
            tasks_only = models.snapshot(target, observations=False, tasks_only=True)
            sibling_detail = models.snapshot(target, observations=False, task='localsibling')
            foreign_detail = models.snapshot(target, observations=False, task='task')

        with self.registry.connect() as connection:
            target_revision = connection.execute(
                'SELECT journal_seq FROM read_model_heads WHERE project=?',
                (target.project_id,)).fetchone()[0]
            origin_revision = connection.execute(
                'SELECT journal_seq FROM read_model_heads WHERE project=?',
                (self.ids['one'],)).fetchone()[0]
            current = {
                row['task']: row['body']
                for row in connection.execute(
                    'SELECT task,body FROM read_model_details WHERE project=?',
                    (target.project_id,))
            }

        self.assertEqual(saved['localsibling'][0], current['localsibling'])
        self.assertEqual(saved['task'][0], current['task'])
        self.assertEqual(target_revision, sibling_detail['task']['_sourceRevision'])
        self.assertEqual(origin_revision, foreign_detail['task']['_sourceRevision'])
        self.assertEqual(foreign_before, foreign_detail['task']['_sourceRevision'])
        self.assertEqual(summary['revision'], tasks_only['revision'])
        self.assertEqual(summary['revision'], sibling_detail['revision'])
        self.assertEqual(summary['revision'], foreign_detail['revision'])
        summary_tasks = {item['id']: item for item in summary['tasks']}
        task_only_tasks = {item['id']: item for item in tasks_only['tasks']}
        self.assertEqual(summary_tasks['localsibling']['_sourceRevision'],
                         sibling_detail['task']['_sourceRevision'])
        self.assertEqual(summary_tasks['task']['_sourceRevision'],
                         foreign_detail['task']['_sourceRevision'])
        self.assertEqual(task_only_tasks['localsibling']['_sourceRevision'],
                         sibling_detail['task']['_sourceRevision'])
        self.assertEqual(task_only_tasks['task']['_sourceRevision'],
                         foreign_detail['task']['_sourceRevision'])

    def test_index_survives_registry_restart(self):
        self.view.evidence('proof.txt')
        restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        with patch('task_transfer.inventory', side_effect=AssertionError('full inventory is forbidden')):
            self.assertEqual(b'proof', restarted.store(self.ids['one']).evidence('proof.txt'))

    def test_view_version_upgrade_rebuilds_page_without_replaying_origin_index(self):
        models = self.registry.read_models
        view_type = type(models)
        with patch.object(view_type, 'VIEW_VERSION', 4), \
             patch('read_models.time.time', return_value=1800000000):
            previous = models.snapshot(self.view, observations=False, summary=True)
            previous_hint = models.hint(self.view)
        self.assertIsInstance(previous_hint, dict)
        models.views.clear()

        with patch('read_models.time.time', return_value=1800000000), \
             patch.object(self.view, '_build_snapshot', wraps=self.view._build_snapshot) as build, \
             patch('task_transfer._origin_projection', side_effect=AssertionError('page upgrade replayed origin index')):
            upgraded = models.snapshot(self.view, observations=False, summary=True)
            upgraded_hint = models.hint(self.view)
        self.assertEqual(previous['tasks'], upgraded['tasks'])
        self.assertIsInstance(upgraded_hint, dict)
        self.assertEqual(1, build.call_count)

        with patch('read_models.time.time', return_value=1800000000), \
             patch.object(self.view, '_build_snapshot', side_effect=AssertionError('warm upgraded page rebuilt')):
            warm = models.snapshot(self.view, observations=False, summary=True)
        self.assertEqual(upgraded['tasks'], warm['tasks'])

    def test_captured_fragment_entry_keeps_first_append_revisions_after_second_task_append(self):
        models = self.registry.read_models
        with patch('read_models.time.time', return_value=1800000000):
            self.view.record({'kind': 'task.created', 'taskId': 'other', 'title': 'Other',
                              'patch': {'title': 'Other', 'status': 'active', 'stages': []}})
            models.snapshot(self.view, observations=False, summary=True)
            self.view.record({'kind': 'note', 'taskId': 'task', 'title': 'First append'})
            first = models.snapshot(self.view, observations=False, summary=True)
            captured = models.views[self.view.project_id]
            self.view.record({'kind': 'note', 'taskId': 'other', 'title': 'Second append'})

            old_forms = (
                models.decode_view(self.view, captured, observations=False, summary=False,
                                   task=None, tasks_only=False, complete_history=False),
                models.decode_view(self.view, captured, observations=False, summary=True,
                                   task=None, tasks_only=False),
                models.decode_view(self.view, captured, observations=False, summary=False,
                                   task=None, tasks_only=True),
                models.decode_view(self.view, captured, observations=False, summary=False,
                                   task='task', tasks_only=False),
                models.decode_view(self.view, captured, observations=False, summary=False,
                                   task='other', tasks_only=False),
            )
            self.assertNotIn('Second append', [event.get('title') for event in old_forms[0]['events']])
            expected = {task['id']: task['_sourceRevision'] for task in first['tasks']}
            for form in old_forms:
                tasks = form.get('tasks', [form['task']] if 'task' in form else [])
                self.assertEqual({task['id']: expected[task['id']] for task in tasks},
                                 {task['id']: task['_sourceRevision'] for task in tasks})
            self.assertNotIn('_originRevisions', old_forms[0])

            current = models.snapshot(self.view, observations=False, summary=True)
            restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
            self.addCleanup(restarted.close_connection_pool)
            fresh = restarted.read_models.snapshot(restarted.store(self.ids['one']),
                                                    observations=False, summary=True)
            self.assertEqual(current['revision'], fresh['revision'])
            self.assertEqual(current['tasks'], fresh['tasks'])
            self.assertIn('Second append', [event.get('title') for event in fresh['events']])

    def test_large_published_view_uses_blob_and_keeps_legacy_text_readable(self):
        from read_models import VIEW_BLOB, pack_view, unpack_view

        large_detail = 'detail-' * 2000
        with patch('read_models.time.time', return_value=1800000000):
            self.view.record({'kind': 'note', 'taskId': 'task', 'title': large_detail})
            original = self.registry.read_models.snapshot(self.view, observations=False, summary=True)
            with self.registry.connect() as connection:
                row = connection.execute(
                    'SELECT body,summary FROM read_model_views WHERE project=?',
                    (self.view.project_id,)).fetchone()
            self.assertIsInstance(row['body'], bytes)
            self.assertTrue(row['body'].startswith(VIEW_BLOB))
            self.assertEqual(original['events'], json.loads(unpack_view(row['body']))['events'])

            restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
            self.addCleanup(restarted.close_connection_pool)
            fresh = restarted.read_models.snapshot(restarted.store(self.ids['one']),
                                                    observations=False, summary=True)
            self.assertEqual(original['tasks'], fresh['tasks'])
            self.assertEqual(original['events'], fresh['events'])

            # A pre-compression installation may have persisted ordinary TEXT;
            # the current reader must continue to accept that representation.
            with restarted.connect() as connection:
                connection.execute('UPDATE read_model_views SET body=?,summary=? WHERE project=?',
                                   (unpack_view(row['body']), unpack_view(row['summary']),
                                    self.view.project_id))
            legacy = restarted.read_models.snapshot(restarted.store(self.ids['one']),
                                                    observations=False, summary=True)
            self.assertEqual(original['events'], legacy['events'])

            restarted_view = restarted.store(self.ids['one'])
            restarted_view.record({'kind': 'note', 'taskId': 'task', 'title': 'after legacy'})
            advanced = restarted.read_models.snapshot(restarted_view, observations=False, summary=True)
            with restarted.connect() as connection:
                updated = connection.execute(
                    'SELECT body FROM read_model_views WHERE project=?',
                    (self.view.project_id,)).fetchone()['body']
            self.assertIsInstance(updated, bytes)
            self.assertTrue(updated.startswith(VIEW_BLOB))
            self.assertNotEqual(original['revision'], advanced['revision'])
            self.assertEqual('after legacy', advanced['events'][0]['title'])

            # A damaged derived row is a cache miss: it must rebuild from the
            # journal and must not poison the next ordinary append.
            with restarted.connect() as connection:
                damaged = connection.execute(
                    'SELECT body,summary FROM read_model_views WHERE project=?',
                    (self.view.project_id,)).fetchone()
                connection.execute(
                    'UPDATE read_model_views SET body=?,summary=? WHERE project=?',
                    (damaged['body'][:-1], damaged['summary'][:-1], self.view.project_id))
            restarted.read_models.views.clear()
            repaired = restarted.read_models.snapshot(restarted_view, observations=False, summary=True)
            self.assertEqual(advanced['events'], repaired['events'])
            with restarted.connect() as connection:
                damaged = connection.execute(
                    'SELECT body,summary FROM read_model_views WHERE project=?',
                    (self.view.project_id,)).fetchone()
                connection.execute(
                    'UPDATE read_model_views SET body=?,summary=? WHERE project=?',
                    (damaged['body'][:-1], damaged['summary'][:-1], self.view.project_id))
            restarted.read_models.views.clear()
            restarted_view.record({'kind': 'note', 'taskId': 'task', 'title': 'after corruption'})
            recovered = restarted.read_models.snapshot(restarted_view, observations=False, summary=True)
            self.assertEqual('after corruption', recovered['events'][0]['title'])

        encoded = pack_view('x' * 12000)
        self.assertIsInstance(encoded, bytes)
        for malformed in (VIEW_BLOB + b'broken', encoded[:-1], encoded + b'trailing'):
            with self.assertRaises(ValueError):
                unpack_view(malformed)

    def test_append_intent_remains_until_matching_head_publication(self):
        import hashlib
        models = self.registry.read_models
        original = models.appended
        prior = models.head(self.view.project_id)['journal_seq']
        seen = []
        def publish(project, before, after, tasks, event, **kwargs):
            with self.registry.connect() as connection:
                intent = connection.execute('SELECT event FROM journal_append_intents WHERE project=?', (project,)).fetchone()
                head = connection.execute('SELECT journal_seq FROM read_model_heads WHERE project=?', (project,)).fetchone()
            self.assertEqual(event['id'], intent[0])
            self.assertEqual(prior, head[0])
            seen.append(event['id'])
            return original(project,before,after,tasks,event,**kwargs)
        with patch.object(models,'appended',publish):
            self.view.record({'kind':'note','taskId':'task','title':'Published atomically'})
        with self.registry.connect() as connection:
            self.assertIsNone(connection.execute('SELECT 1 FROM journal_append_intents').fetchone())
            head = connection.execute('SELECT journal_seq,journal_hash FROM read_model_heads WHERE project=?', (self.view.project_id,)).fetchone()
        self.assertEqual(1,len(seen))
        self.assertEqual(prior+1,head[0])
        self.assertEqual(hashlib.sha256(self.view.journal.read_bytes()).digest(),head[1])

    def test_append_publication_failure_recovers_once(self):
        with patch.object(self.registry.read_models,'appended',side_effect=RuntimeError('before SQL publication')):
            with self.assertRaisesRegex(RuntimeError,'before SQL publication'):
                self.view.record({'kind':'note','taskId':'task','title':'Recover publication'})
        with self.registry.connect() as connection:
            self.assertIsNotNone(connection.execute('SELECT 1 FROM journal_append_intents').fetchone())
        restarted = ProjectRegistry(self.root/'data',CodexProjects(self.catalog))
        store = restarted.store(self.ids['one'])
        store.memory_snapshot()
        store.memory_snapshot()
        with restarted.connect() as connection:
            self.assertIsNone(connection.execute('SELECT 1 FROM journal_append_intents').fetchone())
            self.assertEqual(1,connection.execute("SELECT COUNT(*) FROM read_model_events WHERE kind='note'").fetchone()[0])

    def test_recovery_consumes_semantic_intent_before_history_migration(self):
        with patch('journal_append.checkpoint',side_effect=lambda point: (_ for _ in ()).throw(RuntimeError('crash')) if point=='after_append' else None):
            with self.assertRaisesRegex(RuntimeError,'crash'):
                self.view.record({'kind':'task.updated','taskId':'task','title':'Finished','patch':{'status':'done'}})
        restarted = ProjectRegistry(self.root/'data',CodexProjects(self.catalog))
        store = restarted.store(self.ids['one'])
        first = store.memory_snapshot()
        second = store.memory_snapshot()
        self.assertEqual('done',second['tasks'][0]['status'])
        self.assertEqual(first['revision'],second['revision'])
        with restarted.connect() as connection:
            self.assertIsNone(connection.execute('SELECT 1 FROM journal_append_intents').fetchone())
            self.assertEqual(1,connection.execute("SELECT COUNT(*) FROM read_model_events WHERE kind='task.status_changed'").fetchone()[0])

    def test_recovery_publish_crash_keeps_semantic_migration_obligation(self):
        import journal_append
        with patch('journal_append.checkpoint',side_effect=lambda point: (_ for _ in ()).throw(RuntimeError('append crash')) if point=='after_append' else None):
            with self.assertRaisesRegex(RuntimeError,'append crash'):
                self.view.record({'kind':'task.updated','taskId':'task','title':'Finished','patch':{'status':'done'}})
        restarted = ProjectRegistry(self.root/'data',CodexProjects(self.catalog))
        with patch('journal_append.checkpoint',side_effect=lambda point: (_ for _ in ()).throw(RuntimeError('publication crash')) if point=='after_recovery_publish' else None):
            with self.assertRaisesRegex(RuntimeError,'publication crash'):
                journal_append.recover(restarted)
        with restarted.connect() as connection:
            self.assertIsNone(connection.execute('SELECT 1 FROM journal_append_intents').fetchone())
            self.assertEqual(0,connection.execute('SELECT version FROM read_model_heads WHERE project=?',(self.ids['one'],)).fetchone()[0])
        again = ProjectRegistry(self.root/'data',CodexProjects(self.catalog))
        state = again.store(self.ids['one']).memory_snapshot()
        self.assertEqual('done',state['tasks'][0]['status'])
        with again.connect() as connection:
            self.assertEqual(1,connection.execute("SELECT COUNT(*) FROM read_model_events WHERE kind='task.status_changed'").fetchone()[0])

    def test_another_registry_reuses_verified_journal_proof_but_detects_restored_mtime(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from task_transfer import _origin_signature
        restarted = ProjectRegistry(self.registry.home,CodexProjects(self.catalog))
        store = restarted.base_store(self.ids['one'])
        _,proof = restarted.read_models.file_proofs(self.ids['one'])
        if proof is None:
            self.skipTest('Filesystem does not provide a reusable change token')
        original_open = Path.open
        @contextmanager
        def no_read(path,*args,**kwargs):
            with original_open(path,*args,**kwargs) as stream:
                if path == store.journal:
                    def forbidden(*args):
                        raise AssertionError('Other worker rehashed an unchanged proven journal')
                    yield SimpleNamespace(fileno=stream.fileno,read=forbidden)
                else:
                    yield stream
        with patch.object(Path,'open',no_read):
            self.assertEqual(proof[1],_origin_signature(store)[1])
        before = store.journal.stat()
        changed = store.journal.read_bytes().replace(b'"title": "Task"',b'"title": "Edit"',1)
        store.journal.write_bytes(changed)
        os.utime(store.journal,ns=(before.st_atime_ns,before.st_mtime_ns))
        self.assertNotEqual(proof[1],_origin_signature(store)[1])

    def test_stale_captured_head_rechecks_published_proof_without_rehashing(self):
        reader = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        writer = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        self.addCleanup(reader.close_connection_pool)
        self.addCleanup(writer.close_connection_pool)
        reader_store = reader.store(self.ids['one'])
        writer_store = writer.store(self.ids['one'])
        reader_models = reader.read_models
        reader_models.snapshot(reader_store, observations=False, summary=True)
        captured = reader_models.pending_visibility(self.ids['one'], reader_store, capture=True)
        writer_store.record({'kind': 'note', 'taskId': 'task', 'title': 'Published proof reuse'})

        original_pending = reader_models.pending_visibility
        first = [True]
        def stale_once(project, store, *, capture=False):
            if first[0] and capture:
                first[0] = False
                return captured
            return original_pending(project, store, capture=capture)

        import hashlib
        real_sha256 = hashlib.sha256
        journal_bytes = reader_store.journal.read_bytes()
        seed_bytes = reader_store.data.joinpath('project.json').read_bytes()
        def reject_full_file_hash(value=b'', *args, **kwargs):
            if value in (journal_bytes, seed_bytes):
                raise AssertionError('full digest after proof recheck')
            return real_sha256(value, *args, **kwargs)
        with patch.object(reader_models, 'pending_visibility', side_effect=stale_once), \
             patch('file_freshness.hashlib.sha256', side_effect=reject_full_file_hash):
            reader_models.ensure_origin(self.ids['one'])
        current = reader_models.snapshot(reader_store, observations=False, summary=True)
        self.assertIn('Published proof reuse', [event.get('title') for event in current['events']])

    def test_warm_append_and_retry_do_not_parse_the_complete_journal(self):
        self.view.memory_tasks()
        from project_portal import Store
        event = {'kind':'note','taskId':'task','id':'indexed-write','title':'Indexed write'}
        with patch.object(Store, '_load', side_effect=AssertionError('journal replay during warm append')):
            first = self.view.record(event)
            self.assertEqual(first, self.view.record(event))
        self.assertEqual(1, sum(e['id'] == event['id'] for e in self.view.memory_snapshot()['allEvents']))

    def test_cold_base_writer_prepares_head_before_project_journal_lock(self):
        from contextlib import contextmanager
        from project_portal import Store
        with self.registry.connect() as c:
            c.execute('DELETE FROM read_model_heads WHERE project=?', (self.ids['one'],))
        original, held = Store.locked, set()
        @contextmanager
        def guarded(store):
            key = str(store.lockfile)
            if key in held:
                raise AssertionError('nested project journal OS lock')
            held.add(key)
            try:
                with original(store):
                    yield
            finally:
                held.remove(key)
        with patch.object(Store, 'locked', guarded):
            self.registry.base_store(self.ids['one']).record(
                {'kind':'note','taskId':'task','title':'Cold base writer'})

    def test_prepared_compact_projection_matches_complete_history_projection(self):
        for index in range(30):
            self.view.record({'kind':'note','taskId':'task','title':str(index),'detail':'detail '*400})
        prepared = self.registry.read_models.snapshot(self.view, observations=False, summary=True)
        complete = self.view._build_snapshot(observations=False)
        self.assertEqual(complete['events'], prepared['events'])
        self.assertEqual(complete['eventCount'], prepared['eventCount'])
        self.assertEqual(complete['mainTask'], prepared['mainTask'])
        self.assertEqual(complete['checks'], prepared['checks'])
        self.assertNotIn('_compactEvent', json.dumps(prepared['events']))

    def test_history_page_cache_is_private_and_changes_with_a_write(self):
        first = self.view.history('task')
        first['events'][0]['title'] = 'caller mutation'
        with patch.object(type(self.registry.read_models), '_history_uncached', side_effect=AssertionError('repeat SQL pagination')):
            reused = self.view.history('task')
        self.assertNotEqual('caller mutation',reused['events'][0]['title'])
        self.view.record({'kind':'note','taskId':'task','title':'New cached page'})
        self.assertEqual('New cached page',self.view.history('task')['events'][0]['title'])

    def test_ordinary_writes_advance_prepared_views_without_project_rebuild(self):
        from stage_operations import project_links
        models = self.registry.read_models
        with patch('read_models.time.time',return_value=1800000000):
            self.view.memory_tasks()
            with patch.object(self.view,'_build_snapshot',side_effect=AssertionError('prepared view rebuilt')):
                for event in (
                    dict(kind='task.updated',taskId='task',title='Summary',patch={'summary':'fresh summary'}),
                    dict(kind='note',taskId='task',title='New note',evidence=[{'path':'proof.txt'}]),
                ):
                    self.view.record(event)
                    prepared = models.snapshot(self.view,observations=False,complete_history=False)
                    detail = models.snapshot(self.view,observations=False,task='task')
                    self.assertEqual(prepared['tasks'][0],detail['task'])
            complete = self.view._build_snapshot(observations=False,compact_events=True)
            project_links(self.registry,self.view.project_id,complete)
        for key in ('tasks','revision','mainTask','events','eventCount','lastEventAt','checks','checkCount','relationsRevision'):
            self.assertEqual(complete[key],prepared[key],key)
        self.assertEqual('fresh summary',prepared['tasks'][0]['summary'])

    def test_transferred_task_ordinary_write_advances_current_owner_only(self):
        from stage_operations import project_links
        preview = transfer(self.registry,self.ids['one'],self.ids['two'],'task',preview=True)
        transfer(self.registry,self.ids['one'],self.ids['two'],'task',expected=preview['revision'],request='incremental-transfer')
        target = self.registry.store(self.ids['two'])
        with patch('read_models.time.time',return_value=1800000000):
            target.memory_tasks()
            with patch.object(target,'_build_snapshot',side_effect=AssertionError('transferred view rebuilt')):
                target.record(dict(kind='task.updated',taskId='task',title='Summary',patch={'summary':'owned by two'}))
                result = self.registry.read_models.snapshot(target,observations=False,task='task')
            complete = target._build_snapshot(observations=False,compact_events=True)
            project_links(self.registry,target.project_id,complete)
        self.assertEqual(complete['tasks'][0],result['task'])
        self.assertEqual(self.ids['one'],result['task']['originProject'])
        self.assertEqual([],self.view.memory_tasks()['tasks'])

    def test_append_capture_reuses_only_exact_persisted_blobs(self):
        from read_models import pack_view, unpack_view
        models = self.registry.read_models
        with patch('read_models.time.time', return_value=1800000000):
            self.view.memory_tasks()
            self.view.record(dict(kind='note', taskId='task', title='Warm immutable page'))
            event = dict(kind='task.updated', taskId='task', patch={'summary':'Next'})
            with patch('read_models.unpack_view', side_effect=AssertionError('Repeated decompression')):
                captured = models.capture_append_view(self.ids['one'], event)
            self.assertIsNotNone(captured)
            with self.registry.connect() as c:
                row = c.execute('SELECT summary FROM read_model_views WHERE project=?', (self.ids['one'],)).fetchone()
                changed = json.loads(unpack_view(row[0]))
                changed['replacedPage'] = True
                c.execute('UPDATE read_model_views SET summary=? WHERE project=?',
                          (pack_view(json.dumps(changed)), self.ids['one']))
            replacement = models.capture_append_view(self.ids['one'], event)
            self.assertTrue(json.loads(replacement[1]['summary'])['replacedPage'])
            with self.registry.connect() as c:
                c.execute('UPDATE read_model_views SET summary=? WHERE project=?', (b'corrupt', self.ids['one']))
            self.assertIsNone(models.capture_append_view(self.ids['one'], event))

    def test_seed_digest_reuse_detects_restored_timestamp_change_before_append(self):
        seed_path = self.view.data / 'project.json'
        original = seed_path.read_bytes()
        stamp = seed_path.stat()
        changed = original.replace(b'"one"', b'"two"', 1)
        self.assertNotEqual(original, changed)
        journal = self.view.journal.read_bytes()
        def interfere(point):
            if point == 'after_intent':
                seed_path.write_bytes(changed)
                os.utime(seed_path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        with patch('journal_append.checkpoint', side_effect=interfere):
            with self.assertRaisesRegex(ValueError, 'Seed conflicts'):
                self.view.record(dict(kind='note', taskId='task', title='Reject changed seed'))
        self.assertEqual(journal, self.view.journal.read_bytes())

    def test_incremental_view_rejects_a_changed_dependency_after_append(self):
        models = self.registry.read_models
        with patch('read_models.time.time',return_value=1800000000):
            self.view.memory_tasks()
            original = models.validate_append_view
            def changed(prepared,project,after):
                with patch('read_models.time.time',return_value=1800000011):
                    return original(prepared,project,after)
            with patch.object(models,'validate_append_view',side_effect=changed), \
                    patch.object(models,'prepare_view',wraps=models.prepare_view) as prepare:
                self.view.record(dict(kind='note',taskId='task',title='Different settings'))
                result = models.snapshot(self.view,observations=False,summary=True)
                self.assertEqual(1,prepare.call_count)
        self.assertEqual('Different settings',result['events'][0]['title'])

    def test_prepared_cursor_is_reused_and_backdated_event_rebuilds_history(self):
        models = self.registry.read_models
        with patch('read_models.time.time',return_value=1800000000):
            self.view.memory_tasks()
            self.view.record(dict(kind='note',taskId='task',title='Initialize cursor'))
            with patch.object(models,'_history_uncached',side_effect=AssertionError('history renumbered for ordinary append')):
                self.view.record(dict(kind='note',taskId='task',title='Reuse cursor'))
                models.snapshot(self.view,observations=False,summary=True)
            with patch('project_portal.now',return_value='2099-01-01T00:00:00Z'):
                self.view.record(dict(kind='note',taskId='task',title='Future history'))
            self.view.record(dict(kind='note',taskId='task',title='Earlier than future'))
            prepared = models.snapshot(self.view,observations=False,summary=True)
            complete = self.view._build_snapshot(observations=False,compact_events=True)
        self.assertEqual(complete['events'],prepared['events'])
        self.assertEqual('Future history',prepared['events'][0]['title'])

    def test_waiting_view_read_rechecks_key_after_an_incremental_write(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        models = self.registry.read_models
        with patch('read_models.time.time',return_value=1800000000):
            models.snapshot(self.view,observations=False,summary=True)
            producer = models.build_locks[self.view.project_id]
            models.views.clear()
            producer.acquire()
            observed = threading.Event()
            cold_miss = [True]
            original = models.view_key
            published = models.published_view
            def marked(*args,**kwargs):
                value = original(*args,**kwargs)
                if threading.current_thread().name.startswith('waiting-reader'):
                    observed.set()
                return value
            def force_cold_for_waiting(owner, key):
                if (threading.current_thread().name.startswith('waiting-reader') and
                        cold_miss[0]):
                    cold_miss[0] = False
                    return None
                return published(owner, key)
            with patch.object(models,'view_key',side_effect=marked), \
                    patch.object(models,'published_view',side_effect=force_cold_for_waiting), \
                    patch.object(models,'prepare_view',wraps=models.prepare_view) as prepare, \
                    ThreadPoolExecutor(max_workers=1,thread_name_prefix='waiting-reader') as pool:
                future = pool.submit(models.snapshot,self.view,observations=False,summary=True)
                try:
                    self.assertTrue(observed.wait(3))
                    self.view.record(dict(kind='note',taskId='task',title='Published during wait'))
                    current_key = original(self.view.project_id)
                    with self.registry.connect() as c:
                        row = c.execute('SELECT body,summary FROM read_model_views WHERE project=?',
                                        (self.view.project_id,)).fetchone()
                    from read_models import unpack_view
                    models.views[self.view.project_id] = current_key,unpack_view(row['body']),unpack_view(row['summary'])
                finally:
                    producer.release()
                result = future.result(timeout=3)
                self.assertEqual(0,prepare.call_count)
        self.assertEqual('Published during wait',result['events'][0]['title'])

    def test_append_proof_rejects_same_size_edit_with_restored_mtime(self):
        original = self.view.journal.read_bytes()
        changed = original.replace(b'"title": "Task"',b'"title": "Edit"',1)
        self.assertNotEqual(original,changed)
        stamp = self.view.journal.stat()
        def interfere(point):
            if point == 'after_intent':
                self.view.journal.write_bytes(changed)
                os.utime(self.view.journal,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        with patch('journal_append.checkpoint',side_effect=interfere):
            with self.assertRaisesRegex(ValueError,'conflicts with pending'):
                self.view.record(dict(kind='note',taskId='task',title='Must not append'))
        self.assertEqual(changed,self.view.journal.read_bytes())

    def test_compact_projection_retains_progress_checks_and_checkpoint_metadata(self):
        self.maxDiff = None
        with patch('completion_policy.schedule_checkpoint'):
            self.view.record(dict(kind='task.updated',taskId='task',title='Primary and estimate',
                patch={'primary':{'selected':True,'project':self.ids['one']},
                       'estimate':{'hoursLow':1,'hoursHigh':2,'confidence':'low','updatedAt':'2026-01-01T00:00:00Z'}}))
            self.view.record(dict(kind='stage.created',taskId='task',stageId='stage',title='Milestone',
                                  patch={'title':'Milestone','status':'active'}))
            self.view.record(dict(kind='stage.updated',taskId='task',stageId='stage',title='Completed',patch={'status':'done'}))
            self.view.record(dict(kind='check.passed',taskId='task',title='Passed',runId='run',check={'status':'passed'}))
            self.view.record(dict(kind='git.push',taskId='__project__',title='Push',git={'branch':'main','commits':[]}))
            self.view.record(dict(kind='work.started',taskId='task',title='Hidden work'))
            prepared = self.registry.read_models.snapshot(self.view,observations=False)
            complete = self.view._build_snapshot(observations=False)
            from stage_operations import project_links
            project_links(self.registry,self.view.project_id,complete)
            for field in ('tasks','events','eventCount','lastEventAt','mainTask','checks','checkCount'):
                self.assertEqual(complete[field],prepared[field],field)

    def test_transfer_changes_access_even_with_warm_index_in_another_process(self):
        self.view.evidence('proof.txt')
        other = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        preview = transfer(other, self.ids['one'], self.ids['two'], 'task', preview=True)
        transfer(other, self.ids['one'], self.ids['two'], 'task',
                 expected=preview['revision'], request='indexed-transfer')
        with self.assertRaisesRegex(ValueError, 'not evidence'):
            self.view.evidence('proof.txt')
        target = self.registry.store(self.ids['two'])
        self.assertEqual(b'proof', target.evidence('hub-source/' + self.ids['one'] + '/proof.txt'))

    def test_transferred_checkpoint_result_invalidates_current_owner_view(self):
        models = self.registry.read_models
        with patch('completion_policy.schedule_checkpoint'), patch('read_models.time.time', return_value=1000):
            self.view.record(dict(kind='stage.created',taskId='task',stageId='stage',title='Stage',
                                  patch={'title':'Stage','status':'active'}))
            event = self.view.record(dict(kind='stage.updated',taskId='task',stageId='stage',
                                          title='Done',patch={'status':'done'}))
            with self.registry.connect() as c:
                c.execute('DELETE FROM completion_checkpoints')
                c.execute('INSERT INTO completion_checkpoints VALUES(?,?,?,?,?,?,?,?,?)',
                          ('checkpoint',self.ids['one'],self.ids['one'],'task','stage',event['id'],
                           event['at'],json.dumps({'settingsRevision':'settings'}),json.dumps({'status':'pending'})))
            preview = transfer(self.registry,self.ids['one'],self.ids['two'],'task',preview=True)
            transfer(self.registry,self.ids['one'],self.ids['two'],'task',
                     expected=preview['revision'],request='checkpoint-transfer')
            target = self.registry.store(self.ids['two'])
            before = models.snapshot(target,observations=False,task='task')
            self.assertEqual('pending',before['task']['stages'][0]['gitCheckpoint']['status'])
            with self.registry.connect() as c:
                c.execute('UPDATE completion_checkpoints SET result=? WHERE id=?',
                          (json.dumps({'status':'error','reason':'Publication failed'}),'checkpoint'))
            after = models.snapshot(target,observations=False,task='task')
            self.assertNotEqual(before['revision'],after['revision'])
            self.assertEqual('error',after['task']['stages'][0]['gitCheckpoint']['status'])

    def test_incremental_write_retains_cross_owner_links_only_in_owner_view(self):
        self.view.record(dict(kind='task.created',taskId='linked',title='Linked',
                              patch={'title':'Linked','status':'active','stages':[]}))
        self.view.record(dict(kind='task.updated',taskId='task',title='Link',
                              patch={'links':[{'type':'related','target':'linked'}]}))
        preview = transfer(self.registry,self.ids['one'],self.ids['two'],'linked',preview=True)
        transfer(self.registry,self.ids['one'],self.ids['two'],'linked',
                 expected=preview['revision'],request='linked-transfer')
        self.view.record(dict(kind='task.updated',taskId='task',title='Unrelated update',patch={'summary':'New'}))
        task = self.view.task_context('task')['tasks'][0]
        self.assertEqual(self.ids['two'],task['links'][0]['project'])
        self.assertEqual('New',task['summary'])
        with self.registry.connect() as c:
            raw = json.loads(c.execute('SELECT body FROM read_model_tasks WHERE project=? AND task=?',
                                      (self.ids['one'],'task')).fetchone()[0])
        self.assertNotIn('project',raw['links'][0])

    def test_incremental_write_preserves_hierarchy_validation(self):
        self.view.record(dict(kind='task.created',taskId='other',title='Other',
                              patch={'title':'Other','status':'active','stages':[]}))
        self.view.record(dict(kind='task.updated',taskId='other',title='Parent',patch={'parentTask':'task'}))
        self.view.write_context()  # Finish the deterministic parent-change migration first.
        before = self.view.journal.read_bytes()
        with self.assertRaisesRegex(ValueError,'cyclic'):
            self.view.record(dict(kind='task.updated',taskId='task',title='Cycle',patch={'parentTask':'other'}))
        self.assertEqual(before,self.view.journal.read_bytes())

    def test_compact_graph_context_rejects_invalid_parent_links_and_duplicate_create(self):
        self.view.record(dict(kind='task.created', taskId='parent', title='Parent',
                               patch={'title': 'Parent', 'status': 'active', 'stages': []}))
        before = self.view.journal.read_bytes()
        with self.assertRaisesRegex(ValueError, 'epic'):
            self.view.record(dict(kind='task.created', taskId='child-epic', title='Child epic',
                                  patch={'title': 'Child epic', 'status': 'active', 'type': 'epic',
                                         'parentTask': 'parent', 'stages': []}))
        self.assertEqual(before, self.view.journal.read_bytes())

        with self.assertRaisesRegex(ValueError, 'Unknown linked task'):
            self.view.record(dict(kind='task.updated', taskId='task', title='Unknown link',
                                  patch={'links': [{'type': 'related', 'target': 'missing'}]}))
        self.assertEqual(before, self.view.journal.read_bytes())

        with self.assertRaisesRegex(ValueError, 'unique ID'):
            self.view.record(dict(kind='task.created', taskId='task', title='Duplicate',
                                  patch={'title': 'Duplicate', 'status': 'active', 'stages': []}))
        self.assertEqual(before, self.view.journal.read_bytes())

    def test_legacy_head_rebuilds_missing_graph_before_compact_validation(self):
        with patch('read_models.time.time', return_value=1800000000):
            self.view.record(dict(kind='task.created', taskId='parent', title='Parent',
                                  patch={'title': 'Parent', 'status': 'active', 'type': 'epic',
                                         'stages': []}))
            self.view.record(dict(kind='task.created', taskId='child', title='Child',
                                  patch={'title': 'Child', 'status': 'active', 'parentTask': 'parent',
                                         'links': [{'type': 'related', 'target': 'task'}], 'stages': []}))
            journal = self.view.journal.read_bytes()
            with self.registry.connect() as connection:
                connection.execute('UPDATE read_model_heads SET version=3 WHERE project=?',
                                   (self.ids['one'],))
                connection.execute('DELETE FROM read_model_task_graph WHERE project=?',
                                   (self.ids['one'],))

            restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
            self.addCleanup(restarted.close_connection_pool)
            view = restarted.store(self.ids['one'])
            context = view.write_context(task='child')
            current = view.snapshot(observations=False)
            self.assertEqual(journal, view.journal.read_bytes())
            ids = {task['id'] for task in current['tasks']}
            self.assertTrue({'task', 'parent', 'child'} <= ids)
            child = next(task for task in current['tasks'] if task['id'] == 'child')
            self.assertEqual('parent', child['parentTask'])
            self.assertEqual('task', child['links'][0]['target'])
            self.assertTrue({'parent', 'child'} <= {task['id'] for task in context['tasks']})
            with restarted.connect() as connection:
                graph = connection.execute(
                    'SELECT task,body FROM read_model_task_graph WHERE project=? ORDER BY task',
                    (self.ids['one'],)).fetchall()
            self.assertTrue({'task', 'parent', 'child'} <= {row['task'] for row in graph})

            view.record(dict(kind='task.created', taskId='plain', title='Plain',
                             patch={'title': 'Plain', 'status': 'active', 'stages': []}))
            before_invalid = view.journal.read_bytes()
            with self.assertRaisesRegex(ValueError, 'epic'):
                view.record(dict(kind='task.updated', taskId='child', title='Invalid hierarchy',
                                 patch={'type': 'epic', 'parentTask': 'plain'}))
            self.assertEqual(before_invalid, view.journal.read_bytes())

    def test_historical_source_remains_registered_after_current_sources_change(self):
        self.view.evidence('proof.txt')
        self.view.record({'kind': 'task.updated', 'taskId': 'task', 'title': 'Change',
                          'patch': {'sources': []}})
        self.assertEqual(b'proof', self.view.evidence('proof.txt'))

    def test_invalid_journal_is_rejected_instead_of_serving_the_old_index(self):
        self.view.evidence('proof.txt')
        event = json.loads(self.view.journal.read_text(encoding='utf-8').splitlines()[0])
        event['seq'] = 9
        self.view.journal.write_text(json.dumps(event) + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Invalid journal'):
            self.view.evidence('proof.txt')

    def test_restored_timestamp_does_not_hide_changed_journal_contents(self):
        self.view.evidence('proof.txt')
        before = self.view.journal.stat()
        content = self.view.journal.read_text(encoding='utf-8')
        self.view.journal.write_text(content.replace('proof.txt', 'other.txt'), encoding='utf-8')
        os.utime(self.view.journal, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'not evidence'):
            self.view.evidence('proof.txt')
        (self.view.root / 'other.txt').write_text('new', encoding='utf-8')
        self.assertEqual(b'new', self.view.evidence('other.txt'))

    def test_replacement_between_projection_and_publish_is_retried(self):
        from task_transfer import _origin_projection
        with self.registry.connect() as c:
            c.execute('DELETE FROM read_model_heads WHERE project=?', (self.ids['one'],))
        calls = []
        def replace(*args, **kwargs):
            result = _origin_projection(*args, **kwargs)
            if not calls:
                content = self.view.journal.read_text(encoding='utf-8')
                self.view.journal.write_text(content.replace('proof.txt', 'other.txt'), encoding='utf-8')
            calls.append(1)
            return result
        with patch('task_transfer._origin_projection', side_effect=replace):
            with self.assertRaisesRegex(ValueError, 'not evidence'):
                self.view.evidence('proof.txt')
        self.assertGreaterEqual(len(calls), 2)

    @patch('read_models.time.time',return_value=1000)
    def test_prepared_view_is_reused_and_callers_cannot_mutate_it(self,_clock):
        first = self.view.memory_snapshot()
        first['tasks'][0]['title'] = 'corrupted by caller'
        with patch.object(type(self.view), '_build_snapshot', side_effect=AssertionError('replay forbidden')):
            second = self.view.memory_snapshot()
            self.assertEqual('Task', second['tasks'][0]['title'])
            compact = self.registry.read_models.snapshot(self.view, observations=False, summary=True)
            self.assertFalse(compact['tasks'][0]['detailLoaded'])
            self.assertNotIn('sources', compact['tasks'][0])
            self.assertIn('proof.txt', compact['tasks'][0]['searchText'])
            detail = self.registry.read_models.snapshot(self.view, observations=False, task='task')
            self.assertEqual(first['revision'], detail['revision'])
            self.assertEqual('proof.txt', detail['task']['sources'][0]['path'])

    def test_clock_boundary_during_preparation_is_not_a_domain_conflict(self):
        clock = [1000]
        original = type(self.view)._build_snapshot
        def delayed(view, **kwargs):
            clock[0] += 10
            return original(view, **kwargs)
        with patch('read_models.time.time', side_effect=lambda: clock[0]), \
                patch.object(type(self.view), '_build_snapshot', delayed):
            detail = self.registry.read_models.snapshot(self.view, observations=False, task='task')
        self.assertEqual('task', detail['task']['id'])

    def test_clock_refresh_reuses_static_page_and_hides_progress_inputs(self):
        models = self.registry.read_models
        with patch('read_models.time.time', return_value=1000), \
             patch('task_progress.time.time', return_value=1000):
            self.view.record({'kind': 'task.updated', 'taskId': 'task', 'title': 'Primary',
                              'patch': {'primary': {'selected': True, 'project': self.ids['one']},
                                        'estimate': {'hoursLow': 1, 'hoursHigh': 2,
                                                     'confidence': 'medium', 'note': 'bounded'}}})
            self.view.record({'kind': 'stage.created', 'taskId': 'task', 'stageId': 'milestone',
                              'title': 'Milestone', 'patch': {'title': 'Milestone', 'status': 'active'}})
            self.view.record({'kind': 'stage.updated', 'taskId': 'task', 'stageId': 'milestone',
                              'title': 'Done', 'patch': {'status': 'done'}})
            first = models.snapshot(self.view, observations=False, summary=True)

        with patch('read_models.time.time', return_value=1011), \
             patch('task_progress.time.time', return_value=1011), \
             patch.object(self.view, '_build_snapshot', side_effect=AssertionError('clock refresh rebuilt page')):
            refreshed = models.snapshot(self.view, observations=False)
            summary = models.snapshot(self.view, observations=False, summary=True)
            tasks = models.snapshot(self.view, observations=False, tasks_only=True)
            detail = models.snapshot(self.view, observations=False, task='task')
        with patch('read_models.time.time', return_value=1011), \
             patch('task_progress.time.time', return_value=1011):
            complete = self.view._build_snapshot(observations=False)
        for state in (refreshed, summary, tasks, detail):
            self.assertNotIn('_progressInputs', state)
        self.assertEqual(first['revision'], refreshed['revision'])
        self.assertEqual(complete['mainTask'], refreshed['mainTask'])
        complete_task = complete['tasks'][0]
        refreshed_task = refreshed['tasks'][0]
        for field in ('id', 'title', 'status', 'estimate', 'primary', 'progress',
                      'agentActivity', 'currentWork'):
            self.assertEqual(complete_task.get(field), refreshed_task.get(field), field)
        self.assertEqual(complete['mainTask'], summary['mainTask'])
        for field in ('id', 'title', 'status', 'estimate', 'primary', 'progress',
                      'agentActivity', 'currentWork'):
            self.assertEqual(complete_task.get(field), tasks['tasks'][0].get(field), field)
            self.assertEqual(complete_task.get(field), detail['task'].get(field), field)

    def test_clock_refresh_rebuilds_after_content_change_and_legacy_page(self):
        models = self.registry.read_models
        with patch('read_models.time.time', return_value=1000), \
             patch('task_progress.time.time', return_value=1000):
            models.snapshot(self.view, observations=False, summary=True)
        with patch('read_models.time.time', return_value=1011), \
             patch('task_progress.time.time', return_value=1011):
            self.view.record({'kind': 'note', 'taskId': 'task', 'title': 'Content changed'})
            with patch.object(self.view, '_build_snapshot', wraps=self.view._build_snapshot) as build:
                models.snapshot(self.view, observations=False, summary=True)
                self.assertGreaterEqual(build.call_count, 1)

        with patch('read_models.time.time', return_value=1011), \
             patch('task_progress.time.time', return_value=1011):
            models.snapshot(self.view, observations=False, summary=True)
            from read_models import pack_view, unpack_view
            with self.registry.connect() as connection:
                row = connection.execute('SELECT body FROM read_model_views WHERE project=?',
                                         (self.view.project_id,)).fetchone()
                legacy = json.loads(unpack_view(row['body']))
                legacy.pop('_progressInputs', None)
                connection.execute('UPDATE read_model_views SET body=? WHERE project=?',
                                   (pack_view(json.dumps(legacy, separators=(',', ':'), sort_keys=True)),
                                    self.view.project_id))
            models.views.clear()
        with patch('read_models.time.time', return_value=1021), \
             patch('task_progress.time.time', return_value=1021), \
             patch.object(self.view, '_build_snapshot', wraps=self.view._build_snapshot) as build:
            models.snapshot(self.view, observations=False, summary=True)
            self.assertGreaterEqual(build.call_count, 1)

    def test_clock_refresh_drops_removed_coordination_work_without_stale_current_work(self):
        import sqlite3
        import sys
        import time
        from contextlib import closing
        hub_scripts = Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub/scripts'
        sys.path.insert(0, str(hub_scripts))
        from hub_core import Hub
        hub = Hub(self.registry.home / 'coordination')
        hub.setup()
        anchor = time.time()
        with closing(sqlite3.connect(hub.db)) as connection:
            connection.execute('INSERT OR IGNORE INTO projects(id,root,git_common) VALUES(?,?,?)',
                               (self.ids['one'], str(self.view.root), ''))
            connection.execute(
                "INSERT INTO sessions(id,project,workspace,state,seen,turn,checkpoint,task) VALUES(?,?,?,?,?,?,?,?)",
                ('session', self.ids['one'], str(self.view.root), 'active', anchor, '', '', 'task'))
            connection.execute(
                "INSERT INTO work(id,project,session,task,title,status,revision,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                ('work', self.ids['one'], 'session', 'task', 'Current work', 'active', 1, anchor, anchor))
            connection.execute(
                "INSERT INTO events(id,project,session,kind,work,at,body) VALUES(?,?,?,?,?,?,?)",
                ('work-started', self.ids['one'], 'session', 'work.started', 'work', anchor, '{}'))
            connection.commit()

        models = self.registry.read_models
        from task_progress import work_activity
        activity = work_activity(hub.db, self.ids['one'], anchor)
        self.assertIn('task', activity)
        self.assertTrue(activity['task']['active'])
        with patch('read_models.time.time', return_value=anchor), \
             patch('task_progress.time.time', return_value=anchor):
            warm = models.snapshot(self.view, observations=False)
        warm_task = warm['tasks'][0]
        self.assertEqual('active', warm_task['agentActivity']['state'])
        self.assertEqual('work', warm_task['currentWork']['id'])

        with closing(sqlite3.connect(hub.db)) as connection:
            connection.execute('DELETE FROM work WHERE id=?', ('work',))
            connection.execute('DELETE FROM sessions WHERE id=?', ('session',))
            connection.commit()

        with patch('read_models.time.time', return_value=anchor + 11), \
             patch('task_progress.time.time', return_value=anchor + 11), \
             patch.object(self.view, '_build_snapshot', side_effect=AssertionError('clock refresh rebuilt page')):
            refreshed = models.snapshot(self.view, observations=False)
        with patch('read_models.time.time', return_value=anchor + 11), \
             patch('task_progress.time.time', return_value=anchor + 11):
            complete = self.view._build_snapshot(observations=False)
        refreshed_task = refreshed['tasks'][0]
        complete_task = complete['tasks'][0]
        self.assertNotIn('currentWork', refreshed_task)
        self.assertEqual(complete_task.get('currentWork'), refreshed_task.get('currentWork'))
        self.assertEqual(complete_task['agentActivity'], refreshed_task['agentActivity'])

    def test_concurrent_cold_readers_prepare_one_view_without_recovery_herd(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        models = self.registry.read_models
        models.views.clear()
        with self.registry.connect() as c:
            c.execute('DELETE FROM read_model_views')
        rendezvous = threading.Barrier(8)
        local = threading.local()
        original_key = models.view_key
        def together(*args, **kwargs):
            result = original_key(*args, **kwargs)
            if not getattr(local,'seen',False):
                local.seen = True
                rendezvous.wait(timeout=5)
            return result
        with patch('read_models.time.time', return_value=1000), \
                patch.object(models,'view_key',side_effect=together), \
                patch.object(models,'prepare_view',wraps=models.prepare_view) as prepare:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: models.snapshot(self.view, observations=False, summary=True), range(8)))
        self.assertEqual(1,prepare.call_count)
        self.assertEqual(1,len({result['revision'] for result in results}))

    def test_optimistic_page_build_does_not_block_a_writer_or_publish_a_mixed_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        entered, release = threading.Event(), threading.Event()
        build = self.view._build_snapshot
        def paused(*args,**kwargs):
            result = build(*args,**kwargs)
            if not kwargs.get('serialized',True):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('Writer did not complete during optimistic preparation')
            return result
        models = self.registry.read_models
        with patch.object(self.view,'_build_snapshot',side_effect=paused), ThreadPoolExecutor(max_workers=2) as pool:
            page = pool.submit(models.snapshot,self.view,observations=False,summary=True)
            try:
                self.assertTrue(entered.wait(5))
                writer = pool.submit(self.view.record,dict(kind='note',taskId='task',title='Concurrent write'))
                writer.result(timeout=2)
            finally:
                release.set()
            result = page.result(timeout=5)
        self.assertEqual('Concurrent write',result['events'][0]['title'])
        self.assertEqual(models.domain_key(self.view.project_id),result['revision'])

    def test_published_view_bypasses_a_cold_reader_build_lock(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading

        reader_registry = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        self.addCleanup(reader_registry.close_connection_pool)
        reader = reader_registry.store(self.ids['one'])
        reader_models = reader_registry.read_models
        writer_models = self.registry.read_models
        owner = reader.project_id
        with patch('read_models.time.time', return_value=1800000000):
            reader_models.snapshot(reader, observations=False, summary=True)
            self.view.record({'kind': 'note', 'taskId': 'task', 'title': 'Published before reader lock'})
            expected = writer_models.snapshot(self.view, observations=False, summary=True)
            producer = reader_models.build_locks.setdefault(owner, threading.Lock())
            producer.acquire()
            try:
                with patch.object(reader_models, 'prepare_view',
                                  side_effect=AssertionError('published view rebuilt')):
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(reader_models.snapshot, reader,
                                             observations=False, summary=True)
                        result = future.result(timeout=2)
                self.assertEqual(expected['revision'], result['revision'])
                self.assertEqual(expected['tasks'][0]['_sourceRevision'],
                                 result['tasks'][0]['_sourceRevision'])
                self.assertEqual('Published before reader lock', result['events'][0]['title'])
            finally:
                producer.release()

    def test_independent_registries_share_one_os_view_producer(self):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
        import threading
        from task_transfer import ProjectView
        other = ProjectRegistry(self.registry.home,CodexProjects(self.catalog))
        target = other.store(self.ids['one'])
        self.registry.read_models.ensure_all()
        other.read_models.ensure_all()
        entered, release, requested = threading.Event(), threading.Event(), threading.Event()
        builds = []
        build = ProjectView._build_snapshot
        prepare = other.read_models.prepare_view
        def paused(view,*args,**kwargs):
            builds.append(view)
            if len(builds) == 1:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('View producer was not released')
            return build(view,*args,**kwargs)
        def competing(*args,**kwargs):
            requested.set()
            return prepare(*args,**kwargs)
        with patch.object(ProjectView,'_build_snapshot',paused), \
                patch.object(other.read_models,'prepare_view',side_effect=competing), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.registry.read_models.snapshot,self.view,observations=False,summary=True)
            try:
                self.assertTrue(entered.wait(5))
                second = pool.submit(other.read_models.snapshot,target,observations=False,summary=True)
                self.assertTrue(requested.wait(5))
                with self.assertRaises(FutureTimeout):
                    second.result(timeout=.05)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5)['revision'],second.result(timeout=5)['revision'])
        self.assertEqual(1,len(builds))

    def test_paged_history_matches_legacy_numbering_and_transfer_order(self):
        for n in range(6):
            self.view.record({'kind': 'note', 'taskId': 'task', 'id': 'note-' + str(n), 'title': str(n)})
        for before in (None, 6, 3):
            self.assertEqual(self.view._legacy_history(before=before, limit=2), self.view.history(before=before, limit=2))
        preview = transfer(self.registry, self.ids['one'], self.ids['two'], 'task', preview=True)
        transfer(self.registry, self.ids['one'], self.ids['two'], 'task', expected=preview['revision'], request='paged-history')
        for owner in ('one','two'):
            view = self.registry.store(self.ids[owner])
            self.assertEqual(view._legacy_history(limit=20), view.history(limit=20))
            self.assertEqual(view._build_snapshot(observations=False)['allEvents'], view.memory_snapshot()['allEvents'])
            with self.registry.connect() as c:
                from read_models import unpack_view
                persisted = json.loads(unpack_view(c.execute('SELECT body FROM read_model_views WHERE project=?', (view.project_id,)).fetchone()[0]))
            self.assertNotIn('allEvents', persisted)

    def test_append_recovery_finishes_each_committed_intent_exactly_once(self):
        for point in ('after_intent','after_append','partial_append'):
            event = dict(id='recovery-' + point, kind='note', taskId='task', title=point)
            def fail(at):
                if at == ('after_intent' if point == 'partial_append' else point):
                    raise RuntimeError('Simulated process interruption')
            with patch('journal_append.checkpoint', side_effect=fail):
                with self.assertRaises(RuntimeError):
                    self.view.record(event)
            if point == 'partial_append':
                with self.registry.connect() as c:
                    intent = c.execute('SELECT * FROM journal_append_intents').fetchone()
                with self.view.journal.open('ab') as output:
                    output.write(intent['suffix'][:17])
            restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
            view = restarted.store(self.ids['one'])
            events = view.memory_snapshot()['allEvents']
            self.assertEqual(1, sum(e['id'] == event['id'] for e in events))
            view.record(event)
            self.assertEqual(1, sum(e['id'] == event['id'] for e in view.memory_snapshot()['allEvents']))
            with restarted.connect() as c:
                self.assertEqual(0, c.execute('SELECT count(*) FROM journal_append_intents').fetchone()[0])

    def test_append_recovery_never_overwrites_foreign_or_corrupt_replacement(self):
        with patch('journal_append.checkpoint', side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):
                self.view.record(dict(id='pending',kind='note',taskId='task',title='Pending'))
        replaced = self.view.journal.read_bytes() + b'FOREIGN DATA'
        self.view.journal.write_bytes(replaced)
        with self.assertRaisesRegex(ValueError, 'conflicts with pending'):
            self.view.memory_snapshot()
        self.assertEqual(replaced, self.view.journal.read_bytes())

    def test_missing_to_empty_replacement_is_not_silently_recovered(self):
        view = self.registry.store(self.ids['two'])
        self.assertFalse(view.journal.exists())
        with patch('journal_append.checkpoint', side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):
                view.record(dict(id='new-pending',kind='task.created',taskId='new',title='New',
                                 patch={'title':'New','status':'active','stages':[]}))
        view.journal.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'replacement conflicts'):
            view.memory_snapshot()
        self.assertEqual(b'',view.journal.read_bytes())

    def test_first_journal_publication_never_leaves_an_empty_target(self):
        view = self.registry.store(self.ids['two'])
        event = dict(id='initial-publication',kind='task.created',taskId='new',title='New',
                     patch={'title':'New','status':'active','stages':[]})
        def fail(point):
            if point == 'before_initial_publish':
                self.assertFalse(view.journal.exists())
                raise RuntimeError('Interrupted before atomic publication')
        with patch('journal_append.checkpoint',side_effect=fail):
            with self.assertRaises(RuntimeError):
                view.record(event)
        self.assertFalse(view.journal.exists())
        restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        current = restarted.store(self.ids['two'])
        current.record(event)
        self.assertEqual(1, sum(e['id']==event['id'] for e in current.memory_snapshot()['allEvents']))
        with restarted.connect() as c:
            self.assertEqual(0,c.execute('SELECT count(*) FROM journal_append_intents').fetchone()[0])

    def test_first_journal_publication_cannot_overwrite_a_new_foreign_target(self):
        view = self.registry.store(self.ids['two'])
        def replace(point):
            if point == 'before_initial_publish':
                view.journal.write_bytes(b'FOREIGN')
        with patch('journal_append.checkpoint',side_effect=replace):
            with self.assertRaises(FileExistsError):
                view.record(dict(id='initial-conflict',kind='task.created',taskId='new',title='New',
                                 patch={'title':'New','status':'active','stages':[]}))
        self.assertEqual(b'FOREIGN',view.journal.read_bytes())
        with self.assertRaisesRegex(ValueError,'conflicts with pending'):
            view.memory_snapshot()

    def test_cold_reader_does_not_hold_a_cache_lock_while_waiting_for_writer(self):
        import threading
        from contextlib import contextmanager
        from task_transfer import barrier
        with self.registry.connect() as c:
            c.execute('DELETE FROM read_model_views')
        self.registry.read_models.views.clear()
        writer_ready, reader_waiting = threading.Event(), threading.Event()
        errors = []
        @contextmanager
        def observe(registry):
            if threading.current_thread().name == 'cache-reader':
                reader_waiting.set()
            with barrier(registry):
                yield
        def writer():
            try:
                with barrier(self.registry):
                    writer_ready.set()
                    self.assertTrue(reader_waiting.wait(3))
                    self.view.memory_snapshot()
            except BaseException as error:
                errors.append(error)
        def reader():
            try:
                self.assertTrue(writer_ready.wait(3))
                self.view.memory_snapshot()
            except BaseException as error:
                errors.append(error)
        with patch('task_transfer.barrier', observe):
            threads = [threading.Thread(target=writer,name='cache-writer',daemon=True),
                       threading.Thread(target=reader,name='cache-reader',daemon=True)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=4)
            self.assertTrue(all(not thread.is_alive() for thread in threads), 'Reader/writer lock inversion')
        self.assertEqual([], errors)
