"""Private credential isolation, provider CAS, and durable exact operation retries."""
from pathlib import Path
from contextlib import contextmanager
import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
import threading
import io
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry
from agent_providers import Providers, ProviderError
from provider_runtime import RuntimeError as DriverError
import secret_vault

class ProviderTests(unittest.TestCase):
    def test_legacy_api_key_probe_fingerprint_survives_optional_auth_field(self):
        import hashlib
        from dataclasses import asdict
        from agent_providers import probe_settings_fingerprint,encoded
        from provider_runtime import Config
        self.providers.change(self.save_request())
        item=self.providers.selected()
        legacy=asdict(Config(**item['config']));legacy.pop('auth_method')
        expected=hashlib.sha256(encoded(dict(config=legacy,credentialId=item.get('credentialId',item['id']))).encode()).hexdigest()
        self.assertEqual(probe_settings_fingerprint(item),expected)
        item['config']['auth_method']='api_key'
        self.assertEqual(probe_settings_fingerprint(item),expected)

    def test_chatgpt_provider_is_separate_from_api_key_and_has_no_fallback(self):
        saved=self.providers.change(self.save_request())
        account=dict(id='a'*32,label='ChatGPT account',status='connected',planUsageEnabled=True,
                     generation=1,models=[dict(slug='plan-model',displayName='Plan model')])
        with patch('chatgpt_auth.ChatGPTAuth.account',return_value=account), \
             patch('chatgpt_auth.ChatGPTAuth.catalog',return_value=dict(accounts=[account])):
            body=dict(action='save-chatgpt',expected=self.providers.catalog()['revision'],requestId=uuid.uuid4().hex,
                name='ChatGPT',accountId=account['id'],model='plan-model',networkMode='direct')
            with patch('secret_vault.save',side_effect=AssertionError('OAuth wrote API key')):
                oauth=self.providers.change(body)
            self.assertEqual(self.providers.change(body),oauth)
            selected=self.providers.selected()
            self.assertEqual(selected['config']['auth_method'],'chatgpt_oauth')
            with patch('chatgpt_auth.ChatGPTAuth.access_token',return_value='oauth-access'):
                self.assertEqual(self.providers.credential(selected),'oauth-access')
            from chatgpt_auth import AuthError
            with patch('chatgpt_auth.ChatGPTAuth.access_token',side_effect=AuthError('chatgpt_sign_in_required')):
                with self.assertRaisesRegex(DriverError,'chatgpt_sign_in_required'):
                    self.providers.credential(selected)
            public=self.providers.catalog()
            self.assertEqual(public['items'][1]['authentication']['quotaSource'],'chatgpt_plan')
            with self.assertRaises(ProviderError):
                self.providers.change(dict(body,expected=public['revision'],requestId=uuid.uuid4().hex,model='unknown'))
            self.providers.change(dict(action='delete',id=oauth['id'],expected=public['revision'],requestId=uuid.uuid4().hex))
        api=next(item for item in self.providers.read()[0]['items'] if item['id']==saved['id'])
        self.assertEqual(self.providers.credential(api),'private-example-key')
        self.assertNotIn('oauth-access',json.dumps(self.providers.read()))

    def test_probe_access_source_and_latest_quota_status_survive_reload(self):
        saved=self.providers.change(self.save_request())
        item=self.providers.catalog()['items'][0]
        self.assertEqual(item['authentication'],dict(method='api_key',quotaSource='provider_api'))
        self.assertEqual(item['availability'],dict(status='not_checked'))
        before=self.providers.read()
        body=self.probe_request(saved['id'])
        error=urllib.error.HTTPError('https://api.example.invalid',429,'private',{},io.BytesIO(json.dumps(
            dict(error=dict(code='credit_balance_exhausted',type='insufficient_quota',message='private-example-key'))).encode()))
        opener=self.fake_opener(error=error)
        with patch('provider_runtime.opener_for',return_value=opener):
            result=self.providers.change(body)
            self.assertEqual(self.providers.change(body),result)
        reloaded=Providers(self.registry)
        check=reloaded.catalog()['items'][0]['availability']
        self.assertEqual(check['status'],'quota')
        self.assertEqual(check['requestId'],body['requestId'])
        self.assertEqual(check['providerErrorCode'],'credit_balance_exhausted')
        self.assertEqual(check['checkedAt'],result['updatedAt'])
        self.assertEqual(reloaded.probe_receipt(body['requestId']),result)
        self.assertEqual(self.providers.read(),before,'checks do not change provider settings or revision')
        self.assertEqual(self.providers.credential(self.providers.selected()),'private-example-key')
        self.assertNotIn('private-example-key',json.dumps(result)+json.dumps(reloaded.catalog()))
        self.assertEqual(len(opener.calls),1)

    def test_oauth_refresh_failure_keeps_saved_receipt_and_requests_sign_in(self):
        from chatgpt_auth import AuthError
        account=dict(id='a'*32,label='ChatGPT account',status='connected',planUsageEnabled=True,
            generation=1,models=[dict(slug='plan-model',displayName='Plan model')])
        with patch('chatgpt_auth.ChatGPTAuth.account',return_value=account), \
             patch('chatgpt_auth.ChatGPTAuth.catalog',return_value=dict(accounts=[account])):
            saved=self.providers.change(dict(action='save-chatgpt',expected=self.providers.catalog()['revision'],
                requestId=uuid.uuid4().hex,name='ChatGPT',accountId=account['id'],model='plan-model',networkMode='direct'))
            before=self.providers.read()
            request=self.probe_request(saved['id'])
            def refresh_failure(*args):
                account.update(status='refresh_unknown',planUsageEnabled=False)
                raise AuthError('chatgpt_network_error',diagnostic=dict(operation='oauth',oauthAction='token_refresh',
                    category='timeout',timeoutMs=60000,outcomeUnknown=True))
            with patch('chatgpt_auth.ChatGPTAuth.access_token',side_effect=refresh_failure), \
                 patch('provider_runtime.opener_for',side_effect=AssertionError('No model dispatch')):
                result=self.providers.change(request)
                self.assertEqual(self.providers.change(request),result)
            self.assertEqual(result['status'],'failed')
            current=self.providers.catalog()['items'][0]
            self.assertEqual(current['availability']['status'],'sign_in_required')
            self.assertEqual(current['availability']['requestId'],request['requestId'])
            self.assertEqual(self.providers.probe_receipt(request['requestId']),result)
            self.assertEqual(self.providers.read(),before,'authorization status never edits provider settings')

    def test_received_refresh_pending_is_recoverable_without_changing_provider_or_signing_in(self):
        from chatgpt_auth import AuthError
        account=dict(id='a'*32,label='Example account',status='connected',planUsageEnabled=True,
            generation=1,models=[dict(slug='plan-model',displayName='Plan model')])
        with patch('chatgpt_auth.ChatGPTAuth.account',return_value=account), \
             patch('chatgpt_auth.ChatGPTAuth.catalog',return_value=dict(accounts=[account])):
            saved=self.providers.change(dict(action='save-chatgpt',expected=self.providers.catalog()['revision'],
                requestId=uuid.uuid4().hex,name='ChatGPT',accountId=account['id'],model='plan-model',networkMode='direct'))
            before=self.providers.read()
            body=self.probe_request(saved['id'])
            def pending(*args):
                account.update(status='refresh_pending',planUsageEnabled=False)
                raise AuthError('chatgpt_refresh_pending',diagnostic=dict(operation='oauth',
                    oauthAction='identity_validation',identityReason='signing_key'))
            with patch('chatgpt_auth.ChatGPTAuth.access_token',side_effect=pending), \
                 patch('provider_runtime.opener_for',side_effect=AssertionError('Model dispatch before verification')):
                result=self.providers.change(body)
            self.assertEqual(self.providers.catalog()['items'][0]['availability']['status'],'auth_pending')
            self.assertEqual(result['error']['code'],'chatgpt_refresh_pending')
            self.assertEqual(result['diagnostics'][0]['identityReason'],'signing_key')
            self.assertEqual(self.providers.change(body),result)
            account.update(status='connected',planUsageEnabled=True)
            with patch('chatgpt_auth.ChatGPTAuth.access_token',return_value='rotated-access'), \
                 patch('provider_runtime.opener_for',return_value=self.fake_opener()):
                # OAuth Responses requires a streamed response; use the bounded
                # probe boundary here to isolate provider selection/recovery.
                with patch('provider_runtime.probe',return_value=None):
                    recovered=self.providers.change(self.probe_request(saved['id']))
            self.assertEqual(recovered['status'],'completed')
            self.assertEqual(self.providers.read(),before)

    def test_saved_check_is_invalidated_by_access_changes_but_not_name_or_default(self):
        for change in ('model','networkMode','apiKey'):
            with self.subTest(change=change):
                saved=self.providers.change(self.save_request())
                body=self.probe_request(saved['id'])
                with patch('provider_runtime.opener_for',return_value=self.fake_opener()):
                    result=self.providers.change(body)
                edit=self.edit_request(saved['id'],name='Renamed service')
                self.providers.change(edit)
                def check():return next(item for item in self.providers.catalog()['items'] if item['id']==saved['id'])['availability']
                self.assertEqual(check()['status'],'available')
                self.providers.change(dict(action='select',id='none',expected=self.providers.catalog()['revision'],requestId=uuid.uuid4().hex))
                self.assertEqual(check()['status'],'available')
                edit=self.edit_request(saved['id']);edit[change]={'model':'another-model','networkMode':'system','apiKey':'replacement-key'}[change]
                self.providers.change(edit)
                self.assertEqual(check(),dict(status='settings_changed'))
                self.assertEqual(self.providers.probe_receipt(body['requestId']),result,'history remains readable')

    def probe_request(self, identifier):
        return dict(action='probe',id=identifier,expected=self.providers.catalog()['revision'],requestId=uuid.uuid4().hex)

    def fake_opener(self, response=None, error=None, before=None):
        owner=self
        class Response:
            status=200
            headers={'X-Request-ID':'provider-request-1'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return json.dumps(response or dict(status='completed',output=[])).encode()[:limit]
        class Opener:
            calls=[]
            def open(self,request,timeout):
                self.calls.append(request)
                owner.assertEqual(timeout,60)
                if before:before(request)
                if error:raise error
                return Response()
        return Opener()

    def test_network_policy_edit_keeps_existing_key_and_legacy_read_is_nonmutating(self):
        saved=self.providers.change(self.save_request())
        with self.registry.connect() as c:
            value=self.providers.read(c)[0]
            del value['items'][0]['config']['network_mode']
            original=json.dumps(value)
            c.execute('UPDATE agent_provider_settings SET body=?',(original,));c.commit()
        self.assertEqual(self.providers.catalog()['items'][0]['networkMode'],'direct')
        with self.registry.connect() as c:self.assertEqual(c.execute('SELECT body FROM agent_provider_settings').fetchone()[0],original)
        with patch.object(secret_vault,'save',side_effect=AssertionError('Key was replaced')):
            edit=self.edit_request(saved['id']);edit['networkMode']='system';self.providers.change(edit)
        self.assertEqual(self.providers.catalog()['items'][0]['networkMode'],'system')
        self.assertEqual(self.providers.credential(self.providers.selected()),'private-example-key')

    def test_explicit_probe_reserves_receipt_before_dispatch_and_never_resends(self):
        saved=self.providers.change(self.save_request());body=self.probe_request(saved['id'])
        settings=self.providers.read()[0]
        def before(request):
            receipt=self.providers.probe_receipt(body['requestId'])
            self.assertEqual(receipt['status'],'running')
            self.assertEqual(receipt['diagnostics'][0]['status'],'running')
            self.assertEqual(self.providers.catalog()['items'][0]['availability']['status'],'checking')
            payload=json.loads(request.data)
            self.assertNotIn('tools',payload)
            self.assertEqual(payload['max_output_tokens'],16)
        opener=self.fake_opener(before=before)
        with patch('provider_runtime.opener_for',return_value=opener):
            first=self.providers.change(body)
            self.assertEqual(self.providers.change(body),first)
            self.assertEqual(Providers(self.registry).probe_receipt(body['requestId']),first)
        self.assertEqual(len(opener.calls),1)
        self.assertEqual(first['status'],'completed')
        self.assertEqual(first['diagnostics'][0]['upstreamRequestId'],'provider-request-1')
        self.assertNotIn('private-example-key',json.dumps(first))
        self.assertEqual(self.providers.read()[0],settings)

    def test_probe_unknown_outcome_and_restart_do_not_repeat_model_call(self):
        saved=self.providers.change(self.save_request());body=self.probe_request(saved['id'])
        opener=self.fake_opener(error=TimeoutError('private-example-key'))
        with patch('provider_runtime.opener_for',return_value=opener):
            first=self.providers.change(body)
            self.assertEqual(first['status'],'outcome_unknown')
            self.assertEqual(first['diagnostics'][0]['category'],'timeout')
            self.assertEqual(first['diagnostics'][0]['timeoutMs'],60000)
            self.assertEqual(first['diagnostics'][0]['phase'],'unknown')
            self.assertNotIn('httpStatus',first['diagnostics'][0])
            self.assertEqual(self.providers.change(body),first)
        interrupted=dict(first,status='running')
        with self.registry.connect() as c:
            c.execute('UPDATE agent_provider_requests SET result=? WHERE id=?',(json.dumps(interrupted),body['requestId']));c.commit()
        recovered=Providers(self.registry).probe_receipt(body['requestId'])
        self.assertEqual(recovered['status'],'outcome_unknown')
        self.assertEqual(recovered['error']['code'],'process_interrupted')
        with patch('provider_runtime.opener_for',side_effect=AssertionError('Duplicate model call')):
            self.assertEqual(self.providers.change(body),recovered)
        self.assertEqual(len(opener.calls),1)

    def test_same_probe_id_is_conflict_for_different_requests_and_parallel_sends_once(self):
        saved=self.providers.change(self.save_request());body=self.probe_request(saved['id'])
        entered=threading.Event();release=threading.Event()
        def before(request):entered.set();self.assertTrue(release.wait(5))
        opener=self.fake_opener(before=before)
        with patch('provider_runtime.opener_for',return_value=opener),ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(self.providers.change,body)
            try:
                self.assertTrue(entered.wait(5))
                other=Providers(self.registry)
                self.assertEqual(other.change(body)['status'],'running')
                with self.assertRaises(ProviderError) as caught:other.change(dict(body,id='different-provider'))
                self.assertEqual(caught.exception.body['error'],'provider_request_conflict')
            finally:release.set()
            self.assertEqual(future.result(timeout=5)['status'],'completed')
        self.assertEqual(len(opener.calls),1)

    def test_probe_stale_revision_and_changed_provider_do_not_claim_success(self):
        saved=self.providers.change(self.save_request());body=self.probe_request(saved['id'])
        with patch('provider_runtime.opener_for',side_effect=AssertionError('Unexpected request')):
            with self.assertRaises(ProviderError):self.providers.change(dict(body,expected='stale'))
        opener=self.fake_opener(before=lambda request:self.providers.change(self.edit_request(saved['id'],model='different-model')))
        with patch('provider_runtime.opener_for',return_value=opener):result=self.providers.change(body)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['error']['code'],'provider_revision_conflict')
        self.assertEqual(result['model'],'example-model')
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.registry=ProjectRegistry(Path(temporary.name)/'hub',standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        self.providers=Providers(self.registry)
    def save_request(self):
        return dict(action='save',expected=self.providers.catalog()['revision'],requestId=uuid.uuid4().hex,
            name='Example API',provider='responses',model='example-model',endpoint='',apiKey='private-example-key')
    def test_catalog_is_read_only_and_save_exact_retry_never_duplicates(self):
        self.assertEqual(self.providers.catalog()['default'],'none')
        with self.registry.connect() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_provider_settings'").fetchone())
        body=self.save_request(); saved=self.providers.change(body)
        self.assertEqual(self.providers.change(body),saved)
        self.assertEqual(len(self.providers.catalog()['items']),1)
        selected=self.providers.selected(); self.assertEqual(self.providers.credential(selected),body['apiKey'])
        with self.registry.connect() as c:
            data=c.execute('SELECT body FROM agent_provider_settings').fetchone()[0]
            requests=c.execute('SELECT fingerprint,result FROM agent_provider_requests').fetchall()
        self.assertNotIn(body['apiKey'],data+json.dumps([list(row) for row in requests]))
        self.assertFalse(secret_vault.private_home(self.registry).is_relative_to(self.registry.home))
        changed=dict(body,model='other')
        with self.assertRaises(ProviderError) as caught:self.providers.change(changed)
        self.assertEqual(caught.exception.status,409)
    def test_stale_request_and_invalid_protocol_write_no_credential(self):
        body=self.save_request();self.providers.change(body)
        with patch.object(secret_vault,'save',side_effect=AssertionError('Unexpected vault write')):
            with self.assertRaises(ProviderError):self.providers.change(dict(body,requestId=uuid.uuid4().hex))
            with self.assertRaises(DriverError):self.providers.change(dict(self.save_request(),provider='unsupported'))
        self.assertEqual(len(self.providers.catalog()['items']),1)
    def test_selection_uses_cas_and_durable_history_does_not_limit_reuse(self):
        saved=self.providers.change(self.save_request())
        for index in range(70):
            body=dict(action='select',expected=self.providers.catalog()['revision'],requestId=uuid.uuid4().hex,
                      id='none' if index%2 else saved['id'])
            result=self.providers.change(body)
        self.assertEqual(self.providers.change(body),result)
        self.assertIsNone(self.providers.selected())
    def test_missing_private_key_preserves_portable_metadata(self):
        self.providers.change(self.save_request()); selected=self.providers.selected()
        with patch.object(secret_vault,'read',return_value={}):
            with self.assertRaises(ValueError):self.providers.credential(selected)
        self.assertEqual(self.providers.selected(),selected)

    def edit_request(self, identifier, **changes):
        return dict(self.save_request(),id=identifier,apiKey='',**changes)

    def test_edit_preserves_identity_key_default_and_unrelated_configuration(self):
        first=self.providers.change(self.save_request())
        second=self.providers.change(dict(self.save_request(),name='Other API'))
        before=self.providers.read()[0]
        other=before['items'][1]
        with self.registry.connect() as c:
            before['items'][0]['config']['max_turns']=3
            before['customSetting']={'preserved':True}
            c.execute('UPDATE agent_provider_settings SET body=?',(json.dumps(before),))
            c.commit()
        body=self.edit_request(first['id']);body.update(name='Renamed',model='new-model')
        result=self.providers.change(body)
        self.assertEqual(result['id'],first['id'])
        self.assertEqual(self.providers.change(body),result)
        value,_=self.providers.read()
        self.assertEqual(value['items'][1],other)
        self.assertEqual(value['default'],second['id'])
        self.assertEqual(value['customSetting'],{'preserved':True})
        self.assertEqual(value['items'][0]['config']['max_turns'],3)
        self.assertEqual(self.providers.credential(value['items'][0]),'private-example-key')
        self.assertNotIn('apiKey',json.dumps(self.providers.catalog()))

    def test_changed_endpoint_or_protocol_requires_fresh_key(self):
        saved=self.providers.change(self.save_request())
        before=self.providers.catalog()
        for changes in ({'provider':'anthropic'},{'provider':'chat','endpoint':'https://example.test/v1'}):
            body=self.edit_request(saved['id']);body.update(changes)
            with patch.object(secret_vault,'save',side_effect=AssertionError('Unexpected key write')):
                with self.assertRaises(ProviderError) as caught:self.providers.change(body)
            self.assertEqual(caught.exception.body['error'],'provider_key_required')
            self.assertEqual(self.providers.catalog(),before)
        body=self.edit_request(saved['id']);body.update(provider='chat',endpoint='https://example.test/v1',apiKey='new-key')
        self.providers.change(body)
        self.assertEqual(self.providers.credential(self.providers.selected()),'new-key')
        self.assertEqual(self.providers.catalog()['items'][0]['id'],saved['id'])

    def test_delete_only_target_key_and_never_selects_another_provider(self):
        first=self.providers.change(self.save_request())
        second=self.providers.change(dict(self.save_request(),name='Other API',apiKey='other-key'))
        secret_vault.save(self.registry,'unrelated-client-control','control-key')
        body=dict(action='delete',expected=self.providers.catalog()['revision'],requestId=uuid.uuid4().hex,id=second['id'])
        result=self.providers.change(body)
        self.assertEqual(self.providers.change(body),result)
        self.assertEqual(self.providers.catalog()['default'],'none')
        self.assertEqual([item['id'] for item in self.providers.catalog()['items']],[first['id']])
        keys=secret_vault.read(self.registry)
        self.assertNotIn(second['id'],keys)
        self.assertEqual(keys[first['id']],'private-example-key')
        self.assertEqual(keys['unrelated-client-control'],'control-key')
        with self.assertRaises(ProviderError):self.providers.change(dict(body,requestId=uuid.uuid4().hex))

    def test_delete_after_key_replacement_removes_current_association(self):
        saved=self.providers.change(self.save_request())
        body=self.edit_request(saved['id']);body['apiKey']='replacement-key'
        self.providers.change(body)
        item=self.providers.selected()
        self.providers.change(dict(action='delete',id=saved['id'],expected=self.providers.catalog()['revision'],requestId=uuid.uuid4().hex))
        self.assertNotIn(item['credentialId'],secret_vault.read(self.registry))
        self.assertNotIn(saved['id'],secret_vault.read(self.registry))

    def test_failed_delete_commit_preserves_configuration_and_credential(self):
        saved=self.providers.change(self.save_request())
        before=self.providers.catalog()
        body=dict(action='delete',id=saved['id'],expected=before['revision'],requestId=uuid.uuid4().hex)
        connect=self.registry.connect

        class FailedCommit:
            def __init__(self, connection):self.connection=connection
            def __getattr__(self, name):return getattr(self.connection,name)
            def commit(self):raise sqlite3.OperationalError('injected metadata commit failure')

        @contextmanager
        def failing_connection():
            with connect() as connection:
                yield FailedCommit(connection)

        with patch.object(self.registry,'connect',side_effect=failing_connection), \
             patch.object(self.providers,'remove_credential',side_effect=AssertionError('Cleanup before commit')):
            with self.assertRaises(sqlite3.OperationalError):self.providers.change(body)
        self.assertEqual(self.providers.catalog(),before)
        self.assertEqual(self.providers.credential(self.providers.selected()),'private-example-key')
        with self.registry.connect() as connection:
            self.assertIsNone(connection.execute('SELECT 1 FROM agent_provider_requests WHERE id=?',(body['requestId'],)).fetchone())
            self.assertEqual(connection.execute('SELECT count(*) FROM agent_provider_cleanup').fetchone()[0],0)
        result=self.providers.change(body)
        self.assertEqual(self.providers.change(body),result)
        self.assertEqual(self.providers.catalog()['items'],[])
        self.assertNotIn(saved['id'],secret_vault.read(self.registry))

    def test_delete_replay_finishes_durable_interrupted_cleanup(self):
        saved=self.providers.change(self.save_request())
        secret_vault.save(self.registry,'unrelated-control-key','keep-this-key')
        body=dict(action='delete',id=saved['id'],expected=self.providers.catalog()['revision'],requestId=uuid.uuid4().hex)
        with patch.object(self.providers,'remove_credential',side_effect=OSError('vault temporarily unavailable')):
            result=self.providers.change(body)
        self.assertEqual(self.providers.catalog()['items'],[])
        self.assertIn(saved['id'],secret_vault.read(self.registry))
        self.assertNotIn(saved['id'],json.dumps(self.providers.catalog()))
        with self.registry.connect() as connection:
            self.assertEqual(connection.execute('SELECT id FROM agent_provider_cleanup').fetchone()[0],saved['id'])
        self.assertEqual(self.providers.change(body),result)
        self.assertNotIn(saved['id'],secret_vault.read(self.registry))
        self.assertEqual(secret_vault.get(self.registry,'unrelated-control-key'),'keep-this-key')
        with self.registry.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM agent_provider_cleanup').fetchone()[0],0)

if __name__=='__main__':unittest.main()
