"""Offline registered-file recovery; SQL attachment verification is separate."""
from pathlib import Path

from ..core import EndpointContext
from ..endpoints.profiles import registration_profile
from ..operations.store import JsonOperationStore
from ..providers.embedded_route import contained_database
from ..providers.sqlite.recovery import RecoveryError as Error, host, installed_library, options, program, source_state
from .sqlite_recovery_jobs import SQLiteRecoveryJobs, digest


def manager(service, server):
    from flask import current_app
    endpoint = server.endpoint_profile
    if endpoint is None or endpoint.profile_id != 'sqlite-native' or endpoint.provider_id != 'org.cdeadmin.sqlite':
        raise Error('Select a native SQLite registration')
    # Recovery is a filesystem operation on a private image. Requiring a valid
    # SQL attachment would make a corrupt registered file impossible to recover.
    # Do not mark its unverified runtime or unreadable catalog as verified.
    context = EndpointContext(endpoint_id=endpoint.id, mode='legacy_native', experience_family='sqlite',
        provider_id=endpoint.provider_id, provider_version=endpoint.provider_version or '0.1.0',
        profile_id=endpoint.profile_id, profile_version=endpoint.profile_version or '3.53.0',
        target_adapter_id=endpoint.target_adapter_id, target_adapter_version=endpoint.target_adapter_version or '0.1.0',
        **{name: getattr(endpoint, name) for name in ('pool_namespace', 'session_namespace', 'cache_namespace', 'diagnostic_namespace')})
    admitted = service.endpoint_service.provider_registry.admitted_permissions(context)
    if not {'filesystem', 'backup_admin', 'restore_admin'} <= set(admitted):
        raise Error('SQLite filesystem, backup and restore administration permissions are required')
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore): raise Error('SQLite recovery requires durable application storage')
    owner = service._principal_id(server)
    root = current_app.config.get('CDEADMIN_SQLITE_RECOVERY_ROOT') or str(store.path.parent / 'sqlite-recovery')
    with service._semantic_lock:
        jobs = getattr(service, 'sqlite_recovery_jobs', None)
        if jobs is None:
            jobs = service.sqlite_recovery_jobs = SQLiteRecoveryJobs(str(store.path) + '.sqlite-recovery', root)
            import atexit
            atexit.register(jobs.close)
    return jobs, owner, endpoint


def route(service, server, endpoint, target_id):
    target = service.endpoint_service._owned_database_target(endpoint, target_id)
    profile = registration_profile('sqlite-native')
    selected, _reference = service.endpoint_service._route_and_reference(server, endpoint, profile,
        database_override=target.database,
        database_options=service.endpoint_service._database_target_configuration(target), credential_target=target)
    return selected


def action(service, server, operation, request):
    from flask import current_app
    if not isinstance(request, dict): raise Error('Select a registered SQLite recovery file')
    jobs, owner, endpoint = manager(service, server)
    library_path = current_app.config.get('CDEADMIN_SQLITE_RECOVERY_LIBRARY') or installed_library()
    target = request.get('database_target_id')
    if operation == 'catalog':
        if set(request) - {'database_target_id'}: raise Error('Invalid recovery catalog request')
        if target is not None: service.endpoint_service._owned_database_target(endpoint, target)
        directory = jobs.prepare(owner, endpoint.id, target or 'native-runtime')
        try:
            runtime = program(library_path, directory)
            native = {'available': True, 'native': runtime['native']}
        except (Error, OSError, ValueError):
            native = {'available': False, 'reason': 'SQLite recovery runtime is unavailable on this application host'}
        return {'execution_host': host(), 'runtime': native,
            'runtime_verification_state': getattr(endpoint.runtime_identity, 'verification_state', None),
            'targets': [{'target_id': item.id, 'display_name': item.display_name, 'path': item.database}
                        for item in endpoint.database_targets],
            'scope': 'Native salvage into a new contained file; the original is opened only for read-only image capture'}
    if not isinstance(target, str) or not target: raise Error('Select an exact registered SQLite file')
    fields = {key: value for key, value in request.items() if key != 'database_target_id'}
    if operation == 'list':
        if set(fields) - {'offset', 'limit'}: raise Error('Invalid recovery receipt page')
        return jobs.list(owner, endpoint.id, target, **fields)
    if operation in {'status', 'cancel', 'reconcile'}:
        if set(fields) != {'job_id'}: raise Error('Select one recovery job')
        if operation == 'reconcile':
            record = jobs.load(fields['job_id'], owner, endpoint.id, target)
            current = route(service, server, endpoint, target)
            if contained_database({**current, 'database': record['source']['output_path']}) != record['source']['output_path']:
                raise Error('Recovered output is outside the current registered filesystem scope')
        return {'status': jobs.get, 'cancel': jobs.cancel, 'reconcile': jobs.reconcile}[operation](
            fields['job_id'], owner, endpoint.id, target)
    if operation == 'remove_images':
        if set(fields) != {'job_id', 'confirmation'}: raise Error('Confirm one recovery job image removal')
        return jobs.remove_images(fields['job_id'], owner, endpoint.id, target, fields['confirmation'])
    if operation == 'activate':
        if set(fields) != {'job_id', 'confirmation'}: raise Error('Confirm the recovered file before activation')
        record = jobs.load(fields['job_id'], owner, endpoint.id, target)
        output = record['source']['output_path']
        if fields['confirmation'] != output or record['state'] not in {'completed', 'artifact_verified'}:
            raise Error('Select and confirm a completed recovered copy')
        current = route(service, server, endpoint, target)
        if contained_database({**current, 'database': output}) != output:
            raise Error('Recovered output is outside the current registered filesystem scope')
        if record.get('activated_target_id'):
            service.endpoint_service._owned_database_target(endpoint, record['activated_target_id'])
            return {'database_target_id': record['activated_target_id'], 'receipt': jobs.public(record)}
        from ..providers.sqlite.recovery import digest_file
        if digest_file(output) != (record.get('result') or {}).get('artifact_sha256'):
            raise Error('The recovered file changed before registration')
        service.endpoint_service.attach_database(server, {'database': output, 'display_name': Path(output).name})
        selected = service.endpoint_service._unambiguous_database_target(endpoint, output)
        if selected is None: raise Error('Recovered copy registration is not independently observable')
        import time
        jobs.update(record, activated_target_id=selected.id, activated_at=time.time())
        return {'database_target_id': selected.id, 'receipt': jobs.get(record['job_id'], owner, endpoint.id, target)}
    if operation == 'start':
        record = jobs.load(fields.get('job_id'), owner, endpoint.id, target)
        if record['state'] != 'reviewed': return jobs.start(fields, owner, endpoint.id, target, None)
        selected = record['options']
    elif operation == 'review':
        if set(fields) != {'options'}: raise Error('Review exact native recovery options')
        selected = options(fields['options'])
    else: raise Error('Unknown SQLite recovery action')
    current = route(service, server, endpoint, target)
    directory = jobs.prepare(owner, endpoint.id, target)
    runtime = program(library_path, directory)
    limit = current_app.config.get('CDEADMIN_SQLITE_RECOVERY_MAX_RUNTIME_SECONDS', 86400)
    if type(limit) is not int or not 1 <= limit <= 86400 or selected['timeout_seconds'] > limit:
        raise Error('Recovery runtime exceeds the application host policy')
    configuration = digest({'route': current, 'profile_generation': endpoint.profile_generation,
        'program': runtime, 'root': str(jobs.root), 'runtime_limit': limit})
    if operation == 'review':
        captured = source_state(current, selected)
        return jobs.review(owner, endpoint.id, target, current, captured, runtime, selected, configuration)
    return jobs.start(fields, owner, endpoint.id, target, configuration)
