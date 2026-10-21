"""Original-session diagnostics through authenticated execution/status APIs.

This qualifies MariaDB text/parameter execution and admitted MySQL independent
session-variable observation with both native client interfaces. Other retained
editor/catalog consumers and unavailable observer profiles remain separate gaps.
"""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import secrets
import re
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def native_fetch_matrix(route):
    """Native ERR must survive every cursor fetch port, text and binary."""
    import mariadb
    from mysql_qualification_support import _root_connection
    result = []
    control = _root_connection('mariadb', route['port']); query = control.cursor()
    try:
        for prepared in (False, True):
            for buffered in (False, True):
                for method in ('fetchone', 'fetchmany', 'fetchall'):
                    connection = mariadb.connect(**route)
                    cursor = connection.cursor(prepared=prepared, buffered=buffered)
                    observed = {'prepared': prepared, 'buffered': buffered, 'fetch': method}
                    assert cursor.cdeadmin_checked_fetch_errors is True
                    try:
                        cursor.cdeadmin_checked_fetch_errors = False
                    except AttributeError:
                        pass
                    else:
                        raise AssertionError('Native fetch capability must be read-only')
                    def run():
                        try:
                            if prepared:
                                cursor.execute('SELECT SLEEP(?)', (20,))
                            else:
                                cursor.execute('SELECT SLEEP(20)')
                            getattr(cursor, method)(*([2] if method == 'fetchmany' else []))
                        except mariadb.Error as exc:
                            observed.update(errno=exc.errno, sqlstate=exc.sqlstate)
                    worker = threading.Thread(target=run, daemon=True)
                    try:
                        worker.start(); deadline = time.monotonic() + 15
                        while True:
                            query.execute('SELECT INFO FROM information_schema.PROCESSLIST WHERE ID=' + str(int(connection.connection_id)))
                            row = query.fetchone()
                            if row and row[0] and 'SLEEP(' in row[0]:
                                break
                            assert time.monotonic() < deadline, observed
                            time.sleep(.01)
                        query.execute('KILL QUERY ' + str(int(connection.connection_id)))
                        worker.join(10)
                        assert not worker.is_alive(), observed
                        assert observed.get('errno') == 1317 and observed.get('sqlstate') == '70100', observed
                        result.append(observed)
                    finally:
                        worker.join(25)
                        cursor.close(); connection.close()
    finally:
        query.close(); control.close()
    return result


def qualify(engine, output, *, mysql_interface='pure'):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    proof = {'complete': False, 'full_product_complete': False,
             'engine': engine, 'history_testing': 'not run', 'checks': [],
             'scope': 'MySQL ' + mysql_interface + ' text/parameter/script execution with independent native session-variable observation' if engine == 'mysql' else
                      'MariaDB unbound and parameterized text'}
    paths = [str(Path(__file__).relative_to(ROOT)),
             'tools/driver_patches/mariadb-1.1.14-exact-temporals.patch',
             'tools/cdeadmin_build_mariadb_driver.py',
             'tools/development/native_verify.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/session_state.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_connections.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_values.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mysql_charsets.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mysql_connections.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mysql_session_variables.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mysql_values.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mysql_execution.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_execution.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
    if engine == 'mariadb':
        import mariadb
        proof['native_driver'] = {'version': mariadb.__version__,
            'module_sha256': hashlib.sha256(Path(mariadb._mariadb.__file__).read_bytes()).hexdigest(),
            'checked_fetch_capability': hasattr(mariadb._mariadb.cursor, 'cdeadmin_checked_fetch_errors')}
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False
    for key, value in {'DATA_DIR': 'app', 'SQLITE_PATH': 'app/application.db',
                       'SESSION_DB_PATH': 'app/sessions', 'STORAGE_DIR': 'app/storage',
                       'LOG_FILE': 'app/application.log', 'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure',
                       'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json'}.items():
        setattr(config, key, str(output / value))
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from flask import url_for
    from mysql_qualification_support import server, _root_connection
    if engine == 'mariadb':
        from mariadb_qualification_support import server
    app = create_app('ScratchRobin original native session diagnostics')
    app.PGADMIN_RUNTIME = False; app.PGADMIN_INT_KEY = ''; app.run_before_app_start()
    client = app.test_client(); session_id = None; released = False
    try:
        with server(output / 'fixture') as (route, _name, owned):
            if engine == 'mariadb':
                proof['native_fetch_matrix'] = native_fetch_matrix(route)
            oracle = _root_connection(engine, route['port']); oracle.autocommit = True
            cursor = oracle.cursor()
            try:
                password = secrets.token_urlsafe(32)
                cursor.execute("CREATE USER 'sr_diagnostics'@'%' IDENTIFIED BY %s", (password,))
                if engine == 'mysql':
                    cursor.execute("GRANT ALL PRIVILEGES ON sr_diagnostics.* TO 'sr_diagnostics'@'%'")
                    cursor.execute("GRANT SELECT ON performance_schema.variables_by_thread TO 'sr_diagnostics'@'%'")
                    cursor.execute("GRANT SELECT ON performance_schema.session_account_connect_attrs TO 'sr_diagnostics'@'%'")
                else:
                    cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_diagnostics'@'%'")
                cursor.execute('CREATE DATABASE sr_diagnostics')
                cursor.execute('CREATE TABLE sr_diagnostics.t(id INT PRIMARY KEY,value INT)')
                cursor.execute('INSERT INTO sr_diagnostics.t VALUES(1,1),(2,1)')
                # This routine changes policy before returning ERR. Last OK
                # flags cannot safely describe its current policy afterward.
                cursor.execute("CREATE PROCEDURE sr_diagnostics.fail_after_policy() BEGIN SET autocommit=0; SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='owned diagnostic'; END")
                selected = {**route, 'database': 'sr_diagnostics', 'autocommit': True,
                            'user': 'sr_diagnostics', 'credential_kinds': ['database_password']}
                if engine == 'mysql':
                    selected['use_pure'] = mysql_interface == 'pure'
                with app.test_request_context('/'):
                    user = User.query.first(); uid = user.id
                    group = ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility[engine].set(True, user_id=user.id)
                    registration = Server(user_id=user.id, servergroup_id=group.id, name='Native session diagnostics',
                        host=route['host'], port=route['port'], username='sr_diagnostics',
                        maintenance_db='sr_diagnostics', save_password=0)
                    registration._cde_endpoint_registration = registration_profile(engine + '-native')
                    registration._cde_endpoint_route_configuration = selected
                    db.session.add(registration); db.session.commit()
                    target = str(uuid.uuid4())
                    db.session.add(EndpointDatabaseTarget(id=target, endpoint_id=registration.endpoint_profile.id,
                        display_name='sr_diagnostics', database='sr_diagnostics', configuration='{}', active=1))
                    db.session.commit()
                    url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=registration.id)
                    verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=registration.id)
                with client.session_transaction() as session:
                    session['_user_id'] = str(uid); session['_fresh'] = True
                verified = client.post(verify, json={'password': password}).get_json()
                assert verified.get('success'), verified

                def post(action, **data):
                    response = client.post(url, json={'action': action, 'database_target_id': target, **data})
                    result = response.get_json()
                    assert response.status_code == 200 and result.get('success'), result
                    return result['data']

                session_id = post('open_session', language_profile=engine + '-sql')['session_id']
                if engine == 'mysql':
                    initial = post('transaction', session_id=session_id)['provider_payload']['session_variable_observer']
                    assert initial['admitted'] and initial['original_session_commands_sent'] == 0, initial
                    source_connection_id = int(initial['connection_id'])
                    cursor.execute("SET GLOBAL log_output='TABLE'")
                    cursor.execute('SET GLOBAL general_log=ON')
                    proof['independent_observer_admission'] = initial

                def observation():
                    value = post('transaction', session_id=session_id)['provider_payload']
                    assert value['connection_health_checked'] is False
                    assert value['observation_source'] == 'last-native-protocol-status'
                    return value

                def collect(occurrence):
                    deadline = time.monotonic() + 30; rows = []; final = None
                    while time.monotonic() < deadline:
                        result = post('poll', occurrence_id=occurrence)['occurrence']
                        payload = (result.get('result') or {}).get('extensions', {}).get(engine, {}).get('payload', {})
                        rows.extend(payload.get('rows') or [])
                        if result['operation']['terminal']:
                            final = payload; break
                        time.sleep(.01)
                    assert final is not None, 'Native execution did not terminate'
                    return rows, final

                source_requests = 0
                def sql(source, parameters=None, expected_errno=None):
                    nonlocal source_requests
                    source_requests += 1
                    started = post('execute', session_id=session_id, source=source,
                                   parameters=parameters or [], history_sensitive=True)
                    rows, final = collect(started['occurrence_id'])
                    assert not final.get('session_reuse_blocked'), final
                    if expected_errno is None:
                        assert not final.get('error'), final
                    assert (final.get('error') or {}).get('errno') == expected_errno, final
                    observation()  # Matches the desktop's automatic terminal refresh.
                    return rows

                assert observation()['autocommit'] is True
                for suffix in ('', ';', '; \n-- native tail\n', '; /* native tail */ \n'):
                    sql('UPDATE t SET value=value+1' + suffix)
                    counted = sql('SELECT ROW_COUNT()')
                    assert counted == [[2]], (suffix, counted)
                proof['checks'].append('row-count-survives-execution-and-automatic-status')
                sql('UPDATE t SET value=value+1')
                sql('GET DIAGNOSTICS @sr_native_rows=ROW_COUNT')
                assert sql('SELECT @sr_native_rows') == [[2]]
                proof['checks'].append('native-get-diagnostics-retains-previous-row-count')
                sql('SELECT absent_column FROM t', expected_errno=1054)
                unknown = observation()
                assert unknown['state'] == 'unknown' and unknown['connection_usable'] is True
                assert unknown['status_current'] is False and 'autocommit' not in unknown
                rows = sql('SHOW ERRORS')
                assert rows and rows[0][:2] == ['Error', 1054], rows
                proof['checks'].append('native-error-area-survives-ERR-and-automatic-status')
                # A native warning must survive repeated passive observations.
                sql("SELECT CAST('invalid-owned-number' AS SIGNED)")
                observation(); observation()
                warnings = sql('SHOW WARNINGS')
                assert warnings and warnings[0][1] == 1292, warnings
                proof['checks'].append('native-warning-area-survives-status-observation')
                sql('CALL fail_after_policy()', expected_errno=1644)
                unknown = observation()
                assert unknown['state'] == 'unknown' and 'autocommit' not in unknown
                refused = client.post(url, json={'action': 'transaction_action', 'database_target_id': target,
                    'session_id': session_id, 'transaction_action': 'autocommit_on'}).get_json()
                assert not refused.get('success'), refused
                # The refused toggle itself must not clear the native error.
                rows = sql('SHOW ERRORS')
                assert rows and rows[0][:2] == ['Error', 1644], rows
                assert observation()['autocommit'] is False
                proof['checks'].append('failed-routine-policy-is-unknown-until-fresh-native-status')
                sql('INSERT INTO t VALUES(99,99)')
                assert observation()['in_transaction'] is True
                post('transaction_action', session_id=session_id, transaction_action='rollback')
                assert observation()['in_transaction'] is False
                assert sql('SELECT COUNT(*) FROM t WHERE id=99') == [[0]]
                proof['checks'].append('explicit-rollback-retains-native-finality-and-status')
                if engine == 'mariadb':
                    sql('UPDATE t SET value=value+1')
                    assert sql('SELECT ROW_COUNT(),?', [42]) == [[2, 42]]
                    proof['checks'].append('bound-row-count-survives-execution-and-status')
                else:
                    supplied = "quote ' double \" slash \\ é\n"
                    for mode in ('', 'ANSI_QUOTES', 'NO_BACKSLASH_ESCAPES', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'):
                        sql("SET SESSION sql_mode='" + mode + "'")
                        for statement, bindings in [('SELECT ROW_COUNT(),%s AS supplied', [supplied]),
                                                    ('SELECT ROW_COUNT(),%(value)s AS supplied', {'value': supplied})]:
                            sql('UPDATE t SET value=value+1')
                            assert sql(statement, bindings) == [[2, supplied]], (mode, mysql_interface)
                    proof['checks'].append('positional-and-named-bound-row-count-retains-native-values-across-four-live-native-quote-modes')
                    sql("SET SESSION sql_mode=''")
                    assert sql('UPDATE t SET value=value+1; GET DIAGNOSTICS @sr_script_rows=ROW_COUNT; SELECT @sr_script_rows,%s', [42]) == [[2, 42]]
                    proof['checks'].append('native-row-count-survives-parameter-script-command-boundaries-without-original-session-language-probes')
                    sql('SET NAMES latin1 COLLATE latin1_general_cs')
                    for result_charset in ('latin1', 'NULL'):
                        sql('SET character_set_results=' + result_charset)
                        sql('UPDATE t SET value=value+1')
                        assert sql('SELECT ROW_COUNT(),%s AS `€cœur ÿ`', ['€ Œ œ Ÿ ÿ']) == [[2, '€ Œ œ Ÿ ÿ']]
                    sql('SET NAMES utf8mb4')
                    proof['checks'].append('independent-C-or-pure-charset-observation-preserves-native-latin1-identities-values-and-NULL-result-charset')
                    sql('UPDATE t SET value=value+1')
                    cursor.execute("REVOKE SELECT ON performance_schema.variables_by_thread FROM 'sr_diagnostics'@'%'")
                    started = post('execute', session_id=session_id, source='SELECT ROW_COUNT(),%s', parameters=[42], history_sensitive=True)
                    rows, final = collect(started['occurrence_id'])
                    error = final['error']
                    assert not rows and error['query_dispatch'] == 'not_started' and error['commands_dispatched'] == 0
                    assert error['original_diagnostics_preserved'] and error['native_observer_errno'] == 1142
                    assert not final['session_reuse_blocked']
                    cursor.execute("GRANT SELECT ON performance_schema.variables_by_thread TO 'sr_diagnostics'@'%'")
                    assert sql('SELECT ROW_COUNT(),%s', [42]) == [[2, 42]]
                    proof['checks'].append('observer-revocation-refuses-current-command-without-source-probes-and-native-row-count-survives-permission-restoration')
                    sql('UPDATE t SET value=value+1')
                    cursor.execute("SELECT PROCESSLIST_ID FROM performance_schema.session_connect_attrs WHERE ATTR_NAME='scratchrobin_observer' AND ATTR_VALUE=%s", (str(source_connection_id),))
                    observers = cursor.fetchall()
                    assert len(observers) == 1 and int(observers[0][0]) != source_connection_id, observers
                    cursor.execute('KILL CONNECTION ' + str(int(observers[0][0])))
                    started = post('execute', session_id=session_id, source='SELECT ROW_COUNT(),%s', parameters=[42], history_sensitive=True)
                    rows, final = collect(started['occurrence_id'])
                    assert not rows and final['error']['query_dispatch'] == 'not_started'
                    assert final['error']['original_diagnostics_preserved'] and not final['session_reuse_blocked']
                    assert sql('SELECT ROW_COUNT(),%s', [42]) == [[2, 42]]
                    proof['checks'].append('independent-observer-connection-loss-and-authenticated-renewal-preserve-original-transaction-and-diagnostics-without-user-command-replay')
                # Compare cancellation diagnostics with an independent raw
                # native session. MariaDB can return a successful SLEEP result
                # while retaining an interrupted-query condition in its area.
                cursor.execute('SELECT CONNECTION_ID()'); native_thread = cursor.fetchone()[0]
                control = _root_connection(engine, route['port'])
                control_cursor = control.cursor(); native_cancel = {}
                def raw_sleep():
                    try:
                        cursor.execute('SELECT SLEEP(20)')
                        native_cancel['rows'] = [list(row) for row in cursor.fetchall()]
                        native_cancel['error_number'] = None
                    except Exception as exc:
                        native_cancel['error_number'] = getattr(exc, 'errno', exc.args[0])
                    cursor.execute('SHOW ERRORS')
                    native_cancel['diagnostics'] = [list(row) for row in cursor.fetchall()]
                raw_worker = threading.Thread(target=raw_sleep, daemon=True)
                try:
                    raw_worker.start(); deadline = time.monotonic() + 15
                    while True:
                        control_cursor.execute('SELECT INFO FROM information_schema.PROCESSLIST WHERE ID=' + str(int(native_thread)))
                        row = control_cursor.fetchone()
                        if row and row[0] and 'SLEEP(20)' in row[0]:
                            break
                        assert time.monotonic() < deadline, 'Raw native query did not start'
                        time.sleep(.02)
                    control_cursor.execute('KILL QUERY ' + str(int(native_thread)))
                    raw_worker.join(10)
                    assert not raw_worker.is_alive(), 'Raw native cancellation did not finish'
                finally:
                    control_cursor.close(); control.close()
                    raw_worker.join(25)
                proof['native_cancellation_control'] = native_cancel
                started = post('execute', session_id=session_id, source='SELECT SLEEP(20)',
                               parameters=[], history_sensitive=True)
                deadline = time.monotonic() + 15
                while True:
                    cursor.execute("SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE USER='sr_diagnostics' AND INFO LIKE '%SLEEP(20)%'")
                    if cursor.fetchone()[0]:
                        break
                    assert time.monotonic() < deadline, 'Native query did not start'
                    time.sleep(.02)
                cancelled_at = time.monotonic()
                post('cancel', occurrence_id=started['occurrence_id'])
                _rows, cancelled = collect(started['occurrence_id'])
                assert time.monotonic() - cancelled_at < 10
                assert cancelled['cancelled'] and not cancelled['session_reuse_blocked'], cancelled
                # Match the native response and condition area separately;
                # the application's cancellation flag is not a server ERR.
                assert (cancelled.get('error') or {}).get('errno') == native_cancel['error_number'], cancelled
                assert sql('SHOW ERRORS') == native_cancel['diagnostics']
                proof['checks'].append('captured-native-identity-cancels-query-without-inventing-native-error')
                sql('INSERT INTO t VALUES(99,99)')
                thread = sql('SELECT CONNECTION_ID()')[0][0]
                cursor.execute('KILL CONNECTION ' + str(int(thread)))
                assert observation()['connection_health_checked'] is False
                started = post('execute', session_id=session_id, source='SELECT 1', parameters=[], history_sensitive=True)
                _rows, failed = collect(started['occurrence_id'])
                assert failed['session_reuse_blocked'] is True, failed
                assert observation()['state'] == 'unknown'
                assert observation()['connection_usable'] is False
                proof['checks'].append('unread-disconnect-detected-by-next-command-and-never-replayed')
                post('close_session', session_id=session_id); session_id = None; released = True
                if engine == 'mysql':
                    cursor.execute("SELECT PROCESSLIST_ID FROM performance_schema.session_connect_attrs WHERE ATTR_NAME='scratchrobin_observer' AND ATTR_VALUE=%s", (str(source_connection_id),))
                    assert not cursor.fetchall(), 'A private observer survived closing its source session'
                    proof['checks'].append('retained-private-observer-is-closed-with-source-session')
                    cursor.execute('SELECT command_type,argument FROM mysql.general_log WHERE thread_id=%s ORDER BY event_time', (source_connection_id,))
                    traffic = cursor.fetchall()
                    traffic = [(_kind.decode('ascii') if isinstance(_kind, bytes) else _kind,
                                bytes(_text).decode('latin1') if isinstance(_text, (bytes, bytearray)) else _text)
                               for _kind, _text in traffic]
                    forbidden = ('select version(), @@session.sql_mode', 'select @@session.character_set_client')
                    unexpected = [statement for kind, statement in traffic if kind == 'Ping' or
                                  kind == 'Query' and re.sub(r'\s+', ' ', statement).strip().lower().startswith(forbidden)]
                    assert not unexpected, unexpected
                    proof['original_session_query_count'] = sum(kind == 'Query' for kind, _ in traffic)
                    assert proof['original_session_query_count'] >= source_requests
                    proof['unexpected_original_metadata_or_ping_commands'] = len(unexpected)
                    cursor.execute('SET GLOBAL general_log=OFF')
                    proof['checks'].append('native-general-log-confirms-no-hidden-language-charset-or-ping-commands-on-original-session-after-admission')
            finally:
                if engine == 'mysql' and 'source_connection_id' in locals():
                    try:
                        cursor.execute('SELECT command_type,argument FROM mysql.general_log WHERE thread_id=%s ORDER BY event_time', (source_connection_id,))
                        traffic = [(kind, bytes(text).decode('latin1') if isinstance(text, (bytes, bytearray)) else text)
                                   for kind, text in cursor.fetchall()]
                        (output / 'original-session-traffic.json').write_text(json.dumps(traffic, indent=2).replace(password, '<redacted>') + '\n')
                    except Exception as error:
                        proof['original_traffic_capture_error'] = type(error).__name__
                if session_id is not None:
                    post('close_session', session_id=session_id)
                cursor.close(); oracle.close()
        proof.update(complete=bool(owned['owned_server_stopped'] and released),
                     owned_server_stopped=owned['owned_server_stopped'],
                     native_version=owned['engine_version'], owned_sessions_released=released)
    finally:
        if 'owned' in locals():
            proof['owned_server_stopped'] = owned.get('owned_server_stopped', False)
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert proof['complete']
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('mysql', 'mariadb'), required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--mysql-interface', choices=('pure', 'c'), default='pure')
    arguments = parser.parse_args()
    print(json.dumps(qualify(arguments.engine, arguments.output, mysql_interface=arguments.mysql_interface), indent=2))
