"""Bounded DuckDB DDN apply with one native transaction and rediscovery."""

import os

from ..embedded_route import contained_database
from ...workspace.duckdb_schema_plan import plan
from ...workspace.firebird_catalog_export import build_export


_DERIVED_COLUMN_FACTS = {'data_type_id', 'character_maximum_length',
    'numeric_precision', 'numeric_precision_radix', 'numeric_scale'}


def _column_metadata_matches(actual, desired):
    return (isinstance(actual, dict) and isinstance(desired, dict) and
        all(actual.get(key) == value for key, value in desired.items()
            if key not in _DERIVED_COLUMN_FACTS or value is not None))


def _table_columns_match(actual, desired, added_ids):
    if (not isinstance(actual, list) or not isinstance(desired, list) or
            len(actual) != len(desired)):
        return False
    added_ids = set(added_ids)
    for found, expected in zip(actual, desired):
        if not isinstance(found, dict) or not isinstance(expected, dict):
            return False
        if expected.get('resource_id') not in added_ids:
            if found != expected:
                return False
        elif (found.get('resource_id') != expected.get('resource_id') or
                found.get('name') != expected.get('name') or
                not _column_metadata_matches(
                    {key: value for key, value in found.items()
                        if key not in {'resource_id', 'name'}},
                    {key: value for key, value in expected.items()
                        if key not in {'resource_id', 'name'}})):
            return False
    return True


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
        inbound_rows = {}
        view_descriptors = {}
        macro_descriptors = {}
        for operation in fresh['operations']:
            if operation['operation'] == 'rebuild':
                if (operation.get('affected_view_ids') or
                        operation.get('affected_macro_ids')):
                    from ...workspace.duckdb_schema_plan import _quote
                    for view_id in operation['affected_view_ids']:
                        view = record['baseline']['rows'][view_id]
                        target = '.'.join(_quote(part) for part in view['path'])
                        view_descriptors[view_id] = (target, connection.execute(
                            'DESCRIBE SELECT * FROM ' + target).fetchall())
                    for macro_id in operation.get('affected_macro_ids', []):
                        macro = record['baseline']['rows'][macro_id]
                        bindings = []
                        for overload in macro['native']['overloads']:
                            target = ('.'.join(_quote(part) for part in macro['path']) +
                                '(' + ', '.join('NULL' for _ in overload['parameters']) + ')')
                            kind = overload['catalog_metadata']['function_type']
                            source = ('DESCRIBE SELECT * FROM ' if kind == 'table_macro'
                                else 'DESCRIBE SELECT ') + target
                            bindings.append((source, connection.execute(source).fetchall()))
                        macro_descriptors[macro_id] = bindings
                old_rows = connection.execute('SELECT count(*) FROM ' +
                    operation['target']).fetchone()[0]
                inbounds = operation.get('inbound_children', [])
                parent_offset = inbounds[0]['parent_offset'] if inbounds else 0
                if inbounds:
                    from ...workspace.duckdb_schema_plan import _quote
                    for inbound in inbounds:
                        child = record['baseline']['rows'][inbound['child_resource_id']]
                        child_target = '.'.join(_quote(part) for part in child['path'])
                        inbound_rows[inbound['child_resource_id']] = connection.execute(
                            'SELECT count(*) FROM ' + child_target).fetchone()[0]
                child_creates = {offset: (item, phase)
                    for item in inbounds for phase, offset in
                    enumerate((item['first_offset'], item['final_offset']))}
                child_copies = {offset + 1: (item, phase)
                    for offset, (item, phase) in child_creates.items()}
                for index, statement in enumerate(operation['statements']):
                    result['statement_dispatched'] = True
                    connection.execute(statement)
                    if index in child_creates:
                        inbound, phase = child_creates[index]
                        child = record['baseline']['rows'][inbound['child_resource_id']]
                        scope = (child['path'][0], child['path'][1],
                            inbound['stage_names'][phase])
                        columns = connection.execute(
                            'SELECT column_name, data_type, column_default, is_nullable '
                            'FROM duckdb_columns() WHERE database_name=? AND schema_name=? '
                            'AND table_name=? ORDER BY column_index', scope).fetchall()
                        expected_columns = [(item['name'], item['data_type'],
                            item['default'], item['nullable']) for item in inbound['columns']]
                        constraints = connection.execute(
                            'SELECT constraint_type, constraint_column_names, '
                            'referenced_table, referenced_column_names, constraint_text '
                            'FROM duckdb_constraints() WHERE database_name=? '
                            'AND schema_name=? AND table_name=?', scope).fetchall()
                        expected_constraints = [(
                            fact['constraint_type'], fact['column_names'],
                            fact['referenced_table'], fact['referenced_column_names'],
                            fact['constraint_text']) for fact in
                            inbound['constraints_by_phase'][phase]]
                        def normalized(items):
                            return sorted((kind, tuple(names or ()), referenced or '',
                                tuple(referenced_names or ()), definition or '')
                                for kind, names, referenced, referenced_names, definition in items)
                        if (columns != expected_columns or
                                normalized(constraints) != normalized(expected_constraints)):
                            raise ValueError('Inbound child staging differs from reviewed model')
                        if connection.execute(inbound[
                                'sequence_dependency_checks'][phase]).fetchone()[0] != 0:
                            raise ValueError('Inbound child staged sequence dependencies differ')
                        if (inbound['requires_sequence_dependency'] and
                                connection.execute(inbound[
                                    'sequence_dependency_counts'][phase]).fetchone()[0] == 0):
                            raise ValueError('Inbound child sequence default has no observed dependency')
                    if index in child_copies:
                        inbound, phase = child_copies[index]
                        if connection.execute(inbound['data_checks'][phase]).fetchone()[0] != 0:
                            raise ValueError('Inbound child stage rows differ from original')
                    if index == parent_offset and operation.get('stage_columns') is not None:
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
                        if (operation.get('stage_unique_constraints') is not None or
                                operation.get('stage_check_constraints') is not None):
                            constraints = [item for item in constraints
                                if item[0] not in {'UNIQUE', 'CHECK'}]
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
                        if operation.get('stage_constraint_order') is not None:
                            actual_order = connection.execute(
                                'SELECT constraint_type, constraint_column_names, '
                                'constraint_text FROM duckdb_constraints() '
                                'WHERE database_name=? AND schema_name=? '
                                'AND table_name=? ORDER BY constraint_index',
                                scope).fetchall()
                            if [list(item) for item in actual_order] != operation[
                                    'stage_constraint_order']:
                                raise ValueError('Native staged constraint order differs from reviewed child identities')
                        derived_columns = operation.get('stage_added_derived_columns')
                        if derived_columns is None and operation.get('stage_added_derived'):
                            derived_columns = {operation['stage_null_column']:
                                operation['stage_added_derived']}
                        for column_name, expected_derived in (
                                derived_columns or {}).items():
                            if not expected_derived:
                                continue
                            fields = ('data_type_id', 'character_maximum_length',
                                'numeric_precision', 'numeric_precision_radix',
                                'numeric_scale')
                            observed_facts = connection.execute(
                                'SELECT ' + ', '.join(fields) +
                                ' FROM duckdb_columns() WHERE database_name=? '
                                'AND schema_name=? AND table_name=? AND column_name=?',
                                (*scope, column_name)).fetchone()
                            observed_derived = (dict(zip(fields, observed_facts))
                                if observed_facts is not None else {})
                            if (observed_facts is None or any(
                                    observed_derived.get(key) != value
                                    for key, value in expected_derived.items())):
                                raise ValueError('New staged column derived facts differ from review')
                    if index == parent_offset and operation.get('stage_unique_constraints') is not None:
                        stage_path = record['desired']['rows'][operation['resource_id']]['path']
                        scope = (stage_path[0], stage_path[1], operation['stage_name'])
                        found = connection.execute(
                            "SELECT constraint_column_names, constraint_text "
                            "FROM duckdb_constraints() WHERE database_name=? "
                            "AND schema_name=? AND table_name=? "
                            "AND constraint_type='UNIQUE'", scope).fetchall()
                        expected = [(item['column_names'], item['constraint_text'])
                            for item in operation['stage_unique_constraints']]
                        if sorted((tuple(names), text) for names, text in found) != sorted(
                                (tuple(names), text) for names, text in expected):
                            raise ValueError('Native staged UNIQUE constraints differ from review')
                    if index == parent_offset and operation.get('stage_check_constraints') is not None:
                        stage_path = record['desired']['rows'][operation['resource_id']]['path']
                        scope = (stage_path[0], stage_path[1], operation['stage_name'])
                        found = connection.execute(
                            'SELECT constraint_column_names, constraint_text '
                            'FROM duckdb_constraints() WHERE database_name=? '
                            'AND schema_name=? AND table_name=? '
                            "AND constraint_type='CHECK'", scope).fetchall()
                        expected = [(item['column_names'], item['constraint_text'])
                            for item in operation['stage_check_constraints']]
                        if sorted((tuple(names), text) for names, text in found) != sorted(
                                (tuple(names), text) for names, text in expected):
                            raise ValueError('Native staged CHECK constraints differ from review')
                    if index == parent_offset + 1:
                        difference = connection.execute(
                            operation['data_check']).fetchone()[0]
                        if difference != 0:
                            raise ValueError('Native staging rows differ from original rows')
                        null_columns = operation.get('stage_null_columns')
                        if null_columns is None:
                            null_columns = ([operation['stage_null_column']]
                                if operation.get('stage_null_column') is not None else [])
                        if null_columns:
                            from ...workspace.duckdb_schema_plan import _quote
                            stage_path = record['desired']['rows'][
                                operation['resource_id']]['path']
                            stage_target = '.'.join(_quote(part) for part in
                                [*stage_path[:2], operation['stage_name']])
                            for column_name in null_columns:
                                if connection.execute('SELECT count(*) FROM ' +
                                        stage_target + ' WHERE ' + _quote(
                                            column_name) + ' IS NOT NULL').fetchone()[0]:
                                    raise ValueError('New staged column contains non-NULL values')
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
                for macro_id in operation.get('affected_macro_ids', []):
                    for source, original_projection in macro_descriptors[macro_id]:
                        if connection.execute(source).fetchall() != original_projection:
                            raise ValueError('Native macro projection changed during table rebuild')
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
                        _table_columns_match(current['native'].get('columns'), (
                            record['desired']['rows'][operation['resource_id']]['native'].get('columns')
                            if operation.get('stage_columns') is not None else
                            baseline['native'].get('columns')),
                            operation.get('added_column_ids', [])) and
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
                            added_ids = set(operation.get('added_column_ids', []))
                            def column_verified(column_id):
                                found = observed['rows'].get(column_id)
                                if found is None:
                                    return False
                                if column_id not in added_ids:
                                    return digest(_definition(found)) == operation[
                                        'desired_column_sha256'][column_id]
                                expected = record['desired']['rows'][column_id]
                                return (all(found.get(key) == expected.get(key)
                                    for key in ('resource_id', 'kind', 'name', 'path', 'system')) and
                                    _column_metadata_matches(found['native'].get(
                                        'catalog_metadata'), expected['native'].get(
                                            'catalog_metadata')))
                            verified = all(column_verified(column_id)
                                for column_id in operation['affected_column_ids'])
                        null_columns = operation.get('stage_null_columns')
                        if null_columns is None:
                            null_columns = ([operation['stage_null_column']]
                                if operation.get('stage_null_column') is not None else [])
                        if verified and null_columns:
                            from ...workspace.duckdb_schema_plan import _quote
                            verified = all(connection.execute('SELECT count(*) FROM ' +
                                operation['target'] + ' WHERE ' + _quote(
                                    column_name) + ' IS NOT NULL').fetchone()[0] == 0
                                for column_name in null_columns)
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
                        if verified and operation.get('inbound_children'):
                            from ...workspace.duckdb_schema_plan import _quote
                            verified = (all(connection.execute('SELECT count(*) FROM ' +
                                '.'.join(_quote(part) for part in record['baseline']['rows'][
                                    item['child_resource_id']]['path'])).fetchone()[0] ==
                                inbound_rows[item['child_resource_id']]
                                for item in operation['inbound_children']) and
                                all(observed['rows'].get(identity) is not None and
                                    digest(_definition(observed['rows'][identity])) ==
                                    operation['desired_inbound_sha256'][identity]
                                    for identity in operation['affected_inbound_ids']))
                        if verified:
                            verified = all(observed['rows'].get(macro_id) is not None and
                                digest(_definition(observed['rows'][macro_id])) ==
                                    operation['desired_macro_sha256'][macro_id] and
                                all(connection.execute(source).fetchall() == projection
                                    for source, projection in macro_descriptors[macro_id])
                                for macro_id in operation.get('affected_macro_ids', []))
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
