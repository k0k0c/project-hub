"""Regression coverage for chat history projection and task scoping."""
import json
from contextlib import closing, contextmanager
import http.client
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools/project-portal/plugins/project-hub/scripts"))
from project_portal import Store
from hub_core import Hub
from task_chats import chat_history
from codex_session_catalog import SessionCatalog

PARENT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"
EXPLICIT = "33333333-3333-4333-8333-333333333333"
ARCHIVED = "44444444-4444-4444-8444-444444444444"


@contextmanager
def fixture(tasks=None, sessions=None, catalog=None):
    with tempfile.TemporaryDirectory(prefix="hub-chats-") as temporary:
        root = Path(temporary) / "project"
        data = root / "docs/project-portal"
        data.mkdir(parents=True)
        tasks = tasks or [
            {"id": "task-a", "title": "Alpha", "status": "done", "stages": []},
            {"id": "task-b", "title": "Beta", "status": "done", "stages": []},
        ]
        (data / "project.json").write_text(json.dumps({
            "schemaVersion": 1, "id": "owner", "name": "Owner", "tasks": tasks,
        }), encoding="utf-8")
        coordination = Path(temporary) / "coordination"
        hub = Hub(coordination)
        hub.register(root)
        for sid in sessions or []:
            hub.lifecycle({"session_id": sid, "cwd": str(root), "hook_event_name": "SessionStart"}, "start-" + sid)
        store = Store(root, coordination_home=coordination)
        if catalog is None:
            catalog = {sid: {"id": sid, "name": sid, "cwd": str(root), "updated_at": 1,
                             "archived": False, "source": "test"} for sid in sessions or []}
        def title_lookup(value, default=None):
            if isinstance(value, (list, tuple, set)):
                return {sid: catalog.get(sid, {}).get("name", sid) for sid in value}
            return catalog.get(value, {}).get("name", default)
        with patch("codex_session_catalog.CATALOG.read", return_value={
                "available": True, "sessions": list(catalog.values()), "truncated": False}), \
             patch("project_portal.SESSION_TITLES.get", side_effect=title_lookup):
            yield store, hub


class TaskChatsTest(unittest.TestCase):
    def test_creator_and_current_or_legacy_stage_participation_are_separate_from_activity(self):
        tasks = [dict(id='task-a', title='Alpha', status='active',
            createdBy=dict(session=EXPLICIT, project='owner'), stages=[
                dict(id='one', title='First stage', status='planned', remaining=[]),
                dict(id='two', title='Second stage', status='planned', remaining=[])])]
        with fixture(tasks=tasks, sessions=[PARENT, CHILD]) as (store, hub):
            hub.store_factory = lambda project: store
            hub.begin(PARENT, 'task-a', 'Shared work', ['fixture'], stages=['one', 'two'])
            legacy = hub.begin(CHILD, 'task-a', 'Stage participant', ['resource:review'], stage='one', mode='read')
            with hub.connect() as db:
                db.execute('DELETE FROM work_stage_links WHERE work=?', (legacy['work'],))
            result = chat_history(store, task='task-a')
            rows = {row['id']: row for row in result['sessions']}
            self.assertEqual({link['stage'] for link in rows[PARENT]['stageLinks']}, {'one', 'two'})
            self.assertEqual([link['stage'] for link in rows[CHILD]['stageLinks']], ['one'])
            self.assertGreater(rows[CHILD]['stageLinks'][0]['lastRelatedAt'], 0)
            self.assertEqual(rows[EXPLICIT]['taskLinks'][0]['id'], 'task-a')
            self.assertEqual(rows[EXPLICIT]['state'], 'unknown')
            self.assertEqual(rows[EXPLICIT]['stageLinks'], [])

    def test_one_completed_chat_can_link_multiple_tasks(self):
        with fixture(sessions=[PARENT]) as (store, hub):
            first = hub.begin(PARENT, "task-a", "Alpha work", ["fixture"])
            second = hub.begin(PARENT, "task-b", "Beta work", ["fixture"])
            hub.report(PARENT, first["work"], first["revision"], "Alpha complete", status="done")
            hub.report(PARENT, second["work"], second["revision"], "Beta complete", status="done")
            result = chat_history(store)
            row = next(s for s in result["sessions"] if s["id"] == PARENT)
            self.assertEqual({link["id"] for link in row["taskLinks"]}, {"task-a", "task-b"})
            self.assertEqual(result["coverage"]["tasksWithChats"], 2)

    def test_stale_sessions_task_does_not_hide_recorded_work(self):
        with fixture(sessions=[PARENT]) as (store, hub):
            hub.begin(PARENT, "task-b", "Recorded work", ["fixture"])
            with hub.connect() as connection:
                connection.execute("UPDATE sessions SET task=? WHERE id=?", ("task-a", PARENT))
            result = chat_history(store, task="task-b")
            self.assertEqual([s["id"] for s in result["sessions"]], [PARENT])

    def test_work_from_task_origin_project_keeps_transferred_membership(self):
        tasks = [{"id": "task-a", "title": "Alpha", "status": "done", "originProject": "origin", "stages": []}]
        with fixture(tasks=tasks, sessions=[]) as (store, hub):
            origin = store.root.parent / "origin"
            (origin / "docs/project-portal").mkdir(parents=True)
            (origin / "docs/project-portal/project.json").write_text(json.dumps({
                "schemaVersion": 1, "id": "origin", "name": "Origin", "tasks": [
                    {"id": "task-a", "title": "Alpha", "status": "done", "stages": []}]}), encoding="utf-8")
            hub.register(origin)
            hub.lifecycle({"session_id": CHILD, "cwd": str(origin), "hook_event_name": "SessionStart"}, "start-origin")
            hub.begin(CHILD, "task-a", "Origin work", ["fixture"])
            with patch("codex_session_catalog.CATALOG.read", return_value={"available": True,
                    "sessions": [{"id": CHILD, "name": "Origin chat", "cwd": str(origin),
                                  "updated_at": 2, "archived": False, "source": "test"}], "truncated": False}):
                result = chat_history(store, task="task-a")
            self.assertIn(CHILD, {s["id"] for s in result["sessions"]})

    def test_archived_catalog_session_is_retained(self):
        archived = {ARCHIVED: {"id": ARCHIVED, "name": "Archived chat", "cwd": ".",
                               "updated_at": 9, "archived": True, "source": "test"}}
        with fixture(sessions=[], catalog=archived) as (store, hub):
            with hub.connect() as connection:
                connection.execute("INSERT INTO sessions (id,project,workspace,state,seen,turn,checkpoint,task,last_cursor) VALUES (?,?,?,?,?,?,?,?,?)",
                                   (ARCHIVED, "owner", str(store.root), "closed", 9, "", "", "task-a", 0))
            result = chat_history(store)
            self.assertIn(ARCHIVED, {s["id"] for s in result["sessions"]})

    def test_more_than_two_hundred_histories_page_by_root_and_keep_children(self):
        catalog = {}
        with fixture(sessions=[], catalog=catalog) as (store, hub):
            for i in range(202):
                sid = f"{i:08x}-0000-4000-8000-000000000000"
                catalog[sid] = {"id": sid, "name": f"chat-{i}", "cwd": str(store.root),
                                "updated_at": i, "archived": False, "source": "test"}
                hub.lifecycle({"session_id": sid, "cwd": str(store.root), "hook_event_name": "SessionStart"}, "start-" + sid)
                work = hub.begin(sid, "task-a", f"work-{i}", ["fixture"])
                hub.report(sid, work["work"], work["revision"], "Complete", status="done")
            with hub.connect() as connection:
                parent_sid = "00000000-0000-4000-8000-000000000000"
                child_sid = "00000001-0000-4000-8000-000000000000"
                connection.execute("INSERT INTO session_agents (session,parent,agent_path,nickname,role) VALUES (?,?,?,?,?)",
                                   (child_sid, parent_sid, "/root/child", "Child", "executor"))
            # The catalog is read at call time in the real adapter; patch its result here.
            with patch("codex_session_catalog.CATALOG.read", return_value={"available": True,
                    "sessions": list(catalog.values()), "truncated": True}):
                pages = [chat_history(store, offset=offset, limit=100) for offset in (0, 100, 200)]
                first, second, third = pages
                self.assertEqual(first["total"], 201)
                self.assertEqual(first["next"], 100)
                self.assertEqual(second["offset"], 100)
                self.assertIsNone(third["next"])
                all_rows = [row for page in pages for row in page["sessions"]]
                roots = {row["openSession"] for row in all_rows if not row.get("contextOnly")}
                self.assertEqual(len(roots), 201)
                self.assertEqual(len(all_rows), 202)
                child_page = next(page for page in pages if {"00000000-0000-4000-8000-000000000000",
                                                              "00000001-0000-4000-8000-000000000000"} <=
                                   {row["id"] for row in page["sessions"]})
                self.assertEqual({row["openSession"] for row in child_page["sessions"]
                                  if row['id'] in (parent_sid, child_sid)},
                                 {"00000000-0000-4000-8000-000000000000"})

    def test_explicit_journal_actor_counts_without_work(self):
        with fixture(sessions=[], catalog={}) as (store, hub):
            event = {"id": "event-1", "kind": "note", "taskId": "task-a", "at": "2026-01-01T00:00:00Z",
                     "actor": {"session": EXPLICIT}, "title": "Recorded", "seq": 1, "schemaVersion": 1}
            store.journal.write_text(json.dumps(event) + "\n", encoding="utf-8")
            result = chat_history(store, task="task-a")
            self.assertEqual([s["id"] for s in result["sessions"]], [EXPLICIT])

    def test_namespaced_actor_in_journal_keeps_task_membership_without_native_link(self):
        actor = 'a' * 64
        with fixture(sessions=[], catalog={}) as (store, hub):
            event = {'id': 'event-1', 'kind': 'note', 'taskId': 'task-a', 'at': '2026-01-01T00:00:00Z',
                     'actor': {'session': actor}, 'title': 'Recorded', 'seq': 1, 'schemaVersion': 1}
            store.journal.write_text(json.dumps(event) + '\n', encoding='utf-8')
            row = chat_history(store, task='task-a')['sessions'][0]
            self.assertEqual(row['id'], actor)
            self.assertEqual(row['chatIdentity'], 'unreported')
            self.assertNotIn('nativeChat', row)

    def test_root_activity_includes_child_and_archive_remains_searchable(self):
        with fixture(sessions=[PARENT, CHILD]) as (store, hub):
            with hub.connect() as connection:
                connection.execute('INSERT INTO session_agents (session,parent,agent_path,nickname,role) VALUES (?,?,?,?,?)',
                                   (CHILD, PARENT, '/root/review', 'Review', 'reviewer'))
                connection.execute("UPDATE sessions SET seen=100,state='closed' WHERE id=?", (PARENT,))
                connection.execute('UPDATE sessions SET seen=200 WHERE id=?', (CHILD,))
            result = chat_history(store, query='Review')
            self.assertEqual(result['total'], 1)
            parent = next(s for s in result['sessions'] if s['id'] == PARENT)
            self.assertEqual(parent['lastActivityAt'], 200)
            self.assertTrue(parent['historical'])

    def test_foreign_task_is_excluded_even_when_chat_id_matches(self):
        with fixture(sessions=[PARENT]) as (store, hub):
            hub.begin(PARENT, "task-a", "Owner work", ["fixture"])
            with hub.connect() as connection:
                connection.execute("INSERT INTO projects VALUES (?,?,?)", ("foreign", str(store.root.parent / "foreign"), ""))
                connection.execute("INSERT INTO sessions (id,project,workspace,state,seen,turn,checkpoint,task,last_cursor) VALUES (?,?,?,?,?,?,?,?,?)",
                                   (CHILD, "foreign", str(store.root.parent / "foreign"), "closed", 1, "", "", "task-a", 0))
                connection.execute("INSERT INTO work (id,project,session,task,title,status,revision,created,updated,result,git_snapshot,checkpoint,evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                   ("foreign-work", "foreign", CHILD, "task-a", "Private", "done", 1, 1, 1, "", "", "", "[]"))
            result = chat_history(store)
            self.assertNotIn(CHILD, {s["id"] for s in result["sessions"]})

    def test_http_task_filter_does_not_return_unrelated_chat(self):
        with fixture(sessions=[PARENT, CHILD]) as (store, hub):
            hub.begin(PARENT, "task-a", "Owner work", ["fixture"])
            hub.begin(CHILD, "task-b", "Other work", ["fixture"])
            server = __import__("project_portal").PortalServer(("127.0.0.1", 0), store)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with closing(http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)) as connection:
                    connection.request("GET", "/api/chats?task=task-a")
                    response = connection.getresponse()
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertEqual({row["id"] for row in payload["sessions"]}, {PARENT})
            finally:
                server.shutdown()
                server.server_close()

    def test_catalog_default_hides_archived_and_explicit_read_includes_it(self):
        with fixture(sessions=[]) as (store, hub):
            database = store.root.parent / "catalog.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE threads (id TEXT,name TEXT,cwd TEXT,updated_at REAL,archived INTEGER,source TEXT)")
                connection.execute("INSERT INTO threads VALUES (?,?,?,?,?,?)",
                                   (ARCHIVED, "Archived", str(store.root), 2, 1, "vscode"))
                connection.commit()
            catalog = SessionCatalog(database, ttl=0)
            self.assertEqual(catalog.read(store.root)["sessions"], [])
            self.assertEqual([row["id"] for row in catalog.read(store.root, include_archived=True)["sessions"]], [ARCHIVED])

    def test_unknown_task_fails_closed(self):
        with fixture() as (store, hub):
            with self.assertRaisesRegex(ValueError, "Unknown task"):
                chat_history(store, task="missing")


if __name__ == "__main__":
    unittest.main()
