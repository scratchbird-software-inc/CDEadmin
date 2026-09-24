"""Native scalar editor hints and lossless grid transport."""
from decimal import Decimal
from datetime import date, datetime, time
import base64
import math
import re
import struct
from collections.abc import Mapping

from pgadmin.cdeadmin.sdk.relational import RelationalClientError

from .query_values import normalize_value as normalize_query_value
from .query_columns import describe_columns
from .character_metadata import identifier


def parameter(value):
    """Native temporal text avoids driver timestamp range/precision loss."""
    if isinstance(value, (datetime, time)) and value.tzinfo is None:
        clock = f'{value.hour:02}:{value.minute:02}:{value.second:02}'
        if value.microsecond:
            if value.microsecond % 100:
                raise ValueError(
                    'Firebird temporal precision is 100 microseconds')
            clock += f'.{value.microsecond // 100:04}'
        return (value.date().isoformat() + ' ' + clock
                if isinstance(value, datetime) else clock)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    return value


def normalize_value(value):
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]
    # JS String(-0) and JSON.stringify(-0) both erase its sign. Transport all
    # approximate numerics as round-trip text; the native type remains visible.
    if isinstance(value, float):
        return repr(value)
    return normalize_query_value(parameter(value))


def bind_value(value):
    """Decode explicit wire envelopes; never guess ordinary text encodings."""
    if not isinstance(value, Mapping):
        return value
    if value.get('encoding') in {'float32', 'float64'}:
        if set(value) != {'encoding', 'data'} or not isinstance(
                value.get('data'), str):
            raise RelationalClientError('Firebird float envelope is invalid')
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
                            r'(?:[eE][+-]?\d+)?', value['data'], re.ASCII):
            raise RelationalClientError(
                'Firebird floating-point value invalid')
        try:
            number = float(value['data'])
        except ValueError:
            raise RelationalClientError(
                'Firebird floating-point value invalid')
        if not math.isfinite(number):
            raise RelationalClientError('Firebird floating-point value must '
                                        'be finite and within binary64 range')
        if number == 0 and any(character in '123456789' for character in
                               value['data'].lower().split('e')[0]):
            raise RelationalClientError('Firebird DOUBLE is below '
                                        'nonzero binary64 range')
        if value['encoding'] == 'float32':
            try:
                narrowed = struct.unpack('f', struct.pack('f', number))[0]
            except OverflowError:
                raise RelationalClientError('Firebird FLOAT exceeds '
                                            'finite binary32 range')
            if not math.isfinite(narrowed):
                raise RelationalClientError('Firebird FLOAT exceeds '
                                            'finite binary32 range')
            if number and narrowed == 0:
                raise RelationalClientError('Firebird FLOAT is below '
                                            'nonzero binary32 range')
            number = narrowed
        return number
    if (set(value) != {'encoding', 'data', 'byte_length'} or
            value.get('encoding') != 'base64' or
            not isinstance(value.get('data'), str) or
            type(value.get('byte_length')) is not int):
        raise RelationalClientError(
            'Firebird binary value envelope is invalid')
    try:
        binary = base64.b64decode(value['data'], validate=True)
    except (ValueError, UnicodeError):
        raise RelationalClientError('Firebird binary value is not base64')
    if (len(binary) != value['byte_length'] or
            base64.b64encode(binary).decode('ascii') != value['data']):
        raise RelationalClientError('Firebird binary value length/encoding '
                                    'does not match its envelope')
    return binary


def input_kind(native_type):
    for value_type, kind in ((str, 'text'), (int, 'integer'),
                             (Decimal, 'decimal'), (bool, 'boolean')):
        if native_type is value_type:
            return kind
    return None


def materialize(value):
    # Identity predicates need native values, not their wire encoding.
    # Consume a native stream before deepcopy or releasing the cursor.
    from firebird.driver.core import BlobReader
    if isinstance(value, BlobReader):
        try:
            return value.read()
        finally:
            value.close()
    return value


def input_kinds(cursor):
    kinds = []
    for description, metadata in zip(cursor.description or (),
                                     describe_columns(cursor)):
        if metadata['metadata_source'] != 'firebird-driver.IMessageMetadata':
            kinds.append(input_kind(description[1]))
            continue
        native = metadata['native_type']
        kind = ({'CHAR': 'text', 'VARCHAR': 'text', 'SMALLINT': 'integer',
                 'INTEGER': 'integer', 'BIGINT': 'integer',
                 'INT128': 'integer',
                 'NUMERIC': 'decimal', 'DECIMAL': 'decimal',
                 'FLOAT': 'float32', 'DOUBLE PRECISION': 'float64',
                 'DECFLOAT(16)': 'decfloat', 'DECFLOAT(34)': 'decfloat',
                 'DATE': 'text', 'TIME': 'text', 'TIMESTAMP': 'text',
                 'BOOLEAN': 'boolean'}.get(native))
        if native == 'BLOB' and metadata['native_subtype'] == 1:
            kind = 'text'
        elif (native in {'CHAR CHARACTER SET OCTETS',
                         'VARCHAR CHARACTER SET OCTETS'} or
              native == 'BLOB' and metadata['native_subtype'] == 0):
            kind = 'binary'
        kinds.append(kind)
    return tuple(kinds)


def table_operations(connection, name, columns):
    """Prepare only: do not run trigger/DML probes to discover permissions."""
    import firebird.driver as native
    result = {'update': [], 'insert': [], 'delete': False, 'defaults': False}
    with connection.cursor() as cursor:
        def admitted(source):
            statement = None
            try:
                statement = cursor.prepare(source)
                return True
            except native.DatabaseError:
                return False
            finally:
                if statement is not None:
                    statement.free()
        table = identifier(name)
        for column in columns:
            field = identifier(column)
            if admitted(f'UPDATE {table} SET {field} = ? WHERE 1 = 0'):
                result['update'].append(column)
            if admitted(f'INSERT INTO {table} ({field}) VALUES (?)'):
                result['insert'].append(column)
        result['delete'] = admitted(f'DELETE FROM {table} WHERE 1 = 0')
        result['defaults'] = admitted(f'INSERT INTO {table} DEFAULT VALUES')
    return result
