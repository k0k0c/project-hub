"""Image attachment contracts against disposable projects and an HTTP server."""
import base64
import http.client
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_document_sources import DocumentSourcesFixture
from test_image_sources import jpeg
from plugin_api import call
from task_transfer import transfer


class ImageHttpTest(DocumentSourcesFixture):
    def post(self, body, route='/api/v1/images/upload', origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        try:
            conn.request('POST', route + '?' + urlencode({'project': self.ids['a']}), json.dumps(body), headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def invoke(self, tool, **args):
        return call(self.registry, dict(cwd=str(self.store.root), session='image-agent', tool=tool, arguments=args))

    def upload_svg(self):
        raw = b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30" fill="red"/></svg>'
        status, result = self.post(dict(name='diagram.svg', content=base64.b64encode(raw).decode()))
        self.assertEqual(status, 200, result)
        return raw, result['source']

    def test_upload_requires_registration_and_attachment_is_idempotent(self):
        raw, source = self.upload_svg()
        self.assertEqual(self.get('/api/image', path=source['path'])[0], 400)
        self.invoke('hub_context')
        result = self.invoke('hub_image', task='task', path=source['path'], expected=self.store.snapshot()['revision'])
        self.assertEqual(self.get('/api/image', path=source['path'], preview='original'), (200, raw))
        retry = self.invoke('hub_image', task='task', path=source['path'], expected=result['revision'])
        self.assertEqual(retry['revision'], result['revision'])
        self.assertEqual(len(self.store.snapshot()['tasks'][0]['sources']), 2)
        self.assertEqual(self.get('/api/document', path=source['path'])[0], 400)
        info = self.invoke('hub_memory', ref='source:' + source['path'])
        self.assertIn('sha256', info)
        self.assertNotIn('text', info)

    def test_stage_attachment_and_transfer_preserve_original(self):
        raw, source = self.upload_svg()
        self.invoke('hub_context')
        self.invoke('hub_plan', task='task', stage='visual', title='Visual', remaining=['Inspect'])
        self.invoke('hub_image', task='task', stage='visual', path=source['path'], expected=self.store.snapshot()['revision'])
        task = self.store.snapshot()['tasks'][0]
        self.assertEqual(task['stages'][0]['evidence'][0]['path'], source['path'])
        self.assertEqual(task['sources'][0]['path'], 'proof.md')
        preview = transfer(self.registry, self.ids['a'], self.ids['b'], 'task', preview=True)
        transfer(self.registry, self.ids['a'], self.ids['b'], 'task', preview['revision'], 'image-move')
        target = self.registry.store(self.ids['b']).snapshot()['tasks'][0]
        path = target['stages'][0]['evidence'][0]['path']
        self.assertEqual(self.get('/api/image', project=self.ids['b'], path=path, preview='original'), (200, raw))

    def test_stale_revision_and_unknown_stage_do_not_attach(self):
        _, source = self.upload_svg()
        self.invoke('hub_context')
        for values in [dict(expected='stale'), dict(expected=self.store.snapshot()['revision'], stage='missing')]:
            with self.assertRaises(ValueError):
                self.invoke('hub_image', task='task', path=source['path'], **values)
        self.assertEqual(len(self.store.snapshot()['tasks'][0]['sources']), 1)

    def assert_jpeg_source(self, path, raw, **query):
        status, info = self.get('/api/source', path=path, **query)
        self.assertEqual(status, 200, info)
        self.assertTrue(info['available'])
        self.assertEqual(info['image'], dict(format='jpeg', mime='image/jpeg', previewAvailable=True))
        for preview in ('original', 'thumbnail', 'full'):
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
            try:
                params = dict(project=self.ids['a'], path=path, preview=preview)
                params.update(query)
                conn.request('GET', '/api/image?' + urlencode(params))
                response = conn.getresponse()
                body = response.read()
                self.assertEqual(response.status, 200, body)
                if preview == 'original':
                    self.assertEqual(body, raw)
                    self.assertEqual(response.getheader('Content-Type'), 'image/jpeg')
                else:
                    # Optional Pillow converts previews to PNG; native fallback keeps JPEG.
                    expected_mime = 'image/png' if body.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg'
                    self.assertEqual(response.getheader('Content-Type'), expected_mime)
                    self.assertTrue(body.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')))
            finally:
                conn.close()

    def test_misnamed_jpeg_current_and_archive_use_actual_format(self):
        raw = jpeg()
        (self.store.root / 'capture.png').write_bytes(raw)
        (self.store.data / 'source-archive' / 'capture.png').write_bytes(raw)
        self.store.record(dict(kind='task.updated', taskId='task', title='Attach capture',
                               patch=dict(sources=[dict(path='capture.png')])))
        for mode in ('current', 'archive'):
            with self.subTest(mode=mode):
                self.assert_jpeg_source('capture.png', raw, mode=mode)
        self.assertEqual((self.store.root / 'capture.png').read_bytes(), raw)

    def test_misnamed_jpeg_artifact_and_transfer_keep_reference_and_original(self):
        # Seed the old descriptor format: new publications correct this suffix.
        from artifact_store import publish, register_descriptor
        from knowledge_store import KnowledgeStore
        raw = jpeg()
        item = dict(publish(self.store, 'capture.jpg', raw)['artifact'], name='capture.png')
        knowledge = KnowledgeStore(self.registry, self.ids['a'])
        identifier = knowledge.blob(json.dumps(item, sort_keys=True, separators=(',', ':')).encode())
        register_descriptor(knowledge, identifier)
        source = dict(path=f'hub-artifact/{identifier}/capture.png')
        self.invoke('hub_context')
        self.invoke('hub_artifact', task='task', path=source['path'], expected=self.store.snapshot()['revision'])
        self.assert_jpeg_source(source['path'], raw)
        self.assertEqual(self.get('/api/artifact', path=source['path']), (200, raw))
        transfer(self.registry, self.ids['a'], self.ids['b'], 'task',
                 expected=self.store.snapshot()['revision'], request='misnamed-image-move')
        target = self.registry.store(self.ids['b']).snapshot()['tasks'][0]
        moved = next(item['path'] for item in target['sources'] if item['path'].endswith('/capture.png'))
        self.assertTrue(moved.endswith(source['path']))
        self.assert_jpeg_source(moved, raw, project=self.ids['b'])

    def test_invalid_upload_and_cross_origin_are_rejected(self):
        self.assertEqual(self.post(dict(name='bad.png', content=base64.b64encode(b'not an image').decode()))[0], 409)
        self.assertEqual(self.post(dict(name='../bad.png', content='AA=='))[0], 409)
        self.assertEqual(self.post(dict(name='bad.png', content='AA=='), origin='https://example.com')[0], 403)

    def test_html_artifact_opens_original_page_and_keeps_explicit_download(self):
        raw = b'<!doctype html>\r\n<title>Plan</title><style>body{color:red}</style><h1>Original</h1><script>document.title="Plan"</script>'
        status, result = self.post(dict(name='plan.html', content=base64.b64encode(raw).decode()), route='/api/v1/artifacts/upload')
        self.assertEqual(status, 200, result)
        path = result['source']['path']
        self.assertEqual(self.get('/api/artifact', path=path, preview='html')[0], 400)
        self.invoke('hub_context')
        self.invoke('hub_artifact', task='task', path=path, expected=self.store.snapshot()['revision'])
        for preview in (None, 'html'):
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
            try:
                params = dict(project=self.ids['a'], path=path)
                if preview:
                    params['preview'] = preview
                conn.request('GET', '/api/artifact?' + urlencode(params))
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), raw)
                self.assertTrue(response.getheader('ETag'))
                if preview:
                    self.assertEqual(response.getheader('Content-Type'), 'text/html; charset=utf-8')
                    self.assertIsNone(response.getheader('Content-Disposition'))
                    self.assertIn('sandbox allow-scripts;', response.getheader('Content-Security-Policy'))
                    self.assertNotIn('allow-same-origin', response.getheader('Content-Security-Policy'))
                else:
                    self.assertEqual(response.getheader('Content-Type'), 'application/octet-stream')
                    self.assertIn('attachment;', response.getheader('Content-Disposition'))
            finally:
                conn.close()
        self.assertEqual(self.get('/api/artifact', path=path, mode='archive', preview='html')[0], 400)

    def test_original_has_download_and_sandbox_headers(self):
        _, source = self.upload_svg()
        self.invoke('hub_context')
        self.invoke('hub_image', task='task', path=source['path'], expected=self.store.snapshot()['revision'])
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request('GET', '/api/image?' + urlencode(dict(project=self.ids['a'], path=source['path'], preview='original')))
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(response.getheader('Content-Disposition').startswith("attachment; filename*=UTF-8''"))
            self.assertTrue(response.getheader('Content-Disposition').endswith('.svg'))
            self.assertIn('sandbox', response.getheader('Content-Security-Policy'))
            response.read()
        finally:
            conn.close()
