"""Native lazy module discovery, authorization, masking and caller ownership."""
from contextlib import closing
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client, _resources
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.table_functions import discover, inventory
from pgadmin.cdeadmin.providers.native_editor import metadata
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog


def test_lazy_native_modules_include_hidden_arguments_without_running_wrapped_pragmas(tmp_path):
    connection = sqlite3.connect(tmp_path / 'native.sqlite', factory=SQLiteConnection)
    calls = []; pragmas = []
    try:
        connection.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY,body TEXT)')
        connection.execute("INSERT INTO owned VALUES(1,'committed')"); connection.commit()
        source_id = connection.execute('SELECT sqlite_source_id()').fetchone()[0]
        initial = {row[0] for row in connection.execute('PRAGMA module_list')}
        assert 'json_each' not in initial
        connection.create_function('sqlite_version', 0, lambda: calls.append('version') or 'poisoned')
        connection.create_function('sqlite_source_id', 0, lambda: calls.append('source') or 'poisoned')
        connection.execute('BEGIN'); connection.execute("INSERT INTO owned VALUES(2,'pending')")
        connection.execute('SAVEPOINT retained'); connection.execute('PRAGMA defer_foreign_keys=ON')
        def policy(action, first, second, *_args):
            if action == sqlite3.SQLITE_PRAGMA: pragmas.append((first, second))
            return sqlite3.SQLITE_OK
        connection.set_authorizer(policy)
        resources = _resources(connection, {})
        functions = {row['native']['name']: row for row in resources if row['native'].get('function_type') == 'table'}
        for name in ('json_each', 'json_tree', 'jsonb_each', 'jsonb_tree', 'carray', 'dbstat', 'sqlite_dbpage', 'pragma_table_info', 'pragma_table_xinfo'):
            assert name in functions, name
            observation = functions[name]['native']['table_function_observation']
            assert observation['available'] and observation['observation_complete'], observation
        columns = functions['json_each']['native']['table_function_observation']['scopes'][0]['columns']
        assert [row['name'] for row in columns if row['hidden']] == ['json', 'root']
        assert not any(name in {'wal_checkpoint', 'optimize', 'incremental_vacuum', 'integrity_check'} for name, _value in pragmas)
        assert not calls and connection._cdeadmin_authorizer is policy
        root = next(row for row in resources if row['resource_kind'] == 'database')
        assert root['native']['sqlite_source_id'] == source_id and root['native']['sqlite_runtime_version'] == '3.53.0'
        assert connection.in_transaction and connection.execute('PRAGMA defer_foreign_keys').fetchone() == (1,)
        connection.execute('ROLLBACK TO retained')
        assert connection.execute('SELECT count(*) FROM owned').fetchone() == (2,)
        connection.rollback()
        assert connection.execute('SELECT count(*) FROM owned').fetchone() == (1,)
        restored = read_catalog(json.dumps(build_export(resources, endpoint_id='endpoint', target_id='file',
            generation='native', include_system=True, engine='sqlite')['snapshot']), engine='sqlite')
        assert any(row['native'].get('name') == 'json_each' and row['native'].get('function_type') == 'table'
                   for row in restored['rows'].values())
    finally: connection.close()


def test_real_relation_masking_and_schema_priority_do_not_invent_function_columns(tmp_path):
    connection = sqlite3.connect(tmp_path / 'main.sqlite', factory=SQLiteConnection)
    try:
        connection.execute('CREATE TEMP TABLE json_each(owned_temp TEXT)')
        connection.execute('CREATE TABLE json_tree(owned_main TEXT)')
        connection.execute('ATTACH DATABASE ? AS other', (str(tmp_path / 'other.sqlite'),))
        connection.execute('CREATE TABLE other.pragma_table_info(owned_attached TEXT)')
        observed = metadata(connection, 'sqlite')
        assert observed['context']['search_path'] == ['temp', 'main', 'other']
        functions = {tuple(row['display_path']) for row in observed['resources'] if row.get('table_valued')}
        for name in ('json_each', 'json_tree', 'pragma_table_info'):
            assert (name,) not in functions
        assert ('main', 'json_each') in functions and ('temp', 'json_each') not in functions
        assert ('temp', 'json_tree') in functions and ('main', 'json_tree') not in functions
        assert ('main', 'pragma_table_info') in functions and ('other', 'pragma_table_info') not in functions
        for source in ("SELECT * FROM json_each('{}')", "SELECT * FROM json_tree('{}')", "SELECT * FROM pragma_table_info('owned')"):
            try: connection.execute(source)
            except sqlite3.OperationalError: pass
            else: raise AssertionError('Native ordinary relation did not mask a table-function invocation')
        assert connection.execute("SELECT key FROM main.json_each('{\"snow\":7}')").fetchall() == [('snow',)]
    finally: connection.close()


def test_denied_table_function_observation_is_retained_and_marks_catalog_incomplete(tmp_path):
    path = tmp_path / 'denied.sqlite'
    with closing(sqlite3.connect(path)) as seed: seed.execute('CREATE TABLE owned(id INTEGER)')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    connect = provider.client._connect
    def policy(action, first, second, *_args):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_PRAGMA and first == 'table_xinfo' and str(second).strip('"') == 'json_each' else sqlite3.SQLITE_OK
    def guarded(payload):
        connection = connect(payload); connection.set_authorizer(policy); return connection
    provider.client._connect = guarded
    try:
        result = provider.capture_catalog({'database': str(path), 'filesystem_root': str(tmp_path)}, include_system=True)
        denied = next(row for row in result['resources'] if row['native'].get('name') == 'json_each' and row['native'].get('function_type') == 'table')
        observation = denied['native']['table_function_observation']
        assert not observation['observation_complete'] and not observation['available']
        assert observation['scopes'][0]['native_error_code'] == sqlite3.SQLITE_AUTH
        assert result['complete'] is False
        root = next(row for row in result['resources'] if row['resource_kind'] == 'database')
        assert any(denied['resource_id'] in item.get('unavailable_resource_ids', []) for item in root['native']['catalog_observations'])
        assert any(row['display_name'] == 'owned' for row in result['resources'])
    finally: provider.close()


def test_module_inventory_uses_native_pragma_when_a_user_table_masks_its_wrapper():
    connection = sqlite3.connect(':memory:')
    try:
        connection.execute('CREATE TABLE pragma_module_list(name TEXT)')
        connection.execute("INSERT INTO pragma_module_list VALUES('forged_loaded_module')")
        resources = _resources(connection, {})
        modules = {row['display_name'] for row in resources if row['resource_kind'] == 'extension'}
        assert 'forged_loaded_module' not in modules and 'fts5' in modules
        assert 'json_each' in inventory()
    finally: connection.close()
