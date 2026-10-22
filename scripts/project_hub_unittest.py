"""One discovery process per selected directory, with observed test timings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import unittest

# The phase wrappers below are runner internals.  Mark this module so unittest
# removes their frames while formatting assertion tracebacks, leaving the
# actual test file and assertion line visible to callers.
__unittest = True


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timings = []

    def startTest(self, test):
        self.started = time.monotonic()
        self.phases = {name: 0.0 for name in ('setup', 'body', 'teardown', 'cleanup')}
        self._phase_wrappers = {}
        for method, phase in (('_callSetUp', 'setup'), ('_callTestMethod', 'body'),
                              ('_callTearDown', 'teardown'), ('_callCleanup', 'cleanup')):
            original = getattr(test, method, None)
            if original is None:
                continue
            self._phase_wrappers[method] = original

            def timed_call(*args, _original=original, _phase=phase, **kwargs):
                started = time.monotonic()
                try:
                    return _original(*args, **kwargs)
                finally:
                    self.phases[_phase] += time.monotonic() - started

            setattr(test, method, timed_call)
        super().startTest(test)

    def _emit_immediate_failure(self, kind, test, err):
        """Make failures diagnosable during long discovery runs."""
        details = self._exc_info_to_string(err, test).rstrip()
        print(f'\n[{kind}] {test.id()}\n{details}', file=sys.stderr, flush=True)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._emit_immediate_failure('FAIL', test, err)

    def addError(self, test, err):
        super().addError(test, err)
        self._emit_immediate_failure('ERROR', test, err)

    def stopTest(self, test):
        try:
            # Includes setup, teardown and cleanups, not just the assertion body.
            elapsed = time.monotonic() - self.started
            self.timings.append({'test': test.id(), 'seconds': round(elapsed, 6),
                                 'phases': {name: round(seconds, 6)
                                            for name, seconds in self.phases.items()}})
            super().stopTest(test)
        finally:
            for method, original in self._phase_wrappers.items():
                setattr(test, method, original)
            self._phase_wrappers = {}


def individual_tests(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from individual_tests(test)
        else:
            yield test


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--pattern', action='append')
    parser.add_argument('--timings', type=Path)
    args = parser.parse_args(argv)
    # `python -m unittest` includes cwd, whereas invoking this helper as a file
    # starts with scripts/. Preserve namespace imports such as scripts.tests.
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    previous_ids = set()
    for pattern in sorted(set(args.pattern or ['test*.py'])):
        discovered = list(individual_tests(loader.discover(args.directory, pattern=pattern)))
        # Overlapping patterns must not repeat tests. Preserve deliberate repeats
        # within a single discovery result, including full's existing load_tests.
        suite.addTests(test for test in discovered if test.id() not in previous_ids)
        previous_ids.update(test.id() for test in discovered)
    started = time.monotonic()
    result = unittest.TextTestRunner(resultclass=TimedResult).run(suite)
    record = {'schemaVersion': 1, 'seconds': round(time.monotonic() - started, 6),
              'testsRun': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped),
              'tests': sorted(result.timings, key=lambda item: item['seconds'], reverse=True)}
    if args.timings:
        args.timings.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() and result.testsRun else 1


if __name__ == '__main__':
    sys.exit(main())
