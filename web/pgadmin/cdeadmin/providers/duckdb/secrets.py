"""Secret storage identities and operations on the original native connection."""
from collections.abc import Mapping
from copy import deepcopy

from ...sdk import RelationalClientError
from .object_metadata import native
from .secret_values import compile_secret


def form(field):
    return {'form_id': 'duckdb.secret.create', 'title': 'Create native DuckDB secret', 'fields': [
        field('name', 'Secret name', 'text', False, 'Leave empty for the native default name.'),
        field('secret_type', 'Native secret type', 'text'),
        field('persistence_mode', 'Native persistence', 'select', True, default='TEMPORARY',
              options=('TEMPORARY', 'PERSISTENT', 'DEFAULT')),
        field('storage', 'Native storage', 'text', False, 'Empty uses DuckDB\'s selected default storage.'),
        field('on_conflict', 'Existing secret', 'select', True, default='ERROR',
              options=('ERROR', 'IF NOT EXISTS', 'OR REPLACE')),
        field('properties', 'Secret properties', 'json', False,
              'JSON constants, including provider, scope lists and header maps. Values stay private.',
              default={}, sensitive=True),
        field('property_expressions', 'Native property expressions', 'json', False,
              'Explicit property-to-SQL-expression map. Parsed without execution; evaluated by DuckDB only at apply.',
              default={}, sensitive=True),
    ]}


def compile_operation(adapter, request):
    operation = request.get('operation_id')
    draft = request.get('draft', {})
    if not isinstance(draft, Mapping):
        raise RelationalClientError('Native secret draft requires an object')
    if operation == 'create':
        controls = {'secret_type', 'scope', 'storage', 'persistent'}
        if set(draft) - controls - {'name', 'options', 'properties', 'property_expressions', 'persistence_mode', 'on_conflict'}:
            raise RelationalClientError('Unknown native secret creation control')
        options = deepcopy(draft.get('options', {}))
        properties = draft.get('properties', {})
        if not isinstance(options, dict) or not isinstance(properties, Mapping):
            raise RelationalClientError('Native secret properties require a JSON object')
        for key, value in {key: draft[key] for key in controls if key in draft}.items():
            if key in options and options[key] != value:
                raise RelationalClientError('Conflicting native secret options')
            options[key] = deepcopy(value)
        if any(not isinstance(key, str) or not key or '\x00' in key for key in options):
            raise RelationalClientError('Native secret property names require text without NUL')
        native_keys = [('type' if key == 'secret_type' else key).casefold() for key in options
                       if key not in {'storage', 'persistent', 'parent'}]
        if len(set(native_keys)) != len(native_keys):
            raise RelationalClientError('Native secret property names must be distinct')
        name = draft.get('name', '')
        if not isinstance(name, str):
            raise RelationalClientError('Native secret name requires text')
        quoted_name = adapter._quote(name) if name else ''
        expressions = draft.get('property_expressions', {})
        if not isinstance(expressions, Mapping):
            raise RelationalClientError('Native secret expressions require a JSON object')
        if (any(not isinstance(key, str) or not key for key in expressions) or
                len({key.casefold() for key in expressions}) != len(expressions)):
            raise RelationalClientError('Native secret expressions require distinct text property names')
        expressions = {key.lower(): value for key, value in expressions.items()}
        source, preview = compile_secret(adapter, quoted_name, options,
            persistence_mode=draft.get('persistence_mode'),
            on_conflict=draft.get('on_conflict', 'ERROR'), expressions=expressions, native_properties=properties)
        observed_name = name or '__default_' + options['secret_type']
        return {'statements': [{'source': source, 'preview_source': preview, 'parameters': ()}],
            'duckdb_secret': {'operation': 'create', 'name': observed_name},
            'warnings': warnings(bool(expressions))}
    if operation != 'drop':
        raise RelationalClientError('Unsupported native secret operation')
    target = request.get('target_resource')
    if not isinstance(target, Mapping) or target.get('resource_kind') != 'secret':
        raise RelationalClientError('Select an exact native secret storage target')
    metadata = native(target)
    storage, persistent = metadata.get('storage'), metadata.get('persistent')
    name = target.get('display_name')
    if (not isinstance(storage, str) or not storage or type(persistent) is not bool or
            not isinstance(name, str) or not name or draft.get('confirmation') != name or
            set(draft) - {'confirmation', 'cascade'} or draft.get('cascade')):
        raise RelationalClientError('Confirm the exact native secret name and observed storage')
    # FROM explicitly selects one storage, including extension-provided storages.
    # Native TEMPORARY + FROM is forbidden; storage alone is unambiguous.
    source = 'DROP SECRET ' + adapter._quote(name) + ' FROM ' + adapter._quote(storage)
    baseline = {key: metadata.get(key) for key in ('type', 'provider', 'persistent', 'storage', 'scope')}
    return {'statements': [{'source': source, 'parameters': ()}],
        'duckdb_secret': {'operation': 'drop', 'name': name, 'baseline': baseline},
        'warnings': warnings(False)}


def warnings(expressions):
    return [
        'Uses the original editor connection. Commit and rollback remain caller decisions.',
        'Persistent storage writes files which rollback does not undo; a later native instance can load them.',
        'Native execution errors can abort the caller transaction; only the caller requests rollback.',
        'Secret values are never read. Same-name replacement with identical public metadata cannot be detected.',
        *(['Native property expressions can invoke functions and access external systems at apply.'] if expressions else []),
    ]


def observe(connection, name):
    # DuckDB's parser normalizes ASCII names; preserve other Unicode bytes.
    name = name.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))
    rows = connection.execute('SELECT name,type,provider,persistent,storage,scope '
        'FROM duckdb_secrets() WHERE name=? ORDER BY storage,persistent', [name]).fetchall()
    return [dict(zip(('name', 'type', 'provider', 'persistent', 'storage', 'scope'), row)) for row in rows]


def apply(client, request, connection):
    if connection is None:
        raise RelationalClientError('Native secret operations require the original editor session')
    compiled = request['provider_payload']['compiled']
    intent = compiled['duckdb_secret']
    if intent['operation'] == 'drop':
        baseline = intent['baseline']
        if not any(all(row.get(key) == value for key, value in baseline.items()) for row in observe(connection, intent['name'])):
            raise RelationalClientError('Native secret storage metadata changed; inspect and review it again')
    dispatched = acknowledged = False
    try:
        dispatched = True
        statement = compiled['statements'][0]
        rows = connection.execute(statement['source']).fetchall()
        acknowledged = True
        client._observe(connection)
        try:
            observation = {'available': True, 'objects': observe(connection, intent['name'])}
        except Exception:
            observation = {'available': False}
        return {'accepted': True, 'statement_results': [{'rows': rows, 'rowcount': None}],
            'commit_requested': False, 'rollback_requested': False,
            'staged_in_provider_session': True, 'driver_observation_only': True,
            'transaction_finality_interpreted_by_common_code': False,
            'native_storage_observation': {'native_acknowledged': True, 'observation': observation,
                'persistent_file_effects_undone_by_rollback': False}, 'automatic_retry': False}
    except Exception as error:
        from .driver import uncertain
        try:client._observe(connection, blocked=uncertain(error))
        except Exception:client._observe(connection, blocked=True)
        failure = RelationalClientError('Native secret operation failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.rollback_requested = False
        failure.commit_requested = False
        failure.automatic_retry = False
        raise failure from None
