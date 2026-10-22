"""Run arbitrary argv and publish bounded check events to a loopback Hub."""
from __future__ import annotations

import argparse
import base64
import hashlib
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import signal
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request
import uuid
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

from hub_core import HubError
from hub_http import Client


def string(limit, **extra):
    return dict(type='string', minLength=1, maxLength=limit, **extra)


CHECK_SCHEMA = dict(type='object', additionalProperties=False,
    required=['runId', 'task', 'status', 'command', 'startedAt'],
    properties=dict(
        runId=string(120, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$'), task=string(150),
        stage=dict(string(150), type=['string', 'null']),
        status=dict(type='string', enum=['running', 'passed', 'failed', 'interrupted', 'unknown']),
        title=string(240), profile=string(240), profileVersion=string(240),
        correction=dict(type='object', additionalProperties=False,
                        required=['reason', 'expectedEvent'],
                        properties=dict(reason=string(1200), expectedEvent=string(240))),
        command=dict(type='array', minItems=1, maxItems=100,
                     items=dict(type='string', maxLength=2000)),
        scope=dict(type='array', maxItems=100, items=string(2000)),
        revision=dict(type='object', additionalProperties=False,
                      properties=dict(head=dict(string(200), type=['string', 'null']),
                                      dirty=dict(type='boolean'),
                                      fingerprint=dict(string(200), type=['string', 'null']))),
        startedAt=dict(string(64), type=['string', 'null']), finishedAt=string(64), exitCode=dict(type=['integer', 'null']),
        durationMs=dict(type=['number', 'null'], minimum=0), summary=dict(type='string', maxLength=1600), log=string(2000),
        evidence=dict(type='array', maxItems=20, items=dict(type='object',
            additionalProperties=False, required=['label', 'path'],
            properties=dict(label=string(240), path=string(2000)))),
        counts=dict(type='object', maxProperties=20,
                    propertyNames=dict(maxLength=40),
                    additionalProperties=dict(type='integer', minimum=0))))


def _validate(value, schema):
    kind = schema['type']
    if isinstance(kind, list):
        if value is None and 'null' in kind:
            return
        kind = next(item for item in kind if item != 'null')
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'boolean': type(value) is bool,
             'integer': type(value) is int,
             'number': type(value) in (int, float) and math.isfinite(value)}
    if not valid[kind]:
        raise ValueError('Invalid check field type')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Invalid check status')
    if kind == 'object':
        props = schema.get('properties', {})
        if set(schema.get('required', [])) - value.keys():
            raise ValueError('Missing check field')
        if schema.get('additionalProperties') is False and value.keys() - props.keys():
            raise ValueError('Unknown check field')
        if len(value) > schema.get('maxProperties', 100):
            raise ValueError('Too many check fields')
        for key in value.keys() & props.keys():
            _validate(value[key], props[key])
        if isinstance(schema.get('additionalProperties'), dict):
            for key, item in value.items():
                if not isinstance(key, str) or len(key) > schema.get('propertyNames', {}).get('maxLength', 16000):
                    raise ValueError('Invalid check count name')
                _validate(item, schema['additionalProperties'])
    if kind in ('string', 'array'):
        if not schema.get('minLength', schema.get('minItems', 0)) <= len(value) <= schema.get('maxLength', schema.get('maxItems', 16000)):
            raise ValueError('Check field exceeds bounds')
        if kind == 'array':
            for item in value:
                _validate(item, schema['items'])
        elif '\x00' in value or (schema.get('minLength') and not value.strip()):
            raise ValueError('Invalid check text')
        elif schema.get('pattern') and not re.fullmatch(schema['pattern'], value):
            raise ValueError('Invalid check identifier')
    if kind in ('number', 'integer') and value < schema.get('minimum', -math.inf):
        raise ValueError('Invalid check duration')


def relative_path(value):
    return (not Path(value).is_absolute() and not PureWindowsPath(value).drive
            and not value.startswith(('\\', '/'))
            and '..' not in value.replace('\\', '/').split('/'))


def validate_check(payload):
    try:
        _validate(payload, CHECK_SCHEMA)
        raw = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode('utf-8')
        if len(raw) > 15000:
            raise ValueError('Check metadata exceeds 15000 bytes; link a log instead')
        paths = payload.get('scope', []) + [item['path'] for item in payload.get('evidence', [])]
        if 'log' in payload:
            paths.append(payload['log'])
        if any(not relative_path(path) for path in paths):
            raise ValueError('Check paths must be project-relative')
        if not payload['command'][0].strip():
            raise ValueError('Check executable is required')
        stamps = {}
        if payload['startedAt'] is None and not (payload.get('correction')
                and payload.get('summary', '').strip() and (payload.get('log') or payload.get('evidence'))):
            raise ValueError('Unknown startedAt requires an explicit correction, evidence and summary')
        for field in ('startedAt', 'finishedAt'):
            if field in payload and payload[field] is not None:
                stamp = datetime.fromisoformat(payload[field].replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    raise ValueError('Check timestamps require a timezone')
                stamps[field] = stamp
        if payload['status'] == 'running':
            if 'correction' in payload:
                raise ValueError('Corrections require a terminal result')
            if any(key in payload for key in ('finishedAt', 'exitCode', 'durationMs', 'counts')):
                raise ValueError('Running checks cannot contain finish fields')
        elif 'finishedAt' not in payload:
            raise ValueError('Finished checks require finishedAt')
        elif 'startedAt' in stamps and stamps['finishedAt'] < stamps['startedAt']:
            raise ValueError('Check finished before it started')
        if payload['status'] == 'passed' and payload.get('exitCode') != 0:
            raise ValueError('Passed checks require exitCode zero')
        if payload['status'] == 'failed' and payload.get('exitCode') in (None, 0):
            documented_correction = (payload.get('exitCode') is None and payload.get('correction')
                                    and (payload.get('log') or payload.get('evidence'))
                                    and payload.get('summary', '').strip())
            if not documented_correction:
                raise ValueError('Failed checks require a nonzero exitCode; corrections with an unknown code require evidence and summary')
        return raw
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise HubError('invalid_check', str(error)) from None


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def warn(message):
    print('hub_check: ' + message, file=sys.stderr)


def persist(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def post(client, project, payload):
    data = validate_check(payload)
    url = client.url.removesuffix('/api/v1/plugin/call') + '/api/v1/checks?' + urlencode({'project': project})
    request = Request(url, data=data, headers={'Content-Type': 'application/json'})
    result = client.request_json(request, recovery=dict(runId=payload['runId'], status=payload['status']))
    if result.get('error'):
        raise HubError(result['error'], result.get('message', 'Hub rejected check'))
    return result


def deliver(client, project, directory):
    """Always replay start before finish; the server deduplicates by runId."""
    if (directory / 'delivered.json').exists():
        return True
    try:
        start = json.loads((directory / 'start.json').read_text(encoding='utf-8'))
        if start['project'] != project:
            return False
        post(client, project, start['payload'])
        finish = directory / 'finish.json'
        if not finish.exists():
            return False
        payload = json.loads(finish.read_text(encoding='utf-8'))
        if ('log' not in payload and not (directory / 'log-skipped.json').exists()
                and (directory / 'output.log').is_file()):
            log = directory / 'output.log'
            if log.stat().st_size > 20 * 1024**2:
                note = 'Full log exceeds the artifact upload limit and is retained in external local check storage.'
                if note not in payload.get('summary', ''):
                    payload['summary'] = (payload.get('summary', '')[:1400] + ' ' + note).strip()
                persist(finish, payload)
                persist(directory / 'log-skipped.json', {'reason': 'size_limit', 'bytes': log.stat().st_size})
            else:
                url = client.url.removesuffix('/api/v1/plugin/call') + '/api/v1/artifacts/upload?' + urlencode({'project': project})
                request = Request(url, data=json.dumps({'name': 'check-' + payload['runId'] + '.log',
                    'content': base64.b64encode(log.read_bytes()).decode('ascii'), 'roles': ['evidence']}).encode(),
                    headers={'Content-Type': 'application/json'})
                uploaded = client.request_json(request)
                reference = uploaded['source']['path']
                if not isinstance(reference, str) or not reference.startswith('hub-artifact/') or not relative_path(reference):
                    raise ValueError('Invalid uploaded log reference')
                payload['log'] = reference
                persist(finish, payload)
        post(client, project, payload)
        persist(directory / 'delivered.json', {'at': now()})
        return True
    except Exception as error:
        detail = '; ' + error.body['message'] if isinstance(error, HubError) else ''
        warn('publication pending for ' + directory.name + detail + '; use explicit flush to retry the saved request')
        return False


def check_directory(cwd, log_dir):
    root = Path(cwd).resolve(strict=True)
    fallback = (Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'ProjectHub/checks'
                if os.name == 'nt' else Path.home() / '.local/share/ProjectHub/checks')
    home = Path(os.environ.get('PROJECT_HUB_CHECK_OUTPUT_HOME', fallback)).expanduser().resolve()
    if home.is_relative_to(root) or root.is_relative_to(home):
        raise ValueError('Check output home must be outside the project root')
    namespace = hashlib.sha256(os.path.normcase(str(root)).encode()).hexdigest()[:16]
    base = home / namespace / 'runs'
    if log_dir and (not relative_path(log_dir) or log_dir.startswith('.local/')):
        raise ValueError('log-dir must be a relative folder under external check storage')
    directory = (base / (log_dir or '')).resolve()
    if not directory.is_relative_to(base):
        raise ValueError('log-dir must remain under external check storage')
    return root, directory


def stop_child(child):
    if os.name == 'nt':
        # Native tree cleanup; argv avoids cmd.exe interpretation of user data.
        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=5, check=False)
    else:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        child.kill()
        child.wait()


def execute(args):
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    root, base = check_directory(args.cwd, args.log_dir)
    client = Client(args.url)
    run_id = uuid.uuid4().hex
    directory = base / run_id
    payload = dict(runId=run_id, task=args.task, status='running', command=command,
                   scope=args.scope, startedAt=now())
    for field, value in (('title', args.title), ('stage', args.stage), ('profile', args.profile),
                         ('profileVersion', args.profile_version)):
        if value is not None:
            payload[field] = value
    if args.revision:
        payload['revision'] = json.loads(args.revision)
    log = directory / 'output.log'
    # Reserve space for terminal fields so replay never needs to truncate argv.
    if len(validate_check(payload)) > 13500:
        raise ValueError('Launch metadata exceeds 13500 bytes; reserve space for the finish')
    stream = None
    durable = False
    publication = 'unavailable'
    try:
        directory.mkdir(parents=True)
        stream = log.open('xb')
        persist(directory / 'start.json', {'project': args.project, 'payload': payload})
        durable = True
    except OSError:
        warn('local recording unavailable; command will run, publication gap remains')
    if durable:
        deliver(client, args.project, directory)
    started = time.monotonic()
    child = None
    exit_code = None
    status = 'unknown'
    summary = None
    previous = {}
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    try:
        signals = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, 'SIGBREAK'):
            signals.append(signal.SIGBREAK)
        for sig in signals:
            previous[sig] = signal.signal(sig, interrupted)
        child = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
            shell=False, start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        exit_code = child.wait()
        status = 'passed' if exit_code == 0 else 'failed'
    except KeyboardInterrupt:
        status = 'interrupted'
        summary = 'Wrapper interrupted; child cleanup requested'
    except OSError:
        status = 'unknown'
        summary = 'Command could not be launched'
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, signal.SIG_IGN)
        try:
            if child is not None and (status == 'interrupted' or child.poll() is None):
                try:
                    stop_child(child)
                except (OSError, subprocess.SubprocessError):
                    child.kill()
                    child.wait()
                exit_code = child.returncode
            if stream:
                stream.close()
            finish = dict(payload, status=status, finishedAt=now(),
                          durationMs=round((time.monotonic() - started) * 1000))
            if exit_code is not None:
                finish['exitCode'] = exit_code
            if summary:
                finish['summary'] = summary
            if durable:
                try:
                    persist(directory / 'finish.json', finish)
                    publication = 'delivered' if deliver(client, args.project, directory) else 'pending'
                except OSError:
                    warn('finish could not be saved; run remains unknown, not passed')
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    published_log = None
    if durable and (directory / 'finish.json').exists():
        published_log = json.loads((directory / 'finish.json').read_text(encoding='utf-8')).get('log')
    print(json.dumps({'runId': run_id, 'status': status, 'publication': publication,
                      'log': published_log or str(log), 'localLog': str(log)}))
    return 130 if status == 'interrupted' else (exit_code if exit_code is not None else 127)


def flush(args):
    _, base = check_directory(args.cwd, args.log_dir)
    client = Client(args.url)
    pending = 0
    found = False
    for start in sorted(base.glob('*/start.json')):
        directory = start.parent
        if args.abandon_run == directory.name:
            found = True
        if (directory / 'delivered.json').exists():
            continue
        if args.abandon_run == directory.name and not (directory / 'finish.json').exists():
            saved = json.loads(start.read_text(encoding='utf-8'))
            if saved['project'] != args.project:
                raise ValueError('Abandoned run belongs to another project')
            finish = dict(saved['payload'], status='unknown', finishedAt=now(),
                          summary='Explicitly marked abandoned; child exit was not observed')
            persist(directory / 'finish.json', finish)
        if not deliver(client, args.project, directory):
            pending += 1
    if args.abandon_run and not found:
        raise ValueError('No recorded run matches abandon-run')
    print(json.dumps({'pending': pending}))
    return 1 if pending else 0


def main(argv=None, *, default_url=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('exec', 'flush'):
        part = sub.add_parser(name)
        part.add_argument('--url', default=default_url, required=default_url is None)
        part.add_argument('--project', required=True)
        part.add_argument('--cwd', required=True)
        part.add_argument('--log-dir')
        if name == 'exec':
            part.add_argument('--task', required=True)
            part.add_argument('--title', help='Human-readable purpose of this check run')
            part.add_argument('--stage')
            part.add_argument('--profile')
            part.add_argument('--profile-version')
            part.add_argument('--scope', action='append', default=[])
            part.add_argument('--revision', help='Opaque JSON with head, dirty, optional fingerprint')
            part.add_argument('command', nargs=argparse.REMAINDER)
        else:
            part.add_argument('--abandon-run', help='Explicitly mark a known stopped run unknown')
    args = parser.parse_args(argv)
    try:
        if not 0 < len(args.project) <= 240:
            raise ValueError('project must contain 1-240 characters')
        return execute(args) if args.operation == 'exec' else flush(args)
    except (ValueError, HubError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
