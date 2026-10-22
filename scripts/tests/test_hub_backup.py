"""Independent whole-store preservation and adversarial archive cases."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry, CodexProjects
from hub_backup import BackupError, create_archive, digest, preview_archive, restore_copy
from backup_api import Backups
from plugin_api import ServerHub
from knowledge_store import KnowledgeStore
from artifact_store import publish, resolve
from hub_instructions import Instructions


class BackupFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        catalog = self.base / 'catalog.json'
        for name in ('one', 'two'):
            (self.base / name).mkdir()
        catalog.write_text(json.dumps({'local-projects': {
            name: {'id': name, 'name': name, 'rootPaths': [str(self.base / name)]}
            for name in ('one', 'two')}}))
        self.registry = ProjectRegistry(self.base / 'data', CodexProjects(catalog))
        self.addCleanup(self.registry.close_connection_pool)
        self.ids = {p['name']: p['id'] for p in self.registry.list()['projects']}
        for name, pid in self.ids.items():
            store = self.registry.store(pid)
            store.record({'kind': 'task.created', 'taskId': name + '-task', 'title': name,
                          'patch': {'title': name, 'status': 'active', 'stages': [{'id': 'first', 'title': 'First', 'status': 'planned'}]}})
        ServerHub(self.registry)
        # Keep a committed WAL connection open throughout the snapshot.
        self.db = sqlite3.connect(self.registry.database, isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE preserved_extension(id TEXT PRIMARY KEY, value TEXT)')
        self.db.execute("INSERT INTO preserved_extension VALUES('one','committed WAL')")
        knowledge = KnowledgeStore(self.registry, self.ids['one'])
        knowledge.changeset(knowledge.context()['revision'], 'document', [
            {'op': 'put', 'item': {'id': 'doc:example', 'kind': 'document', 'title': 'Example', 'body': 'Original'}}], 'Document')
        knowledge.changeset(knowledge.context()['revision'], 'document-2', [
            {'op': 'put', 'item': {'id': 'doc:example', 'kind': 'document', 'title': 'Example', 'body': 'Updated'}}], 'Update')
        store = self.registry.store(self.ids['one'])
        first = publish(store, 'result.txt', b'first version')
        store.record({'kind': 'task.updated', 'taskId': 'one-task', 'title': 'Attach first result',
                      'patch': {'sources': [first['source']]}})
        self.artifact = publish(store, 'result.txt', b'second version', previous=first['source']['path'])['source']['path']
        store.record({'kind': 'task.updated', 'taskId': 'one-task', 'title': 'Attach second result',
                      'patch': {'sources': [first['source'], {'path': self.artifact}]}})
        with self.registry.coordination_connect() as db:
            db.execute('CREATE TABLE preserved_delivery(id TEXT PRIMARY KEY, body TEXT)')
            db.execute("INSERT INTO preserved_delivery VALUES('pending','not yet delivered')")
        self.instructions = Instructions(self.registry.home)
        self.skill_root = self.base / 'client/skills/project-hub-user'
        initial = self.instructions.initialize(self.skill_root)
        self.instructions.update(initial['revision'], {'userInstructions': 'Persistent preference'})
        (self.skill_root / 'helper.txt').write_text('Owned companion file')
        (self.skill_root / 'runtime').mkdir()
        (self.skill_root / 'runtime/helper.txt').write_text('Owned runtime companion')
        (self.registry.home / 'future-extension.json').write_text('{"preserved":true}')
        (self.registry.home / 'runtime').mkdir()
        (self.registry.home / 'runtime/server.err.log').write_text('Transient live log')
        generated = self.registry.home / 'language-servers/generated/cache'
        generated.parent.mkdir(parents=True)
        generated.write_text('Disposable')

    def archive(self):
        path = self.base / 'backup.zip'
        self.meta = create_archive(self.registry, path)
        return path

    def rewrite(self, original, *, mutate=None, extra=None, replace=None):
        path = self.base / ('altered-' + str(len(list(self.base.glob('altered-*')))) + '.zip')
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(path, 'w') as target:
            for info in source.infolist():
                data = source.read(info)
                if info.filename == 'manifest.json' and mutate:
                    manifest = json.loads(data)
                    mutate(manifest)
                    data = json.dumps(manifest).encode()
                if replace and info.filename in replace:
                    data = replace[info.filename]
                target.writestr(info, data)
            for name, data in (extra or {}).items():
                target.writestr(name, data)
        return path

    def test_two_projects_wal_history_artifacts_instructions_and_opaque_data(self):
        path = self.archive()
        before = {p.relative_to(self.registry.home).as_posix(): digest(p)
                  for p in self.registry.home.rglob('*') if p.is_file() and not p.name.endswith(('-shm', '-wal'))}
        skill_before = (self.skill_root / 'SKILL.md').read_bytes()
        preview = preview_archive(path)
        self.assertEqual(2, len(preview['projects']))
        self.assertTrue(all(p['tasks'] == 1 for p in preview['projects']))
        copied = Path(restore_copy(path, self.base / 'restored', digest(path))['path'])
        with closing(sqlite3.connect(copied / 'registry.sqlite3')) as db:
            self.assertEqual('committed WAL', db.execute('SELECT value FROM preserved_extension').fetchone()[0])
            self.assertEqual(2, db.execute('SELECT COUNT(*) FROM knowledge_changes').fetchone()[0])
        with closing(sqlite3.connect(copied / 'coordination/coordination.sqlite3')) as db:
            self.assertEqual('not yet delivered', db.execute('SELECT body FROM preserved_delivery').fetchone()[0])
        for pid in self.ids.values():
            self.assertEqual((self.registry.home / 'projects' / pid / 'events.jsonl').read_bytes(),
                             (copied / 'projects' / pid / 'events.jsonl').read_bytes())
        copy_registry = ProjectRegistry(copied, CodexProjects(self.base / 'catalog.json'))
        try:
            self.assertEqual(b'second version', resolve(copy_registry.store(self.ids['one']), self.artifact)[1])
            restored_instructions = Instructions(copied)
            self.assertEqual('Persistent preference', restored_instructions.read()['body'])
            self.assertEqual(copied / 'instructions/project-hub-user', restored_instructions.location())
            self.assertTrue(restored_instructions.read()['history'])
        finally:
            copy_registry.close_connection_pool()
        self.assertEqual('Owned companion file', (copied / 'instructions/project-hub-user/helper.txt').read_text())
        self.assertEqual('Owned runtime companion', (copied / 'instructions/project-hub-user/runtime/helper.txt').read_text())
        self.assertTrue((copied / 'future-extension.json').exists())
        self.assertFalse((copied / 'runtime').exists())
        self.assertFalse((copied / 'language-servers').exists())
        self.assertFalse((copied / 'registry.sqlite3-wal').exists())
        self.assertEqual(skill_before, (self.skill_root / 'SKILL.md').read_bytes())
        self.assertTrue(all(digest(self.registry.home / name) == checksum for name, checksum in before.items()))

    def test_safety_archive_reuses_the_same_consistent_snapshot(self):
        archive=self.base/'safety.zip';snapshot=self.base/'work-current'
        result=create_archive(self.registry,archive,snapshot_destination=snapshot)
        self.assertEqual(digest(archive),result['sha256'])
        with closing(sqlite3.connect(snapshot/'registry.sqlite3')) as db:
            self.assertEqual('committed WAL',db.execute("SELECT value FROM preserved_extension WHERE id='one'").fetchone()[0])
        copied=Path(restore_copy(archive,self.base/'safety-restored',result['sha256'])['path'])
        with closing(sqlite3.connect(copied/'registry.sqlite3')) as db:
            self.assertEqual('committed WAL',db.execute("SELECT value FROM preserved_extension WHERE id='one'").fetchone()[0])
        self.assertEqual(Instructions(copied).read()['body'],Instructions(snapshot).read()['body'])

    def test_minor_extensions_accepted_major_and_required_features_rejected(self):
        archive = self.archive()
        newer = self.rewrite(archive, mutate=lambda m: m.update(formatVersion={'major': 1, 'minor': 9},
            extensions={'org.example.note': {'message': 'optional'}}, futureMetadata={'version': 2}))
        self.assertEqual(9, preview_archive(newer)['formatVersion']['minor'])
        for mutation in (lambda m: m['formatVersion'].update(major=2),
                         lambda m: m['requiredFeatures'].append('unknown-mandatory-feature')):
            with self.subTest(mutation=mutation), self.assertRaises(BackupError):
                preview_archive(self.rewrite(archive, mutate=mutation))

    def test_tamper_traversal_case_alias_and_incomplete_members_rejected(self):
        archive = self.archive()
        cases = [self.rewrite(archive, replace={'home/future-extension.json': b'changed'}),
                 self.rewrite(archive, extra={'../outside.txt': b'bad'}),
                 self.rewrite(archive, extra={'HOME/future-extension.json': b'bad'}),
                 self.rewrite(archive, extra={'home/CON.txt': b'bad'}),
                 self.rewrite(archive, mutate=lambda m: m['files'].pop('home/future-extension.json')),
                 self.rewrite(archive, mutate=lambda m: m['projects'].clear())]
        for path in cases:
            with self.subTest(path=path.name), self.assertRaises(BackupError):
                restore_copy(path, self.base / ('target-' + path.stem))
            self.assertFalse((self.base / ('target-' + path.stem)).exists())
        self.assertFalse((self.base / 'outside.txt').exists())

    def test_existing_destination_and_changed_archive_never_overwritten(self):
        archive = self.archive()
        target = self.base / 'existing'
        target.mkdir()
        marker = target / 'keep.txt'
        marker.write_text('keep')
        with self.assertRaises(BackupError):
            restore_copy(archive, target)
        self.assertEqual('keep', marker.read_text())
        with self.assertRaises(BackupError):
            restore_copy(archive, self.base / 'new', '0' * 64)
        self.assertFalse((self.base / 'new').exists())

    def test_publication_failure_marks_only_new_destination_incomplete(self):
        archive = self.archive()
        target = self.base / 'interrupted'
        original = Path.rename
        def fail_publish(path, other):
            if Path(other) == target / 'data':
                raise OSError('Simulated filesystem failure')
            return original(path, other)
        with patch.object(Path, 'rename', fail_publish), self.assertRaises(OSError):
            restore_copy(archive, target)
        self.assertTrue((target / 'INCOMPLETE').exists())
        self.assertTrue(self.registry.database.exists())

    def test_upload_abort_releases_capacity_and_ready_archive_cannot_be_aborted(self):
        service = Backups(self.registry)
        ids = [service.execute({'action': 'upload-start', 'name': 'backup.zip', 'size': 10})['id'] for _ in range(2)]
        with self.assertRaises(BackupError):
            service.execute({'action': 'upload-start', 'name': 'backup.zip', 'size': 10})
        self.assertTrue(service.execute({'action': 'upload-abort', 'id': ids[0]})['cancelled'])
        self.assertTrue(service.execute({'action': 'upload-abort', 'id': ids[0]})['cancelled'])
        service.execute({'action': 'upload-start', 'name': 'new.zip', 'size': 10})
        meta = service.execute({'action': 'create'})['backup']
        with self.assertRaises(BackupError):
            service.execute({'action': 'upload-abort', 'id': meta['id']})
        self.assertEqual(1, len(service.catalog()['backups']))
