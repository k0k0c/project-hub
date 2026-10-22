import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager, nullcontext
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chatgpt_auth
import secret_vault


class ChatGPTAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.private = Path(self.temp.name) / 'private'
        self.private.mkdir()
        self.registry = SimpleNamespace(home=Path(self.temp.name) / 'hub')
        self.registry.home.mkdir()
        @contextmanager
        def connect():
            connection = sqlite3.connect(':memory:')
            try:
                yield connection
            finally:
                connection.close()
        self.registry.connect = connect
        self.now = [1_700_000_000.0]
        self.private_home_patch = patch.object(secret_vault, 'private_home', side_effect=self.private_home)
        self.private_home_patch.start()
        self.addCleanup(self.private_home_patch.stop)
        self.auth = chatgpt_auth.ChatGPTAuth(
            self.registry, clock=lambda: self.now[0], verify=self.verify
        )
        self.identity = {'sub': 'subject-1', 'email': 'person@example.test', 'name': 'Person'}

    def tearDown(self):
        self.temp.cleanup()

    def private_home(self, registry):
        return self.private

    def verify(self, token, client_id, nonce, jwks, *, subject=None):
        if subject is not None and subject != self.identity['sub']:
            raise chatgpt_auth.AuthError('chatgpt_identity_invalid')
        return dict(self.identity)

    def patch_private(self):
        return patch.object(secret_vault, 'private_home', side_effect=self.private_home)

    def exchange_call(self, models=None, refresh=False):
        calls = []
        models = models or [{'visibility': 'list', 'slug': 'o4-mini', 'display_name': 'o4-mini'}]

        def call(url, **kwargs):
            calls.append((url, kwargs))
            if url == chatgpt_auth.DISCOVERY:
                return {'issuer': chatgpt_auth.ISSUER, 'authorization_endpoint': chatgpt_auth.AUTHORIZE,
                        'token_endpoint': chatgpt_auth.TOKEN, 'jwks_uri': chatgpt_auth.ISSUER + '/.well-known/jwks.json',
                        'revocation_endpoint': chatgpt_auth.ISSUER + '/oauth/revoke'}
            if url.endswith('/.well-known/jwks.json'):
                return {'keys': []}
            if url == chatgpt_auth.TOKEN:
                if kwargs.get('form', {}).get('grant_type') == 'refresh_token':
                    return {'access_token': 'access-rotated', 'refresh_token': 'refresh-rotated',
                            'token_type': 'Bearer', 'expires_in': 3600, 'scope': chatgpt_auth.SCOPES}
                return {'access_token': 'access-initial', 'refresh_token': 'refresh-initial',
                        'id_token': 'id-token', 'token_type': 'Bearer', 'expires_in': 3600,
                        'scope': chatgpt_auth.SCOPES}
            if url == chatgpt_auth.RESOURCE + '/models':
                return {'models': models}
            return {}

        return calls, call

    def start(self, account_id=None, request_id='a' * 32, mode='direct'):
        body = {'action': 'start', 'requestId': request_id, 'networkMode': mode}
        if account_id:
            body['accountId'] = account_id
        return self.auth.start(body, 8769)

    def test_fresh_pkce_exchange_models_and_catalog_sanitizes_tokens(self):
        calls, fake_call = self.exchange_call()
        with self.patch_private(), patch.object(self.auth, '_call', side_effect=fake_call):
            started = self.start()
            self.assertEqual(started['status'], 'pending')
            query = parse_qs(urlsplit(self.auth.authorization_url(started['attemptId'])).query)
            self.assertEqual(query['response_type'], ['code'])
            self.assertEqual(query['code_challenge_method'], ['S256'])
            self.assertEqual(query['redirect_uri'], ['http://127.0.0.1:8769/auth/callback'])
            self.assertNotIn('id_token_hint', query)
            self.assertNotIn('access_token', query)
            result = self.auth.callback({'state': [self._state(started['attemptId'])],
                                         'code': ['one-use-code'], 'client_id': ['client-1']}, 8769)
            self.assertEqual(result['status'], 'completed')
            account = self.auth.catalog()['accounts'][0]
            self.assertEqual(account['status'], 'connected')
            self.assertEqual(account['models'], [{'slug': 'o4-mini', 'displayName': 'o4-mini'}])
            rendered = json.dumps(self.auth.catalog())
            self.assertNotIn('access-initial', rendered)
            self.assertNotIn('refresh-initial', rendered)
            self.assertNotIn('id-token', rendered)
            self.assertTrue(any(url == chatgpt_auth.RESOURCE + '/models' for url, _ in calls))

    def test_sign_in_status_waits_for_model_discovery_before_browser_refresh(self):
        calls,fake_call=self.exchange_call()
        started=self.start()
        during=[]
        def observe(url,**kwargs):
            if url==chatgpt_auth.RESOURCE+'/models':
                during.append(self.auth.attempt(started['attemptId'])['status'])
                with self.auth._store() as store:
                    self.assertNotIn('state',store['attempts'][started['attemptId']])
                    self.assertNotIn('verifier',store['attempts'][started['attemptId']])
            return fake_call(url,**kwargs)
        with patch.object(self.auth,'_call',side_effect=observe):
            result=self.auth.callback(dict(state=[self._state(started['attemptId'])],code=['code'],client_id=['client']),8769)
        self.assertEqual(during,['pending'])
        self.assertEqual(result['status'],'completed')
        self.assertTrue(self.auth.account(result['accountId'])['models'])

    def _state(self, attempt_id):
        with self.auth._store() as store:
            return store['attempts'][attempt_id]['state']

    def test_duplicate_callback_cancel_expiry_port_and_denied_scope(self):
        with self.patch_private():
            first = self.start()
            state = self._state(first['attemptId'])
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_callback_invalid'):
                self.auth.callback({'state': [state], 'code': ['code'], 'client_id': ['client']}, 9999)
            cancelled = self.auth.cancel(first['attemptId'])
            self.assertEqual(cancelled['status'], 'cancelled')
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_callback_invalid'):
                self.auth.callback({'state': [state], 'code': ['code'], 'client_id': ['client']}, 8769)

            denied = self.start(request_id='b' * 32)
            denied_result = self.auth.callback({'state': [self._state(denied['attemptId'])],
                                                'error': ['access_denied']}, 8769)
            self.assertEqual(denied_result['status'], 'failed')
            self.assertEqual(denied_result['error']['code'], 'chatgpt_consent_declined')

            expired = self.start(request_id='c' * 32)
            self.now[0] += 601
            self.assertEqual(self.auth.attempt(expired['attemptId'])['status'], 'expired')
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_attempt_expired'):
                self.auth.authorization_url(expired['attemptId'])

            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_invalid_request'):
                self.auth.start({'action': 'start', 'requestId': 'd' * 32,
                                 'networkMode': 'direct'}, 0)

    def test_returning_subject_mismatch_preserves_previous_session(self):
        calls, fake_call = self.exchange_call()
        with self.patch_private(), patch.object(self.auth, '_call', side_effect=fake_call):
            first = self.start()
            self.auth.callback({'state': [self._state(first['attemptId'])], 'code': ['code'],
                                'client_id': ['client-1']}, 8769)
            account_id = self.auth.catalog()['accounts'][0]['id']
            with self.auth._store() as store:
                store['accounts'][account_id]['subject'] = 'old-subject'
                self.auth._write(store)
            retry = self.start(account_id=account_id, request_id='e' * 32)
            hints=parse_qs(urlsplit(self.auth.authorization_url(retry['attemptId'])).query)
            self.assertEqual(hints['client_id'],['client-1'])
            self.assertEqual(hints['id_token_hint'],['id-token'])
            self.assertEqual(hints['login_hint'],['person@example.test'])
            self.assertNotIn('agent_name_hint',hints)
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_refresh_pending'):
                self.auth.callback({'state': [self._state(retry['attemptId'])], 'code': ['code'],
                                    'client_id': ['client-1']}, 8769)
            with self.auth._store() as store:
                account = store['accounts'][account_id]
                self.assertEqual(account['access_token'], 'access-initial')
                self.assertEqual(account['refresh_token'], 'refresh-initial')
                self.assertEqual(account['subject'], 'old-subject')

    def test_returning_attempts_same_generation_redeem_only_the_first_code(self):
        calls, fake_call = self.exchange_call()
        with self.patch_private(), patch.object(self.auth, '_call', side_effect=fake_call):
            first = self.start(request_id='2' * 32)
            self.auth.callback({'state': [self._state(first['attemptId'])], 'code': ['code'],
                                'client_id': ['client-1']}, 8769)
            account_id = self.auth.catalog()['accounts'][0]['id']
            one = self.start(account_id=account_id, request_id='3' * 32)
            two = self.start(account_id=account_id, request_id='4' * 32)
            self.auth.callback({'state': [self._state(one['attemptId'])], 'code': ['code-one'],
                                'client_id': ['client-1']}, 8769)
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_attempt_changed'):
                self.auth.callback({'state': [self._state(two['attemptId'])], 'code': ['code-two'],
                                    'client_id': ['client-1']}, 8769)
            token_calls = [entry for entry in calls if entry[0] == chatgpt_auth.TOKEN]
            self.assertEqual(len(token_calls), 2)
            self.assertEqual(token_calls[1][1]['form']['code'], 'code-one')

    def test_same_email_registrations_have_separate_client_ids(self):
        calls, fake_call = self.exchange_call()
        identities = iter(({'sub': 'one', 'email': 'same@example.test'},
                           {'sub': 'two', 'email': 'same@example.test'}))
        with self.patch_private(), patch.object(self.auth, '_call', side_effect=fake_call):
            original = self.auth.verify
            self.auth.verify = lambda *args, **kwargs: next(identities)
            for request_id, client_id in (('f' * 32, 'client-one'), ('1' * 32, 'client-two')):
                started = self.start(request_id=request_id)
                self.auth.callback({'state': [self._state(started['attemptId'])], 'code': ['code'],
                                    'client_id': [client_id]}, 8769)
            accounts = self.auth.catalog()['accounts']
            self.assertEqual({item['email'] for item in accounts}, {'same@example.test'})
            self.assertEqual(len({item['id'] for item in accounts}), 2)
            with self.auth._store() as store:
                self.assertEqual({item['client_id'] for item in store['accounts'].values()},
                                 {'client-one', 'client-two'})

    def test_refresh_rotates_once_and_orphan_refresh_intent_is_unknown(self):
        calls, fake_call = self.exchange_call()
        with self.patch_private(), patch.object(self.auth, '_call', side_effect=fake_call):
            with self.auth._store() as store:
                store['accounts']['a' * 32] = self._connected('a' * 32, expires=self.now[0] - 1)
                self.auth._write(store)
            self.assertEqual(self.auth.access_token('a' * 32), 'access-rotated')
            token_calls = [entry for entry in calls if entry[0] == chatgpt_auth.TOKEN]
            self.assertEqual(len(token_calls), 1)
            self.assertEqual(self.auth.access_token('a' * 32), 'access-rotated')
            self.assertEqual(len([entry for entry in calls if entry[0] == chatgpt_auth.TOKEN]), 1)
            with self.auth._store() as store:
                store['accounts']['a' * 32]['expiresAt'] = self.now[0] - 1
                store['accounts']['a' * 32]['refreshIntent'] = True
                self.auth._write(store)
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_refresh_unknown'):
                self.auth.access_token('a' * 32)
            self.assertEqual(self.auth.account('a' * 32)['status'], 'refresh_unknown')

    def _connected(self, account_id, expires):
        return {'id': account_id, 'client_id': 'client', 'subject': 'subject-1', 'email': 'person@example.test',
                'status': 'connected', 'scopes': chatgpt_auth.SCOPES.split(), 'access_token': 'secret-access',
                'refresh_token': 'secret-refresh', 'id_token': 'secret-id', 'expiresAt': expires,
                'generation': 1, 'networkMode': 'direct'}

    def catalog_opener(self, payload):
        raw=json.dumps(payload).encode() if isinstance(payload,dict) else payload
        calls=[]
        class Response:
            status=200
            headers={'Content-Type':'application/json','X-Request-ID':'catalog-response'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):
                calls.append(limit)
                return raw[:limit]
        class Opener:
            def open(self,request,timeout):return Response()
        return Opener(),calls

    def test_large_account_catalog_is_read_but_only_picker_metadata_is_saved(self):
        with self.auth._store() as store:
            store['accounts']['a'*32]=self._connected('a'*32,self.now[0]+3600)
            self.auth._write(store)
        payload=dict(models=[dict(slug='plan-model',display_name='Plan model',visibility='list',
                                  base_instructions='private-model-instructions-'+'x'*700_000),
                             dict(slug='hidden-model',display_name='Hidden model',visibility='hide')])
        opener,reads=self.catalog_opener(payload)
        with patch('chatgpt_auth.opener_for',return_value=opener):
            catalog=self.auth.models('a'*32)
        account=catalog['accounts'][0]
        self.assertEqual(reads,[chatgpt_auth.MODEL_CATALOG_LIMIT+1])
        self.assertEqual(account['models'],[dict(slug='plan-model',displayName='Plan model')])
        self.assertTrue(account['planUsageEnabled'])
        self.assertIsNone(account['modelsError'])
        self.assertIsNone(account['modelsDiagnostic'])
        self.assertLess(self.auth.path.stat().st_size,20_000)
        self.assertNotIn('private-model-instructions',json.dumps(self.auth._read()))
        self.assertNotIn('secret-access',json.dumps(catalog))

    def test_catalog_limit_failure_retains_sign_in_and_safe_reason_until_successful_retry(self):
        with self.auth._store() as store:
            store['accounts']['a'*32]=self._connected('a'*32,self.now[0]+3600)
            self.auth._write(store)
        opener,_=self.catalog_opener(b'x'*(chatgpt_auth.MODEL_CATALOG_LIMIT+1))
        with patch('chatgpt_auth.opener_for',return_value=opener):
            with self.assertRaises(chatgpt_auth.AuthError):self.auth.models('a'*32)
        account=self.auth.account('a'*32)
        self.assertEqual(account['status'],'connected')
        self.assertEqual(account['modelsDiagnostic']['category'],'response_limit')
        self.assertEqual(account['modelsDiagnostic']['httpStatus'],200)
        self.assertEqual(account['modelsDiagnostic']['upstreamRequestId'],'catalog-response')
        self.assertNotIn('x'*100,json.dumps(account))
        opener,_=self.catalog_opener(dict(models=[dict(slug='available-model',display_name='Available',visibility='list')]))
        with patch('chatgpt_auth.opener_for',return_value=opener):self.auth.models('a'*32)
        self.assertIsNone(self.auth.account('a'*32)['modelsDiagnostic'])
        self.assertIsNone(self.auth.account('a'*32)['modelsError'])

    def test_catalog_budget_does_not_expand_oidc_document_budget(self):
        opener,reads=self.catalog_opener(b'x'*512_001)
        with patch('chatgpt_auth.opener_for',return_value=opener):
            with self.assertRaises(chatgpt_auth.AuthError):self.auth._call(chatgpt_auth.DISCOVERY)
        self.assertEqual(reads,[512_001])

    def test_catalog_diagnostics_exclude_body_and_credential_echo(self):
        with self.auth._store() as store:
            store['accounts']['a'*32]=self._connected('a'*32,self.now[0]+3600)
            self.auth._write(store)
        error=chatgpt_auth.AuthError('chatgpt_network_error',diagnostic=dict(category='parse',httpStatus=200,
            host='secret-access.example',upstreamRequestId='secret-refresh',message='private-body',response='private-body'))
        with patch.object(self.auth,'_call',side_effect=error):
            with self.assertRaises(chatgpt_auth.AuthError):self.auth.models('a'*32)
        diagnostic=self.auth.account('a'*32)['modelsDiagnostic']
        self.assertEqual(diagnostic,dict(category='parse',httpStatus=200))
        self.assertNotIn('private-body',json.dumps(self.auth._read()))

    def test_identity_without_plan_scope_never_discovers_models_or_supplies_token(self):
        calls,fake_call=self.exchange_call()
        def limited(url,**kwargs):
            reply=fake_call(url,**kwargs)
            if url==chatgpt_auth.TOKEN:
                reply['scope']='openid profile email'
            return reply
        with patch.object(self.auth,'_call',side_effect=limited):
            started=self.start()
            self.auth.callback(dict(state=[self._state(started['attemptId'])],code=['code'],client_id=['client']),8769)
            account=self.auth.catalog()['accounts'][0]
            self.assertEqual(account['status'],'plan_disabled')
            self.assertFalse(account['planUsageEnabled'])
            self.assertFalse(any(url==chatgpt_auth.RESOURCE+'/models' for url,_ in calls))
            with self.assertRaises(chatgpt_auth.AuthError):self.auth.access_token(account['id'])

    def test_refresh_unknown_is_recorded_and_never_replayed(self):
        with self.auth._store() as store:
            store['accounts']['a'*32]=self._connected('a'*32,self.now[0]-1)
            self.auth._write(store)
        error=chatgpt_auth.AuthError('chatgpt_network_error',diagnostic=dict(outcomeUnknown=True))
        with patch.object(self.auth,'_call',side_effect=error) as call:
            for _ in range(2):
                with self.assertRaises(chatgpt_auth.AuthError):self.auth.access_token('a'*32)
            self.assertEqual(call.call_count,1)
        self.assertEqual(self.auth.account('a'*32)['status'],'refresh_unknown')

    def test_refresh_timeout_records_step_and_budget_without_resending_or_erasing_tokens(self):
        with self.auth._store() as store:
            original=self._connected('a'*32,self.now[0]-1)
            store['accounts']['a'*32]=original
            self.auth._write(store)
        calls=[]
        class Opener:
            def open(self,request,timeout):
                calls.append((request,timeout))
                raise TimeoutError('secret-refresh')
        with patch('chatgpt_auth.opener_for',return_value=Opener()):
            with self.assertRaises(chatgpt_auth.AuthError) as caught:self.auth.access_token('a'*32)
            diagnostic=caught.exception.diagnostic
            self.assertEqual(diagnostic['operation'],'oauth')
            self.assertEqual(diagnostic['oauthAction'],'token_refresh')
            self.assertEqual(diagnostic['timeoutMs'],60000)
            self.assertTrue(diagnostic['outcomeUnknown'])
            with self.assertRaises(chatgpt_auth.AuthError):self.auth.access_token('a'*32)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1],60)
        with self.auth._store() as store:
            saved=store['accounts']['a'*32]
            self.assertEqual(saved['status'],'refresh_unknown')
            self.assertNotIn('refreshIntent',saved)
            for field in ('access_token','refresh_token','id_token','client_id','generation'):
                self.assertEqual(saved[field],original[field])
        self.assertNotIn('secret-refresh',json.dumps(diagnostic))

    def test_identity_network_failure_retains_response_and_recovers_after_restart_without_refresh_replay(self):
        with self.auth._store() as store:
            original = self._connected('a'*32, self.now[0]-1)
            store['accounts']['a'*32] = original
            self.auth._write(store)
        reply = dict(access_token='rotated-access', refresh_token='rotated-refresh',
            id_token='new-id', token_type='Bearer', expires_in=3600, scope=chatgpt_auth.SCOPES)
        error = chatgpt_auth.AuthError('chatgpt_network_error', diagnostic=dict(
            operation='oauth', oauthAction='discovery', category='tls', outcomeUnknown=False))
        with patch.object(self.auth, '_call', return_value=reply) as call, \
             patch.object(self.auth, '_identity', side_effect=error):
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_refresh_pending'):
                self.auth.access_token('a'*32)
            self.assertEqual(self.auth.account('a'*32)['status'], 'refresh_pending')
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_refresh_pending'):
                self.auth.access_token('a'*32)
            self.assertEqual(call.call_count, 1)
        with self.auth._store() as store:
            for field in ('access_token', 'refresh_token', 'id_token'):
                self.assertEqual(store['accounts']['a'*32][field], original[field])
            self.assertEqual(store['accounts']['a'*32]['refreshPending']['tokens']['refresh_token'],'rotated-refresh')
            self.assertNotIn('refreshIntent',store['accounts']['a'*32])
        public=json.dumps(self.auth.catalog())
        self.assertNotIn('rotated-refresh',public)
        self.assertNotIn('rotated-access',public)
        self.assertNotIn('new-id',public)
        restarted=chatgpt_auth.ChatGPTAuth(self.registry,clock=lambda:self.now[0],verify=self.verify)
        with patch.object(restarted,'_identity',return_value=dict(sub='subject-1')), \
             patch.object(restarted,'_call',side_effect=AssertionError('The token exchange must not be replayed')):
            self.assertEqual(restarted.access_token('a'*32),'rotated-access')
            self.assertEqual(restarted.access_token('a'*32),'rotated-access')
        with restarted._store() as store:
            self.assertNotIn('refreshPending',store['accounts']['a'*32])
            self.assertEqual(store['accounts']['a'*32]['refresh_token'],'rotated-refresh')
            self.assertEqual(store['accounts']['a'*32]['status'],'connected')

    def test_rejected_pending_identity_never_activates_or_resends_credentials(self):
        with self.auth._store() as store:
            original=self._connected('a'*32,self.now[0]-1)
            store['accounts']['a'*32]=original
            self.auth._write(store)
        reply=dict(access_token='untrusted-access',refresh_token='rotated-refresh',id_token='wrong-identity',
            token_type='Bearer',expires_in=3600,scope=chatgpt_auth.SCOPES)
        error=chatgpt_auth.AuthError('chatgpt_identity_invalid',diagnostic=dict(operation='oauth',
            oauthAction='identity_validation',identityReason='subject'))
        with patch.object(self.auth,'_call',return_value=reply) as call, \
             patch.object(self.auth,'_identity',side_effect=error):
            for _ in range(2):
                with self.assertRaisesRegex(chatgpt_auth.AuthError,'chatgpt_refresh_pending') as failure:
                    self.auth.access_token('a'*32)
                self.assertEqual(failure.exception.diagnostic['identityReason'],'subject')
            self.assertEqual(call.call_count,1)
        with self.auth._store() as store:
            self.assertEqual(store['accounts']['a'*32]['access_token'],original['access_token'])
        self.assertFalse(self.auth.account('a'*32)['planUsageEnabled'])

    def test_received_pending_response_survives_interruption_before_validation(self):
        with self.auth._store() as store:
            store['accounts']['a'*32]=self._connected('a'*32,self.now[0]-1)
            self.auth._write(store)
        reply=dict(access_token='new-access',refresh_token='new-refresh',token_type='Bearer',expires_in=3600)
        with patch.object(self.auth,'_call',return_value=reply), \
             patch.object(self.auth,'_complete_refresh',side_effect=SystemExit):
            with self.assertRaises(SystemExit):self.auth.access_token('a'*32)
        with patch.object(self.auth,'_call',side_effect=AssertionError('Repeated refresh')):
            self.assertEqual(self.auth.access_token('a'*32),'new-access')
        with self.auth._store() as store:
            self.assertEqual(store['accounts']['a'*32]['id_token'],'secret-id')

    def test_successive_expirations_rotate_the_latest_refresh_without_sign_in(self):
        with self.auth._store() as store:
            store['accounts']['a'*32]=self._connected('a'*32,self.now[0]-1)
            self.auth._write(store)
        refreshes=[]
        def rotate(url,**kwargs):
            self.assertEqual(url,chatgpt_auth.TOKEN)
            refreshes.append(kwargs['form']['refresh_token'])
            n=len(refreshes)
            return dict(access_token='access-'+str(n),refresh_token='refresh-'+str(n),
                token_type='Bearer',expires_in=3600,scope=chatgpt_auth.SCOPES)
        with patch.object(self.auth,'_call',side_effect=rotate):
            for n in range(1,4):
                self.assertEqual(self.auth.access_token('a'*32),'access-'+str(n))
                self.now[0]+=3601
        self.assertEqual(refreshes,['secret-refresh','refresh-1','refresh-2'])

    def test_short_lived_valid_reply_does_not_loop_refresh_exchanges(self):
        with self.auth._store() as store:
            store['accounts']['a'*32]=self._connected('a'*32,self.now[0]-1)
            self.auth._write(store)
        reply=dict(access_token='short-access',refresh_token='short-refresh',token_type='Bearer',expires_in=60)
        with patch.object(self.auth,'_call',return_value=reply) as call:
            self.assertEqual(self.auth.access_token('a'*32),'short-access')
            self.assertEqual(call.call_count,1)

    def test_successful_returning_sign_in_clears_an_old_pending_refresh(self):
        calls,fake_call=self.exchange_call()
        with patch.object(self.auth,'_call',side_effect=fake_call):
            with self.auth._store() as store:
                account=self._connected('a'*32,self.now[0]-1)
                account.update(status='refresh_pending',refreshPending=dict(tokens=dict(refresh_token='old-pending')))
                store['accounts']['a'*32]=account;self.auth._write(store)
            started=self.start(account_id='a'*32)
            self.auth.callback(dict(state=[self._state(started['attemptId'])],code=['code']),8769)
        with self.auth._store() as store:
            account=store['accounts']['a'*32]
            self.assertEqual(account['status'],'connected')
            self.assertEqual(account['access_token'],'access-initial')
            self.assertNotIn('refreshPending',account)

    def test_sign_in_received_response_can_resume_verification_without_redeeming_code_again(self):
        calls,fake_call=self.exchange_call()
        diagnostic=dict(operation='oauth',oauthAction='identity_validation',identityReason='signing_key')
        with patch.object(self.auth,'_call',side_effect=fake_call):
            started=self.start()
            with patch.object(self.auth,'_identity',side_effect=chatgpt_auth.AuthError('chatgpt_identity_invalid',diagnostic=diagnostic)):
                with self.assertRaisesRegex(chatgpt_auth.AuthError,'chatgpt_refresh_pending'):
                    self.auth.callback(dict(state=[self._state(started['attemptId'])],code=['code'],client_id=['client-1']),8769)
            failed=self.auth.attempt(started['attemptId'])
            self.assertEqual(failed['error']['diagnostic']['identityReason'],'signing_key')
            self.assertNotIn('access-initial',json.dumps(failed))
            account_id=failed['accountId']
            self.assertEqual(self.auth.account(account_id)['status'],'refresh_pending')
            self.assertEqual(self.auth.access_token(account_id),'access-initial')
            self.assertEqual(self.auth.attempt(started['attemptId'])['status'],'completed')
        self.assertEqual(len([c for c in calls if c[0]==chatgpt_auth.TOKEN]),1)

    def test_cancelled_received_sign_in_cannot_activate_a_pending_response(self):
        calls,fake_call=self.exchange_call()
        with patch.object(self.auth,'_call',side_effect=fake_call):
            started=self.start()
            with patch.object(self.auth,'_complete_refresh',side_effect=SystemExit):
                with self.assertRaises(SystemExit):
                    self.auth.callback(dict(state=[self._state(started['attemptId'])],code=['code'],client_id=['client-1']),8769)
            self.auth.cancel(started['attemptId'])
            with self.assertRaisesRegex(chatgpt_auth.AuthError,'chatgpt_sign_in_required'):
                self.auth.access_token(self.auth.attempt(started['attemptId'])['accountId'])
        self.assertEqual(len([c for c in calls if c[0]==chatgpt_auth.TOKEN]),1)

    def test_cancel_failed_pending_sign_in_removes_candidate_and_preserves_prior_session(self):
        calls,fake_call=self.exchange_call()
        with self.auth._store() as store:
            store['accounts']['b'*32]=self._connected('b'*32,self.now[0]+3600)
            self.auth._write(store)
        with patch.object(self.auth,'_call',side_effect=fake_call):
            started=self.start('b'*32)
            with patch.object(self.auth,'_identity',side_effect=chatgpt_auth.AuthError('chatgpt_identity_invalid')):
                with self.assertRaisesRegex(chatgpt_auth.AuthError,'chatgpt_refresh_pending'):
                    self.auth.callback(dict(state=[self._state(started['attemptId'])],code=['code']),8769)
            self.assertEqual(self.auth.cancel(started['attemptId'])['status'],'cancelled')
            self.assertEqual(self.auth.access_token('b'*32),'secret-access')
            with self.auth._store() as store:
                self.assertNotIn('refreshPending',store['accounts']['b'*32])
        revoked=[kwargs['form']['token'] for url,kwargs in calls if url.endswith('/oauth/revoke')]
        self.assertEqual(revoked,['refresh-initial'])
        self.assertEqual(len([c for c in calls if c[0]==chatgpt_auth.TOKEN]),1)

    def test_cancel_during_model_discovery_reports_already_completed_sign_in(self):
        calls,fake_call=self.exchange_call()
        started=self.start()
        during=[]
        def observe(url,**kwargs):
            if url==chatgpt_auth.RESOURCE+'/models':
                during.append(self.auth.cancel(started['attemptId'])['status'])
            return fake_call(url,**kwargs)
        with patch.object(self.auth,'_call',side_effect=observe):
            result=self.auth.callback(dict(state=[self._state(started['attemptId'])],code=['code'],client_id=['client']),8769)
        self.assertEqual(during,['completed'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(self.auth.account(result['accountId'])['status'],'connected')
        self.assertFalse(any(url.endswith('/oauth/revoke') for url,_ in calls))

    def test_logout_does_not_make_an_uncommitted_sign_in_completed(self):
        calls,fake_call=self.exchange_call()
        with patch.object(self.auth,'_call',side_effect=fake_call):
            started=self.start()
            with patch.object(self.auth,'_complete_refresh',side_effect=SystemExit):
                with self.assertRaises(SystemExit):
                    self.auth.callback(dict(state=[self._state(started['attemptId'])],code=['code'],client_id=['client']),8769)
            account_id=self.auth.attempt(started['attemptId'])['accountId']
            self.auth.logout(account_id,'f'*32)
            self.assertEqual(self.auth.cancel(started['attemptId'])['status'],'cancelled')
            self.assertEqual(self.auth.account(account_id)['status'],'signed_out')

    def test_pending_response_is_generation_fenced_and_logout_revokes_its_latest_refresh(self):
        with self.auth._store() as store:
            account=self._connected('a'*32,self.now[0]-1)
            account.update(status='refresh_pending',refreshPending=dict(generation=0,clientId='client',subject='subject-1',
                newIdentity=False,tokens=dict(access_token='pending-access',refresh_token='pending-refresh')))
            store['accounts']['a'*32]=account;self.auth._write(store)
        with patch.object(self.auth,'_call',side_effect=AssertionError('No grant for stale pending response')):
            with self.assertRaisesRegex(chatgpt_auth.AuthError,'chatgpt_attempt_changed'):
                self.auth.access_token('a'*32)
        metadata=dict(revocation_endpoint='https://auth.openai.com/oauth/revoke')
        with patch.object(self.auth,'_discovery',return_value=metadata),patch.object(self.auth,'_call',return_value={}) as call:
            self.auth.logout('a'*32,'b'*32)
            self.assertEqual(call.call_args.kwargs['form']['token'],'pending-refresh')
        with self.auth._store() as store:
            account=store['accounts']['a'*32]
            self.assertEqual(account['status'],'signed_out')
            self.assertNotIn('refreshPending',account)

    def test_oauth_metadata_timeout_uses_own_budget_and_safe_step(self):
        calls=[]
        class Opener:
            def open(self,request,timeout):
                calls.append(timeout)
                raise TimeoutError('private')
        with patch('chatgpt_auth.opener_for',return_value=Opener()):
            with self.assertRaises(chatgpt_auth.AuthError) as caught:self.auth._discovery('direct')
        self.assertEqual(calls,[60])
        self.assertEqual(caught.exception.diagnostic['oauthAction'],'discovery')
        self.assertEqual(caught.exception.diagnostic['timeoutMs'],60000)

    def test_public_account_metadata_and_models_reject_credential_echo(self):
        with self.auth._store() as store:
            account=self._connected('a'*32,self.now[0]+3600)
            account.update(email='secret-access@example.test',name='secret-refresh')
            store['accounts'][account['id']]=account;self.auth._write(store)
        self.assertNotIn('secret-',json.dumps(self.auth.catalog()))
        with patch.object(self.auth,'_call',return_value=dict(models=[dict(visibility='list',slug='example',display_name='secret-access')])):
            with self.assertRaisesRegex(chatgpt_auth.AuthError,'chatgpt_models_invalid'):self.auth.models('a'*32)

    def test_logout_clears_private_secrets_and_reports_revocation_result(self):
        calls, fake_call = self.exchange_call()
        with self.patch_private(), patch.object(self.auth, '_call', side_effect=fake_call):
            with self.auth._store() as store:
                store['accounts']['a' * 32] = self._connected('a' * 32, self.now[0] + 1000)
                self.auth._write(store)
            result = self.auth.logout('a' * 32, 'b' * 32)
            self.assertTrue(result['revocationConfirmed'])
            with self.auth._store() as store:
                account = store['accounts']['a' * 32]
                self.assertNotIn('access_token', account)
                self.assertNotIn('refresh_token', account)
                self.assertNotIn('id_token', account)
                self.assertEqual(account['status'], 'signed_out')
            self.assertFalse(self.auth.catalog()['accounts'][0]['planUsageEnabled'])

            with self.auth._store() as store:
                store['accounts']['c' * 32] = self._connected('c' * 32, self.now[0] + 1000)
                self.auth._write(store)
            def failed_revoke(url, **kwargs):
                if kwargs.get('form', {}).get('token'):
                    raise chatgpt_auth.AuthError('chatgpt_network_error', diagnostic={'outcomeUnknown': True})
                return fake_call(url, **kwargs)
            self.auth._call = failed_revoke
            result = self.auth.logout('c' * 32, 'd' * 32)
            self.assertFalse(result['revocationConfirmed'])

    def test_forget_removes_signed_out_account_and_private_attempts_idempotently(self):
        account_id = 'a' * 32
        other_id = 'b' * 32
        with self.auth._store() as store:
            store['accounts'][account_id] = {'id': account_id, 'status': 'signed_out',
                                              'email': 'forget@example.test'}
            store['accounts'][other_id] = {'id': other_id, 'status': 'signed_out'}
            store['attempts']['c' * 32] = {'id': 'c' * 32, 'accountId': account_id,
                                            'status': 'pending'}
            store['attempts']['d' * 32] = {'id': 'd' * 32, 'accountId': other_id,
                                            'status': 'pending'}
            self.auth._write(store)
        with patch('chatgpt_auth.barrier', return_value=nullcontext()):
            self.assertEqual(self.auth.forget(account_id),
                             {'accountId': account_id, 'status': 'forgotten'})
            self.assertEqual(self.auth.forget(account_id),
                             {'accountId': account_id, 'status': 'forgotten'})
        with self.auth._store() as store:
            self.assertNotIn(account_id, store['accounts'])
            self.assertNotIn('c' * 32, store['attempts'])
            self.assertIn(other_id, store['accounts'])
            self.assertIn('d' * 32, store['attempts'])

    def test_forget_rejects_connected_and_exchanging_accounts(self):
        account_id = 'a' * 32
        with self.auth._store() as store:
            store['accounts'][account_id] = self._connected(account_id, self.now[0] + 1000)
            self.auth._write(store)
        with patch('chatgpt_auth.barrier', return_value=nullcontext()):
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_account_sign_out_required'):
                self.auth.forget(account_id)
        with self.auth._store() as store:
            store['accounts'][account_id] = {'id': account_id, 'status': 'signed_out'}
            store['attempts']['c' * 32] = {'id': 'c' * 32, 'accountId': account_id,
                                            'status': 'exchanging'}
            self.auth._write(store)
        with patch('chatgpt_auth.barrier', return_value=nullcontext()):
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_account_busy'):
                self.auth.forget(account_id)

    def test_forget_blocks_provider_reference_and_corrupt_settings(self):
        account_id = 'a' * 32
        with self.auth._store() as store:
            store['accounts'][account_id] = {'id': account_id, 'status': 'signed_out'}
            self.auth._write(store)
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        connection.execute('CREATE TABLE agent_provider_settings(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        connection.execute('INSERT INTO agent_provider_settings VALUES(1, ?)', (json.dumps({
            'version': 1, 'default': 'none', 'items': [{'accountId': account_id,
            'config': {'auth_method': 'chatgpt_oauth'}}]}),))
        connection.commit()
        @contextmanager
        def db():
            yield connection
        with patch.object(self.registry, 'connect', db), patch('chatgpt_auth.barrier', return_value=nullcontext()):
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_account_in_use'):
                self.auth.forget(account_id)
        connection.execute('UPDATE agent_provider_settings SET body=?', ('{broken',))
        connection.commit()
        with patch.object(self.registry, 'connect', db), patch('chatgpt_auth.barrier', return_value=nullcontext()):
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_provider_settings_invalid'):
                self.auth.forget(account_id)
        connection.execute('UPDATE agent_provider_settings SET body=?',
                           (json.dumps({'version': 1, 'default': 'none', 'items': {}}),))
        connection.commit()
        with patch.object(self.registry, 'connect', db), patch('chatgpt_auth.barrier', return_value=nullcontext()):
            with self.assertRaisesRegex(chatgpt_auth.AuthError, 'chatgpt_provider_settings_invalid'):
                self.auth.forget(account_id)

    def test_forget_persists_attempt_cleanup_when_account_is_already_missing(self):
        account_id = 'a' * 32
        with self.auth._store() as store:
            store['attempts']['c' * 32] = {'id': 'c' * 32, 'accountId': account_id,
                                            'status': 'pending'}
            self.auth._write(store)
        with patch('chatgpt_auth.barrier', return_value=nullcontext()):
            self.auth.forget(account_id)
        with self.auth._store() as store:
            self.assertNotIn('c' * 32, store['attempts'])

    def test_catalog_labels_omit_hex_and_disambiguate_duplicates(self):
        with self.auth._store() as store:
            for account_id in ('a' * 32, 'b' * 32):
                store['accounts'][account_id] = {'id': account_id, 'status': 'signed_out',
                                                  'email': 'same@example.test'}
            self.auth._write(store)
        labels=[account['label'] for account in self.auth.catalog()['accounts']]
        self.assertEqual(labels, ['same@example.test (1)', 'same@example.test (2)'])
        self.assertNotIn('aaaaaaaa', labels[0])
        self.assertNotIn('bbbbbbbb', labels[1])


if __name__ == '__main__':
    unittest.main()
