"""Portable static DDN data views with exact typed JSON, never live SQL."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .firebird_catalog_export import MAX_BYTES, MAX_DDN_UNITS, MAX_FILES, _json, _units


def build(document):
    header = deepcopy(document)
    counts = [len(table.pop('rows')) for table in header['tables']]
    envelope = {'format': 'scratchrobin.firebird.data-ddn@1', 'archive': header, 'row_counts': counts}
    pages, current = [], []
    for table_number, table in enumerate(document['tables']):
        for ordinal, values in enumerate(table['rows']):
            identity = f'{table_number}:{ordinal}'
            record = ('record r_' + identity.replace(':', '_') + ' ' + _json(table['name'] + ' / ' + str(ordinal+1)) +
                      ' {uid:' + _json('firebird-data:' + identity) + ';x_record:{table_index:' + str(table_number) +
                      ';ordinal:' + str(ordinal) + ';values_json:' + _json(_json(values)) + ';};}')
            if _units(record) > MAX_DDN_UNITS-20000:
                raise ValueError('A data row exceeds the DDN source limit')
            if current and (len(current) == 100 or _units('\n'.join(current+[record])) > MAX_DDN_UNITS-20000):
                pages.append(current); current = []
            current.append(record)
    if current:
        pages.append(current)
    header_source = 'data data_info {record archive "Static data provenance and native column layouts" {x_record:{header_json:' + _json(_json(envelope)) + ';};}}'
    prefix = 'ddn "0.7";module "scratchrobin.firebird.data";\n'
    if not pages:
        pages = [[]]
    files, parts, views = {}, [header_source], []
    def flush():
        name = 'data.ddn' if not files else 'data-' + str(len(files)+1) + '.ddn'
        files[name] = prefix + '\n'.join(parts)
        return name
    pending = []
    for number, records in enumerate(pages, 1):
        block = 'rows_' + str(number)
        view = 'data_' + str(number)
        if records:
            source = ('data ' + block + ' {' + '\n'.join(records) + '}\nview ' + view +
                      ' "Static data — exact JSON values" {data:[@' + block + '];projection {kind:table;profile:"table.records@1";'
                      'records:[' + ','.join('@' + block + '.' + record.split(' ', 2)[1] for record in records) + '];'
                      'columns:[{key:"name",label:"Table / export row"},{key:"x_record.values_json",label:"Exact typed values (JSON)"}];}'
                      'publication {size:content;fit:none;}}')
        else:
            source = 'view ' + view + ' "Empty static data capture" {data:[@data_info];}'
        if _units(prefix+'\n'.join(parts+[source])) > MAX_DDN_UNITS:
            name = flush()
            for item in pending: item['entry'] = name
            parts, pending = [], []
        parts.append(source)
        info = {'id': view, 'label': 'Static data page '+str(number)}
        views.append(info); pending.append(info)
    name = flush()
    for item in pending: item['entry'] = name
    if len(files) > MAX_FILES or any(_units(value) > MAX_DDN_UNITS for value in files.values()):
        raise ValueError('Static data DDN exceeds its workspace limits')
    snapshot = {'format': 'ddn-workspace@1', 'entry': views[0]['entry'], 'view': views[0]['id'], 'files': files}
    text = _json(snapshot)
    if len(text.encode()) > MAX_BYTES:
        raise ValueError('Static data DDN exceeds 8 MiB; choose a smaller data scope')
    return {'snapshot': snapshot, 'views': views, 'filename': 'firebird-data.ddn-workspace.json',
            'download_text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
            'binding': 'static-export', 'row_identity': 'export ordinal, not a native key',
            'row_count': document['row_count']}


def read(source):
    if not isinstance(source, str) or not source.strip() or len(source.encode()) > MAX_BYTES:
        raise ValueError('Static data source exceeds its limit')
    from .firebird_catalog_import import _decode, _SLOTS
    snapshot = _decode(source) if source.lstrip().startswith('{') else {
        'format': 'ddn-workspace@1', 'entry': 'data.ddn', 'view': 'data_1', 'files': {'data.ddn': source}}
    if (not isinstance(snapshot, dict) or set(snapshot) != {'format', 'entry', 'view', 'files'} or
            snapshot['format'] != 'ddn-workspace@1' or not isinstance(snapshot['files'], dict) or
            not 1 <= len(snapshot['files']) <= MAX_FILES or snapshot['entry'] not in snapshot['files'] or
            any(not isinstance(value, str) or _units(value) > MAX_DDN_UNITS for value in snapshot['files'].values())):
        raise ValueError('Invalid static data workspace')
    if not _SLOTS.acquire(timeout=1):
        raise ValueError('Data reader is busy; retry shortly')
    try:
        result = subprocess.run(['node', '--max-old-space-size=192', str(Path(__file__).parent/'ddn/read_data.mjs')],
            input=_json(snapshot), text=True, encoding='utf-8', capture_output=True, timeout=20,
            env={key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'TMPDIR') if key in os.environ})
        if result.returncode:
            raise ValueError('Invalid static data DDN')
        from .firebird_data_import import unique
        parsed = json.loads(result.stdout, object_pairs_hook=unique)
        envelope = json.loads(parsed['header'], object_pairs_hook=unique)
        if (not isinstance(envelope, dict) or set(envelope) != {'format', 'archive', 'row_counts'} or
                envelope['format'] != 'scratchrobin.firebird.data-ddn@1'):
            raise ValueError('Unsupported static data mapping')
        document = envelope['archive']
        counts = envelope['row_counts']
        if (not isinstance(document, dict) or document.get('format') != 'scratchrobin.firebird.data@1' or
                not isinstance(document.get('tables'), list) or not isinstance(counts, list) or
                len(counts) != len(document['tables']) or any(type(count) is not int or count < 0 for count in counts)):
            raise ValueError('Invalid static data table mapping')
        tables = document['tables']
        for table in tables:
            if not isinstance(table, dict) or 'rows' in table:
                raise ValueError('Ambiguous static data rows')
            table['rows'] = []
        for row in sorted(parsed['rows'], key=lambda row: (row['table_index'], row['ordinal'])):
            index, ordinal = row['table_index'], row['ordinal']
            if (type(index) is not int or type(ordinal) is not int or not 0 <= index < len(tables) or
                    ordinal != len(tables[index]['rows']) or ordinal >= counts[index]):
                raise ValueError('Static data identity is duplicate, missing or out of range')
            tables[index]['rows'].append(json.loads(row['values_json'], object_pairs_hook=unique))
        if [len(table['rows']) for table in tables] != counts or sum(counts) != document.get('row_count'):
            raise ValueError('Static data coverage is incomplete')
        text = _json(document)
        if len(text.encode()) > MAX_BYTES:
            raise ValueError('Static data archive exceeds 8 MiB')
        return text
    except (OSError, subprocess.TimeoutExpired, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Static data reader could not admit this workspace') from error
    finally:
        _SLOTS.release()
