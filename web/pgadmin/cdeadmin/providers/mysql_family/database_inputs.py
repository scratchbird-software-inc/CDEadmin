"""Typed database operation records at the native MySQL input boundary.

The original scalar lists, Shell mappings and native histogram arrays remain
valid API inputs. Descriptor grids add records without changing native options.
"""
from copy import deepcopy
import json
import math
import re
from collections.abc import Mapping

from ...sdk import RelationalClientError

OPERATIONS = frozenset({'analyze_tables', 'check_tables', 'optimize_tables',
                        'repair_tables', 'checksum_tables', 'backup_logical',
                        'verify_logical', 'restore_logical'})


def _text(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise RelationalClientError('Select a nonempty native text value')
    return value


def _mapping(value, option):
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    if not isinstance(value, list):
        raise RelationalClientError('Select structured Shell filter records')
    result = {}
    child = 'partitions' if option == 'partitions' else 'condition'
    for row in value:
        if not isinstance(row, Mapping) or set(row) != {'table', child}:
            raise RelationalClientError('A Shell filter record is invalid')
        table = _text(row['table'])
        if table in result:
            raise RelationalClientError('A Shell filter table is duplicated')
        item = row[child]
        if option == 'partitions':
            if not isinstance(item, list):
                raise RelationalClientError('Select a list of partition names')
            names = []
            for part in item:
                if isinstance(part, Mapping):
                    if set(part) != {'value'}:
                        raise RelationalClientError('A partition record is invalid')
                    part = part['value']
                names.append(_text(part))
            item = names
        else:
            item = _text(item)
        result[table] = item
    return result


def _integer(value, minimum, maximum):
    if isinstance(value, str) and re.fullmatch(r'-?(?:0|[1-9][0-9]*)', value):
        value = int(value)
    if type(value) is not int or not minimum <= value <= maximum:
        raise RelationalClientError('A histogram integer is outside its native range')
    return value


def _frequency(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise RelationalClientError('A histogram frequency must be between zero and one')
    # MySQL requires JSON DOUBLE for frequencies, including the endpoints.
    return float(value)


def _bound(value, kind):
    value = _text(value)
    if kind in {'int', 'enum', 'set', 'uint'}:
        return _integer(value, 0 if kind == 'uint' else -(2**63),
                        2**64-1 if kind == 'uint' else 2**63-1)
    if kind in {'double', 'decimal'}:
        try:
            number = json.loads(value)
            if type(number) not in (int, float) or not math.isfinite(number):
                raise ValueError()
            return float(number) if kind == 'double' else number
        except (ValueError, OverflowError):
            raise RelationalClientError('Select a finite native histogram number') from None
    if kind not in {'string', 'date', 'datetime', 'time'}:
        raise RelationalClientError('Select a supported native histogram data type')
    return value


def _histogram(value):
    if not isinstance(value, Mapping):
        raise RelationalClientError('Select structured histogram data')
    result = deepcopy(dict(value))
    rows = result.get('buckets')
    if rows == []:
        result['sampling-rate'] = _frequency(result.get('sampling-rate'))
        result['null-values'] = _frequency(result.get('null-values'))
    # Existing exported histograms already contain native arrays. Only the new
    # record representation needs conversion; preserve the original API.
    if not isinstance(rows, list) or not any(isinstance(row, Mapping) for row in rows):
        return result
    kind, data_type = result.get('histogram-type'), result.get('data-type')
    if kind not in {'singleton', 'equi-height'}:
        raise RelationalClientError('Select a native histogram type')
    buckets = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) - {'lower', 'upper', 'frequency', 'distinct'}:
            raise RelationalClientError('A histogram bucket record is invalid')
        lower = _bound(row.get('lower'), data_type)
        frequency = _frequency(row.get('frequency'))
        if kind == 'singleton':
            if row.get('upper') not in (None, '') or row.get('distinct') not in (None, ''):
                raise RelationalClientError('Singleton buckets have no upper bound or distinct count')
            buckets.append([lower, frequency])
        else:
            buckets.append([lower, _bound(row.get('upper'), data_type), frequency,
                            _integer(row.get('distinct'), 1, 2**64-1)])
    result['buckets'] = buckets
    result['sampling-rate'] = _frequency(result.get('sampling-rate'))
    result['null-values'] = _frequency(result.get('null-values'))
    return result


def normalize(operation, draft):
    if not isinstance(draft, Mapping):
        raise RelationalClientError('Select structured database operation inputs')
    result = deepcopy(dict(draft))
    if operation == 'backup_logical':
        for name in ('partitions', 'where'):
            if name in result:
                result[name] = _mapping(result[name], name)
    if operation == 'analyze_tables' and result.get('histogram_data') is not None:
        result['histogram_data'] = _histogram(result['histogram_data'])
    return result
