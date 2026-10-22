"""Owned native skills, reset/reinstall, concurrency and instruction boundaries."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub/scripts'))
from hub_instructions import Instructions, InstructionsError, HEADER, catalog, default_body


class HubInstructionsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.instructions = Instructions(self.base / 'data')
        self.root = self.base / '.agents/skills/project-hub-user'

    def test_read_missing_is_side_effect_free_and_does_not_inspect_user_profile(self):
        state = self.instructions.read()
        self.assertFalse(state['initialized'])
        self.assertEqual(state['revision'], 'missing-v1')
        self.assertEqual(state['body'], default_body())
        self.assertFalse((self.base / 'data').exists())
        self.assertTrue(Path(state['path']).is_relative_to(self.base))

    def test_initializer_preserves_edit_and_external_file_across_reinstall(self):
        first = self.instructions.initialize(self.root)
        self.assertTrue(first['nativeDiscovery'])
        changed = self.instructions.update(first['revision'], {'userInstructions': '# Local preference\nKeep checks focused.\n'})
        original = (self.root / 'SKILL.md').read_bytes()
        repeated = self.instructions.initialize(self.root)
        self.assertEqual(repeated['revision'], changed['revision'])
        self.assertEqual((self.root / 'SKILL.md').read_bytes(), original)
        self.assertTrue(original.decode().startswith(HEADER))

    def test_reset_and_manual_delete_return_current_packaged_default(self):
        first = self.instructions.initialize(self.root)
        changed = self.instructions.update(first['revision'], {'userInstructions': 'Custom preferences'})
        self.assertEqual(changed['history'][-1]['before'], first['revision'])
        self.assertEqual(changed['history'][-1]['after'], changed['revision'])
        reset = self.instructions.update(changed['revision'], reset='userInstructions')
        self.assertEqual(reset['body'], default_body())
        self.assertEqual(len(reset['history']), 2)
        self.assertEqual(reset['history'][-1]['after'], reset['revision'])
        self.assertEqual(self.instructions.read()['history'], reset['history'])
        (self.root / 'SKILL.md').unlink()
        self.assertEqual(self.instructions.read()['revision'], 'missing-v1')
        restored = self.instructions.initialize(self.root)
        self.assertEqual(restored['body'], default_body())

    def test_new_defaults_preserve_user_text_and_allow_explicit_current_default_reset(self):
        first = self.instructions.initialize(self.root)
        custom = self.instructions.update(first['revision'], {'userInstructions': 'Keep my preferences'})
        with patch('hub_instructions.default_body', return_value='Updated packaged preference'):
            changed_default = self.instructions.initialize(self.root)
            self.assertEqual(changed_default['revision'], custom['revision'])
            self.assertTrue(changed_default['defaultChanged'])
            reset = self.instructions.update(custom['revision'], reset='all')
            self.assertEqual(reset['body'], 'Updated packaged preference')
            self.assertFalse(reset['defaultChanged'])

    def test_two_editors_using_same_revision_cannot_lose_changes(self):
        first = self.instructions.initialize(self.root)
        def edit(number):
            try:
                return self.instructions.update(first['revision'], {'userInstructions': 'Preference ' + str(number)})
            except InstructionsError as error:
                return error.body
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, (1, 2)))
        self.assertEqual(sum('revision' in result for result in results), 1)
        self.assertEqual(sum(result.get('error') == 'instructions_conflict' for result in results), 1)
        self.assertEqual(len(self.instructions.read()['history']), 1)

    def test_foreign_skill_or_changed_owner_is_never_adopted(self):
        self.root.mkdir(parents=True)
        path = self.root / 'SKILL.md'
        path.write_text('Foreign skill')
        with self.assertRaises(InstructionsError):
            self.instructions.initialize(self.root)
        self.assertEqual(path.read_text(), 'Foreign skill')

    def test_only_body_of_owned_skill_is_editable_and_project_files_untouched(self):
        foreign = self.base / 'project/AGENTS.md'
        foreign.parent.mkdir()
        foreign.write_text('Project instructions')
        first = self.instructions.initialize(self.root)
        for value in ({'core': 'overwrite'}, {'userInstructions': ''}, {'userInstructions': 'x' * 24001},
                      {'path': str(foreign), 'userInstructions': 'edit'}, {'userInstructions': 1}):
            with self.subTest(value=tuple(value)), self.assertRaises(InstructionsError):
                self.instructions.update(first['revision'], value)
        self.assertEqual(foreign.read_text(), 'Project instructions')
        self.assertEqual(self.instructions.read()['revision'], first['revision'])

    def test_explicit_reset_initializes_but_get_does_not(self):
        before = self.instructions.read()
        self.assertFalse(before['restoreAllowed'])
        with self.assertRaises(InstructionsError):
            self.instructions.update(before['revision'], {'userInstructions': 'Custom'})
        with self.assertRaises(InstructionsError):
            self.instructions.update(before['revision'], reset='all')
        self.instructions.initialize(self.root)
        (self.root / 'SKILL.md').unlink()
        before = self.instructions.read()
        self.assertTrue(before['restoreAllowed'])
        restored = self.instructions.update(before['revision'], reset='all')
        self.assertTrue(restored['initialized'])
        self.assertEqual(restored['body'], default_body())

    def test_catalog_uses_actual_package_and_all_declared_tools_scripts_hooks(self):
        self.instructions.initialize(self.root)
        value = catalog(self.base / 'data')
        self.assertEqual(value['scope'], 'native-local')
        self.assertIn('hub_begin', {item['name'] for item in value['tools']})
        self.assertIn('hub_instructions.py', {item['name'] for item in value['scripts']})
        self.assertTrue(all(item['observed'] is None for item in value['hooks']))
        self.assertTrue(all('PLUGIN_ROOT' not in item['command'] for item in value['hooks']))
        self.assertFalse(value['rules'][0]['editable'])
        self.assertIn('Hub не передаёт', value['delivery']['description'])

    def test_redirection_and_broken_metadata_do_not_overwrite_files(self):
        self.instructions.initialize(self.root)
        before = (self.root / 'SKILL.md').read_bytes()
        (self.root / '.project-hub-owned.json').write_text(json.dumps({'kind': 'foreign'}))
        with self.assertRaises(InstructionsError):
            self.instructions.update('anything', reset='all')
        self.assertEqual((self.root / 'SKILL.md').read_bytes(), before)
