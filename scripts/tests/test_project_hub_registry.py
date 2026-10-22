import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_registry import CodexProjects, ProjectRegistry


class RegistryTest(unittest.TestCase):
    def test_discovery_without_chats_rename_and_retained_history(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); catalog=base/'codex.json'
            rows={key:dict(id=key,name=key,rootPaths=[str(base/key)]) for key in ('a','b','g-p-cloud')}
            catalog.write_text(json.dumps({'local-projects':rows}))
            registry=ProjectRegistry(base/'hub',CodexProjects(catalog))
            projects=registry.list()['projects']
            self.assertEqual(len(projects),2)
            first=next(p for p in projects if p['codex_id']=='a')['id']
            second=next(p for p in projects if p['codex_id']=='b')['id']
            registry.store(first).record(dict(kind='task.created',taskId='same',title='Create',
                                             patch=dict(title='First',status='planned',stages=[])))
            self.assertEqual(registry.store(second).snapshot()['tasks'],[])
            rows['a']['name']='Renamed'; del rows['b']
            catalog.write_text(json.dumps({'local-projects':rows}))
            current=registry.list()['projects']
            self.assertEqual(next(p for p in current if p['id']==first)['name'],'Renamed')
            self.assertFalse(next(p for p in current if p['id']==second)['present'])
            self.assertEqual(registry.store(first).snapshot()['tasks'][0]['title'],'First')
            catalog.write_text('{broken')
            self.assertFalse(registry.list()['discovery']['available'])
            self.assertEqual(len(registry.list()['projects']),2)
            with self.assertRaises(KeyError): registry.store('../escape')
            self.assertFalse((base/'a').exists())
