"""Apply admitted relation changes while holding native PostgreSQL DDL locks."""
from copy import deepcopy
from psycopg import sql
from ...workspace.firebird_schema_plan import digest
from .catalog_capture import capture
from .execution import control
from ...workspace.firebird_catalog_export import build_export
from ...workspace.postgresql_schema_plan import build_plan


def _model(connection, record, database_oid, *, in_transaction=False):
    captured = capture(connection, database_oid, _in_transaction=in_transaction)
    plan = record['plan']
    return build_export(captured['resources'], endpoint_id=plan['endpoint_id'],
        target_id=plan['database_target_id'], generation=captured['generation'],
        engine='postgresql', native_model=True)


def _check_created_scope(operation, row, owner=None):
    native = row['native']
    if operation.get('table_owner'):
        from ...workspace.postgresql_creation import TABLE_DEFINITIONS
        field = TABLE_DEFINITIONS[operation['kind']][4]
        if owner is None or int(native['catalog_row'][field]) != owner['native']['oid']:
            raise ValueError('Created table-owned object belongs to a different table identity')
        if operation.get('owner_guard') and owner['native']['oid'] != operation['owner_guard']['oid']:
            raise ValueError('Owning table identity changed before commit')
    parent = operation.get('parent_guard')
    if parent:
        links = native.get('children', {}).get('pg_inherits', [])
        if len(links) != 1 or int(links[0]['inhparent']) != parent['oid'] or int(links[0]['inhrelid']) != native['oid']:
            raise ValueError('Created partition belongs to a different parent identity')
    guard = operation.get('schema_guard')
    if not guard:
        return
    field = {'pg_class': 'relnamespace', 'pg_proc': 'pronamespace', 'pg_type': 'typnamespace',
             'pg_collation': 'collnamespace', 'pg_conversion': 'connamespace',
             'pg_ts_config': 'cfgnamespace', 'pg_ts_dict': 'dictnamespace',
             'pg_ts_parser': 'prsnamespace', 'pg_ts_template': 'tmplnamespace'}.get(native['catalog'])
    namespace = (owner['native'].get('catalog_row', {}).get('relnamespace') if owner else
                 native.get('catalog_row', {}).get(field))
    if namespace is None or int(namespace) != guard['oid']:
        raise ValueError('Created object belongs to a different schema identity')


def _created_identities(operations, model, connection):
    result = []
    for operation in operations:
        if operation.get('routine_signature'):
            oid = connection.execute('SELECT pg_catalog.to_regprocedure(%s)::oid',
                (operation['routine_signature'],)).fetchone()[0]
            identity = 'postgresql:pg_proc:' + str(oid)
            row = model['rows'].get(identity)
            if row is None or row['kind'] != operation['kind'] or row['name'] != operation['name']:
                raise ValueError('Created routine identity is unavailable or inconsistent')
            _check_created_scope(operation, row)
            result.append({'resource_id': operation['resource_id'], 'native_resource_id': identity,
                           'native_sha256': digest(row['native'])})
            continue
        owner = None
        if operation.get('table_owner'):
            reference = operation['table_owner']
            owners = [item for item in model['rows'].values() if item['kind'] == 'table' and
                item['name'] == reference['table'] and item['native'].get('schema') == reference['schema']]
            if len(owners) != 1:
                raise ValueError('Created object owning table is unavailable or ambiguous')
            owner = owners[0]
        matches = [row for row in model['rows'].values() if row['name'] == operation['name'] and
            row['kind'] == operation['kind'] and (operation['kind'] == 'schema' or
                row['native'].get('schema') == operation['schema'])]
        if owner:
            from ...workspace.postgresql_creation import TABLE_DEFINITIONS
            field = TABLE_DEFINITIONS[operation['kind']][4]
            matches = [item for item in matches if str(item['native']['catalog_row'].get(field)) == str(owner['native']['oid'])]
        if len(matches) != 1:
            raise ValueError('Created native identity is unavailable or ambiguous')
        row = matches[0]
        _check_created_scope(operation, row, owner)
        result.append({'resource_id': operation['resource_id'], 'native_resource_id': row['resource_id'],
                       'native_sha256': digest(row['native'])})
    return result


def _added_column_identities(operations, model):
    result = []
    for operation in operations:
        parent = model['rows'].get(operation['parent_resource_id'])
        if parent is None or parent['native']['oid'] != operation['lock_target']['oid']:
            raise ValueError('Column parent identity changed before rediscovery')
        native = parent['native']
        matches = [attribute for attribute in native.get('children', {}).get('pg_attribute', [])
                   if attribute.get('attname') == operation['name']]
        if len(matches) != 1 or str(matches[0].get('attrelid')) != str(native['oid']):
            raise ValueError('Added column identity is unavailable or ambiguous')
        attribute = matches[0]
        if type(attribute.get('attnum')) is not int or attribute['attnum'] <= 0:
            raise ValueError('Added column has an invalid native attribute number')
        result.append({'resource_id': operation['resource_id'],
            'native_resource_id': f'postgresql:pg_attribute:{native["oid"]}:{attribute["attnum"]}',
            'parent_resource_id': operation['parent_resource_id'],
            'attribute_number': attribute['attnum'], 'native_sha256': digest(attribute)})
    return result


def apply_review(provider, route, record):
    for permission in ('administer', 'execute', 'data_read'):
        provider.permissions.require(permission)
    result = {'state': 'not_executed', 'commit_requested': False, 'native_commit_returned': False,
              'native_rollback_returned': False, 'statements_completed': 0, 'attachment_released': False}
    opened = connection = state = None
    try:
        if not record['plan'].get('application_supported'):
            raise ValueError('Native application is not admitted for this plan')
        opened = provider.open_session({'route': route})
        state = provider._sessions[opened['session_id']]
        with state.lock:
            provider._ensure_native_connection(state)
            connection = state.connection.conn
            if int(connection.info.transaction_status) != 0:
                raise ValueError('Schema application requires its own idle attachment')
            connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ')
            connection.execute('SET LOCAL standard_conforming_strings = on')
            connection.execute("SET LOCAL lock_timeout = '2s'")
            connection.execute("SET LOCAL statement_timeout = '15s'")
            targets = {item['lock_target']['oid']: item['lock_target'] for item in record['plan']['operations'] if item.get('lock_target')}
            for oid, target in sorted(targets.items()):
                connection.execute(sql.SQL('LOCK TABLE ONLY {}.{} IN ACCESS EXCLUSIVE MODE').format(
                    sql.Identifier(target['schema']), sql.Identifier(target['name'])))
            current = _model(connection, record, route['database_id'], in_transaction=True)
            fresh = build_plan(record['baseline'], record['desired'], current)
            if not fresh['application_supported'] or fresh['execution_sha256'] != record['plan']['execution_sha256']:
                result['reason'] = 'Metadata changed since review; prepare a new application'
                connection.rollback()
                result['native_rollback_returned'] = True
                return result
            for operation in fresh['operations']:
                connection.execute(operation['statement'])
                result['statements_completed'] += 1
            creations = [operation for operation in fresh['operations'] if operation.get('operation') == 'create']
            additions = [operation for operation in fresh['operations'] if operation.get('operation') == 'add_column']
            if creations or additions:
                inside = _model(connection, record, route['database_id'], in_transaction=True)
                if creations:
                    result['created_objects'] = _created_identities(creations, inside, connection)
                if additions:
                    result['added_columns'] = _added_column_identities(additions, inside)
            result['commit_requested'] = True
            status, command = control(connection, 'COMMIT')
            if status and command == 'ROLLBACK':
                result.update(state='native_rollback_returned', native_rollback_returned=True)
                return result
            if not status or command != 'COMMIT':
                raise RuntimeError('Native commit was not confirmed')
            result.update(state='native_commit_returned', native_commit_returned=True)
            try:
                observed = _model(connection, record, route['database_id'])
                matches = True
                if creations:
                    matches = all(item['native_resource_id'] in observed['rows'] and
                        digest(observed['rows'][item['native_resource_id']]['native']) == item['native_sha256']
                        for item in result['created_objects'])
                if additions:
                    matches = matches and _added_column_identities(additions, observed) == result['added_columns']
                if len(creations) != len(fresh['operations']):
                    altered = deepcopy(record['desired'])
                    for operation in creations:
                        altered['rows'].pop(operation['resource_id'])
                    for operation in additions:
                        altered['rows'][operation['parent_resource_id']]['native'].pop('add_columns', None)
                    remaining = build_plan(record['baseline'], altered, observed)
                    matches = matches and not remaining['blockers'] and not remaining['operations']
                result['rediscovery'] = {'available': True, 'matches_reviewed_properties': matches}
            except Exception as error:
                result['rediscovery'] = {'available': False, 'error_type': type(error).__name__}
    except Exception as error:
        result['error_type'] = type(error).__name__
        result['sqlstate'] = getattr(error, 'sqlstate', None)
        result['state'] = 'unknown_outcome' if result['commit_requested'] else 'not_executed'
        if connection is not None:
            try:
                connection.rollback()
                result['native_rollback_returned'] = True
                if not result['commit_requested']:
                    result['state'] = 'native_rollback_returned'
            except Exception as cleanup_error:
                result['rollback_error_type'] = type(cleanup_error).__name__
                result['state'] = 'unknown_outcome'
        if result['state'] == 'unknown_outcome' and state is not None:
            state.uncertain = True
    finally:
        if opened is not None:
            try:
                provider.close_session(opened)
                result['attachment_released'] = True
            except Exception as error:
                result['release_error_type'] = type(error).__name__
    return result
