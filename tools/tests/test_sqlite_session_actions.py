"""Native retained-connection controls preserve exact names and native rules."""
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.providers.sqlite.native_helpers import helper_supported
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.session_actions import action
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError


@pytest.fixture
def native():
    library=os.environ.get('CDEADMIN_SQLITE_SESSION_LIBRARY')
    if not library or not Path(library).is_file() or not helper_supported('session'):pytest.skip('Native session helper required (built, and supported by this SQLite runtime)')
    connection=sqlite3.connect(':memory:',factory=SQLiteConnection)
    client=SimpleNamespace(close=connection.close)
    def run(operation,**fields):return action(client,connection,{'operation':operation,**fields},library)
    try:yield connection,run,client
    finally:connection.close()


def test_inventory_is_lazy_and_unavailable_components_are_not_empty_capture_claims(native,tmp_path):
    connection,run,client=native
    result=action(client,connection,{'operation':'inventory'},str(tmp_path/'missing-library'))
    assert not result['helper_available'] and result['unavailable_reason'] and not result['native_context_initialized']
    assert connection._cdeadmin_session_api is None
    assert run('inventory')['helper_available'] and not run('inventory')['native_context_initialized']


def test_flags_observe_native_object_configuration_and_refuse_changes_after_attach(native):
    connection,run,_client=native
    capture=run('open',database='main')['capture']['capture_id']
    assert run('object_config',capture_id=capture,option='estimate_size',value=True)['capture']['estimate_size']
    assert run('object_config',capture_id=capture,option='track_rowids',value=True)['capture']['track_rowids']
    connection.execute('CREATE TABLE "native\n雪"(value TEXT)');connection.commit()
    run('attach',capture_id=capture,table_name='native\n雪')
    connection.execute('BEGIN');connection.execute('INSERT INTO "native\n雪" VALUES(?)',('Pending 😀',))
    with pytest.raises(SessionAPIError) as failure:run('object_config',capture_id=capture,option='track_rowids',value=False)
    assert failure.value.native_result_code==sqlite3.SQLITE_MISUSE and connection.in_transaction
    observed=run('configure',capture_id=capture,enabled=False,indirect=True)['capture']
    assert not observed['enabled'] and observed['indirect']
    with pytest.raises(SessionAPIError):run('configure',capture_id=capture,enabled=True,indirect='invalid')
    assert not run('status',capture_id=capture)['capture']['enabled']
    connection.rollback()


def test_native_diff_compares_attached_source_without_mutating_database_or_settling_transaction(native):
    connection,run,_client=native
    connection.execute('ATTACH ? AS "old 雪"',(':memory:',))
    connection.executescript('CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT); CREATE TABLE "old 雪".t(id INTEGER PRIMARY KEY,body TEXT); INSERT INTO "old 雪".t VALUES(1,\'before\'); INSERT INTO t VALUES(1,\'after\');')
    capture=run('open',database='main',estimate_size=True)['capture']['capture_id']
    run('attach',capture_id=capture,table_name='t');connection.execute('BEGIN')
    result=run('diff',capture_id=capture,source_database='old 雪',table_name='t')
    assert result['database_mutation'] is False and result['transaction_open'] and not result['capture']['empty']
    assert connection.execute('SELECT body FROM t').fetchone()==('after',)
    assert connection.execute('SELECT body FROM "old 雪".t').fetchone()==('before',)
    connection.rollback()


def test_capture_ownership_close_confirmation_and_live_controller_survives_missing_installed_file(native,tmp_path):
    connection,run,client=native
    one=run('open',database='main')['capture']['capture_id'];two=run('open',database='temp')['capture']['capture_id']
    page=run('inventory',offset=1,limit=1);assert page['total']==2 and page['captures'][0]['capture_id']==two
    with pytest.raises(SessionAPIError,match='another or closed'):run('status',capture_id='unknown-capture')
    with pytest.raises(SessionAPIError,match='Confirm'):run('close',capture_id=one,confirmed=False)
    assert run('close',capture_id=one,confirmed=True)['closed']
    assert run('status',capture_id=two)['capture']['empty']
    result=action(client,connection,{'operation':'inventory'},str(tmp_path/'missing-library'))
    assert result['helper_available'] and result['native_context_initialized'] and not result['installed_helper_available']


def test_invalid_capture_options_never_load_native_code(native):
    connection,run,_client=native
    with pytest.raises(SessionAPIError):run('open',database='main\x00other')
    with pytest.raises(SessionAPIError):run('open',database='main',track_rowids='yes')
    assert connection._cdeadmin_session_api is None
