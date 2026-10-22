import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepared_sources import PreparedSources
from project_registry import ProjectRegistry


class PreparedSourceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.registry = ProjectRegistry(self.root / 'data')
        self.prepared = PreparedSources(self.registry)
        self.addCleanup(self.prepared.close)
        self.path = self.root / 'image.svg'
        self.raw = b'<svg width="30" height="20"><rect width="30" height="20" fill="red"/></svg>'
        self.path.write_bytes(self.raw)

    def test_persisted_derivative_survives_restart_and_304_skips_decoder(self):
        data, mime, etag = self.prepared.image(self.path, 'thumbnail')
        self.assertEqual(data, self.raw)
        restarted = PreparedSources(ProjectRegistry(self.registry.home))
        self.addCleanup(restarted.close)
        with patch('image_sources.read_image', side_effect=AssertionError('decoder forbidden')):
            self.assertEqual((data,mime,etag), restarted.image(self.path, 'thumbnail'))
            self.assertEqual((b'',mime,etag), restarted.image(self.path, 'thumbnail', if_none_match=etag))

    def test_restored_timestamps_and_same_size_content_do_not_reuse_old_preview(self):
        old = self.prepared.image(self.path, 'thumbnail')
        stat = self.path.stat()
        changed = self.raw.replace(b'red', b'tan')
        self.path.write_bytes(changed)
        os.utime(self.path, ns=(stat.st_atime_ns,stat.st_mtime_ns))
        new = self.prepared.image(self.path, 'thumbnail', if_none_match=old[2])
        self.assertEqual(changed, new[0])
        self.assertNotEqual(old[2], new[2])

    def test_warm_read_uses_immutable_blob_without_publication_lock(self):
        old = self.prepared.image(self.path, 'thumbnail')
        # Complete startup maintenance before excluding all stripe acquisition.
        self.prepared.close()
        with patch.object(self.prepared, 'locked', side_effect=AssertionError('warm publication lock')):
            self.assertEqual(old, self.prepared.image(self.path, 'thumbnail'))
            self.assertEqual((b'', old[1], old[2]), self.prepared.image(self.path, 'thumbnail', if_none_match=old[2]))

    def test_parallel_and_independent_services_decode_a_content_key_once(self):
        other = PreparedSources(ProjectRegistry(self.registry.home))
        self.addCleanup(other.close)
        from image_sources import read_image
        with patch('image_sources.read_image', wraps=read_image) as decoder:
            with ThreadPoolExecutor(max_workers=10) as executor:
                values = list(executor.map(lambda n: (other if n%2 else self.prepared).image(self.path, 'full'), range(10)))
            self.assertEqual(1, decoder.call_count)
            self.assertTrue(all(v == values[0] for v in values))

    def test_damaged_derived_file_is_not_served_and_next_request_rebuilds(self):
        old = self.prepared.image(self.path, 'thumbnail')
        filename = next(self.prepared.home.glob('*.blob'))
        filename.write_bytes(b'damaged')
        with self.assertRaisesRegex(ValueError, 'damaged'):
            self.prepared.image(self.path, 'thumbnail', if_none_match=old[2])
        self.assertEqual(old, self.prepared.image(self.path, 'thumbnail'))

    def test_cache_pruning_removes_only_derived_data_and_rebuilds_evicted_preview(self):
        self.prepared.close()
        self.prepared = PreparedSources(self.registry, max_entries=1)
        self.addCleanup(self.prepared.close)
        first = self.prepared.image(self.path, 'thumbnail')
        self.path.write_bytes(self.raw.replace(b'red', b'tan'))
        second = self.prepared.image(self.path, 'thumbnail')
        self.prepared.prune()
        self.assertEqual(1, len(list(self.prepared.home.glob('*.blob'))))
        self.assertEqual(self.raw.replace(b'red',b'tan'), self.path.read_bytes())
        self.assertEqual(second, self.prepared.image(self.path,'thumbnail'))
        self.path.write_bytes(self.raw)
        self.assertEqual(first, self.prepared.image(self.path,'thumbnail'))
