"""Discovery contracts are checked against backend action matrices, without live data."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent / 'tools/project-portal/plugins/project-hub/scripts'))
from agent_contracts import api_reference, enrich_tools, knowledge_actions
from hub_plugin import TOOLS

try:
    import jsonschema
except ImportError:
    jsonschema = None


def declarations():
    """Use real base declarations and extract runtime additions without runtime IO."""
    module = ast.parse((SCRIPTS / 'agent_runtime.py').read_text(encoding='utf-8'))
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'tools')
    namespace = dict(deepcopy=deepcopy, TOOLS=TOOLS, enrich_tools=enrich_tools)
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<runtime-tools>', 'exec'), namespace)
    return namespace['tools']()


class AgentContractsTest(unittest.TestCase):
    def setUp(self):
        self.original = declarations()
        self.tools = enrich_tools(self.original)
        self.schemas = {tool['name']: tool['inputSchema'] for tool in self.tools}

    def test_knowledge_matrix_matches_authoritative_validator(self):
        module = ast.parse((SCRIPTS / 'knowledge_store.py').read_text(encoding='utf-8'))
        execute = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'execute')
        matrices = {}
        for node in execute.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('allowed', 'required'):
                matrices[node.targets[0].id] = eval(compile(ast.Expression(node.value), '<matrix>', 'eval'), {'set': set})
        exposed = next(tool for tool in TOOLS if tool['name'] == 'hub_knowledge')['inputSchema']['properties']['action']['enum']
        actions = knowledge_actions()
        self.assertEqual(set(exposed), set(actions))
        self.assertEqual(len(actions), 24)
        for action, schema in actions.items():
            with self.subTest(action=action):
                self.assertEqual(set(schema['properties']), matrices['allowed'][action])
                self.assertEqual(set(schema.get('required', [])), matrices['required'].get(action, set()))
                self.assertFalse(schema['additionalProperties'])

    def test_independent_copy_and_complete_reference(self):
        before = deepcopy(self.original)
        self.tools[0]['description'] = 'mutated'
        self.assertEqual(self.original, before)
        reference = api_reference(self.original)
        for tool in self.original:
            self.assertIn('## ' + tool['name'] + '\n', reference)
        for action in knowledge_actions():
            self.assertIn('"' + action + '"', reference)
        self.assertNotIn('"$ref"', reference)
        self.assertIn('sourceProject',self.schemas['hub_task_update']['properties']['patch']['properties']['sources']['items']['properties'])
        for tool in enrich_tools(self.original):
            self.assertEqual(tool['inputSchema']['type'], 'object')
            if tool['name'] in ('hub_knowledge','hub_task_update','hub_review','hub_connection','hub_project_bindings','hub_launch'):
                self.assertNotIn('oneOf', tool['inputSchema'])
            if jsonschema:
                jsonschema.Draft202012Validator.check_schema(tool['inputSchema'])
        # Idempotence supports generators receiving already enriched runtime tools.
        self.assertEqual(enrich_tools(self.original), enrich_tools(enrich_tools(self.original)))

    @unittest.skipUnless(jsonschema, 'jsonschema unavailable; matrix and structure checks remain active')
    def test_action_dependent_examples(self):
        def valid(name, body, expected=True):
            body = dict(session='schema-test', **body)
            errors = list(jsonschema.Draft202012Validator(self.schemas[name]).iter_errors(body))
            self.assertEqual(not errors, expected, '; '.join(error.message for error in errors))
        valid('hub_knowledge', dict(action='context'))
        valid('hub_knowledge', dict(action='read', args={'id': 'guide'}))
        valid('hub_knowledge', dict(action='read'), False)
        valid('hub_knowledge', dict(action='read', args={'id': 'guide', 'query': 'extra'}), False)
        valid('hub_knowledge', dict(action='changeset', args=dict(expected=1, key='change-1', reason='Write guide',
            operations=[dict(op='put', item=dict(id='guide', kind='document', title='Guide', markdown='Text'))])))
        valid('hub_knowledge', dict(action='changeset', args=dict(expected=1, key='change-1', reason='Delete',
            operations=[dict(op='delete')])), False)
        valid('hub_knowledge', dict(action='research', args=dict(query=dict(operation='path', id='a'))), False)
        valid('hub_project_bindings', dict(action='resolve', scope=dict(kind='workspace', root='/work/project'), requestId='a' * 32))
        valid('hub_project_bindings', dict(action='update', bindingId='b', requestId='a' * 32), False)
        valid('hub_project_bindings', dict(action='verify', bindingId='b', requestId='a' * 32, expectedRevision=1, status='manual'))
        valid('hub_connection', dict(action='describe', profile=dict(schemaVersion=1, capabilities=dict(createChat=False))))
        valid('hub_connection', dict(action='describe'), False)
        valid('hub_task_update', dict(task='t', expected=1, patch=dict(sources=[dict(path='docs/design.md', label='Design')], type='epic')))
        valid('hub_task_update', dict(task='t', expected=1, patch=dict(unknown=True)), False)
        proposal = dict(task='t', decision='current', reason='Still required', confidence='high', evidence=['git:' + 'a' * 40], expectedState='a' * 64)
        valid('hub_review', dict(action='propose', actionId='action', work='w', expected=1, proposals=[proposal]))
        valid('hub_review', dict(action='propose', actionId='action', work='w', expected=1, proposals=[dict(proposal, decision='done')]), False)
        valid('hub_review', dict(action='estimate', actionId='action', work='w', expected=1, estimates=[dict(task='t', stage=None,
            expectedState='a' * 64, estimate=dict(confidence='unknown', note='Needs investigation'))]))
        valid('hub_launch', dict(action='ack', requestId='r', nativeId='chat', projectScope=dict(kind='project', nativeRef='ref')))
        valid('hub_launch', dict(action='ack', requestId='r', nativeId='chat'), False)
        valid('hub_launch', dict(action='complete', requestId='r', nativeId='chat', work='w', revision=1))
        valid('hub_launch', dict(action='complete', requestId='r', nativeId='chat', result=dict(title='Result', markdown='Findings')))
        valid('hub_launch', dict(action='fail', requestId='r', nativeId='chat', result=dict(title='Result', markdown='Findings')), False)


if __name__ == '__main__':
    unittest.main()
