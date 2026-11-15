"""Reviewed native DROP must not follow a name onto a replacement relation.

Native cases run only with CDEADMIN_POSTGRESQL_DROP_TEST containing psycopg
connection arguments. Every object and role belongs to a unique test schema.
"""
from copy import deepcopy
from dataclasses import replace
import json
import os
from types import SimpleNamespace
import uuid

import pytest
from psycopg import sql

from pgadmin.cdeadmin.providers.postgresql import destructive_identity as guard
from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider, PostgreSQLStatementRejected
from pgadmin.cdeadmin.core import EndpointContext
from test_ui_descriptor_operations_postgresql import Driver, Permissions, LEGACY_DRIVER_TYPE

SETTINGS = json.loads(os.environ.get('CDEADMIN_POSTGRESQL_DROP_TEST') or 'null')
live = pytest.mark.skipif(SETTINGS is None, reason='CDEADMIN_POSTGRESQL_DROP_TEST is not set')


def request(oid=17000, schema='owned', name='table'):
    return {'resource_kind': 'table', 'operation_id': 'drop', 'draft': {'confirmation': name},
            'target_resource': {'extensions': {'postgresql': {'native': {
                'catalog': 'pg_class', 'oid': oid, 'schema': schema, 'name': name,
                'catalog_row': {'relkind': 'r'}}}}}}


@pytest.mark.parametrize('oid', [None, '17000', True, 0, -1, 2**32])
def test_drop_needs_an_actual_native_oid(oid):
    with pytest.raises(guard.IdentityConflict): guard.target(request(oid))


def test_scope_is_explicit_and_does_not_claim_other_destructive_operations():
    assert guard.applies(request())
    assert not guard.applies({**request(), 'operation_id': 'alter'})
    assert not guard.applies({**request(), 'resource_kind': 'view'})


@pytest.fixture
def native():
    if SETTINGS is None: pytest.skip('CDEADMIN_POSTGRESQL_DROP_TEST is not set')
    import psycopg
    from psycopg.conninfo import make_conninfo
    dsn = make_conninfo(**SETTINGS)
    admin = psycopg.connect(dsn, autocommit=True)
    schema = 'sr_drop_' + uuid.uuid4().hex
    admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    dboid = admin.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()').fetchone()[0]
    providers, roles = [], []

    def provider(role=None):
        context = replace(EndpointContext(endpoint_id=str(uuid.uuid4()), mode='legacy_native',
            experience_family='postgresql', provider_id='org.pgadmin.postgresql', provider_version='9.17.0',
            profile_id='postgresql-native', profile_version='18.3', target_adapter_id='legacy-pgadmin-server',
            target_adapter_version='9.17.0', pool_namespace=str(uuid.uuid4()), session_namespace=str(uuid.uuid4()),
            cache_namespace=str(uuid.uuid4()), diagnostic_namespace=str(uuid.uuid4()),
            effective_permissions=frozenset({'network', 'secret_read', 'data_read', 'data_write', 'administer', 'execute'}),
            legacy_driver_type=LEGACY_DRIVER_TYPE), runtime_verification_state='verified')
        selected = make_conninfo(dsn, options='-c role='+role) if role else dsn
        item = PostgreSQLProvider(context, Permissions(), Driver(selected), catalog_source=object())
        providers.append(item)
        return item

    def create(name='target', partitioned=False):
        suffix = ' PARTITION BY RANGE(id)' if partitioned else ''
        admin.execute(sql.SQL('CREATE TABLE {}.{}(id integer)' + suffix).format(sql.Identifier(schema), sql.Identifier(name)))
        row = admin.execute('SELECT c.oid,n.oid,c.relkind FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s', (schema,name)).fetchone()
        value = request(row[0], schema, name); value['_provider_route'] = {'server_id': 1, 'database_id': dboid}
        value['target_resource']['extensions']['postgresql']['native']['catalog_row'].update(relnamespace=row[1],relkind=row[2])
        if partitioned: value['resource_kind'] = 'partitioned-table'
        return value

    def role():
        value = 'sr_drop_role_' + uuid.uuid4().hex
        admin.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(value))); roles.append(value)
        return value

    def exists(name='target'):
        return int(admin.execute('SELECT COUNT(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s',(schema,name)).fetchone()[0]) == 1

    state = SimpleNamespace(admin=admin, schema=schema, dsn=dsn, dboid=dboid, provider=provider,
                            create=create, role=role, exists=exists)
    installer = provider()
    install_request = {'resource_kind': 'database', 'operation_id': 'install-drop-namespace-guard',
        'draft': {'confirmation': 'INSTALL DROP NAMESPACE GUARD'},
        '_provider_route': {'server_id': 1, 'database_id': dboid}}
    installed = installer.plan_admin_operation(install_request)
    assert installer.apply_admin_operation({'provider_payload': installed['provider_payload']})['transaction_outcome'] == 'committed'
    try: yield state
    finally:
        for item in providers: item.close()
        admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        admin.execute('DROP FUNCTION IF EXISTS pg_catalog.scratchrobin_lock_drop_namespace_v1(oid,oid,text)')
        for value in roles:
            admin.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(value)))
            admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(value)))
        admin.close()


def apply(provider, plan):
    return provider.apply_admin_operation({'provider_payload': plan['provider_payload']})


@live
@pytest.mark.parametrize('partitioned', [False, True])
def test_native_valid_drop_retains_and_locks_the_original_target(native, partitioned):
    p = native.provider(); req = native.create(partitioned=partitioned)
    plan = p.plan_admin_operation(req)
    assert plan['command_preview']['native_target_identity']['relation']['oid'] == guard.target(req)['oid']
    assert apply(p, plan)['transaction_outcome'] == 'committed'
    assert not native.exists()


@live
def test_native_replacement_before_review_is_refused(native):
    p = native.provider(); req = native.create()
    native.admin.execute(sql.SQL('DROP TABLE {}.target').format(sql.Identifier(native.schema)))
    native.create()
    with pytest.raises(PostgreSQLStatementRejected, match='replaced'):
        p.plan_admin_operation(req)
    assert native.exists()


@live
def test_native_replacement_after_review_survives_apply(native):
    p = native.provider(); req = native.create(); plan = p.plan_admin_operation(req)
    native.admin.execute(sql.SQL('DROP TABLE {}.target').format(sql.Identifier(native.schema)))
    replacement = native.create()
    assert guard.target(replacement)['oid'] != guard.target(req)['oid']
    native.admin.execute(sql.SQL('INSERT INTO {}.target VALUES(77)').format(sql.Identifier(native.schema)))
    with pytest.raises(PostgreSQLStatementRejected, match='replaced'):
        apply(p, plan)
    assert native.admin.execute(sql.SQL('SELECT id FROM {}.target').format(sql.Identifier(native.schema))).fetchall() == [(77,)]


@live
def test_native_rename_and_same_name_replacement_do_not_retarget_drop(native):
    p = native.provider(); req = native.create(); plan = p.plan_admin_operation(req)
    native.admin.execute(sql.SQL('ALTER TABLE {}.target RENAME TO retained').format(sql.Identifier(native.schema)))
    native.create()
    with pytest.raises(PostgreSQLStatementRejected): apply(p, plan)
    assert native.exists('retained') and native.exists()


@live
def test_native_same_object_catalog_change_is_stale(native):
    p = native.provider(); plan = p.plan_admin_operation(native.create())
    native.admin.execute(sql.SQL('ALTER TABLE {}.target ADD COLUMN added integer').format(sql.Identifier(native.schema)))
    with pytest.raises(PostgreSQLStatementRejected, match='changed since review'):
        apply(p, plan)
    assert native.exists()


@live
def test_native_contending_replacement_is_not_waited_on_or_replayed(native):
    import psycopg
    p = native.provider(); plan = p.plan_admin_operation(native.create())
    with psycopg.connect(native.dsn) as other:
        other.execute(sql.SQL('DROP TABLE {}.target').format(sql.Identifier(native.schema)))
        other.execute(sql.SQL('CREATE TABLE {}.target(replacement text)').format(sql.Identifier(native.schema)))
        with pytest.raises(PostgreSQLStatementRejected) as failure: apply(p, plan)
        assert failure.value.sqlstate == '55P03'
        other.rollback()
    assert native.exists()


@live
def test_native_guard_holds_the_lock_until_actual_drop_commits(native):
    import psycopg
    p = native.provider(); req = native.create(); binding = p.plan_admin_operation(req)['provider_payload']['destructive_identity']
    with psycopg.connect(native.dsn) as owner:
        guard.lock_and_revalidate(owner, req, binding, native.dboid)
        with psycopg.connect(native.dsn) as contender:
            contender.execute("SET LOCAL lock_timeout='150ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                contender.execute(sql.SQL('DROP TABLE {}.target').format(sql.Identifier(native.schema)))
            contender.rollback()
        owner.execute(p._compile_native_admin(req)['statement']); owner.commit()
    assert not native.exists()


@live
def test_native_unrelated_caller_transaction_is_preserved(native):
    import psycopg
    p = native.provider(); req = native.create(); native.create('pending')
    with psycopg.connect(native.dsn) as caller:
        caller.execute(sql.SQL('INSERT INTO {}.pending VALUES(5)').format(sql.Identifier(native.schema)))
        caller.execute('SAVEPOINT caller_savepoint')
        apply(p, p.plan_admin_operation(req))
        assert native.admin.execute(sql.SQL('SELECT COUNT(*) FROM {}.pending').format(sql.Identifier(native.schema))).fetchone() == (0,)
        caller.execute('ROLLBACK TO caller_savepoint'); caller.rollback()
    assert not native.exists()


@live
def test_native_table_owner_does_not_need_cluster_control_privilege(native):
    p = native.provider(); req = native.create(); role = native.role()
    native.admin.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(native.schema),sql.Identifier(role)))
    native.admin.execute(sql.SQL('ALTER TABLE {}.target OWNER TO {}').format(sql.Identifier(native.schema),sql.Identifier(role)))
    owner = native.provider(role); plan = owner.plan_admin_operation(req)
    assert plan['provider_payload']['destructive_identity']['context']['effective_principal'] == role
    apply(owner, plan); assert not native.exists()


@live
def test_native_schema_owner_only_drop_uses_native_catalog_locks_without_table_privilege(native):
    req = native.create(); role = native.role()
    native.admin.execute(sql.SQL('ALTER SCHEMA {} OWNER TO {}').format(sql.Identifier(native.schema),sql.Identifier(role)))
    owner = native.provider(role); plan = owner.plan_admin_operation(req)
    apply(owner, plan)
    assert not native.exists()
    assert native.admin.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname LIKE 'sr_drop_guard_%%'",(native.schema,)).fetchone()==(0,)


@live
def test_native_other_cluster_with_same_database_parent_and_table_oids_cannot_receive_drop(native, tmp_path):
    import psycopg
    from psycopg.conninfo import make_conninfo
    from tools.postgresql_qualification_support import server
    p = native.provider(); req = native.create(); plan = p.plan_admin_operation(req)
    expected = guard.target(req)
    with server(tmp_path/'other-server') as (route, password, fixture):
        other_dsn = make_conninfo(host=route['host'], port=route['port'], user=route['user'],
                                  password=password, dbname=route['database'])
        with psycopg.connect(other_dsn, autocommit=True) as other:
            # Consume native schema OIDs, never edit catalogs or force OIDs.
            # The independent clusters must really have colliding addresses.
            for _ in range(4096):
                other.execute('CREATE SCHEMA sr_oid_alignment')
                oid = other.execute("SELECT oid FROM pg_namespace WHERE nspname='sr_oid_alignment'").fetchone()[0]
                other.execute('DROP SCHEMA sr_oid_alignment')
                if oid >= expected['schema_oid'] - 1: break
            assert oid == expected['schema_oid'] - 1
            other.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(native.schema)))
            from pgadmin.cdeadmin.providers.postgresql.namespace_guard import INSTALL
            other.execute(INSTALL)
            other.execute(sql.SQL('CREATE TABLE {}.target(id integer)').format(sql.Identifier(native.schema)))
            actual = other.execute('SELECT c.oid,n.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s',(native.schema,'target')).fetchone()
            assert actual == (expected['oid'], expected['schema_oid'])
            assert other.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone() == (native.dboid,)
            other.execute(sql.SQL('INSERT INTO {}.target VALUES(99)').format(sql.Identifier(native.schema)))
            p._driver._manager._dsn = other_dsn
            with pytest.raises(PostgreSQLStatementRejected, match='server, principal or table changed'):
                apply(p, plan)
            assert other.execute(sql.SQL('SELECT id FROM {}.target').format(sql.Identifier(native.schema))).fetchall() == [(99,)]
    assert fixture['owned_server_stopped'] and native.exists()


@live
def test_native_schema_move_with_same_name_replacement_preserves_both_targets(native):
    p = native.provider(); req = native.create(); plan = p.plan_admin_operation(req)
    other_schema = native.schema + '_moved'
    native.admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(other_schema)))
    try:
        native.admin.execute(sql.SQL('ALTER TABLE {}.target SET SCHEMA {}').format(sql.Identifier(native.schema), sql.Identifier(other_schema)))
        native.create()
        with pytest.raises(PostgreSQLStatementRejected): apply(p, plan)
        assert native.exists()
        assert native.admin.execute('SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s',(other_schema,'target')).fetchone() == (1,)
    finally:
        native.admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(other_schema)))


@live
@pytest.mark.parametrize('name', [' quoted"雪; -- ', ' '])
def test_native_quoted_names_keep_exact_identity_through_lock_and_drop(native, name):
    p = native.provider(); req = native.create(name=name)
    apply(p, p.plan_admin_operation(req))
    assert not native.exists(name)


@live
def test_native_schema_owner_catalog_guard_blocks_competing_drop_until_rollback(native):
    import psycopg
    from psycopg.conninfo import make_conninfo
    req=native.create();role=native.role()
    native.admin.execute(sql.SQL('ALTER SCHEMA {} OWNER TO {}').format(sql.Identifier(native.schema),sql.Identifier(role)))
    with psycopg.connect(make_conninfo(native.dsn,options='-c role='+role)) as owner:
        binding=guard.observe(owner,guard.target(req),native.dboid)
        guard.lock_and_revalidate(owner,req,binding,native.dboid)
        assert owner.execute("SELECT count(*)::integer FROM pg_class WHERE relnamespace=%s AND relname LIKE 'sr_drop_guard_%%'",(binding['relation']['schema_oid'],)).fetchone()==(0,)
        with psycopg.connect(native.dsn) as competitor:
            competitor.execute("SET LOCAL lock_timeout='25ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                competitor.execute(sql.SQL('DROP TABLE {}.target').format(sql.Identifier(native.schema)))
            competitor.rollback()
        owner.rollback()
    assert native.exists()


def test_native_identity_observation_uses_stable_rows_with_inherited_driver_cursor(native):
    import psycopg
    from pgadmin.utils.driver.psycopg3.cursor import DictCursor
    request=native.create()
    with psycopg.connect(native.dsn,autocommit=True,cursor_factory=DictCursor)as inherited:
        # This inherited cursor intentionally returns tuples from fetchone,
        # even if callers request row_factory=dict_row. The identity guard must
        # use a native cursor whose row contract it owns.
        assert isinstance(inherited.execute('SELECT 1 AS value').fetchone(),tuple)
        observed=guard.observe(inherited,guard.target(request),native.dboid)
        assert observed['relation']['oid']==request['target_resource']['extensions']['postgresql']['native']['oid']
        assert observed['context']['database_oid']==native.dboid


@live
@pytest.mark.parametrize('schema_owner', [False, True])
def test_namespace_cannot_be_renamed_after_final_identity_check(native, monkeypatch, schema_owner):
    import psycopg
    req = native.create()
    role = native.role() if schema_owner else None
    if role:
        native.admin.execute(sql.SQL('ALTER SCHEMA {} OWNER TO {}').format(
            sql.Identifier(native.schema), sql.Identifier(role)))
    p = native.provider(role); plan = p.plan_admin_operation(req)
    original = guard.lock_and_revalidate
    attempted = []
    def after_check(*args, **kwargs):
        result = original(*args, **kwargs)
        with psycopg.connect(native.dsn, autocommit=True) as competitor:
            competitor.execute("SET lock_timeout='100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                competitor.execute(sql.SQL('ALTER SCHEMA {} RENAME TO {}').format(
                    sql.Identifier(native.schema), sql.Identifier(native.schema+'_moved')))
            with pytest.raises(psycopg.errors.LockNotAvailable):
                competitor.execute(sql.SQL('ALTER TABLE {}.target RENAME TO target_moved').format(
                    sql.Identifier(native.schema)))
            attempted.append(True)
        return result
    monkeypatch.setattr(guard, 'lock_and_revalidate', after_check)
    assert apply(p, plan)['transaction_outcome'] == 'committed'
    assert attempted == [True] and not native.exists()


@live
def test_ordinary_owner_without_installed_namespace_helper_is_refused(native):
    req = native.create(); role = native.role()
    native.admin.execute(sql.SQL('ALTER SCHEMA {} OWNER TO {}').format(
        sql.Identifier(native.schema), sql.Identifier(role)))
    p = native.provider(role); plan = p.plan_admin_operation(req)
    native.admin.execute('DROP FUNCTION pg_catalog.scratchrobin_lock_drop_namespace_v1(oid,oid,text)')
    with pytest.raises(PostgreSQLStatementRejected, match='namespace DROP guard'):
        apply(p, plan)
    assert native.exists()


@live
def test_table_owner_without_table_acl_or_schema_create_can_still_drop(native):
    req = native.create(); role = native.role()
    native.admin.execute(sql.SQL('ALTER TABLE {}.target OWNER TO {}').format(
        sql.Identifier(native.schema),sql.Identifier(role)))
    native.admin.execute(sql.SQL('REVOKE ALL ON {}.target FROM {}').format(
        sql.Identifier(native.schema),sql.Identifier(role)))
    native.admin.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(
        sql.Identifier(native.schema),sql.Identifier(role)))
    p = native.provider(role);plan=p.plan_admin_operation(req)
    assert apply(p,plan)['transaction_outcome']=='committed'
    assert not native.exists()
