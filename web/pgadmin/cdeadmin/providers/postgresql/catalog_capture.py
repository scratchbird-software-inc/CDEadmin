"""Bounded PostgreSQL-native catalog evidence on an independently owned session.

This adapter captures definitions; it never interprets imported SQL as authority.
Callers own attachment creation/release. No existing transaction may be borrowed.
"""
import json
import uuid

from psycopg import sql, errors, Cursor, ServerCursor
from psycopg.rows import tuple_row

MAX_OBJECTS = 20000
MAX_BYTES = 8 * 1024 * 1024

# SQL fragments are application constants. No document/browser text enters them.
# (catalog, kind, name expression, namespace expression, extra FROM, predicate,
#  subobject/address expression, native definition expression)
CATALOGS = (
    ('pg_namespace', 'schema', 'c.nspname', 'c.nspname', '', 'true', 'c.oid', 'NULL::text'),
    ('pg_class', 'relation', 'c.relname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace',
     "c.relkind IN ('r','p','v','m','f','S','i','I','c') AND c.relpersistence <> 't'", 'c.oid',
     "CASE WHEN c.relkind IN ('v','m') THEN pg_catalog.pg_get_viewdef(c.oid,false) WHEN c.relkind IN ('i','I') THEN pg_catalog.pg_get_indexdef(c.oid) END"),
    ('pg_type', 'type', 'c.typname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.typnamespace', 'true', 'c.oid', 'pg_catalog.format_type(c.oid,NULL)'),
    ('pg_proc', 'routine', 'c.proname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.pronamespace', 'true', 'c.oid',
     "CASE WHEN c.prokind <> 'a' THEN pg_catalog.pg_get_functiondef(c.oid) END"),
    ('pg_constraint', 'constraint', 'c.conname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace', 'true', 'c.oid', 'pg_catalog.pg_get_constraintdef(c.oid,false)'),
    ('pg_trigger', 'trigger', 'c.tgname', 'n.nspname', 'JOIN pg_catalog.pg_class r ON r.oid=c.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace', 'true', 'c.oid', 'pg_catalog.pg_get_triggerdef(c.oid,false)'),
    ('pg_rewrite', 'rule', 'c.rulename', 'n.nspname', 'JOIN pg_catalog.pg_class r ON r.oid=c.ev_class JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace', 'true', 'c.oid', 'pg_catalog.pg_get_ruledef(c.oid,false)'),
    ('pg_policy', 'policy', 'c.polname', 'n.nspname', 'JOIN pg_catalog.pg_class r ON r.oid=c.polrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_extension', 'extension', 'c.extname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.extnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_collation', 'collation', 'c.collname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.collnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_conversion', 'conversion', 'c.conname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_operator', 'operator', 'c.oprname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.oprnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_opclass', 'operator-class', 'c.opcname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.opcnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_opfamily', 'operator-family', 'c.opfname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.opfnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_ts_config', 'text-search-configuration', 'c.cfgname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.cfgnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_ts_dict', 'text-search-dictionary', 'c.dictname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.dictnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_ts_parser', 'text-search-parser', 'c.prsname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.prsnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_ts_template', 'text-search-template', 'c.tmplname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.tmplnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_statistic_ext', 'extended-statistics', 'c.stxname', 'n.nspname', 'JOIN pg_catalog.pg_namespace n ON n.oid=c.stxnamespace', 'true', 'c.oid', 'pg_catalog.pg_get_statisticsobjdef(c.oid)'),
    ('pg_cast', 'cast', "pg_catalog.format_type(c.castsource,NULL) || ' AS ' || pg_catalog.format_type(c.casttarget,NULL)", 'NULL::text', '', 'true', 'c.oid', 'NULL::text'),
    ('pg_transform', 'transform', "pg_catalog.format_type(c.trftype,NULL) || ' / ' || l.lanname", 'NULL::text', 'JOIN pg_catalog.pg_language l ON l.oid=c.trflang', 'true', 'c.oid', 'NULL::text'),
    ('pg_default_acl', 'default-privileges', "pg_catalog.pg_get_userbyid(c.defaclrole) || ' / ' || COALESCE(n.nspname, '*') || ' / ' || c.defaclobjtype::text", 'NULL::text', 'LEFT JOIN pg_catalog.pg_namespace n ON n.oid=c.defaclnamespace', 'true', 'c.oid', 'NULL::text'),
    ('pg_user_mapping', 'user-mapping', "CASE WHEN c.umuser=0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(c.umuser) END || ' / ' || s.srvname", 'NULL::text', 'JOIN pg_catalog.pg_foreign_server s ON s.oid=c.umserver', 'true', 'c.oid', 'NULL::text'),
)
GLOBAL = (
    ('pg_language', 'language', 'lanname'), ('pg_event_trigger', 'event-trigger', 'evtname'),
    ('pg_publication', 'publication', 'pubname'), ('pg_foreign_data_wrapper', 'foreign-data-wrapper', 'fdwname'),
    ('pg_foreign_server', 'foreign-server', 'srvname'),
    ('pg_am', 'access-method', 'amname'),
    ('pg_subscription', 'subscription', 'subname'),
)
RELATION_KINDS = {
    'r': 'table', 'p': 'partitioned-table', 'v': 'view',
    'm': 'materialized-view', 'f': 'foreign-table', 'S': 'sequence',
    'i': 'index', 'I': 'partitioned-index', 'c': 'composite-relation',
}
ROUTINE_KINDS = {
    'p': 'procedure', 'a': 'aggregate', 'w': 'window-function', 'f': 'function',
}
CAPTURE_RESOURCE_KINDS = frozenset(
    {'database', 'domain'} | {row[1] for row in CATALOGS + GLOBAL}
    | set(RELATION_KINDS.values()) | set(ROUTINE_KINDS.values())
)
# Child facts remain attached to their owning native object. They are never
# flattened into a common SQL type or treated as standalone deployment commands.
CHILDREN = (
    ('pg_attribute', 'attrelid', 'pg_class', 'attnum > 0 AND NOT attisdropped'),
    ('pg_attrdef', 'adrelid', 'pg_class', 'true'),
    ('pg_index', 'indexrelid', 'pg_class', 'true'),
    ('pg_inherits', 'inhrelid', 'pg_class', 'true'),
    ('pg_partitioned_table', 'partrelid', 'pg_class', 'true'),
    ('pg_sequence', 'seqrelid', 'pg_class', 'true'),
    ('pg_foreign_table', 'ftrelid', 'pg_class', 'true'),
    ('pg_enum', 'enumtypid', 'pg_type', 'true'),
    ('pg_range', 'rngtypid', 'pg_type', 'true'),
    ('pg_aggregate', 'aggfnoid', 'pg_proc', 'true'),
    ('pg_amop', 'amopfamily', 'pg_opfamily', 'true'),
    ('pg_amproc', 'amprocfamily', 'pg_opfamily', 'true'),
    ('pg_ts_config_map', 'mapcfg', 'pg_ts_config', 'true'),
    ('pg_publication_rel', 'prpubid', 'pg_publication', 'true'),
    ('pg_publication_namespace', 'pnpubid', 'pg_publication', 'true'),
    ('pg_subscription_rel', 'srsubid', 'pg_subscription', 'true'),
)
EXCLUSIONS = (
    'Role password hashes, subscription connection strings and user-mapping credentials are not exported.',
    'Foreign-server, wrapper and foreign-table options are redacted; they may contain credentials.',
    'Replication origins/slots, role settings and shared-object metadata require separate capture.',
    'Row data, large-object contents, sequence current values and collected statistics are not metadata capture.',
    'This is documentary native metadata, not a complete backup or deployable migration.',
)


def capture(connection, database_oid, *, include_system=False, _in_transaction=False):
    """Capture using an idle, independently owned psycopg connection."""
    if type(database_oid) is not int or not 1 <= database_oid <= 4294967295:
        raise ValueError('Select an explicit native database OID')
    if type(include_system) is not bool:
        raise ValueError('Invalid system-object selection')
    if type(_in_transaction) is not bool or int(connection.info.transaction_status) != (2 if _in_transaction else 0):
        raise ValueError('Catalog capture requires its own idle connection or an admitted owned transaction')
    resources, observations, addresses = [], [], {}
    size, facts = 0, 0

    def account(value):
        nonlocal size, facts
        size += len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf8'))
        facts += 1
        if size > MAX_BYTES or facts > MAX_OBJECTS:
            raise ValueError('Native catalog exceeds the 20,000-fact / 8 MiB capture limit')

    def read(cursor, query, params=None):
        # Stream on the owning transaction instead of buffering an entire
        # server catalog in libpq before enforcing the application bounds.
        with ServerCursor(cursor.connection, 'scratchrobin_catalog', row_factory=tuple_row) as stream:
            stream.execute(query, params)
            while True:
                rows = stream.fetchmany(128)
                if not rows:
                    break
                yield from rows

    def group(cursor, name, operation):
        cursor.execute('SAVEPOINT catalog_group')
        try:
            count = operation()
        except errors.InsufficientPrivilege:
            cursor.execute('ROLLBACK TO SAVEPOINT catalog_group')
            observations.append({'section': name, 'available': False, 'sqlstate': '42501'})
        else:
            observations.append({'section': name, 'available': True, 'rows': count})
        # Other errors abort the whole capture. Do not mask them by attempting
        # RELEASE inside an already-aborted transaction; the caller rolls back.
        cursor.execute('RELEASE SAVEPOINT catalog_group')

    if not _in_transaction:
        connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
    try:
        with Cursor(connection, row_factory=tuple_row) as cursor:
            cursor.execute("SET LOCAL search_path = pg_catalog")
            cursor.execute("SET LOCAL standard_conforming_strings = on")
            cursor.execute("SET LOCAL statement_timeout = '15s'")
            cursor.execute("SET LOCAL lock_timeout = '2s'")
            cursor.execute('SELECT oid, datname, to_jsonb(d)::text FROM pg_catalog.pg_database d WHERE datname=current_database()')
            oid, database_name, metadata = cursor.fetchone()
            if oid != database_oid:
                raise ValueError('Selected database identity changed')
            root_id = f'postgresql:pg_database:{oid}'
            root = {'resource_id': root_id, 'resource_kind': 'database', 'display_name': database_name,
                    'display_path': [database_name], 'native': {'system_object': False, 'catalog': 'pg_database',
                    'oid': oid, 'catalog_row': json.loads(metadata)}}
            account(root)
            resources.append(root)
            addresses[('pg_database', oid)] = root
            specs = list(CATALOGS) + [(catalog, kind, 'c.' + name, 'NULL::text', '',
                'true' if include_system else 'c.oid >= 16384', 'c.oid', 'NULL::text')
                for catalog, kind, name in GLOBAL]
            for catalog, kind, name, namespace, joins, predicate, identity, definition in specs:
                where = predicate
                if namespace == 'NULL::text' and not include_system:
                    where += ' AND c.oid >= 16384'
                if catalog == 'pg_subscription':
                    where += f' AND c.subdbid = {database_oid}'
                if namespace != 'NULL::text' and not include_system:
                    where += f" AND {namespace} NOT IN ('pg_catalog','information_schema') AND {namespace} NOT LIKE 'pg_toast%%' AND {namespace} NOT LIKE 'pg_temp_%%'"
                native = 'to_jsonb(c)'
                if catalog == 'pg_proc':
                    native += " || jsonb_build_object('identity_arguments', pg_catalog.pg_get_function_identity_arguments(c.oid))"
                if catalog == 'pg_operator':
                    native += " || jsonb_build_object('left_type_identity', CASE WHEN c.oprleft=0 THEN NULL ELSE (pg_catalog.pg_identify_object('pg_catalog.pg_type'::regclass,c.oprleft,0)).identity END, 'right_type_identity', (pg_catalog.pg_identify_object('pg_catalog.pg_type'::regclass,c.oprright,0)).identity)"
                if catalog in {'pg_opclass', 'pg_opfamily'}:
                    method_column = 'opcmethod' if catalog == 'pg_opclass' else 'opfmethod'
                    native += f" || jsonb_build_object('index_method_name', (SELECT amname FROM pg_catalog.pg_am WHERE oid=c.{method_column}))"
                if catalog == 'pg_transform':
                    native += " || jsonb_build_object('language_name', l.lanname, 'data_type_identity', (SELECT pg_catalog.quote_ident(n.nspname) || '.' || pg_catalog.quote_ident(t.typname) FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace WHERE t.oid=c.trftype))"
                if catalog == 'pg_class':
                    native += " || jsonb_build_object('partition_bound_sql', pg_catalog.pg_get_expr(c.relpartbound,c.oid,false), 'partition_key_sql', CASE WHEN c.relkind='p' THEN pg_catalog.pg_get_partkeydef(c.oid) END)"
                if catalog == 'pg_policy':
                    native += " || jsonb_build_object('using_sql', pg_catalog.pg_get_expr(c.polqual,c.polrelid,false), 'check_sql', pg_catalog.pg_get_expr(c.polwithcheck,c.polrelid,false))"
                if catalog == 'pg_foreign_server':
                    native += " - 'srvoptions'"
                if catalog == 'pg_foreign_data_wrapper':
                    native += " - 'fdwoptions'"
                if catalog == 'pg_user_mapping':
                    native = "jsonb_build_object('oid',c.oid,'umuser',c.umuser,'umserver',c.umserver,'options_redacted',true)"
                if catalog == 'pg_subscription':
                    # Never SELECT c.* or to_jsonb(c): those require access to
                    # subconninfo, even if it is removed from the JSON later.
                    fields = ('oid', 'subdbid', 'subskiplsn', 'subname', 'subowner',
                        'subenabled', 'subbinary', 'substream', 'subtwophasestate',
                        'subdisableonerr', 'subpasswordrequired', 'subrunasowner',
                        'subfailover', 'subslotname', 'subsynccommit', 'subpublications', 'suborigin')
                    native = 'jsonb_build_object(' + ','.join(f"'{field}',c.{field}" for field in fields) + ", 'connection_redacted',true)"
                description = 'shobj_description' if catalog == 'pg_subscription' else 'obj_description'
                native_identity = f"(pg_catalog.pg_identify_object('pg_catalog.{catalog}'::regclass,c.oid,0)).identity"
                query = sql.SQL(f"SELECT {identity}, {name}, {namespace}, ({native})::text, {definition}, pg_catalog.{description}(c.oid, %s), {native_identity} FROM pg_catalog.{{}} c {joins} WHERE {where} ORDER BY c.oid").format(sql.Identifier(catalog))

                def objects():
                    pending = []
                    for objid, label, schema, data, ddl, comment, sql_identity in read(cursor, query, (catalog,)):
                        raw = json.loads(data)
                        system = schema in {'pg_catalog', 'information_schema'} or bool(schema and schema.startswith(('pg_toast', 'pg_temp_'))) if schema is not None else objid < 16384
                        native = {'catalog': catalog, 'oid': objid, 'subobject': 0, 'schema': schema,
                                  'system_object': system, 'catalog_row': raw, 'definition': ddl, 'comment': comment,
                                  'sql_identity': sql_identity,
                                  'navigator_parent_resource_id': root_id}
                        item = {'resource_id': f'postgresql:{catalog}:{objid}', 'resource_kind': kind,
                                'display_name': label, 'display_path': [database_name] + ([schema] if schema else []) + [label], 'native': native}
                        account(item)
                        pending.append(item)
                    for item in pending:
                        addresses[(catalog, item['native']['oid'])] = item
                    resources.extend(pending)
                    return len(pending)
                group(cursor, catalog, objects)

            for catalog, owner, parent, predicate in CHILDREN:
                ids = [objid for (cat, objid) in addresses if cat == parent]
                def children():
                    pending = []
                    projection = 'to_jsonb(c)'
                    if catalog == 'pg_attribute':
                        projection += " || jsonb_build_object('formatted_type', pg_catalog.format_type(c.atttypid,c.atttypmod), 'comment', pg_catalog.col_description(c.attrelid,c.attnum), 'default_expression', CASE WHEN c.attgenerated='' AND c.attidentity='' THEN (SELECT pg_catalog.pg_get_expr(d.adbin,d.adrelid,false) FROM pg_catalog.pg_attrdef d WHERE d.adrelid=c.attrelid AND d.adnum=c.attnum) ELSE NULL END)"
                    if catalog == 'pg_attrdef':
                        projection += " || jsonb_build_object('expression_sql', pg_catalog.pg_get_expr(c.adbin,c.adrelid,false))"
                    if catalog == 'pg_foreign_table':
                        projection += " - 'ftoptions'"
                    if catalog == 'pg_publication_rel':
                        projection += " || jsonb_build_object('row_filter_sql', pg_catalog.pg_get_expr(c.prqual,c.prrelid,false))"
                    ordering = {'pg_attribute': 'attnum', 'pg_attrdef': 'adnum', 'pg_enum': 'enumsortorder',
                                'pg_inherits': 'inhseqno', 'pg_ts_config_map': 'maptokentype, mapseqno',
                                'pg_amop': 'amopstrategy, amopopr', 'pg_amproc': 'amprocnum, amproc'}.get(catalog, f'({projection})::text')
                    # Some ownership columns (notably pg_aggregate.aggfnoid) are
                    # regproc, whose text output is a name rather than an OID.
                    query = sql.SQL(f'SELECT {{owner}}::oid, ({projection})::text FROM pg_catalog.{{catalog}} c WHERE {{owner}} = ANY(%s::oid[]) AND {predicate} ORDER BY {{owner}}, {ordering}').format(owner=sql.Identifier(owner), catalog=sql.Identifier(catalog))
                    for parent_oid, data in read(cursor, query, (ids,)):
                        value = json.loads(data)
                        account(value)
                        pending.append((parent_oid, value))
                    for parent_oid, value in pending:
                        addresses[(parent, parent_oid)]['native'].setdefault('children', {}).setdefault(catalog, []).append(value)
                    return len(pending)
                group(cursor, catalog, children)

            # Native dependency addresses include referenced system objects even
            # when those objects are intentionally omitted from the display.
            def dependencies():
                cursor.execute('SELECT oid, relname FROM pg_catalog.pg_class WHERE relnamespace = %s::regnamespace', ('pg_catalog',))
                catalogs = {name: oid for oid, name in cursor.fetchall()}
                keys = list(addresses)
                classids = [catalogs[cat] for cat, _ in keys]
                objids = [oid for _, oid in keys]
                query = '''SELECT c.relname, d.objid, to_jsonb(d)::text
                    FROM pg_catalog.pg_depend d JOIN pg_catalog.pg_class c ON c.oid=d.classid
                    JOIN unnest(%s::oid[],%s::oid[]) wanted(classid,objid)
                    ON wanted.classid=d.classid AND wanted.objid=d.objid
                    ORDER BY d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.refobjsubid,d.deptype'''
                pending = []
                for catalog, objid, data in read(cursor, query, (classids, objids)):
                    value = json.loads(data)
                    account(value)
                    pending.append((catalog, objid, value))
                for catalog, objid, value in pending:
                    addresses[(catalog, objid)]['native'].setdefault('dependencies', []).append(value)
                return len(pending)
            group(cursor, 'pg_depend', dependencies)
            def shared_dependencies():
                cursor.execute('SELECT oid, relname FROM pg_catalog.pg_class WHERE relnamespace = %s::regnamespace', ('pg_catalog',))
                catalogs = {name: oid for oid, name in cursor.fetchall()}
                keys = list(addresses)
                query = '''SELECT c.relname,d.objid,to_jsonb(d)::text
                    FROM pg_catalog.pg_shdepend d JOIN pg_catalog.pg_class c ON c.oid=d.classid
                    JOIN unnest(%s::oid[],%s::oid[]) wanted(classid,objid)
                    ON wanted.classid=d.classid AND wanted.objid=d.objid
                    WHERE d.dbid IN (0,%s)
                    ORDER BY d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.deptype'''
                pending = []
                for catalog, objid, data in read(cursor, query,
                        ([catalogs[cat] for cat, _ in keys], [oid for _, oid in keys], database_oid)):
                    value = json.loads(data)
                    account(value)
                    pending.append((catalog, objid, value))
                for catalog, objid, value in pending:
                    addresses[(catalog, objid)]['native'].setdefault('shared_dependencies', []).append(value)
                return len(pending)
            group(cursor, 'pg_shdepend', shared_dependencies)

            def security_labels(label_catalog):
                cursor.execute('SELECT oid, relname FROM pg_catalog.pg_class WHERE relnamespace = %s::regnamespace', ('pg_catalog',))
                catalogs = {name: oid for oid, name in cursor.fetchall()}
                keys = list(addresses)
                order = 'l.objsubid,' if label_catalog == 'pg_seclabel' else ''
                query = f'''SELECT c.relname,l.objoid,to_jsonb(l)::text
                    FROM pg_catalog.{label_catalog} l JOIN pg_catalog.pg_class c ON c.oid=l.classoid
                    JOIN unnest(%s::oid[],%s::oid[]) wanted(classid,objid)
                    ON wanted.classid=l.classoid AND wanted.objid=l.objoid
                    ORDER BY l.classoid,l.objoid,{order}l.provider'''
                pending = []
                for catalog, objid, data in read(cursor, query,
                        ([catalogs[cat] for cat, _ in keys], [oid for _, oid in keys])):
                    value = json.loads(data)
                    account(value)
                    pending.append((catalog, objid, value))
                for catalog, objid, value in pending:
                    addresses[(catalog, objid)]['native'].setdefault('security_labels', []).append(value)
                return len(pending)
            for label_catalog in ('pg_seclabel', 'pg_shseclabel'):
                group(cursor, label_catalog, lambda: security_labels(label_catalog))
            # Keep branch ownership native: indexes/triggers/constraints belong
            # to their relation, rather than being unrelated database siblings.
            for (catalog, objid), item in addresses.items():
                native = item['native']
                row = native['catalog_row']
                parent = None
                relation_field = {'pg_constraint': 'conrelid', 'pg_trigger': 'tgrelid',
                                  'pg_rewrite': 'ev_class', 'pg_policy': 'polrelid'}.get(catalog)
                if relation_field and row.get(relation_field):
                    parent = addresses.get(('pg_class', int(row[relation_field])))
                if catalog == 'pg_user_mapping':
                    parent = addresses.get(('pg_foreign_server', int(row['umserver'])))
                if catalog == 'pg_default_acl' and row.get('defaclnamespace'):
                    parent = addresses.get(('pg_namespace', int(row['defaclnamespace'])))
                if catalog == 'pg_class':
                    item['resource_kind'] = RELATION_KINDS.get(row['relkind'], 'relation')
                    indexes = native.get('children', {}).get('pg_index', [])
                    if indexes:
                        parent = addresses.get(('pg_class', int(indexes[0]['indrelid'])))
                if catalog == 'pg_type' and row.get('typtype') == 'd':
                    item['resource_kind'] = 'domain'
                if catalog == 'pg_proc':
                    item['resource_kind'] = ROUTINE_KINDS[row['prokind']]
                if parent is None and native.get('schema') and catalog != 'pg_namespace':
                    parent = next((obj for (cat, _oid), obj in addresses.items()
                        if cat == 'pg_namespace' and obj['display_name'] == native['schema']), None)
                if parent:
                    native['navigator_parent_resource_id'] = parent['resource_id']
            root['native'].update(catalog_observations=observations, catalog_warnings=list(EXCLUSIONS),
                                  isolation='repeatable-read/owned-write' if _in_transaction else 'repeatable-read/read-only', coverage_complete=False)
        if not _in_transaction:
            connection.execute('COMMIT')
    except BaseException:
        if not _in_transaction:
            connection.rollback()
        raise
    return {'resources': resources, 'generation': str(uuid.uuid4()), 'database_oid': oid,
            'database_name': database_name, 'observations': observations, 'complete': False}
