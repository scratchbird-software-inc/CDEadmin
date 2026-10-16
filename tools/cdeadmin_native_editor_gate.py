"""Native editor proof on uniquely owned SQL objects; no history operations.

Qualifies retained-session completion, parser rejection, nonexecuting DDL and
preservation of pending interactive work. Receipts cover this editor component,
not full product or platform acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
import config  # noqa: E402,F401
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def provider(engine, route, password=None, embedded=False):
    permissions = SimpleNamespace(require=lambda *_args, **_kwargs: None,
        acquire_secret=lambda *_args, **_kwargs: SecretLease(password.encode()) if password else None)
    route = dict(route)
    if password:
        route.update(credential_reference_id='owned-editor', principal_reference='owned-editor')
    context = SimpleNamespace(endpoint_id='owned-editor', pool_namespace=secrets.token_hex(8),
        session_namespace=secrets.token_hex(8), cache_namespace=secrets.token_hex(8),
        target_adapter_id='firebird-embedded-client' if embedded else engine + '_wire-client',
        effective_permissions=frozenset({'filesystem', 'embedded_runtime'} if embedded else {'network'}))
    if engine in {'mysql', 'mariadb'}:
        from pgadmin.cdeadmin.providers.mysql_family.provider import (
            _create_client, MYSQL_PROFILE, MARIADB_PROFILE, MySQLPilotProvider, MariaDBPilotProvider)
        profile, cls = (MYSQL_PROFILE, MySQLPilotProvider) if engine == 'mysql' else (MARIADB_PROFILE, MariaDBPilotProvider)
        result = cls(context, permissions, _create_client(profile, permissions, context))
    else:
        from importlib import import_module
        module = import_module('pgadmin.cdeadmin.providers.' + engine +
                               ('.embedded_provider' if embedded else '.provider'))
        result = module.create_provider(context, permissions)
    return result, route


def qualify(engine, route, output, *, password=None, embedded=False):
    output.mkdir(parents=True, exist_ok=False)
    proof = {'component': 'native-editor', 'engine': engine, 'embedded': embedded,
             'complete': False, 'checks': [], 'failures': [], 'owned_connections_closed': False,
             'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted((ROOT / 'web/pgadmin/cdeadmin').rglob('*.py'))}}
    client_provider = observer = handle = None
    created = False
    name = 'SR_EDITOR_' + secrets.token_hex(6).upper()
    quoted = lambda value: ('`' + value.replace('`', '``') + '`') if engine in {'mysql', 'mariadb'} else ('"' + value.replace('"', '""') + '"')
    table = quoted(name)
    try:
        client_provider, native_route = provider(engine, route, password, embedded)
        session = client_provider.open_session({'route': native_route})
        handle = client_provider._sessions[session['session_id']].handle
        proof['native_client_type'] = type(getattr(handle, '_native', handle)).__name__
        if engine == 'mysql' and 'use_pure' in native_route:
            assert ('CMySQLConnection' in proof['native_client_type']) == (native_route.get('use_pure') is False)
        observer = client_provider.client._connect({'route': native_route})
        if engine == 'firebird':
            if handle.main_transaction.is_active(): handle.rollback()
            idle = client_provider.validate_source_without_execution({'session_id': session['session_id'],
                'language_profile': 'firebird-sql', 'source': 'CREATE TABLE "SR_NOT_CREATED" (ID INTEGER)'})
            assert idle['grammar_valid'] is True and not handle.main_transaction.is_active()
            symbols = client_provider.complete({'session_id': session['session_id']})['editor_context']
            assert not any(item['display_name'] == 'SR_NOT_CREATED' for item in symbols['resources'])
            assert not handle.main_transaction.is_active()
            proof['checks'].append({'name': 'idle-read-only-preparation-and-metadata-release', 'passed': True})

        def execute(connection, source):
            cursor = connection if engine == 'duckdb' else connection.cursor()
            try:
                cursor.execute(source)
                return cursor.fetchone() if source.lstrip().upper().startswith('SELECT') else None
            finally:
                if cursor is not connection: cursor.close()

        def decision(connection, action):
            if engine == 'duckdb': connection.execute(action.upper())
            else: getattr(connection, action)()

        execute(handle, f'CREATE TABLE {table} (ID INTEGER PRIMARY KEY, "odd column" INTEGER)'.replace('"odd column"', quoted('odd column')))
        created = True
        if engine == 'duckdb': client_provider.client.control_transaction(handle, 'commit')
        else: handle.commit()
        if engine in {'mysql', 'mariadb'}:
            client_provider.client.control_transaction(handle, 'autocommit_off')
        execute(handle, f'INSERT INTO {table} VALUES (1, 9)')
        request = {'session_id': session['session_id'], 'language_profile': engine + '-sql'}
        checks = [('select', f'SELECT ID FROM {table}', True),
                  ('invalid-syntax', 'SELEC 1', False),
                  ('missing-context', 'SELECT * FROM SR_EDITOR_MISSING_CONTEXT', True if engine == 'duckdb' else None),
                  ('nonexecuting-drop', f'DROP TABLE {table}', True)]
        if engine in {'mysql', 'mariadb'}:
            checks += [('nonexecuting-autocommit', 'SET autocommit=1', True),
                       ('compound-body', f'CREATE PROCEDURE {quoted(name + "_P")}() BEGIN SELECT 1; END', True)]
        elif engine == 'firebird':
            checks += [('psql-body', f'CREATE PROCEDURE {quoted(name + "_P")} RETURNS (V INTEGER) AS BEGIN V=1; SUSPEND; END', True)]
        for label, source, expected in checks:
            proof['active_check'] = label
            result = client_provider.validate_source_without_execution({**request, 'source': source})
            if result['grammar_valid'] is not expected:
                raise AssertionError(label + ': expected native grammar status ' + str(expected))
            proof['checks'].append({'name': label, 'grammar_valid': expected,
                                    'authority': result['authority'], 'parser_version': result.get('parser_version')})
        if engine == 'mariadb':
            cursor = handle.cursor()
            try:
                cursor.execute('SELECT @@sql_mode'); original_mode = cursor.fetchone()[0]
                cursor.execute("SET SESSION sql_mode='ORACLE'")
                result = client_provider.validate_source_without_execution({**request, 'script': True,
                    'source': "SELECT NVL(NULL,'it'' contains %s; and ?') FROM dual; SELECT 'a'||'b' FROM dual;"})
                proof['oracle_check'] = {key: result.get(key) for key in ('grammar_valid', 'script_ready', 'sql_mode', 'diagnostics')}
                assert result['script_ready'] and result['grammar_valid'] is True and len(result['statements']) == 2
                unsupported = client_provider.validate_source_without_execution({**request,
                    'source': "SELECT q'[it' contains ;]' FROM dual"})
                assert unsupported['grammar_valid'] is False
                proof['checks'].append({'name': 'native-oracle-mode-and-script-boundaries', 'passed': True, 'unsupported_q_quote_rejected': True})
            finally:
                cursor.execute('SET SESSION sql_mode=?', (original_mode,)); cursor.close()
        if engine == 'firebird':
            result = client_provider.validate_source_without_execution({**request, 'script': True,
                'source': 'SET TERM ^; CREATE PROCEDURE "SR_NOT_CREATED_P" RETURNS(V INTEGER) AS BEGIN V=1; SUSPEND; END^ SET TERM ;^ SELECT 1 FROM RDB$DATABASE;'})
            assert result['grammar_valid'] is True and result['script_ready'] and len(result['statements']) == 2
            proof['checks'].append({'name': 'native-psql-script-terminators-and-body-checking', 'passed': True})
        symbols = client_provider.complete({'session_id': session['session_id'],
            'full_source': 'SELECT ', 'source_before_cursor': 'SELECT '})['editor_context']
        if not any(item['display_name'] == name for item in symbols['resources']):
            raise AssertionError('Native relation completion is missing')
        if not any(item['display_name'] == 'odd column' for item in symbols['resources']):
            raise AssertionError('Exact native column completion is missing')
        proof['checks'].append({'name': 'native-metadata', 'context': symbols['context'],
                                'symbols': len(symbols['resources']), 'truncated': symbols['truncated']})
        if execute(observer, f'SELECT count(*) FROM {table}')[0] != 0:
            raise AssertionError('Checking or completion committed pending work')
        if execute(handle, f'SELECT count(*) FROM {table}')[0] != 1:
            raise AssertionError('Checking or completion discarded pending work')
        decision(handle, 'rollback')
        if execute(handle, f'SELECT count(*) FROM {table}')[0] != 0:
            raise AssertionError('Native rollback no longer controls the pending write')
        proof['checks'].append({'name': 'native-pending-work-preserved', 'passed': True})
    except Exception as error:
        proof['failures'].append({'type': type(error).__name__,
            'native_code': getattr(error, 'errno', getattr(error, 'sqlcode', None)),
            'locations': [{'file': Path(frame.filename).name, 'line': frame.lineno}
                          for frame in traceback.extract_tb(error.__traceback__)]})
    finally:
        try:
            if observer is not None:
                if engine != 'duckdb': observer.rollback()
                observer.close()
            if handle is not None:
                if engine == 'duckdb':
                    try: handle.execute('ROLLBACK')
                    except Exception: pass
                else: handle.rollback()
                if created:
                    cursor = handle if engine == 'duckdb' else handle.cursor()
                    try: cursor.execute('DROP TABLE ' + table)
                    finally:
                        if cursor is not handle: cursor.close()
                    if engine != 'duckdb': handle.commit()
            if client_provider is not None:
                client_provider.client.close()
            proof['owned_connections_closed'] = True
        except Exception as error:
            proof['failures'].append({'phase': 'cleanup', 'type': type(error).__name__})
    proof['complete'] = not proof['failures'] and bool(proof['checks']) and proof['owned_connections_closed']
    (output / 'summary.json').write_text(json.dumps(proof, indent=2, default=str) + '\n')
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('mysql', 'mariadb', 'sqlite', 'duckdb'), required=True)
    parser.add_argument('--route', type=Path)
    parser.add_argument('--password-env')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.route:
        result = qualify(args.engine, json.loads(args.route.read_text()), args.output,
                         password=os.environ[args.password_env] if args.password_env else None)
    elif args.engine in {'sqlite', 'duckdb'}:
        with tempfile.TemporaryDirectory(prefix='sr-editor-') as directory:
            route = {'database': str(Path(directory) / ('native.' + args.engine)), 'filesystem_root': directory}
            result = qualify(args.engine, route, args.output)
    elif args.engine == 'mysql':
        from tools.mysql_qualification_support import server
        import mysql.connector
        args.output.mkdir(parents=True, exist_ok=False)
        results = {}
        with server(args.output / 'fixture') as (route, _name, fixture):
            connection = mysql.connector.connect(**route)
            database = 'sr_editor_' + secrets.token_hex(6)
            try:
                with connection.cursor() as cursor: cursor.execute('CREATE DATABASE ' + database)
                for interface, pure in (('pure', True), ('c-extension', False)):
                    native = qualify('mysql', {**route, 'database': database, 'use_pure': pure}, args.output / interface)
                    results[interface] = {'complete': native['complete'], 'receipt': interface + '/summary.json'}
            finally:
                with connection.cursor() as cursor: cursor.execute('DROP DATABASE ' + database)
                connection.close()
        result = {'complete': all(row['complete'] for row in results.values()) and fixture['owned_server_stopped'],
                  'interfaces': results, 'owned_server_stopped': fixture['owned_server_stopped']}
        (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    else:
        from tools.cdeadmin_mariadb_driver_gate import run
        import mariadb
        def check(route, output):
            connection = mariadb.connect(**route)
            database = 'sr_editor_' + secrets.token_hex(6)
            try:
                cursor = connection.cursor(); cursor.execute('CREATE DATABASE ' + database); cursor.close()
                return qualify('mariadb', {**route, 'database': database}, output)
            finally:
                cursor = connection.cursor(); cursor.execute('DROP DATABASE ' + database); cursor.close(); connection.close()
        result = run('mariadb:12.2.2', args.output, check)
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
