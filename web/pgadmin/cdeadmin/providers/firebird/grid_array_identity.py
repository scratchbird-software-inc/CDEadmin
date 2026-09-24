"""Array original-value checks supplement native record-version predicates."""
from datetime import datetime, time
import struct

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .grid_values import normalize_value


def snapshot(value):
    if isinstance(value, (list, tuple)):
        return tuple(snapshot(item) for item in value)
    if isinstance(value, float):
        return 'float', struct.pack('!d', value)
    zone = (getattr(value.tzinfo, '_timezone_', None)
            if isinstance(value, (datetime, time)) else None)
    return type(value).__name__, normalize_value(value), zone


def verify(cursor, guard):
    """Run inside the caller's task savepoint and exclusive session ownership.

    Native version predicates on the subsequent DML protect against another
    attachment changing the row after this check. Comparing array contents also
    catches changes made earlier in this transaction, whose native record
    version is otherwise unchanged. No write probe or base-view bypass occurs.
    """
    cursor.execute(guard['source'], guard['parameters'])
    rows = cursor.fetchall()
    if len(rows) != 1 or snapshot(rows[0]) != guard['snapshot']:
        raise RelationalClientError(
            'row identity no longer identifies exactly one '
            'unchanged array row')
