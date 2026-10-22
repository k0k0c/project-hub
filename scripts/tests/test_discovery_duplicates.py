"""Guard the test modules against imported-suite discovery regressions."""
import importlib
import unittest


def _test_ids(module_name):
    module = importlib.import_module(module_name)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    return [test.id() for test in _iter_tests(suite)]


def _iter_tests(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _iter_tests(test)
        else:
            yield test


class DiscoveryDuplicateRegressionTest(unittest.TestCase):
    def test_shared_fixture_modules_expose_only_owned_tests(self):
        expected = {
            'test_architecture_navigation_ui': ('ArchitectureNavigationUiTest', 10),
            'test_document_sources': ('DocumentSourcesTest', 6),
            'test_artifact_store': ('ArtifactStoreTest', 9),
            'test_image_http': ('ImageHttpTest', 8),
        }
        for module_name, (class_name, count) in expected.items():
            with self.subTest(module=module_name):
                ids = _test_ids(module_name)
                self.assertEqual(len(ids), count)
                self.assertTrue(all(f'{module_name}.{class_name}.' in test_id for test_id in ids), ids)


if __name__ == '__main__':
    unittest.main()
