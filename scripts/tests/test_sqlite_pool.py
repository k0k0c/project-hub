import os
import gc
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from sqlite_pool import SQLitePool


class SQLitePoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pools = []
        self.path = Path(self.temp.name) / "state.sqlite"
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("CREATE TABLE values_table (value TEXT)")
            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        for pool in self.pools: pool.close()
        self.pools.clear(); gc.collect()
        self.temp.cleanup()

    def pool(self, **kwargs):
        value = SQLitePool(self.path, **kwargs); self.pools.append(value); return value

    def test_leases_are_distinct_and_bound(self):
        pool = self.pool(max_idle=2, max_connections=2, timeout=.1)
        entered = threading.Event()
        release = threading.Event()
        connections = []
        def hold():
            with pool.connect() as connection:
                connections.append(connection); entered.set(); release.wait(2)
        threads = [threading.Thread(target=hold) for _ in range(2)]
        for thread in threads: thread.start()
        self.assertTrue(entered.wait(1))
        with self.assertRaises(TimeoutError):
            with pool.connect(): pass
        release.set()
        for thread in threads: thread.join(2)
        self.assertEqual(2, len({id(connection) for connection in connections}))

    def test_rollback_and_external_visibility(self):
        pool = self.pool(max_idle=1)
        with pool.connect() as connection:
            connection.execute("BEGIN")
            connection.execute("INSERT INTO values_table VALUES ('rolled back')")
        external = sqlite3.connect(self.path)
        try:
            self.assertEqual([], external.execute("SELECT value FROM values_table").fetchall())
            external.execute("INSERT INTO values_table VALUES ('external')")
            external.commit()
        finally:
            external.close()
        with pool.connect() as connection:
            self.assertEqual(['external'], [row[0] for row in connection.execute("SELECT value FROM values_table").fetchall()])

    def test_foreign_keys_stay_enabled_on_reused_lease(self):
        pool = self.pool(max_idle=1, foreign_keys=True)
        with pool.connect() as connection:
            self.assertEqual(1, connection.execute('PRAGMA foreign_keys').fetchone()[0])
            connection.execute('CREATE TABLE parent (id INTEGER PRIMARY KEY)')
            connection.execute('CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))')
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute('INSERT INTO child VALUES (99)')
        with pool.connect() as connection:
            self.assertEqual(1, connection.execute('PRAGMA foreign_keys').fetchone()[0])
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute('INSERT INTO child VALUES (100)')

    def test_failed_transaction_is_rolled_back_before_next_lease(self):
        pool = self.pool(max_idle=1)
        with self.assertRaisesRegex(RuntimeError, 'abort'):
            with pool.connect() as connection:
                connection.execute('BEGIN')
                connection.execute("INSERT INTO values_table VALUES ('uncommitted')")
                raise RuntimeError('abort')
        with pool.connect() as connection:
            self.assertEqual([], connection.execute(
                "SELECT value FROM values_table WHERE value='uncommitted'").fetchall())

    def test_existing_only_rejects_missing_database_until_created_externally(self):
        path = Path(self.temp.name) / 'external.sqlite'
        pool = SQLitePool(path, existing_only=True)
        self.pools.append(pool)
        with self.assertRaises(sqlite3.OperationalError):
            with pool.connect():
                pass
        self.assertFalse(path.exists())
        external = sqlite3.connect(path)
        try:
            external.execute('CREATE TABLE external_values (value TEXT)')
            external.commit()
        finally:
            external.close()
        with pool.connect() as connection:
            connection.execute("INSERT INTO external_values VALUES ('ready')")
            self.assertEqual(['ready'], [row[0] for row in connection.execute(
                'SELECT value FROM external_values').fetchall()])

    def test_replacement_does_not_reuse_old_handle(self):
        pool = self.pool(max_idle=1)
        with pool.connect() as first:
            first.execute("INSERT INTO values_table VALUES ('old')")
        del first
        old_identity = pool._identity()
        replacement = self.path.with_suffix('.new')
        connection = sqlite3.connect(replacement)
        try:
            connection.execute("CREATE TABLE values_table (value TEXT)")
            connection.execute("INSERT INTO values_table VALUES ('new')")
            connection.commit()
        finally:
            connection.close()
        if os.name == 'nt':
            # Windows keeps SQLite file handles open across rename.  Close the
            # idle lease before replacing; the pool still validates freshness
            # on its next open, while POSIX exercises stale-cache eviction.
            pool.close()
            gc.collect()
        os.replace(replacement, self.path)
        if os.name == 'nt': pool = self.pool(max_idle=1)
        with pool.connect() as current:
            self.assertEqual(['new'], [row[0] for row in current.execute("SELECT value FROM values_table").fetchall()])
            self.assertNotEqual(old_identity, pool._identity())
        pool.close()

    def test_replacement_during_active_lease_closes_stale_handle_on_recheckout(self):
        pool = self.pool(max_idle=1)
        replacement_path = Path(self.temp.name) / 'replacement.sqlite'
        replacement = sqlite3.connect(replacement_path)
        try:
            replacement.execute('CREATE TABLE values_table (value TEXT)')
            replacement.execute("INSERT INTO values_table VALUES ('after replacement')")
            replacement.commit()
        finally:
            replacement.close()
        identity = [('device', 1)]
        old = None
        with patch.object(pool, '_identity', side_effect=lambda: identity[0]):
            with pool.connect() as connection:
                old = connection
                connection.execute("INSERT INTO values_table VALUES ('before replacement')")
                identity[0] = ('device', 2)
                pool.path = replacement_path
            with pool.connect() as replacement:
                self.assertIsNot(old, replacement)
                self.assertEqual(['after replacement'], [row[0] for row in replacement.execute(
                    "SELECT value FROM values_table").fetchall()])
            with self.assertRaises(sqlite3.ProgrammingError):
                old.execute('SELECT 1')

    def test_close_rejects_new_and_closes_returned_active(self):
        pool = self.pool(max_idle=1)
        entered = threading.Event(); release = threading.Event(); holder = []
        def hold():
            with pool.connect() as connection:
                holder.append(connection); entered.set(); release.wait(2)
        thread = threading.Thread(target=hold); thread.start(); self.assertTrue(entered.wait(1))
        pool.close(); release.set(); thread.join(2)
        with self.assertRaises(sqlite3.ProgrammingError):
            holder[0].execute("SELECT 1")
        with self.assertRaises(RuntimeError):
            with pool.connect(): pass


if __name__ == '__main__':
    unittest.main()
