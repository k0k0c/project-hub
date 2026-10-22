import json
from pathlib import Path
import sys
import unittest

from knowledge_lsp import LspManager


SERVER = r'''
import json,sys
def send(x):
 b=json.dumps(x).encode();sys.stdout.buffer.write(b"Content-Length: "+str(len(b)).encode()+b"\r\n\r\n"+b);sys.stdout.buffer.flush()
while True:
 h=b''
 while not h.endswith(b'\r\n\r\n'):
  c=sys.stdin.buffer.read(1)
  if not c: raise SystemExit
  h+=c
 n=int(next(x.split(b':')[1] for x in h.split(b'\r\n') if x.lower().startswith(b'content-length')))
 m=json.loads(sys.stdin.buffer.read(n)); method=m.get('method'); p=m.get('params',{})
 if method=='initialize': send({'jsonrpc':'2.0','id':m['id'],'result':{'capabilities':{'documentSymbolProvider':True,'definitionProvider':True,'referencesProvider':True,'callHierarchyProvider':True,'typeHierarchyProvider':True}}})
 elif method=='shutdown': send({'jsonrpc':'2.0','id':m['id'],'result':None})
 elif 'id' in m and method=='textDocument/documentSymbol': send({'jsonrpc':'2.0','id':m['id'],'result':[{'name':'Thing','kind':5}]})
 elif 'id' in m and method=='textDocument/prepareCallHierarchy': send({'jsonrpc':'2.0','id':m['id'],'result':[{'name':'Thing','kind':5,'uri':p['textDocument']['uri'],'range':{'start':{'line':0,'character':0},'end':{'line':0,'character':1}}}]})
 elif 'id' in m and method=='callHierarchy/incomingCalls': send({'jsonrpc':'2.0','id':m['id'],'result':[{'from':p['item']}]})
 elif 'id' in m: send({'jsonrpc':'2.0','id':m['id'],'result':[]})
'''


DIAGNOSTIC_SERVER = r'''
import json,sys
def send(x):
 b=json.dumps(x).encode();sys.stdout.buffer.write(b"Content-Length: "+str(len(b)).encode()+b"\r\n\r\n"+b);sys.stdout.buffer.flush()
def publish(uri, diagnostics):
 send({'jsonrpc':'2.0','method':'textDocument/publishDiagnostics','params':{'uri':uri,'diagnostics':diagnostics}})
mode=''
incoming={}
while True:
 h=b''
 while not h.endswith(b'\r\n\r\n'):
  c=sys.stdin.buffer.read(1)
  if not c: raise SystemExit
  h+=c
 n=int(next(x.split(b':')[1] for x in h.split(b'\r\n') if x.lower().startswith(b'content-length')))
 m=json.loads(sys.stdin.buffer.read(n)); method=m.get('method'); p=m.get('params',{})
 if method=='initialize':
  mode=(p.get('initializationOptions') or {}).get('diagnosticMode','')
  send({'jsonrpc':'2.0','id':m['id'],'result':{'capabilities':{'documentSymbolProvider':True,'callHierarchyProvider':True}}})
 elif method=='shutdown': send({'jsonrpc':'2.0','id':m['id'],'result':None})
 elif method=='textDocument/didOpen':
  uri=p.get('textDocument',{}).get('uri','')
  selected=uri.endswith('test_knowledge_lsp.py')
  warn=(mode=='selected' and selected) or (mode=='other' and not selected)
  publish(uri,[{'severity':1,'message':'non-project file; only syntax errors are reported'}] if warn else [])
 elif 'id' in m and method=='textDocument/documentSymbol':
  send({'jsonrpc':'2.0','id':m['id'],'result':[{'name':'Thing','kind':5}]})
 elif 'id' in m and method=='textDocument/prepareCallHierarchy':
  uri=p.get('textDocument',{}).get('uri','')
  send({'jsonrpc':'2.0','id':m['id'],'result':[{'name':'Thing','kind':5,'uri':uri,'range':{'start':{'line':0,'character':0},'end':{'line':0,'character':1}}}]})
 elif 'id' in m and method=='callHierarchy/incomingCalls':
  uri=(p.get('item') or {}).get('uri','')
  incoming[uri]=incoming.get(uri,0)+1
  if mode=='selected' and incoming[uri]>=2: publish(uri,[])
  send({'jsonrpc':'2.0','id':m['id'],'result':[]})
 elif 'id' in m: send({'jsonrpc':'2.0','id':m['id'],'result':[]})
'''


class KnowledgeLspTest(unittest.TestCase):
    def config(self):
        return {'command': [sys.executable, '-u', '-c', SERVER], 'languages': {'py': 'python'}}

    def test_negotiated_unsupported_capability_is_distinct(self):
        no_cap = SERVER.replace("'documentSymbolProvider':True,", "")
        manager = LspManager(timeout=1)
        try:
            config = {'command': [sys.executable, '-u', '-c', no_cap], 'languages': ['python']}
            result = manager.query(Path(__file__).resolve().parents[1], config, 'symbols', 'tests/test_knowledge_lsp.py')
            self.assertEqual(result['status'], 'unsupported')
        finally:
            manager.close()

    def test_initialize_failure_is_returned_as_bounded_error(self):
        manager = LspManager(timeout=.2)
        try:
            result = manager.query(Path(__file__).resolve().parents[1],
                                   {'command': [sys.executable, '-u', '-c', 'raise SystemExit(7)']},
                                   'symbols', 'tests/test_knowledge_lsp.py')
            self.assertEqual(result['status'], 'error')
            self.assertLessEqual(len(result['diagnostics']), 21)
        finally:
            manager.close()

    def test_framing_operations_persist_and_contain_paths(self):
        root = Path(__file__).resolve().parents[1]
        manager = LspManager(timeout=2)
        try:
            symbols = manager.query(root, self.config(), 'symbols', 'tests/test_knowledge_lsp.py')
            self.assertEqual(symbols['status'], 'ok')
            self.assertEqual(symbols['results'][0]['name'], 'Thing')
            calls = manager.query(root, self.config(), 'incoming-calls', 'tests/test_knowledge_lsp.py')
            self.assertEqual(calls['status'], 'ok')
            self.assertEqual(manager.query(root, self.config(), 'references', 'tests/test_knowledge_lsp.py')['status'], 'empty')
            outside = manager.query(root, self.config(), 'symbols', str(root.parent / 'x.py'))
            self.assertEqual(outside['status'], 'error')
        finally:
            manager.close()

    def test_call_site_selection_resolves_to_declaration_and_keeps_evidence(self):
        root=Path(__file__).resolve().parents[1]
        uri=(root/'tests/test_knowledge_lsp.py').as_uri()
        declaration={'start':{'line':1,'character':2},'end':{'line':1,'character':26}}
        selection={'start':{'line':1,'character':7},'end':{'line':1,'character':12}}
        callsite={'start':{'line':1,'character':17},'end':{'line':1,'character':23}}
        class Fake:
            def request(self,*args,**kwargs):return [{'name':'start()','kind':6,'range':declaration,'selectionRange':selection}]
        incoming=[{'from':{'name':'start() : void','kind':6,'uri':uri,'range':declaration,'selectionRange':callsite},'fromRanges':[callsite]}]
        diagnostics=[]
        LspManager()._repair_call_ranges(Fake(),root,incoming,diagnostics,2,None)
        self.assertEqual(incoming[0]['from']['selectionRange'],selection)
        self.assertEqual(incoming[0]['fromRanges'],[callsite])
        self.assertFalse(diagnostics)

    def test_unsupported_is_distinct_from_empty(self):
        manager = LspManager()
        try:
            self.assertEqual(manager.query(Path('.'), self.config(), 'nope', 'x.py')['status'], 'unsupported')
        finally:
            manager.close()

    def test_semantic_warning_marks_empty_calls_partial_and_clears_per_uri(self):
        root = Path(__file__).resolve().parents[1]
        selected = 'tests/test_knowledge_lsp.py'
        config = {'command': [sys.executable, '-u', '-c', DIAGNOSTIC_SERVER],
                  'languages': {'py': 'python'},
                  'initializationOptions': {'diagnosticMode': 'selected'}}
        manager = LspManager(timeout=2)
        try:
            first = manager.query(root, config, 'incoming-calls', selected)
            self.assertEqual(first['status'], 'partial')
            self.assertTrue(any('non-project file' in str(d) for d in first['diagnostics']))
            cleared = manager.query(root, config, 'incoming-calls', selected)
            self.assertEqual(cleared['status'], 'empty')
            self.assertFalse(any(d.get('code') == 'semantic-incomplete' for d in cleared['diagnostics']))
            self.assertEqual(manager.query(root, config, 'symbols', selected)['status'], 'ok')
        finally:
            manager.close()

    def test_unrelated_file_warning_does_not_poison_selected_empty_result(self):
        root = Path(__file__).resolve().parents[1]
        config = {'command': [sys.executable, '-u', '-c', DIAGNOSTIC_SERVER],
                  'languages': {'py': 'python'},
                  'initializationOptions': {'diagnosticMode': 'other'}}
        manager = LspManager(timeout=2)
        try:
            other = manager.query(root, config, 'symbols', 'tests/test_knowledge_ui.py')
            self.assertEqual(other['status'], 'ok')
            selected = manager.query(root, config, 'incoming-calls', 'tests/test_knowledge_lsp.py')
            self.assertEqual(selected['status'], 'empty')
            self.assertFalse(any(d.get('code') == 'semantic-incomplete' for d in selected['diagnostics']))
        finally:
            manager.close()


if __name__ == '__main__':
    unittest.main()
