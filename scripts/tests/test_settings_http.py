"""Project settings transport contracts with disposable registry and data homes."""
import http.client
import json
import os
from pathlib import Path
from unittest.mock import patch

from test_manual_editing import ManualApiCase
from plugin_api import ServerHub, HubError
from project_settings import DEFAULT_SETTINGS


class SettingsHttpTest(ManualApiCase):
    def test_version_control_is_a_separate_project_runtime_read(self):
        before = self.settings()
        with patch('subprocess.run', side_effect=AssertionError('Plain workspace needs no Git')):
            status, result = self.request('/api/version-control')
            self.assertEqual(status, 200, result)
            self.assertEqual(result['status'], 'no_repository')
            self.assertIsNone(result['provider'])
            self.assertFalse(result['available'])
            self.assertEqual(result['workspaceRoot'], str(self.registry.base_store(self.pid).root))
            self.assertEqual(self.settings(), before)
            self.assertEqual(self.state()['settings'], before)
        other = self.registry.base_store(self.projects['b']).root
        (other / '.git').mkdir()
        with patch('version_control.shutil.which', return_value=None):
            self.assertEqual(self.request('/api/version-control', project=self.projects['b'])[1]['status'], 'client_unavailable')
            self.assertEqual(self.request('/api/version-control')[1]['status'], 'no_repository')

    def settings(self, project=None):
        status, result = self.request('/api/v1/settings', project=project)
        self.assertEqual(status, 200, result)
        return result

    def update(self, changes=None, project=None, **fields):
        body = {'expected': self.settings(project)['revision'], **fields}
        if 'reset' not in fields:
            body['patch'] = changes
        status, result = self.request('/api/v1/settings', body, project)
        self.assertEqual(status, 200, result)
        return result

    def hub(self):
        hub = ServerHub(self.registry)
        for key, pid in self.projects.items():
            hub.ensure_session('settings-test-' + key, str(self.registry.base_store(pid).root))
        return hub

    def test_defaults_off_and_state_projection(self):
        result = self.settings()
        self.assertEqual(set(result), {'settings', 'revision', 'history', 'configured'})
        self.assertEqual(result['settings'], DEFAULT_SETTINGS)
        self.assertFalse(result['settings']['git']['autoCommit'])
        self.assertFalse(result['configured'])
        self.assertIsInstance(result['revision'], str)
        self.assertTrue(result['revision'])
        self.assertEqual(result['history'], [])
        status, state = self.request('/api/v1/state')
        self.assertEqual(status, 200, state)
        self.assertEqual(state['settings'], result)
        self.assertFalse((self.registry.base_store(self.pid).data / 'project-settings.json').exists())

    def test_http_patch_isolation_and_noop(self):
        other = self.settings(self.projects['b'])
        changed = self.update({'git': {'autoCommit': True}, 'tasks': {'columns': ['title', 'status']}})
        self.assertTrue(changed['configured'])
        self.assertTrue(changed['settings']['git']['autoCommit'])
        self.assertEqual(changed['settings']['tasks']['columns'], ['title', 'status'])
        self.assertEqual(changed['history'][-1]['actor'], 'local-user')
        self.assertEqual(self.settings(), changed)
        self.assertEqual(self.state()['settings'], changed)
        self.assertEqual(self.settings(self.projects['b']), other)
        self.assertEqual(self.update({'git': {'autoCommit': True}}), changed)

    def test_http_stale_revision_and_section_reset(self):
        first = self.settings()
        current = self.update({'git': {'autoCommit': True}, 'viewer': {'wrapLines': False}})
        status, result = self.request('/api/v1/settings',
                                      {'expected': first['revision'], 'patch': {'git': {'autoCommit': True}}})
        self.assertEqual(status, 409, result)
        self.assertEqual(result['error'], 'settings_conflict')
        self.assertTrue(result['message'])
        self.assertEqual(self.settings(), current)
        status, result = self.request('/api/v1/settings', {'expected': first['revision'], 'reset': 'git'})
        self.assertEqual(status, 409, result)
        reset = self.update(reset='git')
        self.assertEqual(reset['settings']['git'], DEFAULT_SETTINGS['git'])
        self.assertFalse(reset['settings']['viewer']['wrapLines'])
        self.assertEqual(reset['history'][-1]['sections'], ['git'])
        self.assertNotEqual(reset['revision'], current['revision'])

    def test_http_accepts_optional_summary_and_children_columns(self):
        columns = ['title', 'summary', 'children', 'actions']
        changed = self.update({'tasks': {'columns': columns}})
        self.assertEqual(changed['settings']['tasks']['columns'], columns)
        self.assertEqual(self.settings(), changed)
        self.assertEqual(self.state()['settings'], changed)
        self.assertEqual(self.hub().context('settings-test-a')['projectSettings'], changed)

    def test_http_invalid_schema_is_atomic(self):
        before = self.update({'viewer': {'wrapLines': False}})
        path = self.registry.base_store(self.pid).data / 'project-settings.json'
        original = path.read_bytes()
        bodies = [[], {'patch': {}}, {'expected': before['revision']},
                  {'patch': {}, 'expected': 1}, {'patch': {}, 'global': True},
                  {'patch': {'git': {'autoCommit': 1}}},
                  {'patch': {'git': {'commitOn': 'always'}}},
                  {'patch': {'tasks': {'sort': 'estimate'}}},
                  {'patch': {'tasks': {'overviewSort': 'unknown'}}},
                  {'patch': {'tasks': {'columns': ['status']}}},
                  {'patch': {'tasks': {'columns': ['title', 'title']}}},
                  {'patch': {'viewer': {'showSourceDetails': 'yes'}}},
                  {'patch': {'unknown': {}}}, {'patch': {'git': {'unknown': True}}},
                  {'reset': 'all'}, {'reset': 'git', 'patch': {'viewer': {'wrapLines': True}}}]
        for body in bodies:
            if isinstance(body, dict) and body != {'patch': {}}:
                body = {'expected': before['revision'], **body}
            with self.subTest(body=body):
                status, error = self.request('/api/v1/settings', body)
                if not isinstance(body, dict) or 'global' in body:
                    self.assertEqual(status, 409, error)
                    self.assertIn('error', error)
                else:
                    self.assertEqual(status, 400, error)
                    self.assertEqual(error['error'], 'invalid_settings')
                    self.assertTrue(error['message'])
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(self.settings(), before)

    def test_http_requires_one_known_project(self):
        for query in ('', '?project=unknown', '?project=', '?project=' + self.pid + '&project=' + self.projects['b']):
            for method in ('GET', 'POST'):
                with self.subTest(query=query, method=method):
                    connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
                    try:
                        body = json.dumps({'patch': {}, 'expected': self.settings()['revision']})
                        connection.request(method, '/api/v1/settings' + query,
                                           body if method == 'POST' else None,
                                           {'Content-Type': 'application/json'})
                        response = connection.getresponse()
                        error = json.loads(response.read())
                        self.assertIn(response.status, (400, 409), error)
                        self.assertIn('error', error)
                    finally:
                        connection.close()

    def test_server_hub_context_settings_and_http_agree(self):
        hub = self.hub()
        session = 'settings-test-a'
        initial = hub.settings(session)
        self.assertEqual(initial, self.settings())
        self.assertFalse(initial['settings']['git']['autoCommit'])
        self.assertEqual(hub.context(session)['projectSettings'], initial)
        other = hub.settings('settings-test-b')
        changed = hub.settings(session, patch={'tasks': {'showCompleted': False}}, expected=initial['revision'])
        self.assertEqual(changed['history'][-1]['actor'], session)
        self.assertEqual(hub.context(session)['projectSettings'], changed)
        self.assertEqual(self.settings(), changed)
        self.assertEqual(self.state()['settings'], changed)
        self.assertEqual(hub.settings('settings-test-b'), other)
        with self.assertRaises(HubError) as error:
            hub.settings(session, patch={'tasks': {'showCompleted': False}}, expected=initial['revision'])
        self.assertEqual(error.exception.body['error'], 'settings_conflict')
        self.assertTrue(error.exception.body['message'])
        for invalid in ({'git': {'autoCommit': 1}}, {'viewer': {'unknown': True}}):
            with self.subTest(invalid=invalid), self.assertRaises(HubError) as error:
                hub.settings(session, patch=invalid, expected=changed['revision'])
            self.assertEqual(error.exception.body['error'], 'invalid_settings')
            status, body = self.request('/api/v1/settings', {'patch': invalid, 'expected': changed['revision']})
            self.assertEqual(status, 400, body)
            self.assertEqual(error.exception.body, body)
        self.assertEqual(hub.settings(session), changed)
        reset = hub.settings(session, reset='tasks', expected=changed['revision'])
        self.assertEqual(reset['settings']['tasks'], DEFAULT_SETTINGS['tasks'])
        self.assertEqual(self.settings(), reset)

    def test_corruption_returns_500_and_matching_hub_error_without_overwrite(self):
        hub = self.hub()
        before = self.update({'viewer': {'wrapLines': False}})
        path = self.registry.base_store(self.pid).data / 'project-settings.json'
        corrupt = b'{broken'
        path.write_bytes(corrupt)
        for body in (None, {'patch': {'git': {'autoCommit': True}}, 'expected': before['revision']},
                     {'reset': 'git', 'expected': before['revision']}):
            with self.subTest(body=body):
                status, error = self.request('/api/v1/settings', body)
                self.assertEqual(status, 500, error)
                self.assertEqual(error['error'], 'corrupt_settings')
                self.assertTrue(error['message'])
                with self.assertRaises(HubError) as converted:
                    hub.settings('settings-test-a', **(body or {}))
                self.assertEqual(converted.exception.body, error)
                self.assertEqual(path.read_bytes(), corrupt)
        with self.assertRaises(HubError) as error:
            hub.context('settings-test-a')
        self.assertEqual(error.exception.body['error'], 'corrupt_settings')

    def test_settings_only_change_emits_sse_revision_event(self):
        def read_revision(response):
            for _ in range(20):
                line = response.readline()
                self.assertTrue(line, 'SSE stream closed before revision event')
                if line.startswith(b'data: '):
                    return json.loads(line[6:])
            self.fail('No SSE revision event within 20 lines')

        before = self.settings()
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        response = None
        try:
            connection.request('GET', '/api/v1/events?project=' + self.pid)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn('text/event-stream', response.getheader('Content-Type'))
            initial = read_revision(response)
            changed = self.update({'viewer': {'wrapLines': False}})
            self.assertNotEqual(changed['revision'], before['revision'])
            notification = read_revision(response)
            # Settings alone must wake the stream. The full hint lets a client
            # distinguish this from the redundant initial subscription event.
            self.assertEqual(notification['revision'], initial['revision'])
            self.assertEqual(notification['coordinationRevision'], initial['coordinationRevision'])
            self.assertEqual(notification['titlesRevision'], initial['titlesRevision'])
            self.assertEqual(notification['relationsRevision'], initial['relationsRevision'])
            self.assertEqual(initial['settingsRevision'], before['revision'])
            self.assertEqual(notification['settingsRevision'], changed['revision'])
            self.assertEqual(self.settings(), changed)
        finally:
            self.server.stopping.set()
            if response is not None:
                response.close()
            connection.close()

    def test_authoritative_project_storage_without_global_writes(self):
        fake_home = Path(self.temp.name) / 'unused-global-home'
        fake_home.mkdir()
        sentinel = fake_home / 'sentinel.txt'
        sentinel.write_text('unchanged', encoding='utf-8')
        with patch.dict(os.environ, {'HOME': str(fake_home), 'USERPROFILE': str(fake_home),
                                    'CODEX_HOME': str(fake_home / 'codex'),
                                    'PROJECT_HUB_HOME': str(fake_home / 'hub')}):
            hub = self.hub()
            stores = [self.registry.base_store(pid) for pid in self.projects.values()]
            journals = {store.journal: store.journal.read_bytes() if store.journal.exists() else None
                        for store in stores}
            self.update({'viewer': {'wrapLines': False}})
            # Direct settings must bypass any task view or migrated-origin store.
            with patch.object(self.registry, 'store', side_effect=AssertionError('task view used for settings')):
                current = hub.settings('settings-test-a')
                hub.settings('settings-test-a', patch={'git': {'autoCommit': True}}, expected=current['revision'])
            for path, before in journals.items():
                self.assertEqual(path.read_bytes() if path.exists() else None, before)
            self.assertEqual(list(fake_home.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'unchanged')
            self.assertEqual(set(Path(self.temp.name).rglob('project-settings.json')),
                             {self.registry.base_store(self.pid).data / 'project-settings.json'})
