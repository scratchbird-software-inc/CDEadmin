#!/usr/bin/env python3
"""Replay exported metadata through native ISQL in two disposable databases."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid
from tools.cdeadmin_firebird_logical_volumes_gate import (
    docker, published_port, _configure_client_library, _route_arguments)
from pgadmin.cdeadmin.providers.firebird.provider import _resources
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_sql_export import build_metadata

OWNER = 'firebird-sql-export'


def run(root):
    import firebird.driver as native
    _configure_client_library(native)
    root.mkdir(parents=True, exist_ok=False)
    password = secrets.token_urlsafe(24)
    connection = destination = container = None
    result = {'passed': False, 'owned_container_removed': False}
    try:
        container = docker('create', '--name', 'scratchrobin-export-' + uuid.uuid4().hex[:12],
            '--label', 'cdeadmin-owned-gate=' + OWNER, '--publish', '127.0.0.1::3050',
            '--env', 'FIREBIRD_ROOT_PASSWORD', '--env', 'FIREBIRD_DATABASE',
            'firebirdsql/firebird:5.0.4', env=dict(os.environ, FIREBIRD_ROOT_PASSWORD=password,
            FIREBIRD_DATABASE='/var/lib/firebird/data/source.fdb')).decode().strip()
        docker('start', container)
        route = {'host': '127.0.0.1', 'port': published_port(container), 'user': 'SYSDBA',
                 'database': '/var/lib/firebird/data/source.fdb', 'charset': 'UTF8', 'timeout': 2}
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                connection = native.connect(password=password, **_route_arguments(route, native)); break
            except native.Error:
                time.sleep(.25)
        assert connection is not None
        definitions = [
            'CREATE DOMAIN "Z_DOMAIN" AS INTEGER CHECK (VALUE >= 0)',
            'CREATE TABLE "A_TABLE" (ID Z_DOMAIN NOT NULL PRIMARY KEY, NOTE VARCHAR(80))',
            'CREATE TABLE "B_CHILD" (ID INT PRIMARY KEY, PARENT_ID INT REFERENCES A_TABLE(ID))',
            'CREATE VIEW "V" (ID, NOTE) AS SELECT ID, NOTE FROM A_TABLE',
            'CREATE TABLE CYCLE_A (ID INT CONSTRAINT CYCLE_A_PK PRIMARY KEY USING DESCENDING INDEX CYCLE_A_PK_IX, B INT)',
            'CREATE TABLE CYCLE_B (ID INT PRIMARY KEY, A INT)',
            'ALTER TABLE CYCLE_A ADD CONSTRAINT CYCLE_A_FK FOREIGN KEY (B) REFERENCES CYCLE_B(ID) USING INDEX CYCLE_A_FK_IX',
            'ALTER TABLE CYCLE_B ADD CONSTRAINT CYCLE_B_FK FOREIGN KEY (A) REFERENCES CYCLE_A(ID)',
            "COMMENT ON INDEX CYCLE_A_PK_IX IS 'primary index comment'",
            "COMMENT ON INDEX CYCLE_A_FK_IX IS 'foreign index comment'",
            'CREATE INDEX "IX_NOTE" ON "A_TABLE" (NOTE)',
            'ALTER INDEX "IX_NOTE" INACTIVE',
            "COMMENT ON TABLE A_TABLE IS 'table; comment ^'",
            "COMMENT ON COLUMN A_TABLE.NOTE IS 'column comment'",
            "COMMENT ON VIEW V IS 'view comment'",
            "CREATE EXCEPTION E_TEST 'message;^'",
            'CREATE SEQUENCE S_TEST START WITH 7 INCREMENT BY 3',
            'CREATE ROLE R_TEST',
            'CREATE TRIGGER T_DML FOR A_TABLE ACTIVE BEFORE INSERT POSITION 2 AS\nBEGIN NEW.NOTE = NEW.NOTE; END',
            'CREATE TRIGGER T_CONNECT ACTIVE ON CONNECT POSITION 1 AS\nBEGIN END',
            'CREATE TRIGGER T_DDL ACTIVE BEFORE CREATE TABLE OR ALTER TABLE POSITION 3 AS\nBEGIN END',
            "COMMENT ON TRIGGER T_DML IS 'relation trigger comment'",
            'GRANT SELECT ON TABLE A_TABLE TO ROLE R_TEST',
            'GRANT UPDATE (NOTE) ON TABLE A_TABLE TO ROLE R_TEST WITH GRANT OPTION',
            "CREATE PROCEDURE P_TEST RETURNS (V VARCHAR(20)) AS BEGIN V = ';^'; SUSPEND; END",
            "COMMENT ON PROCEDURE P_TEST IS 'PSQL; comment'",
            'CREATE FUNCTION CYCLE_F1 (N INT) RETURNS INT AS BEGIN RETURN N; END',
            'CREATE FUNCTION CYCLE_F2 (N INT) RETURNS INT AS BEGIN IF (N > 0) THEN RETURN CYCLE_F1(N-1)+1; RETURN 0; END',
            'ALTER FUNCTION CYCLE_F1 (N INT) RETURNS INT AS BEGIN IF (N > 0) THEN RETURN CYCLE_F2(N-1)+1; RETURN 0; END',
            "COMMENT ON FUNCTION CYCLE_F1 IS 'mutual function'",
            'CREATE PACKAGE A_PKG AS BEGIN FUNCTION F RETURNS INTEGER; END',
            'CREATE PACKAGE Z_PKG AS BEGIN FUNCTION F RETURNS INTEGER; END',
            'CREATE PACKAGE BODY A_PKG AS BEGIN FUNCTION F RETURNS INTEGER AS BEGIN RETURN Z_PKG.F(); END END',
            'CREATE PACKAGE BODY Z_PKG AS BEGIN FUNCTION F RETURNS INTEGER AS BEGIN IF (1=0) THEN RETURN A_PKG.F(); RETURN 7; END END',
            "COMMENT ON FUNCTION A_PKG.F IS 'package member comment'",
        ]
        for statement in definitions:
            connection.cursor().execute(statement)
            connection.commit()
        resources = _resources(connection, {})
        connection.rollback()
        model = build_export(resources, endpoint_id='owned', target_id='owned',
                             generation='native', native_model=True)
        exported = build_metadata(model)
        (root/'metadata.json').write_text(json.dumps(exported, indent=2))
        assert not exported['blockers'], exported['blockers'][:12]
        (root/'metadata.sql').write_text(exported['download_text'])
        destination_route = dict(route, database='/var/lib/firebird/data/destination.fdb')
        destination = native.create_database(password=password, **_route_arguments(destination_route, native))
        destination.close(); destination = None
        # The harness, not the export, owns an explicit native outcome.
        completed = subprocess.run(['/usr/local/bin/docker', '--context', 'desktop-linux',
            'exec', '-i', '--env', 'ISC_PASSWORD', container, '/opt/firebird/bin/isql',
            '-bail', '-user', 'SYSDBA', destination_route['database']],
            input=exported['download_text'] + '\nCOMMIT;\nQUIT;\n', text=True,
            env=dict(os.environ, ISC_PASSWORD=password), capture_output=True, timeout=40)
        (root/'isql.stdout').write_text(completed.stdout)
        (root/'isql.stderr').write_text(completed.stderr)
        assert completed.returncode == 0, completed.stderr
        destination = native.connect(password=password, **_route_arguments(destination_route, native))
        with destination.cursor() as cursor:
            cursor.execute("SELECT TRIM(RDB$TRIGGER_NAME), RDB$TRIGGER_SEQUENCE FROM RDB$TRIGGERS WHERE RDB$TRIGGER_NAME IN ('T_DML', 'T_CONNECT', 'T_DDL') ORDER BY 1")
            assert cursor.fetchall() == [('T_CONNECT', 1), ('T_DDL', 3), ('T_DML', 2)]
            cursor.execute("SELECT RDB$DESCRIPTION FROM RDB$TRIGGERS WHERE RDB$TRIGGER_NAME='T_DML'")
            assert cursor.fetchone() == ('relation trigger comment',)
            cursor.execute("SELECT TRIM(RDB$INDEX_NAME), RDB$DESCRIPTION FROM RDB$INDICES WHERE RDB$INDEX_NAME IN ('CYCLE_A_PK_IX', 'CYCLE_A_FK_IX') ORDER BY 1")
            assert cursor.fetchall() == [('CYCLE_A_FK_IX', 'foreign index comment'), ('CYCLE_A_PK_IX', 'primary index comment')]
            cursor.execute('INSERT INTO CYCLE_A VALUES (1, NULL)')
            cursor.execute('INSERT INTO CYCLE_B VALUES (1, 1)')
            cursor.execute('UPDATE CYCLE_A SET B=1 WHERE ID=1')
            cursor.execute('SELECT A.ID, B.ID FROM CYCLE_A A JOIN CYCLE_B B ON A.B=B.ID AND B.A=A.ID')
            assert cursor.fetchone() == (1, 1)
            for statement in ('INSERT INTO CYCLE_A VALUES (2, 999)',
                              'INSERT INTO CYCLE_B VALUES (2, 999)'):
                try:
                    cursor.execute(statement)
                except Exception as error:
                    assert 335544466 in getattr(error, 'gds_codes', ()), type(error).__name__
                else:
                    raise AssertionError('Replayed foreign key did not reject an absent parent')
            cursor.execute('SELECT CYCLE_F1(3), CYCLE_F2(4) FROM RDB$DATABASE')
            assert cursor.fetchone() == (3, 4)
            cursor.execute("SELECT RDB$DESCRIPTION FROM RDB$FUNCTIONS WHERE RDB$FUNCTION_NAME='CYCLE_F1'")
            assert cursor.fetchone() == ('mutual function',)
            cursor.execute('SELECT A_PKG.F() FROM RDB$DATABASE')
            assert cursor.fetchone() == (7,)
            cursor.execute("SELECT RDB$DESCRIPTION FROM RDB$FUNCTIONS WHERE RDB$PACKAGE_NAME='A_PKG' AND RDB$FUNCTION_NAME='F'")
            assert cursor.fetchone() == ('package member comment',)
            cursor.execute('SELECT V FROM P_TEST')
            assert cursor.fetchone() == (';^',)
            cursor.execute("SELECT RDB$INDEX_INACTIVE FROM RDB$INDICES WHERE RDB$INDEX_NAME = 'IX_NOTE'")
            assert cursor.fetchone() == (1,)
            cursor.execute("SELECT RDB$DESCRIPTION FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = 'A_TABLE'")
            assert cursor.fetchone() == ('table; comment ^',)
            cursor.execute("SELECT TRIM(RDB$PRIVILEGE), RDB$GRANT_OPTION, TRIM(RDB$FIELD_NAME) FROM RDB$USER_PRIVILEGES WHERE RDB$USER = 'R_TEST' ORDER BY 1")
            result['replayed_grants'] = cursor.fetchall()
            assert [tuple(value) for value in result['replayed_grants']] == [('S', 0, None), ('U', 1, 'NOTE')], result['replayed_grants']
            cursor.execute('INSERT INTO A_TABLE (ID, NOTE) VALUES (1, \'roundtrip\')')
            cursor.execute('INSERT INTO B_CHILD VALUES (1, 1)')
            cursor.execute('SELECT ID, NOTE FROM V')
            assert cursor.fetchone() == (1, 'roundtrip')
        destination.rollback()
        from tools.firebird_data_export_native import qualify as qualify_data
        result['data_capture'] = qualify_data(connection, route, password, destination, destination_route)
        result.update(passed=True, script_sha256=exported['sha256'],
                      native_isql_replay=True, bidirectional_foreign_keys_enforced=True,
                      comments_grants_psql_fk_view_and_index_verified=True,
                      package_body_cycle_and_member_comment_replayed=True, trigger_families_replayed=True, foreign_key_cycle_and_backing_comments_replayed=True, mutual_routine_cycle_replayed=True)
    finally:
        for value in (connection, destination):
            if value is not None: value.close()
        if container:
            label = docker('inspect', '--format', '{{index .Config.Labels "cdeadmin-owned-gate"}}', container).decode().strip()
            if label != OWNER: raise RuntimeError('Fixture ownership mismatch')
            docker('rm', '--force', '--volumes', container)
            result['owned_container_removed'] = True
        (root/'result.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--client-library', type=Path, default=Path(__file__).resolve().parent / 'reference_engine_demos/runtime/firebird/lib/libfbclient.so.5.0.4')
    args = parser.parse_args()
    os.environ['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] = str(args.client_library.resolve())
    print(json.dumps(run(args.output.resolve()), indent=2))
