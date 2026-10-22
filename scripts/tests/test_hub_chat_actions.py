"""Functional action records in temporary registries; all native adapters fake."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import queue
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_adapter import CodexAdapterError
from hub_chat_actions import ChatActionError, ChatActions


class FakeRegistry:
    def __init__(self, root):
        self.home = root / "hub-data"
        self.home.mkdir()
        self.database = self.home / "registry.sqlite3"
        self.roots = {}
        self.snapshots = {}
        with self.connect() as connection:
            connection.execute("CREATE TABLE spaces(id TEXT PRIMARY KEY,roots TEXT,present INTEGER)")
        for project in ("p", "q"):
            directory = root / project
            directory.mkdir()
            self.roots[project] = directory
            task = {"id": "t", "title": "Current task", "scope": "Bounded work",
                    "acceptance": ["Check the outcome"], "sources": ["docs/checkpoint.md"],
                    "checkpointRefs": ["checkpoint-1"], "stages": [
                        {"id": "done", "title": "Accepted stage", "status": "done",
                         "done": ["prior outcome"], "result": "verified"},
                        {"id": "next", "title": "Remaining stage", "status": "planned",
                         "remaining": ["next action"]}]}
            self.snapshots[project] = {"project": {"id": project}, "tasks": [task],
                                       "allEvents": [{"secret": "HISTORY-MUST-NOT-COPY"}]}
            with self.connect() as connection:
                connection.execute("INSERT INTO spaces VALUES(?,?,1)", (project, json.dumps([str(directory)])))

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return closing(connection)

    def base_store(self, project):
        registry = self
        class Store:
            root = registry.roots[project]
            data = registry.roots[project] / 'data'
            def snapshot(self):
                return deepcopy(registry.snapshots[project])
        return Store()


class FakeAdapter:
    def __init__(self, thread_id, mode="running", gate=None):
        self.thread_id = thread_id
        self.mode = mode
        self.gate = gate
        self.calls = []
        self.results = queue.Queue()
        self.closed = False
        self.turn_count = 0
        self.resume_guard = None

    def create_thread(self, cwd, *, model=None):
        self.calls.append(("create", cwd))
        self.model = model
        return {"threadId": self.thread_id, 'model': model or 'native-default'}

    def start(self, cwd, prompt, thread_id=None, **options):
        self.calls.append(("start", cwd, prompt, thread_id))
        self.native_options = options
        if self.gate:
            self.gate.wait(1)
        if self.mode in ("unknown", "failure"):
            raise CodexAdapterError("private native diagnostic", outcome_unknown=self.mode == "unknown",
                                    thread_id=self.thread_id)
        self.turn_count += 1
        return {"threadId": self.thread_id, "turnId": f"turn-{self.turn_count}", "status": "accepted"}

    def wait_turn(self, timeout):
        if not 0 <= timeout <= 30:
            raise AssertionError("unbounded worker wait")
        if self.closed:
            raise CodexAdapterError("closed", outcome_unknown=True)
        try:
            return self.results.get(timeout=.03)
        except queue.Empty:
            return {"status": "running"}

    def events(self):
        return {"events": [], "dropped": 0}

    def close(self):
        self.closed = True


class ChatActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = FakeRegistry(Path(self.temp.name))
        self.adapters = []
        self.mode = "running"
        self.gate = None
        self.env = patch.dict(os.environ, {"PROJECT_HUB_CODEX_ADAPTER": "stdio"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.service = self.make_service()

    def make_service(self):
        def factory():
            adapter = FakeAdapter(f"thread-{len(self.adapters) + 1}", self.mode, self.gate)
            self.adapters.append(adapter)
            return adapter
        service = ChatActions(self.registry, factory)
        self.addCleanup(service.close)
        return service

    def assert_error(self, code, call):
        with self.assertRaises(ChatActionError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def await_status(self, status, service=None):
        service = service or self.service
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = service.recent("p", "t")[0]
            if result["status"] == status:
                return result
            time.sleep(.01)
        self.fail(f"action never reached {status}")

    def test_disabled_capabilities_and_start_never_initialize(self):
        with patch.dict(os.environ, {"PROJECT_HUB_CODEX_ADAPTER": ""}):
            result = self.service.capabilities("p")
            self.assertFalse(result["enabled"])
            self.assertEqual(result["desktopAttachment"], "unverified")
            self.assert_error("adapter_disabled", lambda: self.service.start("p", "t", "a"))
        self.assertEqual(self.adapters, [])
        self.assertEqual(self.service.recent("p", "t"), [])

    def test_running_activity_is_visible_without_native_content(self):
        response = self.service.start('p', 't', 'activity')
        adapter = self.adapters[0]
        with patch.object(adapter, 'events', return_value={'events': [
                {'method': 'item/started', 'params': {'threadId': adapter.thread_id,
                 'turnId': response['turnId'], 'item': {'type': 'commandExecution',
                 'command': 'PRIVATE-COMMAND', 'output': 'PRIVATE-CONTENT'}}}], 'dropped': 0}):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                current = self.service.recent('p', 't')[0]
                if current.get('activity') == 'tools':
                    break
                time.sleep(.01)
            self.assertEqual(current['status'], 'running')
            self.assertEqual(current['activity'], 'tools')
            self.assertNotIn('PRIVATE-', json.dumps(current))
        adapter.results.put({'status': 'completed'})
        self.assertEqual(self.await_status('completed')['activity'], 'completed')

    def test_launch_failure_displays_safe_reason(self):
        def missing():
            raise CodexAdapterError('private diagnostic', code='codex_not_found')
        service = ChatActions(self.registry, missing)
        self.addCleanup(service.close)
        result = service.start('p', 't', 'missing')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error']['code'], 'codex_not_found')
        self.assertIn('PATH', result['error']['message'])
        self.assertNotIn('private', json.dumps(result))

    def test_only_bounded_public_summary_is_exposed_and_not_persisted(self):
        response = self.service.start('p', 't', 'summary')
        adapter = self.adapters[0]
        events = [{'method': 'item/reasoning/summaryTextDelta', 'params': {
            'threadId': adapter.thread_id, 'turnId': response['turnId'],
            'itemId': 'summary-item', 'summaryIndex': 0, 'delta': 'PUBLIC-SUMMARY '*100}},
            {'method': 'item/reasoning/textDelta', 'params': {'delta': 'PRIVATE-RAW'}}]
        with patch.object(adapter, 'events', side_effect=lambda: {'events': events, 'dropped': 0}):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                current = self.service.recent('p', 't')[0]
                if current.get('progressSummary'):
                    break
                time.sleep(.01)
            self.assertLessEqual(len(current['progressSummary']), 480)
            self.assertNotIn('PRIVATE-RAW', json.dumps(current))
            with self.registry.connect() as connection:
                stored = connection.execute("SELECT response FROM codex_chat_actions WHERE action_id='summary'").fetchone()[0]
            self.assertNotIn('PUBLIC-SUMMARY', stored)
            self.assertNotIn('PRIVATE-RAW', stored)
        adapter.results.put({'status': 'completed'})
        self.assertNotIn('progressSummary', self.await_status('completed'))

    def test_invalid_project_task_stage_and_authoritative_root(self):
        for code, args in (("project_not_found", ("missing", "t", "a")),
                           ("task_not_found", ("p", "missing", "a")),
                           ("stage_not_found", ("p", "t", "a", "missing"))):
            self.assert_error(code, lambda args=args: self.service.start(*args))
        with self.registry.connect() as connection:
            connection.execute("UPDATE spaces SET roots=? WHERE id='p'", (json.dumps([str(Path(self.temp.name) / "missing")]),))
        self.assert_error("project_root_unavailable", lambda: self.service.start("p", "t", "a"))
        self.assertEqual(self.adapters, [])

    def test_prompt_uses_current_bounded_projection_and_local_task_url(self):
        task = self.registry.snapshots["p"]["tasks"][0]
        task["scope"] = "S" * 50000
        task["sources"] = ["ref-" + str(i) + "X" * 1000 for i in range(100)]
        task["stages"] *= 100
        response = self.service.start("p", "t", "a")
        self.assertEqual(response["status"], "accepted")
        cwd, prompt = self.adapters[0].calls[-1][1:3]
        self.assertEqual(cwd, str(self.registry.roots["p"].resolve()))
        self.assertLessEqual(len(prompt), 12500)
        self.assertIn("Bind your own verified identity", prompt)
        self.assertIn("http://127.0.0.1:8769/?project=p#tasks/t", prompt)
        self.assertIn("checkpoint-1", prompt)
        self.assertNotIn("HISTORY-MUST-NOT-COPY", prompt)
        context = json.loads(prompt.split("Current task context (JSON):\n", 1)[1])
        self.assertGreater(context["stagesOmitted"], 0)
        self.assertGreater(context["sourcesOmitted"], 0)
        self.assertEqual(self.adapters[0].resume_guard(response["threadId"]), True)

    def test_requested_is_persisted_before_native_mutation(self):
        observed = []
        original_factory = self.service.adapter_factory
        def factory():
            observed.append(self.service.recent("p", "t")[0]["status"])
            return original_factory()
        self.service.adapter_factory = factory
        self.service.start("p", "t", "a")
        self.assertEqual(observed, ["requested"])
        with self.registry.connect() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"spaces", "codex_chat_actions"})

    def test_terminal_failures_retire_runtime_capacity_and_cannot_resume(self):
        for index in range(5):
            response=self.service.start('p','t','failed-'+str(index))
            self.adapters[-1].results.put({'status':'failed'})
            deadline=time.monotonic()+2
            while self.service.recent('p','t')[0]['status']!='failed' and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertEqual(self.service.recent('p','t')[0]['status'],'failed')
            self.assertFalse(self.service.recent('p','t')[0]['resumeAllowed'])
            self.assertNotIn(response['threadId'],self.service._runtimes)
        self.assertEqual(self.service.start('p','t','sixth')['status'],'accepted')

    def test_control_characters_remain_bounded_valid_context(self):
        task=self.registry.snapshots['p']['tasks'][0]
        for key in ('scope','acceptance','title','result','checkpointRefs'):
            task[key]='\x01'*50000
        response=self.service.start('p','t','control-chars')
        prompt=self.adapters[0].calls[-1][2]
        self.assertLessEqual(len(prompt),12500)
        json.loads(prompt.split('Current task context (JSON):\n',1)[1])

    def test_concurrent_double_click_and_exact_replay_submit_once(self):
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: self.service.start("p", "t", "a"), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.adapters), 1)
        self.assertEqual(self.adapters[0].turn_count, 1)
        self.registry.snapshots["p"]["tasks"][0]["title"] = "New current context"
        self.assertEqual(self.service.start("p", "t", "a"), results[0])

    def test_same_action_id_conflicts_for_changed_signature(self):
        self.service.start("p", "t", "a")
        for args in (("p", "t", "a", "next"), ("q", "t", "a")):
            error = self.assert_error("action_id_conflict", lambda args=args: self.service.start(*args))
            self.assertEqual(error.http_status, 409)
        self.assertEqual(len(self.adapters), 1)

    def test_timeout_unknown_and_known_failure_replay_without_retry(self):
        for mode, expected in (("unknown", "outcome_unknown"), ("failure", "failed")):
            self.mode = mode
            response = self.service.start("p", "t", mode)
            self.assertEqual(response["status"], expected)
            self.assertNotIn("private", json.dumps(response))
            self.assertEqual(response, self.service.start("p", "t", mode))
            self.assertTrue(self.adapters[-1].closed)
        self.assertEqual(len(self.adapters), 2)

    def test_completion_allows_same_retained_runtime_resume(self):
        first = self.service.start("p", "t", "a", stage="next")
        self.adapters[0].results.put({"status": "completed"})
        self.await_status("completed")
        second = self.service.start("p", "t", "b", stage="next", thread_id=first["threadId"])
        self.assertEqual(second["threadId"], first["threadId"])
        self.assertEqual(second["turnId"], "turn-2")
        self.assertEqual(len(self.adapters), 1)
        self.assertFalse(self.adapters[0].closed)

    def test_active_cross_project_and_restart_resume_rejected(self):
        first = self.service.start("p", "t", "a")
        identity = first["threadId"]
        self.assert_error("thread_not_idle", lambda: self.service.start("p", "t", "b", thread_id=identity))
        self.assert_error("thread_ownership_mismatch", lambda: self.service.start("q", "t", "b", thread_id=identity))
        restarted = self.make_service()
        self.assert_error("resume_unverified", lambda: restarted.start("p", "t", "b", thread_id=identity))
        self.assertEqual(restarted.start("p", "t", "a"), first)
        self.assertEqual(self.adapters[0].turn_count, 1)

    def test_cross_task_and_arbitrary_original_chat_resume_rejected(self):
        first = self.service.start("p", "t", "a")
        second_task = deepcopy(self.registry.snapshots["p"]["tasks"][0])
        second_task["id"] = "u"
        self.registry.snapshots["p"]["tasks"].append(second_task)
        self.assert_error("thread_ownership_mismatch", lambda: self.service.start("p", "u", "b", thread_id=first["threadId"]))
        self.assert_error("resume_unverified", lambda: self.service.start("p", "t", "b", thread_id="desktop-original"))

    def test_native_approval_needs_attention_without_raw_request_or_auto_approval(self):
        first = self.service.start("p", "t", "a")
        self.adapters[0].results.put({"status": "needs-attention", "request": {"secret": "PRIVATE-APPROVAL"}})
        response = self.await_status("needs_attention")
        self.assertEqual(response["error"]["code"], "native_user_attention")
        self.assertNotIn("PRIVATE-APPROVAL", json.dumps(response))
        self.assert_error("thread_not_idle", lambda: self.service.start("p", "t", "b", thread_id=first["threadId"]))
        self.assertEqual([call[0] for call in self.adapters[0].calls], ["create", "start"])

    def test_separate_service_concurrency_deduplicates_reservation(self):
        other = self.make_service()
        with ThreadPoolExecutor(max_workers=2) as workers:
            pending = [workers.submit(service.start, "p", "t", "a") for service in (self.service, other)]
            results = [future.result(2) for future in pending]
        self.assertEqual({row["actionId"] for row in results}, {"a"})
        self.assertEqual(len(self.adapters), 1)
        self.assertEqual(self.adapters[0].turn_count, 1)

    def test_origin_validation_and_bad_action_input(self):
        with self.assertRaises(ValueError):
            ChatActions(self.registry, portal_url="https://remote.example")
        self.assert_error("invalid_request", lambda: self.service.start("p", "t", "bad action"))
        self.assert_error("invalid_request", lambda: self.service.start("p", "t", "a", stage={}))
        self.assertEqual(self.adapters, [])


if __name__ == "__main__":
    unittest.main()
