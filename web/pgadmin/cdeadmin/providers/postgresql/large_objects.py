"""Native PostgreSQL large-object operations; bounded chunks, exact offsets."""
import base64
import binascii
import hashlib
import re

OPERATIONS = frozenset({'inspect', 'create', 'read', 'write', 'truncate', 'alter', 'grant', 'revoke', 'drop'})
CHUNK_BYTES = 1024 * 1024
MAX_LENGTH = 4 * 1024 ** 4


def compile_operation(operation, native, draft):
    from .native_admin import PostgreSQLNativeAdminError, _identifier, _literal
    def refuse(message):
        raise PostgreSQLNativeAdminError(message)
    allowed = {
        'inspect': set(), 'create': {'oid', 'large_object_data_base64'},
        'read': {'offset', 'length'}, 'write': {'offset', 'large_object_data_base64'},
        'truncate': {'length', 'confirmation'}, 'alter': {'action', 'value'},
        'grant': {'role', 'privileges', 'grant_option'},
        'revoke': {'role', 'privileges', 'grant_option', 'cascade'}, 'drop': {'confirmation'},
    }
    if operation not in allowed or set(draft) - allowed[operation]:
        refuse('Unknown PostgreSQL large-object operation or option')
    def number(value, label, maximum, *, minimum=0):
        # Offsets and lengths cross the JavaScript exact integer boundary.
        if type(value) is int and abs(value) <= 2**53 - 1:
            value = str(value)
        if not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}', value) or not minimum <= int(value) <= maximum:
            refuse(label + ' requires exact bounded decimal text')
        return value
    oid = number(draft.get('oid', '0') if operation == 'create' else native.get('oid'),
        'Large-object OID', 2**32 - 1, minimum=0 if operation == 'create' else 1)
    if operation in {'create', 'write'}:
        encoded = draft.get('large_object_data_base64', '')
        if not isinstance(encoded, str) or len(encoded) > 4 * ((CHUNK_BYTES + 2) // 3):
            refuse('Large-object chunks are limited to 1 MiB')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            refuse('Large-object input must be canonical base64')
        if len(data) > CHUNK_BYTES or base64.b64encode(data).decode('ascii') != encoded:
            refuse('Large-object input must be canonical base64 within 1 MiB')
        binary = "pg_catalog.decode('" + data.hex() + "','hex')"
    if operation in {'read', 'write'}:
        offset = number(draft.get('offset', '0'), 'Large-object offset', MAX_LENGTH - 1)
    if operation == 'inspect':
        source = ('SELECT m.oid, pg_catalog.pg_get_userbyid(m.lomowner) AS owner, '
            'm.lomacl::text AS privileges, pg_catalog.obj_description(m.oid,\'pg_largeobject\') AS comment '
            'FROM pg_catalog.pg_largeobject_metadata m WHERE m.oid=' + oid + '::oid')
    elif operation == 'create':
        source = f'SELECT pg_catalog.lo_from_bytea({oid}::oid,{binary}) AS oid'
    elif operation == 'read':
        length = number(draft.get('length', str(CHUNK_BYTES)), 'Read length', CHUNK_BYTES, minimum=1)
        if int(offset) + int(length) > MAX_LENGTH:
            refuse('Large-object read exceeds the native 4 TiB address space')
        source = (f'WITH chunk AS MATERIALIZED (SELECT pg_catalog.lo_get({oid}::oid,{offset}::bigint,{length}::integer) AS data) '
            f'SELECT {oid}::oid AS oid,{offset}::bigint AS offset,pg_catalog.octet_length(data) AS byte_length,'
            "pg_catalog.replace(pg_catalog.encode(data,'base64'),E'\\n','') AS data_base64,"
            "pg_catalog.encode(pg_catalog.sha256(data),'hex') AS sha256 FROM chunk")
    elif operation == 'write':
        if int(offset) + len(data) > MAX_LENGTH:
            refuse('Large-object write exceeds the native 4 TiB address space')
        source = f'SELECT pg_catalog.lo_put({oid}::oid,{offset}::bigint,{binary}) AS native_result'
    elif operation == 'truncate':
        length = number(draft.get('length'), 'Truncate length', MAX_LENGTH)
        if draft.get('confirmation') != oid:
            refuse('Large-object truncate confirmation must match its OID')
        source = (f'WITH handle AS MATERIALIZED (SELECT pg_catalog.lo_open({oid}::oid,131072) AS fd), '
            f'changed AS MATERIALIZED (SELECT fd,pg_catalog.lo_truncate64(fd,{length}::bigint) AS native_result FROM handle) '
            f'SELECT {oid}::oid AS oid,native_result,pg_catalog.lo_close(fd) AS close_result FROM changed')
    elif operation == 'alter':
        if draft.get('action') == 'owner':
            source = 'ALTER LARGE OBJECT ' + oid + ' OWNER TO ' + _identifier(draft.get('value'), 'owner')
        elif draft.get('action') == 'comment':
            value = draft.get('value')
            if value is not None and (not isinstance(value, str) or len(value.encode('utf8')) > CHUNK_BYTES):
                refuse('Large-object comment must be bounded text or null')
            source = 'COMMENT ON LARGE OBJECT ' + oid + ' IS ' + ('NULL' if value in (None, '') else _literal(value, 'comment'))
        else:
            refuse('Select large-object owner or comment')
    elif operation in {'grant', 'revoke'}:
        privileges = draft.get('privileges')
        if (not isinstance(privileges, list) or not privileges or
                any(value not in ('SELECT', 'UPDATE') for value in privileges) or
                len(set(privileges)) != len(privileges)):
            refuse('Large-object privileges are distinct SELECT and/or UPDATE')
        grant_option = draft.get('grant_option', False)
        cascade = draft.get('cascade', False)
        if type(grant_option) is not bool or type(cascade) is not bool:
            refuse('Large-object privilege options must be boolean')
        role = 'PUBLIC' if draft.get('role') == 'PUBLIC' else _identifier(draft.get('role'), 'role')
        source = (operation.upper() + (' GRANT OPTION FOR ' if operation == 'revoke' and grant_option else ' ') +
            ', '.join(privileges) + ' ON LARGE OBJECT ' + oid + (' TO ' if operation == 'grant' else ' FROM ') + role)
        source += (' WITH GRANT OPTION' if grant_option else '') if operation == 'grant' else (' CASCADE' if cascade else ' RESTRICT')
    else:
        if draft.get('confirmation') != oid:
            refuse('Large-object drop confirmation must match its OID')
        source = f'SELECT pg_catalog.lo_unlink({oid}::oid) AS native_result'
    result = {'statement': source, 'read_only': operation in {'inspect', 'read'},
        'returns_rows': operation not in {'alter', 'grant', 'revoke'}}
    if operation == 'write':
        # Large-object pages use the command snapshot. A separate native
        # statement observes the new command ID; a CTE in the write statement
        # can still see the preceding page version.
        result.update(post_statement=f'SELECT {oid}::oid AS oid,{offset}::bigint AS offset,'
            f"pg_catalog.encode(pg_catalog.sha256(pg_catalog.lo_get({oid}::oid,{offset}::bigint,{len(data)})),'hex') AS observed_sha256",
            expected_sha256=hashlib.sha256(data).hexdigest())
    return result


def form(operation, field):
    fields = []
    if operation == 'create':
        fields.append(field('oid', 'OID (0 allocates a native identity)', default='0'))
    if operation in {'create', 'write'}:
        fields.append(field('large_object_data_base64', 'Binary chunk', 'multiline',
            default='', max_length=4 * ((CHUNK_BYTES + 2) // 3),
            help='Load a file chunk or enter canonical base64. Maximum 1 MiB per reviewed chunk.'))
    if operation in {'read', 'write'}:
        fields.append(field('offset', 'Byte offset (exact decimal)', default='0'))
    if operation in {'read', 'truncate'}:
        fields.append(field('length', 'Byte length (exact decimal)', required=True,
            default=str(CHUNK_BYTES) if operation == 'read' else '0'))
    if operation == 'alter':
        fields.extend([field('action', 'Change', 'select', required=True,
            options=[{'value': value, 'label': value.title()} for value in ('owner', 'comment')]),
            field('value', 'Owner or comment', 'multiline')])
    if operation in {'grant', 'revoke'}:
        fields.extend([field('role', 'Role', required=True),
            field('privileges', 'Privileges', 'multiselect', required=True,
                options=[{'value': value, 'label': value} for value in ('SELECT', 'UPDATE')]),
            field('grant_option', 'With grant option' if operation == 'grant' else 'Revoke grant option only', 'boolean')])
        if operation == 'revoke':
            fields.append(field('cascade', 'Revoke dependent grants', 'boolean'))
    if operation in {'truncate', 'drop'}:
        fields.append(field('confirmation', 'Type the large-object OID to confirm', required=True))
    return {'form_id': 'postgresql-large-object-' + operation,
        'form_key': 'native:postgresql:database:large-object',
        'title': operation.title() + ' large object', 'fields': fields}
