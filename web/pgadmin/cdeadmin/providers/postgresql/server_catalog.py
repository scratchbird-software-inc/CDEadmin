"""Credential-free native server inventory; database captures remain separate."""
import json
import uuid
from psycopg import Cursor, ServerCursor, errors
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
    ('tablespaces', 'tablespace', 'pg_tablespace', '''SELECT oid::text, spcname,
        jsonb_build_object('oid',oid,'spcname',spcname,'spcowner',spcowner,'spcacl',spcacl,
          'comment',pg_catalog.shobj_description(oid,'pg_tablespace'),'options_redacted',true)::text
        FROM pg_catalog.pg_tablespace ORDER BY oid'''),
    ('replication-slots', 'replication-slot', 'pg_replication_slots',
        'SELECT slot_name, slot_name, to_jsonb(s)::text FROM pg_catalog.pg_replication_slots s WHERE NOT temporary ORDER BY slot_name'),
    ('replication-origins', 'replication-origin', 'pg_replication_origin',
        'SELECT roident::text, roname, to_jsonb(o)::text FROM pg_catalog.pg_replication_origin o ORDER BY roident'),
    ('database-role-settings', 'database-role-settings', 'pg_db_role_setting', '''SELECT
        setdatabase::text || ':' || setrole::text, setdatabase::text || ' / ' || setrole::text,
        jsonb_build_object('setdatabase',setdatabase,'setrole',setrole,'values_redacted',true,
          'setting_names',ARRAY(SELECT split_part(value,'=',1) FROM unnest(setconfig) value))::text
        FROM pg_catalog.pg_db_role_setting ORDER BY setdatabase,setrole'''),
)


INSTANCE_SQL = """SELECT pg_catalog.inet_server_addr()::pg_catalog.text, pg_catalog.inet_server_port()::pg_catalog.text,
    extract(epoch FROM pg_catalog.pg_postmaster_start_time())::pg_catalog.text,
    pg_catalog.current_setting('server_version_num')"""


def _instance(connection):
    with Cursor(connection, row_factory=tuple_row) as cursor:
        cursor.execute(INSTANCE_SQL)
        return list(cursor.fetchone())


def inventory(provider, route):
    provider.permissions.require('data_read', 'resource')
    opened = provider.open_session({'route': {key: value for key, value in route.items() if key != 'database_id'}})
    objects, observations, databases = [], [], []
    size = 0
    try:
        state = provider._sessions[opened['session_id']]
        with state.lock:
            provider._ensure_native_connection(state)
            connection = state.connection.conn
            if int(connection.info.transaction_status) != 0:
                raise ValueError('Server inventory requires an independent idle attachment')
            instance = _instance(connection)
            connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            try:
                with Cursor(connection, row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL search_path = pg_catalog")
                    cursor.execute("SET LOCAL statement_timeout = '15s'")
                    cursor.execute("SET LOCAL lock_timeout = '2s'")
                    cursor.execute('''SELECT oid,datname,datallowconn,datistemplate,
                        has_database_privilege(current_user,oid,'CONNECT')
                        FROM pg_catalog.pg_database ORDER BY oid LIMIT %s''', (MAX_DATABASES + 1,))
                    rows = cursor.fetchall()
                    if len(rows) > MAX_DATABASES:
                        raise ValueError('Server inventory exceeds 1,000 databases; use explicit database captures')
                    databases = [{'oid': oid, 'name': name, 'allows_connections': allowed,
                        'template': template, 'connect_privilege': permitted} for oid, name, allowed, template, permitted in rows]
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
                                        pending.append({'resource_id': f'postgresql:{catalog}:{identity}', 'resource_kind': kind,
                                            'display_name': name, 'display_path': [str(route['server_id']), section, name],
                                            'native': {'catalog': catalog, 'native_identity': identity, 'catalog_row': native,
                                                       'system_object': bool(catalog in {'pg_authid', 'pg_auth_members', 'pg_tablespace'} and int(identity) < 16384)}})
                        except errors.InsufficientPrivilege:
                            cursor.execute('ROLLBACK TO SAVEPOINT server_section')
                            observations.append({'section': section, 'available': False, 'sqlstate': '42501'})
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
            'generation': str(uuid.uuid4()), 'complete': False, 'warnings': [
                'Server and individual database snapshots are independent, not a consistent cluster backup.',
                'Role passwords, role/database-setting values and tablespace options are excluded.',
                'Slot positions are observations, not restorable replication checkpoints.']}


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
    root = {'resource_id': f'postgresql:server:{route["server_id"]}', 'resource_kind': 'server',
        'display_name': str(route['server_id']), 'display_path': [str(route['server_id'])],
        'native': {'system_object': False, 'instance_observation': server.get('instance_observation'), 'catalog_observations': server['observations'], 'catalog_warnings': server['warnings']}}
    server['document'] = build_export([root, *server['resources']], endpoint_id=endpoint_id,
        target_id=f'postgresql-server:{route["server_id"]}', generation=server['generation'], engine='postgresql',
        include_system=include_system)
    return {'format': 'scratchrobin.postgresql.server-catalog@1', 'endpoint_id': endpoint_id,
            'server': server, 'databases': results, 'complete': False,
            'all_selected_captured': all(item['available'] for item in results)}
