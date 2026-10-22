"""Bounded HTTP diagnostics. Never retain URLs, credentials or response bodies."""
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import errno
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class OutboundError(Exception):
    def __init__(self, diagnostic):
        super().__init__(diagnostic['category'])
        self.diagnostic = diagnostic
        self.outcome_unknown = diagnostic['outcomeUnknown']


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new):
        return None


def loopback(url):
    host = urllib.parse.urlsplit(url).hostname
    if host == 'localhost':
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or bool(getattr(address,'ipv4_mapped',None) and address.ipv4_mapped.is_loopback)
    except ValueError:
        return False


def effective_mode(url, mode):
    if mode not in ('direct', 'system'):
        raise ValueError('Unsupported network mode')
    return 'direct' if loopback(url) else mode


def opener_for(url, mode):
    effective = effective_mode(url, mode)
    proxy = urllib.request.ProxyHandler({}) if effective == 'direct' else urllib.request.ProxyHandler()
    return urllib.request.build_opener(proxy, NoRedirects())


def _safe_header(value, secrets):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/=+-]{0,159}', value):
        return None
    return None if any(secret and secret in value for secret in secrets) else value


def _header_kind(headers, name, allowed):
    """Retain fixed format names only, never arbitrary reflected header values."""
    values = [value for key, value in headers.items() if key.lower() == name]
    if not values:
        return 'missing'
    if len(values) != 1 or not isinstance(values[0], str):
        return 'other'
    value = values[0].split(';', 1)[0].strip().lower()
    return value if value in allowed else 'other'


def _body_kind(raw):
    """A bounded structural hint; it never validates inference or retains text."""
    if not raw.strip():
        return 'empty'
    if raw.startswith(b'\x1f\x8b'):
        return 'gzip'
    prefix = raw[:1024].decode('utf-8-sig', errors='ignore').lstrip()
    if prefix.startswith(('{', '[')):
        return 'json-like'
    if prefix.lower().startswith(('<!doctype html', '<html', '<head', '<body')):
        return 'html-like'
    if prefix.startswith(('data:', 'event:', ':')):
        return 'event-stream-like'
    return 'other'


def _headers(result, headers, secrets):
    result['responseMediaType'] = _header_kind(headers, 'content-type', frozenset((
        'text/event-stream', 'application/json', 'application/problem+json',
        'text/html', 'text/plain', 'application/octet-stream')))
    result['responseContentEncoding'] = _header_kind(headers, 'content-encoding',
        frozenset(('identity', 'gzip', 'deflate', 'br', 'zstd')))
    headers = {key.lower():value for key,value in headers.items()}
    for name in ('x-request-id', 'request-id', 'x-goog-request-id', 'x-amzn-requestid'):
        value = _safe_header(headers.get(name), secrets)
        if value:
            result['upstreamRequestId'] = value
            break
    retry = headers.get('retry-after')
    if isinstance(retry, str) and len(retry) <= 80 and not any(secret and secret in retry for secret in secrets):
        if retry.isdecimal() and len(retry) <= 7:
            result['retryAfter'] = min(int(retry), 604800)
        else:
            try:
                date = parsedate_to_datetime(retry)
                if date.tzinfo is not None:
                    result['retryAfter'] = date.astimezone(timezone.utc).isoformat()
            except (ValueError, TypeError, OverflowError):
                pass


def _category(error):
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, socket.gaierror):
        return 'dns', 'connect', False
    if isinstance(reason, ssl.SSLCertVerificationError):
        return 'tls', 'tls', False
    if isinstance(reason, ssl.SSLError):
        # No HTTP response does not prove that dispatch did not happen: an SSL
        # EOF can occur while waiting for headers after the request was sent.
        return 'tls', 'unknown', True
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return 'timeout', 'unknown', True
    if isinstance(reason, ConnectionRefusedError) or getattr(reason, 'errno', None) in (
            errno.ECONNREFUSED, errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EACCES):
        return 'connect', 'connect', False
    return 'transport', 'unknown', True


def _tls_details(error):
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if not isinstance(reason, ssl.SSLError):
        return {}
    if isinstance(reason, ssl.SSLCertVerificationError):
        kind = 'certificate_verification'
    elif isinstance(reason, ssl.SSLEOFError):
        kind = 'unexpected_eof'
    elif isinstance(reason, ssl.SSLZeroReturnError):
        kind = 'connection_closed'
    else:
        kind = {
            'UNEXPECTED_EOF_WHILE_READING':'unexpected_eof',
            'CERTIFICATE_VERIFY_FAILED':'certificate_verification',
            'WRONG_VERSION_NUMBER':'protocol_mismatch',
            'TLSV1_ALERT_PROTOCOL_VERSION':'protocol_version',
            'UNSUPPORTED_PROTOCOL':'protocol_version',
            'SSLV3_ALERT_HANDSHAKE_FAILURE':'handshake_rejected',
            'TLSV1_ALERT_INTERNAL_ERROR':'handshake_rejected',
            'DECRYPTION_FAILED_OR_BAD_RECORD_MAC':'record_error',
        }.get(getattr(reason, 'reason', None), 'other')
    result = dict(tlsReason=kind)
    code = getattr(reason, 'verify_code', None)
    if isinstance(reason, ssl.SSLCertVerificationError) and type(code) is int and 0 <= code <= 2147483647:
        result['tlsVerifyCode'] = code
    return result


_QUOTA_CODES = frozenset(('insufficient_quota', 'credit_balance_exhausted',
    'organization_spend_limit_exceeded', 'project_spend_limit_exceeded',
    'organization_usage_limit_exceeded', 'usage_limit_exceeded'))
_RATE_CODES = frozenset(('rate_limit_exceeded', 'slow_down'))
_AUTH_CODES = frozenset(('invalid_grant', 'invalid_client', 'invalid_token', 'access_denied',
    'subscription_sharing_usage_limit_exceeded', 'subscription_sharing_usage_unavailable'))
_LIMIT_TYPES = frozenset(('insufficient_quota', 'rate_limit_error', 'requests', 'tokens'))


def _limit_error(result, error, secrets, error_codes=()):
    """Keep fixed provider reason identifiers, never error messages or arbitrary codes."""
    try:
        raw = error.read(16385)
        if len(raw) > 16384:
            return
        body = json.loads(raw)
    except (ValueError, RecursionError, OSError, http.client.HTTPException):
        return
    reason = body.get('error') if isinstance(body, dict) else None
    if isinstance(reason,str):
        reason={'code':reason}
    if not isinstance(reason, dict):
        return
    control_code = reason.get('code')
    if (isinstance(control_code, str) and control_code in error_codes
            and not any(secret and secret in control_code for secret in secrets)):
        result['controlErrorCode'] = control_code
    for field, key, allowed in (('code', 'providerErrorCode', _QUOTA_CODES | _RATE_CODES | _AUTH_CODES),
                                ('type', 'providerErrorType', _LIMIT_TYPES)):
        value = reason.get(field)
        if isinstance(value, str) and value in allowed and not any(secret and secret in value for secret in secrets):
            result[key] = value
    code, kind = result.get('providerErrorCode'), result.get('providerErrorType')
    if code in _QUOTA_CODES or code in ('subscription_sharing_usage_limit_exceeded','subscription_sharing_usage_unavailable') or (code is None and kind == 'insufficient_quota'):
        result['category'] = 'quota'
    elif code in _RATE_CODES or (code is None and kind in ('rate_limit_error', 'requests', 'tokens')):
        result['category'] = 'rate_limit'


class _StreamError(ValueError):
    """Fixed structural reason only; no upstream content in diagnostics."""


def _completed_output(terminal, items):
    """Keep final item snapshots when the terminal response omits its output."""
    response = terminal.get('response')
    if terminal['type'] != 'response.completed' or not items or not isinstance(response, dict):
        return
    output = response.get('output', [])
    if not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
        raise _StreamError('sse_output_shape')
    merged = dict(enumerate(output))
    for index, item in items.items():
        # Both snapshots describe the same final item. Missing fields are fine;
        # contradictory snapshots must never dispatch a different tool call.
        existing = merged.get(index, {})
        if any(key in existing and existing[key] != value for key, value in item.items()):
            raise _StreamError('sse_output_conflict')
        merged[index] = {**existing, **item}
    if sorted(merged) != list(range(len(merged))):
        raise _StreamError('sse_output_gap')
    output = [merged[index] for index in range(len(merged))]
    ids = [item['id'] for item in output if isinstance(item.get('id'), str) and item['id']]
    if len(ids) != len(set(ids)):
        raise _StreamError('sse_output_conflict')
    response['output'] = output


def _response_events(raw, *, strict_framing=False):
    """Read SSE records and retain completed output items, never partial deltas."""
    data=[]
    event_type=''
    terminal=None
    items={}
    try:
        lines=re.split(r'\r\n|\r|\n',raw.decode('utf-8-sig'))
    except UnicodeError:
        raise _StreamError('sse_decode') from None
    for line in [*lines, '']:
        if not line:
            if data:
                payload='\n'.join(data)
                data=[]
                if payload=='[DONE]':
                    event_type=''
                    continue
                try:
                    event=json.loads(payload)
                except ValueError:
                    raise _StreamError('sse_json') from None
                if not isinstance(event,dict):
                    raise _StreamError('sse_event_shape')
                if 'type' not in event and event_type:
                    event['type']=event_type
                elif event_type in ('response.completed','response.failed','response.incomplete','error','response.output_item.done') and event.get('type')!=event_type:
                    raise _StreamError('sse_event_type_mismatch')
                if terminal is not None:
                    raise _StreamError('sse_conflicting_terminal')
                if event.get('type') in ('response.completed','response.failed','response.incomplete','error'):
                    terminal=event
                elif event.get('type') == 'response.output_item.done':
                    index, item = event.get('output_index'), event.get('item')
                    if (type(index) is not int or index < 0 or not isinstance(item, dict)
                            or not isinstance(item.get('type'), str)
                            or item.get('status', 'completed') != 'completed'):
                        raise _StreamError('sse_output_shape')
                    if index in items:
                        raise _StreamError('sse_output_conflict')
                    items[index] = item
            event_type=''
            continue
        if line.startswith('data:'):
            data.append(line[5:].removeprefix(' '))
        elif line.startswith('event:'):
            event_type=line[6:].removeprefix(' ')
        elif strict_framing and not line.startswith((':', 'id:', 'retry:')) and line not in ('data', 'event', 'id', 'retry'):
            raise _StreamError('sse_framing')
    if terminal is None:
        raise _StreamError('sse_no_terminal')
    _completed_output(terminal, items)
    return terminal


def json_request(request, *, opener, timeout, limit, network_mode='direct', operation='model',
                 observer=None, allow_empty=False, sse_id=None, sensitive_values=(), responses_stream=False,
                 error_codes=()):
    """One attempt, no redirects/retries. Observer receives only allowlisted facts."""
    parsed = urllib.parse.urlsplit(request.full_url)
    secrets = list(sensitive_values)
    for name, value in request.header_items():
        if name.lower() in ('authorization', 'x-api-key', 'x-goog-api-key', 'proxy-authorization', 'mcp-session-id', 'cookie'):
            secrets.extend((value, value.removeprefix('Bearer ')))
    host = parsed.hostname or ''
    if any(secret and secret in host for secret in secrets):
        host = '[redacted]'
    diagnostic = dict(requestId=uuid.uuid4().hex, attempt=1, operation=operation,
        scheme=parsed.scheme, host=host, port=parsed.port or (443 if parsed.scheme == 'https' else 80),
        networkMode=network_mode, effectiveNetworkMode=effective_mode(request.full_url, network_mode),
        status='running', phase='unknown', category='pending', outcomeUnknown=True, durationMs=0,
        timeoutMs=round(timeout * 1000))
    started = time.monotonic()

    def emit():
        diagnostic['durationMs'] = round((time.monotonic() - started) * 1000, 2)
        if observer:
            observer(deepcopy(diagnostic))

    emit()  # Persist dispatch intent before sending anything.
    failed = None
    response_headers = {}
    try:
        with opener.open(request, timeout=timeout) as response:
            response_headers = getattr(response, 'headers', {})
            diagnostic['httpStatus'] = getattr(response, 'status', 200)
            _headers(diagnostic, response_headers, secrets)
            diagnostic['phase'] = 'read'
            emit()  # Preserve received headers even if the process stops during reading.
            # SSE repeats deltas, completed items and the terminal response. Keep
            # its bounded wire envelope separate from the decoded result limit.
            wire_limit = min(16_000_000, limit * 16) if responses_stream else limit
            raw = response.read(wire_limit + 1)
        diagnostic.update(responseBytes=len(raw), responseBodyKind=_body_kind(raw))
        if len(raw) > wire_limit:
            diagnostic.update(category='response_limit', phase='read', outcomeUnknown=True)
            failed = True
        else:
            try:
                if not raw and allow_empty:
                    value = {}
                elif responses_stream:
                    if diagnostic['responseMediaType'] not in ('text/event-stream', 'missing'):
                        raise _StreamError('sse_content_type')
                    # A missing header must not discard a valid completed stream.
                    # Require SSE framing as well as the terminal event in that case.
                    terminal=_response_events(raw, strict_framing=diagnostic['responseMediaType']=='missing')
                    value=terminal.get('response',{})
                    if not isinstance(value,dict):
                        raise _StreamError('sse_terminal_payload')
                    if terminal['type']!='response.completed':
                        reason=value.get('error') or terminal.get('error') or terminal
                        code=reason.get('code') if isinstance(reason,dict) else None
                        if isinstance(code,str) and code in _AUTH_CODES | _QUOTA_CODES | _RATE_CODES and not any(secret and secret in code for secret in secrets):
                            diagnostic['providerErrorCode']=code
                        diagnostic.update(category='quota' if code in _QUOTA_CODES or code in ('subscription_sharing_usage_limit_exceeded','subscription_sharing_usage_unavailable') else 'rate_limit' if code in _RATE_CODES else 'provider_incomplete',phase='response',outcomeUnknown=terminal['type']=='error')
                        failed=True
                    elif value.get('status')!='completed':
                        raise _StreamError('sse_completed_status')
                elif 'text/event-stream' in response_headers.get('Content-Type', ''):
                    values = [json.loads(line[5:].strip()) for line in raw.decode('utf-8').splitlines()
                              if line.startswith('data:')]
                    value = next(item for item in reversed(values) if isinstance(item, dict) and item.get('id') == sse_id)
                else:
                    value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError()
                if responses_stream and len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > limit:
                    diagnostic.update(category='response_limit', phase='read', outcomeUnknown=True)
                    failed = True
            except (ValueError, UnicodeError, StopIteration) as error:
                diagnostic.update(category='parse', phase='parse', outcomeUnknown=True)
                if isinstance(error,_StreamError):
                    diagnostic['parseReason']=str(error)
                failed = True
    except urllib.error.HTTPError as error:
        status = error.code
        category = ('redirect' if 300 <= status < 400 else 'auth' if status in (401, 403)
                    else 'endpoint_or_model' if status == 404 else 'rate_limit_or_quota' if status == 429
                    else 'server' if status >= 500 else 'http')
        diagnostic.update(httpStatus=status, category=category, phase='response', outcomeUnknown=status >= 500)
        _headers(diagnostic, error.headers or {}, secrets)
        try:
            if status >= 400:
                _limit_error(diagnostic, error, secrets, error_codes)
        finally:
            error.close()
        failed = True
    except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
        category, phase, unknown = _category(error)
        if 'httpStatus' in diagnostic:
            phase, unknown = 'read', True
        diagnostic.update(category=category, phase=phase, outcomeUnknown=unknown,
                          **_tls_details(error))
        failed = True
    if failed:
        diagnostic['status'] = 'failed'
        emit()
        raise OutboundError(deepcopy(diagnostic)) from None
    diagnostic.update(status='completed', phase='response', category='success', outcomeUnknown=False)
    emit()
    return value, response_headers
