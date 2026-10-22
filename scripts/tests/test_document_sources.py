"""Current/archive contracts using disposable projects, catalogs and HTTP servers."""
import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import PortalServer
from project_registry import ProjectRegistry, CodexProjects
from task_transfer import transfer


class DocumentSourcesFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        catalog = self.base/'catalog.json'
        catalog.write_text(json.dumps({'local-projects': {p: dict(id=p, name=p, rootPaths=[str(self.base/p)]) for p in ('a', 'b')}}))
        self.registry = ProjectRegistry(self.base/'data', CodexProjects(catalog))
        self.ids = {p['name']: p['id'] for p in self.registry.list()['projects']}
        self.store = self.registry.store(self.ids['a'])
        self.store.root.mkdir()
        self.current = self.store.root/'proof.md'
        self.current.write_bytes(b'current\r\n')
        self.store.record(dict(kind='task.created', taskId='task', title='Task', patch=dict(title='Task', status='active', stages=[], sources=[dict(path='proof.md')])))
        self.archive = self.store.data/'source-archive'/'proof.md'
        self.archive.parent.mkdir()
        self.archive.write_bytes(b'archived\r\n')
        self.server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def get(self, route, **query):
        query.setdefault('project', self.ids['a'])
        query.setdefault('path', 'proof.md')
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request('GET', route+'?'+urlencode(query))
            response = conn.getresponse()
            data = response.read()
            return response.status, json.loads(data) if 'application/json' in response.getheader('Content-Type') else data
        finally:
            conn.close()

class DocumentSourcesTest(DocumentSourcesFixture):
    def test_current_updates_archive_remains_explicit_and_unchanged(self):
        archived_hash = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.assertEqual(self.get('/api/evidence'), (200, b'current\r\n'))
        self.current.write_bytes(b'new working document')
        status, data = self.get('/api/document')
        self.assertEqual(status, 200)
        self.assertEqual(data['text'], 'new working document')
        self.assertEqual(data['source']['kind'], 'current')
        self.assertEqual(data['source']['sourceProject'], self.ids['a'])
        self.assertEqual(Path(data['source']['resolvedPath']), self.current)
        self.assertEqual(self.get('/api/evidence', mode='archive'), (200, b'archived\r\n'))
        _, archived = self.get('/api/document', mode='archive')
        self.assertEqual(archived['source']['sha256'], archived_hash)
        self.assertEqual(archived['source']['version'], 'sha256:'+archived_hash)
        self.assertEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(), archived_hash)

    def test_standalone_html_keeps_bytes_modes_and_isolation(self):
        raw = b'<!doctype html>\r\n<style>body{background:white}</style><button onclick="this.textContent=42">Plan</button><script>document.title="Original"</script>'
        (self.store.root/'plan.HTML').write_bytes(raw)
        (self.store.data/'source-archive'/'plan.HTML').write_bytes(b'<h1>Archived</h1>')
        self.store.record(dict(kind='task.updated', taskId='task', title='Attach HTML plan', patch=dict(sources=[dict(path='proof.md'), dict(path='plan.HTML')])))

        def request(path, **options):
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
            try:
                conn.request('GET', '/api/evidence?'+urlencode(dict(project=self.ids['a'], path=path, **options)))
                response = conn.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                conn.close()

        status, headers, data = request('plan.HTML', preview='html')
        self.assertEqual((status, data), (200, raw))
        self.assertEqual(headers['Content-Type'], 'text/html; charset=utf-8')
        self.assertNotIn('Content-Disposition', headers)
        policy = headers['Content-Security-Policy']
        self.assertIn('sandbox allow-scripts;', policy)
        self.assertIn("script-src 'unsafe-inline'", policy)
        self.assertIn("connect-src 'none'", policy)
        self.assertNotIn('allow-same-origin', policy)
        self.assertEqual(request('plan.HTML', mode='archive', preview='html')[2], b'<h1>Archived</h1>')
        self.assertEqual(request('plan.HTML')[1]['Content-Type'], 'text/plain; charset=utf-8')
        self.assertEqual(request('proof.md', preview='html')[0], 400)
        (self.store.root/'unregistered.html').write_bytes(raw)
        self.assertEqual(request('unregistered.html', preview='html')[0], 400)

    def test_reads_reuse_initial_source_lookup_and_keep_post_read_validation(self):
        for mode, expected in [('current', 'current\r\n'), ('archive', 'archived\r\n')]:
            with self.subTest(mode=mode):
                with patch.object(self.store, 'source_info', wraps=self.store.source_info) as lookup:
                    self.assertEqual(self.store.document('proof.md', mode)['text'], expected)
                    self.assertEqual(lookup.call_count, 2, 'one initial lookup and one post-read validation')
                with patch.object(self.store, 'source_info', wraps=self.store.source_info) as lookup:
                    self.assertEqual(self.store.log_page('proof.md', mode=mode)['rows'][0]['text'], expected.strip())
                    self.assertEqual(lookup.call_count, 1)
        initial = self.store.source_info('proof.md')
        with patch.object(self.store, 'source_info', side_effect=[initial, ValueError('registration revoked')]):
            with self.assertRaisesRegex(ValueError, 'registration revoked'):
                self.store.document('proof.md')
        with patch.object(self.store, 'source_info', side_effect=[initial, {**initial, 'version':'changed'}]):
            with self.assertRaisesRegex(ValueError, 'File changed'):
                self.store.document('proof.md')

    def test_missing_current_never_substitutes_archive(self):
        self.current.unlink()
        self.assertEqual(self.get('/api/evidence')[0], 404)
        self.assertEqual(self.get('/api/document')[0], 404)
        self.assertEqual(self.get('/api/log')[0], 404)
        status, source = self.get('/api/source')
        self.assertEqual(status, 200)
        self.assertFalse(source['available'])
        self.assertTrue(source['archiveAvailable'])
        self.assertEqual(self.get('/api/evidence', mode='archive'), (200, b'archived\r\n'))
        self.archive.unlink()
        self.assertEqual(self.get('/api/document', mode='archive')[0], 404)

    def test_transferred_evidence_keeps_original_project_for_both_modes(self):
        preview = transfer(self.registry, self.ids['a'], self.ids['b'], 'task', preview=True)
        transfer(self.registry, self.ids['a'], self.ids['b'], 'task', preview['revision'], 'move')
        target = self.registry.store(self.ids['b'])
        target.root.mkdir()
        (target.root/'proof.md').write_text('wrong project')
        visible = target.snapshot()['tasks'][0]['sources'][0]['path']
        for mode, expected in [('current', 'current\r\n'), ('archive', 'archived\r\n')]:
            status, doc = self.get('/api/document', project=self.ids['b'], path=visible, mode=mode)
            self.assertEqual(status, 200)
            self.assertEqual(doc['text'], expected)
            self.assertEqual(doc['source']['sourceProject'], self.ids['a'])
        self.assertEqual(self.get('/api/document', project=self.ids['b'])[0], 400)

    def test_log_mode_versions_and_registration(self):
        _, page = self.get('/api/log')
        self.assertEqual(page['source']['kind'], 'current')
        self.assertEqual(page['rows'][0]['text'], 'current')
        self.assertEqual(self.get('/api/log', mode='archive', version=page['version'])[0], 400)
        _, archived = self.get('/api/log', mode='archive')
        self.assertEqual(archived['rows'][0]['text'], 'archived')
        self.assertEqual(archived['source']['kind'], 'archive')
        for mode in ('current', 'archive'):
            for path in ('../proof.md', 'unknown.md'):
                self.assertEqual(self.get('/api/source', path=path, mode=mode)[0], 400)
                self.assertEqual(self.get('/api/document', path=path, mode=mode)[0], 400)
                self.assertEqual(self.get('/api/log', path=path, mode=mode)[0], 400)
        self.assertEqual(self.get('/api/source', mode='auto')[0], 400)
if __name__ == '__main__':
    unittest.main()
