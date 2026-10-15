"""Bounded, lossless table capture in one exclusively owned MGA snapshot."""
from datetime import datetime, timezone
import hashlib
import json
import time

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 100000
MAX_SECONDS = 120


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def capture(service, server, model, *, contents='data'):
    if contents not in {'data', 'both'}:
        raise ValueError('Choose data or metadata and data')
    target = model['provenance']['database_target_id']
    tables = sorted((row for row in model['rows'].values()
                     if row['kind'] == 'table' and row['system'] != 'true'),
                    key=lambda row: row['resource_id'])
    if not tables:
        raise ValueError('Select at least one persistent table for data export')
    excluded = []
    persistent = []
    for row in tables:
        relation_type = row['native'].get('relation_type')
        if str(relation_type) != '0':
            excluded.append({'resource_id': row['resource_id'], 'name': row['name'],
                             'reason': 'Not an ordinary persistent MGA table'})
        else:
            persistent.append(row)
    if excluded:
        # The caller must select a persistent branch, never silently omit data.
        raise ValueError('Data scope contains nonpersistent or external tables: ' +
                         ', '.join(row['name'] for row in excluded))
    started = time.monotonic()
    document = {'format': 'scratchrobin.firebird.data@1', 'contents': contents,
                'provenance': {**model['provenance'],
                    'data_consistency': 'one owned read-only MGA snapshot',
                    'captured_at': datetime.now(timezone.utc).isoformat(),
                    'sequence_current_values': 'not-captured'},
                'tables': [], 'row_count': 0}
    if contents == 'both':
        document['metadata'] = model
    size = len(encoded(document).encode('utf-8'))
    if size > MAX_BYTES:
        raise ValueError('Metadata alone exceeds the 8 MiB archive limit')
    session = service.open_session(server, 'firebird-sql', target,
                                   session_purpose='firebird-data-export')['session_id']
    continuation = None
    try:
        for table in persistent:
            resource = {'resource_id': table['resource_id'], 'resource_kind': 'table',
                        'display_name': table['name'], 'display_path': table['path'],
                        'extensions': {'firebird': {'native': table['native']}}}
            captured = {'resource_id': table['resource_id'], 'name': table['name'],
                        'native_columns': table['native'].get('columns', []),
                        'columns': None, 'rows': []}
            size += len(encoded(captured).encode('utf-8'))
            while True:
                if time.monotonic() - started > MAX_SECONDS:
                    raise ValueError('Data capture exceeded its time limit; no partial download is available')
                page = service.read_visual_admin_rows(server, {
                    'target_resource': resource, 'session_id': session,
                    'database_target_id': target, 'limit': 200,
                    'continuation': continuation})
                continuation = page.get('continuation')
                if captured['columns'] is None:
                    captured['columns'] = page['columns']
                    size += len(encoded(page['columns']).encode('utf-8'))
                    expected = [column['name'] for column in captured['native_columns']]
                    actual = [column['name'] for column in page['columns']]
                    if expected != actual:
                        raise ValueError('Native column shape changed; refresh the catalog before exporting')
                elif captured['columns'] != page['columns']:
                    raise ValueError('Native column metadata changed during export')
                for row in page['rows']:
                    values = row['values']
                    if set(values) != {column['name'] for column in captured['columns']}:
                        raise ValueError('Export row does not match its native column metadata')
                    size += len(encoded(values).encode('utf-8')) + 1
                    document['row_count'] += 1
                    if document['row_count'] > MAX_ROWS or size > MAX_BYTES:
                        raise ValueError('Data export exceeds the 100,000-row or 8 MiB limit; select a smaller scope')
                    captured['rows'].append(values)
                if continuation is None:
                    if page.get('complete') is False:
                        raise ValueError('Native row capture is incomplete')
                    break
            document['tables'].append(captured)
        text = encoded(document)
        if len(text.encode('utf-8')) > MAX_BYTES:
            raise ValueError('Data export exceeds the 8 MiB limit; select a smaller scope')
    finally:
        # Cleanup failures suppress a success response; the provider retains
        # uncertain handles and its original transaction authority.
        try:
            if continuation:
                service.cancel_visual_admin_rows(server, {'continuation': continuation,
                    'session_id': session, 'database_target_id': target})
        finally:
            try:
                service.transaction_action(server, session, 'rollback', target)
            finally:
                service.close_session(server, session, target)
    from .firebird_data_ddn import build
    try:
        ddn = build(document)
    except ValueError as error:
        ddn = {'unavailable': True, 'reason': str(error)}
    return {'ddn': ddn, 'format': document['format'], 'filename': 'firebird-data.json',
            'download_text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
            'row_count': document['row_count'], 'table_count': len(document['tables']),
            'provenance': document['provenance'], 'contents': contents,
            'native_import_verified': False}
