"""Portal archive lifecycle, origin policy and streaming in both transports."""
import asyncio
import base64
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry, CodexProjects
from project_portal import PortalServer
from portal_asgi import PortalASGI
from backup_api import CHUNK_BYTES, REQUEST_LIMIT
from hub_backup import digest
from hub_import import inspect_home
from hub_lifecycle import home_lease
from backup_api import Backups
from unittest.mock import patch
import uuid


def private_registry(base):
    catalog = base / 'catalog.json'
    catalog.write_text(json.dumps({'local-projects': {}}))
    registry = ProjectRegistry(base / 'data', CodexProjects(catalog))
    registry.refresh()
    return registry


class BackupHTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.registry = private_registry(self.base)
        self.server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join()
        self.temp.cleanup()

    def request(self, path='/api/v1/backups', body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=20)
        data = json.dumps(body).encode() if body is not None else None
        try:
            conn.request('POST' if body is not None else 'GET', path, data,
                         {'Content-Type': 'application/json', **(headers or {})})
            response = conn.getresponse()
            return response.status, dict(response.headers), response.read()
        finally:
            conn.close()

    def test_paginated_catalog_and_invalid_query(self):
        for _ in range(3):
            self.assertEqual(200, self.request(body={'action':'create'})[0])
        status, _, body = self.request('/api/v1/backups?page=2&pageSize=1&sort=createdAt&direction=desc')
        catalog = json.loads(body)
        self.assertEqual(200, status)
        self.assertEqual(1, len(catalog['backups']))
        self.assertEqual({'page':2,'pageSize':1,'pages':3,'total':3}, catalog['pagination']['backups'])
        self.assertTrue(catalog['capabilities']['deleteArchive'])
        self.assertEqual(3, len(json.loads(self.request()[2])['backups']))
        for query in ('page=0','page=1&pageSize=101','sort=unknown','page=1&page=2','unknown=1'):
            self.assertEqual(400, self.request('/api/v1/backups?'+query)[0], query)

    def prepared_copy(self):
        service=Backups(self.registry)
        backup=service.execute({'action':'create'})['backup']
        result=service.execute({'action':'restore-copy','id':backup['id'],
                                'expectedSha256':backup['sha256'],'confirmed':True})
        return service, backup, Path(result['path'])

    def test_archive_deletion_preserves_copy_and_exact_retry(self):
        service, backup, copy=self.prepared_copy()
        body={'action':'delete-archive','id':backup['id'],'expected':backup['sha256'],
              'confirmed':True,'requestId':uuid.uuid4().hex}
        status, _, value=self.request(body=body)
        self.assertEqual(200,status,value)
        self.assertTrue(copy.is_dir())
        self.assertEqual([],service.catalog()['backups'])
        self.assertEqual(1,len(service.catalog()['restoreCopies']))
        self.assertEqual(json.loads(value),json.loads(self.request(body=body)[2]))
        self.assertEqual(409,self.request(body={**body,'expected':'changed'})[0])

    def test_copy_deletion_and_restoration_keep_receipts_separate(self):
        service, backup, copy=self.prepared_copy()
        body={'action':'delete-copy','id':backup['id'],'expected':inspect_home(copy)['revision'],
              'confirmed':True,'requestId':uuid.uuid4().hex}
        self.assertEqual(200,self.request(body=body)[0])
        self.assertFalse(copy.exists())
        self.assertTrue((self.registry.home/'registry.sqlite3').is_file())
        self.assertEqual([],service.catalog()['restoreCopies'])
        self.assertEqual(1,len(service.catalog()['backups']))
        restored=service.execute({'action':'restore-copy','id':backup['id'],
                                 'expectedSha256':backup['sha256'],'confirmed':True})
        new_copy=Path(restored['path'])
        self.assertNotEqual(copy,new_copy)
        self.assertEqual(200,self.request(body=body)[0])
        self.assertTrue(new_copy.is_dir(), 'Retrying an old deletion must not delete a later restoration')
        next_body={**body,'requestId':uuid.uuid4().hex,'expected':inspect_home(new_copy)['revision']}
        self.assertEqual(200,self.request(body=next_body)[0])
        self.assertFalse(new_copy.exists())

    def test_copy_deletion_refuses_stale_preview_live_lease_and_unowned_paths(self):
        service, backup, copy=self.prepared_copy()
        body={'action':'delete-copy','id':backup['id'],'expected':inspect_home(copy)['revision'],
              'confirmed':True,'requestId':uuid.uuid4().hex}
        self.assertEqual(409,self.request(body={**body,'expected':'stale'})[0])
        with home_lease(copy):
            with self.assertRaises(TimeoutError):service.execute(body)
        self.assertTrue(copy.is_dir())
        with patch.object(self.registry,'list',return_value={'projects':[{'roots':[str(copy.parent)]}]}):
            with self.assertRaisesRegex(ValueError,'code workspace'):service.execute(body)
        row=service._read(backup['id']);row['restore']['path']=str(self.registry.home);service._save(row)
        self.assertEqual(409,self.request(body=body)[0])
        self.assertTrue((self.registry.home/'registry.sqlite3').is_file())
        self.assertTrue(copy.is_dir())

    def test_background_delete_retains_request_identity(self):
        service, backup, copy=self.prepared_copy()
        body={'action':'delete-copy','id':backup['id'],'expected':inspect_home(copy)['revision'],
              'confirmed':True,'requestId':uuid.uuid4().hex,'background':True}
        status,_,content=self.request(body=body)
        self.assertEqual(202,status,content)
        job=json.loads(content)['job']
        import time
        for _ in range(100):
            current=json.loads(self.request('/api/v1/backups?job='+job['id'])[2])['job']
            if current['status'] not in ('queued','running'):break
            time.sleep(.02)
        self.assertEqual('succeeded',current['status'],current)
        self.assertEqual(body['requestId'],current['requestId'])
        self.assertEqual(current['id'],json.loads(self.request(body=body)[2])['job']['id'])
        self.assertFalse(copy.exists())

    def test_pending_deletions_recover_after_file_removal(self):
        for action in ('delete-copy', 'delete-archive'):
            service, backup, copy = self.prepared_copy()
            expected = inspect_home(copy)['revision'] if action == 'delete-copy' else backup['sha256']
            body = dict(action=action, id=backup['id'], expected=expected,
                        confirmed=True, requestId=uuid.uuid4().hex)
            save = service._save
            def fail_final(row):
                if row.get('archiveDeleted') or row.get('copyDeleted'):
                    raise OSError('simulated interruption after removal')
                save(row)
            with patch.object(service, '_save', side_effect=fail_final):
                with self.assertRaises(OSError):
                    service.execute(body)
            self.assertTrue(service.execute(body)['deleted'])
            self.assertEqual(200, self.request(body=body)[0])
            self.assertEqual(409, self.request(body={**body, 'requestId':uuid.uuid4().hex})[0])

    def test_malformed_receipts_fail_without_removing_data(self):
        service, backup, copy = self.prepared_copy()
        body = dict(action='delete-archive', id=backup['id'], expected=backup['sha256'],
                    confirmed=True, requestId=uuid.uuid4().hex)
        row = service._read(backup['id'])
        row['archiveDeletion'] = {'invalid': 'not a receipt'}
        service._save(row)
        self.assertEqual(409, self.request(body=body)[0])
        self.assertTrue(service._path(backup['id'], '.zip').is_file())
        self.assertTrue(copy.is_dir())

    def test_empty_catalog_create_download_upload_preview_restore_and_retry(self):
        self.assertEqual(200, self.request()[0])
        status, _, data = self.request(body={'action': 'create'})
        self.assertEqual(200, status, data)
        original = json.loads(data)['backup']
        status, headers, content = self.request('/api/v1/backups/download?id=' + original['id'])
        self.assertEqual(200, status)
        self.assertEqual('application/zip', headers['Content-Type'])
        self.assertEqual(len(content), int(headers['Content-Length']))
        self.assertIn('attachment', headers['Content-Disposition'])
        status, _, data = self.request(body={'action': 'upload-start', 'name': 'copy.zip', 'size': len(content)})
        self.assertEqual(200, status, data)
        upload = json.loads(data)['id']
        for offset in range(0, len(content), CHUNK_BYTES):
            chunk = content[offset:offset + CHUNK_BYTES]
            status, _, data = self.request(body={'action': 'upload-chunk', 'id': upload,
                'offset': offset, 'data': base64.b64encode(chunk).decode()})
            self.assertEqual(200, status, data)
            self.assertEqual(offset + len(chunk), json.loads(data)['offset'])
        status, _, data = self.request(body={'action': 'upload-complete', 'id': upload})
        self.assertEqual(200, status, data)
        checked = json.loads(data)
        self.assertEqual([], checked['preview']['projects'])
        request = {'action': 'restore-copy', 'id': upload, 'expectedSha256': checked['sha256'], 'confirmed': True}
        status, _, data = self.request(body=request)
        self.assertEqual(200, status, data)
        result = json.loads(data)
        self.assertFalse(result['active'])
        self.assertTrue((Path(result['path']) / 'registry.sqlite3').is_file())
        self.assertEqual(result, json.loads(self.request(body=request)[2]))
        catalog = json.loads(self.request()[2])
        self.assertEqual(2, len(catalog['backups']))
        self.assertEqual(result['path'], catalog['restoreCopies'][0]['path'])
        self.assertEqual(self.registry.home, self.server.registry.home)

    def test_origin_upload_limits_order_invalid_archive_and_abort(self):
        self.assertEqual(403, self.request(body={'action': 'create'}, headers={'Origin': 'https://foreign.example'})[0])
        self.assertEqual(413, self.request(body={'padding': 'a' * REQUEST_LIMIT})[0])
        row = json.loads(self.request(body={'action': 'upload-start', 'name': 'bad.zip', 'size': 4})[2])
        self.assertEqual(409, self.request(body={'action': 'upload-chunk', 'id': row['id'],
            'offset': 1, 'data': 'YmFkIQ=='})[0])
        self.assertEqual(200, self.request(body={'action': 'upload-chunk', 'id': row['id'],
            'offset': 0, 'data': 'YmFkIQ=='})[0])
        self.assertEqual(409, self.request(body={'action': 'upload-complete', 'id': row['id']})[0])
        self.assertEqual(200, self.request(body={'action': 'upload-abort', 'id': row['id']})[0])
        self.assertEqual(400, self.request('/api/v1/backups/download?id=../registry.sqlite3')[0])
        self.assertEqual([], json.loads(self.request()[2])['backups'])


class BackupASGITest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.registry = private_registry(self.base)
        # Incompressible opaque data exercises more than one response chunk.
        (self.registry.home / 'opaque.bin').write_bytes(os.urandom(700 * 1024))
        self.app = PortalASGI(self.registry, 18769, threads=2)

    async def asyncTearDown(self):
        self.app.service.stopping.set()
        await asyncio.to_thread(self.app.executor.shutdown, wait=True, cancel_futures=True)
        await asyncio.to_thread(self.app.service.server_close)
        self.temp.cleanup()

    async def request(self, path, body=None, headers=None):
        route, _, query = path.partition('?')
        data = json.dumps(body).encode() if body is not None else b''
        sent = []
        async def receive():
            return {'type': 'http.request', 'body': data, 'more_body': False}
        async def send(event):
            sent.append(event)
        scope = {'type': 'http', 'method': 'POST' if body is not None else 'GET', 'path': route,
            'raw_path': route.encode(), 'query_string': query.encode(), 'http_version': '1.1',
            'headers': [(b'host', b'127.0.0.1:18769'), (b'content-type', b'application/json'), *(headers or [])]}
        await self.app(scope, receive, send)
        return sent[0]['status'], dict(sent[0]['headers']), sent[1:]

    async def test_shared_streaming_descriptor_and_body_limit(self):
        status, _, events = await self.request('/api/v1/backups', {'action': 'create'})
        self.assertEqual(200, status, events)
        meta = json.loads(events[0]['body'])['backup']
        status, headers, events = await self.request('/api/v1/backups/download?id=' + meta['id'])
        self.assertEqual(200, status)
        self.assertGreater(len(events), 2)
        self.assertTrue(all(len(e['body']) <= 256 * 1024 for e in events))
        self.assertFalse(events[-1].get('more_body', False))
        content = b''.join(e['body'] for e in events)
        self.assertEqual(len(content), int(headers[b'content-length']))
        self.assertEqual(meta['sha256'], __import__('hashlib').sha256(content).hexdigest())
        status, _, _ = await self.request('/api/v1/backups', {'padding': 'a' * REQUEST_LIMIT})
        self.assertEqual(413, status)
        status, _, _ = await self.request('/api/v1/backups', {'action': 'create'}, [(b'origin', b'https://foreign.example')])
        self.assertEqual(403, status)
