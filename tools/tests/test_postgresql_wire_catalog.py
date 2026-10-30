"""The shared PostgreSQL-wire catalog reader and CockroachDB's additions."""
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    _annotate_catalog,
)
from pgadmin.cdeadmin.providers.distributed_sql import (  # noqa: E402
    postgresql_constraint_details, resource,
)


class Cursor:
    """Answers each catalog query by a substring of its SQL."""

    def __init__(self, answers):
        self.answers, self.rows = answers, []

    def execute(self, source, parameters=()):
        self.rows = next((rows for needle, rows in self.answers.items()
                          if needle in source), [])

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


class Connection:
    def __init__(self, cursor):
        self.native = cursor

    def cursor(self):
        return self.native

    def rollback(self):
        pass


ATTRIBUTES = [(10, 1, 'id'), (10, 2, 'pid'), (10, 3, 'v'), (20, 1, 'id')]
CONSTRAINTS = [
    ('public', 'child', 'fk1', 'f', [2], 10, 'public', 'parent', [1], 20,
     'a', 'c', 'FOREIGN KEY (pid) REFERENCES parent(id) ON DELETE CASCADE'),
    ('public', 'child', 'ck1', 'c', [3], 10, None, None, None, 0, ' ', ' ',
     'CHECK ((v > 0))'),
    ('public', 'other', 'ck1', 'c', [3], 30, None, None, None, 0, ' ', ' ',
     'CHECK ((v < 9)) NOT VALID'),
    ('public', 'child', 'child_pkey', 'p', [1], 10, None, None, None, 0,
     ' ', ' ', 'PRIMARY KEY (id ASC)'),
]


def test_constraints_are_tied_to_their_table_with_ordered_columns():
    details = postgresql_constraint_details(Cursor({
        'pg_attribute': ATTRIBUTES, 'pg_constraint': CONSTRAINTS}))
    assert details[('public', 'child', 'fk1')] == {
        'columns': ['pid'], 'referenced_schema': 'public',
        'referenced_table': 'parent', 'referenced_columns': ['id'],
        'update_rule': 'NO ACTION', 'delete_rule': 'CASCADE'}
    # Two checks with one name in one schema stay apart.
    assert details[('public', 'child', 'ck1')]['check_clause'] == \
        '((v > 0))'
    assert details[('public', 'other', 'ck1')]['check_clause'] == \
        '((v < 9))'
    assert details[('public', 'child', 'child_pkey')] == {'columns': ['id']}


def native(path, kind, **values):
    return resource(kind, path[:-1], path[-1], 'g', values)


def test_hidden_columns_and_the_engines_own_constraints_stay_out():
    values = [
        native(['public', 't', 'v'], 'column', data_type='bigint'),
        native(['public', 't', 'rowid'], 'column', data_type='bigint'),
        native(['public', 't', 'crdb_internal_ts_shard_8'], 'column'),
        native(['public', 't', 't_pkey'], 'constraint',
               constraint_type='PRIMARY KEY', columns=['rowid']),
        native(['public', 't', 'check_crdb_internal_ts_shard_8'],
               'constraint', constraint_type='CHECK',
               columns=['crdb_internal_ts_shard_8']),
        native(['public', 't', 'uq'], 'constraint',
               constraint_type='UNIQUE', columns=['v']),
        native(['public', 't', 't_pkey'], 'index', definition=(
            'CREATE UNIQUE INDEX t_pkey ON d.public.t USING btree '
            '(rowid ASC)')),
        native(['public', 't', 'ih'], 'index', definition=(
            'CREATE INDEX ih ON d.public.t USING btree (v ASC) USING HASH '
            'WITH (bucket_count=8)')),
        native(['public', 't', 'ip'], 'index', definition=(
            'CREATE INDEX ip ON d.public.t USING btree (v DESC) STORING (w) '
            'WHERE (v > 0)')),
    ]
    cursor = Cursor({
        # is_hidden, crdb_sql_type, column_comment, column_default
        'is_hidden': [('public', 't', 'v', 'NO', 'INT8', None, None),
                      ('public', 't', 'rowid', 'YES', 'INT8', None,
                       'unique_rowid()'),
                      ('public', 't', 'crdb_internal_ts_shard_8', 'YES',
                       'INT8', None, None)],
        'information_schema.statistics': [
            ('public', 't', 't_pkey', 'rowid', 'ASC', 'NO', 'NO', 'NO', 1.0),
            # The primary index stores every column.
            ('public', 't', 't_pkey', 'v', 'N/A', 'YES', 'NO', 'NO', 1.0),
            ('public', 't', 'ih', 'crdb_internal_ts_shard_8', 'ASC', 'NO',
             'YES', 'YES', 1.0),
            ('public', 't', 'ih', 'v', 'ASC', 'NO', 'NO', 'YES', 1.0),
            ('public', 't', 'ih', 'rowid', 'ASC', 'NO', 'YES', 'YES', 1.0),
            ('public', 't', 'ip', 'v', 'DESC', 'NO', 'NO', 'YES', 0.5),
            ('public', 't', 'ip', 'w', 'N/A', 'YES', 'NO', 'YES', 0.5)],
    })
    rows = {item['resource_id']: item['native']
            for item in _annotate_catalog(Connection(cursor), values)}
    assert (rows['column:public:t:v']['hidden'],
            rows['column:public:t:rowid']['hidden']) == (False, True)
    assert rows['column:public:t:v']['native_type'] == 'INT8'
    assert rows['column:public:t:v']['column_key'] == 'UNI'
    assert 'constraint:public:t:t_pkey' not in rows
    assert 'constraint:public:t:check_crdb_internal_ts_shard_8' not in rows
    assert (rows['index:public:t:t_pkey']['storing'],
            rows['index:public:t:t_pkey']['hidden']) == ([], True)
    hashed = rows['index:public:t:ih']
    assert (hashed['columns'], hashed['hash_sharded'],
            hashed['bucket_count'], hashed['hidden']) == (['v'], True, 8,
                                                          False)
    partial = rows['index:public:t:ip']
    assert (partial['columns'], partial['directions'], partial['storing'],
            partial['predicate'], partial['visibility']) == (
        ['v'], ['DESC'], ['w'], 'v > 0', 0.5)


def test_a_users_not_visible_column_is_kept_and_the_table_carries_its_facts():
    values = [
        native(['public', 'u'], 'table'),
        native(['public', 'u', 'id'], 'column', data_type='bigint',
               is_nullable='NO', default_expression=None),
        native(['public', 'u', 'secret'], 'column', data_type='text',
               is_nullable='YES', default_expression="'x'"),
        native(['public', 'u', 'crdb_internal_expiration'], 'column'),
        native(['public', 'u', 'u_pkey'], 'constraint',
               constraint_type='PRIMARY KEY', columns=['id']),
    ]
    cursor = Cursor({
        'is_hidden': [
            ('public', 'u', 'id', 'NO', 'INT8', None, None),
            ('public', 'u', 'secret', 'YES', 'STRING', 'kept', "'x'"),
            ('public', 'u', 'crdb_internal_expiration', 'YES',
             'TIMESTAMPTZ', None, 'current_timestamp()')],
        'attgenerated': [('public', 'u', 'id', '', 'a')],
        'reloptions': [('public', 'u', [
            "ttl='on'", "ttl_expire_after='1 day':::INTERVAL",
            'schema_locked=true'], 'a table')],
        'SHOW CREATE ALL TABLES': [(
            'CREATE TABLE public.u (\n\tid INT8 NOT NULL,\n'
            "\tsecret STRING NOT VISIBLE NULL DEFAULT 'x':::STRING "
            "ON UPDATE 'y':::STRING,\n\tFAMILY f1 (id, secret)\n);",)],
    })
    rows = {item['resource_id']: item['native']
            for item in _annotate_catalog(Connection(cursor), values)}
    secret = rows['column:public:u:secret']
    assert (secret['hidden'], secret['not_visible'], secret['on_update'],
            secret['family'], secret['comment'], secret['default']) == (
        False, True, "'y'", 'f1', 'kept', "'x'")
    assert rows['column:public:u:crdb_internal_expiration']['hidden']
    assert rows['column:public:u:id']['identity'] == 'ALWAYS'
    table = rows['table:public:u']
    assert (table['ttl_expire_after'], table['schema_locked'],
            table['comment'], table['constraints']) == (
        '1 day', True, 'a table',
        [{'name': 'u_pkey', 'kind': 'PRIMARY KEY', 'columns': ['id']}])
