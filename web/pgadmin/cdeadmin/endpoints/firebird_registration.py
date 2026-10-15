"""Local registration identity, credential snapshots and guarded relocation."""

import json
import uuid
from contextlib import ExitStack
from types import SimpleNamespace

from .profiles import EndpointRegistrationError
from .credential_storage import protected_configuration_write


def secret_model(target):
    if not getattr(target, 'registration_credentials', False):
        return None
    return SimpleNamespace(
        id=str(uuid.uuid5(uuid.UUID(target.id),
                         f'registration-password:{target.endpoint_id}')),
        secret_kind='database_password', storage_kind='protected_column',
        secret_reference=f'database_target:{target.id}:registration_password',
    )


def secret_models(endpoint):
    return [model for target in getattr(endpoint, 'database_targets', ())
            if (model := secret_model(target)) is not None]


def owned_firebird(service, server):
    from flask_login import current_user
    endpoint, profile = service._managed_endpoint(server)
    if (not current_user.is_authenticated or
            server.user_id != current_user.id or
            profile['profile_id'] not in {'firebird-native', 'firebird-embedded'}):
        raise EndpointRegistrationError('Firebird registration is unavailable')
    return endpoint, profile


def catalog(service, server, target_id):
    from pgadmin.model import Server
    endpoint, profile = owned_firebird(service, server)
    target = service._owned_database_target(endpoint, target_id)
    destinations = []
    for candidate in Server.query.filter_by(user_id=server.user_id).all():
        other = candidate.endpoint_profile
        if other is not None and other.profile_id == profile['profile_id']:
            destinations.append({'server_id': candidate.id,
                                 'name': candidate.name,
                                 'endpoint_id': other.id,
                                 'generation': other.profile_generation})
    return {'source': service._database_target_value(target),
            'source_server_id': server.id,
            'source_generation': endpoint.profile_generation,
            'destinations': sorted(destinations,
                                   key=lambda row: (row['name'], row['server_id']))}


def transfer(service, server, request):
    from pgadmin.model import Server, EndpointDatabaseTarget, EndpointProfile, db
    from pgadmin.cdeadmin.core import ProviderReleaseError

    if not isinstance(request, dict) or set(request) != {
            'target_id', 'destination_server_id', 'operation',
            'display_name', 'credentials', 'confirmed',
            'source_generation', 'destination_generation'}:
        raise EndpointRegistrationError('Invalid registration transfer fields')
    if request['confirmed'] is not True or request['operation'] not in {'clone', 'move'}:
        raise EndpointRegistrationError('Confirm the registration clone or move')
    if request['credentials'] not in {'source', 'destination'}:
        raise EndpointRegistrationError('Choose the registration credential policy')
    destination_id = request['destination_server_id']
    if isinstance(destination_id, bool) or not isinstance(destination_id, int):
        raise EndpointRegistrationError('Choose a destination server')
    source_endpoint, profile = owned_firebird(service, server)
    destination = Server.query.filter_by(id=destination_id,
                                         user_id=server.user_id).first()
    if destination is None:
        raise EndpointRegistrationError('Destination server is unavailable')
    dest_endpoint, dest_profile = owned_firebird(service, destination)
    if dest_profile['profile_id'] != profile['profile_id']:
        raise EndpointRegistrationError('Registration interfaces must match')
    moving = request['operation'] == 'move'
    if moving and dest_endpoint.id == source_endpoint.id:
        raise EndpointRegistrationError('Move requires a different server')
    for key, endpoint in (('source_generation', source_endpoint),
                          ('destination_generation', dest_endpoint)):
        if (not isinstance(request[key], str) or not request[key] or
                request[key] != endpoint.profile_generation):
            raise EndpointRegistrationError('Registration configuration changed; refresh before transferring')
    target = service._owned_database_target(source_endpoint, request['target_id'])
    _, display_name = service._database_target_input({
        'database': target.database, 'display_name': request['display_name']})
    try:
        with ExitStack() as guards:
            for endpoint_id in sorted({source_endpoint.id, dest_endpoint.id}):
                guards.enter_context(service.provider_registry.
                                     endpoint_configuration_change(endpoint_id))
            with protected_configuration_write(db.session):
                endpoints = {source_endpoint.id: source_endpoint, dest_endpoint.id: dest_endpoint}
                for endpoint_id, endpoint in sorted(endpoints.items()):
                    generation = str(uuid.uuid4())
                    changed = db.session.query(EndpointProfile).filter(
                        EndpointProfile.id == endpoint_id,
                        EndpointProfile.profile_generation == request[
                            'source_generation' if endpoint_id == source_endpoint.id
                            else 'destination_generation'],
                    ).update({'profile_generation': generation}, synchronize_session=False)
                    if changed != 1:
                        raise EndpointRegistrationError('Registration configuration changed; refresh before transferring')
                    endpoint.profile_generation = generation
                if EndpointDatabaseTarget.query.filter_by(
                        endpoint_id=dest_endpoint.id, display_name=display_name).first() is not None:
                    raise EndpointRegistrationError('Destination registration name already exists')
                configuration = service._database_target_configuration(target)
                user, password = None, None
                if request['credentials'] == 'source':
                    route = min(source_endpoint.routes,
                                key=lambda item: (item.priority, item.id))
                    source_route = service._route_configuration(route)
                    user = (target.registration_user if getattr(
                        target, 'registration_credentials', False)
                        else source_route.get('user'))
                    password = (target.registration_password if getattr(
                        target, 'registration_credentials', False)
                        else server.password)
                    # Capture effective role/charset instead of silently inheriting
                    # different destination defaults after a move.
                    for key in ('role', 'charset'):
                        if key not in configuration and key in source_route:
                            configuration[key] = source_route[key]
                else:
                    # Inherited credentials follow the destination's effective
                    # identity, including its role and character set.
                    configuration.pop('role', None)
                    configuration.pop('charset', None)
                old_secret = secret_model(target)
                result = target if moving else EndpointDatabaseTarget(
                    id=str(uuid.uuid4()), database=target.database)
                result.endpoint = dest_endpoint
                result.display_name = display_name
                result.configuration = json.dumps(configuration, sort_keys=True)
                result.active = False
                result.registration_credentials = request['credentials'] == 'source'
                result.registration_user = user
                result.registration_password = password
                db.session.add(result)
                db.session.commit()
            if moving and old_secret:
                service.resolver.forget(old_secret.secret_reference)
            if moving:
                with service._principal_lock:
                    service._principal_overrides.pop((source_endpoint.id, target.id), None)
            return {'operation': request['operation'],
                    'source_endpoint_id': source_endpoint.id,
                    'destination_endpoint_id': dest_endpoint.id,
                    'destination_server_id': destination.id,
                    'target': service._database_target_value(result),
                    'native_database_changed': False,
                    'native_connection_verified': False}
    except ProviderReleaseError as error:
        raise EndpointRegistrationError(str(error)) from None
