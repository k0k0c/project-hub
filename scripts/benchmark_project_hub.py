"""Measure payload sizes and latency with isolated sessions, without model calls."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import math
import statistics
import time
import threading
import http.client
import ast
import subprocess
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/project-portal/plugins/project-hub/scripts'))
from hub_core import Hub, compact
from hub_plugin import TOOLS
sys.path.insert(0, str(ROOT / 'scripts'))
from project_registry import ProjectRegistry, CodexProjects
from project_portal import atomic_write, PortalServer
from plugin_api import ServerHub, call
from hub_plugin import Mcp
from task_transfer import barrier


def measure(operation, samples, prepare=lambda: None):
    timings, payloads = [], []
    for _ in range(samples):
        prepared = prepare()
        start = time.perf_counter_ns()
        result = operation(prepared)
        timings.append((time.perf_counter_ns() - start) / 1e6)
        payloads.append(len(compact(result).encode('utf-8')))
    ordered = sorted(timings)
    return dict(samples=samples, medianMs=statistics.median(timings),
                p95Ms=ordered[math.ceil(.95 * samples) - 1],
                medianPayloadBytes=statistics.median(payloads), maxPayloadBytes=max(payloads))


def benchmark(base, tasks, events, samples):
    project = base / 'project'
    project.mkdir(parents=True)
    catalog = base / 'catalog.json'
    catalog.write_text(json.dumps({'local-projects': {'benchmark': dict(
        id='benchmark', name='Benchmark', rootPaths=[str(project)])}}), encoding='utf-8')
    registry = ProjectRegistry(base / 'data', CodexProjects(catalog))
    pid = registry.list()['projects'][0]['id']
    store = registry.base_store(pid)
    atomic_write(store.data / 'project.json', json.dumps(dict(schemaVersion=1, id=pid,
        name='Benchmark', tasks=[dict(id='task-' + str(i), title='Example ' + str(i),
        status='active', stages=[dict(id='stage', title='Work', status='active', remaining=[])])
        for i in range(tasks)])))
    for i in range(events):
        store.record(dict(kind='decision', taskId='task-' + str(i % tasks),
                          title='Benchmark history', detail='Evidence ' + ('x' * 500)))
    session = 'benchmark-session'
    hub = ServerHub(registry, session)
    hub.ensure_session(session, str(project))
    mcp = Mcp(hub, str(project), session)
    def invoke(tool, **args):
        return call(registry, dict(cwd=str(project), session=session, tool=tool, arguments=args))
    def server_context(_):
        with barrier(registry):
            return hub.context(session)
    # The first server read includes migration/cache population. Keep it
    # separate instead of contaminating the warm distribution.
    rows = {'server.context.first': measure(server_context, 1)}
    rows['server.context.warm'] = measure(server_context, samples)
    cursor = invoke('hub_context')['cursor']
    rows['mcp.context.warm'] = measure(lambda _: mcp.call('hub_context', {}), samples)
    rows['mcp.delta.warm'] = measure(lambda _: mcp.call('hub_context', {'after': cursor}), samples)
    rows['mcp.plan.warm'] = measure(lambda _: invoke('hub_plan', task='task-0'), samples)
    rows['mcp.memory.warm'] = measure(lambda _: invoke('hub_memory', query='Evidence', task='task-0'), samples)
    def cold_context(cold):
        return call(cold, dict(cwd=str(project), session=session, tool='hub_context', arguments={}))
    rows['mcp.context.cold'] = measure(cold_context, samples,
        lambda: ProjectRegistry(registry.home, CodexProjects(registry.catalog.path)))
    rows['mcp.task.create'] = measure(lambda _: invoke('hub_task', title='Created benchmark task',
        scope=['src'], acceptance=['Verified']), samples)
    counter = iter(range(samples * 2))
    rows['mcp.task.rename'] = measure(lambda revision: invoke('hub_task_update', task='task-0',
        expected=revision, patch={'title': 'Renamed ' + str(next(counter))}), samples,
        lambda: invoke('hub_plan', task='task-0')['revision'])
    rows['mcp.task.update'] = measure(lambda revision: invoke('hub_task_update', task='task-0',
        expected=revision, patch={'scope': ['src', 'iteration-' + str(next(counter))]}), samples,
        lambda: invoke('hub_plan', task='task-0')['revision'])
    rows['mcp.comment.equivalent'] = measure(lambda revision: invoke('hub_plan', task='task-0',
        expected=revision, title='Benchmark comment', decision='Recorded benchmark observation'), samples,
        lambda: invoke('hub_plan', task='task-0')['revision'])
    reports = iter(range(samples))
    rows['mcp.report'] = measure(lambda work: invoke('hub_report', work=work['work'],
        revision=work['revision'], result='Benchmark result', status='done'), samples,
        lambda: invoke('hub_begin', task='task-0', stage='stage', title='Benchmark work ' + str(next(reports)),
                       resources=['resource:benchmark']))
    server = PortalServer(('127.0.0.1', 0), registry=registry)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def request(method, path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=30)
        try:
            connection.request(method, path, None if body is None else compact(body),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            result = json.loads(response.read())
            if response.status != 200:
                raise RuntimeError(result)
            return result
        finally:
            connection.close()
    try:
        rows['http.context.warm'] = measure(lambda _: request('POST', '/api/v1/plugin/call',
            dict(cwd=str(project), session=session, tool='hub_context', arguments={})), samples)
        rows['http.history.warm'] = measure(lambda _: request('GET',
            '/api/history?project=' + pid + '&task=task-0&limit=20'), samples)
    finally:
        server.shutdown(); server.server_close(); worker.join()
    return dict(initialTasks=tasks, initialJournalEvents=events,
        finalJournalBytes=registry.base_store(pid).journal.stat().st_size, operations=rows)


def guidance_proxy():
    """Evaluate only literal concatenation and the known session-ID substitution.

    Never import/execute the Git revision or infer model token counts from text.
    """
    relative = 'tools/project-portal/plugins/project-hub/scripts/hub_plugin.py'
    baseline = subprocess.run(['git', '-C', str(ROOT), 'show', 'HEAD:' + relative],
                              capture_output=True, check=True).stdout.decode('utf-8')
    current = (ROOT / relative).read_text(encoding='utf-8-sig')
    session = 'benchmark-session'
    def extract(source):
        tree = ast.parse(source)
        hook = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'hook')
        assignment = next(node for node in ast.walk(hook) if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == 'text' for target in node.targets))
        def literal(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add): return literal(node.left) + literal(node.right)
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                    and node.value.id == 'event' and isinstance(node.slice, ast.Constant)
                    and node.slice.value == 'session_id'): return session
            raise ValueError('Hook guidance no longer uses supported literal construction')
        text = literal(assignment.value)
        return dict(words=len(text.split()), utf8Bytes=len(text.encode('utf-8')),
                    sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())
    before, after = extract(baseline), extract(current)
    return dict(source=relative, baselineRef='HEAD', sessionSubstitution=session,
                measurement='Whitespace word count and UTF-8 bytes; proxies only, not model tokens',
                before=before, after=after,
                delta=dict(words=after['words']-before['words'], utf8Bytes=after['utf8Bytes']-before['utf8Bytes']))


def benchmark_knowledge(base, samples):
    project = base / 'project'; project.mkdir(parents=True)
    catalog = base / 'catalog.json'
    catalog.write_text(json.dumps({'local-projects': {'benchmark': dict(
        id='benchmark', name='Knowledge benchmark', rootPaths=[str(project)])}}), encoding='utf-8')
    registry = ProjectRegistry(base / 'data', CodexProjects(catalog))
    pid = registry.list()['projects'][0]['id']; session = 'benchmark-session'
    def invoke(action, args=None, selected=registry):
        return call(selected, dict(cwd=str(project), session=session, tool='hub_knowledge',
                                   arguments=dict(action=action,args=args or {})))
    binding = call(registry, dict(cwd=str(project), session=session,tool='hub_context',arguments={'session':session}))
    assert binding['project'] == pid and binding['session'] == session, 'Isolated actor binding mismatch'
    # Realistic authored articles and shallow model fixtures. These are not
    # scanned facts about the source repository and do not execute project code.
    entities = [dict(id='entity:'+str(i),kind='entity',title=('Component ' if i<3 else 'Type ')+str(i),
        type='component' if i<3 else 'file' if i<33 else 'class' if i<93 else 'interface' if i<108 else 'external',
        description='Shallow benchmark model element '+str(i),component='entity:'+str(i%3),
        entrypoint=3<=i<9,provenance='authored') for i in range(120)]
    relations = [dict(id='relation:'+str(i),kind='relation',**{'from':'entity:'+str(i),'to':'entity:'+str((i+1)%120)},
        type='depends-on' if i<3 else 'uses' if i%2 else 'extends',provenance='authored',
        description='Benchmark relation '+str(i)) for i in range(120)]
    paragraph = ('This article describes a project workflow, its inputs, verification, failure handling, '
                 'and related architecture. Use the linked model to understand the local responsibility.\n\n')
    documents = [dict(id='doc:'+str(i),kind='document',title='Workflow article '+str(i),
        type=['tutorial','how-to','reference','explanation'][i%4],audience='developer' if i%2 else 'user',
        section='Workflows',status='current',visibility='internal',entityRefs=['entity:'+str(i%120)],
        markdown='# Workflow '+str(i)+'\n\n'+paragraph*12) for i in range(200)]
    items=entities+relations+documents
    receipt=invoke('changeset',dict(expected=invoke('context')['revision'],key='knowledge-fixture',
        operations=[dict(op='put',item=item) for item in items],reason='Seed disposable benchmark fixtures'))
    assert receipt['changed']==440
    # Contract checks run against the same isolated fixture before timing.
    listing=invoke('search',dict(kind='document',query='Workflow',limit=25))
    assert len(listing['items'])==25 and listing['more'] and listing['next']==25
    assert all('markdown' not in item for item in listing['items']), 'Search must omit full articles'
    assert invoke('read',dict(id='doc:0'))['markdown']==documents[0]['markdown']
    operations={}
    def cold(): return ProjectRegistry(registry.home, CodexProjects(catalog))
    for action,args in [('context',{}),('search',dict(kind='document',query='Workflow',limit=25)),('read',dict(id='doc:0'))]:
        invoke(action,args)  # Explicitly prime the retained registry before warm samples.
        operations['mcp.knowledge.'+action+'.warm']=measure(lambda _,a=action,q=args:invoke(a,q),samples)
        operations['mcp.knowledge.'+action+'.cold']=measure(lambda r,a=action,q=args:invoke(a,q,r),samples,cold)
    counter=iter(range(samples))
    def change(expected):
        index=next(counter)
        item=dict(documents[0],title='Workflow article 0 revision '+str(index))
        result=invoke('changeset',dict(expected=expected,key='benchmark-edit-'+str(index),
            operations=[dict(op='put',item=item)],reason='Benchmark article title edit '+str(index)))
        assert result['revision']==expected+1 and result['changed']==1
        return result
    operations['mcp.knowledge.changeset.warm']=measure(change,samples,lambda:invoke('context')['revision'])
    final=invoke('context')
    assert final['counts']==dict(document=200,entity=120,relation=120)
    assert final['revision']==receipt['revision']+samples
    return dict(documents=200,entities=120,relations=120,fixtureUtf8Bytes=len(compact(items).encode()),
        articleUtf8Bytes=len(documents[0]['markdown'].encode()),finalRevision=final['revision'],operations=operations,
        contractChecks=['actor/project binding','search limit/pagination','search omits Markdown',
                        'read preserves article','fresh knowledge revision per mutation','exact counts/final revision'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=9)
    parser.add_argument('--large-events', type=int, default=500)
    parser.add_argument('--knowledge-only', action='store_true', help='Measure isolated knowledge operations and guidance proxies only')
    args = parser.parse_args()
    if args.samples < 1 or args.large_events < 1:
        parser.error('samples and large-events must be positive')
    if args.knowledge_only:
        with tempfile.TemporaryDirectory(prefix='hub-knowledge-benchmark-') as temp:
            result=dict(measurement='perf_counter_ns wall latency and compact UTF-8 response bytes',samples=args.samples,
                cold='fresh registry cache; construction excluded; filesystem/OS caches remain warm',
                warm='same registry; warm-up and fresh expected-revision preparation excluded',
                p95='nearest rank, descriptive samples rather than an SLA',modelCalls=0,liveProjectWrites=0,
                knowledge=benchmark_knowledge(Path(temp),args.samples),hookGuidance=guidance_proxy())
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
        return
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / 'project'
        data = project / 'docs/project-portal'
        data.mkdir(parents=True)
        (data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id='benchmark',
            name='Isolated benchmark', tasks=[dict(id='task', title='Example', status='active', stages=[])])))
        hub = Hub(Path(temp) / 'hub')
        hub.register(project)
        for index in range(100):
            sid = 'session-' + str(index)
            hub.lifecycle(dict(session_id=sid, cwd=str(project), hook_event_name='SessionStart'), 'start-' + sid)
            hub.begin(sid, 'task', 'Independent step ' + str(index), ['src/segment-' + str(index)])
        initial = hub.context('session-0')
        empty = hub.context('session-0', after=initial['cursor'])
        cursor, seen, pages, largest = 0, set(), 0, 0
        while True:
            delta = hub.context('session-0', after=cursor)
            largest = max(largest, len(compact(delta).encode()))
            seen.update(row['seq'] for row in delta['changes'])
            pages += 1
            cursor = delta['cursor']
            if not delta['more']:
                break
        assert len(seen) == 200, 'Pagination lost events'
        assert initial['more'], 'Truncation must be explicit'
        assert not empty['changes']
        result = dict(sessions=100, independentWork=100, eventsRead=len(seen), deltaPages=pages,
                      initialContextBytes=len(compact(initial).encode()), unchangedDeltaBytes=len(compact(empty).encode()),
                      largestDeltaBytes=largest, toolSchemaBytes=len(compact(TOOLS).encode()),
                      modelCalls=0, liveProjectWrites=0,
                      measurement='UTF-8 payload bytes, not tokens or measured end-to-end savings')
        result['latency'] = dict(measurement='perf_counter_ns wall latency and compact UTF-8 bytes',
            cold='fresh registry cache; construction and fixture setup excluded',
            warm='same registry; fresh revision/work preparation excluded from mutation timing',
            p95='nearest-rank; descriptive measurements, not an SLA',
            workloads={'small': benchmark(Path(temp)/'small', 5, 20, args.samples),
                       'large': benchmark(Path(temp)/'large', 100, args.large_events, args.samples)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
