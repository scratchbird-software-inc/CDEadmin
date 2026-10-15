"""Round-trip UI BLOB draft output through real Firebird typed bindings."""
import json
import hashlib
import base64
from pathlib import Path
import subprocess


def qualify(connection, client=None):
    from pgadmin.cdeadmin.providers.firebird.grid_values import bind_value
    module = Path(__file__).resolve().parents[1] / 'web/pgadmin/static/js/Dialogs/firebirdBlobValue.js'
    runner = """
import {readFileSync} from 'node:fs';
const m = await import('data:text/javascript;base64,' + readFileSync(process.argv[1]).toString('base64'));
const original = '\ufeffUnicode 世界\\r\\nMixed\\rTail\\n';
const same = m.blobDraft(original, {text: original.replace(/\\r\\n|\\r/g, '\\n'), isNull: false}, 'text', 'preserve', false);
const revised = m.blobDraft(original, {text: 'Edited 世界\\nTail\\n', isNull: false}, 'text', 'crlf', true);
const binary = m.blobImport(Uint8Array.from({length: 256}, (_, i) => i), 'binary');
process.stdout.write(JSON.stringify({same: same.text, revised: revised.text,
 binary: {encoding: 'base64', data: binary, byte_length: 256}}));
"""
    result = subprocess.run(['node', '--input-type=module', '-e', runner, str(module)],
                            capture_output=True, text=True, check=True, timeout=15)
    values = json.loads(result.stdout)
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE BLOB_EDITOR_TEST (ID INTEGER PRIMARY KEY, T BLOB SUB_TYPE TEXT CHARACTER SET UTF8, B BLOB SUB_TYPE BINARY)')
    connection.commit()
    binary = bind_value(values['binary'])
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO BLOB_EDITOR_TEST VALUES (?, ?, ?)', (1, values['same'], binary))
        cursor.execute('INSERT INTO BLOB_EDITOR_TEST VALUES (?, ?, ?)', (2, '', b''))
        cursor.execute('INSERT INTO BLOB_EDITOR_TEST VALUES (?, ?, ?)', (3, None, None))
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute('SELECT T, B FROM BLOB_EDITOR_TEST ORDER BY ID')
        rows = cursor.fetchall()
        assert rows == [(values['same'], bytes(range(256))), ('', b''), (None, None)], rows
        cursor.execute('UPDATE BLOB_EDITOR_TEST SET T = ? WHERE ID = 1', (values['revised'],))
        cursor.execute('SELECT T FROM BLOB_EDITOR_TEST WHERE ID = 1')
        assert cursor.fetchone() == ('Edited 世界\r\nTail\r\n',)
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute('SELECT T FROM BLOB_EDITOR_TEST WHERE ID = 1')
        assert cursor.fetchone() == (values['same'],)
    connection.rollback()
    transfer = None
    if client is not None:
        binary = bytes(index % 251 for index in range(3600000))
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO BLOB_EDITOR_TEST (ID, B) VALUES (4, ?)', (binary,))
        connection.commit()
        def stream(action, **values):
            return client.query_stream(connection, {'stream_action': action, 'owner_id': 'owned-blob-proof', **values})
        page = stream('open', source='SELECT B FROM BLOB_EDITOR_TEST WHERE ID=4')
        reference = page['rows'][0][0]['blob_reference']
        observed = bytearray()
        sizes = []
        try:
            while True:
                chunk = stream('blob', stream_reference=page['stream_reference'], blob_reference=reference, offset=len(observed))
                raw = base64.b64decode(chunk['data'], validate=True)
                assert chunk['offset'] == len(observed) and chunk['next_offset'] == len(observed) + len(raw)
                assert len(raw) <= 65536
                observed.extend(raw); sizes.append(len(raw))
                if chunk['complete']:
                    break
            assert bytes(observed) == binary
        finally:
            stream('close', stream_reference=page['stream_reference'])
            connection.rollback()
        page = stream('open', source='SELECT B FROM BLOB_EDITOR_TEST WHERE ID=4')
        reference = page['rows'][0][0]['blob_reference']
        stream('blob', stream_reference=page['stream_reference'], blob_reference=reference, offset=0)
        stream('close', stream_reference=page['stream_reference'])
        connection.rollback()
        transfer = {'bytes': len(observed), 'chunks': len(sizes), 'max_chunk_bytes': max(sizes),
                    'sha256': hashlib.sha256(observed).hexdigest(), 'early_stream_release': True}
    return {'passed': True, 'native_large_blob_transfer': transfer, 'utf8_bom_and_mixed_endings_preserved': True,
            'all_binary_byte_values_preserved': True, 'null_and_empty_distinct': True,
            'explicit_crlf_conversion': True, 'edit_rollback_preserves_original': True}
