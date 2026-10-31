"""Typed static DDN data admission and durable, explicitly committed imports."""
from . import ddn_source as ddn
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import uuid

from .firebird_data_import import unique, safe_integer
from .firebird_schema_plan import digest
from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .mysql_schema_plan import root as catalog_root, address
from .mysql_test_data import generated
from ..providers.mysql_family.mysql_data_capture import LAYOUT_FIELDS
from ..providers.mysql_family.mysql_values import parameter

MAX_BYTES = 8 * 1024 * 1024
SLOTS = threading.BoundedSemaphore(2)


def decode(source):
    return json.loads(source, object_pairs_hook=unique, parse_int=safe_integer,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite data value')))


def _native_version_admitted(engine, observed, reference):
    """Exact for single-version profiles; SQLite captures from any admitted
    runtime (owner direction 2026-10-29: SQLite from a declared floor)."""
    if engine == 'sqlite':
        from ..providers.sqlite.provider import PROFILE
        return PROFILE.accepts_runtime_version(observed)
    return observed == reference

def read(source, node='node', *, engine='mysql'):
    versions = {'mysql': '9.7.0', 'mariadb': '12.2.2', 'postgresql': '18.3', 'duckdb': '1.5.2', 'sqlite': '3.53.0'}
    if engine not in versions:
        raise ValueError('Unsupported native data engine')
    if not isinstance(source, str) or not source or len(source.encode('utf8')) > MAX_BYTES:
        raise ValueError('Data DDN must be nonempty text within 8 MiB')
    snapshot = decode(source) if source.lstrip().startswith('{') else {
        'format': 'ddn-source-workspace@1', 'entry': 'result-1.ddn', 'view': 'result_1', 'files': {'result-1.ddn': source}}
    if (not isinstance(snapshot, dict) or set(snapshot) != {'format', 'entry', 'view', 'files'} or
            snapshot['format'] != 'ddn-source-workspace@1' or not isinstance(snapshot['files'], dict) or
            not 1 <= len(snapshot['files']) <= 64 or snapshot.get('entry') not in snapshot['files']):
        raise ValueError('Invalid static data workspace')
    if not SLOTS.acquire(timeout=1):
        raise ValueError('Data DDN reader is busy')
    try:
        result = subprocess.run([ddn.node_executable(node), ddn.NODE_HEAP_OPTION, str(Path(__file__).parent / 'ddn/read_mysql_data.mjs')],
            input=json.dumps(snapshot), text=True, encoding='utf8', capture_output=True, timeout=15,
            env=ddn.runner_environment())
        if result.returncode:
            raise ValueError('Invalid native static data DDN')
        parsed = decode(result.stdout)
        metadata = decode(parsed['header'])
        acquisition = metadata.get('acquisition', {})
        columns = metadata.get('schema', {}).get('columns', [])
        if (metadata.get('mapping') != 'scratchrobin.result.static@1' or acquisition.get('engine_id') != engine or
                not _native_version_admitted(
                    engine,
                    str(acquisition.get('native_version', '')).split('-')[0],
                    versions[engine]) or
                not acquisition.get('transaction_completed') or not 1 <= len(columns) <= 256 or
                len(parsed['rows']) != acquisition.get('rows') or not isinstance(acquisition.get('native_columns'), list)):
            raise ValueError('A native relation capture with exact column metadata is required')
        rows = []
        for record in parsed['rows']:
            row = decode(record['values'])
            display = record['display']
            if (not isinstance(row, list) or len(row) != len(columns) or
                    set(display) != {'c_' + str(i) for i in range(len(columns))} or
                    any(decode(display['c_' + str(i)]) != value for i, value in enumerate(row))):
                raise ValueError('Displayed data and positional native values differ')
            rows.append(row)
        if parsed.get('native_payload'):
            if engine != 'duckdb': raise ValueError('Unexpected native type payload')
            metadata['native_payload'] = parsed['native_payload']
        return metadata, rows
    except (OSError, subprocess.TimeoutExpired, KeyError, TypeError, RecursionError):
        raise ValueError('Data DDN could not be admitted') from None
    finally:
        SLOTS.release()


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
            return "ST_GeomFromWKB(%s,%s,'axis-order=long-lat')", [raw[4:], int.from_bytes(raw[:4], 'little')]
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
    metadata, rows = read(source, node)
    acquisition = metadata['acquisition']
    database, identity = catalog_root(current)
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
    positions = [i for i, name in enumerate(columns) if not generated(by_name[name])]
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
    result = {'format': 'scratchrobin.mysql.data-import-plan@1', 'database': database, 'table': table,
        'server_uuid': identity['server_uuid'], 'endpoint_id': current['provenance']['endpoint_id'],
        'database_target_id': current['provenance']['database_target_id'], 'resource_id': target['resource_id'],
        'native_definition_sha256': digest(native.get('definition')),
        'native_columns': [projection(row) for row in sorted(available, key=lambda row: int(row.get('ordinal_position', 0)))], 'columns': insert_columns, 'rows': values,
        'row_count': len(values), 'storage_engine': engine, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'sql_mode': ','.join(dict.fromkeys([*filter(None, mode.split(',')), 'NO_AUTO_VALUE_ON_ZERO'])),
        'catalog_sql_mode': identity['sql_mode'], 'time_zone': '+00:00',
        'source_coverage': {'mode': acquisition.get('mode'), 'more_rows_observed': acquisition.get('more_rows_observed')},
        'nontransactional_acknowledged': allow_nontransactional, 'ready_for_review': bool(values) and (not nontransactional or allow_nontransactional),
        'warnings': ['Import explicitly inserts and commits the displayed rows on an independently owned connection.',
                     'Constraints, triggers and native privileges remain active. AUTO_INCREMENT allocation and external trigger effects may survive rollback.'] +
                    (['The destination engine is nontransactional; acknowledged rows may survive any later refusal or rollback.'] if nontransactional else []) +
                    (['The table has no primary key; insert acknowledgements are retained, but exact row rediscovery cannot be confirmed.'] if not primary_key else []) +
                    (['The source is a bounded sample; additional source rows are omitted.'] if acquisition.get('more_rows_observed') else [])}
    result['execution_sha256'] = plan_digest(result)
    return result


class MySQLDataApplications(SchemaApplications):
    format = 'scratchrobin.mysql.data-import-plan@1'
    def recent(self, owner, binding):
        with self._store() as store:
            records = [row for row in store.read().get('schema_applications', {}).values()
                       if row['owner'] == owner and row['binding'] == binding]
            return [self._public(row) for row in sorted(records, key=lambda row: row['created_at'], reverse=True)[:20]]

    @staticmethod
    def _public(record):
        value = SchemaApplications._public(record)
        if 'plan' in value:
            value['plan'].pop('rows', None)
        return value

    def review(self, plan, owner, binding):
        if (plan.get('format') != self.format or not plan.get('ready_for_review') or
                not 1 <= plan.get('row_count', 0) <= 6000 or plan.get('execution_sha256') != plan_digest(plan)):
            raise SchemaApplyError('An unblocked native data import preview is required')
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed', 'owner': owner, 'binding': binding,
                  'created_at': self.clock(), 'expires_at': self.clock() + 300, 'plan': deepcopy(plan)}
        record['review_digest'] = digest(record)
        if len(json.dumps(record).encode()) > 4 * 1024 * 1024:
            raise SchemaApplyError('Data review exceeds 4 MiB; capture fewer rows')
        with self._store() as store:
            def save(state):
                records = state.setdefault('schema_applications', {})
                for key in list(records):
                    if records[key]['state'] == 'reviewed' and records[key]['expires_at'] < self.clock():
                        del records[key]
                if len(records) >= 1000:
                    raise SchemaApplyError('Data receipt capacity reached')
                records[record['review_id']] = record
            store.change(save)
        return self._public(record)

    def apply(self, request, owner, binding, execute):
        if (not isinstance(request, dict) or set(request) != {'review_id', 'review_digest', 'confirmed'} or
                request['confirmed'] is not True or not isinstance(request['review_id'], str) or
                not isinstance(request['review_digest'], str)):
            raise SchemaApplyError('Explicit confirmation of a prepared data review is required')
        with self._store() as store:
            def claim(state):
                record = self._record(state, request['review_id'], owner, binding)
                if request['review_digest'] != record['review_digest']:
                    raise SchemaApplyError('Data review fingerprint changed')
                if record['state'] != 'reviewed':
                    return None
                if self.clock() > record['expires_at']:
                    raise SchemaApplyError('Data review expired')
                record.update(state='unknown_outcome', dispatched_at=self.clock())
                claimed = deepcopy(record)
                # Once claimed, only this process owns the input. Durable
                # receipts retain fingerprints/counts, never imported row data.
                record['plan'].pop('rows', None)
                return claimed
            claimed = store.change(claim)
        if claimed is None:
            return self.get(request['review_id'], owner, binding)
        try:
            outcome = execute(claimed)
        except Exception as error:
            outcome = {'state': 'unknown_outcome', 'error_type': type(error).__name__}
        with self._store() as store:
            def finish(state):
                record = self._record(state, request['review_id'], owner, binding)
                record.update(state=outcome['state'], outcome=outcome, finished_at=self.clock())
            store.change(finish)
        return self.get(request['review_id'], owner, binding)
