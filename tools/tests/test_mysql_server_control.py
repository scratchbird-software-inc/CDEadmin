"""Native server control consent, fixed requests and acknowledgement boundaries."""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_server_control as control
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from test_mysql_instance import target, UUID


def planned(operation='restart_server'):
    compiled = control.compile_operation(operation, {'confirmation': 'MySQL', 'disconnect_all_clients': True}, target())
    compiled['mysql_server_control']['review'] = {'execution_identity': {'server_uuid': UUID}, 'instance': {'hostname': 'owned'}}
    return {'provider_payload': {'route': {'host': 'owned'}, 'compiled': compiled}}


@pytest.mark.parametrize('draft', [{}, {'confirmation': 'MySQL', 'disconnect_all_clients': False},
    {'confirmation': 'other', 'disconnect_all_clients': True}, {'confirmation': 'MySQL', 'disconnect_all_clients': 'yes'},
    {'confirmation': 'MySQL', 'disconnect_all_clients': True, 'source': 'SHUTDOWN'}])
def test_server_wide_disconnect_requires_exact_consent_before_connect(draft):
    with pytest.raises(RelationalClientError): control.compile_operation('shutdown_server', draft, target())


def test_server_control_is_native_mysql_and_never_accepts_a_borrowed_session():
    catalog = MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    rows = {row['operation_id']: row for item in catalog['objects'] if item['resource_kind'] == 'server' for row in item['operations']}
    for operation in control.OPERATIONS:
        assert MYSQL_ADMINISTRATION.supports('server', operation) and not MARIADB_ADMINISTRATION.supports('server', operation)
        assert rows[operation]['confirmation_required'] and rows[operation]['mutation_class'] == 'destructive'
    client = Mock()
    with pytest.raises(RelationalClientError): control.apply(client, planned(), object())
    forged = deepcopy(planned()); forged['provider_payload']['compiled']['statements'][0]['source'] = 'DROP DATABASE owned'
    with pytest.raises(RelationalClientError): control.apply(client, forged)
    client._connect.assert_not_called()


@pytest.mark.parametrize('outcome', ['ack', 'stale', 'lost-reply', 'native-refusal'])
def test_native_control_ack_is_not_termination_or_readiness_and_never_replays(monkeypatch, outcome):
    client = Mock(); cursor = client._connect.return_value.cursor.return_value
    monkeypatch.setattr(control, 'environment', lambda _: {'server_uuid': UUID})
    monkeypatch.setattr(control, 'instance', lambda _: {'hostname': 'changed' if outcome == 'stale' else 'owned'})
    class Refused(Exception): errno = 3707; sqlstate = 'HY000'
    if outcome == 'lost-reply': cursor.execute.side_effect = OSError('Owned missing reply')
    if outcome == 'native-refusal': cursor.execute.side_effect = Refused()
    if outcome != 'ack':
        with pytest.raises(RelationalClientError) as failure: control.apply(client, planned())
        assert failure.value.native_dispatched == (outcome != 'stale')
        assert not failure.value.native_acknowledged and not failure.value.automatic_retry
        if outcome == 'native-refusal': assert failure.value.native_status_codes == (3707,) and failure.value.sqlstate == 'HY000'
    else:
        result = control.apply(client, planned())
        assert result['server_control_observation']['native_acknowledged']
        assert result['catalog_refresh_deferred']
        assert not any(result['server_control_observation'][key] for key in
            ('server_termination_observed', 'new_process_generation_observed', 'server_readiness_observed'))
        assert result['native_implicit_commit'] and not result['commit_requested']
        cursor.execute.assert_called_once_with('RESTART')
    client._forget_and_close.assert_called_once()
