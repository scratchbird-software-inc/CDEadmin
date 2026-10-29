"""Read and compare documentary native metadata without granting execution."""
from . import ddn_source as ddn
from decimal import Decimal
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import threading

from .firebird_catalog_export import MAX_BYTES, MAX_DDN_UNITS

_RUNNER = Path(__file__).parent / 'ddn/read_catalog.mjs'
_SLOTS = threading.BoundedSemaphore(2)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate JSON property in catalog document')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Non-finite JSON value in catalog document')


def _decode(value):
    return json.loads(value, object_pairs_hook=_pairs, parse_float=Decimal,
                      parse_constant=_invalid_constant)


def read_catalog(source, node='node', *, engine='firebird'):
    if engine not in {'firebird', 'postgresql', 'mysql', 'mariadb', 'duckdb', 'sqlite'}:
        raise ValueError('Unsupported native catalog engine')
    if not isinstance(source, str) or not source or len(source.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Catalog document must be nonempty UTF-8 text within 8 MiB')
    snapshot = (_decode(source) if source.lstrip().startswith('{') else
                {'format': 'ddn-source-workspace@1', 'entry': 'catalog.ddn',
                 'view': 'inventory_1', 'files': {'catalog.ddn': source}})
    if isinstance(snapshot, dict) and isinstance(snapshot.get('files'), dict):
        for content in snapshot['files'].values():
            if isinstance(content, str) and len(content.encode('utf-16-le')) // 2 > MAX_DDN_UNITS:
                raise ValueError('Catalog document exceeds the paired DDN per-file limit of 2,000,000 UTF-16 units')
    ddn.validate_workspace(snapshot, 'catalog')
    if not _SLOTS.acquire(timeout=1):
        raise ValueError('Catalog reader is busy; retry shortly')
    try:
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'TMPDIR') if key in os.environ}
        result = subprocess.run([node, ddn.NODE_HEAP_OPTION, str(_RUNNER), engine],
                                input=json.dumps(snapshot, ensure_ascii=False), text=True, encoding='utf-8',
                                capture_output=True, timeout=15, env=env, check=False)
        if result.returncode:
            message = 'Invalid or unsupported native catalog DDN document'
            # Admit codes and source offsets only; never parser messages/source.
            try:
                diagnostics = json.loads(result.stdout)['diagnostics']
                details = []
                for item in diagnostics[:16]:
                    if (isinstance(item, dict) and set(item) == {'code', 'source', 'offset'} and
                            isinstance(item['code'], str) and len(item['code']) <= 128 and
                            item['source'] in snapshot['files'] and type(item['offset']) is int and
                            0 <= item['offset'] <= len(snapshot['files'][item['source']].encode('utf-16-le')) // 2):
                        details.append(item)
                if details:
                    message += ': ' + json.dumps(details, ensure_ascii=True)
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
            raise ValueError(message)
        parsed = json.loads(result.stdout)
        provenance = _decode(parsed['provenance'])
        if (not isinstance(provenance, dict) or
                provenance.get('mapping') != f'scratchrobin.{engine}.catalog@1' or
                provenance.get('deployment') != 'documentary-only' or
                type(provenance.get('objects')) is not int or
                provenance['objects'] != len(parsed['rows'])):
            raise ValueError('Invalid catalog provenance or object count')
        for key in ('endpoint_id', 'database_target_id', 'generation'):
            if not isinstance(provenance.get(key), str) or not provenance[key]:
                raise ValueError('Missing catalog provenance identity')
        rows = {}
        for row in parsed['rows']:
            expected_uid = engine + ':' + provenance['endpoint_id'] + ':' + provenance['database_target_id'] + ':' + row['resource_id']
            if row['uid'] != expected_uid:
                raise ValueError('Catalog object identity disagrees with provenance')
            native, path = _decode(row['native_json']), _decode(row['path_json'])
            if not isinstance(native, dict) or not isinstance(path, list) or any(not isinstance(part, str) for part in path):
                raise ValueError('Invalid native metadata or path')
            system = ('true' if native.get('system_object') is True else
                      'false' if native.get('system_object') is False else 'unknown')
            if row['system'] != system:
                raise ValueError('Inconsistent catalog system classification')
            rows[row['resource_id']] = {**row, 'native': native, 'path': path}
        return {'provenance': provenance, 'rows': rows,
                'sha256': hashlib.sha256(source.encode('utf-8')).hexdigest()}
    except (OSError, subprocess.TimeoutExpired, RecursionError, KeyError, TypeError) as error:
        raise ValueError('Catalog reader could not admit this document') from error
    finally:
        _SLOTS.release()


def _equal(left, right):
    # JSON booleans must not compare equal to integers; arrays keep their order.
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    return left == right


def compare_catalogs(document, current):
    for key in ('mapping', 'endpoint_id', 'database_target_id'):
        if document['provenance'][key] != current['provenance'][key]:
            raise ValueError('Document belongs to a different endpoint or registered database')
    changes = []
    counts = {key: 0 for key in ('equal', 'changed', 'document-only', 'current-only')}
    before, after = document['rows'], current['rows']
    for identity in sorted(before.keys() | after.keys()):
        old, new = before.get(identity), after.get(identity)
        fields = []
        if old is None:
            status = 'current-only'
        elif new is None:
            status = 'document-only'
        else:
            for key in ('kind', 'path', 'name', 'system'):
                if not _equal(old[key], new[key]):
                    fields.append(key)
            for key in sorted(old['native'].keys() | new['native'].keys()):
                if key not in old['native'] or key not in new['native'] or not _equal(old['native'][key], new['native'][key]):
                    fields.append('native.' + key)
            status = 'changed' if fields else 'equal'
        counts[status] += 1
        if status != 'equal':
            item = new or old
            changes.append({'resource_id': identity, 'name': item['name'],
                            'kind': item['kind'], 'status': status, 'fields': fields})
    return {'mode': 'documentary-only', 'counts': counts, 'changes': changes,
            'document_sha256': document['sha256'], 'current_sha256': current['sha256'],
            'current_hash_format': current.get('format', 'scratchrobin.firebird.catalog-ddn@1'),
            'generation': current['provenance']['generation'],
            'warnings': ['Documentary differences are not migration instructions. Missing objects do not authorize deletion.',
                         'Catalog visibility and volatile native properties can produce differences.']}
