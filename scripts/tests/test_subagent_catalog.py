"""Subagent metadata uses disposable catalogs and never supplies ownership or liveness."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_session_catalog import SessionCatalog, merge_sessions, parse_source
from project_registry import CodexProjects, ProjectRegistry


def spawn(parent='root', **overrides):
    return json.dumps({'subagent': {'thread_spawn': dict(
        parent_thread_id=parent, depth=1, agent_path='/root/child',
        agent_nickname='Child', agent_role=None, **overrides)}})


class SubagentCatalogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'a'; self.root.mkdir()
        self.other = self.base / 'b'; self.other.mkdir()
        self.db = self.base / 'threads.sqlite'
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('CREATE TABLE threads(id TEXT,name TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER,source TEXT)')
            connection.commit()
        self.catalog = SessionCatalog(self.db, ttl=0)

    def add(self, sid, source='vscode', archived=0, cwd=None):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('INSERT INTO threads VALUES(?,?,?,1,?,?)',
                               (sid, sid, str(cwd or self.root), archived, source))
            connection.commit()

    def registry(self, assignments=None):
        path = self.base / 'projects.json'
        path.write_text(json.dumps({'local-projects': {
            name: dict(id=name, name=name, rootPaths=[str(root)])
            for name, root in [('a', self.root), ('b', self.other)]},
            'thread-project-assignments': assignments or {}}))
        registry = ProjectRegistry(self.base / 'data', CodexProjects(path))
        ids = {p['name']: p['id'] for p in registry.list()['projects']}
        return registry, ids

    def test_describe_and_discovery_preserve_metadata_without_writes(self):
        self.add('root'); self.add('cli', 'cli')
        self.add('child', spawn()); self.add('grandchild', spawn('child'))
        before = self.db.read_bytes()
        child = self.catalog.describe('child')['session']
        self.assertEqual((child['kind'], child['parentSession'], child['agentPath']),
                         ('subagent', 'root', '/root/child'))
        self.assertEqual(child['agentNickname'], 'Child')
        self.assertIsNone(child['agentRole'])
        self.assertEqual(self.catalog.describe('cli')['session']['kind'], 'agent')
        self.assertEqual({r['id'] for r in self.catalog.read(self.root)['sessions']},
                         {'root', 'cli', 'child', 'grandchild'})
        self.assertEqual(self.db.read_bytes(), before)

    def test_malformed_and_unknown_sources_are_rejected(self):
        valid = json.loads(spawn())
        cases = [None, 'subagent', '{', 'null', '[]', '{}', json.dumps({'subagent': []}),
                 json.dumps({'subagent': {'thread_spawn': []}}),
                 json.dumps(dict(valid, unknown=True)),
                 json.dumps({'subagent': dict(valid['subagent'], unknown=True)})]
        for field, value in [('parent_thread_id', 'child'), ('parent_thread_id', ' root '),
                             ('parent_thread_id', ''), ('depth', True), ('depth', 0),
                             ('depth', 33), ('agent_path', []), ('agent_nickname', ' '),
                             ('agent_role', 10), ('unknown', True)]:
            malformed = json.loads(spawn())
            malformed['subagent']['thread_spawn'][field] = value
            cases.append(json.dumps(malformed))
        for source in cases:
            with self.subTest(source=source):
                self.assertIsNone(parse_source(source, 'child'))

    def test_cycles_rejected_even_across_roots_and_archived_parent(self):
        self.add('a', spawn('b'))
        self.add('b', spawn('a'), archived=1, cwd=self.other)
        self.add('self', spawn('self'))
        self.add('orphan', spawn('missing'))
        for sid in ('a', 'b', 'self'):
            self.assertIsNone(self.catalog.describe(sid)['session'])
        self.assertEqual([r['id'] for r in self.catalog.read(self.root)['sessions']], ['orphan'])
        self.assertEqual(self.catalog.describe('orphan')['session']['parentSession'], 'missing')

    def test_archived_described_but_hidden_and_missing_database_not_created(self):
        self.add('archived', spawn(), archived=1)
        self.assertTrue(self.catalog.describe('archived')['session']['archived'])
        self.assertEqual(self.catalog.read(self.root)['sessions'], [])
        self.assertEqual(self.catalog.describe('missing'), dict(available=True, session=None))
        missing = self.base / 'missing.sqlite'
        self.assertEqual(SessionCatalog(missing).describe('x'), dict(available=False, session=None))
        self.assertFalse(missing.exists())
        invalid = self.base / 'invalid.sqlite'; invalid.write_bytes(b'not sqlite')
        self.assertFalse(SessionCatalog(invalid).describe('x')['available'])

    def test_child_assignment_is_independent_and_registration_enriched(self):
        self.add('root'); self.add('child', spawn())
        registry, ids = self.registry({'child': dict(projectKind='local', projectId='b')})
        registered = [dict(id='child', workspace=str(self.root), state='idle', task='own-task')]
        old = self.catalog.read_project(registry, ids['a'], registered, {})
        new = self.catalog.read_project(registry, ids['b'], registered, {})
        self.assertEqual([s['id'] for s in old['sessions']], ['root'])
        self.assertEqual(old['registered'], [])
        self.assertEqual([s['id'] for s in new['sessions']], ['child'])
        self.assertEqual(new['registered'][0]['parentSession'], 'root')
        self.assertEqual(new['registered'][0]['task'], 'own-task')
        self.assertEqual(new['registered'][0]['currentProject'], ids['b'])

    def test_parent_assignment_and_task_never_inherited(self):
        self.add('root'); self.add('child', spawn())
        registry, ids = self.registry({'root': dict(projectKind='local', projectId='b')})
        child_view = self.catalog.read_project(registry, ids['a'], [], {})
        self.assertEqual([s['id'] for s in child_view['sessions']], ['child'])
        rows = merge_sessions(child_view['sessions'], [dict(id='root', state='active',
                              seen=2, task='parent-task')], {}, {'root'}, {'root': 3})
        child = next(row for row in rows if row['id'] == 'child')
        self.assertEqual(child['kind'], 'subagent')
        self.assertEqual(child['state'], 'unknown')
        self.assertEqual(child['activeWork'], 0)
        self.assertIsNone(child['task']); self.assertIsNone(child['seen'])
        self.assertEqual(child['integration'], 'discovered')

    def test_mcp_actors_without_source_folder_keep_only_recorded_project(self):
        self.add('native-no-root')
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('UPDATE threads SET cwd=NULL WHERE id=?',('native-no-root',))
            connection.commit()
        registry,ids=self.registry()
        registered=[dict(id='mcp-actor',project=ids['a'],workspace=None,state='idle'),
                    dict(id='native-no-root',project=ids['b'],workspace=None,state='idle'),
                    dict(id='unknown',project='missing',workspace=None,state='idle')]
        first=self.catalog.read_project(registry,ids['a'],registered,{})
        second=self.catalog.read_project(registry,ids['b'],registered,{})
        self.assertTrue(first['available'])
        self.assertEqual([s['id'] for s in first['registered']],['mcp-actor'])
        self.assertEqual([s['id'] for s in second['registered']],['native-no-root'])
        self.assertEqual(second['registered'][0]['currentProject'],ids['b'])
        self.assertEqual(first['sessions'],[])

    def test_missing_host_catalog_keeps_scoped_completed_hub_history(self):
        registry,ids=self.registry()
        missing=self.base/'unavailable.sqlite'
        registered=[dict(id='old-chat',project=ids['a'],workspace=None,state='closed'),
                    dict(id='other-chat',project=ids['b'],workspace=None,state='idle')]
        result=SessionCatalog(missing).read_project(registry,ids['a'],registered,{},include_archived=True)
        self.assertFalse(result['available'])
        self.assertEqual([s['id'] for s in result['registered']],['old-chat'])
        self.assertTrue(result['registered'][0]['historical'])
        self.assertIsNone(result['registered'][0]['currentProject'])
        recent=SessionCatalog(missing).read_project(registry,ids['a'],registered,{})
        self.assertEqual(recent['registered'],[])
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
