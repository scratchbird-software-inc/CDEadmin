"""Lossless bounded SHOW BINLOG EVENTS without session charset changes."""
from .mariadb_values import value

LIMIT = 200


def source(cursor, name):
    if not isinstance(name, str) or not name or '\0' in name or len(name.encode('utf8')) > 4096:
        raise ValueError('Select an observed bounded native binary-log name')
    cursor.execute('SELECT @@sql_mode')
    modes = str(cursor.fetchone()[0] or '').split(',')
    literal = name if 'NO_BACKSLASH_ESCAPES' in modes else name.replace('\\', '\\\\')
    return "SHOW BINLOG EVENTS IN '" + literal.replace("'", "''") + "' LIMIT 201"


def read(cursor, name):
    if not hasattr(cursor, 'cdeadmin_lossless_text') or getattr(cursor, 'cdeadmin_checked_fetch_errors', False) is not True:
        raise ValueError('Native lossless-text and checked-fetch connector support is required for binary-log events')
    sql = source(cursor, name)
    previous = cursor.cdeadmin_lossless_text
    try:
        cursor.cdeadmin_lossless_text = True
        cursor.execute(sql)
        names = [str(column[0]).lower() for column in cursor.description or ()]
        if names != ['log_name', 'pos', 'event_type', 'server_id', 'end_log_pos', 'info']:
            raise ValueError('Native binary-log result metadata changed')
        metadata = cursor.metadata
        info_field = {key: values[5] for key, values in metadata.items()}
        rows = cursor.fetchall()
        result = []
        for row in rows[:LIMIT]:
            record = dict(zip(names, [value(cell) for cell in row]))
            record['info_native_field'] = dict(info_field)
            record['info_representation'] = ('native-binary' if info_field.get('charset') == 63 else
                'undecodable-native-utf8-bytes' if isinstance(row[5], bytes) else 'native-utf8-text')
            result.append(record)
        return {'events': result, 'complete': len(rows) <= LIMIT, 'truncated': len(rows) > LIMIT,
                'limit': LIMIT, 'automatic_retry': False, 'session_charset_changed': False}
    finally:
        cursor.cdeadmin_lossless_text = previous
