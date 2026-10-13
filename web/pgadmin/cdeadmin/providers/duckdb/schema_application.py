"""Bounded DuckDB DDN apply with one native transaction and rediscovery."""

import os

from ..embedded_route import contained_database
from ...workspace.duckdb_schema_plan import plan
from ...workspace.firebird_catalog_export import build_export


def _model(connection, record, *, in_transaction):
    from .catalog import capture
    observed = capture(connection, include_system=False, _in_transaction=in_transaction)
    provenance = record['baseline']['provenance']
    return build_export(observed['resources'], endpoint_id=provenance['endpoint_id'],
        target_id=provenance['database_target_id'], generation=observed['generation'],
        include_system=False, refreshed=True, engine='duckdb', native_model=True)


def apply_review(provider, route, record):
    for permission in ('administer', 'execute', 'data_read'):
        provider._require(permission, 'resource')
    result = {'state': 'not_dispatched', 'commit_requested': False,
        'native_commit_returned': False, 'native_rollback_returned': False,
        'rediscovery_verified': False, 'automatic_retry': False}
    connection = None
    transaction_started = False
    try:
        path = contained_database(route)
        if path == ':memory:' or not os.path.isfile(path) or route.get('read_only') is True:
            raise ValueError('Native schema application requires a writable registered DuckDB file')
        if not record['plan'].get('application_supported'):
            raise ValueError('Native application is not admitted for this plan')
        connection = provider.client._connect({'route': route})
        identity = record.get('file_identity')
        details = os.stat(path)
        if identity is not None and [details.st_dev, details.st_ino] != identity:
            raise ValueError('Registered DuckDB file identity changed since review')
        connection.execute('BEGIN TRANSACTION')
        transaction_started = True
        live = _model(connection, record, in_transaction=True)
        fresh = plan(record['baseline'], record['desired'], live)
        if (not fresh['application_supported'] or
                fresh['execution_sha256'] != record['plan']['execution_sha256']):
            result['rejection_reason'] = 'Native file definition changed since review'
            connection.execute('ROLLBACK')
            result['native_rollback_returned'] = True
            return result
        rebuild_rows = {}
        view_descriptors = {}
        for operation in fresh['operations']:
            if operation['operation'] == 'rebuild':
                if operation.get('affected_view_ids'):
                    from ...workspace.duckdb_schema_plan import _quote
                    for view_id in operation['affected_view_ids']:
                        view = record['baseline']['rows'][view_id]
                        target = '.'.join(_quote(part) for part in view['path'])
                        view_descriptors[view_id] = (target, connection.execute(
                            'DESCRIBE SELECT * FROM ' + target).fetchall())
                old_rows = connection.execute('SELECT count(*) FROM ' +
                    operation['target']).fetchone()[0]
                for index, statement in enumerate(operation['statements']):
                    result['statement_dispatched'] = True
                    connection.execute(statement)
                    if index == 0 and operation.get('stage_columns') is not None:
                        stage_path = record['desired']['rows'][operation['resource_id']]['path']
                        scope = (stage_path[0], stage_path[1], operation['stage_name'])
                        columns = connection.execute(
                            'SELECT column_name, data_type, column_default, is_nullable '
                            'FROM duckdb_columns() WHERE database_name=? AND schema_name=? '
                            'AND table_name=? ORDER BY column_index', scope).fetchall()
                        expected_columns = [(item['name'], item['data_type'],
                            item['default'], item['nullable']) for item in
                            operation['stage_columns']]
                        constraints = connection.execute(
                            'SELECT constraint_type, constraint_column_names '
                            'FROM duckdb_constraints() WHERE database_name=? '
                            'AND schema_name=? AND table_name=? ORDER BY constraint_index',
                            scope).fetchall()
                        key_columns = operation.get('stage_key_columns') or []
                        primary_keys = [names for kind, names in constraints
                            if kind == 'PRIMARY KEY']
                        nulls = [names for kind, names in constraints
                            if kind == 'NOT NULL']
                        if (columns != expected_columns or
                                primary_keys != ([key_columns] if key_columns else []) or
                                sorted(tuple(names) for names in nulls) !=
                                    sorted((name,) for name in key_columns) or
                                len(constraints) != len(key_columns) + bool(key_columns)):
                            raise ValueError('Native staged columns or constraints differ from review')
                    if index == 1:
                        difference = connection.execute(
                            operation['data_check']).fetchone()[0]
                        if difference != 0:
                            raise ValueError('Native staging rows differ from original rows')
                        dependency_difference = connection.execute(
                            operation['sequence_dependency_check']).fetchone()[0]
                        if dependency_difference != 0:
                            raise ValueError('Native staged sequence dependencies differ')
                        if (operation['requires_sequence_dependency'] and
                                connection.execute(operation[
                                    'sequence_dependency_count']).fetchone()[0] == 0):
                            raise ValueError('Native sequence default has no observed dependency')
                for view_id in operation.get('affected_view_ids', []):
                    target, original_projection = view_descriptors[view_id]
                    if connection.execute('DESCRIBE SELECT * FROM ' +
                            target).fetchall() != original_projection:
                        raise ValueError('Native view projection changed during table rebuild')
                rebuild_rows[operation['resource_id']] = old_rows
            else:
                for statement in operation.get('statements', [operation['source']]):
                    result['statement_dispatched'] = True
                    connection.execute(statement)
        result['commit_requested'] = True
        connection.execute('COMMIT')
        result.update(state='committed', native_commit_returned=True)
        try:
            observed = _model(connection, record, in_transaction=False)
            checks, rediscovered = [], []
            for operation in fresh['operations']:
                current = observed['rows'].get(operation['resource_id'])
                if operation['operation'] == 'drop':
                    verified = current is None
                elif operation['operation'] == 'create':
                    verified = (current is not None and
                        current['kind'] == operation['kind'] and current['name'] == operation['name'])
                    if verified and operation['kind'] == 'view':
                        from ...workspace.duckdb_schema_plan import view_query_tokens
                        expected = view_query_tokens(operation['source'])
                        verified = (expected is not None and expected == view_query_tokens(
                            current['native'].get('ddl')))
                    if verified and operation['kind'] in {'table', 'index'}:
                        from ...workspace.duckdb_schema_plan import create_definition_tokens
                        expected = create_definition_tokens(operation['source'], operation['kind'])
                        verified = (expected is not None and expected == create_definition_tokens(
                            current['native'].get('ddl'), operation['kind']))
                    if verified and operation['kind'] == 'type':
                        from ...workspace.duckdb_schema_plan import type_expression_tokens
                        expected = type_expression_tokens(operation['source'], created=True)
                        verified = (expected is not None and expected == type_expression_tokens(
                            current['native'].get('catalog_metadata', {}).get('resolved_type'),
                            created=False))
                    if verified and operation['kind'] == 'sequence':
                        metadata = current['native'].get('catalog_metadata', {})
                        expected = operation['postcondition']['sequence_options']
                        verified = all(metadata.get(key) == value for key, value in expected.items())
                    if verified and operation['kind'] == 'macro':
                        from ...workspace.duckdb_schema_plan import macro_creation_matches
                        verified = macro_creation_matches(operation['source'], current)
                    if verified and operation['kind'] == 'column':
                        metadata = current['native'].get('catalog_metadata', {})
                        verified = all(metadata.get(key) == value for key, value in
                            operation['postcondition'].items())
                elif operation['operation'] == 'rename':
                    verified = (current is not None and
                        current['kind'] == operation['kind'] and current['name'] == operation['name'] and
                        observed['rows'].get(operation['source_resource_id']) is None)
                elif operation['operation'] == 'rebuild':
                    from ...workspace.duckdb_schema_plan import create_definition_tokens
                    baseline = record['baseline']['rows'][operation['resource_id']]
                    expected = create_definition_tokens(operation['original_source'], 'table')
                    actual = (create_definition_tokens(current['native'].get('ddl'), 'table')
                        if current is not None else None)
                    verified = (current is not None and current['kind'] == 'table' and
                        expected is not None and actual is not None and
                        (operation.get('stage_columns') is not None or expected == actual) and
                        current['native'].get('columns') == (
                            record['desired']['rows'][operation['resource_id']]['native'].get('columns')
                            if operation.get('stage_columns') is not None else
                            baseline['native'].get('columns')) and
                        current['native'].get('catalog_metadata', {}).get('comment') ==
                            baseline['native'].get('catalog_metadata', {}).get('comment'))
                    if verified:
                        from ...workspace.duckdb_schema_plan import _definition, _fk_parent_definition
                        from ...workspace.firebird_schema_plan import digest
                        def signatures(items):
                            return sorted((item.get('constraint_type'),
                                item.get('constraint_text'), tuple(item.get('column_names') or []))
                                for item in items)
                        verified = (signatures(current['native'].get('constraints', [])) ==
                            signatures(operation['postcondition']['constraints']) and
                            {item['resource_id'] for item in
                                current['native'].get('constraints', [])} ==
                            set(operation['desired_child_sha256']) and
                            {item['resource_id'] for item in
                                current['native'].get('indexes', [])} ==
                            set(operation['affected_index_ids']) and
                            connection.execute('SELECT count(*) FROM ' +
                                operation['target']).fetchone()[0] ==
                            rebuild_rows[operation['resource_id']])
                        if verified:
                            verified = all((
                                observed['rows'].get(child_id) is None
                                if child_id not in operation['desired_child_sha256'] else
                                observed['rows'].get(child_id) is not None and
                                operation['desired_child_sha256'][child_id] ==
                                digest(_definition(observed['rows'][child_id])))
                                for child_id in operation['affected_child_ids'])
                        if verified and operation.get('affected_column_ids'):
                            verified = all(observed['rows'].get(column_id) is not None and
                                digest(_definition(observed['rows'][column_id])) ==
                                operation['desired_column_sha256'][column_id]
                                for column_id in operation['affected_column_ids'])
                        if verified:
                            verified = all(observed['rows'].get(index_id) is not None and
                                digest(_definition(observed['rows'][index_id])) ==
                                operation['desired_index_sha256'][index_id]
                                for index_id in operation['affected_index_ids'])
                        if verified:
                            verified = all(observed['rows'].get(parent_id) is not None and
                                digest(_fk_parent_definition(observed['rows'][parent_id])) ==
                                    parent_sha
                                for parent_id, parent_sha in operation.get(
                                    'fk_parent_sha256', {}).items())
                        if verified:
                            verified = all(observed['rows'].get(view_id) is not None and
                                observed['rows'][view_id]['native'].get('state', {}).get('bound') is True and
                                digest(_definition(observed['rows'][view_id])) ==
                                    operation['desired_view_sha256'][view_id] and
                                connection.execute('DESCRIBE SELECT * FROM ' +
                                    view_descriptors[view_id][0]).fetchall() ==
                                    view_descriptors[view_id][1]
                                for view_id in operation.get('affected_view_ids', []))
                        if verified:
                            verified = all(observed['rows'].get(column_id) is not None and
                                digest(_definition(observed['rows'][column_id])) ==
                                    operation['desired_view_column_sha256'][column_id]
                                for column_id in operation.get('affected_view_column_ids', []))
                else:
                    from ...workspace.duckdb_schema_plan import _definition
                    from ...workspace.firebird_schema_plan import digest
                    verified = (current is not None and
                        digest(_definition(current)) != operation['baseline_sha256'])
                    if verified and operation['kind'] == 'view' and operation['operation'] == 'replace':
                        from ...workspace.duckdb_schema_plan import view_query_tokens
                        expected = view_query_tokens(operation['source'])
                        verified = (expected is not None and expected == view_query_tokens(
                            current['native'].get('ddl')) and
                            current['native'].get('catalog_metadata', {}).get('comment') ==
                            operation['preserved_comment'] and
                            {column['name']: column['comment'] for column in
                                current['native'].get('columns', [])
                                if column.get('comment') is not None} ==
                            operation['preserved_column_comments'])
                    if verified and operation.get('postcondition'):
                        if 'overloads' in operation['postcondition']:
                            from ...workspace.duckdb_schema_plan import _macro_overload_postcondition
                            try:
                                verified = (_macro_overload_postcondition(current) ==
                                    operation['postcondition']['overloads'])
                            except ValueError:
                                verified = False
                        elif 'sequence_options' in operation['postcondition']:
                            metadata = current['native'].get('catalog_metadata', {})
                            verified = all(metadata.get(key) == value for key, value in
                                operation['postcondition']['sequence_options'].items())
                        elif 'type_catalog' in operation['postcondition']:
                            metadata = current['native'].get('catalog_metadata', {})
                            verified = all(metadata.get(key) == value for key, value in
                                operation['postcondition']['type_catalog'].items())
                        elif 'primary_key_columns' in operation['postcondition']:
                            verified = (current['native'].get('catalog_metadata', {})
                                .get('has_primary_key') is True and any(
                                item.get('constraint_type') == 'PRIMARY KEY' and
                                item.get('column_names') == operation['postcondition']['primary_key_columns']
                                for item in current['native'].get('constraints', [])))
                        else:
                            metadata = (current['native'].get('catalog_metadata', {})
                                if operation['kind'] in {'column', 'type'} or
                                    (operation['operation'] == 'alter' and
                                     'comment' in operation['postcondition']) else
                                {'definition': (current['native'].get('overloads') or [{}])[0]
                                    .get('definition')})
                            verified = all(metadata.get(key) == value for key, value in
                                operation['postcondition'].items())
                    if (verified and operation['kind'] == 'macro' and
                            'preserved_comment' in operation):
                        comment = operation['preserved_comment']
                        verified = (current['native'].get('catalog_metadata', {})
                            .get('comment') == comment and all(
                            overload.get('catalog_metadata', {}).get('comment') == comment
                            for overload in current['native'].get('overloads', [])))
                    if (verified and operation['kind'] in {'sequence', 'type'} and
                            'preserved_comment' in operation):
                        verified = (current['native'].get('catalog_metadata', {})
                            .get('comment') == operation['preserved_comment'])
                checks.append({'resource_id': operation['resource_id'], 'verified': verified})
                rediscovered.append(current['resource_id'] if current else None)
            result['rediscovery_checks'] = checks
            result['rediscovery_verified'] = all(item['verified'] for item in checks)
            result['rediscovered_resource_ids'] = rediscovered
            result['rediscovered_resource_id'] = rediscovered[0]
        except Exception as error:
            result['rediscovery_error_type'] = type(error).__name__
        return result
    except Exception as error:
        result['error_type'] = type(error).__name__
        result['state'] = 'unknown_outcome' if result['commit_requested'] else (
            'rolled_back' if result.get('statement_dispatched') else 'not_dispatched')
        if connection is not None and transaction_started:
            try:
                connection.execute('ROLLBACK')
                result['native_rollback_returned'] = True
            except Exception as rollback_error:
                result['rollback_error_type'] = type(rollback_error).__name__
                if result.get('statement_dispatched'):
                    result['state'] = 'unknown_outcome'
        return result
    finally:
        if connection is not None:
            try:
                provider.client._discard_failed_session(connection)
                result['attachment_released'] = True
            except Exception as error:
                result['attachment_release_error_type'] = type(error).__name__
