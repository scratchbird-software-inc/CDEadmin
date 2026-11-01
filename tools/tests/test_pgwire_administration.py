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
