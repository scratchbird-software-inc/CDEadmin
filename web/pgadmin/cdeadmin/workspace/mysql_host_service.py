"""Reviewed native diagnostics on an explicitly selected database SSH host."""
from copy import deepcopy
from pathlib import Path
import threading
import base64
import hashlib
import time

from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..providers.mysql_family import mysql_host_transport as native
from ..providers.mysql_family.mysql_clone import configure, rows
from ..providers.mysql_family.mysql_log_purge import private_connection
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import DurableCancellation, MySQLBinlogJobs, digest, identity
from .mysql_monitoring_host import MySQLMonitoringHost


SERVICE_ACTIONS = {'service_start', 'service_stop', 'service_restart'}


def options(value):
    required = {'connection', 'executable', 'configuration_file', 'workspace', 'timeout_seconds'}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - {'operation', 'service', 'binding_job_id', 'disconnect_all_clients','configuration_replacement'}:
        raise native.HostError('Select the exact native host, executable, configuration and private workspace')
    selected = deepcopy(value); selected['connection'] = native.public_route(selected['connection'])
    for key in ('executable', 'workspace'):
        if not isinstance(selected[key], str) or not selected[key] or '\x00' in selected[key] or len(selected[key]) > 32768:
            raise native.HostError('Select bounded native host paths')
    config = selected['configuration_file']
    if config is not None and (not isinstance(config, str) or not config or '\x00' in config or len(config) > 32768):
        raise native.HostError('Select a native configuration filename or no defaults')
    if type(selected['timeout_seconds']) is not int or not 1 <= selected['timeout_seconds'] <= 3600:
        raise native.HostError('Select native diagnostic runtime from 1 through 3600 seconds')
    operation = selected.get('operation', 'validate_config')
    if operation not in SERVICE_ACTIONS | {'validate_config','deploy_config'}:
        raise native.HostError('Select a native MySQL host operation')
    if operation=='deploy_config':
        if config is None:raise native.HostError('Select an existing native option file to replace')
        replacement=selected.get('configuration_replacement')
        if isinstance(replacement,dict) and set(replacement)=={'base64'}:
            try:
                if not isinstance(replacement['base64'],str) or len(replacement['base64'])>700000:raise ValueError()
                data=base64.b64decode(replacement['base64'],validate=True)
            except (ValueError,TypeError):raise native.HostError('Select bounded exact native option-file bytes') from None
            selected['configuration_replacement']={**replacement,'sha256':hashlib.sha256(data).hexdigest()}
        try:native.mysql_host_configuration.content(selected,native.HostError)
        except (ValueError,TypeError):raise native.HostError('Select exact native option-file bytes and their SHA256') from None
    elif 'configuration_replacement' in selected:raise native.HostError('Option-file replacement applies only to native configuration installation')
    if operation in SERVICE_ACTIONS:
        service = selected.get('service')
        if (not isinstance(service, dict) or set(service) != {'manager', 'name'} or
                service['manager'] != 'systemd' or not isinstance(service['name'], str) or not service['name']):
            raise native.HostError('Select the exact native systemd MySQL unit')
        if operation in {'service_stop', 'service_restart'} and selected.get('disconnect_all_clients') is not True:
            raise native.HostError('Confirm disconnection of all clients on the native MySQL service')
        if selected.get('binding_job_id') is not None:
            selected['binding_job_id'] = identity(selected['binding_job_id'])
    elif set(selected) & {'service', 'binding_job_id', 'disconnect_all_clients'}:
        raise native.HostError('Service bindings apply only to native service actions')
    return selected


def credentials(value):
    if not isinstance(value, dict) or set(value) - {'password', 'private_key', 'private_key_password'}:
        raise native.HostError('Supply the explicitly selected SSH credential material')
    for name, content in value.items():
        if not isinstance(content, str) or len(content.encode('utf8')) > (1024 * 1024 if name == 'private_key' else 16384):
            raise native.HostError('SSH credential material exceeds its admitted bound')
    return dict(value)


def native_request(record, action):
    selected = record['options']
    value = {'schema': 'cdeadmin.mysql-native-host.v1', 'action': action,
            'binding': record['source_state']['host_binding'], 'executable': selected['executable'],
            'configuration_file': selected['configuration_file'], 'workspace': selected['workspace'],
            'timeout_seconds': selected['timeout_seconds'], 'reviewed': record['source_state']['remote_review'],
            'job_id': record['job_id'], 'input_digest': record['review_digest']}
    if selected.get('operation')=='deploy_config' and action!='status':value['configuration_replacement']=selected['configuration_replacement']
    if selected.get('operation') in SERVICE_ACTIONS:
        value.update(service=selected['service'], native_pid_file=record['source_state']['native_pid_file'],
                     previous_service_binding=record['source_state']['remote_review'].get('service'))
    return value


class HostJobs(MySQLBinlogJobs):
    operation = 'mysql_database_host_operation'
    review_warnings = (
        'Runs the selected native mysqld configuration check on the authenticated database-server SSH host. The application host is not the execution host.',
        'The native source UUID, host and data-directory identity, SSH public key, executable bytes and selected configuration graph bind this review. Includes, eligible directory members, permissions and resolved paths are rechecked before dispatch.',
        'For a selected configuration file, the native process working directory and HOME are its resolved parent directory, shown in the review. File observations before and after execution do not freeze concurrent writers or prove an atomic native read snapshot. Persisted settings and service arguments remain separate inputs.',
        'This checks native configuration acceptance. It does not start or stop a database, prove server readiness, qualify upgrades or verify physical recovery.',
        'Closing the viewer does not stop an admitted remote diagnostic. A lost SSH reply remains unknown; reconciliation reads its durable remote receipt without repeating the command.',
    )

    def public(self, record):
        result = super().public(record)
        result['execution_host'] = deepcopy(record['program']['execution_host'])
        if 'configuration_replacement' in result['options']:
            selected=result['options']['configuration_replacement'];result['options']['configuration_replacement']={'sha256':selected['sha256'],'content_omitted':True}
        result['remote_observation'] = deepcopy(record['source_state']['remote_review'])
        result['cancellation_scope'] = 'before_native_dispatch_only'
        result['source_identity_scope'] = record['source_state'].get('source_identity_scope', 'current_online_native_source')
        result['source_connection_class'] = record['source_state'].get('source_connection_class')
        return result

    def review(self, owner, endpoint, selected, captured, configuration, program, continuation=None):
        result = super().review(owner, endpoint, selected, captured, configuration, program, continuation)
        if selected.get('operation')=='deploy_config':
            record=self.load(result['job_id'],owner,endpoint)
            self.update(record,remote_database_mutation=True,warnings=list(self.review_warnings)+[
                'Installs the exact selected option-file bytes after native mysqld validation in a private Linux mount view. No service restart is issued.',
                'Original file ownership and permissions are preserved; a private original-file copy is retained with the host job. Native diagnostics can quote option values in this owner-scoped receipt.',
                'Review and dispatch compare the original and prospective include graphs. Concurrent external writers are not frozen. A missing reply never causes automatic replacement retry.'])
            result=self.get(record['job_id'],owner,endpoint)
        if selected.get('operation') in SERVICE_ACTIONS:
            record = self.load(result['job_id'], owner, endpoint)
            self.update(record, remote_database_mutation=True, warnings=list(self.review_warnings) + [
                'This request controls the exact selected native service. Stop/restart disconnect every client; native MySQL owns unfinished-transaction rollback and later recovery.',
                'The unit fragment/drop-in bytes and command identities are observed. External scripts, environment files and credentials remain native service-manager inputs; this review does not freeze a complete startup-input snapshot.',
                'The service-manager client outcome and subsequent unit/process facts do not prove SQL readiness. A timeout or lost SSH reply never causes automatic replay.',
                'An offline review uses the explicitly selected prior owner/registration service association. Its SQL principal facts are previous observations; current SSH host authority authorizes this service request.'])
            result = self.get(record['job_id'], owner, endpoint)
        return result

    def run(self, record, transport, signal):
        sent = False
        try:
            self.update(record, state='active', phase='before_native_dispatch')
            if DurableCancellation(self, record, signal).is_set():
                raise InterruptedError('Native host diagnostic cancelled before dispatch')
            self.update(record, phase='native_dispatch', native_may_have_dispatched=True)
            sent = True
            remote = transport.request(native_request(record, record['options'].get('operation', 'validate_config')),
                                       timeout=record['options']['timeout_seconds'] + 30)
            # Keep the original transport acknowledgement independently from
            # native process outcome and later observation/cleanup failures.
            self.update(record, ssh_reply_observed=True, remote_receipt=remote)
            if remote.get('input_digest') != record['review_digest']:
                raise native.HostError('The remote receipt does not match the admitted native host request')
            state = 'native_process_returned' if remote.get('state') == 'native_process_returned' else 'unknown'
            self.update(record, state=state, phase='finished', finished_at=time.time())
        except BaseException as error:
            self.update(record, state='unknown' if sent else 'cancelled' if signal.is_set() else 'not_dispatched',
                        phase='finished', error_type=type(error).__name__,
                        error_message=str(error) if isinstance(error, native.HostError) else None,
                        finished_at=time.time())
        finally:
            try:
                transport.close()
            finally:
                with self._maps_lock:
                    known = self.workers.get(record['job_id'])
                    if known and known[0] is threading.current_thread():
                        self.workers.pop(record['job_id'], None)

    def cancel(self, job_id, owner, endpoint):
        record = self.load(job_id, owner, endpoint)
        if record.get('native_may_have_dispatched') and record['state'] in {'active', 'dispatching', 'cancel_requested'}:
            raise native.HostError('An admitted remote diagnostic cannot be revoked by closing its viewer; wait for its receipt or reconcile a lost reply')
        return super().cancel(job_id, owner, endpoint)


def manager(service, server):
    from flask import current_app
    endpoint = server.endpoint_profile
    if endpoint is None or endpoint.profile_id != 'mysql-native' or endpoint.provider_id != 'org.cdeadmin.mysql':
        raise native.HostError('Select a native MySQL registration for host administration')
    context = EndpointContext(endpoint_id=endpoint.id, mode='legacy_native', experience_family='mysql',
        provider_id=endpoint.provider_id, provider_version=endpoint.provider_version or '0.1.0',
        profile_id=endpoint.profile_id, profile_version=endpoint.profile_version or '9.7.0',
        target_adapter_id=endpoint.target_adapter_id, target_adapter_version=endpoint.target_adapter_version or '0.1.0',
        **{name: getattr(endpoint, name) for name in ('pool_namespace', 'session_namespace', 'cache_namespace', 'diagnostic_namespace')})
    if 'administer' not in service.endpoint_service.provider_registry.admitted_permissions(context):
        raise native.HostError('Native host diagnostics require administration authority')
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise native.HostError('Native host diagnostics require durable application storage')
    with service._semantic_lock:
        jobs = getattr(service, 'mysql_host_jobs', None)
        if jobs is None:
            root = current_app.config.get('CDEADMIN_MYSQL_HOST_RECEIPT_ROOT') or str(store.path.parent / 'mysql-native-host-receipts')
            jobs = service.mysql_host_jobs = HostJobs(str(store.path) + '.mysql-host', root)
            import atexit
            atexit.register(jobs.close)
    return jobs, service._principal_id(server), endpoint


def source(service, server, *, admitted=None):
    context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, MySQLPilotProvider):
        raise native.HostError('Native MySQL host binding is unavailable')
    from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
    route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
    client,route=admitted if admitted is not None else (provider.client,route)
    connection = private_connection(client, {**route, 'database': None, 'read_timeout': 5, 'write_timeout': 5})
    try:
        configure(connection)
        value = rows(connection, 'SELECT VERSION() AS version,@@server_uuid AS server_uuid,'
            '@@hostname AS hostname,@@datadir AS datadir,@@pid_file AS native_pid_file,CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role')[0]
        if value['version'].split('-')[0] != '9.7.0':
            raise native.HostError('Native host diagnostics require MySQL9.7.0')
        return {'identity': {key: value[key] for key in ('version', 'server_uuid', 'authenticated_principal', 'active_role')},
                'state': {'host_binding': {key: value[key] for key in ('server_uuid', 'hostname', 'datadir')},
                          'native_pid_file': value['native_pid_file'],
                          'source_connection_class': type(connection).__name__}}
    finally:
        client._discard_failed_session(connection)


def program(peer, observed):
    return {**native.program(), 'native_executable': observed['program'],
            'execution_host': {**peer, 'kind': 'database-server-ssh-host',
                               'platform': observed['host']['platform'], 'hostname': observed['host']['hostname']}}


def capture(service, server, jobs, owner, endpoint, selected, configuration):
    reference = selected.get('binding_job_id')
    if reference is None:
        return source(service, server)
    known = jobs.load(reference, owner, endpoint)
    old_connection = known['options']['connection']; connection = selected['connection']
    association = known['source_state'].get('remote_review', {}).get('service')
    if (known['configuration'] != configuration or not association or
            association.get('service_binding_verified') is not True or
            association.get('selected_service') != selected['service'] or
            any(old_connection.get(key) != connection.get(key) for key in ('host', 'port', 'host_key', 'platform'))):
        raise native.HostError('Select a verified service association for this registration and pinned database host')
    return {'identity': deepcopy(known['source']), 'state': {
        'host_binding': deepcopy(known['source_state']['host_binding']),
        'native_pid_file': known['source_state']['native_pid_file'],
        'source_connection_class': known['source_state'].get('source_connection_class'),
        'source_identity_scope': 'previous_online_service_association',
        'binding_job_id': reference, 'previous_service_binding': deepcopy(association)}}


def action(service, server, operation, request):
    if not isinstance(request, dict):
        raise native.HostError('Select a native database-host request')
    jobs, owner, endpoint = manager(service, server)
    if operation == 'peer' and set(request) == {'host', 'port'}:
        return native.probe(request['host'], request['port'])
    if operation == 'list' and not set(request) - {'offset', 'limit'}:
        return jobs.list(owner, endpoint.id, **request)
    if operation in {'status', 'cancel'} and set(request) == {'job_id'}:
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint.id)
    if operation == 'catalog' and not request:
        return source(service, server)
    record = None
    if operation in {'start', 'reconcile'}:
        record = jobs.load(request.get('job_id'), owner, endpoint.id)
        fields = {'job_id', 'credentials'} | ({'review_digest', 'confirmed'} if operation == 'start' else set())
        if set(request) != fields:
            raise native.HostError('Select one exact reviewed native host request')
        admitted = {key: request[key] for key in ('job_id', 'review_digest', 'confirmed')} if operation == 'start' else None
        if operation == 'start':
            if request['confirmed'] is not True:
                raise native.HostError('Confirm this exact native database-host review')
            if record['state'] != 'reviewed':
                return jobs.start(admitted, owner, endpoint.id, {}, None)
        elif jobs.get(record['job_id'], owner, endpoint.id)['state'] in {'dispatching', 'active', 'cancel_requested'}:
            raise native.HostError('Wait for the admitted host diagnostic before reconciliation')
        selected = record['options']
    elif operation == 'review' and set(request) == {'options', 'credentials'}:
        selected = options(request['options'])
    else:
        raise native.HostError('Native host action is unavailable')
    configuration = digest(MySQLMonitoringHost._configuration(server))
    if record is not None and operation!='reconcile' and (record['configuration'] != configuration or
            any(record['program'].get(key) != value for key, value in native.program().items())):
        raise native.HostError('Use the recorded registration, host adapter and file-permission helper for this receipt')
    transport = native.Transport(selected['connection'], credentials(request['credentials']))
    try:
        peer = transport.connect()
        if operation == 'reconcile':
            remote = transport.request(native_request(record, 'status'))
            if remote.get('input_digest') != record['review_digest']:
                raise native.HostError('The remote receipt does not match this reviewed native host job')
            jobs.update(record, reconciliation={'remote_receipt': remote, 'observed_at': time.time(),
                        'original_ssh_acknowledgement_unchanged': True})
            return jobs.get(record['job_id'], owner, endpoint.id)
        captured = capture(service, server, jobs, owner, endpoint.id, selected, configuration)
        inspection = {'schema': 'cdeadmin.mysql-native-host.v1', 'action': 'inspect',
            'binding': captured['state']['host_binding'], 'executable': selected['executable'],
            'configuration_file': selected['configuration_file']}
        if selected.get('operation')=='deploy_config':inspection['configuration_replacement']=selected['configuration_replacement']
        if selected.get('operation') in SERVICE_ACTIONS:
            inspection.update(service=selected['service'], native_pid_file=captured['state']['native_pid_file'],
                              previous_service_binding=captured['state'].get('previous_service_binding'))
        observed = transport.request(inspection)
        captured['state']['remote_review'] = observed
        executable = program(peer, observed)
        if operation == 'review':
            return jobs.review(owner, endpoint.id, selected, captured, configuration, executable)
        if captured['state'] != record['source_state']:
            raise native.HostError('The native source or host observation changed; prepare a new review')
        attached, transport = transport, None
        return jobs.start(admitted, owner, endpoint.id,
            {'configuration': configuration, 'source': captured['identity'], 'program': executable}, attached)
    finally:
        if transport is not None:
            transport.close()
