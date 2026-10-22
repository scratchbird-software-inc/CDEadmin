"""Owned native MySQL topology operations and explicit instance references."""
import atexit
import hashlib
import json
from pathlib import Path

from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..security import SecretLease
from ..providers.mysql_family import mysql_topology as native
from ..providers.mysql_family import mysql_topology_quiescence as quiescence
from ..providers.mysql_family.mysql_log_purge import private_connection
from ..providers.mysql_family.mysql_binlog_archives import delegate_credentials, program_identity, rows
from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import digest
from .mysql_binlog_replay_jobs import MySQLBinlogReplayJobs
from .mysql_binlog_replay_service import source_server
from .mysql_monitoring_host import MySQLMonitoringHost
from .mysql_topology_jobs import TopologyJobs, TopologyTransport


def admitted_context(service, server):
    endpoint = server.endpoint_profile
    if endpoint is None or endpoint.profile_id != 'mysql-native' or endpoint.provider_id != 'org.cdeadmin.mysql':
        raise native.BinlogArchiveError('Select an owned native MySQL registration')
    admitted = EndpointContext(endpoint_id=endpoint.id, mode='legacy_native', experience_family='mysql',
        provider_id=endpoint.provider_id, provider_version=endpoint.provider_version or '0.1.0',
        profile_id=endpoint.profile_id, profile_version=endpoint.profile_version or '9.7.0',
        target_adapter_id=endpoint.target_adapter_id, target_adapter_version=endpoint.target_adapter_version or '0.1.0',
        **{name: getattr(endpoint, name) for name in ('pool_namespace', 'session_namespace', 'cache_namespace', 'diagnostic_namespace')})
    if 'administer' not in service.endpoint_service.provider_registry.admitted_permissions(admitted):
        raise native.BinlogArchiveError('Native topology administration permission is unavailable')
    return admitted


def context(service, server):
    admitted_context(service, server)
    admitted, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(admitted).instance
    if not isinstance(provider, MySQLPilotProvider): raise native.BinlogArchiveError('Native MySQL topology client is unavailable')
    return provider.client, {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}


def manager(service, server):
    from flask import current_app
    admitted_context(service, server)
    owner, endpoint = service._principal_id(server), server.endpoint_profile
    store = service.operation_bus.store
    if not isinstance(store, JsonOperationStore): raise native.BinlogArchiveError('Native topology operations require durable application storage')
    with service._semantic_lock:
        replays = getattr(service, 'mysql_binlog_replay_jobs', None)
        if replays is None:
            root = current_app.config.get('CDEADMIN_MYSQL_BINLOG_REPLAY_ROOT') or str(store.path.parent / 'mysql-binary-log-replays')
            replays = service.mysql_binlog_replay_jobs = MySQLBinlogReplayJobs(str(store.path) + '.mysql-replay', root)
            atexit.register(replays.close)
        jobs = getattr(service, 'mysql_topology_jobs', None)
        if jobs is None:
            root = current_app.config.get('CDEADMIN_MYSQL_TOPOLOGY_ROOT') or str(store.path.parent / 'mysql-topology')
            jobs = service.mysql_topology_jobs = TopologyJobs(str(store.path) + '.mysql-topology', root)
            atexit.register(jobs.close)
        jobs.replay_jobs = replays
        from .mysql_backup_protection import manager as backup_protection
        jobs.backup_protection = backup_protection(service)
    return jobs, owner, endpoint


def action(service, server, operation, request):
    from mysql.connector import Error as NativeError
    from pgadmin.model import Server
    if not isinstance(request, dict): raise native.BinlogArchiveError('Select a native topology request')
    account_secret = None
    if operation == 'start' and 'account_secret' in request:
        request = dict(request)
        account_secret = request.pop('account_secret')
        if (not isinstance(account_secret, dict) or set(account_secret) != {'password'} or
                not isinstance(account_secret['password'], str)):
            raise native.BinlogArchiveError('Supply the native account password separately from the retained review')
        try: valid_secret = len(account_secret['password'].encode('utf8')) <= 1024*1024
        except UnicodeError: valid_secret = False
        if not valid_secret: raise native.BinlogArchiveError('Supply bounded valid UTF-8 account password text')
    jobs, owner, endpoint = manager(service, server)
    if operation == 'catalog' and not request:
        return {'version': '9.7.0', 'operations': [{'id': key, **value} for key, value in native.CALLS.items()]}
    if operation == 'inspect_native' and set(request) == {'options'}:
        selected = native.options(request['options'])
        if not native.CALLS[selected['operation']]['read_only']:
            raise native.BinlogArchiveError('Select a read-only native inspection')
        reviewed = action(service, server, 'review', request)
        return action(service, server, 'start', {'job_id': reviewed['job_id'],
            'review_digest': reviewed['review_digest'], 'confirmed': True})
    if operation == 'list' and not set(request) - {'offset', 'limit'}:
        return jobs.list(owner, endpoint.id, **request)
    if operation in {'status', 'cancel'} and set(request) == {'job_id'}:
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint.id)
    if operation == 'members' and not set(request) - {'offset', 'limit'}:
        offset, limit = request.get('offset', 0), request.get('limit', 25)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise native.BinlogArchiveError('Select a bounded registered-instance page')
        values = [item for item in Server.query.filter_by(user_id=owner).order_by(Server.id) if
            item.endpoint_profile is not None and item.endpoint_profile.profile_id == 'mysql-native' and
            item.endpoint_profile.provider_id == 'org.cdeadmin.mysql']
        return {'instances': [{'server_id': item.id, 'name': item.name} for item in values[offset:offset+limit]],
                'offset': offset, 'limit': limit, 'total': len(values)}
    if operation == 'review' and set(request) == {'options'}:
        selected = native.options(request['options']); record = None
    elif operation == 'start':
        record = jobs.load(request.get('job_id'), owner, endpoint.id)
        if record['state'] != 'reviewed': return jobs.start(request, owner, endpoint.id, {}, None)
        selected = record['options']
    elif operation == 'inspect' and not request:
        selected = record = None
    elif operation in {'reconcile', 'acknowledge'} and set(request) == ({'job_id'} if operation == 'reconcile' else {'job_id', 'target_confirmation', 'observation_digest'}):
        record = jobs.load(request['job_id'], owner, endpoint.id); selected = record['options']
    else: raise native.BinlogArchiveError('Select a native topology action')
    setting_password = bool(selected is not None and native.CALLS[selected['operation']].get('account') and selected['account_password_mode'] == 'set')
    if operation == 'start' and setting_password != (account_secret is not None):
        raise native.BinlogArchiveError('The reviewed account password mode and separately supplied password must agree')
    client, route = context(service, server)
    connection = None; leases = []; transport = None
    try:
        connection = private_connection(client, {**route, 'database': None, 'autocommit': True, 'read_timeout': 15})
        observed = native.capture(connection)
        if operation == 'inspect': return {**observed, 'native_mutation_dispatched': False}
        if operation in {'reconcile', 'acknowledge'}:
            if observed['identity'] != record['source']: raise native.BinlogArchiveError('Topology reconciliation reached another native instance or principal')
            if operation == 'reconcile':
                jobs.observe_utility(record)
                record = jobs.load(record['job_id'], owner, endpoint.id)
            observation = {**observed, 'native_lock_free': rows(connection, 'SELECT IS_FREE_LOCK(%s) AS free',
                ('cdeadmin:binlog-load:' + record['source']['server_uuid'],))[0]['free'] == 1,
                'scope': 'Current seed and visible native metadata identities; no workload readiness or attribution of concurrent topology changes'}
            if record['options']['operation'] in native.SERVER_WORK_CALLS:
                observation['server_recovery_quiescence'] = recovery_quiescence(service, jobs, record, connection)
            if operation == 'acknowledge': return jobs.acknowledge(record, observation, request)
            result = jobs.reconcile(record, observation); result['observation_digest'] = digest(observation); return result
        if selected['target_confirmation'] != observed['identity']['server_uuid']:
            raise native.BinlogArchiveError('Confirm the exact native topology seed UUID')
        seed = {'identity': observed['identity'], 'metadata': observed['metadata'], 'observation': observed,
                'connection': native.connection(client, route, observed, selected)}
        if native.CALLS[selected['operation']].get('account'):
            seed['account_state'] = native.accounts.capture(connection, native.parse(selected['arguments_json'])[0],
                native.CALLS[selected['operation']]['context'])
        members = {}; configurations = {'seed': MySQLMonitoringHost._configuration(server)}
        credentials = {}
        def acquire(key, member_client, member_route):
            lease = delegate_credentials(member_client, member_route); leases.append(lease)
            credentials[key] = lease.use(lambda view: json.loads(bytes(view)))
        if operation == 'start': acquire('seed', client, route)
        if operation == 'start' and setting_password: credentials['account'] = dict(account_secret)
        for server_id in native.member_ids(selected):
            member_server = source_server(owner, server_id)
            member_client, member_route = context(service, member_server)
            member_connection = private_connection(member_client, {**member_route, 'database': None, 'autocommit': True, 'read_timeout': 15})
            try: member = native.capture(member_connection)
            finally: member_client._discard_failed_session(member_connection)
            members[str(server_id)] = {'server_id': server_id, 'endpoint_id': member_server.endpoint_profile.id,
                'identity': member['identity'],
                'connection': native.connection(member_client, member_route, member, selected)}
            configurations[str(server_id)] = MySQLMonitoringHost._configuration(member_server)
            if operation == 'start': acquire(str(server_id), member_client, member_route)
        argument_ids = native.member_ids({**selected, 'witness_server_ids': []})
        allowed_witnesses = {observed['identity']['server_uuid'], *observed['metadata']['instance_uuids'],
            *(members[str(server_id)]['identity']['server_uuid'] for server_id in argument_ids)}
        if any(members[str(server_id)]['identity']['server_uuid'] not in allowed_witnesses for server_id in selected.get('witness_server_ids', [])):
            raise native.BinlogArchiveError('Recovery observations must select native topology members or the selected operation instances')
        workspace = jobs.prepare_scope(owner, endpoint.id)
        program = program_identity(client, route, workspace)
        configuration = digest({'registrations': configurations, 'root': str(jobs.root),
            'adapter_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
            **({'account_adapter_sha256': hashlib.sha256(Path(native.accounts.__file__).read_bytes()).hexdigest()}
               if native.CALLS[selected['operation']].get('account') else {}),
            **({'fanout_adapter_sha256': hashlib.sha256(Path(native.fanout.__file__).read_bytes()).hexdigest()}
               if native.CALLS[selected['operation']].get('fanout') else {})})
        if operation == 'review':
            return jobs.review(owner, endpoint.id, selected, {'identity': observed['identity'],
                'state': {'seed': seed, 'members': members}}, configuration, program)
        if {'seed': seed, 'members': members} != record['source_state']:
            raise native.BinlogArchiveError('Native topology seed, selected instances or metadata changed after review')
        transport = TopologyTransport(client, route, SecretLease(native.canonical(credentials).encode('utf8')), connection, jobs)
        connection = None; admitted = transport; transport = None
        return jobs.start(request, owner, endpoint.id, {'configuration': configuration,
            'source': observed['identity'], 'program': program}, admitted)
    except NativeError as error:
        raise native.BinlogArchiveError('Native topology admission failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
    finally:
        for lease in leases: lease.close()
        if connection is not None: client._discard_failed_session(connection)
        if transport is not None: transport.close()


def recovery_quiescence(service, jobs, record, seed_connection):
    try:
        witness = quiescence.load(jobs.directory(record), record)
        expected = {'seed': record['source'], **{key: member['identity'] for key, member in record['source_state']['members'].items()}}
        if set(witness['targets']) != set(expected): raise native.BinlogArchiveError('Native recovery observation scope changed')
        admitted = {value['profile']['identity']['server_uuid'] for value in witness['targets'].values() if value.get('admitted') is True}
        missing = sorted(set(jobs.fence_identities(record))-admitted)
        if missing:
            return {'qualified': False, 'idle': None, 'reason': 'Native member ownership was not admitted before dispatch',
                'unqualified_native_instances': missing}
        targets = {}
        for key, identity in expected.items():
            original = witness['targets'][key]
            if original.get('profile', {}).get('identity') != identity:
                raise native.BinlogArchiveError('Native recovery owner identity changed')
            if key == 'seed':
                targets[key] = quiescence.observe(seed_connection, original, witness['pid'])
                continue
            member = record['source_state']['members'][key]
            owned = None
            try:
                registered = source_server(record['owner'], member['server_id'])
                if registered.endpoint_profile.id != member['endpoint_id']:
                    raise native.BinlogArchiveError('Native recovery member registration changed')
                member_client, route = context(service, registered)
                owned = private_connection(member_client, {**route, 'database': None, 'autocommit': True, 'read_timeout': 15})
                targets[key] = quiescence.observe(owned, original, witness['pid'])
            except Exception as error:
                targets[key] = {'qualified': False, 'idle': None, 'error_type': type(error).__name__}
            finally:
                if owned is not None: member_client._discard_failed_session(owned)
        qualified = all(value.get('qualified') is True for value in targets.values())
        return {'qualified': qualified, 'idle': all(value.get('idle') is True for value in targets.values()) if qualified else None,
            'targets': targets, 'scope': 'Reviewed native members, original utility sessions and current clone activity; original outcome remains unchanged'}
    except Exception as error:
        return {'qualified': False, 'idle': None, 'error_type': type(error).__name__}
