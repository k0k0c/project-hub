"""Real supervisor/HTTP storage workflows on disposable data, without desktop UI."""
import base64
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid


PAYLOAD = os.environ.get('HUB_STORAGE_VERIFY_PAYLOAD')
PROGRAM = Path(PAYLOAD).resolve() / 'app' if PAYLOAD else Path(__file__).resolve().parents[2]
PYTHON = PROGRAM.parent / 'runtime/python.exe' if PAYLOAD else Path(sys.executable)
sys.path.insert(0, str(PROGRAM / 'scripts'))
from backup_api import Backups
from hub_import import inspect_home
from project_registry import ProjectRegistry
from storage_merge import revision


class StorageRuntimeTests(unittest.TestCase):
    def request(self, route, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            connection.request('GET' if body is None else 'POST', route,
                               None if body is None else json.dumps(body),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = json.loads(response.read())
            self.assertIn(response.status, (200, 202), (route, response.status, data))
            return data
        finally:
            connection.close()

    def ready(self, home):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            self.assertIsNone(self.process.poll(), self.log.read_text(encoding='utf-8', errors='replace'))
            try:
                health = self.request('/api/health')
                if Path(health['dataHome']).resolve() == home.resolve():
                    self.assertTrue(health['supervisorAlive'])
                    self.assertEqual(Path(health['codeRoot']).resolve(), PROGRAM.resolve())
                    return health
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(.1)
        self.fail('Temporary supervised runtime did not become ready: ' + str(home))

    def job(self, response):
        row = response.get('job') or response.get('operation')
        self.assertIsInstance(row, dict, response)
        identifier = row['id']
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                row = self.request('/api/backups?job=' + identifier)['job']
                if row['status'] not in ('queued', 'running'):
                    self.assertEqual(row['status'], 'succeeded', row)
                    return row
            except (OSError, http.client.HTTPException):
                pass  # Publication drains and restarts this exact temporary server.
            self.assertIsNone(self.process.poll(), self.log.read_text(encoding='utf-8', errors='replace'))
            time.sleep(.1)
        self.fail('Temporary storage operation timed out: ' + json.dumps(row, ensure_ascii=False))

    def post_job(self, route, body, section='data'):
        body = dict(body, background=True, requestId=uuid.uuid4().hex, origin={'section': section})
        return self.job(self.request(route, body))

    def projects(self):
        return {item['id'] for item in self.request('/api/v1/projects')['projects']}

    def stop(self):
        if self.process.poll() is None:
            (self.root / 'lifecycle/shutdown.json').write_text('{}', encoding='utf-8')
            try:
                self.process.wait(timeout=35)
            except subprocess.TimeoutExpired:
                # Only the child identified by both temporary data and program
                # paths may be cleaned up; no installed/user runtime is touched.
                try:
                    health = self.request('/api/health')
                    home = Path(health['dataHome']).resolve()
                    if self.root.resolve() in home.parents and Path(health['codeRoot']).resolve() == PROGRAM.resolve():
                        import signal
                        os.kill(health['pid'], signal.SIGTERM)
                except (OSError, http.client.HTTPException):
                    pass
                self.process.terminate()
                self.process.wait(timeout=10)
                self.fail('Temporary supervisor did not drain on shutdown')
        self.output.close()

    def test_folder_zip_publication_and_folder_change_use_one_active_home(self):
        with tempfile.TemporaryDirectory(prefix='hub-storage-runtime-') as temporary:
            self.root = Path(temporary)
            active = self.root / 'data'
            backup_home = self.root / 'data-backups'
            config_path = self.root / 'installation.json'
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                self.port = listener.getsockname()[1]
            config = dict(schemaVersion=1, dataHome=str(active), backupHome=str(backup_home),
                          port=self.port, language='ru')
            config_path.write_text(json.dumps(config), encoding='utf-8')
            environment = {key: value for key, value in os.environ.items() if not key.startswith('PROJECT_HUB_')}
            environment.update(PROJECT_HUB_RUNTIME_MODE='development',
                               PROJECT_HUB_INSTANCE_HOME=str(self.root / 'instances'),
                               LOCALAPPDATA=str(self.root / 'local-app-data'),
                               CODEX_HOME=str(self.root / 'codex'), PYTHONDONTWRITEBYTECODE='1')
            with patch.dict(os.environ, environment, clear=True):
                old = ProjectRegistry(self.root / 'historical', standalone=True)
                try:
                    imported = old.create('Archived project', [], request_id=uuid.uuid4().hex)
                    task = dict(title='Retained task', status='planned', stages=[],
                                createdBy={'project': imported['id'], 'session': 'retained-chat'})
                    old.store(imported['id']).record(dict(kind='task.created', taskId='retained-task', title=task['title'], patch=task))
                    archive = Backups(old).execute({'action': 'create'})['backup']
                    zip_path = Backups(old)._path(archive['id'], '.zip')
                finally:
                    old.close_connection_pool()
                original_revision = revision(old.home)
                original_zip = zip_path.read_bytes()
                supervisor_code = ('import sys; sys.path.insert(0, sys.argv[2] + "/scripts"); '
                    'import hub_desktop; hub_desktop.start_tray=lambda *args, **kwargs: None; '
                    'from hub_lifecycle import supervise; '
                    'raise SystemExit(supervise(sys.argv[1], application_home=sys.argv[2]))')
                self.log = self.root / 'supervisor.log'
                self.output = self.log.open('w', encoding='utf-8')
                active.mkdir(exist_ok=True)
                self.process = subprocess.Popen([str(PYTHON), '-B', '-c', supervisor_code, str(config_path), str(PROGRAM)],
                    cwd=active, env=environment, stdin=subprocess.DEVNULL, stdout=self.output, stderr=self.output,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
                try:
                    initial_pid = self.ready(active)['pid']
                    current = self.post_job('/api/v1/projects', {'action': 'create', 'name': 'Current project', 'roots': []},
                                            section='projects')['result']['project']
                    inspected = self.post_job('/api/v1/storage', {'action': 'inspect-folder', 'path': str(old.home)})['result']
                    # Inspection now prepares the source automatically; no second
                    # user action or duplicated folder snapshot is needed.
                    copied = {'copyId': inspected['copyId']}
                    check_copy = self.post_job('/api/v1/storage', {'action': 'inspect-copy', 'id': copied['copyId']})['result']
                    applied = self.post_job('/api/v1/storage', {'action': 'apply-import', 'id': copied['copyId'],
                        'expected': check_copy['preview']['revision'], 'mode': 'add', 'includeGlobals': False,
                        'expectedActive': check_copy['comparison']['activeRevision'],
                        'confirmed': True})
                    self.assertNotEqual(self.ready(active)['pid'], initial_pid)
                    self.assertEqual(self.projects(), {current['id'], imported['id']})
                    self.assertEqual(Path(applied['result']['activeHome']), active)
                    # The supervisor owns the execution lease at completion;
                    # cleanup must borrow it, not attempt a non-reentrant lock.
                    deadline = time.monotonic() + 5
                    receipt = applied
                    while time.monotonic() < deadline:
                        receipt = self.request('/api/backups?job=' + applied['id'])['job']
                        if receipt.get('cleanup', {}).get('state') == 'complete':
                            break
                        time.sleep(.1)
                    self.assertEqual(receipt.get('cleanup', {}).get('state'), 'complete')
                    self.assertEqual(revision(old.home), original_revision)

                    upload = self.request('/api/v1/backups', {'action': 'upload-start', 'name': 'archive.zip',
                        'size': len(original_zip), 'requestId': uuid.uuid4().hex})
                    from backup_api import CHUNK_BYTES
                    for offset in range(0, len(original_zip), CHUNK_BYTES):
                        part = original_zip[offset:offset + CHUNK_BYTES]
                        self.request('/api/v1/backups', {'action': 'upload-chunk', 'id': upload['id'], 'offset': offset,
                            'data': base64.b64encode(part).decode('ascii')})
                    verified = self.post_job('/api/v1/backups', {'action': 'upload-complete', 'id': upload['id']},
                                             section='backups')['result']
                    restored = self.post_job('/api/v1/backups', {'action': 'restore-copy', 'id': upload['id'],
                        'expectedSha256': verified['sha256'], 'confirmed': True}, section='backups')['result']
                    zip_copy = self.post_job('/api/v1/storage', {'action': 'inspect-copy', 'id': restored['copyId']})['result']
                    self.post_job('/api/v1/storage', {'action': 'apply-import', 'id': restored['copyId'],
                        'expected': zip_copy['preview']['revision'], 'mode': 'replace-all', 'includeGlobals': False,
                        'expectedActive':zip_copy['comparison']['activeRevision'],
                        'confirmed': True})
                    self.ready(active)
                    self.assertEqual(self.projects(), {imported['id']})
                    state = self.request('/api/state?project=' + imported['id'])
                    self.assertEqual(state['tasks'][0]['id'], 'retained-task')

                    new_data, new_backups = self.root / 'new-data', self.root / 'new-backups'
                    folder_body = dict(action='change-folders', dataHome=str(new_data), backupHome=str(new_backups), confirmed=False)
                    folder_preview = self.request('/api/v1/storage', folder_body)['preview']
                    self.assertEqual(Path(folder_preview['oldDataHome']), active)
                    self.post_job('/api/v1/storage', dict(folder_body, confirmed=True), section='settings')
                    self.ready(new_data)
                    self.assertEqual(json.loads(config_path.read_text())['dataHome'], str(new_data))
                    self.assertTrue(active.is_dir())
                    self.assertTrue(list(backup_home.glob('*.zip')))
                    backup = self.post_job('/api/v1/backups', {'action': 'create'}, section='backups')['result']['backup']
                    self.assertTrue((new_backups / (backup['id'] + '.zip')).is_file())
                    self.assertEqual(self.projects(), {imported['id']})
                    self.assertFalse(self.request('/api/backups/status')['writesPaused'])
                    self.assertEqual(zip_path.read_bytes(), original_zip)
                finally:
                    self.stop()


if __name__ == '__main__':
    unittest.main()
