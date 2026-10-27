"""Credential-free native server inventory; database captures remain separate."""
import json
import uuid
from psycopg import Cursor, ServerCursor, Error as PostgreSQLError
from psycopg.rows import tuple_row
from .catalog_capture import capture
from ...workspace.firebird_catalog_export import build_export

MAX_DATABASES = 1000
MAX_BATCH = 32
MAX_FACTS = 20000
MAX_BYTES = 8 * 1024 * 1024

# Deliberate projections: never select pg_authid password hashes, rolconfig
# values, tablespace options or arbitrary role/database-setting values.
SECTIONS = (
    ('roles', 'role', 'pg_authid', '''SELECT oid::text, rolname,
        jsonb_build_object('oid',oid,'rolname',rolname,'rolsuper',rolsuper,
          'rolinherit',rolinherit,'rolcreaterole',rolcreaterole,'rolcreatedb',rolcreatedb,
          'rolcanlogin',rolcanlogin,'rolreplication',rolreplication,'rolconnlimit',rolconnlimit,
          'rolvaliduntil',rolvaliduntil,'rolbypassrls',rolbypassrls,
          'comment',pg_catalog.shobj_description(oid,'pg_authid'))::text
        FROM pg_catalog.pg_roles ORDER BY oid'''),
    ('memberships', 'role-membership', 'pg_auth_members',
        'SELECT oid::text, oid::text, to_jsonb(m)::text FROM pg_catalog.pg_auth_members m ORDER BY oid'),
    ('role-authentication-state', 'role-authentication-state', 'pg_authid', '''SELECT oid::text,rolname,
        jsonb_build_object('oid',oid,'password_present',rolpassword IS NOT NULL,'password_redacted',true)::text
        FROM pg_catalog.pg_authid ORDER BY oid'''),
    ('tablespaces', 'tablespace', 'pg_tablespace', '''SELECT oid::text, spcname,
        jsonb_build_object('oid',oid,'spcname',spcname,'spcowner',spcowner,'spcacl',spcacl,
          'comment',pg_catalog.shobj_description(oid,'pg_tablespace'),'options_redacted',true,
          'option_names',ARRAY(SELECT split_part(value,'=',1) FROM unnest(spcoptions) value),
          'numeric_options',ARRAY(SELECT value FROM unnest(spcoptions) value
              WHERE split_part(value,'=',1) IN ('seq_page_cost','random_page_cost','effective_io_concurrency','maintenance_io_concurrency')
                AND split_part(value,'=',2) ~ '^[0-9]+([.][0-9]+)?$'),
          'location_available',pg_catalog.has_function_privilege(current_user,'pg_catalog.pg_tablespace_location(oid)','EXECUTE'),
          'location',CASE WHEN pg_catalog.has_function_privilege(current_user,'pg_catalog.pg_tablespace_location(oid)','EXECUTE')
              THEN pg_catalog.pg_tablespace_location(oid) ELSE NULL END)::text
        FROM pg_catalog.pg_tablespace ORDER BY oid'''),
    ('replication-slots', 'replication-slot', 'pg_replication_slots',
        "SELECT slot_name, slot_name, (to_jsonb(s) || jsonb_build_object('safe_wal_size',safe_wal_size::text))::text FROM pg_catalog.pg_replication_slots s ORDER BY slot_name"),
    ('replication-origins', 'replication-origin', 'pg_replication_origin',
        'SELECT roident::text, roname, to_jsonb(o)::text FROM pg_catalog.pg_replication_origin o ORDER BY roident'),
    ('database-role-settings', 'database-role-settings', 'pg_db_role_setting', '''SELECT
        setdatabase::text || ':' || setrole::text, setdatabase::text || ' / ' || setrole::text,
        jsonb_build_object('setdatabase',setdatabase,'setrole',setrole,'values_redacted',true,
          'setting_names',ARRAY(SELECT split_part(value,'=',1) FROM unnest(setconfig) value))::text
        FROM pg_catalog.pg_db_role_setting ORDER BY setdatabase,setrole'''),
    ('cluster-control', 'cluster-control', 'pg_control_system', '''SELECT 'cluster','Cluster identity',
        jsonb_build_object('system_identifier',system_identifier::text,
            'pg_control_version',pg_control_version,'catalog_version_no',catalog_version_no,
            'pg_control_last_modified',pg_control_last_modified)::text FROM pg_catalog.pg_control_system()'''),
    ('configuration', 'system-variable', 'pg_settings', '''SELECT name,name,
        ((to_jsonb(s)-'setting'-'boot_val'-'reset_val') || jsonb_build_object(
            'setting',CASE WHEN vartype IN ('bool','integer','real','enum') AND position('.' in name)=0 THEN setting ELSE NULL END,
            'boot_val',CASE WHEN vartype IN ('bool','integer','real','enum') AND position('.' in name)=0 THEN boot_val ELSE NULL END,
            'reset_val',CASE WHEN vartype IN ('bool','integer','real','enum') AND position('.' in name)=0 THEN reset_val ELSE NULL END,
            'values_redacted',NOT(vartype IN ('bool','integer','real','enum') AND position('.' in name)=0)))::text
        FROM pg_catalog.pg_settings s ORDER BY name'''),
    ('configuration-files', 'configuration-entry', 'pg_file_settings', '''SELECT
        jsonb_build_array(sourcefile,sourceline,seqno)::text,sourcefile || ':' || sourceline::text,
        jsonb_build_object('sourcefile',sourcefile,'sourceline',sourceline,'seqno',seqno,
            'name',name,'applied',applied,'setting_present',setting IS NOT NULL,
            'error_present',error IS NOT NULL,'setting_redacted',true,'error_redacted',true)::text
        FROM pg_catalog.pg_file_settings ORDER BY seqno'''),
    ('authentication-rules', 'authentication-rule', 'pg_hba_file_rules', '''SELECT
        jsonb_build_array(file_name,line_number,rule_number)::text,
        file_name || ':' || line_number::text,
        ((to_jsonb(r)-'options'-'error') || jsonb_build_object('options_redacted',true,
            'option_names',ARRAY(SELECT split_part(value,'=',1) FROM unnest(options) value),
            'error_present',error IS NOT NULL,'error_redacted',true))::text
        FROM pg_catalog.pg_hba_file_rules r ORDER BY rule_number NULLS LAST,file_name,line_number'''),
    ('identity-mappings', 'identity-mapping', 'pg_ident_file_mappings', '''SELECT
        jsonb_build_array(file_name,line_number,map_number)::text,
        file_name || ':' || line_number::text,
        ((to_jsonb(m)-'error') || jsonb_build_object('error_present',error IS NOT NULL,'error_redacted',true))::text
        FROM pg_catalog.pg_ident_file_mappings m ORDER BY map_number NULLS LAST,file_name,line_number'''),
    ('available-extensions', 'available-extension', 'pg_available_extensions',
        'SELECT name,name,to_jsonb(e)::text FROM pg_catalog.pg_available_extensions e ORDER BY name'),
    ('extension-versions', 'extension-version', 'pg_available_extension_versions', '''SELECT
        jsonb_build_array(name,version)::text,name || ' / ' || version,to_jsonb(e)::text
        FROM pg_catalog.pg_available_extension_versions e ORDER BY name,version'''),
    ('prepared-transactions', 'prepared-transaction', 'pg_prepared_xacts',
        'SELECT gid,gid,to_jsonb(x)::text FROM pg_catalog.pg_prepared_xacts x ORDER BY gid'),
    ('replication-origin-state', 'replication-origin-state', 'pg_replication_origin_status', '''SELECT
        local_id::text,external_id,to_jsonb(s)::text FROM pg_catalog.pg_replication_origin_status s ORDER BY local_id'''),
    ('replication-workers', 'replication-worker', 'pg_stat_replication', '''SELECT
        pid::text,pid::text,to_jsonb(s)::text FROM pg_catalog.pg_stat_replication s ORDER BY pid'''),
    ('wal-receiver', 'wal-receiver', 'pg_stat_wal_receiver', '''SELECT pid::text,pid::text,
        ((to_jsonb(s)-'conninfo') || jsonb_build_object('connection_present',conninfo IS NOT NULL,'connection_redacted',true))::text
        FROM pg_catalog.pg_stat_wal_receiver s ORDER BY pid'''),
    ('sessions', 'session', 'pg_stat_activity', '''SELECT
        jsonb_build_array(pid,backend_start)::text,pid::text,
        ((to_jsonb(s)-'query') || jsonb_build_object('query_present',query IS NOT NULL,'query_redacted',true,'query_id',query_id::text))::text
        FROM pg_catalog.pg_stat_activity s ORDER BY pid'''),
    ('tls-sessions', 'tls-session', 'pg_stat_ssl',
        "SELECT pid::text,pid::text,(to_jsonb(s) || jsonb_build_object('client_serial',client_serial::text))::text FROM pg_catalog.pg_stat_ssl s ORDER BY pid"),
    ('gssapi-sessions', 'gssapi-session', 'pg_stat_gssapi',
        'SELECT pid::text,pid::text,to_jsonb(s)::text FROM pg_catalog.pg_stat_gssapi s ORDER BY pid'),
)


INSTANCE_SQL = """SELECT pg_catalog.inet_server_addr()::pg_catalog.text, pg_catalog.inet_server_port()::pg_catalog.text,
    extract(epoch FROM pg_catalog.pg_postmaster_start_time())::pg_catalog.text,
    pg_catalog.current_setting('server_version_num')"""

VALUE_ENCODINGS = {
    'pg_control_system': {'system_identifier':'uint64-decimal-text'},
    'pg_stat_activity': {'query_id':'int64-decimal-text'},
    'pg_replication_slots': {'safe_wal_size':'int64-decimal-text'},
    'pg_stat_ssl': {'client_serial':'numeric-decimal-text'},
}


def _instance(connection):
    with Cursor(connection, row_factory=tuple_row) as cursor:
        cursor.execute(INSTANCE_SQL)
        return list(cursor.fetchone())


def inventory(provider, route):
    provider.permissions.require('data_read', 'resource')
    opened = provider.open_session({'route': {key: value for key, value in route.items() if key != 'database_id'}})
    objects, observations, databases = [], [], []
    size = 0
    visibility = {}
    try:
        state = provider._sessions[opened['session_id']]
        with state.lock:
            provider._ensure_native_connection(state)
            connection = state.connection.conn
            if int(connection.info.transaction_status) != 0:
                raise ValueError('Server inventory requires an independent idle attachment')
            instance = _instance(connection)
            if instance[3] != '180003':
                raise ValueError('Server inventory requires native PostgreSQL 18.3')
            connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            try:
                with Cursor(connection, row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL search_path = pg_catalog")
                    cursor.execute("SET LOCAL statement_timeout = '15s'")
                    cursor.execute("SET LOCAL lock_timeout = '2s'")
                    cursor.execute("SELECT current_user,session_user,rolsuper,"
                        "pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE'),"
                        "pg_catalog.pg_has_role(current_user,'pg_read_all_settings','USAGE') "
                        "FROM pg_catalog.pg_roles WHERE rolname=current_user")
                    principal, session_principal, superuser, all_stats, all_settings = cursor.fetchone()
                    visibility = {'principal':principal,'session_principal':session_principal,
                        'superuser':superuser,'read_all_stats':all_stats,'read_all_settings':all_settings,
                        'native_field_filters_apply':not(superuser or all_stats and all_settings)}
                    cursor.execute('''SELECT oid,datname,datallowconn,datistemplate,
                        has_database_privilege(current_user,oid,'CONNECT'),to_jsonb(d)::text
                        FROM pg_catalog.pg_database d ORDER BY oid LIMIT %s''', (MAX_DATABASES + 1,))
                    rows = cursor.fetchall()
                    if len(rows) > MAX_DATABASES:
                        raise ValueError('Server inventory exceeds 1,000 databases; use explicit database captures')
                    databases = [{'oid': oid, 'name': name, 'allows_connections': allowed,
                        'template': template, 'connect_privilege': permitted} for oid, name, allowed, template, permitted, _native in rows]
                    for oid, name, _allowed, _template, _permitted, encoded in rows:
                        size += len(encoded.encode('utf8'))
                        objects.append({'resource_id': f'postgresql:pg_database:{oid}', 'resource_kind': 'database',
                            'display_name': name, 'display_path': [str(route['server_id']), 'databases', name],
                            'native': {'catalog': 'pg_database', 'native_identity': str(oid),
                                'catalog_row': json.loads(encoded), 'system_object': int(oid) < 16384}})
                    observations.append({'section': 'databases', 'available': True, 'rows': len(databases)})
                    for section, kind, catalog, query in SECTIONS:
                        cursor.execute('SAVEPOINT server_section')
                        pending = []
                        try:
                            with ServerCursor(connection, 'scratchrobin_server_inventory', row_factory=tuple_row) as stream:
                                stream.execute(query)
                                while True:
                                    batch = stream.fetchmany(128)
                                    if not batch:break
                                    for identity, name, encoded in batch:
                                        native = json.loads(encoded)
                                        size += len(encoded.encode('utf8'))
                                        if size > MAX_BYTES or len(objects) + len(pending) >= MAX_FACTS:
                                            raise ValueError('Server metadata exceeds 20,000 facts or 8 MiB')
                                        pending.append({'resource_id': f'postgresql:{catalog}:{identity}' +
                                            (':authentication-state' if section == 'role-authentication-state' else ''), 'resource_kind': kind,
                                            'display_name': name, 'display_path': [str(route['server_id']), section, name],
                                            'native': {'catalog': catalog, 'native_identity': identity, 'catalog_row': native,
                                                       **({'navigator_parent_resource_id':f'postgresql:pg_authid:{identity}',
                                                           'projection':'authentication-state'} if section == 'role-authentication-state' else {}),
                                                       **({'value_encodings':VALUE_ENCODINGS[catalog]} if catalog in VALUE_ENCODINGS else {}),
                                                       'system_object': bool(catalog in {'pg_authid', 'pg_auth_members', 'pg_tablespace'} and int(identity) < 16384)}})
                        except PostgreSQLError as error:
                            cursor.execute('ROLLBACK TO SAVEPOINT server_section')
                            observations.append({'section': section, 'available': False, 'sqlstate': error.sqlstate,
                                'category': {'42501':'permission_denied','57014':'timeout',
                                    '0A000':'feature_unavailable','58P01':'resource_unavailable'}.get(error.sqlstate,'query_failed')})
                        else:
                            objects.extend(pending)
                            observations.append({'section': section, 'available': True, 'rows': len(pending)})
                        cursor.execute('RELEASE SAVEPOINT server_section')
                connection.execute('COMMIT')
            except BaseException:
                connection.rollback()
                raise
    finally:
        provider.close_session(opened)
    return {'instance_observation': instance, 'databases': databases, 'resources': objects, 'observations': observations,
            'visibility':visibility,
            'coverage': {'state': 'partial' if any(not item['available'] for item in observations) else 'observed',
                'unavailable_sections': [item['section'] for item in observations if not item['available']],
                'scope': 'Shared catalogs, configuration, authentication, installed capabilities and live native state'},
            'generation': str(uuid.uuid4()), 'complete': False, 'warnings': [
                'Server and individual database snapshots are independent, not a consistent cluster backup.',
                'Role passwords, role/database-setting values and tablespace options are excluded.',
                'String/custom configuration values, authentication options, connection strings and session query text are redacted.',
                'Slots, workers, sessions, TLS/GSSAPI state and prepared transactions are live observations; they are not recovery checkpoints.',
                'Available extension versions describe this installed server; they do not establish native operation or language support.']}


def export_inventory(server, endpoint_id, server_id, *, include_system=False):
    """Render the observed server without requiring any database expansion."""
    root = {'resource_id': f'postgresql:server:{server_id}', 'resource_kind': 'server',
        'display_name': str(server_id), 'display_path': [str(server_id)],
        'native': {'system_object': False, 'instance_observation': server.get('instance_observation'),
            'visibility':server.get('visibility'),
            'catalog_observations': server['observations'], 'catalog_warnings': server['warnings'],
            'coverage_complete': False, 'coverage': server.get('coverage')}}
    return build_export([root, *server['resources']], endpoint_id=endpoint_id,
        target_id=f'postgresql-server:{server_id}', generation=server['generation'],
        engine='postgresql', include_system=include_system)


def bundle(provider, route, endpoint_id, database_ids, *, include_system=False):
    if (not isinstance(database_ids, list) or not 1 <= len(database_ids) <= MAX_BATCH or
            any(type(oid) is not int or not 1 <= oid <= 4294967295 for oid in database_ids) or
            len(set(database_ids)) != len(database_ids) or type(include_system) is not bool):
        raise ValueError('Select 1–32 distinct native database OIDs and a boolean system-object policy')
    server = inventory(provider, route)
    known = {row['oid']: row for row in server['databases']}
    results = []
    size = 0
    for oid in database_ids:
        selected = known.get(oid)
        if selected is None or not selected['allows_connections'] or not selected['connect_privilege']:
            results.append({'database_oid': oid, 'available': False, 'reason': 'Database unavailable or CONNECT not admitted'})
            continue
        opened = None
        try:
            selected_route = {**route, 'database_id': oid}
            opened = provider.open_session({'route': selected_route}, _resolved_database=selected['name'])
            state = provider._sessions[opened['session_id']]
            with state.lock:
                provider._ensure_native_connection(state)
                if _instance(state.connection.conn) != server['instance_observation']:
                    raise ValueError('Server address or postmaster epoch changed during capture')
                captured = capture(state.connection.conn, oid, include_system=include_system)
            document = build_export(captured['resources'], endpoint_id=endpoint_id,
                target_id=f'postgresql-database:{oid}', generation=captured['generation'],
                engine='postgresql', include_system=include_system)
            size += len(json.dumps(document, ensure_ascii=False).encode('utf8'))
            if size > 32 * 1024 * 1024:
                raise ValueError('Server bundle exceeds 32 MiB; select fewer databases')
            results.append({'database_oid': oid, 'database_name': selected['name'], 'available': True, 'document': document})
        except Exception as error:
            results.append({'database_oid': oid, 'database_name': selected['name'], 'available': False,
                'error_type': type(error).__name__, 'reason': str(error)[:2048] if isinstance(error, ValueError) else 'Native capture failed; no substitute database was used'})
        finally:
            if opened is not None:provider.close_session(opened)
    server['document'] = export_inventory(server, endpoint_id, route['server_id'], include_system=include_system)
    return {'format': 'scratchrobin.postgresql.server-catalog@1', 'endpoint_id': endpoint_id,
            'server': server, 'databases': results, 'complete': False,
            'all_selected_captured': all(item['available'] for item in results)}
