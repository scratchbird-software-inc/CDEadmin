"""Reviewed, cancellable native database copies on the original DuckDB handle."""
from copy import deepcopy
import hashlib
import json
import threading
import time
import uuid

from .attachments import catalogs, file_identity, identifier_key, quote
from ...sdk import RelationalClientError

FAMILIES = {
    'schemas': ('duckdb_schemas', ('schema_name',)),
    'tables': ('duckdb_tables', ('schema_name', 'table_name')),
    'columns': ('duckdb_columns', ('schema_name', 'table_name', 'column_name')),
    'constraints': ('duckdb_constraints', ('schema_name', 'table_name', 'constraint_type', 'constraint_text', 'constraint_column_names')),
    'indexes': ('duckdb_indexes', ('schema_name', 'index_name')),
    'views': ('duckdb_views', ('schema_name', 'view_name')),
    'sequences': ('duckdb_sequences', ('schema_name', 'sequence_name')),
    'types': ('duckdb_types', ('schema_name', 'type_name')),
    'macros': ('duckdb_functions', ('schema_name', 'function_name', 'function_type', 'parameters')),
}
ACTIVE = frozenset({'reviewing', 'applying'})
PRIVATE = frozenset({'baseline', 'draft', 'deadline', 'worker', 'origin'})


class Cancelled(Exception):
    pass


def public(record):
    snapshot = record.copy()
    return deepcopy({key: value for key, value in snapshot.items() if key not in PRIVATE})


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def check_cancel(record):
    if record['cancel_requested']:
        raise Cancelled()


def physical_columns(table, columns):
    """Follow native COPY's physical columns without evaluating virtual values."""
    import duckdb
    source = table['sql'].encode('utf8')
    positions = duckdb.tokenize(table['sql'])
    tokens = []
    for index, (offset, kind) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(source)
        tokens.append((source[offset:end].decode('utf8').strip(), kind))
    sections, section, depth = [], [], 0
    for word, kind in tokens:
        if kind == duckdb.token_type.operator and word in {'(', '[', '{'}:
            depth += 1
            if depth == 1:
                continue
        elif kind == duckdb.token_type.operator and word in {')', ']', '}'}:
            depth -= 1
            if depth == 0:
                sections.append(section)
                break
        if depth == 1 and kind == duckdb.token_type.operator and word == ',':
            sections.append(section)
            section = []
        elif depth:
            section.append((word, kind))
    generated = set()
    marker = [(word, duckdb.token_type.keyword) for word in ('generated', 'always', 'as')]
    for section in sections:
        lowered = [(word.lower() if kind == duckdb.token_type.keyword else word, kind) for word, kind in section]
        if any(lowered[index:index+3] == marker for index in range(len(lowered)-2)):
            name = section[0][0]
            if name.startswith('"') and name.endswith('"'):
                name = name[1:-1].replace('""', '"')
            generated.add(identifier_key(name))
    return [row['column_name'] for row in sorted(columns, key=lambda row: row['column_index'])
        if identifier_key(row['column_name']) not in generated]


def observe(handle, alias, record):
    """Keep native declarations private; compare data with native bag aggregates."""
    result = {'objects': {}, 'tables': {}}
    for family, (function, _identity) in FAMILIES.items():
        check_cancel(record)
        where = 'database_name=?'
        if family not in {'constraints', 'indexes', 'sequences'}:
            where += ' AND NOT internal'
        if family == 'macros':
            where += " AND function_type IN ('macro','table_macro')"
        cursor = handle.execute('SELECT * FROM ' + function + '() WHERE ' + where + ' LIMIT 16385', [alias])
        names = [column[0] for column in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
        if len(rows) > 16384:
            raise ValueError('Native database-copy metadata exceeds the reviewed catalog budget')
        result['objects'][family] = sorted(rows, key=encoded)
    for table in result['objects']['tables']:
        check_cancel(record)
        path = [alias, table['schema_name'], table['table_name']]
        record['active_table'] = path
        columns = [row for row in result['objects']['columns']
            if row['schema_name'] == path[1] and row['table_name'] == path[2]]
        physical = physical_columns(table, columns)
        if not physical:
            raise ValueError('Native physical copy-column evidence is unavailable')
        value = 'hash(ROW(' + ','.join('t.' + quote(column) for column in physical) + '))'
        row = handle.execute('SELECT count(*), coalesce(bit_xor(' + value + '),0), '
            'coalesce(sum(' + value + '::HUGEINT),0) FROM ' + '.'.join(map(quote, path)) + ' t').fetchone()
        result['tables'][encoded(path[1:])] = [str(value) for value in row]
    record.pop('active_table', None)
    if len(encoded(result).encode()) > 8 * 1024 * 1024:
        raise ValueError('Native database-copy metadata exceeds the reviewed byte budget')
    return result


def compile_operation(route, draft, before):
    if not isinstance(draft, dict) or set(draft) != {'source_catalog', 'destination_catalog', 'mode'}:
        raise ValueError('Select source, destination and native database-copy mode')
    if not isinstance(draft['mode'], str) or draft['mode'] not in {'ALL', 'SCHEMA', 'DATA'}:
        raise ValueError('Select native schema, data or schema and data copy')
    selected = []
    for field in ('source_catalog', 'destination_catalog'):
        name = draft[field]
        if not isinstance(name, str) or not name or '\x00' in name or len(name.encode()) > 65536:
            raise ValueError('Select an exact attached native catalog name')
        row = next((row for row in before if identifier_key(row['name']) == identifier_key(name)), None)
        if row is None or row['type'] != 'duckdb':
            raise ValueError('Select an attached native DuckDB catalog')
        if row['path'] is None:
            if route.get('allow_memory') is not True:
                raise ValueError('In-memory database copy requires registered memory authorization')
            identity = {'memory': True}
        else:
            identity = file_identity(route, row['path'])
            identity = {key: identity[key] for key in ('path', 'device', 'inode')}
        selected.append({'catalog': row, 'file_identity': identity})
    source, destination = selected
    if source['catalog']['oid'] == destination['catalog']['oid']:
        raise ValueError('Native source and destination catalogs must differ')
    if route.get('read_only') is True or destination['catalog']['read_only']:
        raise ValueError('Native database copy requires a writable authorized destination')
    prefix = 'COPY FROM DATABASE ' + quote(source['catalog']['name']) + ' TO ' + quote(destination['catalog']['name'])
    modes = ['SCHEMA', 'DATA'] if draft['mode'] == 'ALL' else [draft['mode']]
    statements = [prefix + ' (' + mode + ')' for mode in modes]
    import duckdb
    for statement in statements:
        parsed = duckdb.extract_statements(statement)
        if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.COPY_DATABASE:
            raise ValueError('Exactly one native COPY DATABASE statement is required per step')
    return {'source': source, 'destination': destination, 'statements': statements, 'mode': draft['mode']}


def baseline(handle, route, draft, record):
    before = catalogs(handle)
    origin = record['origin']
    if not any((row['name'], row['oid'], row['path']) ==
            (origin[0], str(origin[1]), origin[2]) for row in before):
        raise ValueError('The original registered native catalog identity changed')
    compiled = compile_operation(route, draft, before)
    context = record['session_scope_id']
    result = {'catalogs': before, 'compiled': compiled, 'session_scope_id': context,
        'transaction_id': str(handle.execute('SELECT current_transaction_id()').fetchone()[0])}
    for side in ('source', 'destination'):
        check_cancel(record)
        record['phase'] = 'reading_' + side
        result[side] = observe(handle, compiled[side]['catalog']['name'], record)
    return result


def object_keys(observation, family):
    fields = FAMILIES[family][1]
    return {encoded([row.get(field) for field in fields]) for row in observation['objects'][family]}


def dispatch(handle, source):
    handle.execute(source)
    handle.fetchall()


def verify(before, after, mode):
    source, destination = before['source'], before['destination']
    object_checks = {}
    for family in FAMILIES:
        expected = object_keys(destination, family)
        if mode != 'DATA':
            expected |= object_keys(source, family)
        object_checks[family] = expected == object_keys(after, family)
    data_checks = {}
    def column_types(observation, name):
        return sorted((row['column_index'], row['column_name'], row['data_type'])
            for row in observation['objects']['columns']
            if encoded([row['schema_name'], row['table_name']]) == name)
    for name, values in after['tables'].items():
        old = list(map(int, destination['tables'].get(name, ['0', '0', '0'])))
        copied = list(map(int, source['tables'].get(name, ['0', '0', '0']))) if mode != 'SCHEMA' else [0, 0, 0]
        expected = [old[0] + copied[0], old[1] ^ copied[1], old[2] + copied[2]]
        conversion = mode == 'DATA' and name in source['tables'] and column_types(source, name) != column_types(destination, name)
        data_checks[name] = {
            'method': 'native_row_count_after_conversion' if conversion else 'native_row_bag_aggregates',
            'expected_rows': str(expected[0]), 'observed_rows': values[0],
            'verified': int(values[0]) == expected[0] if conversion else list(map(int, values)) == expected}
    return {'native_object_identities': object_checks, 'native_table_postconditions': data_checks,
        'verification_method': 'native object identities and per-table native row aggregates; native DATA conversions use row counts, not cross-type hashes; neither is a collision-free data proof',
        'verified': all(object_checks.values()) and all(row['verified'] for row in data_checks.values())}


def worker(client, handle, route, record, reviewing):
    from .driver import uncertain
    blocked = False
    try:
        current = baseline(handle, route, record['draft'], record)
        check_cancel(record)
        if reviewing:
            compiled = current['compiled']
            record.update(baseline=current, source_catalog=compiled['source']['catalog']['name'],
                destination_catalog=compiled['destination']['catalog']['name'],
                source=';\n'.join(compiled['statements']) + ';',
                mode=compiled['mode'], deadline=time.monotonic() + 300,
                source_table_rows={key: values[0] for key, values in current['source']['tables'].items()},
                destination_table_rows={key: values[0] for key, values in current['destination']['tables'].items()})
            record['review_digest'] = hashlib.sha256(encoded(public(record)).encode()).hexdigest()
            record['state'] = 'reviewed'
        else:
            if current != record['baseline'] or record['deadline'] < time.monotonic():
                record.update(state='refused', reason='Native catalogs, transaction, definitions or data changed since review')
                return
            record['steps'] = []
            for source in current['compiled']['statements']:
                check_cancel(record)
                record.update(phase='copying_schema' if source.endswith('(SCHEMA)') else 'copying_data',
                    native_dispatched=True, native_catalog_or_data_effects_possible=True)
                step = {'source': source, 'native_dispatched': True, 'native_acknowledged': False}
                record['steps'].append(step)
                try:client.publish_receipt(handle,'database_copy',public(record))
                except Exception:
                    step.update(native_dispatched=False)
                    record['native_dispatched']=any(value['native_dispatched'] for value in record['steps'])
                    record['native_catalog_or_data_effects_possible']=record['native_dispatched']
                    raise
                dispatch(handle, source)
                step['native_acknowledged'] = True
                client.publish_receipt(handle,'database_copy',public(record))
            record.update(native_acknowledged=True, phase='observing_destination')
            after = observe(handle, current['compiled']['destination']['catalog']['name'], record)
            observation = verify(current, after, current['compiled']['mode'])
            record.update(state='acknowledged', observation=observation, rediscovery_verified=observation['verified'])
            blocked = not observation['verified']
    except Exception as error:
        import duckdb
        cancelled = isinstance(error, (Cancelled, duckdb.InterruptException))
        blocked = uncertain(error) and not isinstance(error, (ValueError, Cancelled))
        if record['native_acknowledged']:
            state = 'acknowledged'
            blocked = True
        elif blocked and record['native_dispatched']:
            state = 'unknown_outcome'
        elif any(step['native_acknowledged'] for step in record.get('steps', [])):
            state = 'partial'
        else:
            state = 'cancelled' if cancelled else 'refused'
        record.update(state=state, error_type=type(error).__name__, rediscovery_verified=False)
        if isinstance(error, ValueError):
            record['reason'] = str(error)
    finally:
        try:
            client._observe(handle, blocked=blocked)
        except Exception:
            client._observe(handle, blocked=True)
        with client._lock:
            record['session_reuse_blocked'] = bool(client._states[id(handle)].get('session_reuse_blocked'))
            if record['state'] != 'reviewed':
                record.pop('baseline', None)
                record.pop('draft', None)
            record['phase'] = 'finished'
            try:client.publish_receipt(handle,'database_copy',public(record))
            except Exception as error:record['receipt_recording_error_type']=type(error).__name__
            finally:client._busy.discard(id(handle))


def action(client, handle, route, request):
    if not isinstance(request, dict):
        raise ValueError('Select a native database-copy request')
    operation = request.get('operation')
    allowed = {'inventory': {'operation'}, 'review': {'operation', 'draft'},
        'apply': {'operation', 'review_id', 'review_digest', 'confirmation', 'confirmed'},
        'receipt': {'operation', 'review_id'}, 'cancel': {'operation', 'review_id'},
        'discard': {'operation', 'review_id', 'review_digest'}}
    if operation not in allowed or set(request) != allowed[operation]:
        raise ValueError('Unknown native database-copy request')
    with client._lock:
        context = client._attachment_contexts.get(id(handle))
        if context is None or context['route'] != route:
            raise ValueError('The retained DuckDB session belongs to another or changed registration')
        records = client._database_copy_reviews
        if operation not in {'inventory', 'review'}:
            record = records.get(request['review_id'])
            if record is None or record['session_scope_id'] != context['session_scope_id']:
                raise ValueError('The database-copy receipt belongs to another or closed native session')
            if operation in {'apply', 'discard'} and request['review_digest'] != record.get('review_digest'):
                raise ValueError('Select the exact native database-copy review')
            if operation == 'receipt':
                return public(record)
            if operation == 'cancel':
                if record['state'] in ACTIVE:
                    record['cancel_requested'] = True
                    handle.interrupt()
                return public(record)
            if record['state'] != 'reviewed' or record['phase'] != 'finished':
                return public(record)
            if operation == 'discard':
                record.update(state='discarded')
                record.pop('baseline', None)
                client.publish_receipt(handle,'database_copy',public(record))
                return public(record)
            if (record['deadline'] < time.monotonic() or request['confirmed'] is not True or
                    request['confirmation'] != record['destination_catalog']):
                raise ValueError('Confirm the current reviewed destination catalog')
        client._require_idle(handle)
        if operation == 'inventory':
            return {'catalogs': catalogs(handle), 'session_scope_id': context['session_scope_id']}
        if operation == 'review':
            for key in list(records):
                old = records[key]
                if old['state'] not in ACTIVE and (old['deadline'] < time.monotonic() or
                        old['session_scope_id'] not in {value['session_scope_id'] for value in client._attachment_contexts.values()}):
                    del records[key]
            if len(records) >= 16:
                raise ValueError('Close old native database-copy reviews before creating another')
            # Reject forged SQL/options and unauthorized files before starting a worker.
            compile_operation(route, request['draft'], catalogs(handle))
            record = {'review_id': str(uuid.uuid4()), 'state': 'reviewing', 'phase': 'starting',
                'session_scope_id': context['session_scope_id'], 'draft': deepcopy(request['draft']),
                'origin': context['origin'],
                'deadline': time.monotonic() + 300, 'cancel_requested': False,
                'native_dispatched': False, 'native_acknowledged': False, 'rediscovery_verified': False,
                'automatic_retry': False, 'caller_transaction_decision_requested': False,
                'warnings': ['The original native transaction owns all copy effects. Commit and rollback remain your decision.',
                    'Review and revalidation read all selected tables to compare native row aggregates.',
                    'Data mode appends native rows. Schema mode creates native objects. Schema and data runs those two native steps in order.',
                    'Native conflicts and the one-writable-database-per-transaction restriction are returned without a fallback or implicit transaction decision.',
                    'Live review/application belongs to this original session. Durable receipts remain read-only after release. Acknowledgement does not mean the caller committed.']}
            records[record['review_id']] = record
        else:
            record.update(state='applying', phase='starting', cancel_requested=False)
        client.publish_receipt(handle,'database_copy',public(record))
        client._busy.add(id(handle))
        thread = threading.Thread(target=worker, args=(client, handle, deepcopy(route), record, operation == 'review'),
            daemon=True, name='cdeadmin-duckdb-database-copy')
        record['worker'] = thread
        try:
            thread.start()
        except BaseException:
            client._busy.discard(id(handle))
            record.update(state='refused', phase='finished')
            raise
        return public(record)
