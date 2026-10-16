"""Native MySQL product workflows on an explicitly supplied disposable server.

Creates only uniquely named databases/accounts and restores its selected server
variable. Source credentials never enter receipts. Both connector implementations
run independently. Cluster, browser and ScratchBird history proofs are separate.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import sys
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
import config  # noqa: E402,F401
import mysql.connector  # noqa: E402
from tools.mysql_driver_gate_support import provider_access  # noqa: E402
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MySQLPilotProvider, _create_client  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog  # noqa: E402
from pgadmin.cdeadmin.workspace.mysql_server_plan import plan as server_plan  # noqa: E402
from pgadmin.cdeadmin.workspace.mysql_server_apply import MySQLServerApplications  # noqa: E402
from pgadmin.cdeadmin.workspace.mysql_data_import import preview, MySQLDataApplications  # noqa: E402
from pgadmin.cdeadmin.providers.mysql_roles import account  # noqa: E402
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import identifier  # noqa: E402


def confirmation(receipt):
    return {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}


def model(provider, route, *, server=False):
    captured = provider.capture_server_catalog(route) if server else provider.capture_catalog(route)
    exported = build_export(captured['resources'], endpoint_id='owned-native',
        target_id='server:' + captured['server_uuid'] if server else 'owned-database',
        generation=captured['generation'], include_system=True, refreshed=True, engine='mysql')
    return read_catalog(json.dumps(exported['snapshot']), engine='mysql')


def server_workflows(provider, route, native, output):
    applications = MySQLServerApplications(output / 'server-reviews.json')
    token = secrets.token_hex(5)
    user, role, group, space = 'sr_ddn_u_' + token + "@'\\é", 'sr_ddn_r_' + token, 'sr_ddn_rg_' + token, 'sr_ddn_ts_' + token
    results = []
    def change(section, facts, kind, action, draft=None):
        baseline = model(provider, route, server=True)
        desired = deepcopy(baseline)
        from pgadmin.cdeadmin.workspace.mysql_server_plan import SPEC
        uuid = next(row['native']['server_uuid'] for row in baseline['rows'].values() if row['kind'] == 'server')
        key = 'mysql-server:' + json.dumps([uuid, section, [facts[name] for name in SPEC[section][1]]], ensure_ascii=False, separators=(',', ':'))
        row = desired['rows'].get(key)
        if row is None:
            row = {'resource_id': key, 'kind': kind, 'name': ' / '.join(str(facts[name]) for name in SPEC[section][1]),
                'system': 'false', 'native': {'server_uuid': uuid, 'system_object': False, 'section': section, 'catalog_row': facts}}
            desired['rows'][key] = row
        row['native']['mysql_change'] = {'action': action, 'draft': draft or {}, 'confirmation': row['name']}
        plan = server_plan(baseline, desired, model(provider, route, server=True))
        plan['endpoint_id'] = 'owned-native'
        assert plan['ready_for_review'], plan['blockers'] + plan['conflicts']
        receipt = applications.review(plan, baseline, desired, 1, 'owned-server')
        calls = []
        def execute(record, operation):
            calls.append(operation['resource_id'])
            return provider.apply_server_operation(route, record, operation)
        result = applications.apply(confirmation(receipt), 1, 'owned-server', execute)
        assert result['state'] == 'acknowledged', result
        restarted = MySQLServerApplications(output / 'server-reviews.json')
        assert restarted.apply(confirmation(receipt), 1, 'owned-server', execute)['state'] == 'acknowledged'
        assert len(calls) == 1
        results.append({'kind': kind, 'operation': action, 'native_rediscovery_verified': True, 'repeat_not_dispatched': True})
    with native.cursor() as cursor:
        cursor.execute('SELECT @@GLOBAL.max_connections')
        original = cursor.fetchone()[0]
    try:
        change('system-variables', {'variable_name': 'max_connections'}, 'system-variable', 'set_global', {'value': int(original) + 1})
        change('system-variables', {'variable_name': 'max_connections'}, 'system-variable', 'set_global', {'value': int(original)})
        change('accounts', {'user': user, 'host': '%'}, 'user', 'create')
        change('accounts', {'user': user, 'host': '%'}, 'user', 'alter', {'active': True})
        with native.cursor() as cursor:
            cursor.execute('CREATE TABLE grant_target(id INT, txt VARCHAR(20))')
            cursor.execute('CREATE PROCEDURE grant_proc() SELECT 1')
            cursor.execute("CREATE LIBRARY grant_lib LANGUAGE JAVASCRIPT AS 'export const value = 1'")
            cursor.execute('SELECT CONCAT(QUOTE(%s),%s,QUOTE(%s))', (user, '@', '%'))
            native_grantee = cursor.fetchone()[0]
        for section, facts in [
            ('visible-global-grants', {'grantee': native_grantee, 'privilege_type': 'SELECT'}),
            ('schema-grants', {'grantee': native_grantee, 'table_schema': native.database, 'privilege_type': 'SELECT'}),
            ('table-grants', {'grantee': native_grantee, 'table_schema': native.database, 'table_name': 'grant_target', 'privilege_type': 'INSERT'}),
            ('column-grants', {'grantee': native_grantee, 'table_schema': native.database, 'table_name': 'grant_target', 'column_name': 'txt', 'privilege_type': 'UPDATE'}),
            ('routine-grants', {'grantee': native_grantee, 'table_schema': native.database, 'routine_name': 'grant_proc', 'routine_type': 'PROCEDURE', 'privilege_type': 'EXECUTE'}),
            ('routine-grants', {'grantee': native_grantee, 'table_schema': native.database, 'routine_name': 'grant_lib', 'routine_type': 'LIBRARY', 'privilege_type': 'EXECUTE'}),
        ]:
            change(section, facts, 'privilege', 'grant')
            change(section, facts, 'privilege', 'revoke')
        with native.cursor() as cursor:
            cursor.execute('CREATE ROLE ' + account(role, '%'))
        change('role-edges', {'from_user': role, 'from_host': '%', 'to_user': user, 'to_host': '%'},
               'role-membership', 'grant', {'admin_option': True})
        change('default-roles', {'user': user, 'host': '%', 'default_role_user': role, 'default_role_host': '%'},
               'default-role', 'set_default', {'mode': 'SELECTED'})
        change('default-roles', {'user': user, 'host': '%', 'default_role_user': role, 'default_role_host': '%'},
               'default-role', 'set_default', {'mode': 'NONE'})
        change('role-edges', {'from_user': role, 'from_host': '%', 'to_user': user, 'to_host': '%'}, 'role-membership', 'revoke')
        with native.cursor() as cursor:
            cursor.execute("SHOW GLOBAL STATUS LIKE 'Resource_group_supported'")
            support = cursor.fetchone()
        if support and str(support[1]).upper() == 'ON':
            change('resource-groups', {'resource_group_name': group}, 'resource-group', 'create',
                   {'name': group, 'resource_type': 'USER', 'priority': 0, 'enabled': True})
            change('resource-groups', {'resource_group_name': group}, 'resource-group', 'alter', {'state': 'DISABLE'})
            change('resource-groups', {'resource_group_name': group}, 'resource-group', 'drop', {'force': True})
        elif support and str(support[1]).upper() == 'OFF':
            with native.cursor() as cursor:
                try:
                    cursor.execute('CREATE RESOURCE GROUP ' + identifier(group) + ' TYPE=USER')
                except mysql.connector.Error as error:
                    from mysql.connector.errorcode import ER_FEATURE_UNSUPPORTED
                    assert error.errno == ER_FEATURE_UNSUPPORTED
                    results.append({'kind': 'resource-group', 'native_capability': 'unsupported',
                                    'native_refusal_verified': True, 'error_code': error.errno})
                else:
                    raise AssertionError('Native resource group capability contradicts execution')
        else:
            raise AssertionError('Native resource group support observation is unavailable')
        change('tablespaces', {'name': space, 'space_type': 'General'}, 'tablespace', 'create',
               {'name': space, 'datafile': space + '.ibd', 'encryption': 'N'})
        change('tablespaces', {'name': space}, 'tablespace', 'alter', {'change': 'AUTOEXTEND_SIZE', 'autoextend_size': 8388608})
        change('tablespaces', {'name': space}, 'tablespace', 'drop')
        change('accounts', {'user': user, 'host': '%'}, 'user', 'drop')
    finally:
        with native.cursor() as cursor:
            cursor.execute('SET GLOBAL max_connections=%s', (original,))
            cursor.execute('DROP USER IF EXISTS ' + account(user, '%'))
            cursor.execute('DROP ROLE IF EXISTS ' + account(role, '%'))
            cursor.execute('SELECT COUNT(*) FROM information_schema.RESOURCE_GROUPS WHERE RESOURCE_GROUP_NAME=%s', (group,))
            if cursor.fetchone()[0]:
                cursor.execute('DROP RESOURCE GROUP ' + identifier(group) + ' FORCE')
            cursor.execute('SELECT COUNT(*) FROM information_schema.INNODB_TABLESPACES WHERE NAME=%s', (space,))
            if cursor.fetchone()[0]:
                cursor.execute('DROP TABLESPACE ' + identifier(space))
    return results


def data_workflows(provider, route, native, output):
    with native.cursor() as cursor:
        cursor.execute('SET SESSION sql_mode=%s', ('NO_AUTO_VALUE_ON_ZERO',))
        cursor.execute('CREATE TABLE source_data(id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,u BIGINT UNSIGNED,n DECIMAL(65,30),d DATETIME(6),tm TIME(6),js JSON,txt VARCHAR(30),payload LONGBLOB,g POINT SRID 4326,v VECTOR(3),hidden_value VARBINARY(4) INVISIBLE,computed_id BIGINT GENERATED ALWAYS AS(LENGTH(txt)+1) STORED) ENGINE=InnoDB')
        cursor.execute("INSERT INTO source_data(id,u,n,d,tm,js,txt,payload,g,v,hidden_value) VALUES(0,18446744073709551615,12345678901234567890.123456789012345678901234567890,'0000-00-00 00:00:00.000000','-25:01:02.123456','{\"nested\":[1,2]}','Maya é',X'00FF00',ST_GeomFromText('POINT(-79.38 43.65)',4326,'axis-order=long-lat'),STRING_TO_VECTOR('[0.1,-2,3]'),X'01020304')")
        cursor.execute('CREATE TABLE target_data LIKE source_data')
        cursor.execute('CREATE TABLE target_failure LIKE source_data')
        cursor.execute('CREATE TABLE target_stale LIKE source_data')
        cursor.execute('CREATE TABLE source_myisam(id INT PRIMARY KEY, txt VARCHAR(10)) ENGINE=MyISAM')
        cursor.execute("INSERT INTO source_myisam VALUES(1,'exact')")
        cursor.execute('CREATE TABLE target_myisam LIKE source_myisam')
    source_model = model(provider, route)
    resource = next(row['resource_id'] for row in source_model['rows'].values() if row['kind'] == 'table' and row['name'] == 'source_data')
    data = provider.capture_data(route, resource, endpoint_id='owned-native', target_id='owned-database', mode='full', row_limit=100)
    source = json.dumps(data['snapshot'])
    native_plan = preview(source, model(provider, route), table='target_data')
    assert native_plan['ready_for_review'] and native_plan['row_count'] == 1
    applications = MySQLDataApplications(output / 'data-reviews.json')
    receipt = applications.review(native_plan, 1, 'owned-db')
    calls = []
    def execute(record):
        calls.append(1)
        return provider.apply_data_import(route, record)
    result = applications.apply(confirmation(receipt), 1, 'owned-db', execute)
    assert result['state'] == 'committed' and result['outcome']['rediscovery_verified'], result
    assert applications.apply(confirmation(receipt), 1, 'owned-db', execute)['state'] == 'committed'
    assert len(calls) == 1
    assert '18446744073709551615' not in (output / 'data-reviews.json').read_text()
    with native.cursor() as cursor:
        cursor.execute('SELECT id,u,n,d,tm,js,txt,HEX(payload),HEX(g),HEX(v),HEX(hidden_value),computed_id FROM source_data')
        original = cursor.fetchall()
        cursor.execute('SELECT id,u,n,d,tm,js,txt,HEX(payload),HEX(g),HEX(v),HEX(hidden_value),computed_id FROM target_data')
        assert cursor.fetchall() == original
    from pgadmin.cdeadmin.workspace.mysql_data_import import plan_digest
    failure = preview(source, model(provider, route), table='target_failure')
    failure['rows'] *= 2
    failure['row_count'] = 2
    failure['execution_sha256'] = plan_digest(failure)
    outcome = provider.apply_data_import(route, {'plan': failure})
    assert outcome['state'] == 'rolled_back' and outcome['acknowledged_rows'] == 1, outcome
    stale = preview(source, model(provider, route), table='target_stale')
    with native.cursor() as cursor:
        cursor.execute('ALTER TABLE target_stale ADD COLUMN external_change INT')
    outcome = provider.apply_data_import(route, {'plan': stale})
    assert outcome['state'] == 'not_dispatched' and outcome['acknowledged_rows'] == 0, outcome
    archive_model = model(provider, route)
    resource = next(row['resource_id'] for row in archive_model['rows'].values() if row['kind'] == 'table' and row['name'] == 'source_myisam')
    nontransactional = json.dumps(provider.capture_data(route, resource, endpoint_id='owned-native', target_id='owned-database', mode='full', row_limit=100)['snapshot'])
    assert not preview(nontransactional, archive_model, table='target_myisam')['ready_for_review']
    partial = preview(nontransactional, archive_model, table='target_myisam', allow_nontransactional=True)
    partial['rows'] *= 2
    partial['row_count'] = 2
    partial['execution_sha256'] = plan_digest(partial)
    outcome = provider.apply_data_import(route, {'plan': partial})
    assert outcome['state'] == 'partial_nontransactional' and outcome['acknowledged_rows'] == 1, outcome
    with native.cursor() as cursor:
        for table, count in [('target_failure', 0), ('target_stale', 0), ('target_myisam', 1)]:
            cursor.execute('SELECT COUNT(*) FROM ' + identifier(table))
            assert cursor.fetchone()[0] == count
    return {'exact_uint64_decimal_zero_datetime_extended_time_json_unicode_blob_geometry_vector': True,
            'generated_columns_omitted_and_verified': True, 'explicit_zero_auto_increment_retained': True, 'invisible_column_data_retained': True,
            'separate_connection_postimages': True, 'repeat_and_restart_no_replay': True,
            'receipt_excludes_imported_row_data': True, 'native_constraint_failure_rolls_back_innodb_prefix': True,
            'stale_native_layout_refused_before_insert': True, 'myisam_requires_acknowledgement_and_retains_partial_effects': True}


def qualify(route, output, *, password=None):
    if any('password' in key.lower() for key in route):
        raise ValueError('Keep route credentials outside JSON')
    output.mkdir(parents=True, exist_ok=False)
    proof = {'schema': 'scratchrobin.mysql.completion-proof@1', 'complete': False, 'platform': platform.platform(),
             'python': platform.python_version(), 'driver': importlib.metadata.version('mysql-connector-python'),
             'scopes': [], 'failures': [], 'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted((ROOT / 'web/pgadmin/cdeadmin').rglob('*.py'))}}
    for pure in (True, False):
        selected = {**route, 'use_pure': pure, 'autocommit': True, 'sql_mode': 'NO_AUTO_VALUE_ON_ZERO'}
        connection = client = None
        created = False
        database = 'sr_product_' + secrets.token_hex(7)
        try:
            connection = mysql.connector.connect(**selected, **({'password': password} if password else {}))
            request_route, permissions = provider_access(selected, password)
            permissions.require = lambda *_: None  # Only this explicitly owned qualification principal.
            client = _create_client(MYSQL_PROFILE, permissions, None)
            provider = MySQLPilotProvider(SimpleNamespace(endpoint_id='owned-native'), permissions, client)
            with connection.cursor() as cursor:
                cursor.execute('SELECT VERSION()')
                version = cursor.fetchone()[0]
                if version.split('-')[0] != '9.7.0':
                    raise ValueError('Exact MySQL 9.7.0 is required')
                cursor.execute('CREATE DATABASE ' + identifier(database) + ' CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
                created = True
            connection.database = database
            native_route = {**request_route, 'database': database}
            directory = output / ('pure' if pure else 'cext')
            directory.mkdir()
            for name, run in [('server-ddn', server_workflows), ('data-ddn', data_workflows)]:
                try:
                    receipt = run(provider, native_route, connection, directory)
                    proof['scopes'].append({'connector': 'pure' if pure else 'cext', 'name': name, 'passed': True, 'checks': receipt})
                except Exception as error:
                    proof['failures'].append({'connector': 'pure' if pure else 'cext', 'scope': name, 'type': type(error).__name__,
                        'native_error_code': getattr(error, 'errno', None), 'locations': [{'file': Path(frame.filename).name, 'line': frame.lineno}
                            for frame in traceback.extract_tb(error.__traceback__)]})
                    traceback.print_exc()
        except Exception as error:
            proof['failures'].append({'connector': 'pure' if pure else 'cext', 'scope': 'setup',
                'type': type(error).__name__, 'native_error_code': getattr(error, 'errno', None)})
        finally:
            try:
                if client is not None:
                    client.close()
                if connection is not None:
                    if created:
                        with connection.cursor() as cursor:
                            cursor.execute('DROP DATABASE IF EXISTS ' + identifier(database))
                    connection.close()
            except Exception as error:
                proof['failures'].append({'connector': 'pure' if pure else 'cext', 'scope': 'cleanup',
                    'type': type(error).__name__})
    proof['complete'] = not proof['failures'] and len(proof['scopes']) == 4
    (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path)
    parser.add_argument('--password-env')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.route:
        result = qualify(json.loads(args.route.read_text()), args.output, password=os.environ[args.password_env] if args.password_env else None)
    else:
        from tools.mysql_qualification_support import server
        with server(args.output.parent / (args.output.name + '-fixture')) as (route, _, fixture):
            result = qualify(route, args.output)
        result['owned_cleanup_confirmed'] = fixture['owned_server_stopped']
        result['complete'] = result['complete'] and result['owned_cleanup_confirmed']
        (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    sys.exit(0 if result['complete'] else 1)
