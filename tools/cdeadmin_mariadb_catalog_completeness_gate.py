"""Independent raw MariaDB inventory, navigator and DDN fact reconciliation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
import config  # noqa: E402,F401
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_PROFILE, _resources  # noqa: E402
from pgadmin.cdeadmin.providers.mysql_family.mariadb_catalog import capture, _value, DENIED  # noqa: E402
from pgadmin.cdeadmin.navigator import resource_children  # noqa: E402

INVENTORY = {
    'database': 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s',
    'column': 'SELECT TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s',
    'index': 'SELECT DISTINCT TABLE_SCHEMA,TABLE_NAME,INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s',
    'constraint': 'SELECT TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=%s',
    'trigger': 'SELECT TRIGGER_SCHEMA,EVENT_OBJECT_TABLE,TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s',
    'partition': 'SELECT DISTINCT TABLE_SCHEMA,TABLE_NAME,PARTITION_NAME FROM information_schema.PARTITIONS WHERE TABLE_SCHEMA=%s AND PARTITION_NAME IS NOT NULL',
    'procedure': "SELECT ROUTINE_SCHEMA,ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_TYPE='PROCEDURE'",
    'function': "SELECT ROUTINE_SCHEMA,ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_TYPE='FUNCTION'",
    'package': "SELECT ROUTINE_SCHEMA,ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_TYPE='PACKAGE'",
    'event': 'SELECT EVENT_SCHEMA,EVENT_NAME FROM information_schema.EVENTS WHERE EVENT_SCHEMA=%s',
    'plugin': 'SELECT PLUGIN_NAME,PLUGIN_TYPE FROM information_schema.PLUGINS',
    'server-link': 'SELECT Server_name FROM mysql.servers',
    'system-variable': "SELECT 'Configuration',VARIABLE_NAME FROM information_schema.SYSTEM_VARIABLES",
    'session': "SELECT 'Sessions',CAST(ID AS CHAR) FROM information_schema.PROCESSLIST",
    'character-set': 'SELECT CHARACTER_SET_NAME FROM information_schema.CHARACTER_SETS',
    'collation': 'SELECT COLLATION_NAME FROM information_schema.COLLATIONS',
    'storage-engine': 'SELECT ENGINE FROM information_schema.ENGINES',
    'privilege': "SELECT 'global',GRANTEE,PRIVILEGE_TYPE FROM information_schema.USER_PRIVILEGES",
    'tablespace': 'SELECT NAME FROM information_schema.INNODB_SYS_TABLESPACES',
    'lock': "SELECT 'Locks',LOCK_ID FROM information_schema.INNODB_LOCKS",
    'lock-wait': "SELECT 'Lock waits',CONCAT(REQUESTING_TRX_ID,' -> ',BLOCKING_TRX_ID) FROM information_schema.INNODB_LOCK_WAITS",
    'table-storage': "SELECT TABLE_SCHEMA,TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s",
}


def quote(value):
    return '`' + value.replace('`', '``') + '`'


def reachable(resources, database):
    pending = [{'scope': scope, 'parent_path': [], 'database': database}
               for scope in ('server', 'database')]
    visited, found = set(), set()
    while pending:
        state = pending.pop()
        key = json.dumps(state, sort_keys=True)
        if key in visited:
            continue
        visited.add(key)
        for node in resource_children(resources, state, {'engine_id': 'mariadb'}):
            if node['node_type'] == 'resource':
                found.add(node['resource_id'])
                if node.get('has_children') and not node.get('section'):
                    pending.append({**state, 'scope': 'resource', 'resource_id': node['resource_id'], 'parent_path': node['display_path']})
            else:
                pending.append({**state, 'scope': node.get('scope', 'kind'), **{key: value for key, value in node.items()
                    if key in {'resource_kind', 'parent_path', 'virtual_branch', 'object_scope'}}})
    return found


def reconcile(connection, database, *, privileged):
    failures, checks, unavailable = [], [], []
    def read(source):
        with connection.cursor() as cursor:
            try:
                cursor.execute(source, (database,) if '%s' in source else None)
                return Counter(tuple('' if cell is None else str(cell) for cell in row) for row in cursor.fetchall())
            except Exception as error:
                if getattr(error, 'errno', None) not in DENIED:
                    raise
                return None
    expected = {kind: read(sql) for kind, sql in INVENTORY.items()}
    unavailable_grants = []
    for scope, source in (
        ('database', "SELECT 'database',GRANTEE,TABLE_SCHEMA,PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA=%s"),
        ('table', "SELECT 'table',GRANTEE,TABLE_SCHEMA,TABLE_NAME,PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES WHERE TABLE_SCHEMA=%s"),
        ('column', "SELECT 'column',GRANTEE,TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,PRIVILEGE_TYPE FROM information_schema.COLUMN_PRIVILEGES WHERE TABLE_SCHEMA=%s"),
    ):
        values = read(source)
        if values is None:
            unavailable_grants.append(scope)
        elif expected['privilege'] is not None:
            expected['privilege'].update(values)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CONCAT(QUOTE(User),'@',QUOTE(Host)),Db,Routine_name,Routine_type,Proc_priv FROM mysql.procs_priv WHERE Db=%s", (database,))
            for who, db, name, kind, privileges in cursor.fetchall():
                if isinstance(privileges, str):
                    privileges = privileges.split(',')
                for privilege in privileges:
                    if privilege.upper() in {'EXECUTE', 'ALTER ROUTINE'}:
                        expected['privilege'][('routine', who, db, name, kind, privilege.upper())] += 1
    except Exception as error:
        if getattr(error, 'errno', None) not in DENIED:
            raise
        unavailable_grants.append('routine')
    for kind, native_types in (('table', "'BASE TABLE','SYSTEM VERSIONED'"), ('view', "'VIEW'"), ('sequence', "'SEQUENCE'")):
        expected[kind] = read("SELECT TABLE_SCHEMA,TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE IN (" + native_types + ")")
    expected['role'] = read("SELECT User,Host FROM mysql.user WHERE is_role='Y'")
    expected['user'] = read("SELECT User,Host FROM mysql.user WHERE is_role='N'")
    expected['replication-channel'] = read('SELECT Connection_name FROM information_schema.SLAVE_STATUS')
    expected['loadable-function'] = read('SELECT name FROM mysql.func')
    contract = json.loads((ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_metrics_12_2_2.json').read_text())
    observations = {row['observation_id']: row for row in contract['native_observations']}
    expected['metric'] = Counter(('Metrics', observations[row['observation_id']]['native_name']) for row in contract['metrics'])
    resources = _resources(connection, {'route': {'database': database}}, MARIADB_PROFILE)
    actual = {kind: Counter() for kind in expected}
    for row in resources:
        kind, native = row['resource_kind'], row.get('native', {})
        if kind not in actual:
            if kind not in {'server','binary-log','binary-log-event','binary-log-status','general-log-entry','slow-query','log-configuration','tls-configuration'}:
                failures.append({'undeclared_inventory_kind': kind})
            continue
        if kind in {'user', 'role'}:
            key = (native.get('user'), native.get('host'))
        elif kind == 'replication-channel':
            key = (row['display_name'],)
        elif kind == 'plugin':
            key = (native['plugin_name'], native['plugin_type'])
        elif kind == 'table-storage':
            key = (native['table_schema'], native['table_name'])
        elif kind == 'privilege':
            scope = native.get('scope', 'global')
            if scope in unavailable_grants:
                continue
            key = (scope, native['grantee'],
                   *([native['table_schema']] if scope != 'global' else []),
                   *([native['table_name']] if scope in {'table', 'column'} else []),
                   *([native['column_name']] if scope == 'column' else []),
                   *([native['routine_name'], native['routine_type']] if scope == 'routine' else []),
                   native['privilege'])
        else:
            key = tuple(row['display_path'])
        actual[kind][key] += 1
    for kind, values in expected.items():
        if values is None:
            unavailable.append(kind)
            checks.append({'kind': kind, 'native_available': False, 'provider_count': sum(actual[kind].values())})
            if privileged:
                failures.append({'kind': kind, 'privileged_inventory_denied': True})
            continue
        missing, extra = values - actual[kind], actual[kind] - values
        checks.append({'kind': kind, 'native_available': True, 'native_count': sum(values.values()),
                       'provider_count': sum(actual[kind].values()), 'equal': not missing and not extra})
        if missing or extra:
            failures.append({'kind': kind, 'missing': list(missing.elements()), 'extra': list(extra.elements())})
    ids = [row['resource_id'] for row in resources]
    if len(ids) != len(set(ids)):
        failures.append({'duplicate_resource_ids': True})
    found = reachable(resources, database)
    missing = {row['resource_id'] for row in resources if row['resource_kind'] not in {'server', 'database'}} - found
    if missing:
        failures.append({'unreachable_resource_ids': sorted(missing)})
    coverage = next(row['native']['catalog_coverage'] for row in resources if row['resource_kind'] == 'server')
    if ((unavailable or unavailable_grants) and coverage['state'] != 'partial') or (privileged and coverage['failed_query_count']):
        failures.append({'incorrect_catalog_coverage': coverage})
    captured = capture(connection, database)
    facts = []
    for catalog, column in [('COLUMNS', 'TABLE_SCHEMA'), ('STATISTICS', 'TABLE_SCHEMA'),
                            ('TABLE_CONSTRAINTS', 'TABLE_SCHEMA'), ('KEY_COLUMN_USAGE', 'TABLE_SCHEMA'),
                            ('REFERENTIAL_CONSTRAINTS', 'CONSTRAINT_SCHEMA'), ('CHECK_CONSTRAINTS', 'CONSTRAINT_SCHEMA'),
                            ('PARTITIONS', 'TABLE_SCHEMA'), ('VIEWS', 'TABLE_SCHEMA'), ('PERIODS', 'TABLE_SCHEMA'), ('KEY_PERIOD_USAGE', 'TABLE_SCHEMA')]:
        with connection.cursor() as cursor:
            try:
                cursor.execute('SELECT * FROM information_schema.' + catalog + ' WHERE ' + column + '=%s', (database,))
                names = [str(col[0]).lower() for col in cursor.description]
                raw = [{name: _value(value) for name, value in zip(names, row)} for row in cursor.fetchall()]
            except Exception as error:
                if getattr(error, 'errno', None) not in DENIED:
                    raise
                if privileged:
                    failures.append({'ddn_section_denied': catalog})
                continue
        visible = [fact for row in captured['resources'] for key in ('children', 'unattached_facts')
                   for fact in row['native'].get(key, {}).get(catalog, [])]
        canonical = lambda rows: Counter(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows)
        equal = canonical(raw) == canonical(visible)
        facts.append({'section': catalog, 'native_count': len(raw), 'ddn_count': len(visible), 'equal': equal})
        if not equal:
            failures.append({'ddn_native_fact_mismatch': catalog})
    return {'checks': checks, 'ddn_facts': facts, 'unavailable_native_sections': unavailable, 'unavailable_grant_scopes': unavailable_grants,
            'catalog_coverage': coverage, 'resource_count': len(resources), 'reachable_count': len(found), 'failures': failures}


def qualify(route, output, *, password=None):
    import mariadb
    output.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'engine_version': '12.2.2'}
    connection = mariadb.connect(**route, autocommit=True, **({'password':password} if password is not None else {}))
    database = 'sr_catalog_' + secrets.token_hex(6)
    user, role, secret = 'sr_reader_' + secrets.token_hex(5), 'sr_role_' + secrets.token_hex(5), secrets.token_urlsafe(30)
    try:
        with connection.cursor() as cursor:
            cursor.execute('CREATE DATABASE ' + quote(database))
            connection.database = database
            for sql in [
                'CREATE TABLE `a:b` (`c` BIGINT PRIMARY KEY, txt VARCHAR(20), CONSTRAINT ck CHECK (`c`>0))',
                'CREATE TABLE `a` (`b:c` BIGINT PRIMARY KEY, parent BIGINT, CONSTRAINT fk FOREIGN KEY(parent) REFERENCES `a:b`(c))',
                "CREATE VIEW v AS SELECT 'MATERIALIZED' AS marker FROM `a:b`",
                'CREATE TABLE pt(id INT PRIMARY KEY) PARTITION BY RANGE(id) (PARTITION p0 VALUES LESS THAN(10), PARTITION p1 VALUES LESS THAN(MAXVALUE))',
                'CREATE TABLE temporal(id INT PRIMARY KEY) WITH SYSTEM VERSIONING',
                'CREATE TABLE application(id INT PRIMARY KEY, s DATE,e DATE, PERIOD FOR booking(s,e))',
                'CREATE SEQUENCE seq',
                'CREATE PROCEDURE p() SELECT 1', 'CREATE FUNCTION f() RETURNS INT DETERMINISTIC RETURN 1',
                'CREATE PACKAGE pkg PROCEDURE answer(); END',
                'CREATE PACKAGE BODY pkg PROCEDURE answer() BEGIN SELECT 1; END; END',
                'CREATE TRIGGER tr BEFORE INSERT ON `a` FOR EACH ROW SET NEW.parent=NEW.parent',
                "CREATE EVENT ev ON SCHEDULE EVERY 1 DAY DISABLE DO SELECT 1",
            ]:
                cursor.execute(sql)
            cursor.execute('CREATE ROLE ' + quote(role))
            cursor.execute('CREATE USER ' + quote(user) + "@'%' IDENTIFIED BY %s", (secret,))
            cursor.execute('GRANT SELECT,SHOW VIEW,EXECUTE ON ' + quote(database) + '.* TO ' + quote(user) + "@'%'")
            cursor.execute('GRANT INSERT ON ' + quote(database) + '.`a:b` TO ' + quote(user) + "@'%'")
            cursor.execute('GRANT UPDATE(txt) ON ' + quote(database) + '.`a:b` TO ' + quote(user) + "@'%'")
            cursor.execute('GRANT EXECUTE ON PROCEDURE ' + quote(database) + '.p TO ' + quote(user) + "@'%'")
            cursor.execute('CREATE TABLE former_target(id INT)')
            cursor.execute('GRANT SELECT ON ' + quote(database) + '.former_target TO ' + quote(user) + "@'%'")
            cursor.execute('DROP TABLE former_target')
            cursor.execute('GRANT ' + quote(role) + ' TO ' + quote(user) + "@'%'")
        proof['privileged'] = reconcile(connection, database, privileged=True)
        limited = mariadb.connect(**{**route,'user':user,'password':secret,'database':database}, autocommit=True)
        try:
            proof['restricted'] = reconcile(limited, database, privileged=False)
        finally:
            limited.close()
        proof['complete'] = not proof['privileged']['failures'] and not proof['restricted']['failures']
    finally:
        with connection.cursor() as cursor:
            cursor.execute('DROP DATABASE IF EXISTS ' + quote(database))
            cursor.execute('DROP USER IF EXISTS ' + quote(user) + "@'%'")
            cursor.execute('DROP ROLE IF EXISTS ' + quote(role))
        connection.close()
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    from tools.cdeadmin_mariadb_driver_gate import run
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(0 if run('mariadb:12.2.2', args.evidence, qualify)['complete'] else 1)
