"""Host-side dialect row SQL compilation across all six core engines."""
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.workspace.data_surface_host import compile_host_row_sql  # noqa: E402


def test_postgresql_host_row_sql_variants():
    cols = [{'name': 'id'}, {'name': 'payload'}, {'name': 'raw'}]
    row = {'id': 7, 'payload': {'status': 'ok'}, 'raw': {'encoding': 'base64', 'data': 'SGk='}}

    upsert = compile_host_row_sql('postgresql', '"public"."events"', cols, [row], mode='upsert', key_columns=['id'])
    assert upsert['compiled_on_host'] is True
    assert 'ON CONFLICT ("id") DO UPDATE' in upsert['sql']
    assert '\'{"status": "ok"}\'::jsonb' in upsert['sql']
    assert "decode('SGk=', 'base64')" in upsert['sql']
    assert 'RETURNING *;' in upsert['sql']

    ovr = compile_host_row_sql('postgresql', '"public"."events"', cols, [row], mode='insert_overriding')
    assert 'OVERRIDING SYSTEM VALUE' in ovr['sql']


def test_sqlite_host_row_sql_variants():
    cols = [{'name': 'id'}, {'name': 'big'}, {'name': 'blob_col'}]
    row = {'id': 1, 'big': {'int64': '9007199254740995'}, 'blob_col': {'encoding': 'base64', 'data': 'SGk='}}

    upsert = compile_host_row_sql('sqlite', '"main"."items"', cols, [row], mode='upsert', key_columns=['id'])
    assert 'ON CONFLICT ("id") DO UPDATE' in upsert['sql']
    assert '9007199254740995' in upsert['sql']
    assert "X'4869'" in upsert['sql']

    ign = compile_host_row_sql('sqlite', '"main"."items"', cols, [row], mode='ignore')
    assert ign['sql'].startswith('INSERT OR IGNORE INTO "main"."items"')


def test_duckdb_host_row_sql_variants_and_nested_containers():
    cols = [{'name': 'id'}, {'name': 'big'}, {'name': 'tags'}, {'name': 'kv'}, {'name': 'u'}, {'name': 'raw'}]
    row = {
        'id': 42,
        'big': {'hugeint': '170141183460469231731687303715884105727'},
        'tags': ['alpha', 'beta'],
        'kv': {'duckdb_type': 'MAP', 'entries': [{'key': 'k1', 'value': 10}]},
        'u': {'duckdb_type': 'UNION', 'tag': 'txt', 'value': 'hello'},
        'raw': {'encoding': 'base64', 'data': 'SGk='},
    }

    upsert = compile_host_row_sql('duckdb', '"main"."metrics"', cols, [row], mode='upsert', key_columns=['id'])
    assert '170141183460469231731687303715884105727' in upsert['sql']
    assert "['alpha', 'beta']" in upsert['sql']
    assert "MAP(['k1'], [10])" in upsert['sql']
    assert 'union_value("txt" := \'hello\')' in upsert['sql']
    assert "from_hex('4869')" in upsert['sql']

    copy_stmt = compile_host_row_sql('duckdb', '"main"."metrics"', cols, [row], mode='copy_parquet', key_columns=['id'])
    assert "TO 'row_export.parquet' (FORMAT PARQUET);" in copy_stmt['sql']


def test_mysql_and_mariadb_host_row_sql_bound_and_inline():
    cols = [{'name': 'id'}, {'name': 'note'}]
    rows = [{'id': 5, 'note': 'alpha'}, {'id': None, 'note': 'beta'}]

    upd = compile_host_row_sql(
        'mysql', '`orders`', cols, [rows[0]],
        mode='update', key_columns=['id'], inline_literals=False,
    )
    assert upd['sql'] == 'UPDATE `orders` SET `note` = %s WHERE `id` <=> %s;'
    assert upd['parameters'] == ['alpha', 5]

    in_q = compile_host_row_sql(
        'mariadb', '`orders`', cols, rows,
        mode='in', in_column='id', inline_literals=True,
    )
    assert in_q['sql'] == 'SELECT * FROM `orders` WHERE `id` IN (5) OR `id` IS NULL;'


def test_firebird_host_row_sql_bound_and_inline():
    cols = [{'name': 'ID'}, {'name': 'PAYLOAD'}]
    row = {'values': {'ID': 9, 'PAYLOAD': {'encoding': 'base64', 'data': 'SGk='}}}

    upsert_bound = compile_host_row_sql(
        'firebird', 'ITEMS', cols, [row],
        mode='upsert', key_columns=['ID'], inline_literals=False,
    )
    assert 'UPDATE OR INSERT INTO ITEMS (ID, PAYLOAD) VALUES (?, ?) MATCHING (ID);' == upsert_bound['sql']
    assert len(upsert_bound['plans']) == 1
    assert upsert_bound['plans'][0]['parameters'][0] == 9

    upd_inline = compile_host_row_sql(
        'firebird', 'ITEMS', cols, [row],
        mode='update', key_columns=['ID'], inline_literals=True,
    )
    assert "SET PAYLOAD = X'4869' WHERE ID IS NOT DISTINCT FROM 9;" in upd_inline['sql']
