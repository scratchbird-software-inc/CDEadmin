"""The reversible UUID field pair exposed to the record surfaces."""

from collections.abc import Mapping
from uuid import UUID

from ...sdk.relational import RelationalClientError
from .grid_values import bind_value, normalize_value

PAIR_ID = 'firebird-uuid-octets'
STATEMENTS = {
    'display': 'SELECT UUID_TO_CHAR(CAST(? AS CHAR(16) CHARACTER SET OCTETS)) FROM RDB$DATABASE',
    'store': 'SELECT CHAR_TO_UUID(CAST(? AS VARCHAR(36) CHARACTER SET ASCII)) FROM RDB$DATABASE',
}


def convert(connection, pair, direction, values):
    if pair != PAIR_ID or not isinstance(direction, str) or direction not in STATEMENTS:
        raise RelationalClientError('Field conversion is unavailable for this provider')
    if not isinstance(values, list) or len(values) > 500:
        raise RelationalClientError('Field conversion requires at most 500 values')
    bindings = []
    for value in values:
        if value is None:
            bindings.append(None)
            continue
        if direction == 'display':
            binary = bind_value(value) if isinstance(value, Mapping) else None
            if not isinstance(binary, bytes) or len(binary) != 16:
                raise RelationalClientError('A 16-byte Firebird UUID value is required')
            bindings.append(binary)
        else:
            try:
                if not isinstance(value, str) or len(value) != 36:
                    raise ValueError
                normalized = str(UUID(value))
                if normalized != value.lower():
                    raise ValueError
            except ValueError:
                raise RelationalClientError('Enter a UUID in the 8-4-4-4-12 format') from None
            bindings.append(normalized)

    output = []
    with connection.cursor() as cursor:
        for value in bindings:
            if value is None:
                output.append(None)
                continue
            cursor.execute(STATEMENTS[direction], (value,))
            converted = cursor.fetchone()[0]
            if direction == 'display':
                if not isinstance(converted, str) or len(converted) != 36:
                    raise RelationalClientError('Firebird did not return a UUID string')
            elif not isinstance(converted, bytes) or len(converted) != 16:
                raise RelationalClientError('Firebird did not return 16 UUID bytes')
            output.append(normalize_value(converted))
    return output
