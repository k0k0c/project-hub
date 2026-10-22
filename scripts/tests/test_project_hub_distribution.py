"""Transfer the real ZIP into a fresh profile; never use live Hub data."""
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import setup_project_hub as setup
from build_project_hub_distribution import build
from test_project_hub_package import hook_argv


class LocalDistributionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive_home = tempfile.TemporaryDirectory()
        cls.archive = Path(cls.archive_home.name) / 'handoff.zip'
        cls.built = build(cls.archive)

    @classmethod
    def tearDownClass(cls):
        cls.archive_home.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        with zipfile.ZipFile(self.archive) as archive:
            archive.extractall(self.base / 'extracted with spaces')
        self.bundle = self.base / 'extracted with spaces/project-hub-0.2.0'
        self.app = self.base / 'installed application with spaces'
        self.data = self.base / 'private user data'

    def install(self, **kwargs):
        return setup.install(self.bundle, self.app, self.data,
                             skip_codex_registration=True, **kwargs)

    def test_archive_is_reproducible_and_has_only_verified_runtime_inputs(self):
        second = self.base / 'second.zip'
        repeated = build(second)
        self.assertEqual(self.archive.read_bytes(), second.read_bytes())
        self.assertEqual(self.built['sha256'], repeated['sha256'])
        manifest = setup.verify_bundle(self.bundle)
        names = manifest['files']
        self.assertNotIn('scripts/tests/test_project_hub_distribution.py', names)
        self.assertFalse(any('/.git/' in '/' + p or p.startswith(('.local/', '.codex/', '.agents/')) for p in names))
        self.assertIn('scripts/ArchitectureSourceScanner.java', names)
        self.assertIn('scripts/hub_project_review.py', names)
        for runtime in ('artifact_store.py', 'git_batch_store.py', 'task_chats.py', 'agent-workflow.md',
                        'native_instruction_store.py', 'native_project_rule.py', 'project_bindings.py', 'agent_launches.py',
                        'codex_desktop_setup.py', 'codex_desktop_bridge.mjs'):
            self.assertIn('scripts/' + runtime, names)
        self.assertIn('tools/project-portal/web/connection-projects.js',names)
        self.assertIn('docs/mcp-project-connections.md',names)
        self.assertIn('docs/codex-desktop-control.md', names)
        self.assertIn('docs/agent-actions.md', names)
        self.assertIn('docs/check-wrapper.md', names)
        self.assertIn('(docs/check-wrapper.md)', (self.bundle / 'README.md').read_text())
        self.assertIn('Wrap every such execution', (self.bundle /
            'tools/project-portal/plugins/project-hub/skills/project-hub/SKILL.md').read_text())
        self.assertFalse(any(p.startswith('.project-hub/') for p in names))
        self.assertIn('tools/project-portal/web/vendor/elk.LICENSE.md', names)
        self.assertEqual(names['tools/project-portal/web/vendor/layout-base.js'],
                         'f5c66be21c9cca16c4f25a576bffbd16ed1a48181c1c2dcbb8d905ec822e76b5')
        self.assertEqual(manifest['lineEndings'], 'LF for UTF-8 text; binary assets unchanged')

    def test_html_runtime_runs_from_the_extracted_bundle(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from knowledge_html import Page; "
            "page = Page(); page.feed('<title>Packaged HTML</title>'); "
            "print(''.join(page.title))"
        )
        result = subprocess.run(
            [sys.executable, '-I', '-S', '-c', code, str(self.bundle / 'scripts')],
            cwd=self.base, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'Packaged HTML')

    def test_standalone_payload_excludes_native_executor_and_imports_api_facade(self):
        from build_project_hub_distribution import RUNTIME
        self.assertIn('outbound_http.py',RUNTIME)
        archive=self.base/'independent.zip'
        build(archive,standalone=True)
        destination=self.base/'independent'
        with zipfile.ZipFile(archive) as incoming:
            incoming.extractall(destination)
        bundle=destination/'project-hub-0.2.0'
        self.assertFalse((bundle/'scripts/codex_adapter.py').exists())
        self.assertFalse((bundle/'scripts/hub_chat_actions.py').exists())
        self.assertFalse((bundle/'setup_project_hub.py').exists())
        self.assertTrue((bundle/'scripts/codex_session_catalog.py').exists())
        for relative in ('scripts/codex_desktop_setup.py', 'scripts/codex_desktop_bridge.mjs', 'docs/codex-desktop-control.md'):
            self.assertTrue((bundle / relative).is_file(), relative)
        self.assertNotIn(b'\r\n', (bundle / 'scripts/codex_desktop_bridge.mjs').read_bytes())
        code=("import sys; sys.path.insert(0,sys.argv[1]); from unified_actions import UnifiedActions; "
              "from agent_launches import Launches; from native_instruction_store import build_bundle_plan; "
              "from native_project_rule import plan; from agent_instructions import bundle; "
              "assert '## Task pipeline' in bundle()['instructionBundle']['files']['workflow.md']; "
              "assert bundle()['instructionBundle']['files']['user-additions.md']==''; print('API facade available')")
        result=subprocess.run([sys.executable,'-I','-S','-c',code,str(bundle/'scripts')],
                              cwd=self.base,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stdout.strip(),'API facade available')

    def test_install_with_spaces_and_update_preserve_data_and_previous_runtime(self):
        self.data.mkdir()
        (self.data / 'existing-history.txt').write_text('keep this history')
        first = self.install(port=17701)
        self.assertFalse(first['codexRegistered'])
        prepared = self.app / 'plugins/project-hub'
        primary = json.loads((prepared / 'plugin.json').read_text())
        legacy = json.loads((prepared / '.codex-plugin/plugin.json').read_text())
        self.assertEqual(primary['version'], legacy['version'])
        old_version = primary['version']
        user_skill = Path(first['userSkillRoot']) / 'SKILL.md'
        self.assertTrue(user_skill.is_file())
        original_skill = user_skill.read_text(encoding='utf-8')
        custom_skill = original_skill.split('---\n\n', 1)[0] + '---\n\n# Receiver preferences\nKeep my local rules.\n'
        user_skill.write_text(custom_skill, encoding='utf-8')
        mcp = json.loads((prepared / 'mcp.json').read_text())['mcpServers']['project_hub']
        self.assertEqual(Path(mcp['args'][0]), prepared / 'scripts/client_entry.py')
        self.assertEqual(Path(mcp['command']), Path(sys.executable))
        self.assertEqual(json.loads((prepared / 'connection.json').read_text())['url'], 'http://127.0.0.1:17701')
        (self.app / 'operator-note.txt').write_text('old runtime note')
        updated = setup.install(self.bundle, self.app, skip_codex_registration=True)
        self.assertEqual(updated['dataHome'], str(self.data))
        self.assertEqual(updated['url'], first['url'])
        self.assertEqual((Path(updated['backup']) / 'operator-note.txt').read_text(), 'old runtime note')
        self.assertEqual((self.data / 'existing-history.txt').read_text(), 'keep this history')
        self.assertEqual(updated['userSkillRoot'], first['userSkillRoot'])
        self.assertEqual(user_skill.read_text(encoding='utf-8'), custom_skill)
        self.assertNotEqual(json.loads((prepared / 'plugin.json').read_text())['version'], old_version)

    def test_corruption_and_unsafe_manifest_references_fail_before_install(self):
        path = self.bundle / 'scripts/project_portal.py'
        original = path.read_bytes()
        path.write_bytes(original + b'\n# changed\n')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.install()
        self.assertFalse(self.app.exists())
        path.write_bytes(original)
        manifest_path = self.bundle / 'distribution.json'
        original_manifest = manifest_path.read_text()
        for name in ('../outside.py', 'C:/outside.py', '.agents/profile.json'):
            malformed = json.loads(original_manifest)
            malformed['files'][name] = '0' * 64
            manifest_path.write_text(json.dumps(malformed))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'reference'):
                setup.verify_bundle(self.bundle)
        manifest_path.write_text(original_manifest)

    def test_unowned_destination_and_runtime_data_overlap_are_rejected(self):
        self.app.mkdir()
        sentinel = self.app / 'existing.txt'
        sentinel.write_text('untouched')
        with self.assertRaisesRegex(ValueError, 'unowned'):
            self.install()
        self.assertEqual(sentinel.read_text(), 'untouched')
        another = self.base / 'separate app'
        with self.assertRaisesRegex(ValueError, 'separate directories'):
            setup.install(self.bundle, another, another / 'data', skip_codex_registration=True)
        self.assertFalse(another.exists())

    def test_registration_uses_codex_commands_and_respects_other_marketplace(self):
        real_which = setup.shutil.which
        def which(name):
            return 'codex-test' if name == 'codex' else real_which(name)
        with patch.object(setup.shutil, 'which', side_effect=which), patch.object(setup, 'codex_command',
                side_effect=[{'installed': []}, {}, {}]) as command:
            result = setup.install(self.bundle, self.app, self.data,
                                   user_skill_root=self.base / '.agents/skills/project-hub-user')
        self.assertTrue(result['codexRegistered'])
        self.assertEqual(command.call_args_list[1].args,
                         ('codex-test', 'marketplace', 'add', str(self.app), '--json'))
        self.assertEqual(command.call_args_list[2].args,
                         ('codex-test', 'add', 'project-hub@project-hub-local', '--json'))
        other = self.base / 'other install'
        with patch.object(setup.shutil, 'which', side_effect=which), patch.object(setup, 'codex_command',
                return_value={'installed': [{'name': 'project-hub', 'marketplaceName': 'other'}]}):
            with self.assertRaisesRegex(ValueError, 'Another marketplace'):
                setup.install(self.bundle, other, self.data)
        self.assertFalse(other.exists())

    def test_fresh_launcher_server_and_prepared_mcp_hooks_use_private_data(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        self.install(port=port)
        project = self.base / 'receiver project'
        project.mkdir()
        second_project = self.base / 'second receiver project'
        second_project.mkdir()
        profile = self.base / 'empty Codex profile'
        profile.mkdir()
        (profile / '.codex-global-state.json').write_text(json.dumps({'local-projects': {
            'receiver': dict(id='receiver', name='Receiver project', rootPaths=[str(project)]),
            'other': dict(id='other', name='Second receiver project', rootPaths=[str(second_project)])}}))
        env = dict(os.environ, CODEX_HOME=str(profile), PROJECT_HUB_HOME=str(self.data))
        for key in ('PROJECT_HUB_URL', 'CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'PLUGIN_ROOT'):
            env.pop(key, None)
        kwargs = {'start_new_session': True} if os.name != 'nt' else {}
        process = subprocess.Popen([sys.executable, str(self.app / 'setup_project_hub.py'),
            'serve', '--install-root', str(self.app)], cwd=self.base, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', **kwargs)
        def stop():
            if os.name == 'nt':
                if process.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            else:
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
            process.communicate(timeout=10)
        self.addCleanup(stop)
        url = 'http://127.0.0.1:' + str(port)
        deadline = time.monotonic() + 15
        while True:
            try:
                with urlopen(url + '/api/health', timeout=.4) as response:
                    health = json.load(response)
                break
            except OSError:
                if process.poll() is not None or time.monotonic() > deadline:
                    self.fail('Fresh receiver server did not start: ' + process.communicate(timeout=5)[1])
                time.sleep(.1)
        self.assertTrue(health['multiProject'])
        self.assertEqual(Path(health['codeRoot']), self.app)
        self.assertEqual(Path(health['dataHome']), self.data)
        with urlopen(url + '/vendor/layout-base.js') as response:
            self.assertEqual(hashlib.sha256(response.read()).hexdigest(),
                             'f5c66be21c9cca16c4f25a576bffbd16ed1a48181c1c2dcbb8d905ec822e76b5')
        prepared = self.app / 'plugins/project-hub'
        env['PLUGIN_ROOT'] = str(prepared)
        hook = json.loads((prepared / 'hooks/hooks.json').read_text())['hooks']['SessionStart'][0]['hooks'][0]
        event = dict(hook_event_name='SessionStart', session_id='distribution-test-session', cwd=str(project))
        observed = subprocess.run(hook_argv(hook), input=json.dumps(event), capture_output=True,
            text=True, encoding='utf-8', env=env, timeout=10)
        self.assertEqual(observed.returncode, 0, observed.stderr)
        self.assertIn('distribution-test-session', observed.stdout)
        request = dict(jsonrpc='2.0', id=1, method='tools/call', params=dict(name='hub_context',
            arguments=dict(session='distribution-test-session')))
        mcp = json.loads((prepared / 'mcp.json').read_text())['mcpServers']['project_hub']
        response = subprocess.run([mcp['command'], *mcp['args'], '--root', str(project)],
            input=json.dumps(request) + '\n', capture_output=True, text=True, encoding='utf-8', env=env, timeout=10)
        self.assertEqual(response.returncode, 0, response.stderr)
        context = json.loads(json.loads(response.stdout)['result']['content'][0]['text'])
        self.assertNotIn('error', context, context)
        self.assertEqual(context['session'], 'distribution-test-session')
        self.assertTrue(context['project'])
        self.assertTrue((self.data / 'registry.sqlite3').is_file())
        self.assertFalse((profile / 'project-hub').exists())

        def get(route):
            with urlopen(url + route, timeout=10) as response:
                return json.load(response)
        def mutate(route, pid, body):
            state = get('/api/state?project=' + pid + '&view=portal')
            request = Request(url + '/api/v1/' + route + '?project=' + pid,
                json.dumps({'expected': state['revision'], **body}).encode(),
                {'Content-Type': 'application/json'})
            with urlopen(request, timeout=10) as response:
                return json.load(response)
        projects = {p['codex_id']: p['id'] for p in get('/api/projects')['projects']}
        for key, root, custom_profile, version, command, exit_code in (
                ('receiver', project, 'python-focused', 'project-a-v1',
                 [sys.executable, '-c', "print('python receiver runner')"], 0),
                ('other', second_project, 'javascript-contract', 'project-b-v9',
                 ['node', '-e', "console.log('javascript receiver runner');process.exit(7)"], 7)):
            pid = projects[key]
            task = mutate('tasks/create', pid, {'task': {'title': 'Receiver checks'}})['createdTask']
            stage = mutate('stages/create', pid, {'task': task,
                'stage': {'title': 'Verify custom runner'}})['createdStage']
            # No --url or creator helper: use the receiving installation's config.
            result = subprocess.run([sys.executable, str(prepared / 'scripts/client_entry.py'),
                'check', 'exec', '--project', pid, '--cwd', str(root), '--task', task,
                '--stage', stage, '--title', 'Receiver custom checks', '--profile', custom_profile,
                '--profile-version', version, '--', *command],
                capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)
            self.assertEqual(result.returncode, exit_code, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output['publication'], 'delivered')
            rows = get('/api/v1/checks?project=' + pid)['runs']
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]['taskId'], rows[0]['stageId'], rows[0]['profile'],
                rows[0]['profileVersion'], rows[0]['status'], rows[0]['exitCode']),
                (task, stage, custom_profile, version, 'passed' if exit_code == 0 else 'failed', exit_code))
            self.assertEqual(rows[0]['command'], command)
            self.assertTrue((Path(output['localLog']).parent / 'delivered.json').is_file())
            self.assertFalse((root / '.local/checks').exists())
            self.assertEqual(subprocess.run([sys.executable, str(prepared / 'scripts/client_entry.py'),
                'check', 'flush', '--project', pid, '--cwd', str(root)],
                capture_output=True, env=env, timeout=10).returncode, 0)


if __name__ == '__main__':
    unittest.main()
