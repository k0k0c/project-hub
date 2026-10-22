"""Contract tests for durable history, local HTTP/SSE and real check results."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import Store, PortalServer, main


class PortalTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "docs/project-portal"
        self.data.mkdir(parents=True)
        self.seed = {"schemaVersion": 1, "id": "fixture", "name": "Fixture", "baselineAt": "2026-01-02T03:04:05Z", "tasks": [
            {"id": "task", "title": "Existing task", "status": "active", "stages": [
                {"id": "stage", "title": "First stage", "status": "active", "done": [], "remaining": ["Implement"]}
            ], "sources": [{"label": "Evidence", "path": "proof.txt"}]}]}
        (self.data / "project.json").write_text(json.dumps(self.seed), encoding="utf-8")
        (self.root / "proof.txt").write_text("verified", encoding="utf-8")
        self.store = Store(self.root)
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.temporary.cleanup()

    def event(self, **values):
        return {"taskId": "task", "kind": "note", "title": "Progress", **values}

    def start_server(self):
        self.server = PortalServer(("127.0.0.1", 0), self.store)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def test_seed_is_baseline_not_invented_event_history(self):
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["revision"], 0)
        self.assertEqual(snapshot["events"], [])
        self.assertEqual(snapshot["tasks"][0]["title"], "Existing task")
        self.assertEqual(snapshot["tasks"][0]["createdAt"], self.seed["baselineAt"])
        self.assertEqual(snapshot["tasks"][0]["updatedAt"], self.seed["baselineAt"])

    def test_task_dates_and_reopen_event_survive_new_store(self):
        self.store.record(self.event(kind="task.updated",
                                     patch={"status": "done", "closedManually": True,
                                            "closeReason": "Verified"}))
        self.store.record(self.event(kind="task.updated", patch={"status": "active"}))
        task = Store(self.root).snapshot()["tasks"][0]
        self.assertEqual(task["createdAt"], self.seed["baselineAt"])
        self.assertNotEqual(task["updatedAt"], self.seed["baselineAt"])
        self.assertEqual(task["status"], "active")
        self.assertNotIn("closedManually", task)
        self.assertNotIn("closeReason", task)

    def test_task_changes_are_materialized_as_explicit_history_events(self):
        self.store.record(self.event(taskId="epic", kind="task.created",
                                     patch={"title": "Parent", "status": "active", "type": "epic", "stages": []}))
        self.store.record(self.event(kind="task.updated", patch={"status": "done"}))
        self.store.record(self.event(kind="task.updated", patch={"status": "active"}))
        self.store.record(self.event(kind="task.updated", patch={"type": "bug", "priority": "critical",
                                                                  "parentTask": "epic", "links": [{"type": "related", "target": "epic"}]}))
        self.store.record(self.event(kind="task.updated", patch={"links": []}))

        events = self.store.history(task_id="task")["events"]
        kinds = [event["kind"] for event in events]
        self.assertIn("task.status_changed", kinds)
        self.assertIn("task.reopened", kinds)
        self.assertIn("task.type_changed", kinds)
        self.assertIn("task.priority_changed", kinds)
        self.assertIn("task.parent_changed", kinds)
        self.assertIn("task.linked", kinds)
        self.assertIn("task.unlinked", kinds)
        self.assertNotIn("task.updated", kinds)
        reopened = next(event for event in events if event["kind"] == "task.reopened")
        self.assertEqual(reopened["change"]["from"], "done")
        self.assertIn("Завершено", reopened["detail"])

    def test_work_lifecycle_is_kept_for_projection_but_hidden_from_history(self):
        self.store.record(self.event(kind="work.started", stageId="stage", title="Agent started"))
        self.store.record(self.event(kind="work.completed", title="Agent stopped"))
        self.store.record(self.event(kind="note", title="Visible note"))
        kinds = [event["kind"] for event in self.store.history(task_id="task")["events"]]
        self.assertEqual(kinds, ["note"])
        self.assertEqual(self.store.snapshot()["tasks"][0]["stages"][0]["status"], "active")

    def test_append_stage_preserves_existing_plan_and_retries(self):
        self.store.record(self.event(kind='task.created',taskId='dynamic',patch={'title':'Dynamic','status':'active','stages':[]}))
        before = self.store.journal.read_text(encoding='utf-8').splitlines()[0]
        self.store.record(self.event(kind='stage.created',taskId='dynamic',stageId='new',patch={'title':'New','status':'done'}))
        self.assertEqual(self.store.journal.read_text(encoding='utf-8').splitlines()[0], before)
        event = self.event(id='add-viewer', kind='stage.created', stageId='viewer', patch={'title':'Viewer','status':'done','done':['Verified'],'evidence':[{'path':'proof.txt'}]})
        self.store.record(event)
        self.store.record(event)
        stages = Store(self.root).snapshot()['tasks'][0]['stages']
        self.assertEqual([s['id'] for s in stages], ['stage','viewer'])
        self.assertEqual(stages[0]['remaining'], ['Implement'])
        self.assertEqual(stages[1]['done'], ['Verified'])
        with self.assertRaises(ValueError):
            self.store.record({**event, 'id':'duplicate'})
        with self.assertRaises(ValueError):
            self.store.record(self.event(kind='stage.created',stageId='bad',patch={'title':'Bad','status':'done','evidence':[{'path':'../outside'}]}))

    def test_task_and_stage_changes_survive_new_store(self):
        self.store.record(self.event(kind="work.started", stageId="stage", title="Testing"))
        self.store.record(self.event(kind="stage.updated", stageId="stage", patch={"status": "done", "done": ["Implemented"], "remaining": []}))
        self.store.record(self.event(kind="work.completed"))
        self.store.record(self.event(kind="task.updated", patch={"status": "done"}))
        restored = Store(self.root).snapshot()
        self.assertEqual(restored["revision"], 5)
        task = restored["tasks"][0]
        self.assertEqual(task["status"], "done")
        self.assertEqual(task["stages"][0]["done"], ["Implemented"])
        self.assertNotIn("currentWork", task)

    def test_stage_commit_is_backfilled_into_task_and_project_history(self):
        commit = {"status": "committed", "sha": "a" * 40, "shortSha": "a" * 10,
                  "message": "Implement stage", "files": ["feature.py"]}
        self.store.record(self.event(kind="stage.updated", stageId="stage", patch={"gitCommit": commit}))

        state = self.store.snapshot()
        self.assertEqual(state["revision"], 2)
        self.assertEqual([event["kind"] for event in state["events"]], ["git.commit", "stage.updated"])
        self.assertEqual(state["events"][0]["taskId"], "task")
        self.assertEqual(state["events"][0]["stageId"], "stage")
        self.assertEqual(self.store.history(task_id="task", kind="git")["events"][0]["git"]["sha"], "a" * 40)
        self.assertEqual(len(self.store.history(kind="git")["events"]), 1)

    @patch("project_portal.git_history")
    def test_trailered_local_commit_is_published_to_history(self, git_history):
        git_history.return_value = [{"sha": "b" * 40, "shortSha": "b" * 10,
                                     "message": "Trailer commit", "files": ["feature.py"],
                                     "fileCount": 1, "taskId": "task", "stageId": "stage",
                                     "pushed": False}]

        state = self.store.snapshot()
        self.assertEqual([event["kind"] for event in state["events"]], ["git.commit"])
        self.assertEqual(state["events"][0]["git"]["pushed"], False)
        self.assertEqual(self.store.history(kind="git")["events"][0]["stageId"], "stage")

    def test_idempotent_retry_and_conflict_leave_one_event(self):
        payload = self.event(id="stable-id")
        first = self.store.record(payload)
        self.assertEqual(first, Store(self.root).record(payload))
        with self.assertRaisesRegex(ValueError, "different content"):
            self.store.record({**payload, "title": "Other"})
        self.assertEqual(self.store.snapshot()["revision"], 1)

    def test_validation_does_not_modify_existing_journal(self):
        self.store.record(self.event())
        original = self.store.journal.read_bytes()
        invalid = [self.event(kind="unknown"), self.event(taskId="missing"),
                   self.event(kind="stage.updated", stageId="missing", patch={"status": "done"}),
                   self.event(kind="task.updated", patch={"id": "replacement"}),
                   self.event(kind="task.updated", patch={"status": "imaginary"}),
                   self.event(patch={"status": "done"}), self.event(at="2000-01-01")]
        for payload in invalid:
            with self.assertRaises(ValueError):
                self.store.record(payload)
            self.assertEqual(original, self.store.journal.read_bytes())

    def test_invalid_task_shape_and_dependency_cycle_never_commit(self):
        self.store.record(self.event())
        original = self.store.journal.read_bytes()
        invalid = [self.event(kind="task.updated", patch={"estimate": {"percentLow": 80, "percentHigh": 60}}),
                   self.event(kind="stage.updated", stageId="stage", patch={"done": "wrong shape"}),
                   self.event(kind="stage.updated", stageId="stage", patch={"dependsOn": ["stage"]}),
                   self.event(kind="stage.updated", stageId="stage", patch={"dependsOn": ["missing"]})]
        for payload in invalid:
            with self.assertRaises(ValueError):
                self.store.record(payload)
            self.assertEqual(self.store.journal.read_bytes(), original)

    def test_concurrent_independent_store_writers_preserve_every_event(self):
        def write(i):
            return Store(self.root).record(self.event(id=str(i), title=f"Event {i}"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as workers:
            list(workers.map(write, range(48)))
        history = self.store.history(limit=100)["events"]
        self.assertEqual(len(history), 48)
        self.assertEqual(len({e["id"] for e in history}), 48)
        self.assertEqual([e["seq"] for e in history], list(range(48, 0, -1)))

    def test_atomic_replace_failure_keeps_old_history(self):
        self.store.record(self.event(id="first"))
        original = self.store.journal.read_bytes()
        with patch("project_portal.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.store.record(self.event(id="second"))
        self.assertEqual(original, self.store.journal.read_bytes())
        self.assertEqual(len(list(self.data.glob("events.jsonl.*"))), 0)

    def test_corrupt_journal_rejected_without_silent_history_loss(self):
        self.store.journal.write_text('{"seq": 1', encoding="utf-8")
        original = self.store.journal.read_bytes()
        with self.assertRaises(ValueError):
            self.store.record(self.event())
        self.assertEqual(original, self.store.journal.read_bytes())

    def test_future_tasks_do_not_overwrite_completed_history(self):
        self.store.record(self.event(kind="task.updated", patch={"status": "done"}))
        self.store.record(self.event(taskId="next", kind="task.created", patch={"title": "Next task", "status": "planned", "stages": []}))
        tasks = self.store.snapshot()["tasks"]
        self.assertEqual([(t["id"], t["status"]) for t in tasks], [("task", "done"), ("next", "planned")])
        self.assertEqual(len(self.store.history(task_id="task")["events"]), 1)

    def test_pagination_and_task_filter_have_no_duplicates_or_gaps(self):
        for i in range(9):
            self.store.record(self.event(title=str(i)))
        first = self.store.history(task_id="task", limit=4)
        second = self.store.history(task_id="task", before=first["next"], limit=4)
        third = self.store.history(task_id="task", before=second["next"], limit=4)
        all_events = first["events"] + second["events"] + third["events"]
        self.assertEqual([e["seq"] for e in all_events], list(range(9, 0, -1)))
        self.assertIsNone(third["next"])
        self.assertEqual(self.store.history(task_id="other")["events"], [])

    def test_log_paging_filters_stack_trace_and_rejects_stale_cursor(self):
        path = self.root / 'proof.txt'
        path.write_text('INFO ready\nERROR failed\n    at Demo.run(Demo.java:1)\n' + 'INFO next\n' * 210, encoding='utf-8')
        errors = self.store.log_page('proof.txt', level='ERROR')
        self.assertEqual([r['line'] for r in errors['rows']], [2, 3])
        first = self.store.log_page('proof.txt')
        self.assertEqual(len(first['rows']), 200)
        second = self.store.log_page('proof.txt', first['next'], first['line'], previous=first['previous'], version=first['version'])
        self.assertEqual(second['rows'][0]['line'], 201)
        self.assertFalse(second['more'])
        self.assertEqual(len(self.store.log_page('proof.txt', search='DEMO')['rows']), 1)
        path.write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'File changed'):
            self.store.log_page('proof.txt', version=first['version'])
        with self.assertRaises(ValueError):
            self.store.log_page('../outside')

    def test_log_preview_bounds_large_files_and_long_lines(self):
        (self.root / 'proof.txt').write_bytes(b'x' * 4_100_000)
        page = self.store.log_page('proof.txt')
        self.assertTrue(page['more'])
        self.assertLessEqual(page['scanned'], 2_065_536)
        self.assertTrue(page['rows'][0]['continued'])
        self.assertLessEqual(len(page['rows'][0]['text']), 65536)

    def test_evidence_only_serves_registered_project_sources(self):
        self.assertEqual(self.store.evidence("proof.txt"), b"verified")
        (self.root / "secret.txt").write_text("private", encoding="utf-8")
        for path in ("secret.txt", "../outside", str(self.root / "proof.txt")):
            with self.assertRaises(ValueError):
                self.store.evidence(path)
        with self.assertRaises(ValueError):
            self.store.record(self.event(evidence=[{"path": "../outside"}]))

    def test_outdated_completion_does_not_clear_new_current_work(self):
        first = self.store.record(self.event(kind="work.started", title="First"))
        self.store.record(self.event(kind="work.started", title="Second"))
        self.store.record(self.event(kind="work.completed", workId=first["id"]))
        self.assertEqual(self.store.snapshot()["tasks"][0]["currentWork"]["title"], "Second")

    def test_http_snapshot_evidence_and_local_host_validation(self):
        self.start_server()
        with urllib.request.urlopen(self.url + "/api/state", timeout=4) as response:
            self.assertEqual(json.load(response)["project"]["id"], "fixture")
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
        with urllib.request.urlopen(self.url + "/api/evidence?path=proof.txt", timeout=4) as response:
            self.assertEqual(response.read(), b"verified")
        request = urllib.request.Request(self.url + "/api/state", headers={"Host": "outside.example"})
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(request, timeout=4)
        self.assertEqual(rejected.exception.code, 403)

    def test_canvas_module_is_served_to_the_architecture_page(self):
        self.start_server()
        with urllib.request.urlopen(self.url + "/", timeout=4) as response:
            bootstrap = response.read()
            self.assertIn(b'src="/asset-loader.js"', bootstrap)
            self.assertNotIn(b'src="/architecture-canvas.js"', bootstrap)
        with urllib.request.urlopen(self.url + "/architecture-canvas.js", timeout=4) as response:
            self.assertEqual(response.headers.get_content_type(), "text/javascript")
            self.assertEqual(response.read(), (self.store.installation_root / "tools/project-portal/web/architecture-canvas.js").read_bytes())
        with urllib.request.urlopen(self.url + "/architecture-routing.js", timeout=4) as response:
            self.assertEqual(response.headers.get_content_type(), "text/javascript")
            self.assertEqual(response.read(), (self.store.installation_root / "tools/project-portal/web/architecture-routing.js").read_bytes())

    def test_sse_observes_external_writer_and_reconnects_at_current_revision(self):
        self.start_server()
        def read_revision(response):
            while True:
                line = response.readline().decode()
                if line.startswith("data: "):
                    return json.loads(line[6:])["revision"]
                if not line:
                    self.fail("SSE ended before an update")
        with urllib.request.urlopen(self.url + "/api/events", timeout=4) as stream:
            self.assertEqual(read_revision(stream), 0)
            Store(self.root).record(self.event())
            self.assertEqual(read_revision(stream), 1)
            Store(self.root).record(self.event(title="Second"))
        # A reconnect fetches the complete current projection, not a best-effort tail.
        request = urllib.request.Request(self.url + "/api/events", headers={"Last-Event-ID": "0"})
        with urllib.request.urlopen(request, timeout=4) as stream:
            self.assertEqual(read_revision(stream), 2)
        self.assertEqual(len(self.store.history()["events"]), 2)

    def test_check_runner_records_actual_success_and_failure(self):
        for expected in (0, 3):
            result = main(["--root", str(self.root), "run", "--task", "task", "--stage", "stage", "--title", "Probe", "--log", f"target/check-{expected}.log", "--", sys.executable, "-c", f"print('result'); raise SystemExit({expected})"])
            self.assertEqual(result, expected)
            events = self.store.history()["events"]
            self.assertEqual(events[0]["kind"], "check.passed" if expected == 0 else "check.failed")
            self.assertEqual(events[0]["runId"], events[1]["runId"])
            self.assertIn(b"result", self.store.evidence(f"target/check-{expected}.log"))

    def test_checks_are_not_lost_when_recent_event_window_moves(self):
        self.store.record(self.event(kind="check.started", runId="pending"))
        self.store.record(self.event(kind="check.started", runId="finished"))
        self.store.record(self.event(kind="check.passed", runId="finished"))
        for i in range(30):
            self.store.record(self.event(title=f"Later note {i}"))
        snapshot = self.store.snapshot()
        self.assertEqual(len(snapshot["events"]), 24)
        self.assertEqual(snapshot["checkCount"], 2)
        self.assertEqual([e["kind"] for e in snapshot["checks"]], ["check.passed", "check.started"])
        self.assertEqual([e["kind"] for e in self.store.history(kind="check", limit=2)["events"]], ["check.passed", "check.started"])

    def test_server_restart_keeps_revision_and_project_state(self):
        self.store.record(self.event(kind="task.updated", patch={"status": "done"}))
        self.start_server()
        self.server.shutdown()
        self.server.server_close()
        self.store = Store(self.root)
        self.start_server()
        with urllib.request.urlopen(self.url + "/api/state", timeout=4) as response:
            data = json.load(response)
        self.assertEqual(data["revision"], 2)
        self.assertEqual(data["tasks"][0]["status"], "done")


if __name__ == "__main__":
    unittest.main()
