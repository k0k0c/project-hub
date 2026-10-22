"""Fake stdio children only: no native model generation, credentials or data."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("codex_adapter", Path(__file__).parents[1] / "codex_adapter.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
CodexAdapter = MODULE.CodexAdapter
CodexAdapterError = MODULE.CodexAdapterError


class ExecutableDiscoveryTests(unittest.TestCase):
    def test_desktop_binary_available_without_injected_session_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / 'OpenAI' / 'Codex' / 'bin' / 'version' / 'codex.exe'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'fixture only; never executed')
            with patch.object(MODULE.shutil, 'which', return_value=None), patch.dict(MODULE.os.environ, {'LOCALAPPDATA': temporary}):
                if MODULE.os.name == 'nt':
                    self.assertEqual(CodexAdapter.resolve_executable(), str(executable))
                else:
                    self.assertIsNone(CodexAdapter.resolve_executable())
            with patch.object(MODULE.shutil, 'which', return_value='configured-codex'):
                self.assertEqual(CodexAdapter.resolve_executable(), 'configured-codex')

    def test_missing_executable_has_safe_launch_error_code(self):
        with patch.object(CodexAdapter, 'resolve_executable', return_value=None):
            adapter = CodexAdapter()
            with self.assertRaises(CodexAdapterError) as caught:
                adapter._open()
            self.assertEqual(caught.exception.code, 'codex_not_found')

CHILD = r'''
import json, sys, time
from pathlib import Path
mode, log = sys.argv[1:3]
if "--version" in sys.argv:
    print("codex-cli fake-0.160.0")
    sys.exit(0)
def send(value):
    print(json.dumps(value), flush=True)
cwd = None
turn_count = 0
for line in sys.stdin:
    message = json.loads(line)
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(message) + "\n")
    method = message.get("method")
    if method is None:
        if mode == 'user-input':
            send({'method': 'turn/completed', 'params': {'threadId': 'owned-thread',
                  'turn': {'id': 'owned-turn', 'status': 'completed'}}})
        continue
    if "id" not in message:
        continue
    ident = message["id"]
    params = message.get("params", {})
    if mode == "timeout" and method == "initialize":
        time.sleep(30)
    if mode == "malformed" and method == "initialize":
        print("not json", flush=True)
        break
    if mode == "disconnect" and method == "initialize":
        break
    if method == "initialize":
        result = {"userAgent": "fake"}
    elif method == 'model/list':
        result = {'data': [{'id': 'fixture-model', 'displayName': 'Fixture Model'}], 'nextCursor': None}
    elif method == "thread/start":
        cwd = params["cwd"]
        result = {"thread": {"id": "owned-thread", "cwd": cwd}}
        if mode != 'missing-model':
            result.update(model=params.get('model') or 'configured-native-model', reasoningEffort='high')
    elif method == "skills/list":
        result = {"data": [{"cwd": directory, "skills": [{"name": "fake-skill"}],
                            "errors": []} for directory in params["cwds"]]}
    elif method == "thread/read":
        result = {"thread": {"id": params["threadId"], "cwd": str(Path(log).parent),
                  "status": {"type": "active" if mode == "active" else "notLoaded"}}}
        if mode == "reject-empty-resume" and cwd is not None:
            result["thread"]["status"]["type"] = "idle"
        if mode == "wrong-cwd":
            result["thread"]["cwd"] = str(Path(log).parent.parent)
    elif method == "thread/resume":
        if mode == "reject-empty-resume" and cwd is not None and turn_count == 0:
            send({"id": ident, "error": {"code": -32600, "message": "cannot resume empty created thread"}})
            continue
        result = {"thread": {"id": params["threadId"]}}
    elif method == "turn/start":
        if mode == "rpc-error":
            send({"id": ident, "error": {"code": -32000, "message": "secret diagnostic"}})
            continue
        if mode == "turn-timeout":
            time.sleep(30)
        # Interleaved notifications and server request with colliding id must
        # not become the response to turn/start.
        send({"method": "item/started", "params": {"threadId": "owned-thread"}})
        turn_count += 1
        turn_id = "owned-turn" if turn_count == 1 else "owned-turn-" + str(turn_count)
        if mode == "approval":
            send({"id": ident, "method": "item/commandExecution/requestApproval", "params": {
                 'threadId': 'owned-thread', 'turnId': turn_id}})
        result = {"turn": {"id": turn_id, "status": "inProgress"}}
        if mode == "complete":
            send({"method": "turn/completed", "params": {"threadId": "owned-thread",
                 "turn": {"id": turn_id, "status": "completed"}}})
        if mode == 'user-input':
            send({'id': 'question-1', 'method': 'item/tool/requestUserInput', 'params': {
                'threadId': 'owned-thread', 'turnId': turn_id, 'itemId': 'item-1', 'isBlocking': True,
                'questions': [{'id': 'choice', 'header': 'Plan', 'question': 'Apply the plan?',
                               'options': [{'label': 'Continue', 'description': 'Start implementation'}]}]}})
    else:
        result = {}
    send({"id": ident, "result": result})
    if mode == "no-read-after-initialize" and method == "initialize":
        # Keep the read end open but never consume the next request. A large
        # write must reach its deadline without relying on a response timeout.
        time.sleep(30)
'''


class AdapterTests(unittest.TestCase):
    def test_model_catalog_does_not_start_a_thread_and_explicit_model_is_scoped(self):
        adapter = self.adapter()
        self.assertEqual(adapter.models()['models'][0]['id'], 'fixture-model')
        self.assertEqual([row['method'] for row in self.requests()], ['initialize', 'initialized', 'model/list'])
        created = adapter.create_thread(str(self.root), model='fixture-model')
        self.assertEqual(created['model'], 'fixture-model')
        request = self.requests()[-1]
        self.assertEqual(request['params'], {'cwd': str(self.root.resolve()), 'model': 'fixture-model'})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.child = self.root / "child.py"
        self.child.write_text(CHILD, encoding="utf-8")
        self.log = self.root / "protocol.jsonl"

    def adapter(self, mode="running", **kwargs):
        adapter = CodexAdapter([sys.executable, str(self.child), mode, str(self.log)],
                               timeout=kwargs.pop("timeout", 1), **kwargs)
        self.addCleanup(adapter.close)
        return adapter

    def requests(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_probe_handshake_has_no_thread_or_model_call(self):
        adapter = self.adapter()
        result = adapter.probe()
        self.assertTrue(result["available"])
        self.assertEqual(result["desktopAttachment"], "unverified")
        adapter.close()
        self.assertEqual([m["method"] for m in self.requests()], ["initialize", "initialized"])
        self.assertEqual(adapter._process.returncode, 0)

    def test_create_only_and_start_omit_native_overrides(self):
        adapter = self.adapter()
        created = adapter.create_thread(str(self.root))
        self.assertEqual(created["status"], "created")
        adapter.close()
        self.assertNotIn("turn/start", [m["method"] for m in self.requests()])
        self.log.unlink()
        adapter = self.adapter()
        result = adapter.start(str(self.root), "explicit user prompt")
        self.assertEqual(result["turnId"], "owned-turn")
        self.assertEqual(adapter.wait_turn()["status"], "running")
        adapter.close()
        for request in self.requests():
            self.assertFalse({"model", "sandbox", "approvalPolicy", "permissions"} & request["params"].keys())

    def test_completion_survives_event_drain(self):
        adapter = self.adapter("complete")
        adapter.start(str(self.root), "go")
        adapter.events()
        self.assertEqual(adapter.wait_turn(1)["status"], "completed")

    def test_native_plan_and_default_keep_the_configured_model_and_effort(self):
        adapter = self.adapter('complete')
        adapter.start(str(self.root), 'prepare plan', collaboration_mode='plan')
        self.assertEqual(adapter.wait_turn(1)['status'], 'completed')
        adapter.resume_guard = lambda _: True
        adapter.start(str(self.root), 'execute', 'owned-thread', collaboration_mode='default')
        adapter.close()
        turns = [request['params'] for request in self.requests() if request.get('method') == 'turn/start']
        self.assertEqual([turn['collaborationMode']['mode'] for turn in turns], ['plan', 'default'])
        for turn in turns:
            self.assertEqual(turn['collaborationMode']['settings'], {'model': 'configured-native-model',
                'reasoning_effort': 'high', 'developer_instructions': None})
            self.assertNotIn('approvalPolicy', turn)
            self.assertNotIn('sandbox', turn)

    def test_requested_plan_without_native_configuration_refuses_without_turn(self):
        adapter = self.adapter('missing-model')
        with self.assertRaisesRegex(CodexAdapterError, 'settings unavailable'):
            adapter.start(str(self.root), 'plan', collaboration_mode='plan')
        adapter.close()
        self.assertFalse(any(request.get('method') == 'turn/start' for request in self.requests()))

    def test_native_user_input_is_correlated_and_does_not_answer_approval(self):
        adapter = self.adapter('user-input')
        adapter.start(str(self.root), 'plan', collaboration_mode='plan')
        request = adapter.wait_turn(1)['request']
        with self.assertRaises(ValueError):
            adapter.respond_user_input(request['id'], {'unrelated': ['Continue']})
        adapter.respond_user_input(request['id'], {'choice': ['Continue']})
        self.assertEqual(adapter.wait_turn(1)['status'], 'completed')
        with self.assertRaises(CodexAdapterError):
            adapter.respond_user_input(request['id'], {'choice': ['Continue']})
        adapter.close()
        replies = [row for row in self.requests() if 'method' not in row]
        self.assertEqual(replies, [{'id': 'question-1', 'result': {'answers': {'choice': {'answers': ['Continue']}}}}])
        self.log.unlink()
        approval = self.adapter('approval')
        approval.start(str(self.root), 'go')
        pending = approval.wait_turn(1)['request']
        with self.assertRaises(CodexAdapterError):
            approval.respond_user_input(pending['id'], {'choice': ['Continue']})

    def test_skill_discovery_and_owned_thread_read_do_not_start_turns(self):
        adapter = self.adapter(allowed_threads={"owned-thread": str(self.root)})
        skills = adapter.skills([str(self.root)])
        self.assertEqual(skills["data"][0]["skills"][0]["name"], "fake-skill")
        self.assertEqual(adapter.thread_read("owned-thread")["thread"]["id"], "owned-thread")
        adapter.close()
        methods = [m["method"] for m in self.requests()]
        self.assertEqual(methods, ["initialize", "initialized", "skills/list", "thread/read"])
        discovery = next(m for m in self.requests() if m["method"] == "skills/list")
        self.assertEqual(discovery["params"], {"cwds": [str(self.root.resolve())], "forceReload": True})
        read = next(m for m in self.requests() if m["method"] == "thread/read")
        self.assertFalse(read["params"]["includeTurns"])

    def test_read_only_methods_reject_unknown_thread_and_invalid_directories(self):
        adapter = self.adapter()
        with self.assertRaises(CodexAdapterError):
            adapter.thread_read("unrelated-thread")
        for directories in ([], str(self.root)):
            with self.assertRaises(ValueError):
                adapter.skills(directories)
        with self.assertRaises(FileNotFoundError):
            adapter.skills([str(self.root / "missing")])
        self.assertIsNone(adapter._process)

    def test_server_request_with_colliding_id_needs_attention(self):
        adapter = self.adapter("approval")
        result = adapter.start(str(self.root), "go")
        self.assertEqual(result["status"], "accepted")
        adapter.events()
        self.assertEqual(adapter.wait_turn(1)["status"], "needs-attention")
        adapter.close()
        self.assertTrue(all("method" in m for m in self.requests()))

    def test_arbitrary_and_unguarded_resume_rejected_before_launch(self):
        for kwargs in ({}, {"allowed_threads": {"owned-thread": str(self.root)}}):
            adapter = self.adapter(**kwargs)
            with self.assertRaises(CodexAdapterError):
                adapter.start(str(self.root), "go", "owned-thread")
            self.assertIsNone(adapter._process)

    def test_resume_checks_native_project_and_active_status(self):
        for mode in ("active", "wrong-cwd"):
            adapter = self.adapter(mode, allowed_threads={"owned-thread": str(self.root)},
                                   resume_guard=lambda _: True)
            with self.assertRaises(CodexAdapterError):
                adapter.start(str(self.root), "go", "owned-thread")
            adapter.close()
        methods = [m["method"] for m in self.requests()]
        self.assertNotIn("thread/resume", methods)
        self.assertNotIn("turn/start", methods)

    def test_owned_idle_resume(self):
        adapter = self.adapter(allowed_threads={"owned-thread": str(self.root)},
                               resume_guard=lambda _: True)
        self.assertEqual(adapter.start(str(self.root), "go", "owned-thread")["status"], "accepted")
        adapter.close()
        methods = [m["method"] for m in self.requests()]
        self.assertEqual(methods[-3:], ["thread/read", "thread/resume", "turn/start"])

    def test_two_phase_created_empty_thread_starts_without_native_resume(self):
        adapter = self.adapter("reject-empty-resume", resume_guard=lambda _: True)
        receipt = self.root / "action-receipt.json"
        created = adapter.create_thread(str(self.root))
        receipt.write_text(json.dumps(created), encoding="utf-8")
        owned_id = json.loads(receipt.read_text(encoding="utf-8"))["threadId"]
        accepted = adapter.start(str(self.root), "Explicit two-phase user launch", thread_id=owned_id)
        receipt.write_text(json.dumps({**created, **accepted}), encoding="utf-8")
        self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["status"], "accepted")
        self.assertEqual(accepted["turnId"], "owned-turn")
        self.assertIn(owned_id, adapter._loaded_threads)
        adapter.close()
        self.assertEqual(adapter._loaded_threads, set())
        self.assertEqual([request["method"] for request in self.requests()],
                         ["initialize", "initialized", "thread/start", "thread/read", "turn/start"])

    def test_external_ownership_mapping_still_resumes_before_first_turn(self):
        adapter = self.adapter("reject-empty-resume",
                               allowed_threads={"owned-thread": str(self.root)},
                               resume_guard=lambda _: True)
        self.assertEqual(adapter._loaded_threads, set())
        result = adapter.start(str(self.root), "Explicit stored-thread launch", thread_id="owned-thread")
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(adapter._loaded_threads, {"owned-thread"})
        adapter.close()
        self.assertEqual([request["method"] for request in self.requests()][-3:],
                         ["thread/read", "thread/resume", "turn/start"])

    def test_completed_turn_retains_loading_but_still_requires_idle_guard(self):
        adapter = self.adapter("complete", resume_guard=lambda _: True)
        created = adapter.create_thread(str(self.root))
        adapter.start(str(self.root), "first", thread_id=created["threadId"])
        self.assertEqual(adapter.wait_turn(1)["status"], "completed")
        adapter.resume_guard = lambda _: False
        with self.assertRaises(CodexAdapterError):
            adapter.start(str(self.root), "blocked", thread_id=created["threadId"])
        adapter.resume_guard = lambda _: True
        second = adapter.start(str(self.root), "second", thread_id=created["threadId"])
        self.assertEqual(second["turnId"], "owned-turn-2")
        self.assertEqual(adapter.wait_turn(1)["status"], "completed")
        adapter.close()
        self.assertEqual([request["method"] for request in self.requests()].count("thread/resume"), 0)

    def test_io_abort_clears_runtime_loading_proof(self):
        adapter = self.adapter("turn-timeout", timeout=.15, resume_guard=lambda _: True)
        created = adapter.create_thread(str(self.root))
        self.assertEqual(adapter._loaded_threads, {created["threadId"]})
        with self.assertRaises(CodexAdapterError) as caught:
            adapter.start(str(self.root), "explicit timed-out turn", thread_id=created["threadId"])
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertEqual(adapter._loaded_threads, set())

    def test_native_error_and_unknown_turn_timeout_preserve_thread_id(self):
        for mode in ("rpc-error", "turn-timeout"):
            adapter = self.adapter(mode, timeout=2, resume_guard=lambda _: True)
            # This tests an error after a known thread was created, not how
            # quickly Windows starts the fixture process under a full suite.
            created = adapter.create_thread(str(self.root))
            adapter.timeout = 0.15
            with self.assertRaises(CodexAdapterError) as caught:
                adapter.start(str(self.root), "go", thread_id=created['threadId'])
            self.assertEqual(caught.exception.thread_id, "owned-thread")
            self.assertEqual(caught.exception.outcome_unknown, mode == "turn-timeout")
            self.assertNotIn("secret", str(caught.exception))
            if mode == "turn-timeout":
                with self.assertRaises(CodexAdapterError):
                    adapter.start(str(self.root), "blind retry")
            adapter.close()

    def test_unavailable_and_bounded_initialization_failure(self):
        adapter = CodexAdapter(str(self.root / "missing.exe"))
        self.assertFalse(adapter.probe()["available"])
        for mode in ("timeout", "malformed", "disconnect"):
            adapter = self.adapter(mode, timeout=0.15)
            # This case targets handshake cleanup, independent of the time
            # Windows takes to start a separate --version Python child.
            version = MODULE.subprocess.CompletedProcess([], 0, stdout="codex-cli fixture", stderr="")
            with patch.object(MODULE.subprocess, "run", return_value=version):
                self.assertFalse(adapter.probe()["available"])
            self.assertIsNotNone(adapter._process)
            self.assertIsNotNone(adapter._process.returncode)

    def test_overlapping_start_and_invalid_arguments_rejected(self):
        adapter = self.adapter()
        with self.assertRaises(ValueError):
            adapter.start(str(self.root), " ")
        adapter.start(str(self.root), "go")
        with self.assertRaises(CodexAdapterError):
            adapter.start(str(self.root), "again")
        with self.assertRaises(ValueError):
            adapter.wait_turn(61)

    def test_wedged_pipe_write_and_close_are_bounded_and_unknown(self):
        adapter = self.adapter('no-read-after-initialize', timeout=0.2)
        # Initialize before timing the large send: this mode stops consuming
        # stdin immediately after its successful handshake.
        self.assertTrue(adapter.probe()['available'])
        started = time.monotonic()
        # A daemon watchdog lets a regression fail the assertion instead of
        # wedging the test process inside TextIO.write/close.
        completed = threading.Event()
        outcome = {}

        def request_and_close():
            try:
                adapter._request('turn/start', {'threadId': 'owned-thread',
                    'input': [{'type': 'text', 'text': 'explicit prompt ' * 100000}]})
            except BaseException as error:
                outcome['error'] = error
            finally:
                adapter.close()
                completed.set()

        worker = threading.Thread(target=request_and_close, daemon=True)
        worker.start()
        if not completed.wait(3):
            # Tear down only our fake child before reporting a regression; this
            # unblocks a legacy write so registered cleanup cannot hang, either.
            adapter._process.kill()
            worker.join(timeout=2)
            self.fail('blocked pipe write or close exceeded its bound')
        self.assertLess(time.monotonic() - started, 3)
        error = outcome.get('error')
        self.assertIsInstance(error, CodexAdapterError)
        self.assertTrue(error.outcome_unknown)
        self.assertIn('write timed out', str(error))
        self.assertIsNotNone(adapter._process.poll())
        self.assertFalse(adapter._write_pending)
        self.assertFalse(adapter._writer.is_alive())
        self.assertEqual([request['method'] for request in self.requests()], ['initialize'])
        with self.assertRaises(CodexAdapterError):
            adapter.create_thread(str(self.root))


if __name__ == "__main__":
    unittest.main()
