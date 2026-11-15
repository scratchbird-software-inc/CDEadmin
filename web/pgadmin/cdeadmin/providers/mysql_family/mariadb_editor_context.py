"""Explicit source-context refresh; passive completion remains command-free."""
from ...sdk import RelationalClientError

QUERY=('SELECT @@server_uid,CURRENT_USER(),VERSION(),CONNECTION_ID(),DATABASE(),'
       '@@sql_mode,@@character_set_client,CURRENT_ROLE(),@@character_set_connection,'
       '@@character_set_results,@@collation_connection')
FIELDS=('server_uid','principal','version','connection_id','default_schema','sql_mode',
        'character_set_client','active_role','character_set_connection',
        'character_set_results','collation_connection')


def observe(client,handle):
    entry=client._completion_identities.get(id(handle))
    if entry is None or entry[0] is not handle:
        raise RelationalClientError('Original MariaDB identity is unavailable')
    cursor=handle.cursor()
    try:
        cursor.execute(QUERY);row=cursor.fetchone()
        if not row or len(row)!=len(FIELDS) or tuple(row[:4])!=entry[1]:
            raise RelationalClientError('Original MariaDB context identity changed')
        return dict(zip(FIELDS,row))
    finally:cursor.close()


def apply_to_peer(peer,context):
    """Set only the separately owned observation connection's native context."""
    cursor=peer.cursor()
    try:
        for field in ('sql_mode','character_set_client','character_set_connection',
                      'character_set_results','collation_connection'):
            cursor.execute('SET SESSION '+field+'=?',(context[field],))
        role=context['active_role']
        if role is None:cursor.execute('SET ROLE NONE')
        elif isinstance(role,str) and role and '\x00' not in role:
            cursor.execute('SET ROLE `'+role.replace('`','``')+'`')
        else:raise RelationalClientError('Native active role is unrecognized')
    finally:cursor.close()
