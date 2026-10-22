"""Preview/apply/remove only an owned scoped project-binding rule."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from native_instruction_store import atomic
from native_onboarding import OnboardingError, read_rule, merge_block, cursor_frontmatter
from project_bindings import ProjectBindings


def plan(host, binding, workspace):
    if host not in ('codex','cursor'):
        raise OnboardingError('A documented project-rule adapter is required.')
    scope = ProjectBindings.scope(binding['scope'])
    root = Path(workspace).resolve()
    if scope.get('root') != str(root):
        raise OnboardingError('The project rule must be at the exact bound root.')
    ProjectBindings.scope(dict(kind='workspace',root=str(root)))
    path = root/('AGENTS.md' if host=='codex' else '.cursor/rules/project-hub.mdc')
    if host=='codex' and (read_rule(root/'AGENTS.override.md') or b'').strip():
        path = root/'AGENTS.override.md'
    # A source project is an intended rule location. Reject links on the full
    # target path, rather than using the private configuration/source guard.
    from project_workspaces import no_reparse
    no_reparse(path)
    before = read_rule(path)
    owner = binding['connection']
    if not re.fullmatch('[0-9a-f]{32}',owner):
        raise OnboardingError('Invalid connection owner.')
    begin = f'<!-- project-hub:binding:{owner}:start -->'.encode()
    end = f'<!-- project-hub:binding:{owner}:end -->'.encode()
    data = {key:binding[key] for key in ('connection','bindingId','project','revision','scope','status')}
    if binding['status']=='unbound':
        original = before or b''
        if original.count(begin)!=original.count(end) or original.count(begin)>1:
            raise OnboardingError('Incomplete or duplicate owned project rule.')
        after = re.sub(rb'^'+re.escape(begin)+rb'\r?\n.*?^'+re.escape(end)+rb'\r?\n?',b'',original,flags=re.M|re.S)
    else:
        body = ('## Project Hub project binding\n\n'+json.dumps(data,ensure_ascii=False,indent=2)+
                '\nUse this canonical project and binding revision with the global MCP rules. '
                'At startup validate with hub_context; refresh on binding conflict. '
                'This rule applies only to the stated root/native project scope.\n')
        original = cursor_frontmatter(before) if host=='cursor' else before
        after = merge_block(original,body,begin=begin,end=end)
    proof = hashlib.sha256(json.dumps([str(path),hashlib.sha256(before or b'').hexdigest(),before is not None,
                                      hashlib.sha256(after).hexdigest()]).encode()).hexdigest()
    return dict(path=path,before=before,after=after,previewSha256=proof)


def apply(value, expected):
    if expected != value['previewSha256'] or read_rule(value['path'])!=value['before']:
        raise OnboardingError('Project rule changed; preview the current rule before applying.')
    from project_workspaces import no_reparse
    no_reparse(value['path'])
    if value['before']!=value['after']: atomic(value['path'],value['after'])
    return dict(rulePath=str(value['path']),changed=value['before']!=value['after'],instructionsPersisted=True,setupVerified=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',choices=('codex','cursor'),required=True)
    parser.add_argument('--binding',type=Path,required=True,help='JSON binding returned by hub_project_bindings')
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--expected-preview')
    args=parser.parse_args(argv)
    binding=json.loads(args.binding.read_text(encoding='utf-8'))
    value=plan(args.host,binding.get('binding',binding),args.workspace)
    result=apply(value,args.expected_preview) if args.apply else dict(rulePath=str(value['path']),previewSha256=value['previewSha256'],
        changed=value['before']!=value['after'],persistentRule=value['after'].decode('utf-8-sig'),setupVerified=False)
    print(json.dumps(result,ensure_ascii=False))
    return 0
