"""Background children retain their pipes without allocating Windows consoles."""
from contextlib import closing
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
PLUGIN = SCRIPTS.parent / 'tools/project-portal/plugins/project-hub/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN))
import git_changesets
import git_integration
import hub_core
import knowledge_scan
from codex_session_catalog import SessionCatalog
from event_broker import EventBroker
from knowledge_store import KnowledgeStore
import native_mcp_setup
from project_portal import SessionTitles
from project_registry import CodexProjects, ProjectRegistry
from backup_api import Backups
from storage_operations import status as storage_status


def _flags():
    return getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0


def _registry(base, root):
    catalog = base / 'projects.json'
    catalog.write_text(json.dumps({'local-projects': {
        'fixture': dict(id='fixture', name='Fixture', rootPaths=[str(root)])},
        'thread-project-assignments': {}}), encoding='utf-8')
    registry = ProjectRegistry(base / 'data', CodexProjects(catalog))
    project = registry.list()['projects'][0]['id']
    return registry, project


class _ImmediateExecutor:
    def submit(self, callback, *args):
        callback(*args)


CONSOLE_CHILD = r'''
import ctypes, json, os, pathlib, sys
spec = json.loads(sys.argv[1])
payload = sys.stdin.buffer.read() if spec.get('readInput') else b''
console_window = ctypes.windll.kernel32.GetConsoleWindow
console_window.restype = ctypes.c_void_p
pathlib.Path(spec['record']).write_text(json.dumps(dict(
    console=int(console_window() or 0),
    executable=sys.executable, input=payload.hex())), encoding='utf-8')
if spec.get('registration'):
    target = pathlib.Path(os.environ['CODEX_HOME']) / 'config.toml'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('[mcp_servers.fixture]\nurl = "http://127.0.0.1:1/mcp"\n'
                      'bearer_token_env_var = "FIXTURE_TOKEN"\n', encoding='utf-8')
os.write(1, spec.get('stdout', '').encode('utf-8') + (payload if spec.get('echo') else b''))
os.write(2, b'fixture stderr\n')
sys.exit(spec.get('exit', 0))
'''


def _windowed_probe(base, console_python):
    """Exercise runtime launchers from pythonw, using a console-subsystem child."""
    import ctypes
    check = unittest.TestCase()
    console_window = ctypes.windll.kernel32.GetConsoleWindow
    console_window.restype = ctypes.c_void_p
    check.assertIsNone(console_window())
    root = base / 'source'
    root.mkdir()
    (root / '.git').mkdir()
    (root / 'sample.py').write_text('class Example: pass\n', encoding='utf-8')
    child = base / 'console_child.py'
    child.write_text(CONSOLE_CHILD, encoding='utf-8')
    launches = []
    original_run = subprocess.run

    def exercise(name, callback, **spec):
        record = base / (name + '.json')
        specification = dict(spec, record=str(record))

        def launch(command, **options):
            completed = original_run([str(console_python), '-B', str(child),
                                      json.dumps(specification)], **options)
            observed = json.loads(record.read_text(encoding='utf-8'))
            check.assertEqual(observed['console'], 0, name)
            check.assertEqual(Path(observed['executable']).resolve(), console_python.resolve())
            sent = options.get('input')
            if isinstance(sent, str):
                sent = sent.encode(options.get('encoding') or 'utf-8')
            check.assertEqual(observed['input'], (sent or b'').hex(), name)
            expected = spec.get('stdout', '').encode('utf-8') + ((sent or b'') if spec.get('echo') else b'')
            check.assertEqual(completed.stdout, expected.decode('utf-8') if options.get('text') else expected)
            check.assertEqual(completed.stderr, 'fixture stderr\n' if options.get('text') else b'fixture stderr\n')
            launches.append(dict(name=name, console=observed['console']))
            return completed

        with patch.object(subprocess, 'run', side_effect=launch):
            return callback()

    check.assertEqual(exercise('git-text', lambda: git_integration._run(root, 'status'),
                               stdout=' M unicode-имя.txt\n'), ' M unicode-имя.txt')
    check.assertEqual(exercise('git-history-input', lambda: git_integration._history_batch(
        root, ['rev-list', '--stdin'], ['a' * 40]), readInput=True, echo=True), 'a' * 40 + '\n')
    binary = b'\x00\xffinput\n'
    check.assertEqual(exercise('git-content-input', lambda: git_changesets.git(
        root, 'hash-object', '--stdin', input_bytes=binary), readInput=True, echo=True), binary)
    with check.assertRaisesRegex(git_integration.GitIntegrationError, 'fixture stderr'):
        exercise('git-error', lambda: git_integration._run(root, 'status'), exit=7)
    check.assertEqual(exercise('git-common', lambda: hub_core.git_common(root),
                               stdout=str(root) + '\n'), hub_core.canonical(root))
    check.assertEqual(exercise('workspace-root', lambda: hub_core.workspace_root(
        root, dict(root=str(base / 'other'))), stdout=str(root) + '\n'), hub_core.canonical(root))

    (root / 'Example.java').write_text('class Example {}', encoding='utf-8')
    with patch.object(knowledge_scan.shutil, 'which', return_value=str(console_python)):
        parsed = exercise('java-parser', lambda: knowledge_scan.scan(root), readInput=True,
                          stdout=json.dumps(dict(types=[], diagnostics=[])))
    check.assertIn('types', parsed['capabilities']['java'])
    (root / 'Example.java').unlink()

    registry, project = _registry(base, root)
    registry._knowledge_executor = _ImmediateExecutor()
    knowledge = KnowledgeStore(registry, project)
    job = exercise('scan-git-head', lambda: knowledge.start_scan(), stdout='a' * 40 + '\n')
    check.assertEqual(knowledge.job(job['id'])['state'], 'ready')

    registration = native_mcp_setup.Registration('codex', base / 'host/config.toml', None,
        'fixture', dict(url='http://127.0.0.1:1/mcp', bearer_token_env_var='FIXTURE_TOKEN'),
        str(console_python))
    result = exercise('native-registration', lambda: native_mcp_setup.apply_registration(registration),
                      registration=True)
    check.assertTrue(result['registered'])
    return launches


@unittest.skipUnless(shutil.which('git'), 'Git is required')
class BackgroundProcessTests(unittest.TestCase):
    def test_upload_status_is_byte_receipt_with_durable_terminal_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            data_home = base / 'data'
            backup_home = base / 'backups'
            data_home.mkdir()
            registry = SimpleNamespace(home=data_home)
            with patch.dict(os.environ, {'PROJECT_HUB_CONFIGURED_HOME': str(data_home),
                                         'PROJECT_HUB_BACKUP_HOME': str(backup_home)}), \
                 patch('hub_lifecycle.catalog', return_value={'operations': []}), \
                 patch('backup_session.active', return_value=None):
                backups = Backups(registry)
                identifier = 'a' * 32
                backups._save({'id': identifier, 'state': 'preview', 'name': 'received.zip',
                               'size': 8, 'offset': 8, 'createdAt': '2026-10-12T10:00:00+00:00',
                               'startedAt': '2026-10-12T10:00:01+00:00',
                               'finishedAt': '2026-10-12T10:00:09+00:00',
                               'uploadRequestId': 'b' * 32,
                               'uploadOrigin': {'section': 'backups'}})
                row = next(item for item in storage_status(registry)['operations']
                           if item['id'] == identifier)
                self.assertEqual('succeeded', row['status'])
                self.assertEqual('complete', row['phase'])
                self.assertEqual('upload:' + identifier, row['workflowId'])
                self.assertEqual({'id': identifier}, row['payload'])
                self.assertEqual('bytes', row['progress']['unit'])
                self.assertEqual(8, row['elapsed'])

    def test_upload_terminal_states_and_legacy_elapsed_are_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            data_home = base / 'data'
            backup_home = base / 'backups'
            data_home.mkdir()
            registry = SimpleNamespace(home=data_home)
            with patch.dict(os.environ, {'PROJECT_HUB_CONFIGURED_HOME': str(data_home),
                                         'PROJECT_HUB_BACKUP_HOME': str(backup_home)}), \
                 patch('hub_lifecycle.catalog', return_value={'operations': []}), \
                 patch('backup_session.active', return_value=None):
                backups = Backups(registry)
                started = backups.execute({'action': 'upload-start', 'name': 'chunked.zip',
                                           'size': 3, 'requestId': '5' * 32})
                replay = backups.execute({'action': 'upload-start', 'name': 'chunked.zip',
                                          'size': 3, 'requestId': '5' * 32})
                self.assertEqual(started['startedAt'], replay['startedAt'])
                backups.execute({'action': 'upload-chunk', 'id': started['id'], 'offset': 0,
                                 'data': base64.b64encode(b'abc').decode('ascii')})
                stored_upload = backups._read(started['id'])
                self.assertIn('uploadReceivedAt', stored_upload)
                common = {'name': 'received.zip', 'size': 8, 'offset': 8,
                          'createdAt': '2026-10-12T10:00:00+00:00',
                          'startedAt': '2026-10-12T10:00:01+00:00',
                          'uploadReceivedAt': '2026-10-12T10:00:04+00:00',
                          'uploadRequestId': 'b' * 32, 'uploadOrigin': {'section': 'backups'}}
                rejected = dict(common, id='c' * 32, state='rejected',
                                finishedAt='2026-10-12T10:00:09+00:00')
                aborted = dict(common, id='d' * 32, state='cancelled', offset=2,
                               uploadRequestId='e' * 32, finishedAt='2026-10-12T10:00:05+00:00')
                timed_out = dict(common, id='f' * 32, state='uploading', offset=2,
                                 uploadRequestId='1' * 32, uploadReceivedAt=None,
                                 uploadUpdated=time.time() - 901)
                legacy = dict(common, id='2' * 32, state='preview',
                              uploadRequestId='3' * 32, uploadReceivedAt=None,
                              uploadUpdated=1800000000)
                for row in (rejected, aborted, timed_out, legacy):
                    backups._save(row)
                rows = {row['id']: row for row in storage_status(registry)['operations']}
                self.assertEqual('failed', rows[rejected['id']]['status'])
                self.assertEqual('failed', rows[aborted['id']]['status'])
                self.assertEqual('interrupted', rows[timed_out['id']]['status'])
                self.assertEqual('upload-interrupted', backups._read(timed_out['id'])['state'])
                first = rows[legacy['id']]
                second = {row['id']: row for row in storage_status(registry)['operations']}[legacy['id']]
                self.assertEqual(first['elapsed'], second['elapsed'])

    def test_active_backup_job_elapsed_remains_live_without_finished_at(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            data_home = base / 'data'
            backup_home = base / 'backups'
            data_home.mkdir()
            registry = SimpleNamespace(home=data_home)
            with patch.dict(os.environ, {'PROJECT_HUB_CONFIGURED_HOME': str(data_home),
                                         'PROJECT_HUB_BACKUP_HOME': str(backup_home)}):
                backups = Backups(registry)
                identifier = '4' * 32
                now = time.time()
                backups._save_job({'id': identifier, 'status': 'running',
                                   'createdAt': '2026-10-12T10:00:00+00:00',
                                   'createdEpoch': now - 10})
                with patch('project_portal.Store.lock_probe') as probe:
                    probe.return_value.locked.side_effect = TimeoutError
                    first = backups._read_job(identifier)['elapsed']
                    time.sleep(.01)
                    second = backups._read_job(identifier)['elapsed']
                self.assertGreaterEqual(first, 9)
                self.assertGreater(second, first)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hub-background-processes-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'source'
        self.root.mkdir()
        self.git('init', '-q', '--object-format=sha1')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.hooksPath', str(self.base / 'empty-hooks'))
        (self.root / 'sample.py').write_text('class Example: pass\n', encoding='utf-8')
        self.git('add', 'sample.py')
        self.git('commit', '-qm', 'Fixture')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True,
                              check=True, timeout=10, creationflags=_flags()).stdout

    def test_expired_diagnostics_repeat_worktree_discovery_without_console_windows(self):
        linked = self.base / 'linked-worktree'
        self.git('worktree', 'add', '-q', '--detach', str(linked))
        registry, project = _registry(self.base, self.root)
        hub_core.Hub(registry.home / 'coordination').setup()
        database = self.base / 'threads.sqlite'
        with closing(sqlite3.connect(database)) as connection:
            connection.execute('CREATE TABLE threads(id TEXT,name TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER,source TEXT)')
            connection.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',
                               ('outside-root', 'Fixture chat', str(linked), 1, 0, 'vscode'))
            connection.commit()
        titles = self.base / 'session_index.jsonl'
        titles.write_text('', encoding='utf-8')
        catalog = SessionCatalog(database, ttl=0)
        store = registry.store(project)
        broker = EventBroker(SimpleNamespace(stopping=threading.Event()))
        self.addCleanup(broker.close)
        run = subprocess.run
        with patch('codex_session_catalog.CATALOG', catalog), \
                patch('project_portal.SESSION_TITLES', SessionTitles(titles)):
            for repeat in range(2):
                with patch.object(subprocess, 'run', wraps=run) as launches:
                    result = broker._shared_diagnostics(store)
                self.assertTrue(result['available'], result)
                self.assertEqual([session['id'] for session in result['sessions']], ['outside-root'])
                self.assertGreaterEqual(len(launches.call_args_list), 2)
                for launch in launches.call_args_list:
                    self.assertEqual(launch.args[0][0], 'git')
                    self.assertEqual(launch.kwargs['creationflags'], _flags())
                with registry.connect() as connection:
                    connection.execute('UPDATE observation_cache SET observed_wall=0')

    def test_git_wrappers_preserve_binary_input_history_and_error_details(self):
        payload = b'\x00\xffunicode-\xd0\xb8\n'
        expected = hashlib.sha1(b'blob ' + str(len(payload)).encode('ascii') + b'\0' + payload).hexdigest()
        actual = git_changesets.git(self.root, 'hash-object', '--stdin', input_bytes=payload)
        self.assertEqual(actual, (expected + '\n').encode('ascii'))
        head = self.git('rev-parse', 'HEAD').decode('ascii').strip()
        self.assertEqual(git_integration._history_batch(self.root, ['rev-list', '--stdin'], [head]), head + '\n')
        failure = subprocess.run(['git', '-C', str(self.root), 'rev-parse', '--verify', 'missing-fixture-ref'],
                                 capture_output=True, timeout=10, creationflags=_flags())
        with self.assertRaises(git_integration.GitIntegrationError) as caught:
            git_integration._run(self.root, 'rev-parse', '--verify', 'missing-fixture-ref')
        self.assertEqual(str(caught.exception), failure.stderr.decode('utf-8', errors='replace').strip())

    def test_knowledge_scan_retains_repository_revision_without_console_windows(self):
        registry, project = _registry(self.base, self.root)
        registry._knowledge_executor = _ImmediateExecutor()
        knowledge = KnowledgeStore(registry, project)
        run = subprocess.run
        with patch.object(subprocess, 'run', wraps=run) as launches:
            job = knowledge.start_scan()
        result = knowledge.job(job['id'])
        self.assertEqual(result['state'], 'ready', result)
        self.assertGreater(len(launches.call_args_list), 0)
        for launch in launches.call_args_list:
            self.assertEqual(launch.kwargs['creationflags'], _flags())
        with registry.connect() as connection:
            revision = json.loads(connection.execute('SELECT code_revision FROM knowledge_changes').fetchone()[0])
        self.assertEqual(revision['heads'], [self.git('rev-parse', 'HEAD').decode('ascii').strip()])


class NativeWindowedProcessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Native Windows console check')
    def test_runtime_launches_from_pythonw_keep_pipes_without_a_console(self):
        console_python = Path(sys.executable).with_name('python.exe').resolve()
        windowed_python = console_python.with_name('pythonw.exe')
        if not console_python.is_file() or not windowed_python.is_file():
            self.skipTest('Matching python.exe and pythonw.exe are required')
        with tempfile.TemporaryDirectory(prefix='hub-pythonw-probe-') as temporary:
            base = Path(temporary).resolve()
            report = base / 'report.json'
            completed = subprocess.run([str(windowed_python), '-B', '-S', str(Path(__file__).resolve()),
                '--windowed-probe', str(base), str(console_python), str(report)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=45, creationflags=_flags())
            self.assertEqual(completed.returncode, 0, report.read_text(encoding='utf-8') if report.exists() else 'No probe report')
            result = json.loads(report.read_text(encoding='utf-8'))
            self.assertNotIn('error', result, result)
            self.assertEqual({launch['name'] for launch in result['launches']}, {
                'git-text', 'git-history-input', 'git-content-input', 'git-error', 'git-common',
                'workspace-root', 'java-parser', 'scan-git-head', 'native-registration'})
            self.assertTrue(all(launch['console'] == 0 for launch in result['launches']))


if __name__ == '__main__':
    if sys.argv[1:2] == ['--windowed-probe']:
        probe_report = Path(sys.argv[4])
        try:
            probe_result = dict(launches=_windowed_probe(Path(sys.argv[2]), Path(sys.argv[3])))
        except Exception:
            probe_result = dict(error=traceback.format_exc())
        probe_report.write_text(json.dumps(probe_result), encoding='utf-8')
        raise SystemExit(1 if 'error' in probe_result else 0)
    unittest.main()
