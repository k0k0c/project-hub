"""Settings tests use isolated stores; no installed plugin or production data."""
import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools/project-portal/plugins/project-hub/scripts"))
from project_portal import Store
from project_settings import DEFAULT_SETTINGS, HISTORY_LIMIT, MAX_FILE_BYTES, SORTS
from project_settings import SettingsError, read_settings, update_settings


class ProjectSettingsTest(unittest.TestCase):
    def test_architecture_defaults_validation_and_old_snapshot_upgrade(self):
        value = self.update({'architecture': {'model': 'fixture-model', 'depth': 7,
                            'descriptionDetail': 'detailed', 'agentSummaries': False}})
        self.assertEqual(value['settings']['architecture']['depth'], 7)
        self.assertEqual(value['settings']['architecture']['representation'], 'symbols')
        for invalid in ({'depth': True}, {'depth': 0}, {'model': 'bad model'},
                        {'representation': 'java-only'}, {'descriptionDetail': 'article'}):
            with self.assertRaises(SettingsError):
                self.update({'architecture': invalid})
        self.update({'architecture': {'depth': 'all'}})
        self.assertEqual(read_settings(self.store)['settings']['architecture']['depth'], 'all')
        old = self.update({}, reset='architecture')
        # Legacy files and every audit snapshot predate this section. Upgrade
        # must not create a new disk revision or break their continuity.
        old['settings'].pop('architecture')
        old['history'] = [entry for entry in old['history'] if entry['sections'] != ['architecture']]
        # Use an ordinary git change to construct a valid legacy journal.
        fresh = {'git': dict(DEFAULT_SETTINGS['git']), 'tasks': dict(DEFAULT_SETTINGS['tasks']),
                 'viewer': dict(DEFAULT_SETTINGS['viewer'])}
        after = json.loads(json.dumps(fresh)); after['git']['autoCommit'] = True
        self.path.write_text(json.dumps({'settings': after, 'revision': 'legacy', 'configured': True,
            'history': [{'at': '2026-01-01T00:00:00Z', 'actor': 'fixture', 'sections': ['git'],
                         'before': fresh, 'after': after}]}), encoding='utf-8')
        upgraded = read_settings(self.store)
        self.assertEqual(upgraded['revision'], 'legacy')
        self.assertEqual(upgraded['settings']['architecture'], DEFAULT_SETTINGS['architecture'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root, data_dir=self.root / "data")
        self.path = self.store.data / "project-settings.json"

    def update(self, changes, **kwargs):
        return update_settings(self.store, changes, read_settings(self.store)["revision"], **kwargs)

    def test_missing_defaults_detached_and_not_persisted(self):
        first = read_settings(self.store)
        self.assertEqual(first["settings"], DEFAULT_SETTINGS)
        self.assertFalse(first["configured"])
        self.assertEqual(first["history"], [])
        first["settings"]["tasks"]["columns"].clear()
        self.assertEqual(read_settings(self.store)["settings"], DEFAULT_SETTINGS)
        self.assertFalse(self.path.exists())

    def test_partial_patch_history_and_reload(self):
        before = read_settings(self.store)
        result = self.update({"git": {"autoCommit": True}, "viewer": {"wrapLines": False}}, actor="fixture")
        self.assertNotEqual(result["revision"], before["revision"])
        self.assertTrue(result["configured"])
        self.assertEqual(result["settings"]["tasks"], DEFAULT_SETTINGS["tasks"])
        entry = result["history"][0]
        self.assertEqual(entry["sections"], ["git", "viewer"])
        self.assertEqual(entry["actor"], "fixture")
        self.assertEqual(entry["before"], before["settings"])
        self.assertEqual(entry["after"], result["settings"])
        self.assertEqual(read_settings(Store(self.root, data_dir=self.store.data)), result)
        self.assertFalse(self.store.journal.exists())

    def test_legacy_overview_preferences_and_history(self):
        saved = self.update({"viewer": {"wrapLines": False}})
        for settings in [saved["settings"], saved["history"][0]["before"], saved["history"][0]["after"]]:
            settings["tasks"].pop("showEpicsOnOverview", None)
            settings["tasks"].pop("showUpcomingOnOverview", None)
        self.path.write_text(json.dumps(saved), encoding="utf-8")
        raw = self.path.read_bytes()
        loaded = read_settings(self.store)
        self.assertFalse(loaded["settings"]["tasks"]["showEpicsOnOverview"])
        self.assertTrue(loaded["settings"]["tasks"]["showUpcomingOnOverview"])
        self.assertEqual(loaded["revision"], saved["revision"])
        self.assertEqual(self.path.read_bytes(), raw)
        enabled = self.update({"tasks": {"showEpicsOnOverview": True,
                                           "showUpcomingOnOverview": False}})
        self.assertTrue(read_settings(self.store)["settings"]["tasks"]["showEpicsOnOverview"])
        self.assertFalse(read_settings(self.store)["settings"]["tasks"]["showUpcomingOnOverview"])
        self.assertEqual(len(enabled["history"]), 2)
        reset = self.update(None, reset="tasks")
        self.assertFalse(reset["settings"]["tasks"]["showEpicsOnOverview"])
        self.assertTrue(reset["settings"]["tasks"]["showUpcomingOnOverview"])
        self.assertFalse(reset["settings"]["viewer"]["wrapLines"])

    def test_noop_and_stale_even_for_same_values(self):
        initial = read_settings(self.store)
        self.assertEqual(self.update({}), initial)
        self.assertFalse(self.path.exists())
        result = self.update({"git": {"autoCommit": True}})
        raw, stamp = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.assertEqual(self.update({"git": {"autoCommit": True}}), result)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(self.path.stat().st_mtime_ns, stamp)
        with self.assertRaises(SettingsError) as error:
            update_settings(self.store, {"git": {"autoCommit": True}}, initial["revision"])
        self.assertEqual(error.exception.status, 409)

    def test_reset_is_scoped_and_idempotent(self):
        self.update({"git": {"autoCommit": True}, "viewer": {"wrapLines": False}})
        result = self.update(None, reset="git")
        self.assertEqual(result["settings"]["git"], DEFAULT_SETTINGS["git"])
        self.assertFalse(result["settings"]["viewer"]["wrapLines"])
        self.assertEqual(self.update({}, reset="git"), result)
        for section in DEFAULT_SETTINGS:
            self.update(None, reset=section)
        self.assertEqual(read_settings(self.store)["settings"], DEFAULT_SETTINGS)

    def test_strict_invalid_patches_leave_file_unchanged(self):
        self.update({"viewer": {"wrapLines": False}})
        raw = self.path.read_bytes()
        invalid = [None, [], {"unknown": {}}, {"git": None}, {"git": {"extra": True}},
                   {"tasks": {"showEpicsOnOverview": "true"}},
                   {"tasks": {"showUpcomingOnOverview": "true"}},
                   {"git": {"autoCommit": 1}}, {"git": {"commitOn": "always"}},
                   {"tasks": {"showCompleted": "true"}}, {"tasks": {"sort": "estimate"}},
                   {"tasks": {"overviewSort": []}}, {"tasks": {"columns": ["status"]}},
                   {"tasks": {"columns": ["title", "title"]}},
                   {"tasks": {"columns": ["title", {}]}},
                   {"tasks": {"columns": ["title", "unknown"]}},
                   {"viewer": {"showSourceDetails": 0}}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SettingsError):
                self.update(value)
            self.assertEqual(self.path.read_bytes(), raw)
        for options in ({"reset": "unknown"}, {"reset": []}, {"actor": ""}, {"actor": "x" * 201}):
            with self.subTest(options=options), self.assertRaises(SettingsError):
                self.update({}, **options)
        with self.assertRaises(SettingsError):
            self.update({"git": {}}, reset="git")
        for expected in (None, 1, ""):
            with self.assertRaises(SettingsError):
                update_settings(self.store, {}, expected)

    def test_all_ui_sorts_columns_and_commit_modes(self):
        for sort in SORTS:
            result = self.update({"tasks": {"sort": sort, "overviewSort": sort}})
            self.assertEqual(result["settings"]["tasks"]["sort"], sort)
        for mode in ("stage", "task", "stage-and-task"):
            self.update({"git": {"commitOn": mode}})
        result = self.update({"tasks": {"columns": ["actions", "title"]}})
        self.assertEqual(result["settings"]["tasks"]["columns"], ["actions", "title"])

    def test_history_is_bounded(self):
        for number in range(HISTORY_LIMIT + 5):
            self.update({"git": {"autoCommit": number % 2 == 0}}, actor=str(number))
        result = read_settings(self.store)
        self.assertEqual(len(result["history"]), HISTORY_LIMIT)
        self.assertEqual(result["history"][0]["actor"], "5")
        self.assertLess(self.path.stat().st_size, MAX_FILE_BYTES)

    def test_corrupt_file_never_overwritten(self):
        good = self.update({"git": {"autoCommit": True}})
        bad = [b"", b"{broken", b"\xff", b"[]", b'{"settings":{},"settings":{}}',
               b" " * (MAX_FILE_BYTES + 1)]
        for field, value in (("settings", {}), ("revision", ""), ("history", []), ("configured", False)):
            bad.append(json.dumps({**good, field: value}).encode())
        inconsistent = json.loads(json.dumps(good))
        inconsistent["history"][0]["after"]["git"]["autoCommit"] = False
        bad.append(json.dumps(inconsistent).encode())
        for raw in bad:
            self.path.write_bytes(raw)
            for operation in (lambda: read_settings(self.store),
                              lambda: update_settings(self.store, {}, good["revision"]),
                              lambda: update_settings(self.store, None, good["revision"], reset="git")):
                with self.subTest(raw=raw[:40]), self.assertRaises(SettingsError) as error:
                    operation()
                self.assertEqual(error.exception.code, "corrupt_settings")
                self.assertEqual(self.path.read_bytes(), raw)

    def test_atomic_failure_preserves_file_and_cleans_temporary(self):
        self.update({"git": {"autoCommit": True}})
        raw = self.path.read_bytes()
        with patch("project_settings.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.update({"git": {"autoCommit": False}})
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(list(self.store.data.glob("project-settings.json.*")), [])

    def test_concurrent_independent_stores_reject_lost_update(self):
        revision = read_settings(self.store)["revision"]
        def change(index):
            store = Store(self.root, data_dir=self.store.data)
            try:
                update_settings(store, {"git": {"commitOn": ("stage", "task")[index]}}, revision)
                return 200
            except SettingsError as error:
                return error.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(change, range(2))), [200, 409])
        self.assertEqual(len(read_settings(self.store)["history"]), 1)

    def test_project_data_isolation(self):
        other = Store(self.root, data_dir=self.root / "other-data")
        self.update({"git": {"autoCommit": True}})
        self.assertFalse(read_settings(other)["settings"]["git"]["autoCommit"])
        self.assertFalse((other.data / "project-settings.json").exists())
