import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import secret_vault


class SecretVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = SimpleNamespace(home=self.root / 'data')
        self.registry.home.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_uses_private_home_and_does_not_write_plaintext(self):
        secret = 'provider-key-without-whitespace'
        secret_vault.save(self.registry, 'provider', secret)

        self.assertEqual(secret_vault.get(self.registry, 'provider'), secret)
        path = self.root / 'private' / 'provider-credentials.json'
        self.assertTrue(path.is_file())
        self.assertNotIn(secret.encode(), path.read_bytes())
        self.assertFalse((self.registry.home / 'provider-credentials.json').exists())

        # On Windows this exercises the real DPAPI protect/unprotect calls;
        # elsewhere it still verifies the vault's file and redaction contract.
        protected = secret_vault._protect(b'round-trip')
        self.assertEqual(secret_vault._protect(protected, decrypt=True), b'round-trip')

    def test_invalid_content_has_fixed_error_without_echoing_secret(self):
        secret = 'DO-NOT-ECHO-THIS-KEY'
        path = self.root / 'private'
        path.mkdir()
        payload = {
            'version': 1,
            'protection': 'windows-dpapi' if secret_vault.os.name == 'nt' else 'private-file',
            'content': base64.b64encode(secret.encode()).decode('ascii'),
        }
        (path / 'provider-credentials.json').write_text(json.dumps(payload), encoding='utf-8')

        with self.assertRaisesRegex(ValueError, '^Private credential storage is invalid$') as caught:
            secret_vault.read(self.registry)
        self.assertNotIn(secret, str(caught.exception))

    def test_missing_key_and_invalid_key_are_redacted(self):
        with self.assertRaisesRegex(ValueError, '^API key is unavailable in this installation$'):
            secret_vault.get(self.registry, 'missing')
        for value in ('', 'contains whitespace', '\nnewline'):
            with self.assertRaisesRegex(ValueError, '^Supply a nonempty API key without whitespace$'):
                secret_vault.save(self.registry, 'provider', value)

    def test_application_tree_and_reparse_paths_are_rejected(self):
        app_data = Path(secret_vault.__file__).resolve().parents[1] / 'vault-test-data'
        unsafe_registry = SimpleNamespace(home=app_data / 'data')
        with patch.object(secret_vault, 'control_directory', return_value=None):
            with self.assertRaises(ValueError):
                secret_vault.private_home(unsafe_registry)

        with patch.object(secret_vault, 'external_path', side_effect=ValueError('reparse point')):
            with self.assertRaisesRegex(ValueError, '^reparse point$'):
                secret_vault.private_home(self.registry)


if __name__ == '__main__':
    unittest.main()
