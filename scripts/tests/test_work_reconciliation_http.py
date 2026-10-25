"""Local user confirmation and project boundaries on disposable HTTP servers."""
import http.client
import json
import threading
import unittest

import test_work_reconciliation as fixtures
from project_portal import PortalServer


class WorkReconciliationHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.WorkReconciliationTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.server = PortalServer(('127.0.0.1', 0), registry=self.fixture.registry)
        worker = threading.Thread(target=self.server.serve_forever, kwargs=dict(poll_interval=.05), daemon=True)
        worker.start()
        def stop():
            self.server.shutdown(); self.server.server_close(); worker.join()
        self.addCleanup(stop)

    def request(self, path, body=None, origin=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            headers = {'Content-Type': 'application/json'}
            if origin: headers['Origin'] = origin
            connection.request('POST' if body else 'GET', path, json.dumps(body) if body else None, headers)
            response = connection.getresponse()
            content = response.read()
            return response.status, json.loads(content) if response.getheader('Content-Type', '').startswith('application/json') else content
        finally:
            connection.close()

    def test_active_interruption_needs_local_confirmation_and_current_revision(self):
        f = self.fixture
        started = f.start()
        route = '/api/work-reconciliation?project=' + f.project + '&task=' + f.task
        status, data = self.request(route)
        self.assertEqual(status, 200, data)
        work = data['work'][0]
        body = dict(work=work['id'], revision=work['revision'], owner=work['session'], observedStatus='active',
                    status='cancelled', reason='User agreed to stop this contribution', result='Cancelled by user',
                    interruptActive=False, confirmed=work['id']+':'+str(work['revision']))
        mutation = '/api/v1/work-reconciliation?project=' + f.project
        self.assertEqual(self.request(mutation, body, 'https://example.invalid')[0], 403)
        self.assertEqual(self.request(mutation, body)[1]['error'], 'work_active')
        body['interruptActive'] = True
        f.invoke(f.first, 'hub_report', work=started['work'], revision=started['revision'], result='Owner still working', status='active')
        self.assertEqual(self.request(mutation, body)[1]['error'], 'revision_conflict')
        current = self.request(route)[1]['work'][0]
        body.update(revision=current['revision'], confirmed=current['id']+':'+str(current['revision']))
        body['confirmed'] = 'not-the-observed-work'
        self.assertEqual(self.request(mutation, body)[1]['error'], 'confirmation_required')
        body['confirmed'] = current['id']+':'+str(current['revision'])
        status, saved = self.request(mutation, body)
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved['planSync'], 'saved')
        self.assertEqual(self.request(mutation, body), (status, saved))
        self.assertEqual(self.request(route)[1]['work'], [])
        with f.registry.coordination_connect() as c:
            event = c.execute('SELECT session,body FROM events WHERE seq=?', (saved['revision'],)).fetchone()
            self.assertTrue(event['session'].startswith('local-user:work-reconciliation:'))
            self.assertTrue(json.loads(event['body'])['reconciliation']['userAction'])

    def test_user_route_refuses_another_project_and_serves_dialog_asset(self):
        f = self.fixture
        work = f.waiting()
        other = f.registry.create('Other project')['id']
        self.assertNotEqual(self.request('/api/work-reconciliation?project='+other+'&task='+f.task)[0], 200)
        body = dict(work=work['id'], revision=work['revision'], owner=work['session'], observedStatus='waiting',
                    status='done', reason='Accepted', result='Accepted', interruptActive=False,
                    confirmed=work['id']+':'+str(work['revision']))
        self.assertEqual(self.request('/api/v1/work-reconciliation?project='+other, body)[1]['error'], 'work_project_mismatch')
        self.assertEqual(f.row(work['id'])['status'], 'waiting')
        status, source = self.request('/work-reconciliation.js')
        self.assertEqual(status, 200)
        self.assertIn(b'interruptActive', source)


if __name__ == '__main__':
    unittest.main()
