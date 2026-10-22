"""Finite native-hook notice delivery, isolated state and fake HTTP clients."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

PLUGIN_SCRIPTS = Path(__file__).resolve().parents[2] / "tools" / "project-portal" / "plugins" / "project-hub" / "scripts"
sys.path.insert(0, str(PLUGIN_SCRIPTS))
import hub_watch
from hub_core import HubError


class FakeClients:
    def __init__(self, results=None, error=None, entered=None, release=None):
        self.results = list(results or [{"notices": [], "cursor": 0}])
        self.error = error
        self.entered = entered
        self.release = release
        self.created = []
        self.calls = []

    def __call__(self, url, timeout):
        self.created.append({"url": url, "timeout": timeout})
        factory = self
        class Client:
            def call(self, cwd, session, tool, arguments):
                factory.calls.append({"cwd": cwd, "session": session, "tool": tool,
                                      "arguments": dict(arguments)})
                if factory.entered:
                    factory.entered.set()
                if factory.release and not factory.release.wait(2):
                    raise AssertionError("Fake client was not released")
                if factory.error:
                    raise factory.error
                return factory.results.pop(0)
        return Client()


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = {"url": "http://127.0.0.1:8769", "instructionsDataHome": str(self.home / "owned-data")}
        self.raw = {"session_id": "native-root", "cwd": str(self.home),
                    "hook_event_name": "UserPromptSubmit", "prompt": "PRIVATE-PROMPT",
                    "transcript_path": "PRIVATE-TRANSCRIPT", "tool_input": "PRIVATE-INPUT"}

    def path(self, actor="native-root"):
        key = hashlib.sha256(actor.encode()).hexdigest()
        return Path(self.config["instructionsDataHome"]) / "notice-delivery" / (key + ".json")

    def run_watch(self, client, *, raw=None, config=None, emitter=None):
        output = []
        hub_watch.run(self.raw if raw is None else raw, self.config if config is None else config,
                      emitter or output.append, client_factory=client)
        return output

    def seed(self, value, actor="native-root"):
        path = self.path(actor)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_one_finite_notice_request_emits_only_native_additional_context_facts(self):
        result = {"cursor": 7, "notices": [{"kind": "work.completed", "task": "task-1",
                    "actor": "native-other", "summary": "Independent check completed"}]}
        client = FakeClients([result])
        output = self.run_watch(client)
        self.assertEqual(client.created, [{"url": self.config["url"], "timeout": 48}])
        self.assertEqual(client.calls, [{"cwd": str(self.home), "session": "native-root",
                                        "tool": "hub_notice", "arguments": {"after": 0, "seconds": 45}}])
        self.assertEqual(len(output), 1)
        self.assertEqual(set(output[0]), {"hookSpecificOutput"})
        specific = output[0]["hookSpecificOutput"]
        self.assertEqual(set(specific), {"hookEventName", "additionalContext"})
        self.assertEqual(specific["hookEventName"], "UserPromptSubmit")
        prefix, encoded = specific["additionalContext"].split("\n", 1)
        self.assertIn("advisory facts", prefix)
        self.assertEqual(json.loads(encoded), result)
        serialized = json.dumps(client.calls) + json.dumps(output)
        for marker in ("PRIVATE-PROMPT", "PRIVATE-TRANSCRIPT", "PRIVATE-INPUT"):
            self.assertNotIn(marker, serialized)
        self.assertEqual(json.loads(self.path().read_text()), {"cursor": 7})

    def test_cursor_saved_after_emit_and_reused_on_later_invocation(self):
        self.seed({"cursor": 3})
        client = FakeClients([{"notices": [{"kind": "stage.done"}], "cursor": 8},
                              {"notices": [], "cursor": 10}])
        observed = []
        def emitter(value):
            observed.append((value, json.loads(self.path().read_text())["cursor"]))
        self.run_watch(client, emitter=emitter)
        self.assertEqual(observed[0][1], 3)
        self.assertEqual(json.loads(self.path().read_text())["cursor"], 8)
        self.assertEqual(self.run_watch(client), [{}])
        self.assertEqual([call["arguments"]["after"] for call in client.calls], [3, 8])
        self.assertEqual(json.loads(self.path().read_text())["cursor"], 10)

    def test_emit_failure_preserves_cursor_and_does_not_raise_or_emit_twice(self):
        self.seed({"cursor": 4})
        client = FakeClients([{"notices": [{"kind": "work.completed"}], "cursor": 9}])
        emissions = []
        def broken(value):
            emissions.append(value)
            raise OSError("Native output sink unavailable")
        self.run_watch(client, emitter=broken)
        self.assertEqual(len(emissions), 1)
        self.assertEqual(json.loads(self.path().read_text())["cursor"], 4)

    def test_cursor_persist_failure_does_not_duplicate_successful_emission(self):
        self.seed({"cursor": 4})
        client = FakeClients([{"notices": [{"kind": "work.completed"}], "cursor": 9}])
        with patch.object(hub_watch, "_atomic", side_effect=OSError("Read-only state")):
            output = self.run_watch(client)
        self.assertEqual(len(output), 1)
        self.assertIn("hookSpecificOutput", output[0])
        self.assertEqual(json.loads(self.path().read_text())["cursor"], 4)

    def test_offline_and_client_errors_fail_open_without_model_or_chat_calls(self):
        for error in (OSError("offline"), ValueError("malformed response"),
                      HubError("server_unavailable", "offline")):
            with self.subTest(error=type(error).__name__):
                client = FakeClients(error=error)
                self.assertEqual(self.run_watch(client), [{}])
                self.assertEqual([call["tool"] for call in client.calls], ["hub_notice"])
                self.assertFalse(self.path().exists())

    def test_missing_configuration_or_unrelated_event_never_calls_server(self):
        cases = [({}, self.raw), ({"url": self.config["url"]}, self.raw),
                 (self.config, {**self.raw, "hook_event_name": "PreToolUse"}),
                 (self.config, {}), (self.config, []), (None, self.raw), ([], self.raw)]
        for config, raw in cases:
            with self.subTest(config=config, raw=raw):
                client = FakeClients()
                output = []
                hub_watch.run(raw, config, output.append, client_factory=client)
                self.assertEqual(output, [{}])
                self.assertEqual(client.calls, [])

    def test_malformed_metadata_fails_open_without_contacting_server(self):
        cases = [{**self.raw, "session_id": None}, {**self.raw, "session_id": "x" * 151},
                 {**self.raw, "cwd": "relative"}, {**self.raw, "cwd": None},
                 {**self.raw, "agent_id": []}, {**self.raw, "agent_id": ""},
                 {"hook_event_name": "UserPromptSubmit", "agent_id": "native-child", "cwd": str(self.home)}]
        for raw in cases:
            with self.subTest(raw=raw):
                client = FakeClients()
                self.assertEqual(self.run_watch(client, raw=raw), [{}])
                self.assertEqual(client.calls, [])

    def test_malformed_state_and_result_fail_open_without_cursor_advance(self):
        for state in ([], None, {"cursor": True}, {"cursor": -1}, {"cursor": "3"}):
            with self.subTest(state=state):
                self.seed(state)
                before = self.path().read_bytes()
                client = FakeClients()
                self.assertEqual(self.run_watch(client), [{}])
                self.assertEqual(client.calls, [])
                self.assertEqual(self.path().read_bytes(), before)
        self.path().unlink()
        for result in ([], None, "invalid"):
            with self.subTest(result=result):
                client = FakeClients([result])
                self.assertEqual(self.run_watch(client), [{}])
                self.assertFalse(self.path().exists())

    def test_invalid_json_state_and_unwritable_directory_or_lock_fail_open(self):
        self.seed({})
        self.path().write_text("{invalid", encoding="utf-8")
        client = FakeClients()
        self.assertEqual(self.run_watch(client), [{}])
        self.assertEqual(client.calls, [])
        self.path().unlink()
        for failure in ("directory", "lock"):
            with self.subTest(failure=failure):
                client = FakeClients()
                if failure == "directory":
                    with patch.object(hub_watch.Path, "mkdir", side_effect=OSError("Data home unavailable")):
                        output = self.run_watch(client)
                else:
                    original = hub_watch.Path.open
                    def opening(path, *args, **kwargs):
                        if path.suffix == ".lock":
                            raise OSError("Lock unavailable")
                        return original(path, *args, **kwargs)
                    with patch.object(hub_watch.Path, "open", opening):
                        output = self.run_watch(client)
                self.assertEqual(output, [{}])
                self.assertEqual(client.calls, [])

    def test_same_session_concurrent_watcher_is_nonblocking_and_deduplicated(self):
        entered, release = threading.Event(), threading.Event()
        client = FakeClients([{"notices": [], "cursor": 2}], entered=entered, release=release)
        first_output, second_output, errors = [], [], []
        def invoke(output):
            try:
                hub_watch.run(self.raw, self.config, output.append, client_factory=client)
            except Exception as error:
                errors.append(error)
        first = threading.Thread(target=invoke, args=(first_output,), daemon=True)
        second = threading.Thread(target=invoke, args=(second_output,), daemon=True)
        first.start()
        try:
            self.assertTrue(entered.wait(1), "First watcher never reached fake notice wait")
            second.start()
            second.join(.5)
            self.assertFalse(second.is_alive(), "Second watcher blocked on the active session lock")
            self.assertEqual(second_output, [{}])
            self.assertEqual(len(client.calls), 1)
        finally:
            release.set()
            first.join(2)
            if second.ident is not None:
                second.join(2)
        self.assertEqual(errors, [])
        self.assertFalse(first.is_alive())
        self.assertEqual(first_output, [{}])
        self.assertEqual(json.loads(self.path().read_text()), {"cursor": 2})

    def test_native_subagent_uses_own_cursor_and_actor_not_parents(self):
        for metadata in ({"agent_id": "native-child"}, {"identity": {"agent_id": "native-child"}}):
            with self.subTest(metadata=metadata):
                self.seed({"cursor": 41})
                child_path = self.path("native-child")
                if child_path.exists():
                    child_path.unlink()
                client = FakeClients([{"notices": [], "cursor": 2}, {"notices": [], "cursor": 42}])
                self.assertEqual(self.run_watch(client, raw={**self.raw, **metadata}), [{}])
                self.assertEqual(client.calls[0]["session"], "native-child")
                self.assertEqual(client.calls[0]["arguments"]["after"], 0)
                self.assertEqual(json.loads(child_path.read_text()), {"cursor": 2})
                self.assertEqual(json.loads(self.path().read_text()), {"cursor": 41})
                self.run_watch(client)
                self.assertEqual(client.calls[1]["session"], "native-root")
                self.assertEqual(client.calls[1]["arguments"]["after"], 41)


if __name__ == "__main__":
    unittest.main()
