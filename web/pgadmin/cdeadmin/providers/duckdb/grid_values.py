"""Exact native row pages, private optimistic identities, and write codecs.

Python fetchall() narrows TIMESTAMP_NS to microseconds. Keep display values
in the existing Arrow wire format, and bind private originals from native
scalar text inside their native container/type. Neither representation is
executable user SQL. The outer lambda observes each source value once.

For DML writes (INSERT / UPDATE), compile_write_value() validates typed input
envelopes against the column's exact DuckDBPyType and emits lossless native
expressions/parameters, failing closed on precision loss or unsupported opaque
types (DU-AUD-42, DU-AUD-43).
"""
import base64
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import math
import re
import uuid

from ...sdk import RelationalClientError
from .unions import capture, quote, restore
from .values import (
    ADMITTED_TEMPORAL_TYPES,
    INTEGER_RANGES,
    SAFE_INTEGER,
    decode_interval_components,
    scalar,
    temporal_ticks_to_sql_text,
    validate_decimal_string,
)

NATIVE = '"system"."main".'

_TEMPORAL_IDS = {
    'date': ('DATE', 'date32[day]'),
    'time': ('TIME', 'time64[us]'),
    'time with time zone': ('TIMETZ', None),
    'timestamp_s': ('TIMESTAMP_S', 'timestamp[s]'),
    'timestamp_ms': ('TIMESTAMP_MS', 'timestamp[ms]'),
    'timestamp': ('TIMESTAMP', 'timestamp[us]'),
    'timestamp_ns': ('TIMESTAMP_NS', 'timestamp[ns]'),
    'timestamp with time zone': ('TIMESTAMPTZ', 'timestamp[us, tz='),
}
_INT_IDS = {
    'tinyint': 'TINYINT',
    'smallint': 'SMALLINT',
    'integer': 'INTEGER',
    'bigint': 'BIGINT',
    'hugeint': 'HUGEINT',
    'utinyint': 'UTINYINT',
    'usmallint': 'USMALLINT',
    'uinteger': 'UINTEGER',
    'ubigint': 'UBIGINT',
    'uhugeint': 'UHUGEINT',
    'bignum': 'BIGNUM',
}
_ZONE_RE = re.compile(
    r'(?:Z|[+-]\d{2}(?::?\d{2})?(?::?\d{2})?|[A-Za-z_]+/[A-Za-z0-9_+-]+)\s*$',
    re.IGNORECASE,
)


def input_envelope_spec(kind):
    """Describe admitted exact write envelopes for a DuckDBPyType."""
    kid = getattr(kind, 'id', None)
    sql = str(kind)
    if kid == 'boolean':
        return {'admitted': True, 'native_type': sql, 'envelopes': ['boolean', 'null']}
    if kid in _INT_IDS:
        envelopes = ['integer-envelope', 'null']
        if kid not in {'hugeint', 'uhugeint', 'bignum', 'ubigint', 'bigint'}:
            envelopes.insert(0, 'safe-int')
        else:
            envelopes.append('safe-int')
        return {'admitted': True, 'native_type': sql, 'envelopes': envelopes}
    if kid in {'float', 'double'}:
        return {'admitted': True, 'native_type': sql, 'envelopes': ['number', 'special-float-text', 'null']}
    if kid == 'decimal':
        meta = dict(kind.children)
        return {
            'admitted': True,
            'native_type': sql,
            'precision': meta['precision'],
            'scale': meta['scale'],
            'envelopes': ['decimal-envelope', 'safe-int', 'null'],
        }
    if kid == 'varchar':
        return {'admitted': True, 'native_type': sql, 'envelopes': ['string', 'null']}
    if kid == 'enum':
        meta = dict(kind.children)
        return {'admitted': True, 'native_type': sql, 'values': list(meta['values']), 'envelopes': ['enum-label', 'null']}
    if kid == 'blob':
        return {'admitted': True, 'native_type': sql, 'envelopes': ['base64-envelope', 'null']}
    if kid == 'bit':
        return {'admitted': True, 'native_type': sql, 'envelopes': ['bit-envelope', 'null']}
    if kid == 'uuid':
        return {'admitted': True, 'native_type': sql, 'envelopes': ['uuid-envelope', 'uuid-string', 'null']}
    if kid in _TEMPORAL_IDS:
        sql_tp, arrow_tp = _TEMPORAL_IDS[kid]
        envs = ['temporal-envelope', 'null']
        if arrow_tp is not None:
            envs.insert(0, 'temporal-ticks-envelope')
        return {'admitted': True, 'native_type': sql, 'temporal_kind': sql_tp, 'envelopes': envs}
    if kid == 'interval':
        return {'admitted': True, 'native_type': sql, 'envelopes': ['interval-envelope', 'null']}
    if kid in {'list', 'array'}:
        meta = dict(kind.children)
        child_spec = input_envelope_spec(meta['child'])
        return {
            'admitted': child_spec['admitted'],
            'native_type': sql,
            'envelopes': ([f'{kid}-envelope', 'array', 'null'] if child_spec['admitted'] else []),
            **({'size': meta['size']} if kid == 'array' else {}),
            'element': child_spec,
        }
    if kid == 'struct':
        fields = {name: input_envelope_spec(sub) for name, sub in kind.children}
        admitted = bool(fields) and all(spec['admitted'] for spec in fields.values())
        return {
            'admitted': admitted,
            'native_type': sql,
            'envelopes': (['struct-object', 'struct-envelope', 'null'] if admitted else []),
            'fields': fields,
        }
    if kid == 'map':
        meta = dict(kind.children)
        k_spec = input_envelope_spec(meta['key'])
        v_spec = input_envelope_spec(meta['value'])
        admitted = k_spec['admitted'] and v_spec['admitted']
        return {
            'admitted': admitted,
            'native_type': sql,
            'envelopes': (['map-envelope', 'null'] if admitted else []),
            'key': k_spec,
            'value': v_spec,
        }
    if kid == 'union':
        members = {name: input_envelope_spec(sub) for name, sub in kind.children[1:]}
        admitted = bool(members) and all(spec['admitted'] for spec in members.values())
        return {
            'admitted': admitted,
            'native_type': sql,
            'envelopes': (['union-envelope', 'null'] if admitted else []),
            'members': members,
        }
    return {'admitted': False, 'native_type': sql, 'envelopes': []}


def compile_write_value(value, kind):
    """Compile one column write value against its exact DuckDBPyType.

    Returns (sql_expression, list_of_bound_parameters). Fails closed on any
    precision loss, mismatched container arity, or unsupported opaque type.
    """
    native_type = str(kind)
    kid = getattr(kind, 'id', None)
    spec = input_envelope_spec(kind)
    if not spec['admitted']:
        raise RelationalClientError(
            f'DuckDB column type {native_type} has no admitted lossless write codec'
        )
    if value is None:
        return f'CAST(? AS {native_type})', [None]
    if isinstance(value, Mapping) and value.get('encoding') == 'duckdb-arrow-opaque':
        raise RelationalClientError(
            'Opaque DuckDB Arrow presentation envelopes cannot be written; use a typed input envelope'
        )

    if kid == 'boolean':
        if type(value) is not bool:
            raise RelationalClientError('DuckDB BOOLEAN column requires true, false, or null')
        return 'CAST(? AS BOOLEAN)', [value]

    if kid in _INT_IDS:
        sql_int = _INT_IDS[kid]
        if type(value) is int:
            if abs(value) > SAFE_INTEGER:
                raise RelationalClientError(
                    f'DuckDB {sql_int} integer exceeds JS safe range; wrap in an integer envelope'
                )
            integer = value
            raw = str(value)
        elif isinstance(value, Mapping) and value.get('encoding') == 'integer':
            if set(value) - {'encoding', 'data', 'native_type'}:
                raise RelationalClientError('DuckDB integer envelope fields invalid')
            raw = value.get('data')
            if not isinstance(raw, str) or not re.fullmatch(r'-?(0|[1-9][0-9]*)', raw):
                raise RelationalClientError('DuckDB integer envelope requires canonical integer text')
            integer = int(raw)
        else:
            raise RelationalClientError(f'DuckDB {sql_int} column requires a safe integer or integer envelope')
        if sql_int != 'BIGNUM':
            lo, hi = INTEGER_RANGES[sql_int]
            if not (lo <= integer <= hi):
                raise RelationalClientError(f'DuckDB integer {raw} is out of range for {sql_int}')
        return f'CAST(? AS {native_type})', [raw]

    if kid in {'float', 'double'}:
        if type(value) in {int, float} and not isinstance(value, bool):
            if isinstance(value, int) and abs(value) > SAFE_INTEGER:
                raise RelationalClientError('Wide integer cannot be narrowed into floating-point without explicit text')
            if isinstance(value, float) and not math.isfinite(value):
                raise RelationalClientError('Use canonical text NaN, Infinity, or -Infinity for non-finite floats')
            return f'CAST(? AS {native_type})', [float(value)]
        if isinstance(value, str) and value.strip() in {'NaN', 'Infinity', '-Infinity', '-0.0', '0.0'}:
            return f'CAST(? AS {native_type})', [value.strip()]
        if isinstance(value, Mapping) and value.get('encoding') == 'float':
            raw = value.get('data')
            if set(value) != {'encoding', 'data'} or not isinstance(raw, str):
                raise RelationalClientError('DuckDB float envelope requires text data')
            try:
                float(raw)
            except ValueError:
                raise RelationalClientError('DuckDB float envelope value is invalid') from None
            return f'CAST(? AS {native_type})', [raw]
        raise RelationalClientError(f'DuckDB {native_type} requires a finite number or float envelope')

    if kid == 'decimal':
        meta = dict(kind.children)
        prec, scale = meta['precision'], meta['scale']
        if type(value) is int:
            if abs(value) > SAFE_INTEGER:
                raise RelationalClientError('Unsafe integer requires a decimal envelope')
            raw = str(value)
        elif isinstance(value, Mapping) and value.get('encoding') == 'decimal':
            if set(value) - {'encoding', 'data', 'precision', 'scale'}:
                raise RelationalClientError('DuckDB decimal envelope fields invalid')
            raw = value.get('data')
        else:
            raise RelationalClientError(
                f'DuckDB {native_type} requires a decimal envelope (floats are rejected to prevent precision loss)'
            )
        validate_decimal_string(raw, max_precision=prec, max_scale=scale)
        return f'CAST(? AS {native_type})', [raw]

    if kid == 'varchar':
        if not isinstance(value, str):
            raise RelationalClientError('DuckDB VARCHAR column requires text or null')
        return 'CAST(? AS VARCHAR)', [value]

    if kid == 'enum':
        allowed = set(dict(kind.children)['values'])
        if not isinstance(value, str) or value not in allowed:
            raise RelationalClientError(f'DuckDB {native_type} value is not an admitted enum label')
        return f'CAST(? AS {native_type})', [value]

    if kid == 'blob':
        if isinstance(value, (bytes, bytearray, memoryview)):
            raw_bytes = bytes(value)
        elif isinstance(value, Mapping) and value.get('encoding') == 'base64':
            if set(value) - {'encoding', 'data', 'byte_length'} or not isinstance(value.get('data'), str):
                raise RelationalClientError('DuckDB BLOB base64 envelope is invalid')
            try:
                raw_bytes = base64.b64decode(value['data'], validate=True)
            except Exception:
                raise RelationalClientError('DuckDB BLOB base64 payload is invalid') from None
            if 'byte_length' in value and value['byte_length'] != len(raw_bytes):
                raise RelationalClientError('DuckDB BLOB byte_length does not match decoded bytes')
        else:
            raise RelationalClientError('DuckDB BLOB column requires a base64 envelope')
        return 'CAST(? AS BLOB)', [raw_bytes]

    if kid == 'bit':
        if isinstance(value, Mapping) and value.get('encoding') == 'bit':
            if set(value) != {'encoding', 'data'}:
                raise RelationalClientError('DuckDB BIT envelope fields invalid')
            raw = value.get('data')
        else:
            raise RelationalClientError('DuckDB BIT column requires a bit envelope')
        if not isinstance(raw, str) or not raw or any(ch not in '01' for ch in raw):
            raise RelationalClientError('DuckDB BIT string must contain only 0 and 1')
        return 'CAST(? AS BIT)', [raw]

    if kid == 'uuid':
        raw = value.get('data') if isinstance(value, Mapping) and value.get('encoding') == 'uuid' else value
        if isinstance(value, Mapping) and set(value) != {'encoding', 'data'}:
            raise RelationalClientError('DuckDB UUID envelope fields invalid')
        if not isinstance(raw, str):
            raise RelationalClientError('DuckDB UUID column requires UUID text or uuid envelope')
        try:
            canonical = str(uuid.UUID(raw))
        except Exception:
            raise RelationalClientError('DuckDB UUID value is invalid') from None
        return 'CAST(? AS UUID)', [canonical]

    if kid in _TEMPORAL_IDS:
        expected_sql, expected_arrow = _TEMPORAL_IDS[kid]
        if isinstance(value, Mapping) and value.get('encoding') == 'temporal-ticks':
            if set(value) != {'encoding', 'arrow_type', 'ticks'}:
                raise RelationalClientError('DuckDB temporal-ticks envelope fields invalid')
            arrow_type = str(value.get('arrow_type') or '')
            if expected_arrow is None:
                raise RelationalClientError(f'DuckDB {native_type} requires a temporal text envelope with offset')
            if expected_arrow.endswith('tz='):
                if not arrow_type.startswith('timestamp[us, tz='):
                    raise RelationalClientError(f'DuckDB {native_type} requires timezone-qualified microsecond ticks')
            elif arrow_type != expected_arrow:
                raise RelationalClientError(
                    f'DuckDB {native_type} requires arrow_type {expected_arrow!r}, got {arrow_type!r}'
                )
            _, sql_text = temporal_ticks_to_sql_text(arrow_type, value.get('ticks'))
            return f'CAST(? AS {native_type})', [sql_text]
        if isinstance(value, Mapping) and value.get('encoding') == 'temporal':
            if set(value) != {'encoding', 'native_type', 'data'}:
                raise RelationalClientError('DuckDB temporal envelope fields invalid')
            req_tp = ADMITTED_TEMPORAL_TYPES.get(str(value.get('native_type') or '').strip().upper())
            if req_tp != expected_sql:
                raise RelationalClientError(
                    f'DuckDB {native_type} temporal envelope type mismatch ({value.get("native_type")!r})'
                )
            text = value.get('data')
            if not isinstance(text, str) or not text.strip():
                raise RelationalClientError('DuckDB temporal envelope requires non-empty text')
            text = text.strip()
            if expected_sql in {'TIMETZ', 'TIMESTAMPTZ'} and text.lower() not in {'infinity', '-infinity'}:
                if not _ZONE_RE.search(text):
                    raise RelationalClientError(f'DuckDB {native_type} requires an explicit timezone or offset')
            if expected_sql in {'TIMESTAMP', 'TIMESTAMPTZ', 'TIMESTAMP_MS', 'TIMESTAMP_S', 'TIME'}:
                frac = re.search(r'\.(\d+)', text)
                max_digits = {'TIME': 6, 'TIMESTAMP': 6, 'TIMESTAMPTZ': 6, 'TIMESTAMP_MS': 3, 'TIMESTAMP_S': 0}[expected_sql]
                if frac and len(frac.group(1).rstrip('0')) > max_digits:
                    raise RelationalClientError(
                        f'DuckDB {native_type} cannot accept {len(frac.group(1))} fractional digits without truncation'
                    )
            return f'CAST(? AS {native_type})', [text]
        raise RelationalClientError(f'DuckDB {native_type} requires a temporal or temporal-ticks envelope')

    if kid == 'interval':
        if not isinstance(value, Mapping) or value.get('encoding') != 'interval':
            raise RelationalClientError('DuckDB INTERVAL column requires an interval envelope')
        months, days, micros = decode_interval_components(value)
        return (
            f'({NATIVE}to_months(?) + {NATIVE}to_days(?) + {NATIVE}to_microseconds(?))',
            [months, days, micros],
        )

    if kid in {'list', 'array'}:
        meta = dict(kind.children)
        if isinstance(value, Mapping) and value.get('encoding') in {'list', 'array'}:
            allowed = {'encoding', 'items', 'element_type'} | ({'size'} if kid == 'array' else set())
            if set(value) - allowed or not isinstance(value.get('items'), list):
                raise RelationalClientError(f'DuckDB {kid} envelope fields invalid')
            items = value['items']
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            raise RelationalClientError(f'DuckDB {native_type} requires a list/array')
        if kid == 'array' and len(items) != meta['size']:
            raise RelationalClientError(
                f'DuckDB {native_type} requires exactly {meta["size"]} elements, got {len(items)}'
            )
        exprs, params = [], []
        for item in items:
            sub_expr, sub_params = compile_write_value(item, meta['child'])
            exprs.append(sub_expr)
            params.extend(sub_params)
        return f'CAST([{", ".join(exprs)}] AS {native_type})', params

    if kid == 'struct':
        if isinstance(value, Mapping) and value.get('encoding') == 'struct':
            if set(value) != {'encoding', 'fields'} or not isinstance(value.get('fields'), Mapping):
                raise RelationalClientError('DuckDB struct envelope requires fields')
            fields_obj = value['fields']
        elif isinstance(value, Mapping) and 'encoding' not in value:
            fields_obj = value
        else:
            raise RelationalClientError(f'DuckDB {native_type} requires a struct object')
        expected_names = [name for name, _ in kind.children]
        if set(fields_obj) != set(expected_names):
            raise RelationalClientError(
                f'DuckDB {native_type} requires exact struct fields {expected_names}'
            )
        parts, params = [], []
        for name, sub_kind in kind.children:
            sub_expr, sub_params = compile_write_value(fields_obj[name], sub_kind)
            parts.append(f'{quote(name)} := {sub_expr}')
            params.extend(sub_params)
        return f'CAST({NATIVE}struct_pack({", ".join(parts)}) AS {native_type})', params

    if kid == 'map':
        meta = dict(kind.children)
        if not isinstance(value, Mapping) or value.get('encoding') != 'map':
            raise RelationalClientError(f'DuckDB {native_type} requires a map envelope')
        if set(value) - {'encoding', 'entries', 'key_type', 'value_type'} or not isinstance(value.get('entries'), list):
            raise RelationalClientError('DuckDB map envelope requires entries')
        key_exprs, val_exprs, key_params, val_params, seen_keys = [], [], [], [], []
        for pair in value['entries']:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2 or pair[0] is None:
                raise RelationalClientError('DuckDB MAP entry must be a [non-null key, value] pair')
            if pair[0] in seen_keys:
                raise RelationalClientError('DuckDB MAP keys must be unique')
            seen_keys.append(pair[0])
            k_expr, k_params = compile_write_value(pair[0], meta['key'])
            v_expr, v_params = compile_write_value(pair[1], meta['value'])
            key_exprs.append(k_expr)
            val_exprs.append(v_expr)
            key_params.extend(k_params)
            val_params.extend(v_params)
        return (
            f'CAST({NATIVE}map([{", ".join(key_exprs)}], [{", ".join(val_exprs)}]) AS {native_type})',
            key_params + val_params,
        )

    if kid == 'union':
        if not isinstance(value, Mapping) or value.get('encoding') != 'union':
            raise RelationalClientError(f'DuckDB {native_type} requires a union envelope')
        if set(value) - {'encoding', 'tag', 'value', 'union_type'}:
            raise RelationalClientError('DuckDB union envelope fields invalid')
        tag = value.get('tag')
        members = dict(kind.children[1:])
        if not isinstance(tag, str) or tag not in members:
            raise RelationalClientError(f'DuckDB union tag {tag!r} is not in {native_type}')
        sub_expr, sub_params = compile_write_value(value.get('value'), members[tag])
        return (
            f'CAST({NATIVE}union_value({quote(tag)} := {sub_expr}) AS {native_type})',
            sub_params,
        )

    raise RelationalClientError(f'DuckDB type {native_type} write codec is unavailable')


def _binding_source(expression, kind, counter):
    """Produce nullable strings at leaves without a Python scalar conversion."""
    children = dict(kind.children) if kind.id in {
        'struct', 'union', 'list', 'array', 'map'} else {}
    if not children:
        return f'CAST({expression} AS VARCHAR)'
    counter[0] += 1
    variable = '__cde_bound_' + str(counter[0])
    if kind.id in {'list', 'array'}:
        return (f'{NATIVE}list_transform({expression}, lambda {variable}: '
                + _binding_source(variable, children['child'], counter) + ')')
    if kind.id == 'map':
        key = _binding_source(variable + '.key', children['key'], counter)
        value = _binding_source(variable + '.value', children['value'], counter)
        return (f'{NATIVE}list_transform({NATIVE}map_entries({expression}), '
                f'lambda {variable}: {NATIVE}struct_pack(key := {key}, value := {value}))')
    if kind.id == 'union':
        fields = [quote(name) + ' := ' + _binding_source(
            f'{NATIVE}union_extract({expression}, '
            + "'" + name.replace("'", "''") + "')", child, counter)
            for name, child in kind.children[1:]]
        body = (f'{NATIVE}struct_pack(tag := CAST({NATIVE}union_tag({expression}) AS VARCHAR), '
                f'members := {NATIVE}struct_pack(' + ', '.join(fields) + '))')
    else:
        fields = [quote(name) + ' := ' + _binding_source(
            expression + '.' + quote(name), child, counter)
            for name, child in kind.children]
        body = NATIVE + 'struct_pack(' + ', '.join(fields) + ')'
    return f'CASE WHEN {expression} IS NULL THEN NULL ELSE {body} END'


def _bound_expression(value, kind):
    """Reconstruct a private original using bound leaves and native types."""
    native_type = str(kind)  # An engine-supplied DuckDBPyType, never a draft.
    if value is None:
        return f'CAST(? AS {native_type})', [None]
    sources, parameters = [], []

    def child(item, child_type):
        source, bound = _bound_expression(item, child_type)
        parameters.extend(bound)
        return source

    children = dict(kind.children) if kind.id in {
        'struct', 'union', 'list', 'array', 'map'} else {}
    if kind.id == 'struct':
        sources = [quote(name) + ' := ' + child(value[name], child_type)
                   for name, child_type in kind.children]
        source = NATIVE + 'struct_pack(' + ', '.join(sources) + ')'
    elif kind.id == 'union':
        tag = value['tag']
        if tag not in children:
            raise RelationalClientError('Native union identity is unavailable')
        source = (NATIVE + 'union_value(' + quote(tag) + ' := '
                  + child(value['members'][tag], children[tag]) + ')')
    elif kind.id in {'list', 'array'}:
        source = '[' + ', '.join(
            child(item, children['child']) for item in value) + ']'
    elif kind.id == 'map':
        keys = [child(item['key'], children['key']) for item in value]
        values = [child(item['value'], children['value']) for item in value]
        source = (NATIVE + 'map([' + ', '.join(keys) + '], ['
                  + ', '.join(values) + '])')
    else:
        return f'CAST(? AS {native_type})', [value]
    return f'CAST({source} AS {native_type})', parameters


@dataclass(frozen=True)
class NativeCell:
    kind: object
    public: object
    original: object

    def __deepcopy__(self, memo):
        # Private cells are never exposed or edited. Copy only their public
        # wire values at the presentation boundary, not the native type object.
        return self

    def binding(self):
        return _bound_expression(self.original, self.kind)


class RowCursor:
    def __init__(self, connection):
        self.connection = connection
        self.relation = None
        self.kinds = None
        self.description = None
        self.lossless = connection.execute(
            f"SELECT {NATIVE}current_setting('arrow_lossless_conversion')"
        ).fetchone()[0]

    def execute(self, source):
        self.connection.execute('SET arrow_lossless_conversion=true')
        relation = self.connection.sql(source)
        self.kinds = list(relation.types)
        self.description = [(name, kind) for name, kind in
                            zip(relation.columns, self.kinds)]
        fields = []
        for index, kind in enumerate(self.kinds):
            variable = '__cde_value_' + str(index)
            public = capture(variable, kind, [0], NATIVE)
            original = _binding_source(variable, kind, [0])
            fields.append(
                f'{NATIVE}list_transform([#{index + 1}], lambda {variable}: '
                f'{NATIVE}struct_pack(public_value := {public}, original := {original}))'
                f'[1] AS __cde_cell_{index}')
        self.relation = relation.project(', '.join(fields))
        return self

    def fetchall(self):
        table = self.relation.to_arrow_table()
        return [tuple(NativeCell(
            kind, restore(scalar(table.column(index)[row]['public_value']), kind),
            table.column(index)[row]['original'].as_py())
            for index, kind in enumerate(self.kinds))
            for row in range(table.num_rows)]

    def close(self):
        self.relation = None
        self.kinds = None
        if not self.lossless:
            self.connection.execute('SET arrow_lossless_conversion=false')


def public_values(values):
    return {name: deepcopy(value.public) if isinstance(value, NativeCell)
            else deepcopy(value) for name, value in values.items()}


def identity_predicate(quote_name, identity):
    clauses, parameters = [], []
    originals = dict(zip(identity.key_columns, identity.key_values))
    originals.update({name: value for name, value in identity.original.items()
                      if name not in originals})
    for name, value in originals.items():
        if not isinstance(value, NativeCell):
            raise RelationalClientError('Native row identity needs a fresh page')
        source, bound = value.binding()
        clauses.append(quote_name(name) + ' IS NOT DISTINCT FROM ' + source)
        parameters.extend(bound)
    return ' AND '.join(clauses), tuple(parameters)
