#!/usr/bin/env python3
"""Live parity probe: MySQL/MariaDB object kinds a MySQL-wire engine runs.

Owner direction, 2026-10-29: Dolt, TiDB and Vitess reach full parity with
MySQL and MariaDB, filtered per engine so nothing is offered that the engine
does not directly support. This probe supplies the evidence for that filter.

Each probe runs a minimal native statement sequence in a scratch database the
probe creates and drops (or, with ``--existing-database``, in an existing
database such as a Vitess keyspace, cleaning up its own objects). A probe
passes only when every statement executes; grammar acceptance is not support.
Retention probes then read ``SHOW CREATE TABLE`` back, because some engines
accept a clause and silently discard it.

A passing probe shows the statement executed; it does not prove the engine's
semantics match MySQL's. A failing probe on one engine version or server
setting is evidence for that configuration only.

usage: cdeadmin_mysql_wire_parity_probe.py --engine ID --host H --port P
       --user U [--existing-database DB] --output result.json
The password is read from CDEADMIN_PROBE_PASSWORD (empty when unset).
"""

import argparse
import json
import os
import time
import uuid

# kind: statements; {db} is the scratch database, {suffix} a random suffix
PROBES = {
    'database': ['CREATE DATABASE {db}_x', 'DROP DATABASE {db}_x'],
    'table': ['CREATE TABLE {db}.t (id INT PRIMARY KEY, v VARCHAR(20))',
              'ALTER TABLE {db}.t ADD COLUMN w INT', 'DROP TABLE {db}.t'],
    'column-generated': [
        'CREATE TABLE {db}.g (a INT PRIMARY KEY, b INT AS (a*2) STORED)',
        'DROP TABLE {db}.g'],
    'index': ['CREATE TABLE {db}.i (id INT PRIMARY KEY, v INT)',
              'CREATE INDEX iv ON {db}.i (v)', 'DROP INDEX iv ON {db}.i',
              'DROP TABLE {db}.i'],
    'index-fulltext': ['CREATE TABLE {db}.f (id INT PRIMARY KEY, body TEXT)',
                       'CREATE FULLTEXT INDEX fb ON {db}.f (body)',
                       'DROP TABLE {db}.f'],
    'index-spatial': [
        'CREATE TABLE {db}.s (id INT PRIMARY KEY, p POINT NOT NULL SRID 0)',
        'CREATE SPATIAL INDEX sp ON {db}.s (p)', 'DROP TABLE {db}.s'],
    'index-invisible': [
        'CREATE TABLE {db}.iv (id INT PRIMARY KEY, v INT, INDEX ix (v) '
        'INVISIBLE)', 'DROP TABLE {db}.iv'],
    'index-functional': [
        'CREATE TABLE {db}.fx (id INT PRIMARY KEY, v VARCHAR(20), '
        'INDEX ((LOWER(v))))', 'DROP TABLE {db}.fx'],
    'constraint-foreign-key': [
        'CREATE TABLE {db}.p (id INT PRIMARY KEY)',
        'CREATE TABLE {db}.c (id INT PRIMARY KEY, pid INT, '
        'FOREIGN KEY (pid) REFERENCES {db}.p (id))',
        'DROP TABLE {db}.c', 'DROP TABLE {db}.p'],
    'constraint-check': [
        'CREATE TABLE {db}.k (id INT PRIMARY KEY, v INT, '
        'CONSTRAINT ck CHECK (v > 0))',
        'ALTER TABLE {db}.k DROP CHECK ck', 'DROP TABLE {db}.k'],
    'constraint-unique': [
        'CREATE TABLE {db}.u (id INT PRIMARY KEY, v INT, UNIQUE KEY uv (v))',
        'DROP TABLE {db}.u'],
    'view': ['CREATE TABLE {db}.vt (id INT PRIMARY KEY)',
             'CREATE VIEW {db}.v AS SELECT id FROM {db}.vt',
             'DROP VIEW {db}.v', 'DROP TABLE {db}.vt'],
    'trigger': ['CREATE TABLE {db}.tt (id INT PRIMARY KEY, v INT)',
                'CREATE TRIGGER {db}.trg BEFORE INSERT ON {db}.tt '
                'FOR EACH ROW SET NEW.v = 1',
                'DROP TRIGGER {db}.trg', 'DROP TABLE {db}.tt'],
    'event': ['CREATE EVENT {db}.ev ON SCHEDULE EVERY 1 DAY DISABLE DO '
              'SELECT 1', 'DROP EVENT {db}.ev'],
    'procedure': ['CREATE PROCEDURE {db}.pr() SELECT 1', 'CALL {db}.pr()',
                  'DROP PROCEDURE {db}.pr'],
    'function': ['CREATE FUNCTION {db}.fn(a INT) RETURNS INT DETERMINISTIC '
                 'RETURN a + 1', 'SELECT {db}.fn(1)', 'DROP FUNCTION {db}.fn'],
    'sequence': ['CREATE SEQUENCE {db}.sq', 'SELECT NEXTVAL({db}.sq)',
                 'DROP SEQUENCE {db}.sq'],
    'partition-range': [
        'CREATE TABLE {db}.pr (id INT PRIMARY KEY) PARTITION BY RANGE (id) '
        '(PARTITION p0 VALUES LESS THAN (10), '
        'PARTITION p1 VALUES LESS THAN MAXVALUE)',
        'ALTER TABLE {db}.pr TRUNCATE PARTITION p0', 'DROP TABLE {db}.pr'],
    'partition-hash': ['CREATE TABLE {db}.ph (id INT PRIMARY KEY) '
                       'PARTITION BY HASH (id) PARTITIONS 4',
                       'DROP TABLE {db}.ph'],
    'tablespace': ["CREATE TABLESPACE ts_{suffix} ADD DATAFILE "
                   "'ts_{suffix}.ibd'", 'DROP TABLESPACE ts_{suffix}'],
    'user': ["CREATE USER 'u_{suffix}'@'%' IDENTIFIED BY 'Probe-pw-2026!'",
             "DROP USER 'u_{suffix}'@'%'"],
    'role': ["CREATE ROLE 'r_{suffix}'", "DROP ROLE 'r_{suffix}'"],
    'privilege': [
        "CREATE USER 'g_{suffix}'@'%' IDENTIFIED BY 'Probe-pw-2026!'",
        "GRANT SELECT ON {db}.* TO 'g_{suffix}'@'%'",
        "SHOW GRANTS FOR 'g_{suffix}'@'%'",
        "REVOKE SELECT ON {db}.* FROM 'g_{suffix}'@'%'",
        "DROP USER 'g_{suffix}'@'%'"],
    'plugin': ['SHOW PLUGINS'],
    'component': ['SELECT * FROM mysql.component'],
    'resource-group-mysql': ['CREATE RESOURCE GROUP rg_{suffix} TYPE = USER',
                             'DROP RESOURCE GROUP rg_{suffix}'],
    'resource-group-tidb': [
        'CREATE RESOURCE GROUP rg_{suffix} RU_PER_SEC = 100',
        'DROP RESOURCE GROUP rg_{suffix}'],
    'replication-channel': ['SHOW REPLICA STATUS'],
    'binary-log': ['SHOW BINARY LOGS'],
    'session': ['SHOW PROCESSLIST'],
    'system-variable': ["SHOW GLOBAL VARIABLES LIKE 'max_connections'"],
    'status-metric': ["SHOW GLOBAL STATUS LIKE 'Uptime'"],
    'spatial-reference-system': [
        'SELECT COUNT(*) FROM '
        'information_schema.ST_SPATIAL_REFERENCE_SYSTEMS'],
    'server-link': ["CREATE SERVER sl_{suffix} FOREIGN DATA WRAPPER mysql "
                    "OPTIONS (HOST '127.0.0.1')", 'DROP SERVER sl_{suffix}'],
    'lock-catalog': ['SELECT * FROM performance_schema.data_locks LIMIT 1'],
    'system-versioning': ['CREATE TABLE {db}.sv (id INT PRIMARY KEY) '
                          'WITH SYSTEM VERSIONING', 'DROP TABLE {db}.sv'],
    'temporary-table': ['CREATE TEMPORARY TABLE {db}.tmp (id INT)',
                        'DROP TEMPORARY TABLE {db}.tmp'],
    'json-type': ['CREATE TABLE {db}.j (id INT PRIMARY KEY, d JSON)',
                  'DROP TABLE {db}.j'],
    'auto-increment': ['CREATE TABLE {db}.ai (id INT AUTO_INCREMENT '
                       'PRIMARY KEY)', 'DROP TABLE {db}.ai'],
    'analyze-table': ['CREATE TABLE {db}.an (id INT PRIMARY KEY)',
                      'ANALYZE TABLE {db}.an', 'DROP TABLE {db}.an'],
    'optimize-table': ['CREATE TABLE {db}.op (id INT PRIMARY KEY)',
                       'OPTIMIZE TABLE {db}.op', 'DROP TABLE {db}.op'],
    'check-table': ['CREATE TABLE {db}.ck2 (id INT PRIMARY KEY)',
                    'CHECK TABLE {db}.ck2', 'DROP TABLE {db}.ck2'],
    'explain': ['EXPLAIN SELECT 1'],
    'explain-analyze': ['EXPLAIN ANALYZE SELECT 1'],
    'xa': ["XA START 'x_{suffix}'", "XA END 'x_{suffix}'",
           "XA ROLLBACK 'x_{suffix}'"],
    'savepoint': ['START TRANSACTION', 'SAVEPOINT s1',
                  'ROLLBACK TO SAVEPOINT s1', 'ROLLBACK'],
    'lock-tables': ['CREATE TABLE {db}.lt (id INT PRIMARY KEY)',
                    'LOCK TABLES {db}.lt READ', 'UNLOCK TABLES',
                    'DROP TABLE {db}.lt'],
    'charset-collation': ['SHOW CHARACTER SET', 'SHOW COLLATION'],
    'flush-privileges': ['FLUSH PRIVILEGES'],
}

# kind: (create statement, table, text SHOW CREATE TABLE must keep)
RETENTION = {
    'retained-partition-hash': (
        'CREATE TABLE {db}.rph (id INT PRIMARY KEY) PARTITION BY HASH (id) '
        'PARTITIONS 4', 'rph', 'PARTITION'),
    'retained-system-versioning': (
        'CREATE TABLE {db}.rsv (id INT PRIMARY KEY) WITH SYSTEM VERSIONING',
        'rsv', 'SYSTEM VERSIONING'),
    'retained-index-invisible': (
        'CREATE TABLE {db}.rii (id INT PRIMARY KEY, v INT, INDEX ix (v) '
        'INVISIBLE)', 'rii', 'INVISIBLE'),
    'retained-fulltext': (
        'CREATE TABLE {db}.rft (id INT PRIMARY KEY, b TEXT, '
        'FULLTEXT KEY fb (b))', 'rft', 'FULLTEXT'),
    'retained-spatial': (
        'CREATE TABLE {db}.rsp (id INT PRIMARY KEY, p POINT NOT NULL SRID 0, '
        'SPATIAL KEY sp (p))', 'rsp', 'SPATIAL'),
    'retained-check': (
        'CREATE TABLE {db}.rck (id INT PRIMARY KEY, v INT, '
        'CONSTRAINT ck CHECK (v > 0))', 'rck', 'CHECK'),
    'retained-generated-stored': (
        'CREATE TABLE {db}.rgs (a INT PRIMARY KEY, b INT AS (a*2) STORED)',
        'rgs', 'STORED'),
    'retained-row-format': (
        'CREATE TABLE {db}.rrf (id INT PRIMARY KEY) ROW_FORMAT=COMPRESSED',
        'rrf', 'ROW_FORMAT'),
    'retained-table-comment': (
        "CREATE TABLE {db}.rtc (id INT PRIMARY KEY) COMMENT='probe'", 'rtc',
        "COMMENT='probe'"),
}

# Sharded DDL reaches vtgate schema tracking asynchronously.
TRACKING_RETRIES = 20


def _connect(mysql, options, database=None):
    arguments = dict(host=options.host, port=options.port, user=options.user,
                     password=os.environ.get('CDEADMIN_PROBE_PASSWORD', ''),
                     autocommit=True, use_pure=True)
    if database:
        arguments['database'] = database
    for _attempt in range(30):  # a just-started server may refuse logins
        try:
            return mysql.connect(**arguments)
        except mysql.InterfaceError as error:
            if error.errno not in (2003, 2013):
                raise
            time.sleep(2)
    return mysql.connect(**arguments)


def _run(mysql, connection, statement):
    """Execute one statement; None on success, else the native error."""
    if not connection.is_connected():
        connection.reconnect(attempts=3, delay=1)
    cursor = connection.cursor(buffered=True)
    try:
        cursor.execute(statement)
        while True:
            if cursor.with_rows:
                cursor.fetchall()
            if not cursor.nextset():
                break
        return None
    except mysql.Error as error:
        return {'errno': error.errno, 'msg': str(error.msg)[:200],
                'connection_lost': not connection.is_connected()}
    finally:
        cursor.close()


def _run_tracked(mysql, connection, statement):
    for _attempt in range(TRACKING_RETRIES):
        try:
            error = _run(mysql, connection, statement)
        except mysql.Error as exc:
            error = {'errno': exc.errno, 'msg': 'client: ' + str(exc)[:180]}
        if not (error and error.get('errno') == 1105 and
                'not found' in error.get('msg', '')):
            return error
        time.sleep(1)
    return error


def probe_kind(mysql, options, database, statements, values):
    connection = _connect(mysql, options, database)
    try:
        for index, statement in enumerate(statements):
            statement = statement.format(**values)
            error = _run_tracked(mysql, connection, statement)
            if error:
                for cleanup in statements[index + 1:]:
                    if cleanup.upper().startswith('DROP'):
                        try:
                            _run(mysql, connection, cleanup.format(**values))
                        except mysql.Error:
                            pass
                return {'step': index, 'statement': ' '.join(
                    statements[index].split(' ')[:3]), **error}
        return 'supported'
    finally:
        try:
            connection.close()
        except mysql.Error:
            pass


def probe_retention(mysql, connection, database, statement, table, needle):
    error = _run_tracked(mysql, connection, statement.format(db=database))
    if error:
        return {'step': 'create', **error}
    text, last = None, None
    for _attempt in range(TRACKING_RETRIES):
        cursor = connection.cursor(buffered=True)
        try:
            cursor.execute(f'SHOW CREATE TABLE {database}.{table}')
            text = cursor.fetchone()[1]
            break
        except mysql.Error as exc:
            last = exc
            time.sleep(1)
        finally:
            cursor.close()
    _run_tracked(mysql, connection, f'DROP TABLE {database}.{table}')
    if text is None:
        return {'step': 'show-create', 'errno': last.errno,
                'msg': str(last.msg)[:200]}
    if needle.upper() in text.upper():
        return 'supported'
    return {'errno': None, 'msg': 'accepted but not retained: ' +
            ' '.join(text.split())[:200]}


def _objects(mysql, connection, database):
    cursor = connection.cursor(buffered=True)
    try:
        cursor.execute(f'SHOW FULL TABLES FROM {database}')
        return sorted(f'{row[0]} ({row[1]})' for row in cursor.fetchall())
    finally:
        cursor.close()


def main():
    import mysql.connector as mysql
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--engine', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--existing-database')
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    suffix = uuid.uuid4().hex[:8]
    database = options.existing_database or 'cde_probe_' + suffix
    connection = _connect(mysql, options)
    cursor = connection.cursor()
    cursor.execute('SELECT VERSION()')
    version = cursor.fetchone()[0]
    cursor.close()
    setup = None
    if not options.existing_database:
        setup = _run(mysql, connection, f'CREATE DATABASE {database}')
        if setup:
            raise SystemExit(f'cannot create the scratch database: {setup}')
    before = (_objects(mysql, connection, database)
              if options.existing_database else [])
    values = {'db': database, 'suffix': suffix}
    results = {}
    try:
        for kind, statements in PROBES.items():
            results[kind] = probe_kind(mysql, options, database, statements,
                                       values)
        for kind, (statement, table, needle) in RETENTION.items():
            results[kind] = probe_retention(mysql, connection, database,
                                            statement, table, needle)
    finally:
        leftovers = []
        if options.existing_database:
            time.sleep(5)  # let schema tracking settle before comparing
            leftovers = sorted(
                set(_objects(mysql, connection, database)) - set(before))
        else:
            _run(mysql, connection, f'DROP DATABASE IF EXISTS {database}')
        connection.close()
    with open(options.output, 'w', encoding='utf-8') as handle:
        json.dump({'engine': options.engine, 'version': version,
                   'probe_database': None if options.existing_database
                   else 'scratch', 'leftover_objects': leftovers,
                   'results': results}, handle, indent=1,
                  sort_keys=True)
        handle.write('\n')
    supported = sum(value == 'supported' for value in results.values())
    print(f'{options.engine} {version}: {supported}/{len(results)} supported')
    if leftovers:
        print('WARNING: objects the probe could not remove from '
              f'{database}: {", ".join(leftovers)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
