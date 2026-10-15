"""Qualify metadata-only transfers with persisted aliases of an owned native DB."""
import json
from unittest.mock import patch


def qualify(connection, client, route):
    # This harness supplies authenticated owners around the real SQLite-backed
    # configuration models; the native attachment remains independent of them.
    from tools.tests.test_firebird_registration_transfer import rig, request
    from pgadmin.cdeadmin.endpoints.firebird_registration import transfer
    scope = rig.__wrapped__()
    fixture = next(scope)
    try:
        for server in (fixture.source, fixture.destination):
            server.username = 'SYSDBA'
            server.endpoint_profile.routes[0].configuration = json.dumps({
                **{key: route[key] for key in ('host', 'port') if key in route},
                'user': 'SYSDBA', 'charset': 'UTF8', 'trusted_auth': False})
            server.endpoint_profile.profile_id = ('firebird-embedded' if
                route.get('attachment_mode') == 'embedded' else 'firebird-native')
        fixture.target.database = route['database']
        fixture.model.db.session.commit()
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE SR_REG_SENTINEL (V INTEGER)')
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO SR_REG_SENTINEL VALUES (1)')
        connection.commit()
        with patch.object(client, 'open_session', wraps=client.open_session) as opens:
            cloned = transfer(fixture.service, fixture.source, request(fixture))
            clone_id = cloned['target']['target_id']
            assert clone_id != fixture.target.id and not cloned['target']['active']
            assert cloned['target']['database'] == route['database']
            moved = transfer(fixture.service, fixture.source, request(fixture,
                target_id=clone_id, operation='move', display_name='Moved alias',
                destination_server_id=fixture.destination.id, credentials='destination'))
            assert moved['target']['target_id'] == clone_id
            assert not moved['target']['active']
            assert not moved['native_database_changed'] and not moved['native_connection_verified']
            opens.assert_not_called()
        # Separate, explicit verification of the relocated alias opens its own
        # connection and sees the original native data; transfer never opens it.
        target = fixture.model.db.session.get(fixture.model.EndpointDatabaseTarget, clone_id)
        verified_route = {**route, 'database': target.database,
                          **json.loads(target.configuration)}
        native = client.open_session({'route': verified_route})
        try:
            with native.cursor() as cursor:
                cursor.execute('SELECT V FROM SR_REG_SENTINEL')
                assert cursor.fetchall() == [(1,)]
            native.rollback()
        finally:
            client.close_session(native)
        return {'passed': True, 'clone_new_identity': True, 'move_preserved_identity': True,
                'inactive_after_each_transfer': True, 'native_open_not_requested_by_transfer': True,
                'explicit_verification_preserved_original_data': True,
                'local_configuration_persisted': True}
    finally:
        scope.close()


def retain_recreated(route, path):
    """Called only after the owned native replacement's create receipt returns."""
    from tools.tests.test_firebird_registration_transfer import rig
    scope = rig.__wrapped__()
    fixture = next(scope)
    try:
        fixture.source.endpoint_profile.profile_id = ('firebird-embedded' if
            route.get('attachment_mode') == 'embedded' else 'firebird-native')
        fixture.target.database = path
        fixture.target.display_name = 'Remaining alias'
        fixture.model.db.session.commit()
        old_id = fixture.target.id
        catalog = fixture.service.retain_created_database(fixture.source, {
            'database': path, 'display_name': 'Native replacement'})
        replacement = next(item for item in catalog['targets']
                           if item['display_name'] == 'Native replacement')
        assert replacement['target_id'] != old_id and replacement['active']
        assert not fixture.target.active and fixture.target.id == old_id
        assert fixture.target.display_name == 'Remaining alias'
        return {'new_registration_identity': True, 'existing_alias_preserved': True,
                'replacement_active': True}
    finally:
        scope.close()
