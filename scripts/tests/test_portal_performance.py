"""Bounded portal invalidation and lock tests; all inputs are disposable."""
import io
import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import Handler, PortalServer, Store
from project_registry import CodexProjects, ProjectRegistry
import codex_session_catalog
import project_portal
from event_broker import EventBroker


class PortalPerformanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog_path = self.root / 'codex.json'
        self.rows = {'one': dict(id='one', name='One', rootPaths=[str(self.root / 'source')])}
        self.write_catalog()
        self.registry = ProjectRegistry(self.root / 'hub', CodexProjects(self.catalog_path))

    def write_catalog(self):
        self.catalog_path.write_text(json.dumps({'local-projects': self.rows}), encoding='utf-8')

    def test_registry_refresh_is_stable_but_rename_removal_and_return_change_updated(self):
        with patch('project_registry.time.time', return_value=100):
            first = self.registry.list()['projects'][0]
        with patch('project_registry.time.time', return_value=200):
            self.assertEqual(first, self.registry.list()['projects'][0])
        self.rows['one']['name'] = 'Renamed'
        self.write_catalog()
        with patch('project_registry.time.time', return_value=300):
            renamed = self.registry.list()['projects'][0]
        self.assertEqual((first['id'], 'Renamed', 300),
                         (renamed['id'], renamed['name'], renamed['updated']))
        saved = self.rows.pop('one')
        self.write_catalog()
        with patch('project_registry.time.time', return_value=400):
            removed = self.registry.list()['projects'][0]
        self.assertEqual((first['id'], 0, 400), (removed['id'], removed['present'], removed['updated']))
        with patch('project_registry.time.time', return_value=500):
            self.assertEqual(removed, self.registry.list()['projects'][0])
        self.rows['one'] = saved
        self.write_catalog()
        with patch('project_registry.time.time', return_value=600):
            restored = self.registry.list()['projects'][0]
        self.assertEqual((first['id'], 1, 600), (restored['id'], restored['present'], restored['updated']))

    def test_event_signature_tracks_journal_settings_and_coordination_wal(self):
        data, coordination = self.root / 'data', self.root / 'coordination'
        data.mkdir()
        coordination.mkdir()
        store = Store(self.root, data_dir=data, coordination_home=coordination)
        with patch.object(codex_session_catalog, 'CATALOG', SimpleNamespace(database=self.root / 'catalog.sqlite3')), \
                patch.object(project_portal, 'SESSION_TITLES', SimpleNamespace(path=self.root / 'titles.json')):
            previous = store.event_signature()
            self.assertEqual(previous, store.event_signature())
            empty_wal = coordination / 'coordination.sqlite3-wal'
            empty_wal.touch()
            self.assertEqual(previous, store.event_signature(), 'empty WAL is not a committed change')
            empty_wal.unlink()
            for path in (store.journal, data / 'project-settings.json', coordination / 'coordination.sqlite3-wal'):
                with self.subTest(path=path.name):
                    path.write_bytes(b'first')
                    created = store.event_signature()
                    self.assertNotEqual(previous, created)
                    path.write_bytes(b'larger changed input')
                    updated = store.event_signature()
                    self.assertNotEqual(created, updated)
                    self.assertEqual(updated, store.event_signature())
                    path.unlink()
                    previous = store.event_signature()
                    self.assertNotEqual(updated, previous)

    def test_snapshot_diagnostics_run_after_ownership_barrier_is_released(self):
        project = self.registry.list()['projects'][0]['id']
        store = self.registry.store(project)

        def diagnostics():
            self.assertEqual(0, getattr(self.registry.transfer_local, 'depth', 0))
            return {'available': True, 'revision': 123}

        with patch.object(store, 'diagnostics', side_effect=diagnostics) as observed:
            state = store.snapshot()
        observed.assert_called_once_with()
        self.assertEqual({'available': True, 'revision': 123}, state['coordination'])
        self.assertEqual([], state['tasks'])

    def test_event_signature_tolerates_unreadable_optional_metadata(self):
        store = Store(self.root, data_dir=self.root / 'data', coordination_home=self.root / 'coordination')
        catalog = self.root / 'catalog.sqlite3'
        titles = self.root / 'session_index.jsonl'
        original_stat = Path.stat

        def stat(path, *args, **kwargs):
            if path in (catalog, titles):
                raise PermissionError('Optional metadata is temporarily inaccessible')
            return original_stat(path, *args, **kwargs)

        with patch.object(codex_session_catalog, 'CATALOG', SimpleNamespace(database=catalog)), \
                patch.object(project_portal, 'SESSION_TITLES', SimpleNamespace(path=titles)), \
                patch.object(Path, 'stat', stat):
            signature = store.event_signature()
        self.assertNotIn(str(catalog), [entry[0] for entry in signature])
        self.assertIn((str(titles), None, None), signature)

    def test_unrelated_host_database_writes_do_not_invalidate_event_signature(self):
        store = Store(self.root, data_dir=self.root / 'data')
        catalog = self.root / 'catalog.sqlite3'
        with patch.object(codex_session_catalog, 'CATALOG', SimpleNamespace(database=catalog)), \
                patch.object(project_portal, 'SESSION_TITLES', SimpleNamespace(path=self.root / 'titles.json')):
            before = store.event_signature()
            catalog.write_bytes(b'unrelated host activity')
            Path(str(catalog) + '-wal').write_bytes(b'unrelated messages')
            self.assertEqual(before, store.event_signature())

    def event_server(self, **attributes):
        server = SimpleNamespace(event_cache_lock=threading.Lock(), event_cache={},
                                 stopping=threading.Event(), **attributes)
        def read_snapshot(store):
            if not hasattr(store, 'diagnostics'):
                store.diagnostics = lambda: {'available': True, 'revision': 0}
            return store.snapshot()
        server.read_snapshot = read_snapshot
        server.event_broker = EventBroker(server)
        self.addCleanup(lambda: (server.stopping.set(), server.event_broker.close()))
        server.event_state = lambda store: PortalServer.event_state(server, store)
        return server

    def wait_for_hint(self, server, store, predicate=lambda hint: hint is not None):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                hint = server.event_state(store)
            except ValueError:
                raise
            if predicate(hint):
                return hint
            time.sleep(.02)
        self.fail('revision producer did not publish the expected hint')

    def test_sse_revision_hints_report_changed_sections_and_current_revision(self):
        revision = [0]
        snapshots = []
        store = SimpleNamespace(data=self.root / 'data', event_signature=lambda: 'stable',
                                snapshot=lambda: (snapshots.append(revision[0]) or {'revision': revision[0]}))
        server = self.event_server()
        first = self.wait_for_hint(server, store)
        self.assertEqual(0, first['revision'])
        self.assertEqual({'coordination', 'knowledge', 'tasks'}, set(first['changedSections']))
        revision[0] = 1
        second = self.wait_for_hint(server, store, lambda hint: hint and hint.get('revision') == 1)
        self.assertEqual(['tasks'], second['changedSections'])
        self.assertGreaterEqual(len(snapshots), 2)

    def test_sse_periodic_producer_rechecks_when_signature_is_unchanged(self):
        revision = [0]
        calls = [0]
        def snapshot():
            calls[0] += 1
            return {'revision': revision[0]}
        store = SimpleNamespace(data=self.root / 'data', event_signature=lambda: 'stable', snapshot=snapshot)
        server = self.event_server()
        self.wait_for_hint(server, store)
        revision[0] = 2
        self.wait_for_hint(server, store, lambda hint: hint and hint.get('revision') == 2)
        self.assertGreaterEqual(calls[0], 2)

    def test_idle_projects_stop_polling_and_refresh_on_reconnection(self):
        revision = [0]
        store = SimpleNamespace(data=self.root / 'data', snapshot=lambda: {'revision':revision[0]})
        server = self.event_server()
        first = self.wait_for_hint(server,store)
        broker = server.event_broker
        key = str(store.data)
        with broker.condition:
            broker.projects[key]['last_used'] -= broker.idle_seconds+1
            self.assertTrue(broker.condition.wait_for(lambda:key not in broker.projects,timeout=3))
        revision[0] = 2
        refreshed = self.wait_for_hint(server,store,lambda hint:hint and hint['revision'] == 2)
        self.assertEqual(0,first['revision'])
        self.assertIn('tasks',refreshed['changedSections'])

    def test_sse_subscriber_does_not_start_a_second_snapshot_while_producer_is_busy(self):
        started, release = threading.Event(), threading.Event()
        calls = [0]
        def snapshot():
            calls[0] += 1
            started.set()
            self.assertTrue(release.wait(3))
            return {'revision': 5}
        store = SimpleNamespace(data=self.root / 'data', event_signature=lambda: 'same', snapshot=snapshot)
        server = self.event_server()
        first = server.event_state(store)
        self.assertIsNone(first)
        self.assertTrue(started.wait(3))
        self.assertIsNone(server.event_state(store))
        release.set()
        self.assertEqual(5, self.wait_for_hint(server, store)['revision'])
        self.assertEqual(1, calls[0])

    def test_sse_subscribers_share_one_inflight_snapshot(self):
        server = self.event_server()
        snapshot_started, release_snapshot, second_entered = threading.Event(), threading.Event(), threading.Event()

        def snapshot():
            snapshot_started.set()
            self.assertTrue(release_snapshot.wait(3))
            return {'revision': 5}

        store = SimpleNamespace(data=self.root / 'data', event_signature=lambda: 'same', snapshot=Mock(side_effect=snapshot),
                                diagnostics=lambda: {'available': True, 'revision': 0})

        def second_subscriber():
            second_entered.set()
            return server.event_state(store)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(server.event_state, store)
            try:
                self.assertTrue(snapshot_started.wait(3))
                second = pool.submit(second_subscriber)
                self.assertTrue(second_entered.wait(3))
            finally:
                release_snapshot.set()
            self.assertIsNone(first.result(timeout=3))
            self.assertIsNone(second.result(timeout=3))
        self.assertEqual(5, self.wait_for_hint(server, store)['revision'])
        store.snapshot.assert_called_once_with()

    def test_http_and_sse_share_snapshot_and_never_lend_mutable_cache(self):
        server = self.event_server()
        server.read_snapshot = lambda store: PortalServer.read_snapshot(server, store)
        store = SimpleNamespace(data=self.root / 'data', event_signature=lambda: 'stable',
            snapshot=Mock(return_value={'revision': 8, 'tasks': [{'title': 'Saved'}],
                                        'allEvents': [{'id': 'event'}]}),
            diagnostics=lambda: {'available': True, 'revision': 0})
        first = server.read_snapshot(store)
        first['tasks'][0]['title'] = 'Changed by response decoration'
        first.pop('allEvents')
        hint = self.wait_for_hint(server, store)
        self.assertEqual(8, hint['revision'])
        self.assertNotIn('tasks', hint)
        self.assertNotIn('allEvents', hint)
        second = server.read_snapshot(store)
        self.assertEqual('Saved', second['tasks'][0]['title'])
        self.assertEqual([{'id': 'event'}], second['allEvents'])
        store.snapshot.assert_called_once_with()

    def test_read_cache_invalidates_on_authoritative_change_and_keeps_failures_visible(self):
        server = self.event_server()
        token = ['first']
        store = SimpleNamespace(data=self.root / 'data', event_signature=lambda: token[0],
            snapshot=Mock(side_effect=[{'revision': 1}, ValueError('unreadable'), {'revision': 2}]))
        self.assertEqual(1, server.read_snapshot(store)['revision'])
        token[0] = 'second'
        with self.assertRaisesRegex(ValueError, 'unreadable'):
            server.read_snapshot(store)
        self.assertEqual(2, server.read_snapshot(store)['revision'])

    def test_static_assets_revalidate_but_api_responses_are_not_browser_cached(self):
        handler = object.__new__(Handler)
        handler.server = SimpleNamespace(registry=None)
        handler.path = '/static/app.js'
        handler.headers = {'If-None-Match': '"same"'}
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = io.BytesIO()
        handler.reply(200, b'asset', 'text/javascript', etag='"same"')
        handler.send_response.assert_called_with(304)
        handler.send_header.assert_any_call('Cache-Control', 'no-cache')
        self.assertEqual(b'', handler.wfile.getvalue())
        handler.reply(200, {'revision': 1})
        handler.send_response.assert_called_with(200)
        handler.send_header.assert_any_call('Cache-Control', 'no-store')

    def test_portal_bootstrap_skips_git_but_default_api_keeps_it(self):
        handler = object.__new__(Handler)
        from email.message import Message
        handler.headers = Message(); handler.headers['Host'] = '127.0.0.1:1234'
        handler.server = SimpleNamespace(registry=None, server_port=1234,
            store=SimpleNamespace(root=self.root),
            read_snapshot=lambda store: {'project': {'name': 'Fixture'}, 'tasks': [], 'revision': 1})
        handler.reply = Mock()
        handler.path = '/api/state?view=portal'
        with patch('project_portal.cached_read_repository', return_value={'available': False}) as git:
            handler.do_GET()
            git.assert_not_called()
            self.assertNotIn('git', handler.reply.call_args.args[1])
            self.assertEqual(['snapshot'], [name for name, _ in handler.request_timings])
            handler.path = '/api/state'
            handler.do_GET()
            git.assert_called_once_with(self.root)
            self.assertEqual({'available': False}, handler.reply.call_args.args[1]['git'])
            self.assertEqual(['snapshot', 'git'], [name for name, _ in handler.request_timings])

    def test_cached_sse_revision_never_authorizes_stale_mutation(self):
        data = self.root / 'data'
        data.mkdir()
        (data / 'project.json').write_text(json.dumps({
            'schemaVersion': 1, 'id': 'fixture', 'name': 'Fixture', 'tasks': []}), encoding='utf-8')
        store = Store(self.root, data_dir=data)
        server = self.event_server()
        with patch.object(store, 'event_signature', return_value='unchanged-hint'), \
                patch('project_portal.time.monotonic', return_value=1):
            first = self.wait_for_hint(server, store)
            self.assertEqual(0, first['revision'])
            store.record({'taskId': 'one', 'kind': 'task.created', 'title': 'Create',
                          'patch': {'title': 'One', 'status': 'planned', 'stages': []}}, expected_revision=0)
            updated = self.wait_for_hint(server, store, lambda hint: hint and hint.get('revision') != 0)
            self.assertEqual(store.snapshot()['revision'], updated['revision'])
            with self.assertRaises(ValueError):
                store.record({'taskId': 'one', 'kind': 'task.updated', 'title': 'Stale edit',
                              'patch': {'title': 'Must not persist'}}, expected_revision=0)
        self.assertEqual('One', store.snapshot()['tasks'][0]['title'])

    @patch('read_models.time.time', return_value=1000)
    def test_ack_names_committed_write_and_old_receipt_cannot_authorize_next_write(self, _clock):
        project = self.registry.list()['projects'][0]['id']
        store = self.registry.store(project)
        store.record(dict(kind='task.created', taskId='task', title='Create',
                          patch=dict(title='Task', status='active', stages=[])))
        models = self.registry.read_models
        models.snapshot(store, observations=False, summary=True)
        store.record(dict(kind='task.updated', taskId='task', title='First', patch=dict(summary='First')))
        first = dict(store.write_receipt)
        self.assertEqual(models.domain_key(project), first['revision'])
        store.record(dict(kind='task.updated', taskId='task', title='Second', patch=dict(summary='Second')))
        self.assertNotEqual(first['revision'], models.domain_key(project))
        handler = object.__new__(Handler)
        handler.path = '/api/v1/tasks/update?view=ack'
        with patch.object(models, 'domain_key', side_effect=AssertionError('receipt must not read a later version')):
            self.assertEqual(dict(accepted=True, revision=first['revision']),
                             handler.task_write_response(store, receipt=first))
        with self.assertRaisesRegex(ValueError, 'Task changed'):
            store.record(dict(kind='task.updated', taskId='task', title='Stale', patch=dict(summary='Stale')),
                         expected_revision=first['revision'])
        self.assertIsNone(store.write_receipt)
        self.assertEqual(models.domain_key(project), handler.task_write_response(store)['revision'])
        self.assertEqual('Second', store.task_context('task')['tasks'][0]['summary'])

    @patch('read_models.time.time', return_value=1000)
    def test_semantic_write_does_not_reuse_previous_prepared_receipt(self, _clock):
        project = self.registry.list()['projects'][0]['id']
        store = self.registry.store(project)
        store.record(dict(kind='task.created', taskId='task', title='Create',
                          patch=dict(title='Task', status='active', stages=[])))
        self.registry.read_models.snapshot(store, observations=False, summary=True)
        store.record(dict(kind='note', taskId='task', title='Prepared'))
        self.assertIsNotNone(store.write_receipt)
        store.record(dict(kind='task.updated', taskId='task', title='Title', patch=dict(title='New title')))
        self.assertIsNone(store.write_receipt)
        handler = object.__new__(Handler)
        handler.path = '/api/v1/tasks/update?view=ack'
        self.assertEqual(self.registry.read_models.domain_key(project),
                         handler.task_write_response(store, receipt=store.write_receipt)['revision'])


if __name__ == '__main__':
    unittest.main()
