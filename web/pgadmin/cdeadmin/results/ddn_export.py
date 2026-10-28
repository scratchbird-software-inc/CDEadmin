"""Portable, static DDN views of an authorized and redacted result selection."""
import base64
import json

from .models import ResultLimitError
from ..workspace import ddn_source as ddn


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def export_workspace(metadata, records):
    columns = metadata.get('schema', {}).get('columns', [])
    if len(columns) > 256:
        raise ResultLimitError('DDN export supports at most 256 result columns')
    keys = [column.get('key', column['name']) for column in columns]
    definitions = [{"key": "name", "label": "Buffered row"}] + [
        {"key": 'x_record.c_' + str(i), "label": column['name']}
        for i, column in enumerate(columns)]
    provenance = {key: metadata.get(key) for key in (
        'result_id', 'execution_id', 'schema', 'complete', 'export_coverage')}
    if 'acquisition' in metadata:
        provenance['acquisition'] = metadata['acquisition']
    provenance['provider_continuation_remaining'] = bool(metadata.get('provider_continuation'))
    provenance['mapping'] = 'scratchrobin.result.static@1'
    provenance['value_encoding'] = metadata.get('value_encoding', 'exact redacted provider JSON; columns remain positional')
    provenance['consistency'] = metadata.get('consistency', 'buffered result selection; no new database read')
    module = 'scratchrobin.result.static'
    header = ddn.header(module)
    files = {}
    native_payload = metadata.get('native_payload_bytes')
    if native_payload is not None and (not isinstance(native_payload, bytes) or len(native_payload) > 4 * 1024 * 1024):
        raise ResultLimitError('Native data payload must be bytes within 4 MiB')
    # The paired runtime admits 128 elements per live view. Leave space for
    # provenance/placeholder elements instead of creating unrenderable pages.
    for start in range(0, max(1, len(records)), 100):
        if len(files) >= 64:
            raise ResultLimitError('DDN result exceeds 64 workspace files')
        page = len(files) + 1
        lines = []
        refs = []
        for ordinal, record in enumerate(records[start:start + 100], start + 1):
            values = [record.get(key) for key in keys] if isinstance(record, dict) else list(record)
            if len(values) != len(columns):
                raise ResultLimitError('DDN result row does not match its column metadata')
            fields = {'values_json': encoded(values), **{
                'c_' + str(i): encoded(value) for i, value in enumerate(values)}}
            identity = 'r_' + str(ordinal)
            lines.append(ddn.record_definition(identity, str(ordinal), fields, module=module, block='rows'))
            refs.append('rows.' + identity)
        if not lines:
            lines.append(ddn.record_definition('empty', 'No rows in this export', {}, module=module, block='rows'))
            refs.append('rows.empty')
        title = f'{metadata.get("title", "Buffered query data")} — page {page}; {len(records)} exported rows'
        source = header + ddn.record_definition('capture', 'Static export coverage',
            {'native_json': encoded(provenance)}, module=module, block='provenance')
        source += '\n'.join(lines) + ddn.table_view('result_' + str(page), title, refs, definitions)
        if len(source.encode('utf-16-le')) // 2 > 2000000:
            raise ResultLimitError('DDN result file exceeds its document limit')
        files['result-' + str(page) + '.ddn'] = source
    if native_payload is not None:
        # Keep the binary type representation once per workspace instead of
        # duplicating it in every page's provenance. These static records have
        # no view, connector or executable expression.
        for start in range(0, len(native_payload), 1024 * 1024):
            if len(files) >= 64:
                raise ResultLimitError('Native data payload exceeds 64 workspace files')
            ordinal = start // (1024 * 1024) + 1
            facts = {'ordinal': ordinal, 'encoding': 'arrow-ipc-base64',
                     'data': base64.b64encode(native_payload[start:start + 1024 * 1024]).decode('ascii')}
            files['native-values-' + str(ordinal) + '.ddn'] = header + ddn.record_definition(
                'p_' + str(ordinal), 'Native typed values', facts, module=module, block='native_payload')
    try:
        ddn.connect_files(files)
    except ValueError as error:
        raise ResultLimitError(str(error)) from error
    result = encoded({'format': 'ddn-source-workspace@1', 'entry': 'result-1.ddn',
                      'view': 'result_1', 'files': files}).encode('utf8')
    if len(result) > 8 * 1024 * 1024:
        raise ResultLimitError('DDN result exceeds 8 MiB')
    return result
