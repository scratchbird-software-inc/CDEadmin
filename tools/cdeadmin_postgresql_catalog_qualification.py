"""Real native DDN capture qualification called by the PostgreSQL driver gate."""
import json
import uuid


def qualify(provider, route, password, server, user, receipt, evidence):
    import psycopg
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog, compare_catalogs
    name = 'scratchrobin_catalog_' + uuid.uuid4().hex
    admin = psycopg.connect(host=route['host'], port=route['port'], user=route['user'], password=password,
        dbname=route['database'], autocommit=True, **route.get('connection_params', {}))
    created = False
    extra_cleanup = []
    try:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
        created = True
        admin.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(sql.Identifier(name)))
        for statement in (
            "CREATE TYPE mood AS ENUM ('a', 'Quoted ü')",
            'CREATE DOMAIN positive AS numeric(30,4) CHECK (VALUE > 0)',
            'CREATE TABLE parent (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, amount positive, state mood, "values" integer[], doubled numeric GENERATED ALWAYS AS (amount * 2) STORED)',
            'CREATE TABLE child (id integer, parent_id bigint REFERENCES parent(id))',
            "COMMENT ON TABLE parent IS 'Native table comment'",
            "COMMENT ON COLUMN parent.amount IS 'Native column comment'",
            'CREATE VIEW visible AS SELECT id, amount FROM parent',
            'CREATE MATERIALIZED VIEW cached AS SELECT id FROM parent',
            'CREATE TABLE events (id integer) PARTITION BY RANGE (id)',
            'CREATE TABLE events_first PARTITION OF events FOR VALUES FROM (0) TO (100)',
            'ALTER TABLE parent ENABLE ROW LEVEL SECURITY',
            'CREATE POLICY positive_only ON parent USING (amount > 0)',
            "CREATE FUNCTION echo_value(value integer) RETURNS integer LANGUAGE SQL IMMUTABLE AS 'SELECT value'",
            "CREATE PROCEDURE no_op() LANGUAGE SQL AS 'SELECT 1'",
            "CREATE FUNCTION mood_number(mood) RETURNS integer LANGUAGE SQL IMMUTABLE AS 'SELECT 1'",
            'CREATE CAST (mood AS integer) WITH FUNCTION mood_number(mood)',
        ):
            admin.execute(statement)
        admin.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO PUBLIC').format(sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE FOREIGN DATA WRAPPER {}').format(sql.Identifier(name)))
        extra_cleanup.append(sql.SQL('DROP FOREIGN DATA WRAPPER {} CASCADE').format(sql.Identifier(name)))
        admin.execute(sql.SQL("CREATE SERVER {} FOREIGN DATA WRAPPER {} OPTIONS (secret 'catalog-option-canary')").format(sql.Identifier(name), sql.Identifier(name)))
        admin.execute(sql.SQL("CREATE USER MAPPING FOR CURRENT_USER SERVER {} OPTIONS (password 'catalog-option-canary')").format(sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE PUBLICATION {} FOR TABLE parent WHERE (id > 0)').format(sql.Identifier(name)))
        extra_cleanup.append(sql.SQL('DROP PUBLICATION {}').format(sql.Identifier(name)))
        # No external connection, slot or worker is created by this fixture.
        admin.execute(sql.SQL("CREATE SUBSCRIPTION {} CONNECTION 'host=127.0.0.1 port=1 dbname=absent password=catalog-subscription-canary' PUBLICATION {} WITH (connect=false, enabled=false, create_slot=false, copy_data=false, slot_name=NONE)").format(sql.Identifier(name), sql.Identifier(name)))
        extra_cleanup.append(sql.SQL('DROP SUBSCRIPTION {}').format(sql.Identifier(name)))
        oid = admin.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()').fetchone()[0]
        selected = {'server_id': server.id, 'database_id': oid, 'owner_id': user.id,
                    'principal_reference': 'worker:proof', 'credential_reference_id': 'proof-password'}
        before_sessions = set(provider._sessions)
        native = provider.capture_catalog(selected)
        assert set(provider._sessions) == before_sessions
        resources = native['resources']
        subscription = next(row for row in resources if row['resource_kind'] == 'subscription' and row['display_name'] == name)
        assert subscription['native']['catalog_row']['connection_redacted'] is True
        assert 'subconninfo' not in subscription['native']['catalog_row']
        assert 'catalog-subscription-canary' not in json.dumps(native)
        assert 'catalog-option-canary' not in json.dumps(native)
        mapping = next(row for row in resources if row['resource_kind'] == 'user-mapping' and row['display_name'].endswith(' / ' + name))
        assert mapping['native']['catalog_row']['options_redacted'] is True
        assert any(row['resource_kind'] == 'cast' and row['display_name'].startswith(name + '.mood AS ') for row in resources)
        assert any(row['resource_kind'] == 'default-privileges' and name in row['display_name'] for row in resources)
        publication = next(row for row in resources if row['resource_kind'] == 'publication' and row['display_name'] == name)
        assert publication['native']['children']['pg_publication_rel'][0]['row_filter_sql'] == '(id > 0)'
        assert next(row for row in native['resources'] if row['resource_kind'] == 'database')['native']['catalog_observations']
        receipt['checks'].append('native-ddn-casts-default-privileges-publication-filters-and-credential-free-subscription-mapping-identities')
        reader, reader_password = name + '_reader', uuid.uuid4().hex
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(reader), sql.Literal(reader_password)))
        extra_cleanup.append(sql.SQL('DROP ROLE {}').format(sql.Identifier(reader)))
        from pgadmin.cdeadmin.providers.postgresql.catalog_capture import capture
        with psycopg.connect(host=route['host'], port=route['port'], user=reader,
                password=reader_password, dbname=route['database'], autocommit=True,
                **route.get('connection_params', {})) as limited:
            restricted = capture(limited, oid)
        restricted_subscription = next(row for row in restricted['resources']
            if row['resource_kind'] == 'subscription' and row['display_name'] == name)
        assert restricted_subscription['native']['catalog_row']['connection_redacted'] is True
        assert 'catalog-subscription-canary' not in json.dumps(restricted)
        assert 'catalog-option-canary' not in json.dumps(restricted)
        receipt['checks'].append('native-ddn-nonsuperuser-subscription-column-privileges-without-secret-selection')
        from pgadmin.cdeadmin.providers.postgresql import catalog_capture
        original_limit = catalog_capture.MAX_BYTES
        try:
            catalog_capture.MAX_BYTES = 1
            try:
                provider.capture_catalog(selected)
            except ValueError as error:
                assert 'capture limit' in str(error)
            else:
                raise AssertionError('Root catalog metadata bypassed the capture budget')
            assert set(provider._sessions) == before_sessions
        finally:
            catalog_capture.MAX_BYTES = original_limit
        receipt['checks'].append('native-ddn-root-capture-budget-failure-releases-owned-session')
        scoped = {(row['native']['catalog'], row['display_name']): row for row in resources if row['native'].get('schema') == name}
        table = scoped[('pg_class', 'parent')]
        assert table['resource_kind'] == 'table'
        assert table['native']['comment'] == 'Native table comment'
        columns = {x['attname']: x for x in table['native']['children']['pg_attribute']}
        assert columns['id']['attidentity'] == 'a'
        assert columns['amount']['comment'] == 'Native column comment'
        assert columns['values']['formatted_type'] == 'integer[]'
        assert columns['doubled']['attgenerated'] == 's'
        assert 'expression_sql' in table['native']['children']['pg_attrdef'][0]
        assert scoped[('pg_type', 'positive')]['resource_kind'] == 'domain'
        assert scoped[('pg_class', 'events')]['resource_kind'] == 'partitioned-table'
        assert scoped[('pg_class', 'events')]['native']['catalog_row']['partition_key_sql'] == 'RANGE (id)'
        assert 'FROM (0) TO (100)' in scoped[('pg_class', 'events_first')]['native']['catalog_row']['partition_bound_sql']
        assert scoped[('pg_class', 'visible')]['resource_kind'] == 'view'
        assert scoped[('pg_class', 'cached')]['resource_kind'] == 'materialized-view'
        assert scoped[('pg_proc', 'no_op')]['resource_kind'] == 'procedure'
        assert scoped[('pg_proc', 'echo_value')]['resource_kind'] == 'function'
        assert scoped[('pg_policy', 'positive_only')]['native']['catalog_row']['using_sql']
        from pgadmin.utils.driver import get_driver
        from pgadmin.utils.crypto import encrypt
        from pgadmin.utils.master_password import get_crypt_key, set_crypt_key
        present, key = get_crypt_key()
        if not present:
            import secrets
            set_crypt_key(secrets.token_urlsafe(32))
            present, key = get_crypt_key()
        assert present
        explorer_manager = get_driver('psycopg3').connection_manager(server.id)
        status, _ = explorer_manager.connection().connect(password=encrypt(password, key))
        assert status
        try:
            workspace_resources = provider.list_resources({
                'resource_kind': 'server', 'resource_id': 'qualification-root',
                'route': selected, 'authority_path': [],
            })
            inspector = provider.resource_contributions()['inspectors'][0]
            assert all(row['resource_kind'] in inspector.resource_kinds for row in workspace_resources)
            workspace_policy = next(row for row in workspace_resources
                if row['resource_id'] == scoped[('pg_policy', 'positive_only')]['resource_id'])
            assert workspace_policy['resource_kind'] == 'row-policy'
            assert provider.inspect_resource(workspace_policy)['extensions']['postgresql']['catalog_kind'] == 'policy'
        finally:
            explorer_manager.release()
        receipt['checks'].append('native-captured-catalog-inspector-coverage-and-policy-form-identity')
        assert scoped[('pg_type', 'mood')]['native']['children']['pg_enum'][1]['enumlabel'] == 'Quoted ü'
        assert scoped[('pg_class', 'child')]['native']['dependencies']
        document = build_export(resources, endpoint_id='qualification', target_id=f'postgresql-database:{oid}',
            generation=native['generation'], engine='postgresql')
        diagram = document['diagram']
        assert diagram['foreign_keys'] >= 1 and not diagram.get('unavailable')
        source = diagram['snapshot']['files']['relations.ddn']
        assert name + '.parent [table]' in source
        assert name + '.events [partitioned-table]' in source
        assert 'integer[]' in source and 'Native column comment' in source
        import subprocess
        from pathlib import Path
        runtime = (Path(__file__).resolve().parents[1] / 'web/pgadmin/static/vendor/ddn/current/ddn.mjs').as_uri()
        script = 'import runtime from ' + json.dumps(runtime) + ";let input='';for await(const part of process.stdin)input+=part;const diagram=JSON.parse(input),w=runtime.createWorkspace(diagram.snapshot.files);try{for(const view of diagram.views){const r=w.renderSync({entry:view.entry,view:view.id});if(r.diagnostics.some(x=>x.severity==='error'))throw Error('Invalid native graph');}}finally{w.destroy();}"
        subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(diagram),
                       text=True, capture_output=True, timeout=30, check=True)
        receipt['checks'].append('native-postgresql-relational-ddn-public-renderer')
        baseline = read_catalog(json.dumps(document['snapshot']), engine='postgresql')
        assert baseline['rows'][table['resource_id']]['native']['children'] == table['native']['children']
        admin.execute("COMMENT ON TABLE parent IS 'Changed native comment'")
        current = provider.capture_catalog(selected)
        model = build_export(current['resources'], endpoint_id='qualification', target_id=f'postgresql-database:{oid}',
            generation=current['generation'], engine='postgresql', native_model=True)
        diff = compare_catalogs(baseline, model)
        assert any(item['resource_id'] == table['resource_id'] and 'native.comment' in item['fields'] for item in diff['changes'])
        receipt['checks'].append('native-ddn-types-partitions-constraints-comments-dependencies-and-live-diff')
        from copy import deepcopy
        from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan, COMMENT_TYPES
        desired = deepcopy(model)
        for identity, row in desired['rows'].items():
            if row['native'].get('schema') == name and row['kind'] in COMMENT_TYPES and row['system'] == 'false':
                row['native']['comment'] = 'Qualified DDN comment: é \\ quote \' ; SELECT 1;'
        attributes = desired['rows'][table['resource_id']]['native']['children']['pg_attribute']
        for attribute in attributes:
            if attribute['attname'] in {'id', 'amount'}:
                attribute['comment'] = 'Native DDN column comment: quoted ü'
        plan = build_plan(model, desired, model)
        if not plan['ready_for_review']:
            receipt['failures'].append({'owned_fixture_plan_blockers': plan['blockers']})
        assert plan['ready_for_review'] and not plan['application_supported'] and plan['operations']
        admin.execute('BEGIN')
        try:
            for operation in plan['operations']:
                try:
                    admin.execute(operation['statement'])
                except Exception as error:
                    receipt['failures'].append({'owned_fixture_statement': operation['statement'],
                        'native_kind': operation['kind'], 'sqlstate': getattr(error, 'sqlstate', None)})
                    raise
            admin.execute('COMMIT')
        except Exception:
            admin.execute('ROLLBACK')
            raise
        observed = provider.capture_catalog(selected)
        observed_model = build_export(observed['resources'], endpoint_id='qualification',
            target_id=f'postgresql-database:{oid}', generation=observed['generation'], engine='postgresql', native_model=True)
        converged = build_plan(model, desired, observed_model)
        assert converged['ready_for_review'] and not converged['operations']
        assert converged['counts']['converged'] == len(plan['operations'])
        receipt['checks'].append('native-ddn-comment-generation-signatures-quoted-text-and-rediscovery')
        branch = build_export(resources, endpoint_id='qualification', target_id=f'postgresql-database:{oid}',
            generation=native['generation'], engine='postgresql', resource_id=table['resource_id'])
        branch_model = read_catalog(json.dumps(branch['snapshot']), engine='postgresql')
        assert table['resource_id'] in branch_model['rows']
        assert scoped[('pg_policy', 'positive_only')]['resource_id'] in branch_model['rows']
        assert scoped[('pg_class', 'child')]['resource_id'] not in branch_model['rows']
        receipt['checks'].append('native-ddn-branch-ownership-and-independent-attachment-release')
        qualify_server(provider, selected, admin, route, password, receipt)
        qualify_creation(provider, selected, admin, receipt, evidence)
        qualify_existing_creation(provider, selected, admin, receipt, evidence)
        qualify_existing_partition(provider, selected, admin, receipt, evidence)
        qualify_table_owned(provider, selected, admin, receipt, evidence)
        qualify_row_security(provider, selected, admin, receipt, evidence)
        qualify_data_capture(provider, selected, admin, receipt)
        qualify_test_data(provider, selected, admin, receipt, name)
        qualify_application(provider, selected, admin, receipt, evidence, name)
        qualify_column_removal(provider, selected, admin, receipt, evidence, name)
        qualify_column_addition(provider, selected, admin, receipt, evidence, name)
    finally:
        try:
            cleanup_errors = []
            for statement in reversed(extra_cleanup):
                try:
                    admin.execute(statement)
                except Exception as error:
                    cleanup_errors.append(type(error).__name__)
            if created:
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
            if cleanup_errors:
                raise RuntimeError('Owned catalog fixture cleanup failed: ' + ', '.join(cleanup_errors))
        finally:
            admin.close()


def qualify_creation(provider, route, admin, receipt, evidence):
    """Execute generated fixture SQL only; product review/apply is separate."""
    from copy import deepcopy
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    name = 'srb_creation_' + uuid.uuid4().hex
    def model():
        native = provider.capture_catalog(route)
        return build_export(native['resources'], endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}', generation=native['generation'],
            engine='postgresql', native_model=True)
    baseline = model()
    desired = deepcopy(baseline)
    def add(kind, **draft):
        identity = 'postgresql:new:' + str(uuid.uuid4())
        desired['rows'][identity] = {'resource_id': identity, 'kind': kind, 'name': draft['name'],
            'path': [name, draft['name']], 'system': 'false',
            'native': {'system_object': False, 'create': draft}}
        return identity
    add('schema', name=name)
    enum = add('type', schema=name, name='Mood', labels=['', ' spaced ', "a'b"])
    composite = add('type', schema=name, name='Pair', type_kind='COMPOSITE', attributes=[
        {'name': 'label', 'data_type': 'text', 'collation': {'schema': 'pg_catalog', 'name': 'C'}},
        {'name': 'amount', 'data_type': 'numeric(12,2)'}])
    interval = add('type', schema=name, name='Span', type_kind='RANGE', subtype='float8',
        subtype_diff={'schema': 'pg_catalog', 'name': 'float8mi'})
    domain = add('domain', schema=name, name='positive', data_type='numeric(12,2)', default='1', nullable=False,
        checks=[{'name': 'positive', 'expression': 'VALUE > 0'}])
    parent = add('table', schema=name, name='Mixed table', depends_on=[enum, domain, composite, interval], columns=[
        {'name': 'id', 'data_type': 'bigint', 'identity': 'ALWAYS'},
        {'name': 'pair', 'data_type': '"' + name + '"."Pair"'},
        {'name': 'span', 'data_type': '"' + name + '"."Span"'},
        {'name': 'positive', 'data_type': '"' + name + '".positive'},
        {'name': 'state', 'data_type': '"' + name + '"."Mood"'},
        {'name': 'amount', 'data_type': 'double precision', 'default': '2 + 3'},
        {'name': 'doubled', 'data_type': 'double precision', 'generated': {'expression': 'amount * 2', 'storage': 'STORED'}}],
        keys=[{'kind': 'PRIMARY KEY', 'name': 'Mixed key', 'columns': ['id']}])
    add('table', schema=name, name='child', depends_on=[parent], columns=[
        {'name': 'parent_id', 'data_type': 'bigint'}], keys=[
        {'kind': 'CHECK', 'name': 'positive', 'expression': 'parent_id > 0'},
        {'kind': 'FOREIGN KEY', 'name': 'parent_fk', 'columns': ['parent_id'],
         'references': {'schema': name, 'table': 'Mixed table', 'columns': ['id']},
         'deferrable': True, 'initially_deferred': True, 'on_delete': 'CASCADE'}])
    add('view', schema=name, name='visible', depends_on=[parent],
        query='SELECT id, amount FROM "' + name + '"."Mixed table" WHERE amount > 0',
        security_barrier=True, security_invoker=True, check_option='LOCAL')
    add('materialized-view', schema=name, name='cached', depends_on=[parent],
        query='SELECT id, doubled FROM "' + name + '"."Mixed table"', with_data=False)
    add('sequence', schema=name, name='Exact sequence', start='9223372036854775799')
    add('index', schema=name, name='Partial expression index', table='Mixed table', depends_on=[parent],
        unique=True, keys=[{'expression': 'amount + 1', 'order': 'DESC', 'nulls': 'LAST'}],
        include=['id'], nulls_distinct=False, predicate='amount > 0',
        storage_parameters={'fillfactor': 75})
    add('index', schema=name, name='BRIN configured index', table='Mixed table', depends_on=[parent],
        method='brin', keys=[{'column': 'id',
            'opclass': {'schema': 'pg_catalog', 'name': 'int8_minmax_multi_ops'},
            'opclass_parameters': {'values_per_range': 32}}],
        storage_parameters={'pages_per_range': 16, 'autosummarize': True})
    for data_type, body in [('integer', 'SELECT value + 1'), ('text', 'SELECT value')]:
        add('function', schema=name, name=' Echo ü ', definition=sql.SQL(
            'CREATE FUNCTION {}.{}(value ' + data_type + ') RETURNS ' + data_type +
            ' LANGUAGE SQL IMMUTABLE STRICT AS $$ ' + body + ' $$').format(
                sql.Identifier(name), sql.Identifier(' Echo ü ')).as_string(admin))
    add('procedure', schema=name, name='bump', definition=sql.SQL(
        'CREATE PROCEDURE {}.bump(INOUT value integer) LANGUAGE plpgsql AS $$ BEGIN value := value + 1; END $$'
        ).format(sql.Identifier(name)).as_string(admin))
    add('window-function', schema=name, name='row_number', definition=sql.SQL(
        "CREATE FUNCTION {}.row_number() RETURNS bigint LANGUAGE internal WINDOW AS 'window_row_number'"
        ).format(sql.Identifier(name)).as_string(admin))
    add('aggregate', schema=name, name='total', definition=sql.SQL(
        'CREATE AGGREGATE {}.total(integer) (SFUNC=pg_catalog.int4pl, STYPE=integer, INITCOND=0)'
        ).format(sql.Identifier(name)).as_string(admin))
    template=add('text-search-template',schema=name,name='native_template',definition=sql.SQL(
        'CREATE TEXT SEARCH TEMPLATE {}.native_template (INIT=pg_catalog.dsimple_init, LEXIZE=pg_catalog.dsimple_lexize)').format(sql.Identifier(name)).as_string(admin))
    add('text-search-dictionary',schema=name,name='native_dictionary',depends_on=[template],definition=sql.SQL(
        'CREATE TEXT SEARCH DICTIONARY {}.native_dictionary (TEMPLATE={}.native_template)').format(sql.Identifier(name),sql.Identifier(name)).as_string(admin))
    add('text-search-parser',schema=name,name='native_parser',definition=sql.SQL(
        'CREATE TEXT SEARCH PARSER {}.native_parser (START=pg_catalog.prsd_start, GETTOKEN=pg_catalog.prsd_nexttoken, END=pg_catalog.prsd_end, LEXTYPES=pg_catalog.prsd_lextype, HEADLINE=pg_catalog.prsd_headline)').format(sql.Identifier(name)).as_string(admin))
    add('text-search-configuration',schema=name,name='native_configuration',definition=sql.SQL(
        'CREATE TEXT SEARCH CONFIGURATION {}.native_configuration (COPY=pg_catalog.simple)').format(sql.Identifier(name)).as_string(admin))
    add('collation',schema=name,name='native_collation',definition=sql.SQL(
        'CREATE COLLATION {}.native_collation FROM pg_catalog."C"').format(sql.Identifier(name)).as_string(admin))
    add('conversion',schema=name,name='native_conversion',definition=sql.SQL(
        "CREATE CONVERSION {}.native_conversion FOR 'UTF8' TO 'LATIN1' FROM pg_catalog.utf8_to_iso8859_1").format(sql.Identifier(name)).as_string(admin))
    def partition(kind,table,definition,depends_on=None):
        return add(kind,schema=name,name=table,depends_on=depends_on or [],definition=definition.format(scope=sql.Identifier(name).as_string(admin)))
    range_parent=partition('partitioned-table','range_parent','CREATE TABLE {scope}.range_parent(value integer) PARTITION BY RANGE(value)')
    partition('table','range_first','CREATE TABLE {scope}.range_first PARTITION OF {scope}.range_parent FOR VALUES FROM (0) TO (10)',[range_parent])
    subparent=partition('partitioned-table','range_sub','CREATE TABLE {scope}.range_sub PARTITION OF {scope}.range_parent FOR VALUES FROM (10) TO (20) PARTITION BY HASH(value)',[range_parent])
    partition('table','sub_leaf','CREATE TABLE {scope}.sub_leaf PARTITION OF {scope}.range_sub FOR VALUES WITH (MODULUS 1, REMAINDER 0)',[subparent])
    partition('table','range_other','CREATE TABLE {scope}.range_other PARTITION OF {scope}.range_parent DEFAULT',[range_parent])
    list_parent=partition('partitioned-table','list_parent','CREATE TABLE {scope}.list_parent(value text) PARTITION BY LIST(value)')
    partition('table','list_leaf',"CREATE TABLE {scope}.list_leaf PARTITION OF {scope}.list_parent FOR VALUES IN ('red','blue')",[list_parent])
    hash_parent=partition('partitioned-table','hash_parent','CREATE TABLE {scope}.hash_parent(value integer) PARTITION BY HASH(value)')
    for remainder in (0,1):
        partition('table','hash_'+str(remainder),'CREATE TABLE {scope}.hash_'+str(remainder)+' PARTITION OF {scope}.hash_parent FOR VALUES WITH (MODULUS 2, REMAINDER '+str(remainder)+')',[hash_parent])
    plan = build_plan(baseline, desired, baseline)
    assert plan['ready_for_review'] and plan['application_supported'] and len(plan['operations']) == 33, plan['blockers']
    try:
        admin.execute('BEGIN')
        for operation in plan['operations']:
            admin.execute(operation['statement'])
        admin.execute('COMMIT')
        labels = admin.execute('SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=%s ORDER BY e.enumsortorder', (name,)).fetchall()
        assert [row[0] for row in labels] == ['', ' spaced ', "a'b"]
        value = admin.execute('SELECT nextval(%s::regclass)', ('"' + name + '"."Exact sequence"',)).fetchone()[0]
        assert str(value) == '9223372036854775799'
        inserted = admin.execute(sql.SQL('INSERT INTO {}.{} DEFAULT VALUES RETURNING id, amount, doubled').format(
            sql.Identifier(name), sql.Identifier('Mixed table'))).fetchone()
        from decimal import Decimal
        assert tuple(Decimal(str(value)) for value in inserted) == (1, 5, 10)
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.visible').format(sql.Identifier(name))).fetchone()[0]) == 1
        admin.execute(sql.SQL('REFRESH MATERIALIZED VIEW {}.cached').format(sql.Identifier(name)))
        assert int(admin.execute(sql.SQL('SELECT doubled FROM {}.cached').format(sql.Identifier(name))).fetchone()[0]) == 10
        index = admin.execute('SELECT i.indisvalid, i.indisunique, i.indnullsnotdistinct, i.indnkeyatts, i.indnatts FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s', (name, 'Partial expression index')).fetchone()
        assert tuple(index) == (True, True, True, 1, 2), index
        options = admin.execute('SELECT c.relname, c.reloptions, pg_get_indexdef(c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname IN (%s,%s)', (name, 'Partial expression index', 'BRIN configured index')).fetchall()
        options = {row[0]: row[1:] for row in options}
        assert 'fillfactor=75' in options['Partial expression index'][0]
        assert set(options['BRIN configured index'][0]) == {'pages_per_range=16', 'autosummarize=true'}
        assert 'values_per_range' in options['BRIN configured index'][1] and '32' in options['BRIN configured index'][1]
        receipt['checks'].append('native-ddn-index-storage-and-operator-class-parameters-rediscovery')
        try:
            admin.execute(sql.SQL('INSERT INTO {}.{} DEFAULT VALUES').format(sql.Identifier(name), sql.Identifier('Mixed table')))
            raise AssertionError('Generated unique expression index did not enforce uniqueness')
        except Exception as error:
            assert getattr(error, 'sqlstate', None) == '23505', type(error).__name__
        admin.execute(sql.SQL('UPDATE {}.{} SET pair=ROW(%s,%s), span=%s').format(sql.Identifier(name), sql.Identifier('Mixed table')), (' spaced ', '12.34', '[1.25,4.75)'))
        typed = admin.execute(sql.SQL('SELECT (pair).label, (pair).amount::text, lower(span), upper(span), span @> 2.0::float8 FROM {}.{}').format(sql.Identifier(name), sql.Identifier('Mixed table'))).fetchone()
        assert typed[0] == ' spaced ' and typed[1] == '12.34' and typed[4] is True, typed
        assert Decimal(str(typed[2])) == Decimal('1.25') and Decimal(str(typed[3])) == Decimal('4.75'), typed
        receipt['checks'].append('native-ddn-composite-range-types-table-values-and-range-operators')
        receipt['checks'].append('native-ddn-partial-expression-unique-covering-index-enforcement')
        receipt['checks'].append('native-ddn-domain-view-and-materialized-view-generation-use')
        admin.execute(sql.SQL('INSERT INTO {}.child VALUES (%s)').format(sql.Identifier(name)), (inserted[0],))
        admin.execute(sql.SQL('DELETE FROM {}.{} WHERE id=%s').format(sql.Identifier(name), sql.Identifier('Mixed table')), (inserted[0],))
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.child').format(sql.Identifier(name))).fetchone()[0]) == 0
        receipt['checks'].append('native-ddn-identity-default-generated-check-foreign-key-cascade')
        observed = model()
        assert any(row['name'] == 'Mixed table' and row['kind'] == 'table' for row in observed['rows'].values())
        repeated = build_plan(baseline, desired, observed)
        assert not repeated['ready_for_review'] and any('already occupies' in item['reason'] for item in repeated['blockers'])
        receipt['checks'].append('native-ddn-explicit-schema-enum-table-sequence-generation-order-and-rediscovery')
    finally:
        if admin.info.transaction_status != 0:
            admin.execute('ROLLBACK')
        admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(name)))

    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql.schema_application import apply_review
    applications = PostgreSQLSchemaApplications(evidence / 'creation-reviews.json')
    try:
        fresh = model()
        plan = build_plan(baseline, desired, fresh)
        review = applications.review(plan, baseline, desired, 7, 'creation-route', route['database_id'])
        request = {'review_id': review['review_id'], 'review_digest': review['review_digest'], 'confirmed': True}
        original_ensure = provider._ensure_native_connection
        def nonstandard_default(state):
            original_ensure(state)
            if int(state.connection.conn.info.transaction_status) == 0:
                state.connection.conn.execute('SET standard_conforming_strings=off')
        provider._ensure_native_connection = nonstandard_default
        from pgadmin.cdeadmin.providers.postgresql import schema_application as native_creation
        original_control = native_creation.control
        literal_policy_observations = []
        def check_literal_policy(connection, statement):
            before = connection.execute('SHOW standard_conforming_strings').fetchone()[0]
            answer = original_control(connection, statement)
            after = connection.execute('SHOW standard_conforming_strings').fetchone()[0]
            literal_policy_observations.append((before, after))
            return answer
        native_creation.control = check_literal_policy
        try:
            outcome = applications.apply(request, 7, 'creation-route', lambda record: apply_review(provider, route, record))
        finally:
            del provider._ensure_native_connection
            native_creation.control = original_control
        assert literal_policy_observations == [('on', 'off')], literal_policy_observations
        assert outcome['state'] == 'native_commit_returned', outcome
        assert outcome['outcome']['rediscovery']['matches_reviewed_properties'], outcome
        assert len(outcome['outcome']['created_objects']) == 33
        assert int(admin.execute(sql.SQL('SELECT {}.{}(4::integer)').format(sql.Identifier(name), sql.Identifier(' Echo ü '))).fetchone()[0]) == 5
        assert admin.execute(sql.SQL('SELECT {}.{}(%s::text)').format(sql.Identifier(name), sql.Identifier(' Echo ü ')), ('exact ü',)).fetchone()[0] == 'exact ü'
        assert int(admin.execute(sql.SQL('CALL {}.bump(2)').format(sql.Identifier(name))).fetchone()[0]) == 3
        assert int(admin.execute(sql.SQL('SELECT {}.total(v) FROM (VALUES (2),(3)) AS valueset(v)').format(sql.Identifier(name))).fetchone()[0]) == 5
        assert [int(row[0]) for row in admin.execute(sql.SQL('SELECT {}.row_number() OVER (ORDER BY v) FROM (VALUES (2),(3)) AS valueset(v)').format(sql.Identifier(name))).fetchall()] == [1, 2]
        assert 'hello' in admin.execute('SELECT ts_lexize(%s::regdictionary,%s)::text', (name+'.native_dictionary','HELLO')).fetchone()[0]
        assert 'hello' in admin.execute('SELECT to_tsvector(%s::regconfig,%s)::text',(name+'.native_configuration','HELLO')).fetchone()[0]
        assert admin.execute('SELECT token FROM ts_parse(%s,%s) WHERE token=%s',(name+'.native_parser','HELLO','HELLO')).fetchone()[0]=='HELLO'
        assert admin.execute(sql.SQL("SELECT 'a' COLLATE {}.native_collation < 'b' COLLATE {}.native_collation").format(sql.Identifier(name),sql.Identifier(name))).fetchone()[0] is True
        assert admin.execute("SELECT conproc='pg_catalog.utf8_to_iso8859_1'::regproc FROM pg_conversion c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname=%s AND conname=%s",(name,'native_conversion')).fetchone()[0] is True
        admin.execute(sql.SQL('INSERT INTO {}.range_parent VALUES (1),(12),(42)').format(sql.Identifier(name)))
        for table,value in [('range_first',1),('sub_leaf',12),('range_other',42)]:
            assert int(admin.execute(sql.SQL('SELECT value FROM {}.{}').format(sql.Identifier(name),sql.Identifier(table))).fetchone()[0])==value
        admin.execute(sql.SQL("INSERT INTO {}.list_parent VALUES ('red'),('blue')").format(sql.Identifier(name)))
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.list_leaf').format(sql.Identifier(name))).fetchone()[0])==2
        admin.execute(sql.SQL('INSERT INTO {}.hash_parent SELECT generate_series(1,100)').format(sql.Identifier(name)))
        assert int(admin.execute(sql.SQL('SELECT count(DISTINCT tableoid) FROM {}.hash_parent').format(sql.Identifier(name))).fetchone()[0])==2
        receipt['checks'].append('native-ddn-range-list-hash-default-and-subpartition-create-oid-rediscovery-and-routing')
        receipt['checks'].append('native-ddn-collation-conversion-text-search-create-rediscovery-and-native-use')
        receipt['checks'].append('native-ddn-aggregate-and-window-function-definition-rediscovery-and-execution')
        receipt['checks'].append('native-ddn-routine-overloads-procedure-create-oid-rediscovery-and-authorized-invocation')
        receipt['checks'].append('native-ddn-reviewed-new-schema-batch-commit-and-exact-oid-rediscovery')
        receipt['checks'].append('native-ddn-owned-literal-policy-with-nonstandard-connection-default')
    finally:
        admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(name)))
    invalid = deepcopy(desired)
    invalid['rows'][parent]['native']['create']['columns'][0]['data_type'] = 'srb_missing_' + uuid.uuid4().hex
    fresh = model()
    plan = build_plan(baseline, invalid, fresh)
    review = applications.review(plan, baseline, invalid, 7, 'creation-route', route['database_id'])
    request = {'review_id': review['review_id'], 'review_digest': review['review_digest'], 'confirmed': True}
    try:
        outcome = applications.apply(request, 7, 'creation-route', lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'native_rollback_returned', outcome
        assert outcome['outcome']['statements_completed'] >= 1
        assert admin.execute('SELECT oid FROM pg_namespace WHERE nspname=%s', (name,)).fetchone() is None
        receipt['checks'].append('native-ddn-failed-new-schema-batch-rolls-back-all-created-objects')
    finally:
        admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(name)))


def qualify_application(provider, route, admin, receipt, evidence, schema):
    """Real durable review, locked native mutation, conflict and lost-commit proof."""
    from copy import deepcopy
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql import schema_application as native
    from psycopg import sql
    store = PostgreSQLSchemaApplications(evidence / 'schema-reviews.json')
    def model():
        captured = provider.capture_catalog(route)
        return build_export(captured['resources'], endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}', generation=captured['generation'],
            engine='postgresql', native_model=True)
    def reviewed(value, names=('parent',)):
        baseline = model(); desired = deepcopy(baseline)
        identities = []
        for identity, row in desired['rows'].items():
            if row['native'].get('schema') == schema and row['name'] in names and row['kind'] in {'table', 'view', 'partitioned-table'}:
                row['native']['comment'] = value
                identities.append(identity)
                if row['name'] == 'parent':
                    row['native']['children']['pg_attribute'][0]['comment'] = value
        assert len(identities) == len(names)
        plan = build_plan(baseline, desired, baseline)
        assert plan['application_supported'], plan['blockers']
        return store.review(plan, baseline, desired, 7, 'qualification-route', route['database_id'])
    def request(record):
        return {'review_id': record['review_id'], 'review_digest': record['review_digest'], 'confirmed': True}
    sessions = set(provider._sessions)
    prepared = reviewed('Reviewed native comments', ('parent', 'visible', 'events'))
    result = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
    assert result['state'] == 'native_commit_returned', result
    assert result['outcome']['rediscovery']['matches_reviewed_properties'], result
    assert result['outcome']['attachment_released'] and set(provider._sessions) == sessions
    receipt['checks'].append('native-ddn-durable-review-table-view-partition-and-column-comments')

    admin.execute(sql.SQL('CREATE TABLE {}.type_probe(value integer)').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('INSERT INTO {}.type_probe VALUES(42000)').format(sql.Identifier(schema)))
    def type_review(target):
        baseline=model();desired=deepcopy(baseline)
        row=next(row for row in desired['rows'].values() if row['name']=='type_probe' and
            row['kind']=='table' and row['native'].get('schema')==schema)
        row['native']['children']['pg_attribute'][0]['formatted_type']=target
        plan=build_plan(baseline,desired,baseline)
        assert plan['application_supported'],plan['blockers']
        return store.review(plan,baseline,desired,7,'qualification-route',route['database_id'])
    result=store.apply(request(type_review('bigint')),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
    assert int(admin.execute(sql.SQL('SELECT value FROM {}.type_probe').format(sql.Identifier(schema))).fetchone()[0])==42000
    result=store.apply(request(type_review('smallint')),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert result['state']=='native_rollback_returned' and not result['outcome']['commit_requested'],result
    assert int(admin.execute(sql.SQL('SELECT value FROM {}.type_probe').format(sql.Identifier(schema))).fetchone()[0])==42000
    type_receipt=type_review('numeric(20,4)')
    admin.execute(sql.SQL('ALTER TABLE {}.type_probe ALTER COLUMN value TYPE double precision').format(sql.Identifier(schema)))
    result=store.apply(request(type_receipt),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert result['outcome']['statements_completed']==0 and not result['outcome']['commit_requested'],result
    receipt['checks'].append('native-ddn-column-type-widening-preserves-data-overflow-rolls-back-concurrent-type-refused')
    def mixed_review(table, nullable):
        baseline=model();desired=deepcopy(baseline)
        row=next(row for row in desired['rows'].values() if row['name']=='type_probe' and
            row['kind']=='table' and row['native'].get('schema')==schema)
        row['native']['comment']='mixed '+table
        row['native']['children']['pg_attribute'][0]['attnotnull']=not nullable
        identity='postgresql:new:'+str(uuid.uuid4())
        desired['rows'][identity]={'resource_id':identity,'name':table,'kind':'table','path':[schema,table],
            'system':'false','native':{'system_object':False,'create':{'name':table,'schema':schema,
            'columns':[{'name':'id','data_type':'integer'}]}}}
        plan=build_plan(baseline,desired,baseline)
        assert plan['application_supported'],plan['blockers']
        return store.review(plan,baseline,desired,7,'qualification-route',route['database_id'])
    result=store.apply(request(mixed_review('mixed_created',True)),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
    assert len(result['outcome']['created_objects'])==1
    admin.execute(sql.SQL('INSERT INTO {}.mixed_created VALUES(7)').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('INSERT INTO {}.type_probe VALUES(NULL)').format(sql.Identifier(schema)))
    result=store.apply(request(mixed_review('mixed_failed',False)),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert result['state']=='native_rollback_returned' and not result['outcome']['commit_requested'],result
    assert admin.execute('SELECT to_regclass(%s)',(schema+'.mixed_failed',)).fetchone()[0] is None
    assert admin.execute("SELECT obj_description(%s::regclass,'pg_class')",(schema+'.type_probe',)).fetchone()[0]=='mixed mixed_created'
    receipt['checks'].append('native-ddn-mixed-create-alter-atomic-commit-combined-rediscovery-and-failure-rollback')
    admin.execute(sql.SQL('CREATE TABLE {}.drop_probe(value integer)').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('INSERT INTO {}.drop_probe VALUES(77)').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('CREATE VIEW {}.drop_view AS SELECT * FROM {}.drop_probe').format(sql.Identifier(schema),sql.Identifier(schema)))
    def drop_review(name):
        baseline=model();desired=deepcopy(baseline)
        row=next(row for row in desired['rows'].values() if row['name']==name and row['kind'] in {'table','view'} and row['native'].get('schema')==schema)
        row['native']['drop']=True
        plan=build_plan(baseline,desired,baseline)
        assert plan['application_supported'],plan['blockers']
        return store.review(plan,baseline,desired,7,'qualification-route',route['database_id'])
    result=store.apply(request(drop_review('drop_probe')),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert result['state']=='native_rollback_returned' and result['outcome']['sqlstate']=='2BP01',result
    assert int(admin.execute(sql.SQL('SELECT value FROM {}.drop_probe').format(sql.Identifier(schema))).fetchone()[0])==77
    prepared_drop=drop_review('drop_view')
    admin.execute(sql.SQL("COMMENT ON VIEW {}.drop_view IS 'independent change'").format(sql.Identifier(schema)))
    result=store.apply(request(prepared_drop),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert result['outcome']['statements_completed']==0 and not result['outcome']['commit_requested'],result
    for drop_name in ('drop_view','drop_probe'):
        original_oid=int(admin.execute('SELECT to_regclass(%s)::oid',(schema+'.'+drop_name,)).fetchone()[0])
        result=store.apply(request(drop_review(drop_name)),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
        assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
        assert admin.execute('SELECT oid FROM pg_class WHERE oid=%s',(original_oid,)).fetchone() is None
    receipt['checks'].append('native-ddn-explicit-table-view-drop-restrict-dependent-failure-data-preservation-and-concurrent-refusal')



    admin.execute(sql.SQL('CREATE TABLE {}.rename_probe (value integer CHECK (value > 0))').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('CREATE VIEW {}.rename_view AS SELECT value FROM {}.rename_probe').format(sql.Identifier(schema), sql.Identifier(schema)))
    renamed = ' Renamed " ü '
    def rename_review(name, not_null):
        baseline = model(); desired = deepcopy(baseline)
        row = next(row for row in desired['rows'].values() if row['kind'] == 'table' and
            row['name'] == 'rename_probe' and row['native'].get('schema') == schema)
        row['native']['children']['pg_attribute'][0].update(attname=name, attnotnull=not_null, comment='Renamed column')
        plan = build_plan(baseline, desired, baseline)
        assert plan['application_supported'], plan['blockers']
        return store.review(plan, baseline, desired, 7, 'qualification-route', route['database_id'])
    prepared = rename_review(renamed, True)
    outcome = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
    assert outcome['state'] == 'native_commit_returned', outcome
    assert outcome['outcome']['rediscovery']['matches_reviewed_properties'], outcome
    admin.execute(sql.SQL('INSERT INTO {}.rename_probe ({}) VALUES (3)').format(sql.Identifier(schema), sql.Identifier(renamed)))
    assert int(admin.execute(sql.SQL('SELECT value FROM {}.rename_view').format(sql.Identifier(schema))).fetchone()[0]) == 3
    prepared = rename_review('rollback_name', True)
    admin.execute(sql.SQL('ALTER TABLE {}.rename_probe RENAME COLUMN {} TO independently_renamed').format(sql.Identifier(schema), sql.Identifier(renamed)))
    refused = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
    assert refused['outcome']['statements_completed'] == 0, refused
    admin.execute(sql.SQL('ALTER TABLE {}.rename_probe ALTER COLUMN independently_renamed DROP NOT NULL').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('INSERT INTO {}.rename_probe VALUES (NULL)').format(sql.Identifier(schema)))
    prepared = rename_review('rollback_name', True)
    rolled_back = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
    assert rolled_back['state'] == 'native_rollback_returned', rolled_back
    assert admin.execute('SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum=1',
        (sql.Identifier(schema, 'rename_probe').as_string(admin),)).fetchone()[0] == 'independently_renamed'
    receipt['checks'].append('native-ddn-column-rename-quoted-identity-dependencies-concurrent-refusal-and-combined-rollback')
    def relation_rename_review(old_name, new_name):
        baseline = model(); desired = deepcopy(baseline)
        row = next(row for row in desired['rows'].values() if row['kind'] in {'table','view'} and
            row['name'] == old_name and row['native'].get('schema') == schema)
        row['native']['catalog_row']['relname'] = new_name
        plan = build_plan(baseline, desired, baseline)
        assert plan['application_supported'], plan['blockers']
        return store.review(plan, baseline, desired, 7, 'qualification-route', route['database_id'])
    table_name = ' Renamed table " ü '
    old_oid = admin.execute('SELECT %s::regclass::oid', (sql.Identifier(schema,'rename_probe').as_string(admin),)).fetchone()[0]
    for old_name, new_name in [('rename_probe',table_name),('rename_view','renamed_dependency_view')]:
        prepared = relation_rename_review(old_name,new_name)
        outcome = store.apply(request(prepared),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
        assert outcome['state']=='native_commit_returned',outcome
        assert outcome['outcome']['rediscovery']['matches_reviewed_properties'],outcome
    assert admin.execute('SELECT %s::regclass::oid',(sql.Identifier(schema,table_name).as_string(admin),)).fetchone()[0] == old_oid
    assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.renamed_dependency_view').format(sql.Identifier(schema))).fetchone()[0]) == 2
    prepared=relation_rename_review(table_name,'must_not_rename')
    admin.execute(sql.SQL('ALTER TABLE {}.{} RENAME TO independent_relation_name').format(sql.Identifier(schema),sql.Identifier(table_name)))
    refused=store.apply(request(prepared),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert refused['outcome']['statements_completed']==0 and not refused['outcome']['native_commit_returned'],refused
    receipt['checks'].append('native-ddn-relation-rename-table-view-oid-dependencies-and-concurrent-refusal')
    admin.execute(sql.SQL('CREATE TABLE {}.default_probe(value integer DEFAULT 7, nullable integer)').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('INSERT INTO {}.default_probe DEFAULT VALUES').format(sql.Identifier(schema)))
    def default_review(value, failing=False):
        baseline=model();desired=deepcopy(baseline)
        row=next(row for row in desired['rows'].values() if row['kind']=='table' and row['name']=='default_probe' and row['native'].get('schema')==schema)
        row['native']['children']['pg_attribute'][0]['default_expression']=value
        if failing:row['native']['children']['pg_attribute'][1]['attnotnull']=True
        plan=build_plan(baseline,desired,baseline)
        assert plan['application_supported'],plan['blockers']
        return store.review(plan,baseline,desired,7,'qualification-route',route['database_id'])
    for value in ('42',None):
        prepared=default_review(value)
        outcome=store.apply(request(prepared),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
        assert outcome['state']=='native_commit_returned' and outcome['outcome']['rediscovery']['matches_reviewed_properties'],outcome
        inserted=admin.execute(sql.SQL('INSERT INTO {}.default_probe DEFAULT VALUES RETURNING value').format(sql.Identifier(schema))).fetchone()[0]
        assert inserted is None if value is None else int(inserted)==42
    assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.default_probe WHERE value=7').format(sql.Identifier(schema))).fetchone()[0])==1
    prepared=default_review('43',failing=True)
    outcome=store.apply(request(prepared),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert outcome['state']=='native_rollback_returned' and outcome['outcome']['sqlstate']=='23502',outcome
    assert admin.execute(sql.SQL('INSERT INTO {}.default_probe DEFAULT VALUES RETURNING value').format(sql.Identifier(schema))).fetchone()[0] is None
    prepared=default_review('43')
    admin.execute(sql.SQL('ALTER TABLE {}.default_probe ALTER COLUMN value SET DEFAULT 44').format(sql.Identifier(schema)))
    refused=store.apply(request(prepared),7,'qualification-route',lambda record:native.apply_review(provider,route,record))
    assert refused['outcome']['statements_completed']==0 and not refused['outcome']['native_commit_returned'],refused
    receipt['checks'].append('native-ddn-column-default-set-drop-existing-values-concurrent-refusal-and-batch-rollback')
    admin.execute(sql.SQL('CREATE TABLE {}.nullability_probe (value integer)').format(sql.Identifier(schema)))
    def nullable_review(value, comment=None):
        baseline = model(); desired = deepcopy(baseline)
        for row in desired['rows'].values():
            if row['kind'] == 'table' and row['name'] == 'nullability_probe' and row['native'].get('schema') == schema:
                row['native']['children']['pg_attribute'][0]['attnotnull'] = value
                if comment is not None:
                    row['native']['comment'] = comment
        if value is False:
            import hashlib, re
            from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
            from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff
            captured = provider.capture_catalog(route)
            exported = build_export(captured['resources'], endpoint_id='qualification',
                target_id=f'postgresql-database:{route["database_id"]}', generation=captured['generation'], engine='postgresql')
            original = exported['diagram']['snapshot']; authored = deepcopy(original)
            identity = next(key for key, row in baseline['rows'].items() if row['kind'] == 'table' and
                row['name'] == 'nullability_probe' and row['native'].get('schema') == schema)
            field = 'n_' + hashlib.sha256((identity + ':1').encode()).hexdigest()
            count = 0
            for filename, source in authored['files'].items():
                authored['files'][filename], changed = re.subn(r'(field ' + field + r'\b[^}]*?)nullable: false;', r'\1nullable: true;', source)
                count += changed
            assert count == 1
            mapped = handoff(exported['snapshot'], original, authored, engine='postgresql')
            baseline, desired = (read_catalog(mapped[key], engine='postgresql') for key in ('baseline', 'desired'))
        plan = build_plan(baseline, desired, baseline)
        assert plan['application_supported'], plan['blockers']
        return store.review(plan, baseline, desired, 7, 'qualification-route', route['database_id'])
    def null_state():
        return admin.execute('SELECT a.attnotnull FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s AND a.attname=%s', (schema, 'nullability_probe', 'value')).fetchone()[0]
    for value in (True, False):
        prepared = nullable_review(value)
        outcome = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
        assert outcome['state'] == 'native_commit_returned', outcome
        assert outcome['outcome']['rediscovery']['matches_reviewed_properties'], outcome
        assert null_state() is value
    admin.execute(sql.SQL('INSERT INTO {}.nullability_probe VALUES (NULL)').format(sql.Identifier(schema)))
    prepared = nullable_review(True, 'must roll back')
    outcome = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
    assert outcome['state'] == 'native_rollback_returned' and outcome['outcome']['sqlstate'] == '23502', outcome
    assert null_state() is False
    assert admin.execute('SELECT obj_description(c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s', (schema, 'nullability_probe')).fetchone()[0] is None
    receipt['checks'].append('native-ddn-reviewed-column-nullability-set-drop-rediscovery-and-null-data-rollback')
    receipt['checks'].append('native-ddn-graphical-field-nullability-handoff-review-apply')

    prepared = reviewed('Must not overwrite concurrent change')
    admin.execute(sql.SQL('COMMENT ON TABLE {}.parent IS {}').format(sql.Identifier(schema), sql.Literal('Concurrent comment')))
    result = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
    assert result['state'] == 'not_executed' and result['outcome']['statements_completed'] == 0, result
    receipt['checks'].append('native-ddn-locked-preflight-preserves-concurrent-comments')
    prepared = reviewed('Lock wait must be bounded')
    admin.execute('BEGIN')
    try:
        admin.execute(sql.SQL('LOCK TABLE {}.parent IN ACCESS EXCLUSIVE MODE').format(sql.Identifier(schema)))
        result = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
        assert result['state'] == 'native_rollback_returned' and result['outcome']['sqlstate'] == '55P03', result
        assert result['outcome']['statements_completed'] == 0
    finally:admin.execute('ROLLBACK')
    receipt['checks'].append('native-ddn-lock-timeout-rolls-back-owned-transaction')
    prepared = reviewed('Native rollback acknowledgement')
    original = native.control
    def rollback_acknowledgement(connection, statement):
        return original(connection, 'ROLLBACK' if statement == 'COMMIT' else statement)
    try:
        native.control = rollback_acknowledgement
        result = store.apply(request(prepared), 7, 'qualification-route', lambda record: native.apply_review(provider, route, record))
        assert result['state'] == 'native_rollback_returned', result
        assert result['outcome']['native_rollback_returned'] and not result['outcome']['native_commit_returned']
        assert admin.execute("SELECT obj_description(%s::regclass,'pg_class')", (schema + '.parent',)).fetchone()[0] == 'Concurrent comment'
    finally:native.control = original
    receipt['checks'].append('native-ddn-rollback-acknowledgement-is-not-commit-uncertainty')
    prepared = reviewed('Committed before lost reply')
    original = native.control
    calls = []
    def lose_reply(connection, statement):
        answer = original(connection, statement)
        if statement == 'COMMIT':
            calls.append(statement)
            raise ConnectionError('Owned lost commit reply')
        return answer
    try:
        native.control = lose_reply
        execute = lambda record: native.apply_review(provider, route, record)
        result = store.apply(request(prepared), 7, 'qualification-route', execute)
        assert result['state'] == 'unknown_outcome', result
        assert admin.execute("SELECT obj_description(%s::regclass,'pg_class')", (schema + '.parent',)).fetchone()[0] == 'Committed before lost reply'
        restarted = PostgreSQLSchemaApplications(store.path)
        assert restarted.apply(request(prepared), 7, 'qualification-route', execute)['state'] == 'unknown_outcome'
        assert calls == ['COMMIT'] and set(provider._sessions) == sessions
    finally:native.control = original
    receipt['checks'].append('native-ddn-lost-commit-reply-retained-across-receipt-restart-without-replay')


def qualify_server(provider, selected, admin, route, password, receipt):
    import psycopg
    from psycopg import sql
    from pgadmin.cdeadmin.providers.postgresql.server_catalog import inventory, bundle
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    database = ' srb_server_' + uuid.uuid4().hex + ' '
    role = 'srb_role_' + uuid.uuid4().hex
    secret_marker = uuid.uuid4().hex
    created_database = created_role = False
    try:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        created_database = True
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(secret_marker)))
        created_role = True
        admin.execute(sql.SQL('ALTER ROLE {} SET scratchrobin.private_token TO {}').format(sql.Identifier(role), sql.Literal(secret_marker)))
        oid = admin.execute('SELECT oid FROM pg_database WHERE datname=%s', (database,)).fetchone()[0]
        with psycopg.connect(host=route['host'], port=route['port'], user=route['user'], password=password,
            dbname=database, autocommit=True, **route.get('connection_params', {})) as other:
            other.execute('CREATE TABLE public.server_inventory_marker (id integer)')
        sessions = set(provider._sessions)
        server = inventory(provider, selected)
        assert secret_marker not in json.dumps(server)
        found = next(item for item in server['databases'] if item['oid'] == oid)
        assert found['name'] == database and found['connect_privilege']
        native_role = next(item for item in server['resources'] if item['resource_kind'] == 'role' and item['display_name'] == role)
        assert 'rolpassword' not in native_role['native']['catalog_row']
        result = bundle(provider, selected, 'qualification', [selected['database_id'], oid])
        assert result['all_selected_captured'], [(item['database_oid'], item.get('reason')) for item in result['databases']]
        assert secret_marker not in json.dumps(result)
        documents = {item['database_oid']: read_catalog(json.dumps(item['document']['snapshot']), engine='postgresql') for item in result['databases']}
        assert any(row['name'] == 'server_inventory_marker' and row['kind'] == 'table' for row in documents[oid]['rows'].values())
        assert not any(row['name'] == 'server_inventory_marker' for row in documents[selected['database_id']]['rows'].values())
        assert documents[oid]['provenance']['database_target_id'] == f'postgresql-database:{oid}'
        shared = read_catalog(json.dumps(result['server']['document']['snapshot']), engine='postgresql')
        assert any(row['name'] == role and row['kind'] == 'role' for row in shared['rows'].values())
        assert set(provider._sessions) == sessions
        receipt['checks'].append('native-server-ddn-shared-metadata-secret-redaction-two-databases-and-exact-spaced-name')
    finally:
        if created_database:admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
        if created_role:admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def qualify_test_data(provider, route, admin, receipt, schema):
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.postgresql_test_data import generate, FORMAT
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    admin.execute(sql.SQL('CREATE TABLE {}.recipe_parent (id bigint PRIMARY KEY, amount numeric(30,9), payload bytea)').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('CREATE TABLE {}.recipe_child (parent_id bigint REFERENCES {}.recipe_parent(id), amount numeric(30,9))').format(sql.Identifier(schema), sql.Identifier(schema)))
    admin.execute(sql.SQL('CREATE TABLE {}.recipe_identity (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, label text)').format(sql.Identifier(schema)))
    admin.execute(sql.SQL('CREATE TABLE {}.recipe_identity_child (parent_id bigint NOT NULL REFERENCES {}.recipe_identity(id))').format(sql.Identifier(schema), sql.Identifier(schema)))
    captured = provider.capture_catalog(route)
    model = build_export(captured['resources'], endpoint_id='qualification', target_id=f'postgresql-database:{route["database_id"]}', generation=captured['generation'], engine='postgresql', native_model=True)
    def identity(name):
        return next(key for key, row in model['rows'].items() if row['kind'] == 'table' and row['name'] == name and row['native'].get('schema') == schema)
    parent, child = identity('recipe_parent'), identity('recipe_child')
    recipe = {'format': FORMAT, 'scope': {'endpoint_id': 'qualification', 'database_target_id': f'postgresql-database:{route["database_id"]}'}, 'seed': 42, 'tables': [
        {'table': child, 'count': 2, 'columns': {'parent_id': {'kind': 'generated', 'table': parent, 'column': 'id'}}},
        {'table': parent, 'count': 2, 'columns': {
            'id': {'kind': 'sequential', 'start': '9223372036854775790', 'step': '1'},
            'amount': {'kind': 'constant', 'value': {'type': 'decimal', 'value': '12345678901234567890.123456789'}},
            'payload': {'kind': 'constant', 'value': {'type': 'binary', 'value': 'AP8='}}}}]}
    generated = generate(model, recipe)
    assert generated == generate(model, recipe) and not generated['executed']
    try:
        admin.execute('BEGIN')
        admin.execute(generated['source'])
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.recipe_child').format(sql.Identifier(schema))).fetchone()[0]) == 2
        values = admin.execute(sql.SQL('SELECT id::text, amount::text, encode(payload, %s) FROM {}.recipe_parent ORDER BY id').format(sql.Identifier(schema)), ('hex',)).fetchall()
        assert values[0] == ('9223372036854775790', '12345678901234567890.123456789', '00ff'), values
        admin.execute('ROLLBACK')
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.recipe_parent').format(sql.Identifier(schema))).fetchone()[0]) == 0
    finally:
        if admin.info.transaction_status != 0: admin.execute('ROLLBACK')
    receipt['checks'].append('native-test-data-recipe-parent-order-exact-numeric-binary-and-explicit-rollback')
    parent, child = identity('recipe_identity'), identity('recipe_identity_child')
    recipe['tables'] = [
        {'table': child, 'count': 3, 'columns': {'parent_id': {'kind': 'returned', 'table': parent, 'column': 'id'}}},
        {'table': parent, 'count': 2, 'columns': {'label': {'kind': 'constant', 'value': 'native identity'}}}]
    generated = generate(model, recipe)
    assert not generated['executed'] and generated['rows'] == 5
    try:
        admin.execute('BEGIN')
        assert int(admin.execute(generated['source']).fetchone()[0]) == 5
        actual = admin.execute(sql.SQL('SELECT p.id::text, count(*) FROM {}.recipe_identity p JOIN {}.recipe_identity_child c ON c.parent_id=p.id GROUP BY p.id ORDER BY p.id').format(sql.Identifier(schema), sql.Identifier(schema))).fetchall()
        assert [int(row[1]) for row in actual] == [2, 1], actual
        admin.execute('ROLLBACK')
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.recipe_identity_child').format(sql.Identifier(schema))).fetchone()[0]) == 0
    finally:
        if admin.info.transaction_status != 0: admin.execute('ROLLBACK')
    receipt['checks'].append('native-test-data-returning-identity-parent-dependencies-and-rollback')
    parent, child = identity('recipe_parent'), identity('recipe_child')
    recipe['tables'] = [{'table': child, 'count': 3, 'columns': {
        'parent_id': {'kind': 'existing', 'table': parent, 'column': 'id', 'order_by': ['id']},
        'amount': {'kind': 'existing', 'table': parent, 'column': 'amount', 'order_by': ['id']}}}]
    generated = generate(model, recipe)
    try:
        admin.execute('BEGIN')
        admin.execute(sql.SQL('INSERT INTO {}.recipe_parent(id,amount) VALUES (9223372036854775790,12345678901234567890.123456789), (9223372036854775791,12345678901234567891.123456789)').format(sql.Identifier(schema)))
        assert int(admin.execute(generated['source']).fetchone()[0]) == 3
        actual = admin.execute(sql.SQL('SELECT parent_id::text, count(*) FROM {}.recipe_child GROUP BY parent_id ORDER BY parent_id').format(sql.Identifier(schema))).fetchall()
        assert [(row[0], int(row[1])) for row in actual] == [('9223372036854775790', 2), ('9223372036854775791', 1)], actual
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.recipe_child c JOIN {}.recipe_parent p ON p.id=c.parent_id WHERE c.amount IS DISTINCT FROM p.amount').format(sql.Identifier(schema),sql.Identifier(schema))).fetchone()[0]) == 0
        admin.execute('ROLLBACK')
        # Empty samples supply SQL NULL instead of causing division by zero.
        admin.execute('BEGIN')
        assert int(admin.execute(generated['source']).fetchone()[0]) == 3
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.recipe_child WHERE parent_id IS NULL').format(sql.Identifier(schema))).fetchone()[0]) == 3
        admin.execute('ROLLBACK')
    finally:
        if admin.info.transaction_status != 0: admin.execute('ROLLBACK')
    receipt['checks'].append('native-test-data-existing-snapshot-exact-values-empty-sample-and-rollback')
    # The sample must obey the executing account's visibility, not the metadata
    # capture account. The role and grants are transactional fixture changes.
    role = schema + '_recipe'
    try:
        admin.execute('BEGIN')
        admin.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema),sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT SELECT ON {}.recipe_parent TO {}').format(sql.Identifier(schema),sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT SELECT, INSERT ON {}.recipe_child TO {}').format(sql.Identifier(schema),sql.Identifier(role)))
        admin.execute(sql.SQL('INSERT INTO {}.recipe_parent(id,amount) VALUES (1,11),(2,22)').format(sql.Identifier(schema)))
        admin.execute(sql.SQL('ALTER TABLE {}.recipe_parent ENABLE ROW LEVEL SECURITY').format(sql.Identifier(schema)))
        admin.execute(sql.SQL('CREATE POLICY visible_sample ON {}.recipe_parent FOR SELECT USING (id=2)').format(sql.Identifier(schema)))
        admin.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
        assert int(admin.execute(generated['source']).fetchone()[0]) == 3
        values = admin.execute(sql.SQL('SELECT parent_id::text, amount::text FROM {}.recipe_child').format(sql.Identifier(schema))).fetchall()
        assert values == [('2','22.000000000')] * 3, values
        admin.execute('RESET ROLE')
        admin.execute(sql.SQL('REVOKE SELECT ON {}.recipe_parent FROM {}').format(sql.Identifier(schema),sql.Identifier(role)))
        admin.execute(sql.SQL('REVOKE ALL ON {}.recipe_parent FROM PUBLIC').format(sql.Identifier(schema)))
        admin.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
        try:
            admin.execute(generated['source'])
            raise AssertionError('Sample read without native SELECT privilege succeeded')
        except Exception as error:
            assert getattr(error, 'sqlstate', None) == '42501', (type(error).__name__, getattr(error, 'sqlstate', None))
    finally:
        if admin.info.transaction_status != 0: admin.execute('ROLLBACK')
    assert int(admin.execute('SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname=%s', (role,)).fetchone()[0]) == 0
    receipt['checks'].append('native-test-data-sample-composite-alignment-row-security-and-permission-refusal')


def qualify_existing_creation(provider, route, admin, receipt, evidence):
    from copy import deepcopy
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql import schema_application as native
    name = 'srb_existing_' + uuid.uuid4().hex
    store = PostgreSQLSchemaApplications(evidence / 'existing-schema-reviews.json')
    def prepare():
        captured = provider.capture_catalog(route)
        baseline = build_export(captured['resources'], endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}', generation=captured['generation'],
            engine='postgresql', native_model=True)
        desired = deepcopy(baseline)
        function_id = 'postgresql:new:' + str(uuid.uuid4())
        table_id = 'postgresql:new:' + str(uuid.uuid4())
        for identity, kind, draft in [
            (function_id, 'function', {'name':'value', 'schema':name,
                'definition':f'CREATE FUNCTION {name}.value() RETURNS integer LANGUAGE SQL AS $$ SELECT 55 $$'}),
            (table_id, 'table', {'name':'created', 'schema':name, 'depends_on':[function_id],
                'columns':[{'name':'value','data_type':'integer','default':name+'.value()'}]}),
        ]:
            desired['rows'][identity] = {'resource_id':identity,'name':draft['name'],'kind':kind,
                'path':[name,draft['name']],'system':'false','native':{'system_object':False,'create':draft}}
        plan = build_plan(baseline, desired, baseline)
        assert plan['application_supported'] and all(op.get('schema_guard') for op in plan['operations']), plan
        return store.review(plan, baseline, desired, 7, 'existing-scope', route['database_id'])
    def apply(review):
        return store.apply({'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True},
            7, 'existing-scope', lambda record:native.apply_review(provider, route, record))
    def replace_schema():
        admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    try:
        reviewed = prepare()
        result = apply(reviewed)
        assert result['state'] == 'native_commit_returned', result
        assert result['outcome']['rediscovery']['matches_reviewed_properties'], result
        assert int(admin.execute(sql.SQL('INSERT INTO {}.created DEFAULT VALUES RETURNING value').format(sql.Identifier(name))).fetchone()[0]) == 55
        original_oid=int(admin.execute('SELECT to_regprocedure(%s)::oid',(name+'.value()',)).fetchone()[0])
        def overload_review():
            captured=provider.capture_catalog(route)
            baseline=build_export(captured['resources'],endpoint_id='qualification',
                target_id=f'postgresql-database:{route["database_id"]}',generation=captured['generation'],engine='postgresql',native_model=True)
            desired=deepcopy(baseline);identity='postgresql:new:'+str(uuid.uuid4())
            desired['rows'][identity]={'resource_id':identity,'name':'value','kind':'function','system':'false','path':[name,'value'],
                'native':{'system_object':False,'create':{'name':'value','schema':name,
                    'definition':f'CREATE FUNCTION {name}.value(input integer) RETURNS integer LANGUAGE SQL AS $$ SELECT input+1 $$'}}}
            plan=build_plan(baseline,desired,baseline)
            assert plan['application_supported'],plan['blockers']
            return store.review(plan,baseline,desired,7,'existing-scope',route['database_id'])
        result=apply(overload_review())
        assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
        assert int(admin.execute(sql.SQL('SELECT {}.value(41)').format(sql.Identifier(name))).fetchone()[0])==42
        result=apply(overload_review())
        assert result['state']=='native_rollback_returned' and not result['outcome']['commit_requested'],result
        assert int(admin.execute('SELECT to_regprocedure(%s)::oid',(name+'.value()',)).fetchone()[0])==original_oid
        assert int(admin.execute(sql.SQL('SELECT {}.value()').format(sql.Identifier(name))).fetchone()[0])==55
        receipt['checks'].append('native-ddn-existing-routine-overload-create-use-duplicate-signature-rollback-preserves-original')

        replace_schema()
        reviewed = prepare()
        replace_schema()
        result = apply(reviewed)
        assert result['outcome']['statements_completed'] == 0 and not result['outcome']['commit_requested'], result
        reviewed = prepare()
        original = native.build_plan
        def replace_after_preflight(*args, **kwargs):
            plan = original(*args, **kwargs)
            replace_schema()
            return plan
        native.build_plan = replace_after_preflight
        try:
            result = apply(reviewed)
        finally:
            native.build_plan = original
        assert not result['outcome']['commit_requested'], result
        assert result['outcome']['native_rollback_returned'], result
        assert admin.execute('SELECT pg_catalog.to_regclass(%s)', (name+'.created',)).fetchone()[0] is None
        assert admin.execute('SELECT pg_catalog.to_regprocedure(%s)', (name+'.value()',)).fetchone()[0] is None
        receipt['checks'].append('native-ddn-existing-schema-create-use-oid-guard-before-and-after-preflight-replacement')
    finally:
        admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(name)))


def qualify_existing_partition(provider, route, admin, receipt, evidence):
    from copy import deepcopy
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql import schema_application as native
    name = 'srb_partition_' + uuid.uuid4().hex
    store = PostgreSQLSchemaApplications(evidence / 'existing-partition-reviews.json')
    def prepare(child, lower, upper):
        captured = provider.capture_catalog(route)
        baseline = build_export(captured['resources'], endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}', generation=captured['generation'],
            engine='postgresql', native_model=True)
        parent = next(key for key, row in baseline['rows'].items() if row['name']=='parent' and
            row['kind']=='partitioned-table' and row['native'].get('schema')==name)
        desired = deepcopy(baseline)
        identity = 'postgresql:new:' + str(uuid.uuid4())
        desired['rows'][identity] = {'resource_id':identity,'name':child,'kind':'table',
            'path':[name,child],'system':'false','native':{'system_object':False,'create':{
                'name':child,'schema':name,'depends_on':[parent],
                'definition':f'CREATE TABLE {name}.{child} PARTITION OF {name}.parent FOR VALUES FROM ({lower}) TO ({upper})'}}}
        plan = build_plan(baseline, desired, baseline)
        assert plan['application_supported'] and plan['operations'][0]['parent_guard']['resource_id']==parent, plan
        return store.review(plan, baseline, desired, 7, 'partition-scope', route['database_id'])
    def apply(review):
        return store.apply({'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True},
            7, 'partition-scope', lambda record:native.apply_review(provider, route, record))
    admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    try:
        admin.execute(sql.SQL('CREATE TABLE {}.parent(value integer) PARTITION BY RANGE(value)').format(sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE TABLE {}.other PARTITION OF {}.parent DEFAULT').format(sql.Identifier(name),sql.Identifier(name)))
        admin.execute(sql.SQL('INSERT INTO {}.parent VALUES(22)').format(sql.Identifier(name)))
        reviewed = prepare('first',0,10)
        original = native.build_plan
        lock_observed = []
        def contend(*args, **kwargs):
            plan = original(*args, **kwargs)
            admin.execute("SET lock_timeout='100ms'")
            try:
                admin.execute(sql.SQL('ALTER TABLE {}.parent RENAME TO stolen').format(sql.Identifier(name)))
                raise AssertionError('Parent rename escaped the application lock')
            except Exception as error:
                assert getattr(error,'sqlstate',None)=='55P03'
                lock_observed.append(True)
            finally:
                admin.execute('RESET lock_timeout')
            return plan
        native.build_plan = contend
        try:
            result = apply(reviewed)
        finally:
            native.build_plan = original
        assert lock_observed and result['state']=='native_commit_returned', result
        assert result['outcome']['rediscovery']['matches_reviewed_properties'], result
        admin.execute(sql.SQL('INSERT INTO {}.parent VALUES(1)').format(sql.Identifier(name)))
        rows=admin.execute(sql.SQL('SELECT value,tableoid::regclass::text FROM {}.parent ORDER BY value').format(sql.Identifier(name))).fetchall()
        assert [(int(row[0]),row[1]) for row in rows]==[(1,name+'.first'),(22,name+'.other')]
        # Existing DEFAULT data must not be silently moved or lost.
        result = apply(prepare('blocked',20,30))
        assert result['state']=='native_rollback_returned' and not result['outcome']['commit_requested'], result
        assert admin.execute('SELECT to_regclass(%s)',(name+'.blocked',)).fetchone()[0] is None
        reviewed = prepare('replacement_probe',30,40)
        admin.execute(sql.SQL('ALTER TABLE {}.parent RENAME TO original').format(sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE TABLE {}.parent(value integer) PARTITION BY RANGE(value)').format(sql.Identifier(name)))
        result = apply(reviewed)
        assert not result['outcome']['commit_requested'] and result['outcome']['statements_completed']==0, result
        receipt['checks'].append('native-ddn-existing-partition-parent-lock-routing-default-conflict-and-replacement-refusal')
    finally:
        admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(name)))


def qualify_table_owned(provider, route, admin, receipt, evidence):
    from copy import deepcopy
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql.schema_application import apply_review
    name='sr_owned_'+uuid.uuid4().hex
    role='sr_policy_'+uuid.uuid4().hex
    store=PostgreSQLSchemaApplications(evidence/'table-owned-reviews.json')
    def model():
        captured=provider.capture_catalog(route)
        return build_export(captured['resources'],endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}',generation=captured['generation'],engine='postgresql',native_model=True)
    def add(desired,kind,object_name,**draft):
        identity='postgresql:new:'+str(uuid.uuid4())
        desired['rows'][identity]={'resource_id':identity,'kind':kind,'name':object_name,'system':'false','path':[name,object_name],
            'native':{'system_object':False,'create':{'name':object_name,'schema':name,**draft}}}
        return identity
    def apply(baseline,desired):
        plan=build_plan(baseline,desired,baseline)
        assert plan['application_supported'],plan['blockers']
        review=store.review(plan,baseline,desired,7,'table-owned',route['database_id'])
        return store.apply({'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True},
            7,'table-owned',lambda record:apply_review(provider,route,record))
    role_created=False
    admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    try:
        baseline=model();desired=deepcopy(baseline)
        function=add(desired,'function','change',definition=f'CREATE FUNCTION {name}.change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.value := NEW.value+10; RETURN NEW; END $$')
        for table in ('first','second'):
            parent=add(desired,'table',table,columns=[{'name':'value','data_type':'integer'}])
            add(desired,'trigger','same',table=table,depends_on=[parent,function],definition=f'CREATE TRIGGER same BEFORE INSERT ON {name}.{table} FOR EACH ROW EXECUTE FUNCTION {name}.change()')
            add(desired,'policy','same',table=table,depends_on=[parent],definition=f'CREATE POLICY same ON {name}.{table} FOR SELECT USING (value>10)')
            add(desired,'rule','same',table=table,depends_on=[parent],definition=f'CREATE RULE same AS ON DELETE TO {name}.{table} DO INSTEAD NOTHING')
        result=apply(baseline,desired)
        assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
        assert len(result['outcome']['created_objects'])==9
        baseline=model();desired=deepcopy(baseline)
        parent=next(key for key,row in baseline['rows'].items() if row['kind']=='table' and row['name']=='first' and row['native'].get('schema')==name)
        parent_oid=baseline['rows'][parent]['native']['oid']
        rename_fields={'trigger':('tgrelid','tgname'),'rule':('ev_class','rulename'),'policy':('polrelid','polname')}
        renamed=' renamed " ü '
        rename_ids=[]
        for key,row in desired['rows'].items():
            if row['kind'] in rename_fields:
                owner_field,name_field=rename_fields[row['kind']]
                if row['name']=='same' and str(row['native']['catalog_row'].get(owner_field))==str(parent_oid):
                    row['native']['catalog_row'][name_field]=renamed;rename_ids.append(key)
        result=apply(baseline,desired)
        assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
        observed=model()
        assert len(rename_ids)==3 and all(observed['rows'][key]['name']==renamed for key in rename_ids)
        receipt['checks'].append('native-ddn-table-owned-rename-quoted-whitespace-oid-preservation-and-other-table-isolation')
        activation_fields={'trigger':'tgenabled','rule':'ev_enabled'}
        for activation in ('D','R','A','O'):
            baseline=model();desired=deepcopy(baseline)
            for key in rename_ids:
                row=desired['rows'][key]
                if row['kind'] in activation_fields:
                    row['native']['catalog_row'][activation_fields[row['kind']]]=activation
            result=apply(baseline,desired)
            assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
            for replication_role in ('origin','replica'):
                admin.execute("SET session_replication_role = '"+replication_role+"'")
                try:
                    admin.execute(sql.SQL('TRUNCATE TABLE {}.first').format(sql.Identifier(name)))
                    admin.execute(sql.SQL('INSERT INTO {}.first VALUES (1)').format(sql.Identifier(name)))
                    active=activation=='A' or (activation=='O' and replication_role=='origin') or (activation=='R' and replication_role=='replica')
                    value=admin.execute(sql.SQL('SELECT value FROM {}.first').format(sql.Identifier(name))).fetchone()[0]
                    assert int(value)==(11 if active else 1),(activation,replication_role,value)
                    admin.execute(sql.SQL('DELETE FROM {}.first').format(sql.Identifier(name)))
                    count=admin.execute(sql.SQL('SELECT count(*) FROM {}.first').format(sql.Identifier(name))).fetchone()[0]
                    assert int(count)==(1 if active else 0),(activation,replication_role,count)
                finally:
                    admin.execute('SET session_replication_role = DEFAULT')
            admin.execute(sql.SQL('TRUNCATE TABLE {}.first').format(sql.Identifier(name)))
        receipt['checks'].append('native-ddn-trigger-rule-disabled-origin-replica-always-reviewed-apply-and-native-session-effects')
        for table in ('first','second'):
            admin.execute(sql.SQL('INSERT INTO {}.{} VALUES (1),(-1)').format(sql.Identifier(name),sql.Identifier(table)))
            admin.execute(sql.SQL('DELETE FROM {}.{}').format(sql.Identifier(name),sql.Identifier(table)))
            assert sorted(int(row[0]) for row in admin.execute(sql.SQL('SELECT value FROM {}.{}').format(sql.Identifier(name),sql.Identifier(table))).fetchall())==[9,11]
            admin.execute(sql.SQL('ALTER TABLE {}.{} ENABLE ROW LEVEL SECURITY').format(sql.Identifier(name),sql.Identifier(table)))
        admin.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)));role_created=True
        admin.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(name),sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}').format(sql.Identifier(name),sql.Identifier(role)))
        admin.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        try:
            assert [int(row[0]) for row in admin.execute(sql.SQL('SELECT value FROM {}.first').format(sql.Identifier(name))).fetchall()]==[11]
        finally:admin.execute('RESET ROLE')
        baseline=model();desired=deepcopy(baseline)
        parent=next(key for key,row in baseline['rows'].items() if row['kind']=='table' and row['name']=='first' and row['native'].get('schema')==name)
        add(desired,'trigger','later',table='first',depends_on=[parent],definition=f'CREATE TRIGGER later BEFORE UPDATE ON {name}.first FOR EACH ROW EXECUTE FUNCTION {name}.change()')
        result=apply(baseline,desired)
        assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
        admin.execute(sql.SQL('UPDATE {}.first SET value=100').format(sql.Identifier(name)))
        assert all(int(row[0])==110 for row in admin.execute(sql.SQL('SELECT value FROM {}.first').format(sql.Identifier(name))).fetchall())
        receipt['checks'].append('native-ddn-table-owned-trigger-rule-policy-create-exact-parent-identities-new-existing-tables-and-native-effects')
        baseline=model();desired=deepcopy(baseline)
        parent_oid=baseline['rows'][parent]['native']['oid']
        fields={'trigger':'tgrelid','rule':'ev_class','policy':'polrelid'}
        children=[key for key,row in baseline['rows'].items() if row['kind'] in fields and
            row['name']==renamed and str(row['native']['catalog_row'].get(fields[row['kind']]))==str(parent_oid)]
        assert len(children)==3
        for key in children:desired['rows'][key]['native']['comment']='Table-owned reviewed comment'
        result=apply(baseline,desired)
        assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
        baseline=model();desired=deepcopy(baseline)
        for key in children:desired['rows'][key]['native']['drop']=True
        result=apply(baseline,desired)
        assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
        observed=model()
        assert all(key not in observed['rows'] for key in children)
        assert len([row for row in observed['rows'].values() if row['kind'] in fields and
            row['name']=='same' and row['native'].get('schema')==name])==3
        admin.execute(sql.SQL('INSERT INTO {}.first VALUES (1)').format(sql.Identifier(name)))
        assert int(admin.execute(sql.SQL('SELECT min(value) FROM {}.first').format(sql.Identifier(name))).fetchone()[0])==1
        admin.execute(sql.SQL('DELETE FROM {}.first').format(sql.Identifier(name)))
        assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.first').format(sql.Identifier(name))).fetchone()[0])==0
        admin.execute(sql.SQL('INSERT INTO {}.first VALUES (5)').format(sql.Identifier(name)))
        admin.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        try:
            assert int(admin.execute(sql.SQL('SELECT count(*) FROM {}.first').format(sql.Identifier(name))).fetchone()[0])==0
            assert [int(row[0]) for row in admin.execute(sql.SQL('SELECT value FROM {}.second').format(sql.Identifier(name))).fetchall()]==[11]
        finally:admin.execute('RESET ROLE')
        admin.execute(sql.SQL('CREATE POLICY {} ON {}.first FOR SELECT USING (true)').format(sql.Identifier(renamed),sql.Identifier(name)))
        converged=build_plan(baseline,desired,model())
        assert not converged['blockers'] and not converged['operations'] and converged['counts']['converged']==3
        receipt['checks'].append('native-ddn-table-owned-comment-drop-exact-parent-same-name-isolation-rls-remains-enabled-and-replacement-preserved')
    finally:
        admin.execute('SET session_replication_role = DEFAULT')
        admin.execute('RESET ROLE')
        admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
        if role_created:admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def qualify_row_security(provider, route, admin, receipt, evidence):
    from copy import deepcopy
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql.schema_application import apply_review
    name='sr_rls_'+uuid.uuid4().hex
    owner,reader=name+'_owner',name+'_reader'
    roles=[]
    store=PostgreSQLSchemaApplications(evidence/'row-security-reviews.json')
    def model():
        captured=provider.capture_catalog(route)
        return build_export(captured['resources'],endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}',generation=captured['generation'],engine='postgresql',native_model=True)
    admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    try:
        for role in (owner,reader):
            admin.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOBYPASSRLS').format(sql.Identifier(role)))
            roles.append(role)
            admin.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(name),sql.Identifier(role)))
        admin.execute(sql.SQL('CREATE TABLE {}.records (id integer)').format(sql.Identifier(name)))
        admin.execute(sql.SQL('INSERT INTO {}.records VALUES (-1),(1)').format(sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE POLICY positive ON {}.records FOR SELECT USING (id>0)').format(sql.Identifier(name)))
        admin.execute(sql.SQL('ALTER TABLE {}.records OWNER TO {}').format(sql.Identifier(name),sql.Identifier(owner)))
        admin.execute(sql.SQL('GRANT SELECT ON {}.records TO {}').format(sql.Identifier(name),sql.Identifier(reader)))
        for enabled,forced in ((True,False),(True,True),(False,True),(False,False)):
            baseline=model();desired=deepcopy(baseline)
            identity=next(key for key,row in baseline['rows'].items() if row['kind']=='table' and row['native'].get('schema')==name)
            desired['rows'][identity]['native']['catalog_row'].update(relrowsecurity=enabled,relforcerowsecurity=forced)
            plan=build_plan(baseline,desired,baseline)
            assert plan['application_supported'],plan['blockers']
            review=store.review(plan,baseline,desired,7,'row-security',route['database_id'])
            result=store.apply({'review_id':review['review_id'],'review_digest':review['review_digest'],'confirmed':True},
                7,'row-security',lambda record:apply_review(provider,route,record))
            assert result['state']=='native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'],result
            for role in (owner,reader):
                admin.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
                try:
                    observed=[int(row[0]) for row in admin.execute(sql.SQL('SELECT id FROM {}.records ORDER BY id').format(sql.Identifier(name))).fetchall()]
                    expected=[1] if enabled and (forced or role==reader) else [-1,1]
                    assert observed==expected,(enabled,forced,role,observed)
                finally:admin.execute('RESET ROLE')
        receipt['checks'].append('native-ddn-row-security-enable-disable-force-no-force-owner-and-ordinary-role-policy-effects')
    finally:
        admin.execute('RESET ROLE')
        admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
        for role in roles:admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def qualify_data_capture(provider, route, admin, receipt):
    from psycopg import sql, errors
    from unittest.mock import patch
    from pgadmin.cdeadmin.providers.postgresql import data_capture
    import subprocess
    from pathlib import Path
    name='sr_capture_'+uuid.uuid4().hex
    role='sr_capture_role_'+uuid.uuid4().hex
    role_created=False
    sessions=set(provider._sessions)
    admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    try:
        admin.execute(sql.SQL('CREATE TABLE {}.data(id integer, "exact" numeric(40,9), "binary" bytea, nullable text)').format(sql.Identifier(name)))
        admin.execute(sql.SQL("INSERT INTO {}.data SELECT n,12345678901234567890.123456789,decode('00ff','hex'),NULL FROM generate_series(1,257)n").format(sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE VIEW {}.visible AS SELECT * FROM {}.data').format(sql.Identifier(name),sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE MATERIALIZED VIEW {}.cached AS SELECT * FROM {}.data').format(sql.Identifier(name),sql.Identifier(name)))
        def resource(table):return 'postgresql:pg_class:'+str(admin.execute('SELECT to_regclass(%s)::oid',(name+'.'+table,)).fetchone()[0])
        identity=resource('data')
        partial=data_capture.capture(provider,route,'qualification',identity,row_limit=2)
        assert partial['coverage']['rows']==2 and partial['coverage']['truncated'] and not partial['coverage']['selection_complete']
        full=data_capture.capture(provider,route,'qualification',identity,mode='full',row_limit=300)
        assert full['coverage']['rows']==257 and full['coverage']['selection_complete'] and len(full['snapshot']['files'])==3
        assert '12345678901234567890.123456789' in json.dumps(full['snapshot'])
        assert 'postgresql-text' in json.dumps(full['snapshot'])
        for table in ('visible','cached'):
            result=data_capture.capture(provider,route,'qualification',resource(table),mode='full',row_limit=257)
            assert result['coverage']['rows']==257 and result['coverage']['selection_complete']
        with patch.object(data_capture,'MAX_BYTES',1):
            try:data_capture.capture(provider,route,'qualification',identity)
            except ValueError as error:assert '4 MiB' in str(error)
            else:raise AssertionError('Data capture ignored its byte budget')
        assert set(provider._sessions)==sessions
        runtime=(Path(__file__).resolve().parents[1]/'web/pgadmin/static/vendor/ddn/current/ddn.mjs').as_uri()
        script='import runtime from '+json.dumps(runtime)+";let input='';for await(const part of process.stdin)input+=part;const doc=JSON.parse(input),w=runtime.createWorkspace(doc.snapshot.files);try{for(const view of doc.views){const r=w.renderSync({entry:view.entry,view:view.id});if(r.diagnostics.some(x=>x.severity==='error'))throw Error('Invalid data capture');}}finally{w.destroy();}"
        subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(full),text=True,capture_output=True,timeout=30,check=True)
        admin.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)));role_created=True
        admin.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(name),sql.Identifier(role)))
        admin.execute(sql.SQL('ALTER TABLE {}.data ENABLE ROW LEVEL SECURITY').format(sql.Identifier(name)))
        admin.execute(sql.SQL('CREATE POLICY visible ON {}.data FOR SELECT USING(id<3)').format(sql.Identifier(name)))
        original=provider._ensure_native_connection
        def restricted(state):
            original(state)
            state.connection.conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        with patch.object(provider,'_ensure_native_connection',side_effect=restricted):
            try:data_capture.capture(provider,route,'qualification',identity)
            except errors.InsufficientPrivilege:pass
            else:raise AssertionError('Unprivileged table read was admitted')
            admin.execute(sql.SQL('GRANT SELECT ON {}.data TO {}').format(sql.Identifier(name),sql.Identifier(role)))
            visible=data_capture.capture(provider,route,'qualification',identity,mode='full')
            assert visible['coverage']['rows']==2 and visible['coverage']['selection_complete']
        assert set(provider._sessions)==sessions
        receipt['checks'].append('native-ddn-selected-data-streamed-exact-values-full-partial-views-materialized-views-row-security-permission-refusal-budget-and-owned-release')
    finally:
        admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
        if role_created:admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def qualify_column_removal(provider, route, admin, receipt, evidence, schema):
    """Actual review/apply removal, dependency rollback and concurrent drift."""
    from copy import deepcopy
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql.schema_application import apply_review
    store = PostgreSQLSchemaApplications(evidence / 'column-removal-reviews.json')
    table = sql.Identifier(schema, 'column_removal')
    view = sql.Identifier(schema, 'column_removal_view')
    admin.execute(sql.SQL('CREATE TABLE {}(retained integer, removable text, guarded text)').format(table))
    admin.execute(sql.SQL("INSERT INTO {} VALUES (42, 'original', 'protected')").format(table))
    admin.execute(sql.SQL('CREATE VIEW {} AS SELECT guarded FROM {}').format(view, table))
    def review(*names):
        captured = provider.capture_catalog(route)
        baseline = build_export(captured['resources'], endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}', generation=captured['generation'],
            engine='postgresql', native_model=True)
        desired = deepcopy(baseline)
        row = next(row for row in desired['rows'].values() if row['kind'] == 'table'
            and row['name'] == 'column_removal' and row['native'].get('schema') == schema)
        for attribute in row['native']['children']['pg_attribute']:
            if attribute['attname'] in names: attribute['drop'] = True
        plan = build_plan(baseline, desired, baseline)
        assert plan['application_supported'], plan['blockers']
        return store.review(plan, baseline, desired, 7, 'column-removal-route', route['database_id'])
    def apply(prepared):
        return store.apply({'review_id': prepared['review_id'], 'review_digest': prepared['review_digest'],
            'confirmed': True}, 7, 'column-removal-route', lambda record: apply_review(provider, route, record))
    try:
        failed = apply(review('removable', 'guarded'))
        assert failed['state'] == 'native_rollback_returned', failed
        assert failed['outcome']['sqlstate'] == '2BP01', failed
        assert failed['outcome']['statements_completed'] == 1, failed
        assert admin.execute(sql.SQL('SELECT * FROM {}').format(table)).fetchone() == (42, 'original', 'protected')
        receipt['checks'].append('native-ddn-column-removal-dependent-view-refusal-atomic-rollback')
        stale = review('removable')
        admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN removable SET DEFAULT 'changed'").format(table))
        refused = apply(stale)
        assert refused['state'] == 'not_executed' and refused['outcome']['statements_completed'] == 0, refused
        receipt['checks'].append('native-ddn-column-removal-concurrent-default-drift-refusal')
        applied = apply(review('removable'))
        assert applied['state'] == 'native_commit_returned', applied
        assert applied['outcome']['rediscovery']['matches_reviewed_properties'], applied
        assert admin.execute(sql.SQL('SELECT * FROM {}').format(table)).fetchone() == (42, 'protected')
        receipt['checks'].append('native-ddn-column-removal-review-commit-rediscovery-retained-data')
    finally:
        admin.execute(sql.SQL('DROP VIEW IF EXISTS {}').format(view))
        admin.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(table))


def qualify_column_addition(provider, route, admin, receipt, evidence, schema):
    from copy import deepcopy
    import uuid
    from psycopg import sql
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
    from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
    from pgadmin.cdeadmin.providers.postgresql.schema_application import apply_review
    store = PostgreSQLSchemaApplications(evidence / 'column-addition-reviews.json')
    table = sql.Identifier(schema, 'column_addition')
    admin.execute(sql.SQL('CREATE TABLE {}(retained integer)').format(table))
    admin.execute(sql.SQL('INSERT INTO {} VALUES (42)').format(table))
    def review(*definitions):
        captured = provider.capture_catalog(route)
        baseline = build_export(captured['resources'], endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}', generation=captured['generation'],
            engine='postgresql', native_model=True)
        desired = deepcopy(baseline)
        row = next(row for row in desired['rows'].values() if row['kind'] == 'table'
            and row['name'] == 'column_addition' and row['native'].get('schema') == schema)
        row['native']['add_columns'] = [{'resource_id': 'postgresql:new:' + str(uuid.uuid4()),
            'definition': definition} for definition in definitions]
        plan = build_plan(baseline, desired, baseline)
        assert plan['application_supported'], plan['blockers']
        return store.review(plan, baseline, desired, 7, 'column-addition-route', route['database_id'])
    def apply(prepared):
        return store.apply({'review_id': prepared['review_id'], 'review_digest': prepared['review_digest'],
            'confirmed': True}, 7, 'column-addition-route', lambda record: apply_review(provider, route, record))
    try:
        failed = apply(review({'name': 'first_added', 'data_type': 'text'},
            {'name': 'must_have_value', 'data_type': 'integer', 'nullable': False}))
        assert failed['state'] == 'native_rollback_returned', failed
        assert failed['outcome']['sqlstate'] == '23502' and failed['outcome']['statements_completed'] == 1, failed
        assert admin.execute(sql.SQL('SELECT * FROM {}').format(table)).fetchone() == (42,)
        receipt['checks'].append('native-ddn-column-addition-not-null-failure-atomic-rollback')
        prepared = review({'name': ' amount ', 'data_type': 'numeric(29,6)',
                'default': '12345678901234567890123.456789', 'nullable': False},
            {'name': 'doubled', 'data_type': 'bigint',
                'generated': {'expression': 'retained * 2', 'storage': 'STORED'}},
            {'name': 'identity_value', 'data_type': 'bigint', 'identity': 'ALWAYS'})
        applied = apply(prepared)
        assert applied['state'] == 'native_commit_returned', applied
        assert applied['outcome']['rediscovery']['matches_reviewed_properties'], applied
        mapped = applied['outcome']['added_columns']
        assert len(mapped) == 3 and len({item['native_resource_id'] for item in mapped}) == 3
        assert all(item['resource_id'].startswith('postgresql:new:') and item['attribute_number'] > 1 for item in mapped)
        values = admin.execute(sql.SQL('SELECT " amount "::text, doubled::text, identity_value::text FROM {}').format(table)).fetchone()
        assert values == ('12345678901234567890123.456789', '84', '1'), values
        replay = apply(prepared)
        assert replay['state'] == 'native_commit_returned' and replay['outcome'] == applied['outcome']
        receipt['checks'].append('native-ddn-column-addition-durable-draft-native-identity-map-no-replay')
        receipt['checks'].append('native-ddn-column-addition-exact-default-generated-identity-existing-row-values')
        from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff, read_relations
        from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
        import hashlib, json
        captured = provider.capture_catalog(route)
        exported = build_export(captured['resources'], endpoint_id='qualification',
            target_id=f'postgresql-database:{route["database_id"]}', generation=captured['generation'], engine='postgresql')
        original = exported['diagram']['snapshot']
        rows = read_relations(original, engine='postgresql')
        parent_id = next(key for key, value in rows.items() if value['native'].get('schema') == schema
            and value['native'].get('catalog_row', {}).get('relname') == 'column_addition')
        draft_uid = rows[parent_id]['uid'] + ':new:' + str(uuid.uuid4())
        anchor = 'field n_' + hashlib.sha256((parent_id + ':1').encode()).hexdigest()
        field = 'field owned_graphical "diagram field" {uid: ' + json.dumps(draft_uid) + '; datatype: "text"; nullable: true;}'
        edited = deepcopy(original)
        edited['files'] = {key: source.replace(anchor, field + '\n' + anchor) for key, source in edited['files'].items()}
        assert edited != original
        handed = handoff(exported['snapshot'], original, edited, engine='postgresql')
        baseline = read_catalog(handed['baseline'], engine='postgresql')
        desired = read_catalog(handed['desired'], engine='postgresql')
        planned = build_plan(baseline, desired, baseline)
        assert planned['application_supported'], planned['blockers']
        graphical = store.review(planned, baseline, desired, 7, 'column-addition-route', route['database_id'])
        result = apply(graphical)
        assert result['state'] == 'native_commit_returned' and result['outcome']['rediscovery']['matches_reviewed_properties'], result
        assert admin.execute(sql.SQL('SELECT "diagram field" FROM {}').format(table)).fetchone() == (None,)
        receipt['checks'].append('native-ddn-new-graphical-field-parent-bound-handoff-review-apply-rediscovery')
        stale = review({'name': 'conflicting', 'data_type': 'text'})
        admin.execute(sql.SQL('ALTER TABLE {} ADD COLUMN conflicting integer').format(table))
        refused = apply(stale)
        assert refused['state'] == 'not_executed' and refused['outcome']['statements_completed'] == 0, refused
        observed = admin.execute("SELECT format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid=%s::regclass AND attname='conflicting'", (table.as_string(admin),)).fetchone()[0]
        assert observed == 'integer'
        receipt['checks'].append('native-ddn-column-addition-concurrent-same-name-preserved')
    finally:
        admin.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(table))
