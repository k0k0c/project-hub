"""Exercise real onboarding, scoped HTTP calls and Streamable HTTP routes."""
import http.client
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_portal import PortalServer
from project_registry import ProjectRegistry
from mcp_transport import LEGACY


class AgentHttpTests(unittest.TestCase):
    def test_chatgpt_crypto_error_keeps_json_api_and_browser_repair_guidance_separate(self):
        from chatgpt_auth import AuthError, ChatGPTAuth
        failure=AuthError('chatgpt_crypto_unavailable',503)
        with patch.object(ChatGPTAuth,'catalog',side_effect=failure):
            status,result=self.request('/api/chatgpt-auth')
            self.assertEqual(status,503)
            self.assertEqual(result['error'],'chatgpt_crypto_unavailable')
        with patch.object(ChatGPTAuth,'callback',side_effect=failure):
            connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
            try:
                connection.request('GET','/auth/callback?state=private-state&code=private-code')
                response=connection.getresponse();body=response.read().decode()
                self.assertEqual(response.status,503)
                self.assertTrue(response.getheader('Content-Type').startswith('text/html'))
                self.assertIn('chatgpt_crypto_unavailable',body)
                self.assertNotIn('private-state',body)
                self.assertNotIn('private-code',body)
                self.assertIn('Восстановите компоненты Hub',body)
            finally:
                connection.close()

    def test_chatgpt_invalid_callback_has_localized_recovery_without_reflecting_secrets(self):
        import urllib.parse
        from ui_preferences import read, update
        self.enterContext(patch('secret_vault.private_home',return_value=Path(self.temp.name)/'private'))
        for language in ('ru','en'):
            preferences=read(self.registry)
            update(self.registry,dict(language=language,expected=preferences['revision']))
            connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
            try:
                query=urllib.parse.urlencode(dict(state='private-state',code='private-code',error_description='<script>private-body</script>'))
                connection.request('GET','/auth/callback?'+query)
                response=connection.getresponse()
                body=response.read().decode()
                self.assertEqual(response.status,400)
                self.assertTrue(response.getheader('Content-Type').startswith('text/html'))
                self.assertEqual(response.getheader('Cache-Control'),'no-store')
                self.assertEqual(response.getheader('Referrer-Policy'),'no-referrer')
                self.assertIn(f'lang="{language}"',body)
                self.assertIn('href="/#settings/agents/models"',body)
                self.assertIn('chatgpt_callback_invalid',body)
                for secret in ('private-state','private-code','private-body','<script>'):
                    self.assertNotIn(secret,body)
            finally:
                connection.close()

    def test_chatgpt_forget_roundtrip_has_local_guards_and_no_network(self):
        from chatgpt_auth import ChatGPTAuth
        with patch('secret_vault.private_home',return_value=Path(self.temp.name)/'private'):
            auth=ChatGPTAuth(self.registry)
            with auth._store() as store:
                store['accounts']['a'*32]=dict(id='a'*32,status='signed_out',email='remove@example.test')
                store['accounts']['b'*32]=dict(id='b'*32,status='signed_out',email='keep@example.test')
                auth._write(store)
            request=dict(action='forget',accountId='a'*32,requestId='c'*32)
            self.assertEqual(self.request('/api/v1/chatgpt-auth',request,headers={'Origin':'https://example.invalid'})[0],403)
            self.assertEqual(self.request('/api/v1/chatgpt-auth',request,headers={'Content-Type':'text/plain'})[0],415)
            with patch.object(ChatGPTAuth,'_call',side_effect=AssertionError('Forget must not call OpenAI')):
                status,result=self.request('/api/v1/chatgpt-auth',request)
                self.assertEqual(status,200,result)
                self.assertEqual(result,dict(accountId='a'*32,status='forgotten'))
                self.assertEqual(self.request('/api/v1/chatgpt-auth',request),(status,result))
            accounts=self.request('/api/chatgpt-auth')[1]['accounts']
            self.assertEqual([account['id'] for account in accounts],['b'*32])
            self.assertEqual(accounts[0]['label'],'keep@example.test')

    def test_chatgpt_auth_local_origin_content_type_and_safe_redirect(self):
        import urllib.parse
        from chatgpt_auth import ChatGPTAuth
        with patch('secret_vault.private_home',return_value=Path(self.temp.name)/'private'):
            start=dict(action='start',requestId='9'*32,networkMode='direct')
            self.assertEqual(self.request('/api/v1/chatgpt-auth',start,headers={'Origin':'https://example.invalid'})[0],403)
            self.assertEqual(self.request('/api/v1/chatgpt-auth',start,headers={'Content-Type':'text/plain'})[0],415)
            status,attempt=self.request('/api/v1/chatgpt-auth',start)
            self.assertEqual(status,200,attempt)
            self.assertEqual(self.request('/api/chatgpt-auth')[1],dict(accounts=[]))
            self.assertEqual(self.request('/api/chatgpt-auth?attemptId='+attempt['attemptId'])[1]['status'],'pending')
            connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            try:
                connection.request('GET',attempt['authorizePath'])
                response=connection.getresponse();response.read()
                self.assertEqual(response.status,303)
                location=urllib.parse.urlsplit(response.getheader('Location'))
                self.assertEqual(location.netloc,'auth.openai.com')
                query=urllib.parse.parse_qs(location.query)
                connection.request('GET','/auth/callback?'+urllib.parse.urlencode(dict(state=query['state'][0],error='access_denied')))
                response=connection.getresponse();response.read()
                self.assertEqual(response.status,303)
                self.assertEqual(response.getheader('Referrer-Policy'),'no-referrer')
                self.assertNotIn('state=',response.getheader('Location'))
            finally:connection.close()
            self.assertEqual(ChatGPTAuth(self.registry).attempt(attempt['attemptId'])['status'],'failed')

    def test_provider_probe_roundtrip_and_receipt_refresh_never_resends(self):
        _,catalog=self.request('/api/agent-providers')
        body=dict(action='save',expected=catalog['revision'],requestId='1'*32,name='Example service',
                  provider='responses',model='example-model',endpoint='',apiKey='private-test-key',networkMode='system')
        status,saved=self.request('/api/v1/agent-providers',body)
        self.assertEqual(status,200,saved)
        _,catalog=self.request('/api/agent-providers')
        self.assertEqual(catalog['items'][0]['networkMode'],'system')
        probe=dict(action='probe',id=saved['id'],expected=catalog['revision'],requestId='2'*32)
        with patch('provider_runtime.probe') as send:
            status,receipt=self.request('/api/v1/agent-providers',probe)
            self.assertEqual(status,200,receipt)
            self.assertEqual(receipt['status'],'completed')
            status,read=self.request('/api/agent-providers?requestId='+probe['requestId'])
            self.assertEqual(read,receipt)
            status,again=self.request('/api/v1/agent-providers',probe)
            self.assertEqual(again,receipt)
            self.assertEqual(send.call_count,1)
        self.assertNotIn('private-test-key',json.dumps(receipt))
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.registry=ProjectRegistry(Path(self.temp.name)/'home',standalone=True)
        self.server=PortalServer(('127.0.0.1',0),registry=self.registry)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,body=None,headers=None,raw=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            data=raw if raw is not None else None if body is None else json.dumps(body)
            c.request('GET' if data is None else 'POST',path,data,dict({'Content-Type':'application/json'},**(headers or {})))
            r=c.getresponse();data=r.read();return r.status,json.loads(data) if data else None
        finally:c.close()

    def connect(self):
        status,invite=self.request('/api/v1/connections',{'action':'invite','requestId':'a'*32})
        self.assertEqual(status,200,invite)
        path='/connect/'+invite['token']
        status,setup=self.request(path);self.assertEqual(status,200,setup)
        self.assertIn('native',setup['setupInstructions']);self.assertIn('Contract version: 5',setup['workflow'])
        self.assertEqual(setup['scope'],'global')
        self.assertNotIn('STDIO',setup['setupInstructions'])
        self.assertEqual(setup['localSetup']['transport'],'streamable-http')
        self.assertTrue(setup['localSetup']['sameMachineOnly'])
        self.assertEqual(setup['localSetup']['supportedNativeHosts'],['codex','cursor'])
        self.assertTrue(Path(setup['localSetup']['launcher'][-1]).is_file())
        self.assertTrue(Path(setup['localSetup']['privateConnectionDirectory']).is_absolute())
        payload=dict(invitation=setup['invitation'],client='unknown-example-host',externalId='connection-example',model='Client-reported model')
        status,connection=self.request('/api/v1/agent/enroll',payload);self.assertEqual(status,200,connection)
        self.assertEqual(self.request('/api/v1/agent/enroll',payload)[1],connection)
        self.assertEqual(self.registry.list()['projects'],[])
        self.project = self.registry.create('Explicitly registered example')['id']
        return invite,connection

    def test_one_link_enrollment_scoped_calls_and_catalog_revocation(self):
        invite,connection=self.connect();headers={'Authorization':'Bearer '+connection['token']}
        status,context=self.request('/api/v1/agent/call',{'tool':'hub_context','arguments':{'session':'new-conversation','project':self.project}},headers)
        self.assertEqual(status,200,context);self.assertEqual(context['connection']['project'],self.project)
        status,task=self.request('/api/v1/agent/call',{'tool':'hub_task','arguments':{'session':'new-conversation','project':self.project,'title':'Review','scope':['Inspect'],'acceptance':['Verified']}},headers)
        self.assertEqual(status,200,task);self.assertIn('task',task)
        catalog=self.request('/api/v1/connections')[1]
        self.assertNotIn(connection['token'],json.dumps(catalog));self.assertNotIn(invite['token'],json.dumps(catalog))
        self.assertIsNone(catalog['bindings'][0]['project'])
        self.assertEqual(catalog['bindings'][0]['scope'],'global')
        status,missing=self.request('/api/v1/agent/call',{'tool':'hub_context','arguments':{'session':'new-conversation'}},headers)
        self.assertEqual(status,409,missing);self.assertEqual(missing['error'],'project_required')
        self.assertEqual(self.request('/api/v1/connections',{'action':'revoke','id':connection['binding']})[0],200)
        self.assertEqual(self.request('/api/v1/agent/call',{'tool':'hub_context','arguments':{'session':'new-conversation'}},headers)[0],401)

    def test_mcp_jsonrpc_parse_method_and_origin_contracts(self):
        _,connection=self.connect();headers={'Authorization':'Bearer '+connection['token'],'Accept':'application/json, text/event-stream','MCP-Protocol-Version':LEGACY[-1]}
        status,body=self.request('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list'},headers)
        self.assertEqual(status,200,body);self.assertTrue(body['result']['tools'])
        self.assertEqual(self.request('/mcp')[0],405)
        self.assertEqual(self.request('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list'},dict(headers,Origin='https://example.invalid'))[0],403)
        for raw in ('broken','{"jsonrpc":"2.0","id":NaN,"method":"tools/list"}'):
            status,body=self.request('/mcp',headers=headers,raw=raw)
            self.assertEqual(status,400,body);self.assertEqual(body['error']['code'],-32700);self.assertIsNone(body['id'])
        status,body=self.request('/mcp',{'jsonrpc':'2.0','id':{},'method':'tools/list'},headers)
        self.assertEqual(status,400,body);self.assertIsNone(body['id'])

    def test_launch_documents_fit_the_transport_with_a_bounded_request(self):
        _,connection=self.connect();headers={'Authorization':'Bearer '+connection['token']}
        # JSON escaping of a valid Unicode article can exceed the old 160KB.
        body=dict(tool='hub_launch',arguments=dict(session='article-session',action='complete',requestId='0'*32,
                  nativeId='native-chat',result=dict(title='Article',markdown='Описание. '*5000)))
        status,result=self.request('/api/v1/agent/call',body,headers)
        self.assertEqual(status,404,result)
        self.assertEqual(result['error'],'launch_missing')
        self.assertEqual(self.request('/api/v1/agent/call',raw='x'*1_000_001,headers=headers)[0],413)

    def test_bound_plan_read_remains_available_during_snapshot_but_mutations_refuse(self):
        _,connection=self.connect();headers={'Authorization':'Bearer '+connection['token']}
        _,context=self.request('/api/v1/agent/call',{'tool':'hub_context','arguments':{'session':'one','project':self.project}},headers)
        _,created=self.request('/api/v1/agent/call',{'tool':'hub_task','arguments':{'session':'one','project':self.project,'title':'Example','scope':['Inspect'],'acceptance':['Verified']}},headers)
        from hub_backup import live_snapshot
        entered,release=threading.Event(),threading.Event()
        def snapshot():
            with live_snapshot(self.registry):
                entered.set()
                if not release.wait(10):raise AssertionError('Snapshot did not finish')
        with ThreadPoolExecutor(max_workers=1) as pool:
            operation=pool.submit(snapshot)
            try:
                self.assertTrue(entered.wait(8))
                started=time.monotonic()
                status,plan=self.request('/api/v1/agent/call',{'tool':'hub_plan','arguments':{'session':'one','project':self.project,'task':created['task']}},headers)
                self.assertEqual(status,200,plan)
                status,error=self.request('/api/v1/agent/call',{'tool':'hub_plan','arguments':{'session':'one','project':self.project,'task':created['task'],'stage':'inspect','title':'Inspect'}},headers)
                self.assertEqual(status,423,error);self.assertTrue(error['retryable'])
                self.assertLess(time.monotonic()-started,2)
            finally:release.set()
            operation.result(timeout=8)

    def test_global_artifact_upload_requires_selection_and_metadata_is_bounded(self):
        _,connection=self.connect();headers={'Authorization':'Bearer '+connection['token']}
        payload=dict(name='proof.txt',content='cHJvb2Y=')
        status,missing=self.request('/api/v1/agent/artifacts',payload,headers)
        self.assertEqual(status,409,missing);self.assertEqual(missing['error'],'project_required')
        status,uploaded=self.request('/api/v1/agent/artifacts',dict(payload,project=self.project),headers)
        self.assertEqual(status,200,uploaded)
        self.assertIn('source',uploaded)
        status,discovered=self.request('/api/v1/agent/call',dict(tool='hub_projects',arguments={'session':'own-conversation'}),headers)
        self.assertEqual(status,200,discovered)
        self.assertEqual(discovered['projects'][0]['id'],self.project)
        catalog=self.request('/api/v1/connections')[1]
        self.assertEqual(catalog['bindings'][0]['metadata']['model'],'Client-reported model')
        self.assertFalse(catalog['bindings'][0]['activity']['runningVerified'])


if __name__=='__main__':unittest.main()
