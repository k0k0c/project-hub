"""Focused service contract tests for explicit architecture research submits."""
import json
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hub_chat_actions import ChatActionError
from knowledge_store import KnowledgeStore
import test_hub_chat_actions as fixtures


class ArchitectureResearchTests(unittest.TestCase):
    make_service = fixtures.ChatActionsTests.make_service
    def setUp(self):
        fixtures.ChatActionsTests.setUp(self)
        self.knowledge = KnowledgeStore(self.registry, "p")
        item = {"id": "code:thing", "kind": "entity", "type": "class", "title": "Thing",
                "description": "A selected architecture type", "source": {"path": "src/Thing.java", "line": 4}}
        self.knowledge.changeset(0, "seed-research", [{"op": "put", "item": item}], "seed")

    def research(self, **changes):
        value = {"objectId": "code:thing", "template": "explain", "prompt": "Explain this type.", "revision": 1}
        value.update(changes)
        return value

    def test_research_prompt_uses_authoritative_root_and_source(self):
        result = self.service.start_research("p", self.research(), "research-1")
        self.assertEqual(result["status"], "accepted")
        cwd, prompt = self.adapters[0].calls[-1][1:3]
        self.assertEqual(cwd, str(self.registry.roots["p"].resolve()))
        self.assertIn("code:thing", prompt)
        self.assertIn("src/Thing.java", prompt)
        self.assertIn('"operation":"architecture-analyze"', prompt)
        self.assertNotIn("select or create your own research task", prompt)

    def test_retry_is_idempotent_and_changed_arguments_conflict(self):
        request = self.research()
        first = self.service.start_research("p", request, "research-2")
        self.assertEqual(first, self.service.start_research("p", request, "research-2"))
        changed = dict(request, prompt="A different question")
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research("p", changed, "research-2")
        self.assertEqual(error.exception.code, "action_id_conflict")
        self.assertEqual(len(self.adapters), 1)

    def test_missing_object_and_payload_bounds_are_rejected(self):
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research("p", self.research(objectId="missing"), "research-3")
        self.assertEqual(error.exception.code, "research_object_not_found")
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research("p", self.research(prompt="x" * 6001), "research-4")
        self.assertEqual(error.exception.code, "invalid_request")

    def test_runtime_overrides_are_not_accepted_or_forwarded(self):
        request = self.research(cwd="C:/untrusted", executable=["evil"])
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research("p", request, "research-5")
        self.assertEqual(error.exception.code,"invalid_request")
        self.assertEqual(self.adapters,[])

    def test_research_requires_current_knowledge_revision_before_launch(self):
        request = self.research()
        del request['revision']
        for index, value in enumerate([request, self.research(revision=True), self.research(revision='1')]):
            with self.assertRaises(ChatActionError) as error:
                self.service.start_research('p', value, 'invalid-revision-'+str(index))
            self.assertEqual(error.exception.code, 'invalid_request')
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research('p', self.research(revision=0), 'stale-revision')
        self.assertEqual(error.exception.code, 'stale_revision')
        self.assertEqual(self.adapters, [])

    def test_structure_map_requires_saved_view_scope_and_keeps_scope_metadata(self):
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research("p", self.research(template="structure-map"), "map-missing-scope")
        self.assertEqual(error.exception.code, "invalid_request")
        node_a={"id":"code:a","kind":"entity","type":"class","title":"A"}
        node_b={"id":"code:b","kind":"entity","type":"class","title":"B"}
        edge={"id":"rel:a-b","kind":"relation","from":"code:a","to":"code:b","type":"uses"}
        view={"id":"research:view-1","kind":"view","viewType":"research","title":"Saved canvas","nodeIds":["code:a","code:b"],"orderedEdges":["rel:a-b"],"researchBasis":{"revision":1}}
        self.knowledge.changeset(1,"seed-research-view",[{"op":"put","item":node_a},{"op":"put","item":node_b},{"op":"put","item":edge},{"op":"put","item":view}],"seed view")
        request=self.research(objectId="research:view-1",template="structure-map",revision=2,
                              scope={"kind":"canvas","viewId":"research:view-1"})
        result=self.service.start_research("p",request,"map-valid")
        self.assertEqual(result["status"],"accepted");self.assertEqual(result["researchScope"],{"kind":"canvas","viewId":"research:view-1"})
        prompt=self.adapters[0].calls[-1][2];self.assertIn('"template":"structure-map"',prompt);self.assertIn('"canvasCounts"',prompt)

    def test_structure_map_rejects_missing_result_and_class_decompose(self):
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research("p",self.research(template="decompose"),"decompose-class")
        self.assertEqual(error.exception.code,"invalid_request")
        view={"id":"research:view-2","kind":"view","viewType":"research","title":"Canvas","nodeIds":[],"orderedEdges":[]}
        self.knowledge.changeset(1,"seed-empty-view",[{"op":"put","item":view}],"seed view")
        request=self.research(objectId="research:view-2",template="structure-map",revision=2,
                              scope={"kind":"result","viewId":"research:view-2","resultId":"research:missing"})
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research("p",request,"map-missing-result")
        self.assertEqual(error.exception.code,"research_result_not_found")

    def test_structure_map_snapshot_allows_one_authored_revision_but_rejects_source_or_knowledge_changes(self):
        import knowledge_research
        knowledge_research.setup(self.knowledge);basis=knowledge_research.fingerprint(self.knowledge)[0]
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO knowledge_research VALUES(?,?,?,?)',('p','result-snapshot','',json.dumps({"id":"result-snapshot","status":"ready","fingerprint":basis,"fingerprintScope":"sources","nodes":[{"id":"code:thing","kind":"entity","type":"class","title":"Thing"}],"relations":[]})));connection.commit()
        saved=knowledge_research.save_map(self.knowledge,1,'snapshot-map','Snapshot',['code:thing'],[],resultId='result-snapshot')
        request=self.research(objectId=saved['id'],template='structure-map',revision=saved['revision'],scope={"kind":"result","viewId":saved['id'],"resultId":"result-snapshot"})
        accepted=self.service.start_research('p',request,'map-snapshot-valid');self.assertEqual(accepted['status'],'accepted')
        (self.registry.roots['p']/'src').mkdir(exist_ok=True);(self.registry.roots['p']/'src'/'Thing.java').write_text('changed',encoding='utf-8')
        with self.assertRaises(ChatActionError) as error:self.service.start_research('p',request,'map-snapshot-file-changed')
        self.assertEqual(error.exception.code,'research_result_stale')

    def test_structure_map_snapshot_rejects_second_knowledge_revision(self):
        import knowledge_research
        knowledge_research.setup(self.knowledge);basis=knowledge_research.fingerprint(self.knowledge)[0]
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO knowledge_research VALUES(?,?,?,?)',('p','result-revision','',json.dumps({"id":"result-revision","status":"ready","fingerprint":basis,"fingerprintScope":"sources","nodes":[{"id":"code:thing","kind":"entity","type":"class","title":"Thing"}],"relations":[]})));connection.commit()
        saved=knowledge_research.save_map(self.knowledge,1,'revision-map','Snapshot',['code:thing'],[],resultId='result-revision')
        self.knowledge.changeset(saved['revision'],'after-snapshot',[{"op":"put","item":{"id":"code:after","kind":"entity","type":"class","title":"After"}}],'after snapshot')
        request=self.research(objectId=saved['id'],template='structure-map',revision=saved['revision']+1,scope={"kind":"result","viewId":saved['id'],"resultId":"result-revision"})
        with self.assertRaises(ChatActionError) as error:self.service.start_research('p',request,'map-snapshot-knowledge-changed')
        self.assertEqual(error.exception.code,'research_result_stale')

    def test_structure_map_result_scope_checks_provenance_and_freshness(self):
        import knowledge_research
        good={"id":"research:view-good","kind":"view","viewType":"research","title":"Good","nodeIds":["code:thing"],"orderedEdges":[]}
        bad={"id":"research:view-bad","kind":"view","viewType":"research","title":"Bad","nodeIds":["code:thing"],"orderedEdges":[]}
        self.knowledge.changeset(1,"seed-result-views",[{"op":"put","item":good},{"op":"put","item":bad}],"seed views")
        knowledge_research.setup(self.knowledge);basis=knowledge_research.fingerprint(self.knowledge)[0]
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO knowledge_research VALUES(?,?,?,?)',('p','result-good','',json.dumps({"id":"result-good","status":"ready","fingerprint":basis,"fingerprintScope":"sources","nodes":[{"id":"code:thing","kind":"entity","type":"class","title":"Thing"}],"relations":[]})))
            connection.execute('INSERT INTO knowledge_research VALUES(?,?,?,?)',('p','result-unrelated','',json.dumps({"id":"result-unrelated","status":"ready","fingerprint":basis,"fingerprintScope":"sources","nodes":[{"id":"code:other","kind":"entity","type":"class","title":"Other"}],"relations":[]})))
            connection.commit()
        request=self.research(objectId="research:view-good",template="structure-map",revision=2,scope={"kind":"result","viewId":"research:view-good","resultId":"result-good"})
        result=self.service.start_research('p',request,'map-result-valid');self.assertEqual(result['status'],'accepted');self.assertEqual(result['researchScope']['resultId'],'result-good')
        bad_request=self.research(objectId="research:view-bad",template="structure-map",revision=2,scope={"kind":"result","viewId":"research:view-bad","resultId":"result-unrelated"})
        with self.assertRaises(ChatActionError) as error:self.service.start_research('p',bad_request,'map-result-unrelated')
        self.assertEqual(error.exception.code,'research_scope_mismatch')
        with self.registry.connect() as connection:connection.execute('INSERT INTO knowledge_research VALUES(?,?,?,?)',('p','result-stale','',json.dumps({"id":"result-stale","status":"ready","fingerprint":"0"*64,"fingerprintScope":"sources","nodes":[{"id":"code:thing","kind":"entity"}],"relations":[]})));connection.commit()
        stale_request=dict(request,scope={"kind":"result","viewId":"research:view-good","resultId":"result-stale"})
        with self.assertRaises(ChatActionError) as error:self.service.start_research('p',stale_request,'map-result-stale')
        self.assertEqual(error.exception.code,'research_result_stale')

    def test_structure_map_result_scope_reads_all_result_pages(self):
        import knowledge_research
        nodes=[{"id":f"code:n{i}","kind":"entity","type":"class","title":f"N{i}"} for i in range(205)]
        view={"id":"research:view-large","kind":"view","viewType":"research","title":"Large","nodeIds":[n["id"] for n in nodes],"orderedEdges":[]}
        self.knowledge.changeset(1,"seed-large-view",[{"op":"put","item":n} for n in nodes]+[{"op":"put","item":view}],"seed large view")
        first={"status":"ready","stale":False,"items":nodes[:200],"more":True,"next":200};second={"status":"ready","stale":False,"items":nodes[200:],"more":False,"next":205}
        request=self.research(objectId="research:view-large",template="structure-map",revision=2,scope={"kind":"result","viewId":"research:view-large","resultId":"result-large"})
        with patch.object(knowledge_research,"result",side_effect=[first,second]):
            result=self.service.start_research('p',request,'map-large-result')
        self.assertEqual(result['status'],'accepted');self.assertEqual(result['researchScope']['resultId'],'result-large')

    def test_project_history_includes_other_objects_active_first_and_pages(self):
        with self.registry.connect() as connection:
            for index in range(25):
                response = dict(project='p',task='__research__:code:'+str(index),actionId='history-'+str(index),
                                status='running' if index==0 else 'completed',createdAt=index,
                                researchTitle='Object '+str(index),researchTemplate='explain')
                connection.execute('INSERT INTO codex_chat_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    ('p',response['task'],response['actionId'],'fixture',response['status'],None,None,None,'fixture',index,index,json.dumps(response)))
            connection.execute('INSERT INTO codex_chat_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                ('p','ordinary-task','ordinary','fixture','running',None,None,None,'fixture',100,100,json.dumps(dict(actionId='ordinary',task='ordinary-task'))))
        queries=[]
        connect=self.registry.connect
        @contextmanager
        def traced_connect():
            with connect() as connection:
                connection.set_trace_callback(queries.append)
                try:
                    yield connection
                finally:
                    connection.set_trace_callback(None)
        with patch.object(self.registry,'connect',side_effect=traced_connect):
            first=self.service.research_history('p')
        history_query=next(query for query in queries if query.startswith('SELECT response FROM codex_chat_actions'))
        with connect() as connection:
            plan=[row['detail'] for row in connection.execute('EXPLAIN QUERY PLAN '+history_query)]
        self.assertTrue(any('codex_research_history' in detail for detail in plan),plan)
        self.assertFalse(any('TEMP B-TREE' in detail for detail in plan),plan)
        self.assertEqual(len(first['items']),20)
        self.assertEqual(first['items'][0]['researchTitle'],'Object 0')
        self.assertEqual(first['items'][1]['researchTitle'],'Object 24')
        self.assertTrue(first['more'])
        second=self.service.research_history('p',first['next'])
        self.assertEqual(len(second['items']),5)
        self.assertFalse(second['more'])
        self.assertEqual(len({r['actionId'] for r in first['items']+second['items']}),25)
        with self.assertRaises(ChatActionError):self.service.research_history('missing')
        with self.assertRaises(ChatActionError):self.service.research_history('p','invalid')

    def test_detail_level_and_project_model_reach_only_research_thread(self):
        from project_settings import read_settings, update_settings
        from project_portal import Store
        settings_store = Store(self.registry.roots['p'], data_dir=self.registry.roots['p'] / 'data')
        update_settings(settings_store, {'architecture': {'model': 'fixture-model', 'descriptionDetail': 'detailed'}},
                        read_settings(settings_store)['revision'])
        result = self.service.start_research('p', self.research(), 'detailed')
        self.assertEqual(result['model'], 'fixture-model')
        self.assertEqual(result['detailLevel'], 'detailed')
        self.assertIn('"detailLevel":"detailed"', self.adapters[0].calls[-1][2])
        second = self.service.start_research('p', self.research(detailLevel='brief'), 'brief')
        self.assertEqual(second['detailLevel'], 'brief')
        self.assertIn('"detailLevel":"brief"', self.adapters[1].calls[-1][2])
        with self.assertRaises(ChatActionError):
            self.service.start_research('p', self.research(detailLevel='article'), 'invalid-detail')


if __name__ == "__main__":
    unittest.main()
