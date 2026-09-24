"""View inserts need distinct one-use session authority, not a row token."""
from dataclasses import replace
import time
import uuid
import json
from unittest.mock import MagicMock

import firebird.driver as native
import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.relational_admin import _RowIdentity
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.providers.firebird.views import grid_update_identity


def retained(values):
    token = str(uuid.uuid4())
    route = {'database': 'owned'}
    identity = _RowIdentity(
        ADMINISTRATION._route_fingerprint(route), ('V',), (), (), {},
        time.monotonic(), session_id='owned', resource_kind='view',
        writable_columns=('VALUE',), delete_allowed=False, purpose='insert',
        insert_defaults_allowed=True)
    ADMINISTRATION._row_identities[token] = identity
    request = {'_provider_route': route, 'resource_kind': 'view',
               'target_resource': {'resource_kind': 'view',
                                   'display_path': ['V']},
               'operation_id': 'insert', 'session_id': 'owned',
               'draft': {'values': values,
                         'options': {'identity_token': token}}}
    return request, token, identity


@pytest.mark.parametrize('values', [{}, {'VALUE': 3}, {'VALUE': None}])
def test_native_default_or_bound_insert_and_one_use(values):
    request, token, _ = retained(values)
    statement = ADMINISTRATION._compile_insert(request)
    assert statement == (
        {'source': 'INSERT INTO "V" ("VALUE") VALUES (?)',
         'parameters': (values['VALUE'],)} if values else
        {'source': 'INSERT INTO "V" DEFAULT VALUES', 'parameters': ()})
    assert token not in ADMINISTRATION._row_identities
    with pytest.raises(RelationalClientError,
                       match='unavailable or mismatched'):
        ADMINISTRATION._compile_insert(request)


@pytest.mark.parametrize('fault', [
    'session', 'route', 'path', 'kind', 'purpose', 'expired', 'column',
    'defaults', 'missing', 'malformed', 'target-kind', 'table-disguise',
])
def test_insert_authority_fails_closed(fault):
    request, token, identity = retained({} if fault == 'defaults'
                                        else {'VALUE': 1})
    if fault == 'session':
        request['session_id'] = 'other'
    elif fault == 'route':
        request['_provider_route'] = {'database': 'other'}
    elif fault == 'path':
        request['target_resource']['display_path'] = ['OTHER']
    elif fault == 'kind':
        identity = replace(identity, resource_kind='table')
    elif fault == 'purpose':
        identity = replace(identity, purpose='row')
    elif fault == 'expired':
        identity = replace(identity, issued_at=time.monotonic() - 601)
    elif fault == 'column':
        request['draft']['values'] = {'COMPUTED': 2}
    elif fault == 'defaults':
        identity = replace(identity, insert_defaults_allowed=False)
    elif fault == 'missing':
        request['draft']['options'] = {}
    elif fault == 'malformed':
        request['draft']['options']['identity_token'] = {}
    elif fault == 'target-kind':
        request['target_resource']['resource_kind'] = 'table'
    elif fault == 'table-disguise':
        request['resource_kind'] = 'table'
    ADMINISTRATION._row_identities[token] = identity
    try:
        with pytest.raises(RelationalClientError):
            ADMINISTRATION._compile_insert(request)
    finally:
        ADMINISTRATION._row_identities.pop(token, None)


@pytest.mark.parametrize('operation', ['update', 'delete'])
def test_insert_authority_is_not_a_row_selector(operation):
    request, token, _ = retained({'VALUE': 1})
    request['operation_id'] = operation
    request['draft'] = {'selector': {'identity_token': token},
                        'changes': {'VALUE': 4}}
    with pytest.raises(RelationalClientError, match='another purpose'):
        ADMINISTRATION._compile_identity_dml(request)


@pytest.mark.parametrize('operation,denied', [
    ('insert', False), ('insert-defaults', False), ('insert-defaults', True)])
def test_insert_preparation_does_not_execute_mutations(operation, denied):
    handle = MagicMock()
    cursor = handle.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [[('BASE', 0)], [('ID',)],
                                   [('ID_ALIAS', 'ID', 0)]]
    cursor.fetchone.side_effect = [(None, 0), (0,)]
    if denied:
        cursor.prepare.side_effect = native.DatabaseError('denied')
    result = grid_update_identity(handle, 'V"X', operation=operation)
    assert result == (((), ()) if denied else
                      (('ID_ALIAS',), ('ID_ALIAS',)) if operation == 'insert'
                      else (('ID_ALIAS',), ()))
    cursor.prepare.assert_called_once_with(
        'INSERT INTO "V""X" ("ID_ALIAS") VALUES (?)'
        if operation == 'insert' else
        'INSERT INTO "V""X" DEFAULT VALUES')
    if not denied:
        cursor.prepare.return_value.free.assert_called_once_with()
    assert all(call.args[0].startswith('SELECT')
               for call in cursor.execute.call_args_list)
    handle.commit.assert_not_called()
    handle.rollback.assert_not_called()


@pytest.mark.parametrize('fault', [
    None, 'checks', 'permissions', 'failure', 'version', 'cleanup', 'complete',
    'statement'])
def test_insert_dialect_activation_evidence(fault):
    from tools.reference_engine_demos import generate_firebird_dialect_contract
    module = generate_firebird_dialect_contract
    document = json.loads((module.WEB / 'pgadmin/cdeadmin/providers/firebird/'
                           'firebird_dialect_5_0_4.json').read_text())
    evidence = {
        'schema': 'cdeadmin.firebird-views.v1', 'engine_version': '5.0.4',
        'complete': True, 'owned_container_removed': True, 'failures': [],
        'view_insert_checks': [
            {'case': mode + ':' + action, 'passed': True}
            for mode in ('explicit', 'defaults', 'null', 'computed',
                         'wrong-session', 'replay')
            for action in ('commit', 'rollback')],
        'view_insert_permissions': [
            {'phase': phase, 'passed': True}
            for phase in ('select-only', 'insert-only', 'revoked')],
        'task_evidence': {'visual_admin.view.insert': {
            'live_execution': 'passed',
            'statements': ['INSERT INTO "V" DEFAULT VALUES']}},
    }
    if fault == 'checks':
        evidence['view_insert_checks'].pop()
    elif fault == 'permissions':
        evidence['view_insert_permissions'].pop()
    elif fault == 'failure':
        evidence['view_insert_checks'][0]['passed'] = False
    elif fault == 'version':
        evidence['engine_version'] = '5.0.3'
    elif fault == 'cleanup':
        evidence['owned_container_removed'] = False
    elif fault == 'complete':
        evidence['complete'] = False
    elif fault == 'statement':
        record = evidence['task_evidence']['visual_admin.view.insert']
        record['statements'] = []
    if fault:
        with pytest.raises(ValueError):
            module.supplement_view_insert(
                document, evidence, 'a' * 64, 'owned.json')
    else:
        result = module.supplement_view_insert(
            document, evidence, 'a' * 64, 'owned.json')
        assert result == module.supplement_view_insert(
            result, evidence, 'a' * 64, 'owned.json')
