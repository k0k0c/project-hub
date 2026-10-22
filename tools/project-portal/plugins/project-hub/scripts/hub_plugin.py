"""Codex hook and MCP entry point. JSON-lines stdio; standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

from hub_core import Hub, HubError, compact, home, workspace_root
from hub_check import CHECK_SCHEMA, validate_check


def persist(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w', encoding='utf-8', newline='\n') as f:
            f.write(compact(data))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def flush(hub, limit=20):
    delivered = 0
    pending = hub.home / 'outbox'
    if not pending.exists():
        return dict(delivered=0, pending=0)
    paths = sorted(pending.glob('*.json'))
    for path in paths[:limit]:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            hub.lifecycle(data['event'], data['id'])
            path.unlink(missing_ok=True)
            delivered += 1
        except FileNotFoundError:
            continue  # Another process acknowledged the same idempotent event.
        except (OSError, sqlite3.Error):
            break
        except (ValueError, KeyError):
            # Preserve malformed/rejected records for inspection; don't silently drop them.
            break
    return dict(delivered=delivered, pending=len(list(pending.glob('*.json'))))


def migration_resource(root):
    canonical = os.path.normcase(str(Path(root).resolve()))
    return 'resource:migration-root-' + hashlib.sha256(canonical.encode()).hexdigest()[:24]


def migration_roots(hub, session, origin):
    """Explicit local, session-scoped grants; not inferred from writable OS roots."""
    path = hub.home / 'migration-roots.json'
    if not path.exists():
        return []
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
        if config['schemaVersion'] != 1 or not isinstance(config['grants'], list):
            raise ValueError('Unsupported grants')
        roots = []
        for grant in config['grants']:
            if grant['session'] != session:
                continue
            source, target = Path(grant['origin']), Path(grant['root'])
            if not source.is_absolute() or not target.is_absolute():
                raise ValueError('Absolute paths required')
            if source.resolve() == Path(origin).resolve():
                if target.resolve() == Path(target.anchor) or not target.is_dir():
                    raise ValueError('Grant must name an existing directory, not a drive')
                roots.append(target.resolve())
        return roots
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HubError('invalid_migration_grants', 'Cannot validate scoped migration grants') from error


def changed_paths(payload, cwd, root=None, external_roots=(), project_roots=()):
    """Only claim coverage we can prove: structured apply_patch/Edit/Write paths."""
    name = payload.get('tool_name', '')
    args = payload.get('tool_input', {})
    if name == 'apply_patch' and isinstance(args, str):
        args = {'patch': args}
    if not isinstance(args, dict):
        return None
    if name in ('apply_patch', 'Edit', 'Write'):
        paths = [args[k] for k in ('file_path', 'path') if isinstance(args.get(k), str)]
        command = args.get('command', args.get('patch', ''))
        paths += re.findall(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$', command, re.M)
        result = []
        for p in paths:
            path = Path(p)
            absolute = (path if path.is_absolute() else Path(cwd) / path).resolve()
            if project_roots:
                matched = next(((Path(r), prefix) for r, prefix in project_roots
                                if absolute.is_relative_to(Path(r))), None)
                if matched:
                    relative = absolute.relative_to(matched[0]).as_posix()
                    result.append(matched[1] + relative)
                    continue
                approved = next((r for r in external_roots if absolute.is_relative_to(r)), None)
                if approved is None:
                    raise HubError('outside_workspace', 'Patch points outside the project folders')
                result.append(migration_resource(approved))
                continue
            try:
                p = absolute.relative_to(Path(root or cwd).resolve()).as_posix()
            except ValueError:
                approved = next((r for r in external_roots if absolute.is_relative_to(r)), None)
                if approved is None:
                    raise HubError('outside_workspace', 'Patch points outside this workspace')
                p = migration_resource(approved)
            result.append(p)
        return result
    return None


def hook(hub, raw, remind=True):
    # Tool execution never depends on Hub identity, storage, claims or availability.
    if raw.get('hook_event_name') in ('PreToolUse', 'PostToolUse'):
        try:
            hub.observe_edit(raw)
        except Exception:
            # Diagnostics are optional, including unavailable/malformed metadata.
            pass
        return {}
    from hub_core import hook_actor
    raw=hook_actor(raw)
    event = {k: raw[k] for k in ('session_id', 'agent_id', 'origin_session_id', 'cwd', 'hook_event_name', 'turn_id', 'source', 'tool_name') if k in raw}
    if not all(k in event for k in ('session_id', 'cwd', 'hook_event_name')):
        return dict(systemMessage='Project Hub: missing hook identity; tracking unavailable')
    project = hub.locate(event['cwd'])
    if not project:
        return {}  # The plugin never enrolls unrelated projects.
    kind = event['hook_event_name']
    event_id = uuid.uuid4().hex
    record = dict(id=event_id, event=event)
    pending = hub.home / 'outbox' / (str(time.time_ns()) + '-' + event_id + '.json')
    persist(pending, record)
    delivery = flush(hub)
    if delivery['pending']:
        return dict(systemMessage='Project Hub: tracking delayed. Continue the user task; Hub is optional.')
    return hook_reminder(event) if remind else dict(observed=True)


def hook_reminder(event):
    """Static bundled workflow reminder, rendered locally by the plugin hook."""
    kind=event.get('hook_event_name')
    if kind in ('SessionStart', 'UserPromptSubmit') and event.get('session_id'):
        text = ('Project Hub never blocks work. Apply the packaged workflow and native project-hub-user skill if available. '
                'Bind your own identity; reuse the best matching task and visible stage. '
                'Send hub_begin(stage) before substantive work; task creation is not work start. '
                'Read projectSettings before writes/completion, publish verified results and evidence, then close accepted tasks. '
                'Stop/SessionEnd do not complete work. Parallel notices are advisory, not permission to message other chats. '
                'Use project checks appropriate to changed scope. Hub unavailable: continue and record the gap. '
                'Originating session: ' + event['session_id'])
        return dict(hookSpecificOutput=dict(hookEventName=kind, additionalContext=text))
    return {}


from project_settings import COLUMNS, SORTS


TOOLS = [
    dict(name='hub_notice', description='Read advisory facts about relevant declared parallel work for your own bound session. Uses an independent durable cursor: after=0 replays; cursor acknowledges only this returned page. seconds=0 reads immediately; up to45 waits without model polling. Same task, declared dependencies or writer resource overlap; freshness is observation, never proof of running or permission to message. No user instruction text is delivered. Follow queueMore for further pages; workRef resolves full details with hub_context(work).',
         inputSchema=dict(type='object', properties=dict(after=dict(type='integer', minimum=0), seconds=dict(type='integer', minimum=0, maximum=45)), required=['after'], additionalProperties=False)),
    dict(name='hub_knowledge', description='Project knowledge for documentation and shallow architecture. context returns policy/capabilities and knowledge revision. search/read/history retrieve bounded items. source-tree lists registered scanned files; source-read reads a bounded text page by file ID and verifies its stored hash against current source. Changed or unavailable source requires a fresh scan. subsystem-plan previews a create/update/remove changeset for the exact policy revision, retaining stable subsystem IDs and history. changeset atomically applies put/delete items with expected knowledge revision, unique key, reason and task/stage; validate_only previews; revisions differ from hub_plan. scan queues a local non-AI job; job reads its result. import-preview snapshots Markdown/text/HTML and local assets and returns format-aware candidate summaries/readArgs. import-read pages source/markdown/html/diff using identifier,index,field,offset,limit (max12000 characters). import-apply accepts reviewed candidates with optional metadata keyed by candidate ID for topic/status/date/version classification. HTML and Markdown share audience/section; HTML defaults to an isolated full-width viewer with a separate-page link. External code/network and host bridges are unsupported. export validates and returns a ZIP download reference. impact assesses structure/contracts/behavior/userWorkflow; cosmetic/internal edits need no map rewrite. restore creates a new revision. Keep long articles in documentation and short class/component/relation purposes in architecture; no method catalog. Preserve provenance/authored meaning.',
         inputSchema=dict(type='object',properties=dict(action=dict(type='string',enum=['context','search','source-tree','source-read','subsystem-plan','read','history','changeset','scan','job','import-preview','import-read','import-apply','impact','restore','export','research-capabilities','research-object','research','research-result','research-cancel','research-history','research-save','research-providers']),args=dict(type='object')),required=['action'],additionalProperties=False)),
    dict(name='hub_image', description='Attach an important image to an existing or newly created task, optionally to a stage, atomically. Use a project-relative file path (or an existing hub-source reference) and the current hub_plan revision. Preserves existing sources and avoids duplicate paths. Original files are retained; task sources show images from every stage. Copy external generated assets into the project artifact directory first.',
         inputSchema=dict(type='object', properties=dict(task=dict(type='string'), path=dict(type='string'), expected=dict(type=['integer','string']), stage=dict(type='string'), label=dict(type='string', maxLength=240)), required=['task','path','expected'], additionalProperties=False)),
    dict(name='hub_artifact', description='Attach any-format immutable artifact to a task or stage. A project-relative file is snapshotted into the existing Hub CAS outside checkout; its original remains a validation input. Existing hub-artifact references from uploads and registered hub-source references can be attached directly. Read the current hub_plan revision. roles describe use and never exclude inputs from tests. previous explicitly continues a registered version with the same stable artifact ID. Binary preview is optional; original bytes remain downloadable.',
         inputSchema=dict(type='object', properties=dict(task=dict(type='string'), path=dict(type='string'), expected=dict(type=['integer','string']), stage=dict(type='string'), label=dict(type='string', maxLength=240), roles=dict(type='array', uniqueItems=True, items=dict(type='string', enum=['evidence','deliverable','product-input','test-fixture'])), previous=dict(type='string')), required=['task','path','expected'], additionalProperties=False)),
    dict(name='hub_check', description='Publish an observed check run for the bound project. Send running first, then a factual finish with the same runId and immutable launch metadata. To explicitly correct a running or terminal record, resend full metadata and factual corrected fields with correction={reason, expectedEvent}, using the current projected run.id. Only explicit correction may repair startedAt (null if unknown), with summary and evidence/log; other launch metadata remain immutable. Corrections append audit history; stale competing corrections fail and identical retries are idempotent. Unknown or abandoned execution is never passed. Profiles and command selection belong to the project; no credentials or environment capture.', inputSchema=CHECK_SCHEMA),
    dict(name='hub_checkpoint', description='Retry a visible task/stage Git checkpoint obligation. Read current project revision and pass expected; stage is optional. Without commits, ordinary retry is unchanged. For explicit existing-commit reconciliation, supply commits and reason together: 1-20 full 40/64-hex SHAs oldest to newest and a nonblank reason up to 1200 characters. Only an error checkpoint on a completed target can be reconciled. New immutable boundaries verify original/committed bytes, modes, ancestry and the frozen completed result with caller attribution; shared commits can cover distinct tasks. Legacy boundaries retain same-task trailer/history checks and are labelled legacy. Reconciliation performs no Git writes; original snapshots and errors remain. Identical commits/reason retries are idempotent; conflicting completed adoption is rejected. Preserve safe scope, dirty files and pre-existing index; never blindly expand scope. Inspect gitCheckpoint, verification and gitCommit before claiming coverage. Push requires separate authorization.',
         inputSchema=dict(type='object', properties=dict(task=dict(type='string'), stage=dict(type='string'),
             commits=dict(type='array', minItems=1, maxItems=20, uniqueItems=True,
                 items=dict(type='string', pattern=r'^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$'),
                 description='Existing full commit SHAs, oldest to newest; unique ignoring case; requires reason. The server normalizes SHAs to lowercase.'),
             reason=dict(type='string', minLength=1, maxLength=1200, pattern=r'\S',
                 description='Nonblank explicit reconciliation reason; requires commits.'),
             expected=dict(type=['integer','string'], description='Current project revision, not settings revision.')),
             oneOf=[dict(required=['commits','reason']),
                    {'not': {'anyOf': [dict(required=['commits']), dict(required=['reason'])]}}],
             required=['task','expected'], additionalProperties=False)),
    dict(name='hub_git_batch', description='Review a shared Git candidate and its many-to-many checkpoint coverage. Preview selects 1-20 completed task/stage obligations, current project revision and an attribution reason. Optional commit reviews one existing non-merge commit; omit it to prepare the current integration HEAD candidate. Preview performs no Git writes and retains immutable review evidence in the existing CAS. Inspect details (steps, hunks, changes, changesets, files) with the returned batchBlob. Legacy obligations return explicit unproven issues without inferred ownership. Reconcile an existing commit only after review, with the exact preview batchId in confirmed and the same reason. It verifies original boundaries, complete chains/disjoint UTF-8 text hunks, binary bytes, modes, ancestry and the entire candidate; ambiguous conflicts refuse. Each target keeps its original checkpoint ID/history. Publication retries never repeat Git. This tool does not commit or push; use native Git permissions and ordinary hooks for a new commit.',
         inputSchema=dict(type='object', additionalProperties=False, properties=dict(
             action=dict(type='string', enum=['preview','reconcile','details']),
             targets=dict(type='array', minItems=1, maxItems=20, uniqueItems=True, items=dict(type='object', additionalProperties=False,
                 properties=dict(task=dict(type='string', minLength=1, maxLength=256), stage=dict(type='string', minLength=1, maxLength=256)), required=['task'])),
             expected=dict(type=['integer','string']), reason=dict(type='string', minLength=1, maxLength=1200),
             commit=dict(type='string', pattern=r'^(?:[a-f0-9]{40}|[a-f0-9]{64})$'),
             confirmed=dict(type='string', pattern=r'^[a-f0-9]{64}$'), blob=dict(type='string', pattern=r'^[a-f0-9]{64}$'),
             section=dict(type='string', enum=['steps','hunks','changes','changesets','files']),
             offset=dict(type='integer', minimum=0), limit=dict(type='integer', minimum=1, maximum=100)),
             required=['action'], oneOf=[
                 dict(properties=dict(action=dict(const='preview')), required=['targets','expected','reason'],
                      **{'not':dict(anyOf=[dict(required=[key]) for key in ('confirmed','blob','section','offset','limit')])}),
                 dict(properties=dict(action=dict(const='reconcile')), required=['targets','expected','reason','commit','confirmed'],
                      **{'not':dict(anyOf=[dict(required=[key]) for key in ('blob','section','offset','limit')])}),
                 dict(properties=dict(action=dict(const='details')), required=['blob'],
                      **{'not':dict(anyOf=[dict(required=[key]) for key in ('targets','expected','reason','commit','confirmed')])})])),
    dict(name='hub_settings', description='Canonical settings read/update for the bound project. No arguments reads settings (git, tasks, viewer), revision, configured and history. Read authoritative projectSettings from hub_context or this tool before write work and completion. Updates require explicit user intent, patch sections OR reset=git/tasks/viewer, and expected settings revision (not task revision). Settings grant no credentials or approval powers.',
         inputSchema=dict(type='object', properties=dict(
             patch=dict(type='object', additionalProperties=False, properties=dict(
                 git=dict(type='object', additionalProperties=False, properties=dict(
                     autoCommit=dict(type='boolean'), commitOn=dict(type='string', enum=['stage-and-task','stage','task']))),
                 tasks=dict(type='object', additionalProperties=False, properties=dict(
                     columns=dict(type='array', minItems=1, uniqueItems=True, items=dict(type='string', enum=sorted(COLUMNS)), contains=dict(const='title')),
                     sort=dict(type='string', enum=sorted(SORTS)),
                     overviewSort=dict(type='string', enum=sorted(SORTS)), showCompleted=dict(type='boolean'),
                     showEpicsOnOverview=dict(type='boolean'), showUpcomingOnOverview=dict(type='boolean'))),
                 viewer=dict(type='object', additionalProperties=False, properties=dict(
                     wrapLines=dict(type='boolean'), showSourceDetails=dict(type='boolean'))))),
             expected=dict(type='string', minLength=1, maxLength=128, description='Exact settings revision returned by hub_settings or projectSettings.'),
             reset=dict(type='string', enum=['git','tasks','viewer'])), additionalProperties=False,
             oneOf=[dict(maxProperties=0), dict(required=['patch','expected'], **{'not':dict(required=['reset'])}),
                    dict(required=['reset','expected'], **{'not':dict(required=['patch'])})])),
    dict(name='hub_memory', description='Search project history before substantial investigation. Read source:path for the current working file, source-archive:path for an explicit historical snapshot. Use returned versionRef with offset for consistent pages. Missing current files never silently fall back to archives. Historical records are not current-code guarantees.', inputSchema=dict(type='object', properties=dict(query=dict(type='string'),task=dict(type='string'),ref=dict(type='string'),offset=dict(type='integer'),limit=dict(type='integer')),additionalProperties=False)),
    dict(name='hub_migration_preview', description='Read-only preview of legacy task taxonomy before classification. Never writes journal events.', inputSchema=dict(type='object', properties=dict(), additionalProperties=False)),
    dict(name='hub_plan', description='Read task plan/revision. Every task needs a stage. Supply stage, title, remaining, status and expected from the read: a missing stage ID is created; an existing ID is updated. expected checks concurrency, never selects the operation. Identical retries are idempotent. Creation without expected is supported for legacy callers. Decisions require a nonempty title and decision; pass the current expected revision. Decisions do not create stages. Update estimate/primary separately with expected; continuation of substantial work triggers a coarse estimate before or just after hub_begin.', inputSchema=dict(type='object',properties=dict(task=dict(type='string'),stage=dict(type='string'),title=dict(type='string'),remaining=dict(type='array',items=dict(type='string')),status=dict(type='string'),decision=dict(type='string',description='Decision detail; also supply a nonempty title. Records history, not a stage.'),expected=dict(type=['integer','string']),primary=dict(type='boolean'),estimate=dict(type='object',properties=dict(percentLow=dict(type='number',minimum=0,maximum=100),percentHigh=dict(type='number',minimum=0,maximum=100),hoursLow=dict(type='number',minimum=0),hoursHigh=dict(type='number',minimum=0),confidence=dict(type='string',maxLength=160),note=dict(type='string',maxLength=800)),required=['percentLow','percentHigh','confidence','note'],additionalProperties=False)),required=['task'],additionalProperties=False)),
    dict(name='hub_context', description='Read compact context/team or deltas. FIRST call: bind your own host CODEX_THREAD_ID (subagents must not use inherited parent IDs even from that variable, or CODEX_SESSION_ID), or your own startup ID. Verify session/project. Binding is per MCP instance. Later omit session; on identity_missing rebind the same verified own ID and retry once. If recovery fails, continue work and disclose the recording gap. Never guess an ID.',
         inputSchema=dict(type='object', properties=dict(session=dict(type='string'), after=dict(type='integer', minimum=0),
                          work=dict(type='string'), query=dict(type='string', maxLength=200), offset=dict(type='integer', minimum=0),
                          limit=dict(type='integer', minimum=1, maximum=30)), additionalProperties=False)),
    dict(name='hub_task', description='Create a task only when none matches; returns its handle. Scope/acceptance do not create a plan: next read hub_plan and create at least one stage. Identical retries are idempotent. Set type, priority, parentTask and weight when known.',
         inputSchema=dict(type='object', properties=dict(title=dict(type='string', maxLength=240),
                          scope=dict(type='array', items=dict(type='string'), minItems=1, maxItems=8),
                          acceptance=dict(type='array', items=dict(type='string'), minItems=1, maxItems=8),
                          type=dict(type='string', enum=['epic','task','bug']), priority=dict(type='string', enum=['blocker','critical','major','minor','trivial']),
                          parentTask=dict(type=['string','null']), weight=dict(type=['number','null'], minimum=0)), required=['title', 'scope', 'acceptance'], additionalProperties=False)),
    dict(name='hub_task_update', description='Update task metadata. Read hub_plan(task) and pass its exact revision as expected. Attach documents with patch.sources: merge existing sources with {label,path} using project-relative paths. Preserve existing sources/provenance. Report evidence alone does not populate task sources.',
         inputSchema=dict(type='object', properties=dict(task=dict(type='string'), patch=dict(type='object'), expected=dict(type=['integer','string'])), required=['task','patch','expected'], additionalProperties=False)),
    dict(name='hub_task_link', description='Add a non-hierarchical relation between two tasks.',
         inputSchema=dict(type='object', properties=dict(task=dict(type='string'), target=dict(type='string'), project=dict(type=['string','null']), type=dict(type='string', enum=['blocks','blocked-by','related','duplicates','duplicated-by']), expected=dict(type=['integer','string'])), required=['task','target','type','expected'], additionalProperties=False)),
    dict(name='hub_task_close', description='Close a task manually or automatically. Automatic close requires all descendants to be complete; manual close returns a warning when they are not.',
         inputSchema=dict(type='object', properties=dict(task=dict(type='string'), expected=dict(type=['integer','string']), mode=dict(type='string', enum=['auto','manual']), reason=dict(type='string')), required=['task','expected'], additionalProperties=False)),
    dict(name='hub_begin', description='Start task work linked to an existing plan stage, including reviews and small fixes. Pass stage so reports publish visible results. resources requires 1-30 files/directories or resource:name entries. Use read for review, write for implementation. Overlapping claims return an advisory resource_overlap warning with owners and freshness; coordinate a confirmed simultaneous edit, but the work and its Git boundary are recorded.',
         inputSchema=dict(type='object', properties=dict(task=dict(type='string'), title=dict(type='string', maxLength=240),
                          resources=dict(type='array', items=dict(type='string'), minItems=1, maxItems=30),
                          stage=dict(type='string'), stages=dict(type='array', maxItems=30, uniqueItems=True, items=dict(type='string')),
                          phase=dict(type='string', enum=['planning','research','implementation','review','testing']),
                          mode=dict(type='string', enum=['read', 'write'])), required=['task', 'title', 'resources'], additionalProperties=False)),
    dict(name='hub_report', description='Save result/checkpoint with evidence paths using the work revision. Stage-linked work publishes visible results; unlinked legacy work only saves work history. status=done releases work; stage_status=done completes the verified stage when no other work in that stage remains open. Otherwise the work result is saved, stage completion is deferred, and stageCompletionDeferred lists open work. Verify planSync and read back the stage. Also attach created documents to task.sources via hub_task_update before closing.',
         inputSchema=dict(type='object', properties=dict(work=dict(type='string'), revision=dict(type='integer'), result=dict(type='string', maxLength=1600),
                          checkpoint=dict(type='string', maxLength=1200), status=dict(type='string', enum=['active', 'waiting', 'done', 'cancelled']),
                          stage_status=dict(type='string',enum=['active','done','blocked','cancelled']), stage=dict(type='string'),
                          phase=dict(type='string',enum=['planning','research','implementation','review','testing']),
                          waiting_kind=dict(type='string',enum=['external_dependency','user_confirmation']),
                          evidence=dict(type='array', items=dict(type='string'), maxItems=12)), required=['work', 'revision', 'result'], additionalProperties=False)),
    dict(name='hub_review', description='Read bounded project/task/stage summaries or every page of your own immutable action scope. A verified action-owning chat with active planning/research/review work and read claims can publish evidenced proposals. Only an explicit estimate intent may publish estimate metadata. Task status/scope proposals require later explicit user application in the Hub dialog; this tool cannot apply them. Estimates describe sequential active agent time excluding waits/queues/pauses, with range, confidence, age and unknown coverage.',
         inputSchema=dict(type='object', properties=dict(action=dict(type='string', enum=['summary','propose','estimate']),
             target=dict(type='string', enum=['project','task','stage']), task=dict(type='string'), stage=dict(type='string'),
             offset=dict(type='integer', minimum=0), scopeRef=dict(type='string'), actionId=dict(type='string', maxLength=128),
             work=dict(type='string'), expected=dict(type=['integer','string']),
             proposals=dict(type='array', minItems=1, maxItems=20, items=dict(type='object')),
             estimates=dict(type='array', minItems=1, maxItems=20, items=dict(type='object'))),
             required=['action'], additionalProperties=False)),
    dict(name='hub_wait', description='Wait up to 20 seconds for project changes without repeated model polling. Returns a bounded delta.',
         inputSchema=dict(type='object', properties=dict(after=dict(type='integer', minimum=0), seconds=dict(type='integer', minimum=0, maximum=20)), required=['after'], additionalProperties=False)),
]


# Legacy journals use integer revisions; project views use opaque revisions.
next(t for t in TOOLS if t['name']=='hub_plan')['inputSchema']['properties']['expected']={'type':['integer','string']}
next(t for t in TOOLS if t['name']=='hub_plan')['inputSchema']['properties']['blocker'] = dict(
    type=['object','null'], properties=dict(kind=dict(type='string', enum=['technical','user_input','administrative']),
        reason=dict(type='string', minLength=1, maxLength=1200),
        action=dict(type='string', minLength=1, maxLength=1200)),
    required=['kind','reason','action'], additionalProperties=False)
for tool in TOOLS:
    if tool['name'] == 'hub_context':
        tool['description'] += ' Returns authoritative projectSettings policy and settings revision; MUST read it or hub_settings before write work. Unavailable settings mean unknown policy, not autoCommit=false.'
    elif tool['name'] in ('hub_plan', 'hub_report', 'hub_task_close'):
        tool['description'] += ' Server enforces project Git policy at completion through all routes; prefer hub_report stage_status=done for stage completion. Inspect Git outcome and attach checkpoint SHA; no_changes differs from missing safe scope, pending or error. Push needs separate authorization.'

class Mcp:
    def __init__(self, hub, cwd=None, session=None, client=None):
        self.hub = hub
        self.client = client
        self.cwd = cwd or os.getcwd()
        self.session = session or os.environ.get('CODEX_THREAD_ID') or os.environ.get('CODEX_SESSION_ID')

    def call(self, name, args):
        if not isinstance(args, dict):
            raise HubError('invalid_arguments', 'Arguments must be an object')
        tool = next((t for t in TOOLS if t['name'] == name), None)
        if not tool:
            raise HubError('unknown_tool', 'Unknown Project Hub tool')
        schema = tool['inputSchema']
        if set(args) - set(schema['properties']) or set(schema.get('required', [])) - set(args):
            raise HubError('invalid_arguments', 'Missing or unknown argument')
        if name == 'hub_check':
            validate_check(args)
        if name == 'hub_review':
            action = args['action']
            required = {'summary': {'action'}, 'propose': {'action','actionId','work','expected','proposals'},
                        'estimate': {'action','actionId','work','expected','estimates'}}.get(action)
            allowed = (required | ({'scopeRef','actionId','offset'} if args.get('scopeRef') else
                       {'target','task','stage','offset','expected'})) if action == 'summary' else required
            if action == 'summary' and args.get('scopeRef') and not args.get('actionId'):
                raise HubError('invalid_arguments', 'A captured scope requires its actionId')
            if required is None or required - set(args) or set(args) - allowed:
                raise HubError('invalid_arguments', 'Select an exact summary, propose or estimate request')
        if name == 'hub_git_batch':
            action = args.get('action')
            required = {'details': {'action', 'blob'}, 'preview': {'action', 'targets', 'expected', 'reason'},
                        'reconcile': {'action', 'targets', 'expected', 'reason', 'commit', 'confirmed'}}.get(action)
            allowed = required | ({'section', 'offset', 'limit'} if action == 'details' else {'commit'}) if required else set()
            if required is None or set(args) - allowed or required - set(args):
                raise HubError('invalid_arguments', 'Select preview, reconcile or details with its exact fields')
        if name == 'hub_notice' and (isinstance(args.get('seconds',0),bool) or
                not isinstance(args.get('seconds',0),int) or not 0<=args.get('seconds',0)<=45):
            raise HubError('invalid_arguments','seconds must be an integer from0 to45')
        if name == 'hub_checkpoint' and ('commits' in args or 'reason' in args):
            commits, reason = args.get('commits'), args.get('reason')
            if (not isinstance(commits, list) or not 1 <= len(commits) <= 20
                    or any(not isinstance(sha, str) or not re.fullmatch(
                        r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', sha) for sha in commits)
                    or not isinstance(reason, str) or not reason.strip() or len(reason) > 1200):
                raise HubError('invalid_arguments', 'Reconciliation requires 1-20 full 40/64-hex commit SHAs and a nonblank reason up to 1200 characters')
            if len({sha.lower() for sha in commits}) != len(commits):
                raise HubError('invalid_arguments', 'Reconciliation commit SHAs must be unique ignoring case')
        if name == 'hub_settings' and args:
            if ('patch' in args) == ('reset' in args) or 'expected' not in args:
                raise HubError('invalid_arguments', 'Settings updates require patch OR reset and expected settings revision')
            if not isinstance(args['expected'], str) or not 0 < len(args['expected']) <= 128:
                raise HubError('invalid_arguments', 'expected must be the nonempty settings revision string')
            if 'patch' in args and not isinstance(args['patch'], dict):
                raise HubError('invalid_arguments', 'patch must be a settings object')
            if 'reset' in args and args['reset'] not in ('git', 'tasks', 'viewer'):
                raise HubError('invalid_arguments', 'reset must be git, tasks, or viewer')
        if name == 'hub_context' and args.get('session'):
            if self.session and args['session'] != self.session:
                raise HubError('session_mismatch', 'This MCP connection is already bound to another session')
            self.session = args['session']
        if not self.session:
            raise HubError('identity_missing', 'Bind hub_context with your verified own session, check session/project, and retry once. Never use an inherited parent ID. If unavailable, continue authorized work and report the recording gap.')
        if self.client is not None:
            return self.client.call(self.cwd,self.session,name,args)
        if not self.hub.locate(self.cwd):
            raise HubError('project_unregistered', 'This workspace is not registered with Project Hub')
        self.hub.ensure_session(self.session, self.cwd)
        if hasattr(self.hub, 'authorize_tool'):
            self.hub.authorize_tool(self.session, name, args)
        if name == 'hub_check':
            return self.hub.check(self.session, **args)
        if name == 'hub_review':
            if not hasattr(self.hub, 'review'):
                raise HubError('server_required', 'Review requires the connected Hub server')
            return self.hub.review(self.session, **args)
        if name == 'hub_knowledge':
            if not hasattr(self.hub, 'knowledge'):
                raise HubError('server_required', 'Knowledge tools require the connected Project Hub server')
            return self.hub.knowledge(self.session, **args)
        if name == 'hub_settings':
            return self.hub.settings(self.session, **args)
        if name == 'hub_notice':
            from hub_notices import wait
            return wait(self.hub, self.session, args['after'], args.get('seconds', 0))
        if name == 'hub_checkpoint':
            reconcile = {key: args[key] for key in ('commits', 'reason') if key in args}
            return self.hub.checkpoint(self.session, args['task'], args['expected'],
                                       stage=args.get('stage'), **reconcile)
        if name == 'hub_git_batch':
            if not hasattr(self.hub, 'git_batch'):
                raise HubError('server_required', 'Git batch review requires the connected server')
            return self.hub.git_batch(self.session, **args)
        if name == 'hub_context':
            with self.hub.transaction() as c:
                s = self.hub.session(c, self.session)
                if not c.execute("SELECT 1 FROM events WHERE session=? AND project=? AND kind='McpBind' LIMIT 1",
                                 (self.session, s['project'])).fetchone():
                    self.hub.emit(c, s['project'], self.session, 'McpBind', {})
        deferred_read = name == 'hub_plan' and getattr(self.hub,'defer_outbox_for_read',False)
        if not deferred_read:
            flush(self.hub)
        from hub_memory import Memory
        memory = None
        with self.hub.connect() as c:
            pending = c.execute('SELECT 1 FROM plan_outbox LIMIT 1').fetchone()
        if name != 'hub_report' and (pending or name in ('hub_memory','hub_plan','hub_begin')):
            memory = Memory(self.hub,self.session)
            if not deferred_read:
                memory.flush_reports()
        if name == 'hub_memory':
            return memory.read(**args)
        if name == 'hub_migration_preview':
            return self.hub.migration_preview(self.session)
        if name == 'hub_plan':
            return memory.plan(**args)
        if name == 'hub_context':
            if any(k in args for k in ('work', 'query', 'offset')):
                if 'after' in args:
                    raise HubError('invalid_arguments', 'Use either delta cursor or work lookup')
                return self.hub.lookup(self.session, args.get('work'), args.get('query', ''), args.get('offset', 0), args.get('limit', 8))
            result = self.hub.context(self.session, args.get('after'), args.get('limit', 12))
            if 'after' not in args:
                self.progress_hint(result)
            return result
        if name == 'hub_begin':
            result = self.hub.begin(self.session, **args)
            if args.get('stage') or args.get('stages'):
                try:
                    saved = Memory(self.hub,self.session).flush_reports(work=result['work'])
                    result['planSync'] = 'saved' if saved else 'pending'
                except (OSError,ValueError,sqlite3.Error) as error:
                    result['planSync'] = 'pending'; result['message'] = str(error)[:200]
            self.progress_hint(result, args['task'])
            return result
        if name == 'hub_task':
            return self.hub.create_task(self.session, **args)
        if name == 'hub_task_update':
            return self.hub.update_task(self.session, **args)
        if name == 'hub_image':
            if not hasattr(self.hub, 'attach_image'):
                raise HubError('server_required', 'Image attachment requires the connected Project Hub server')
            return self.hub.attach_image(self.session, **args)
        if name == 'hub_artifact':
            if not hasattr(self.hub, 'attach_artifact'):
                raise HubError('server_required', 'Artifact attachment requires the connected Project Hub server')
            return self.hub.attach_artifact(self.session, **args)
        if name == 'hub_task_link':
            return self.hub.link_task(self.session, **args)
        if name == 'hub_task_close':
            return self.hub.close_task(self.session, **args)
        if name == 'hub_report':
            result = self.hub.report(self.session, **args)
            with self.hub.connect() as c:
                linked = c.execute('SELECT 1 FROM work_stages WHERE work=?', (args['work'],)).fetchone()
            if linked:
                try:
                    saved = Memory(self.hub,self.session).flush_reports(work=result['work'])
                    result['planSync']='saved' if saved else 'pending'
                except (OSError,ValueError,sqlite3.Error) as error:
                    result['planSync']='pending'; result['message']=str(error)[:200]
            # The receipt and its delivery must not wait for an advisory full snapshot.
            result['progressHint'] = dict(deferred=True, next='Read hub_plan(task) at the next checkpoint')
            return result
        if name == 'hub_wait':
            duration = args.get('seconds', 20)
            if not isinstance(duration, int) or not 0 <= duration <= 20:
                raise HubError('invalid_wait', 'seconds must be 0–20')
            deadline = time.monotonic() + duration
            while True:
                result = self.hub.context(self.session, args['after'])
                if result['changes'] or time.monotonic() >= deadline:
                    return result
                time.sleep(.25)

    def progress_hint(self, result, task=None):
        if not hasattr(self.hub, 'store_factory'):
            return
        from hub_memory import Memory
        try:
            result['progressHint'] = Memory(self.hub,self.session).progress(task)
        except (OSError, ValueError, KeyError, sqlite3.Error):
            # The durable work/report acknowledgement must survive a hint failure.
            result['progressHint'] = dict(unavailable=True, next='Read hub_plan(task) at the next checkpoint')

    def dispatch(self, message):
        if 'id' not in message:
            return None
        rid, method = message['id'], message.get('method')
        if method == 'initialize':
            requested = message.get('params', {}).get('protocolVersion')
            version = requested if requested in ('2024-11-05', '2025-03-26', '2025-06-18') else '2025-03-26'
            result = dict(protocolVersion=version, capabilities=dict(tools={}), serverInfo=dict(name='project-hub', version='0.2.0'))
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = dict(tools=TOOLS)
        elif method == 'tools/call':
            try:
                params = message.get('params', {})
                value = self.call(params.get('name'), params.get('arguments', {}))
                result = dict(content=[dict(type='text', text=compact(value))], isError=False)
            except HubError as e:
                result = dict(content=[dict(type='text', text=compact(e.body))], isError=True)
            except (ValueError, TypeError, OSError, sqlite3.Error) as e:
                result = dict(content=[dict(type='text', text=compact(dict(error='unavailable', message=str(e)[:200])))], isError=True)
        else:
            return dict(jsonrpc='2.0', id=rid, error=dict(code=-32601, message='Method not found'))
        return dict(jsonrpc='2.0', id=rid, result=result)

    def serve(self):
        for line in sys.stdin:
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError('Object required')
                response = self.dispatch(message)
            except (ValueError, KeyError):
                response = dict(jsonrpc='2.0', id=None, error=dict(code=-32700, message='Invalid JSON-RPC message'))
            if response is not None:
                print(compact(response), flush=True)


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['hook', 'mcp', 'register', 'doctor', 'context', 'begin', 'report'])
    parser.add_argument('--root', default=os.getcwd())
    parser.add_argument('--session')
    parser.add_argument('--task')
    parser.add_argument('--title')
    parser.add_argument('--resource', action='append', default=[])
    parser.add_argument('--work')
    parser.add_argument('--revision', type=int)
    parser.add_argument('--result')
    parser.add_argument('--checkpoint', default='')
    parser.add_argument('--status', choices=['active', 'waiting', 'done', 'cancelled'], default='active')
    args = parser.parse_args()
    if os.environ.get('PROJECT_HUB_URL') and args.command in ('mcp','hook'):
        from hub_http import Client
        client=Client(os.environ['PROJECT_HUB_URL'], timeout=1.5 if args.command=='hook' else 15)
        if args.command=='mcp':
            Mcp(None,args.root,args.session,client=client).serve()
        else:
            try:
                raw=json.load(sys.stdin)
                result=client.hook(raw)
            except (HubError,OSError,ValueError,TypeError,AttributeError):
                result={}
            print(compact(result))
        return
    if os.environ.get('PROJECT_HUB_URL'):
        parser.error('Server mode supports mcp and hook; use MCP tools for other operations')
    hub = Hub()
    if args.command == 'register':
        print(compact(hub.register(args.root)))
    elif args.command == 'hook':
        raw = {}
        try:
            raw = json.load(sys.stdin)
            print(compact(hook(hub, raw)))
        except (HubError, OSError, sqlite3.Error, ValueError, TypeError, AttributeError):
            print(compact({}))
    elif args.command == 'mcp':
        Mcp(hub, args.root, args.session).serve()
    elif args.command == 'context':
        print(compact(Mcp(hub, args.root, args.session).call('hub_context', {})))
    elif args.command == 'begin':
        print(compact(Mcp(hub, args.root, args.session).call('hub_begin',
                      dict(task=args.task, title=args.title, resources=args.resource))))
    elif args.command == 'report':
        print(compact(Mcp(hub, args.root, args.session).call('hub_report',
                      dict(work=args.work, revision=args.revision, result=args.result,
                           checkpoint=args.checkpoint, status=args.status))))
    else:
        print(compact(dict(database=str(hub.db), project=hub.locate(args.root),
                           queue=flush(hub) if hub.db.exists() else None,
                           coverage='Runtime hook trust/firing must be verified in Codex; shell writes are not fully guarded')))


if __name__ == '__main__':
    main()
