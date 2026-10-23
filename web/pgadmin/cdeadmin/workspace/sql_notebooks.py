"""Portable SQL investigations. Persistence never dispatches provider work."""
import copy
import json
import re

ASSET_TYPE = 'cdeadmin.sql-notebook.v1'
FORMAT = 'scratchrobin.sql-notebook@1'
MAX_BYTES = 2 * 1024 * 1024
SECRET = re.compile(
    r'-----BEGIN (?:ENCRYPTED |RSA |EC |OPENSSH )?PRIVATE KEY-----|'
    r'\b[a-z][a-z0-9+.-]*://[^\s/]+:[^\s/@]+@|'
    r'\b(?:password|passwd|access_token|refresh_token|client_secret|api_key)'
    r'\s*[=:]\s*[\x22\x27]?[^\s\x22\x27,;]+|'
    r'\bIDENTIFIED\s+(?:WITH\s+\S+\s+)?(?:BY|AS)\b|'
    r'\bSET\s+PASSWORD\b', re.I)


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('Invalid notebook ' + label)


def _text(value, maximum, *, empty=False):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value or (not empty and not value.strip()):
        raise ValueError('Invalid notebook text')
    if SECRET.search(value):
        raise ValueError('Remove credential material before storing or sharing a notebook')


def validate(value):
    """Strict allowlist; no session handles, parameters, credentials or native blobs.

    Credential patterns are a guard, not a classifier for arbitrary business data.
    The author must review notes, SQL literals and selected snapshot data.
    """
    _exact(value, {'format', 'scope', 'cells'}, 'document')
    if value['format'] != FORMAT:
        raise ValueError('Unsupported notebook format')
    scope = value['scope']
    if scope is not None:
        _exact(scope, {'engine', 'endpoint_id', 'database_target_id'}, 'connection scope')
        if scope['engine'] != 'mysql':
            raise ValueError('This notebook workflow requires native MySQL')
        for name in ('endpoint_id', 'database_target_id'):
            _text(scope[name], 256)
    cells = value['cells']
    if not isinstance(cells, list) or len(cells) > 200:
        raise ValueError('Notebook requires at most 200 cells')
    identities = set()
    for cell in cells:
        if not isinstance(cell, dict) or cell.get('kind') not in ('note', 'sql'):
            raise ValueError('Invalid notebook cell')
        _exact(cell, {'id', 'kind', 'source'} | ({'snapshot'} if cell['kind'] == 'sql' else set()), 'cell fields')
        _text(cell['id'], 64)
        if cell['id'] in identities:
            raise ValueError('Duplicate notebook cell identity')
        identities.add(cell['id'])
        _text(cell['source'], 262144, empty=True)
        snapshot = cell.get('snapshot')
        if snapshot is None:
            continue
        _exact(snapshot, {'columns', 'rows', 'captured_at', 'source', 'scope', 'limited'}, 'snapshot')
        _text(snapshot['captured_at'], 64)
        _text(snapshot['source'], 262144)
        if snapshot['source'] != cell['source'] or snapshot['scope'] != scope:
            raise ValueError('Snapshot differs from its executed SQL or connection scope')
        if type(snapshot['limited']) is not bool:
            raise ValueError('Invalid notebook snapshot limits')
        columns, rows = snapshot['columns'], snapshot['rows']
        if not isinstance(columns, list) or not 1 <= len(columns) <= 128:
            raise ValueError('Select 1 to 128 snapshot columns')
        for name in columns:
            _text(name, 256)
        if len(set(columns)) != len(columns):
            raise ValueError('Duplicate snapshot column')
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError('Retain at most 100 snapshot rows')
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns):
                raise ValueError('Invalid notebook snapshot row')
            for item in row:
                # Display strings preserve native types without coercing large
                # integers, Decimal, binary or temporal values through JS floats.
                if item is not None:
                    _text(item, 8192, empty=True)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf8')
    if len(encoded) > MAX_BYTES:
        raise ValueError('Notebook exceeds the 2 MiB sharing limit')
    return copy.deepcopy(value)
