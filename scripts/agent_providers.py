"""Local administrator provider settings; keys remain in the private vault."""
import hashlib
import json
import re
import uuid
import time

from provider_runtime import Config, RuntimeError as DriverError
from task_transfer import barrier


class ProviderError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.status=status
        self.body=dict(error=code,message=message)


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'))


def probe_settings_fingerprint(item):
    from dataclasses import asdict
    config=asdict(Config(**item['config']))
    # Preserve receipts issued before the optional ChatGPT authorization field.
    if config['auth_method']=='api_key':
        config.pop('auth_method')
    value=dict(config=config,credentialId=item.get('credentialId',item['id']))
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def probe_availability(receipt):
    status=receipt.get('status')
    diagnostics=receipt.get('diagnostics') or []
    diagnostic=diagnostics[-1] if diagnostics else {}
    category=diagnostic.get('category')
    state=('available' if status=='completed' else 'checking' if status=='running'
           else 'outcome_unknown' if status in ('outcome_unknown','interrupted')
           else category if category in ('quota','rate_limit','rate_limit_or_quota','auth','dns','tls','connect','timeout')
           else 'failed')
    # Legacy 429 receipts do not distinguish quota from throttling.
    if diagnostic.get('httpStatus')==429 and not any(diagnostic.get(key) for key in ('providerErrorCode','providerErrorType')):
        state='rate_limit_or_quota'
    return dict(status=state,requestId=receipt['requestId'],checkedAt=receipt['updatedAt'],
                **{key:diagnostic[key] for key in ('httpStatus','providerErrorCode','providerErrorType') if key in diagnostic})


class Providers:
    def __init__(self, registry):
        self.registry=registry

    def read(self, connection=None):
        if connection is None:
            with self.registry.connect() as connection:
                return self.read(connection)
        exists=connection.execute("SELECT 1 FROM sqlite_master WHERE name='agent_provider_settings'").fetchone()
        row=connection.execute('SELECT body FROM agent_provider_settings WHERE id=1').fetchone() if exists else None
        value=json.loads(row[0]) if row else dict(version=1,default='none',items=[])
        # Read old settings without rewriting their database. Native execution
        # is no longer an executor in the independent pipeline.
        if isinstance(value, dict) and value.get('default') == 'codex':
            value = {**value, 'default':'none'}
        if not isinstance(value,dict) or value.get('version')!=1 or not isinstance(value.get('items'),list) or len(value['items'])>16:
            raise ProviderError('provider_configuration','Preserve invalid provider configuration for recovery')
        for item in value['items']:
            try:
                config=Config(**item['config'])
                if config.auth_method=='chatgpt_oauth' and not re.fullmatch('[0-9a-f]{32}',item.get('accountId','')):
                    raise DriverError('invalid_chatgpt_account')
            except (KeyError,TypeError,DriverError):
                raise ProviderError('provider_configuration','Preserve invalid provider configuration for recovery') from None
        if value.get('default') != 'none' and not any(item['id']==value.get('default') for item in value['items']):
            raise ProviderError('provider_unavailable','Select an available agent provider',409)
        return value,hashlib.sha256(encoded(value).encode()).hexdigest()

    def catalog(self):
        with self.registry.connect() as connection:
            value,revision=self.read(connection)
            exists=connection.execute("SELECT 1 FROM sqlite_master WHERE name='agent_provider_probe_latest'").fetchone()
            identifiers=[item['id'] for item in value['items']]
            latest={row['provider']:json.loads(row['result']) for row in connection.execute(
                'SELECT latest.provider,requests.result FROM agent_provider_probe_latest latest '
                'JOIN agent_provider_requests requests ON requests.id=latest.request_id '
                'WHERE latest.provider IN ('+','.join('?' for _ in identifiers)+')',identifiers).fetchall()} if exists and identifiers else {}
        accounts=self._auth_accounts(value['items'])
        def availability(item):
            receipt=latest.get(item['id'])
            if (item['config'].get('auth_method')=='chatgpt_oauth' and
                    self.authentication(item,accounts)['status']=='refresh_pending'):
                return dict(status='auth_pending',**(
                    dict(requestId=receipt['requestId'],checkedAt=receipt['updatedAt']) if receipt else {}))
            if (item['config'].get('auth_method')=='chatgpt_oauth' and
                    self.authentication(item,accounts)['status'] in ('refresh_unknown','reauth_required','signed_out')):
                return dict(status='sign_in_required',**(
                    dict(requestId=receipt['requestId'],checkedAt=receipt['updatedAt']) if receipt else {}))
            if receipt is None:
                return dict(status='not_checked')
            if receipt.get('settingsFingerprint')!=self._probe_fingerprint(item,accounts):
                return dict(status='settings_changed')
            return probe_availability(receipt)
        return dict(revision=revision,default=value['default'],items=[dict(id=item['id'],name=item['name'],
            provider=item['config']['provider'],model=item['config']['model'],endpoint=item['config'].get('endpoint',''),
            networkMode=item['config'].get('network_mode','direct'),
            authentication=self.authentication(item,accounts),availability=availability(item),
            capabilities=dict(hubResult=True,nativeChat=False,sourceExecution=False)) for item in value['items']])

    def selected(self):
        value,_=self.read()
        return next((item for item in value['items'] if item['id']==value['default']),None)

    def credential(self, item):
        if item['config'].get('auth_method')=='chatgpt_oauth':
            from chatgpt_auth import ChatGPTAuth, AuthError
            try:
                return ChatGPTAuth(self.registry).access_token(item['accountId'],item['config'].get('network_mode','direct'))
            except AuthError as error:
                raise DriverError(error.body['error'],diagnostic=error.diagnostic) from None
        import secret_vault
        return secret_vault.get(self.registry,item.get('credentialId',item['id']))

    def _auth_accounts(self, items):
        if not any(item['config'].get('auth_method')=='chatgpt_oauth' for item in items):
            return {}
        from chatgpt_auth import ChatGPTAuth
        return {account['id']:account for account in ChatGPTAuth(self.registry).catalog()['accounts']}

    def authentication(self, item, accounts=None):
        if item['config'].get('auth_method')!='chatgpt_oauth':
            return dict(method='api_key',quotaSource='provider_api')
        accounts=self._auth_accounts([item]) if accounts is None else accounts
        account=accounts.get(item['accountId'],{})
        return dict(method='chatgpt_oauth',quotaSource='chatgpt_plan',accountId=item['accountId'],
            label=account.get('label','ChatGPT'),status=account.get('status','signed_out'),
            planUsageEnabled=account.get('planUsageEnabled',False))

    def _probe_fingerprint(self, item, accounts=None):
        base=probe_settings_fingerprint(item)
        if item['config'].get('auth_method')!='chatgpt_oauth':
            return base
        accounts=self._auth_accounts([item]) if accounts is None else accounts
        account=accounts.get(item['accountId'],{})
        return hashlib.sha256(encoded([base,item['accountId'],account.get('generation'),
            account.get('status'),account.get('planUsageEnabled')]).encode()).hexdigest()

    def remove_credential(self, identifier):
        """Remove only this configuration's association under the vault lock."""
        import base64
        import os
        import secret_vault
        from hub_lifecycle import atomic_json, file_lock
        home=secret_vault.private_home(self.registry)
        with file_lock(home / 'provider-credentials.lock',timeout=2):
            value=secret_vault.read(self.registry)
            if identifier not in value:
                return
            del value[identifier]
            path=home / 'provider-credentials.json'
            content=base64.b64encode(secret_vault._protect(json.dumps(value).encode())).decode('ascii')
            atomic_json(path,dict(version=1,protection='windows-dpapi' if os.name=='nt' else 'private-file',content=content))
            os.chmod(path,0o600)

    def cleanup_credentials(self, connection):
        """Finish durable private cleanup intents after their metadata commit."""
        for row in connection.execute('SELECT id FROM agent_provider_cleanup').fetchall():
            try:
                self.remove_credential(row[0])
            except (OSError,ValueError):
                # Keep the intent for an exact retry or later provider change.
                continue
            connection.execute('DELETE FROM agent_provider_cleanup WHERE id=?',(row[0],))
            connection.commit()

    def change(self, body):
        if isinstance(body, dict) and body.get('action') == 'probe':
            return self.probe(body)
        common={'action','expected','requestId'}
        action=body.get('action') if isinstance(body,dict) else None
        allowed={'save':common|{'name','provider','model','endpoint','apiKey'},
            'save-chatgpt':common|{'name','model','accountId','networkMode'},'select':common|{'id'},'delete':common|{'id'}}
        fields=set(body) if isinstance(body,dict) else set()
        valid_fields=action in allowed and (fields==allowed[action] or (action=='save' and
            fields-{'id','networkMode'}==allowed[action]) or (action=='save-chatgpt' and fields-{'id'}==allowed[action]))
        if not valid_fields or not isinstance(body['requestId'],str) or not re.fullmatch('[0-9a-f]{32}',body['requestId']):
            raise ProviderError('invalid_provider_request','Use an explicit provider operation and request ID')
        fingerprint=hashlib.sha256(encoded(body).encode()).hexdigest()
        with barrier(self.registry),self.registry.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                connection.execute('CREATE TABLE IF NOT EXISTS agent_provider_settings(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL)')
                connection.execute('CREATE TABLE IF NOT EXISTS agent_provider_requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL)')
                connection.execute('CREATE TABLE IF NOT EXISTS agent_provider_cleanup(id TEXT PRIMARY KEY)')
                receipt=connection.execute('SELECT fingerprint,result FROM agent_provider_requests WHERE id=?',(body['requestId'],)).fetchone()
                if receipt:
                    if receipt[0]!=fingerprint:
                        raise ProviderError('provider_request_conflict','Request ID has different content',409)
                    connection.commit()
                    self.cleanup_credentials(connection)
                    return json.loads(receipt[1])
                value,revision=self.read(connection)
                if body['expected']!=revision:
                    raise ProviderError('provider_revision_conflict','Provider settings changed; refresh before editing',409)
                existing=next((item for item in value['items'] if item['id']==body.get('id')),None)
                if action=='delete':
                    if existing is None:
                        raise ProviderError('provider_unavailable','Select an available provider',409)
                    identifier=existing['id']
                    credential_ids=[] if existing['config'].get('auth_method')=='chatgpt_oauth' else [existing.get('credentialId',identifier),*existing.get('retiredCredentialIds',[])]
                    for credential_id in dict.fromkeys(credential_ids):
                        connection.execute('INSERT OR IGNORE INTO agent_provider_cleanup VALUES(?)',(credential_id,))
                    value['items'].remove(existing)
                    if value['default']==identifier:
                        value['default']='none'
                elif action=='select':
                    if body['id'] != 'none' and not any(item['id']==body['id'] for item in value['items']):
                        raise ProviderError('provider_unavailable','Select an available provider',409)
                    value['default']=identifier=body['id']
                elif action=='save-chatgpt':
                    from chatgpt_auth import ChatGPTAuth
                    from dataclasses import asdict
                    if 'id' in body and (existing is None or existing['config'].get('auth_method')!='chatgpt_oauth'):
                        raise ProviderError('provider_auth_mismatch','Create a separate ChatGPT provider')
                    account=ChatGPTAuth(self.registry).account(body['accountId'])
                    if not account or not account['planUsageEnabled']:
                        raise ProviderError('chatgpt_plan_permission_required','Authorize ChatGPT plan usage first',409)
                    if body['model'] not in {model['slug'] for model in account['models']}:
                        raise ProviderError('chatgpt_model_unavailable','Choose a model from this account catalog',409)
                    if not isinstance(body['name'],str) or not 1<=len(body['name'].strip())<=160:
                        raise ProviderError('invalid_provider_name','Supply a bounded provider name')
                    if existing is None and len(value['items'])>=16:
                        raise ProviderError('provider_limit','At most sixteen provider configurations are supported')
                    identifier=existing['id'] if existing else uuid.uuid4().hex
                    config=Config(**{**(existing['config'] if existing else {}), 'provider':'responses',
                        'model':body['model'],'credential_env':'PROJECT_HUB_CHATGPT_'+identifier.upper(),
                        'auth_method':'chatgpt_oauth','network_mode':body['networkMode']})
                    updated=dict(id=identifier,name=body['name'].strip(),config=asdict(config),accountId=account['id'])
                    if existing:
                        value['items'][value['items'].index(existing)]=updated
                    else:
                        value['items'].append(updated);value['default']=identifier
                else:
                    if existing and existing['config'].get('auth_method')=='chatgpt_oauth':
                        raise ProviderError('provider_auth_mismatch','Keep API-key and ChatGPT providers separate')
                    if 'id' in body and existing is None:
                        raise ProviderError('provider_unavailable','Select an available provider',409)
                    if existing is None and len(value['items'])>=16:
                        raise ProviderError('provider_limit','At most sixteen provider configurations are supported')
                    if not isinstance(body['name'],str) or not 1<=len(body['name'].strip())<=160:
                        raise ProviderError('invalid_provider_name','Supply a bounded provider name')
                    identifier=existing['id'] if existing else uuid.uuid4().hex
                    config=Config(**{**(existing['config'] if existing else {}),
                        'provider':body['provider'],'model':body['model'],'endpoint':body['endpoint'],
                        'network_mode':body.get('networkMode',existing['config'].get('network_mode','direct') if existing else 'direct'),
                        'credential_env':existing['config']['credential_env'] if existing else 'PROJECT_HUB_API_'+identifier.upper()})
                    from dataclasses import asdict
                    import secret_vault
                    if existing and body['apiKey']=='':
                        if any(existing['config'].get(key,'')!=getattr(config,key) for key in ('provider','endpoint')):
                            raise ProviderError('provider_key_required','Supply a new API key when changing protocol or endpoint')
                        credential_id=existing.get('credentialId',identifier)
                    else:
                        # A replacement key gets a fresh slot: a failed metadata
                        # commit can never attach it to the previous endpoint.
                        credential_id=uuid.uuid4().hex if existing else identifier
                        secret_vault.save(self.registry,credential_id,body['apiKey'])
                    updated=dict(existing or {},id=identifier,name=body['name'].strip(),config=asdict(config))
                    if credential_id!=identifier:
                        updated['credentialId']=credential_id
                    if existing and credential_id!=existing.get('credentialId',identifier):
                        # Retire old slots only after metadata commits; keep
                        # their ownership for deletion if cleanup is interrupted.
                        updated['retiredCredentialIds']=list(dict.fromkeys([
                            *existing.get('retiredCredentialIds',[]),existing.get('credentialId',identifier)]))
                    if existing:
                        value['items'][value['items'].index(existing)]=updated
                    else:
                        value['items'].append(updated)
                        value['default']=identifier
                result=dict(saved=True,id=identifier,requestId=body['requestId'])
                connection.execute('INSERT INTO agent_provider_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(encoded(value),))
                connection.execute('INSERT INTO agent_provider_requests VALUES(?,?,?)',(body['requestId'],fingerprint,encoded(result)))
                if action=='save' and existing and updated.get('retiredCredentialIds'):
                    for retired in updated['retiredCredentialIds']:
                        connection.execute('INSERT OR IGNORE INTO agent_provider_cleanup VALUES(?)',(retired,))
                connection.commit()
                self.cleanup_credentials(connection)
                return result
            except BaseException:
                connection.rollback()
                raise

    def probe_receipt(self, identifier, *, recover=True):
        if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
            raise ProviderError('invalid_provider_request','Use a saved probe request ID')
        with self.registry.connect() as connection:
            exists=connection.execute("SELECT 1 FROM sqlite_master WHERE name='agent_provider_requests'").fetchone()
            row=connection.execute('SELECT result FROM agent_provider_requests WHERE id=?',(identifier,)).fetchone() if exists else None
        if row is None:
            raise ProviderError('provider_probe_not_found','Unknown provider probe',404)
        result=json.loads(row[0])
        if result.get('kind')!='model-probe':
            raise ProviderError('provider_probe_not_found','Unknown provider probe',404)
        if recover and result['status']=='running':
            from hub_lifecycle import file_lock
            try:
                with file_lock(self.registry.home/'.local'/'provider-probes'/(identifier+'.lock'),timeout=0):
                    # A live owner holds this lease throughout dispatch. Never resend.
                    result=self.probe_receipt(identifier,recover=False)
                    if result['status']=='running':
                        result.update(status='outcome_unknown',updatedAt=time.time(),
                            error=dict(code='process_interrupted',message='Probe interrupted; inspect its receipt before a new attempt.'))
                        self._save_probe(result)
            except TimeoutError:
                pass
        return result

    def _save_probe(self, result):
        with barrier(self.registry), self.registry.connect() as connection:
            connection.execute('UPDATE agent_provider_requests SET result=? WHERE id=?',
                (encoded(result),result['requestId']))
            connection.commit()

    def probe(self, body):
        if (set(body)!={'action','id','expected','requestId'} or not isinstance(body['requestId'],str)
                or not re.fullmatch('[0-9a-f]{32}',body['requestId'])):
            raise ProviderError('invalid_provider_request','Use an explicit saved provider and probe request ID')
        from hub_lifecycle import file_lock
        from provider_runtime import HTTP, probe
        from copy import deepcopy
        identifier=body['requestId']
        fingerprint=hashlib.sha256(encoded(body).encode()).hexdigest()
        # Same-ID concurrent requests may read a durable receipt, but never dispatch twice.
        try:
            lease=file_lock(self.registry.home/'.local'/'provider-probes'/(identifier+'.lock'),timeout=0)
            lease.__enter__()
        except TimeoutError:
            with self.registry.connect() as connection:
                row=connection.execute('SELECT fingerprint FROM agent_provider_requests WHERE id=?',(identifier,)).fetchone()
            if row is None:
                raise ProviderError('provider_probe_busy','Probe is being reserved; refresh its receipt shortly',409)
            if row['fingerprint']!=fingerprint:
                raise ProviderError('provider_request_conflict','Request ID has different content',409)
            return self.probe_receipt(identifier)
        try:
            with barrier(self.registry),self.registry.connect() as connection:
                value,revision=self.read(connection)
                exists=connection.execute("SELECT 1 FROM sqlite_master WHERE name='agent_provider_requests'").fetchone()
                prior=connection.execute('SELECT fingerprint,result FROM agent_provider_requests WHERE id=?',(identifier,)).fetchone() if exists else None
                if prior:
                    if prior['fingerprint']!=fingerprint:
                        raise ProviderError('provider_request_conflict','Request ID has different content',409)
                    # Lease is ours; recover any interrupted dispatch without sending.
                    result=json.loads(prior['result'])
                    if result.get('kind')!='model-probe':
                        raise ProviderError('provider_request_conflict','Request ID belongs to a different operation',409)
                    if result['status']=='running':
                        result.update(status='outcome_unknown',updatedAt=time.time(),error=dict(code='process_interrupted',message='Probe interrupted; a new attempt requires an explicit action.'))
                        connection.execute('UPDATE agent_provider_requests SET result=? WHERE id=?',(encoded(result),identifier))
                        connection.commit()
                    return result
                if body['expected']!=revision:
                    raise ProviderError('provider_revision_conflict','Provider settings changed; refresh before testing',409)
                item=deepcopy(next((item for item in value['items'] if item['id']==body['id']),None))
                if item is None:
                    raise ProviderError('provider_unavailable','Select a saved provider',409)
                config=Config(**item['config'])
                connection.execute('CREATE TABLE IF NOT EXISTS agent_provider_requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL)')
                connection.execute('CREATE TABLE IF NOT EXISTS agent_provider_probe_latest(provider TEXT PRIMARY KEY,request_id TEXT NOT NULL)')
                result=dict(requestId=identifier,id=item['id'],kind='model-probe',status='running',
                    model=config.model,protocol=config.provider,networkMode=config.network_mode,
                    authentication=self.authentication(item),settingsFingerprint=self._probe_fingerprint(item),
                    createdAt=time.time(),updatedAt=time.time(),diagnostics=[],error=None)
                connection.execute('INSERT INTO agent_provider_requests VALUES(?,?,?)',(identifier,fingerprint,encoded(result)))
                connection.execute('INSERT INTO agent_provider_probe_latest VALUES(?,?) '
                    'ON CONFLICT(provider) DO UPDATE SET request_id=excluded.request_id',(item['id'],identifier))
                connection.commit()
            def observe(diagnostics):
                result.update(diagnostics=diagnostics,updatedAt=time.time())
                self._save_probe(result)
            transport=HTTP(config.network_mode,observer=observe)
            try:
                key=self.credential(item)
                probe(config,key,transport)
                result.update(status='completed')
                with self.registry.connect() as connection:
                    current,_=self.read(connection)
                if next((entry for entry in current['items'] if entry['id']==item['id']),None)!=item:
                    result.update(status='failed',error=dict(code='provider_revision_conflict',message='Provider changed during the probe; review its captured settings.'))
            except DriverError as error:
                result.update(status='outcome_unknown' if error.outcome_unknown else 'failed',
                    error=dict(code=error.code,message='The provider probe did not complete; inspect its safe diagnostics.'))
                if error.diagnostic and not result['diagnostics']:
                    result['diagnostics']=[error.diagnostic]
            except Exception:
                sent=bool(result['diagnostics'])
                result.update(status='outcome_unknown' if sent else 'failed',
                    error=dict(code='provider_probe_unknown' if sent else 'provider_credential_unavailable',
                               message='The provider probe requires review.'))
            result['updatedAt']=time.time()
            self._save_probe(result)
            return result
        finally:
            lease.__exit__(None,None,None)
