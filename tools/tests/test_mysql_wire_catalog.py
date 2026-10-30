"""The shared MySQL-wire catalog reader used by Dolt, TiDB and Vitess."""
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.distributed_sql import (  # noqa: E402
    mysql_catalog, mysql_constraint_details, mysql_default_expression,
    mysql_procedures,
)
from pgadmin.cdeadmin.providers.vitess.provider import (  # noqa: E402
    _catalog as vitess_catalog, _extras as vitess_extras,
)


class Cursor:
    """Answers each catalog query by a substring of its SQL."""

    def __init__(self, answers):
        self.answers, self.rows, self.seen = answers, [], []

    def execute(self, source, parameters=()):
        self.seen.append((source, tuple(parameters)))
        for needle, rows in self.answers.items():
            if needle in source:
                if isinstance(rows, Exception):
                    raise rows
                self.rows = rows
                return
        self.rows = []

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


def native(rows, resource_id):
    item = next(row for row in rows if row['resource_id'] == resource_id)
    value = dict(item['native'])
    value.pop('definition', None)
    value.pop('navigator_parent_resource_id', None)
    return value


def test_defaults_render_as_the_clause_an_editor_writes_back():
    assert mysql_default_expression('varchar(40)', 'x', '') == "'x'"
    assert mysql_default_expression('varchar(9)', "it's", '') == "'it''s'"
    assert mysql_default_expression('int', '5', '') == '5'
    assert mysql_default_expression('decimal(5,2)', '1.50', '') == '1.50'
    assert mysql_default_expression(
        'int', '(1 + 1)', 'DEFAULT_GENERATED') == '(1 + 1)'
    # TiDB reports CURRENT_TIMESTAMP without DEFAULT_GENERATED.
    assert mysql_default_expression(
        'datetime', 'CURRENT_TIMESTAMP', '') == 'CURRENT_TIMESTAMP'
    assert mysql_default_expression('int', None, '') is None


def test_columns_keep_definition_order_and_indexes_their_columns():
    cursor = Cursor({
        'information_schema.TABLES': [('db', 't', 'BASE TABLE')],
        'ORDINAL_POSITION, COLUMN_DEFAULT': [
            ('db', 't', 'id', 'int', 'NO', 1, None, 'PRI', ''),
            ('db', 't', 'label', 'varchar(20)', 'YES', 2, 'x', '', ''),
        ],
        'SEQ_IN_INDEX': [
            # TiDB returns NON_UNIQUE as a string.
            ('db', 't', 'PRIMARY', '0', 'BTREE', 1, 'id'),
            ('db', 't', 'ix', '1', 'BTREE', 1, 'label'),
            ('db', 't', 'ix', '1', 'BTREE', 2, 'id'),
        ],
    })
    rows = mysql_catalog(Connection(cursor), {}, 'Engine')
    columns = [row['display_name'] for row in rows
               if row['resource_kind'] == 'column']
    assert columns == ['id', 'label']
    assert native(rows, 'column:db:t:label') == {
        'data_type': 'varchar(20)', 'is_nullable': 'YES',
        'ordinal_position': 2, 'column_default': 'x',
        'default_expression': "'x'", 'column_key': '', 'extra': ''}
    assert native(rows, 'index:db:t:PRIMARY') == {
        'unique': True, 'index_type': 'BTREE', 'columns': ['id']}
    assert native(rows, 'index:db:t:ix') == {
        'unique': False, 'index_type': 'BTREE', 'columns': ['label', 'id']}


def test_narrow_catalogs_fall_back_to_the_previous_columns():
    refused = RuntimeError('unknown column')
    cursor = Cursor({
        'information_schema.TABLES': [('db', 't', 'BASE TABLE')],
        'ORDINAL_POSITION, COLUMN_DEFAULT': refused,
        'IS_NULLABLE FROM information_schema.COLUMNS': [
            ('db', 't', 'id', 'int', 'NO')],
        'SEQ_IN_INDEX': refused,
        'SELECT DISTINCT': [('db', 't', 'PRIMARY', 0, 'BTREE')],
    })
    rows = mysql_catalog(Connection(cursor), {}, 'Engine')
    assert native(rows, 'column:db:t:id') == {
        'data_type': 'int', 'is_nullable': 'NO'}
    assert native(rows, 'index:db:t:PRIMARY') == {
        'unique': True, 'index_type': 'BTREE'}


def test_procedures_carry_parameters_and_skip_functions():
    cursor = Cursor({
        'information_schema.PARAMETERS': [
            ('ks', 'p', 'IN', 'a', 'int'), ('ks', 'p', 'OUT', 'b', 'text')],
        'information_schema.ROUTINES': [
            ('ks', 'p', 'PROCEDURE', '', 'begin end', 'DEFINER', 'NO',
             'CONTAINS SQL', ''),
            ('ks', 'f', 'FUNCTION', 'int', 'return 1', 'DEFINER', 'YES',
             'NO SQL', '')],
    })
    assert mysql_procedures(cursor) == [('ks', 'p', {
        'routine_type': 'PROCEDURE', 'data_type': '', 'body': 'begin end',
        'parameters': [{'name': 'a', 'type': 'int', 'mode': 'IN'},
                       {'name': 'b', 'type': 'text', 'mode': 'OUT'}],
        'sql_security': 'DEFINER', 'deterministic': False,
        'data_access': 'CONTAINS SQL', 'comment': ''})]
    assert all(parameters == () for _source, parameters in cursor.seen)


def test_procedures_for_one_schema_name_it_in_both_queries():
    # Vitess routes information_schema reads by the schema predicate.
    cursor = Cursor({})
    assert mysql_procedures(cursor, 'lookup_keyspace') == []
    assert [parameters for _source, parameters in cursor.seen] == [
        ('lookup_keyspace',), ('lookup_keyspace',)]
    assert all('SCHEMA = %s' in source for source, _ in cursor.seen)


def test_without_a_schema_the_catalog_sql_is_unchanged():
    cursor = Cursor({})
    mysql_catalog(Connection(cursor), {}, 'Engine')
    mysql_constraint_details(cursor)
    assert all(parameters == () for _source, parameters in cursor.seen)
    assert not any('= %s' in source for source, _ in cursor.seen)


def test_one_schema_is_one_equality_predicate_on_every_read():
    cursor = Cursor({})
    mysql_catalog(Connection(cursor), {}, 'Engine', schema='ks')
    mysql_constraint_details(cursor, 'ks')
    assert len(cursor.seen) == 9
    assert all(parameters == ('ks',) for _source, parameters in cursor.seen)
    assert all('SCHEMA = %s' in source for source, _ in cursor.seen)


class Vtgate(Cursor):
    """vtgate's information_schema routing (live, 23.0.3): an equality
    predicate naming a keyspace reads that keyspace, no predicate reads the
    session keyspace, and an IN list of keyspaces reads nothing."""

    session = 'sharded'

    def __init__(self, answers, keyspaces):
        super().__init__(answers)
        self.keyspaces = keyspaces

    def execute(self, source, parameters=()):
        self.seen.append((source, tuple(parameters)))
        if 'information_schema' not in source:
            return super().execute(source, parameters)
        if ' IN (' in source:
            self.rows = []
            return
        keyspace = parameters[0] if parameters else self.session
        self.rows = []
        for needle, rows in self.keyspaces.get(keyspace, {}).items():
            if needle in source:
                self.rows = rows
                return


def test_vitess_catalog_reads_every_keyspace_once():
    cursor = Vtgate({
        'SHOW VITESS_KEYSPACES': [('sharded',), ('lookup',)],
        'SHOW VITESS_SHARDS': [('sharded/-80',), ('sharded/80-',),
                               ('lookup/-',)],
        'FROM `lookup`.`ids` WHERE id = 0': [(500, 50)],
    }, {
        'sharded': {
            "TABLE_COMMENT = 'vitess_sequence'": [],
            'information_schema.TABLES': [
                ('vt_sharded', 'orders', 'BASE TABLE')],
            'SEQ_IN_INDEX': [
                ('vt_sharded', 'orders', 'PRIMARY', 0, 'BTREE', 1, 'a'),
                ('vt_sharded', 'orders', 'PRIMARY', 0, 'BTREE', 2, 'b')],
        },
        'lookup': {
            "TABLE_COMMENT = 'vitess_sequence'": [('vt_lookup', 'ids')],
            'information_schema.TABLES': [
                ('vt_lookup', 'ids', 'BASE TABLE')],
        },
    })
    rows = vitess_catalog(Connection(cursor), {
        'route': {'database': 'sharded'}})
    found = {row['resource_id'] for row in rows}
    assert {'table:sharded:orders', 'table:lookup:ids',
            'sequence:lookup:ids'} <= found
    # One read per keyspace: a two-column key keeps two columns.
    assert native(rows, 'index:sharded:orders:PRIMARY')['columns'] == [
        'a', 'b']
    sequence = native(rows, 'sequence:lookup:ids')
    assert (sequence['next_id'], sequence['cache']) == (500, 50)
    assert not any(' IN (' in source for source, _ in cursor.seen)


def test_vitess_migration_keeps_every_shard_state():
    def row(shard, status, ready):
        value = [None] * 53
        value[1:9] = ['m1', 'ks', shard, 'vt_ks', 't', 'alter table t',
                      'vitess', '']
        value[16], value[44] = status, ready
        return tuple(value)

    cursor = Cursor({'SHOW VITESS_MIGRATIONS': [
        row('80-', 'running', 0), row('-80', 'complete', 1)]})
    record = next(item for item in vitess_extras(cursor, {}, 'g', {'ks'})
                  if item['resource_kind'] == 'online-ddl')
    assert record['resource_id'] == 'online-ddl:ks:m1'
    assert record['native']['status'] == 'mixed'
    assert record['native']['ready_to_complete'] is False
    assert [(item['shard'], item['status'])
            for item in record['native']['shards']] == [
        ('-80', 'complete'), ('80-', 'running')]
