"""Reviewed permanent replication-slot operations on an owned SQL connection."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import socket
import threading
import time
import uuid

from ..providers.postgresql import large_object_files as private_sql
from ..providers.postgresql.continuity import ContinuityError
from .postgresql_continuity_slots import IDENTITY, SLOT_PROPERTIES, name

OPERATIONS = {'wal_slot_sql_physical_create', 'wal_slot_sql_logical_create',
              'wal_slot_sql_physical_copy', 'wal_slot_sql_logical_copy',
              'wal_slot_sql_advance', 'wal_slot_sql_drop'}


def options(operation, value):
    if operation not in OPERATIONS or not isinstance(value, dict):
        raise ContinuityError('Select a native SQL slot operation')
    fields = {'slot', 'timeout_seconds'}
    if operation.endswith('_physical_create'): fields.add('reserve_wal')
    if operation.endswith('_logical_create'): fields.update(('plugin', 'two_phase', 'failover'))
    if operation.endswith('_copy'): fields.add('source_slot')
    if operation.endswith('_logical_copy'): fields.add('plugin')
    if operation.endswith('_advance'): fields.add('upto_lsn')
    if set(value) - fields: raise ContinuityError('Invalid native SQL slot options')
    selected = {'slot': name(value.get('slot')), 'timeout_seconds': value.get('timeout_seconds', 30)}
    duration = selected['timeout_seconds']
    if duration is not None and (type(duration) is not int or not 1 <= duration <= 2147483):
        raise ContinuityError('Native SQL slot timeout requires 1 to 2147483 seconds or no deadline')
    for key in ('reserve_wal', 'two_phase', 'failover'):
        if key in fields:
            selected[key] = value.get(key, key == 'reserve_wal')
            if type(selected[key]) is not bool: raise ContinuityError('Native slot flags require boolean values')
    if 'source_slot' in fields:
        selected['source_slot'] = name(value.get('source_slot'))
        if selected['source_slot'] == selected['slot']:
            raise ContinuityError('Select a distinct destination slot')
    if 'plugin' in fields:
        plugin = value.get('plugin', '' if operation.endswith('_copy') else 'pgoutput')
        if not isinstance(plugin, str) or '\x00' in plugin or len(plugin) > 63 or (not plugin and operation.endswith('_create')):
            raise ContinuityError('Select an exact native output plugin name')
        selected['plugin'] = plugin
    if 'upto_lsn' in fields:
        lsn = value.get('upto_lsn')
        if not isinstance(lsn, str) or re.fullmatch(r'[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}', lsn) is None or int(lsn.replace('/', ''), 16) == 0:
            raise ContinuityError('Select a nonzero native WAL position')
        selected['upto_lsn'] = lsn.upper()
    return selected


def client_identity():
    import psycopg
    from psycopg import pq
    return {'kind': 'native-python-sql-client', 'psycopg_version': psycopg.__version__,
            'libpq_version': pq.version(), 'libpq_implementation': pq.__impl__,
            'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'private_transport_sha256': hashlib.sha256(Path(private_sql.__file__).read_bytes()).hexdigest()}


def observation(connection, slot):
    import json
    with private_sql.cursor(connection) as query:
        query.execute('SELECT ' + SLOT_PROPERTIES + '::pg_catalog.text FROM pg_catalog.pg_replication_slots s WHERE s.slot_name=%s', (slot,))
        row = query.fetchone()
    return json.loads(row[0]) if row else None


def enrich(identity, connection, selected):
    result = {'sql_identity': identity}
    for prefix, slot in (('slot', selected['slot']), ('copy_slot', selected.get('source_slot'))):
        observed = observation(connection, slot) if slot is not None else None
        result[prefix + '_snapshot'] = observed
        result[prefix + '_identity'] = None if observed is None else {key: observed.get(key) for key in IDENTITY}
    return result


def capture(provider, route, server, selected, database_id):
    import psycopg
    from ..providers.postgresql.provider import PostgreSQLProviderError
    transport = None
    try:
        provider.permissions.require('execute'); provider.permissions.require('secret_read')
        # Discover the exact target on a private admitted server attachment.
        # Opening a shared database studio first is not a prerequisite.
        opened = provider.open_session({'route': route})
        try:
            state = provider._sessions[opened['session_id']]
            provider._ensure_native_connection(state)
            peer = private_sql.identity(state.connection.conn)
            with private_sql.cursor(state.connection.conn) as query:
                query.execute('SELECT datname FROM pg_catalog.pg_database WHERE oid=%s AND datallowconn AND pg_catalog.has_database_privilege(oid,\'CONNECT\')', (database_id,))
                found = query.fetchone()
            if found is None: raise ContinuityError('Selected native slot database is unavailable or CONNECT is not admitted')
        finally: provider.close_session(opened)
        identity, transport = private_sql.capture(provider, {**route, 'database_id': database_id}, server,
            resolved_database=found[0], application_name='ScratchRobin native SQL slot admission')
        if (identity['database_oid'] != str(database_id) or
                {key: value for key, value in identity.items() if key not in {'database', 'database_oid'}} !=
                {key: value for key, value in peer.items() if key not in {'database', 'database_oid'}}):
            raise ContinuityError('Selected native slot database or server identity changed during admission')
        with transport.parameters() as parameters:
            with private_sql.attach(parameters, identity) as connection:
                with private_sql.cursor(connection) as query: query.execute('SET statement_timeout = 5000')
                source = enrich(identity, connection, selected)
        return source, transport
    except (psycopg.Error, private_sql.LargeObjectFileError, PostgreSQLProviderError) as error:
        if transport is not None: transport.close()
        raise ContinuityError('Native SQL slot admission failed (' + (getattr(error, 'sqlstate', None) or type(error).__name__) + '); review the selected PostgreSQL 18.3 database and role') from None
    except BaseException:
        if transport is not None: transport.close()
        raise


def review(jobs, request, owner, endpoint, source, configuration, paths, runtime_limit):
    if set(request) != {'operation', 'options', 'database_target_id'}:
        raise ContinuityError('Select an explicit database for a native SQL slot review')
    target = request['database_target_id']
    if not isinstance(target, str) or not 1 <= len(target) <= 256:
        raise ContinuityError('Select an explicit PostgreSQL database target')
    operation = request['operation']; selected = options(operation, request['options'])
    from psycopg._capabilities import capabilities
    if not capabilities.has_cancel_safe():
        raise ContinuityError('Native SQL slot jobs require libpq 17 or later for bounded cancellation')
    if runtime_limit is not None and (type(runtime_limit) is not int or runtime_limit < 1 or
            selected['timeout_seconds'] is None or selected['timeout_seconds'] > runtime_limit):
        raise ContinuityError('Application runtime policy requires a bounded native SQL slot duration')
    record = {'job_id': str(uuid.uuid4()), 'owner': owner, 'endpoint_id': endpoint,
              'database_target_id': target, 'configuration': configuration, 'operation': operation,
              'options': selected, 'source': deepcopy(source), 'paths': deepcopy(paths), 'inputs': [],
              'tool_identities': {}, 'client_identity': client_identity(), 'state': 'reviewed',
              'created_at': time.time(), 'expires_at': time.time() + 600, 'runtime_limit': runtime_limit,
              'cancel_requested': False, 'artifact_wal_method': None,
              'execution_host': {'kind': 'application-host', 'platform': os.name, 'hostname': socket.gethostname()},
              'warnings': [
                  'This permanent slot operation uses an independent native SQL connection to the selected database, preserving the reviewed effective role.',
                  'Slot changes are native nontransactional side effects. Cancellation, a lost reply or SQL rollback cannot establish that a slot change was undone. Unacknowledged dispatches are never replayed.',
                  'Native command acknowledgement is recorded before the later catalog observation. The catalog cannot establish an uncertain original outcome.',
                  'Slots can retain WAL and prevent server storage from being reclaimed. PostgreSQL controls slot concurrency and privileges.']}
    if operation.endswith('_advance'):
        record['warnings'].append('Advancement discards an earlier replication position. PostgreSQL clamps the requested position to flushed or replayed WAL and returns the position actually reached; consumers may lose unread changes.')
    if operation.endswith('_logical_create'):
        record['warnings'].append('Logical creation uses the selected database and installed output plugin. Native snapshot initialization may wait for concurrent transactions. Two-phase and failover capabilities are validated by PostgreSQL.')
    if operation.endswith('_drop'):
        record['warnings'].append('Dropping a slot removes its retained position. Active slots are refused by PostgreSQL; no session is terminated automatically.')
    record['artifact_location'] = str(jobs.directory(record))
    return jobs.save_review(record)


def statement(operation, selected):
    slot = selected['slot']
    if operation.endswith('_physical_create'):
        return 'SELECT slot_name::pg_catalog.text,lsn::pg_catalog.text FROM pg_catalog.pg_create_physical_replication_slot(%s::pg_catalog.name,%s,false)', (slot, selected['reserve_wal'])
    if operation.endswith('_logical_create'):
        return 'SELECT slot_name::pg_catalog.text,lsn::pg_catalog.text FROM pg_catalog.pg_create_logical_replication_slot(%s::pg_catalog.name,%s::pg_catalog.name,false,%s,%s)', (slot, selected['plugin'], selected['two_phase'], selected['failover'])
    if operation.endswith('_physical_copy'):
        return 'SELECT slot_name::pg_catalog.text,lsn::pg_catalog.text FROM pg_catalog.pg_copy_physical_replication_slot(%s::pg_catalog.name,%s::pg_catalog.name,false)', (selected['source_slot'], slot)
    if operation.endswith('_logical_copy'):
        if selected['plugin']:
            return 'SELECT slot_name::pg_catalog.text,lsn::pg_catalog.text FROM pg_catalog.pg_copy_logical_replication_slot(%s::pg_catalog.name,%s::pg_catalog.name,false,%s::pg_catalog.name)', (selected['source_slot'], slot, selected['plugin'])
        return 'SELECT slot_name::pg_catalog.text,lsn::pg_catalog.text FROM pg_catalog.pg_copy_logical_replication_slot(%s::pg_catalog.name,%s::pg_catalog.name,false)', (selected['source_slot'], slot)
    if operation.endswith('_advance'):
        return 'SELECT slot_name::pg_catalog.text,end_lsn::pg_catalog.text FROM pg_catalog.pg_replication_slot_advance(%s::pg_catalog.name,%s::pg_catalog.pg_lsn)', (slot, selected['upto_lsn'])
    if operation.endswith('_drop'):
        return 'SELECT pg_catalog.pg_drop_replication_slot(%s::pg_catalog.name)', (slot,)
    raise ContinuityError('Native SQL slot operation is unavailable')


def run(jobs, record, transport, signal):
    """One dispatch; positive native acknowledgement wins a concurrent cancel."""
    connection = None; observer = None; stopped = threading.Event(); dispatch = False; acknowledged = False
    selected = record['options']; deadline = None
    if selected['timeout_seconds'] is not None: deadline = time.monotonic() + selected['timeout_seconds']
    try:
        if client_identity() != record['client_identity']:
            raise ContinuityError('Native SQL client changed after review')
        with transport.parameters() as parameters:
            connection = private_sql.attach({**parameters, 'application_name': 'ScratchRobin native SQL slot ' + record['job_id']}, record['source']['sql_identity'])
            def watch():
                while not stopped.wait(.2):
                    try:
                        current = jobs.load(record['job_id'], record['owner'], record['endpoint_id'])
                        if current.get('cancel_requested') or deadline is not None and time.monotonic() >= deadline: signal.set()
                        if signal.is_set():
                            connection.cancel_safe(timeout=1)
                    except Exception:
                        # A cancellation request is not a native outcome. Keep
                        # observing the original command, without a new dispatch.
                        continue
            observer = threading.Thread(target=watch, daemon=True, name='postgresql-slot-cancel-' + record['job_id'])
            observer.start()
            with private_sql.cursor(connection) as query:
                query.execute("SELECT pg_catalog.set_config('statement_timeout','5000',false)")
            observed = enrich(record['source']['sql_identity'], connection, selected)
            for key in ('slot_identity', 'copy_slot_identity'):
                if observed[key] != record['source'][key]:
                    raise ContinuityError('Native replication slot changed after review')
            if selected.get('plugin'):
                with private_sql.cursor(connection) as query:
                    query.execute('SELECT %s::pg_catalog.name::pg_catalog.text', (selected['plugin'],))
                    if query.fetchone()[0] != selected['plugin']:
                        raise ContinuityError('Native output plugin name would be truncated')
            current = jobs.load(record['job_id'], record['owner'], record['endpoint_id'])
            if signal.is_set() or current.get('cancel_requested') or deadline is not None and time.monotonic() >= deadline:
                jobs.update(record, state='cancelled', native_sql_acknowledged=False, sql_dispatched=False, finished_at=time.time())
                return
            with private_sql.cursor(connection) as query:
                query.execute("SELECT pg_catalog.set_config('statement_timeout',%s,false)", ('0' if selected['timeout_seconds'] is None else str(selected['timeout_seconds']) + 's',))
            command, arguments = statement(record['operation'], selected)
            jobs.update(record, state='active', phase='native_sql_slot_command', sql_dispatched=True,
                        native_backend_pid=connection.info.backend_pid, remote_finality_inferred=False)
            dispatch = True
            with private_sql.cursor(connection) as query:
                query.execute(command, arguments)
                row = query.fetchone()
            acknowledged = True
            result = {'slot_name': selected['slot']} if record['operation'].endswith('_drop') else {'slot_name': row[0], 'end_lsn': row[1]}
            # Persist the actual reply before any later observation or cleanup.
            jobs.update(record, state='completed', native_sql_acknowledged=True, native_sql_result=result,
                        sql_dispatched=True, remote_finality_inferred=False, slot_observation_state='pending',
                        slot_existed_before=record['source']['slot_snapshot'] is not None, finished_at=time.time())
            stopped.set()
            if observer is not None: observer.join(timeout=2)
            try:
                with private_sql.cursor(connection) as query: query.execute('SET statement_timeout = 5000')
                after = observation(connection, selected['slot'])
                jobs.update(record, slot_observation=after, slot_observation_state='observed', slot_observed_at=time.time())
            except Exception as error:
                jobs.update(record, slot_observation_state='unavailable',
                            slot_observation_blocker='Current native slot observation is unavailable (' + type(error).__name__ + ')')
    except Exception as error:
        if acknowledged:
            # Even a later cleanup or observation failure cannot erase an ACK.
            jobs.update(record, state='completed', native_sql_acknowledged=True, slot_observation_state='unavailable')
        else:
            jobs.update(record, state='unknown' if dispatch else 'cancelled' if signal.is_set() else 'not_dispatched',
                        sql_dispatched=dispatch, native_sql_acknowledged=False,
                        native_sqlstate=getattr(error, 'sqlstate', None), error_type=type(error).__name__,
                        error_reason=str(error) if isinstance(error, ContinuityError) else None,
                        remote_finality_inferred=False, finished_at=time.time())
    finally:
        stopped.set()
        if observer is not None: observer.join(timeout=2)
        if connection is not None:
            try: connection.close()
            except Exception: pass  # Connection cleanup cannot rewrite a native ACK.
