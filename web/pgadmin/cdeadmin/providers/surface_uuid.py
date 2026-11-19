"""Opt-in native, byte-order-preserving UUID field conversions."""
import base64
import binascii
from contextlib import closing
from uuid import UUID

from ..sdk.relational import RelationalClientError

MYSQL_STATEMENTS = {
    'display': 'SELECT BIN_TO_UUID(%s, 0)',
    'store': 'SELECT UUID_TO_BIN(%s, 0)',
}
MARIADB_STATEMENTS = {
    'display': (
        "SELECT LOWER(CONCAT(SUBSTRING(bits, 1, 8), '-', SUBSTRING(bits, 9, 4), "
        "'-', SUBSTRING(bits, 13, 4), '-', SUBSTRING(bits, 17, 4), '-', SUBSTRING(bits, 21, 12))) "
        "FROM (SELECT HEX(?) AS bits) AS uuid_bytes"
    ),
    'store': "SELECT UNHEX(REPLACE(?, '-', ''))",
}


SQLITE_STATEMENTS = {
    'display': (
        "SELECT LOWER(SUBSTR(bits, 1, 8) || '-' || SUBSTR(bits, 9, 4) || '-' || "
        "SUBSTR(bits, 13, 4) || '-' || SUBSTR(bits, 17, 4) || '-' || SUBSTR(bits, 21, 12)) "
        "FROM (SELECT HEX(?) AS bits)"
    ),
    'store': None,
}
DUCKDB_STATEMENTS = {
    'display': 'SELECT CAST(CAST(HEX(?) AS UUID) AS VARCHAR)',
    'store': "SELECT UNHEX(REPLACE(CAST(CAST(? AS UUID) AS VARCHAR), '-', ''))",
}
STATEMENTS = {
    'mysql': MYSQL_STATEMENTS, 'mariadb': MARIADB_STATEMENTS,
    'sqlite': SQLITE_STATEMENTS, 'duckdb': DUCKDB_STATEMENTS,
    'postgresql': {
        'display': "SELECT CAST(CAST(ENCODE(%s::bytea, 'hex') AS UUID) AS TEXT)",
        'store': 'SELECT UUID_SEND(%s::uuid)',
    },
}


def _bindings(request, engine):
    statements = STATEMENTS[engine]
    direction = request.get('direction')
    values = request.get('values')
    if (request.get('pair') != f'{engine}-uuid-binary'
            or not isinstance(direction, str) or direction not in statements):
        raise RelationalClientError('Field conversion is unavailable for this provider')
    if not isinstance(values, list) or len(values) > 500:
        raise RelationalClientError('Field conversion requires at most 500 values')

    bindings = []
    for value in values:
        if value is None:
            bindings.append(None)
        elif direction == 'display':
            if (not isinstance(value, dict) or value.get('encoding') != 'base64'
                    or not isinstance(value.get('data'), str) or len(value['data']) != 24
                    or value.get('byte_length') != 16):
                raise RelationalClientError('A 16-byte binary UUID value is required')
            try:
                raw = base64.b64decode(value['data'], validate=True)
            except (ValueError, binascii.Error):
                raise RelationalClientError('A 16-byte binary UUID value is required') from None
            if len(raw) != 16:
                raise RelationalClientError('A 16-byte binary UUID value is required')
            bindings.append(raw)
        else:
            try:
                if not isinstance(value, str) or len(value) != 36 or str(UUID(value)) != value.lower():
                    raise ValueError
            except ValueError:
                raise RelationalClientError('Enter a UUID in the 8-4-4-4-12 format') from None
            bindings.append(value.lower())

    return direction, bindings


def convert(provider, request, engine):
    provider._require('execute')
    direction, bindings = _bindings(request, engine)
    if not any(value is not None for value in bindings):
        return {'values': bindings}
    connection = provider.client.open_session({'route': request['_provider_route']})
    try:
        return _convert_values(connection, engine, direction, bindings)
    finally:
        provider.client.close_session(connection)


def convert_postgresql(connection, request):
    direction, bindings = _bindings(request, 'postgresql')
    return _convert_values(connection, 'postgresql', direction, bindings)


def _convert_values(connection, engine, direction, bindings):
    statements = STATEMENTS[engine]
    output = []
    with closing(connection.cursor()) as cursor:
        for value in bindings:
            if value is None:
                output.append(None)
                continue
            statement = statements[direction]
            if statement is None:
                # SQLite's oldest supported runtime predates UNHEX.
                # UUID validation above guarantees a hex-only blob literal.
                cursor.execute(f"SELECT X'{UUID(value).hex}'")
            else:
                cursor.execute(statement, (value,))
            converted = cursor.fetchone()[0]
            if direction == 'display':
                if not isinstance(converted, str) or len(converted) != 36:
                    raise RelationalClientError('The provider did not return UUID text')
                output.append(converted)
            else:
                if not isinstance(converted, (bytes, bytearray)) or len(converted) != 16:
                    raise RelationalClientError('The provider did not return 16 UUID bytes')
                output.append({
                    'encoding': 'base64',
                    'data': base64.b64encode(converted).decode('ascii'),
                    'byte_length': 16,
                })
    return {'values': output}
