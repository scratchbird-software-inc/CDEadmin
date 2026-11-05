##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2026, The ScratchBird Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""user_preferences.value is unbounded text (schema 60, 2026-11-05).

The structural and SQLite tests always run. The PostgreSQL test, which shows
the 1024-character refusal the migration removes, runs when
``CDEADMIN_ROUNDTRIP_POSTGRESQL`` holds ``{"host", "port", "user",
"password"?, "database"?}`` for a role that may create a schema; it works in
a schema of its own and drops it afterwards.
"""

import importlib.util
import json
import os
import re
import unittest
import uuid
from pathlib import Path

try:
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    MIGRATION_DEPENDENCIES = True
except ImportError:  # pragma: no cover
    MIGRATION_DEPENDENCIES = False

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / 'web/pgadmin/model/__init__.py'
REVISION = 'cde_user_preference_text_v1'
SETTINGS = json.loads(os.environ.get('CDEADMIN_ROUNDTRIP_POSTGRESQL') or 'null')
LONG = 'x' * 5000


def load(name):
    path = ROOT / f'web/migrations/versions/{name}_.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_tables(connection):
    metadata = sa.MetaData()
    sa.Table('user', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    sa.Table('preferences', metadata,
             sa.Column('id', sa.Integer(), primary_key=True))
    sa.Table('user_preferences', metadata,
             # As the real table: both keys cascade on delete.
             sa.Column('pid', sa.Integer(),
                       sa.ForeignKey('preferences.id', ondelete='CASCADE'),
                       primary_key=True),
             sa.Column('uid', sa.Integer(),
                       sa.ForeignKey('user.id', ondelete='CASCADE'),
                       primary_key=True),
             sa.Column('value', sa.String(1024), nullable=False))
    metadata.create_all(connection)
    connection.execute(sa.text('INSERT INTO "user" (id) VALUES (1)'))
    connection.execute(sa.text('INSERT INTO preferences (id) VALUES (1), (2)'))
    connection.execute(sa.text(
        "INSERT INTO user_preferences (pid, uid, value) VALUES (1, 1, 'kept')"))


def migrate(connection, step):
    module = load(REVISION)
    module.op = Operations(MigrationContext.configure(connection))
    getattr(module, step)()


def value_type(connection):
    column = next(column for column in sa.inspect(connection).get_columns(
        'user_preferences') if column['name'] == 'value')
    return column['type']


def table_shape(connection):
    # SQLite rebuilds the table to change a column; the keys must survive.
    inspector = sa.inspect(connection)
    keys = sorted((tuple(key['constrained_columns']), key['referred_table'],
                   (key.get('options') or {}).get('ondelete'))
                  for key in inspector.get_foreign_keys('user_preferences'))
    return keys, inspector.get_pk_constraint('user_preferences')[
        'constrained_columns']


EXPECTED_SHAPE = ([(('pid',), 'preferences', 'CASCADE'),
                   (('uid',), 'user', 'CASCADE')], ['pid', 'uid'])


def insert_long(connection):
    connection.execute(sa.text(
        'INSERT INTO user_preferences (pid, uid, value) VALUES (2, 1, :value)'),
        {'value': LONG})


class SourceTests(unittest.TestCase):
    def test_model_and_version_declare_text(self):
        source = MODEL_PATH.read_text(encoding='utf-8')
        self.assertRegex(source, r'SCHEMA_VERSION\s*=\s*60\b')
        start = source.index("__tablename__ = 'user_preferences'")
        model = source[start:source.index('class ', start)]
        self.assertIn('value = db.Column(db.Text, nullable=False)', model)

    def test_migration_follows_the_previous_head(self):
        source = (ROOT / f'web/migrations/versions/{REVISION}_.py').read_text(
            encoding='utf-8')
        self.assertTrue(re.search(r"^down_revision = 'cde_bi_embeds_v1'$",
                                  source, re.MULTILINE))


@unittest.skipUnless(MIGRATION_DEPENDENCIES, 'alembic is unavailable')
class SQLiteTests(unittest.TestCase):
    def test_round_trip_keeps_values(self):
        engine = sa.create_engine('sqlite:///:memory:')
        with engine.connect() as connection:
            create_tables(connection)
            self.assertEqual(table_shape(connection), EXPECTED_SHAPE)
            migrate(connection, 'upgrade')
            self.assertIsInstance(value_type(connection), sa.Text)
            self.assertEqual(table_shape(connection), EXPECTED_SHAPE)
            insert_long(connection)
            connection.execute(sa.text(
                'DELETE FROM user_preferences WHERE pid = 2'))
            migrate(connection, 'downgrade')
            column = value_type(connection)
            self.assertIsInstance(column, sa.String)
            self.assertEqual(column.length, 1024)
            self.assertEqual(table_shape(connection), EXPECTED_SHAPE)
            self.assertEqual(connection.execute(sa.text(
                'SELECT value FROM user_preferences')).scalars().all(),
                ['kept'])


@unittest.skipUnless(MIGRATION_DEPENDENCIES and SETTINGS is not None,
                     'CDEADMIN_ROUNDTRIP_POSTGRESQL is not set')
class PostgreSQLTests(unittest.TestCase):
    def setUp(self):
        url = sa.engine.URL.create(
            'postgresql+psycopg', username=SETTINGS['user'],
            password=SETTINGS.get('password'), host=SETTINGS['host'],
            port=SETTINGS.get('port'),
            database=SETTINGS.get('database', 'postgres'))
        self.schema = f'pref_text_{uuid.uuid4().hex[:8]}'
        admin = sa.create_engine(url)
        with admin.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA {self.schema}'))
        self.addCleanup(admin.dispose)
        self.addCleanup(self.drop_schema, admin)
        self.engine = sa.create_engine(url, connect_args={
            'options': f'-c search_path={self.schema}'})
        self.addCleanup(self.engine.dispose)

    def drop_schema(self, admin):
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA {self.schema} CASCADE'))

    def test_widens_the_column_and_refuses_to_truncate(self):
        with self.engine.begin() as connection:
            create_tables(connection)
        # Before: a value over 1024 characters is refused.
        with self.assertRaises(sa.exc.DataError):
            with self.engine.begin() as connection:
                insert_long(connection)
        with self.engine.begin() as connection:
            migrate(connection, 'upgrade')
        with self.engine.begin() as connection:
            self.assertIsInstance(value_type(connection), sa.Text)
            self.assertEqual(table_shape(connection), EXPECTED_SHAPE)
            insert_long(connection)
        # Downgrade fails rather than truncate the long value.
        with self.assertRaises(sa.exc.DataError):
            with self.engine.begin() as connection:
                migrate(connection, 'downgrade')
        with self.engine.begin() as connection:
            self.assertEqual(connection.execute(sa.text(
                'SELECT length(value) FROM user_preferences WHERE pid = 2'
            )).scalar(), len(LONG))
            connection.execute(sa.text(
                'DELETE FROM user_preferences WHERE pid = 2'))
            migrate(connection, 'downgrade')
            self.assertEqual(value_type(connection).length, 1024)
            self.assertEqual(connection.execute(sa.text(
                'SELECT value FROM user_preferences')).scalars().all(),
                ['kept'])


if __name__ == '__main__':
    unittest.main()
