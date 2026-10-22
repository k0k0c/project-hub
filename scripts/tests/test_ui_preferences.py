"""The interface preference is installation scoped, not translated project content."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry
from project_portal import PortalServer
from ui_preferences import read, update, PreferenceError


class UiPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.registry = ProjectRegistry(Path(self.temp.name)/'home', standalone=True)

    def test_default_read_does_not_write_and_language_is_global(self):
        with patch.dict(os.environ, {'PROJECT_HUB_UI_LANGUAGE':'en'}):
            first = read(self.registry)
        self.assertEqual(first['language'], 'en')
        self.assertFalse((self.registry.home/'ui-preferences.json').exists())
        project = self.registry.create('User content: Русский', [], request_id='a'*32)
        saved = update(self.registry, {'language':'en','expected':first['revision']})
        self.assertEqual(saved['language'], 'en')
        self.assertEqual(self.registry.list()['projects'][0]['name'], 'User content: Русский')
        data = self.registry.home/'projects'/project['id']/'project.json'
        self.assertEqual(json.loads(data.read_text())['name'], 'User content: Русский')

    def test_compare_and_swap_retry_and_corrupt_file_preservation(self):
        first = read(self.registry)
        second = update(self.registry, {'language':'en','expected':first['revision']})
        self.assertEqual(update(self.registry, {'language':'en','expected':first['revision']}), second)
        with self.assertRaises(PreferenceError) as caught:
            update(self.registry, {'language':'ru','expected':first['revision']})
        self.assertEqual(caught.exception.status, 409)
        path = self.registry.home/'ui-preferences.json'; path.write_bytes(b'{broken')
        with self.assertRaises(PreferenceError):
            update(self.registry, {'language':'ru','expected':hashlib.sha256(b'{broken').hexdigest()})
        self.assertEqual(path.read_bytes(), b'{broken')

    def test_http_bootstrap_uses_saved_language_without_project(self):
        update(self.registry, {'language':'en','expected':read(self.registry)['revision']})
        server = PortalServer(('127.0.0.1',0), registry=self.registry)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            connection.request('GET','/'); response=connection.getresponse()
            self.assertEqual(response.status,200)
            self.assertIn(b'<html lang="en" data-hub-locale="en">', response.read())
            connection.request('GET','/api/preferences'); response=connection.getresponse()
            self.assertEqual(json.loads(response.read())['language'],'en')
            connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
