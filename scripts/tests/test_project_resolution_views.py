"""Project membership is identical across portal discovery, hooks and MCP."""
import json
import sqlite3
import unittest
from unittest.mock import patch
import test_project_hub_bindings as bindings
from codex_session_catalog import SessionCatalog
from plugin_api import HubError


class ProjectViewsTest(unittest.TestCase):
    setUp=bindings.BindingsTest.setUp
    tearDown=bindings.BindingsTest.tearDown
    save_catalog=bindings.BindingsTest.save_catalog
    invoke=bindings.BindingsTest.invoke
    task=bindings.BindingsTest.task
    git=bindings.BindingsTest.git

    def metadata(self, rows):
        db=self.base/'threads.sqlite'
        with sqlite3.connect(db) as c:
            c.execute('CREATE TABLE threads(id TEXT,name TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER,source TEXT)')
            c.executemany('INSERT INTO threads VALUES(?,?,?,1,?,?)',[(sid,sid,str(cwd),archived,'vscode') for sid,cwd,archived in rows])
        c.close()
        return SessionCatalog(db,ttl=0)

    def assign(self,sid,project,kind='local'):
        data=json.loads(self.catalog.read_text())
        data.setdefault('thread-project-assignments',{})[sid]=dict(projectKind=kind,projectId=project)
        self.catalog.write_text(json.dumps(data))

    def test_registry_snapshot_uses_compact_diagnostics(self):
        self.invoke(self.a,'diagnostics','hub_context')
        store=self.registry.store(self.ids['a'])
        with patch.object(store,'coordination',side_effect=AssertionError('archive accessed')):
            view=store.snapshot()['coordination']
        self.assertIn('sessions',view)
        self.assertFalse({'work','team','attempts','claims'} & view.keys())

    def test_diagnostics_does_not_create_uninitialized_database(self):
        store=self.registry.store(self.ids['a'])
        database=self.registry.home/'coordination/coordination.sqlite3'
        self.assertFalse(database.exists())
        store.snapshot()
        store.snapshot()
        self.assertFalse(database.exists())

    def test_move_is_visible_before_hook_without_moving_work(self):
        task=self.task(self.a,'moved')
        work=self.invoke(self.a,'moved','hub_begin',task=task,title='Retained',resources=['src'])
        catalog=self.metadata([('moved',self.a,0)])
        self.assign('moved','b')
        with patch('codex_session_catalog.CATALOG',catalog):
            old=self.registry.store(self.ids['a']).coordination()
            new=self.registry.store(self.ids['b']).coordination()
        self.assertTrue(old['available']);self.assertTrue(new['available'])
        self.assertTrue(old['sessions'][0]['historical'])
        self.assertEqual(new['sessions'][0]['id'],'moved')
        self.assertEqual(old['work'][0]['id'],work['work'])
        self.assertEqual(self.invoke(self.a,'moved','hub_context')['project'],self.ids['b'])
        with patch('codex_session_catalog.CATALOG',catalog):
            self.assertEqual(self.registry.store(self.ids['a']).coordination()['sessions'][0]['activeWork'],1)

    def test_archived_sessions_hidden_unless_reservations_exist(self):
        task=self.task(self.a,'retained')
        self.invoke(self.a,'retained','hub_begin',task=task,title='Keep',resources=['src'])
        self.invoke(self.a,'archived','hub_context')
        catalog=self.metadata([('retained',self.a,1),('archived',self.a,1),('normal',self.a,0)])
        with patch('codex_session_catalog.CATALOG',catalog):
            view=self.registry.store(self.ids['a']).coordination()
        self.assertEqual({s['id'] for s in view['sessions']},{'retained','normal'})
        self.assertEqual(view['registeredCount'],1)
        self.assertEqual(view['discovery']['archivedCount'],2)

    def test_primary_nested_and_unknown_assignment_use_same_policy(self):
        nested=self.a/'nested';nested.mkdir()
        self.save_catalog({'a':[self.a],'b':[nested,self.a]})
        catalog=self.metadata([('primary',self.a,0),('nested',nested,0),('unknown',self.a,0),('remote',self.a,0)])
        self.assign('unknown','missing');self.assign('remote','remote','cloud')
        for name,cwd in [('primary',self.a),('nested',nested)]:
            pid=self.invoke(cwd,name,'hub_context')['project']
            result=catalog.read_project(self.registry,pid,[],{})
            self.assertEqual([r['id'] for r in result['sessions']],[name])
        for name in ('unknown','remote'):
            with self.assertRaises(HubError):self.invoke(self.a,name,'hub_context')

    def test_invalid_metadata_never_falls_back_to_old_root(self):
        catalog=self.metadata([('chat',self.a,0)])
        self.catalog.write_text('{broken')
        result=catalog.read_project(self.registry,self.ids['a'],[],{})
        self.assertFalse(result['available']);self.assertEqual(result['sessions'],[])
        with self.assertRaises(HubError):self.invoke(self.a,'chat','hub_context')

    def test_cached_paths_do_not_delay_assignment_or_root_changes(self):
        catalog=self.metadata([('chat',self.a,0)])
        catalog.ttl=30
        self.assertEqual(len(catalog.read_project(self.registry,self.ids['a'],[],{})['sessions']),1)
        self.assign('chat','b')
        self.assertEqual(catalog.read_project(self.registry,self.ids['a'],[],{})['sessions'],[])
        self.assertEqual(len(catalog.read_project(self.registry,self.ids['b'],[],{})['sessions']),1)
        self.save_catalog({'a':[self.b],'b':[self.a]})
        self.assertEqual(len(catalog.read_project(self.registry,self.ids['b'],[],{})['sessions']),1)

    def test_external_worktree_catalog_matches_mcp(self):
        self.git('init')
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-m','Initial')
        tree=self.base/'external'
        self.git('worktree','add','--detach',str(tree))
        try:
            catalog=self.metadata([('tree',tree,0)])
            pid=self.invoke(tree,'tree','hub_context')['project']
            result=catalog.read_project(self.registry,pid,[],{})
            self.assertEqual([r['id'] for r in result['sessions']],['tree'])
        finally:self.git('worktree','remove','--force',str(tree))
