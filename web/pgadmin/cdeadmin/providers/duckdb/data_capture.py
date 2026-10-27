"""Explicit bounded DuckDB relation data acquisition for public DDN views."""

from datetime import datetime, timezone
import hashlib
import json
import os
import threading
import time
import uuid
from ..native_data_layout import inspect_relation

from ..embedded_route import contained_database
from .provider import _resource_id
from .values import scalar
from ...results.ddn_export import export_workspace
from pgadmin.cdeadmin.sdk import RelationalClientError

MAX_ROWS = 6000
MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 30


def relation_address(resource_id):
    if not isinstance(resource_id, str) or not resource_id.startswith('duckdb:'):
        raise ValueError('Select an exact native DuckDB relation')
    try:
        parts = json.loads(resource_id[7:])
    except (ValueError, TypeError):
        raise ValueError('Invalid native DuckDB relation identity') from None
    if (not isinstance(parts, list) or len(parts) != 4 or parts[0] not in {'table', 'view'} or
            any(not isinstance(part, str) or not part or '\0' in part for part in parts[1:]) or
            resource_id != _resource_id(parts[0], parts[1:3], parts[3])):
        raise ValueError('Relation identity is not an exact native DuckDB table or view')
    return parts


def _identifier(value):
    return '"' + value.replace('"', '""') + '"'


def capture(provider, route, resource_id, *, endpoint_id, target_id, mode='sample', row_limit=100):
    if (type(row_limit) is not int or not 1 <= row_limit <= MAX_ROWS or
            mode not in {'sample', 'full'}):
        raise ValueError('Select sample/full mode and a 1–6,000 row budget')
    kind, catalog, schema, name = relation_address(resource_id)
    provider.permissions.require('data_read', 'resource')
    provider.permissions.require('execute')
    path = contained_database(route)
    if path == ':memory:':
        raise RelationalClientError('Independent :memory: relation capture is unavailable')
    if not os.path.isfile(path):
        raise RelationalClientError('Registered DuckDB database file does not exist')
    connection = provider.client._connect({'route': route})
    begun = False
    reader = None
    timer = threading.Timer(MAX_SECONDS, connection.interrupt)
    timer.daemon = True
    started = time.monotonic()
    try:
        connection.execute('BEGIN TRANSACTION')
        begun = True
        timer.start()
        connection.execute('SELECT current_database()')
        if connection.fetchone()[0] != catalog:
            raise ValueError('Relation belongs to another DuckDB catalog or session attachment')
        native_table = 'duckdb_tables()' if kind == 'table' else 'duckdb_views()'
        connection.execute('SELECT COUNT(*) FROM ' + native_table +
            ' WHERE database_name=? AND schema_name=? AND ' +
            ('table_name' if kind == 'table' else 'view_name') + '=? AND NOT internal',
            [catalog, schema, name])
        if connection.fetchone()[0] != 1:
            raise ValueError('Native relation is unavailable or its kind changed')
        qualified = '.'.join(map(_identifier, (catalog, schema, name)))
        layout = inspect_relation(connection, 'duckdb', resource_id, route)
        connection.execute('SELECT * FROM ' + qualified + ' LIMIT ?', [row_limit + 1])
        description = list(connection.description or ())
        if not 1 <= len(description) <= 256:
            raise ValueError('DDN data capture needs 1–256 visible columns')
        reader = connection.to_arrow_reader(128)
        columns = [{'name': str(field.name), 'native_name': str(field.name), 'key': str(index), 'ordinal': index,
                    'native_type': str(description[index][1]), 'arrow_type': str(field.type)}
                   for index, field in enumerate(reader.schema)]
        arrow_schema = reader.schema
        native_batches = []
        rows, size, exceeded = [], 0, False
        for batch in reader:
            remaining = row_limit - len(rows)
            if remaining > 0: native_batches.append(batch.slice(0, min(remaining, batch.num_rows)))
            for index in range(batch.num_rows):
                if time.monotonic() - started > MAX_SECONDS:
                    raise ValueError('DuckDB data capture exceeded 30 seconds')
                if len(rows) >= row_limit:
                    exceeded = True
                    continue
                row = [scalar(column[index]) for column in batch.columns]
                size += len(json.dumps(row, ensure_ascii=False, allow_nan=False).encode('utf8'))
                if size > MAX_BYTES:
                    raise ValueError('DuckDB data capture exceeds 4 MiB')
                rows.append(row)
        reader.close(); reader = None
        if exceeded and mode == 'full':
            raise ValueError('Full data capture exceeds the row budget')
        acquisition = {'engine_id': 'duckdb', 'endpoint_id': endpoint_id,
            'database_target_id': target_id, 'resource_id': resource_id,
            'catalog': catalog, 'schema': schema, 'relation': name, 'kind': kind,
            'mode': mode, 'row_limit': row_limit, 'rows': len(rows),
            'more_rows_observed': exceeded, 'ordering': 'unspecified native order',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'consistency': 'independently owned native read transaction',
            'value_encoding': 'exact DuckDB Arrow positional JSON; temporal ticks and binary envelopes'}
        import pyarrow as pa
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, arrow_schema) as writer:
            for batch in native_batches: writer.write_batch(batch)
        payload = sink.getvalue().to_pybytes()
        acquisition.update(native_version=layout['native_version'], native_columns=layout['native_columns'], native_layout=layout,
            transaction_completed=True, native_payload={'format': 'arrow-ipc@1', 'byte_length': len(payload),
                'sha256': hashlib.sha256(payload).hexdigest(), 'chunks': (len(payload) + 1024 * 1024 - 1) // (1024 * 1024)})
        metadata = {'result_id': str(uuid.uuid4()), 'execution_id': None,
            'native_payload_bytes': payload,
            'title': qualified, 'schema': {'columns': columns}, 'complete': not exceeded,
            'export_coverage': 'full relation' if not exceeded else 'bounded sample',
            'acquisition': acquisition, 'consistency': acquisition['consistency'],
            'value_encoding': acquisition['value_encoding']}
        connection.execute('ROLLBACK'); begun = False
        encoded = export_workspace(metadata, rows)
        if len(encoded) > 8 * 1024 * 1024:
            raise ValueError('DuckDB DDN data document exceeds 8 MiB')
        snapshot = json.loads(encoded)
        return {'snapshot': snapshot, 'acquisition': acquisition, 'columns': columns,
            'views': [{'id': 'result_' + str(number), 'label': 'Data page ' + str(number), 'entry': filename}
                      for number, filename in enumerate((name for name in snapshot['files'] if name.startswith('result-')), 1)],
            'sha256': hashlib.sha256(encoded).hexdigest(),
            'filename': 'duckdb-relation-data.ddn-workspace.json',
            'warnings': ['This is a bounded sample; more rows were observed.'] if exceeded else []}
    finally:
        if timer.is_alive():
            timer.cancel(); timer.join()
        try:
            if reader is not None: reader.close()
        finally:
            try:
                if begun: connection.execute('ROLLBACK')
            finally:
                provider.client._discard_failed_session(connection)
