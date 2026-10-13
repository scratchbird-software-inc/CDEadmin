"""Encode imported definitions through native MariaDB; never execute their DDL."""
import base64
import hashlib
import re


def encode_metadata(connection, metadata):
    if (type(connection.server_status) is not int or connection.server_status & 1 or
            connection.autocommit is not True):
        raise ValueError('Native encoding requires its own idle connection')
    if (metadata.get('engine_id') != 'mariadb' or metadata.get('blockers') or
            not metadata.get('statements') or not metadata.get('native_encoding_required')):
        raise ValueError('A complete encoding-required MariaDB metadata export is required')
    cursor = connection.cursor(buffered=False)
    encoded, size = [], 0
    try:
        cursor.execute('SELECT VERSION(),@@server_uid,DATABASE(),@@character_set_client,@@collation_connection')
        identity = cursor.fetchone()
        if (str(identity[0]).split('-')[0] != '12.2.2' or identity[1] != metadata['server_uid'] or
                identity[2] != metadata['database'] or identity[3] != 'utf8mb4'):
            raise ValueError('Native MariaDB encoding connection identity changed')
        for block in metadata['statements']:
            context = block['context']
            charset, collation = context['character_set_client'], context['collation_connection']
            if not all(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_]+', value) for value in (charset, collation)):
                raise ValueError('Invalid native charset/collation identity')
            # Stored client and connection charsets can differ. Validate each,
            # without requiring an invalid same-charset relationship.
            cursor.execute('SELECT CHARACTER_SET_NAME FROM information_schema.CHARACTER_SETS WHERE CHARACTER_SET_NAME=?', (charset,))
            if cursor.fetchall() != [(charset,)]:
                raise ValueError('Native character set is unavailable')
            # MariaDB's native UCA-1400 aliases need not appear in either
            # information_schema collation inventory. Ask the native setter to
            # validate the name, then restore the owned UTF-8 connection context
            # before sending any imported text. Client charset never changes.
            try:
                cursor.execute('SET SESSION collation_connection=?', (collation,))
            finally:
                cursor.execute('SET SESSION collation_connection=?', (identity[4],))
            statement = block['statement']
            cursor.execute('SELECT CAST(CONVERT(? USING ' + charset + ') AS BINARY), '
                'CONVERT(CONVERT(? USING ' + charset + ') USING utf8mb4)', (statement, statement))
            data, roundtrip = cursor.fetchone()
            if not isinstance(data, (bytes, bytearray)) or roundtrip != statement:
                raise ValueError('Native character conversion would lose definition text for ' + block['name'])
            size += len(data)
            if size > 8 * 1024 * 1024:
                raise ValueError('Native encoded statements exceed 8 MiB')
            encoded.append((block, bytes(data)))
    finally:
        cursor.close()
    from ...workspace.mysql_encoded_script import render
    data, encodings = render(encoded, metadata['database'], engine='mariadb')
    return {**metadata, 'script_available': True, 'native_encoding_required': False,
        'script_preview': '\n\n'.join(block['statement'] + ';' for block, _ in encoded),
        'encoded_script': {'consumer': 'mariadb-cli-fresh-session', 'encoding': 'mariadb-client-mixed-charsets',
            'data_base64': base64.b64encode(data).decode('ascii'), 'sha256': hashlib.sha256(data).hexdigest(),
            'byte_size': len(data), 'required_client_options': ['--binary-mode', '--default-character-set=utf8mb4'],
            'statement_encodings': encodings}}
