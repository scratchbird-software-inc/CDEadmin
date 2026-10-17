"""Independent native catalog and navigator reconciliation for three engines.

Expected inventories are raw release-native queries, never provider declarations.
Receipts cover the observed installation and connection scopes only. Optional
uninstalled features and denied sections remain explicit in the owning matrix.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
import config  # noqa: E402,F401
from pgadmin.cdeadmin.navigator import resource_children  # noqa: E402


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def reconcile_sets(expected, actual, resources, engine, facts):
    failures, checks = [], []
    for kind in sorted(set(expected) | set(actual)):
        raw, visible = Counter(expected.get(kind, [])), Counter(actual.get(kind, []))
        equal = raw == visible
        checks.append({'kind': kind, 'native_count': sum(raw.values()),
                       'provider_count': sum(visible.values()), 'equal': equal})
        if not equal:
            failures.append({'kind': kind, 'missing': list((raw - visible).elements()),
                             'extra': list((visible - raw).elements())})
    ids = [row['resource_id'] for row in resources]
    if len(ids) != len(set(ids)): failures.append({'duplicate_identities': True})
    roots = [row for row in resources if row['resource_kind'] == 'database']
    pending = [{'scope': 'server', 'parent_path': []}] + [
        {'scope': 'database', 'parent_path': [], 'database': row['display_name']} for row in roots]
    # The workspace supplies registered database roots above resource_children.
    # Reconcile their identities natively and report them separately here.
    visited, found = set(), {row['resource_id'] for row in roots}
    while pending:
        state = pending.pop(); key = canonical(state)
        if key in visited: continue
        visited.add(key)
        for node in resource_children(resources, state, {'engine_id': engine}):
            if node['node_type'] == 'resource':
                found.add(node['resource_id'])
                if node.get('has_children') and not node.get('section'):
                    pending.append({**state, 'scope': 'resource', 'resource_id': node['resource_id'], 'parent_path': node['display_path']})
            else:
                pending.append({**state, 'scope': node.get('scope', 'kind'), **{key: value for key, value in node.items()
                    if key in {'resource_kind', 'parent_path', 'virtual_branch', 'object_scope'}}})
    missing = set(ids) - found
    if missing: failures.append({'unreachable_resource_ids': sorted(missing)})
    for fact in facts:
        if not fact['equal']: failures.append({'native_child_fact_mismatch': fact['section']})
    return {'engine': engine, 'checks': checks, 'native_child_facts': facts,
            'resource_count': len(ids), 'reachable_count': len(found), 'failures': failures,
            'registration_roots': [row['resource_id'] for row in roots],
            'complete': not failures, 'scope': 'Exact observed native metadata and navigator; feature acceptance remains separate'}


def sqlite(connection):
    from pgadmin.cdeadmin.providers.sqlite.provider import _resources
    quote = lambda value: '"' + value.replace('"', '""') + '"'
    expected, facts = {}, []
    def add(kind, path): expected.setdefault(kind, []).append(tuple(path))
    resources = _resources(connection, {})
    by_path = {(row['resource_kind'], tuple(row['display_path'])): row for row in resources}
    def module(source):
        # Observe the native parser independently of provider classifications.
        import sqlite3
        probe=sqlite3.connect(':memory:');observed=[]
        def record(code,_name,argument,_database,_context):
            if code==sqlite3.SQLITE_CREATE_VTABLE:observed.append(argument)
            return sqlite3.SQLITE_OK
        try:
            probe.set_authorizer(record);probe.execute('EXPLAIN '+source).fetchone()
            return observed[0] if len(observed)==1 else None
        finally:probe.close()
    for _, schema, _ in connection.execute('PRAGMA database_list'):
        add('database' if schema == 'main' else 'attached-database', [schema])
        for kind, name, owner, ddl in connection.execute('SELECT type,name,tbl_name,sql FROM ' + quote(schema) + '.sqlite_schema'):
            if kind == 'table' and (ddl or '').lstrip().upper().startswith('CREATE VIRTUAL TABLE'):
                kind = 'fts-table' if (module(ddl) or '').lower() in {'fts3','fts4','fts5'} else 'virtual-table'
            path = [schema, owner, name] if kind in {'index', 'trigger'} else [schema, name]
            if kind != 'index' or tuple(path) not in expected.get('index', []): add(kind, path)
            resource = by_path.get((kind, tuple(path)))
            facts.append({'section': canonical([schema, name, 'ddl']), 'equal': resource is not None and resource['native'].get('ddl') == (ddl or '')})
            if kind in {'fts-table','virtual-table'}:
                observed=(resource or {}).get('native',{}).get('module_observation',{})
                facts.append({'section':canonical([schema,name,'native-module']),'equal':observed.get('available') is True and observed.get('module')==module(ddl)})
                native_module=module(ddl)
                if native_module and native_module.lower() in {'fts3','fts4','fts5'}:
                    configuration=(resource or {}).get('native',{}).get('fts_configuration',{})
                    if native_module.lower()=='fts5':
                        settings=list(connection.execute('SELECT k,v FROM '+quote(schema)+'.'+quote(name+'_config')+' ORDER BY k'))
                        native_version=next(value for key,value in settings if key=='version')
                        expected_commands=[list(row) for row in settings if row[0]!='version']
                    else:
                        present=connection.execute('SELECT 1 FROM '+quote(schema)+'.sqlite_schema WHERE name=?',(name+'_stat',)).fetchone()
                        settings=list(connection.execute('SELECT value FROM '+quote(schema)+'.'+quote(name+'_stat')+' WHERE id=2')) if present else []
                        native_version=None;expected_commands=[['automerge',settings[0][0]]] if settings else []
                    facts.append({'section':canonical([schema,name,'native-fts-configuration']),
                        'equal':configuration.get('available') is True and configuration.get('commands')==expected_commands and configuration.get('native_format_version')==native_version})
            if kind not in {'table', 'view', 'fts-table', 'virtual-table'}: continue
            raw = list(connection.execute('PRAGMA ' + quote(schema) + '.table_xinfo(' + quote(name) + ')'))
            for _, column, *_ in raw: add('column', [schema, name, column])
            observed = (resource or {}).get('native', {}).get('columns', [])
            actual = [(row['ordinal_position'], row['name'], row['data_type'], int(not row['nullable']),
                       row['default'], row['primary_key_position'], row['hidden']) for row in observed]
            facts.append({'section': canonical([schema, name, 'table_xinfo']), 'equal': Counter(raw) == Counter(actual)})
            if kind == 'view': continue
            for _, index, _, _, _ in connection.execute('PRAGMA ' + quote(schema) + '.index_list(' + quote(name) + ')'):
                if (schema, name, index) not in expected.get('index', []):
                    add('index', [schema, name, index])
                raw_keys = list(connection.execute('PRAGMA ' + quote(schema) + '.index_xinfo(' + quote(index) + ')'))
                native = by_path.get(('index', (schema, name, index)), {}).get('native', {}).get('catalog_metadata', {})
                keys = [(row['sequence'], row['column_id'], row['name'], int(row['descending']), row['collation'], int(row['is_key']))
                        for row in native.get('keys', [])]
                facts.append({'section': canonical([schema, index, 'index_xinfo']), 'equal': Counter(raw_keys) == Counter(keys)})
            raw_foreign = list(connection.execute('PRAGMA ' + quote(schema) + '.foreign_key_list(' + quote(name) + ')'))
            actual_foreign = []
            for row in (resource or {}).get('native', {}).get('constraints', []):
                if row['constraint_type'] != 'FOREIGN KEY': continue
                identity = int(row['name'].rsplit('_', 1)[1])
                actual_foreign.extend((identity, index, row['referenced_table'], column, target,
                    row['on_update'], row['on_delete'], row['match']) for index, (column, target) in
                    enumerate(zip(row['columns'], row['referenced_columns'])))
            facts.append({'section': canonical([schema, name, 'foreign_key_list']), 'equal': Counter(raw_foreign) == Counter(actual_foreign)})
    for source, kind in [('PRAGMA pragma_list', 'pragma'), ('PRAGMA module_list', 'extension'),
                         ('PRAGMA compile_options', 'compile-option')]:
        for (name,) in connection.execute(source): add(kind, [name])
    for _, name in connection.execute('PRAGMA collation_list'): add('collation', [name])
    for name, builtin, kind, encoding, arity, _ in connection.execute('PRAGMA function_list'):
        add('native-function', [json.dumps([name, builtin, kind, encoding, arity], ensure_ascii=False, separators=(',', ':'))])
    actual = {}
    for row in resources:
        if row['resource_kind'] in {'constraint', 'metric'}: continue
        actual.setdefault(row['resource_kind'], []).append(tuple(row['display_path']))
    return reconcile_sets(expected, actual, resources, 'sqlite', facts)


DUCKDB_INVENTORY = {
    'database': "SELECT database_name FROM duckdb_databases() WHERE NOT internal AND database_name=current_database()",
    'attached-database': "SELECT database_name FROM duckdb_databases() WHERE NOT internal AND database_name<>current_database()",
    'schema': 'SELECT s.database_name,s.schema_name FROM duckdb_schemas() s JOIN duckdb_databases() d USING(database_name) WHERE NOT d.internal',
    'table': 'SELECT database_name,schema_name,table_name FROM duckdb_tables() WHERE NOT internal',
    'view': 'SELECT database_name,schema_name,view_name FROM duckdb_views() WHERE NOT internal',
    'column': 'SELECT database_name,schema_name,table_name,column_name FROM duckdb_columns() WHERE NOT internal',
    'index': 'SELECT database_name,schema_name,table_name,index_name FROM duckdb_indexes()',
    'sequence': 'SELECT database_name,schema_name,sequence_name FROM duckdb_sequences()',
    'type': 'SELECT database_name,schema_name,type_name FROM duckdb_types() WHERE NOT internal',
    'extension': 'SELECT extension_name FROM duckdb_extensions()',
    'secret': 'SELECT name FROM duckdb_secrets()',
}


def duckdb(connection):
    from pgadmin.cdeadmin.providers.duckdb.provider import _resources
    expected = {kind: connection.execute(query).fetchall() for kind, query in DUCKDB_INVENTORY.items()}
    for kind in ('function', 'macro'):
        expected[kind] = connection.execute('SELECT DISTINCT database_name,schema_name,function_name FROM duckdb_functions() WHERE ' +
            ("function_type LIKE '%macro%'" if kind == 'macro' else "function_type NOT LIKE '%macro%'")).fetchall()
    expected['constraint'] = connection.execute('SELECT database_name,schema_name,table_name,constraint_name,constraint_index FROM duckdb_constraints()').fetchall()
    resources = _resources(connection, {})
    actual, facts = {}, []
    for row in resources:
        path = tuple(row['display_path']); native = row.get('native', {})
        if row['resource_kind'] == 'constraint': path += (native['catalog_metadata']['constraint_index'],)
        actual.setdefault(row['resource_kind'], []).append(path)
    raw = connection.execute('SELECT database_name,schema_name,function_name,function_type,parameters,parameter_types,varargs,macro_definition FROM duckdb_functions()').fetchall()
    observed = [(row['display_path'][0], row['display_path'][1], row['display_name'],
        overload['catalog_metadata']['function_type'], [parameter['name'] for parameter in overload['parameters']],
        [parameter['data_type'] for parameter in overload['parameters']], overload['catalog_metadata']['varargs'], overload.get('definition'))
        for row in resources if row['resource_kind'] in {'macro', 'function'} for overload in row['native']['overloads']]
    facts.append({'section': 'duckdb_functions overloads/signatures/bodies', 'native_count': len(raw),
                  'provider_count': len(observed), 'equal': Counter(map(canonical, raw)) == Counter(map(canonical, observed))})
    return reconcile_sets(expected, actual, resources, 'duckdb', facts)


# PostgreSQL 18 native object catalogs; OIDs preserve overload and punctuation
# identities. Shared catalogs are reconciled separately by server_inventory.
PG_CATALOGS = ('pg_namespace', 'pg_class', 'pg_type', 'pg_proc', 'pg_constraint', 'pg_trigger',
    'pg_rewrite', 'pg_policy', 'pg_extension', 'pg_collation', 'pg_conversion', 'pg_operator',
    'pg_opclass', 'pg_opfamily', 'pg_ts_config', 'pg_ts_dict', 'pg_ts_parser', 'pg_ts_template',
    'pg_statistic_ext', 'pg_cast', 'pg_transform', 'pg_default_acl', 'pg_user_mapping', 'pg_language',
    'pg_event_trigger', 'pg_publication', 'pg_foreign_data_wrapper', 'pg_foreign_server', 'pg_am', 'pg_subscription', 'pg_largeobject_metadata')
PG_CHILDREN = (('pg_attribute', 'attrelid', 'pg_class', 'attnum>0 AND NOT attisdropped'),
    ('pg_attrdef', 'adrelid', 'pg_class', 'true'), ('pg_index', 'indexrelid', 'pg_class', 'true'),
    ('pg_inherits', 'inhrelid', 'pg_class', 'true'), ('pg_partitioned_table', 'partrelid', 'pg_class', 'true'),
    ('pg_sequence', 'seqrelid', 'pg_class', 'true'), ('pg_foreign_table', 'ftrelid', 'pg_class', 'true'),
    ('pg_enum', 'enumtypid', 'pg_type', 'true'), ('pg_range', 'rngtypid', 'pg_type', 'true'),
    ('pg_aggregate', 'aggfnoid', 'pg_proc', 'true'), ('pg_amop', 'amopfamily', 'pg_opfamily', 'true'),
    ('pg_amproc', 'amprocfamily', 'pg_opfamily', 'true'), ('pg_ts_config_map', 'mapcfg', 'pg_ts_config', 'true'),
    ('pg_publication_rel', 'prpubid', 'pg_publication', 'true'), ('pg_publication_namespace', 'pnpubid', 'pg_publication', 'true'),
    ('pg_subscription_rel', 'srsubid', 'pg_subscription', 'true'))


def postgresql(connection, database_oid):
    from pgadmin.cdeadmin.providers.postgresql.catalog_capture import capture
    captured = capture(connection, database_oid, include_system=True)
    resources = captured['resources']; expected, actual, facts = {}, {}, []
    for catalog in PG_CATALOGS:
        predicate = "relpersistence<>'t'" if catalog == 'pg_class' else 'true'
        if catalog == 'pg_subscription': predicate = 'subdbid=' + str(int(database_oid))
        expected['pg_largeobject' if catalog == 'pg_largeobject_metadata' else catalog] = [(int(row[0]),) for row in connection.execute('SELECT oid FROM pg_catalog.' + catalog + ' WHERE ' + predicate)]
    expected['pg_database'] = [(database_oid,)]
    for row in resources: actual.setdefault(row['native']['catalog'], []).append((row['native']['oid'],))
    for catalog, owner_column, parent, predicate in PG_CHILDREN:
        owners = [row['native']['oid'] for row in resources if row['native']['catalog'] == parent]
        raw = [json.loads(row[0]) for row in connection.execute('SELECT to_jsonb(c)::text FROM pg_catalog.' + catalog +
            ' c WHERE ' + owner_column + '=ANY(%s::oid[]) AND (' + predicate + ')', (owners,))]
        observed = [child for row in resources for child in row['native'].get('children', {}).get(catalog, [])]
        # Capture adds readable expressions/type names, redacting foreign options.
        keys = set(raw[0]) if raw else set()
        if catalog == 'pg_foreign_table': keys.discard('ftoptions')
        project = lambda row: {key: row[key] for key in keys if key in row}
        facts.append({'section': catalog, 'native_count': len(raw), 'provider_count': len(observed),
                      'equal': Counter(canonical(project(row)) for row in raw) == Counter(canonical(project(row)) for row in observed)})
    result = reconcile_sets(expected, actual, resources, 'postgresql', facts)
    result['observations'] = captured['resources'][0]['native']['catalog_observations']
    return result


def qualify(engine, output):
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='scratchrobin-catalog-') as temporary:
        root = Path(temporary)
        if engine == 'sqlite':
            import sqlite3
            connection = sqlite3.connect(root / 'owned.db')
            connection.execute('ATTACH DATABASE ? AS "other.db"', (str(root / 'attached.db'),))
            connection.create_function('owned_function', 2, lambda a, b: a)
            connection.create_collation('owned_collation', lambda a, b: (a > b) - (a < b))
            statements = ['CREATE TABLE "odd.table"("odd.column" INTEGER PRIMARY KEY, label TEXT UNIQUE, n INTEGER GENERATED ALWAYS AS (length(label)))',
                'CREATE TABLE child(parent INTEGER REFERENCES "odd.table"("odd.column"))',
                'CREATE INDEX "odd.index" ON child(parent)', 'CREATE VIEW "odd.view" AS SELECT * FROM child',
                'CREATE TEMP TABLE session_table(id INTEGER)', 'CREATE TABLE "other.db".attached(id INTEGER)',
                'CREATE VIRTUAL TABLE search USING fts5(body)',
                'CREATE VIRTUAL TABLE "quoted.search" USING "fts5"(body)',
                "CREATE VIRTUAL TABLE 'single.search' USING 'fts4'(body)",
                'CREATE VIRTUAL TABLE [bracket.search] USING [fts3](body)',
                'CREATE VIRTUAL TABLE "quoted.spatial" USING "rtree"(id,x1,x2)']
            statements += ["INSERT INTO search(search,rank) VALUES('pgsz',1024)",
                "INSERT INTO search(search,rank) VALUES('rank','bm25(2.0)')",
                "INSERT INTO 'single.search'('single.search') VALUES('automerge=4')",
                "INSERT INTO 'bracket.search'('bracket.search') VALUES('automerge=4')"]
        else:
            import duckdb as native
            connection = native.connect(str(root / 'owned.duckdb'))
            statements = ["ATTACH '" + str(root / 'attached.duckdb').replace("'", "''") + "' AS other",
                'CREATE TABLE "odd.table"("odd.column" INTEGER PRIMARY KEY, amount DECIMAL(30,8))',
                'CREATE TABLE child(parent INTEGER REFERENCES "odd.table"("odd.column"))',
                'CREATE VIEW "odd.view" AS SELECT * FROM child', 'CREATE INDEX "odd.index" ON child(parent)',
                'CREATE TEMP TABLE session_table(id INTEGER)', 'CREATE TABLE other.attached(id INTEGER)',
                "CREATE TYPE mood AS ENUM ('a','Quoted ü')", 'CREATE MACRO overloaded(x) AS x+1, (x,y) AS x+y',
                'CREATE SEQUENCE owned_sequence START 41']
        try:
            for statement in statements: connection.execute(statement)
            if engine == 'sqlite': connection.commit()
            result = globals()[engine](connection)
        finally: connection.close()
    result['owned_state_removed'] = not root.exists()
    result['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [Path(__file__), ROOT / 'web/pgadmin/cdeadmin/navigator.py',
            ROOT / f'web/pgadmin/cdeadmin/providers/{engine}/provider.py',
            *([ROOT/'web/pgadmin/cdeadmin/providers/sqlite/modules.py',ROOT/'web/pgadmin/cdeadmin/providers/sqlite/fts_configuration.py'] if engine=='sqlite' else [])]}
    (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('sqlite', 'duckdb'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if qualify(args.engine, args.output)['complete'] else 1)
