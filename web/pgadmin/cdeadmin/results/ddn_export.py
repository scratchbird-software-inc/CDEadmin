"""Portable, static DDN views of an authorized and redacted result selection."""
import json

from .models import ResultLimitError


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
    header = 'ddn "0.6"; module "scratchrobin.result.static";\n'
    files = {}
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
            lines.append('record ' + identity + ' ' + encoded(str(ordinal)) +
                         ' {x_record: ' + encoded(fields) + ';}')
            refs.append('@rows.' + identity)
        if not lines:
            lines.append('record empty "No rows in this export" {}')
            refs.append('@rows.empty')
        title = f'{metadata.get("title", "Buffered query data")} — page {page}; {len(records)} exported rows'
        source = header + 'data provenance {record capture "Static export coverage" {x_record: {native_json:' + encoded(encoded(provenance)) + '};}}\n'
        source += 'data rows {' + '\n'.join(lines) + '}\n'
        source += 'view result_' + str(page) + ' ' + encoded(title) + ' {data: [@rows]; projection {kind: table; profile: "table.records@1"; records: [' + ','.join(refs) + ']; columns: ' + encoded(definitions) + ';} publication {size: content; fit: none;}}'
        if len(source.encode('utf-16-le')) // 2 > 2000000:
            raise ResultLimitError('DDN result file exceeds its document limit')
        files['result-' + str(page) + '.ddn'] = source
    result = encoded({'format': 'ddn-workspace@1', 'entry': 'result-1.ddn',
                      'view': 'result_1', 'files': files}).encode('utf8')
    if len(result) > 8 * 1024 * 1024:
        raise ResultLimitError('DDN result exceeds 8 MiB')
    return result
