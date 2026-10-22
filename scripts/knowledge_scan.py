"""Local, shallow source inventory. Never imports or executes project code."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

VERSION = 'shallow-4'
EXCLUDED = {'.git', '.codex', '.agents', '.local', '.tmp', '.test-tmp', '.gradle',
            '__pycache__', 'node_modules', 'target', 'build', 'dist', 'vendor'}
LANGUAGES = {'.py': 'python', '.java': 'java', '.js': 'javascript', '.mjs': 'javascript',
             '.ts': 'typescript', '.tsx': 'typescript', '.rs': 'rust', '.go': 'go',
             '.c': 'c', '.h': 'c', '.cpp': 'cpp', '.cs': 'csharp', '.kt': 'kotlin'}


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def entity_id(kind, name):
    return 'code:' + kind + ':' + digest(name)[:24]


def short_comment(value):
    return (value or '').strip().split('\n\n', 1)[0][:400]


def scan(root, policy=None, previous=None, path_prefix=''):
    """Return one immutable candidate; caller validates/applies it transactionally.

    Python uses the standard AST; Java uses the JDK compiler parser (parse only).
    Other languages explicitly retain file-level capability until an adapter exists.
    File hashes permit parse reuse; no filesystem timestamps establish freshness.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Scan root must be an existing project directory')
    policy = policy or {}
    previous = previous or {}
    helper = Path(__file__).with_name('ArchitectureSourceScanner.java')
    parser_version = VERSION + ':' + digest(helper.read_bytes()) if helper.exists() else VERSION
    java = shutil.which('java')
    release=Path(java).resolve().parent.parent/'release' if java else None
    parser_version += ':'+str(sys.version_info[:3])+':'+str(java)+':'+(digest(release.read_bytes()) if release and release.is_file() else '')
    excluded = EXCLUDED | set(policy.get('excludeDirectories', []))
    max_files = min(20000, max(1, int(policy.get('maxFiles', 10000))))
    max_bytes = min(8_000_000, max(1024, int(policy.get('maxFileBytes', 2_000_000))))
    files, diagnostics, facts, cache, java_files = [], [], [], {}, []
    fingerprint = hashlib.sha256(json.dumps(policy, sort_keys=True).encode())
    components = policy.get('components', [])
    parents = {c['id']:c.get('parent') for c in components}
    def lineage(identifier):
        result=[]
        while identifier and identifier not in result:
            result.append(identifier); identifier=parents.get(identifier)
        return result
    lineages={identifier:lineage(identifier) for identifier in parents}
    ancestor_sets={identifier:set(chain) for identifier,chain in lineages.items()}
    component_paths=[(prefix.replace('\\','/').removeprefix('./').rstrip('/'), position, configured['id'])
                     for position,configured in enumerate(components) for prefix in configured.get('paths',[])]
    capabilities = {'python': ['modules', 'types', 'declared-inheritance', 'entrypoints'],
                    'java': ['files']}
    inspected = reused = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in excluded and
                         not (Path(directory) / d).is_symlink() and
                         not getattr(Path(directory) / d, 'is_junction', lambda: False)())
        for name in sorted(names):
            path = Path(directory) / name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            relative = path_prefix + path.relative_to(root).as_posix()
            language = LANGUAGES.get(path.suffix.lower())
            if language is None and name not in {'pom.xml', 'package.json', 'pyproject.toml',
                                                'Cargo.toml', 'go.mod', 'build.gradle', 'settings.gradle'}:
                continue
            if len(files) >= max_files:
                diagnostics.append({'path': relative, 'code': 'file-limit', 'message': 'Scan is partial: file limit reached'})
                break
            if path.stat().st_size > max_bytes:
                diagnostics.append({'path': relative, 'code': 'size-limit', 'message': 'File excluded by size limit'})
                continue
            try:
                data = path.read_bytes()
                content_hash = digest(data)
                fingerprint.update(relative.encode() + b'\0' + content_hash.encode())
                text = data.decode('utf-8-sig')
            except (OSError, UnicodeError) as error:
                diagnostics.append({'path': relative, 'code': 'read-error', 'message': str(error)[:200]})
                continue
            matches = [(len(prefix),len(lineages[identifier]),-position,identifier)
                       for prefix,position,identifier in component_paths
                       if prefix=='.' or relative==prefix or relative.startswith(prefix+'/')]
            component = max(matches)[3] if matches else None
            file_id = entity_id('file', relative)
            file = dict(id=file_id, kind='entity', type='file', title=relative, language=language,
                        component=component, source=dict(path=relative, hash=content_hash, line=1),
                        generatedBy=VERSION, entrypoint=relative in policy.get('entrypoints', []))
            files.append(file)
            cached = previous.get(relative)
            if cached and cached.get('hash') == content_hash and cached.get('version') == parser_version:
                parsed = cached['facts']
                reused += 1
                facts.extend(parsed)
                cache[relative] = cached
                if not policy.get('entrypoints'): file['entrypoint'] = file['entrypoint'] or cached.get('entrypoint', False) or any(x.get('entrypoint') for x in parsed)
                if language == 'java':
                    capabilities['java'] = ['files', 'types', 'interfaces', 'declared-inheritance', 'entrypoints']
                continue
            inspected += 1
            if language == 'python':
                try:
                    tree = ast.parse(text, filename=relative)
                    module = relative.removeprefix(path_prefix).removesuffix('.py').replace('/', '.').removesuffix('.__init__')
                    parsed = []
                    def visit_type(node, parent=''):
                        qualified = module + '.' + parent + node.name
                        parsed.append(dict(name=qualified, title=node.name, type='class', language='python',
                            path=relative, line=node.lineno, bases=[ast.unparse(b) for b in node.bases],
                            imports=[], references=[dict(name=ast.unparse(call.func),line=call.lineno) for call in ast.walk(node) if isinstance(call,ast.Call) and isinstance(call.func,(ast.Name,ast.Attribute))],
                            comment=short_comment(ast.get_docstring(node))))
                        for child in node.body:
                            if isinstance(child, ast.ClassDef):
                                visit_type(child, parent + node.name + '.')
                    for node in tree.body:
                        if isinstance(node, ast.ClassDef):
                            visit_type(node)
                        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and \
                                isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__' and \
                                any(isinstance(v, ast.Constant) and v.value == '__main__' for v in node.test.comparators):
                            if not policy.get('entrypoints'): file['entrypoint'] = True
                    imports = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import): imports.extend(a.name for a in node.names)
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            imports.extend(node.module + '.' + a.name for a in node.names)
                    for item in parsed: item['imports'] = sorted(set(imports))
                    facts.extend(parsed)
                    cache[relative] = dict(hash=content_hash, version=parser_version, facts=parsed, entrypoint=file['entrypoint'])
                except SyntaxError as error:
                    diagnostics.append(dict(path=relative, code='parse-error', message=str(error)[:200]))
            elif language == 'java':
                java_files.append((path, file))
            elif language:
                capabilities.setdefault(language, ['files'])
        if len(files) >= max_files:
            break
    if java_files:
        if java and helper.exists():
            try:
                result = subprocess.run([java, str(helper)], input='\n'.join(str(p) for p, _ in java_files).encode('utf-8'),
                    capture_output=True, timeout=120, cwd=root,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
                if result.returncode:
                    raise ValueError(result.stderr[-1500:].decode('utf-8',errors='replace'))
                parsed = json.loads(result.stdout.decode('utf-8'))
                by_path = {str(p.resolve()): f for p, f in java_files}
                for item in parsed['types']:
                    file = by_path[item.pop('path')]
                    item.update(path=file['source']['path'], language='java')
                    if not policy.get('entrypoints'): file['entrypoint'] = file['entrypoint'] or item.get('entrypoint', False)
                    facts.append(item)
                for path, file in java_files:
                    own = [f for f in facts if f['path'] == file['source']['path']]
                    if not parsed['diagnostics']:
                        cache[file['source']['path']] = dict(hash=file['source']['hash'], version=parser_version, facts=own, entrypoint=file['entrypoint'])
                capabilities['java'] = ['files', 'types', 'interfaces', 'declared-inheritance', 'entrypoints']
                for error in parsed['diagnostics']:
                    diagnostics.append(dict(code='parse-error', message=error[:300]))
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                diagnostics.append(dict(code='adapter-error', language='java', message=str(error)[:300]))
        else:
            diagnostics.append(dict(code='adapter-unavailable', language='java', message='A local JDK is required for Java type parsing'))
    entities = list(files)
    for component in components:
        entities.append(dict(id=component['id'], kind='entity', type='component', title=component['title'],
                             parent=component.get('parent'), paths=component.get('paths', []),
                             generatedBy=VERSION, description=component.get('description', '')))
    file_map = {f['source']['path']: f for f in files}
    # Monorepos may declare the same qualified name in independent applications.
    # Keep both declarations and resolve only unique candidates.
    index = {}
    for fact in facts:
        fact['id'] = entity_id('type', fact['language'] + ':' + fact['path'] + ':' + fact['name'])
        index.setdefault(fact['name'], set()).add(fact['id'])
    suffix_index={}
    for name,values in index.items():
        for position,character in enumerate(name):
            if character=='.': suffix_index.setdefault(name[position+1:],set()).update(values)
    relations = []; external_ids=set()
    def resolve(candidates):
        matches=set().union(*(index.get(c,set()) for c in candidates))
        if not matches:
            # Source-layout prefixes may differ from import package names.
            # This is explicitly syntax resolution, never runtime dispatch.
            matches=set().union(*(suffix_index.get(c,set()) for c in candidates if '.' in c))
        return matches
    for fact in facts:
        file = file_map[fact['path']]
        identifier = fact['id']
        entities.append(dict(id=identifier, kind='entity', type=fact['type'], title=fact['title'],
            qualifiedName=fact['name'], language=fact['language'], component=file['component'],
            source=dict(file['source'], line=fact['line']), summaryFromSource=fact.get('comment', ''),
            generatedBy=VERSION, entrypoint=fact.get('entrypoint', False) and (not policy.get('entrypoints') or fact['path'] in policy['entrypoints'])))
        relations.append(dict(id=entity_id('relation', file['id'] + ':contains:' + identifier),
            kind='relation', **{'from': file['id'], 'to': identifier}, type='contains', provenance='static',
            resolution='declaration', evidence=[dict(path=fact['path'], line=fact['line'])], generatedBy=VERSION))
        for relation_type, bases in [('extends', fact.get('bases', [])), ('implements', fact.get('interfaces', []))]:
            for base in bases:
                # Resolve only an unambiguous declaration/import; no runtime dispatch claim.
                base = base.split('<')[0]
                candidates = [base, fact['name'].rsplit('.', 1)[0] + '.' + base]
                candidates += [i for i in fact.get('imports', []) if i.endswith('.' + base)]
                matches = resolve(candidates)
                if len(matches) == 1:
                    target = matches.pop()
                else:
                    target = entity_id('external', fact['language'] + ':' + base)
                    if target not in external_ids:
                        external_ids.add(target)
                        entities.append(dict(id=target, kind='entity', type='external', title=base,
                                             generatedBy=VERSION, resolution='unresolved'))
                relations.append(dict(id=entity_id('relation', identifier + relation_type + target),
                    kind='relation', **{'from': identifier, 'to': target}, type=relation_type, provenance='static',
                    resolution='syntax', evidence=[dict(path=fact['path'], line=fact['line'])], generatedBy=VERSION))
        for reference in fact.get('references', []):
            name = reference['name'].split('<')[0].removesuffix('[]')
            candidates = [name, fact['name'].rsplit('.', 1)[0] + '.' + name]
            candidates += [i for i in fact.get('imports', []) if i.endswith('.' + name)]
            matches = resolve(candidates)
            if len(matches) == 1:
                target = matches.pop()
                if target != identifier:
                    relations.append(dict(id=entity_id('relation', identifier + ':uses:' + target),
                        kind='relation', **{'from': identifier, 'to': target}, type='uses', provenance='static',
                        resolution='syntax', evidence=[dict(path=fact['path'], line=reference['line'])], generatedBy=VERSION))
        for imported in fact.get('imports', []):
            matches = resolve([imported])
            if len(matches) == 1:
                target = next(iter(matches))
                relations.append(dict(id=entity_id('relation', file['id']+':imports:'+target), kind='relation',
                    **{'from':file['id'],'to':target}, type='imports', provenance='static', resolution='syntax',
                    evidence=[dict(path=fact['path'],line=1)], generatedBy=VERSION))
    for file in files:
        if file['component']:
            relations.append(dict(id=entity_id('relation', file['component'] + file['id']), kind='relation',
                **{'from': file['component'], 'to': file['id']}, type='contains', provenance='authored',
                generatedBy=VERSION, evidence=[dict(path=file['source']['path'], line=1)]))
    for component in components:
        if component.get('parent'):
            relations.append(dict(id=entity_id('relation',component['parent']+':contains:'+component['id']),
                kind='relation', **{'from':component['parent'],'to':component['id']}, type='contains',
                provenance='authored',resolution='configuration',generatedBy=VERSION,evidence=[]))
    component_map={e['id']:e.get('component') for e in entities}
    direct={}
    for edge in {r['id']:r for r in relations}.values():
        source,target=component_map.get(edge['from']),component_map.get(edge['to'])
        if source and target and source!=target and edge['type']!='contains':
            aggregate=direct.setdefault((source,target),dict(count=0,evidence=[]))
            aggregate['count']+=1
            for proof in edge.get('evidence',[]):
                if proof not in aggregate['evidence'] and len(aggregate['evidence'])<10:
                    aggregate['evidence'].append(proof)
    aggregates={}
    for (source,target),direct_aggregate in direct.items():
        for source_group in lineages[source]:
            for target_group in lineages[target]:
                # Membership is not a dependency. Roll up only across branches.
                if source_group in ancestor_sets[target_group] or target_group in ancestor_sets[source_group]:
                    continue
                aggregate=aggregates.setdefault((source_group,target_group),dict(count=0,evidence=[]))
                aggregate['count']+=direct_aggregate['count']
                for proof in direct_aggregate['evidence']:
                    if proof not in aggregate['evidence'] and len(aggregate['evidence'])<10:
                        aggregate['evidence'].append(proof)
    for (source,target),aggregate in aggregates.items():
        relations.append(dict(id=entity_id('relation',source+':depends-on:'+target),kind='relation',
            **{'from':source,'to':target},type='depends-on',provenance='static',resolution='aggregate-syntax',
            count=aggregate['count'], evidence=aggregate['evidence'],generatedBy=VERSION))
    return dict(schemaVersion=1, adapterVersion=VERSION, fingerprint=fingerprint.hexdigest(),
                entities=entities, relations=list({r['id']: r for r in relations}.values()), capabilities=capabilities, diagnostics=diagnostics,
                status='partial' if diagnostics else 'ready', cache=cache,
                counts=dict(files=len(files), types=len(facts), parsed=inspected, reused=reused))
