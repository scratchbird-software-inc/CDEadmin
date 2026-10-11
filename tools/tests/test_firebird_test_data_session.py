import config
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError
from tools.tests.test_cdeadmin_context_menu import profile
from pgadmin.cdeadmin.context_menu import database_target_context_actions


def service(profile_id='firebird-native'):
    owner = object.__new__(ProviderWorkspaceService)
    endpoint = {'route': {'database': 'owned.fdb', 'user': 'owner', 'credential_reference': 'retained',
        'transaction_auto_commit': True, 'transaction_access': 'READ', 'transaction_ignore_limbo': True}}
    context = SimpleNamespace(profile_id=profile_id)
    owner.endpoint_service = SimpleNamespace(workspace=Mock(return_value=(context, endpoint, None)))
    owner.studio_service = SimpleNamespace(open_session=Mock(return_value={'provider_session': {'session_id': 'separate'}}))
    return owner, endpoint


@pytest.mark.parametrize('profile_id', ['firebird-native', 'firebird-embedded'])
@pytest.mark.parametrize('purpose', ['firebird-test-data', 'firebird-row-grid'])
def test_generator_session_overrides_only_its_native_transaction_defaults(profile_id, purpose):
    owner, endpoint = service(profile_id)
    before = deepcopy(endpoint)
    result = owner.open_session('server', 'firebird-sql', 'target', session_purpose=purpose)
    assert result['session_id'] == 'separate'
    route = owner.studio_service.open_session.call_args.args[1]['route']
    assert route['transaction_auto_commit'] is False and route['transaction_access'] == 'WRITE'
    assert route['transaction_no_auto_undo'] is False and route['transaction_ignore_limbo'] is False
    assert route['database'] == 'owned.fdb' and route['credential_reference'] == 'retained'
    assert endpoint == before
    owner.endpoint_service.workspace.assert_called_once_with('server', database_target_id='target')


@pytest.mark.parametrize('profile_id, language, purpose', [
    ('mysql-native', 'mysql-sql', 'firebird-test-data'),
    ('mysql-native', 'mysql-sql', 'firebird-row-grid'),
    ('firebird-native', 'postgresql-sql', 'firebird-row-grid'),
    ('firebird-native', 'firebird-sql', 'unrecognized'),
    ('firebird-native', 'postgresql-sql', 'firebird-test-data')])
def test_other_engine_language_and_unknown_purpose_are_refused(profile_id, language, purpose):
    owner, _ = service(profile_id)
    with pytest.raises(ProviderWorkspaceError): owner.open_session('server', language, 'target', session_purpose=purpose)
    owner.studio_service.open_session.assert_not_called()


def test_ordinary_sessions_keep_registered_transaction_policy():
    owner, endpoint = service()
    owner.open_session('server', 'firebird-sql', 'target')
    assert owner.studio_service.open_session.call_args.args[1] is endpoint


def test_generator_navigation_is_firebird_database_scoped():
    target = {'target_id': 'db', 'database': 'owned.fdb', 'label': 'Owned'}
    for engine in ('firebird', 'mysql'):
        actions = database_target_context_actions(profile(engine, multiple=True), target)
        matching = [item for item in actions if item['command_id'] == 'database.firebird.test_data']
        assert bool(matching) == (engine == 'firebird')
        if matching:
            assert matching[0]['arguments']['tab'] == 'firebird-test-data'
            assert matching[0]['arguments']['database_target_id'] == 'db'
