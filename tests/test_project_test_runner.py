"""Focused runner contracts; every repository and test data home is disposable."""
import importlib.util
import io
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('project_hub_check', SOURCE / 'scripts/project_hub_check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SelectionPolicyTests(unittest.TestCase):
    def test_local_source_and_test_edits_execute_exact_union_once(self):
        config = {'profiles': {'docs': [], 'full': ['test_*.py'], 'broad': ['test_*.py']},
                  'rules': [], 'sourceTests': {'scripts/local.py': ['scripts/tests/test_owned.py']}}
        paths = ['scripts/local.py', 'scripts/tests/test_owned.py', 'scripts/tests/test_new.py']
        profiles, reasons = runner.select_profiles(config, paths, 'auto')
        self.assertEqual(['test-files'], profiles)
        self.assertEqual(3, len(reasons))
        selected = runner.selected_test_paths(config, paths, profiles)
        self.assertEqual(['scripts/tests/test_new.py', 'scripts/tests/test_owned.py'], selected)
        files = {p: ('100644', b'') for p in selected + [runner.UNITTEST_RUNNER, 'scripts/tests/test_unrelated.py']}
        commands = runner.commands_for(config, profiles, files, selected)
        self.assertEqual(1, len(commands))
        self.assertEqual(1, commands[0].count('test_owned.py'))
        self.assertNotIn('test_unrelated.py', commands[0])
        self.assertEqual(['full'], runner.select_profiles(config, paths + ['unknown.py'], 'auto')[0])
        self.assertEqual(['full'], runner.select_profiles(config, paths, 'release')[0])

    def test_missing_exact_tests_and_unsafe_mapping_fail_closed(self):
        config = {'profiles': {'docs': [], 'full': ['test_*.py']}, 'rules': []}
        with self.assertRaisesRegex(ValueError, 'absent'):
            runner.commands_for(config, ['test-files'], {}, ['scripts/tests/test_deleted.py'])
        for mapping in ({'../escape.py': ['scripts/tests/test_owned.py']},
                        {'scripts/local.py': ['scripts/tests/test_../escape.py']},
                        {'scripts/local.py': []}, {'scripts/local.py': ['product.py']}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                runner.select_profiles(dict(config, sourceTests=mapping), ['scripts/local.py'], 'auto')

    def test_installer_ui_and_runner_source_select_focused_contracts(self):
        config = json.loads((SOURCE / runner.CONFIG).read_text())
        for path, expected in [('installer/project-hub.iss', ['installer-lifecycle']),
                               ('scripts/hub_update.py', ['installer-lifecycle']),
                               ('scripts/build_windows_installer.py', ['distribution']),
                               ('scripts/build_project_hub_distribution.py', ['distribution']),
                               ('scripts/hub_source.py', ['portable-runtime']),
                               ('tools/project-portal/web/settings.js', ['settings-ui']),
                               ('tools/project-portal/web/projects.js', ['test-files']),
                               ('SOURCE-NOTICES.md', ['docs']),
                               ('scripts/project_hub_check_publish.py', ['runner'])]:
            with self.subTest(path=path):
                self.assertEqual(expected, runner.select_profiles(config, [path], 'auto')[0])
        self.assertEqual(['full'], runner.select_profiles(config, ['scripts/project_portal.py'], 'auto')[0])

    def test_configured_focused_profiles_keep_javascript_syntax_coverage(self):
        config = {'profiles': {'small': ['test_owned.py'], 'full': ['test_*.py']},
                  'javascriptProfiles': ['small', 'test-files', 'full']}
        files = {'scripts/tests/test_owned.py': ('100644', b''), runner.UNITTEST_RUNNER: ('100644', b''),
                 'tools/project-portal/web/app.js': ('100644', b'')}
        self.assertEqual(['node', '--check', 'tools/project-portal/web/app.js'],
                         runner.commands_for(config, ['small'], files)[-1])
        with self.assertRaisesRegex(ValueError, 'javascriptProfiles'):
            runner.commands_for(dict(config, javascriptProfiles=['unknown']), ['small'], files)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = Path(self.temp.name).parent / (Path(self.temp.name).name + '-check-output')
        self.output.mkdir()
        self.output_env = patch.dict(os.environ, {'PROJECT_HUB_CHECK_OUTPUT_HOME': str(self.output)})
        self.output_env.start()
        self.addCleanup(self.output_env.stop)
        self.git('init', '-q')
        self.write('.gitignore', '.local/\n__pycache__/\n')
        self.write(runner.CONFIG, json.dumps({'version': 2, 'profiles': {
            name: ([] if name == 'docs' else ['test_*.py']) for name in runner.PROFILES if name not in ('auto', 'release')}, 'rules': [
                {'paths': ['web/*.css'], 'profiles': ['css']},
                {'paths': ['web/*'], 'profiles': ['javascript']}]}))
        self.write('scripts/tests/test_fixture.py', 'import unittest\nclass Test(unittest.TestCase):\n def test_ok(self): pass\n')
        self.write(runner.UNITTEST_RUNNER, (SOURCE / runner.UNITTEST_RUNNER).read_text(encoding='utf-8'))
        self.git('add', '.')

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        return subprocess.check_output(['git', '-C', str(self.root), *args], env=env, stderr=subprocess.PIPE)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8', newline='\n')

    def results(self):
        return [json.loads(p.read_text()) for p in self.output.rglob('*.json') if p.parent.name != 'receipts']

    def test_check_output_is_external_namespaced_and_rejects_overlap(self):
        output = runner.output_home(self.root)
        self.assertTrue(output.is_relative_to(self.output))
        self.assertEqual(16, output.name.__len__())
        with patch.dict(os.environ, {'PROJECT_HUB_CHECK_OUTPUT_HOME': str(self.root / 'inside')}):
            with self.assertRaises(ValueError):
                runner.output_home(self.root)

    def external_fixture(self, roles=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        cas = Path(directory.name)
        data = b'\x00opaque\xfffixture'
        content_hash = runner.digest(data)
        descriptor = dict(schemaVersion=1, kind='artifact-descriptor', artifactId='fixture',
                          name='opaque.bin', contentHash=content_hash, version=content_hash,
                          size=len(data), roles=roles or ['evidence', 'test-fixture'], provenance='Disposable fixture')
        raw = runner.canonical(descriptor)
        descriptor_hash = runner.digest(raw)
        for identifier, content in ((content_hash, data), (descriptor_hash, raw)):
            path = cas / 'blobs' / identifier[:2] / identifier
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        entry = dict(environment='PROJECT_HUB_INPUT_FIXTURE_CAS', path='fixtures/opaque.bin',
                     ref='hub-artifact/' + descriptor_hash + '/opaque.bin')
        config = json.loads((self.root / runner.CONFIG).read_text())
        config['validationInputs'] = dict(version=1, artifacts=[entry], files=[], builds=[], profileDependencies={})
        self.write(runner.CONFIG, json.dumps(config))
        return cas, entry, content_hash, data

    def test_external_artifact_is_materialized_in_private_snapshot_and_receipt(self):
        cas, entry, content_hash, data = self.external_fixture()
        self.write('scripts/tests/test_fixture.py', "import unittest,os,pathlib\nclass Test(unittest.TestCase):\n def test_fixture(self):\n  self.assertEqual(pathlib.Path('fixtures/opaque.bin').read_bytes()," + repr(data) + ")\n  self.assertNotIn('PROJECT_HUB_INPUT_FIXTURE_CAS',os.environ)\n")
        self.git('add', '.')
        with patch.dict(os.environ, {entry['environment']: str(cas)}):
            self.assertEqual(0, runner.run(self.root, 'full'))
            self.assertEqual(0, runner.run(self.root, 'full'))
            self.assertEqual(0, runner.run(self.root, 'full', staged=True))
        results = self.results()
        self.assertEqual(2, sum(bool(row['reused']) for row in results))
        item = next(item for item in results[0]['inputManifest'] if item['path'] == entry['path'])
        self.assertEqual(item['sha256'], content_hash)
        self.assertEqual(item['source']['ref'], entry['ref'])
        self.assertEqual(item['source']['roles'], ['evidence', 'test-fixture'])
        self.assertFalse((self.root / entry['path']).exists())
        self.assertEqual({'staged', 'worktree'}, {row['mode'] for row in results})

    def test_declared_build_and_profile_dependencies_run_before_tests_and_full(self):
        self.write('build.py', "from pathlib import Path\nPath('generated').mkdir(exist_ok=True)\nPath('generated/result').write_text('built')\n")
        self.write('scripts/tests/test_fixture.py', "import unittest,pathlib\nclass Test(unittest.TestCase):\n def test_built(self): self.assertEqual(pathlib.Path('generated/result').read_text(),'built')\n")
        config = json.loads((self.root / runner.CONFIG).read_text())
        config['validationInputs'] = dict(version=1, builds=[dict(id='fixture-build', argv=['python', '-S', 'build.py'], inputs=['build.py'], profiles=['css'])], profileDependencies={'css': ['javascript']})
        self.write(runner.CONFIG, json.dumps(config))
        self.assertEqual(['css'], runner.select_profiles(config, ['build.py'], 'auto')[0])
        self.assertEqual(0, runner.run(self.root, 'css'))
        self.assertEqual(0, runner.run(self.root, 'release'))
        for row in self.results():
            self.assertEqual(row['commands'][0], ['python', '-S', 'build.py'])
            self.assertEqual(row['buildDependencies'], ['fixture-build'])
        self.assertEqual({'css', 'javascript'}, set(next(row for row in self.results() if row['profiles'] != ['full'])['profiles']))

    def test_explain_resolves_inputs_commands_and_hashes_without_host_binding_values(self):
        cas, entry, _, _ = self.external_fixture()
        output = io.StringIO()
        with patch.dict(os.environ, {entry['environment']: str(cas)}), redirect_stdout(output):
            self.assertEqual(0, runner.run(self.root, 'full', explain=True))
        result = json.loads(output.getvalue())
        self.assertEqual(result['externalInputs'], [entry['path']])
        self.assertEqual(result['inputManifestSha256'], runner.digest(runner.canonical(result['inputManifest'])))
        self.assertTrue(Path(result['executionSpec']['argv'][0][0]).is_absolute())
        self.assertNotIn(str(cas), output.getvalue())
        self.assertFalse(any(self.output.rglob('*')))

    def test_external_inputs_fail_closed_for_missing_corrupt_and_unsafe_sources(self):
        cas, entry, content_hash, data = self.external_fixture()
        config = json.loads((self.root / runner.CONFIG).read_text())
        checkout = runner.collect(self.root)
        with self.assertRaisesRegex(ValueError, 'Missing absolute'):
            runner.resolve_validation_inputs(self.root, config, checkout, {})
        bindings = {entry['environment']: str(cas)}
        for target in ('../escape', '.git/index', '.local/escape', runner.CONFIG, 'fixtures/../escape'):
            with self.subTest(target=target):
                invalid = json.loads(json.dumps(config))
                invalid['validationInputs']['artifacts'][0]['path'] = target
                with self.assertRaises(ValueError):
                    runner.resolve_validation_inputs(self.root, invalid, checkout, bindings)
        (cas / 'blobs' / content_hash[:2] / content_hash).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            runner.resolve_validation_inputs(self.root, config, checkout, bindings)
        (cas / 'blobs' / content_hash[:2] / content_hash).unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            runner.resolve_validation_inputs(self.root, config, checkout, bindings)
        self.assertEqual(data, b'\x00opaque\xfffixture')

    def test_pinned_dependency_file_changes_or_role_changes_never_hide_input(self):
        cas, entry, _, data = self.external_fixture(['evidence'])
        config = json.loads((self.root / runner.CONFIG).read_text())
        dependency = cas / 'dependency.bin'
        dependency.write_bytes(b'dependency')
        config['validationInputs']['files'] = [dict(environment='PROJECT_HUB_INPUT_DEPENDENCY', path='vendor/dependency.bin', sha256=runner.digest(b'dependency'), mode='100644')]
        self.write(runner.CONFIG, json.dumps(config))
        with patch.dict(os.environ, {entry['environment']: str(cas), 'PROJECT_HUB_INPUT_DEPENDENCY': str(dependency)}):
            self.assertEqual(0, runner.run(self.root, 'docs'))
            dependency.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                runner.run(self.root, 'docs')
        files, origins, _ = runner.resolve_validation_inputs(self.root, dict(config, validationInputs=dict(version=1, artifacts=[entry])), runner.collect(self.root), {entry['environment']: str(cas)})
        self.assertEqual(files[entry['path']][1], data)
        self.assertEqual(origins[entry['path']]['roles'], ['evidence'])
        result = self.results()[0]
        self.assertTrue(any(item['path'] == 'vendor/dependency.bin' for item in result['inputManifest']))

    def test_external_blob_removed_during_run_refuses_receipt(self):
        cas, entry, content_hash, _ = self.external_fixture()
        original = runner.subprocess.run
        def remove_after_launch(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs.get('cwd') == self.root:
                (cas / 'blobs' / content_hash[:2] / content_hash).unlink(missing_ok=True)
            return result
        with patch.dict(os.environ, {entry['environment']: str(cas)}), patch.object(runner.subprocess, 'run', side_effect=remove_after_launch):
            self.assertNotEqual(0, runner.run(self.root, 'full'))
        self.assertEqual(self.results()[0]['failureKind'], 'inputs_changed')
        self.assertFalse(list(self.output.rglob('receipts/*.json')))

    def test_invalid_build_graph_or_policy_is_not_silently_ignored(self):
        config = json.loads((self.root / runner.CONFIG).read_text())
        for policy in ({'version': 1, 'exclude': ['fixture']},
                       {'version': 1, 'profileDependencies': {'css': ['javascript'], 'javascript': ['css']}},
                       {'version': 1, 'profileDependencies': {'css': ['missing']}},
                       {'version': 1, 'builds': [{'id': 'invalid'}]}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                runner.validation_policy(dict(config, validationInputs=policy))

    def test_auto_uses_declared_external_dependency_coverage_with_clean_checkout(self):
        cas, entry, _, data = self.external_fixture()
        config = json.loads((self.root / runner.CONFIG).read_text())
        config['validationInputs']['builds'] = [dict(id='artifact-build', argv=['python', '-S', '-c',
            "from pathlib import Path; assert Path('fixtures/opaque.bin').read_bytes()==" + repr(data)],
            inputs=['fixtures/opaque.bin'], profiles=['artifacts'])]
        config['validationInputs']['profileDependencies'] = {'artifacts': ['runner']}
        self.write(runner.CONFIG, json.dumps(config))
        self.git('config', 'user.email', 'inputs@example.test')
        self.git('config', 'user.name', 'Input Fixture')
        self.git('add', '.')
        self.git('commit', '-qm', 'Declared fixture')
        with patch.dict(os.environ, {entry['environment']: str(cas)}):
            self.assertEqual(0, runner.run(self.root, 'auto'))
        result = self.results()[0]
        self.assertEqual(result['checkoutScope'], [])
        self.assertEqual(result['validationScope'], [entry['path']])
        self.assertEqual(result['profiles'], ['artifacts', 'runner'])
        self.assertEqual(result['buildDependencies'], ['artifact-build'])

    def test_malformed_pinned_artifact_metadata_is_refused(self):
        cas, entry, _, _ = self.external_fixture()
        config = json.loads((self.root / runner.CONFIG).read_text())
        identifier = entry['ref'].split('/')[1]
        descriptor = json.loads((cas / 'blobs' / identifier[:2] / identifier).read_bytes())
        for key, value in [('artifactId', ''), ('provenance', ''), ('previous', 'unsafe'), ('artifactId', '\0bad')]:
            invalid = dict(descriptor, **{key: value})
            raw = runner.canonical(invalid); identifier = runner.digest(raw)
            path = cas / 'blobs' / identifier[:2] / identifier
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            config['validationInputs']['artifacts'][0]['ref'] = 'hub-artifact/' + identifier + '/opaque.bin'
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'descriptor'):
                runner.resolve_validation_inputs(self.root, config, runner.collect(self.root), {entry['environment']: str(cas)})

    def test_mapping_unions_dependencies_and_unknown_falls_back(self):
        config = json.loads((self.root / runner.CONFIG).read_text())
        self.assertEqual(runner.select_profiles(config, ['web/a.css'], 'auto')[0], ['css', 'javascript'])
        self.assertEqual(runner.select_profiles(config, ['web/a.css', 'unknown'], 'auto')[0], ['full'])
        self.assertEqual(runner.select_profiles(config, [], 'auto')[0], ['docs'])
        self.assertEqual(runner.select_profiles(config, ['web/a.css'], 'release')[0], ['full'])

    def test_project_css_selection_and_new_checks_coverage(self):
        config = json.loads((SOURCE / runner.CONFIG).read_text())
        self.assertEqual(['css'], runner.select_profiles(config, ['tools/project-portal/web/style.css'], 'auto')[0])
        for profile, name in [('css', 'test_checks_ui.py'), ('javascript', 'test_checks_ui.py'),
                              ('package', 'test_check_wrapper.py'), ('package', 'test_check_publish.py'),
                              ('package', 'test_checks_end_to_end.py'), ('core', 'test_checks_http.py')]:
            self.assertTrue(any(runner.fnmatch.fnmatchcase(name, p) for p in config['profiles'][profile]))

    def test_project_specialization_preserves_shared_and_unknown_boundaries(self):
        config = json.loads((SOURCE / runner.CONFIG).read_text())
        cases = [(['docs/html-documentation.md'], ['docs']),
                 (['docs/design/prototype.html'], ['docs']),
                 (['docs/tool.py'], ['full']),
                 (['tools/project-portal/web/documentation.css'], ['test-files']),
                 (['tools/project-portal/web/html-documents.js'], ['documentation-ui']),
                 (['scripts/tests/test_html_documents_ui.py'], ['test-files']),
                 (['scripts/knowledge_html.py'], ['html-documents']),
                 (['tools/project-portal/plugins/project-hub/skills/project-hub/SKILL.md'], ['plugin-docs']),
                 (['tools/project-portal/plugins/project-hub/skills/project-hub/scripts/new.py'], ['full']),
                 (['tools/project-portal/web/index.html'], ['css']),
                 (['tools/project-portal/web/checks.js'], ['javascript']),
                 (['scripts/tests/test_checks_http.py'], ['test-files']),
                 (['scripts/tests/test_new_contract.py'], ['test-files']),
                 (['tests/test_project_test_runner.py'], ['test-files']),
                 (['scripts/project_hub_check.py'], ['runner']),
                 (['docs/readme.md', 'scripts/plugin_api.py'], ['full'])]
        for paths, expected in cases:
            with self.subTest(paths=paths):
                self.assertEqual(expected, runner.select_profiles(config, paths, 'auto')[0])

    def test_instruction_prose_selection_preserves_runtime_and_release_coverage(self):
        config = json.loads((SOURCE / runner.CONFIG).read_text())
        package = 'tools/project-portal/plugins/project-hub/'
        prose = package + 'assets/instructions-catalog.json'
        cases = [([prose], ['hub-instructions']),
                 ([prose, package + 'assets/default-user-instructions.md'], ['hub-instructions', 'plugin-docs']),
                 ([prose, 'tools/project-portal/web/settings.css'], ['hub-instructions', 'settings-ui']),
                 ([prose, 'tools/project-portal/web/settings.js'], ['hub-instructions', 'settings-ui']),
                 ([prose, package + 'scripts/hub_instructions.py'], ['full']),
                 ([package + 'scripts/hub_core.py'], ['full']),
                 ([package + 'scripts/hub_http.py'], ['full']),
                 ([package + 'hooks/hooks.json'], ['full']),
                 ([package + 'assets/unknown.json'], ['full']),
                 (['scripts/project_portal.py'], ['full']),
                 (['scripts/project_hub_check.py'], ['runner']),
                 ([runner.CONFIG], ['runner'])]
        for paths, expected in cases:
            with self.subTest(paths=paths):
                self.assertEqual(expected, runner.select_profiles(config, paths, 'auto')[0])
        self.assertEqual(['full'], runner.select_profiles(config, [prose], 'release')[0])

    def test_changed_tests_do_not_expand_to_all_owning_profiles(self):
        config = {'profiles': {'docs': [], 'portal': ['test_owned.py'], 'full': ['test_*.py']}, 'rules': []}
        self.assertEqual(['test-files'], runner.select_profiles(config, ['scripts/tests/test_owned.py'], 'auto')[0])
        self.assertEqual(['test-files'], runner.select_profiles(config, ['scripts/tests/test_unknown.py'], 'auto')[0])
        with self.assertRaises(ValueError):
            runner.select_profiles(config, [], 'invented-profile')

    def test_auto_worktree_does_not_silently_launch_full_but_staged_still_validates(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, runner.run(self.root, explain=True))
        self.assertEqual(['full'], json.loads(output.getvalue())['profiles'])
        with patch.object(runner, 'preflight_spec', side_effect=AssertionError('Full must be explicit')):
            with self.assertRaisesRegex(ValueError, 'auto would run the full suite'):
                runner.run(self.root)
        self.assertEqual([], self.results())
        self.assertEqual(0, runner.run(self.root, staged=True))
        self.assertEqual(['full'], self.results()[0]['profiles'])

    def test_grouped_selection_executes_union_once_and_collects_timings(self):
        self.write('scripts/tests/test_second.py', 'import unittest\nclass Test(unittest.TestCase):\n def test_second(self): pass\n')
        config = json.loads((self.root / runner.CONFIG).read_text())
        commands = runner.commands_for(config, ['css', 'javascript'], runner.collect(self.root))
        self.assertEqual(1, len(commands))
        self.assertEqual(1, commands[0].count('test_fixture.py'))
        self.assertEqual(0, runner.run(self.root, 'css'))
        result = self.results()[0]
        self.assertEqual(2, result['timings'][0]['unittest']['testsRun'])
        self.assertEqual(2, len(result['timings'][0]['unittest']['tests']))
        self.assertGreaterEqual(result['timings'][0]['seconds'], 0)

    def test_docs_profile_uses_diff_and_receipts_without_unit_tests(self):
        self.write('scripts/tests/test_fixture.py', 'raise RuntimeError("must not run for prose")\n')
        self.assertEqual(0, runner.run(self.root, 'docs'))
        self.assertEqual([], self.results()[0]['commands'])
        self.assertEqual([], self.results()[0]['timings'])
        self.assertEqual(0, runner.run(self.root, 'docs'))
        self.assertEqual(1, sum(bool(r['reused']) for r in self.results()))

    def test_task_scope_excludes_foreign_selection_but_keeps_full_tree_identity(self):
        self.git('config', 'user.email', 'runner@example.test')
        self.git('config', 'user.name', 'Runner')
        self.git('commit', '-qm', 'Baseline')
        self.write('web/a.css', 'local change')
        self.write('foreign.py', 'unrelated backend')
        self.assertEqual(0, runner.run(self.root, scopes=['web']))
        result = self.results()[0]
        self.assertEqual(['css', 'javascript'], result['profiles'])
        self.assertEqual(['web/a.css'], result['scope'])
        self.assertIn('foreign.py', result['checkoutScope'])
        self.assertEqual('task-feedback', result['coverage'])
        self.write('foreign.py', 'changed foreign input')
        self.assertEqual(0, runner.run(self.root, scopes=['web']))
        self.assertFalse(any(r['reused'] for r in self.results()))
        for kwargs in ({'staged': True}, {'profile': 'full'}, {'profile': 'release'},
                       {'scopes': ['../outside']}, {'scopes': ['missing']}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                runner.run(self.root, **({'scopes': ['web']} | kwargs))

    def test_configured_timeout_and_distinct_timeout_failure(self):
        actual = runner.subprocess.run
        observed_timeouts = []

        def timeout_test(*args, **kwargs):
            if args[0][0] == sys.executable:
                observed_timeouts.append(kwargs['timeout'])
                raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
            return actual(*args, **kwargs)

        with patch.object(runner.subprocess, 'run', side_effect=timeout_test):
            self.assertNotEqual(0, runner.run(self.root, 'full', timeout=42))
        self.assertEqual([42], observed_timeouts)
        self.assertEqual('timeout', self.results()[0]['failureKind'])
        self.assertTrue(self.results()[0]['stable'])
        for value in (0, -1, float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.run(self.root, timeout=value)

    def test_dirty_untracked_and_staged_are_different_actual_inputs(self):
        before = runner.tree_key(runner.collect(self.root, True))
        self.write('scripts/tests/test_fixture.py', 'unstaged failing content')
        self.write('untracked.txt', 'new dependency')
        self.assertEqual(before, runner.tree_key(runner.collect(self.root, True)))
        self.assertNotEqual(before, runner.tree_key(runner.collect(self.root)))
        self.assertIn('untracked.txt', runner.changed_paths(self.root))

    def test_receipt_reuse_requires_equivalent_tree_and_artifacts(self):
        self.assertEqual(0, runner.run(self.root, 'full'))
        self.assertEqual(0, runner.run(self.root, 'full', staged=True))
        reused = [r for r in self.results() if r['reused']]
        self.assertEqual(1, len(reused))
        original = json.loads(Path(reused[0]['reused']).read_text())
        Path(original['log']).write_text('corrupted')
        self.assertEqual(0, runner.run(self.root, 'full'))
        self.assertEqual(1, sum(bool(r['reused']) for r in self.results()))

    def test_full_receipt_satisfies_focused_but_not_reverse(self):
        self.assertEqual(0, runner.run(self.root, 'css'))
        self.assertEqual(0, runner.run(self.root, 'full'))
        self.assertFalse(any(r['reused'] for r in self.results()))
        self.assertEqual(0, runner.run(self.root, 'portal', staged=True))
        self.assertEqual(1, sum(bool(r['reused']) for r in self.results()))

    def test_line_endings_prevent_reuse_and_explain_tree_difference(self):
        # Model Git's checkout conversion explicitly, independent of user config.
        # Without it diff --check correctly treats raw CR bytes as whitespace.
        self.git('config', 'core.autocrlf', 'true')
        path = self.root / 'scripts/tests/test_fixture.py'
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        self.assertEqual(0, runner.run(self.root, 'full'))
        self.assertEqual(0, runner.run(self.root, 'full', staged=True))
        staged = next(r for r in self.results() if r['mode'] == 'staged')
        self.assertIsNone(staged['reused'])
        self.assertEqual(['tree', 'inputManifest', 'executionSpec'], staged['receiptReuse']['changed'])
        self.assertEqual('inputs_changed', staged['receiptReuse']['reason'])

    def test_reuse_diagnostic_supports_legacy_results_and_hides_environment(self):
        output = runner.output_home(self.root)
        output.mkdir(parents=True, exist_ok=True)
        (output / 'previous.json').write_text(json.dumps({
            'exitCode': 0, 'commands': [['python']], 'tree': 'old'}))
        result = runner.reuse_diagnostic(output, {'tree': 'new', 'toolchain': 'hash'}, [['python']])
        self.assertEqual(['tree'], result['changed'])
        self.assertEqual(['toolchain'], result['unrecorded'])
        self.assertEqual({'reason': 'fresh_requested'}, runner.reuse_diagnostic(output, {}, [], True))

    def test_whitespace_failure_is_not_cached(self):
        self.write('scripts/tests/test_fixture.py', '# trailing space \n')
        self.git('add', 'scripts/tests/test_fixture.py')
        self.assertNotEqual(0, runner.run(self.root, 'full', staged=True))
        self.assertIn('Diff safety check failed', Path(self.results()[0]['log']).read_text())

    def test_valid_receipt_never_skips_diff_check(self):
        self.assertEqual(0, runner.run(self.root, 'full'))
        actual = runner.subprocess.run

        def fail_diff(*args, **kwargs):
            if '--check' in args[0]:
                return subprocess.CompletedProcess(args[0], 2)
            return actual(*args, **kwargs)

        with patch.object(runner.subprocess, 'run', side_effect=fail_diff):
            self.assertEqual(2, runner.run(self.root, 'full'))
        self.assertFalse(any(r['reused'] for r in self.results()))

    def test_failure_never_produces_receipt(self):
        self.write('scripts/tests/test_fixture.py', 'import unittest\nclass Test(unittest.TestCase):\n def test_bad(self): self.fail("expected")\n')
        self.assertNotEqual(0, runner.run(self.root, 'full'))
        self.assertFalse(list(self.output.rglob('receipts/*.json')))

    def test_snapshot_uses_private_homes_and_no_inherited_git(self):
        self.write('scripts/tests/test_fixture.py', f'''import os, pathlib, subprocess, tempfile, unittest
class Test(unittest.TestCase):
 def test_isolation(self):
  self.assertNotIn('GIT_INDEX_FILE', os.environ)
  self.assertNotEqual(os.environ['PROJECT_HUB_HOME'], 'production')
  self.assertTrue(pathlib.Path(os.environ['PROJECT_HUB_HOME']).is_dir())
  self.assertNotIn('.git', [p.name for p in pathlib.Path('.').iterdir()])
  self.assertFalse(pathlib.Path.cwd().resolve().is_relative_to(pathlib.Path({str(self.root)!r})))
  with tempfile.TemporaryDirectory() as directory:
   root = pathlib.Path(directory) / 'a'
   root.mkdir()
   unrelated = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True)
   self.assertNotEqual(unrelated.returncode, 0)
   subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True)
   evidence = root / 'evidence' / ('long-evidence-name-' * 6 + '0000.txt')
   evidence.parent.mkdir()
   evidence.write_text('proof')
   subprocess.run(['git', '-C', str(root), 'add', 'evidence'], check=True)
''')
        with patch.dict(os.environ, {'PROJECT_HUB_HOME': 'production'}):
            self.assertEqual(0, runner.run(self.root, 'full'))

    def test_config_environment_and_tool_changes_invalidate_key(self):
        self.assertEqual(0, runner.run(self.root, 'full'))
        with patch.dict(os.environ, {'CHECK_FIXTURE_SWITCH': 'changed'}):
            self.assertEqual(0, runner.run(self.root, 'full'))
        self.write('untracked-input.txt', 'dirty')
        self.assertEqual(0, runner.run(self.root, 'full'))
        self.assertEqual(3, len({r['key'] for r in self.results()}))
        self.assertFalse(any(r['reused'] for r in self.results()))

    def test_execution_spec_records_and_launches_exact_absolute_commands(self):
        actual = runner.subprocess.run
        launched = []
        def observe(argv, **kwargs):
            if '-S' in argv:
                launched.append(list(argv))
                self.assertTrue(Path(argv[0]).is_absolute())
                self.assertNotIn('GIT_INDEX_FILE', kwargs['env'])
            return actual(argv, **kwargs)
        with patch.object(runner.subprocess, 'run', side_effect=observe):
            self.assertEqual(0, runner.run(self.root, 'full'))
        result = self.results()[0]
        planned = result['executionSpec']['argv']
        self.assertEqual(launched[0][:-1], planned[0][:-1])
        self.assertEqual(planned[0][-1], '<private>/timings-0.json')
        manifest = result['inputManifest']
        self.assertEqual([item['path'] for item in manifest], sorted(runner.collect(self.root)))
        self.assertEqual(result['executionSpec']['inputManifestSha256'],
                         runner.digest(runner.canonical(manifest)))

    def test_legacy_receipt_without_execution_spec_is_not_reused(self):
        self.assertEqual(0, runner.run(self.root, 'full'))
        path = next(self.output.rglob('receipts/*.json'))
        old = json.loads(path.read_text())
        old.pop('executionSpec')
        path.write_text(json.dumps(old))
        self.assertEqual(0, runner.run(self.root, 'full'))
        self.assertFalse(any(result['reused'] for result in self.results()))

    def test_resolution_uses_captured_path_without_rewriting_it(self):
        marker = 'literal-path;MSYS-looking/bin'
        env = dict(runner.base_environment(), PATH=marker)
        git = runner.shutil.which('git')
        with patch.object(runner.shutil, 'which', return_value=git) as resolve:
            commands = runner.resolve_commands([['git', 'diff', '--check']], env)
        resolve.assert_called_once_with('git', path=marker)
        self.assertEqual(commands[0][0], str(Path(git).resolve()))
        self.assertEqual(env['PATH'], marker)

    @unittest.skipUnless(os.name == 'nt', 'Git for Windows launch normalization')
    def test_native_launcher_applies_same_effective_environment_from_git_shell(self):
        original = runner.base_environment()
        executable = runner.shutil.which('git', path=original['PATH'])
        home = str(self.root / 'private-home')
        native = runner.native_windows_environment(dict(original), home)
        installation = Path(native['PATH'].split(os.pathsep)[0]).parent
        shell = dict(original, PATH=os.pathsep.join([str(Path(home) / 'bin'), str(installation / 'mingw64/libexec/git-core'),
                      str(installation / 'mingw64/bin'), str(installation / 'usr/bin'), original['PATH']]),
                      MSYSTEM='MINGW64', SHELL='/usr/bin/bash', SHLVL='1', PWD='/c/source', TERM='xterm')
        effective = runner.native_windows_environment(shell, home)
        self.assertEqual(native, effective)
        commands = [['git', '--version'], ['node', '--version']]
        self.assertEqual(runner.resolve_commands(commands, native), runner.resolve_commands(commands, effective))
        self.assertIn('PATH', effective)
        self.assertNotIn('MSYSTEM', effective)

    @unittest.skipUnless(os.name == 'nt', 'Real Git for Windows pre-commit environment')
    def test_real_git_hook_and_native_launch_resolve_identical_execution_spec(self):
        config = json.loads((self.root / runner.CONFIG).read_text())
        config['executionEnvironment'] = {'version': 1, 'mode': 'native'}
        self.write(runner.CONFIG, json.dumps(config))
        self.git('config', 'user.name', 'Native launcher test')
        self.git('config', 'user.email', 'launcher@example.test')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('add', '.')
        self.git('commit', '-qm', 'initial fixture')
        probe = self.root / '.local/spec-probe.py'
        probe.parent.mkdir()
        probe.write_text('''import importlib.util,json,pathlib,sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))
s=importlib.util.spec_from_file_location('runner',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
root=pathlib.Path(sys.argv[2]);files=m.collect(root,True);config=json.loads(files[m.CONFIG][1])
commands=m.commands_for(config,['full'],files)
env=m.base_environment(config)
entries=env['PATH'].split(m.os.pathsep)
def classify(entry):
 path=pathlib.Path(entry);known={'git-core','bin','cmd','usr','mingw64','Git','git','msys64','msys32'}
 return '/'.join(part if part in known else 'other' for part in path.parts[-3:]) + (' fixture' if path.is_relative_to(root) else '') + (' home' if m.os.environ.get('HOME') and path.is_relative_to(pathlib.Path(m.os.environ['HOME']).resolve()) else '')
value=dict(spec=m.execution_spec(commands,files,env,1800),environmentKeys={key:m.digest(val.encode()) for key,val in env.items()},pathHashes=[m.digest(entry.encode()) for entry in entries],pathClasses=[classify(entry) for entry in entries])
print(json.dumps(value,sort_keys=True))
''', encoding='utf-8')
        argv = [sys.executable, str(probe), str(SOURCE / 'scripts/project_hub_check.py'), str(self.root)]
        native = json.loads(subprocess.check_output(argv, cwd=self.root))
        output = self.root / '.local/hook-spec.json'
        hook = self.root / '.git/hooks/pre-commit'
        shell_argv = ' '.join(shlex.quote(Path(arg).as_posix()) for arg in argv)
        hook.write_text('#!/bin/sh\n' + shell_argv + ' > ' + shlex.quote(output.as_posix()) + '\n', encoding='utf-8', newline='\n')
        self.git('commit', '--allow-empty', '-qm', 'ordinary hook fixture')
        hooked = json.loads(output.read_text(encoding='utf-8'))
        keys = native['environmentKeys'].keys() | hooked['environmentKeys'].keys()
        changed = sorted(key for key in keys if native['environmentKeys'].get(key) != hooked['environmentKeys'].get(key))
        path_positions = [native['pathHashes'].index(value) if value in native['pathHashes'] else 'added' for value in hooked['pathHashes']]
        self.assertEqual(native['spec'], hooked['spec'], 'Effective environment keys changed: ' + ', '.join(changed)
                         + '; native PATH length=' + str(len(native['pathHashes'])) + '; hook PATH positions=' + str(path_positions)
                         + '; added classes=' + str([hooked['pathClasses'][index] for index, value in enumerate(path_positions) if value == 'added']))

    def test_config_and_toolchain_changes_do_not_reuse(self):
        self.assertEqual(0, runner.run(self.root, 'full'))
        config = json.loads((self.root / runner.CONFIG).read_text())
        config['note'] = 'changed configuration'
        self.write(runner.CONFIG, json.dumps(config))
        self.assertEqual(0, runner.run(self.root, 'full'))
        with patch.object(runner, 'toolchain', return_value={'runtime': 'different'}):
            self.assertEqual(0, runner.run(self.root, 'full'))
        self.assertEqual(3, len({r['key'] for r in self.results()}))
        self.assertFalse(any(r['reused'] for r in self.results()))

    def test_staged_run_ignores_unstaged_failure(self):
        self.write('scripts/tests/test_fixture.py', 'raise RuntimeError("unstaged")\n')
        self.assertEqual(0, runner.run(self.root, 'full', staged=True))
        self.assertNotEqual(0, runner.run(self.root, 'full'))

    def test_alternate_index_is_read_and_not_passed_to_tests(self):
        alternate = self.root / '.git/alternate-index'
        alternate.write_bytes((self.root / '.git/index').read_bytes())
        self.write('scripts/tests/test_fixture.py', 'raise RuntimeError("different index")\n')
        self.git('add', 'scripts/tests/test_fixture.py')
        with patch.dict(os.environ, {'GIT_INDEX_FILE': str(alternate)}):
            self.assertEqual(0, runner.run(self.root, 'full', staged=True))
        self.assertNotEqual(0, runner.run(self.root, 'full', staged=True))

    def test_execution_error_records_failure_without_receipt(self):
        actual = runner.subprocess.run

        def fail(*args, **kwargs):
            if args[0][0] == sys.executable:
                raise subprocess.TimeoutExpired(args[0], 900)
            return actual(*args, **kwargs)

        with patch.object(runner.subprocess, 'run', side_effect=fail):
            self.assertNotEqual(0, runner.run(self.root, 'full'))
        self.assertEqual(1, len(self.results()))
        self.assertFalse(self.results()[0]['reused'])
        self.assertFalse(list(self.output.rglob('receipts/*.json')))

    def test_preflight_timeout_records_result_and_does_not_run_tests(self):
        actual = runner.subprocess.run
        launched = []
        def timeout(argv, **kwargs):
            launched.append(argv)
            if '--check' in argv:
                raise subprocess.TimeoutExpired(argv, 60)
            return actual(argv, **kwargs)
        with patch.object(runner.subprocess, 'run', side_effect=timeout):
            self.assertNotEqual(0, runner.run(self.root, 'full'))
        result = self.results()[0]
        self.assertEqual(result['failureKind'], 'timeout')
        self.assertEqual(result['preflightSpec']['timeoutSeconds'], 60)
        self.assertEqual(result['timings'], [])
        self.assertFalse(any('-S' in argv for argv in launched))

    def test_missing_tool_at_stability_check_keeps_failed_result(self):
        actual = runner.execution_spec
        calls = 0
        def disappearing(*args):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise FileNotFoundError('tool removed during checks')
            return actual(*args)
        with patch.object(runner, 'execution_spec', side_effect=disappearing):
            self.assertNotEqual(0, runner.run(self.root, 'full'))
        result = self.results()[0]
        self.assertFalse(result['stable'])
        self.assertEqual(result['failureKind'], 'inputs_changed')
        self.assertFalse(list(self.output.rglob('receipts/*.json')))

    def test_explain_does_not_execute_or_create_results(self):
        self.assertEqual(0, runner.run(self.root, 'full', explain=True))
        self.assertFalse(any(self.output.rglob('*')))

    def test_normal_python_runner_import_does_not_write_source_bytecode(self):
        source_cache = SOURCE / 'scripts' / '__pycache__'
        before = {path for path in source_cache.glob('project_hub_check*.pyc')} if source_cache.exists() else set()
        env = dict(os.environ)
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        result = subprocess.run([sys.executable, str(SOURCE / 'scripts/project_hub_check.py'), '--help'],
                                cwd=SOURCE, env=env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        after = {path for path in source_cache.glob('project_hub_check*.pyc')} if source_cache.exists() else set()
        self.assertEqual(before, after)

    def test_lock_conflicts_and_releases_on_process_exit(self):
        lock = self.root / 'shared.lock'
        code = '''import importlib.util, pathlib, sys
s=importlib.util.spec_from_file_location('runner', sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
try:
 with m.receipt_lock(pathlib.Path(sys.argv[2]), timeout=0.15): pass
except TimeoutError: sys.exit(23)
'''
        with runner.receipt_lock(lock):
            result = subprocess.run([sys.executable, '-c', code, runner.__file__, str(lock)])
            self.assertEqual(23, result.returncode)
        result = subprocess.run([sys.executable, '-c', code, runner.__file__, str(lock)])
        self.assertEqual(0, result.returncode)

    def test_source_mutation_during_run_prevents_receipt(self):
        actual = runner.subprocess.run

        def change(*args, **kwargs):
            if args[0][0] == sys.executable:
                self.write('concurrent.txt', 'modified during checks')
            return actual(*args, **kwargs)

        with patch.object(runner.subprocess, 'run', side_effect=change):
            self.assertNotEqual(0, runner.run(self.root, 'full'))
        self.assertFalse(list(self.output.rglob('receipts/*.json')))


if __name__ == '__main__':
    unittest.main()
