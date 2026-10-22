"""Request identity and diagnostic boundaries on disposable HTTP servers."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import PortalServer, Store
from request_metrics import RequestMetrics, measure


class RequestMetricsTests(unittest.TestCase):
    def test_server_default_poll_interval_is_shutdown_friendly(self):
        with tempfile.TemporaryDirectory() as temporary:
            server = PortalServer(('127.0.0.1', 0), Store(Path(temporary), data_dir=Path(temporary) / 'data'))
            try:
                with patch('socketserver.BaseServer.serve_forever', return_value=None) as serve:
                    server.serve_forever()
                serve.assert_called_once_with(poll_interval=.05)
            finally:
                server.server_close()

    def test_nested_binding_and_error_restore_the_outer_request(self):
        outer, inner = RequestMetrics('outer'), RequestMetrics('inner')
        with outer.bind():
            with measure('before'):
                pass
            with self.assertRaises(ValueError):
                with inner.bind(), measure('inner'):
                    raise ValueError('test')
            with measure('after'):
                pass
        self.assertEqual({'before', 'after'}, set(outer.durations))
        self.assertEqual({'inner'}, set(inner.durations))

    def test_request_state_is_separate_in_parallel_workers(self):
        def request(index):
            metrics = RequestMetrics(str(index))
            with metrics.bind(), measure('only_' + str(index)):
                pass
            return metrics.durations
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            rows = list(executor.map(request, range(20)))
        for index, row in enumerate(rows):
            self.assertEqual({'only_' + str(index)}, set(row))

    def test_invalid_identifiers_are_replaced(self):
        for value in ('bad\r\nInjected: true', 'x' * 65, None):
            self.assertRegex(RequestMetrics(value).identifier, r'^[0-9a-f]{32}$')

    def test_http_health_identifies_runtime_and_propagates_request_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = PortalServer(('127.0.0.1', 0), Store(root, data_dir=root / 'data'))
            worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
            worker.start()
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request('GET', '/api/health', headers={'X-Request-ID': 'test-request'})
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(200, response.status)
                self.assertEqual('test-request', response.getheader('X-Request-ID'))
                self.assertIn('serialization;dur=', response.getheader('Server-Timing'))
                self.assertIn('total;dur=', response.getheader('Server-Timing'))
                self.assertRegex(body['runtimeVersion'], r'^[0-9a-f]{64}$')
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)
