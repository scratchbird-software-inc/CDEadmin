"""Native relation continuity for reviewed table DROP.

The apply transaction takes the relation lock before re-reading its identity
and holds that lock through DROP and COMMIT. A name/SQL comparison alone is
not a relation identity check. No caller-owned transaction is used here.
"""
from collections.abc import Mapping
from psycopg import sql, Cursor
from psycopg.rows import dict_row, tuple_row

from .native_admin import _native_target


class IdentityConflict(ValueError):
    """The reviewed native target is unavailable; refresh and review again."""


def applies(request):
    return request.get('resource_kind') in {'table', 'partitioned-table'} and request.get('operation_id') == 'drop'


def target(request):
    native = _native_target(request); row = native.get('catalog_row') or {}
    oid = native.get('oid'); schema = native.get('schema'); name = native.get('name') or row.get('relname')
    kind = 'p' if request.get('resource_kind') == 'partitioned-table' else 'r'
    if (native.get('catalog') != 'pg_class' or type(oid) is not int or not 0 < oid < 2**32
            or any(not isinstance(value, str) or not value or '\x00' in value for value in (schema, name))
            or row.get('relkind', kind) != kind):
        raise IdentityConflict('Refresh the exact native table identity before reviewing DROP')
    parent = row.get('relnamespace')
    if parent is not None and (type(parent) is not int or not 0 < parent < 2**32):
        raise IdentityConflict('Refresh the native schema identity before reviewing DROP')
    return {'oid': oid, 'schema': schema, 'name': name, 'relkind': kind, 'schema_oid': parent}


CONTEXT = '''SELECT d.oid AS database_oid,d.datname AS database_name,
 pg_catalog.inet_server_addr()::text AS server_address,
 pg_catalog.inet_server_port() AS server_port,
 pg_catalog.pg_postmaster_start_time()::text AS postmaster_start,
 CURRENT_USER::text AS effective_principal,SESSION_USER::text AS authenticated_principal,
 pg_catalog.current_setting('role') AS active_role,
 CASE WHEN pg_catalog.has_function_privilege('pg_catalog.pg_control_system()', 'EXECUTE')
 THEN (SELECT system_identifier::text FROM pg_catalog.pg_control_system())
 ELSE NULL END AS system_identifier
 FROM pg_catalog.pg_database d WHERE d.datname=pg_catalog.current_database()'''
RELATION = '''SELECT c.oid,n.oid AS schema_oid,n.nspname AS schema,c.relname AS name,
 c.relkind::text AS relkind,c.xmin::text AS catalog_xmin
 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE c.oid=%s'''


def observe(connection, expected, database_id=None):
    with Cursor(connection, row_factory=dict_row) as cursor:
        cursor.execute(CONTEXT); context = cursor.fetchone()
        if context is None or database_id is not None and context['database_oid'] != database_id:
            raise IdentityConflict('The reviewed native database identity changed; refresh and review again')
        cursor.execute(RELATION, (expected['oid'],)); relation = cursor.fetchone()
    if relation is None or any(relation[key] != expected[key] for key in ('oid', 'schema', 'name', 'relkind')) or (
            expected['schema_oid'] is not None and relation['schema_oid'] != expected['schema_oid']):
        raise IdentityConflict('The native table was removed, replaced or moved; refresh and review DROP again')
    return {'target': expected, 'context': dict(context), 'relation': dict(relation)}


def lock_and_revalidate(connection, request, binding, database_id=None):
    expected = target(request)
    if not isinstance(binding, Mapping) or binding.get('target') != expected:
        raise IdentityConflict('The retained DROP identity is unavailable or changed; create a new review')
    # Reject an already stale target before any transient guard-view DDL.
    if observe(connection, expected, database_id) != binding:
        raise IdentityConflict('The native server, principal or table changed since review; refresh and review DROP again')
    from .namespace_guard import lock as lock_namespace
    lock_namespace(connection, expected['oid'], binding['relation']['schema_oid'], expected['schema'])
    with Cursor(connection, row_factory=tuple_row) as cursor:
        cursor.execute("SELECT pg_catalog.has_table_privilege(%s, 'UPDATE,DELETE,TRUNCATE')", (expected['oid'],))
        lock_privilege = cursor.fetchone()[0]
        if lock_privilege:
            cursor.execute(sql.SQL('LOCK TABLE ONLY {}.{} IN ACCESS EXCLUSIVE MODE NOWAIT').format(
                sql.Identifier(expected['schema']), sql.Identifier(expected['name'])))
        else:
            # Native owners can DROP even after revoking their own table
            # ACLs, and a table owner need not have CREATE on the namespace.
            # The helper has retained both namespace and relation catalog
            # tuples: competing rename/drop cannot commit a replacement.
            # DROP acquires the native relation lock itself, with bounded
            # waiting. No transient DDL or extra namespace rights are needed.
            cursor.execute("SET LOCAL lock_timeout = '1ms'")
    current = observe(connection, expected, database_id)
    if current != binding:
        raise IdentityConflict('The native server, principal or table changed since review; refresh and review DROP again')
    return current
