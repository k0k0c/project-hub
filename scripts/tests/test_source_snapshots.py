"""Removed evidence stays readable from the data home and portable archive."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry, CodexProjects
from artifact_store import publish
from source_snapshots import register
from hub_backup import create_archive, restore_copy


class SourceSnapshotsTest(unittest.TestCase):
    def test_removed_project_paths_survive_whole_home_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / 'project'; root.mkdir()
            catalog = base / 'catalog.json'
            catalog.write_text(json.dumps({'local-projects': {'example': {'id': 'example', 'name': 'Example', 'rootPaths': [str(root)]}}}))
            registry = ProjectRegistry(base / 'data', CodexProjects(catalog))
            pid = registry.list()['projects'][0]['id']
            store = registry.base_store(pid)
            name = 'docs/old-report.md'
            source = root / name; source.parent.mkdir(); source.write_bytes(b'Original report')
            data = source.read_bytes()
            content = io.BytesIO()
            with zipfile.ZipFile(content, 'w') as snapshot:
                snapshot.writestr(name, data)
                snapshot.writestr('archive-manifest.json', json.dumps({'kind': 'hub-source-snapshot',
                    'files': {name: hashlib.sha256(data).hexdigest()}}))
            ref = publish(store, 'source-snapshot.zip', content.getvalue())['source']['path']
            store.record({'kind': 'task.created', 'taskId': 'example-task', 'title': 'Example',
                          'patch': {'title': 'Example', 'status': 'active', 'sources': [{'path': name}]}})
            self.assertEqual(1, register(store, ref, [name])['registered'])
            source.unlink()
            self.assertFalse(store.resolve_path(name).exists())
            info = store.source_info(name)
            self.assertFalse(info['currentAvailable'])
            self.assertTrue(info['archiveAvailable'])
            with self.assertRaises(FileNotFoundError):
                store.read_evidence(name)
            path = store.resolve_evidence_path(name, 'archive')
            self.assertTrue(path.is_relative_to(registry.home))
            self.assertEqual(data, path.read_bytes())
            archived_info = store.source_info(name, 'archive')
            self.assertEqual('sha256:' + hashlib.sha256(data).hexdigest(), archived_info['version'])
            self.assertEqual(ref, archived_info['snapshot'])
            archive = base / 'backup.zip'; create_archive(registry, archive)
            restored = Path(restore_copy(archive, base / 'restored')['path'])
            other = ProjectRegistry(restored, CodexProjects(catalog))
            try:
                restored_store = other.base_store(pid)
                self.assertFalse(restored_store.resolve_path(name).exists())
                self.assertEqual(data, restored_store.resolve_evidence_path(name, 'archive').read_bytes())
            finally:
                other.close_connection_pool()
            source.write_bytes(b'Current source')
            self.assertEqual(b'Current source', store.resolve_path(name).read_bytes())
            self.assertEqual(data, store.resolve_evidence_path(name, 'archive').read_bytes())
            self.assertFalse((root / 'source-snapshots').exists())
            registry.close_connection_pool()

    def test_changed_source_rejected_without_alias_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); root = base / 'project'; root.mkdir()
            catalog = base / 'catalog.json'
            catalog.write_text(json.dumps({'local-projects': {'example': {'id': 'example', 'name': 'Example', 'rootPaths': [str(root)]}}}))
            registry = ProjectRegistry(base / 'data', CodexProjects(catalog))
            store = registry.base_store(registry.list()['projects'][0]['id'])
            (root / 'report.txt').write_bytes(b'Changed')
            content = io.BytesIO()
            with zipfile.ZipFile(content, 'w') as snapshot:
                snapshot.writestr('report.txt', b'Original')
                snapshot.writestr('archive-manifest.json', json.dumps({'kind': 'hub-source-snapshot',
                    'files': {'report.txt': hashlib.sha256(b'Original').hexdigest()}}))
            ref = publish(store, 'snapshot.zip', content.getvalue())['source']['path']
            with self.assertRaises(ValueError):register(store, ref, ['report.txt'])
            self.assertFalse((store.data / 'source-file-aliases.json').exists())
            registry.close_connection_pool()
