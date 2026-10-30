"""A keyspace VSchema as editor rows, and the edit merged back into it.

Vitess replaces a keyspace's VSchema whole (vtctld ApplyVSchema), so the
editor reads it at execute time, replaces only the sections the editor sent,
validates what vtctld does not, and applies the result in one step.

Live, 23.0.3: vtctld accepted a reference table whose source is missing
(vtgate then serves the whole keyspace in error), a sequence that does not
exist, and an unsharded flag on a two-shard keyspace; these are refused here.
"""

import copy
import json
import re

from pgadmin.cdeadmin.sdk import RelationalClientError

SETTINGS = ('sharded', 'foreign_key_mode', 'require_explicit_routing')
SECTIONS = (*SETTINGS, 'tables', 'table_vindexes', 'vindexes')
FOREIGN_KEY_MODES = ('unspecified', 'disallow', 'unmanaged', 'managed')
TABLE_TYPES = ('', 'reference', 'sequence')
# Linux caps one command-line argument at 128 KiB (MAX_ARG_STRLEN); the
# VSchema travels inline because the tool may run where host files are not.
MAX_DOCUMENT_BYTES = 128 * 1024 - 1

_NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_$-]{0,63}')
_QUALIFIED = re.compile(
    r'[A-Za-z0-9_][A-Za-z0-9_$-]{0,63}\.[A-Za-z0-9_][A-Za-z0-9_$-]{0,63}')
_PARAM_KEY = re.compile(r'[A-Za-z0-9_]{1,64}')
_KEYSPACE_ID = re.compile(r'(?:[0-9A-Fa-f]{2}){1,8}')


def _fail(message):
    raise RelationalClientError(f'Vitess VSchema edit: {message}')


def _name(value, label):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        _fail(f'{label} {value!r} is not a valid name')
    return value


def _columns(value, label):
    if isinstance(value, str):
        value = [item.strip() for item in value.split(',') if item.strip()]
    if not isinstance(value, list) or not value:
        _fail(f'{label} needs at least one column')
    return [_name(item, f'{label} column') for item in value]


def _vindex_columns(entry):
    columns = entry.get('columns') or (
        [entry['column']] if entry.get('column') else [])
    return [str(item) for item in columns]


def flatten(document):
    """Editor rows from a GetVSchema document (the reopened record)."""
    document = document if isinstance(document, dict) else {}
    tables = document.get('tables') or {}
    rows, table_vindexes = [], []
    for name in sorted(tables):
        spec = tables[name] if isinstance(tables[name], dict) else {}
        auto = spec.get('auto_increment') or {}
        rows.append({
            'name': name, 'type': str(spec.get('type') or ''),
            'source': str(spec.get('source') or ''),
            'pinned': str(spec.get('pinned') or ''),
            'auto_increment_column': str(auto.get('column') or ''),
            'auto_increment_sequence': str(auto.get('sequence') or ''),
        })
        for entry in spec.get('column_vindexes') or []:
            table_vindexes.append({
                'table': name, 'vindex': str(entry.get('name') or ''),
                'columns': ', '.join(_vindex_columns(entry)),
            })
    vindexes = document.get('vindexes') or {}
    return {
        'sharded': bool(document.get('sharded')),
        'foreign_key_mode': str(
            document.get('foreign_key_mode') or 'unspecified'),
        'require_explicit_routing': bool(
            document.get('require_explicit_routing')),
        'tables': rows,
        'table_vindexes': table_vindexes,
        'vindexes': [{
            'name': name, 'type': str(spec.get('type') or ''),
            'params': {str(key): str(value) for key, value in (
                spec.get('params') or {}).items()},
            'owner': str(spec.get('owner') or ''),
        } for name, spec in sorted(vindexes.items())
            if isinstance(spec, dict)],
    }


def normalize(draft):
    """The sections an edit sends, checked for shape; the rest untouched."""
    sections = {}
    for key in ('sharded', 'require_explicit_routing'):
        if key in draft:
            if not isinstance(draft[key], bool):
                _fail(f'{key} must be true or false')
            sections[key] = draft[key]
    if 'foreign_key_mode' in draft:
        if draft['foreign_key_mode'] not in FOREIGN_KEY_MODES:
            _fail('foreign key mode must be one of ' +
                  ', '.join(FOREIGN_KEY_MODES))
        sections['foreign_key_mode'] = draft['foreign_key_mode']
    if 'vindexes' in draft:
        rows, names = [], set()
        for row in _rows(draft['vindexes'], 'vindexes'):
            name = _name(row.get('name'), 'vindex')
            if name in names:
                _fail(f'vindex {name} appears twice')
            names.add(name)
            params = row.get('params') or {}
            if not isinstance(params, dict) or any(
                    not _PARAM_KEY.fullmatch(str(key)) or
                    not isinstance(value, (str, int, bool))
                    for key, value in params.items()):
                _fail(f'vindex {name} parameters must be names to values')
            owner = row.get('owner') or ''
            rows.append({
                'name': name, 'type': _name(row.get('type'), 'vindex type'),
                'params': {str(key): (str(value).lower() if isinstance(
                    value, bool) else str(value))
                    for key, value in params.items()},
                'owner': _name(owner, 'owner') if owner else '',
            })
        sections['vindexes'] = rows
    if 'tables' in draft:
        rows, names = [], set()
        for row in _rows(draft['tables'], 'tables'):
            name = _name(row.get('name'), 'table')
            if name in names:
                _fail(f'table {name} appears twice')
            names.add(name)
            table_type = row.get('type') or ''
            if table_type not in TABLE_TYPES:
                _fail(f'table {name} type must be normal, reference or '
                      'sequence')
            source = row.get('source') or ''
            if source and (table_type != 'reference' or
                           not _QUALIFIED.fullmatch(source)):
                _fail(f'table {name} source is keyspace.table and only for '
                      'a reference table')
            pinned = row.get('pinned') or ''
            if pinned and not _KEYSPACE_ID.fullmatch(pinned):
                _fail(f'table {name} pinned keyspace id must be hex bytes')
            column = row.get('auto_increment_column') or ''
            sequence = row.get('auto_increment_sequence') or ''
            if bool(column) != bool(sequence):
                _fail(f'table {name} sequence needs both the column and '
                      'the keyspace.sequence')
            if sequence and not _QUALIFIED.fullmatch(sequence):
                _fail(f'table {name} sequence is keyspace.sequence')
            rows.append({
                'name': name, 'type': table_type, 'source': source,
                'pinned': pinned.lower(),
                'auto_increment_column': (
                    _name(column, 'sequence column') if column else ''),
                'auto_increment_sequence': sequence,
            })
        sections['tables'] = rows
    if 'table_vindexes' in draft:
        sections['table_vindexes'] = [{
            'table': _name(row.get('table'), 'table'),
            'vindex': _name(row.get('vindex'), 'vindex'),
            'columns': ', '.join(_columns(row.get('columns'), 'vindex')),
        } for row in _rows(draft['table_vindexes'], 'table vindexes')]
    if not sections:
        _fail('nothing to change')
    return sections


def _rows(value, label):
    if not isinstance(value, list) or len(value) > 4096 or any(
            not isinstance(row, dict) for row in value):
        _fail(f'{label} must be a list of rows')
    return value


def stale_sections(current, baseline, sections):
    """Sections changed in the topology since the editor read them."""
    if not isinstance(baseline, dict):
        return []
    now = flatten(current)
    return [key for key in sections
            if key in baseline and now.get(key) != baseline.get(key)]


def merge(document, sections):
    """The VSchema with the sent sections replaced and all else kept."""
    merged = copy.deepcopy(document if isinstance(document, dict) else {})
    for key in SETTINGS:
        if key in sections:
            merged[key] = sections[key]
    if 'vindexes' in sections:
        merged['vindexes'] = {row['name']: {
            'type': row['type'], 'params': dict(row['params']),
            **({'owner': row['owner']} if row['owner'] else {}),
        } for row in sections['vindexes']}
    if 'tables' in sections or 'table_vindexes' in sections:
        rows = flatten(merged)
        tables = sections.get('tables', rows['tables'])
        table_vindexes = sections.get('table_vindexes',
                                      rows['table_vindexes'])
        known = {row['name'] for row in tables}
        for row in table_vindexes:
            if row['table'] not in known:
                _fail(f"table {row['table']} has vindexes but is not in "
                      'Tables')
        old = merged.get('tables') or {}
        rebuilt = {}
        for row in tables:
            # Keep what the editor does not show (columns, authoritative).
            spec = copy.deepcopy(old.get(row['name']) or {})
            for key, value in (('type', row['type']),
                               ('source', row['source']),
                               ('pinned', row['pinned'])):
                if value:
                    spec[key] = value
                else:
                    spec.pop(key, None)
            if row['auto_increment_column']:
                spec['auto_increment'] = {
                    'column': row['auto_increment_column'],
                    'sequence': row['auto_increment_sequence']}
            else:
                spec.pop('auto_increment', None)
            spec['column_vindexes'] = [{
                'name': item['vindex'],
                'columns': _columns(item['columns'], 'vindex'),
            } for item in table_vindexes if item['table'] == row['name']]
            if not spec['column_vindexes']:
                spec.pop('column_vindexes')
            rebuilt[row['name']] = spec
        merged['tables'] = rebuilt
    return merged


def validate(keyspace, merged, shard_count, documents):
    """Refuse what vtctld accepts but vtgate cannot serve.

    ``documents`` maps other keyspaces to their VSchema (sources and
    sequences live there); ``shard_count`` is None when unknown.
    """
    if not merged.get('sharded') and shard_count and shard_count > 1:
        _fail(f'{keyspace} has {shard_count} shards; an unsharded VSchema '
              'would route every query to one of them')
    vindexes = merged.get('vindexes') or {}
    for name, spec in (merged.get('tables') or {}).items():
        for entry in spec.get('column_vindexes') or []:
            if entry.get('name') not in vindexes:
                _fail(f"table {name} uses vindex {entry.get('name')}, which "
                      'is not defined in this keyspace')
        if spec.get('type') == 'reference' and spec.get('source'):
            source_keyspace, source_table = spec['source'].split('.', 1)
            source = merged if source_keyspace == keyspace else (
                documents.get(source_keyspace))
            if not isinstance(source, dict) or source_table not in (
                    source.get('tables') or {}):
                _fail(f"reference table {name} source {spec['source']} is "
                      'not a table in that keyspace\'s VSchema')
        auto = spec.get('auto_increment') or {}
        if auto.get('sequence'):
            sequence_keyspace, sequence = auto['sequence'].split('.', 1)
            owner = merged if sequence_keyspace == keyspace else (
                documents.get(sequence_keyspace))
            entry = ((owner or {}).get('tables') or {}).get(sequence) or {}
            if entry.get('type') != 'sequence':
                _fail(f"table {name} sequence {auto['sequence']} is not a "
                      'sequence in that keyspace\'s VSchema')
        if merged.get('sharded') and not spec.get('column_vindexes') and \
                spec.get('type') not in {'reference', 'sequence'} and \
                not spec.get('pinned'):
            _fail(f'table {name} in sharded keyspace {keyspace} needs a '
                  'primary vindex, a pin or a reference type')
    text = json.dumps(merged, sort_keys=True, separators=(',', ':'))
    if len(text.encode('utf-8')) > MAX_DOCUMENT_BYTES:
        _fail('the VSchema exceeds 128 KiB, the largest single argument '
              'the tool can take')
    return text


def referenced_keyspaces(keyspace, merged):
    """Other keyspaces whose VSchema validation needs."""
    found = set()
    for spec in (merged.get('tables') or {}).values():
        for value in (spec.get('source'),
                      (spec.get('auto_increment') or {}).get('sequence')):
            if value and '.' in value and value.split('.', 1)[0] != keyspace:
                found.add(value.split('.', 1)[0])
    return sorted(found)


def applied(sections, document):
    """Whether a GetVSchema document now holds every sent section."""
    now = flatten(document)
    for key, value in sections.items():
        if key == 'tables':
            if [row['name'] for row in now['tables']] != sorted(
                    row['name'] for row in value):
                return False
            by_name = {row['name']: row for row in now['tables']}
            if any(by_name[row['name']] != row for row in value):
                return False
        elif key == 'table_vindexes':
            if sorted(map(json.dumps, now['table_vindexes'])) != sorted(
                    map(json.dumps, value)):
                return False
            for table in {row['table'] for row in value}:
                if [row for row in now['table_vindexes']
                        if row['table'] == table] != [
                        row for row in value if row['table'] == table]:
                    return False
        elif key == 'vindexes':
            if sorted(now['vindexes'], key=lambda row: row['name']) != sorted(
                    value, key=lambda row: row['name']):
                return False
        elif now.get(key) != value:
            return False
    return True
