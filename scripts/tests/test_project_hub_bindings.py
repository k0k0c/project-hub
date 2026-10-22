"""Real local Git/workspace identity and cross-project physical reservations."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry, CodexProjects
from plugin_api import ServerHub, call, HubError
from hub_core import git_common


class BindingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.a=self.base/'a';self.a.mkdir()
        self.b=self.base/'b';self.b.mkdir()
        self.catalog=self.base/'catalog.json'
        self.save_catalog({'a':[self.a],'b':[self.b]})
        self.registry=ProjectRegistry(self.base/'data',CodexProjects(self.catalog))
        self.ids={p['name']:p['id'] for p in self.registry.list()['projects']}

    def tearDown(self):
        self.tmp.cleanup()

    def save_catalog(self, roots):
        self.catalog.write_text(json.dumps({'local-projects':{
            name:dict(id=name,name=name,rootPaths=[str(p) for p in paths]) for name,paths in roots.items()}}))

    def invoke(self,cwd,session,tool,**arguments):
        return call(self.registry,dict(cwd=str(cwd),session=session,tool=tool,arguments=arguments))

    def task(self,cwd,session):
        return self.invoke(cwd,session,'hub_task',title='Binding test',scope=['src'],acceptance=['Verified'])['task']

    def git(self,*args):
        return subprocess.run(['git','-C',str(self.a),*args],check=True,capture_output=True,text=True,timeout=10)

    def test_real_external_worktree_shares_project_and_named_reservations(self):
        self.git('init')
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-m','Initial')
        tree=self.base/'external-worktree'
        self.git('worktree','add','--detach',str(tree))
        try:
            task=self.task(self.a,'primary')
            context=self.invoke(tree,'tree','hub_context')
            self.assertEqual(context['project'],self.ids['a'])
            self.invoke(self.a,'primary','hub_begin',task=task,title='Owner',resources=['resource:shared'])
            overlap=self.invoke(tree,'tree','hub_begin',task=task,title='Competitor',resources=['resource:shared'])
            self.assertEqual(overlap['warning'],'resource_overlap')
            work=self.invoke(tree,'tree','hub_begin',task=task,title='Tree files',resources=['src'])
            event=dict(session_id='tree',cwd=str(tree),hook_event_name='PreToolUse',tool_name='Write',tool_input={'path':str(tree/'src/file.py')})
            verdict=call(self.registry,dict(cwd=str(tree),session='tree',tool='hook',arguments=event))
            self.assertNotEqual(verdict.get('hookSpecificOutput',{}).get('permissionDecision'),'deny')
            self.assertEqual(ServerHub(self.registry).locate(tree)['root'],str(self.a.resolve()).lower() if sys.platform=='win32' else str(self.a.resolve()))
            nested=tree/'nested';nested.mkdir()
            self.save_catalog({'a':[self.a],'b':[nested]})
            tb=self.task(nested,'nested')
            self.invoke(tree,'tree','hub_begin',task=task,title='Shared tree path',resources=['nested/src'])
            overlap=self.invoke(nested,'nested','hub_begin',task=tb,title='Nested tree file',resources=['src/file.py'])
            self.assertEqual(overlap['warning'],'resource_overlap')
        finally:
            self.git('worktree','remove','--force',str(tree))

    def test_nested_projects_conflict_on_same_physical_file_only(self):
        nested=self.a/'nested';nested.mkdir()
        self.save_catalog({'a':[self.a],'b':[nested]})
        ta=self.task(self.a,'a');tb=self.task(nested,'b')
        owner=self.invoke(self.a,'a','hub_begin',task=ta,title='Owner',resources=['nested/src'])
        overlap=self.invoke(nested,'b','hub_begin',task=tb,title='Overlap',resources=['src/file.py'])
        self.assertEqual(overlap['warning'],'resource_overlap')
        self.invoke(nested,'b','hub_begin',task=tb,title='Separate',resources=['other'])
        self.invoke(self.a,'a','hub_report',work=owner['work'],revision=owner['revision'],result='Released',status='done')
        self.invoke(nested,'b','hub_begin',task=tb,title='Overlap',resources=['src/file.py'])

    def test_conflict_git_checks_are_bounded_and_refreshed_per_call(self):
        self.git('init')
        task=self.task(self.a,'owner')
        owner=self.invoke(self.a,'owner','hub_begin',task=task,title='Many claims',
                          resources=['src/file'+str(i) for i in range(25)])
        hub=ServerHub(self.registry)
        with hub.connect() as c, patch('plugin_api.git_common',wraps=git_common) as lookup:
            self.assertEqual(hub.conflicts(c,self.ids['b'],['other/'+str(i) for i in range(15)]),[])
            # One lookup for each project's root, independent of path/claim pairs.
            self.assertEqual(lookup.call_count,2)
            lookup.reset_mock()
            self.assertEqual(hub.conflicts(c,self.ids['b'],['other']),[])
            self.assertEqual(lookup.call_count,2)
        # A later registry change must affect the very same ServerHub instance.
        nested=self.a/'src';nested.mkdir()
        self.save_catalog({'a':[self.a],'b':[nested]})
        self.registry.list()
        with hub.connect() as c:
            conflicts=hub.conflicts(c,self.ids['b'],['file0'])
        self.assertEqual([row['id'] for row in conflicts],[owner['work']])

    def test_primary_owner_wins_over_secondary_attachment(self):
        self.save_catalog({'a':[self.a],'b':[self.b,self.a]})
        self.assertEqual(self.invoke(self.a,'a','hub_context')['project'],self.ids['a'])
        self.assertEqual(self.invoke(self.b,'b','hub_context')['project'],self.ids['b'])

    def test_explicit_chat_assignment_uses_attached_root(self):
        self.save_catalog({'a':[self.a],'b':[self.b,self.a]})
        data=json.loads(self.catalog.read_text())
        data['thread-project-assignments']={'moved':{'projectKind':'local','projectId':'b'}}
        self.catalog.write_text(json.dumps(data))
        self.assertEqual(self.invoke(self.a,'moved','hub_context')['project'],self.ids['b'])
        self.assertEqual(self.invoke(self.a,'normal','hub_context')['project'],self.ids['a'])

    def test_independent_projects_and_ambiguous_roots(self):
        ta=self.task(self.a,'a');tb=self.task(self.b,'b')
        self.invoke(self.a,'a','hub_begin',task=ta,title='One',resources=['src'])
        self.invoke(self.b,'b','hub_begin',task=tb,title='Two',resources=['src'])
        self.save_catalog({'a':[self.a],'b':[self.a]})
        with self.assertRaises(HubError) as caught:
            self.invoke(self.a,'new','hub_context')
        self.assertEqual(caught.exception.body['error'],'project_ambiguous')

    def test_alternate_non_git_root_keeps_identity_and_guards_its_files(self):
        alias=self.base/'alias';alias.mkdir()
        self.save_catalog({'a':[self.a,alias],'b':[self.b]})
        task=self.task(self.a,'primary')
        self.assertEqual(self.invoke(alias,'alias','hub_context')['project'],self.ids['a'])
        prefix=ServerHub.root_prefix(alias)
        self.invoke(alias,'alias','hub_begin',task=task,title='Alias files',resources=[prefix+'src'])
        event=dict(session_id='alias',cwd=str(alias),hook_event_name='PreToolUse',tool_name='Write',tool_input={'path':str(alias/'src/file.py')})
        verdict=call(self.registry,dict(cwd=str(alias),session='alias',tool='hook',arguments=event))
        self.assertNotEqual(verdict.get('hookSpecificOutput',{}).get('permissionDecision'),'deny')

    def test_moved_chat_primary_and_secondary_paths_have_distinct_claims(self):
        self.save_catalog({'a':[self.a],'b':[self.b,self.a]})
        data=json.loads(self.catalog.read_text())
        data['thread-project-assignments']={'moved':{'projectKind':'local','projectId':'b'}}
        self.catalog.write_text(json.dumps(data))
        task=self.task(self.a,'moved')
        self.invoke(self.a,'moved','hub_begin',task=task,title='Primary',resources=['src'])
        def edit(path):
            event=dict(session_id='moved',cwd=str(self.a),hook_event_name='PreToolUse',tool_name='Write',tool_input={'path':str(path)})
            return call(self.registry,dict(cwd=str(self.a),session='moved',tool='hook',arguments=event)).get('hookSpecificOutput',{}).get('permissionDecision')
        self.assertNotEqual(edit(self.b/'src/file.py'),'deny')
        self.assertIsNone(edit('src/file.py'))  # Filesystem permissions belong to Codex.
        self.assertIsNone(edit(self.base/'outside.py'))
        prefix=ServerHub.root_prefix(self.a)
        self.invoke(self.a,'moved','hub_begin',task=task,title='Secondary',resources=[prefix+'src'])
        self.assertNotEqual(edit('src/file.py'),'deny')
        ta=self.task(self.a,'normal')
        physical=self.invoke(self.a,'normal','hub_begin',task=ta,title='Physical overlap',resources=['src'])
        self.assertEqual(physical['warning'],'resource_overlap')
        data['local-projects']['b']['rootPaths']=[str(self.b)]
        self.catalog.write_text(json.dumps(data))
        self.assertEqual(self.invoke(self.a,'moved','hub_context')['project'],self.ids['b'])
        self.assertNotEqual(edit(self.b/'src/file.py'),'deny')
        self.assertIsNone(edit('src/file.py'))

    def test_explicit_unknown_assignment_does_not_fallback_to_cwd(self):
        data=json.loads(self.catalog.read_text())
        data['thread-project-assignments']={'moved':{'projectKind':'local','projectId':'missing'}}
        self.catalog.write_text(json.dumps(data))
        with self.assertRaises(HubError) as caught:
            self.invoke(self.a,'moved','hub_context')
        self.assertEqual(caught.exception.body['error'],'project_unregistered')

    def test_nested_attached_roots_conflict_inside_same_project(self):
        nested=self.a/'nested';nested.mkdir()
        self.save_catalog({'a':[self.a,nested],'b':[self.b]})
        task=self.task(self.a,'owner')
        self.invoke(self.a,'owner','hub_begin',task=task,title='Parent path',resources=['nested/src'])
        prefix=ServerHub.root_prefix(nested)
        overlap=self.invoke(self.a,'other','hub_begin',task=task,title='Attached path',resources=[prefix+'src/file.py'])
        self.assertEqual(overlap['warning'],'resource_overlap')


if __name__=='__main__':unittest.main()
