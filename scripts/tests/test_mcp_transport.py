"""Both MCP protocol eras must preserve explicit application conversation scope."""
import base64
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from agent_bindings import Connections
from mcp_transport import dispatch, LEGACY, MODERN, META_VERSION, META_CAPABILITIES, META_INFO, WORKFLOW_URI
from project_registry import ProjectRegistry


class McpTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = ProjectRegistry(Path(self.temp.name)/'home',standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        connections = Connections(self.registry)
        project = self.registry.create('Legacy scoped example')['id']
        invite = connections.invite(project,request_id='a'*32)
        self.connection = connections.enroll(invite['token'],'example','workspace')

    def request(self, method, params=None, *, modern=True, extra_headers=None, identifier=1):
        params = dict(params or {})
        headers = {'Accept':'application/json, text/event-stream','Authorization':'Bearer '+self.connection['token']}
        if modern:
            params.setdefault('_meta',{META_VERSION:MODERN,META_CAPABILITIES:{}})
            headers.update({'MCP-Protocol-Version':MODERN,'Mcp-Method':method})
            if method in ('tools/call','resources/read','prompts/get'):
                headers['Mcp-Name'] = params.get('uri') if method=='resources/read' else params.get('name','')
        else:
            headers['MCP-Protocol-Version'] = LEGACY[-1]
        headers.update(extra_headers or {})
        message = dict(jsonrpc='2.0',method=method,params=params)
        if identifier is not None:
            message['id'] = identifier
        return dispatch(self.registry,message,headers,'# Universal workflow\nExample workflow')

    def test_modern_discovery_and_tools_without_handshake(self):
        status, discovery = self.request('server/discover')
        self.assertEqual(status,200,discovery)
        result = discovery['result']
        self.assertEqual(result['resultType'],'complete')
        self.assertIn(MODERN,result['supportedVersions'])
        self.assertEqual(result['_meta'][META_INFO]['name'],'project-hub')
        status, listed = self.request('tools/list')
        self.assertEqual(status,200,listed)
        self.assertTrue(all('session' in item['inputSchema']['required'] for item in listed['result']['tools']))
        context_tool = next(item for item in listed['result']['tools'] if item['name']=='hub_context')
        self.assertNotIn('CODEX_THREAD_ID',context_tool['description'])
        self.assertIn('every call',context_tool['description'])
        self.assertEqual(context_tool['annotations'],dict(readOnlyHint=False,destructiveHint=False,openWorldHint=False))
        knowledge_tool = next(item for item in listed['result']['tools'] if item['name']=='hub_knowledge')
        self.assertNotIn('annotations',knowledge_tool,'Mixed source/research/edit capability keeps native consent')
        first = self.request('tools/call',dict(name='hub_context',arguments={'session':'first'}))[1]['result']['structuredContent']
        second = self.request('tools/call',dict(name='hub_context',arguments={'session':'second'}))[1]['result']['structuredContent']
        self.assertNotEqual(first['connection']['actor'],second['connection']['actor'])
        self.assertEqual(first['connection']['project'],second['connection']['project'])

    def test_legacy_initialize_and_notifications_keep_legacy_result_shape(self):
        status, initialized = self.request('initialize',dict(protocolVersion=LEGACY[-1],capabilities={},clientInfo=dict(name='Example',version='1')),modern=False)
        self.assertEqual(status,200,initialized)
        self.assertEqual(initialized['result']['protocolVersion'],LEGACY[-1])
        self.assertNotIn('resultType',initialized['result'])
        self.assertEqual(self.request('notifications/initialized',modern=False,identifier=None),(202,None))
        self.assertEqual(self.request('tools/list',modern=False)[0],200)
        self.assertEqual(self.request('resources/templates/list',modern=False)[1]['result'],{'resourceTemplates':[]})

    def test_required_metadata_header_matching_and_unknown_version_errors(self):
        cases = [
            ('tools/list',{'_meta':{META_VERSION:MODERN}}, {},-32602),
            ('tools/list',{}, {'Mcp-Method':'tools/call'},-32020),
            ('tools/call',{'name':'hub_context','arguments':{'session':'one'}},{'Mcp-Name':'hub_task'},-32020),
            ('tools/list',{'_meta':{META_VERSION:'2099-01-01',META_CAPABILITIES:{}}},{'MCP-Protocol-Version':'2099-01-01'},-32022),
        ]
        for method,params,headers,code in cases:
            with self.subTest(code=code):
                status,body = self.request(method,params,extra_headers=headers)
                self.assertEqual(status,400,body)
                self.assertEqual(body['error']['code'],code)
        self.assertEqual(self.request('tools/list',extra_headers={'Accept':'application/json'})[0],406)

    def test_resource_read_decodes_header_sentinel_and_publishes_workflow(self):
        encoded = '=?base64?'+base64.b64encode(WORKFLOW_URI.encode()).decode()+'?='
        status,body = self.request('resources/read',{'uri':WORKFLOW_URI},extra_headers={'Mcp-Name':encoded})
        self.assertEqual(status,200,body)
        self.assertIn('Universal workflow',body['result']['contents'][0]['text'])
        status,body = self.request('resources/read',{'uri':WORKFLOW_URI},extra_headers={'Mcp-Name':'=?base64?invalid!?='})
        self.assertEqual(status,400,body)
        self.assertEqual(body['error']['code'],-32020)

    def test_complete_api_reference_is_discoverable_and_matches_bundle(self):
        listed=self.request('resources/list')[1]['result']['resources']
        uri='project-hub://instructions/api-reference'
        self.assertIn(uri,{item['uri'] for item in listed})
        status,body=self.request('resources/read',{'uri':uri})
        self.assertEqual(status,200,body)
        from agent_instructions import bundle
        self.assertEqual(body['result']['contents'][0]['text'],bundle(self.registry)['instructionBundle']['files']['api-reference.md'])

    def test_credentials_and_duplicate_headers_are_rejected(self):
        self.assertEqual(self.request('tools/list',extra_headers={'Authorization':''})[0],401)
        self.assertEqual(self.request('tools/list',extra_headers={'Authorization':'Bearer invalid'})[0],401)
        status,body = self.request('tools/list',extra_headers={'mcp-method':'tools/list'})
        self.assertEqual(status,400,body)
        self.assertEqual(body['error']['code'],-32020)

    def test_modern_unsupported_methods_do_not_fall_back_to_legacy(self):
        for method in ('unknown/method','initialize'):
            with self.subTest(method=method):
                status,body = self.request(method)
                self.assertEqual(status,404,body)
                self.assertEqual(body['error']['code'],-32601)
        self.assertEqual(self.request('notifications/initialized',identifier=None)[0],400)

    def test_missing_conversation_is_a_tool_error_and_does_not_bind_ambient_identity(self):
        status,body = self.request('tools/call',dict(name='hub_context',arguments={}))
        self.assertEqual(status,200,body)
        self.assertTrue(body['result']['isError'])
        self.assertIn('identity_missing',body['result']['content'][0]['text'])
        self.assertFalse((self.registry.home/'coordination'/'coordination.sqlite3').exists())

    def test_global_mcp_discovery_and_typed_explicit_project_selection(self):
        connections = Connections(self.registry)
        self.connection = connections.enroll(connections.invite(request_id='b'*32)['token'],'unknown-host','global')
        listed = self.request('tools/list')[1]['result']['tools']
        self.assertIn('hub_projects',{item['name'] for item in listed})
        schema = next(item for item in listed if item['name']=='hub_context')['inputSchema']
        self.assertIn('project',schema['properties'])
        self.assertIn('workspace',schema['properties'])
        link = next(item for item in listed if item['name']=='hub_task_link')['inputSchema']
        self.assertEqual(link['properties']['project']['type'],['string','null'])
        self.assertIn('targetProject',link['properties'])
        projects = self.request('tools/call',dict(name='hub_projects',arguments={'session':'global-chat'}))[1]['result']['structuredContent']['projects']
        missing = self.request('tools/call',dict(name='hub_context',arguments={'session':'global-chat'}))[1]['result']
        self.assertTrue(missing['isError'])
        self.assertIn('project_required',missing['content'][0]['text'])
        context = self.request('tools/call',dict(name='hub_context',arguments={'session':'global-chat','project':projects[0]['id']}))[1]['result']['structuredContent']
        self.assertEqual(context['connection']['scope'],'global')
        self.assertEqual(context['connection']['project'],projects[0]['id'])


if __name__=='__main__':
    unittest.main()
