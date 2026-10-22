"""Bounded loopback transport. Never falls back to client-side storage."""
import json
import re
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from hub_core import HubError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, url, timeout=15):
        if not isinstance(url, str):
            raise ValueError('Use a loopback Project Hub server URL')
        parts=urlsplit(url)
        if parts.scheme!='http' or parts.hostname not in ('127.0.0.1','localhost') or parts.username or parts.password or parts.path not in ('','/') or parts.query or parts.fragment:
            raise ValueError('Use a loopback Project Hub server URL')
        self.url=url.rstrip('/')+'/api/v1/plugin/call'
        self.timeout=timeout
        self.notice_cursors = {}
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def hook(self, raw):
        # Send identity and affected paths, never prompts, file content or outputs.
        tool_hook = raw.get('hook_event_name') in ('PreToolUse', 'PostToolUse')
        if tool_hook and (raw.get('tool_name') not in ('apply_patch','Edit','Write')
                          or not raw.get('session_id') or not raw.get('cwd')):
            return {}
        event={k:raw[k] for k in ('session_id','agent_id','cwd','hook_event_name','turn_id','source','tool_name') if k in raw}
        args=raw.get('tool_input',{})
        if raw.get('tool_name') == 'apply_patch' and isinstance(args,str):
            args={'patch':args}
        if isinstance(args,dict) and raw.get('tool_name') in ('apply_patch','Edit','Write'):
            paths={k:args[k] for k in ('file_path','path') if isinstance(args.get(k),str)}
            command=args.get('command',args.get('patch',''))
            if isinstance(command,str):
                paths['patch']='\n'.join(re.findall(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): .+$',command,re.M))
            event['tool_input']=paths
        if tool_hook:
            try:
                self.call(event.get('cwd'),event.get('session_id'),'hook',event)
            except Exception:
                pass
            return {}
        result=self.call(event.get('cwd'),event.get('session_id'),'hook',event)
        if result.get('systemMessage'):
            return result
        if not result.get('observed'):
            return {}
        from hub_plugin import hook_reminder
        from hub_core import hook_actor
        return hook_reminder(hook_actor(event))

    def call(self, cwd, session, tool, arguments):
        if tool=='hub_wait':
            duration=arguments.get('seconds',20)
            if not isinstance(duration,int) or not 0<=duration<=20:raise HubError('invalid_wait','seconds must be 0–20')
            deadline=time.monotonic()+duration
            while True:
                result=self.call(cwd,session,'hub_context',{'after':arguments['after']})
                if result.get('changes') or time.monotonic()>=deadline:return result
                time.sleep(.25)
        data=json.dumps(dict(cwd=str(cwd),session=session,tool=tool,arguments=arguments)).encode()
        if tool in ('hub_context', 'hub_begin', 'hub_report'):
            data=json.dumps(dict(cwd=str(cwd),session=session,tool=tool,arguments=arguments,
                                 noticeAfter=self.notice_cursors.get((session,str(cwd)),0))).encode()
        if len(data)>16000:raise HubError('request_too_large','Use a smaller request')
        request=Request(self.url,data=data,headers={'Content-Type':'application/json'})
        read_only = tool in ('hub_context', 'hub_memory', 'hub_migration_preview', 'hub_notice') or (
            tool == 'hub_review' and arguments.get('action') == 'summary') or (
            tool == 'hub_git_batch' and arguments.get('action') in ('preview', 'details')) or (
            tool=='hub_knowledge' and arguments.get('action') in ('context','search','read','history','job','import-read','export','research-capabilities','research-object','research-result','research-history','research-providers')) or (
            tool=='hub_knowledge' and arguments.get('action')=='impact' and not arguments.get('args',{}).get('record')) or (
            tool in ('hub_plan', 'hub_settings') and not any(
                key in arguments for key in ('stage', 'decision', 'estimate', 'primary', 'patch', 'reset')))
        recovery = None
        if tool == 'hub_report':
            recovery = dict(work=arguments.get('work'), revision=arguments.get('revision'))
        elif tool == 'hub_review' and arguments.get('action') in ('propose','estimate'):
            recovery = dict(action=arguments['action'], actionId=arguments.get('actionId'), work=arguments.get('work'),
                            expected=arguments.get('expected'), instruction='Read the action receipt/result before retrying the same publication')
        elif tool == 'hub_check':
            recovery = dict(runId=arguments.get('runId'), status=arguments.get('status'))
        elif tool=='hub_knowledge' and arguments.get('action') in ('changeset','import-apply','restore'):
            recovery=dict(action=arguments['action'],key=arguments.get('args',{}).get('key'),expected=arguments.get('args',{}).get('expected'))
        elif tool == 'hub_begin':
            # begin deduplicates this exact session/task/stage/title/scope. Its
            # original server snapshot survives a lost acknowledgement; changing
            # any field on retry would instead establish a later boundary.
            recovery = dict(session=session, task=arguments.get('task'),
                            stage=arguments.get('stage'), title=arguments.get('title'),
                            resources=arguments.get('resources'), mode=arguments.get('mode', 'write'))
            recovery.update({key: arguments[key] for key in ('stages', 'phase') if key in arguments})
        elif tool == 'hub_git_batch' and arguments.get('action') == 'reconcile':
            recovery = dict(action='reconcile', batchId=arguments.get('confirmed'), commit=arguments.get('commit'),
                            targets=arguments.get('targets'), expected=arguments.get('expected'),
                            reason=arguments.get('reason'), actor=session)
        timeout = min(self.timeout, .5) if tool == 'hook' and arguments.get('hook_event_name') in ('PreToolUse','PostToolUse') else self.timeout
        if tool == 'hub_notice':
            seconds = arguments.get('seconds', 0)
            if isinstance(seconds, bool) or not isinstance(seconds, int) or not 0 <= seconds <= 45:
                raise HubError('invalid_wait', 'seconds must be 0–45')
            timeout = max(timeout, seconds + 3)
        result = self.request_json(request, timeout=timeout, write=not read_only, recovery=recovery)
        notice = result.get('parallelNotices')
        if isinstance(notice, dict) and isinstance(notice.get('cursor'), int):
            key=(session,str(cwd))
            self.notice_cursors[key]=max(self.notice_cursors.get(key,0),notice['cursor'])
        return result

    def request_json(self, request, *, timeout=None, write=True, recovery=None):
        """A missing acknowledgement is not evidence that the server did not write."""
        reason = 'transport_error'
        try:
            with self.opener.open(request,timeout=self.timeout if timeout is None else timeout) as response:
                raw=response.read(256001)
                reason = 'response_too_large' if len(raw) > 256000 else 'invalid_response'
                if len(raw)>256000:raise ValueError('Response too large')
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError('Expected a response object')
                return result
        except HTTPError as error:
            try:
                with error: raw=error.read(16001)
                body=json.loads(raw) if len(raw) <= 16000 else {}
            except (OSError, HTTPException, ValueError):body={}
            if not isinstance(body,dict):body={}
            if error.code >= 500 or not body.get('error'):
                self.unknown_response(write, recovery, 'http_error', error)
            # Preserve owners, work handles and revisions: callers need these to
            # reuse an existing result or wait for the right work, not just fail.
            details={k:v for k,v in body.items() if k not in ('error','message')}
            raise HubError(body.get('error','server_error'),body.get('message','Project Hub rejected the request'),**details) from None
        except (OSError,URLError,HTTPException,ValueError) as error:
            if isinstance(error, TimeoutError) or isinstance(getattr(error, 'reason', None), TimeoutError):
                reason = 'timeout'
            self.unknown_response(write, recovery, reason, error)

    @staticmethod
    def unknown_response(write, recovery, reason, error):
        if not write:
            raise HubError('server_unavailable', 'Project Hub response unavailable', reason=reason) from error
        details = dict(writeOutcome='unknown', reason=reason, retrySafe=recovery is not None)
        message = 'Project Hub acknowledgement unavailable; the server may have saved the write.'
        if recovery is not None:
            details['recovery'] = recovery
            message += ' Retry the identical request with its original identifiers and content.'
        else:
            message += ' Read back the result before retrying.'
        raise HubError('write_outcome_unknown', message, **details) from error
