"""Explicit source-context refresh; passive completion remains command-free."""
from ...sdk import RelationalClientError
from .mariadb_catalog import identifier

QUERY = (
    'SELECT @@server_uid,CURRENT_USER(),VERSION(),CONNECTION_ID(),DATABASE(),'
    '@@sql_mode,@@character_set_client,CURRENT_ROLE(),@@character_set_connection,'
    '@@character_set_results,@@collation_connection,@@lower_case_table_names,'
    "(SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_TYPE='TEMPORARY')"
)
FIELDS = (
    'server_uid', 'principal', 'version', 'connection_id', 'default_schema', 'sql_mode',
    'character_set_client', 'active_role', 'character_set_connection',
    'character_set_results', 'collation_connection', 'lower_case_table_names',
    'temporary_table_count',
)
MAX_TEMPORARY_TABLES = 128
TEMPORARY_TABLES_SQL = (
    'SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE, TABLE_COLLATION, TABLE_COMMENT '
    "FROM information_schema.TABLES WHERE TABLE_TYPE='TEMPORARY' "
    f'ORDER BY TABLE_SCHEMA, TABLE_NAME LIMIT {MAX_TEMPORARY_TABLES + 1}'
)


def observe(client, handle, *, include_temporary=False):
    entry = client._completion_identities.get(id(handle))
    if entry is None or entry[0] is not handle:
        raise RelationalClientError('Original MariaDB identity is unavailable')
    cursor = handle.cursor()
    commands_sent = 0
    try:
        cursor.execute(QUERY)
        commands_sent += 1
        row = cursor.fetchone()
        if not row or len(row) != len(FIELDS) or tuple(row[:4]) != entry[1]:
            raise RelationalClientError('Original MariaDB context identity changed')
        observed = dict(zip(FIELDS, row))
        observed['lower_case_table_names'] = int(observed.get('lower_case_table_names') or 0)
        temp_count = int(observed.get('temporary_table_count') or 0)
        observed['temporary_table_count'] = temp_count
        if temp_count > 0 and isinstance(getattr(client, '_temporary_session_handles', None), set):
            client._temporary_session_handles.add(id(handle))
        if not include_temporary:
            observed['original_session_commands_sent'] = commands_sent
            return observed

        temporary_tables = []
        enumeration_complete = True
        if temp_count > 0:
            cursor.execute(TEMPORARY_TABLES_SQL)
            commands_sent += 1
            rows = cursor.fetchall()
            if len(rows) > MAX_TEMPORARY_TABLES:
                enumeration_complete = False
                rows = rows[:MAX_TEMPORARY_TABLES]
            for db_name, tbl_name, engine_name, collation, comment in rows:
                qualified = f'{identifier(str(db_name))}.{identifier(str(tbl_name))}'
                cursor.execute(f'SHOW FULL COLUMNS FROM {qualified}')
                commands_sent += 1
                cols = []
                for col_row in cursor.fetchall():
                    extra = str(col_row[6] or '')
                    cols.append({
                        'name': str(col_row[0]),
                        'column_type': str(col_row[1] or ''),
                        'collation': col_row[2],
                        'nullable': str(col_row[3] or '').upper() == 'YES',
                        'key': str(col_row[4] or ''),
                        'default': col_row[5],
                        'extra': extra,
                        'comment': str(col_row[8] or '') if len(col_row) > 8 else '',
                        'hidden_from_star': 'INVISIBLE' in extra.upper().split(),
                    })
                temporary_tables.append({
                    'database': str(db_name),
                    'name': str(tbl_name),
                    'engine': engine_name,
                    'collation': collation,
                    'comment': comment,
                    'columns': cols,
                })
        observed['temporary_tables'] = temporary_tables
        observed['temporary_enumeration_complete'] = enumeration_complete
        observed['original_session_commands_sent'] = commands_sent
        return observed
    finally:
        cursor.close()


def apply_to_peer(peer, context):
    """Set only the separately owned observation connection's native context."""
    cursor = peer.cursor()
    try:
        for field in (
            'sql_mode', 'character_set_client', 'character_set_connection',
            'character_set_results', 'collation_connection',
        ):
            cursor.execute('SET SESSION ' + field + '=?', (context[field],))
        role = context['active_role']
        if role is None:
            cursor.execute('SET ROLE NONE')
        elif isinstance(role, str) and role and '\x00' not in role:
            cursor.execute('SET ROLE `' + role.replace('`', '``') + '`')
        else:
            raise RelationalClientError('Native active role is unrecognized')
    finally:
        cursor.close()
