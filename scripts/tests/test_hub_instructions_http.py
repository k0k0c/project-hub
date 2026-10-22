"""Instructions API edits only its native user skill on disposable storage."""
from pathlib import Path
from test_manual_editing import ManualApiCase
from hub_instructions import Instructions


class InstructionsHttpTest(ManualApiCase):
    def test_get_is_read_only_and_explicit_reset_initializes(self):
        status, first = self.request('/api/v1/instructions')
        self.assertEqual(status, 200, first)
        self.assertFalse(first['initialized'])
        self.assertFalse((self.registry.home / 'instructions').exists())
        status, error = self.request('/api/v1/instructions', {'expected': first['revision'], 'reset': 'all'})
        self.assertEqual(status, 409, error)
        initialized = Instructions(self.registry.home).initialize()
        Path(initialized['path']).unlink()
        status, reset = self.request('/api/v1/instructions', {'expected': 'missing-v1', 'reset': 'all'})
        self.assertEqual(status, 200, reset)
        self.assertTrue(reset['initialized'])
        self.assertTrue(Path(reset['path']).is_relative_to(self.registry.home))

    def test_stale_edit_retained_and_unknown_fields_cannot_select_foreign_path(self):
        first = Instructions(self.registry.home).initialize()
        status, changed = self.request('/api/v1/instructions', {'expected': first['revision'],
            'patch': {'userInstructions': 'Edited user preference'}})
        self.assertEqual(status, 200, changed)
        status, error = self.request('/api/v1/instructions', {'expected': first['revision'],
            'patch': {'userInstructions': 'Lost update'}})
        self.assertEqual(status, 409, error)
        self.assertEqual(error['error'], 'instructions_conflict')
        status, error = self.request('/api/v1/instructions', {'expected': changed['revision'],
            'path': 'AGENTS.md', 'reset': 'all'})
        self.assertNotEqual(status, 200)
        self.assertEqual(Instructions(self.registry.home).read()['body'], 'Edited user preference')
