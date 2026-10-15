"""Real configuration persistence and scope guards for registration aliases."""
import config
import json
import sys
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pgadmin.cdeadmin.core import ProviderRegistry, ProviderReleaseError
from pgadmin.cdeadmin.endpoints.service import EndpointService, ProtectedColumnResolver
from pgadmin.cdeadmin.endpoints.firebird_registration import catalog, transfer, secret_model
from pgadmin.cdeadmin.endpoints.profiles import EndpointRegistrationError, registration_profile
from tools.tests import test_cdeadmin_endpoint_persistence as persistence


@pytest.fixture
def rig():
    setup = persistence.EndpointPersistenceModelTests(); setup.setUp()
    model = setup.model
    try:
        servers = []
        for ident in (10, 11):
            server = model.Server(id=ident, user_id=1, servergroup_id=1,
                name=f'Server {ident}', host='localhost', port=3050 + ident,
                maintenance_db='unused', username='SOURCE', password='encrypted-source',
                save_password=1, use_ssh_tunnel=0, tunnel_authentication=0,
                tunnel_prompt_password=0, shared=False, kerberos_conn=False,
                cloud_status=0, is_adhoc=0)
            model.db.session.add(server); model.db.session.commit()
            endpoint = server.endpoint_profile
            endpoint.profile_id = 'firebird-native'; endpoint.provider_version = '0.1.0'
            endpoint.profile_version = '0.1.0'
            endpoint.routes[0].configuration = json.dumps({'host': 'localhost', 'port': server.port,
                'user': 'SOURCE', 'charset': 'WIN1252', 'role': 'APPLICATION', 'trusted_auth': False})
            servers.append(server)
        target = model.EndpointDatabaseTarget(id=str(uuid.uuid4()), endpoint=servers[0].endpoint_profile,
            database='/db/owned.fdb', display_name='Original', configuration='{}', active=True)
        model.db.session.add(target); model.db.session.commit()
        registry = ProviderRegistry(); service = EndpointService(registry, Mock())
        with patch.dict(sys.modules, {'pgadmin.model': model}), patch('flask_login.current_user', SimpleNamespace(id=1, is_authenticated=True)):
            yield SimpleNamespace(app=setup.app, model=model, service=service, source=servers[0], destination=servers[1], target=target)
    finally:
        setup.tearDown()


def request(rig, **changes):
    destination = rig.destination if changes.get('destination_server_id') == rig.destination.id else rig.source
    return {'source_generation': rig.source.endpoint_profile.profile_generation,
            'destination_generation': destination.endpoint_profile.profile_generation,
            'target_id': rig.target.id, 'destination_server_id': rig.source.id,
            'operation': 'clone', 'display_name': 'Alias', 'credentials': 'source',
            'confirmed': True, **changes}


def test_clone_keeps_filename_with_distinct_id_and_credential_snapshot(rig):
    result = transfer(rig.service, rig.source, request(rig))
    clone = rig.model.EndpointDatabaseTarget.query.filter_by(id=result['target']['target_id']).one()
    assert clone.id != rig.target.id and clone.database == rig.target.database
    assert not clone.active and rig.target.active
    assert clone.registration_user == 'SOURCE'
    assert clone.registration_password == 'encrypted-source'
    assert json.loads(clone.configuration) == {'role': 'APPLICATION', 'charset': 'WIN1252'}
    rig.source.password = 'changed-later'; rig.model.db.session.commit()
    assert clone.registration_password == 'encrypted-source'
    assert 'encrypted-source' not in json.dumps(result)
    assert not result['native_database_changed'] and not result['native_connection_verified']
    assert len(catalog(rig.service, rig.source, clone.id)['destinations']) == 2
    with pytest.raises(EndpointRegistrationError, match='exact registration'):
        rig.service._unambiguous_database_target(rig.source.endpoint_profile, clone.database)


def test_move_keeps_id_inactive_and_uses_selected_destination_policy(rig):
    before = rig.target.id
    result = transfer(rig.service, rig.source, request(rig, operation='move',
        destination_server_id=rig.destination.id, credentials='destination'))
    assert result['target']['target_id'] == before
    assert rig.target.endpoint_id == rig.destination.endpoint_profile.id
    assert not rig.target.active and not rig.target.registration_credentials
    assert rig.target.registration_password is None
    assert rig.source.endpoint_profile.database_targets == []


def test_guards_are_held_for_both_endpoints_and_pending_work_refuses_all_changes(rig):
    calls = []
    @contextmanager
    def guard(endpoint_id):
        calls.append(endpoint_id)
        if endpoint_id == rig.destination.endpoint_profile.id:
            raise ProviderReleaseError('pending work')
        yield
    with patch.object(rig.service.provider_registry, 'endpoint_configuration_change', guard):
        with pytest.raises(EndpointRegistrationError, match='pending work'):
            transfer(rig.service, rig.source, request(rig, operation='move', destination_server_id=rig.destination.id))
    assert rig.target.endpoint_id == rig.source.endpoint_profile.id
    assert rig.target.active and rig.target.display_name == 'Original'
    assert calls


@pytest.mark.parametrize('changes', [
    {'display_name': 'Original'}, {'operation': 'move'},
    {'destination_server_id': 9999}, {'destination_server_id': True},
    {'confirmed': False}, {'credentials': 'guess'}, {'target_id': 'missing'}])
def test_invalid_transfer_does_not_change_records(rig, changes):
    with pytest.raises(EndpointRegistrationError):transfer(rig.service, rig.source, request(rig, **changes))
    assert rig.model.EndpointDatabaseTarget.query.count() == 1
    assert rig.target.active


def test_missing_saved_password_does_not_capture_session_password(rig):
    rig.source.password = None; rig.model.db.session.commit()
    result = transfer(rig.service, rig.source, request(rig))
    clone = rig.model.db.session.get(rig.model.EndpointDatabaseTarget, result['target']['target_id'])
    assert clone.registration_credentials and clone.registration_password is None
    assert not result['target']['has_saved_registration_password']


def test_registration_route_and_transient_password_are_isolated_from_parent(rig):
    result = transfer(rig.service, rig.source, request(rig))
    clone = rig.model.db.session.get(rig.model.EndpointDatabaseTarget, result['target']['target_id'])
    profile = registration_profile('firebird-native')
    route, reference = rig.service._route_and_reference(rig.source, rig.source.endpoint_profile,
        profile, database_override=clone.database, database_options=json.loads(clone.configuration),
        credential_target=clone)
    assert route['user'] == 'SOURCE' and route['charset'] == 'WIN1252'
    assert reference.locator == f'database_target:{clone.id}:registration_password'
    assert reference.reference_id != rig.source.endpoint_profile.secret_references[0].id
    with rig.service._transient_credentials(rig.source.endpoint_profile, route, reference, 'prompt-only'):
        value = rig.service.resolver(reference.locator, SimpleNamespace(endpoint_id=clone.endpoint_id), 'connect', 'user:1')
        assert value == 'prompt-only'
        with pytest.raises(EndpointRegistrationError):
            rig.service.resolver(reference.locator, SimpleNamespace(endpoint_id='different'), 'connect', 'user:1')
    assert not rig.service.resolver._transient
    old_reference = secret_model(clone)
    transfer(rig.service, rig.source, request(rig, target_id=clone.id, operation='move',
        destination_server_id=rig.destination.id, display_name='Moved'))
    assert secret_model(clone).id != old_reference.id


def test_registration_locator_requires_exact_uuid_and_column():
    for value in ('database_target:10:registration_password',
                  f'database_target:{uuid.uuid4()}:password', 'unknown:1:password'):
        with pytest.raises(EndpointRegistrationError):ProtectedColumnResolver._parse_locator(value)


def test_registration_passwords_follow_key_rotation_and_explicit_clearing(rig):
    from pgadmin.utils.crypto import encrypt, decrypt
    from pgadmin.cdeadmin.endpoints import registration_credentials
    rig.source.password = encrypt('owned-password', 'old-key')
    rig.model.db.session.commit()
    result = transfer(rig.service, rig.source, request(rig))
    clone = rig.model.db.session.get(rig.model.EndpointDatabaseTarget, result['target']['target_id'])
    registration_credentials.reencrypt(rig.source, 'old-key', 'new-key')
    rig.model.db.session.commit()
    assert decrypt(clone.registration_password, 'new-key') == b'owned-password'
    assert registration_credentials.has_saved(rig.source)
    rig.service.clear_saved_credentials(rig.source)
    assert clone.registration_password is None and rig.source.password is None
    assert clone.registration_credentials and clone.registration_user == 'SOURCE'
    assert not registration_credentials.has_saved(rig.source)



def test_concurrent_clones_cannot_admit_two_identical_names(rig):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    source_id, target_id = rig.source.id, rig.target.id
    generation = rig.source.endpoint_profile.profile_generation
    class Registry:
        @contextmanager
        def endpoint_configuration_change(self, _endpoint_id):
            barrier.wait(timeout=10)
            yield
    def worker():
        with rig.app.app_context():
            source = rig.model.db.session.get(rig.model.Server, source_id)
            service = EndpointService(Registry(), Mock())
            try:
                return transfer(service, source, {'target_id': target_id,
                    'destination_server_id': source_id, 'operation': 'clone',
                    'display_name': 'Concurrent alias', 'credentials': 'source', 'confirmed': True,
                    'source_generation': generation, 'destination_generation': generation})
            except EndpointRegistrationError as error:
                return {'refused': str(error)}
            finally:
                rig.model.db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert sum('target' in item for item in results) == 1, results
    assert sum('refused' in item for item in results) == 1, results
    rig.model.db.session.expire_all()
    assert rig.model.EndpointDatabaseTarget.query.filter_by(display_name='Concurrent alias').count() == 1


@pytest.mark.parametrize('endpoint_name', ['source', 'destination'])
def test_reviewed_generation_cannot_follow_later_configuration(rig, endpoint_name):
    reviewed = request(rig, destination_server_id=rig.destination.id)
    endpoint = getattr(rig, endpoint_name).endpoint_profile
    endpoint.profile_generation = str(uuid.uuid4())
    rig.model.db.session.commit()
    with pytest.raises(EndpointRegistrationError, match='configuration changed'):
        transfer(rig.service, rig.source, reviewed)
    assert rig.model.EndpointDatabaseTarget.query.count() == 1
    assert rig.target.active and rig.target.display_name == 'Original'


def test_destination_credentials_inherit_role_and_charset(rig):
    rig.target.configuration = json.dumps({'role': 'SOURCE_ONLY', 'charset': 'ASCII', 'sql_dialect': 1})
    rig.model.db.session.commit()
    result = transfer(rig.service, rig.source, request(rig, credentials='destination'))
    clone = rig.model.db.session.get(rig.model.EndpointDatabaseTarget, result['target']['target_id'])
    assert json.loads(clone.configuration) == {'sql_dialect': 1}
    assert not clone.registration_credentials
    assert clone.registration_user is None and clone.registration_password is None


@pytest.mark.parametrize('profile_id', ['firebird-native', 'firebird-embedded'])
def test_created_database_gets_new_identity_beside_existing_alias(rig, profile_id):
    rig.source.endpoint_profile.profile_id = profile_id
    rig.model.db.session.commit()
    old_id = rig.target.id
    value = rig.service.retain_created_database(rig.source, {
        'database': rig.target.database, 'display_name': 'Replacement'})
    replacement = next(item for item in value['targets'] if item['display_name'] == 'Replacement')
    assert replacement['target_id'] != old_id and replacement['active']
    assert rig.target.id == old_id and not rig.target.active
    assert rig.target.display_name == 'Original'
    assert rig.model.EndpointDatabaseTarget.query.count() == 2


@pytest.mark.parametrize('profile_id', ['firebird-native', 'firebird-embedded'])
def test_created_database_registration_collision_keeps_existing_alias(rig, profile_id):
    rig.source.endpoint_profile.profile_id = profile_id
    rig.model.db.session.commit()
    generation = rig.source.endpoint_profile.profile_generation
    with pytest.raises(EndpointRegistrationError, match='without repeating native creation'):
        rig.service.retain_created_database(rig.source, {
            'database': rig.target.database, 'display_name': rig.target.display_name})
    assert rig.model.EndpointDatabaseTarget.query.count() == 1
    assert rig.target.active
    assert rig.source.endpoint_profile.profile_generation == generation


def test_removing_inactive_alias_invalidates_reviewed_transfer(rig):
    cloned = transfer(rig.service, rig.source, request(rig))
    reviewed = request(rig, display_name='Later clone')
    rig.service.delete_database_target(rig.source, cloned['target']['target_id'],
                                      {'confirmation': rig.target.database})
    assert rig.source.endpoint_profile.profile_generation != reviewed['source_generation']
    with pytest.raises(EndpointRegistrationError, match='configuration changed'):
        transfer(rig.service, rig.source, reviewed)
    assert rig.model.EndpointDatabaseTarget.query.count() == 1
