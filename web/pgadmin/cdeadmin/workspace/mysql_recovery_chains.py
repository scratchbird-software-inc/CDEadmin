"""Reviewed native GTID dependencies for retained Shell backups and archives.

Dependencies protect files. They do not attest data equivalence, native log
generation epochs, physical recovery or a production cutover.
"""
from copy import deepcopy
import time
import uuid

from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError, manifest
from ..providers.mysql_family.mysql_dump_verification import document
from ..providers.mysql_family.mysql_clone import rows
from .mysql_binlog_jobs import digest, identity


def _gtids(value):
    if not isinstance(value, str) or '\x00' in value or len(value.encode('utf8')) > 1024 * 1024:
        raise BinlogArchiveError('Complete bounded native GTID metadata is required')
    return value


def coverage(connection, base, artifacts, stop=None):
    """Let MySQL normalize/subtract sets, including native tagged GTIDs."""
    covered = rows(connection, 'SELECT GTID_SUBTRACT(%s,%s) AS value', (_gtids(base), ''))[0]['value']
    edges = []
    for artifact in artifacts:
        start = _gtids(artifact.get('start_from', {}).get('gtidExecuted'))
        changes = _gtids(artifact.get('gtid_set'))
        facts = rows(connection, 'SELECT GTID_SUBSET(%s,%s) AS available,GTID_SUBTRACT(%s,%s) AS missing',
                     (start, covered, start, covered))[0]
        if facts['available'] != 1:
            raise BinlogArchiveError('Recovery archive has a native GTID dependency gap: ' + str(facts['missing']))
        added = rows(connection, 'SELECT GTID_SUBTRACT(%s,%s) AS value', (changes, covered))[0]['value']
        union = ','.join(part for part in (covered, changes) if part)
        after = rows(connection, 'SELECT GTID_SUBTRACT(%s,%s) AS value', (_gtids(union), ''))[0]['value']
        edges.append({'required_before': start, 'covered_before': covered, 'archive_gtids': changes,
                      'additional_gtids': added, 'covered_after': after})
        covered = after
    if stop:
        # A set does not define inter-SID event ordering. Retain the complete
        # last archive; the native replay utility owns stopBefore/stopAfter.
        valid = rows(connection, 'SELECT GTID_SUBSET(%s,%s) AS archived,GTID_SUBSET(%s,%s) AS already_present',
                     (stop, artifacts[-1]['gtid_set'], stop, edges[-1]['covered_before']))[0]
        if valid['archived'] != 1 or valid['already_present'] != 0:
            raise BinlogArchiveError('Select a new stop GTID in the final archive')
    return {'base_gtids': base, 'archive_edges': edges, 'all_selected_archive_gtids': covered,
            'selected_stop_gtid': stop, 'stop_order_calculated': False}


def selection(request):
    if not isinstance(request, dict) or set(request) != {'backup_id', 'archive_job_ids', 'stop_mode', 'stop_gtid'}:
        raise BinlogArchiveError('Select a managed backup, ordered Shell archives and a recovery target')
    backup = identity(request['backup_id']); archives = request['archive_job_ids']
    if not isinstance(archives, list) or not 1 <= len(archives) <= 64:
        raise BinlogArchiveError('Select one to 64 distinct ordered archive jobs')
    archives = [identity(item) for item in archives]
    if len(set(archives)) != len(archives):
        raise BinlogArchiveError('Select distinct ordered archive jobs')
    from ..providers.mysql_family.mysql_binlog_replay import options
    selected = options({'stop_mode': request['stop_mode'], 'stop_gtid': request['stop_gtid'],
                        'target_confirmation': '00000000-0000-0000-0000-000000000001'})
    return {'backup_id': backup, 'archive_job_ids': archives,
            'stop_mode': selected['stop_mode'], 'stop_gtid': selected['stop_gtid']}


def inputs(registry, store, jobs, owner, endpoint, selected, client, route, connection, instance_backups=None):
    backup = registry.records(store).get(selected['backup_id'])
    if (backup is None or not (backup.get('native_dump_completion_acknowledged') is True or backup.get('native_artifact_completion_observed') is True) or
            backup.get('native_consistent') is not True or
            backup.get('native_gtid_snapshot_inconsistent') is not False):
        raise BinlogArchiveError('Select an acknowledged consistent managed logical dump with complete native GTID metadata')
    if backup.get('backup_kind') == 'mysql_native_logical_instance':
        if instance_backups is None:
            raise BinlogArchiveError('Managed instance backup storage is unavailable')
        original = instance_backups.load(backup['native_instance_job_id'], owner, endpoint)
        path = instance_backups.directory(original) / 'archive'
        if str(path) != backup['artifact_path'] or original.get('artifact_removed') or original.get('artifact_removal') or original.get('native_process_termination_confirmed') is not True:
            raise BinlogArchiveError('Managed instance backup is unavailable or its native writer is unconfirmed')
    else:
        _root, path = client._workspace_path(route.get('tool_workspace'), backup['artifact_path'], 'Recovery base dump')
    files = manifest(path)
    if digest(files) != backup.get('artifact_manifest_digest'):
        raise BinlogArchiveError('Recovery base bytes changed since the native dump acknowledgement')
    top = document(path / '@.json')
    boundary = {key: str(top.get('source', {}).get('binlog', {}).get(key))
                for key in ('file', 'position', 'gtidExecuted')}
    if boundary != backup.get('native_boundary'):
        raise BinlogArchiveError('Recovery base native boundary changed')
    native = rows(connection, 'SELECT VERSION() AS version,@@server_uuid AS server_uuid,'
                  'CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role,@@GLOBAL.gtid_mode AS gtid_mode')[0]
    if (native['version'].split('-')[0] != '9.7.0' or native['server_uuid'] != backup['source']['server_uuid'] or
            native['gtid_mode'] not in {'ON', 'ON_PERMISSIVE'}):
        raise BinlogArchiveError('Recovery dependencies require the original MySQL9.7.0 instance')
    archive_inputs, artifacts = [], []
    for job_id in selected['archive_job_ids']:
        record = jobs.load(job_id, owner, endpoint)
        if (record['state'] not in {'completed', 'artifact_verified'} or record.get('artifact_removed') or
                record.get('artifact_removal') or record.get('native_process_termination_confirmed') is not True or
                record['source']['server_uuid'] != native['server_uuid']):
            raise BinlogArchiveError('Recovery dependencies require retained, completed archives from the same native source')
        artifact = jobs.native_verify(jobs.directory(record) / 'archive', record['source'])
        if digest(artifact) != digest((record.get('result') or {}).get('artifact')):
            raise BinlogArchiveError('Recovery archive bytes changed since native verification')
        archive_inputs.append({'job_id': job_id, 'endpoint_id': endpoint, 'operation': record['operation'],
                               'artifact_digest': digest(artifact), 'source_uuid': native['server_uuid']})
        artifacts.append(artifact)
    calculation = coverage(connection, _gtids(boundary['gtidExecuted']), artifacts, selected['stop_gtid'])
    if rows(connection, 'SELECT GTID_SUBSET(%s,@@GLOBAL.gtid_executed) AS present',
            (calculation['all_selected_archive_gtids'],))[0]['present'] != 1:
        raise BinlogArchiveError('The original native source no longer contains these GTIDs; review its reset or replacement separately')
    calculation['selected_gtids_still_executed_on_source'] = True
    if manifest(path) != files:
        raise BinlogArchiveError('Recovery base changed during dependency review')
    return {'backup_id': backup['backup_id'], 'backup_instance_job_id': backup.get('native_instance_job_id'), 'backup_snapshot': digest(backup),
            'backup_artifact_digest': digest(files), 'database': backup['database'],
            'archives': archive_inputs, 'native_identity': native, 'source': deepcopy(backup['source']),
            'selection': selected, 'coverage': calculation,
            'native_log_generation_attested': False, 'database_recovery_verified': False,
            'production_cutover_verified': False, 'native_mutation_dispatched': False,
            'scope': 'Native GTID prerequisites and exact retained inputs. GTID reuse after a reset and external dependencies require operator review; no data or recovery equivalence is inferred.'}


def public(record):
    return {key: deepcopy(value) for key, value in record.items() if key not in {'owner', 'endpoint_id'}}


def offline(registry, owner, endpoint, operation, request):
    with registry.store(owner, endpoint) as store:
        state = store.read(); chains = state.get('mysql_recovery_chains', {})
        if operation == 'list' and isinstance(request, dict) and not set(request) - {'offset', 'limit'}:
            offset, limit = request.get('offset', 0), request.get('limit', 25)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise BinlogArchiveError('Select a recovery dependency page')
            values = sorted(chains.values(), key=lambda row: (row['created_at'], row['chain_id']), reverse=True)
            return {'chains': [public(row) for row in values[offset:offset + limit]], 'total': len(values),
                    'offset': offset, 'limit': limit, 'native_mutation_dispatched': False}
        if operation == 'review_retire' and isinstance(request, dict) and set(request) == {'chain_id'}:
            chain = chains.get(identity(request['chain_id']))
            if chain is None or chain['state'] != 'active':
                raise BinlogArchiveError('Select an active recovery dependency')
            review = {'review_id': str(uuid.uuid4()), 'chain_id': chain['chain_id'], 'snapshot': digest(chain),
                      'expires_at': time.time() + 300}
            review['review_digest'] = digest(review)
            store.change(lambda value: value.setdefault('mysql_recovery_chain_retire_reviews', {}).update({review['review_id']: review}))
            return {**review, 'chain': public(chain)}
        if operation == 'retire' and isinstance(request, dict) and set(request) == {'review_id', 'review_digest', 'confirmed'} and request['confirmed'] is True:
            review = state.get('mysql_recovery_chain_retire_reviews', {}).get(identity(request['review_id']))
            if review is None or review['review_digest'] != request['review_digest']:
                raise BinlogArchiveError('Review the exact recovery dependency retirement')
            chain = chains[review['chain_id']]
            if chain['state'] == 'retired' and chain.get('retirement_review_id') == review['review_id']:
                return public(chain)
            if time.time() > review['expires_at'] or digest(chain) != review['snapshot']:
                raise BinlogArchiveError('Recovery dependencies changed; prepare a new retirement review')
            result = {**chain, 'state': 'retired', 'retired_at': time.time(), 'retirement_review_id': review['review_id']}
            store.change(lambda value: value['mysql_recovery_chains'].update({chain['chain_id']: result}))
            return public(result)
        raise BinlogArchiveError('Select a recovery dependency action')


def action(service, server, jobs, owner, endpoint, operation, request):
    from mysql.connector import Error as NativeError
    from ..sdk.relational import RelationalClientError
    registry = jobs.backup_protection
    if operation in {'list', 'review_retire', 'retire'}:
        return offline(registry, owner, endpoint.id, operation, request)
    if operation not in {'review', 'activate'}:
        raise BinlogArchiveError('Select a recovery dependency action')
    if not isinstance(request, dict):
        raise BinlogArchiveError('A recovery dependency request is required')
    if operation == 'review':
        selected = selection(request)
    elif set(request) != {'review_id', 'review_digest', 'confirmed', 'source_lineage_confirmed'} or request['confirmed'] is not True or request['source_lineage_confirmed'] is not True:
        raise BinlogArchiveError('Confirm the reviewed dependencies and original GTID lineage; native GTID reuse is not attested')
    from ..providers.mysql_family.provider import MySQLPilotProvider
    from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
    context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, MySQLPilotProvider):
        raise BinlogArchiveError('Native MySQL recovery dependency client is unavailable')
    client = provider.client; route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
    connection = None
    from .mysql_instance_backup_service import manager as instance_manager
    instance_backups, _, _, _ = instance_manager(service, server)
    try:
        connection = client._connect({'route': {**route, 'database': None, 'autocommit': True, 'read_timeout': 15}})
        with registry.store(owner, endpoint.id) as store:
            if operation == 'activate':
                review = store.read().get('mysql_recovery_chain_reviews', {}).get(identity(request['review_id']))
                if review is None or review['review_digest'] != request['review_digest']:
                    raise BinlogArchiveError('Recovery dependency review is unavailable')
                existing = store.read().get('mysql_recovery_chains', {}).get(review['review_id'])
                if existing is not None:
                    return public(existing)
                if review['expires_at'] < time.time():
                    raise BinlogArchiveError('Recovery dependency review expired')
                selected = review['inputs']['selection']
            observed = inputs(registry, store, jobs, owner, endpoint.id, selected, client, route, connection, instance_backups)
            if operation == 'review':
                review = {'review_id': str(uuid.uuid4()), 'created_at': time.time(), 'expires_at': time.time() + 300, 'inputs': observed}
                review['review_digest'] = digest(review)
                store.change(lambda value: value.setdefault('mysql_recovery_chain_reviews', {}).update({review['review_id']: review}))
                return review
            if observed != review['inputs']:
                raise BinlogArchiveError('Recovery backup, archives or native identity changed; prepare a new review')
            record = {**observed, 'chain_id': review['review_id'], 'state': 'active', 'created_at': time.time(),
                      'source_lineage_operator_confirmed': True, 'native_log_generation_attested': False,
                      'blanket_backup_hold_retirement_issued': False}
            store.change(lambda value: value.setdefault('mysql_recovery_chains', {}).update({record['chain_id']: record}))
            return public(record)
    except NativeError as error:
        raise BinlogArchiveError('Native recovery dependency observation failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
    except RelationalClientError as error:
        raise BinlogArchiveError(str(error)) from None
    finally:
        if connection is not None:
            client._discard_failed_session(connection)
