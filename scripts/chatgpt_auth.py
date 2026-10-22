"""Local Sign in with ChatGPT. OAuth credentials never enter portable Hub data."""
from contextlib import contextmanager
from copy import deepcopy
import base64
import hashlib
import hmac
import html
import json
import math
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
import uuid

from hub_launcher import external_path
from hub_lifecycle import atomic_json, file_lock
from outbound_http import OutboundError, json_request, opener_for
import secret_vault
from task_transfer import barrier

ISSUER = 'https://auth.openai.com'
DISCOVERY = ISSUER + '/.well-known/openid-configuration'
AUTHORIZE = ISSUER + '/api/accounts/authorize'
TOKEN = ISSUER + '/api/accounts/oauth/token'
RESOURCE = 'https://api.openai.com/v1'
SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
PLAN_SCOPES = frozenset(('resource.invoke', 'chatgpt.tokens.use.direct'))
IDENTIFIER = re.compile(r'[0-9a-f]{32}')
MODEL = re.compile(r'[A-Za-z0-9_.:/-]{1,160}')
MODEL_CATALOG_LIMIT = 8 * 1024 * 1024
OAUTH_TIMEOUT = 60
DIAGNOSTIC_FIELDS = frozenset(('requestId','attempt','operation','scheme','host','port',
    'networkMode','effectiveNetworkMode','durationMs','timeoutMs','oauthAction','status','phase','category','httpStatus',
    'providerErrorCode','providerErrorType','upstreamRequestId','retryAfter','outcomeUnknown','tlsReason','tlsVerifyCode',
    'identityReason'))


class AuthError(ValueError):
    def __init__(self, code, status=400, diagnostic=None):
        super().__init__(code)
        self.status = status
        self.body = dict(error=code, message='Review the ChatGPT connection and try again.')
        self.diagnostic = diagnostic


def browser_error(error, language='ru'):
    """An auth return page contains no callback parameters or provider body."""
    language = 'en' if language == 'en' else 'ru'
    code = error.body['error']
    invalid = code in ('chatgpt_callback_invalid','chatgpt_attempt_expired','chatgpt_attempt_missing')
    pending = code == 'chatgpt_refresh_pending'
    crypto = code == 'chatgpt_crypto_unavailable' or (error.diagnostic or {}).get('identityReason') == 'crypto_unavailable'
    if language == 'ru':
        title = 'Ссылка входа недействительна' if invalid else 'Авторизация ожидает проверки' if pending else 'Вход в ChatGPT не завершён'
        explanation = ('Попытка могла истечь, быть отменена или уже использована. Начните новый вход из сохранённого подключения: «Изменить» → «Продолжить в ChatGPT». Срок попытки начнётся после нажатия кнопки.' if invalid else
            'Hub сохранил полученный ответ в защищённом хранилище. Откройте сохранённое подключение и запустите новую проверку модели: Hub продолжит проверку этого ответа без повторного обмена кода на токены.' if pending else
            'Откройте настройки запросов к моделям и проверьте состояние сохранённого подключения ChatGPT.')
        action, details = 'Открыть настройки моделей', 'Код ошибки'
        if crypto:
            title='Не удалось проверить авторизацию'
            explanation='Hub не смог загрузить компонент проверки подписи. Восстановите компоненты Hub, затем повторите проверку авторизации в настройках моделей. Повторный вход не устраняет эту ошибку.'
    else:
        title = 'Sign-in link is no longer valid' if invalid else 'Authorization needs verification' if pending else 'ChatGPT sign-in did not complete'
        explanation = ('The attempt may have expired, been cancelled or already been used. Start again from the saved connection: Edit → Continue in ChatGPT. The attempt starts when you press the button.' if invalid else
            'Hub retained the received response in protected storage. Open the saved connection and start a new model check. Hub will resume verification without exchanging the authorization code again.' if pending else
            'Open model request settings and review the saved ChatGPT connection.')
        action, details = 'Open model settings', 'Error code'
        if crypto:
            title='Authorization could not be verified'
            explanation='Hub could not load its signature verification component. Repair Hub components, then verify authorization again in model settings. Signing in again does not fix this error.'
    safe_code = code if re.fullmatch(r'chatgpt_[a-z_]{1,64}',code) else 'chatgpt_auth_failed'
    return (f'<!doctype html><html lang="{language}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        f'<title>{html.escape(title)} — Project Hub</title><link rel="stylesheet" href="/style.css">'
        '<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text)}'
        'main{box-sizing:border-box;width:min(600px,calc(100% - 32px));padding:28px;border:1px solid var(--line);'
        'border-top:3px solid var(--amber);border-radius:8px;background:var(--panel)}'
        'h1{font-size:22px;margin:0 0 16px}p{color:var(--muted)}a{display:inline-block;margin:12px 0;'
        'padding:9px 14px;color:var(--accent);background:var(--accent-bg);border:1px solid var(--accent);border-radius:4px}'
        'details{margin-top:16px;color:var(--muted)}</style>'
        f'<main><h1>{html.escape(title)}</h1><p>{html.escape(explanation)}</p>'
        f'<a href="/#settings/agents/models">{html.escape(action)}</a>'
        f'<details><summary>{html.escape(details)}</summary><code>{html.escape(safe_code)}</code></details>'
        '</main></html>').encode('utf-8')


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise AuthError('chatgpt_invalid_request')
    return value


def text(value, limit=32768):
    return isinstance(value, str) and 0 < len(value) <= limit and not any(ord(c) < 33 for c in value)


def public_text(value, account, limit=200):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):
        return ''
    if any(account.get(key) and account[key] in value for key in ('access_token','refresh_token','id_token')):
        return ''
    return value


def model_diagnostic(value, account):
    if not isinstance(value,dict):
        return None
    return {key:item for key,item in value.items() if key in DIAGNOSTIC_FIELDS and (
        isinstance(item,str) and public_text(item,account) or
        type(item) in (bool,int,float) and math.isfinite(item))}


def verify_id_token(token, client_id, nonce, jwks, *, subject=None):
    """Use maintained JWT/crypto implementations; no algorithm negotiation from a token."""
    try:
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa, ec
        if not jwt.algorithms.has_crypto:
            raise ImportError()
    except ImportError:
        raise AuthError('chatgpt_crypto_unavailable',503,dict(operation='oauth',
            oauthAction='identity_validation',category='configuration',phase='verify',
            identityReason='crypto_unavailable',outcomeUnknown=False)) from None
    reason = 'token_format'
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get('alg')
        reason = 'algorithm'
        if algorithm not in ('RS256', 'ES256') or not text(header.get('kid'), 200):
            raise ValueError()
        reason = 'signing_key'
        keys = jwks.get('keys')
        if not isinstance(keys, list) or len(keys) > 64:
            raise ValueError()
        matches = [key for key in keys if isinstance(key, dict) and key.get('kid') == header['kid']]
        if len(matches) != 1:
            raise ValueError()
        key = matches[0]
        if key.get('use', 'sig') != 'sig' or key.get('alg', algorithm) != algorithm:
            raise ValueError()
        if 'key_ops' in key and (not isinstance(key['key_ops'], list) or 'verify' not in key['key_ops']):
            raise ValueError()
        public = jwt.PyJWK.from_dict(key, algorithm=algorithm)
        claims = jwt.decode(token, public.key, algorithms=[algorithm], issuer=ISSUER,
            audience=client_id, leeway=30, options={'require':['iss','aud','exp','iat','sub']})
        reason = 'claims'
        if not text(claims.get('sub'), 512) or type(claims['exp']) not in (int, float) or type(claims['iat']) not in (int, float):
            raise ValueError()
        if not math.isfinite(claims['exp']) or not math.isfinite(claims['iat']):
            raise ValueError()
        reason = 'authorized_party'
        if claims.get('azp', client_id) != client_id:
            raise ValueError()
        if isinstance(claims['aud'], list) and len(claims['aud']) > 1 and claims.get('azp') != client_id:
            raise ValueError()
        reason = 'nonce'
        if nonce is not None and (not isinstance(claims.get('nonce'), str) or not hmac.compare_digest(claims['nonce'], nonce)):
            raise ValueError()
        reason = 'subject'
        if subject is not None and claims['sub'] != subject:
            raise ValueError()
        return claims
    except Exception as error:
        reasons = {'ExpiredSignatureError':'expired', 'ImmatureSignatureError':'not_yet_valid',
            'InvalidAudienceError':'audience', 'InvalidIssuerError':'issuer',
            'InvalidIssuedAtError':'issued_at', 'MissingRequiredClaimError':'required_claim',
            'InvalidSignatureError':'signature', 'DecodeError':'token_format'}
        reason = reasons.get(type(error).__name__, reason)
        raise AuthError('chatgpt_identity_invalid', diagnostic=dict(operation='oauth',
            oauthAction='identity_validation', category='identity', phase='verify',
            identityReason=reason, outcomeUnknown=False)) from None


class ChatGPTAuth:
    def __init__(self, registry, *, clock=time.time, verify=verify_id_token):
        self.registry, self.clock, self.verify = registry, clock, verify
        self.home = secret_vault.private_home(registry)
        self.path = external_path(self.home / 'chatgpt-credentials.json')

    def _read(self):
        if not self.path.exists():
            return dict(version=1, hostId=None, accounts={}, attempts={})
        try:
            with self.path.open('rb') as stream:
                raw = stream.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError()
            envelope = json.loads(raw)
            protection = 'windows-dpapi' if os.name == 'nt' else 'private-file'
            if envelope.get('version') != 1 or envelope.get('protection') != protection:
                raise ValueError()
            value = json.loads(secret_vault._protect(base64.b64decode(envelope['content'], validate=True), True))
            if value.get('version') != 1 or not isinstance(value.get('accounts'), dict) or not isinstance(value.get('attempts'), dict):
                raise ValueError()
            return value
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise AuthError('chatgpt_private_storage_unavailable', 503) from None

    def _write(self, value):
        encoded = json.dumps(value, separators=(',', ':')).encode()
        if len(encoded) > 1_000_000:
            raise AuthError('chatgpt_account_limit')
        content = base64.b64encode(secret_vault._protect(encoded)).decode('ascii')
        atomic_json(self.path, dict(version=1, protection='windows-dpapi' if os.name=='nt' else 'private-file', content=content))
        os.chmod(self.path, 0o600)

    @contextmanager
    def _store(self):
        with file_lock(self.home / 'chatgpt-store.lock', timeout=5):
            yield self._read()

    def _account_lock(self, account_id):
        return file_lock(self.home / ('chatgpt-account-' + identifier(account_id) + '.lock'), timeout=35)

    def _public_account(self, account):
        status = account.get('status', 'signed_out')
        if status == 'connected' and account.get('expiresAt', 0) <= self.clock() and not account.get('refresh_token'):
            status = 'reauth_required'
        enabled = PLAN_SCOPES <= set(account.get('scopes', []))
        email = public_text(account.get('email'),account,320)
        label = email or public_text(account.get('name'),account) or 'ChatGPT'
        return dict(id=account['id'], label=label, email=email,
            status=status, planUsageEnabled=enabled and status=='connected', generation=account.get('generation', 0),
            models=account.get('models', []), modelsError=account.get('modelsError'),
            modelsDiagnostic=model_diagnostic(account.get('modelsDiagnostic'),account),
            networkMode=account.get('networkMode', 'direct'), revocationConfirmed=account.get('revocationConfirmed'))

    def catalog(self):
        with self._store() as store:
            accounts=[self._public_account(account) for account in store['accounts'].values()]
        labels={}
        for account in accounts:
            labels.setdefault(account['label'], []).append(account)
        for same_label in labels.values():
            if len(same_label) > 1:
                for index, account in enumerate(same_label, 1):
                    account['label'] = f"{account['label']} ({index})"
        return dict(accounts=accounts)

    def account(self, account_id):
        identifier(account_id)
        return next((entry for entry in self.catalog()['accounts'] if entry['id']==account_id), None)

    def _call(self, url, *, mode='direct', form=None, bearer=None, allow_empty=False, limit=512_000, timeout=OAUTH_TIMEOUT):
        headers = {'Accept':'application/json'}
        data = None
        sensitive = []
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            sensitive = [value for key, value in form.items() if key in ('code','code_verifier','refresh_token','token')]
        if bearer:
            headers['Authorization'] = 'Bearer ' + bearer
        request = urllib.request.Request(url, data=data, headers=headers, method='POST' if form is not None else 'GET')
        try:
            return json_request(request, opener=opener_for(url, mode), timeout=timeout, limit=limit,
                network_mode=mode, operation='oauth', allow_empty=allow_empty, sensitive_values=sensitive)[0]
        except OutboundError as error:
            reason = error.diagnostic.get('providerErrorCode')
            code = 'chatgpt_' + reason if reason in ('invalid_grant','invalid_client','access_denied') else 'chatgpt_network_error'
            action = ('token_refresh' if url==TOKEN and form and form.get('grant_type')=='refresh_token'
                else 'code_exchange' if url==TOKEN else 'discovery' if url==DISCOVERY
                else 'identity_keys' if url==ISSUER+'/.well-known/jwks.json'
                else 'model_list' if url==RESOURCE+'/models' else 'other')
            raise AuthError(code, 502, dict(error.diagnostic,oauthAction=action)) from None

    def _discovery(self, mode):
        metadata = self._call(DISCOVERY, mode=mode)
        if (metadata.get('issuer') != ISSUER or metadata.get('authorization_endpoint') != AUTHORIZE
                or metadata.get('token_endpoint') != TOKEN or metadata.get('jwks_uri') != ISSUER+'/.well-known/jwks.json'):
            raise AuthError('chatgpt_discovery_invalid')
        return metadata

    def _identity(self, token, client_id, nonce, mode, subject=None):
        metadata = self._discovery(mode)
        jwks = self._call(metadata['jwks_uri'], mode=mode)
        return self.verify(token, client_id, nonce, jwks, subject=subject)

    @staticmethod
    def _clear_attempt(attempt, status, code=None):
        attempt['status'] = status
        if code:
            attempt['error'] = dict(code=code)
        for key in ('state','nonce','verifier'):
            attempt.pop(key, None)

    def start(self, request, port):
        if set(request)-{'action','requestId','accountId','networkMode'} or request.get('action')!='start':
            raise AuthError('chatgpt_invalid_request')
        request_id = identifier(request.get('requestId'))
        account_id = request.get('accountId')
        if account_id is not None:
            identifier(account_id)
        mode = request.get('networkMode', 'direct')
        if mode not in ('direct','system') or type(port) is not int or not 1<=port<=65535:
            raise AuthError('chatgpt_invalid_request')
        fingerprint = hashlib.sha256(json.dumps([request,port], sort_keys=True).encode()).hexdigest()
        with self._store() as store:
            prior = store['attempts'].get(request_id)
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise AuthError('chatgpt_request_conflict',409)
                return dict(attemptId=request_id,status=prior['status'],authorizePath='/auth/chatgpt/authorize?attemptId='+request_id)
            for key, attempt in list(store['attempts'].items()):
                if attempt['expiresAt'] <= self.clock():
                    self._clear_attempt(attempt, 'expired')
                if attempt['expiresAt'] < self.clock()-3600:
                    del store['attempts'][key]
            if len(store['attempts']) >= 32 or (account_id is None and len(store['accounts'])>=16):
                raise AuthError('chatgpt_account_limit')
            account = store['accounts'].get(account_id) if account_id else None
            if account_id and account is None:
                raise AuthError('chatgpt_account_missing',404)
            if not store['hostId']:
                store['hostId'] = 'urn:uuid:' + str(uuid.uuid4())
            account_id = account_id or uuid.uuid4().hex
            store['attempts'][request_id] = dict(id=request_id, fingerprint=fingerprint, accountId=account_id,
                clientId=account.get('client_id') if account else None, subject=account.get('subject') if account else None,
                generation=account.get('generation',0) if account else 0, hostId=store['hostId'],
                state=secrets.token_urlsafe(32), nonce=secrets.token_urlsafe(32), verifier=secrets.token_urlsafe(64),
                redirectUri=f'http://127.0.0.1:{port}/auth/callback', networkMode=mode,
                expiresAt=self.clock()+600, status='pending')
            self._write(store)
        return dict(attemptId=request_id,status='pending',authorizePath='/auth/chatgpt/authorize?attemptId='+request_id)

    def attempt(self, attempt_id):
        identifier(attempt_id)
        with self._store() as store:
            attempt = store['attempts'].get(attempt_id)
            if attempt is None:
                raise AuthError('chatgpt_attempt_missing',404)
            if attempt['status'] in ('pending','exchanging') and attempt['expiresAt']<=self.clock():
                self._clear_attempt(attempt,'expired')
                self._write(store)
            result={key:deepcopy(attempt[key]) for key in ('status','accountId','error') if key in attempt} | dict(attemptId=attempt_id)
            if result['status']=='exchanging':
                result['status']='pending'
            return result

    def authorization_url(self, attempt_id):
        identifier(attempt_id)
        with self._store() as store:
            attempt = deepcopy(store['attempts'].get(attempt_id))
            account = deepcopy(store['accounts'].get(attempt.get('accountId'))) if attempt else None
        if not attempt or attempt['status']!='pending' or attempt['expiresAt']<=self.clock():
            raise AuthError('chatgpt_attempt_expired')
        query=dict(client_id=attempt['clientId'] or 'dynamic_agent_client',response_type='code',
            redirect_uri=attempt['redirectUri'],scope=SCOPES,resource=RESOURCE,state=attempt['state'],nonce=attempt['nonce'],
            code_challenge_method='S256',code_challenge=base64.urlsafe_b64encode(hashlib.sha256(attempt['verifier'].encode()).digest()).decode().rstrip('='),
            ext_agent_host_id=attempt['hostId'])
        if not attempt['clientId']:
            query['agent_name_hint']='Project Hub'
        elif account:
            if public_text(account.get('email'),account,320):
                query['login_hint']=public_text(account['email'],account,320)
            if text(account.get('id_token')):
                query['id_token_hint']=account['id_token']
        # Only this fixed OpenAI endpoint receives the retained identity hint.
        # The local redirect route suppresses access logs and referrer forwarding.
        return AUTHORIZE+'?'+urllib.parse.urlencode(query)

    def cancel(self, attempt_id):
        identifier(attempt_id)
        revoke = None
        with self._store() as store:
            attempt=store['attempts'].get(attempt_id)
            if attempt is None:
                raise AuthError('chatgpt_attempt_missing',404)
            account=store['accounts'].get(attempt['accountId'],{})
            pending=account.get('refreshPending',{})
            linked=pending.get('kind')=='sign-in' and pending.get('attemptId')==attempt_id
            recoverable=attempt['status']=='failed' and attempt.get('error',{}).get('code')=='chatgpt_refresh_pending'
            if attempt['status']=='exchanging' and 'committedGeneration' in attempt:
                # Verification already committed atomically. Model discovery
                # may still be running, but cancellation cannot claim to undo
                # a completed sign-in.
                self._clear_attempt(attempt,'completed')
                self._write(store)
            elif attempt['status'] in ('pending','exchanging') or recoverable:
                self._clear_attempt(attempt,'cancelled')
                if linked:
                    revoke=(pending['tokens'].get('refresh_token'),account['client_id'],pending['networkMode'])
                    account.pop('refreshPending',None)
                    account['status']=pending.get('priorStatus','reauth_required' if account.get('access_token') else 'signed_out')
                self._write(store)
        if revoke and revoke[0]:
            self._revoke(*revoke)
        return self.attempt(attempt_id)

    def _tokens(self, reply, *, prior=None):
        if not text(reply.get('access_token')) or str(reply.get('token_type','')).lower()!='bearer':
            raise AuthError('chatgpt_token_response_invalid')
        expires=reply.get('expires_in')
        if type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires<=86400:
            raise AuthError('chatgpt_token_response_invalid')
        refresh=reply.get('refresh_token')
        if refresh is not None and not text(refresh):
            raise AuthError('chatgpt_token_response_invalid')
        scopes=reply.get('scope')
        if scopes is None and prior is not None:
            granted=prior['scopes']
        elif isinstance(scopes,str) and len(scopes)<=4096:
            granted=scopes.split()
        else:
            granted=[]
        return dict(access_token=reply['access_token'],refresh_token=refresh or (prior or {}).get('refresh_token'),
            id_token=reply.get('id_token') or (prior or {}).get('id_token'),scopes=granted,
            expiresAt=self.clock()+expires,earliestRefreshAt=reply.get('earliest_refresh_at'))

    def callback(self, query, port):
        if any(len(values)!=1 for values in query.values()) or not text(query.get('state',[''])[0], 200):
            raise AuthError('chatgpt_callback_invalid')
        state=query['state'][0]
        with self._store() as store:
            matches=[value for value in store['attempts'].values() if value.get('state') and hmac.compare_digest(value['state'],state)]
            if len(matches)!=1:
                raise AuthError('chatgpt_callback_invalid')
            attempt=matches[0]
            if (attempt['status']!='pending' or attempt['expiresAt']<=self.clock()
                    or attempt['redirectUri']!=f'http://127.0.0.1:{port}/auth/callback'):
                raise AuthError('chatgpt_callback_invalid')
            account_id=attempt['accountId']
            if 'error' in query:
                self._clear_attempt(attempt,'failed','chatgpt_consent_declined')
                self._write(store)
                return dict(attemptId=attempt['id'],status='failed',accountId=account_id,error=dict(code='chatgpt_consent_declined'))
            client_id=query.get('client_id',[attempt['clientId']])[0]
            if not text(client_id,200) or client_id=='dynamic_agent_client' or (attempt['clientId'] and client_id!=attempt['clientId']):
                self._clear_attempt(attempt,'failed','chatgpt_client_invalid');self._write(store)
                raise AuthError('chatgpt_client_invalid')
            code=query.get('code',[''])[0]
            if not text(code,4096):
                self._clear_attempt(attempt,'failed','chatgpt_callback_invalid');self._write(store)
                raise AuthError('chatgpt_callback_invalid')
            # Preserve the issued registration before redeeming the one-use code.
            account=store['accounts'].setdefault(account_id,dict(id=account_id,client_id=client_id,status='signed_out',generation=0))
            if account.get('client_id')!=client_id:
                raise AuthError('chatgpt_client_invalid')
            attempt['status']='exchanging'
            attempt=deepcopy(attempt)
            self._write(store)
        with self._account_lock(account_id):
            try:
                with self._store() as store:
                    if (store['attempts'][attempt['id']]['status']!='exchanging'
                            or store['accounts'][account_id].get('generation',0)!=attempt['generation']):
                        raise AuthError('chatgpt_attempt_changed')
                reply=self._call(TOKEN,mode=attempt['networkMode'],form=dict(grant_type='authorization_code',
                    client_id=client_id,code=code,code_verifier=attempt['verifier'],redirect_uri=attempt['redirectUri'],resource=RESOURCE))
                tokens=self._tokens(reply)
                if not text(tokens.get('id_token')):
                    raise AuthError('chatgpt_identity_invalid')
                with self._store() as store:
                    live=store['attempts'][attempt['id']]
                    account=store['accounts'][account_id]
                    if live['status']!='exchanging' or account.get('generation',0)!=attempt['generation']:
                        raise AuthError('chatgpt_attempt_changed')
                    account['refreshPending']=dict(kind='sign-in',tokens=tokens,newIdentity=True,
                        generation=attempt['generation'],clientId=client_id,subject=attempt['subject'],
                        nonce=attempt['nonce'],attemptId=attempt['id'],networkMode=attempt['networkMode'],
                        priorStatus=account['status'] if account['status']!='refresh_pending' else 'reauth_required')
                    account.pop('refreshIntent',None)
                    account['status']='refresh_pending'
                    self._write(store)
                self._complete_refresh(account_id,deepcopy(account),attempt['networkMode'])
            except AuthError as error:
                with self._store() as store:
                    live=store['attempts'].get(attempt['id'])
                    if live and live['status']=='exchanging':
                        self._clear_attempt(live,'failed',error.body['error'])
                        diagnostic=model_diagnostic(error.diagnostic,store['accounts'][account_id])
                        if diagnostic:live['error']['diagnostic']=diagnostic
                        self._write(store)
                raise
        if PLAN_SCOPES<=set(tokens['scopes']):
            try:
                self.models(account_id)
            except AuthError:
                pass  # Keep the verified account; model discovery has a separate status.
        with self._store() as store:
            live=store['attempts'][attempt['id']]
            if live['status']=='exchanging':
                self._clear_attempt(live,'completed')
                self._write(store)
        return self.attempt(attempt['id'])

    def access_token(self, account_id, mode=None):
        with self._account_lock(account_id):
            return self._access_token(account_id,mode)

    def _access_token(self, account_id, mode=None):
        with self._store() as store:
            account=deepcopy(store['accounts'].get(account_id))
            if not account or account.get('status') not in ('connected','refresh_pending'):
                raise AuthError('chatgpt_sign_in_required',409)
        mode=mode or account.get('networkMode','direct')
        if account.get('refreshPending'):
            access=self._complete_refresh(account_id, account, mode)
            if not PLAN_SCOPES<=set(account['refreshPending']['tokens']['scopes']):
                raise AuthError('chatgpt_plan_permission_required',409)
            if account['refreshPending']['tokens']['expiresAt']<=self.clock():
                # A reply recovered after downtime can have an expired access
                # token. Its verified replacement refresh is now committed;
                # one normal exchange can renew it without replaying the old.
                return self._access_token(account_id,mode)
            return access
        if account.get('status')!='connected':
            raise AuthError('chatgpt_sign_in_required',409)
        with self._store() as store:
            if not PLAN_SCOPES<=set(account.get('scopes',[])):
                raise AuthError('chatgpt_plan_permission_required',409)
            if account.get('refreshIntent'):
                store['accounts'][account_id]['status']='refresh_unknown';self._write(store)
                raise AuthError('chatgpt_refresh_unknown',409)
            if account.get('expiresAt',0)>self.clock()+120:
                return account['access_token']
            if not account.get('refresh_token'):
                raise AuthError('chatgpt_sign_in_required',409)
            earliest=account.get('earliestRefreshAt')
            if isinstance(earliest,(int,float)) and earliest>self.clock():
                if account['expiresAt']>self.clock()+5:
                    return account['access_token']
                raise AuthError('chatgpt_refresh_not_ready',409)
            store['accounts'][account_id]['refreshIntent']=True
            self._write(store)
        refresh_received = False
        try:
            reply=self._call(TOKEN,mode=mode,form=dict(grant_type='refresh_token',client_id=account['client_id'],
                refresh_token=account['refresh_token'],resource=RESOURCE))
            refresh_received = True
            if not text(reply.get('refresh_token')):
                raise AuthError('chatgpt_token_response_invalid')
            tokens=self._tokens(reply,prior=account)
            with self._store() as store:
                current=store['accounts'][account_id]
                # The old refresh token may already be spent. Durably retain
                # the received replacement before discovery/JWKS/validation.
                # Pending credentials are private and cannot authorize a model.
                current['refreshPending']=dict(tokens=tokens,newIdentity=bool(reply.get('id_token')),
                    generation=account.get('generation',0),clientId=account['client_id'],subject=account['subject'])
                current.pop('refreshIntent',None)
                current['status']='refresh_pending'
                self._write(store)
        except AuthError as error:
            with self._store() as store:
                current=store['accounts'][account_id]
                current.pop('refreshIntent',None)
                if error.body['error']=='chatgpt_plan_permission_required':
                    current['status']='plan_disabled'
                elif not refresh_received and error.diagnostic and not error.diagnostic.get('outcomeUnknown') and error.body['error']=='chatgpt_network_error':
                    current['status']='connected'
                else:
                    current['status']='refresh_unknown' if refresh_received or error.diagnostic and error.diagnostic.get('outcomeUnknown') else 'reauth_required'
                self._write(store)
            if refresh_received and error.body['error'] == 'chatgpt_network_error':
                raise AuthError('chatgpt_refresh_unknown', 409, error.diagnostic) from None
            raise
        return self._complete_refresh(account_id, deepcopy(current), mode)

    def _complete_refresh(self, account_id, account, mode):
        """Retry only validation of a known response, never its token exchange."""
        pending=account['refreshPending']
        if (pending.get('generation')!=account.get('generation',0) or
                pending.get('clientId')!=account['client_id'] or pending.get('subject')!=account.get('subject')):
            raise AuthError('chatgpt_attempt_changed',409)
        tokens=pending['tokens']
        try:
            if pending['newIdentity']:
                identity=self._identity(tokens['id_token'],account['client_id'],pending.get('nonce'),mode,subject=account.get('subject'))
        except AuthError as error:
            raise AuthError('chatgpt_refresh_pending',409,error.diagnostic) from None
        with self._store() as store:
            current=store['accounts'][account_id]
            if (current.get('generation',0)!=pending['generation'] or
                    current.get('refreshPending')!=pending or current.get('status')!='refresh_pending'):
                raise AuthError('chatgpt_attempt_changed',409)
            sign_in=pending.get('kind')=='sign-in'
            if sign_in:
                live=store['attempts'].get(pending['attemptId'])
                if (not live or live.get('generation')!=pending['generation'] or live.get('accountId')!=account_id
                        or live.get('status') not in ('exchanging','failed') or
                        live['status']=='failed' and live.get('error',{}).get('code')!='chatgpt_refresh_pending'):
                    raise AuthError('chatgpt_attempt_changed',409)
                current.update(subject=identity['sub'],issuer=ISSUER,
                    email=identity.get('email','') if isinstance(identity.get('email',''),str) else '',
                    name=identity.get('name','') if isinstance(identity.get('name',''),str) else '',
                    networkMode=pending['networkMode'],generation=current.get('generation',0)+1,
                    models=[],modelsError=None,modelsDiagnostic=None)
                # A recovered failed attempt can finish now. The original
                # callback keeps polling pending until model discovery ends.
                status='completed' if live['status']=='failed' else 'exchanging'
                live['committedGeneration']=current['generation']
                live.pop('error',None)
                self._clear_attempt(live,status)
            current.update(tokens)
            current.pop('refreshPending',None)
            current['status']='connected' if PLAN_SCOPES<=set(tokens['scopes']) else 'plan_disabled'
            self._write(store)
        if not sign_in and not PLAN_SCOPES<=set(tokens['scopes']):
            raise AuthError('chatgpt_plan_permission_required',409)
        return tokens['access_token']

    def models(self, account_id):
        with self._account_lock(account_id):
            identifier(account_id)
            try:
                token=self._access_token(account_id)
                with self._store() as store:
                    account=deepcopy(store['accounts'][account_id])
                # The account catalog includes verbose model capabilities/instructions.
                # Keep a separate bounded read budget; persist only picker metadata.
                reply=self._call(RESOURCE+'/models',mode=account.get('networkMode','direct'),bearer=token,
                    limit=MODEL_CATALOG_LIMIT,timeout=30)
                values=reply.get('models')
                if not isinstance(values,list) or len(values)>512:
                    raise AuthError('chatgpt_models_invalid')
                models=[]
                for item in values:
                    if not isinstance(item,dict) or item.get('visibility')!='list':
                        continue
                    slug,name=item.get('slug'),item.get('display_name')
                    if not isinstance(slug,str) or not MODEL.fullmatch(slug) or not public_text(name,account) or not public_text(slug,account):
                        raise AuthError('chatgpt_models_invalid')
                    models.append(dict(slug=slug,displayName=name))
                with self._store() as store:
                    current=store['accounts'][account_id]
                    if current.get('generation')!=account.get('generation') or current.get('status')!='connected':
                        raise AuthError('chatgpt_account_changed',409)
                    current.update(models=models,modelsError=None,modelsDiagnostic=None);self._write(store)
            except AuthError as error:
                with self._store() as store:
                    if account_id in store['accounts']:
                        current=store['accounts'][account_id]
                        current.update(modelsError=error.body['error'],modelsDiagnostic=model_diagnostic(error.diagnostic,current))
                        self._write(store)
                raise
            return self.catalog()

    def _revoke(self, renewable, client_id, mode):
        try:
            metadata=self._discovery(mode)
            endpoint=metadata.get('revocation_endpoint','')
            parsed=urllib.parse.urlsplit(endpoint)
            if parsed.scheme!='https' or parsed.netloc!='auth.openai.com' or parsed.query or parsed.fragment:
                raise AuthError('chatgpt_discovery_invalid')
            self._call(endpoint,mode=mode,allow_empty=True,
                form=dict(token=renewable,token_type_hint='refresh_token',client_id=client_id))
            return True
        except AuthError:
            return False

    def logout(self, account_id, request_id):
        identifier(request_id)
        with self._account_lock(account_id):
            with self._store() as store:
                account=deepcopy(store['accounts'].get(account_id))
                if account is None:
                    raise AuthError('chatgpt_account_missing',404)
                if account.get('logoutRequest')==request_id:
                    return dict(accountId=account_id,status='signed_out',revocationConfirmed=account.get('revocationConfirmed',False))
                current=store['accounts'][account_id]
                current.update(status='signed_out',generation=current.get('generation',0)+1,logoutRequest=request_id,
                    revocationConfirmed=False,models=[],modelsError=None,modelsDiagnostic=None)
                for key in ('access_token','refresh_token','id_token','refreshIntent','refreshPending'):
                    current.pop(key,None)
                self._write(store)
            # A received replacement supersedes the old renewable session even
            # while its identity validation is pending.
            renewable=account.get('refreshPending',{}).get('tokens',{}).get('refresh_token') or account.get('refresh_token')
            confirmed=not bool(renewable)
            if renewable:
                confirmed=self._revoke(renewable,account['client_id'],account.get('networkMode','direct'))
            with self._store() as store:
                store['accounts'][account_id]['revocationConfirmed']=confirmed;self._write(store)
        return dict(accountId=account_id,status='signed_out',revocationConfirmed=confirmed)

    def forget(self, account_id):
        """Remove a signed-out local account and its private OAuth attempt metadata."""
        identifier(account_id)
        # Provider writes use this barrier before changing their SQLite settings;
        # taking it here makes the reference check and account removal atomic.
        with barrier(self.registry), self._account_lock(account_id), self._store() as store:
            account = store['accounts'].get(account_id)
            if account is not None:
                if account.get('status', 'signed_out') != 'signed_out' or any(
                        account.get(key) for key in ('access_token', 'refresh_token', 'id_token')):
                    raise AuthError('chatgpt_account_sign_out_required', 409)
            with self.registry.connect() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_provider_settings'"
                ).fetchone()
                if exists:
                    row = connection.execute('SELECT body FROM agent_provider_settings WHERE id=1').fetchone()
                    if row:
                        try:
                            settings = json.loads(row[0])
                        except (TypeError, ValueError):
                            raise AuthError('chatgpt_provider_settings_invalid', 409) from None
                        if (not isinstance(settings, dict) or settings.get('version') != 1
                                or not isinstance(settings.get('items'), list)):
                            raise AuthError('chatgpt_provider_settings_invalid', 409)
                        for item in settings['items']:
                            config = item.get('config', {}) if isinstance(item, dict) else {}
                            if not isinstance(item, dict) or not isinstance(config, dict):
                                raise AuthError('chatgpt_provider_settings_invalid', 409)
                            if (config.get('auth_method') == 'chatgpt_oauth'
                                    and item.get('accountId') == account_id):
                                raise AuthError('chatgpt_account_in_use', 409)
            changed = False
            for attempt_id, attempt in list(store['attempts'].items()):
                if attempt.get('accountId') != account_id:
                    continue
                if attempt.get('status') == 'exchanging':
                    raise AuthError('chatgpt_account_busy', 409)
                del store['attempts'][attempt_id]
                changed = True
            if account is not None:
                del store['accounts'][account_id]
                changed = True
            if changed:
                self._write(store)
        return dict(accountId=account_id,status='forgotten')

    def change(self, body, port):
        if not isinstance(body,dict):
            raise AuthError('chatgpt_invalid_request')
        action=body.get('action')
        if action=='start':
            return self.start(body,port)
        identifier(body.get('requestId'))
        if action=='cancel' and set(body)=={'action','requestId','attemptId'}:
            return self.cancel(body['attemptId'])
        if action in ('models','logout','forget') and set(body)=={'action','requestId','accountId'}:
            if action == 'models':
                return self.models(body['accountId'])
            if action == 'logout':
                return self.logout(body['accountId'],body['requestId'])
            return self.forget(body['accountId'])
        raise AuthError('chatgpt_invalid_request')
