"""Owner-authorized native workload inspection on disposable observer sessions."""
from ..providers.mysql_family.mysql_monitoring import MySQLMonitor
from ..providers.mysql_family import mysql_workload as native
from ..providers.mysql_family.mysql_script import Statements


def action(service, server, operation, request):
    if not isinstance(request, dict):
        raise native.WorkloadError('A native workload request is required')
    endpoint = server.endpoint_profile
    if endpoint is None or endpoint.profile_id != 'mysql-native' or endpoint.provider_id != 'org.cdeadmin.mysql':
        raise native.WorkloadError('Select a native MySQL registration')
    target = request.get('database_target_id')
    context, payload, _ = service.endpoint_service.workspace(server, database_target_id=target)
    registry = service.endpoint_service.provider_registry
    if 'administer' not in registry.admitted_permissions(context):
        raise native.WorkloadError('Workload inspection requires endpoint administration authority')
    binding = registry.resolve(context)
    route = payload['route']
    selected_schema = request.get('schema_name')
    if target is not None:
        if selected_schema is not None and selected_schema != route.get('database'):
            raise native.WorkloadError('The workload schema differs from the registered target')
        selected_schema = route.get('database')
    native.schema_name(selected_schema)
    fields = set(request) - {'database_target_id'}
    allowed = {'snapshot': {'schema_name', 'rank'}, 'waits': {'schema_name', 'digest'},
        'sample': {'schema_name', 'digest', 'confirmed'},
        'plan': {'schema_name', 'digest', 'confirmed', 'sample_sha256'},
        'slow_table': {'schema_name', 'start_utc', 'end_utc', 'confirmed'},
        'slow_file': {'schema_name', 'start_utc', 'end_utc', 'text', 'confirmed'}}
    if operation not in allowed or fields - allowed[operation]:
        raise native.WorkloadError('Unsupported native workload action')
    if operation in {'sample', 'plan', 'slow_table', 'slow_file'} and request.get('confirmed') is not True:
        raise native.WorkloadError('Explicit private SQL inspection is required')
    # No interactive session, pool, operation receipt, SQL history or dashboard
    # persistence is involved. Native server logging remains server-owned.
    observer = MySQLMonitor(binding.permissions, route, scope='database' if target else 'server')
    try:
        observer._open()
        identity = observer._read(observer.identity_source)[0]
        if identity['version'].split('-')[0] != '9.7.0' or identity['database_name'] != route.get('database'):
            raise native.WorkloadError('The workload observer native identity changed')
        selected = {'schema_name': selected_schema, 'digest': request.get('digest')}
        if operation == 'snapshot':
            result = native.observe(observer, selected_schema, request.get('rank', 'total_latency'))
        elif operation == 'waits':
            result = native.digest_waits(observer, selected)
        elif operation in {'sample', 'plan'}:
            result = native.private_sample(observer, selected)
            if operation == 'plan':
                if request.get('sample_sha256') != result['sample_sha256']:
                    raise native.WorkloadError('The displayed native SQL sample changed; inspect it again')
                if selected_schema is not None:
                    observer._connection.database = selected_schema
                settings = observer._read('SELECT @@sql_mode AS sql_mode')[0]
                statements = Statements(result['query_sample_text'])
                command = statements.next('9.7.0', settings['sql_mode'])
                if command is None or statements.has_next('9.7.0', settings['sql_mode']):
                    raise native.WorkloadError('The native sample is not one complete statement')
                import re
                if not re.match(r'\s*(?:SELECT|WITH|UPDATE|DELETE|INSERT|REPLACE)\b', command, re.I):
                    raise native.WorkloadError('The sample has no supported native EXPLAIN statement prefix')
                # Deliberately no ANALYZE. Native EXPLAIN still needs explicit
                # operator consent; native optimizer/functions own its effects.
                rows = observer._read('EXPLAIN FORMAT=JSON ' + command)
                result = {'rendered': {'view_model': {'columns': [{'name': 'EXPLAIN'}],
                    'rows': [[row['explain']] for row in rows]}}, 'sql_mode': settings['sql_mode'],
                    'sample_sha256': result['sample_sha256'],
                    'basis': 'Current observer settings and current schema; not original session settings. Native optimizer may evaluate expressions.'}
        elif operation == 'slow_table':
            result = native.slow_table(observer, {k: (selected_schema if k == 'schema_name' else request.get(k))
                for k in ('schema_name', 'start_utc', 'end_utc')})
        else:
            start, end = native.cutoff(request.get('start_utc')), native.cutoff(request.get('end_utc'))
            entries = native.parse_slow_file(request.get('text'), selected_schema, start, end)
            result = native.aggregate_log(observer, entries, source='uploaded-native-slow-log',
                window={'schema_name': selected_schema, 'start_utc': request.get('start_utc'), 'end_utc': request.get('end_utc')})
        if observer._transaction_active():
            raise native.WorkloadError('The native workload observer retained a transaction')
        return {**result, 'identity': identity, 'connection': 'dedicated-observer', 'history': 'not recorded'}
    finally:
        observer.close()
