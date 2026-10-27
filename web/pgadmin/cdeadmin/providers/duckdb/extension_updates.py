"""Native extension update results and nontransactional file effects."""
from collections.abc import Mapping
from copy import deepcopy

from ...sdk import RelationalClientError
from ...security.redaction import redact_text
from .object_metadata import native

FIELDS = ('extension_name', 'loaded', 'installed', 'install_path', 'description',
    'aliases', 'extension_version', 'install_mode', 'installed_from')
SELECT = 'SELECT ' + ','.join(FIELDS) + ' FROM duckdb_extensions() ORDER BY extension_name'
OPERATIONS = frozenset({('extension', 'update'), ('database', 'update_extensions')})


def inventory(connection):
    rows = [dict(zip(FIELDS, row)) for row in connection.execute(SELECT).fetchall()]
    for row in rows:
        if isinstance(row['installed_from'], str):
            row['installed_from'] = redact_text(row['installed_from'])
    return rows


def context(connection):
    row = connection.execute("SELECT version(),current_setting('extension_directory'),"
        "current_setting('home_directory')").fetchone()
    return dict(zip(('runtime_version', 'extension_directory', 'home_directory'), row))


def compile_operation(adapter, request):
    kind, operation = request.get('resource_kind'), request.get('operation_id')
    target, draft = request.get('target_resource'), request.get('draft')
    if ((kind, operation) not in OPERATIONS or not isinstance(target, Mapping) or
            target.get('resource_kind') != kind or not isinstance(draft, Mapping) or
            set(draft) != {'confirmation', 'filesystem_effects_acknowledged'} or
            draft.get('filesystem_effects_acknowledged') is not True or
            draft.get('confirmation') != target.get('display_name')):
        raise RelationalClientError('Review the exact DuckDB extension target and native file effects')
    path = adapter._target_path(target)
    if len(path) != 1 or path[0] != target.get('display_name'):
        raise RelationalClientError('Select an exact DuckDB extension update address')
    value = native(target)
    observed_context = value.get('extension_update_context')
    if not isinstance(observed_context, Mapping) or observed_context.get('runtime_version') != 'v1.5.2':
        raise RelationalClientError('Exact native DuckDB extension installation context is unavailable')
    if kind == 'extension':
        baseline = value.get('catalog_metadata')
        if not isinstance(baseline, Mapping) or baseline.get('extension_name') != path[0]:
            raise RelationalClientError('Exact DuckDB extension metadata is unavailable')
        if baseline.get('installed') is not True or baseline.get('install_mode') == 'STATICALLY_LINKED':
            raise RelationalClientError('Select an installed native extension file; built-in code has no updateable file')
        baseline = [deepcopy(dict(baseline))]
        source = 'UPDATE EXTENSIONS (' + adapter._quote(path[0]) + ')'
    else:
        baseline = value.get('extension_inventory')
        if not isinstance(baseline, list):
            raise RelationalClientError('Complete native DuckDB extension inventory is unavailable')
        source = 'UPDATE EXTENSIONS'
    if any(not isinstance(row, Mapping) or set(row) != set(FIELDS) for row in baseline):
        raise RelationalClientError('Complete native DuckDB extension facts are required')
    return {'statements': [{'source': source, 'parameters': ()}],
        'duckdb_extension_update': {'kind': kind, 'operation': operation,
            'target': deepcopy(dict(target)), 'draft': dict(draft),
            'baseline': deepcopy(baseline), 'context': dict(observed_context)},
        'warnings': [
            'Extension updates write native installation files outside database transactions. Rollback does not undo these files.',
            'Loaded extension code stays loaded; updated binaries take effect in a new native database instance.',
            'An update of several extensions can change some files before a later failure. Automatic replay is disabled.']}


def form(kind, operation, field):
    return {'form_id': 'duckdb.' + kind + '.' + operation,
        'title': 'Update native DuckDB extension' if kind == 'extension' else 'Update all installed DuckDB extensions',
        'fields': [field('confirmation', 'Exact object name', 'text', True),
            field('filesystem_effects_acknowledged',
                'I reviewed the native extension files and accept effects outside database rollback', 'boolean', True)]}


def apply(adapter, client, request, connection=None):
    compiled = request['provider_payload']['compiled'];intent = compiled['duckdb_extension_update']
    rebuilt = compile_operation(adapter, {'resource_kind': intent['kind'],
        'operation_id': intent['operation'], 'target_resource': intent['target'], 'draft': intent['draft']})
    if rebuilt != compiled:
        raise RelationalClientError('The reviewed DuckDB extension update changed')
    owns_connection = connection is None
    if owns_connection:
        connection = client._connect({'route': request['provider_payload']['route']})
    dispatched = acknowledged = False
    try:
        from .provider import _resources
        target = intent['target']
        live = next((row for row in _resources(connection, {'session_catalog': True})
            if row['resource_id'] == target['resource_id']), None)
        if (live is None or live['resource_kind'] != target['resource_kind'] or
                live['display_path'] != target['display_path']):
            raise RelationalClientError('DuckDB extension update resource identity changed')
        before = inventory(connection)
        selected = before if intent['kind'] == 'database' else [
            row for row in before if row['extension_name'] == target['display_name']]
        if selected != intent['baseline'] or context(connection) != intent['context']:
            raise RelationalClientError('DuckDB extension installation or directory changed since review')
        dispatched = True
        connection.execute(compiled['statements'][0]['source'])
        acknowledged = True
        names = [str(column[0]) for column in connection.description]
        rows = [dict(zip(names, row)) for row in connection.fetchall()]
        for row in rows:
            if isinstance(row.get('repository'), str):
                row['repository'] = redact_text(row['repository'])
        after = inventory(connection)
        if not owns_connection:
            client._observe(connection)
        return {'accepted': True, 'commit_requested': False, 'rollback_requested': False,
            'staged_in_provider_session': False, 'driver_observation_only': True,
            'transaction_finality_interpreted_by_common_code': False,
            'extension_update_observation': {'native_acknowledged': True,
                'native_results': rows, 'before': selected,
                'after': after if intent['kind'] == 'database' else [
                    row for row in after if row['extension_name'] == target['display_name']],
                'effects_outside_database_transaction': True,
                'loaded_code_replaced': False, 'caller_transaction_decision_requested': False},
            'automatic_retry': False}
    except BaseException as error:
        if not owns_connection:
            from .driver import uncertain
            try:
                client._observe(connection, blocked=(
                    not isinstance(error, RelationalClientError) and uncertain(error)))
            except Exception:
                client._observe(connection, blocked=True)
        if not isinstance(error, Exception):
            raise
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            'Native DuckDB extension update failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched;failure.native_acknowledged = acknowledged
        failure.native_filesystem_effects_possible = dispatched;failure.automatic_retry = False
        raise failure from None
    finally:
        if owns_connection:
            client._forget_and_close(connection)
