"""Fixture isolation for the offline Firebird browser qualification gate."""

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.cdeadmin_firebird_offline_profile_ui_gate import prepare_copy


class OfflineProfileFixtureTests(unittest.TestCase):
    def test_only_selected_profile_is_retargeted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.db'
            with sqlite3.connect(path) as db:
                db.executescript('''
                    CREATE TABLE user (id INTEGER, email TEXT);
                    CREATE TABLE server (id INTEGER, user_id INTEGER,
                        name TEXT, host TEXT, port INTEGER, password TEXT,
                        save_password INTEGER);
                    CREATE TABLE cde_endpoint (id INTEGER,
                        legacy_server_id INTEGER, profile_id TEXT);
                    CREATE TABLE cde_endpoint_route (id INTEGER,
                        endpoint_id INTEGER, priority INTEGER,
                        configuration TEXT);
                    CREATE TABLE cde_endpoint_database_target
                        (endpoint_id INTEGER);
                    CREATE TABLE cde_endpoint_runtime_identity
                        (endpoint_id INTEGER, verification_state TEXT,
                        verified_runtime_family TEXT,
                        verified_runtime_version TEXT);
                    INSERT INTO user VALUES (1, 'qa@example.test');
                    INSERT INTO user VALUES (2, 'other@example.test');
                ''')
                for number in (1, 2):
                    db.execute('INSERT INTO server VALUES '
                               '(?, ?, ?, ?, ?, ?, ?)',
                               (number, number, 'original', 'remote', 3050,
                                'fixture-secret', 1))
                    db.execute('INSERT INTO cde_endpoint VALUES (?, ?, ?)',
                               (number, number, 'firebird-native'))
                    db.execute('INSERT INTO cde_endpoint_route VALUES '
                               '(?, ?, 0, ?)', (number, number, json.dumps({
                                   'host': 'remote',
                                   'database': 'example.fdb'})))
                    db.execute('INSERT INTO cde_endpoint_database_target '
                               'VALUES (?)', (number,))
                    db.execute('INSERT INTO cde_endpoint_runtime_identity '
                               'VALUES (?, ?, ?, ?)',
                               (number, 'verified', 'firebird', '5.0.4'))
            self.assertEqual(prepare_copy(path, 'qa@example.test', 39999),
                             (1, 1))
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT host, password, '
                                            'save_password FROM server '
                                            'WHERE id = 1').fetchone(),
                                 ('127.0.0.1', None, 0))
                self.assertEqual(db.execute('SELECT name, host FROM server '
                                            'WHERE id = 2').fetchone(),
                                 ('original', 'remote'))
                self.assertEqual(db.execute('SELECT * FROM '
                                            'cde_endpoint_database_target'
                                            ).fetchall(), [(2,)])
                route = json.loads(db.execute('SELECT configuration FROM '
                                              'cde_endpoint_route WHERE id = 1'
                                              ).fetchone()[0])
                self.assertNotIn('database', route)
                self.assertEqual(route['port'], 39999)
