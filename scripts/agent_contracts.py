"""Client-facing operation contracts shared by MCP discovery and API reference.

These schemas explain request shapes. Revision checks, ownership, paths, secrets,
cross-field semantics and authorization remain authoritative in the backend.
No schema references are used: clients receive self-contained tool definitions.
"""
from copy import deepcopy
import json


def text(description='', **bounds):
    return dict(type='string', **({'description': description} if description else {}), **bounds)


def enum(*values):
    return dict(type='string', enum=list(values))


def array(items=None, **bounds):
    return dict(type='array', items=items or text(), **bounds)


def obj(properties, required=(), additional=False, **extra):
    result = dict(type='object', properties=properties, additionalProperties=additional, **extra)
    if required:
        result['required'] = list(required)
    return result


def when(field, value, then):
    return {'if': {'properties': {field: {'const': value}}, 'required': [field]}, 'then': then}


REVISION = dict(type=['integer', 'string'], description='Exact revision returned by the corresponding read; knowledge and project revisions differ.')
INTEGER = dict(anyOf=[dict(type='integer'), dict(type='string', pattern=r'^-?[0-9]+$')])
BOOLEAN = dict(type='boolean')
HASH = text('Captured target-state SHA-256 from the scoped review.', pattern='^[a-f0-9]{64}$')
NULL_TEXT = dict(type=['string', 'null'])
STATUS = enum('planned', 'active', 'queued', 'blocked', 'done', 'cancelled')
PRIORITY = dict(type=['string', 'null'], enum=['blocker', 'critical', 'major', 'minor', 'trivial', None])
SCOPE = obj(dict(kind=enum('workspace', 'project'), root=NULL_TEXT, nativeRef=NULL_TEXT), ['kind'],
            anyOf=[{'required': ['root'], 'properties': {'root': text(minLength=1)}},
                   {'required': ['nativeRef'], 'properties': {'nativeRef': text(minLength=1)}}],
            description='Actual native project scope: kind plus absolute root and/or opaque nativeRef.')
SOURCE = obj(dict(path=text('Project-relative path or existing Hub artifact/source reference.'), label=text(), sourceProject=NULL_TEXT,
                  hash=text(pattern='^[a-f0-9]{64}$'), assets=array(obj(dict(hash=text(), name=text()), ['hash', 'name'], True))),
             ['path'], True)
GROUPS = array(obj(dict(id=text(), title=text(), parent=text(), nodeIds=array(), description=text()), ['id', 'title']), maxItems=512)


def estimate(review=False):
    properties = dict(hoursLow=dict(type='number', minimum=0), hoursHigh=dict(type='number', minimum=0),
                      percentLow=dict(type='number', minimum=0, maximum=100), percentHigh=dict(type='number', minimum=0, maximum=100),
                      confidence=text(maxLength=160), note=text(maxLength=1200))
    if not review:
        properties.update(updatedBy=text(), updatedAt=text())
    result = obj(properties, ['confidence', 'note'] if review else (), not review,
                 description='Sequential active agent hours. Omit both hours when unknown; intervals require both bounds.')
    result['dependentRequired'] = {'hoursLow': ['hoursHigh'], 'hoursHigh': ['hoursLow'],
                                   'percentLow': ['percentHigh'], 'percentHigh': ['percentLow']}
    if not review:
        result['type'] = ['object', 'null']
    return result


def task_patch():
    blocker = obj(dict(kind=enum('technical', 'user_input', 'administrative'), reason=text(maxLength=1200), action=text(maxLength=1200)),
                  ['kind', 'reason', 'action'])
    blocker['type'] = ['object', 'null']
    return obj(dict(title=text(), summary=text(), status=STATUS, estimate=estimate(),
                    primary=obj(dict(selected=BOOLEAN, project=text()), ['selected', 'project']),
                    scope=array(), deferred=array(), acceptance=array(), sources=array(SOURCE),
                    type=enum('epic', 'task', 'bug'), priority=PRIORITY,
                    parentTask=NULL_TEXT, links=array(obj(dict(type=enum('blocks', 'blocked-by', 'related', 'duplicates', 'duplicated-by'),
                        target=text(), project=NULL_TEXT), ['type', 'target'], True)),
                    weight=dict(type=['number', 'null'], exclusiveMinimum=0), closedManually=BOOLEAN,
                    closeWarning=array(), closeReason=text(), gitCheckpoint=dict(type=['object', 'null'], properties={}, additionalProperties=True),
                    gitCommit=dict(type=['object', 'null'], properties={}, additionalProperties=True), blocker=blocker),
               description='Metadata patch, for example {"sources":[{"label":"Design","path":"docs/design.md"}]}. Merge existing sources before attaching more.')


def knowledge_item():
    # Items deliberately permit extension fields accepted by validate_item.
    fields = {key: text() for key in ('id', 'kind', 'title', 'description', 'markdown', 'type', 'audience', 'section',
                                    'status', 'visibility', 'format', 'from', 'to', 'viewType', 'provenance')}
    fields.update(kind=enum('document', 'entity', 'relation', 'view'), entityRefs=array(), documentRefs=array(),
                  sources=array(SOURCE), evidence=array(SOURCE), source=SOURCE, nodeIds=array(), orderedEdges=array(),
                  presentationGroups=GROUPS, htmlBundle=obj(dict(entry=text(), files=array(obj(dict(path=text(), hash=text(pattern='^[a-f0-9]{64}$'),
                      size=dict(type='integer', minimum=0)), ['path', 'hash', 'size'], True), minItems=1)), ['entry', 'files'], True))
    fields.update({key: NULL_TEXT for key in ('documentDate', 'dateBasis', 'versionLabel', 'versionGroup')})
    result = obj(fields, ['id', 'kind'], True)
    result['allOf'] = [when('kind', kind, {'required': ['title']}) for kind in ('document', 'entity', 'view')]
    result['allOf'].append(when('kind', 'relation', {'required': ['from', 'to', 'type']}))
    return result


def knowledge_actions():
    """Exactly the 24 agent-exposed actions, excluding backup administration."""
    common = dict(task=text(), stage=text())
    pagination = dict(offset=INTEGER, limit=INTEGER)
    write = dict(expected=REVISION, key=text('Stable idempotency key for this exact change.'))
    operation = obj(dict(op=enum('put', 'delete'), id=text(), item=knowledge_item()), ['op'])
    operation['allOf'] = [when('op', 'put', {'required': ['item']}), when('op', 'delete', {'required': ['id']})]
    query = obj(dict(operation=text('Operation ID returned by research-capabilities.'), id=text(), target=text(),
                     depth=dict(anyOf=[dict(type='integer', minimum=1, maximum=10000), {'const': 'all'}]),
                     representation=enum('symbols', 'files', 'symbols-in-files'), provider=text(),
                     line=dict(type='integer', minimum=1), column=dict(type='integer', minimum=1), catalogOnly=BOOLEAN,
                     intent=enum('browse', 'research')), ['operation', 'id'])
    query['allOf'] = [when('operation', 'path', {'required': ['target']})]
    metadata = obj({key: (array() if key in ('entityRefs', 'documentRefs') else NULL_TEXT if key in
                   ('documentDate', 'dateBasis', 'versionLabel', 'versionGroup') else text()) for key in
                   ('title', 'description', 'audience', 'section', 'type', 'status', 'visibility', 'entityRefs',
                    'documentRefs', 'documentDate', 'dateBasis', 'versionLabel', 'versionGroup')})
    policy = obj(dict(audiences=array(), sections=array(), entrypoints=array(), excludeDirectories=array(), scanRoots=array(),
        components=array(obj(dict(id=text(), title=text(), parent=NULL_TEXT, description=text(), paths=array()), ['id', 'title'], True)),
        updateMode=enum('manual', 'on-demand', 'background'), reviewMode=enum('significant', 'manual'),
        maxFiles=dict(type='integer', minimum=1, maximum=20000), maxFileBytes=dict(type='integer', minimum=1024, maximum=8000000),
        descriptionLimit=dict(type='integer', minimum=1, maximum=1200), intervalSeconds=dict(type='integer', minimum=30, maximum=86400)))
    return {
        'context': obj({}),
        'search': obj(dict(query=text(), kind=text(), type=text(), component=text(), entrypoint=text(), endpoint=text(), **pagination)),
        'source-tree': obj(dict(query=text(), component=text(), mode=text(), **pagination)),
        'source-read': obj(dict(id=text(), **pagination), ['id']),
        'read': obj(dict(id=text(), revision=INTEGER), ['id']),
        'history': obj(dict(id=text(), **pagination)),
        'subsystem-plan': obj(dict(**write, operation=enum('create', 'update', 'remove'), identifier=text(),
            patch=obj(dict(title=text(), description=text(), paths=array(), parent=NULL_TEXT)),
            reason=text(), **common), ['expected', 'operation', 'identifier', 'key', 'reason']),
        'changeset': obj(dict(**write, operations=array(operation, maxItems=500), reason=text(), validate_only=BOOLEAN,
            policy=policy, code_revision=obj(dict(fingerprint=text(), heads=obj({}, additional=text()), rootRefs=array(), basis=text()), additional=True), **common), ['expected', 'key', 'operations', 'reason']),
        'scan': obj(common), 'job': obj(dict(id=text()), ['id']),
        'import-preview': obj(dict(paths=array()), ['paths']),
        'import-read': obj(dict(identifier=text(), index=INTEGER, field=enum('source', 'markdown', 'html', 'diff'), **pagination), ['identifier']),
        'import-apply': obj(dict(identifier=text(), **write, selections=array(), metadata=obj({}, additional=metadata), **common), ['identifier', 'expected', 'key']),
        'restore': obj(dict(id=text(), revision=INTEGER, **write, **common), ['id', 'revision', 'expected', 'key']),
        'impact': obj(dict(paths=array(), change=obj(dict(**{key: BOOLEAN for key in ('structure', 'contracts', 'behavior', 'userWorkflow',
            'cosmetic', 'noStructuralImpact', 'knowledgeUpdated')}, reason=text()), additional=True), record=BOOLEAN, **common)),
        'export': obj(dict(public=BOOLEAN)),
        'research-capabilities': obj(dict(id=text()), ['id']), 'research-object': obj(dict(id=text()), ['id']),
        'research': obj(dict(query=query, **common), ['query']),
        'research-result': obj(dict(id=text(), **pagination), ['id']),
        'research-cancel': obj(dict(id=text()), ['id']), 'research-history': obj(pagination),
        'research-save': obj(dict(**write, title=text(), nodeIds=array(), edgeIds=array(), presentationGroups=GROUPS, resultId=text()),
                             ['expected', 'key', 'title', 'nodeIds', 'edgeIds']),
        'research-providers': obj({}),
    }


def proposal():
    result = obj(dict(task=text(), stage=NULL_TEXT, decision=enum('current', 'done', 'superseded', 'duplicate', 'clarify'),
        reason=text(minLength=1, maxLength=1200), confidence=text(minLength=1, maxLength=160), expectedState=HASH,
        evidence=array(text(minLength=1, maxLength=300), minItems=1, maxItems=6), priority=PRIORITY,
        criteria=array(obj(dict(requirement=text(), evidence=text()), ['requirement', 'evidence']), minItems=1, maxItems=100),
        replacement=obj(dict(task=text(), stage=text(), expectedState=HASH), ['task', 'stage', 'expectedState']),
        requirements=array(text(minLength=1, maxLength=400), maxItems=20)),
        ['task', 'decision', 'reason', 'confidence', 'evidence', 'expectedState'])
    result['allOf'] = [when('decision', 'done', {'required': ['criteria']})] + [
        when('decision', decision, {'required': ['replacement', 'requirements']}) for decision in ('superseded', 'duplicate')]
    return result


def connection_profile():
    action = obj(dict(tool=text(), arguments=obj({}, additional=True), path=text(), method=enum('GET', 'POST'),
                      idField=text(), uriField=text(), projectRouting=BOOLEAN))
    capabilities = obj(dict(openChat={'anyOf': [obj(dict(uriTemplate=text())), {'type': 'null'}, {'const': False}]},
                            **{key: {'anyOf': [action, {'type': 'null'}, {'const': False}]}
                               for key in ('createChat', 'sendMessage')}))
    native = obj({key: dict(type=['string', 'null']) for key in ('client', 'clientInstance', 'host', 'nativeId', 'openUri', 'title', 'model')})
    rules = obj(dict(scope=enum('project', 'application'), destination=text(), consent=BOOLEAN, revision=text(),
                     status=enum('saved', 'manual'), manifestPath=text(), loadVerified=BOOLEAN, compactionVerified=BOOLEAN,
                     bootstrapSha256=text(), connectionId=text()), ['scope', 'status', 'consent'])
    return obj(dict(schemaVersion={'const': 1, 'type': 'integer'}, clientVersion=NULL_TEXT, clientInstance=NULL_TEXT,
        host=NULL_TEXT, model=NULL_TEXT, nativeChat=native, capabilities=capabilities,
        projectContext=obj(dict(kind=enum('repository', 'workspace', 'project'), identification=enum('root', 'native-ref', 'both'),
            projectInstructions=BOOLEAN, globalInstructions=BOOLEAN), ['kind', 'identification', 'projectInstructions', 'globalInstructions']),
        control=obj(dict(protocol=enum('mcp-http', 'http-json'), endpoint=text()), ['protocol', 'endpoint']),
        persistentInstructions=rules), ['schemaVersion'],
        description='Declarative client capabilities, for example {"schemaVersion":1,"capabilities":{}}. Keep credentials and commands in private native configuration.')


def enrich_tools(tools):
    """Return independent enriched declarations, preserving all existing tools."""
    result = deepcopy(tools)
    for tool in result:
        schema = tool['inputSchema']; properties = schema['properties']; name = tool['name']
        if 'projectScope' in properties:
            properties['projectScope'] = deepcopy(SCOPE)
        if name == 'hub_knowledge':
            actions = knowledge_actions()
            properties['action']['enum'] = list(actions)
            # The union keeps every named field discoverable; action branches narrow it.
            fields = {key: value for args in actions.values() for key, value in args['properties'].items()}
            fields['query'] = {'anyOf': [text(), actions['research']['properties']['query']]}
            properties['args'] = obj(fields, description='Action-specific arguments; see conditional schemas. Example: read uses {"id":"guide"}.')
            schema['allOf'] = [when('action', action, dict(properties={'args': args},
                **({'required': ['args']} if args.get('required') else {}))) for action, args in actions.items()]
        elif name == 'hub_task_update':
            properties['patch'] = task_patch()
        elif name == 'hub_review':
            properties['proposals']['items'] = proposal()
            properties['estimates']['items'] = obj(dict(task=text(), stage=NULL_TEXT, expectedState=HASH, estimate=estimate(True)),
                                                   ['task', 'stage', 'expectedState', 'estimate'])
            schema['allOf'] = [when('action', action, {'required': ['actionId', 'work', 'expected', field]})
                               for action, field in (('propose', 'proposals'), ('estimate', 'estimates'))]
        elif name == 'hub_connection':
            properties['profile'] = connection_profile()
            schema['allOf'] = [when('action', 'describe', {'required': ['profile']})]
        elif name == 'hub_project_bindings':
            properties['scope'] = deepcopy(SCOPE)
            required = {action: ['bindingId'] for action in ('read', 'history', 'workspaces')}
            required.update({action: ['scope', 'requestId'] for action in ('resolve', 'create')})
            required.update({action: ['bindingId', 'expectedRevision', 'requestId'] for action in ('update', 'repair', 'unbind', 'verify', 'relocate')})
            required['verify'] += ['status']
            required['relocate'] += ['scope', 'expectedProjectRevision', 'workspaceId']
            required['resume'] = ['bindingId', 'requestId']
            allowed = {action: ['bindingId'] for action in ('read', 'history', 'workspaces')}
            allowed.update({action: ['scope', 'project', 'name', 'requestId'] for action in ('resolve', 'create')})
            allowed.update(update=['bindingId', 'scope', 'project', 'expectedRevision', 'requestId'],
                verify=['bindingId', 'expectedRevision', 'requestId', 'rulePath', 'status'],
                relocate=['bindingId', 'scope', 'expectedRevision', 'expectedProjectRevision', 'workspaceId', 'requestId'],
                repair=['bindingId', 'expectedRevision', 'requestId'], unbind=['bindingId', 'expectedRevision', 'requestId'],
                resume=['bindingId', 'requestId'], list=[])
            schema['allOf'] = [when('action', action, obj(
                {key: properties[key] for key in ['session', 'action', *fields]}, required.get(action, ())))
                for action, fields in allowed.items()]
        elif name == 'hub_launch':
            document = obj(dict(title=text(), markdown=text(minLength=1, maxLength=120000)), ['title', 'markdown'])
            properties['result'] = {'anyOf': [document, text(maxLength=1600)]}
            schema['allOf'] = [when('action', 'ack', {'required': ['projectScope', 'nativeId']}),
                when('action', 'fail', {'required': ['nativeId', 'result'], 'properties': {'result': text(minLength=1, maxLength=1600)}}),
                when('action', 'complete', {'required': ['nativeId'], 'anyOf': [
                    {'required': ['work', 'revision']}, {'required': ['result'], 'properties': {'result': document}}]})]
    # Fragments above share immutable catalog constants while being assembled;
    # callers must never be able to mutate those constants or another result.
    return deepcopy(result)


def api_reference(tools):
    """Generate a complete Markdown reference from the same discovery catalog."""
    lines = ['# Project Hub agent API', '',
             'Use Streamable HTTP MCP tool discovery for the current contract. Each request uses its own conversation session.', '',
             'Schemas describe shapes; backend validation enforces permissions, revisions, ownership and semantic constraints.', '']
    for tool in enrich_tools(tools):
        lines += ['## ' + tool['name'], '', tool.get('description', ''), '',
                  '```json', json.dumps(tool['inputSchema'], ensure_ascii=False, separators=(',', ':')), '```', '']
    return '\n'.join(lines)
