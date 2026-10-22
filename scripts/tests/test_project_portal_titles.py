import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import SessionTitles


class SessionTitleTest(unittest.TestCase):
    def test_latest_name_and_partial_append(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'index.jsonl'
            path.write_text(json.dumps(dict(id='a', thread_name='Original')) + '\n', encoding='utf-8')
            names = SessionTitles(path)
            self.assertEqual(names.get(['a']), {'a': 'Original'})
            with path.open('a', encoding='utf-8') as out:
                out.write(json.dumps(dict(id='a', thread_name='Renamed <script>')) + '\n{"id":')
            self.assertEqual(names.get(['a', 'b']), {'a': 'Renamed <script>', 'b': None})

    def test_missing_index_returns_unknown_without_inventing_title(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(SessionTitles(Path(temp) / 'missing').get(['a']), {'a': None})

    def test_unrelated_names_not_returned(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'index.jsonl'
            path.write_text(json.dumps(dict(id='other', thread_name='Other project')), encoding='utf-8')
            self.assertEqual(SessionTitles(path).get(['a']), {'a': None})
