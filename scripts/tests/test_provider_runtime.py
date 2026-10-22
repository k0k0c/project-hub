import json
import io
from pathlib import Path
import sys
import threading
import unittest
import urllib.error
import socket
import ssl
import urllib.request
from email.message import Message
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from agent_sdk import Client
from provider_runtime import Config, Driver, HubTools, HTTP, RuntimeError, load_config, probe
from outbound_http import opener_for


SCHEMA = {"name": "hub_context", "description": "Read context", "inputSchema": {
    "type": "object", "properties": {"session": {"type": "string"}, "task": {"type": "string"}}, "required": ["session"]}}


class Reply:
    def __init__(self, data): self.data = json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size): return self.data[:size]


def stream_reply(events):
    response = Reply({})
    response.headers = {}  # ChatGPT can omit Content-Type; still require SSE framing.
    response.data = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events).encode()
    return response


class HubHTTP:
    def __init__(self, project="p"): self.project, self.calls = project, []
    def open(self, request, timeout):
        body = json.loads(request.data)
        self.calls.append(body)
        return Reply({"connection": {"project": self.project}, "task": body["arguments"].get("task")})


class FakeHTTP:
    def __init__(self, replies): self.replies, self.calls = list(replies), []
    def __call__(self, url, headers, body, timeout, limit):
        self.calls.append((url, headers, body, timeout, limit))
        value = self.replies.pop(0)
        if isinstance(value, Exception): raise value
        return value


def replies(kind):
    if kind == "responses":
        return [{"status": "completed", "output": [{"type": "reasoning", "encrypted_content": "opaque"},
            {"type": "function_call", "call_id": "c", "name": "hub_context", "arguments": '{"task":"t"}'}]},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Analysis"}]}]}]
    if kind == "anthropic":
        return [{"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "c", "name": "hub_context", "input": {"task": "t"}}]},
            {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Analysis"}]}]
    if kind == "gemini":
        return [{"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [
            {"thoughtSignature": "signed-bytes", "functionCall": {"id": "c", "name": "hub_context", "args": {"task": "t"}}}]}}]},
            {"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": "Analysis"}]}}]}]
    return [{"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
        "tool_calls": [{"id": "c", "type": "function", "function": {"name": "hub_context", "arguments": '{"task":"t"}'}}]}}]},
        {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Analysis"}}]}]


class ProviderTests(unittest.TestCase):
    def test_stream_wire_overhead_does_not_consume_decoded_result_limit(self):
        value = dict(status='completed', output=[dict(type='message', content=[dict(type='output_text', text='Analysis')])])
        events = [dict(type='response.output_text.delta', delta='Analysis') for _ in range(40)]
        response = stream_reply([*events, dict(type='response.completed', response=value)])
        self.assertGreater(len(response.data), 1000)
        http = self.http_with(reply=response)
        self.assertEqual(http('https://api.openai.com/v1/responses', {}, dict(stream=True), 2, 1000), value)
        self.assertEqual(http.opener.calls, 1)

    def test_stream_wire_and_decoded_results_remain_independently_bounded(self):
        for oversized_wire in (False, True):
            with self.subTest(oversized_wire=oversized_wire):
                value = dict(status='completed', output=[dict(type='message', content=[dict(type='output_text', text='x' * 1000)])])
                events = [dict(type='response.completed', response=value)]
                if oversized_wire:
                    events = [dict(type='response.output_text.delta', delta='x') for _ in range(100)] + events
                response = stream_reply(events)
                http = self.http_with(reply=response)
                with self.assertRaises(RuntimeError) as caught:
                    http('https://api.openai.com/v1/responses', {}, dict(stream=True), 2, 200)
                self.assertTrue(caught.exception.outcome_unknown)
                self.assertEqual(http.diagnostics[-1]['category'], 'response_limit')
                self.assertEqual(http.opener.calls, 1)

    def test_stream_preserves_done_items_in_order_without_terminal_duplicates(self):
        reasoning = dict(type='reasoning', id='r', encrypted_content='opaque-final')
        message = dict(type='message', id='m', status='completed', role='assistant',
                       content=[dict(type='output_text', text='Analysis')])
        done = [dict(type='response.output_item.done', output_index=index, item=item)
                for index, item in ((1, message), (0, reasoning))]
        for output in (None, [], [reasoning], [reasoning, message]):
            with self.subTest(output=output):
                value = dict(status='completed')
                if output is not None:
                    value['output'] = output
                events = [dict(type='response.output_item.added', output_index=0,
                               item=dict(reasoning, encrypted_content='unfinished')),
                          *done, dict(type='response.completed', response=value)]
                http = self.http_with(reply=stream_reply(events))
                actual = http('https://api.openai.com/v1/responses', {}, dict(stream=True), 2, 10000)
                self.assertEqual(actual['output'], [reasoning, message])
                self.assertEqual(http.opener.calls, 1)

    def test_stream_tool_loop_keeps_reasoning_and_final_text_from_done_events(self):
        driver, hub, _ = self.driver(auth_method='chatgpt_oauth')
        values = replies('responses')
        responses = [stream_reply([
            *(dict(type='response.output_item.done', output_index=i, item=item)
              for i, item in enumerate(value['output'])),
            dict(type='response.completed', response=dict(status='completed', output=[]))])
            for value in values]
        requests = []
        class Opener:
            def open(self, request, timeout):
                requests.append(json.loads(request.data))
                return responses.pop(0)
        http = HTTP(); http.opener = Opener(); driver.transport = http
        result = driver.run('Question')
        self.assertEqual((result['text'], result['turns'], result['toolCalls']), ('Analysis', 2, 1))
        self.assertEqual(len(requests), 2)  # One request per turn; no retries.
        self.assertEqual(requests[1]['input'][2]['encrypted_content'], 'opaque')
        self.assertEqual(requests[1]['input'][-1]['call_id'], 'c')
        self.assertEqual(hub.calls[1]['arguments']['task'], 't')

    def test_stream_invalid_done_items_fail_closed_with_safe_reasons(self):
        item = dict(type='message', id='m', content=[dict(type='output_text', text='SECRET')])
        def done(index=0, value=item):
            return dict(type='response.output_item.done', output_index=index, item=value)
        cases = [
            ([done(-1)], [], 'sse_output_shape'),
            ([done(True)], [], 'sse_output_shape'),
            ([done('0')], [], 'sse_output_shape'),
            ([done(value=None)], [], 'sse_output_shape'),
            ([done(value=dict(item, status='in_progress'))], [], 'sse_output_shape'),
            ([done(1000000000)], [], 'sse_output_gap'),
            ([done(), done()], [], 'sse_output_conflict'),
            ([done(), done(1)], [], 'sse_output_conflict'),
            ([done()], [dict(item, content=[])], 'sse_output_conflict'),
            ([done()], None, 'sse_output_shape'),
        ]
        for events, output, reason in cases:
            with self.subTest(reason=reason, events=events):
                response = stream_reply([*events, dict(type='response.completed',
                    response=dict(status='completed', output=output))])
                http = self.http_with(reply=response)
                with self.assertRaises(RuntimeError) as caught:
                    http('https://api.openai.com/v1/responses', {'Authorization':'Bearer SECRET'}, dict(stream=True), 2, 10000)
                self.assertTrue(caught.exception.outcome_unknown)
                self.assertEqual(http.diagnostics[-1]['parseReason'], reason)
                self.assertNotIn('SECRET', json.dumps(http.diagnostics))
                self.assertEqual(http.opener.calls, 1)

    def test_done_items_require_completed_inference_before_tool_dispatch(self):
        item = replies('responses')[0]['output'][1]
        done = dict(type='response.output_item.done', output_index=0, item=item)
        for terminal in (None, dict(type='response.failed', response=dict(status='failed',
                error=dict(code='subscription_sharing_usage_limit_exceeded'))),
                dict(type='response.incomplete', response=dict(status='incomplete'))):
            with self.subTest(terminal=terminal):
                driver, hub, _ = self.driver(auth_method='chatgpt_oauth')
                http = self.http_with(reply=stream_reply([done, *([terminal] if terminal else [])]))
                driver.transport = http
                with self.assertRaises(RuntimeError): driver.run('Question')
                self.assertEqual(len(hub.calls), 1)  # Binding verification only.
                self.assertEqual(http.opener.calls, 1)

    def test_stream_item_collection_preserves_secret_and_tool_scope_guards(self):
        for item, code in ((dict(type='message', content=[dict(type='output_text', text='provider-private-key')]), 'credential_echo_rejected'),
                           (dict(type='function_call', call_id='c', name='shell', arguments='{}'), 'tool_scope_denied')):
            with self.subTest(code=code):
                driver, hub, _ = self.driver(auth_method='chatgpt_oauth')
                http = self.http_with(reply=stream_reply([
                    dict(type='response.output_item.done', output_index=0, item=item),
                    dict(type='response.completed', response=dict(status='completed', output=[]))]))
                driver.transport = http
                with self.assertRaisesRegex(RuntimeError, code): driver.run('Question')
                self.assertEqual(len(hub.calls), 1)
                self.assertEqual(http.opener.calls, 1)
                self.assertNotIn('provider-private-key', json.dumps(http.diagnostics))

    def test_unexpected_stream_format_records_only_safe_fixed_hints_without_retry(self):
        duplicate = Message()
        duplicate['Content-Type'] = 'text/event-stream'
        duplicate['Content-Type'] = 'text/html; private=SECRET'
        cases = [
            ({'Content-Type':'application/json; private=SECRET'},b'{"private":"SECRET"}','application/json','json-like','missing'),
            ({'content-type':'TEXT/HTML; charset=utf-8'},b'<!doctype html><html>SECRET</html>','text/html','html-like','missing'),
            ({'Content-Type':'SECRET','Content-Encoding':'SECRET'},b'private SECRET','other','other','other'),
            ({'Content-Type':'application/x-text/event-stream'},b'', 'other','empty','missing'),
            ({'Content-Type':'text/plain','Content-Encoding':'gzip'},b'\x1f\x8bSECRET','text/plain','gzip','gzip'),
            (duplicate,b'<html>SECRET</html>','other','html-like','missing'),
        ]
        for headers,raw,media,kind,encoding in cases:
            with self.subTest(media=media,kind=kind):
                response=Reply({});response.data=raw;response.headers=headers;response.status=200
                http=self.http_with(reply=response)
                with self.assertRaises(RuntimeError) as caught:
                    http('https://api.openai.com/v1/responses',{'Authorization':'Bearer SECRET'},dict(stream=True),60,64000)
                diagnostic=http.diagnostics[-1]
                self.assertTrue(caught.exception.outcome_unknown)
                self.assertEqual(diagnostic['parseReason'],'sse_content_type')
                self.assertEqual(diagnostic['responseMediaType'],media)
                self.assertEqual(diagnostic['responseBodyKind'],kind)
                self.assertEqual(diagnostic['responseContentEncoding'],encoding)
                self.assertEqual(diagnostic['responseBytes'],len(raw))
                self.assertEqual(diagnostic['httpStatus'],200)
                self.assertEqual(http.opener.calls,1)
                self.assertNotIn('SECRET',json.dumps(http.diagnostics))

    def test_missing_content_type_requires_valid_sse_framing_and_completed_inference(self):
        completed=b'event: response.completed\ndata: {"response":{"status":"completed","output":[]}}\n\n'
        for raw,category,reason in (
                (b'\xef\xbb\xbf: heartbeat\nid: 1\nretry: 1000\n\n'+completed,None,None),
                (b'data: {"type":"response.created"}\n\n','parse','sse_no_terminal'),
                (b'<html>SECRET</html>','parse','sse_framing'),
                (b'<html>SECRET\n'+completed+b'</html>','parse','sse_framing'),
                (b'{"status":"completed","output":[],"private":"SECRET"}','parse','sse_framing'),
                (b'data: SECRET\n\n','parse','sse_json'),
                (b'data: \xff\n\n','parse','sse_decode'),
                (b'data: {"type":"response.completed","response":{"status":"in_progress"}}\n\n','parse','sse_completed_status'),
                (b'data: {"type":"response.failed","response":{"error":{"code":"subscription_sharing_usage_limit_exceeded","message":"SECRET"}}}\n\n','quota',None)):
            with self.subTest(category=category,reason=reason):
                response=Reply({});response.data=raw;response.headers={};response.status=200
                http=self.http_with(reply=response)
                args=('https://api.openai.com/v1/responses',{'Authorization':'Bearer SECRET'},dict(stream=True),60,64000)
                if category:
                    with self.assertRaises(RuntimeError):http(*args)
                    self.assertEqual(http.diagnostics[-1]['category'],category)
                    self.assertEqual(http.diagnostics[-1].get('parseReason'),reason)
                    self.assertEqual(http.diagnostics[-1]['outcomeUnknown'],category=='parse')
                else:
                    self.assertEqual(http(*args),dict(status='completed',output=[]))
                    self.assertEqual(http.diagnostics[-1]['status'],'completed')
                    self.assertFalse(http.diagnostics[-1]['outcomeUnknown'])
                self.assertEqual(http.diagnostics[-1]['responseMediaType'],'missing')
                self.assertEqual(http.opener.calls,1)
                self.assertNotIn('SECRET',json.dumps(http.diagnostics))

    def test_stream_accept_and_media_type_parameters_require_real_completed_event(self):
        response=Reply({});response.data=b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n'
        response.headers={'cOnTeNt-TyPe':'Text/Event-Stream; charset=utf-8; private=SECRET'}
        http=self.http_with(reply=response)
        requests=[]
        original_open=http.opener.open
        def capture(request,timeout):
            requests.append(request)
            return original_open(request,timeout)
        http.opener.open=capture
        self.assertEqual(http('https://api.openai.com/v1/responses',{},dict(stream=True),60,64000)['status'],'completed')
        self.assertEqual(requests[0].get_header('Accept'),'text/event-stream')
        self.assertEqual(http.diagnostics[-1]['responseMediaType'],'text/event-stream')
        self.assertEqual(http.diagnostics[-1]['responseBodyKind'],'event-stream-like')
        self.assertNotIn('SECRET',json.dumps(http.diagnostics))

    def test_sse_event_field_bom_and_json_unicode_line_separators(self):
        value=dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text='OK\u2028done')])])
        raw='\ufeffevent: response.completed\r\ndata: '+json.dumps(dict(response=value),ensure_ascii=False)+'\r\n\r\ndata: [DONE]\r\n\r\n'
        response=Reply({});response.data=raw.encode();response.headers={'Content-Type':'text/event-stream'}
        http=self.http_with(reply=response)
        self.assertEqual(http('https://api.openai.com/v1/responses',{},dict(stream=True),60,64000),value)
        self.assertEqual(http.diagnostics[-1]['status'],'completed')

    def test_sse_safe_parse_reasons_never_leak_payload_or_accept_missing_completion(self):
        cases=[
            ('application/json',b'{"private":"SECRET"}','sse_content_type'),
            ('text/event-stream',b'data: \xff\n\n','sse_decode'),
            ('text/event-stream',b'data: {SECRET\n\n','sse_json'),
            ('text/event-stream',b'data: ["SECRET"]\n\n','sse_event_shape'),
            ('text/event-stream',b'data: {"type":"response.created","private":"SECRET"}\n\n','sse_no_terminal'),
            ('text/event-stream',b'data: {"type":"response.completed","response":null}\n\n','sse_terminal_payload'),
            ('text/event-stream',b'data: {"type":"response.completed","response":{"status":"in_progress"}}\n\n','sse_completed_status'),
            ('text/event-stream',b'event: response.completed\ndata: {"type":"response.failed","response":{"status":"failed"}}\n\n','sse_event_type_mismatch'),
        ]
        for content_type,raw,reason in cases:
            with self.subTest(reason=reason):
                response=Reply({});response.data=raw;response.headers={'Content-Type':content_type}
                http=self.http_with(reply=response)
                with self.assertRaises(RuntimeError) as caught:http('https://api.openai.com/v1/responses',{'Authorization':'Bearer SECRET'},dict(stream=True),60,64000)
                self.assertTrue(caught.exception.outcome_unknown)
                self.assertEqual(http.diagnostics[-1]['parseReason'],reason)
                self.assertEqual(http.diagnostics[-1]['category'],'parse')
                self.assertNotIn('SECRET',json.dumps(http.diagnostics))

    def test_probe_wait_budget_is_separate_from_analysis_and_never_retries(self):
        for auth in ('api_key','chatgpt_oauth'):
            for deadline,expected in ((120,60),(4,4)):
                with self.subTest(auth=auth,deadline=deadline):
                    transport=FakeHTTP([TimeoutError('no response')])
                    config=Config('responses','configured-model','KEY',auth_method=auth,deadline=deadline)
                    with self.assertRaises(TimeoutError):probe(config,'secret',transport)
                    self.assertEqual(len(transport.calls),1)
                    self.assertEqual(transport.calls[0][3],expected)
                    self.assertLessEqual(transport.calls[0][4],64000)

    def test_read_timeout_preserves_received_headers_and_uncertain_outcome(self):
        response=Reply({});response.status=200;response.headers={'X-Request-ID':'request-read','Content-Type':'text/event-stream'}
        events=[]
        def read(size):
            self.assertEqual(events[-1][-1]['phase'],'read')
            self.assertEqual(events[-1][-1]['httpStatus'],200)
            self.assertEqual(events[-1][-1]['responseMediaType'],'text/event-stream')
            raise TimeoutError('private')
        response.read=read
        http=self.http_with(reply=response);http.observer=lambda values:events.append(values)
        with self.assertRaises(RuntimeError) as caught:http('https://example.invalid',{},dict(),60,100)
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertEqual(http.diagnostics[0]['phase'],'read')
        self.assertEqual(http.diagnostics[0]['timeoutMs'],60000)
        self.assertEqual(http.diagnostics[0]['upstreamRequestId'],'request-read')
        self.assertNotIn('responseBytes',http.diagnostics[0])
        self.assertNotIn('private',json.dumps(events))

    def test_chatgpt_plan_preserves_tools_history_without_unsupported_fields(self):
        driver,hub,http=self.driver(auth_method='chatgpt_oauth')
        self.assertEqual(driver.run('Question')['text'],'Analysis')
        self.assertEqual(len(http.calls),2)
        for _,_,body,_,_ in http.calls:
            self.assertIs(body['stream'],True)
            self.assertIs(body['store'],False)
            self.assertNotIn('max_output_tokens',body)
            self.assertNotIn('tools',body)
            self.assertNotIn('previous_response_id',body)
            self.assertEqual(body['input'][0]['type'],'additional_tools')
            self.assertEqual(body['input'][0]['tools'][0]['name'],'hub_context')
        self.assertEqual(http.calls[1][2]['input'][2]['encrypted_content'],'opaque')
        self.assertEqual(http.calls[1][2]['input'][-1]['call_id'],'c')

    def test_chatgpt_stream_terminal_outcome_and_no_retries(self):
        cases=[('response.completed',dict(status='completed',output=[]),None),
               ('response.failed',dict(status='failed',error=dict(code='subscription_sharing_usage_limit_exceeded',message='SECRET')),'quota'),
               ('response.failed',dict(status='failed',error=dict(code='subscription_sharing_usage_unavailable')),'quota'),
               ('response.incomplete',dict(status='incomplete'),'provider_incomplete')]
        for kind,response,category in cases:
            with self.subTest(kind=kind,response=response):
                raw=(': comment\r\ndata: '+json.dumps(dict(type=kind,response=response))+'\r\n\r\ndata: [DONE]\r\n\r\n').encode()
                reply=Reply({});reply.data=raw;reply.headers={'Content-Type':'text/event-stream'}
                http=self.http_with(reply=reply)
                args=('https://api.openai.com/v1/responses',{'Authorization':'Bearer SECRET'},dict(stream=True),2,10000)
                if category:
                    with self.assertRaises(RuntimeError):http(*args)
                    self.assertEqual(http.diagnostics[-1]['category'],category)
                    self.assertFalse(http.diagnostics[-1]['outcomeUnknown'])
                else:
                    self.assertEqual(http(*args),response)
                self.assertEqual(http.opener.calls,1)
                self.assertNotIn('SECRET',json.dumps(http.diagnostics))

    def test_chatgpt_stream_malformed_truncated_or_conflicting_is_unknown(self):
        for raw in (b'data: []\n\n',b'data: {"type":"response.created"}\n\n',
                    b'data: {"type":"response.completed","response":null}\n\n',
                    b'data: {"type":"response.completed","response":{"status":"completed"}}\n\ndata: {"type":"response.failed"}\n\n'):
            reply=Reply({});reply.data=raw;reply.headers={'Content-Type':'text/event-stream'}
            http=self.http_with(reply=reply)
            with self.assertRaises(RuntimeError):
                http('https://api.openai.com/v1/responses',{},dict(stream=True),2,10000)
            self.assertEqual(http.diagnostics[-1]['category'],'parse')
            self.assertTrue(http.diagnostics[-1]['outcomeUnknown'])

    def http_with(self, *, reply=None, error=None, network_mode='direct'):
        http = HTTP(network_mode)
        class Opener:
            calls=0
            def open(self, request, timeout):
                self.calls+=1
                if error is not None:
                    raise error
                return reply
        http.opener=Opener()
        return http

    def test_http_error_categories_and_safe_correlation_without_retry(self):
        for status,category,unknown in ((401,'auth',False),(403,'auth',False),(404,'endpoint_or_model',False),
                                        (429,'rate_limit_or_quota',False),(503,'server',True),(307,'redirect',False)):
            with self.subTest(status=status):
                headers=Message();headers['X-Request-ID']='upstream-123';headers['Retry-After']='9'
                headers['Authorization']='Bearer forbidden-response-key'
                error=urllib.error.HTTPError('https://example.invalid/private',status,'SECRET upstream body',headers,io.BytesIO(b'SECRET'))
                http=self.http_with(error=error)
                with self.assertRaises(RuntimeError) as caught:
                    http('https://example.invalid/private',{'Authorization':'Bearer SECRET'},dict(prompt='private-prompt'),1,1000)
                diagnostic=http.diagnostics[-1]
                self.assertEqual(diagnostic['category'],category)
                self.assertEqual(diagnostic['httpStatus'],status)
                self.assertEqual(diagnostic['upstreamRequestId'],'upstream-123')
                self.assertEqual(diagnostic['retryAfter'],9)
                self.assertEqual(caught.exception.outcome_unknown,unknown)
                self.assertEqual(http.opener.calls,1)
                self.assertEqual(len(http.diagnostics),1)
                self.assertNotIn('SECRET',json.dumps(diagnostic))
                self.assertNotIn('private',json.dumps(diagnostic))
                self.assertNotIn('forbidden',json.dumps(diagnostic))

    def test_429_reason_distinguishes_quota_from_throttling_without_retaining_body(self):
        for code,kind,category in (
                ('insufficient_quota','insufficient_quota','quota'),
                ('credit_balance_exhausted','insufficient_quota','quota'),
                ('project_spend_limit_exceeded','insufficient_quota','quota'),
                ('organization_spend_limit_exceeded','insufficient_quota','quota'),
                ('organization_usage_limit_exceeded','insufficient_quota','quota'),
                ('usage_limit_exceeded','insufficient_quota','quota'),
                ('rate_limit_exceeded','tokens','rate_limit'),
                ('slow_down','rate_limit_error','rate_limit'),
                (None,'insufficient_quota','quota'),
                ('PRIVATE-KEY','PRIVATE-PROMPT','rate_limit_or_quota')):
            with self.subTest(code=code):
                body=json.dumps(dict(error=dict(code=code,type=kind,message='PRIVATE-PROMPT PRIVATE-KEY',param='private'))).encode()
                error=urllib.error.HTTPError('https://example.invalid/private',429,'private',{},io.BytesIO(body))
                http=self.http_with(error=error)
                with self.assertRaises(RuntimeError) as caught:
                    http('https://example.invalid',{'Authorization':'Bearer PRIVATE-KEY'},dict(),1,100)
                diagnostic=http.diagnostics[-1]
                self.assertEqual(diagnostic['category'],category)
                if code and code!='PRIVATE-KEY':self.assertEqual(diagnostic['providerErrorCode'],code)
                if kind!='PRIVATE-PROMPT':self.assertEqual(diagnostic['providerErrorType'],kind)
                self.assertFalse(caught.exception.outcome_unknown)
                self.assertEqual(http.opener.calls,1)
                self.assertNotIn('PRIVATE',json.dumps(diagnostic))
                self.assertNotIn('message',diagnostic)
                self.assertTrue(error.closed)

    def test_429_malformed_large_and_unreadable_bodies_keep_http_failure(self):
        class Unreadable(io.BytesIO):
            def read(self,size):raise TimeoutError('PRIVATE-KEY')
        bodies=[io.BytesIO(b'not-json PRIVATE-KEY'),io.BytesIO(b'\xff'),io.BytesIO(b'[]'),
                io.BytesIO(b'{"error":[]}'),io.BytesIO(b'['*1500+b']'*1500),io.BytesIO(b' '*16385),Unreadable()]
        for body in bodies:
            with self.subTest(body=type(body).__name__):
                error=urllib.error.HTTPError('https://example.invalid',429,'private',{},body)
                http=self.http_with(error=error)
                with self.assertRaises(RuntimeError):http('https://example.invalid',{},dict(),1,100)
                diagnostic=http.diagnostics[-1]
                self.assertEqual(diagnostic['category'],'rate_limit_or_quota')
                self.assertEqual(diagnostic['httpStatus'],429)
                self.assertFalse(diagnostic['outcomeUnknown'])
                self.assertNotIn('providerErrorCode',diagnostic)
                self.assertNotIn('PRIVATE',json.dumps(diagnostic))
                self.assertTrue(error.closed)

    def test_recognized_error_identifier_cannot_echo_a_request_credential(self):
        error=urllib.error.HTTPError('https://example.invalid',429,'private',{},io.BytesIO(
            b'{"error":{"code":"insufficient_quota","type":"insufficient_quota"}}'))
        http=self.http_with(error=error)
        with self.assertRaises(RuntimeError):
            http('https://example.invalid',{'Authorization':'Bearer insufficient_quota'},dict(),1,100)
        self.assertNotIn('providerErrorCode',http.diagnostics[-1])
        self.assertNotIn('providerErrorType',http.diagnostics[-1])
        self.assertEqual(http.diagnostics[-1]['category'],'rate_limit_or_quota')

    def test_http_dns_tls_connect_timeout_and_parse_remain_distinct(self):
        for error,category,unknown in ((socket.gaierror(-2,'private'), 'dns',False),
                (ssl.SSLCertVerificationError('private'),'tls',False),
                (ConnectionRefusedError(111,'private'),'connect',False),
                (TimeoutError('private'),'timeout',True)):
            with self.subTest(category=category):
                http=self.http_with(error=urllib.error.URLError(error))
                with self.assertRaises(RuntimeError) as caught:http('https://example.invalid',{},dict(),1,100)
                self.assertEqual(http.diagnostics[0]['category'],category)
                self.assertEqual(caught.exception.outcome_unknown,unknown)
                self.assertNotIn('private',json.dumps(http.diagnostics))
        response=Reply({});response.data=b'not-json SECRET'
        http=self.http_with(reply=response)
        with self.assertRaises(RuntimeError) as caught:http('https://example.invalid',{},dict(),1,100)
        self.assertEqual(http.diagnostics[0]['category'],'parse')
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertNotIn('SECRET',json.dumps(http.diagnostics))

    def test_tls_subtypes_are_safe_and_no_headers_do_not_prove_no_dispatch(self):
        certificate=ssl.SSLCertVerificationError('SECRET')
        certificate.verify_code=20
        certificate.verify_message='SECRET'
        protocol=ssl.SSLError('SECRET');protocol.reason='WRONG_VERSION_NUMBER'
        unknown=ssl.SSLError('SECRET');unknown.reason='SECRET'
        for error,kind,uncertain in (
                (certificate,'certificate_verification',False),
                (ssl.SSLEOFError('SECRET'),'unexpected_eof',True),
                (ssl.SSLZeroReturnError('SECRET'),'connection_closed',True),
                (protocol,'protocol_mismatch',True),(unknown,'other',True)):
            with self.subTest(kind=kind):
                http=self.http_with(error=urllib.error.URLError(error))
                with self.assertRaises(RuntimeError) as caught:
                    http('https://example.invalid',{'Authorization':'Bearer SECRET'},dict(test=True),1,100)
                diagnostic=http.diagnostics[-1]
                self.assertEqual(diagnostic['category'],'tls')
                self.assertEqual(diagnostic['tlsReason'],kind)
                self.assertEqual(diagnostic['phase'],'unknown' if uncertain else 'tls')
                self.assertEqual(caught.exception.outcome_unknown,uncertain)
                self.assertEqual(http.opener.calls,1)
                self.assertEqual(diagnostic.get('tlsVerifyCode'),20 if kind=='certificate_verification' else None)
                self.assertNotIn('SECRET',json.dumps(http.diagnostics))

    def test_tls_eof_while_reading_preserves_http_status_and_unknown_outcome(self):
        response=Reply({});response.status=200;response.headers={'X-Request-ID':'read-tls'}
        def read(size):raise ssl.SSLEOFError('SECRET')
        response.read=read
        http=self.http_with(reply=response)
        with self.assertRaises(RuntimeError) as caught:
            http('https://example.invalid',{'Authorization':'Bearer SECRET'},dict(),1,100)
        diagnostic=http.diagnostics[-1]
        self.assertEqual(diagnostic['httpStatus'],200)
        self.assertEqual(diagnostic['phase'],'read')
        self.assertEqual(diagnostic['tlsReason'],'unexpected_eof')
        self.assertEqual(diagnostic['upstreamRequestId'],'read-tls')
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertEqual(http.opener.calls,1)
        self.assertNotIn('SECRET',json.dumps(http.diagnostics))

    def test_http_success_records_headers_and_dispatch_intent_before_open(self):
        response=Reply(dict(ok=True));response.headers={'X-Request-ID':'request-9'};response.status=200
        http=self.http_with(reply=response)
        events=[];http.observer=lambda values:events.append(values)
        result=http('https://example.invalid',{},dict(),1,100)
        self.assertEqual(result,dict(ok=True))
        self.assertEqual([event[-1]['status'] for event in events],['running','running','completed'])
        self.assertEqual(events[1][-1]['phase'],'read')
        self.assertEqual(events[-1][-1]['upstreamRequestId'],'request-9')
        self.assertFalse(events[-1][-1]['outcomeUnknown'])

    def test_system_proxy_is_used_only_for_external_requests_and_defaults_preserved(self):
        with patch('outbound_http.urllib.request.getproxies',return_value={'https':'http://user:private@proxy.invalid:8080'}):
            for url,mode,proxy in (('https://api.example.invalid','system',True),
                    ('https://api.example.invalid','direct',False),('http://127.0.0.1:1','system',False),
                    ('http://localhost:1','system',False),('http://[::1]:1','system',False)):
                opener=opener_for(url,mode)
                handlers=[item for item in opener.handlers if isinstance(item,urllib.request.ProxyHandler)]
                self.assertEqual(bool(handlers),proxy)
            self.assertEqual(Config('responses','m','KEY').network_mode,'direct')
            with self.assertRaises(RuntimeError):Config('responses','m','KEY',network_mode='invalid')

    def test_secret_echo_in_request_id_is_omitted(self):
        reply=Reply(dict(ok=True));reply.headers={'X-Request-ID':'SECRET'}
        http=self.http_with(reply=reply)
        http('https://example.invalid',{'Authorization':'Bearer SECRET'},dict(),1,100)
        self.assertNotIn('upstreamRequestId',http.diagnostics[0])
    def driver(self, kind="responses", data=None, project="p", **limits):
        hub = HubHTTP(project)
        client = Client("http://127.0.0.1:8769", "hub-private-token", opener=hub, session="own-api-run")
        broker = HubTools(client, "p", [SCHEMA])
        fake = FakeHTTP(replies(kind) if data is None else data)
        driver = Driver(Config(kind, "configured-model", "TEST_PROVIDER_KEY", **limits), broker,
                        transport=fake, environ={"TEST_PROVIDER_KEY": "provider-private-key"})
        return driver, hub, fake

    def test_four_protocols_tool_then_result_real_sdk_scope(self):
        for kind in ("responses", "anthropic", "gemini", "chat"):
            with self.subTest(kind=kind):
                driver, hub, http = self.driver(kind)
                result = driver.run("Question")
                self.assertEqual(result["text"], "Analysis")
                self.assertEqual(result["kind"], "hub-result")
                self.assertEqual(result["toolCalls"], 1)
                self.assertEqual(hub.calls[1]["arguments"], {"task": "t", "session": "own-api-run"})
                self.assertNotIn("private", json.dumps(result))
                self.assertNotIn("session", json.dumps(http.calls[0][2]))
                second = http.calls[1][2]
                if kind == "responses":
                    self.assertFalse(second["store"])
                    self.assertEqual(second["input"][1]["encrypted_content"], "opaque")
                    self.assertEqual(second["input"][-1]["call_id"], "c")
                elif kind == "anthropic":
                    self.assertEqual(http.calls[0][1]["anthropic-version"], "2023-06-01")
                    self.assertEqual(second["messages"][-1]["content"][0]["tool_use_id"], "c")
                elif kind == "gemini":
                    self.assertEqual(second["contents"][1]["parts"][0]["thoughtSignature"], "signed-bytes")
                    self.assertEqual(second["contents"][-1]["parts"][0]["functionResponse"]["id"], "c")
                    self.assertEqual(http.calls[0][1], {"x-goog-api-key": "provider-private-key"})
                else:
                    self.assertEqual(second["messages"][-1]["role"], "tool")
                    self.assertEqual(second["messages"][-1]["tool_call_id"], "c")

    def test_project_mismatch_prevents_provider_call(self):
        driver, hub, http = self.driver(project="other")
        with self.assertRaisesRegex(RuntimeError, "project_binding_mismatch"): driver.run("Question")
        self.assertEqual(http.calls, [])

    def test_model_cannot_override_session_or_project(self):
        for field in ("project", "session", "cwd"):
            data = replies("responses")
            data[0]["output"][1]["arguments"] = json.dumps({field: "other"})
            driver, hub, http = self.driver(data=data)
            with self.assertRaisesRegex(RuntimeError, "tool_binding_override"): driver.run("Question")
            self.assertEqual(len(hub.calls), 1)

    def test_unknown_tool_and_knowledge_mutation_denied(self):
        driver, hub, http = self.driver()
        http.replies[0]["output"][1]["name"] = "shell"
        with self.assertRaisesRegex(RuntimeError, "tool_scope_denied"): driver.run("Question")
        with self.assertRaisesRegex(RuntimeError, "tool_scope_unsupported"):
            HubTools(driver.broker.client, "p", [dict(SCHEMA, name="hub_report")])
        broker = HubTools(driver.broker.client, "p", [dict(SCHEMA, name="hub_knowledge")])
        with self.assertRaisesRegex(RuntimeError, "tool_action_denied"):
            broker.call("hub_knowledge", {"action": "changeset"}, 1)

    def test_cancel_before_and_after_http(self):
        event = threading.Event(); event.set()
        driver, hub, http = self.driver()
        with self.assertRaisesRegex(RuntimeError, "cancelled"): driver.run("Question", cancel=event)
        self.assertEqual(hub.calls, [])
        event.clear()
        def transport(*args):
            event.set()
            return replies("responses")[0]
        driver.transport = transport
        with self.assertRaisesRegex(RuntimeError, "cancelled"): driver.run("Question", cancel=event)
        self.assertEqual(len(hub.calls), 1)

    def test_limits_stop_before_tools(self):
        driver, hub, http = self.driver(max_turns=1)
        with self.assertRaisesRegex(RuntimeError, "loop_limit"): driver.run("Question")
        self.assertEqual(len(hub.calls), 1)
        driver, hub, http = self.driver(max_bytes=40)
        with self.assertRaisesRegex(RuntimeError, "context_limit"): driver.run("Question")
        self.assertEqual(http.calls, [])

    def test_tool_budget_reserves_final_answer_and_never_dispatches_over_limit(self):
        data = replies('responses')
        call = dict(data[0]['output'][1], call_id='second')
        data[0]['output'].append(call)
        driver, hub, http = self.driver(data=data, max_tools=1, max_turns=3)
        result = driver.run('Question')
        self.assertEqual(result['text'], 'Analysis')
        self.assertEqual(result['toolCalls'], 1)
        self.assertTrue(result['finalizedForBudget'])
        self.assertEqual(len(hub.calls), 2)  # Binding verification + one permitted read.
        self.assertEqual(len(http.calls), 2)
        final = http.calls[1][2]
        self.assertNotIn('tools', final)
        self.assertIn('Read budget exhausted', final['instructions'])
        outputs = [value for value in final['input'] if value.get('type') == 'function_call_output']
        self.assertEqual(len(outputs), 2)
        self.assertEqual(json.loads(outputs[-1]['output'])['error']['code'], 'tool_budget_exhausted')

    def test_last_turn_has_no_read_tools_for_each_protocol(self):
        for kind in ('responses', 'anthropic', 'gemini', 'chat'):
            with self.subTest(kind=kind):
                driver, hub, http = self.driver(kind=kind, max_turns=2)
                result = driver.run('Question')
                self.assertEqual(result['turns'], 2)
                self.assertEqual(result['toolCalls'], 1)
                self.assertTrue(result['finalizedForBudget'])
                final = http.calls[-1][2]
                if kind == 'gemini':
                    self.assertNotIn('tools', final)
                    prompt = final['systemInstruction']['parts'][0]['text']
                else:
                    self.assertNotIn('tools', final)
                    prompt = final.get('instructions', final.get('system', final.get('messages', [{}])[0].get('content', '')))
                self.assertIn('Read budget exhausted', prompt)

    def test_chatgpt_final_answer_omits_additional_tools_and_keeps_scope_guards(self):
        driver, hub, http = self.driver(auth_method='chatgpt_oauth', max_tools=1)
        self.assertEqual(driver.run('Question')['text'], 'Analysis')
        self.assertFalse(any(item.get('type') == 'additional_tools' for item in http.calls[-1][2]['input']))
        self.assertEqual(len(hub.calls), 2)
        data = replies('responses')
        data[0]['output'].append(dict(data[0]['output'][1], call_id='denied', name='shell'))
        driver, hub, http = self.driver(data=data, max_tools=1)
        with self.assertRaisesRegex(RuntimeError, 'tool_scope_denied'):
            driver.run('Question')
        self.assertEqual(len(hub.calls), 1)

    def test_deadline_and_timeout(self):
        driver, hub, http = self.driver(timeout=3, deadline=5)
        ticks = iter([0, 0, 0, 0, 6])
        driver.clock = lambda: next(ticks)
        with self.assertRaisesRegex(RuntimeError, "deadline_exceeded"): driver.run("Question")
        self.assertEqual(len(hub.calls), 1)
        self.assertLessEqual(http.calls[0][3], 3)

    def test_secret_echo_and_upstream_errors_not_returned(self):
        for key in ("provider-private-key", "hub-private-token"):
            driver, hub, http = self.driver(data=[{"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": key}]}]}])
            with self.assertRaisesRegex(RuntimeError, "credential_echo_rejected"): driver.run("Question")
        driver, hub, http = self.driver(data=[ValueError("provider-private-key")])
        with self.assertRaisesRegex(RuntimeError, "malformed_provider_response") as error: driver.run("Question")
        self.assertNotIn("private", str(error.exception))
        self.assertEqual(len(http.calls), 1)

    def test_http_5xx_has_no_retry_or_body_echo(self):
        http = HTTP()
        http.opener = type("Opener", (), {"open": lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.HTTPError("https://example.invalid", 503, "secret-upstream", {}, None))})()
        with self.assertRaises(RuntimeError) as error: http("https://example.invalid", {}, {}, 1, 100)
        self.assertTrue(error.exception.outcome_unknown)
        self.assertEqual(str(error.exception), "provider_http_error")

    def test_capabilities_config_and_external_config_boundary(self):
        for endpoint in ('https://api.example:99999/v1','https://api.example:invalid/v1'):
            with self.assertRaisesRegex(RuntimeError,'invalid_endpoint'):
                Config('chat','m','KEY',endpoint=endpoint)
        self.assertFalse(Driver.capabilities()["nativeChat"])
        with self.assertRaisesRegex(RuntimeError, "native_chat_unsupported"):
            Config("responses", "m", "KEY", capability="native-chat")
        with self.assertRaisesRegex(RuntimeError, "invalid_endpoint"):
            Config("chat", "m", "KEY", endpoint="https://user:secret@example.invalid/v1")
        with self.assertRaisesRegex(RuntimeError, "external_config_required"):
            load_config(Path(__file__), forbidden_roots=[Path(__file__).parent])
        with self.assertRaisesRegex(RuntimeError, "external_config_required"):
            load_config("relative.json", forbidden_roots=[Path(__file__).parent])

    def test_external_metadata_only_config_and_raw_key_rejected(self):
        external = Path.home() / "isolated-not-created-provider.json"
        metadata = {"provider": "responses", "model": "explicit", "credential_env": "PRIVATE_KEY"}
        with patch.object(Path, "open", return_value=io.BytesIO(json.dumps(metadata).encode())):
            config = load_config(external, forbidden_roots=[Path(__file__).resolve().parents[2]])
        self.assertEqual(config.credential_env, "PRIVATE_KEY")
        metadata["api_key"] = "forbidden-raw-secret"
        with patch.object(Path, "open", return_value=io.BytesIO(json.dumps(metadata).encode())):
            with self.assertRaisesRegex(RuntimeError, "invalid_private_config"):
                load_config(external, forbidden_roots=[Path(__file__).resolve().parents[2]])

    def test_gemini_parallel_calls_without_ids_preserve_order(self):
        data = replies("gemini")
        parts = data[0]["candidates"][0]["content"]["parts"]
        parts[0]["functionCall"].pop("id")
        parts.append({"functionCall": {"name": "hub_context", "args": {"task": "second"}}})
        driver, hub, http = self.driver("gemini", data=data)
        self.assertEqual(driver.run("Question")["toolCalls"], 2)
        continuation = http.calls[1][2]["contents"][-1]["parts"]
        self.assertNotIn("id", continuation[0]["functionResponse"])
        self.assertEqual([p["functionResponse"]["response"]["task"] for p in continuation], ["t", "second"])
        declaration = http.calls[0][2]["tools"][0]["functionDeclarations"][0]
        self.assertIn("parametersJsonSchema", declaration)
        self.assertNotIn("parameters", declaration)

    def test_truncated_and_malformed_ack_never_become_success(self):
        for data, code in (([{"status": "incomplete", "output": []}], "provider_incomplete"),
                           ([{"status": "completed"}], "malformed_provider_response")):
            driver, hub, http = self.driver(data=data)
            with self.assertRaisesRegex(RuntimeError, code): driver.run("Question")
            self.assertEqual(len(http.calls), 1)

    def test_default_grants_reject_mutation_without_client_call(self):
        driver, hub, http = self.driver()
        broker = HubTools(driver.broker.client, "p", [dict(SCHEMA, name="hub_knowledge")])
        with self.assertRaisesRegex(RuntimeError, "tool_action_denied"):
            broker.call("hub_knowledge", {"action": "changeset"}, 1)
        self.assertEqual(hub.calls, [])

    def test_explicit_trusted_grant_allows_changeset(self):
        client = Client("http://127.0.0.1:8769", "hub-private-token", opener=HubHTTP(), session="own-api-run")
        broker = HubTools(client, "p", [dict(SCHEMA, name="hub_knowledge")],
                          trusted_host_grants={"hub_knowledge": {"changeset"}})
        broker.call("hub_knowledge", {"action": "changeset"}, 1)
        self.assertEqual(client.opener.calls[0]["arguments"]["action"], "changeset")

    def test_grant_descriptor_names_are_subset_and_grants_are_immutable(self):
        grants = {"hub_knowledge": {"read"}}
        client = Client("http://127.0.0.1:8769", "hub-private-token", opener=HubHTTP(), session="own-api-run")
        broker = HubTools(client, "p", [dict(SCHEMA, name="hub_knowledge")], trusted_host_grants=grants)
        grants["hub_knowledge"].add("changeset")
        with self.assertRaisesRegex(RuntimeError, "tool_action_denied"):
            broker.call("hub_knowledge", {"action": "changeset"}, 1)
        with self.assertRaisesRegex(RuntimeError, "tool_scope_unsupported"):
            HubTools(client, "p", [dict(SCHEMA, name="unknown")], trusted_host_grants=grants)

    def test_invalid_finite_budgets_and_reference_types_are_rejected(self):
        import math
        base = dict(provider="responses", model="fixture", credential_env="FIXTURE_KEY")
        for field, value in (("timeout", True), ("timeout", math.nan), ("timeout", math.inf),
                             ("deadline", -math.inf), ("model", 1), ("credential_env", None)):
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                Config(**{**base, field: value})


if __name__ == "__main__": unittest.main()
