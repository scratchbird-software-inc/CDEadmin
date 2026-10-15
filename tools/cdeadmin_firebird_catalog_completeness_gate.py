#!/usr/bin/env python3
"""Independent native inventory and navigator reconciliation on Firebird 5.0.4.

SQL here deliberately reads raw identity columns rather than calling the provider
query builders. Comparisons are multisets, so duplicate projections cannot hide.
"""
import argparse
from collections import Counter
import json
import os
import secrets
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client, _resources  # noqa: E402
from tools.cdeadmin_firebird_local_fixture import run_local  # noqa: E402
from pgadmin.cdeadmin.navigator import resource_children  # noqa: E402

# Every query returns (parent, name), except users which include their plugin.
INVENTORY = {
    'table': "SELECT '', RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$VIEW_BLR IS NULL",
    'view': "SELECT '', RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$VIEW_BLR IS NOT NULL",
    'column': 'SELECT RDB$RELATION_NAME, RDB$FIELD_NAME FROM RDB$RELATION_FIELDS',
    'index': 'SELECT RDB$RELATION_NAME, RDB$INDEX_NAME FROM RDB$INDICES',
    'constraint': 'SELECT RDB$RELATION_NAME, RDB$CONSTRAINT_NAME FROM RDB$RELATION_CONSTRAINTS',
    'domain': "SELECT '', RDB$FIELD_NAME FROM RDB$FIELDS WHERE COALESCE(RDB$SYSTEM_FLAG,0)>0 OR RDB$FIELD_NAME NOT STARTING WITH 'RDB$'",
    'sequence': "SELECT '', RDB$GENERATOR_NAME FROM RDB$GENERATORS",
    'trigger': 'SELECT RDB$RELATION_NAME, RDB$TRIGGER_NAME FROM RDB$TRIGGERS',
    'procedure': 'SELECT RDB$PACKAGE_NAME, RDB$PROCEDURE_NAME FROM RDB$PROCEDURES',
    'function': 'SELECT RDB$PACKAGE_NAME, RDB$FUNCTION_NAME FROM RDB$FUNCTIONS WHERE RDB$MODULE_NAME IS NULL',
    'external-function': 'SELECT RDB$PACKAGE_NAME, RDB$FUNCTION_NAME FROM RDB$FUNCTIONS WHERE RDB$MODULE_NAME IS NOT NULL',
    'package': "SELECT '', RDB$PACKAGE_NAME FROM RDB$PACKAGES",
    'exception': "SELECT '', RDB$EXCEPTION_NAME FROM RDB$EXCEPTIONS",
    'role': "SELECT '', RDB$ROLE_NAME FROM RDB$ROLES",
    'character-set': "SELECT '', RDB$CHARACTER_SET_NAME FROM RDB$CHARACTER_SETS",
    'collation': "SELECT '', RDB$COLLATION_NAME FROM RDB$COLLATIONS",
    'blob-filter': "SELECT '', RDB$FUNCTION_NAME FROM RDB$FILTERS",
    'publication': "SELECT '', RDB$PUBLICATION_NAME FROM RDB$PUBLICATIONS",
    'configuration': "SELECT '', RDB$CONFIG_NAME FROM RDB$CONFIG",
    'authentication-mapping': "SELECT '', RDB$MAP_NAME FROM RDB$AUTH_MAPPING",
    'global-authentication-mapping': "SELECT '', SEC$MAP_NAME FROM SEC$GLOBAL_AUTH_MAPPING",
    'user': 'SELECT SEC$USER_NAME, SEC$PLUGIN FROM SEC$USERS',
}


def normalized(value):
    return str(value).rstrip(' ') if value is not None else ''


def native_inventory(connection):
    result = {}
    with connection.cursor() as cursor:
        for kind, sql in INVENTORY.items():
            try:
                cursor.execute(sql)
                result[kind] = Counter(tuple(normalized(value) for value in row) for row in cursor.fetchall())
            except Exception:
                if kind not in {'global-authentication-mapping', 'user', 'configuration'}:
                    raise
                result[kind] = None
    return result


def provider_inventory(resources):
    result = {kind: Counter() for kind in INVENTORY}
    for item in resources:
        kind = item['resource_kind']
        if kind not in result:
            continue
        native = item.get('native', {})
        if kind == 'user':
            key = (item['display_name'], normalized(native.get('plugin')))
        elif kind == 'trigger':
            key = (normalized(native.get('relation')), item['display_name'])
        else:
            path = item['display_path']
            key = (path[-2] if len(path) > 1 else '', item['display_name'])
        result[kind][key] += 1
    return result


def reachable(resources):
    # Exercise actual provider navigation, including virtual folders, package
    # children and relation detail groups. Detail sections are leaves, not copies.
    queue = [{'scope': 'database', 'parent_path': []}]
    visited, found = set(), set()
    while queue:
        state = queue.pop()
        token = json.dumps(state, sort_keys=True)
        if token in visited:
            continue
        visited.add(token)
        try:
            nodes = resource_children(resources, state, {'engine_id': 'firebird'})
        except Exception as error:
            error.navigator_state = state
            raise
        for node in nodes:
            if node['node_type'] == 'resource':
                found.add(node['resource_id'])
                if node.get('has_children') and not node.get('section'):
                    queue.append({**state, 'scope': 'resource',
                                  'resource_id': node['resource_id'], 'parent_path': node['display_path']})
            else:
                queue.append({**state, 'scope': 'kind',
                    **{key: value for key, value in node.items() if key in (
                        'resource_kind', 'parent_path', 'virtual_branch', 'object_scope')}})
    return found


def auxiliary_inventory(connection, resources):
    expected = {'privilege': Counter(), 'storage-file': Counter(), 'shadow': Counter()}
    actual = {kind: Counter() for kind in expected}
    with connection.cursor() as cursor:
        cursor.execute('SELECT RDB$USER, RDB$RELATION_NAME, RDB$FIELD_NAME, RDB$PRIVILEGE, '
                       'RDB$GRANTOR, RDB$GRANT_OPTION, RDB$USER_TYPE, RDB$OBJECT_TYPE FROM RDB$USER_PRIVILEGES')
        for row in cursor.fetchall():
            values = [normalized(value) for value in row]
            membership = values[3] == 'M' and values[7] == '13'
            default_role = bool(values[2]) if membership else False
            if membership:
                values[2] = ''
            values[1] = values[1] or 'database'
            expected['privilege'][('object', *values, default_role)] += 1
        try:
            cursor.execute('SELECT SEC$USER, SEC$USER_TYPE FROM SEC$DB_CREATORS')
            for row in cursor.fetchall():
                expected['privilege'][('creation', *map(normalized, row))] += 1
        except Exception:
            pass  # The provider must explicitly report unavailable authority.
        cursor.execute('SELECT MON$DATABASE_NAME FROM MON$DATABASE')
        expected['storage-file'][('primary', cursor.fetchone()[0])] += 1
        cursor.execute('SELECT RDB$SHADOW_NUMBER, RDB$FILE_NAME, RDB$FILE_SEQUENCE, '
                       'RDB$FILE_START, RDB$FILE_LENGTH, RDB$FILE_FLAGS FROM RDB$FILES')
        for number, filename, *values in cursor.fetchall():
            expected['storage-file'][('catalog', str(number or 0), filename, *map(normalized, values))] += 1
            if number:
                expected['shadow'][(str(number),)] = 1
    for item in resources:
        kind, value = item['resource_kind'], item.get('native', {})
        if kind == 'privilege':
            if value.get('scope') == 'server-security-database':
                key = ('creation', normalized(value['grantee']), normalized(value['user_type']))
            else:
                key = ('object', *(normalized(value.get(field)) for field in (
                    'grantee', 'object_name', 'field', 'privilege', 'grantor',
                    'grant_option', 'user_type', 'object_type')), value.get('default_role', False))
            actual[kind][key] += 1
        elif kind == 'storage-file':
            key = (('primary', value['filename']) if value['file_kind'] == 'primary-database' else
                   ('catalog', str(value.get('shadow_number') or 0), value.get('filename'),
                    *(normalized(value.get(field)) for field in ('sequence', 'start', 'length', 'flags_raw'))))
            actual[kind][key] += 1
        elif kind == 'shadow':
            actual[kind][(item['display_name'],)] += 1
    checks, errors = [], []
    for kind in expected:
        missing, extra = expected[kind]-actual[kind], actual[kind]-expected[kind]
        checks.append({'kind': kind, 'native_count': sum(expected[kind].values()),
                       'provider_count': sum(actual[kind].values()), 'complete': not missing and not extra})
        if missing or extra:
            errors.append({'kind': kind, 'missing': list(missing.elements()), 'extra': list(extra.elements())})
    return checks, errors


def reconcile(connection, mode='network', *, privileged=True):
    expected = native_inventory(connection)
    resources = _resources(connection, {'route': {'attachment_mode': mode}})
    actual = provider_inventory(resources)
    errors, checks = [], []
    for kind in INVENTORY:
        if expected[kind] is None:
            if privileged and mode == 'network':
                errors.append({'kind': kind, 'privileged_inventory_unavailable': True})
            checks.append({'kind': kind, 'native_available': False, 'native_count': None,
                           'provider_count': sum(actual[kind].values()), 'complete': None,
                           'unavailability_reported': not actual[kind]})
            if actual[kind]:
                errors.append({'kind': kind, 'unavailable_native_projection': True})
            continue
        missing, extra = expected[kind]-actual[kind], actual[kind]-expected[kind]
        checks.append({'kind': kind, 'native_count': sum(expected[kind].values()),
                       'provider_count': sum(actual[kind].values()), 'complete': not missing and not extra})
        if missing or extra:
            errors.append({'kind': kind, 'missing': list(missing.elements()), 'extra': list(extra.elements())})
    auxiliary_checks, auxiliary_errors = auxiliary_inventory(connection, resources)
    checks.extend(auxiliary_checks)
    errors.extend(auxiliary_errors)
    roots = {'server', 'database'}
    wanted = {item['resource_id'] for item in resources if item['resource_kind'] not in roots}
    try:
        found = reachable(resources)
    except Exception as error:
        errors.append({'navigator_error_type': type(error).__name__, 'state': getattr(error, 'navigator_state', {})})
        found = set()
    unreachable = sorted(wanted-found)
    if unreachable:
        errors.append({'unreachable': unreachable})
    database = next(item['native'] for item in resources if item['resource_kind'] == 'database')
    if any(expected[kind] is None for kind in expected) and database['catalog_coverage']['state'] != 'partial':
        errors.append({'partial_coverage_not_reported': True})
    return {'catalog_coverage': database['catalog_coverage'], 'checks': checks, 'resource_count': len(resources),
            'reachable_count': len(wanted & found), 'failures': errors}


def fixture(connection, shadow, *, user_account=True):
    statements = [
        'CREATE DOMAIN CDE_NUM AS NUMERIC(18,4) CHECK (VALUE >= 0)',
        'CREATE SEQUENCE CDE_SEQ START WITH 12 INCREMENT BY 3',
        'CREATE DOMAIN CDE_ARRAY AS INTEGER[-2:3,5:6]',
        'CREATE TABLE "Cde:Parent" (ID BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, "Col:Name" CDE_NUM DEFAULT 1, TXT VARCHAR(30) CHARACTER SET UTF8, ARR CDE_ARRAY, CALC COMPUTED BY (ID+1))',
        'CREATE TABLE CDE_CHILD (ID INTEGER PRIMARY KEY, PID BIGINT, CONSTRAINT CDE_FK FOREIGN KEY (PID) REFERENCES "Cde:Parent" (ID))',
        'CREATE INDEX CDE_EXPR ON CDE_CHILD COMPUTED BY (ID+1)',
        'CREATE VIEW CDE_VIEW AS SELECT ID, "Col:Name" FROM "Cde:Parent"',
        'CREATE EXCEPTION CDE_EXCEPTION \'catalog evidence\'',
        'CREATE ROLE CDE_ROLE',
        'GRANT SELECT ON "Cde:Parent" TO ROLE CDE_ROLE',
        'CREATE PROCEDURE CDE_P (X INTEGER) RETURNS (Y INTEGER) AS BEGIN Y=X; SUSPEND; END',
        'CREATE FUNCTION CDE_F (X INTEGER) RETURNS INTEGER AS BEGIN RETURN X; END',
        'CREATE PACKAGE CDE_PK AS BEGIN PROCEDURE CDE_P (X INTEGER) RETURNS (Y INTEGER); FUNCTION CDE_F (X INTEGER) RETURNS INTEGER; END',
        'CREATE PACKAGE BODY CDE_PK AS BEGIN PROCEDURE CDE_P (X INTEGER) RETURNS (Y INTEGER) AS BEGIN Y=X; SUSPEND; END FUNCTION CDE_F (X INTEGER) RETURNS INTEGER AS BEGIN RETURN X; END END',
        'CREATE TRIGGER CDE_TRIGGER FOR CDE_CHILD ACTIVE BEFORE INSERT POSITION 0 AS BEGIN NEW.PID=NEW.PID; END',
        'CREATE TRIGGER CDE_CONNECT ACTIVE ON CONNECT POSITION 0 AS BEGIN END',
        "COMMENT ON TABLE CDE_CHILD IS 'Visible catalog fixture with dependencies'",
        'CREATE COLLATION CDE_COLLATION FOR UTF8 FROM UNICODE CASE INSENSITIVE',
        "DECLARE FILTER CDE_FILTER INPUT_TYPE -100 OUTPUT_TYPE -101 ENTRY_POINT 'cde_filter' MODULE_NAME 'not-loaded-by-catalog'",
        "DECLARE EXTERNAL FUNCTION CDE_UDF INTEGER RETURNS INTEGER BY VALUE ENTRY_POINT 'cde_udf' MODULE_NAME 'not-loaded-by-catalog'",
    ]
    if user_account:
        statements.append("CREATE USER CDE_CATALOG_USER PASSWORD '" + secrets.token_urlsafe(24) + "' FIRSTNAME 'Catalog' MIDDLENAME 'Native' LASTNAME 'Evidence' USING PLUGIN Srp")
    statements.extend([
        "CREATE SHADOW 1 AUTO '" + str(shadow).replace("'", "''") + "'",
        "ALTER DATABASE ADD DIFFERENCE FILE '" + str(shadow).replace("'", "''") + ".delta'",
        "CREATE MAPPING CDE_MAP USING PLUGIN Srp FROM USER 'external-name' TO USER CDE_MAPPED",
    ])
    for source in statements:
        connection.execute_immediate(source)
        connection.commit()


def user_metadata(connection):
    from pgadmin.cdeadmin.providers.firebird.provider import ADMINISTRATION
    rows = _resources(connection, {})
    user = next(item for item in rows if item['resource_kind'] == 'user' and item['display_name'] == 'CDE_CATALOG_USER')
    assert user['native']['first_name'] == 'Catalog'
    assert user['native']['middle_name'] == 'Native'
    assert user['native']['last_name'] == 'Evidence'
    assert type(user['native']['active']) is bool
    assert type(user['native']['administrator']) is bool
    source, _ = ADMINISTRATION._alter_user(user, {'active': False})
    assert source.endswith('USING PLUGIN "Srp"')
    connection.execute_immediate(source)
    connection.commit()
    observed = next(item for item in _resources(connection, {}) if item['resource_id'] == user['resource_id'])
    assert observed['native']['active'] is False
    connection.rollback()
    source = ADMINISTRATION._compile_drop({'resource_kind': 'user', 'target_resource': user})['source']
    assert source.endswith('USING PLUGIN "Srp"')
    connection.execute_immediate(source)
    connection.commit()
    assert not any(item['resource_id'] == user['resource_id'] for item in _resources(connection, {}))
    connection.rollback()
    return {'exact_names': True, 'native_boolean_flags': True, 'plugin_bound_alter_drop': True}


def run(runtime, evidence):
    report = {'captures': [], 'failures': []}
    def check(native, admin, route, accounts, target, temporary):
        _create_client(SimpleNamespace(acquire_secret=None))
        fixture(admin, temporary/'network.shd')
        result = reconcile(admin)
        report['captures'].append({'attachment': 'network', **result})
        report['failures'].extend(result['failures'])
        admin.rollback()
        from tools.cdeadmin_firebird_local_fixture import _route_arguments
        user, credential = accounts['Srp'][0]
        restricted = native.connect(password=credential, **_route_arguments({**route, 'user': user}, native))
        try:
            result = reconcile(restricted, privileged=False)
            report['captures'].append({'attachment': 'network-restricted', **result})
            report['failures'].extend(result['failures'])
            restricted.rollback()
        finally:
            restricted.close()
        report['user_metadata'] = user_metadata(admin)
        # A distinct local database avoids mixing embedded and server ownership.
        local = native.create_database(str(temporary/'embedded.fdb'), user='SYSDBA', charset='UTF8')
        try:
            fixture(local, temporary/'embedded.shd', user_account=False)
            result = reconcile(local, 'embedded', privileged=False)
            report['captures'].append({'attachment': 'embedded', **result})
            report['failures'].extend(result['failures'])
            local.rollback()
        finally:
            local.close()
        # Existing failure-injection gate now also covers relation objects and
        # publication memberships. A separate admitted account owns its reads.
        admin.execute_immediate('ALTER USER ' + user + ' GRANT ADMIN ROLE USING PLUGIN Srp')
        admin.commit()
        profile = temporary/'observation-profiles.json'
        descriptor = os.open(profile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump({'profiles': [{'engine': 'firebird', **route, 'user': user, 'password': credential}]}, stream)
        try:
            from tools.cdeadmin_firebird_catalog_observation_gate import run as observe_failures
            report['observation_failures'] = observe_failures(profile)
            if not report['observation_failures']['complete']:
                report['failures'].append({'observation_failure_gate_failed': True})
        finally:
            profile.unlink()
        if report['failures']:
            raise AssertionError('Catalog inventory reconciliation failed')
    result = run_local(runtime, evidence, check)
    result['inventory'] = report
    result['complete'] = result['complete'] and not report['failures'] and len(report['captures']) == 3
    (evidence/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    receipt = run(options.runtime_root, options.evidence)
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if receipt['complete'] else 1)
