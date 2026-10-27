"""Exact native COMMENT ON operations with caller-owned transaction handling."""
from collections.abc import Mapping

from ...sdk.relational import RelationalClientError


KINDS = frozenset({
    'table', 'view', 'column', 'index', 'sequence', 'type', 'macro',
})


def native(resource):
    value = resource.get('native')
    if value is None:
        extension = (resource.get('extensions') or {}).get('duckdb') or {}
        value = extension.get('native', extension)
    if not isinstance(value, Mapping):
        raise RelationalClientError('DuckDB native object metadata is unavailable')
    return value


def signature(resource):
    value = native(resource)
    metadata = value.get('catalog_metadata', value)
    overloads = value.get('overloads')
    if overloads is not None:
        identities = [(row['catalog_metadata'].get('oid'),
                       row['catalog_metadata'].get('function_type'),
                       row['catalog_metadata'].get('comment')) for row in overloads]
        return {'overloads': sorted(identities, key=repr)}
    return {key: metadata.get(key) for key in (
        'oid', 'database_oid', 'owner_oid', 'ordinal_position', 'comment')}


def compile_operation(adapter, request):
    kind, target = request.get('resource_kind'), request.get('target_resource')
    draft = request.get('draft')
    if (kind not in KINDS or not isinstance(target, Mapping) or
            target.get('resource_kind') != kind or not isinstance(draft, Mapping) or
            set(draft) - {'comment', 'clear_comment', 'confirmation'}):
        raise RelationalClientError('Select an exact native DuckDB comment target')
    path = adapter._target_path(target)
    expected = 4 if kind in {'index', 'column'} else 3
    if len(path) != expected or draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('DuckDB comment confirmation must match the exact object name')
    clear = draft.get('clear_comment', False)
    if type(clear) is not bool:
        raise RelationalClientError('Remove comment must be boolean')
    comment = draft.get('comment')
    if clear:
        if comment not in (None, ''):
            raise RelationalClientError('Set a comment or remove it, not both')
        comment = None
    elif not isinstance(comment, str) or '\x00' in comment:
        raise RelationalClientError('DuckDB comment must be text without NUL')
    value = native(target)
    metadata = value.get('catalog_metadata', value)
    if metadata.get('internal'):
        raise RelationalClientError('Internal DuckDB objects cannot be edited')
    keyword = kind.upper()
    if kind == 'macro':
        overloads = value.get('overloads') or [value]
        types = {row.get('catalog_metadata', {}).get('function_type') for row in overloads}
        if len(types) != 1 or None in types:
            raise RelationalClientError('Select an unambiguous native DuckDB function family')
        function_type = next(iter(types))
        if function_type not in {'table_macro', 'macro'}:
            raise RelationalClientError('DuckDB comments target SQL macros, not native functions')
        keyword = 'MACRO TABLE' if function_type == 'table_macro' else 'MACRO'
    # Indexes are displayed beneath their owner table but named in the schema.
    sql_path = (*path[:2], path[-1]) if kind == 'index' else path
    source = ('COMMENT ON ' + keyword + ' ' + adapter._qualified(sql_path) +
              ' IS ' + ('NULL' if comment is None else adapter._literal(comment)))
    return {'statements': [{'source': source, 'parameters': ()}],
            'duckdb_comment': {'target': dict(target), 'draft': dict(draft),
                              'baseline': signature(target), 'comment': comment},
            'warnings': []}


def apply(adapter, client, request, connection=None):
    payload = request.get('provider_payload') or {}
    compiled = payload.get('compiled') or {}
    intent = compiled['duckdb_comment']
    target = intent['target']
    rebuilt = compile_operation(adapter, {
        'resource_kind': target['resource_kind'], 'operation_id': 'comment',
        'target_resource': target, 'draft': intent['draft']})
    if rebuilt != compiled:
        raise RelationalClientError('The reviewed DuckDB comment operation changed')
    owns_connection = connection is None
    if owns_connection:
        connection = client._connect({'route': payload['route']})
    dispatched = acknowledged = False
    try:
        if owns_connection:
            connection.execute('BEGIN TRANSACTION')
        from .provider import _resources
        def current():
            return next((row for row in _resources(connection, {'session_catalog': True})
                         if row['resource_id'] == target['resource_id']), None)
        live = current()
        if (live is None or live['resource_kind'] != target['resource_kind'] or
                live['display_path'] != target['display_path'] or
                signature(live) != intent['baseline']):
            raise RelationalClientError('DuckDB object identity or comment changed since review')
        dispatched = True
        connection.execute(compiled['statements'][0]['source'])
        acknowledged = True
        observed = current()
        metadata = native(observed)
        overloads = metadata.get('overloads')
        comments = ([row['catalog_metadata'].get('comment') for row in overloads]
                    if overloads else [metadata.get('catalog_metadata', metadata).get('comment')])
        verified = bool(comments) and all(value == intent['comment'] for value in comments)
        if owns_connection:
            connection.commit()
        else:
            client._observe(connection)
        return {'accepted': True, 'commit_requested': owns_connection,
                'rollback_requested': False, 'staged_in_provider_session': not owns_connection,
                'driver_observation_only': True,
                'transaction_finality_interpreted_by_common_code': False,
                'metadata_observation': {'native_acknowledged': acknowledged,
                    'comment_matches': verified, 'comments': comments,
                    'scope': 'native attachment before owned commit' if owns_connection else 'caller-owned transaction'},
                'automatic_retry': False}
    except BaseException as error:
        if owns_connection:
            try:
                connection.rollback()
            except Exception:
                pass
        else:
            from .driver import uncertain
            try:
                client._observe(connection, blocked=(
                    not isinstance(error, RelationalClientError) and uncertain(error)))
            except Exception:
                client._observe(connection, blocked=True)
        if not isinstance(error, Exception):
            raise
        failure = RelationalClientError('DuckDB comment operation failed (' + type(error).__name__ + ')')
        if isinstance(error, RelationalClientError):
            failure = error
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        raise failure from None
    finally:
        if owns_connection:
            client._forget_and_close(connection)
