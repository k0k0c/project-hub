"""Readers observe the last committed SQL projection during managed appends."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_task_read_models as read_model_fixtures
from project_registry import CodexProjects, ProjectRegistry


class CommittedReadVisibilityTests(unittest.TestCase):
    def setUp(self):
        read_model_fixtures.ReadModelTests.setUp(self)

    def _reader(self):
        registry = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        self.addCleanup(registry.close_connection_pool)
        return registry, registry.store(self.ids['one'])

    def test_reader_lends_old_projection_after_verified_append_until_sql_publish(self):
        writer_models = self.registry.read_models
        reader_registry, reader = self._reader()
        writer = self.registry.store(self.ids['one'])
        warmed = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        entered, release = threading.Event(), threading.Event()
        original = writer_models.appended

        def paused(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(*args, **kwargs)

        with patch.object(writer_models, 'appended', side_effect=paused), ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(writer.record, dict(kind='note', taskId='task', title='Committed later'))
            try:
                self.assertTrue(entered.wait(5))
                old = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
                self.assertEqual(warmed['revision'], old['revision'])
                self.assertNotIn('Committed later', [event.get('title') for event in old['events']])
            finally:
                release.set()
            pending.result(timeout=5)
        fresh = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        self.assertIn('Committed later', [event.get('title') for event in fresh['events']])
        self.assertNotEqual(fresh['revision'], old['revision'])

    def test_cold_view_build_uses_old_sql_head_without_waiting_paused_writer(self):
        writer_models = self.registry.read_models
        reader_registry, reader = self._reader()
        writer = self.registry.store(self.ids['one'])
        warmed = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        entered, release = threading.Event(), threading.Event()
        original = writer_models.appended

        def paused(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(*args, **kwargs)

        with patch.object(writer_models, 'appended', side_effect=paused), ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(writer.record, dict(kind='note', taskId='task', title='Cold old head'))
            try:
                self.assertTrue(entered.wait(5))
                with reader_registry.connect() as connection:
                    connection.execute('DELETE FROM read_model_views WHERE project=?', (reader.project_id,))
                    connection.execute('DELETE FROM read_model_details WHERE project=?', (reader.project_id,))
                reader_registry.read_models.views.clear()
                cold = pool.submit(reader_registry.read_models.snapshot,
                                   reader, observations=False, summary=True).result(timeout=2)
                self.assertEqual(warmed['revision'], cold['revision'])
                self.assertNotIn('Cold old head', [event.get('title') for event in cold['events']])
            finally:
                release.set()
            pending.result(timeout=5)
        fresh = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        self.assertIn('Cold old head', [event.get('title') for event in fresh['events']])

    def test_reader_handles_verify_gap_then_lends_old_head_before_publish(self):
        """The reader waits only for the proof gap, never for ownership."""
        import journal_append
        import task_transfer

        writer_models = self.registry.read_models
        reader_registry, reader = self._reader()
        writer = self.registry.store(self.ids['one'])
        warmed = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        verify_entered = threading.Event()
        release_verify = threading.Event()
        gap_seen = threading.Event()
        appended_entered = threading.Event()
        release_publish = threading.Event()
        reader_barrier_entered = threading.Event()
        original_verify = journal_append.verify_finish
        original_appended = writer_models.appended
        original_barrier = task_transfer.barrier

        def paused_verify(*args, **kwargs):
            verify_entered.set()
            self.assertTrue(release_verify.wait(5))
            return original_verify(*args, **kwargs)

        def paused_appended(*args, **kwargs):
            appended_entered.set()
            self.assertTrue(release_publish.wait(5))
            return original_appended(*args, **kwargs)

        def observe_barrier(registry):
            if registry is reader_registry:
                reader_barrier_entered.set()
            return original_barrier(registry)

        original_committed_read = reader_registry.read_models._committed_append_read

        def observe_committed_read(*args, **kwargs):
            result = original_committed_read(*args, **kwargs)
            if result is None:
                gap_seen.set()
            return result

        with patch.object(journal_append, 'verify_finish', side_effect=paused_verify), \
             patch.object(writer_models, 'appended', side_effect=paused_appended), \
             patch.object(task_transfer, 'barrier', side_effect=observe_barrier), \
             patch.object(reader_registry.read_models, '_committed_append_read',
                          side_effect=observe_committed_read), \
             ThreadPoolExecutor(max_workers=2) as pool:
            writer_future = pool.submit(writer.record,
                                        dict(kind='note', taskId='task', title='Proof gap'))
            reader_future = None
            try:
                self.assertTrue(verify_entered.wait(5))
                reader_future = pool.submit(reader_registry.read_models.snapshot,
                                            reader, observations=False, summary=True)
                self.assertTrue(gap_seen.wait(5))
                release_verify.set()
                self.assertTrue(appended_entered.wait(5))
                old = reader_future.result(timeout=2)
                self.assertEqual(warmed['revision'], old['revision'])
                self.assertNotIn('Proof gap', [event.get('title') for event in old['events']])
                self.assertFalse(reader_barrier_entered.is_set())
            finally:
                release_verify.set()
                release_publish.set()
            writer_future.result(timeout=5)
        fresh = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        self.assertIn('Proof gap', [event.get('title') for event in fresh['events']])
        self.assertNotEqual(warmed['revision'], fresh['revision'])

    def test_reader_races_first_signature_with_writer_and_lends_old_head(self):
        """A writer starting after the initial SQL query cannot strand a read."""
        import task_transfer

        writer_models = self.registry.read_models
        reader_registry, reader = self._reader()
        writer = self.registry.store(self.ids['one'])
        warmed = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        appended_entered, release_publish = threading.Event(), threading.Event()
        reader_barrier_entered = threading.Event()
        writer_done = threading.Event()
        writer_error = []
        writer_thread = None
        original_appended = writer_models.appended
        original_reuse = reader_registry.read_models.file_digests.reuse
        original_barrier = task_transfer.barrier

        def paused_appended(*args, **kwargs):
            appended_entered.set()
            self.assertTrue(release_publish.wait(5))
            return original_appended(*args, **kwargs)

        def write_raced_event():
            try:
                writer.record(dict(kind='note', taskId='task', title='First signature race'))
            except BaseException as error:  # surfaced after the reader is released
                writer_error.append(error)
            finally:
                writer_done.set()

        first_reader_signature = True

        def start_writer_before_reader_signature(path, **kwargs):
            nonlocal first_reader_signature, writer_thread
            if first_reader_signature:
                first_reader_signature = False
                writer_thread = threading.Thread(target=write_raced_event)
                writer_thread.start()
                self.assertTrue(appended_entered.wait(5))
            return original_reuse(path, **kwargs)

        def observe_barrier(registry):
            if registry is reader_registry:
                reader_barrier_entered.set()
            return original_barrier(registry)

        with patch.object(writer_models, 'appended', side_effect=paused_appended), \
             patch.object(reader_registry.read_models.file_digests, 'reuse', side_effect=start_writer_before_reader_signature), \
             patch.object(task_transfer, 'barrier', side_effect=observe_barrier), \
             ThreadPoolExecutor(max_workers=1) as pool:
            reader_future = pool.submit(reader_registry.read_models.snapshot,
                                        reader, observations=False, summary=True)
            try:
                old = reader_future.result(timeout=2)
                self.assertEqual(warmed['revision'], old['revision'])
                self.assertNotIn('First signature race',
                                 [event.get('title') for event in old['events']])
                self.assertFalse(reader_barrier_entered.is_set())
            except FutureTimeout:
                self.fail('reader blocked behind the writer ownership barrier after a signature race')
            finally:
                release_publish.set()
                if writer_thread is not None:
                    writer_thread.join(5)
            self.assertTrue(writer_done.is_set())
            if writer_error:
                raise writer_error[0]
        fresh = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        self.assertIn('First signature race', [event.get('title') for event in fresh['events']])
        self.assertNotEqual(warmed['revision'], fresh['revision'])

    def test_reader_rechecks_after_writer_finishes_before_visibility_probe(self):
        """A stale pending row must be reread if the writer finishes mid-probe."""
        import task_transfer

        writer_models = self.registry.read_models
        reader_registry, reader = self._reader()
        writer = self.registry.store(self.ids['one'])
        warmed = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        appended_entered, release_publish = threading.Event(), threading.Event()
        reader_barrier_entered = threading.Event()
        writer_error = []
        original_appended = writer_models.appended
        original_committed_read = reader_registry.read_models._committed_append_read
        original_barrier = task_transfer.barrier

        def paused_appended(*args, **kwargs):
            appended_entered.set()
            self.assertTrue(release_publish.wait(5))
            return original_appended(*args, **kwargs)

        def write_event():
            try:
                writer.record(dict(kind='note', taskId='task', title='Pending visibility race'))
            except BaseException as error:
                writer_error.append(error)

        def observe_barrier(registry):
            if registry is reader_registry:
                reader_barrier_entered.set()
            return original_barrier(registry)

        first_probe = True
        writer_future = None

        def finish_writer_before_probe(*args, **kwargs):
            nonlocal first_probe
            if first_probe:
                first_probe = False
                release_publish.set()
                writer_future.result(timeout=5)
            return original_committed_read(*args, **kwargs)

        with patch.object(writer_models, 'appended', side_effect=paused_appended), \
             patch.object(reader_registry.read_models, '_committed_append_read',
                          side_effect=finish_writer_before_probe), \
             patch.object(task_transfer, 'barrier', side_effect=observe_barrier), \
             ThreadPoolExecutor(max_workers=2) as pool:
            writer_future = pool.submit(write_event)
            reader_future = None
            try:
                self.assertTrue(appended_entered.wait(5))
                reader_future = pool.submit(reader_registry.read_models.snapshot,
                                            reader, observations=False, summary=True)
                fresh = reader_future.result(timeout=3)
                self.assertFalse(reader_barrier_entered.is_set())
                self.assertNotEqual(warmed['revision'], fresh['revision'])
                self.assertIn('Pending visibility race',
                              [event.get('title') for event in fresh['events']])
            finally:
                release_publish.set()
                if writer_future is not None:
                    writer_future.result(timeout=5)
            if writer_error:
                raise writer_error[0]

    def test_reader_lends_old_projection_while_intent_is_preappend_paused(self):
        reader_registry, reader = self._reader()
        writer = self.registry.store(self.ids['one'])
        warmed = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        entered, release = threading.Event(), threading.Event()

        def paused(point):
            if point == 'after_intent':
                entered.set()
                self.assertTrue(release.wait(5))

        with patch('journal_append.checkpoint', side_effect=paused), ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(writer.record, dict(kind='note', taskId='task', title='Intent paused'))
            try:
                self.assertTrue(entered.wait(5))
                old = reader_registry.read_models.snapshot(reader, observations=False, summary=True)
                self.assertEqual(warmed['revision'], old['revision'])
                self.assertNotIn('Intent paused', [event.get('title') for event in old['events']])
            finally:
                release.set()
            pending.result(timeout=5)
        self.assertIn('Intent paused', [event.get('title') for event in
                                        reader_registry.read_models.snapshot(reader, observations=False, summary=True)['events']])

    def test_tampered_paused_journal_is_not_lent_as_old_projection(self):
        reader_registry, reader = self._reader()
        writer = self.registry.store(self.ids['one'])
        entered, release = threading.Event(), threading.Event()

        def paused(point):
            if point == 'after_intent':
                entered.set()
                self.assertTrue(release.wait(5))

        with patch('journal_append.checkpoint', side_effect=paused), ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(writer.record, dict(kind='note', taskId='task', title='Tamper paused'))
            reader_future = None
            try:
                self.assertTrue(entered.wait(5))
                original = writer.journal.read_bytes()
                stat = writer.journal.stat()
                changed = bytearray(original)
                changed[0] = ord('X') if changed[0] != ord('X') else ord('Y')
                writer.journal.write_bytes(changed)
                os.utime(writer.journal, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                reader_future = pool.submit(reader_registry.read_models.snapshot,
                                            reader, observations=False, summary=True)
                with self.assertRaises(FutureTimeout):
                    reader_future.result(timeout=.05)
            finally:
                release.set()
            with self.assertRaises(ValueError):
                pending.result(timeout=5)
            with self.assertRaises(ValueError):
                reader_future.result(timeout=5)
        self.assertEqual(bytes(changed), writer.journal.read_bytes())

    def test_unrelated_writer_recovers_stale_intent_before_appending(self):
        writer = self.registry.store(self.ids['one'])
        reader_registry, reader = self._reader()
        reader_registry.read_models.snapshot(reader, observations=False, summary=True)
        with patch('journal_append.checkpoint', side_effect=lambda point:
                   (_ for _ in ()).throw(RuntimeError('stale intent')) if point == 'after_intent' else None):
            with self.assertRaisesRegex(RuntimeError, 'stale intent'):
                writer.record(dict(kind='note', taskId='task', title='Stale A'))
        from project_portal import Store
        other_project = self.registry.base_store(self.ids['two'])
        global_store = Store(self.registry.home)
        project_store = Store(other_project.root, data_dir=other_project.data)
        entered, release = threading.Event(), threading.Event()
        def hold_unrelated_writer():
            with global_store.locked(label='test-global-writer'):
                with project_store.locked(label='test-project-writer'):
                    entered.set()
                    release.wait(5)
        holder = threading.Thread(target=hold_unrelated_writer)
        holder.start()
        try:
            self.assertTrue(entered.wait(5))
            with ThreadPoolExecutor(max_workers=1) as pool:
                read_future = pool.submit(reader_registry.read_models.snapshot,
                                          reader, observations=False, summary=True)
                with self.assertRaises(FutureTimeout):
                    read_future.result(timeout=.05)
                release.set()
                result = read_future.result(timeout=5)
        finally:
            release.set()
            holder.join(5)
        self.assertIn('Stale A', [event.get('title') for event in result['events']])


if __name__ == '__main__':
    unittest.main()
