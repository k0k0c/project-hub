"""Focused disposable-data checks for installation setup wizard progress."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_bindings import Connections, digest
from project_portal import PortalServer
from project_registry import ProjectRegistry
from setup_wizard import SetupWizardError, change, read


class SetupWizardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = ProjectRegistry(Path(self.temp.name) / "home", standalone=True)
        self.server = PortalServer(("127.0.0.1", 0), registry=self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_read_is_default_and_does_not_create_state(self):
        state_path = self.registry.home / "setup-wizard.json"
        result = read(self.registry)
        self.assertEqual(result["revision"], 0)
        self.assertEqual(result["progress"], {"started": False, "completed": False,
                                               "step": "welcome", "application": "codex"})
        self.assertFalse(state_path.exists())

    def test_concurrent_claim_has_one_winner_and_same_request_replays(self):
        requests = [format(i, "032x") for i in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda request: self._claim(request), requests))
        self.assertEqual(sum(result["claimed"] for result in results), 1)
        winner = next(result for result in results if result["claimed"])
        replay = change(self.registry, {"action": "claim", "expected": 0, "requestId": requests[results.index(winner)]})
        self.assertTrue(replay["claimed"])
        self.assertTrue(replay["progress"]["started"])

    def _claim(self, request_id):
        try:
            return change(self.registry, {"action": "claim", "expected": 0, "requestId": request_id})
        except SetupWizardError as error:
            self.assertEqual(error.code, "revision_conflict")
            return {"claimed": False}

    def test_save_merges_and_rejects_stale_revision_and_secrets(self):
        saved = change(self.registry, {"action": "save", "expected": 0, "requestId": "a" * 32,
                                       "patch": {"step": "api-key", "providerKind": "responses", "model": "gpt-test"}})
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["progress"]["step"], "api-key")
        self.assertFalse(saved["autoEligible"])
        with self.assertRaisesRegex(SetupWizardError, "changed"):
            change(self.registry, {"action": "save", "expected": 0, "requestId": "b" * 32,
                                   "patch": {"completed": True}})
        for patch in ({"apiKey": "secret"}, {"token": "secret"}, {"url": "https://secret.invalid"},
                      {"manualProjectRoot": 123}, {"manualProjectRoot": "x" * 4097}):
            with self.assertRaises(SetupWizardError):
                change(self.registry, {"action": "save", "expected": 1, "requestId": "c" * 32, "patch": patch})

    def test_identifier_selection_can_be_cleared(self):
        saved = change(self.registry, {"action": "save", "expected": 0, "requestId": "2" * 32,
                                       "patch": {"invitationId": "invite-old", "connectionId": "connection-old"}})
        cleared = change(self.registry, {"action": "save", "expected": saved["revision"], "requestId": "3" * 32,
                                         "patch": {"invitationId": "", "connectionId": ""}})
        self.assertEqual(cleared["progress"]["invitationId"], "")
        self.assertEqual(cleared["progress"]["connectionId"], "")
        with self.assertRaises(SetupWizardError):
            change(self.registry, {"action": "save", "expected": cleared["revision"], "requestId": "4" * 32,
                                   "patch": {"projectId": None}})

    def test_corrupt_symlink_and_oversized_state_fail_without_reset(self):
        state_path = self.registry.home / "setup-wizard.json"
        state_path.write_text("{}", encoding="utf-8")
        with self.assertRaises(SetupWizardError):
            read(self.registry)
        state_path.unlink()
        state_path.write_bytes(b"{" + b"x" * (64 * 1024) + b"}")
        with self.assertRaises(SetupWizardError):
            read(self.registry)
        state_path.unlink()
        target = Path(self.temp.name) / "target.json"
        target.write_text("{}", encoding="utf-8")
        try:
            state_path.symlink_to(target)
        except OSError:
            return  # Windows may not grant symlink creation to this process.
        with self.assertRaises(SetupWizardError):
            read(self.registry)

    def test_invitation_projection_only_exposes_safe_binding_and_status(self):
        Connections(self.registry).setup()
        invitation_id = "invite-used"
        with self.registry.connect() as db:
            db.execute("INSERT INTO agent_invitations(id,token_hash,expires,response,revoked) VALUES(?,?,?,?,0)",
                       (invitation_id, digest("private-token"), time.time() + 100, json.dumps({
                           "binding": "connection-safe", "token": "private-token", "apiKey": "private-key"})))
        change(self.registry, {"action": "save", "expected": 0, "requestId": "d" * 32,
                               "patch": {"invitationId": invitation_id}})
        invitation = read(self.registry)["invitation"]
        self.assertEqual(invitation, {"id": invitation_id, "state": "used", "connectionId": "connection-safe"})
        self.assertNotIn("private-token", json.dumps(invitation))
        self.assertNotIn("apiKey", json.dumps(invitation))

    def test_completed_state_resumes_and_http_guards_routes_and_assets(self):
        change(self.registry, {"action": "save", "expected": 0, "requestId": "e" * 32,
                               "patch": {"completed": True, "step": "finish"}})
        self.assertFalse(read(self.registry)["autoEligible"])
        status, body = self.request("/api/setup-wizard")
        self.assertEqual(status, 200)
        self.assertFalse(body["autoEligible"])
        status, body = self.request("/api/v1/setup-wizard", {"action": "save", "expected": 1,
                                                               "requestId": "f" * 32, "patch": {"step": "welcome"}})
        self.assertEqual(status, 200)
        self.assertEqual(body["progress"]["step"], "welcome")
        status, _ = self.request("/api/v1/setup-wizard", {"action": "save", "expected": 2,
                                                            "requestId": "1" * 32, "patch": {"step": "welcome"}},
                                 {"Origin": "https://example.invalid"})
        self.assertEqual(status, 403)
        status, _, raw = self.request_raw("/setup-wizard.js")
        self.assertEqual(status, 200)
        self.assertIn(b"HubSetupWizardUI", raw)
        status, _, raw = self.request_raw("/setup-wizard.css")
        self.assertEqual(status, 200)
        self.assertIn(b"#hub-setup-wizard", raw)

    def request_raw(self, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            data = None if body is None else json.dumps(body)
            connection.request("GET" if body is None else "POST", path, data,
                               {"Content-Type": "application/json", **(headers or {})})
            response = connection.getresponse()
            return response.status, dict(response.headers), response.read()
        finally:
            connection.close()

    def request(self, path, body=None, headers=None):
        status, _, raw = self.request_raw(path, body, headers)
        try:
            return status, json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return status, raw


if __name__ == "__main__":
    unittest.main()
