"""Native scalar editor hints and lossless grid transport."""
from decimal import Decimal

from .query_values import normalize_value  # noqa: F401
from .query_columns import describe_columns
from .character_metadata import identifier


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
                 'DECFLOAT(16)': 'decfloat', 'DECFLOAT(34)': 'decfloat',
                 'BOOLEAN': 'boolean'}.get(native))
        if native == 'BLOB' and metadata['native_subtype'] == 1:
            kind = 'text'
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
