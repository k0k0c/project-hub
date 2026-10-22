"""Source checkout, installed assets and writable state have independent roots."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import Store, PortalServer


class StoragePathsTest(unittest.TestCase):
    def test_state_and_assets_do_not_require_hub_code_in_project(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, data, install = base / 'project', base / 'data', base / 'install'
            root.mkdir(); data.mkdir()
            assets = install / 'tools/project-portal/web'
            assets.mkdir(parents=True)
            (assets / 'index.html').write_text('<html>Independent</html>')
            (data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id='p', name='P', tasks=[])))
            store = Store(root, data_dir=data, installation_root=install, coordination_home=base/'coordination')
            store.record(dict(kind='task.created', taskId='task', title='Create', patch=dict(title='Task',status='planned',stages=[])))
            self.assertEqual(store.snapshot()['tasks'][0]['id'], 'task')
            self.assertFalse((root / 'docs').exists())
            self.assertTrue((data / 'events.jsonl').exists())
            server = PortalServer(('127.0.0.1',0),store)
            worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            try:
                connection = http.client.HTTPConnection('127.0.0.1',server.server_port)
                connection.request('GET','/')
                response = connection.getresponse()
                self.assertEqual(response.status,200)
                self.assertIn(b'Independent',response.read())
                connection.close()
            finally:
                server.shutdown(); server.server_close(); worker.join()
