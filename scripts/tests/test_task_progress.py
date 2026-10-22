"""Progress and main-task contracts using temporary stores and coordination data."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import Store
from task_progress import project_progress, timestamp, work_activity
from project_registry import ProjectRegistry, CodexProjects
from task_transfer import transfer


def task(identity, hours=None, active=False):
    value = dict(id=identity, title=identity, status='active', stages=[])
    if hours is not None:
        value['estimate'] = dict(percentLow=20, percentHigh=40, hoursLow=hours/2, hoursHigh=hours)
    if active:
        value['currentWork'] = dict(at='2026-01-01T00:00:00Z')
    return value


class ProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / 'docs/project-portal'
        self.data.mkdir(parents=True)
        (self.data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id='p', name='P', tasks=[task('a'), task('b')])) )
        self.store = Store(self.root, coordination_home=self.root / 'coordination')

    def tearDown(self):
        self.tmp.cleanup()

    def update(self, identity='a', **values):
        return self.store.record(dict(taskId=identity, kind='task.updated', title='Update', patch=values))

    def test_primary_election_clear_completion_and_reopen(self):
        self.update(primary=dict(selected=True, project='p'))
        self.update('b', primary=dict(selected=True, project='p'))
        self.update(primary=dict(selected=False, project='p'))
        self.assertEqual(self.store.snapshot()['mainTask'], dict(task='b', reason='explicit'))
        self.update('b', status='done')
        self.update('b', status='active')
        self.assertEqual(self.store.snapshot()['mainTask']['reason'], 'latest-active')
        self.update(primary=dict(selected=True, project='p'))
        self.update(primary=dict(selected=False, project='p'))
        self.assertEqual(self.store.snapshot()['mainTask']['task'], 'b')

    def test_primary_validation(self):
        for primary in (True, {}, dict(selected=1, project='p'), dict(selected=True, project=''), dict(selected=True, project='p', other=1)):
            with self.assertRaises(ValueError):
                self.update(primary=primary)

    def test_selection_only_current_active_then_remaining_size(self):
        tasks = [task('old', 100), task('small', 4, True), task('big', 12, True)]
        self.assertEqual(project_progress(tasks, [], 'p')['task'], 'old')
        tasks[2]['status'] = 'cancelled'
        self.assertEqual(project_progress(tasks, [], 'p')['task'], 'old')
        tasks[1].pop('currentWork')
        self.assertEqual(project_progress(tasks, [], 'p')['task'], 'old')
        tasks = [task('a', active=True), task('b', active=True)]
        tasks[1]['currentWork']['at'] = '2026-01-02T00:00:00Z'
        self.assertEqual(project_progress(tasks, [], 'p'), dict(task='b', reason='latest-active'))

    def test_legacy_and_review_unchanged_ranges(self):
        estimate = dict(percentLow=55, percentHigh=60, hoursLow=3, hoursHigh=8, confidence='reviewed', note='same ranges', updatedBy='agent')
        values = [task('old', 8)]
        project_progress(values, [], 'p')
        self.assertEqual(values[0]['progress']['reason'], 'legacy')
        event = self.update(estimate=estimate)
        first = self.store.snapshot()['tasks'][0]
        self.assertEqual(first['estimate'], dict(estimate, updatedAt=event['at']))
        self.assertFalse(first['progress']['reviewDue'])
        again = self.update(estimate=estimate)
        self.assertNotEqual(event['at'], again['at'])
        self.assertEqual(self.store.snapshot()['tasks'][0]['estimate']['percentLow'], 55)

    def test_milestone_same_second_then_review_clears(self):
        estimate = dict(percentLow=10, percentHigh=30)
        self.update(primary=dict(selected=True, project='p'))
        self.update(estimate=estimate)
        self.store.record(dict(taskId='a', stageId='s', kind='stage.created', title='done', patch=dict(title='s', status='done')))
        self.assertEqual(self.store.snapshot()['tasks'][0]['progress']['reason'], 'milestone')
        self.assertEqual(self.store.snapshot()['mainTask'], dict(task='a', reason='explicit'))
        self.update(estimate=estimate)
        self.assertFalse(self.store.snapshot()['tasks'][0]['progress']['reviewDue'])

    def database(self, stop=1800, status='active'):
        db = self.root / 'test.sqlite3'
        with closing(sqlite3.connect(db)) as c:
            c.executescript('CREATE TABLE work(id,project,session,task,status,created,updated); CREATE TABLE sessions(id,project,state,seen); CREATE TABLE events(seq,project,session,work,kind,at);')
            c.execute('INSERT INTO work VALUES (?,?,?,?,?,?,?)', ('w','p','s','a',status,100,stop))
            c.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('s','p','idle',stop))
            c.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)', [(1,'p','s',None,'SessionStart',100),(2,'p','s','w','work.started',100),(3,'p','s',None,'Stop',stop)])
            c.commit()
        return db

    def test_idle_freezes_active_time_and_enrolled_work_overrides_stale_current(self):
        db = self.database()
        values = [task('a', active=True)]
        values[0]['estimate'] = dict(percentLow=10, percentHigh=20, updatedAt='1970-01-01T00:01:40Z')
        project_progress(values, [], 'p', db, at=10000)
        self.assertFalse(values[0]['progress']['active'])
        self.assertNotIn('currentWork', values[0])
        self.assertEqual(values[0]['currentWorks'], [])
        self.assertFalse(values[0]['progress']['reviewDue'])
        previous = copy.deepcopy(values)
        project_progress(values, [], 'p', db, at=100000)
        self.assertEqual(values, previous)

    def test_interleaved_work_and_session_boundaries_keep_exact_activity(self):
        db = self.database(stop=300)
        with closing(sqlite3.connect(db)) as c:
            c.execute('DELETE FROM events')
            c.execute("UPDATE sessions SET state='active',seen=400 WHERE id='s'")
            c.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('s2','p','idle',250))
            c.executemany('INSERT INTO work VALUES (?,?,?,?,?,?,?)', [
                ('w2','p','s2','b','done',110,250), ('w3','p','s','a','waiting',120,180)])
            events = [
                ('s',None,'SessionStart',100), ('s','w','work.started',100),
                ('s2',None,'SessionStart',105), ('s2','w2','work.started',110),
                ('s','w3','work.started',120), ('s',None,'Stop',150),
                ('s2','w2','work.waiting',160), ('s',None,'PreToolUse',170),
                ('s','w3','work.waiting',180), ('s2',None,'UserPromptSubmit',190),
                ('s2','w2','work.active',200), ('s2',None,'Stop',230),
                ('s2','w2','work.done',250), ('unrelated','other','work.started',260),
                ('unrelated',None,'Interrupt',270), ('s','w','work.active',300)]
            c.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',
                          [(seq,'p',*event) for seq,event in enumerate(events,1)])
            c.commit()
        self.assertEqual(work_activity(db, 'p', 400), {
            'a': {'active': True, 'latest': 300,
                  'intervals': [(100,150), (170,400), (120,150), (170,180)],
                  'currentWorks': [dict(id='w',eventId='w',title='w',stageId=None,session='s',
                                        source='coordination',at='1970-01-01T00:01:40.000000Z',
                                        updatedAt='1970-01-01T00:05:00.000000Z')],
                  'unknown': False, 'stages': {}, 'waitingSessions': {'s'}},
            'b': {'active': False, 'latest': 0, 'intervals': [(110,160),(200,230)],
                  'currentWorks': [], 'unknown': False, 'stages': {}}})

    def test_actual_active_hour_is_due_even_after_stop(self):
        db = self.database(stop=3800)
        values = [task('a')]
        values[0]['estimate'] = dict(percentLow=10, percentHigh=20, updatedAt='1970-01-01T00:01:40Z')
        project_progress(values, [], 'p', db, at=10000)
        self.assertEqual(values[0]['progress']['reason'], 'interval')

    def test_waiting_interval_excluded_and_resumed_session_accumulates(self):
        db = self.database(stop=1800)
        with closing(sqlite3.connect(db)) as c:
            c.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)', [
                (4,'p','s','w','work.waiting',1900),
                (5,'p','s',None,'UserPromptSubmit',5000),
                (6,'p','s','w','work.active',6000)])
            c.execute("UPDATE sessions SET state='active',seen=7800")
            c.execute('UPDATE work SET updated=6000')
            c.commit()
        values = [task('a')]
        values[0]['estimate'] = dict(percentLow=10,percentHigh=20,updatedAt='1970-01-01T00:01:40Z')
        project_progress(values, [], 'p', db, at=7899)
        self.assertFalse(values[0]['progress']['reviewDue'])
        self.assertTrue(values[0]['progress']['active'])
        project_progress(values, [], 'p', db, at=7900)
        self.assertEqual(values[0]['progress']['reason'], 'interval')

    def test_current_works_all_active_chats_stages_and_tasks(self):
        db = self.database()
        with closing(sqlite3.connect(db)) as c:
            c.execute('ALTER TABLE work ADD COLUMN title')
            c.execute('CREATE TABLE work_stages(work,stage)')
            c.execute("UPDATE sessions SET state='active',seen=2900")
            c.execute("UPDATE work SET title='First chat work'")
            c.executemany('INSERT INTO sessions VALUES (?,?,?,?)', [('s2','p','active',2200),('idle','p','idle',2400)])
            c.executemany('INSERT INTO work VALUES (?,?,?,?,?,?,?,?)', [
                ('second','p','s2','a','active',200,2200,'Second chat work'),
                ('other-task','p','s2','b','active',200,2100,'Other task work'),
                ('waiting','p','s2','a','waiting',200,2500,'Waiting'),
                ('closed','p','s2','a','done',200,2600,'Closed'),
                ('stopped','p','idle','a','active',200,2700,'Idle chat'),
                ('unknown','p','missing-session','a','active',200,2800,'Unknown chat'),
                ('foreign','other-project','s2','a','active',200,2900,'Other project')])
            c.executemany('INSERT INTO work_stages VALUES (?,?)', [('w','one'),('second','two'),('other-task','three')])
            c.commit()
        values = [task('a', active=True), task('b')]
        values[0]['currentWork']['title'] = 'Old journal work'
        project_progress(values, [], 'p', db, at=3000)
        current = values[0]['currentWorks']
        self.assertEqual([w['id'] for w in current], ['second','w'])
        self.assertEqual([w['stageId'] for w in current], ['two','one'])
        self.assertEqual([w['session'] for w in current], ['s2','s'])
        self.assertEqual(current[0]['title'], 'Second chat work')
        self.assertEqual(timestamp(current[0]['at']), 200)
        self.assertEqual(timestamp(current[0]['updatedAt']), 2200)
        self.assertEqual(current[0]['source'], 'coordination')
        self.assertEqual(values[0]['currentWork'], current[0])
        self.assertEqual([w['id'] for w in values[1]['currentWorks']], ['other-task'])
        values[0]['status'] = 'done'
        project_progress(values, [], 'p', db, at=4000)
        self.assertEqual(values[0]['currentWorks'], [])
        self.assertNotIn('currentWork', values[0])

    def test_legacy_current_work_is_never_in_confirmed_active_array(self):
        values = [task('legacy', active=True)]
        old = dict(values[0]['currentWork'])
        project_progress(values, [], 'p')
        self.assertEqual(values[0]['currentWorks'], [])
        self.assertEqual(values[0]['currentWork'], old)
        self.assertEqual(values[0]['agentActivity'], dict(state='unknown', sessions=0))

    def test_agent_activity_priority_unique_sessions_and_logical_status(self):
        db = self.database()
        values = [task('a')]
        project_progress(values, [], 'p', db, at=3000)
        self.assertEqual(values[0]['agentActivity'], dict(state='idle', sessions=0))
        with closing(sqlite3.connect(db)) as c:
            c.execute('INSERT INTO work VALUES (?,?,?,?,?,?,?)', ('unknown','p','missing','a','active',100,2000))
            c.commit()
        project_progress(values, [], 'p', db, at=3000)
        self.assertEqual(values[0]['agentActivity'], dict(state='unknown', sessions=0))
        with closing(sqlite3.connect(db)) as c:
            c.execute("UPDATE sessions SET state='active',seen=2900")
            c.execute('INSERT INTO work VALUES (?,?,?,?,?,?,?)', ('second','p','s','a','active',100,2100))
            c.commit()
        values[0]['status'] = 'planned'
        project_progress(values, [], 'p', db, at=3000)
        self.assertEqual(values[0]['agentActivity'], dict(state='active', sessions=1))
        self.assertEqual(len(values[0]['currentWorks']), 2)
        project_progress(values, [], 'p', db, at=3000000)
        self.assertEqual(values[0]['agentActivity'], dict(state='unknown', sessions=0))
        self.assertEqual(values[0]['currentWorks'], [])
        values[0]['status'] = 'cancelled'
        project_progress(values, [], 'p', db, at=3000000)
        self.assertEqual(values[0]['agentActivity'], dict(state='idle', sessions=0))

    def test_closed_work_is_idle_without_session_but_open_unknown_is_not(self):
        db = self.database(status='done')
        with closing(sqlite3.connect(db)) as c:
            c.execute('DELETE FROM sessions')
            c.commit()
        values = [task('a')]
        project_progress(values, [], 'p', db, at=3000)
        self.assertEqual(values[0]['agentActivity'], dict(state='idle', sessions=0))
        with closing(sqlite3.connect(db)) as c:
            c.execute("UPDATE work SET status='waiting'")
            c.commit()
        project_progress(values, [], 'p', db, at=3000)
        self.assertEqual(values[0]['agentActivity'], dict(state='unknown', sessions=0, waitingSessions=1))

    def test_stage_activity_is_independent_of_task_and_other_stages(self):
        db = self.database()
        with closing(sqlite3.connect(db)) as c:
            c.execute('CREATE TABLE work_stages(work,stage)')
            c.execute("UPDATE sessions SET state='active',seen=2900")
            c.execute('INSERT INTO work VALUES (?,?,?,?,?,?,?)', ('unknown','p','missing','a','active',100,2000))
            c.executemany('INSERT INTO work_stages VALUES (?,?)', [('w','one'),('unknown','two')])
            c.commit()
        values = [task('a')]
        values[0]['stages'] = [dict(id=s, title=s, status='active') for s in ('one','two','unobserved')]
        project_progress(values, [], 'p', db, at=3000)
        one, two, unobserved = values[0]['stages']
        self.assertEqual(values[0]['agentActivity'], dict(state='active', sessions=1))
        self.assertEqual(one['agentActivity'], dict(state='active', sessions=1))
        self.assertEqual(two['agentActivity'], dict(state='unknown', sessions=0))
        self.assertEqual(unobserved['agentActivity'], dict(state='unknown', sessions=0))
        with closing(sqlite3.connect(db)) as c:
            c.execute("UPDATE sessions SET state='idle',seen=3100 WHERE id='s'")
            c.execute('INSERT INTO events VALUES (?,?,?,?,?,?)', (4,'p','s',None,'Stop',3100))
            c.commit()
        project_progress(values, [], 'p', db, at=3200)
        self.assertEqual(one['agentActivity'], dict(state='idle', sessions=0))
        self.assertEqual(one['status'], 'active')
        self.assertEqual(two['agentActivity'], dict(state='unknown', sessions=0))
        self.assertEqual(values[0]['agentActivity'], dict(state='unknown', sessions=0))
        two['status'] = 'done'
        unobserved['status'] = 'cancelled'
        project_progress(values, [], 'p', db, at=3300)
        self.assertEqual(two['agentActivity'], dict(state='idle', sessions=0))
        self.assertEqual(unobserved['agentActivity'], dict(state='idle', sessions=0))

    def test_transfer_primary_does_not_leak_or_revive_and_revision_stable(self):
        catalog = self.root / 'catalog.json'
        catalog.write_text(json.dumps({'local-projects': {p: dict(id=p,name=p,rootPaths=[str(self.root/p)]) for p in ('a','b')}}))
        registry = ProjectRegistry(self.root/'registry', CodexProjects(catalog))
        ids = {p['name']:p['id'] for p in registry.list()['projects']}
        source, target = registry.store(ids['a']), registry.store(ids['b'])
        source.record(dict(taskId='x',kind='task.created',title='X',patch=dict(title='X',status='active',stages=[])))
        source.record(dict(taskId='x',kind='task.updated',title='Pin',patch=dict(primary=dict(selected=True,project=ids['a']))))
        self.assertEqual(source.snapshot()['mainTask']['reason'], 'explicit')
        before = source.snapshot()['revision']
        with patch('task_progress.time.time', return_value=timestamp('2040-01-01T00:00:00Z')):
            self.assertEqual(source.snapshot()['revision'], before)
        transfer(registry,ids['a'],ids['b'],'x',before,'out')
        self.assertEqual(target.snapshot()['mainTask']['reason'], 'latest-active')
        transfer(registry,ids['b'],ids['a'],'x',target.snapshot()['revision'],'back')
        self.assertEqual(source.snapshot()['mainTask']['reason'], 'latest-active')
        source.record(dict(taskId='x',kind='task.updated',title='Pin again',patch=dict(primary=dict(selected=True,project=ids['a']))))
        self.assertEqual(source.snapshot()['mainTask']['reason'], 'explicit')


if __name__ == '__main__':
    unittest.main()
