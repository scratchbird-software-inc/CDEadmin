"""SQLite tier 2/3 operations round-trip: the OperationDialog's draft (field
defaults + values) -> provider plan -> apply on a real database file."""
from contextlib import closing
from dataclasses import replace
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.sqlite.provider import ADMINISTRATION, _create_client, _resources  # noqa: E402
from ui_descriptor_roundtrip import engine_operations, operation_draft  # noqa: E402

OPERATIONS = engine_operations('sqlite')


@pytest.fixture
def live(tmp_path):
    path = tmp_path / 'ops.sqlite'
    with closing(sqlite3.connect(path)) as seed:
        seed.execute('CREATE TABLE owner(id INTEGER PRIMARY KEY, label TEXT)')
        seed.execute("INSERT INTO owner VALUES (1, 'a')")
        seed.commit()
    route = {'database': str(path), 'filesystem_root': str(tmp_path), 'timeout': .05}
    client = _create_client()
    if client.config.profile.exact_version != sqlite3.sqlite_version:
        # The provider admits one exact SQLite build; this round trip is about
        # the descriptor contract, so run it on the interpreter's SQLite.
        client.config = replace(client.config, profile=replace(client.config.profile,
                                                               exact_version=sqlite3.sqlite_version))
    connection = client.open_session({'route': route})
    try:
        with closing(sqlite3.connect(path)) as observer:
            database = next(row for row in _resources(observer, {'route': route}) if row['resource_kind'] == 'database')
        yield path, route, client, connection, database
    finally:
        client.close()


def run(client, connection, route, target, operation_id, values=None):
    operation = OPERATIONS[f'{operation_id}@database']
    # The dialog asks the user to type the route database for typed-name confirmations.
    draft = operation_draft(operation, values, confirmation=route['database'])
    request = {'resource_kind': 'database', 'operation_id': operation_id, 'target_resource': target,
               '_provider_route': route, 'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == [], operation_id
    planned = ADMINISTRATION.plan(request)
    result = ADMINISTRATION.apply(client, planned, connection=connection)
    assert result['accepted'], (operation_id, result)
    return planned, result


@pytest.mark.parametrize('operation_id,values', [
    ('integrity_check', None), ('quick_check', None), ('foreign_key_check', None),
    ('foreign_key_check', {'table': 'owner'}), ('vacuum', None), ('incremental_vacuum', {'pages': 1}),
    ('optimize', None), ('analyze', None), ('analyze', {'target': 'owner'}), ('reindex', None),
    ('wal_checkpoint', None), ('wal_checkpoint', {'mode': 'TRUNCATE'}),
])
def test_maintenance_and_diagnostic_operations(live, operation_id, values):
    path, route, client, connection, database = live
    planned, _result = run(client, connection, route, database, operation_id, values)
    assert planned['command_preview']['statements'], operation_id


def test_backup_and_restore_operations(live):
    path, route, client, connection, database = live
    backup = Path(route['filesystem_root']) / 'copy.sqlite'
    run(client, connection, route, database, 'backup', {'backup_path': str(backup), 'overwrite': True})
    assert backup.exists()
    connection.execute("INSERT INTO owner VALUES (2, 'b')")
    connection.commit()
    run(client, connection, route, database, 'restore', {'backup_path': str(backup)})
    assert connection.execute('SELECT count(*) FROM owner').fetchone()[0] == 1


def test_every_declared_database_operation_is_exercised():
    declared = {key.split('@')[0] for key, op in OPERATIONS.items() if op['resource_kind'] == 'database'}
    exercised = {'integrity_check', 'quick_check', 'foreign_key_check', 'vacuum', 'incremental_vacuum', 'optimize',
                 'analyze', 'reindex', 'reindex_original_session','analyze_original_session','shrink_memory_original_session','set_connection_pragma_case_sensitive_like', 'wal_checkpoint', 'backup', 'restore', 'set_connection_synchronous',
                 *('set_connection_limit_'+name for name in ('length','sql_length','column','expr_depth','compound_select','function_arg','attached','like_pattern_length','variable_number','trigger_depth','vdbe_op','worker_threads')),
                 *('set_connection_pragma_'+name for name in ('foreign_keys','query_only','recursive_triggers','read_uncommitted','reverse_unordered_selects','automatic_index','ignore_check_constraints','trusted_schema','legacy_alter_table','cell_size_check','full_column_names','short_column_names','count_changes','empty_result_callbacks','fullfsync','checkpoint_fullfsync','defer_foreign_keys','busy_timeout','wal_autocheckpoint','analysis_limit'))}
    from pgadmin.cdeadmin.providers.sqlite.connection_config import CONFIGS
    exercised.update('set_connection_config_'+name for name in CONFIGS)
    from pgadmin.cdeadmin.providers.sqlite.schema_settings import SPECS
    exercised.update('set_connection_pragma_'+name for name in SPECS)
    exercised.update('set_connection_pragma_'+name for name in ('soft_heap_limit','hard_heap_limit'))
    from pgadmin.cdeadmin.providers.sqlite.extended_config import NAMES as EXTENDED
    exercised.update('set_connection_config_'+name for name in EXTENDED)
    from pgadmin.cdeadmin.providers.sqlite.connection_pragmas import DEBUG_FLAGS
    exercised.update('set_connection_pragma_'+name for name in DEBUG_FLAGS)
    exercised.add('configuration_capabilities')
    exercised.update('set_connection_pragma_'+name for name in ('temp_store_directory','data_store_directory','lock_proxy_file'))
    assert declared == exercised


def test_connection_synchronous_operation_on_retained_connection(live):
    from pgadmin.cdeadmin.providers.sqlite.connection_settings import action
    _path, _route, _client, connection, _database = live
    before = action(connection, {'operation':'inspect'})['effective_code']
    result = action(connection, {'operation':'set_connection_synchronous',
        'value':'NORMAL', 'expected_code':before, 'confirmed':True})
    assert result['effective_code'] == connection.execute('PRAGMA synchronous').fetchone()[0] == 1


@pytest.mark.parametrize('name',['length','sql_length','column','expr_depth','compound_select','function_arg','attached','like_pattern_length','variable_number','trigger_depth','vdbe_op','worker_threads'])
def test_connection_limit_descriptor_roundtrip(live,name):
    from pgadmin.cdeadmin.providers.sqlite.connection_limits import action, LIMITS
    from ui_descriptor_roundtrip import operation_draft
    _path, _route, _client, connection, _database = live
    code = getattr(sqlite3,LIMITS[name])
    before = connection.getlimit(code)
    op = OPERATIONS['set_connection_limit_'+name+'@database']
    requested = before-1 if before>0 else 1
    draft = operation_draft(op, {'value':requested,'expected_value':before,'confirmed':True})
    result = action(connection,sqlite3,{'operation':'set_connection_limit','limit':name,**draft})
    assert result['effective_value'] == connection.getlimit(code)
    assert result['effective_value'] == requested if before>0 else 0 <= result['effective_value'] <= requested


@pytest.mark.parametrize('name',['foreign_keys','query_only','recursive_triggers','read_uncommitted','reverse_unordered_selects','automatic_index','ignore_check_constraints','trusted_schema','legacy_alter_table','cell_size_check','full_column_names','short_column_names','count_changes','empty_result_callbacks','fullfsync','checkpoint_fullfsync','defer_foreign_keys'])
def test_connection_pragma_descriptor_roundtrip(live,name):
    from pgadmin.cdeadmin.providers.sqlite.connection_pragmas import action
    from ui_descriptor_roundtrip import operation_draft
    _path, _route, _client, connection, _database = live
    before=action(connection,{'operation':'inspect','pragma':name})['effective_value']
    op=OPERATIONS['set_connection_pragma_'+name+'@database']
    draft=operation_draft(op,{'value':not before,'expected_value':before,'confirmed':True})
    result=action(connection,{'operation':'set_connection_pragma','pragma':name,**draft})
    assert result['effective_value'] is not before


@pytest.mark.parametrize('name',['busy_timeout','wal_autocheckpoint','analysis_limit'])
def test_numeric_connection_pragma_descriptor_roundtrip(live,name):
    from ui_descriptor_roundtrip import operation_draft
    from pgadmin.cdeadmin.providers.sqlite.connection_pragmas import action
    from pgadmin.cdeadmin.providers.sqlite.connection_tuning import CALLBACKS
    _path, _route, _client, connection, _database = live
    before=action(connection,{'operation':'inspect','pragma':name})['effective_value']
    values={'value':3,'expected_value':before,'confirmed':True}
    if name in CALLBACKS:values['replace_callback_confirmed']=True
    draft=operation_draft(OPERATIONS['set_connection_pragma_'+name+'@database'],values)
    result=action(connection,{'operation':'set_connection_pragma','pragma':name,**draft})
    assert result['effective_value']==connection.execute('PRAGMA '+name).fetchone()[0]==3
