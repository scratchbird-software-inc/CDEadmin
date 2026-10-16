"""Native PostgreSQL mode/body/completion and typed DDN import qualification."""
import json
import uuid


def qualify(provider, session, raw, route, password, receipt, evidence, *, owner_id):
    import psycopg
    from psycopg import sql
    from pglast import parser
    from pgadmin.cdeadmin.providers.postgresql.data_capture import capture
    from pgadmin.cdeadmin.workspace.native_data_import import preview, apply, NativeDataApplications
    from pgadmin.cdeadmin.workspace.mysql_data_import import read
    assert parser.CDEADMIN_PARSE_OPTIONS_REVISION == 2
    name = 'scratchrobin_editor_' + uuid.uuid4().hex
    database_oid = raw.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()').fetchone()[0]
    state = provider._sessions[session['session_id']]
    native_route = {'server_id': state.server_id, 'database_id': database_oid,
        'owner_id': owner_id, 'principal_reference': 'worker:proof', 'credential_reference_id': 'proof-password'}
    observer = psycopg.connect(host=route['host'], port=route['port'], user=route['user'], password=password,
        dbname=route['database'], autocommit=True, **route.get('connection_params', {}))
    created = False
    original_quote = raw.execute("SELECT current_setting('backslash_quote')").fetchone()[0]
    def check(source, **options):
        return provider.validate_source_without_execution({**session, 'language_profile': 'postgresql-sql', 'source': source, **options})
    try:
        raw.execute('SET standard_conforming_strings=off')
        assert check(r"SELECT 'it\'s'; SELECT 'é'", script=True)['script_ready']
        raw.execute('SET backslash_quote=off')
        assert check(r"SELECT 'it\'s'")['grammar_valid'] is False
        raw.execute('SET backslash_quote=safe_encoding')
        raw.execute('SET standard_conforming_strings=on')
        assert check(r"SELECT 'it\'s'")['grammar_valid'] is False
        for language, body in [('sql', r"SELECT 'it\'s'"), ('plpgsql', r"BEGIN RETURN 'it\'s'; END")]:
            source = f'CREATE FUNCTION never_executed() RETURNS text LANGUAGE {language} SET standard_conforming_strings TO off AS $b${body}$b$'
            assert check(source)['grammar_valid'] is True
            assert check(source.replace('TO off', 'TO on'))['grammar_valid'] is False
        assert check('DO $$not valid plpgsql$$')['grammar_valid'] is False
        assert raw.info.transaction_status == 0
        receipt['checks'].append('native-session-string-settings-and-offline-sql-plpgsql-body-grammar-no-execution')
        raw.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name))); created = True
        raw.execute(sql.SQL("CREATE TYPE {}.mood AS ENUM ('a','Quoted ü')").format(sql.Identifier(name)))
        definition = '(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, amount numeric(38,10), state ' + sql.Identifier(name, 'mood').as_string(raw) + ', "values" int[], payload bytea, document jsonb, moment timestamptz, duration interval, calculated bigint GENERATED ALWAYS AS(id*2) STORED)'
        for table in ('source', 'destination'):
            raw.execute(sql.SQL('CREATE TABLE {} ').format(sql.Identifier(name, table)) + sql.SQL(definition))
        raw.execute(sql.SQL('INSERT INTO {}(amount,state,"values",payload,document,moment,duration) VALUES(12345678901234567890.1234567890,\'Quoted ü\',ARRAY[1,NULL,3],decode(\'0080ff\',\'hex\'),%s::jsonb,TIMESTAMPTZ \'2026-10-16 12:13:14.123456+03\',INTERVAL \'2 months 3 days 1 microsecond\')').format(sql.Identifier(name, 'source')), ('{"exact":12345678901234567890}',))
        source_oid, target_oid = [raw.execute('SELECT %s::regclass::oid', (sql.Identifier(name, table).as_string(raw),)).fetchone()[0] for table in ('source', 'destination')]
        before = set(provider._sessions)
        data = capture(provider, native_route, 'owned-source', 'postgresql:pg_class:' + str(source_oid), mode='full')
        source = json.dumps(data['snapshot'])
        from pgadmin.cdeadmin.workspace.native_data_import import connection
        from pgadmin.cdeadmin.providers.native_data_layout import inspect_relation
        with connection(provider, native_route, 'postgresql') as inspector:
            destination_layout = inspect_relation(inspector, 'postgresql', 'postgresql:pg_class:' + str(target_oid), native_route)
            inspector.execute('ROLLBACK')
        source_metadata, _ = read(source, engine='postgresql')
        (evidence / 'typed-data-layouts.json').write_text(json.dumps({'source_columns': source_metadata['acquisition']['native_columns'],
            'display_columns': source_metadata['schema']['columns'], 'destination_columns': destination_layout['native_columns']}, indent=2) + '\n')
        plan = preview(provider, native_route, 'postgresql', source, 'postgresql:pg_class:' + str(target_oid), endpoint_id='owned-target', target_id='postgresql-database:' + str(database_oid))
        store = NativeDataApplications(evidence / 'postgresql-data-imports.json', 'postgresql')
        reviewed = store.review(plan, 1, 'owned-import')
        request = {'review_id': reviewed['review_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True}
        outcome = store.apply(request, 1, 'owned-import', lambda record: apply(provider, native_route, 'postgresql', record))
        assert outcome['state'] == 'native_commit_returned', outcome
        restored = capture(provider, native_route, 'owned-target', 'postgresql:pg_class:' + str(target_oid), mode='full')
        assert read(source, engine='postgresql')[1] == read(json.dumps(restored['snapshot']), engine='postgresql')[1]
        assert set(provider._sessions) == before
        assert int(observer.execute(sql.SQL('SELECT calculated FROM {}').format(sql.Identifier(name, 'destination'))).fetchone()[0]) == 2
        assert store.apply(request, 1, 'owned-import', lambda _: (_ for _ in ()).throw(AssertionError('No replay')))['state'] == 'native_commit_returned'
        receipt['checks'].append('native-typed-ddn-import-enum-numeric-array-bytea-jsonb-timezone-interval-identity-generated-values-independent-observation-and-no-replay')
        prefix = 'SELECT * FROM ' + sql.Identifier(name).as_string(raw) + '.'
        complete = lambda: provider.complete({**session, 'full_source': prefix, 'source_before_cursor': prefix})
        assert 'destination' in str(complete())
        raw.execute(sql.SQL('DROP TABLE {}').format(sql.Identifier(name, 'destination')))
        assert 'destination' not in str(complete())
        receipt['checks'].append('native-completion-refresh-discards-dropped-relation-metadata')
        provider.control_transaction({**session, 'action': 'autocommit_off'})
        raw.execute(sql.SQL('INSERT INTO {}(amount) VALUES(42)').format(sql.Identifier(name, 'source')))
        assert check(r"SELECT E'it\'s'")['grammar_valid'] is True
        assert 'source' in str(complete())
        assert raw.info.transaction_status == 2
        assert int(observer.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name, 'source'))).fetchone()[0]) == 1
        assert int(raw.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name, 'source'))).fetchone()[0]) == 2
        provider.control_transaction({**session, 'action': 'rollback'})
        provider.control_transaction({**session, 'action': 'autocommit_on'})
        receipt['checks'].append('native-editor-setting-observation-preserves-pending-interactive-work')
    finally:
        if not raw.closed:
            if raw.info.transaction_status: raw.rollback()
            if not raw.autocommit: raw.autocommit = True
            raw.execute('SET standard_conforming_strings=on')
            raw.execute(sql.SQL('SET backslash_quote={}').format(sql.Literal(original_quote)))
            if created: raw.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
        observer.close()
