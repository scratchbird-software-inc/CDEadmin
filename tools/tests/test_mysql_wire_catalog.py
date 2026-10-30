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
    mysql_catalog, mysql_default_expression,
)


class Cursor:
    """Answers each catalog query by a substring of its SQL."""

    def __init__(self, answers):
        self.answers, self.rows = answers, []

    def execute(self, source, _parameters=()):
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
