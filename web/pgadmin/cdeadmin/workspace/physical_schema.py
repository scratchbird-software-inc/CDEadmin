"""Physical-schema x_record vocabulary shared by the *_erd.py emitters, the
reverse reader and the per-engine plan adapters.

The normative description is docs/en_US/ddn_physical_schema_vocabulary.rst.
Vocabulary keys ride beside the existing annotation keys (subject_id,
subject_kind, resource_id, native_json, parent_id, field_*_json). They state
the DESIRED physical facts; the exact native facts stay in native_json and are
the baseline. Edits are detected by comparing the edited vocabulary with the
baseline vocabulary, never with a normalised catalog guess.
"""
import json
import re
import uuid

VERSION = 'scratchrobin.physical-schema@1'
ENGINES = ('postgresql', 'sqlite', 'duckdb', 'mysql', 'mariadb')
KINDS = ('index', 'primary-key', 'unique', 'check', 'foreign-key')
ROLE = {'index': 'index', 'primary-key': 'constraint', 'unique': 'constraint',
        'check': 'constraint', 'foreign-key': 'ref'}
ACTIONS = ('NO ACTION', 'RESTRICT', 'CASCADE', 'SET NULL', 'SET DEFAULT')
# Flat x_record keys. *_json values are JSON text, like native_json.
KEYS = ('physical_kind', 'physical_name', 'rename_from', 'columns_json', 'unique', 'method',
        'predicate', 'expression', 'referenced_columns_json', 'on_delete', 'on_update',
        'drop', 'drop_confirmation',
        # MySQL / MariaDB additions (additive; PostgreSQL, SQLite and DuckDB never emit them).
        'index_type', 'prefix_lengths_json', 'directions_json', 'visible', 'enforced')
_TYPES = {'physical_kind': str, 'physical_name': str, 'rename_from': str, 'columns_json': str,
          'unique': bool, 'method': str, 'predicate': str, 'expression': str,
          'referenced_columns_json': str, 'on_delete': str, 'on_update': str,
          'drop': bool, 'drop_confirmation': str,
          'index_type': str, 'prefix_lengths_json': str, 'directions_json': str, 'visible': bool, 'enforced': bool}


def pick(values):
    """Vocabulary subset of an x_record, dropping absent (None) values."""
    return {key: values[key] for key in KEYS if values.get(key) is not None}


def encode(names):
    return json.dumps(list(names), ensure_ascii=False, separators=(',', ':'))


def normalize(raw, label='physical record'):
    """Validate types and decode the *_json lists; unknown keys are rejected."""
    if not isinstance(raw, dict):
        raise ValueError('Invalid ' + label)
    result = {}
    for key, value in raw.items():
        if key not in _TYPES or type(value) is not _TYPES[key]:
            raise ValueError('Unsupported or mistyped physical-schema property: ' + str(key))
        result[key] = value
    if result.get('physical_kind', KINDS[0]) not in KINDS:
        raise ValueError('Unsupported physical kind')
    for key in ('columns_json', 'referenced_columns_json'):
        if key in result:
            try:
                decoded = json.loads(result[key])
            except ValueError:
                raise ValueError(key + ' must be a JSON array of names') from None
            if (not isinstance(decoded, list) or not 1 <= len(decoded) <= 32 or
                    any(not isinstance(item, str) or not item or '\x00' in item for item in decoded) or
                    len(set(decoded)) != len(decoded)):
                raise ValueError(key + ' must be 1 to 32 distinct non-empty names')
            result[key[:-5]] = decoded
    columns = result.get('columns', [])
    if 'prefix_lengths_json' in result:
        try:
            decoded = json.loads(result['prefix_lengths_json'])
        except ValueError:
            raise ValueError('prefix_lengths_json must be a JSON array of lengths') from None
        if (not isinstance(decoded, list) or not 1 <= len(decoded) <= 32 or
                any(item is not None and (type(item) is not int or not 1 <= item <= 3072) for item in decoded)):
            raise ValueError('prefix_lengths_json must be 1 to 32 entries of null or a length from 1 to 3072')
        if columns and len(decoded) != len(columns):
            raise ValueError('prefix_lengths_json needs one entry per column')
        result['prefix_lengths'] = decoded
    if 'directions_json' in result:
        try:
            decoded = json.loads(result['directions_json'])
        except ValueError:
            raise ValueError('directions_json must be a JSON array of ASC or DESC') from None
        if not isinstance(decoded, list) or not 1 <= len(decoded) <= 32 or any(item not in ('ASC', 'DESC') for item in decoded):
            raise ValueError('directions_json must be 1 to 32 entries of ASC or DESC')
        if columns and len(decoded) != len(columns):
            raise ValueError('directions_json needs one entry per column')
        result['directions'] = decoded
    if result.get('index_type', 'FULLTEXT') not in ('FULLTEXT', 'SPATIAL'):
        raise ValueError('index_type must be FULLTEXT or SPATIAL')
    for key in ('on_delete', 'on_update'):
        if key in result and result[key] not in ACTIONS:
            raise ValueError('Foreign-key action must be one of: ' + ', '.join(ACTIONS))
    for key in ('physical_name', 'rename_from', 'drop_confirmation'):
        if key in result and (not result[key] or '\x00' in result[key]):
            raise ValueError(key + ' must be non-empty text')
    return result


def changes(before, after):
    """Properties the edit changed. A property missing from the edited record is
    a presentation omission, never clear or delete intent."""
    old, new = normalize(before or {}), normalize(after or {})
    changed = {}
    for key in new:
        if key in {'rename_from', 'drop', 'drop_confirmation'} or key.endswith('_json'):
            continue
        if key not in old or old[key] != new[key]:
            changed[key] = new[key]
    for key in ('columns', 'referenced_columns', 'prefix_lengths', 'directions'):
        if key in new and new[key] != old.get(key):
            changed[key] = new[key]
    return changed


def rename(before, after, label):
    """(old, new) only when the edit carries an explicit rename mapping."""
    old, new = normalize(before or {}), normalize(after or {})
    wanted = new.get('physical_name')
    mapped = new.get('rename_from')
    if mapped is not None and wanted is None:
        raise ValueError('rename_from needs the new physical_name')
    if wanted is None or wanted == old.get('physical_name'):
        return None
    if mapped is None:
        raise ValueError('Renaming ' + label + ' requires an explicit rename_from mapping; a changed name is never inferred as a rename')
    if mapped != old.get('physical_name'):
        raise ValueError('rename_from does not name the baseline ' + label)
    return mapped, wanted


def drop(before, after, name, label):
    """True only for drop: true together with the exact object name."""
    new = normalize(after or {})
    if 'drop' not in new:
        if 'drop_confirmation' in new:
            raise ValueError('drop_confirmation without drop: true')
        return False
    if not new['drop']:
        return False
    if new.get('drop_confirmation') != name:
        raise ValueError('Dropping ' + label + ' requires drop_confirmation equal to its exact current name')
    if set(changes(before, after)) - {'drop'}:
        raise ValueError('Review a drop separately from other edits to the same object')
    return True


def draft_identity(engine, parent_uid, uid):
    """Validate a designer-assigned draft uid: <parent uid>:new:<canonical uuid>."""
    prefix = parent_uid + ':new:'
    if not isinstance(uid, str) or not uid.startswith(prefix):
        raise ValueError('Physical draft requires an explicit draft identity under its owning table')
    suffix = uid[len(prefix):]
    try:
        if str(uuid.UUID(suffix)) != suffix:
            raise ValueError()
    except ValueError:
        raise ValueError('Physical draft requires a canonical draft UUID') from None
    return engine + ':new:' + suffix


_ACTION_CODES = {'a': 'NO ACTION', 'r': 'RESTRICT', 'c': 'CASCADE', 'n': 'SET NULL', 'd': 'SET DEFAULT'}
ACTION_CODES = _ACTION_CODES


def split_check(definition):
    """Expression text of a pg_get_constraintdef CHECK; None when not a plain CHECK."""
    match = re.fullmatch(r'CHECK \((.*)\)( NOT VALID)?', definition or '', re.S)
    return match.group(1) if match else None
