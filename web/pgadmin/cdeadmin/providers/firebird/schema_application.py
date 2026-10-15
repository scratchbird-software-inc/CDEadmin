"""Execute a reviewed schema change in one owned native MGA transaction."""
from copy import deepcopy

from .provider import _resources, status_codes
from .identity import rename_identity, verify_rename
from ...workspace.firebird_catalog_export import build_export
from ...workspace.firebird_schema_plan import build_plan, _model
from ...workspace.firebird_domain_plan import creation_model
from ...workspace.firebird_table_plan import creation_model as table_creation_model
from ...workspace.firebird_column_plan import creation_model as column_creation_model
from ...workspace.firebird_lifecycle_plan import column_grants
from ...workspace.firebird_collation_plan import created_matches


def capture(connection, target):
    return build_export(_resources(connection, {}), endpoint_id=target['endpoint_id'],
        target_id=target['database_target_id'], generation=target['generation'],
        include_system=True, native_model=True)


def apply_review(provider, route, record):
    from .ddl_dialect import generated_dialect
    with generated_dialect(record['plan']['sql_dialect']):
        return _apply_review(provider, route, record)


def _apply_review(provider, route, record):
    provider._admit_transport({'route': route})
    provider.permissions.require('administer', 'resource')
    client = provider.client
    connection = None
    outcome = {'state': 'not_executed', 'commit_requested': False,
               'native_commit_returned': False, 'native_rollback_returned': False,
               'statements_completed': 0, 'attachment_released': False}
    started = False
    owned_route = {**deepcopy(route), 'transaction_isolation': 'SNAPSHOT',
        'transaction_access': 'WRITE', 'transaction_lock_timeout': 10,
        'transaction_auto_commit': False, 'transaction_no_auto_undo': False,
        'transaction_ignore_limbo': False}
    with client._temporary_operation():
        try:
            connection = client._connect({'route': owned_route})
            # No caller-owned attachment/transaction enters this path.
            if connection.main_transaction.is_active():
                connection.rollback()
            current = capture(connection, record['plan']['target'])
            fresh = build_plan(record['baseline'], record['desired'], current)
            outcome['preflight_status'] = fresh['status']
            outcome['preflight_execution_sha256'] = fresh['execution_sha256']
            if fresh['execution_sha256'] != record['plan']['execution_sha256']:
                outcome['reason'] = 'Metadata changed since review; prepare a new application'
                outcome['preflight_blockers'] = fresh['blockers']
                return outcome
            started = True
            with connection.cursor() as cursor:
                for phase in ('statements', 'deferred_statements'):
                    for operation in fresh['operations']:
                        for ordinal, statement in enumerate(operation.get(phase, [])):
                            transition = operation.get('rename_transition') if ordinal == operation.get('rename_statement_index') else None
                            previous = rename_identity(cursor, transition, transition['old_name']) if transition else None
                            cursor.execute(statement)
                            outcome['statements_completed'] += 1
                            if transition:
                                outcome.setdefault('identity_transitions', []).append(verify_rename(cursor, transition, previous))
            outcome['commit_requested'] = True
            connection.commit()
            outcome.update(state='native_commit_returned', native_commit_returned=True)
            # The previous native transaction ended; rediscovery gets a fresh
            # snapshot. A read failure cannot erase the observed commit.
            try:
                after = capture(connection, record['plan']['target'])
                observations = []
                for operation in fresh['operations']:
                    result_identity = operation.get('result_resource_id', operation['resource_id'])
                    actual = after['rows'].get(result_identity)
                    model = _model(actual) if actual is not None else None
                    expected = operation['after']
                    grants_match = True
                    if operation['operation'] == 'rename' and operation['kind'] == 'column':
                        transition = operation['rename_transition']
                        grants_match = (column_grants(after, transition['table'], transition['new_name']) == operation['after_column_grants']
                            and not column_grants(after, transition['table'], transition['old_name']))
                    if model is not None and expected is not None and 'creation_type' in expected:
                        model['creation_type'] = creation_model(actual, after)
                    if model is not None and expected is not None and 'creation_column' in expected:
                        model['creation_column'] = {key: value for key, value in
                            column_creation_model(actual, after, observed=True).items() if key != 'dependencies'}
                        expected = {**expected, 'creation_column': {key: value for key, value in
                            expected['creation_column'].items() if key != 'dependencies'}}
                    if model is not None and expected is not None and 'creation_table' in expected:
                        # Dependency identities are pre-execution guards, not
                        # table properties: successful CREATE adds identities
                        # to the catalog observed by expression dependency guards.
                        separately_created = {item['after']['name'] for item in fresh['operations']
                            if item['kind'] == 'index' and item['operation'] == 'create'
                            and item['after']['table'] == actual['name']
                            and not item.get('embedded_index_definition')}
                        table_observation = deepcopy(actual)
                        table_observation['native']['indexes'] = [item for item in actual['native'].get('indexes', [])
                            if item['name'] not in separately_created]
                        model['creation_table'] = {key: value for key, value in
                            table_creation_model(table_observation, after, observed=True).items() if key != 'dependencies'}
                        expected = {**expected, 'creation_table': {key: value for key, value in
                            expected['creation_table'].items() if key != 'dependencies'}}
                    collation_creation = operation['kind'] == 'collation' and operation['operation'] == 'create'
                    matches = created_matches(model, expected) if collation_creation else model == expected
                    observations.append({'resource_id': operation['resource_id'],
                                         **({'native_collation_attributes': model.get('specific_attributes') if model else None} if collation_creation else {}),
                                         'result_resource_id': result_identity,
                                         'matches_reviewed_properties': matches and grants_match and (
                                             operation['operation'] != 'rename' or operation['resource_id'] not in after['rows'])})
                outcome['rediscovery'] = {'available': True, 'objects': observations}
                connection.rollback()
            except Exception as error:
                outcome['rediscovery'] = {'available': False, 'error_type': type(error).__name__}
        except Exception as error:
            outcome['error_type'] = type(error).__name__
            outcome['native_status_codes'] = list(status_codes(error))
            # Commit may have reached the server even when its response was
            # lost. Successful cleanup cannot disambiguate that outcome.
            outcome['state'] = 'unknown_outcome' if started else 'not_executed'
            if connection is not None:
                try:
                    if connection.main_transaction.is_active():
                        connection.rollback()
                        outcome['native_rollback_returned'] = True
                        if started and not outcome['commit_requested']:
                            outcome['state'] = 'native_rollback_returned'
                except Exception as rollback_error:
                    outcome['rollback_error_type'] = type(rollback_error).__name__
                    if started:
                        outcome['state'] = 'unknown_outcome'
        finally:
            if connection is not None:
                try:
                    client._release_attachment(connection)
                    outcome['attachment_released'] = True
                except Exception as error:
                    outcome['release_error_type'] = type(error).__name__
    return outcome
