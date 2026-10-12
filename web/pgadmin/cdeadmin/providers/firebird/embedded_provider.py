"""Local-file interface sharing Firebird's native SQL implementation."""

from dataclasses import replace
from pathlib import Path

from ..relational_admin import (
    RelationalAdministration, _FIREBIRD_SERVICE_OPERATIONS,
)
from .provider import (
    FirebirdProvider, PROFILE as NETWORK_PROFILE,
    ADMINISTRATION as NETWORK_ADMINISTRATION, _create_client,
)
from .embedded import embedded_route
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


PROFILE = replace(
    NETWORK_PROFILE, provider_id='org.cdeadmin.firebird.embedded',
    profile_id='firebird-embedded', protocol_id='firebird_embedded',
    dialect_contract_file='firebird_embedded_dialect_5_0_4.json',
    metrics_contract_file='firebird_embedded_metrics_5_0_4.json',
    required_permissions=('embedded_runtime', 'filesystem'), admin_tools=(),
    resource_kinds=tuple(kind for kind in NETWORK_PROFILE.resource_kinds
                         if kind != 'service-operation'))


class EmbeddedAdministration(RelationalAdministration):
    """Reuse SQL forms without exposing the network service boundary."""

    def catalog(self, catalog):
        value = super().catalog(catalog)
        value['objects'] = [
            resource for resource in value.get('objects', [])
            if resource['resource_kind'] not in {'server', 'service-operation'}
        ]
        for resource in value['objects']:
            if resource['resource_kind'] != 'database':
                continue
            for operation in resource.get('operations', []):
                if operation['operation_id'] != 'create':
                    continue
                for field in operation.get('form', {}).get('fields', []):
                    if field['field_id'] == 'database_path':
                        field['label'] = (
                            'Absolute local database filename on the '
                            'ScratchRobin host')
        return value


ADMINISTRATION = EmbeddedAdministration(replace(
    NETWORK_ADMINISTRATION.dialect,
    not_applicable_concepts=(
        NETWORK_ADMINISTRATION.dialect.not_applicable_concepts |
        frozenset({'servers'})),
    supported={
        kind: (operations - _FIREBIRD_SERVICE_OPERATIONS
               if kind == 'database' else operations)
        for kind, operations in (
            NETWORK_ADMINISTRATION.dialect.supported.items())
        if kind not in {'server', 'service-operation'}
    }))


class EmbeddedFirebirdProvider(FirebirdProvider):
    def create_initial_database(self, request):
        """Bootstrap an explicit local file before it can be verified.

        This is not discovery: opening an absent database never creates it.
        The native driver also receives overwrite=False, closing the race
        between this friendly existence check and native file creation.
        """
        self._admit_transport(request)
        self.permissions.require('administer')
        route = embedded_route(request['route'], self.permissions)
        if Path(route['database']).exists():
            raise RelationalClientError(
                'Create database will not overwrite an existing file')
        return self.client.create_database(
            {'route': route}, route['database'], 'firebird-create-database')


def create_provider(context, permissions, client=None):
    return EmbeddedFirebirdProvider(
        context, permissions, client or _create_client(
            permissions, attachment_mode='embedded', profile=PROFILE,
            administration=ADMINISTRATION), profile=PROFILE)
