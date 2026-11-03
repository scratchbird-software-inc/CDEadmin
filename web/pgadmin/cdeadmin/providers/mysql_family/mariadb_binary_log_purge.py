"""MariaDB binary-log purge, accepted only when the native index confirms it.

PURGE BINARY LOGS succeeds with only a note when the server keeps a file it
considers in use (MariaDB 12.2.2 also reuses an automatic purge refusal for
later manual purges), so the statement's success is not evidence of removal.
"""
import re

from ...sdk.relational import RelationalClientError

NAME = re.compile(r'[A-Za-z0-9_.-]+')


def native_logs(cursor):
    cursor.execute('SHOW BINARY LOGS')
    names = [row[0] for row in cursor.fetchall()]
    if not names or len(names) != len(set(names)) or not all(
            isinstance(name, str) for name in names):
        raise RelationalClientError('The MariaDB binary-log index is unconfirmed')
    return names


def purge(connection, options):
    boundary = options.get('to_file') if isinstance(options, dict) and set(options) == {'to_file'} else None
    if not isinstance(boundary, str) or NAME.fullmatch(boundary) is None:
        raise RelationalClientError('MariaDB binary-log identity is invalid')
    cursor = connection.cursor()
    try:
        before = native_logs(cursor)
        if boundary not in before:
            raise RelationalClientError('The selected MariaDB binary log is no longer in the native index')
        candidates = before[:before.index(boundary)]
        # The boundary is restricted to NAME, so the literal cannot escape.
        cursor.execute("PURGE BINARY LOGS TO '" + boundary + "'")
        cursor.execute('SHOW WARNINGS')
        codes = sorted({row[1] for row in cursor.fetchall() if isinstance(row[1], int)})
        after = native_logs(cursor)
    finally:
        cursor.close()
    retained = [name for name in candidates if name in after]
    if retained or boundary not in after:
        detail = f'; native note code {", ".join(map(str, codes))}' if codes else ''
        raise RelationalClientError(
            f'MariaDB kept {len(retained)} of {len(candidates)} binary logs before '
            f'{boundary}, starting with {retained[0] if retained else boundary}{detail}')
    return {
        'operation_id': 'purge_binary_logs',
        'purge_boundary': boundary,
        'purged_names': candidates,
        'retained_names': [],
        'native_index_verified': True,
        'driver_observation_only': True,
        'transaction_finality_interpreted_by_common_code': False,
    }
