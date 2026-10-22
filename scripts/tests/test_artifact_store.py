"""Any-format artifacts, compatibility and integrity on disposable registries."""
import base64
import hashlib
import http.client
import json
from urllib.parse import urlencode

from test_document_sources import DocumentSourcesFixture
from artifact_store import publish, resolve, parse, materialize
from knowledge_store import KnowledgeStore, KnowledgeError
from task_transfer import transfer
from plugin_api import call
from test_image_sources import jpeg, png


class ArtifactStoreTest(DocumentSourcesFixture):
    def invoke(self, tool, **args):
        return call(self.registry, dict(cwd=str(self.store.root), session='artifact-agent', tool=tool, arguments=args))

    def attach(self, source):
        task = self.store.memory_snapshot()['tasks'][0]
        self.store.record(dict(kind='task.updated', taskId='task', title='Artifact attached',
                               patch=dict(sources=[*task['sources'], source])))

    def upload(self, name, content, **extra):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            body = dict(name=name, content=base64.b64encode(content).decode(), **extra)
            connection.request('POST', '/api/v1/artifacts/upload?' + urlencode(dict(project=self.ids['a'])),
                               json.dumps(body), {'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_unknown_format_stays_outside_checkout_and_requires_registration(self):
        before = {path.relative_to(self.store.root) for path in self.store.root.rglob('*')}
        content = b'\x00opaque\xff\x01'
        status, result = self.upload('evidence.unknown', content, roles=['evidence', 'test-fixture'])
        self.assertEqual(status, 200, result)
        source = result['source']
        self.assertEqual(self.get('/api/artifact', path=source['path'])[0], 400)
        self.attach(source)
        self.assertEqual(self.get('/api/artifact', path=source['path']), (200, content))
        info = self.store.source_info(source['path'])
        self.assertEqual(info['sha256'], hashlib.sha256(content).hexdigest())
        self.assertEqual(info['roles'], ['evidence', 'test-fixture'])
        self.assertFalse(info['textPreviewAvailable'])
        self.assertEqual(before, {path.relative_to(self.store.root) for path in self.store.root.rglob('*')})
        with self.assertRaisesRegex(ValueError, 'preview'):
            self.store.document(source['path'])
        # Attaching a product source leaves its current file and validation
        # boundary intact; snapshots do not redefine runtime input ownership.
        self.assertEqual(self.store.evidence('proof.md'), b'current\r\n')

    def test_versions_deduplicate_and_preserve_id_and_transfer_provenance(self):
        first = publish(self.store, 'result.dat', b'old')
        self.assertEqual(first, publish(self.store, 'result.dat', b'old'))
        self.attach(first['source'])
        second = publish(self.store, 'result.dat', b'new', previous=first['source']['path'])
        self.attach(second['source'])
        self.assertEqual(first['artifact']['artifactId'], second['artifact']['artifactId'])
        self.assertEqual(second['artifact']['previous'], first['descriptorHash'])
        transfer(self.registry, self.ids['a'], self.ids['b'], 'task',
                 expected=self.store.snapshot()['revision'], request='artifact-move')
        target = self.registry.store(self.ids['b'])
        refs = [source['path'] for source in target.memory_snapshot()['tasks'][0]['sources'] if 'hub-artifact/' in source['path']]
        self.assertEqual([target.evidence(ref) for ref in refs], [b'old', b'new'])
        self.assertEqual(target.source_info(refs[0])['sourceProject'], self.ids['a'])
        continued = publish(target, 'result.dat', b'continued', previous=refs[1])
        self.assertEqual(continued['artifact']['artifactId'], first['artifact']['artifactId'])
        backup = KnowledgeStore(self.registry, self.ids['b']).backup()
        self.assertTrue({first['descriptorHash'], second['descriptorHash'], continued['descriptorHash']}
                        <= set(backup['artifactDescriptors']))

    def test_image_upload_corrects_suffix_before_immutable_publication(self):
        for requested, raw, expected in [('capture.png', jpeg(), 'capture.jpg'),
                                          ('diagram.jpg', png(), 'diagram.png')]:
            with self.subTest(requested=requested):
                status, result = self.upload(requested, raw)
                self.assertEqual(status, 200, result)
                self.assertEqual(result['artifact']['name'], expected)
                self.assertEqual(result['artifact']['originalName'], requested)
                self.assertTrue(result['source']['path'].endswith('/' + expected))
                self.assertEqual(self.upload(requested, raw)[1]['source'], result['source'])
                self.attach(result['source'])
                descriptor, original = resolve(self.store, result['source']['path'])
                self.assertEqual(original, raw)
                self.assertEqual(descriptor['originalName'], requested)
                backup = KnowledgeStore(self.registry, self.ids['a']).backup()
                KnowledgeStore(self.registry, self.ids['b']).restore_backup(backup)
                self.assertEqual(resolve(self.registry.store(self.ids['b']), result['source']['path']),
                                 (descriptor, raw))

    def test_agent_import_corrects_image_name_without_renaming_product_file(self):
        raw = jpeg()
        path = self.store.root / 'capture.png'
        path.write_bytes(raw)
        self.invoke('hub_context')
        result = self.invoke('hub_artifact', task='task', path='capture.png',
                             expected=self.store.snapshot()['revision'])
        self.assertTrue(result['source']['path'].endswith('/capture.jpg'))
        self.assertEqual(result['artifact']['originalName'], 'capture.png')
        self.assertEqual(result['artifact']['provenance'], 'project-source:capture.png')
        self.assertEqual(path.read_bytes(), raw)
        self.assertFalse((self.store.root / 'capture.jpg').exists())
        self.assertEqual(self.store.evidence(result['source']['path']), raw)

    def test_opaque_and_unsafe_image_named_artifacts_are_not_rewritten(self):
        for raw in (b'opaque bytes', b'<svg onload="x()"/>'):
            with self.subTest(raw=raw):
                status, result = self.upload('opaque.png', raw)
                self.assertEqual(status, 200, result)
                self.assertEqual(result['artifact']['name'], 'opaque.png')
                self.assertNotIn('originalName', result['artifact'])
                self.attach(result['source'])
                self.assertEqual(self.get('/api/artifact', path=result['source']['path']), (200, raw))
                self.assertEqual(self.get('/api/image', path=result['source']['path'])[0], 400)

    def test_corruption_name_forgery_and_unregistered_previous_fail_closed(self):
        result = publish(self.store, 'original.dat', b'bytes')
        reference = result['source']['path']
        with self.assertRaises(ValueError):
            resolve(self.store, reference.rsplit('/', 1)[0] + '/forged.dat')
        with self.assertRaises(ValueError):
            publish(self.store, 'next.dat', b'new', previous=reference)
        self.attach(result['source'])
        path = materialize(self.store, reference)
        path.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.source_info(reference)
        self.assertEqual(self.upload('../bad.dat', b'bytes')[0], 409)
        self.assertEqual(self.upload('bad.dat', b'bytes', roles=['exclude-tests'])[0], 409)

    def test_backup_contains_task_only_descriptors_and_all_content_versions(self):
        first = publish(self.store, 'report.bin', b'first')
        self.attach(first['source'])
        second = publish(self.store, 'report.bin', b'second', previous=first['source']['path'])
        self.attach(second['source'])
        backup = KnowledgeStore(self.registry, self.ids['a']).backup()
        expected = {first['descriptorHash'], second['descriptorHash'],
                    first['artifact']['contentHash'], second['artifact']['contentHash']}
        self.assertTrue(expected <= backup['blobs'].keys())
        KnowledgeStore(self.registry, self.ids['b']).restore_backup(backup)
        for entry in (first, second):
            self.assertEqual(resolve(self.registry.store(self.ids['b']), entry['source']['path'])[0], entry['artifact'])
        self.assertEqual(KnowledgeStore(self.registry, self.ids['b']).backup()['artifactDescriptors'], backup['artifactDescriptors'])

    def test_arbitrary_descriptor_looking_json_is_opaque_and_history_is_required(self):
        first = publish(self.store, 'opaque.json', b'{"kind":"artifact-descriptor","arbitrary":"bytes"}')
        self.attach(first['source'])
        second = publish(self.store, 'opaque.json', b'next', previous=first['source']['path'])
        backup = KnowledgeStore(self.registry, self.ids['a']).backup()
        self.assertEqual(set(backup['artifactDescriptors']), {first['descriptorHash'], second['descriptorHash']})
        del backup['blobs'][first['descriptorHash']]
        with self.assertRaises(KnowledgeError) as raised:
            KnowledgeStore(self.registry, self.ids['b']).restore_backup(backup)
        self.assertEqual(raised.exception.body['error'], 'invalid_backup')

    def test_agent_attachment_snapshots_product_file_and_preserves_multi_role_input(self):
        path = self.store.root / 'fixture.bin'
        path.write_bytes(b'\x00original')
        self.invoke('hub_context')
        self.invoke('hub_plan', task='task', stage='implementation', title='Implementation', remaining=['Check'])
        args = dict(task='task', stage='implementation', path='fixture.bin', roles=['evidence', 'test-fixture'])
        first = self.invoke('hub_artifact', expected=self.store.snapshot()['revision'], **args)
        retry = self.invoke('hub_artifact', expected=first['revision'], **args)
        self.assertEqual(first['revision'], retry['revision'])
        self.assertEqual(first['artifact']['roles'], ['evidence', 'test-fixture'])
        self.assertEqual(path.read_bytes(), b'\x00original')
        path.write_bytes(b'\x00updated')
        self.assertEqual(self.store.evidence(first['source']['path']), b'\x00original')
        second = self.invoke('hub_artifact', expected=first['revision'], previous=first['source']['path'], **args)
        self.assertEqual(first['artifact']['artifactId'], second['artifact']['artifactId'])
        self.assertEqual(len(self.store.snapshot()['tasks'][0]['stages'][0]['evidence']), 2)
        metadata = self.invoke('hub_memory', ref='source:' + second['source']['path'])
        self.assertNotIn('text', metadata)
        self.assertEqual(metadata['sha256'], hashlib.sha256(b'\x00updated').hexdigest())
