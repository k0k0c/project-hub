"""Durable advisory notice contracts in isolated existing Hub databases."""
import concurrent.futures
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools/project-portal/plugins/project-hub/scripts'))
from project_portal import Store
from hub_core import Hub, HubError
from hub_memory import Memory
import hub_notices


class HubNoticesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projects = {}
        self.root = self.project('notices-test')
        self.hub = Hub(Path(self.tmp.name) / 'shared')
        self.hub.register(self.root)
        self.hub.store_factory = self.store_for_project
        for session in ('a', 'b', 'c'):
            self.hub.ensure_session(session, self.root)
        self.memory = Memory(self.hub, 'a')
        for task in ('task', 'other'):
            self.memory.plan(task, stage='work', title='Work', remaining=['Verify'])

    def project(self, name):
        root = Path(self.tmp.name) / name
        data = root / 'docs/project-portal'
        data.mkdir(parents=True)
        (data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id=name, name=name,
            tasks=[dict(id=task, title=task, status='active', stages=[]) for task in ('task', 'other')])), encoding='utf-8')
        external = Path(self.tmp.name) / (name + '-data')
        shutil.copytree(data, external)
        self.projects[name] = (root, external)
        return root

    def store_for_project(self, project):
        root, data = self.projects[project]
        return Store(root, data_dir=data, coordination_home=self.hub.home)

    def begin(self, session='a', resources=None, task='task', mode='write', title=None):
        return self.hub.begin(session, task, title or 'Work ' + session,
                              resources or ['src/core'], mode=mode, stage='work')

    def report(self, session, work, status='active', result='Progress'):
        with self.hub.connect() as c:
            revision = c.execute('SELECT revision FROM work WHERE id=?', (work['work'],)).fetchone()[0]
        return self.hub.report(session, work['work'], revision, result, status=status)

    def queue_count(self, session='a'):
        hub_notices.setup(self.hub)
        with self.hub.connect() as c:
            return c.execute('SELECT COUNT(*) FROM parallel_notices WHERE session=?', (session,)).fetchone()[0]

    def test_read_read_silence_path_writes_and_named_resources(self):
        own = self.begin(mode='read')
        foreign = self.begin('b', ['src/core/Node.py'], task='other', mode='read')
        self.assertEqual(hub_notices.notices(self.hub, 'a')['notices'], [])
        self.begin('c', ['src/core2'], task='other')
        self.assertEqual(hub_notices.notices(self.hub, 'a')['notices'], [])
        writer = self.begin('b', ['src/core'], task='other', title='Writer')
        notice = hub_notices.notices(self.hub, 'a')['notices'][0]
        self.assertEqual(notice['work'], writer['work'])
        self.assertEqual(notice['targetWork'], own['work'])
        self.assertEqual(notice['reason'], 'resource_overlap')
        self.assertEqual(notice['stage'], 'work')
        self.assertEqual(notice['relevantResources'], ['src/core'])
        self.assertEqual(notice['resources'], [dict(name='src/core', mode='write')])
        self.assertNotEqual(notice['work'], foreign['work'])
        self.begin('a', ['resource:device'], mode='read', title='Device read')
        self.begin('b', ['resource:device'], task='other', mode='read', title='Other device read')
        self.assertEqual(len(hub_notices.notices(self.hub, 'a')['notices']), 1)
        shared = self.begin('c', ['resource:device'], task='other', title='Device writer')
        current = hub_notices.notices(self.hub, 'a')['notices']
        self.assertIn(shared['work'], [notice['work'] for notice in current])

    def test_same_task_separate_scopes_exclude_own_session_and_other_project(self):
        self.begin(resources=['src/core'], mode='read')
        self.begin(resources=['src/ui'], title='Own separate work')
        foreign = self.begin('b', ['docs/review'], mode='read')
        other_root = self.project('other-project')
        self.hub.register(other_root)
        self.hub.ensure_session('other-session', other_root)
        self.hub.begin('other-session', 'task', 'Other project', ['src/core'])
        response = hub_notices.notices(self.hub, 'a')
        self.assertEqual([notice['work'] for notice in response['notices']], [foreign['work']])
        self.assertEqual(response['notices'][0]['reason'], 'same_task')
        self.assertEqual(response['notices'][0]['relevantResources'], [])
        self.assertEqual(response['notices'][0]['session'], 'b')
        self.assertEqual(response['notices'][0]['targetSession'], 'a')

    def test_report_dedup_scope_status_change_and_stale_owner_unknown(self):
        self.begin()
        foreign = self.begin('b', ['src/ui'])
        first = hub_notices.notices(self.hub, 'a')
        before = self.queue_count()
        self.report('b', foreign, result='Changed report text')
        hub_notices.refresh_all(self.hub)
        repeated = hub_notices.notices(self.hub, 'a')
        self.assertEqual(self.queue_count(), before)
        self.assertEqual(first['cursor'], repeated['cursor'])
        self.report('b', foreign, status='waiting')
        hub_notices.refresh_all(self.hub)
        waiting = hub_notices.wait(self.hub, 'a', first['cursor'], timeout=0)
        self.assertEqual(len(waiting['notices']), 1)
        self.assertEqual(waiting['notices'][0]['status'], 'waiting')
        self.assertGreater(waiting['cursor'], first['cursor'])
        self.begin(resources=['docs'], title='Additional own scope')
        changed = hub_notices.notices(self.hub, 'a')
        self.assertGreater(changed['cursor'], waiting['cursor'])
        before = self.queue_count()
        with self.hub.transaction() as c:
            c.execute('UPDATE sessions SET seen=? WHERE id=?', (time.time() - 3600, 'b'))
        stale = hub_notices.notices(self.hub, 'a')['notices'][0]
        self.assertEqual(stale['freshness']['state'], 'stale')
        self.assertEqual(stale['activity'], 'unknown')
        self.assertFalse(stale['runningVerified'])
        self.assertEqual(self.queue_count(), before, 'owner observations must not duplicate notices')
        # Existing claim data changing changes the signature, independently of
        # result text. Production scope registration stays with Hub.begin.
        with self.hub.transaction() as c:
            c.execute('UPDATE claims SET name=? WHERE work=?', ('docs/updated', foreign['work']))
        scoped = hub_notices.notices(self.hub, 'a')
        self.assertGreater(scoped['cursor'], changed['cursor'])

    def test_closed_resolution_once_and_history_retained(self):
        own = self.begin()
        foreign = self.begin('b', ['src/ui'])
        first = hub_notices.notices(self.hub, 'a')
        self.report('b', foreign, status='waiting')
        hub_notices.notices(self.hub, 'a')
        self.report('b', foreign, status='done')
        hub_notices.refresh_all(self.hub)
        self.assertEqual(hub_notices.notices(self.hub, 'a')['notices'], [])
        page = hub_notices.wait(self.hub, 'a', first['cursor'], timeout=0)
        resolved = [notice for notice in page['notices'] if notice['kind'] == 'resolved']
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]['work'], foreign['work'])
        self.assertEqual(resolved[0]['status'], 'done')
        count = self.queue_count()
        hub_notices.refresh_all(self.hub)
        self.assertEqual(self.queue_count(), count)
        self.assertEqual(hub_notices.wait(self.hub, 'a', page['cursor'], timeout=0)['notices'], [])
        with self.hub.connect() as c:
            self.assertEqual(c.execute('SELECT status FROM work WHERE id=?', (own['work'],)).fetchone()[0], 'active')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM claims WHERE work=?', (foreign['work'],)).fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT status FROM work WHERE id=?', (foreign['work'],)).fetchone()[0], 'done')

    def test_durable_paging_retry_and_independent_cursor(self):
        self.begin()
        for index in range(11):
            self.begin('b', ['src/' + str(index)], title='Foreign ' + str(index))
        first = hub_notices.wait(self.hub, 'a', 0, timeout=0)
        self.assertGreater(len(first['notices']), 0)
        self.assertLessEqual(len(first['notices']), 8)
        self.assertLessEqual(len(json.dumps(first, ensure_ascii=False, separators=(',', ':')).encode('utf-8')), 3000)
        self.assertTrue(first['more'])
        self.assertEqual(first['moreCursor'], first['cursor'])
        again = hub_notices.wait(Hub(self.hub.home), 'a', 0, timeout=0)
        immutable = ('id', 'work', 'status', 'observedAt', 'kind', 'reason', 'resolves')
        self.assertEqual([{key: item[key] for key in immutable if key in item} for item in first['notices']],
                         [{key: item[key] for key in immutable if key in item} for item in again['notices']],
                         'durable retries preserve event facts/IDs while liveness is recalculated')
        delivered = [notice['id'] for notice in first['notices']]
        page = first
        while page['queueMore']:
            page = hub_notices.wait(self.hub, 'a', page['cursor'], timeout=0)
            self.assertGreater(len(page['notices']), 0)
            self.assertEqual(page['cursor'], page['notices'][-1]['id'])
            self.assertLessEqual(len(json.dumps(page, ensure_ascii=False, separators=(',', ':')).encode('utf-8')), 3000)
            delivered.extend(notice['id'] for notice in page['notices'])
        self.assertEqual(len(delivered), 11)
        self.assertEqual(len(set(delivered)), 11)
        with self.hub.connect() as c:
            self.assertEqual(c.execute('SELECT last_cursor FROM sessions WHERE id=?', ('a',)).fetchone()[0], 0)

    def test_delayed_closed_work_replay_is_current_even_before_backlogged_resolution(self):
        self.begin()
        foreign = [self.begin('b', ['src/' + str(index)], title='Backlog ' + str(index)) for index in range(11)]
        observed = time.time()
        with self.hub.transaction() as c:
            c.execute('UPDATE sessions SET seen=? WHERE id=?', (observed, 'b'))
        with patch.object(hub_notices.time, 'time', return_value=observed):
            hub_notices.notices(self.hub, 'a')
        with self.hub.connect() as c:
            original = c.execute('SELECT seq,payload,created FROM parallel_notices WHERE session=? ORDER BY seq LIMIT 1', ('a',)).fetchone()
        stored = json.loads(original['payload'])
        self.assertEqual(stored['status'], 'active')
        self.assertEqual(stored['freshness']['state'], 'fresh')
        self.report('b', foreign[0], status='done')
        # Reporting can update owner observations. Make the delivered liveness
        # deliberately stale; no queue mutation or timestamp normalization.
        with self.hub.transaction() as c:
            c.execute('UPDATE sessions SET seen=? WHERE id=?', (observed, 'b'))
        with patch.object(hub_notices.time, 'time', return_value=observed + 900):
            first = hub_notices.wait(self.hub, 'a', 0, timeout=0)
            self.assertTrue(first['queueMore'])
            self.assertFalse(any(item['kind'] == 'resolved' for item in first['notices']))
            old_event = next(item for item in first['notices'] if item['work'] == foreign[0]['work'])
            self.assertEqual(old_event['id'], original['seq'])
            self.assertEqual(old_event['status'], 'active', 'event status remains historical')
            self.assertEqual(old_event['observedAt'], original['created'])
            self.assertEqual(old_event['currentStatus'], 'done')
            self.assertEqual(old_event['ownerSeen'], observed)
            self.assertEqual(old_event['freshness'], {'state': 'stale', 'ageSeconds': 900.0})
            self.assertEqual(old_event['activity'], 'closed')
            self.assertFalse(old_event['runningVerified'])
            delivered = list(first['notices'])
            page = first
            while page['queueMore']:
                page = hub_notices.wait(self.hub, 'a', page['cursor'], timeout=0)
                self.assertGreater(len(page['notices']), 0)
                self.assertGreater(page['cursor'], delivered[-1]['id'])
                self.assertLessEqual(len(json.dumps(page, ensure_ascii=False, separators=(',', ':')).encode('utf-8')), 3000)
                delivered.extend(page['notices'])
        resolutions = [item for item in delivered if item['kind'] == 'resolved']
        self.assertEqual(len(resolutions), 1)
        self.assertEqual(resolutions[0]['status'], 'done')
        self.assertEqual(resolutions[0]['currentStatus'], 'done')
        self.assertEqual(resolutions[0]['activity'], 'closed')
        self.assertEqual(len({item['id'] for item in delivered}), 12)
        self.assertEqual(self.queue_count(), 12)
        with self.hub.connect() as c:
            payload = c.execute('SELECT payload FROM parallel_notices WHERE seq=?', (original['seq'],)).fetchone()[0]
        self.assertEqual(payload, original['payload'], 'delivery must not rewrite immutable queued facts')

    def test_delayed_replay_recalculates_age_from_current_owner_observation(self):
        self.begin()
        self.begin('b', ['src/ui'])
        observed = time.time()
        with self.hub.transaction() as c:
            c.execute('UPDATE sessions SET seen=? WHERE id=?', (observed, 'b'))
        with patch.object(hub_notices.time, 'time', return_value=observed):
            initial = hub_notices.wait(self.hub, 'a', 0, timeout=0)['notices'][0]
        count = self.queue_count()
        with patch.object(hub_notices.time, 'time', return_value=observed + 900):
            stale = hub_notices.wait(self.hub, 'a', 0, timeout=0)['notices'][0]
        self.assertEqual(stale['freshness'], {'state': 'stale', 'ageSeconds': 900.0})
        self.assertEqual(stale['activity'], 'unknown')
        self.assertEqual(stale['currentStatus'], 'active')
        with self.hub.transaction() as c:
            c.execute('UPDATE sessions SET seen=? WHERE id=?', (observed + 901, 'b'))
        with patch.object(hub_notices.time, 'time', return_value=observed + 902):
            refreshed = hub_notices.wait(self.hub, 'a', 0, timeout=0)['notices'][0]
        self.assertEqual(refreshed['ownerSeen'], observed + 901)
        self.assertEqual(refreshed['freshness'], {'state': 'fresh', 'ageSeconds': 1.0})
        self.assertEqual(refreshed['activity'], 'declared-unfinished')
        self.assertFalse(refreshed['runningVerified'])
        for item in (stale, refreshed):
            self.assertEqual((item['id'], item['status'], item['observedAt']),
                             (initial['id'], initial['status'], initial['observedAt']))
        self.assertEqual(self.queue_count(), count, 'liveness changes do not duplicate event notices')

    def test_status_cycle_is_a_new_transition_but_same_state_report_dedupes(self):
        self.begin()
        foreign = self.begin('b', ['src/ui'])
        first = hub_notices.notices(self.hub, 'a')
        self.report('b', foreign, status='waiting')
        waiting = hub_notices.notices(self.hub, 'a')
        self.report('b', foreign, status='active')
        active = hub_notices.notices(self.hub, 'a')
        self.assertGreater(waiting['cursor'], first['cursor'])
        self.assertGreater(active['cursor'], waiting['cursor'])
        replay = hub_notices.wait(self.hub, 'a', waiting['cursor'], timeout=0)
        self.assertEqual([notice['status'] for notice in replay['notices']], ['active'])
        count = self.queue_count()
        self.report('b', foreign, status='active', result='More detail at the same state')
        repeated = hub_notices.notices(self.hub, 'a')
        self.assertEqual(repeated['cursor'], active['cursor'])
        self.assertEqual(self.queue_count(), count)

    def test_dependency_relevance_is_declared_and_coverage_unknown_without_map(self):
        self.begin(resources=['src/core'], mode='read')
        foreign = self.begin('b', ['docs'], task='other', mode='read')
        unknown = hub_notices.notices(self.hub, 'a')
        self.assertEqual(unknown['notices'], [])
        self.assertEqual(unknown['coverage']['dependencyCoverage'], 'unknown')
        dependencies = {'task': ['other']}
        response = hub_notices.notices(self.hub, 'a', dependencies=dependencies)
        self.assertEqual([notice['work'] for notice in response['notices']], [foreign['work']])
        self.assertEqual(response['notices'][0]['reason'], 'task_dependency')
        self.assertEqual(response['coverage']['dependencyCoverage'], 'declared')
        # The other side sees the same declared dependency, without requiring
        # matching resources or read/write contention.
        hub_notices.refresh_all(self.hub, dependency_maps={'notices-test': dependencies})
        other = hub_notices.notices(self.hub, 'b', dependencies=dependencies)
        self.assertEqual(other['notices'][0]['reason'], 'task_dependency')

    def test_semantic_column_upgrade_preserves_existing_queue_and_claims(self):
        self.begin()
        foreign = self.begin('b', ['src/ui'])
        first = hub_notices.notices(self.hub, 'a')
        count = self.queue_count()
        with self.hub.transaction() as c:
            c.execute('''CREATE TABLE notice_legacy (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL, project TEXT NOT NULL,
                fingerprint TEXT NOT NULL, foreign_work TEXT NOT NULL, kind TEXT NOT NULL,
                payload TEXT NOT NULL, created REAL NOT NULL, closed INTEGER NOT NULL DEFAULT 0,
                UNIQUE(session,project,fingerprint))''')
            c.execute('''INSERT INTO notice_legacy
                SELECT seq,session,project,semantic,foreign_work,kind,payload,created,closed FROM parallel_notices''')
            c.execute('DROP TABLE parallel_notices')
            c.execute('ALTER TABLE notice_legacy RENAME TO parallel_notices')
        hub_notices.setup(self.hub)
        migrated = hub_notices.notices(self.hub, 'a')
        self.assertEqual(migrated['cursor'], first['cursor'])
        self.assertEqual(self.queue_count(), count)
        with self.hub.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM claims WHERE work=?', (foreign['work'],)).fetchone()[0], 1)
            self.assertTrue(all(row['semantic'] for row in c.execute('SELECT semantic FROM parallel_notices')))

    def test_unicode_large_scopes_exact_subsets_queue_and_response_byte_bounds(self):
        resources = ['scope/' + '😀' * 170 + '/' + str(index) for index in range(30)]
        for index in range(12):
            self.begin(resources=resources, title='Own broad scope ' + str(index))
        foreign = [self.begin('b', resources, title='Unicode foreign ' + str(index)) for index in range(3)]
        with patch.object(hub_notices, 'overlaps', wraps=hub_notices.overlaps) as comparisons:
            current = hub_notices.notices(self.hub, 'a')
        # Prefix/exact sets avoid every own-claim x foreign-claim comparison.
        self.assertLessEqual(comparisons.call_count, 12 * 3 * 30)
        self.assertLessEqual(len(json.dumps(current, ensure_ascii=False, separators=(',', ':')).encode('utf-8')), 3000)
        self.assertTrue(current['more'])
        received, cursor = [], 0
        for _ in range(5):
            page = hub_notices.wait(self.hub, 'a', cursor, timeout=0, max_bytes=1800)
            self.assertLessEqual(len(json.dumps(page, ensure_ascii=False, separators=(',', ':')).encode('utf-8')), 1800)
            self.assertGreater(len(page['notices']), 0)
            self.assertEqual(page['cursor'], page['notices'][-1]['id'])
            for item in page['notices']:
                self.assertEqual(item['workRef'], 'work:' + item['work'])
                self.assertTrue(item['detailsMore'])
                if 'resources' in item:
                    self.assertEqual(item['resourceCount'], 30)
                    self.assertTrue(item['resourcesMore'])
                    self.assertTrue(all(resource['name'] in resources for resource in item['resources']))
                    self.assertLessEqual(len(item['targetWorks']), 3)
                received.append(item['work'])
            cursor = page['cursor']
            if not page['queueMore']:
                break
        self.assertEqual(set(received), {work['work'] for work in foreign})
        self.assertEqual(len(received), 3)
        with self.hub.connect() as c:
            for row in c.execute('SELECT payload FROM parallel_notices WHERE session=?', ('a',)):
                self.assertLessEqual(len(row['payload'].encode('utf-8')), 16000)
        with patch.object(hub_notices, 'MAX_OWN_WORK', 2), patch.object(hub_notices, 'MAX_FOREIGN_WORK', 2):
            bounded = hub_notices.notices(self.hub, 'a', enqueue=False)
        self.assertTrue(bounded['coverage']['ownMore'])
        self.assertTrue(bounded['coverage']['foreignMore'])
        self.assertEqual(bounded['coverage']['ownWorkLimit'], 2)
        self.assertEqual(bounded['coverage']['foreignWorkLimit'], 2)

    def test_wait_wakes_after_committed_update_on_same_home_condition(self):
        self.begin()
        ready = threading.Event()
        condition = hub_notices._condition(self.hub)
        original_wait = condition.wait

        def announced_wait(timeout=None):
            ready.set()
            return original_wait(timeout)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with patch.object(condition, 'wait', side_effect=announced_wait):
                waiting = pool.submit(hub_notices.wait, Hub(self.hub.home), 'a', 0, 4)
                self.assertTrue(ready.wait(2), 'wait reached the condition after its initial durable read')
                foreign = self.begin('b', ['src/ui'])
                hub_notices.refresh_all(self.hub)
                response = waiting.result(timeout=2)
        self.assertEqual([notice['work'] for notice in response['notices']], [foreign['work']])

    def test_read_only_facts_have_no_queue_or_journal_mutation_and_bounds(self):
        self.begin()
        self.begin('b', ['src/ui'])
        with self.hub.connect() as c:
            before = c.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        queue_before = self.queue_count()
        current = hub_notices.notices(self.hub, 'a', enqueue=False)
        self.assertEqual(len(current['notices']), 1)
        self.assertEqual(current['cursor'], 0)
        self.assertEqual(self.queue_count(), queue_before)
        with self.hub.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0], before)
        self.assertEqual(hub_notices.wait(self.hub, 'a', 0, timeout=0)['notices'][0]['kind'], 'relevant')
        for after, timeout in ((-1, 0), (True, 0), ('0', 0), (0, float('inf')), (0, -1)):
            with self.subTest(after=after, timeout=timeout), self.assertRaises(HubError):
                hub_notices.wait(self.hub, 'a', after, timeout)
        for budget in (0, 512, True, '3000'):
            with self.subTest(budget=budget), self.assertRaises(HubError):
                hub_notices.notices(self.hub, 'a', max_bytes=budget)


if __name__ == '__main__':
    unittest.main()
