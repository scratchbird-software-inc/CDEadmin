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
        for operation in fresh['operations']:
            result['statement_dispatched'] = True
            connection.execute(operation['source'])
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
                    if verified and operation['kind'] == 'column':
                        metadata = current['native'].get('catalog_metadata', {})
                        verified = all(metadata.get(key) == value for key, value in
                            operation['postcondition'].items())
                elif operation['operation'] == 'rename':
                    verified = (current is not None and
                        current['kind'] == operation['kind'] and current['name'] == operation['name'] and
                        observed['rows'].get(operation['source_resource_id']) is None)
                else:
                    from ...workspace.duckdb_schema_plan import _definition
                    from ...workspace.firebird_schema_plan import digest
                    verified = (current is not None and
                        digest(_definition(current)) != operation['baseline_sha256'])
                    if verified and operation['kind'] == 'view' and operation['operation'] == 'replace':
                        from ...workspace.duckdb_schema_plan import view_query_tokens
                        expected = view_query_tokens(operation['source'])
                        verified = (expected is not None and expected == view_query_tokens(
                            current['native'].get('ddl')))
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
