"""Native all-channel commands and irreversible reset qualification on owned server."""
import pytest
from test_mariadb_server_diagnostics import native
from test_mariadb_key_caches import plan,execute
from pgadmin.cdeadmin.sdk import RelationalClientError


def test_native_all_channels_and_default_reset(native):
    n=native
    channels=['','owned_one','owned_two']
    try:
        for index,channel in enumerate(channels):
            n.cursor.execute("CHANGE MASTER '"+channel+"' TO MASTER_HOST='127.0.0.1',MASTER_PORT="+str(9+index)+",MASTER_USER='owned_missing',MASTER_CONNECT_RETRY=1")
        for threads in ['IO_THREAD','SQL_THREAD','ALL']:
            started=execute(n,'start_all_replicas',threads=threads)
            assert len(started['after']['connections'])==3
            execute(n,'stop_all_replicas',threads=threads)
        execute(n,'stop_all_replicas')
        result=execute(n,'reset_default_replica',remove_configuration=True,configuration_loss_confirmed=True)
        assert [row[0]for row in result['after']['connections']]==['owned_one','owned_two']
    finally:
        n.cursor.execute('STOP ALL SLAVES')
        for channel in channels:n.cursor.execute("RESET SLAVE '"+channel+"' ALL")


def test_native_global_resets_and_original_transaction(native):
    n=native
    n.cursor.execute('START TRANSACTION');n.cursor.execute('INSERT INTO observer_pending VALUES(59)');n.cursor.execute('SAVEPOINT caller')
    execute(n,'reset_query_cache')
    result=execute(n,'reset_binary_logs',next_log_number='9',history_loss_confirmed=True)
    assert result['after']['binary_log_names']==['sr-owned.000009']
    n.cursor.execute('ROLLBACK TO SAVEPOINT caller');n.cursor.execute('SELECT * FROM observer_pending');assert n.cursor.fetchall()==[(59,)]
    n.handle.rollback()


def test_native_reset_confirmation_and_stale_topology(native):
    n=native
    with pytest.raises(RelationalClientError,match='history loss'):plan(n,'reset_binary_logs')
    with pytest.raises(RelationalClientError,match='configuration loss'):plan(n,'reset_default_replica',remove_configuration=True)
    reviewed=plan(n,'stop_all_replicas')
    try:
        n.cursor.execute("CHANGE MASTER 'owned_stale' TO MASTER_HOST='127.0.0.1',MASTER_PORT=9,MASTER_USER='owned_missing'")
        with pytest.raises(RelationalClientError)as error:n.client.apply_admin_operation(reviewed)
        assert not error.value.native_dispatched and error.value.connection_release['connection_released']
    finally:n.cursor.execute("RESET SLAVE 'owned_stale' ALL")
