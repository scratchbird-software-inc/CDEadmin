"""Native retained-session catalog and transaction preservation qualification."""
import json
import secrets
from collections import Counter


def qualify(provider, route, password, server, user, receipt, evidence):
    import psycopg
    from psycopg import Cursor, sql
    from psycopg.rows import tuple_row
    from psycopg.pq import TransactionStatus
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProviderError
    from pgadmin.cdeadmin.providers.postgresql import session_catalog
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    selected = {'server_id': server.id, 'owner_id': user.id,
        'principal_reference': 'worker:proof', 'credential_reference_id': 'proof-password'}
    opened = provider.open_session({'route': selected})
    state = provider._sessions[opened['session_id']]
    provider._ensure_native_connection(state)
    connection = state.connection.conn
    other = psycopg.connect(host=route['host'], port=route['port'], user=route['user'], password=password,
        dbname=route['database'], autocommit=True, row_factory=tuple_row, **route.get('connection_params', {}))
    prefix = 'sr_session_' + secrets.token_hex(8)
    names = [prefix + suffix for suffix in ('_temp', '_pending', '_new_temp', '_other')]
    request = {'session_id': opened['session_id'], 'language_profile': 'postgresql-sql'}
    checks = []
    def observe():
        return provider.capture_session_catalog(request)
    def context():
        with Cursor(connection, row_factory=tuple_row) as cursor:
            cursor.execute("SELECT current_setting('search_path'),current_setting('standard_conforming_strings'),current_setting('statement_timeout'),current_setting('lock_timeout')")
            return cursor.fetchone()
    def relations(captured):
        return {item['display_name']:item for item in captured['resources'] if item['native'].get('catalog') == 'pg_class'}
    original_capture = session_catalog.capture
    try:
        with Cursor(connection, row_factory=tuple_row) as cursor:
            cursor.execute(sql.SQL('CREATE TEMP TABLE {} (id int PRIMARY KEY, "Value ü" text CHECK (length("Value ü") > 0))').format(sql.Identifier(names[0])))
            cursor.execute(sql.SQL('INSERT INTO {} VALUES (1,\'retained\')').format(sql.Identifier(names[0])))
        # This fixture provider uses autocommit. Establish the baseline temp
        # object before entering a user-owned transaction.
        if connection.info.transaction_status == TransactionStatus.INTRANS:
            connection.commit()
        other.execute(sql.SQL('CREATE TEMP TABLE {} (id int, value text)').format(sql.Identifier(names[3])))
        idle = observe()
        assert connection.info.transaction_status == TransactionStatus.IDLE
        assert names[0] in relations(idle) and names[3] not in relations(idle)
        assert relations(idle)[names[0]]['native']['session_local'] is True
        checks.append('idle-capture-includes-own-temp-excludes-other-backend-temp-and-leaves-no-transaction')
        all_objects = provider.capture_session_catalog({**request, 'include_system':True})
        other_temp = other.execute('SELECT nspname FROM pg_namespace WHERE oid=pg_my_temp_schema()').fetchone()[0]
        other_toast = 'pg_toast_temp_' + other_temp.removeprefix('pg_temp_')
        assert not any(item['native'].get('schema') in {other_temp,other_toast} for item in all_objects['resources'])
        assert any(item['native'].get('schema', '').startswith('pg_toast_temp_') for item in all_objects['resources'] if item['native'].get('schema'))
        checks.append('system-inclusive-capture-keeps-own-toast-and-excludes-other-temporary-and-toast-namespaces')
        with Cursor(connection, row_factory=tuple_row) as cursor:
            cursor.execute('BEGIN')
            cursor.execute("SET LOCAL search_path=public; SET LOCAL standard_conforming_strings=off; SET LOCAL statement_timeout='90s'; SET LOCAL lock_timeout='5s'")
            cursor.execute(sql.SQL('CREATE TABLE public.{} (id int)').format(sql.Identifier(names[1])))
            cursor.execute(sql.SQL('INSERT INTO public.{} VALUES (42)').format(sql.Identifier(names[1])))
            cursor.execute(sql.SQL('CREATE TEMP TABLE {} (id int, amount numeric(38,12))').format(sql.Identifier(names[2])))
        before = context()
        pending = observe()
        assert connection.info.transaction_status == TransactionStatus.INTRANS and context() == before
        observed = relations(pending)
        assert {names[0], names[1], names[2]} <= observed.keys() and names[3] not in observed
        native = observed[names[0]]['native']
        attributes = native['children']['pg_attribute']
        assert [row['attname'] for row in attributes] == ['id', 'Value ü']
        assert any(item['resource_kind'] == 'constraint' and item['native']['navigator_parent_resource_id'] == observed[names[0]]['resource_id'] for item in pending['resources'])
        reconciled = []
        with Cursor(connection, row_factory=tuple_row) as cursor:
            for catalog, namespace in (('pg_class','relnamespace'), ('pg_type','typnamespace'), ('pg_constraint','connamespace')):
                cursor.execute(sql.SQL('SELECT oid FROM pg_catalog.{} WHERE {}=pg_catalog.pg_my_temp_schema()').format(
                    sql.Identifier(catalog), sql.Identifier(namespace)))
                expected = Counter(row[0] for row in cursor)
                actual = Counter(item['native']['oid'] for item in pending['resources']
                    if item['native'].get('catalog') == catalog and item['native'].get('session_local'))
                assert actual == expected, (catalog, expected-actual, actual-expected)
                reconciled.append({'catalog':catalog,'native_count':sum(expected.values()),'provider_count':sum(actual.values())})
        checks.append('independent-native-own-temporary-relation-type-and-constraint-inventory-reconciled')
        assert other.execute('SELECT to_regclass(%s)', ('public.' + names[1],)).fetchone()[0] is None
        with Cursor(connection, row_factory=tuple_row) as cursor:
            cursor.execute(sql.SQL('SELECT id FROM public.{}').format(sql.Identifier(names[1])))
            assert cursor.fetchone()[0] == 42
        checks.append('pending-catalog-child-facts-native-parent-paths-and-data-preserved-with-original-local-settings')
        document = build_export(pending['resources'], endpoint_id=provider.context.endpoint_id,
            target_id='postgresql-database:' + str(pending['database_oid']), generation=pending['generation'],
            refreshed=True, engine='postgresql')
        model = read_catalog(json.dumps(document['snapshot']), engine='postgresql')
        assert model['provenance']['observation_scope'] == 'retained-session'
        assert model['rows'][observed[names[0]]['resource_id']]['system'] == 'false'
        try:
            build_plan(model, model, model)
        except ValueError as error:
            assert 'Retained-session' in str(error)
        else:
            raise AssertionError('Session catalog was admitted as an independent migration')
        checks.append('session-ddn-roundtrip-preserves-scope-and-refuses-independent-migration')
        def refused(native, *_args, **_kwargs):
            native.execute('SELECT 1/0')
        session_catalog.capture = refused
        try:
            observe()
        except PostgreSQLProviderError:
            assert not state.uncertain and connection.info.transaction_status == TransactionStatus.INTRANS and context() == before
        else:
            raise AssertionError('Native failure was hidden')
        finally:
            session_catalog.capture = original_capture
        checks.append('native-capture-failure-rolls-back-only-observation-savepoint')
        connection.rollback()
        fresh = observe()
        assert names[0] in relations(fresh) and names[1] not in relations(fresh) and names[2] not in relations(fresh)
        checks.append('fresh-capture-removes-rolled-back-temporary-and-permanent-catalog-changes')
        connection.execute('BEGIN')
        try:
            connection.execute('SELECT 1/0')
        except psycopg.errors.DivisionByZero:
            pass
        try:
            observe()
        except PostgreSQLProviderError:
            assert connection.info.transaction_status == TransactionStatus.INERROR and not state.uncertain
        else:
            raise AssertionError('An aborted user transaction was implicitly repaired')
        checks.append('aborted-user-transaction-refused-without-implicit-rollback')
        connection.rollback()
        (evidence / 'session-catalog.json').write_text(json.dumps({'complete':True, 'checks':checks,
            'independent_reconciliation':reconciled,
            'resource_count':len(pending['resources']), 'native_version':connection.info.server_version,
            'scope':'retained PostgreSQL session; history excluded'}, indent=2)+'\n')
        receipt['checks'].extend('native-session-catalog-' + item for item in checks)
    finally:
        session_catalog.capture = original_capture
        try:
            if not connection.closed:connection.rollback()
        finally:
            provider.close_session(opened)
            other.close()
