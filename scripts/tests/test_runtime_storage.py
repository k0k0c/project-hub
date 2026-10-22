"""A source/bundle launch leaves its own tree immutable."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_project_hub_distribution import build
from project_portal import Store
from project_registry import ProjectRegistry, CodexProjects


class RuntimeStorageTest(unittest.TestCase):
    def test_common_launcher_resolves_external_configuration_without_writes(self):
        from hub_launcher import external_path, LauncherError
        source = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'external data'
            self.assertEqual(external_path(data, application_home=source), data.resolve())
            self.assertFalse(data.exists())
            with self.assertRaises(LauncherError):
                external_path(source / 'data', application_home=source)

    def test_default_server_launch_has_empty_external_data_and_immutable_program(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            archive = base / 'runtime.zip'
            build(archive)
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(base / 'program')
            app = next((base / 'program').iterdir())
            catalog = base / 'empty-catalog.json'
            catalog.write_text(json.dumps({'local-projects': {}}))
            data = base / 'user data'
            before = {p.relative_to(app): hashlib.sha256(p.read_bytes()).hexdigest() for p in app.rglob('*') if p.is_file()}
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1', 0))
                port = reserve.getsockname()[1]
            env = dict(os.environ, PROJECT_HUB_HOME=str(data), PROJECT_HUB_ASGI_CATALOG=str(catalog),
                       CODEX_HOME=str(base / 'empty-profile'))
            process = subprocess.Popen([sys.executable, '-B', str(app / 'scripts/project_portal.py'),
                'serve', '--transport', 'threaded', '--port', str(port)], cwd=app,
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 12
                while True:
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/api/v1/projects', timeout=1) as response:
                            result = json.load(response)
                        break
                    except OSError:
                        if process.poll() is not None:
                            self.fail(process.communicate()[1].decode(errors='replace'))
                        if time.monotonic() > deadline:
                            self.fail('Server did not become ready')
                        time.sleep(.05)
                self.assertEqual([], result['projects'])
                with urlopen(f'http://127.0.0.1:{port}/api/health') as response:
                    self.assertEqual(str(data.resolve()), json.load(response)['dataHome'])
                with urlopen(f'http://127.0.0.1:{port}/api/v1/backups') as response:
                    self.assertEqual([], json.load(response)['backups'])
            finally:
                process.terminate()
                process.communicate(timeout=10)
            after = {p.relative_to(app): hashlib.sha256(p.read_bytes()).hexdigest() for p in app.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertTrue((data / 'registry.sqlite3').is_file())
            self.assertTrue((base / 'user data-backups').is_dir())

    def test_overlapping_state_and_coordination_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'program'
            root.mkdir()
            with self.assertRaises(ValueError):
                Store(root, data_dir=root / 'data', installation_root=root)
            with self.assertRaises(ValueError):
                Store(root, data_dir=Path(temp) / 'external', installation_root=root, coordination_home=root / 'coordination')
            self.assertEqual([], list(root.iterdir()))
        source = Path(__file__).resolve().parents[2]
        with self.assertRaises(ValueError):
            ProjectRegistry(source / 'must-not-create-data', CodexProjects(source / 'absent-catalog.json'))
        self.assertFalse((source / 'must-not-create-data').exists())
