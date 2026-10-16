"""MariaDB typed native data plans; no implicit temporal-history restoration."""
import hashlib
import re
from .mysql_data_import import read, MySQLDataApplications
from .mariadb_schema_plan import root as catalog_root, address
from .mysql_test_data import generated
from .firebird_schema_plan import digest
from ..providers.mysql_family.mariadb_data_capture import LAYOUT_FIELDS
from ..providers.mysql_family.mariadb_values import parameter


def bound(value, column):
    if isinstance(value, dict) and value.get('encoding') == 'base64':
        allowed = {'encoding', 'data', 'byte_length', 'native_charset', 'charset_id'}
        if set(value) - allowed:
            raise ValueError('Unknown native binary transport fields')
        raw = parameter({key: item for key, item in value.items() if key in {'encoding', 'data', 'byte_length'}})
        if 'native_charset' in value:
            charset = value['native_charset']
            if charset != column.get('character_set_name') or not isinstance(charset, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}', charset):
                raise ValueError('Opaque text charset differs from the native column')
            return 'CONVERT(%s USING ' + charset + ')', [raw]
        if column['column_type'].split('(')[0].lower() in {'geometry', 'point', 'linestring', 'polygon', 'multipoint', 'multilinestring', 'multipolygon', 'geometrycollection'}:
            if len(raw) < 9:
                raise ValueError('Native geometry bytes are incomplete')
            return 'ST_GeomFromWKB(%s,%s)', [raw[4:], int.from_bytes(raw[:4], 'little')]
        if column['column_type'].split('(')[0].lower() == 'vector':
            # Connector bytes can arrive with the connection character set.
            # VECTOR requires binary charset, without re-encoding float32 data.
            import math
            import struct
            dimension = re.fullmatch(r'vector\((\d+)\)', column['column_type'], re.I)
            if (not dimension or len(raw) != 4 * int(dimension[1]) or
                    not all(math.isfinite(item[0]) for item in struct.iter_unpack('<f', raw))):
                raise ValueError('Native VECTOR dimensions or finite float32 values differ')
            return 'CAST(%s AS BINARY)', [raw]
        return '%s', [raw]
    return '%s', [parameter(value)]


def plan_digest(plan):
    return digest({key: value for key, value in plan.items() if key != 'execution_sha256'})


def preview(source, current, *, table=None, allow_nontransactional=False, node='node'):
    if type(allow_nontransactional) is not bool:
        raise ValueError('Nontransactional acknowledgement must be boolean')
    metadata, rows = read(source, node, engine='mariadb')
    acquisition = metadata['acquisition']
    database, identity, context = catalog_root(current)
    table = acquisition['relation'] if table is None else table
    selected = [row for row in current['rows'].values() if row['kind'] == 'table' and row['name'] == table and row.get('system') == 'false']
    if len(selected) != 1:
        raise ValueError('Select one exact native destination table')
    target = selected[0]
    address(target, database)
    native = target['native']
    captured = acquisition['native_columns']
    available = native.get('children', {}).get('COLUMNS', [])
    by_name = {row['column_name']: row for row in available}
    columns = [row.get('native_name') for row in metadata['schema']['columns']]
    if (len(by_name) != len(available) or columns != [row.get('column_name') for row in captured] or
            len(set(columns)) != len(columns) or set(columns) != set(by_name)):
        raise ValueError('Archived columns differ from the destination native layout')
    projection = lambda row: {key: row.get(key) for key in LAYOUT_FIELDS}
    if any(projection(column) != projection(by_name[column['column_name']]) for column in captured):
        raise ValueError('Native column types, character sets, generated expressions or spatial layout differ')
    positions = [i for i, name in enumerate(columns) if not generated(by_name[name]) and not re.search(r'AS ROW (?:START|END)', by_name[name].get('extra', ''), re.I)]
    insert_columns = [columns[i] for i in positions]
    if not insert_columns:
        raise ValueError('The destination has no explicit writable columns')
    values = [[row[i] for i in positions] for row in rows]
    for row in values:
        for value, name in zip(row, insert_columns):
            bound(value, by_name[name])
    mode = acquisition.get('sql_mode')
    if not isinstance(mode, str) or not re.fullmatch(r'[A-Z_,]*', mode):
        raise ValueError('Native source SQL mode is unavailable')
    engine = native.get('catalog_row', {}).get('engine')
    nontransactional = engine != 'InnoDB'
    primary_key = any(row.get('index_name') == 'PRIMARY'
                      for row in native.get('children', {}).get('STATISTICS', []))
    result = {'format': 'scratchrobin.mariadb.data-import-plan@1', 'database': database, 'table': table,
        'server_uid': identity['server_uid'], 'endpoint_id': current['provenance']['endpoint_id'],
        'database_target_id': current['provenance']['database_target_id'], 'resource_id': target['resource_id'],
        'native_definition_sha256': digest(native.get('definition')),
        'system_versioned': native.get('catalog_row', {}).get('table_type') == 'SYSTEM VERSIONED',
        'native_columns': [projection(row) for row in sorted(available, key=lambda row: int(row.get('ordinal_position', 0)))], 'columns': insert_columns, 'rows': values,
        'row_count': len(values), 'storage_engine': engine, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'sql_mode': ','.join(dict.fromkeys([*filter(None, mode.split(',')), 'NO_AUTO_VALUE_ON_ZERO'])),
        'catalog_sql_mode': context['sql_mode'], 'time_zone': '+00:00',
        'source_coverage': {'mode': acquisition.get('mode'), 'more_rows_observed': acquisition.get('more_rows_observed')},
        'nontransactional_acknowledged': allow_nontransactional, 'ready_for_review': bool(values) and (not nontransactional or allow_nontransactional),
        'warnings': ['Import explicitly inserts and commits the displayed rows on an independently owned connection.',
                     'Constraints, triggers and native privileges remain active. AUTO_INCREMENT allocation and external trigger effects may survive rollback.'] +
                    (['System-versioned imports insert current rows with native new system-time boundaries; archived history and old boundaries are not restored.'] if native.get('catalog_row', {}).get('table_type') == 'SYSTEM VERSIONED' else []) +
                    (['The destination engine is nontransactional; acknowledged rows may survive any later refusal or rollback.'] if nontransactional else []) +
                    (['The table has no primary key; insert acknowledgements are retained, but exact row rediscovery cannot be confirmed.'] if not primary_key else []) +
                    (['The source is a bounded sample; additional source rows are omitted.'] if acquisition.get('more_rows_observed') else [])}
    result['execution_sha256'] = plan_digest(result)
    return result


class MariaDBDataApplications(MySQLDataApplications):
    format = 'scratchrobin.mariadb.data-import-plan@1'
