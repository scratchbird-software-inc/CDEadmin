"""Exact DuckDB Arrow presentation and native parameter/write envelopes."""
import base64
import datetime
import decimal
import math
import re
import sys
import uuid

from pgadmin.cdeadmin.sdk import RelationalClientError

SAFE_INTEGER = 2**53 - 1

INTEGER_RANGES = {
    'TINYINT': (-(2**7), 2**7 - 1),
    'SMALLINT': (-(2**15), 2**15 - 1),
    'INTEGER': (-(2**31), 2**31 - 1),
    'INT': (-(2**31), 2**31 - 1),
    'INT4': (-(2**31), 2**31 - 1),
    'BIGINT': (-(2**63), 2**63 - 1),
    'INT8': (-(2**63), 2**63 - 1),
    'HUGEINT': (-(2**127), 2**127 - 1),
    'UTINYINT': (0, 2**8 - 1),
    'USMALLINT': (0, 2**16 - 1),
    'UINTEGER': (0, 2**32 - 1),
    'UBIGINT': (0, 2**64 - 1),
    'UHUGEINT': (0, 2**128 - 1),
}

ADMITTED_TEMPORAL_TYPES = {
    'DATE': 'DATE',
    'TIME': 'TIME',
    'TIMETZ': 'TIMETZ',
    'TIME WITH TIME ZONE': 'TIMETZ',
    'TIMESTAMP': 'TIMESTAMP',
    'TIMESTAMP_S': 'TIMESTAMP_S',
    'TIMESTAMP_MS': 'TIMESTAMP_MS',
    'TIMESTAMP_NS': 'TIMESTAMP_NS',
    'TIMESTAMPTZ': 'TIMESTAMPTZ',
    'TIMESTAMP WITH TIME ZONE': 'TIMESTAMPTZ',
}

_EPOCH_DATE = datetime.date(1970, 1, 1)
_EPOCH_DATETIME = datetime.datetime(1970, 1, 1)
_DATE_INF = 2147483647
_TS_INF = 9223372036854775807
_ZONE_PATTERN = re.compile(
    r'(?:Z|[+-]\d{2}(?::?\d{2})?(?::?\d{2})?|[A-Za-z_]+/[A-Za-z0-9_+-]+)\s*$',
    re.IGNORECASE,
)


def binary(data):
    return {
        'encoding': 'base64',
        'data': base64.b64encode(data).decode('ascii'),
        'byte_length': len(data),
    }


def scalar(item):
    import pyarrow as pa
    if not item.is_valid:
        return None
    kind = item.type
    if isinstance(kind, pa.BaseExtensionType):
        if kind.extension_name == 'arrow.uuid':
            return str(item.as_py())
        stored = item.value
        name = getattr(kind, 'type_name', kind.extension_name)
        if name in {'hugeint', 'uhugeint'}:
            return str(int.from_bytes(
                stored.as_py(), sys.byteorder, signed=name == 'hugeint',
            ))
        return {
            'encoding': 'duckdb-arrow-opaque',
            'native_type': name,
            'vendor': getattr(kind, 'vendor_name', None),
            'storage_type': str(kind.storage_type),
            'storage': scalar(stored),
        }
    if pa.types.is_dictionary(kind):
        return scalar(item.value)
    if pa.types.is_union(kind):
        tag = kind.type_codes.index(item.type_code)
        return {
            'tag': kind[tag].name,
            'type_code': item.type_code,
            'value': scalar(item.value),
        }
    if pa.types.is_struct(kind):
        return {field.name: scalar(item[field.name]) for field in kind}
    if pa.types.is_map(kind):
        return {
            'encoding': 'map',
            'entries': [
                [scalar(pair['key']), scalar(pair['value'])]
                for pair in item.values
            ],
        }
    if (pa.types.is_list(kind) or pa.types.is_large_list(kind) or
            pa.types.is_fixed_size_list(kind) or pa.types.is_list_view(kind) or
            pa.types.is_large_list_view(kind)):
        return [scalar(child) for child in item.values]
    if pa.types.is_interval(kind):
        interval = item.as_py()
        return {
            'months': interval.months,
            'days': interval.days,
            'nanoseconds': str(interval.nanoseconds),
        }
    if pa.types.is_temporal(kind):
        return {
            'encoding': 'temporal-ticks',
            'arrow_type': str(kind),
            'ticks': str(item.value),
        }
    value = item.as_py()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > SAFE_INTEGER else value
    if isinstance(value, (float, decimal.Decimal)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return binary(bytes(value))
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str) or value is None:
        return value
    raise RelationalClientError('DuckDB Arrow value is not representable')


def _parse_int_string(raw, label):
    if type(raw) is int and abs(raw) <= SAFE_INTEGER:
        return raw
    if isinstance(raw, str) and re.fullmatch(r'-?(0|[1-9][0-9]*)', raw):
        return int(raw)
    raise RelationalClientError(f'DuckDB {label} requires an exact integer string')


def temporal_ticks_to_sql_text(arrow_type, ticks_raw):
    """Convert an exact Arrow temporal tick count to canonical SQL text + type."""
    if not isinstance(arrow_type, str) or not arrow_type:
        raise RelationalClientError('DuckDB temporal-ticks requires arrow_type')
    ticks = _parse_int_string(ticks_raw, 'temporal ticks')
    if arrow_type == 'date32[day]':
        if ticks == _DATE_INF:
            return 'DATE', 'infinity'
        if ticks == -_DATE_INF:
            return 'DATE', '-infinity'
        try:
            day = _EPOCH_DATE + datetime.timedelta(days=ticks)
        except OverflowError:
            raise RelationalClientError('DuckDB DATE ticks exceed representable range') from None
        return 'DATE', day.isoformat()
    if arrow_type == 'time64[us]':
        if ticks < 0 or ticks > 86_400_000_000:
            raise RelationalClientError('DuckDB TIME ticks must be between 00:00:00 and 24:00:00')
        if ticks == 86_400_000_000:
            return 'TIME', '24:00:00'
        seconds, micros = divmod(ticks, 1_000_000)
        minutes, secs = divmod(seconds, 60)
        hours, mins = divmod(minutes, 60)
        return 'TIME', f'{hours:02d}:{mins:02d}:{secs:02d}.{micros:06d}'
    if arrow_type == 'timestamp[s]':
        if abs(ticks) >= _TS_INF:
            raise RelationalClientError('DuckDB TIMESTAMP_S does not admit infinity ticks')
        try:
            dt = _EPOCH_DATETIME + datetime.timedelta(seconds=ticks)
        except OverflowError:
            raise RelationalClientError('DuckDB TIMESTAMP_S ticks exceed range') from None
        return 'TIMESTAMP_S', dt.strftime('%Y-%m-%d %H:%M:%S')
    if arrow_type == 'timestamp[ms]':
        if abs(ticks) >= _TS_INF:
            raise RelationalClientError('DuckDB TIMESTAMP_MS does not admit infinity ticks')
        seconds, millis = divmod(ticks, 1_000)
        try:
            dt = _EPOCH_DATETIME + datetime.timedelta(seconds=seconds)
        except OverflowError:
            raise RelationalClientError('DuckDB TIMESTAMP_MS ticks exceed range') from None
        return 'TIMESTAMP_MS', f"{dt.strftime('%Y-%m-%d %H:%M:%S')}.{millis:03d}"
    if arrow_type == 'timestamp[us]' or arrow_type.startswith('timestamp[us, tz='):
        sql_type = 'TIMESTAMPTZ' if 'tz=' in arrow_type else 'TIMESTAMP'
        if ticks == _TS_INF:
            return sql_type, 'infinity'
        if ticks == -_TS_INF:
            return sql_type, '-infinity'
        seconds, micros = divmod(ticks, 1_000_000)
        try:
            dt = _EPOCH_DATETIME + datetime.timedelta(seconds=seconds)
        except OverflowError:
            raise RelationalClientError(f'DuckDB {sql_type} ticks exceed range') from None
        suffix = '+00:00' if sql_type == 'TIMESTAMPTZ' else ''
        return sql_type, f"{dt.strftime('%Y-%m-%d %H:%M:%S')}.{micros:06d}{suffix}"
    if arrow_type == 'timestamp[ns]':
        if abs(ticks) >= _TS_INF:
            raise RelationalClientError('DuckDB TIMESTAMP_NS ticks exceed int64 nanosecond range')
        seconds, nanos = divmod(ticks, 1_000_000_000)
        try:
            dt = _EPOCH_DATETIME + datetime.timedelta(seconds=seconds)
        except OverflowError:
            raise RelationalClientError('DuckDB TIMESTAMP_NS ticks exceed calendar range') from None
        return 'TIMESTAMP_NS', f"{dt.strftime('%Y-%m-%d %H:%M:%S')}.{nanos:09d}"
    raise RelationalClientError(f'Unsupported DuckDB temporal-ticks arrow_type: {arrow_type}')


def decode_interval_components(value):
    allowed = {'encoding', 'months', 'days', 'microseconds', 'nanoseconds'}
    if set(value) - allowed or ('microseconds' in value and 'nanoseconds' in value):
        raise RelationalClientError('DuckDB interval envelope fields are invalid')
    if 'months' not in value or 'days' not in value or (
        'microseconds' not in value and 'nanoseconds' not in value
    ):
        raise RelationalClientError('DuckDB interval requires months, days, and microseconds/nanoseconds')
    months = _parse_int_string(value['months'], 'interval months')
    days = _parse_int_string(value['days'], 'interval days')
    if not (-(2**31) <= months < 2**31) or not (-(2**31) <= days < 2**31):
        raise RelationalClientError('DuckDB interval months/days exceed 32-bit signed range')
    if 'nanoseconds' in value:
        nanos = _parse_int_string(value['nanoseconds'], 'interval nanoseconds')
        if nanos % 1000 != 0:
            raise RelationalClientError(
                'DuckDB INTERVAL has microsecond precision; sub-microsecond nanoseconds fail closed'
            )
        micros = nanos // 1000
    else:
        micros = _parse_int_string(value['microseconds'], 'interval microseconds')
    if not (-(2**63) <= micros < 2**63):
        raise RelationalClientError('DuckDB interval microseconds exceed 64-bit signed range')
    return months, days, micros


def validate_decimal_string(data, max_precision=38, max_scale=None):
    if not isinstance(data, str) or not re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?', data):
        raise RelationalClientError('DuckDB decimal is invalid')
    digits = data.lstrip('-').split('.')
    int_digits = len(digits[0].lstrip('0'))
    scale = len(digits[1]) if len(digits) > 1 else 0
    if max_scale is not None:
        if scale > max_scale:
            raise RelationalClientError(
                f'DuckDB decimal scale {scale} exceeds column scale {max_scale}'
            )
        if int_digits > (max_precision - max_scale):
            raise RelationalClientError(
                f'DuckDB decimal integer digits ({int_digits}) exceed DECIMAL({max_precision},{max_scale})'
            )
        return max_precision, max_scale
    precision = max(1, int_digits + scale)
    if precision > 38 or scale > 38:
        raise RelationalClientError('DuckDB decimal exceeds precision')
    return precision, scale


def _typed_value(text, sql_type):
    import duckdb
    try:
        return duckdb.Value(text, duckdb.sqltype(sql_type))
    except Exception:
        raise RelationalClientError(f'DuckDB {sql_type} parameter value is invalid') from None


def parameter(value):
    import duckdb
    if isinstance(value, dict):
        if 'encoding' in value:
            encoding = value.get('encoding')
            if encoding == 'duckdb-arrow-opaque':
                raise RelationalClientError(
                    'Opaque DuckDB Arrow presentation envelopes cannot be bound directly; '
                    'use an explicit typed input envelope'
                )
            if encoding == 'struct':
                if set(value) != {'encoding', 'fields'} or not isinstance(value['fields'], dict):
                    raise RelationalClientError('DuckDB struct envelope requires a fields object')
                if not all(isinstance(k, str) for k in value['fields']):
                    raise RelationalClientError('DuckDB struct keys must be text')
                return {k: parameter(v) for k, v in value['fields'].items()}
            if encoding in {'integer', 'decimal', 'base64'}:
                extra_allowed = {'encoding', 'data', 'byte_length', 'native_type', 'precision', 'scale'}
                if set(value) - extra_allowed:
                    raise RelationalClientError('DuckDB parameter fields invalid')
                data = value.get('data')
                if not isinstance(data, str):
                    raise RelationalClientError('DuckDB exact parameter needs text')
                if encoding == 'base64':
                    if set(value) - {'encoding', 'data', 'byte_length'}:
                        raise RelationalClientError('DuckDB binary parameter fields invalid')
                    try:
                        result = base64.b64decode(data, validate=True)
                    except Exception:
                        raise RelationalClientError('DuckDB binary parameter is invalid') from None
                    if 'byte_length' in value and value['byte_length'] != len(result):
                        raise RelationalClientError('DuckDB binary length differs')
                    return result
                if encoding == 'integer':
                    if set(value) - {'encoding', 'data', 'native_type'}:
                        raise RelationalClientError('DuckDB integer parameter fields invalid')
                    if not re.fullmatch(r'-?(0|[1-9][0-9]*)', data):
                        raise RelationalClientError('DuckDB integer is invalid')
                    integer = int(data)
                    requested = value.get('native_type')
                    if requested is not None:
                        key = str(requested).strip().upper()
                        if key == 'BIGNUM':
                            return _typed_value(data, 'BIGNUM')
                        bounds = INTEGER_RANGES.get(key)
                        if bounds is None:
                            raise RelationalClientError('Unsupported DuckDB integer native_type')
                        if not (bounds[0] <= integer <= bounds[1]):
                            raise RelationalClientError(f'DuckDB integer out of {key} range')
                        return duckdb.Value(integer if key != 'BIGNUM' and abs(integer) <= SAFE_INTEGER else data,
                                            duckdb.sqltype(key))
                    if -(2**127) <= integer < 2**127:
                        kind = 'HUGEINT'
                    elif 0 <= integer < 2**128:
                        kind = 'UHUGEINT'
                    else:
                        kind = 'BIGNUM'
                    return duckdb.Value(data, duckdb.sqltype(kind))
                if set(value) - {'encoding', 'data', 'precision', 'scale'}:
                    raise RelationalClientError('DuckDB decimal parameter fields invalid')
                req_prec = value.get('precision')
                req_scale = value.get('scale')
                if (req_prec is None) != (req_scale is None):
                    raise RelationalClientError('DuckDB decimal requires both precision and scale when specified')
                if req_prec is not None:
                    if type(req_prec) is not int or type(req_scale) is not int or not (1 <= req_prec <= 38) or not (0 <= req_scale <= req_prec):
                        raise RelationalClientError('DuckDB decimal precision/scale invalid')
                    precision, scale = validate_decimal_string(data, req_prec, req_scale)
                else:
                    precision, scale = validate_decimal_string(data)
                return _typed_value(data, f'DECIMAL({precision},{scale})')
            if encoding == 'bit':
                if set(value) != {'encoding', 'data'}:
                    raise RelationalClientError('DuckDB bit parameter fields invalid')
                data = value.get('data')
                if not isinstance(data, str) or not data or any(ch not in '01' for ch in data):
                    raise RelationalClientError('DuckDB BIT parameter must be a non-empty binary string of 0 and 1')
                return _typed_value(data, 'BIT')
            if encoding == 'uuid':
                if set(value) != {'encoding', 'data'}:
                    raise RelationalClientError('DuckDB uuid parameter fields invalid')
                data = value.get('data')
                if not isinstance(data, str):
                    raise RelationalClientError('DuckDB UUID parameter must be text')
                try:
                    canonical = str(uuid.UUID(data))
                except Exception:
                    raise RelationalClientError('DuckDB UUID parameter is invalid') from None
                return _typed_value(canonical, 'UUID')
            if encoding == 'temporal-ticks':
                if set(value) != {'encoding', 'arrow_type', 'ticks'}:
                    raise RelationalClientError('DuckDB temporal-ticks parameter fields invalid')
                sql_type, sql_text = temporal_ticks_to_sql_text(
                    value.get('arrow_type'), value.get('ticks'),
                )
                return _typed_value(sql_text, sql_type)
            if encoding == 'temporal':
                if set(value) != {'encoding', 'native_type', 'data'}:
                    raise RelationalClientError('DuckDB temporal parameter fields invalid')
                raw_type = str(value.get('native_type') or '').strip().upper()
                sql_type = ADMITTED_TEMPORAL_TYPES.get(raw_type)
                data = value.get('data')
                if sql_type is None or not isinstance(data, str) or not data.strip():
                    raise RelationalClientError('DuckDB temporal parameter requires an admitted native_type and text')
                text = data.strip()
                if sql_type in {'TIMETZ', 'TIMESTAMPTZ'} and text.lower() not in {'infinity', '-infinity'}:
                    if not _ZONE_PATTERN.search(text):
                        raise RelationalClientError(f'DuckDB {sql_type} parameter requires an explicit timezone or offset')
                return _typed_value(text, sql_type)
            if encoding == 'interval':
                months, days, micros = decode_interval_components(value)
                return _typed_value(
                    f'{months} months {days} days {micros} microseconds', 'INTERVAL',
                )
            if encoding == 'map':
                if set(value) != {'encoding', 'key_type', 'value_type', 'entries'}:
                    raise RelationalClientError('DuckDB map parameter requires key_type, value_type, and entries')
                entries = value.get('entries')
                if not isinstance(entries, list):
                    raise RelationalClientError('DuckDB map entries must be a list of [key, value] pairs')
                try:
                    map_type = duckdb.sqltype(f"MAP({value['key_type']}, {value['value_type']})")
                except Exception:
                    raise RelationalClientError('DuckDB map key_type/value_type is invalid') from None
                if map_type.id != 'map':
                    raise RelationalClientError('DuckDB map type did not resolve to MAP')
                keys, vals, seen = [], [], []
                for pair in entries:
                    if not isinstance(pair, (list, tuple)) or len(pair) != 2 or pair[0] is None:
                        raise RelationalClientError('DuckDB map entry must be a [non-null key, value] pair')
                    bound_k = parameter(pair[0])
                    if bound_k in seen:
                        raise RelationalClientError('DuckDB map keys must be unique')
                    seen.append(bound_k)
                    keys.append(bound_k)
                    vals.append(parameter(pair[1]))
                try:
                    return duckdb.Value({'key': keys, 'value': vals}, map_type)
                except Exception:
                    raise RelationalClientError('DuckDB map parameter entries failed native type check') from None
            if encoding == 'union':
                if set(value) != {'encoding', 'union_type', 'tag', 'value'}:
                    raise RelationalClientError('DuckDB union parameter requires union_type, tag, and value')
                tag = value.get('tag')
                if not isinstance(tag, str) or not tag:
                    raise RelationalClientError('DuckDB union tag must be text')
                try:
                    u_type = duckdb.sqltype(str(value['union_type']))
                except Exception:
                    raise RelationalClientError('DuckDB union_type is invalid') from None
                if u_type.id != 'union':
                    raise RelationalClientError('DuckDB union_type did not resolve to UNION')
                members = list(u_type.children[1:])
                member_map = dict(members)
                if tag not in member_map:
                    raise RelationalClientError(f'DuckDB union tag {tag!r} is not a member of {u_type}')
                member_types = [str(tp) for _, tp in members]
                if len(set(member_types)) != len(member_types):
                    raise RelationalClientError(
                        'DuckDB Python parameter binding cannot disambiguate duplicate member types in UNION; '
                        'bind the member value and construct with union_value(tag := $param)'
                    )
                inner = parameter(value['value'])
                if inner is None:
                    raise RelationalClientError(
                        'DuckDB Python parameter binding cannot tag a NULL union member; '
                        'use union_value(tag := CAST(NULL AS ...)) or structured row DML'
                    )
                try:
                    return duckdb.Value(inner, u_type)
                except Exception:
                    raise RelationalClientError('DuckDB union parameter value failed native type check') from None
            if encoding in {'list', 'array'}:
                expected_keys = {'encoding', 'element_type', 'items'} | ({'size'} if encoding == 'array' else set())
                if set(value) != expected_keys or not isinstance(value.get('items'), list):
                    raise RelationalClientError(f'DuckDB {encoding} parameter fields invalid')
                if encoding == 'array':
                    size = value.get('size')
                    if type(size) is not int or size <= 0 or len(value['items']) != size:
                        raise RelationalClientError('DuckDB fixed ARRAY parameter length mismatch')
                    type_spec = f"({value['element_type']})[{size}]"
                    try:
                        target_type = duckdb.sqltype(f"{value['element_type']}[{size}]")
                    except Exception:
                        try:
                            target_type = duckdb.sqltype(type_spec)
                        except Exception:
                            raise RelationalClientError('DuckDB array element_type is invalid') from None
                else:
                    try:
                        target_type = duckdb.sqltype(f"{value['element_type']}[]")
                    except Exception:
                        raise RelationalClientError('DuckDB list element_type is invalid') from None
                items = [parameter(item) for item in value['items']]
                try:
                    return duckdb.Value(items, target_type)
                except Exception:
                    raise RelationalClientError(f'DuckDB {encoding} parameter items failed native type check') from None
            raise RelationalClientError(f'Unsupported DuckDB parameter encoding: {encoding!r}')
        if not all(isinstance(key, str) for key in value):
            raise RelationalClientError('DuckDB struct keys must be text')
        return {key: parameter(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [parameter(child) for child in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int) and abs(value) <= SAFE_INTEGER:
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise RelationalClientError('DuckDB parameter needs an exact envelope')


def parameters(value):
    if value is None:
        return []
    if isinstance(value, dict):
        if 'encoding' in value:
            raise RelationalClientError('Top-level DuckDB named parameter map cannot be a scalar envelope')
        if not all(isinstance(key, str) for key in value):
            raise RelationalClientError('DuckDB parameter names must be text')
        return {key: parameter(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [parameter(child) for child in value]
    raise RelationalClientError('DuckDB parameters must be an object or array')
