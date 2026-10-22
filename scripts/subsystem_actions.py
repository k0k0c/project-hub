"""Build ordinary KnowledgeStore changesets from subsystem forms.

Retain the built request for retries: building again from a newer context is a
different request. This adapter never edits knowledge items or starts a scan.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import PurePosixPath

from knowledge_store import KnowledgeError, KnowledgeStore


EDITABLE = frozenset({'title', 'parent', 'paths', 'description'})


def subsystem_references(store, identifier):
    """Project-scoped removal blockers, read before building the changeset.

The changeset revision check protects against concurrent writes after this
read. Even the generated component entity blocks removal until an explicit
item migration/cleanup has been designed; authored history is never deleted.
"""
    scalar = ('component', 'parent', 'from', 'to')
    arrays = ('componentAncestors', 'entityRefs', 'nodeIds', 'orderedEdges')
    predicates = ['id=?']
    for field in scalar:
        predicates.append(f"json_extract(body,'$.{field}')=?")
    for field in arrays:
        predicates.append(f"EXISTS (SELECT 1 FROM json_each(body,'$.{field}') WHERE value=?)")
    with store.registry.connect() as connection:
        rows = connection.execute(
            'SELECT id FROM knowledge_items WHERE project=? AND (' +
            ' OR '.join(predicates) + ') ORDER BY id LIMIT 21',
            (store.project, *([identifier] * len(predicates))),
        ).fetchall()
    return [row['id'] for row in rows]


def build_subsystem_request(context, action, identifier, patch=None, *, key,
                            reason, task=None, stage=None, references=None):
    """Transform an exact policy snapshot into existing changeset arguments.

Removal requires references checked at this context's revision. None means
unchecked, whereas [] means checked and empty. Null parent clears a parent.
No ID changes, default-policy merge, generated facts, or source deletions.
"""
    if not isinstance(context, dict) or 'revision' not in context or 'policy' not in context:
        raise KnowledgeError('invalid_subsystem', 'Knowledge context is required', 400)
    if not isinstance(identifier, str) or not identifier:
        raise KnowledgeError('invalid_subsystem', 'Subsystem ID is required', 400)
    if action not in ('create', 'update', 'remove'):
        raise KnowledgeError('invalid_subsystem', 'Use create, update or remove', 400)
    patch = {} if patch is None else patch
    if not isinstance(patch, dict) or set(patch) - EDITABLE:
        raise KnowledgeError('invalid_subsystem', 'Only subsystem fields may be changed', 400)
    policy = deepcopy(context['policy'])
    KnowledgeStore.validate_policy(policy)
    components = policy.setdefault('components', [])
    found = next((value for value in components if value['id'] == identifier), None)
    if action == 'create':
        if found is not None:
            raise KnowledgeError('subsystem_exists', 'Subsystem ID already exists')
        if not isinstance(patch.get('title'), str) or not patch['title'].strip():
            raise KnowledgeError('invalid_subsystem', 'A subsystem title is required', 400)
        found = dict(id=identifier, paths=[])
        found.update(deepcopy(patch))
        components.append(found)
    elif found is None:
        raise KnowledgeError('unknown_subsystem', 'Subsystem does not exist', 404)
    elif action == 'update':
        if not patch:
            raise KnowledgeError('invalid_subsystem', 'Choose fields to update', 400)
        if 'title' in patch and (not isinstance(patch['title'], str) or not patch['title'].strip()):
            raise KnowledgeError('invalid_subsystem', 'A subsystem title is required', 400)
        found.update(deepcopy(patch))
    else:
        if patch:
            raise KnowledgeError('invalid_subsystem', 'Removal does not accept edits', 400)
        if any(value.get('parent') == identifier for value in components):
            raise KnowledgeError('subsystem_has_children', 'Move child subsystems before removing this subsystem')
        if references is None:
            raise KnowledgeError('subsystem_unchecked', 'Check saved references before removing a subsystem')
        if references:
            raise KnowledgeError('subsystem_in_use', 'Saved architecture items still reference this subsystem', references=list(references)[:20])
        components.remove(found)
    # Canonical root representation; preserve everything else, including any
    # additional component metadata that the existing validator accepts.
    if action != 'remove' and 'parent' in patch and patch['parent'] is None:
        found.pop('parent', None)
    KnowledgeStore.validate_policy(policy)
    request = dict(expected=context['revision'], key=key, operations=[], reason=reason, policy=policy)
    if task is not None:
        request['task'] = task
    if stage is not None:
        request['stage'] = stage
    return request


def plan_subsystem(store, *, expected, action, identifier, patch=None, key, reason, task=None, stage=None):
    """Preview a complete, immutable ordinary changeset without applying it."""
    context = store.context()
    if type(expected) is not int or context['revision'] != expected:
        raise KnowledgeError('revision_conflict', 'Refresh/reconcile before resubmitting', revision=context['revision'])
    references = subsystem_references(store, identifier) if action == 'remove' else None
    empty_item = None
    if references == [identifier]:
        item = store.read(identifier)
        if item.get('type') == 'component' and not any(item.get(field) for field in
                ('description', 'documentRefs', 'sources', 'evidence', 'source', 'nodeIds')):
            references = []
            empty_item = item
    request = build_subsystem_request(context, action, identifier, patch, key=key, reason=reason,
        task=task, stage=stage, references=references)
    if empty_item is not None:
        request['operations'] = [dict(op='put', item={**empty_item, 'removed': True})]
    if action != 'remove':
        try:
            item = store.read(identifier)
        except KnowledgeError as error:
            if error.status != 404:
                raise
            item = dict(id=identifier, kind='entity', type='component', title='', provenance='authored')
        if item.get('kind') != 'entity' or item.get('type') != 'component':
            raise KnowledgeError('subsystem_id_conflict', 'Subsystem ID belongs to a different architecture item')
        component = next(row for row in request['policy']['components'] if row['id'] == identifier)
        item.pop('removed', None)
        for field in ('title', 'parent', 'paths'):
            if field in component:
                item[field] = deepcopy(component[field])
            else:
                item.pop(field, None)
        if patch and 'description' in patch:
            item['description'] = component.get('description', '')
        request['operations'] = [dict(op='put', item=item)]
    store.changeset(**request, validate_only=True)
    return {'request': request}


def plan_first_level(store, expected, proposals, *, key, reason, actor=None, task=None, stage=None, parent=None):
    """Validate model suggestions into an ordinary additive authored changeset.

    Model output cannot choose IDs, alter existing subsystems or introduce
    arbitrary item fields. Source boundaries must match the available inventory.
    The caller applies this exact request; conflicts never cause a rebuilt write.
    """
    context = store.context()
    if type(expected) is not int or context['revision'] != expected:
        raise KnowledgeError('revision_conflict', 'Refresh/reconcile before resubmitting', revision=context['revision'])
    invalid = lambda: KnowledgeError('invalid_subsystem_proposal', 'Use bounded new subsystems and verified source boundaries', 400)
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 10 or not isinstance(key, str) or not key:
        raise invalid()
    policy = deepcopy(context['policy'])
    if parent is not None and not any(component['id'] == parent for component in policy['components']):
        raise invalid()
    titles = {component['title'].strip().casefold() for component in policy['components']
              if component.get('parent') == parent}
    with store.registry.connect() as connection:
        rows = connection.execute("""SELECT body FROM knowledge_items WHERE project=? AND kind='entity'
            AND json_extract(body,'$.type')='file' AND json_extract(body,'$.generatedBy') IS NOT NULL
            AND COALESCE(json_extract(body,'$.removed'),0)=0
            AND COALESCE(json_extract(body,'$.analysisStatus'),'current') NOT IN ('stale','unavailable')""",
            (store.project,)).fetchall()
    available = {ref['id'] for ref in context.get('rootRefs', []) if ref.get('available')}
    inventory = []
    for row in rows:
        source = json.loads(row['body']).get('source', {})
        path = source.get('path', '')
        root = path.split('/')[1] if path.startswith('@roots/') else '0'
        digest = source.get('hash', '')
        if root in available and isinstance(path, str) and len(digest) == 64:
            inventory.append(dict(path=path, hash=digest))
    operations = []
    prefix = 'subsystem:ai:' + hashlib.sha256(key.encode()).hexdigest()[:20] + ':'
    for index, proposal in enumerate(proposals):
        if not isinstance(proposal, dict) or set(proposal) != {'title', 'description', 'paths'}:
            raise invalid()
        title, description, paths = (proposal[field] for field in ('title', 'description', 'paths'))
        if (not isinstance(title, str) or not title.strip() or len(title) > 300 or
                any(ord(char) < 32 for char in title) or title.strip().casefold() in titles or
                not isinstance(description, str) or len(description) > 1200 or
                not isinstance(paths, list) or len(paths) > 20):
            raise invalid()
        titles.add(title.strip().casefold())
        evidence, cleaned = [], []
        for path in paths:
            if (not isinstance(path, str) or not 1 <= len(path) <= 300 or '\\' in path or ':' in path or
                    any(ord(char) < 32 for char in path) or PurePosixPath(path).is_absolute() or
                    '..' in PurePosixPath(path).parts):
                raise invalid()
            normalized = str(PurePosixPath(path))
            matches = [source for source in inventory if source['path'] == normalized or
                       source['path'].startswith(normalized.rstrip('/') + '/') or
                       normalized == '.' and not source['path'].startswith('@roots/')]
            if not matches or normalized in cleaned:
                raise invalid()
            cleaned.append(normalized)
            evidence.extend(matches[:3])
        identifier = prefix + str(index)
        if any(component['id'] == identifier for component in policy['components']):
            raise invalid()
        component = dict(id=identifier, title=title.strip(), description=description, paths=cleaned)
        if parent is not None:
            component['parent'] = parent
        policy['components'].append(component)
        item = dict(component, kind='entity', type='component', provenance='authored')
        if evidence:
            item['evidence'] = list({source['path']: source for source in evidence}.values())[:3]
        operations.append(dict(op='put', item=item))
    KnowledgeStore.validate_policy(policy)
    request = dict(expected=expected, key=key, operations=operations, policy=policy,
                   reason=reason, task=task, stage=stage)
    if actor is not None:
        request['actor'] = actor
    store.changeset(**request, validate_only=True)
    return request
