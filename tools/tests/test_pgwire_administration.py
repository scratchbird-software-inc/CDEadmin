"""PG-wire native administration shared by CockroachDB and YugabyteDB.

Each feature was executed and read back live on CockroachDB 26.1.3 and
YugabyteDB 2025.2.2.2 (2026-11-01) before it was declared.
"""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    NATIVE_ADMINISTRATION as COCKROACH,
)
from pgadmin.cdeadmin.providers.yugabytedb.control_plane import (  # noqa
    NATIVE_ADMINISTRATION as YUGABYTE,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

TABLE = {'display_name': 't', 'display_path': ['s', 't']}
CONSTRAINT = {'display_name': 'ck', 'display_path': ['s', 't', 'ck']}
ROLE = {'display_name': 'r', 'display_path': ['r']}
DATABASE = {'display_name': 'd', 'display_path': ['d']}
TYPE = {'display_name': 'ty', 'display_path': ['s', 'ty']}


def sql(native, kind, operation, draft, target):
    return [item['source'] for item in native.statements({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': target})]


@pytest.mark.parametrize('native', [COCKROACH, YUGABYTE])
def test_shared_statements(native):
    assert sql(native, 'table', 'truncate', {'cascade': True}, TABLE) == [
        'TRUNCATE TABLE "s"."t" CASCADE']
    assert sql(native, 'table', 'analyze', {}, TABLE) == ['ANALYZE "s"."t"']
    assert sql(native, 'table', 'set_schema', {'schema': 'n"x'}, TABLE) == [
        'ALTER TABLE "s"."t" SET SCHEMA "n""x"']
    with pytest.raises(RelationalClientError, match='already'):
        sql(native, 'table', 'set_schema', {'schema': 's'}, TABLE)
    assert sql(native, 'table', 'set_owner', {'owner': 'o'}, TABLE) == [
        'ALTER TABLE "s"."t" OWNER TO "o"']
    assert sql(native, 'constraint', 'validate', {}, CONSTRAINT) == [
        'ALTER TABLE "s"."t" VALIDATE CONSTRAINT "ck"']
    assert sql(native, 'role', 'set_setting', {
        'setting': 'statement_timeout', 'value': "9'00"}, ROLE) == [
        "ALTER ROLE \"r\" SET statement_timeout = '9''00'"]
    assert sql(native, 'user', 'set_setting', {
        'setting': 'search_path', 'value': 'public', 'database': 'd'},
        ROLE) == ["ALTER ROLE \"r\" IN DATABASE \"d\" SET search_path = "
                  "'public'"]
    # Database session defaults are the database editor's settings grid.
    assert not native.supports('database', 'set_setting')
    with pytest.raises(RelationalClientError, match='unavailable'):
        sql(native, 'database', 'reset_setting', {
            'setting': 'statement_timeout'}, DATABASE)
    for setting in ('Bad', 'a;b', 'x y'):
        with pytest.raises(RelationalClientError, match='setting'):
            sql(native, 'role', 'reset_setting', {'setting': setting}, ROLE)
    assert sql(native, 'type', 'grant', {
        'principal': 'u', 'privileges': ['USAGE'], 'grant_option': True},
        TYPE) == ['GRANT USAGE ON TYPE "s"."ty" TO "u" WITH GRANT OPTION']
    assert sql(native, 'schema', 'revoke', {
        'principal': 'u', 'privileges': ['USAGE', 'CREATE']},
        {'display_name': 's', 'display_path': ['s']}) == [
        'REVOKE CREATE, USAGE ON SCHEMA "s" FROM "u"']


def test_privileges_are_only_those_each_engine_reads_back():
    # CockroachDB accepts DROP, RESTORE and ZONECONFIG on a database but
    # never shows them in SHOW GRANTS; YugabyteDB has TEMPORARY instead.
    assert sql(COCKROACH, 'database', 'grant', {
        'principal': 'u', 'privileges': ['BACKUP', 'CONNECT']},
        DATABASE) == ['GRANT CONNECT, BACKUP ON DATABASE "d" TO "u"']
    for privilege in ('DROP', 'RESTORE', 'ZONECONFIG', 'TEMPORARY'):
        with pytest.raises(RelationalClientError, match='privilege'):
            sql(COCKROACH, 'database', 'grant', {
                'principal': 'u', 'privileges': [privilege]}, DATABASE)
    assert sql(YUGABYTE, 'database', 'grant', {
        'principal': 'u', 'privileges': ['TEMPORARY']}, DATABASE) == [
        'GRANT TEMPORARY ON DATABASE "d" TO "u"']
    with pytest.raises(RelationalClientError, match='privilege'):
        sql(YUGABYTE, 'database', 'grant', {
            'principal': 'u', 'privileges': ['BACKUP']}, DATABASE)


def test_sessions_use_each_engines_identity():
    cockroach = {'display_name': '18e3f1784449eb040000000000000001',
                 'display_path': ['18e3f1784449eb040000000000000001']}
    assert sql(COCKROACH, 'session', 'terminate_connection', {},
               cockroach) == [
        "CANCEL SESSION '18e3f1784449eb040000000000000001'"]
    assert sql(COCKROACH, 'session', 'terminate_query', {}, cockroach) == [
        'CANCEL QUERIES (SELECT query_id FROM [SHOW CLUSTER STATEMENTS] '
        "WHERE session_id = '18e3f1784449eb040000000000000001')"]
    pid = {'display_name': '4242', 'display_path': ['4242']}
    assert sql(YUGABYTE, 'session', 'terminate_query', {}, pid) == [
        'SELECT pg_cancel_backend(4242)']
    assert sql(YUGABYTE, 'session', 'terminate_connection', {}, pid) == [
        'SELECT pg_terminate_backend(4242)']
    for native, bad in ((COCKROACH, pid), (YUGABYTE, cockroach),
                        (YUGABYTE, {'display_path': ["1'; --"]})):
        with pytest.raises(RelationalClientError, match='session'):
            sql(native, 'session', 'terminate_query', {}, bad)


def plan(kind, operation, draft, target):
    return {'resource_kind': kind, 'operation_id': operation,
            'draft': draft, 'target_resource': target}


def test_confirmation_reads_the_exact_state():
    setting = plan('role', 'set_setting', {
        'setting': 'statement_timeout', 'value': '9s'}, ROLE)
    assert YUGABYTE.confirmed(setting, [(['statement_timeout=9s'],)])
    assert not YUGABYTE.confirmed(setting, [(['statement_timeout=8s'],)])
    reset = plan('role', 'reset_setting', {'setting': 'statement_timeout'},
                 ROLE)
    assert YUGABYTE.confirmed(reset, [(['search_path=public'],)])
    assert not YUGABYTE.confirmed(reset, [(['statement_timeout=9s'],)])
    grant = plan('database', 'grant', {
        'principal': 'u', 'privileges': ['CONNECT'], 'grant_option': True},
        DATABASE)
    assert COCKROACH.confirmed(grant, [('CONNECT', True)])
    assert not COCKROACH.confirmed(grant, [('CONNECT', False)])
    assert not COCKROACH.confirmed(grant, [])
    revoke = plan('database', 'revoke', {
        'principal': 'u', 'privileges': ['CONNECT']}, DATABASE)
    assert COCKROACH.confirmed(revoke, [('CREATE', False)])
    assert not COCKROACH.confirmed(revoke, [('CONNECT', False)])
    analyze = plan('table', 'analyze', {}, TABLE)
    assert YUGABYTE.confirmed(analyze, [(True,)])
    for rows in ([(False,)], [(None,)], []):
        assert not YUGABYTE.confirmed(analyze, rows)
    cancel = {'display_name': '7', 'display_path': ['7']}
    query = plan('session', 'terminate_query', {}, cancel)
    assert YUGABYTE.confirmed(query, [(7, 'idle')])
    assert not YUGABYTE.confirmed(query, [(7, 'active')])
    session = '18e3f1784449eb040000000000000001'
    cluster = plan('session', 'terminate_query', {},
                   {'display_name': session, 'display_path': [session]})
    assert COCKROACH.confirmed(cluster, [(session, '')])
    assert not COCKROACH.confirmed(cluster, [(session, 'SELECT 1')])


# Partitions after create, single-column keys (live, 2026-11-01).
PARENT = {'display_name': 'p', 'display_path': ['s', 'p']}


def test_yugabytedb_partition_bounds_are_typed_values():
    assert sql(YUGABYTE, 'table', 'create_partition', {
        'name': 'p1', 'bound': 'RANGE', 'from_mode': 'MINVALUE',
        'to_mode': 'VALUE', 'to_value': "1'0"}, PARENT) == [
        'CREATE TABLE "s"."p1" PARTITION OF "s"."p" FOR VALUES FROM '
        "(MINVALUE) TO ('1''0')"]
    assert sql(YUGABYTE, 'table', 'attach_partition', {
        'table': 'q', 'bound': 'LIST',
        'in_values': [{'value': 'a'}, {'value': 'b'}]}, PARENT) == [
        'ALTER TABLE "s"."p" ATTACH PARTITION "s"."q" FOR VALUES IN '
        "('a', 'b')"]
    assert sql(YUGABYTE, 'table', 'create_partition', {
        'name': 'h', 'bound': 'HASH', 'modulus': 4, 'remainder': 3},
        PARENT) == ['CREATE TABLE "s"."h" PARTITION OF "s"."p" FOR VALUES '
                    'WITH (MODULUS 4, REMAINDER 3)']
    assert sql(YUGABYTE, 'table', 'create_partition', {
        'name': 'd', 'bound': 'DEFAULT'}, PARENT) == [
        'CREATE TABLE "s"."d" PARTITION OF "s"."p" DEFAULT']
    assert sql(YUGABYTE, 'partition', 'detach', {}, {
        'display_name': 'q', 'display_path': ['s', 'p', 'q']}) == [
        'ALTER TABLE "s"."p" DETACH PARTITION "s"."q"']
    for draft in ({'bound': 'HASH', 'modulus': 4, 'remainder': 4},
                  {'bound': 'LIST', 'in_values': []},
                  {'bound': 'LIST', 'in_values': ['a', 'a']},
                  {'bound': 'RANGE', 'from_mode': 'VALUE',
                   'from_value': 'a\nb', 'to_mode': 'MAXVALUE'},
                  {'bound': 'SOMETIMES'}):
        with pytest.raises(RelationalClientError):
            sql(YUGABYTE, 'table', 'create_partition',
                {'name': 'x', **draft}, PARENT)
    assert not COCKROACH.supports('table', 'create_partition')


def test_cockroachdb_repartition():
    assert sql(COCKROACH, 'table', 'repartition', {
        'strategy': 'LIST', 'column': 'k', 'list_partitions': [
            {'partition': 'p1', 'value': '1'},
            {'partition': 'p1', 'value': '2'},
            {'partition': 'pd', 'default': True}]}, PARENT) == [
        'ALTER TABLE "s"."p" PARTITION BY LIST ("k") (PARTITION "p1" '
        "VALUES IN ('1', '2'), PARTITION \"pd\" VALUES IN (DEFAULT))"]
    assert sql(COCKROACH, 'table', 'repartition', {
        'strategy': 'RANGE', 'column': 'k', 'range_partitions': [
            {'partition': 'lo', 'from_mode': 'MINVALUE', 'to_value': '10'},
            {'partition': 'hi', 'from_value': '10',
             'to_mode': 'MAXVALUE'}]}, PARENT) == [
        'ALTER TABLE "s"."p" PARTITION BY RANGE ("k") (PARTITION "lo" '
        "VALUES FROM (MINVALUE) TO ('10'), PARTITION \"hi\" VALUES FROM "
        "('10') TO (MAXVALUE))"]
    assert sql(COCKROACH, 'table', 'repartition', {
        'strategy': 'NOTHING'}, PARENT) == [
        'ALTER TABLE "s"."p" PARTITION BY NOTHING']
    with pytest.raises(RelationalClientError, match='column'):
        sql(COCKROACH, 'table', 'repartition', {
            'strategy': 'LIST', 'list_partitions': [
                {'partition': 'a', 'value': '1'}]}, PARENT)
    with pytest.raises(RelationalClientError, match='repeats'):
        sql(COCKROACH, 'table', 'repartition', {
            'strategy': 'RANGE', 'column': 'k', 'range_partitions': [
                {'partition': 'a', 'from_mode': 'MINVALUE',
                 'to_mode': 'MAXVALUE'}] * 2}, PARENT)


def test_partition_confirmation_reads_the_stored_bound():
    attach = plan('table', 'attach_partition', {
        'table': 'q', 'bound': 'LIST', 'in_values': ['b', "a'x"]}, PARENT)
    assert YUGABYTE.confirmed(attach, [('p', "FOR VALUES IN ('a''x', 'b')")])
    assert not YUGABYTE.confirmed(attach, [('p', "FOR VALUES IN ('b')")])
    assert not YUGABYTE.confirmed(attach, [('other', "FOR VALUES IN "
                                            "('a''x', 'b')")])
    ranged = plan('table', 'create_partition', {
        'name': 'r', 'bound': 'RANGE', 'from_value': '0', 'to_value': '10'},
        PARENT)
    assert YUGABYTE.confirmed(ranged, [('p', 'FOR VALUES FROM (0) TO (10)')])
    assert not YUGABYTE.confirmed(ranged, [('p', 'FOR VALUES FROM (10) '
                                                 'TO (0)')])
    detach = plan('partition', 'detach', {}, {
        'display_name': 'q', 'display_path': ['s', 'p', 'q']})
    assert YUGABYTE.confirmed(detach, [(None, None)])
    assert not YUGABYTE.confirmed(detach, [('p', 'DEFAULT')])
    assert not YUGABYTE.confirmed(detach, [])  # the table itself is gone
    listed = plan('table', 'repartition', {
        'strategy': 'LIST', 'column': 'k', 'list_partitions': [
            {'partition': 'p1', 'value': '2'},
            {'partition': 'p1', 'value': '1'},
            {'partition': 'pd', 'default': True}]}, PARENT)
    assert COCKROACH.confirmed(listed, [('p1', 'k', '(1), (2)'),
                                        ('pd', 'k', '(DEFAULT)')])
    assert not COCKROACH.confirmed(listed, [('p1', 'k', '(1)'),
                                            ('pd', 'k', '(DEFAULT)')])
    removed = plan('table', 'repartition', {'strategy': 'NOTHING'}, PARENT)
    assert COCKROACH.confirmed(removed, [])
    assert not COCKROACH.confirmed(removed, [('p1', 'k', '(1)')])


def test_partition_inspection_reads_partitions_not_table_facts():
    issued = []

    def query(source, parameters=()):
        issued.append(source)
        return {'rows': []}
    YUGABYTE.inspect(plan('table', 'attach_partition', {
        'table': 'q', 'bound': 'DEFAULT'}, PARENT), query)
    COCKROACH.inspect(plan('table', 'repartition', {
        'strategy': 'NOTHING'}, PARENT), query)
    assert 'relpartbound' in issued[0] and 'SHOW PARTITIONS' in issued[1]


# CockroachDB's own administration (live, 2026-11-01).
SETTING = {'display_name': 'sql.log.slow_query.latency_threshold',
           'display_path': ['sql.log.slow_query.latency_threshold']}


def test_cockroachdb_cluster_settings():
    assert sql(COCKROACH, 'cluster-setting', 'set_value', {'value': '7s'},
               SETTING) == ["SET CLUSTER SETTING "
                            "sql.log.slow_query.latency_threshold = '7s'"]
    assert sql(COCKROACH, 'cluster-setting', 'reset', {}, SETTING) == [
        'RESET CLUSTER SETTING sql.log.slow_query.latency_threshold']
    with pytest.raises(RelationalClientError, match='setting name'):
        sql(COCKROACH, 'cluster-setting', 'reset', {},
            {'display_path': ['a; DROP TABLE x']})
    set_value = plan('cluster-setting', 'set_value', {'value': '40MiB'},
                     SETTING)
    assert COCKROACH.confirmed(set_value, [('40 MiB', 'override')])
    assert not COCKROACH.confirmed(set_value, [('32 MiB', 'override')])
    assert not COCKROACH.confirmed(set_value, [('40 MiB', 'default')])
    reset = plan('cluster-setting', 'reset', {}, SETTING)
    assert COCKROACH.confirmed(reset, [('0s', 'default')])
    assert not COCKROACH.confirmed(reset, [('7s', 'override')])
    assert not YUGABYTE.supports('cluster-setting', 'set_value')


def test_cockroachdb_system_privileges():
    assert sql(COCKROACH, 'user', 'grant_system', {
        'privileges': ['VIEWJOB', 'VIEWACTIVITY'], 'grant_option': True},
        ROLE) == ['GRANT SYSTEM VIEWACTIVITY, VIEWJOB TO "r" WITH GRANT '
                  'OPTION']
    assert sql(COCKROACH, 'role', 'revoke_system', {
        'privileges': ['BACKUP']}, ROLE) == ['REVOKE SYSTEM BACKUP FROM "r"']
    # Accepted by GRANT but shown only as REPAIRCLUSTER.
    with pytest.raises(RelationalClientError, match='privilege'):
        sql(COCKROACH, 'role', 'grant_system', {
            'privileges': ['REPAIRCLUSTERMETADATA']}, ROLE)
    grant = plan('role', 'grant_system', {'privileges': ['VIEWJOB'],
                                          'grant_option': True}, ROLE)
    assert COCKROACH.confirmed(grant, [('VIEWJOB', True)])
    assert not COCKROACH.confirmed(grant, [('VIEWJOB', False)])
    revoke = plan('role', 'revoke_system', {'privileges': ['VIEWJOB']}, ROLE)
    assert COCKROACH.confirmed(revoke, [])
    assert not COCKROACH.confirmed(revoke, [('VIEWJOB', False)])


def test_cockroachdb_splits_and_storage_parameters():
    assert sql(COCKROACH, 'table', 'split_at', {
        'split_values': [{'value': '5'}, {'value': "m'x"}]}, TABLE) == [
        "ALTER TABLE \"s\".\"t\" SPLIT AT VALUES ('5'), ('m''x')"]
    split = plan('table', 'split_at', {'split_values': ['5', "m'x"]}, TABLE)
    assert COCKROACH.confirmed(split, [('<before:/Table/1>',), ('…/1/5',),
                                       ('…/1/"m\'x"',)])
    assert not COCKROACH.confirmed(split, [('…/1/15',), ('…/1/"m\'x"',)])
    # Only backslash and double quote are escaped (live).
    quoted = plan('table', 'split_at', {'split_values': ['a"b\\c']}, TABLE)
    assert COCKROACH.confirmed(quoted, [('…/1/"a\\"b\\\\c"',)])
    assert sql(COCKROACH, 'table', 'set_storage_parameter', {
        'parameter': 'exclude_data_from_backup', 'value': 'TRUE'}, TABLE) == [
        'ALTER TABLE "s"."t" SET (exclude_data_from_backup = true)']
    assert sql(COCKROACH, 'table', 'reset_storage_parameter', {
        'parameter': 'schema_locked'}, TABLE) == [
        'ALTER TABLE "s"."t" RESET (schema_locked)']
    for parameter, value in (('fillfactor', '70'),
                             ('sql_stats_histogram_buckets_count', '1.5'),
                             ('exclude_data_from_backup', 'yes')):
        with pytest.raises(RelationalClientError):
            sql(COCKROACH, 'table', 'set_storage_parameter', {
                'parameter': parameter, 'value': value}, TABLE)
    stored = plan('table', 'set_storage_parameter', {
        'parameter': 'sql_stats_automatic_collection_fraction_stale_rows',
        'value': '0.5'}, TABLE)
    assert COCKROACH.confirmed(stored, [(
        ['sql_stats_automatic_collection_fraction_stale_rows=0.5'],)])
    assert not COCKROACH.confirmed(stored, [(['schema_locked=true'],)])


def test_schema_locked_false_is_recorded_by_removal():
    unlocked = plan('table', 'set_storage_parameter', {
        'parameter': 'schema_locked', 'value': 'false'}, TABLE)
    assert COCKROACH.confirmed(unlocked, [(None,)])
    assert not COCKROACH.confirmed(unlocked, [(['schema_locked=true'],)])
    locked = plan('table', 'set_storage_parameter', {
        'parameter': 'schema_locked', 'value': 'true'}, TABLE)
    assert not COCKROACH.confirmed(locked, [(None,)])
    # Only schema_locked: another false is stored explicitly.
    stats = plan('table', 'set_storage_parameter', {
        'parameter': 'sql_stats_forecasts_enabled', 'value': 'false'}, TABLE)
    assert not COCKROACH.confirmed(stats, [(None,)])
