#!/usr/bin/env python3
"""Live parity probe: PostgreSQL object kinds a PostgreSQL-wire engine runs.

Owner direction, 2026-10-29: CockroachDB and YugabyteDB YSQL reach full
parity with PostgreSQL, including their own native features, filtered per
engine so nothing is offered that the engine does not directly support. This
probe supplies the evidence for that filter; PostgreSQL itself is the
reference run.

Each probe runs a minimal native statement sequence, in autocommit, in a
scratch database the probe creates and drops. A probe passes only when every
statement executes; grammar acceptance is not support. A statement that runs
but draws a notice saying it was ignored or is unsupported is recorded as
``accepted_with_notice``. Retention probes then read the object back from
the catalog, because an engine can accept a clause and discard it.

A passing probe shows the statement executed; it does not prove the engine's
semantics match PostgreSQL's. A failing probe is evidence for that engine
version and configuration only: the settings that gate features (license,
rangefeeds, regions) are recorded with the results, and a gated failure is
not the same as no support.

usage: cdeadmin_postgresql_wire_parity_probe.py --engine ID --host H
       --port P --user U [--sslmode disable] --output result.json
The password is read from CDEADMIN_PROBE_PASSWORD (empty when unset).
"""

import argparse
import json
import os
import re
import time
import uuid

# Statements run in the scratch database; {db} names it, {suffix} is random.
TABLE = 'CREATE TABLE t (id INT PRIMARY KEY, v INT, w INT, j JSONB)'
PROBES = {
    # Shared PostgreSQL surface.
    'database': ['CREATE DATABASE {db}_x', 'DROP DATABASE {db}_x'],
    'schema': ['CREATE SCHEMA s', 'ALTER SCHEMA s RENAME TO s2',
               'DROP SCHEMA s2'],
    'table': [TABLE, 'ALTER TABLE t ADD COLUMN x INT',
              'ALTER TABLE t RENAME TO t2', 'DROP TABLE t2'],
    'table-unlogged': ['CREATE UNLOGGED TABLE u (id INT PRIMARY KEY)',
                       'DROP TABLE u'],
    'table-temporary': ['CREATE TEMP TABLE tt (id INT PRIMARY KEY)',
                        'DROP TABLE tt'],
    'crdb-table-temporary-opt-in': [
        "SET experimental_enable_temp_tables = 'on'",
        'CREATE TEMP TABLE tt (id INT PRIMARY KEY)', 'DROP TABLE tt'],
    'table-partitioned': [
        'CREATE TABLE pt (id INT, k INT) PARTITION BY RANGE (k)',
        'CREATE TABLE pt1 PARTITION OF pt FOR VALUES FROM (0) TO (10)',
        'DROP TABLE pt'],
    'table-inherits': ['CREATE TABLE pa (id INT)',
                       'CREATE TABLE pc (x INT) INHERITS (pa)',
                       'DROP TABLE pc', 'DROP TABLE pa'],
    'table-like': [TABLE, 'CREATE TABLE tl (LIKE t INCLUDING ALL)',
                   'DROP TABLE tl', 'DROP TABLE t'],
    'table-as': [TABLE, 'CREATE TABLE ta AS SELECT id, v FROM t',
                 'DROP TABLE ta', 'DROP TABLE t'],
    'column-generated-stored': [
        'CREATE TABLE g (a INT PRIMARY KEY, b INT GENERATED ALWAYS AS '
        '(a * 2) STORED)', 'DROP TABLE g'],
    'column-generated-virtual': [
        'CREATE TABLE gv (a INT PRIMARY KEY, b INT GENERATED ALWAYS AS '
        '(a * 2) VIRTUAL)', 'DROP TABLE gv'],
    'column-identity': [
        'CREATE TABLE ci (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, '
        'v INT)', 'INSERT INTO ci (v) VALUES (1)', 'DROP TABLE ci'],
    'column-collate': ['CREATE TABLE cc (id INT PRIMARY KEY, '
                       'v TEXT COLLATE "C")', 'DROP TABLE cc'],
    # An ICU locale tag, which CockroachDB takes where "C" is refused.
    'column-collate-icu': ['CREATE TABLE ci (id INT PRIMARY KEY, '
                           'v TEXT COLLATE "en-US")', 'DROP TABLE ci'],
    'column-alter-type': [TABLE, 'ALTER TABLE t ALTER COLUMN v TYPE BIGINT',
                          'DROP TABLE t'],
    'column-rename-drop': [TABLE, 'ALTER TABLE t RENAME COLUMN v TO v2',
                           'ALTER TABLE t DROP COLUMN v2', 'DROP TABLE t'],
    'index': [TABLE, 'CREATE INDEX iv ON t (v)', 'DROP INDEX iv',
              'DROP TABLE t'],
    'index-unique': [TABLE, 'CREATE UNIQUE INDEX iu ON t (v)',
                     'DROP TABLE t'],
    'index-partial': [TABLE, 'CREATE INDEX ip ON t (v) WHERE v > 0',
                      'DROP TABLE t'],
    'index-expression': [TABLE, 'CREATE INDEX ie ON t ((v + w))',
                         'DROP TABLE t'],
    'index-include': [TABLE, 'CREATE INDEX ii ON t (v) INCLUDE (w)',
                      'DROP TABLE t'],
    'index-desc': [TABLE, 'CREATE INDEX id ON t (v DESC)', 'DROP TABLE t'],
    'index-gin': [TABLE, 'CREATE INDEX ig ON t USING gin (j)',
                  'DROP TABLE t'],
    'index-gist': ['CREATE TABLE gs (id INT PRIMARY KEY, r INT4RANGE)',
                   'CREATE INDEX igs ON gs USING gist (r)', 'DROP TABLE gs'],
    'index-brin': [TABLE, 'CREATE INDEX ib ON t USING brin (v)',
                   'DROP TABLE t'],
    'index-hash': [TABLE, 'CREATE INDEX ih ON t USING hash (v)',
                   'DROP TABLE t'],
    'index-concurrently': [TABLE, 'CREATE INDEX CONCURRENTLY ic ON t (v)',
                           'DROP INDEX CONCURRENTLY ic', 'DROP TABLE t'],
    'index-nulls-not-distinct': [
        TABLE, 'CREATE UNIQUE INDEX inn ON t (v) NULLS NOT DISTINCT',
        'DROP TABLE t'],
    'index-rename': [TABLE, 'CREATE INDEX ir ON t (v)',
                     'ALTER INDEX ir RENAME TO ir2', 'DROP TABLE t'],
    'constraint-foreign-key': [
        'CREATE TABLE p (id INT PRIMARY KEY)',
        'CREATE TABLE c (id INT PRIMARY KEY, pid INT REFERENCES p (id) '
        'ON DELETE CASCADE)', 'DROP TABLE c', 'DROP TABLE p'],
    'constraint-check': [TABLE, 'ALTER TABLE t ADD CONSTRAINT ck '
                         'CHECK (v > 0)', 'ALTER TABLE t DROP CONSTRAINT ck',
                         'DROP TABLE t'],
    'constraint-unique': [TABLE, 'ALTER TABLE t ADD CONSTRAINT uq UNIQUE (v)',
                          'DROP TABLE t'],
    'constraint-not-valid': [
        TABLE, 'ALTER TABLE t ADD CONSTRAINT nv CHECK (v > 0) NOT VALID',
        'ALTER TABLE t VALIDATE CONSTRAINT nv', 'DROP TABLE t'],
    'constraint-deferrable': [
        'CREATE TABLE dp (id INT PRIMARY KEY)',
        'CREATE TABLE dc (id INT PRIMARY KEY, pid INT REFERENCES dp (id) '
        'DEFERRABLE INITIALLY DEFERRED)', 'DROP TABLE dc', 'DROP TABLE dp'],
    'constraint-exclusion': [
        'CREATE TABLE ex (id INT PRIMARY KEY, r INT4RANGE, '
        'EXCLUDE USING gist (r WITH &&))', 'DROP TABLE ex'],
    # PostgreSQL makes a nullable key column NOT NULL; the second probe
    # declares it, as an engine that refuses the first requires.
    'constraint-primary-key-change': [
        TABLE, 'ALTER TABLE t DROP CONSTRAINT t_pkey, '
        'ADD CONSTRAINT t_pkey PRIMARY KEY (id, v)', 'DROP TABLE t'],
    'constraint-primary-key-change-not-null': [
        TABLE, 'ALTER TABLE t ALTER COLUMN v SET NOT NULL',
        'ALTER TABLE t DROP CONSTRAINT t_pkey, '
        'ADD CONSTRAINT t_pkey PRIMARY KEY (id, v)', 'DROP TABLE t'],
    'view': [TABLE, 'CREATE VIEW vw AS SELECT id FROM t',
             'CREATE OR REPLACE VIEW vw AS SELECT id, v FROM t',
             'ALTER VIEW vw RENAME TO vw2', 'DROP VIEW vw2', 'DROP TABLE t'],
    'view-check-option': [TABLE, 'CREATE VIEW vc AS SELECT id, v FROM t '
                          'WHERE v > 0 WITH CHECK OPTION', 'DROP VIEW vc',
                          'DROP TABLE t'],
    'view-security-barrier': [
        TABLE, 'CREATE VIEW vb WITH (security_barrier) AS SELECT id FROM t',
        'DROP VIEW vb', 'DROP TABLE t'],
    'view-recursive': [
        'CREATE RECURSIVE VIEW vr (n) AS VALUES (1) UNION ALL '
        'SELECT n + 1 FROM vr WHERE n < 3', 'DROP VIEW vr'],
    'materialized-view': [
        TABLE, 'CREATE MATERIALIZED VIEW mv AS SELECT id, v FROM t',
        'REFRESH MATERIALIZED VIEW mv', 'DROP MATERIALIZED VIEW mv',
        'DROP TABLE t'],
    'materialized-view-concurrently': [
        TABLE, 'CREATE MATERIALIZED VIEW mc AS SELECT id, v FROM t',
        'CREATE UNIQUE INDEX mci ON mc (id)',
        'REFRESH MATERIALIZED VIEW CONCURRENTLY mc',
        'DROP MATERIALIZED VIEW mc', 'DROP TABLE t'],
    'sequence': ['CREATE SEQUENCE sq START 10 INCREMENT 2 CACHE 5',
                 "SELECT nextval('sq')", 'ALTER SEQUENCE sq RESTART 100',
                 'ALTER SEQUENCE sq RENAME TO sq2', 'DROP SEQUENCE sq2'],
    'sequence-owned-by': [TABLE, 'CREATE SEQUENCE so OWNED BY t.v',
                          'DROP TABLE t'],
    'type-enum': ["CREATE TYPE e AS ENUM ('a', 'b')",
                  "ALTER TYPE e ADD VALUE 'c'",
                  "ALTER TYPE e RENAME VALUE 'c' TO 'd'", 'DROP TYPE e'],
    'type-composite': ['CREATE TYPE cp AS (a INT, b TEXT)',
                       'DROP TYPE cp'],
    'type-range': ['CREATE TYPE rg AS RANGE (subtype = int4)',
                   'DROP TYPE rg'],
    'domain': ['CREATE DOMAIN dm AS INT CHECK (VALUE > 0)', 'DROP DOMAIN dm'],
    'function-sql': [
        'CREATE FUNCTION f(a INT) RETURNS INT LANGUAGE SQL AS '
        "'SELECT a + 1'", 'SELECT f(1)', 'DROP FUNCTION f'],
    'function-plpgsql': [
        'CREATE FUNCTION fp(a INT) RETURNS INT LANGUAGE plpgsql AS '
        "'BEGIN RETURN a + 1; END'", 'SELECT fp(1)', 'DROP FUNCTION fp'],
    'function-set-returning': [
        'CREATE FUNCTION fs() RETURNS SETOF INT LANGUAGE SQL AS '
        "'SELECT 1 UNION ALL SELECT 2'", 'SELECT * FROM fs()',
        'DROP FUNCTION fs'],
    'procedure': [
        'CREATE PROCEDURE pr(a INT) LANGUAGE plpgsql AS '
        "'BEGIN RAISE NOTICE ''x''; END'", 'CALL pr(1)',
        'DROP PROCEDURE pr'],
    'trigger': [
        TABLE, 'CREATE FUNCTION tf() RETURNS TRIGGER LANGUAGE plpgsql AS '
        "'BEGIN NEW.v := 1; RETURN NEW; END'",
        'CREATE TRIGGER tg BEFORE INSERT ON t FOR EACH ROW '
        'EXECUTE FUNCTION tf()', 'INSERT INTO t (id) VALUES (1)',
        'DROP TRIGGER tg ON t', 'DROP FUNCTION tf', 'DROP TABLE t'],
    'trigger-statement': [
        TABLE, 'CREATE FUNCTION ts() RETURNS TRIGGER LANGUAGE plpgsql AS '
        "'BEGIN RETURN NULL; END'",
        'CREATE TRIGGER tgs AFTER INSERT ON t FOR EACH STATEMENT '
        'EXECUTE FUNCTION ts()', 'DROP TRIGGER tgs ON t',
        'DROP FUNCTION ts', 'DROP TABLE t'],
    'event-trigger': [
        'CREATE FUNCTION et() RETURNS event_trigger LANGUAGE plpgsql AS '
        "'BEGIN END'", 'CREATE EVENT TRIGGER evt ON ddl_command_start '
        'EXECUTE FUNCTION et()', 'DROP EVENT TRIGGER evt',
        'DROP FUNCTION et'],
    'rule': [TABLE, 'CREATE RULE rl AS ON INSERT TO t DO INSTEAD NOTHING',
             'DROP RULE rl ON t', 'DROP TABLE t'],
    'aggregate': ['CREATE AGGREGATE ag (INT) (sfunc = int4pl, stype = INT)',
                  'DROP AGGREGATE ag (INT)'],
    'operator': ['CREATE OPERATOR === (LEFTARG = INT, RIGHTARG = INT, '
                 'FUNCTION = int4eq)', 'DROP OPERATOR === (INT, INT)'],
    'collation': ["CREATE COLLATION co (locale = 'C')", 'DROP COLLATION co'],
    'extension': ['CREATE EXTENSION IF NOT EXISTS fuzzystrmatch',
                  "SELECT levenshtein('a', 'b')"],
    'role': ['CREATE ROLE r{suffix}', 'ALTER ROLE r{suffix} WITH LOGIN',
             'DROP ROLE r{suffix}'],
    'role-password': ["CREATE USER u{suffix} WITH PASSWORD 'Pw-{suffix}!'",
                      'DROP USER u{suffix}'],
    'role-membership': ['CREATE ROLE ra{suffix}', 'CREATE ROLE rb{suffix}',
                        'GRANT ra{suffix} TO rb{suffix}',
                        'REVOKE ra{suffix} FROM rb{suffix}',
                        'DROP ROLE rb{suffix}', 'DROP ROLE ra{suffix}'],
    'grant-table': [TABLE, 'CREATE ROLE rg{suffix}',
                    'GRANT SELECT, INSERT ON t TO rg{suffix}',
                    'REVOKE INSERT ON t FROM rg{suffix}',
                    'REVOKE ALL ON t FROM rg{suffix}', 'DROP TABLE t',
                    'DROP ROLE rg{suffix}'],
    'grant-column': [TABLE, 'CREATE ROLE rc{suffix}',
                     'GRANT SELECT (v) ON t TO rc{suffix}',
                     'REVOKE SELECT (v) ON t FROM rc{suffix}',
                     'DROP TABLE t', 'DROP ROLE rc{suffix}'],
    'default-privileges': [
        'CREATE ROLE rd{suffix}',
        'ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO rd{suffix}',
        'ALTER DEFAULT PRIVILEGES REVOKE SELECT ON TABLES FROM rd{suffix}',
        'DROP ROLE rd{suffix}'],
    'row-level-security': [
        TABLE, 'ALTER TABLE t ENABLE ROW LEVEL SECURITY',
        'CREATE POLICY pl ON t USING (v > 0)',
        'ALTER POLICY pl ON t USING (v > 1)', 'DROP POLICY pl ON t',
        'DROP TABLE t'],
    'comment': [TABLE, "COMMENT ON TABLE t IS 'probe'",
                "COMMENT ON COLUMN t.v IS 'probe'", 'DROP TABLE t'],
    # Clauses the CockroachDB forms were first checked on by hand
    # (2026-10-30); each is a row here so every column records it.
    'trigger-instead-of': [
        TABLE, 'CREATE VIEW tv AS SELECT id, v FROM t',
        'CREATE FUNCTION tr() RETURNS TRIGGER LANGUAGE plpgsql AS '
        "'BEGIN RETURN NEW; END'",
        'CREATE TRIGGER ti INSTEAD OF INSERT ON tv FOR EACH ROW '
        'EXECUTE FUNCTION tr()', 'DROP VIEW tv', 'DROP FUNCTION tr',
        'DROP TABLE t'],
    'trigger-truncate': [
        TABLE, 'CREATE FUNCTION tr() RETURNS TRIGGER LANGUAGE plpgsql AS '
        "'BEGIN RETURN NEW; END'",
        'CREATE TRIGGER tt AFTER TRUNCATE ON t FOR EACH STATEMENT '
        'EXECUTE FUNCTION tr()', 'DROP TRIGGER tt ON t',
        'DROP FUNCTION tr', 'DROP TABLE t'],
    'trigger-update-of': [
        TABLE, 'CREATE FUNCTION tr() RETURNS TRIGGER LANGUAGE plpgsql AS '
        "'BEGIN RETURN NEW; END'",
        'CREATE TRIGGER tu BEFORE UPDATE OF v ON t FOR EACH ROW '
        'EXECUTE FUNCTION tr()', 'DROP TRIGGER tu ON t',
        'DROP FUNCTION tr', 'DROP TABLE t'],
    'trigger-referencing': [
        TABLE, 'CREATE FUNCTION tr() RETURNS TRIGGER LANGUAGE plpgsql AS '
        "'BEGIN RETURN NEW; END'",
        'CREATE TRIGGER trf AFTER INSERT ON t REFERENCING NEW TABLE AS nt '
        'FOR EACH STATEMENT EXECUTE FUNCTION tr()',
        'DROP TRIGGER trf ON t', 'DROP FUNCTION tr', 'DROP TABLE t'],
    'trigger-or-replace': [
        TABLE, 'CREATE FUNCTION tr() RETURNS TRIGGER LANGUAGE plpgsql AS '
        "'BEGIN RETURN NEW; END'",
        'CREATE TRIGGER tor BEFORE INSERT ON t FOR EACH ROW '
        'EXECUTE FUNCTION tr()',
        'CREATE OR REPLACE TRIGGER tor BEFORE UPDATE ON t FOR EACH ROW '
        'EXECUTE FUNCTION tr()', 'DROP TRIGGER tor ON t',
        'DROP FUNCTION tr', 'DROP TABLE t'],
    'trigger-alter': [
        TABLE, 'CREATE FUNCTION tr() RETURNS TRIGGER LANGUAGE plpgsql AS '
        "'BEGIN RETURN NEW; END'",
        'CREATE TRIGGER ta BEFORE INSERT ON t FOR EACH ROW '
        'EXECUTE FUNCTION tr()', 'ALTER TRIGGER ta ON t RENAME TO ta2',
        'ALTER TABLE t DISABLE TRIGGER ta2',
        'ALTER TABLE t ENABLE TRIGGER ta2',
        "COMMENT ON TRIGGER ta2 ON t IS 'probe'", 'DROP TRIGGER ta2 ON t',
        'DROP FUNCTION tr', 'DROP TABLE t'],
    'role-superuser': ['CREATE ROLE rs{suffix} WITH SUPERUSER',
                       'DROP ROLE rs{suffix}'],
    'role-inherit': ['CREATE ROLE ri{suffix} WITH NOINHERIT',
                     'DROP ROLE ri{suffix}'],
    'role-connection-limit': ['CREATE ROLE rc{suffix} CONNECTION LIMIT 5',
                              'DROP ROLE rc{suffix}'],
    # Separate rows: each one's cleanup drops the role it created.
    'role-rename': ['CREATE ROLE rr{suffix}',
                    'ALTER ROLE rr{suffix} RENAME TO rn{suffix}',
                    # Renamed back so the cleanup's DROP always matches.
                    'ALTER ROLE rn{suffix} RENAME TO rr{suffix}',
                    'DROP ROLE rr{suffix}'],
    'role-comment': ['CREATE ROLE rm{suffix}',
                     "COMMENT ON ROLE rm{suffix} IS 'probe'",
                     'DROP ROLE rm{suffix}'],
    'sequence-cycle': ['CREATE SEQUENCE sc MAXVALUE 3 CYCLE',
                       'DROP SEQUENCE sc'],
    'sequence-comment': ['CREATE SEQUENCE sm',
                         "COMMENT ON SEQUENCE sm IS 'probe'",
                         'DROP SEQUENCE sm'],
    'comment-view': ['CREATE VIEW cv AS SELECT 1 AS x',
                     "COMMENT ON VIEW cv IS 'probe'", 'DROP VIEW cv'],
    'comment-function': [
        "CREATE FUNCTION cf() RETURNS INT LANGUAGE SQL AS 'SELECT 1'",
        "COMMENT ON FUNCTION cf() IS 'probe'", 'DROP FUNCTION cf'],
    'comment-policy': [
        TABLE, 'CREATE POLICY cp ON t USING (true)',
        "COMMENT ON POLICY cp ON t IS 'probe'", 'DROP POLICY cp ON t',
        'DROP TABLE t'],
    'type-composite-alter': [
        'CREATE TYPE ca AS (a INT)', 'ALTER TYPE ca ADD ATTRIBUTE b TEXT',
        'DROP TYPE ca'],
    'type-enum-alter': [
        "CREATE TYPE ea AS ENUM ('a', 'b')",
        "ALTER TYPE ea ADD VALUE 'c' AFTER 'a'",
        "ALTER TYPE ea RENAME VALUE 'b' TO 'bb'", 'DROP TYPE ea'],
    'policy-alter-command': [
        TABLE, 'CREATE POLICY pc ON t USING (true)',
        'ALTER POLICY pc ON t FOR SELECT', 'DROP POLICY pc ON t',
        'DROP TABLE t'],
    'database-connection-limit': [
        'CREATE DATABASE {db}_cl CONNECTION LIMIT 5',
        'DROP DATABASE {db}_cl'],
    'database-template': [
        'CREATE DATABASE {db}_tp TEMPLATE template0',
        'DROP DATABASE {db}_tp'],
    'function-variadic': [
        'CREATE FUNCTION fv(VARIADIC a INT[]) RETURNS INT LANGUAGE SQL '
        "AS 'SELECT 1'", 'DROP FUNCTION fv'],
    'function-options': [
        'CREATE FUNCTION fo() RETURNS INT LANGUAGE SQL PARALLEL SAFE '
        "COST 10 SET search_path = public AS 'SELECT 1'",
        'DROP FUNCTION fo'],
    'publication': [TABLE, 'CREATE PUBLICATION pb FOR TABLE t',
                    'DROP PUBLICATION pb', 'DROP TABLE t'],
    'foreign-data': [
        'CREATE EXTENSION IF NOT EXISTS postgres_fdw',
        "CREATE SERVER fs FOREIGN DATA WRAPPER postgres_fdw OPTIONS "
        "(host 'localhost')", 'DROP SERVER fs'],
    'statistics-extended': [
        TABLE, 'CREATE STATISTICS st (dependencies) ON v, w FROM t',
        'DROP STATISTICS st', 'DROP TABLE t'],
    'text-search': ['CREATE TEXT SEARCH CONFIGURATION ts (COPY = simple)',
                    'DROP TEXT SEARCH CONFIGURATION ts'],
    'maintenance-analyze': [TABLE, 'ANALYZE t', 'DROP TABLE t'],
    'maintenance-vacuum': [TABLE, 'VACUUM t', 'DROP TABLE t'],
    'maintenance-reindex': [TABLE, 'CREATE INDEX rx ON t (v)',
                            'REINDEX TABLE t', 'DROP TABLE t'],
    'maintenance-cluster': [TABLE, 'CREATE INDEX cx ON t (v)',
                            'CLUSTER t USING cx', 'DROP TABLE t'],
    'truncate': [TABLE, 'TRUNCATE t', 'DROP TABLE t'],
    'large-object': ['SELECT lo_unlink(lo_create(0))'],
    'listen-notify': ['LISTEN ch', "NOTIFY ch, 'x'", 'UNLISTEN ch'],
    'owner-change': [TABLE, 'CREATE ROLE ro{suffix}',
                     'ALTER TABLE t OWNER TO ro{suffix}', 'DROP TABLE t',
                     'DROP ROLE ro{suffix}'],
    # CockroachDB-native surface (PostgreSQL is expected to refuse these).
    'crdb-index-hash-sharded': [
        'CREATE TABLE hs (id INT PRIMARY KEY, ts TIMESTAMP)',
        'CREATE INDEX hsi ON hs (ts) USING HASH', 'DROP TABLE hs'],
    'crdb-index-storing': [TABLE, 'CREATE INDEX st ON t (v) STORING (w)',
                           'DROP TABLE t'],
    'crdb-index-inverted': [TABLE, 'CREATE INVERTED INDEX ij ON t (j)',
                            'DROP TABLE t'],
    'crdb-index-visibility': [
        TABLE, 'CREATE INDEX nvi ON t (v) NOT VISIBLE',
        'ALTER INDEX nvi VISIBILITY 0.5', 'ALTER INDEX nvi VISIBLE',
        'DROP TABLE t'],
    'crdb-column-not-visible': [TABLE, 'ALTER TABLE t ADD COLUMN h INT '
                                'NOT VISIBLE', 'DROP TABLE t'],
    'crdb-column-on-update': [
        'CREATE TABLE ou (id INT PRIMARY KEY, v INT, '
        'at TIMESTAMPTZ ON UPDATE now())', 'DROP TABLE ou'],
    'crdb-column-families': [
        'CREATE TABLE cf (a INT PRIMARY KEY, b INT, c INT, '
        'FAMILY f1 (a, b), FAMILY f2 (c))', 'DROP TABLE cf'],
    'crdb-alter-primary-key': [
        TABLE, 'ALTER TABLE t ALTER COLUMN v SET NOT NULL',
        'ALTER TABLE t ALTER PRIMARY KEY USING COLUMNS (v)',
        'DROP TABLE t'],
    'crdb-row-ttl': [
        "CREATE TABLE ttl (id INT PRIMARY KEY) WITH "
        "(ttl_expire_after = '1 day')",
        "ALTER TABLE ttl SET (ttl_job_cron = '@daily')",
        'ALTER TABLE ttl RESET (ttl)', 'DROP TABLE ttl'],
    'crdb-table-partition-list': [
        'CREATE TABLE pl (k INT, id INT, PRIMARY KEY (k, id)) '
        'PARTITION BY LIST (k) (PARTITION p1 VALUES IN (1), '
        'PARTITION pd VALUES IN (DEFAULT))', 'DROP TABLE pl'],
    'crdb-zone-config': [
        TABLE, 'ALTER TABLE t CONFIGURE ZONE USING gc.ttlseconds = 600',
        'ALTER TABLE t CONFIGURE ZONE DISCARD', 'DROP TABLE t'],
    'crdb-split-scatter': [
        TABLE, 'ALTER TABLE t SPLIT AT VALUES (5)',
        'ALTER TABLE t SCATTER', 'ALTER TABLE t UNSPLIT ALL',
        'DROP TABLE t'],
    'crdb-statistics': [TABLE, 'CREATE STATISTICS sv ON v FROM t',
                        'DROP TABLE t'],
    'crdb-database-placement': [
        'ALTER DATABASE {db} SET PRIMARY REGION "local"'],
    'crdb-external-connection': [
        "CREATE EXTERNAL CONNECTION ec{suffix} AS "
        "'nodelocal://1/cde_probe/{suffix}'",
        'DROP EXTERNAL CONNECTION ec{suffix}'],
    'crdb-backup': [
        TABLE, "BACKUP TABLE t INTO 'nodelocal://1/cde_probe/{suffix}'",
        "SHOW BACKUPS IN 'nodelocal://1/cde_probe/{suffix}'",
        'DROP TABLE t'],
    'crdb-backup-schedule': [
        TABLE, "CREATE SCHEDULE cs{suffix} FOR BACKUP TABLE t INTO "
        "'nodelocal://1/cde_probe/s{suffix}' RECURRING '@yearly' "
        "FULL BACKUP ALWAYS",
        "PAUSE SCHEDULES WITH x AS (SHOW SCHEDULES) SELECT id FROM x WHERE "
        "label = 'cs{suffix}'",
        "DROP SCHEDULES WITH x AS (SHOW SCHEDULES) SELECT id FROM x WHERE "
        "label = 'cs{suffix}'", 'DROP TABLE t'],
    'crdb-changefeed': [
        TABLE, "CREATE CHANGEFEED FOR TABLE t INTO 'null://' "
        "WITH initial_scan = 'no'",
        "CANCEL JOBS (SELECT job_id FROM [SHOW CHANGEFEED JOBS] WHERE "
        "sink_uri = 'null://' AND status = 'running')", 'DROP TABLE t'],
    'crdb-export': [
        TABLE, "EXPORT INTO CSV 'nodelocal://1/cde_probe/e{suffix}' "
        'FROM TABLE t', 'DROP TABLE t'],
    'crdb-show-ranges': [TABLE, 'SHOW RANGES FROM TABLE t', 'DROP TABLE t'],
    'crdb-session-setting': ['SET sql_safe_updates = true',
                             'RESET sql_safe_updates'],
    # YugabyteDB YSQL native surface (placement values are the demo node's).
    'ysql-primary-key-hash': [
        'CREATE TABLE yh (id INT, v INT, PRIMARY KEY (id HASH, v ASC))',
        'DROP TABLE yh'],
    'ysql-split-into': [
        'CREATE TABLE ys (id INT PRIMARY KEY) SPLIT INTO 4 TABLETS',
        'DROP TABLE ys'],
    'ysql-split-at': [
        'CREATE TABLE yr (id INT, PRIMARY KEY (id ASC)) '
        'SPLIT AT VALUES ((10), (20))', 'DROP TABLE yr'],
    'ysql-index-hash': [TABLE, 'CREATE INDEX yih ON t (v HASH)',
                        'DROP INDEX yih', 'DROP TABLE t'],
    'ysql-index-split': [TABLE, 'CREATE INDEX yis ON t (v ASC) '
                         'SPLIT AT VALUES ((5))', 'DROP INDEX yis',
                         'DROP TABLE t'],
    'ysql-index-nonconcurrently': [
        TABLE, 'CREATE INDEX NONCONCURRENTLY yin ON t (v)',
        'DROP INDEX yin', 'DROP TABLE t'],
    'ysql-tablespace-placement': [
        "CREATE TABLESPACE yts{suffix} WITH (replica_placement="
        "'{{\"num_replicas\":1,\"placement_blocks\":[{{\"cloud\":"
        "\"cloud1\",\"region\":\"datacenter1\",\"zone\":\"rack1\","
        "\"min_num_replicas\":1}}]}}')",
        'CREATE TABLE ytt (id INT PRIMARY KEY) TABLESPACE yts{suffix}',
        'DROP TABLE ytt', 'DROP TABLESPACE yts{suffix}'],
    'ysql-colocated-database': [
        'CREATE DATABASE {db}_colo WITH COLOCATION = true',
        'DROP DATABASE {db}_colo'],
    'ysql-tablegroup': ['CREATE TABLEGROUP ytg', 'DROP TABLEGROUP ytg'],
    'ysql-hash-code': ['SELECT yb_hash_code(1)'],
    'ysql-table-properties': [
        TABLE, "SELECT * FROM yb_table_properties('t'::regclass)",
        'DROP TABLE t'],
}

# kind: (setup statements, check query, any of these needles, cleanup)
RETENTION = {
    'retained-unlogged': (
        ['CREATE UNLOGGED TABLE ru (id INT PRIMARY KEY)'],
        "SELECT relpersistence FROM pg_class WHERE relname = 'ru'", ['u'],
        ['DROP TABLE ru']),
    'retained-partial-index': (
        [TABLE, 'CREATE INDEX rpi ON t (v) WHERE v > 0'],
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'rpi'",
        ['WHERE'], ['DROP TABLE t']),
    'retained-include': (
        [TABLE, 'CREATE INDEX rii ON t (v) INCLUDE (w)'],
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'rii'",
        ['INCLUDE', 'STORING'], ['DROP TABLE t']),
    'retained-index-method-hash': (
        [TABLE, 'CREATE INDEX rih ON t USING hash (v)'],
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'rih'",
        ['USING hash'], ['DROP TABLE t']),
    'retained-index-method-brin': (
        [TABLE, 'CREATE INDEX rib ON t USING brin (v)'],
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'rib'",
        ['USING brin'], ['DROP TABLE t']),
    'retained-check': (
        [TABLE, 'ALTER TABLE t ADD CONSTRAINT rck CHECK (v > 0)'],
        'SELECT pg_get_constraintdef(oid) FROM pg_constraint '
        "WHERE conname = 'rck'", ['CHECK'], ['DROP TABLE t']),
    'retained-fk-actions': (
        ['CREATE TABLE p (id INT PRIMARY KEY)',
         'CREATE TABLE c (id INT PRIMARY KEY, pid INT, CONSTRAINT rfk '
         'FOREIGN KEY (pid) REFERENCES p (id) ON DELETE CASCADE '
         'ON UPDATE SET NULL)'],
        'SELECT pg_get_constraintdef(oid) FROM pg_constraint '
        "WHERE conname = 'rfk'", ['ON DELETE CASCADE'],
        ['DROP TABLE c', 'DROP TABLE p']),
    'retained-deferrable': (
        ['CREATE TABLE p (id INT PRIMARY KEY)',
         'CREATE TABLE c (id INT PRIMARY KEY, pid INT, CONSTRAINT rdf '
         'FOREIGN KEY (pid) REFERENCES p (id) DEFERRABLE INITIALLY '
         'DEFERRED)'],
        "SELECT condeferrable::TEXT FROM pg_constraint WHERE conname = 'rdf'",
        ['true'], ['DROP TABLE c', 'DROP TABLE p']),
    'retained-generated-virtual': (
        ['CREATE TABLE rgv (a INT PRIMARY KEY, b INT GENERATED ALWAYS AS '
         '(a * 2) VIRTUAL)'],
        "SELECT attgenerated::TEXT FROM pg_attribute WHERE attrelid = "
        "'rgv'::regclass AND attname = 'b'", ['v'], ['DROP TABLE rgv']),
    'retained-identity': (
        ['CREATE TABLE rid (id INT GENERATED ALWAYS AS IDENTITY '
         'PRIMARY KEY)'],
        'SELECT is_identity FROM information_schema.columns WHERE '
        "table_name = 'rid' AND column_name = 'id'", ['YES'],
        ['DROP TABLE rid']),
    'retained-view-check-option': (
        [TABLE, 'CREATE VIEW rvc AS SELECT id, v FROM t WHERE v > 0 '
         'WITH CHECK OPTION'],
        'SELECT check_option FROM information_schema.views WHERE '
        "table_name = 'rvc'", ['CASCADED', 'LOCAL'],
        ['DROP VIEW rvc', 'DROP TABLE t']),
    'retained-security-barrier': (
        [TABLE, 'CREATE VIEW rsb WITH (security_barrier) AS SELECT id '
         'FROM t'],
        "SELECT array_to_string(reloptions, ',') FROM pg_class "
        "WHERE relname = 'rsb'", ['security_barrier'],
        ['DROP VIEW rsb', 'DROP TABLE t']),
    'retained-table-comment': (
        [TABLE, "COMMENT ON TABLE t IS 'probe'"],
        "SELECT obj_description('t'::regclass, 'pg_class')", ['probe'],
        ['DROP TABLE t']),
    'retained-nulls-not-distinct': (
        [TABLE, 'CREATE UNIQUE INDEX rnd ON t (v) NULLS NOT DISTINCT'],
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'rnd'",
        ['NULLS NOT DISTINCT'], ['DROP TABLE t']),
    'retained-sequence-options': (
        ['CREATE SEQUENCE rsq START 10 INCREMENT 2 CACHE 5'],
        'SELECT start_value || \',\' || increment_by || \',\' || '
        "cache_size FROM pg_sequences WHERE sequencename = 'rsq'",
        ['10,2,5'], ['DROP SEQUENCE rsq']),
    # CockroachDB-native clauses, read back from SHOW CREATE TABLE.
    'crdb-retained-hash-sharded': (
        ['CREATE TABLE rhs (id INT PRIMARY KEY, ts TIMESTAMP, '
         'INDEX (ts) USING HASH)'],
        'SELECT create_statement FROM [SHOW CREATE TABLE rhs]',
        ['USING HASH'], ['DROP TABLE rhs']),
    'crdb-retained-storing': (
        [TABLE, 'CREATE INDEX rst ON t (v) STORING (w)'],
        'SELECT create_statement FROM [SHOW CREATE TABLE t]', ['STORING'],
        ['DROP TABLE t']),
    'crdb-retained-not-visible-index': (
        [TABLE, 'CREATE INDEX rnv ON t (v) NOT VISIBLE'],
        'SELECT create_statement FROM [SHOW CREATE TABLE t]',
        ['NOT VISIBLE'], ['DROP TABLE t']),
    'crdb-retained-not-visible-column': (
        [TABLE, 'ALTER TABLE t ADD COLUMN h INT NOT VISIBLE'],
        'SELECT create_statement FROM [SHOW CREATE TABLE t]',
        ['NOT VISIBLE'], ['DROP TABLE t']),
    'crdb-retained-on-update': (
        ['CREATE TABLE rou (id INT PRIMARY KEY, at TIMESTAMPTZ '
         'ON UPDATE now())'],
        'SELECT create_statement FROM [SHOW CREATE TABLE rou]',
        ['ON UPDATE'], ['DROP TABLE rou']),
    'crdb-retained-families': (
        ['CREATE TABLE rcf (a INT PRIMARY KEY, b INT, FAMILY f1 (a), '
         'FAMILY f2 (b))'],
        'SELECT create_statement FROM [SHOW CREATE TABLE rcf]',
        ['FAMILY f2'], ['DROP TABLE rcf']),
    'crdb-retained-row-ttl': (
        ["CREATE TABLE rtl (id INT PRIMARY KEY) WITH "
         "(ttl_expire_after = '1 day')"],
        'SELECT create_statement FROM [SHOW CREATE TABLE rtl]',
        ['ttl_expire_after'], ['DROP TABLE rtl']),
    'crdb-retained-partition': (
        ['CREATE TABLE rpl (k INT, id INT, PRIMARY KEY (k, id)) '
         'PARTITION BY LIST (k) (PARTITION p1 VALUES IN (1))'],
        'SELECT create_statement FROM [SHOW CREATE TABLE rpl]',
        ['PARTITION p1'], ['DROP TABLE rpl']),
    'ysql-retained-primary-key-hash': (
        ['CREATE TABLE ykh (id INT, v INT, PRIMARY KEY (id HASH, v ASC))'],
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'ykh'",
        ['id HASH'], ['DROP TABLE ykh']),
    'ysql-retained-split-into': (
        ['CREATE TABLE ysi (id INT PRIMARY KEY) SPLIT INTO 4 TABLETS'],
        "SELECT num_tablets FROM yb_table_properties('ysi'::regclass)",
        ['4'], ['DROP TABLE ysi']),
    'ysql-retained-split-at': (
        ['CREATE TABLE ysa (id INT, PRIMARY KEY (id ASC)) '
         'SPLIT AT VALUES ((10), (20))'],
        "SELECT num_tablets FROM yb_table_properties('ysa'::regclass)",
        ['3'], ['DROP TABLE ysa']),
    'ysql-retained-tablespace-placement': (
        ["CREATE TABLESPACE ytr{suffix} WITH (replica_placement="
         "'{{\"num_replicas\":1,\"placement_blocks\":[{{\"cloud\":"
         "\"cloud1\",\"region\":\"datacenter1\",\"zone\":\"rack1\","
         "\"min_num_replicas\":1}}]}}')"],
        "SELECT array_to_string(spcoptions, ',') FROM pg_tablespace "
        "WHERE spcname = 'ytr{suffix}'",
        ['placement_blocks'], ['DROP TABLESPACE ytr{suffix}']),
}

# Notices that mean a statement was accepted but not carried out as asked.
IGNORED = re.compile(r'ignor|no-op|not supported|unimplemented|has no effect'
                     r'|will behave as a regular', re.IGNORECASE)
# CockroachDB's routine progress notice for schema changes.
ROUTINE = re.compile(r'^waiting for job\(s\) to complete')

# Settings that gate features, recorded with the results.
SETTINGS = {
    'cockroachdb': {
        'license': 'SHOW CLUSTER SETTING enterprise.license',
        'rangefeeds': 'SHOW CLUSTER SETTING kv.rangefeed.enabled',
        'regions': 'SELECT count(*) FROM [SHOW REGIONS FROM CLUSTER]',
        'locality': 'SHOW LOCALITY',
        'user': 'SELECT current_user',
    },
    'yugabytedb': {
        'superuser': "SELECT current_setting('is_superuser')",
        'placement': "SELECT string_agg(cloud || '.' || region || '.' || "
                     "zone, ',') FROM yb_servers()",
        'servers': 'SELECT count(*) FROM yb_servers()',
        'user': 'SELECT current_user',
    },
    'postgresql': {
        'superuser': "SELECT current_setting('is_superuser')",
        'available_extensions': "SELECT string_agg(name, ',' ORDER BY name) "
                                'FROM pg_available_extensions WHERE name IN '
                                "('fuzzystrmatch', 'postgres_fdw')",
        'user': 'SELECT current_user',
    },
}


class Session:
    """One autocommit connection that keeps the notices each statement
    draws (a failed statement never poisons the next one)."""

    def __init__(self, psycopg, options, database):
        arguments = dict(host=options.host, port=options.port,
                         user=options.user, dbname=database,
                         password=os.environ.get('CDEADMIN_PROBE_PASSWORD',
                                                 ''),
                         sslmode=options.sslmode, autocommit=True,
                         connect_timeout=10)
        for _attempt in range(30):  # a just-started server may refuse
            try:
                self.connection = psycopg.connect(**arguments)
                break
            except psycopg.OperationalError:
                time.sleep(2)
        else:
            self.connection = psycopg.connect(**arguments)
        self.notices = []
        self.connection.add_notice_handler(
            lambda notice: self.notices.append(
                str(notice.message_primary or '')[:200]))
        self.psycopg = psycopg

    def run(self, statement):
        """None on success, else the native error."""
        self.notices.clear()
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(statement)
                if cursor.description is not None:
                    cursor.fetchall()
            return None
        except self.psycopg.Error as error:
            diagnostic = getattr(error, 'diag', None)
            return {'sqlstate': getattr(error, 'sqlstate', None),
                    'msg': str(getattr(diagnostic, 'message_primary', '') or
                               error).strip()[:200]}

    def value(self, query):
        with self.connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
        return None if row is None else row[0]

    def close(self):
        try:
            self.connection.close()
        except self.psycopg.Error:
            pass


def _cleanup(session, statements):
    for statement in statements:
        if statement.upper().startswith(('DROP', 'CANCEL')):
            session.run(statement)


def probe_kind(psycopg, options, database, statements, values):
    session = Session(psycopg, options, database)
    try:
        ignored = []
        for index, statement in enumerate(statements):
            statement = statement.format(**values)
            error = session.run(statement)
            ignored.extend(notice for notice in session.notices
                           if IGNORED.search(notice))
            if error:
                _cleanup(session, [item.format(**values)
                                   for item in statements[index + 1:]])
                return {'step': index, 'statement': ' '.join(
                    statement.split(' ')[:4]), **error}
        if ignored:
            return {'status': 'accepted_with_notice', 'notices': ignored}
        return 'supported'
    finally:
        session.close()


def notices_of(psycopg, options, database, statements, values):
    """Every notice a probe's statements draw, for the record."""
    session = Session(psycopg, options, database)
    found = []
    try:
        for statement in statements:
            session.run(statement.format(**values))
            found.extend(notice for notice in session.notices
                         if not ROUTINE.match(notice))
    finally:
        session.close()
    return found


def probe_retention(psycopg, options, database, setup, check, needles,
                    cleanup, values):
    session = Session(psycopg, options, database)
    try:
        for index, statement in enumerate(setup):
            error = session.run(statement.format(**values))
            if error:
                _cleanup(session, [item.format(**values) for item in cleanup])
                return {'step': f'setup {index}', **error}
        failure = {'step': 'check', 'msg': 'nothing to read back'}
        try:
            text = session.value(check.format(**values))
        except psycopg.Error as error:
            text = None
            failure['msg'] = str(error).strip()[:200]
        _cleanup(session, [item.format(**values) for item in cleanup])
        if text is None:
            return failure
        text = str(text)
        if any(needle.lower() in text.lower() for needle in needles):
            return 'supported'
        return {'msg': 'accepted but not retained: ' +
                ' '.join(text.split())[:200]}
    finally:
        session.close()


def main():
    import psycopg
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--engine', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--maintenance-database', default='postgres')
    parser.add_argument('--sslmode', default='prefer')
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    suffix = uuid.uuid4().hex[:8]
    database = 'cde_probe_' + suffix
    admin = Session(psycopg, options, options.maintenance_database)
    version = admin.value('SELECT version()')
    family = ('cockroachdb' if 'CockroachDB' in version else
              'yugabytedb' if '-YB-' in version else 'postgresql')
    settings = {}
    for key, query in SETTINGS[family].items():
        try:
            settings[key] = str(admin.value(query))[:200]
        except psycopg.Error as error:
            settings[key] = 'unreadable: ' + str(error).strip()[:120]
    setup = admin.run(f'CREATE DATABASE {database}')
    if setup:
        raise SystemExit(f'cannot create the scratch database: {setup}')
    values = {'db': database, 'suffix': suffix}
    results = {}
    try:
        notices = {}
        for kind, statements in PROBES.items():
            results[kind] = probe_kind(psycopg, options, database,
                                       statements, values)
            if results[kind] == 'supported':
                found = notices_of(psycopg, options, database, statements,
                                   values)
                if found:
                    notices[kind] = found
        for kind, (setup_sql, check, needles, cleanup) in RETENTION.items():
            results[kind] = probe_retention(psycopg, options, database,
                                            setup_sql, check, needles,
                                            cleanup, values)
    finally:
        leftovers = admin.run(f'DROP DATABASE IF EXISTS {database} CASCADE'
                              if family == 'cockroachdb' else
                              f'DROP DATABASE IF EXISTS {database} '
                              'WITH (FORCE)')
        roles = []
        try:
            with admin.connection.cursor() as cursor:
                cursor.execute('SELECT rolname FROM pg_roles WHERE rolname '
                               'LIKE %s', (f'%{suffix}',))
                roles = [row[0] for row in cursor.fetchall()]
        except psycopg.Error:
            pass
        admin.close()
    with open(options.output, 'w', encoding='utf-8') as handle:
        json.dump({'engine': options.engine, 'version': version,
                   'settings': settings, 'leftover_roles': roles,
                   'scratch_drop_error': leftovers,
                   'notices_on_supported': notices,
                   'external_storage_prefix': (
                       'nodelocal://1/cde_probe/' + suffix
                       if family == 'cockroachdb' else None),
                   'results': results}, handle, indent=1, sort_keys=True)
        handle.write('\n')
    supported = sum(value == 'supported' for value in results.values())
    print(f'{options.engine}: {supported}/{len(results)} supported')
    if roles or leftovers:
        print(f'WARNING: leftovers: roles {roles}, drop {leftovers}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
