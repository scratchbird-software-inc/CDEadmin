##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Thin authenticated workspace orchestration over common CDEadmin services.

The facade does not interpret query text, provider operation state,
cancellation outcome, or transaction finality. Those values remain owned by
the endpoint provider and are returned as opaque contract presentations.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import threading

from pgadmin.cdeadmin.resources import ResourcePage, ResourceRef
from pgadmin.cdeadmin.visual_admin.provider import (
    VisualAdminAccessError,
    VisualAdminExecutionError,
)
from pgadmin.cdeadmin.visual_admin.operational_workspace import (
    build_operational_workspace,
)
from pgadmin.cdeadmin.grid_contract import workspace_grid_contract


APP_EXTENSION_KEY = 'cdeadmin_provider_workspace'


class ProviderWorkspaceError(RuntimeError):
    """A provider endpoint workspace request cannot be admitted."""


class ProviderWorkspaceService:
    """Mount explorer, studio and typed results for one endpoint."""

    def __init__(
        self, endpoint_service, resource_service, studio_service,
        result_service, semantic_model_service=None, operation_bus=None,
        report_delivery_service=None, report_scheduler_service=None,
    ):
        self.endpoint_service = endpoint_service
        self.resource_service = resource_service
        self.studio_service = studio_service
        self.result_service = result_service
        self.semantic_model_service = semantic_model_service
        self.operation_bus = operation_bus
        self.report_delivery_service = report_delivery_service
        self.report_scheduler_service = report_scheduler_service
        from ..providers.firebird.events import EventSubscriptions
        self.firebird_events = EventSubscriptions()
        self._semantic_executions = {}
        self._semantic_lock = threading.RLock()
        from pgadmin.cdeadmin.providers.firebird.recovery_groups import (
            RecoveryGroups,
        )
        self.firebird_recovery_groups = RecoveryGroups(
            operation_bus.store if operation_bus is not None else None)

    def firebird_recovery_action(
            self, server, action, request, resolve_server):
        """Resolve each participant under the authenticated route's owner."""
        from pgadmin.cdeadmin.providers.firebird.provider import (
            FirebirdProvider,
        )
        from pgadmin.cdeadmin.providers.firebird.recovery_groups import (
            RecoveryGroupError, inspect_participant, participant_binding,
        )
        owner = self._principal_id(server)
        groups = self.firebird_recovery_groups
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id',
                   None) not in {'firebird-native', 'firebird-embedded'}:
            raise RecoveryGroupError('Select a Firebird recovery workspace')

        def resolve(selection):
            participant = resolve_server(selection['server_id'])
            if participant is None or self._principal_id(participant) != owner:
                raise RecoveryGroupError('Participant endpoint is unavailable')
            context, endpoint, _root = self.endpoint_service.workspace(
                participant,
                database_target_id=selection['database_target_id'])
            provider = self.endpoint_service.provider_registry.resolve(
                context).instance
            if not isinstance(provider, FirebirdProvider) or (
                    context.profile_id not in {
                        'firebird-native', 'firebird-embedded'}):
                raise RecoveryGroupError('Select a verified Firebird endpoint')
            route = endpoint['route']
            binding = participant_binding(context, route)
            identity, observation = inspect_participant(
                provider, route, selection['transaction_id'])

            def execute(decision):
                values = {
                    'transaction_id': selection['transaction_id'],
                    'confirmation': selection['transaction_id'],
                    'database_confirmation': route['database'],
                    'coordinator_reviewed': True,
                }
                result = provider.client.run_limbo_operation(
                    {'route': route}, decision + '_limbo_local', values)
                try:
                    self.resource_service.invalidate(context)
                except Exception as error:
                    # A failed explorer refresh cannot erase a native receipt.
                    result['workspace_follow_up'] = {
                        'refresh_required': True,
                        'error_type': type(error).__name__,
                    }
                return result

            def dispatch(decision):
                # Re-resolve immediately before each native call: earlier
                # participants may have taken time or changed authorization.
                latest = resolve(selection)
                if latest['binding'] != binding or (
                        latest['database_identity'] != identity):
                    raise RecoveryGroupError(
                        'Participant changed before dispatch')
                return latest['execute'](decision)

            return {'database': route['database'],
                    'server_name': participant.name, 'binding': binding,
                    'database_identity': identity, 'observation': observation,
                    'dispatch': dispatch, 'execute': execute}

        coordinator = int(server.id)
        if action == 'firebird_recovery_preview':
            return groups.preview(request, owner, coordinator, resolve)
        if action == 'firebird_recovery_apply':
            return groups.apply(request, owner, coordinator, resolve)
        if action == 'firebird_recovery_status' and isinstance(request, dict):
            return groups.get(request.get('group_id'), owner, coordinator)
        raise RecoveryGroupError('Recovery action is unavailable')

    def registration_workspace(self, server):
        """Read local endpoint configuration without native verification.

        The authenticated workspace route enforces endpoint ownership. This
        response admits no native resources, sessions, or capabilities.
        """
        catalog = self.endpoint_service.route_catalog(server)
        return {'endpoint_registration': {
            'display_name': server.name,
            'is_password_saved': bool(getattr(server, 'save_password', False)),
            'forms': catalog['server_forms'],
            'primary_route': (catalog['routes'][0]
                              if catalog['routes'] else None),
        }}

    def bootstrap(
        self, server, database_target_id=Ellipsis,
        focused_operation_id=None,
    ):
        from .firebird_editor import languages as editor_languages
        context, endpoint, root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        binding = self.endpoint_service.provider_registry.resolve(context)
        describe_admin = getattr(
            binding.instance, 'visual_admin_descriptor', None
        )
        visual_admin = describe_admin() if callable(describe_admin) else None
        service_targets = self._service_workspace_targets(
            context, root, visual_admin, server, database_target_id,
            focused_operation_id,
        )
        if service_targets is None:
            page = self.resource_service.list_page(
                context, root, page_size=500,
                provider_route=endpoint['route'],
            ).to_dict()
        else:
            page = ResourcePage(
                parent=ResourceRef(
                    context.endpoint_id, root['resource_id']
                ),
                generation=root['generation'],
                items=service_targets,
                next_cursor=None,
                total_count=len(service_targets),
            ).to_dict()
        describe_engine_contract = getattr(
            binding.instance, 'engine_contract_descriptor', None
        )
        engine_contracts = (
            describe_engine_contract()
            if callable(describe_engine_contract) else {
                'schema': 'cdeadmin.engine-contract-activation.v1',
                'state': 'blocked',
                'dialect': {
                    'state': 'blocked',
                    'reason': 'provider_exact_dialect_contract_absent',
                },
                'metrics': {
                    'state': 'blocked',
                    'reason': 'provider_exact_metrics_contract_absent',
                },
            }
        )
        route_catalog = self.endpoint_service.route_catalog(server)
        endpoint_display_name = getattr(
            server, 'name', root.get('display_name', 'Endpoint')
        )
        from pgadmin.cdeadmin.visual_admin.navigation_design import navigation_design
        native_navigation = navigation_design(
            root.get('engine_id') or (visual_admin or {}).get('engine_id'),
            context.profile_id)
        return {
            'native_navigation': native_navigation,
            'endpoint': {
                'endpoint_id': context.endpoint_id,
                'display_name': endpoint_display_name,
                'mode': context.mode,
                'experience_family': context.experience_family,
                'provider_id': context.provider_id,
                'provider_version': context.provider_version,
                'profile_id': context.profile_id,
                'profile_version': context.profile_version,
                'runtime_verification_state': (
                    context.runtime_verification_state
                ),
                'verified_runtime_family': (
                    context.verified_runtime_family
                ),
                'verified_runtime_version': (
                    context.verified_runtime_version
                ),
                'route_management_available': bool(
                    getattr(
                        getattr(server, 'endpoint_profile', None),
                        'provider_version', None,
                    )
                ),
            },
            'endpoint_registration': {
                'display_name': endpoint_display_name,
                'is_password_saved': bool(
                    getattr(server, 'save_password', False)
                ),
                'forms': route_catalog['server_forms'],
                'primary_route': (
                    route_catalog['routes'][0]
                    if route_catalog['routes'] else None
                ),
            },
            'languages': editor_languages(self.studio_service.languages(context)),
            'engine_contracts': engine_contracts,
            'database_targets': self.endpoint_service.database_catalog(
                server
            ),
            'resource_page': page,
            'visual_admin': visual_admin,
            'grid_workspace': workspace_grid_contract(
                context, binding.instance, visual_admin,
            ),
            'operational_workspace': (
                build_operational_workspace(
                    visual_admin, page.get('items', [])
                ) if visual_admin is not None else None
            ),
            'semantic_models': (
                {
                    'capabilities': self._semantic_capabilities(
                        binding.instance
                    ),
                    'items': self.semantic_model_service.list(
                        self._principal_id(server), context.endpoint_id
                    ),
                    'delivery': self.report_delivery_service.catalog()
                    if self.report_delivery_service is not None else {
                        'manual_delivery': False, 'profiles': [],
                        'automatic_scheduling': False,
                    },
                    'scheduler': self.report_scheduler_service.catalog()
                    if self.report_scheduler_service is not None else {
                        'automatic_scheduling': False,
                    },
                    'delegations': self.report_scheduler_service.list_grants(
                        self._principal_id(server), context.endpoint_id
                    ) if self.report_scheduler_service is not None else [],
                } if self.semantic_model_service is not None else {
                    'capabilities': {'designer': False}, 'items': [],
                }
            ),
        }

    def _service_workspace_targets(
        self, context, root, visual_admin, server, database_target_id,
        focused_operation_id,
    ):
        """Build attachment-free targets for provider service tasks."""
        if focused_operation_id is None:
            return None
        if not isinstance(focused_operation_id, str) or not (
                focused_operation_id.strip()):
            raise ProviderWorkspaceError(
                'focused provider operation identity is invalid'
            )
        operation_id = focused_operation_id.strip()
        operation = None
        if isinstance(visual_admin, dict):
            for descriptor in visual_admin.get('objects', []):
                if descriptor.get('resource_kind') != 'database':
                    continue
                operation = next((
                    item for item in descriptor.get('operations', [])
                    if item.get('operation_id') == operation_id
                ), None)
                if operation is not None:
                    break
        if operation is None:
            raise ProviderWorkspaceError(
                'focused provider operation is unavailable'
            )
        if operation.get('workspace_scope') != 'server_service':
            return None
        if (operation.get('target_required') is False and
                database_target_id in (Ellipsis, None, '')):
            # The task owns its explicit server-side target field (for
            # example a recovery shadow). Do not fabricate or attach to a
            # registered database just to render that form.
            return ()
        if not isinstance(database_target_id, str) or not database_target_id:
            raise ProviderWorkspaceError(
                'provider service operation requires a database target'
            )
        catalog = self.endpoint_service.database_catalog(server)
        targets = catalog.get('targets', []) if isinstance(
            catalog, dict
        ) else []
        target = next((
            item for item in targets
            if item.get('target_id') == database_target_id
        ), None)
        if target is None:
            raise ProviderWorkspaceError(
                'provider service database target is unavailable'
            )
        display_name = target['display_name']
        return ({
            'identity': copy.deepcopy(root['identity']),
            'endpoint_id': context.endpoint_id,
            'resource_id': f'database-service-target:{database_target_id}',
            'identity_kind': 'cdeadmin-database-target-id',
            'resource_kind': 'database',
            'model_family': root['model_family'],
            'display_name': display_name,
            'parent_resource_id': root['resource_id'],
            'display_path': [root['display_name'], display_name],
            'authority_path': ['database', display_name],
            'is_virtual': True,
            'generation': root['generation'],
            'capability_ids': [],
            'extensions': {'cdeadmin': {
                'database_target_id': database_target_id,
                'service_scope_only': True,
                'focused_operation_id': operation_id,
            }},
        },)

    def database_target_action(self, server, action, request):
        """Manage server-owned database attachments and refresh resources."""
        request = request or {}
        if not isinstance(request, dict):
            raise ProviderWorkspaceError(
                'database target request must be an object'
            )
        if action == 'database_target_list':
            return self.endpoint_service.database_catalog(server)
        if action == 'database_target_transfer_catalog':
            from ..endpoints.firebird_registration import catalog
            return catalog(self.endpoint_service, server, request.get('target_id'))
        if action == 'database_target_transfer':
            from ..endpoints.firebird_registration import transfer
            return transfer(self.endpoint_service, server, request)
        if action == 'database_target_attach':
            result = self.endpoint_service.attach_database(server, request)
        elif action == 'database_target_activate':
            result = self.endpoint_service.activate_database(
                server, request.get('target_id'), request
            )
        elif action == 'database_target_update':
            result = self.endpoint_service.update_database_target(
                server, request.get('target_id'), request
            )
        elif action == 'database_target_disconnect':
            result = self.endpoint_service.disconnect_database(server)
        elif action == 'database_target_delete':
            result = self.endpoint_service.delete_database_target(
                server, request.get('target_id'), request
            )
        else:
            raise ProviderWorkspaceError(
                'database target action is unavailable'
            )
        context, _endpoint, _root = self.endpoint_service.workspace(server)
        self.resource_service.invalidate(context)
        return result

    def _semantic_capabilities(self, provider):
        capabilities = self.semantic_model_service.capabilities(provider)
        capabilities['scheduled_report_execution'] = bool(
            capabilities.get('execution_available') and
            self.report_scheduler_service is not None and
            self.report_scheduler_service.available
        )
        return capabilities

    def report_scheduler_action(self, server, action, request):
        """Apply authenticated owner actions to unattended report grants."""
        if self.report_scheduler_service is None:
            raise ProviderWorkspaceError(
                'report scheduler service is not initialized'
            )
        if not isinstance(request, dict):
            raise ProviderWorkspaceError(
                'report scheduler request must be an object'
            )
        endpoint = getattr(server, 'endpoint_profile', None)
        if endpoint is None:
            raise ProviderWorkspaceError(
                'report scheduler endpoint is unavailable'
            )
        user_id = self._principal_id(server)
        service = self.report_scheduler_service
        if action == 'report_scheduler_authorize':
            return service.authorize(
                server, request.get('model_id'), request.get('report_id'),
                request.get('expires_in_days', 30),
            )
        if action == 'report_scheduler_revoke':
            return service.revoke(
                user_id, endpoint.id, request.get('report_id')
            )
        if action == 'report_scheduler_list':
            return {'items': service.list_grants(
                user_id, endpoint.id
            )}
        if action == 'report_scheduler_occurrences':
            return {'items': service.occurrences(
                user_id, endpoint.id, request.get('report_id')
            )}
        if action == 'report_scheduler_cancel':
            return service.cancel(
                user_id, endpoint.id,
                request.get('occurrence_id'),
            )
        raise ProviderWorkspaceError(
            'report scheduler action is unavailable'
        )

    def deliver_result(self, server, request):
        """Deliver a bounded export under the authenticated endpoint owner."""
        if self.report_delivery_service is None:
            raise ProviderWorkspaceError(
                'report delivery service is not initialized'
            )
        if not isinstance(request, dict) or set(request) != {
                'request_key', 'result_id', 'format', 'profile_id', 'target'}:
            raise ProviderWorkspaceError('result delivery request is invalid')
        context, _endpoint, _root = self.endpoint_service.workspace(server)
        exported = self.result_service.export(
            request.get('result_id'), request.get('format'),
            endpoint_id=context.endpoint_id,
        )
        content = exported.pop('content')
        export_format = request.get('format')
        return self.report_delivery_service.deliver(
            self._principal_id(server), context.endpoint_id, {
                **request, 'content': content,
                'media_type': self._export_media_type(export_format),
                'filename': (
                    f"cdeadmin-result-{request.get('result_id')}."
                    f'{export_format}'
                ),
            }
        )

    def list_result_deliveries(self, server):
        """Return secret-free durable delivery occurrences for this owner."""
        if self.report_delivery_service is None:
            raise ProviderWorkspaceError(
                'report delivery service is not initialized'
            )
        context, _endpoint, _root = self.endpoint_service.workspace(server)
        return {'items': self.report_delivery_service.list(
            self._principal_id(server), context.endpoint_id
        )}

    def resource_page(self, server, request):
        """Return the next generation-bound root navigator page."""
        if not isinstance(request, dict):
            raise ProviderWorkspaceError(
                'resource page request must be an object'
            )
        if set(request).difference({
                'continuation', 'generation', 'database_target_id'}):
            raise ProviderWorkspaceError(
                'resource page request contains unsupported fields'
            )
        continuation = request.get('continuation')
        generation = request.get('generation')
        database_target_id = request.get('database_target_id', Ellipsis)
        if continuation is not None and not isinstance(continuation, str):
            raise ProviderWorkspaceError(
                'resource page continuation must be text'
            )
        if generation is not None and not isinstance(generation, str):
            raise ProviderWorkspaceError(
                'resource page generation must be text'
            )
        context, endpoint, root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id,
        )
        return self.resource_service.list_page(
            context, root, page_size=500, cursor=continuation,
            expected_generation=generation,
            provider_route=endpoint['route'],
        ).to_dict()

    def navigator_snapshot(self, server, database_target_id=Ellipsis):
        """Return the complete bounded resource set for one tree branch.

        Tree navigation is independently scoped per retained database.  It
        never changes the endpoint's active Data Studio database.
        """
        context, endpoint, root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id,
        )
        binding = self.endpoint_service.provider_registry.resolve(context)
        describe_admin = getattr(
            binding.instance, 'visual_admin_descriptor', None
        )
        page = self.resource_service.list_page(
            context, root, page_size=500,
            provider_route=endpoint['route'],
        ).to_dict()
        resources = list(page['items'])
        continuation = page.get('next_cursor')
        generation = page['generation']
        while continuation is not None:
            page = self.resource_service.list_page(
                context, root, page_size=500, cursor=continuation,
                expected_generation=generation,
                provider_route=endpoint['route'],
            ).to_dict()
            resources.extend(page['items'])
            continuation = page.get('next_cursor')
        return {
            'generation': generation,
            'resources': resources,
            'visual_admin': (
                describe_admin() if callable(describe_admin) else None
            ),
        }

    def refresh_resources(self, server, request):
        """Refresh only this endpoint's resource generation."""
        if not isinstance(request, dict) or set(request).difference({
                'generation', 'database_target_id'}):
            raise ProviderWorkspaceError(
                'resource refresh request is invalid'
            )
        generation = request.get('generation')
        database_target_id = request.get('database_target_id', Ellipsis)
        if not isinstance(generation, str) or not generation:
            raise ProviderWorkspaceError(
                'resource refresh generation is required'
            )
        context, endpoint, root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id,
        )
        # Verify the caller's generation before invalidating. A stale browser
        # must reopen or reconcile instead of refreshing a newer tree.
        self.resource_service.list_page(
            context, root, page_size=1,
            expected_generation=generation,
            provider_route=endpoint['route'],
        )
        self.resource_service.invalidate(context)
        return self.resource_service.list_page(
            context, root, page_size=500,
            provider_route=endpoint['route'],
        ).to_dict()

    def mariadb_server_catalog(self, server, request):
        from ..providers.mysql_family.provider import MariaDBPilotProvider
        from .firebird_catalog_export import build_export, MAX_BYTES
        if not isinstance(request, dict) or set(request) - {'targets', 'include_system'}:
            raise ProviderWorkspaceError('Invalid MariaDB server catalog request')
        self._principal_id(server)
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) != 'mariadb-native':
            raise ProviderWorkspaceError('Select an owned native MariaDB server')
        targets, include_system = request.get('targets', []), request.get('include_system', True)
        if (not isinstance(targets, list) or len(targets) > 32 or any(not isinstance(value, str) or not value for value in targets) or
                len(targets) != len(set(targets)) or type(include_system) is not bool):
            raise ProviderWorkspaceError('Select at most 32 distinct registered database targets')
        registered = self.endpoint_service.database_catalog(server)['targets']
        if not set(targets) <= {item['target_id'] for item in registered}:
            raise ProviderWorkspaceError('Database expansion requires owned registered targets')
        context, endpoint, _root = self.endpoint_service.workspace(server)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if context.profile_id != 'mariadb-native' or not isinstance(provider, MariaDBPilotProvider):
            raise ProviderWorkspaceError('Select a native MariaDB endpoint')
        try:
            captured = provider.capture_server_catalog(endpoint['route'])
            result = build_export(captured['resources'], endpoint_id=str(context.endpoint_id),
                target_id='server:' + captured['server_uid'], generation=captured['generation'],
                include_system=include_system, refreshed=True, engine='mariadb')
            result.update(server_uid=captured['server_uid'], registered_targets=[{key: item.get(key)
                for key in ('target_id', 'database', 'display_name')} for item in registered], databases=[])
            for target in targets:
                database = self.mariadb_catalog(server, {'database_target_id': target, 'include_system': include_system})
                if database['server_uid'] != captured['server_uid']:
                    raise ValueError('Database capture reported another native server UID')
                result['databases'].append({'target_id': target, 'capture': database})
                if len(json.dumps(result, ensure_ascii=False).encode('utf8')) > MAX_BYTES:
                    raise ValueError('Server/database DDN collection exceeds 8 MiB; select a smaller batch')
            if len(json.dumps(result, ensure_ascii=False).encode('utf8')) > MAX_BYTES:
                raise ValueError('Server DDN collection exceeds 8 MiB')
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def _mariadb_catalog_context(self, server, target):
        from ..providers.mysql_family.provider import MariaDBPilotProvider
        self._principal_id(server)
        if (getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) != 'mariadb-native' or
                not isinstance(target, str) or not target):
            raise ProviderWorkspaceError('Select an owned native MariaDB database target')
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        matches = [item for item in self.endpoint_service.database_catalog(server)['targets']
                   if item['target_id'] == target]
        if (context.profile_id != 'mariadb-native' or len(matches) != 1 or not matches[0].get('database') or
                matches[0]['database'] != endpoint['route'].get('database')):
            raise ProviderWorkspaceError('Registered MariaDB database identity changed')
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, MariaDBPilotProvider):
            raise ProviderWorkspaceError('Select a native MariaDB endpoint')
        return context, endpoint, provider

    def mariadb_data_capture(self, server, request):
        if not isinstance(request, dict) or set(request) - {'database_target_id', 'resource_id', 'mode', 'row_limit', 'expected_server_uid'}:
            raise ProviderWorkspaceError('Invalid MariaDB relation data request')
        context, endpoint, provider = self._mariadb_catalog_context(server, request.get('database_target_id'))
        try:
            return provider.capture_data(endpoint['route'], request.get('resource_id'),
                endpoint_id=str(context.endpoint_id), target_id=request['database_target_id'], expected_server_uid=request.get('expected_server_uid'),
                mode=request.get('mode', 'sample'), row_limit=request.get('row_limit', 100))
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_native_metadata(self, server, request):
        from .firebird_catalog_import import read_catalog
        from .mariadb_sql_export import build_metadata
        if not isinstance(request, dict) or set(request) != {'database_target_id', 'source'}:
            raise ProviderWorkspaceError('Invalid native MariaDB metadata export request')
        try:
            target = request['database_target_id']
            context, endpoint, provider = self._mariadb_catalog_context(server, target)
            document = read_catalog(request['source'], engine='mariadb')
            if (document['provenance']['endpoint_id'] != context.endpoint_id or
                    document['provenance']['database_target_id'] != target):
                raise ValueError('Document belongs to another endpoint or database')
            metadata = build_metadata(document)
            if metadata['database'] != endpoint['route'].get('database'):
                raise ValueError('Native metadata names another registered database')
            if metadata.get('native_encoding_required'):
                metadata = provider.encode_native_metadata(endpoint['route'], metadata)
            return metadata
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_catalog(self, server, request, *, compare=False):
        from .firebird_catalog_export import build_export
        from .firebird_catalog_import import read_catalog, compare_catalogs
        if not isinstance(request, dict) or set(request) - {
                'database_target_id', 'include_system', 'resource_id', 'source'}:
            raise ProviderWorkspaceError('Invalid MariaDB catalog request')
        try:
            target = request.get('database_target_id')
            context, endpoint, provider = self._mariadb_catalog_context(server, target)
            include_system = request.get('include_system', False)
            if type(include_system) is not bool:
                raise ValueError('Invalid system-object selection')
            resource_id = request.get('resource_id')
            if resource_id is not None and (not isinstance(resource_id, str) or not resource_id):
                raise ValueError('Invalid native object selection')
            document = read_catalog(request.get('source'), engine='mariadb') if compare else None
            if document and (document['provenance']['endpoint_id'] != context.endpoint_id or
                             document['provenance']['database_target_id'] != target):
                raise ValueError('Document belongs to another endpoint or database')
            captured = provider.capture_catalog(endpoint['route'], include_system=include_system)
            result = build_export(captured['resources'], endpoint_id=context.endpoint_id,
                target_id=target, generation=captured['generation'], resource_id=resource_id,
                include_system=include_system, refreshed=True, engine='mariadb', native_model=compare)
            if compare:
                return compare_catalogs(document, result)
            result['server_uid'] = captured['resources'][0]['native']['catalog_row']['server_uid']
            result['objects'] = [{'resource_id': item['resource_id'], 'name': item['display_name'],
                'kind': item['resource_kind'], 'path': item['display_path']} for item in captured['resources']]
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def _mysql_catalog_context(self, server, target):
        from ..providers.mysql_family.provider import MySQLPilotProvider
        self._principal_id(server)
        if (getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) != 'mysql-native' or
                not isinstance(target, str) or not target):
            raise ProviderWorkspaceError('Select an owned native MySQL database target')
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        matches = [item for item in self.endpoint_service.database_catalog(server)['targets']
                   if item['target_id'] == target]
        if (context.profile_id != 'mysql-native' or len(matches) != 1 or not matches[0].get('database') or
                matches[0]['database'] != endpoint['route'].get('database')):
            raise ProviderWorkspaceError('Registered MySQL database identity changed')
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, MySQLPilotProvider):
            raise ProviderWorkspaceError('Select a native MySQL endpoint')
        return context, endpoint, provider

    def mysql_server_catalog(self, server, request):
        from ..providers.mysql_family.provider import MySQLPilotProvider
        from .firebird_catalog_export import build_export, MAX_BYTES
        if not isinstance(request, dict) or set(request) - {'targets', 'include_system'}:
            raise ProviderWorkspaceError('Invalid MySQL server catalog request')
        self._principal_id(server)
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) != 'mysql-native':
            raise ProviderWorkspaceError('Select an owned native MySQL server')
        targets, include_system = request.get('targets', []), request.get('include_system', True)
        if (not isinstance(targets, list) or len(targets) > 32 or any(not isinstance(value, str) or not value for value in targets) or
                len(targets) != len(set(targets)) or type(include_system) is not bool):
            raise ProviderWorkspaceError('Select at most 32 distinct registered database targets')
        registered = self.endpoint_service.database_catalog(server)['targets']
        if not set(targets) <= {item['target_id'] for item in registered}:
            raise ProviderWorkspaceError('Database expansion requires owned registered targets')
        context, endpoint, _root = self.endpoint_service.workspace(server)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if context.profile_id != 'mysql-native' or not isinstance(provider, MySQLPilotProvider):
            raise ProviderWorkspaceError('Select a native MySQL endpoint')
        try:
            captured = provider.capture_server_catalog(endpoint['route'])
            result = build_export(captured['resources'], endpoint_id=str(context.endpoint_id),
                target_id='server:' + captured['server_uuid'], generation=captured['generation'],
                include_system=include_system, refreshed=True, engine='mysql')
            result.update(server_uuid=captured['server_uuid'], registered_targets=[{key: item.get(key)
                for key in ('target_id', 'database', 'display_name')} for item in registered], databases=[])
            for target in targets:
                database = self.mysql_catalog(server, {'database_target_id': target, 'include_system': include_system})
                if database['server_uuid'] != captured['server_uuid']:
                    raise ValueError('Database capture reported another native server UUID')
                result['databases'].append({'target_id': target, 'capture': database})
                if len(json.dumps(result, ensure_ascii=False).encode('utf8')) > MAX_BYTES:
                    raise ValueError('Server/database DDN collection exceeds 8 MiB; select a smaller batch')
            if len(json.dumps(result, ensure_ascii=False).encode('utf8')) > MAX_BYTES:
                raise ValueError('Server DDN collection exceeds 8 MiB')
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def _mariadb_server_context(self, server):
        from ..providers.mariadb_family.provider import MariaDBPilotProvider
        self._principal_id(server)
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) != 'mariadb-native':
            raise ProviderWorkspaceError('Select an owned native MariaDB server')
        context, endpoint, _ = self.endpoint_service.workspace(server)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if context.profile_id != 'mariadb-native' or not isinstance(provider, MariaDBPilotProvider):
            raise ProviderWorkspaceError('Select a native MariaDB endpoint')
        return context, endpoint, provider

    def mariadb_server_plan(self, server, request):
        from .firebird_catalog_import import read_catalog
        from .firebird_catalog_export import build_export
        from .mariadb_server_plan import plan
        if not isinstance(request, dict) or set(request) != {'baseline', 'source'}:
            raise ProviderWorkspaceError('Server preview requires baseline and desired DDN')
        context, endpoint, provider = self._mariadb_server_context(server)
        try:
            baseline, desired = [read_catalog(request[key], engine='mariadb') for key in ('baseline', 'source')]
            if any(document['provenance']['endpoint_id'] != str(context.endpoint_id) for document in (baseline, desired)):
                raise ValueError('Server DDN belongs to another registered endpoint')
            acquired = provider.capture_server_catalog(endpoint['route'])
            live = build_export(acquired['resources'], endpoint_id=str(context.endpoint_id),
                target_id='server:' + acquired['server_uid'], generation=acquired['generation'],
                include_system=True, refreshed=True, engine='mariadb', native_model=True)
            result = plan(baseline, desired, live)
            result['endpoint_id'] = str(context.endpoint_id)
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_server_application(self, server, action, request):
        from dataclasses import asdict
        from .mariadb_server_apply import MariaDBServerApplications
        from .firebird_schema_plan import digest
        from .firebird_catalog_import import read_catalog
        from ..operations.store import JsonOperationStore
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid server application request')
        context, endpoint, provider = self._mariadb_server_context(server)
        provider._require('administer', 'resource')
        provider._require('execute')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Server application requires durable receipt storage')
        applications = MariaDBServerApplications(str(store.path) + '.mariadb-server-applications.json')
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'scope': 'mariadb-server'})
        try:
            if action == 'review':
                if set(request) != {'baseline', 'source', 'execution_sha256'}:
                    raise ValueError('Invalid server review request')
                preview = self.mariadb_server_plan(server, {key: value for key, value in request.items() if key != 'execution_sha256'})
                if preview['execution_sha256'] != request['execution_sha256']:
                    raise ValueError('Displayed native server plan changed; preview again')
                return applications.review(preview, read_catalog(request['baseline'], engine='mariadb'),
                    read_catalog(request['source'], engine='mariadb'), owner, binding)
            if action == 'receipts' and not request:
                return {'receipts': applications.recent(owner, binding)}
            if action == 'receipt' and set(request) == {'review_id'}:
                return applications.get(request['review_id'], owner, binding)
            if action != 'apply':
                raise ValueError('Invalid server application action')
            def execute(record, operation):
                fresh_context, fresh_endpoint, fresh_provider = self._mariadb_server_context(server)
                if digest({'context': asdict(fresh_context), 'route': fresh_endpoint['route'], 'scope': 'mariadb-server'}) != binding:
                    raise ValueError('Server registration changed before dispatch')
                result = fresh_provider.apply_server_operation(fresh_endpoint['route'], record, operation)
                if result['state'] != 'not_dispatched':
                    try:
                        self.resource_service.invalidate(fresh_context)
                    except Exception as error:
                        result['explorer_refresh_error_type'] = type(error).__name__
                return result
            return applications.apply(request, owner, binding, execute)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def _mysql_server_context(self, server):
        from ..providers.mysql_family.provider import MySQLPilotProvider
        self._principal_id(server)
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) != 'mysql-native':
            raise ProviderWorkspaceError('Select an owned native MySQL server')
        context, endpoint, _ = self.endpoint_service.workspace(server)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if context.profile_id != 'mysql-native' or not isinstance(provider, MySQLPilotProvider):
            raise ProviderWorkspaceError('Select a native MySQL endpoint')
        return context, endpoint, provider

    def mysql_server_plan(self, server, request):
        from .firebird_catalog_import import read_catalog
        from .firebird_catalog_export import build_export
        from .mysql_server_plan import plan
        if not isinstance(request, dict) or set(request) != {'baseline', 'source'}:
            raise ProviderWorkspaceError('Server preview requires baseline and desired DDN')
        context, endpoint, provider = self._mysql_server_context(server)
        try:
            baseline, desired = [read_catalog(request[key], engine='mysql') for key in ('baseline', 'source')]
            if any(document['provenance']['endpoint_id'] != str(context.endpoint_id) for document in (baseline, desired)):
                raise ValueError('Server DDN belongs to another registered endpoint')
            acquired = provider.capture_server_catalog(endpoint['route'])
            live = build_export(acquired['resources'], endpoint_id=str(context.endpoint_id),
                target_id='server:' + acquired['server_uuid'], generation=acquired['generation'],
                include_system=True, refreshed=True, engine='mysql', native_model=True)
            result = plan(baseline, desired, live)
            result['endpoint_id'] = str(context.endpoint_id)
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_server_application(self, server, action, request):
        from dataclasses import asdict
        from .mysql_server_apply import MySQLServerApplications
        from .firebird_schema_plan import digest
        from .firebird_catalog_import import read_catalog
        from ..operations.store import JsonOperationStore
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid server application request')
        context, endpoint, provider = self._mysql_server_context(server)
        provider._require('administer', 'resource')
        provider._require('execute')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Server application requires durable receipt storage')
        applications = MySQLServerApplications(str(store.path) + '.mysql-server-applications.json')
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'scope': 'mysql-server'})
        try:
            if action == 'review':
                if set(request) != {'baseline', 'source', 'execution_sha256'}:
                    raise ValueError('Invalid server review request')
                preview = self.mysql_server_plan(server, {key: value for key, value in request.items() if key != 'execution_sha256'})
                if preview['execution_sha256'] != request['execution_sha256']:
                    raise ValueError('Displayed native server plan changed; preview again')
                return applications.review(preview, read_catalog(request['baseline'], engine='mysql'),
                    read_catalog(request['source'], engine='mysql'), owner, binding)
            if action == 'receipts' and not request:
                return {'receipts': applications.recent(owner, binding)}
            if action == 'receipt' and set(request) == {'review_id'}:
                return applications.get(request['review_id'], owner, binding)
            if action != 'apply':
                raise ValueError('Invalid server application action')
            def execute(record, operation):
                fresh_context, fresh_endpoint, fresh_provider = self._mysql_server_context(server)
                if digest({'context': asdict(fresh_context), 'route': fresh_endpoint['route'], 'scope': 'mysql-server'}) != binding:
                    raise ValueError('Server registration changed before dispatch')
                result = fresh_provider.apply_server_operation(fresh_endpoint['route'], record, operation)
                if result['state'] != 'not_dispatched':
                    try:
                        self.resource_service.invalidate(fresh_context)
                    except Exception as error:
                        result['explorer_refresh_error_type'] = type(error).__name__
                return result
            return applications.apply(request, owner, binding, execute)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_schema_plan(self, server, request, *, validate=False):
        from .firebird_catalog_export import build_export
        from .firebird_catalog_import import read_catalog
        from .mysql_schema_plan import plan
        if not isinstance(request, dict) or set(request) != {'database_target_id', 'baseline', 'source'}:
            raise ProviderWorkspaceError('Native MySQL preview requires baseline and desired DDN')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mysql_catalog_context(server, target)
        try:
            baseline = read_catalog(request['baseline'], engine='mysql')
            desired = read_catalog(request['source'], engine='mysql')
            for document in (baseline, desired):
                if (document['provenance']['endpoint_id'] != str(context.endpoint_id) or
                        document['provenance']['database_target_id'] != target):
                    raise ValueError('Document belongs to another endpoint or registered database')
            captured = provider.capture_catalog(endpoint['route'])
            live = build_export(captured['resources'], endpoint_id=str(context.endpoint_id), target_id=target,
                generation=captured['generation'], refreshed=True, engine='mysql', native_model=True)
            result = plan(baseline, desired, live)
            if validate:
                result.update(provider.validate_schema_plan(endpoint['route'], result))
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_relational_review(self, server, request):
        from .firebird_relational_review import handoff
        if (not isinstance(request, dict) or not {'database_target_id', 'original', 'snapshot'} <= set(request) or
                set(request) - {'database_target_id', 'original', 'snapshot', 'allow_new_columns', 'allow_column_renames', 'allow_foreign_keys'} or
                type(request.get('allow_new_columns', False)) is not bool or
                type(request.get('allow_column_renames', False)) is not bool or
                type(request.get('allow_foreign_keys', False)) is not bool):
            raise ProviderWorkspaceError('Original and edited MySQL relational designs and boolean column admission are required')
        catalog = self.mysql_catalog(server, {'database_target_id': request['database_target_id']})
        try:
            return handoff(catalog['snapshot'], request['original'], request['snapshot'], engine='mysql',
                           allow_new_columns=request.get('allow_new_columns', False),
                           allow_column_renames=request.get('allow_column_renames', False),
                           allow_foreign_keys=request.get('allow_foreign_keys', False))
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_schema_application(self, server, action, request):
        from dataclasses import asdict
        from .mysql_schema_apply import MySQLSchemaApplications
        from .firebird_schema_plan import digest
        from .firebird_catalog_import import read_catalog
        from ..operations.store import JsonOperationStore
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid MySQL application request')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mysql_catalog_context(server, target)
        provider._require('administer', 'resource')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Native application requires durable receipt storage')
        applications = MySQLSchemaApplications(str(store.path) + '.mysql-schema-applications.json')
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': target})
        try:
            if action == 'mysql_schema_review':
                if set(request) != {'baseline', 'source', 'execution_sha256', 'database_target_id'}:
                    raise ValueError('Invalid MySQL schema review request')
                preview = self.mysql_schema_plan(server, {key: value for key, value in request.items()
                    if key != 'execution_sha256'}, validate=True)
                if preview['execution_sha256'] != request['execution_sha256']:
                    raise ValueError('The displayed plan changed; preview native changes again')
                return applications.review(preview, read_catalog(request['baseline'], engine='mysql'),
                    read_catalog(request['source'], engine='mysql'), owner, binding, target)
            if action == 'mysql_schema_receipt':
                if set(request) != {'review_id', 'database_target_id'} or not isinstance(request['review_id'], str):
                    raise ValueError('Invalid MySQL schema receipt request')
                return applications.get(request['review_id'], owner, binding)
            if action != 'mysql_schema_apply':
                raise ValueError('Unknown MySQL schema application action')
            def execute(record):
                result = provider.apply_schema_review(endpoint['route'], record)
                if result['state'] != 'not_dispatched':
                    try:
                        self.resource_service.invalidate(context)
                        result['explorer_invalidated'] = True
                    except Exception as error:
                        result.update(explorer_invalidated=False, refresh_error_type=type(error).__name__)
                return result
            return applications.apply({key: value for key, value in request.items()
                if key != 'database_target_id'}, owner, binding, execute)
        except (ValueError, RecursionError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_schema_plan(self, server, request, *, validate=False):
        from .firebird_catalog_export import build_export
        from .firebird_catalog_import import read_catalog
        from .mariadb_schema_plan import plan
        if not isinstance(request, dict) or set(request) != {'database_target_id', 'baseline', 'source'}:
            raise ProviderWorkspaceError('Native MariaDB preview requires baseline and desired DDN')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mariadb_catalog_context(server, target)
        try:
            baseline = read_catalog(request['baseline'], engine='mariadb')
            desired = read_catalog(request['source'], engine='mariadb')
            for document in (baseline, desired):
                if (document['provenance']['endpoint_id'] != str(context.endpoint_id) or
                        document['provenance']['database_target_id'] != target):
                    raise ValueError('Document belongs to another endpoint or registered database')
            captured = provider.capture_catalog(endpoint['route'])
            live = build_export(captured['resources'], endpoint_id=str(context.endpoint_id), target_id=target,
                generation=captured['generation'], refreshed=True, engine='mariadb', native_model=True)
            result = plan(baseline, desired, live)
            if validate:
                result.update(provider.validate_schema_plan(endpoint['route'], result))
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_schema_application(self, server, action, request):
        from dataclasses import asdict
        from .mariadb_schema_apply import MariaDBSchemaApplications
        from .firebird_schema_plan import digest
        from .firebird_catalog_import import read_catalog
        from ..operations.store import JsonOperationStore
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid MariaDB application request')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mariadb_catalog_context(server, target)
        provider._require('administer', 'resource')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Native application requires durable receipt storage')
        applications = MariaDBSchemaApplications(str(store.path) + '.mariadb-schema-applications.json')
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': target})
        try:
            if action == 'mariadb_schema_review':
                if set(request) != {'baseline', 'source', 'execution_sha256', 'database_target_id'}:
                    raise ValueError('Invalid MariaDB schema review request')
                preview = self.mariadb_schema_plan(server, {key: value for key, value in request.items()
                    if key != 'execution_sha256'}, validate=True)
                if preview['execution_sha256'] != request['execution_sha256']:
                    raise ValueError('The displayed plan changed; preview native changes again')
                return applications.review(preview, read_catalog(request['baseline'], engine='mariadb'),
                    read_catalog(request['source'], engine='mariadb'), owner, binding, target)
            if action == 'mariadb_schema_receipt':
                if set(request) != {'review_id', 'database_target_id'} or not isinstance(request['review_id'], str):
                    raise ValueError('Invalid MariaDB schema receipt request')
                return applications.get(request['review_id'], owner, binding)
            if action != 'mariadb_schema_apply':
                raise ValueError('Unknown MariaDB schema application action')
            def execute(record):
                result = provider.apply_schema_review(endpoint['route'], record)
                if result['state'] != 'not_dispatched':
                    try:
                        self.resource_service.invalidate(context)
                        result['explorer_invalidated'] = True
                    except Exception as error:
                        result.update(explorer_invalidated=False, refresh_error_type=type(error).__name__)
                return result
            if request.get('maintenance_window_confirmed') is not True:
                raise ValueError('Confirm an exclusive DDL maintenance window before applying')
            return applications.apply({key: value for key, value in request.items()
                if key not in {'database_target_id', 'maintenance_window_confirmed'}}, owner, binding, execute)
        except (ValueError, RecursionError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_relational_review(self, server, request):
        from .firebird_relational_review import handoff
        if (not isinstance(request, dict) or not {'database_target_id', 'original', 'snapshot'} <= set(request) or
                set(request) - {'database_target_id', 'original', 'snapshot', 'allow_new_columns', 'allow_column_renames', 'allow_foreign_keys', 'allow_temporal_history'} or
                type(request.get('allow_new_columns', False)) is not bool or
                type(request.get('allow_column_renames', False)) is not bool or
                type(request.get('allow_foreign_keys', False)) is not bool or
                type(request.get('allow_temporal_history', False)) is not bool):
            raise ProviderWorkspaceError('Original and edited MariaDB relational designs and boolean column admission are required')
        catalog = self.mariadb_catalog(server, {'database_target_id': request['database_target_id']})
        try:
            return handoff(catalog['snapshot'], request['original'], request['snapshot'], engine='mariadb',
                           allow_new_columns=request.get('allow_new_columns', False),
                           allow_column_renames=request.get('allow_column_renames', False),
                           allow_foreign_keys=request.get('allow_foreign_keys', False),
                allow_temporal_history=request.get('allow_temporal_history', False))
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_test_data(self, server, request):
        from .firebird_catalog_export import build_export
        from .mariadb_test_data import generate, template
        if not isinstance(request, dict) or set(request) - {'database_target_id', 'recipe'}:
            raise ProviderWorkspaceError('Invalid MariaDB test-data request')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mariadb_catalog_context(server, target)
        try:
            captured = provider.capture_catalog(endpoint['route'])
            model = build_export(captured['resources'], endpoint_id=str(context.endpoint_id), target_id=target,
                generation=captured['generation'], refreshed=True, engine='mariadb', native_model=True)
            return generate(model, request['recipe']) if 'recipe' in request else template(model)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_recipe_asset(self, server, action, request):
        from .assets import ProjectAssetError
        from .mysql_recipe_assets import MySQLRecipeAssets
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid MariaDB recipe request')
        context, _endpoint, _provider = self._mariadb_catalog_context(server, request.get('database_target_id'))
        assets = self.firebird_design_assets.assets
        try:
            if action == 'save':
                # Validate native identities and generators without executing the script.
                self.mariadb_test_data(server, {'database_target_id': request.get('database_target_id'), 'recipe': request.get('recipe')})
            return MySQLRecipeAssets(assets, engine='mariadb').apply(self._principal_id(server), {
                'endpoint_id': str(context.endpoint_id), 'database_target_id': request['database_target_id']}, action, request)
        except ProjectAssetError as error:
            raise ProviderWorkspaceError(str(error)) from None
        except (IntegrityError, StaleDataError):
            assets.repository.rollback()
            raise ProviderWorkspaceError('Recipe changed concurrently; reload before saving') from None

    def mariadb_data_plan(self, server, request):
        from .mariadb_data_import import preview
        from .firebird_catalog_export import build_export
        if not isinstance(request, dict) or set(request) - {'database_target_id', 'source', 'table', 'allow_nontransactional'}:
            raise ProviderWorkspaceError('Invalid native data import request')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mariadb_catalog_context(server, target)
        provider._require('data_write', 'resource')
        try:
            acquired = provider.capture_catalog(endpoint['route'])
            live = build_export(acquired['resources'], endpoint_id=str(context.endpoint_id), target_id=target,
                generation=acquired['generation'], refreshed=True, engine='mariadb', native_model=True)
            return preview(request.get('source'), live, table=request.get('table'),
                allow_nontransactional=request.get('allow_nontransactional', False),
                node=getattr(self, 'ddn_node', 'node'))
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_data_application(self, server, action, request):
        from dataclasses import asdict
        from .mariadb_data_import import MariaDBDataApplications
        from .firebird_schema_plan import digest
        from ..operations.store import JsonOperationStore
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid native data application request')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mariadb_catalog_context(server, target)
        provider._require('data_write', 'resource')
        provider._require('execute')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Data imports require durable receipt storage')
        applications = MariaDBDataApplications(str(store.path) + '.mariadb-data-imports.json')
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': target})
        try:
            if action == 'review':
                if set(request) - {'database_target_id', 'source', 'table', 'allow_nontransactional', 'execution_sha256'}:
                    raise ValueError('Invalid native data review request')
                plan = self.mariadb_data_plan(server, {key: value for key, value in request.items() if key != 'execution_sha256'})
                if request.get('execution_sha256') != plan['execution_sha256']:
                    raise ValueError('Displayed data import changed; preview again')
                return applications.review(plan, owner, binding)
            if action == 'receipts' and set(request) == {'database_target_id'}:
                return {'receipts': applications.recent(owner, binding)}
            if action == 'receipt' and set(request) == {'database_target_id', 'review_id'}:
                return applications.get(request['review_id'], owner, binding)
            if action != 'apply':
                raise ValueError('Invalid native data application action')
            def execute(record):
                result = provider.apply_data_import(endpoint['route'], record)
                if result['state'] != 'not_dispatched':
                    try:
                        self.resource_service.invalidate(context)
                    except Exception as error:
                        result['explorer_refresh_error_type'] = type(error).__name__
                return result
            return applications.apply({key: value for key, value in request.items() if key != 'database_target_id'}, owner, binding, execute)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_recipe_asset(self, server, action, request):
        from .assets import ProjectAssetError
        from .mysql_recipe_assets import MySQLRecipeAssets
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid MySQL recipe request')
        context, _endpoint, _provider = self._mysql_catalog_context(server, request.get('database_target_id'))
        assets = self.firebird_design_assets.assets
        try:
            if action == 'save':
                # Validate native identities and generators without executing the script.
                self.mysql_test_data(server, {'database_target_id': request.get('database_target_id'), 'recipe': request.get('recipe')})
            return MySQLRecipeAssets(assets).apply(self._principal_id(server), {
                'endpoint_id': str(context.endpoint_id), 'database_target_id': request['database_target_id']}, action, request)
        except ProjectAssetError as error:
            raise ProviderWorkspaceError(str(error)) from None
        except (IntegrityError, StaleDataError):
            assets.repository.rollback()
            raise ProviderWorkspaceError('Recipe changed concurrently; reload before saving') from None

    def mysql_data_plan(self, server, request):
        from .mysql_data_import import preview
        from .firebird_catalog_export import build_export
        if not isinstance(request, dict) or set(request) - {'database_target_id', 'source', 'table', 'allow_nontransactional'}:
            raise ProviderWorkspaceError('Invalid native data import request')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mysql_catalog_context(server, target)
        provider._require('data_write', 'resource')
        try:
            acquired = provider.capture_catalog(endpoint['route'])
            live = build_export(acquired['resources'], endpoint_id=str(context.endpoint_id), target_id=target,
                generation=acquired['generation'], refreshed=True, engine='mysql', native_model=True)
            return preview(request.get('source'), live, table=request.get('table'),
                allow_nontransactional=request.get('allow_nontransactional', False),
                node=getattr(self, 'ddn_node', 'node'))
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_data_application(self, server, action, request):
        from dataclasses import asdict
        from .mysql_data_import import MySQLDataApplications
        from .firebird_schema_plan import digest
        from ..operations.store import JsonOperationStore
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid native data application request')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mysql_catalog_context(server, target)
        provider._require('data_write', 'resource')
        provider._require('execute')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Data imports require durable receipt storage')
        applications = MySQLDataApplications(str(store.path) + '.mysql-data-imports.json')
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': target})
        try:
            if action == 'review':
                if set(request) - {'database_target_id', 'source', 'table', 'allow_nontransactional', 'execution_sha256'}:
                    raise ValueError('Invalid native data review request')
                plan = self.mysql_data_plan(server, {key: value for key, value in request.items() if key != 'execution_sha256'})
                if request.get('execution_sha256') != plan['execution_sha256']:
                    raise ValueError('Displayed data import changed; preview again')
                return applications.review(plan, owner, binding)
            if action == 'receipts' and set(request) == {'database_target_id'}:
                return {'receipts': applications.recent(owner, binding)}
            if action == 'receipt' and set(request) == {'database_target_id', 'review_id'}:
                return applications.get(request['review_id'], owner, binding)
            if action != 'apply':
                raise ValueError('Invalid native data application action')
            def execute(record):
                result = provider.apply_data_import(endpoint['route'], record)
                if result['state'] != 'not_dispatched':
                    try:
                        self.resource_service.invalidate(context)
                    except Exception as error:
                        result['explorer_refresh_error_type'] = type(error).__name__
                return result
            return applications.apply({key: value for key, value in request.items() if key != 'database_target_id'}, owner, binding, execute)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_test_data(self, server, request):
        from .firebird_catalog_export import build_export
        from .mysql_test_data import generate, template
        if not isinstance(request, dict) or set(request) - {'database_target_id', 'recipe'}:
            raise ProviderWorkspaceError('Invalid MySQL test-data request')
        target = request.get('database_target_id')
        context, endpoint, provider = self._mysql_catalog_context(server, target)
        try:
            captured = provider.capture_catalog(endpoint['route'])
            model = build_export(captured['resources'], endpoint_id=str(context.endpoint_id), target_id=target,
                generation=captured['generation'], refreshed=True, engine='mysql', native_model=True)
            return generate(model, request['recipe']) if 'recipe' in request else template(model)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_data_capture(self, server, request):
        if not isinstance(request, dict) or set(request) - {'database_target_id', 'resource_id', 'mode', 'row_limit'}:
            raise ProviderWorkspaceError('Invalid MySQL relation data request')
        context, endpoint, provider = self._mysql_catalog_context(server, request.get('database_target_id'))
        try:
            return provider.capture_data(endpoint['route'], request.get('resource_id'),
                endpoint_id=str(context.endpoint_id), target_id=request['database_target_id'],
                mode=request.get('mode', 'sample'), row_limit=request.get('row_limit', 100))
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mariadb_design_asset(self, server, action, request):
        from .assets import ProjectAssetError
        from .firebird_design_assets import NativeDesignAssets
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid MariaDB design request')
        context, _endpoint, _provider = self._mariadb_catalog_context(server, request.get('database_target_id'))
        assets = self.firebird_design_assets.assets
        try:
            return NativeDesignAssets(assets, engine='mariadb').apply(self._principal_id(server), {
                'endpoint_id': str(context.endpoint_id),
                'database_target_id': request['database_target_id']}, action, request)
        except ProjectAssetError as error:
            raise ProviderWorkspaceError(str(error)) from None
        except (IntegrityError, StaleDataError):
            assets.repository.rollback()
            raise ProviderWorkspaceError('Design storage changed concurrently; reload before saving') from None

    def mysql_design_asset(self, server, action, request):
        from .assets import ProjectAssetError
        from .firebird_design_assets import NativeDesignAssets
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid MySQL design request')
        context, _endpoint, _provider = self._mysql_catalog_context(server, request.get('database_target_id'))
        assets = self.firebird_design_assets.assets
        try:
            return NativeDesignAssets(assets, engine='mysql').apply(self._principal_id(server), {
                'endpoint_id': str(context.endpoint_id),
                'database_target_id': request['database_target_id']}, action, request)
        except ProjectAssetError as error:
            raise ProviderWorkspaceError(str(error)) from None
        except (IntegrityError, StaleDataError):
            assets.repository.rollback()
            raise ProviderWorkspaceError('Design storage changed concurrently; reload before saving') from None

    def mysql_native_metadata(self, server, request):
        from .firebird_catalog_import import read_catalog
        from .mysql_sql_export import build_metadata
        if not isinstance(request, dict) or set(request) != {'database_target_id', 'source'}:
            raise ProviderWorkspaceError('Invalid native MySQL metadata export request')
        try:
            target = request['database_target_id']
            context, endpoint, provider = self._mysql_catalog_context(server, target)
            document = read_catalog(request['source'], engine='mysql')
            if (document['provenance']['endpoint_id'] != context.endpoint_id or
                    document['provenance']['database_target_id'] != target):
                raise ValueError('Document belongs to another endpoint or database')
            metadata = build_metadata(document)
            if metadata.get('native_encoding_required'):
                metadata = provider.encode_native_metadata(endpoint['route'], metadata)
            return metadata
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_catalog(self, server, request, *, compare=False):
        from .firebird_catalog_export import build_export
        from .firebird_catalog_import import read_catalog, compare_catalogs
        if not isinstance(request, dict) or set(request) - {
                'database_target_id', 'include_system', 'resource_id', 'source'}:
            raise ProviderWorkspaceError('Invalid MySQL catalog request')
        try:
            target = request.get('database_target_id')
            context, endpoint, provider = self._mysql_catalog_context(server, target)
            include_system = request.get('include_system', False)
            if type(include_system) is not bool:
                raise ValueError('Invalid system-object selection')
            resource_id = request.get('resource_id')
            if resource_id is not None and (not isinstance(resource_id, str) or not resource_id):
                raise ValueError('Invalid native object selection')
            document = read_catalog(request.get('source'), engine='mysql') if compare else None
            if document and (document['provenance']['endpoint_id'] != context.endpoint_id or
                             document['provenance']['database_target_id'] != target):
                raise ValueError('Document belongs to another endpoint or database')
            captured = provider.capture_catalog(endpoint['route'], include_system=include_system)
            result = build_export(captured['resources'], endpoint_id=context.endpoint_id,
                target_id=target, generation=captured['generation'], resource_id=resource_id,
                include_system=include_system, refreshed=True, engine='mysql', native_model=compare)
            if compare:
                return compare_catalogs(document, result)
            result['server_uuid'] = captured['resources'][0]['native']['catalog_row']['server_uuid']
            result['objects'] = [{'resource_id': item['resource_id'], 'name': item['display_name'],
                'kind': item['resource_kind'], 'path': item['display_path']} for item in captured['resources']]
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def postgresql_catalog(self, server, request, *, compare=False, plan=False):
        from ..providers.postgresql.provider import PostgreSQLProvider
        from ..providers.postgresql.connection_target import database_oid
        from .firebird_catalog_export import build_export
        from .firebird_catalog_import import read_catalog, compare_catalogs
        if not isinstance(request, dict) or set(request) - {
                'database_target_id', 'include_system', 'resource_id', 'source', 'baseline'}:
            raise ProviderWorkspaceError('Invalid PostgreSQL catalog request')
        try:
            target = request.get('database_target_id')
            if database_oid(target) is None:
                raise ValueError('Select an explicit PostgreSQL database')
            include_system = request.get('include_system', False)
            if type(include_system) is not bool:
                raise ValueError('Invalid system-object selection')
            resource_id = request.get('resource_id')
            if resource_id is not None and (not isinstance(resource_id, str) or not resource_id):
                raise ValueError('Invalid native object selection')
            document = read_catalog(request.get('source'), engine='postgresql') if compare or plan else None
            baseline = read_catalog(request.get('baseline'), engine='postgresql') if plan else None
            context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
            provider = self.endpoint_service.provider_registry.resolve(context).instance
            if not isinstance(provider, PostgreSQLProvider):
                raise ValueError('Select a native PostgreSQL endpoint')
            for imported in (document, baseline):
                if imported and (imported['provenance']['endpoint_id'] != context.endpoint_id or
                                 imported['provenance']['database_target_id'] != target):
                    raise ValueError('Document belongs to another endpoint or database')
            captured = provider.capture_catalog(endpoint['route'], include_system=include_system)
            result = build_export(captured['resources'], endpoint_id=context.endpoint_id,
                target_id=target, generation=captured['generation'], resource_id=None if plan else resource_id,
                include_system=include_system, refreshed=True, engine='postgresql', native_model=compare or plan)
            if plan:
                from .postgresql_schema_plan import build_plan
                return build_plan(baseline, document, result)
            if compare:
                return compare_catalogs(document, result)
            result['objects'] = [{'resource_id': item['resource_id'], 'name': item['display_name'],
                                  'kind': item['resource_kind'], 'path': item['display_path']}
                                 for item in captured['resources']]
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def native_recipe_asset(self, server, engine, action, request):
        from .assets import ProjectAssetError
        from .mysql_recipe_assets import MySQLRecipeAssets
        from ..providers.postgresql.provider import PostgreSQLProvider
        from ..providers.duckdb.provider import DuckDBPilotProvider
        from ..providers.sqlite.provider import SQLiteProvider
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        providers = {'postgresql': PostgreSQLProvider, 'duckdb': DuckDBPilotProvider,
                     'sqlite': SQLiteProvider}
        if engine not in providers or not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid native recipe request')
        target = request.get('database_target_id')
        if not isinstance(target, str) or not target:
            raise ProviderWorkspaceError('Select an explicit native database')
        context, _endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, providers[engine]):
            raise ProviderWorkspaceError('Recipe engine differs from the native endpoint')
        assets = self.firebird_design_assets.assets
        try:
            if action == 'save':
                getattr(self, engine + '_test_data')(server, {
                    'database_target_id': target, 'recipe': request.get('recipe')})
            return MySQLRecipeAssets(assets, engine=engine).apply(self._principal_id(server), {
                'endpoint_id': str(context.endpoint_id), 'database_target_id': target}, action, request)
        except ProjectAssetError as error:
            raise ProviderWorkspaceError(str(error)) from None
        except (IntegrityError, StaleDataError):
            assets.repository.rollback()
            raise ProviderWorkspaceError('Recipe changed concurrently; reload before saving') from None

    def _native_data_context(self, server, engine, request):
        from ..providers.postgresql.provider import PostgreSQLProvider
        from ..providers.duckdb.provider import DuckDBPilotProvider
        from ..providers.sqlite.provider import SQLiteProvider
        providers = {'postgresql': PostgreSQLProvider, 'duckdb': DuckDBPilotProvider, 'sqlite': SQLiteProvider}
        if engine not in providers or not isinstance(request, dict) or not isinstance(request.get('database_target_id'), str) or not request['database_target_id']:
            raise ProviderWorkspaceError('Select an explicit native data destination')
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=request['database_target_id'])
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, providers[engine]):
            raise ProviderWorkspaceError('Data import engine differs from the selected endpoint')
        provider.permissions.require('data_write', 'resource')
        provider.permissions.require('execute')
        return context, endpoint, provider

    def native_data_plan(self, server, engine, request):
        from .native_data_import import preview
        context, endpoint, provider = self._native_data_context(server, engine, request)
        if set(request) != {'database_target_id', 'source', 'resource_id'}:
            raise ProviderWorkspaceError('Invalid native data preview request')
        try:
            return preview(provider, endpoint['route'], engine, request['source'], request['resource_id'],
                endpoint_id=str(context.endpoint_id), target_id=request['database_target_id'], node=getattr(self, 'ddn_node', 'node'))
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def native_data_application(self, server, engine, action, request):
        from dataclasses import asdict
        from .native_data_import import NativeDataApplications, apply
        from .firebird_schema_plan import digest
        from ..operations.store import JsonOperationStore
        context, endpoint, provider = self._native_data_context(server, engine, request)
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Data imports require durable operation storage')
        applications = NativeDataApplications(str(store.path) + '.' + engine + '-data-imports.json', engine)
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': request['database_target_id']})
        try:
            if action == 'review':
                if set(request) != {'database_target_id', 'source', 'resource_id', 'execution_sha256'}:
                    raise ValueError('Invalid native data review request')
                plan = self.native_data_plan(server, engine, {key: value for key, value in request.items() if key != 'execution_sha256'})
                if request['execution_sha256'] != plan['execution_sha256']:
                    raise ValueError('Displayed native data import changed; preview again')
                return applications.review(plan, owner, binding)
            if action == 'receipts' and set(request) == {'database_target_id'}:
                return {'receipts': applications.recent(owner, binding)}
            if action == 'receipt' and set(request) == {'database_target_id', 'review_id'}:
                return applications.get(request['review_id'], owner, binding)
            if action != 'apply': raise ValueError('Invalid native data application action')
            def execute(record):
                outcome = apply(provider, endpoint['route'], engine, record)
                if outcome['state'] != 'not_dispatched':
                    try: self.resource_service.invalidate(context)
                    except Exception as error: outcome['explorer_refresh_error_type'] = type(error).__name__
                return outcome
            return applications.apply({key: value for key, value in request.items() if key != 'database_target_id'}, owner, binding, execute)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def postgresql_test_data(self, server, request):
        from ..providers.postgresql.provider import PostgreSQLProvider
        from ..providers.postgresql.connection_target import database_oid
        from .firebird_catalog_export import build_export
        from .postgresql_test_data import generate, template
        if not isinstance(request, dict) or set(request) - {'database_target_id', 'recipe'}:
            raise ProviderWorkspaceError('Invalid PostgreSQL test-data request')
        try:
            target = request.get('database_target_id')
            if database_oid(target) is None:
                raise ValueError('Select an explicit PostgreSQL database')
            context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
            provider = self.endpoint_service.provider_registry.resolve(context).instance
            if not isinstance(provider, PostgreSQLProvider):
                raise ValueError('Select a native PostgreSQL endpoint')
            captured = provider.capture_catalog(endpoint['route'])
            model = build_export(captured['resources'], endpoint_id=context.endpoint_id,
                target_id=target, generation=captured['generation'], engine='postgresql', native_model=True)
            return generate(model, request['recipe']) if 'recipe' in request else template(model)
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def postgresql_data_capture(self, server, request):
        from ..providers.postgresql.provider import PostgreSQLProvider
        from ..providers.postgresql.connection_target import database_oid
        from ..providers.postgresql.data_capture import capture
        if not isinstance(request, dict) or set(request) != {'database_target_id', 'resource_id', 'mode', 'row_limit'}:
            raise ProviderWorkspaceError('Invalid PostgreSQL data capture request')
        try:
            target = request['database_target_id']
            if database_oid(target) is None:
                raise ValueError('Select an explicit PostgreSQL database')
            context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
            provider = self.endpoint_service.provider_registry.resolve(context).instance
            if not isinstance(provider, PostgreSQLProvider):
                raise ValueError('Select a native PostgreSQL endpoint')
            return capture(provider, endpoint['route'], context.endpoint_id, request['resource_id'],
                           mode=request['mode'], row_limit=request['row_limit'])
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def postgresql_continuity(self, server, operation, request):
        from .postgresql_continuity_service import action
        from ..providers.postgresql.continuity import ContinuityError
        try:
            return action(self, server, operation, request)
        except ContinuityError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def mysql_clone(self, server, operation, request):
        from .mysql_clone_service import action
        from ..providers.mysql_family.mysql_clone import CloneError
        try:return action(self,server,operation,request)
        except CloneError as error:raise ProviderWorkspaceError(str(error)) from None

    def postgresql_server_catalog(self, server, request):
        from ..providers.postgresql.provider import PostgreSQLProvider
        from ..providers.postgresql.server_catalog import inventory, bundle, export_inventory
        if not isinstance(request, dict) or set(request) - {'database_ids', 'include_system'}:
            raise ProviderWorkspaceError('Invalid PostgreSQL server catalog request')
        if type(request.get('include_system', False)) is not bool:
            raise ProviderWorkspaceError('PostgreSQL system-object inclusion must be boolean')
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=None)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, PostgreSQLProvider):
            raise ProviderWorkspaceError('Select a native PostgreSQL server')
        try:
            if 'database_ids' not in request:
                result = inventory(provider, endpoint['route'])
                result['document'] = export_inventory(result, context.endpoint_id, endpoint['route']['server_id'],
                    include_system=request.get('include_system', False))
                return result
            return bundle(provider, endpoint['route'], context.endpoint_id, request['database_ids'],
                          include_system=request.get('include_system', False))
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def postgresql_schema_application(self, server, action, request):
        from dataclasses import asdict
        from .postgresql_schema_apply import PostgreSQLSchemaApplications
        from .firebird_schema_plan import digest
        from .firebird_catalog_import import read_catalog
        from ..operations.store import JsonOperationStore
        from ..providers.postgresql.provider import PostgreSQLProvider
        from ..providers.postgresql.schema_application import apply_review
        from ..providers.postgresql.connection_target import database_oid
        if not isinstance(request, dict) or database_oid(request.get('database_target_id')) is None:
            raise ProviderWorkspaceError('Select an explicit PostgreSQL database target')
        target = request['database_target_id']
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, PostgreSQLProvider):
            raise ProviderWorkspaceError('Native schema application requires PostgreSQL')
        provider.permissions.require('administer', 'resource')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Native application requires durable operation storage')
        applications = PostgreSQLSchemaApplications(str(store.path) + '.postgresql-schema-applications.json')
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': target})
        try:
            if action == 'postgresql_schema_review':
                if set(request) != {'baseline', 'source', 'execution_sha256', 'database_target_id', 'include_system'}:
                    raise ValueError('Invalid PostgreSQL schema review request')
                plan = self.postgresql_catalog(server, {key: value for key, value in request.items()
                    if key != 'execution_sha256'}, plan=True)
                if plan['execution_sha256'] != request['execution_sha256']:
                    raise ValueError('The displayed plan changed; preview native changes again')
                return applications.review(plan, read_catalog(request['baseline'], engine='postgresql'),
                    read_catalog(request['source'], engine='postgresql'), owner, binding, target)
            if action == 'postgresql_schema_receipt':
                if set(request) != {'review_id', 'database_target_id'} or not isinstance(request['review_id'], str):
                    raise ValueError('Invalid PostgreSQL schema receipt request')
                return applications.get(request['review_id'], owner, binding)
            if action != 'postgresql_schema_apply':
                raise ValueError('Unknown PostgreSQL schema application action')
            def execute(record):
                result = apply_review(provider, endpoint['route'], record)
                try:
                    self.resource_service.invalidate(context)
                    result['explorer_invalidated'] = True
                except Exception as error:
                    result['explorer_invalidated'] = False
                    result['refresh_error_type'] = type(error).__name__
                return result
            return applications.apply({key: value for key, value in request.items()
                if key != 'database_target_id'}, owner, binding, execute)
        except (ValueError, RecursionError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def postgresql_relational_review(self, server, request):
        from .firebird_relational_review import handoff
        if not isinstance(request, dict) or not {'original', 'snapshot'} <= request.keys():
            raise ProviderWorkspaceError('Original and edited relational designs are required')
        options = dict(request)
        original, snapshot = options.pop('original'), options.pop('snapshot')
        catalog = self.postgresql_catalog(server, options)
        try:
            return handoff(catalog['snapshot'], original, snapshot, engine='postgresql')
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def duckdb_catalog(self, server, request, *, compare=False):
        from .duckdb_catalog_service import catalog
        try:
            return catalog(self, server, request, compare=compare)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def sqlite_catalog(self, server, request, *, compare=False):
        from .sqlite_catalog_service import catalog
        try:
            return catalog(self, server, request, compare=compare)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def sqlite_data_capture(self, server, request):
        from .sqlite_catalog_service import data
        try:
            return data(self, server, request)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def sqlite_data_script(self, server, request):
        from .sqlite_catalog_service import data_script
        try:
            return data_script(self, server, request)
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def sqlite_test_data(self, server, request):
        from .sqlite_catalog_service import test_data
        try:
            return test_data(self, server, request)
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def sqlite_schema_plan(self, server, request):
        from .sqlite_catalog_service import schema_plan
        try:
            return schema_plan(self, server, request)
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def sqlite_schema_application(self, server, action, request):
        from dataclasses import asdict
        import os
        import stat
        from .sqlite_schema_apply import SQLiteSchemaApplications, apply_review
        from .firebird_catalog_import import read_catalog
        from .firebird_schema_plan import digest
        from ..operations.store import JsonOperationStore
        from ..providers.sqlite.provider import SQLiteProvider
        from ..providers.embedded_route import contained_database
        if (not isinstance(request, dict) or
                not isinstance(request.get('database_target_id'), str) or
                not request['database_target_id']):
            raise ProviderWorkspaceError('Select an exact SQLite registered file')
        target = request['database_target_id']
        context, endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=target)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, SQLiteProvider) or context.profile_id != 'sqlite-native':
            raise ProviderWorkspaceError('Native schema application requires SQLite')
        provider._require('administer', 'resource')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Native application requires durable receipt storage')
        try:
            path = contained_database(endpoint['route'])
            if path == ':memory:':
                raise ValueError('Native application requires an existing writable SQLite file')
            info = os.stat(path)
            if not stat.S_ISREG(info.st_mode) or endpoint['route'].get('read_only') is True:
                raise ValueError('Native application requires an existing writable SQLite file')
            applications = SQLiteSchemaApplications(
                str(store.path) + '.sqlite-schema-applications.json')
            owner = self._principal_id(server)
            binding = digest({'context': asdict(context), 'route': endpoint['route'],
                'target': target, 'file_identity': [info.st_dev, info.st_ino]})
            if action == 'sqlite_schema_review':
                if (not {'database_target_id', 'baseline', 'desired', 'execution_sha256'} <= set(request) or
                        set(request) - {'database_target_id', 'baseline', 'desired', 'execution_sha256', 'deletions', 'rebuilds', 'column_renames'}):
                    raise ValueError('Invalid SQLite schema review request')
                preview = self.sqlite_schema_plan(server, {key: value for key, value in request.items()
                    if key != 'execution_sha256'})
                if preview['execution_sha256'] != request['execution_sha256']:
                    raise ValueError('Displayed SQLite plan changed; preview again')
                return applications.review(preview,
                    read_catalog(request['baseline'], engine='sqlite'),
                    read_catalog(request['desired'], engine='sqlite'),
                    owner, binding, target,
                    file_identity=[info.st_dev, info.st_ino])
            if action == 'sqlite_schema_receipt':
                if set(request) != {'database_target_id', 'review_id'} or not isinstance(request['review_id'], str):
                    raise ValueError('Invalid SQLite schema receipt request')
                return applications.get(request['review_id'], owner, binding)
            if action != 'sqlite_schema_apply' or set(request) != {
                    'database_target_id', 'review_id', 'review_digest', 'confirmed'}:
                raise ValueError('Invalid SQLite schema application request')
            def execute(record):
                outcome = apply_review(provider, endpoint['route'], record)
                if outcome['state'] != 'not_dispatched':
                    try:
                        self.resource_service.invalidate(context)
                        outcome['explorer_invalidated'] = True
                    except Exception as error:
                        outcome.update(explorer_invalidated=False,
                                       refresh_error_type=type(error).__name__)
                return outcome
            return applications.apply({key: value for key, value in request.items()
                if key != 'database_target_id'}, owner, binding, execute)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def duckdb_data_capture(self, server, request):
        from .duckdb_catalog_service import data
        try:
            return data(self, server, request)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def duckdb_test_data(self, server, request):
        from .duckdb_catalog_service import test_data
        try:
            return test_data(self, server, request)
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def duckdb_copy_plan(self, server, request):
        from .duckdb_catalog_service import copy_plan
        try:
            return copy_plan(self, server, request)
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def duckdb_attachment_plan(self, server, request):
        from .duckdb_attachment import plan
        from ..providers.duckdb.provider import DuckDBPilotProvider
        if not isinstance(request, dict) or not isinstance(request.get('database_target_id'), str) or not request['database_target_id']:
            raise ProviderWorkspaceError('Select a registered DuckDB database file')
        target = request['database_target_id']
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
            raise ProviderWorkspaceError('Select a native DuckDB endpoint')
        provider._require('execute', 'resource')
        try:
            return plan(endpoint['route'], {key: value for key, value in request.items()
                if key != 'database_target_id'})
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def duckdb_design_asset(self, server, action, request):
        from .assets import ProjectAssetError
        from .firebird_design_assets import NativeDesignAssets
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        if not isinstance(request, dict) or not isinstance(request.get('database_target_id'), str) or not request['database_target_id']:
            raise ProviderWorkspaceError('Select a registered DuckDB database file')
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=request['database_target_id'])
        if context.profile_id != 'duckdb-native' or context.provider_id != 'org.cdeadmin.duckdb':
            raise ProviderWorkspaceError('Select a native DuckDB endpoint')
        assets = self.firebird_design_assets.assets
        try:
            return NativeDesignAssets(assets, engine='duckdb').apply(self._principal_id(server), {
                'endpoint_id': str(context.endpoint_id),
                'database_target_id': request['database_target_id']}, action, request)
        except ProjectAssetError as error:
            raise ProviderWorkspaceError(str(error)) from None
        except (IntegrityError, StaleDataError):
            assets.repository.rollback()
            raise ProviderWorkspaceError('Design storage changed concurrently; reload before saving') from None

    def sqlite_design_asset(self, server, action, request):
        from .assets import ProjectAssetError
        from .firebird_design_assets import NativeDesignAssets
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        if (not isinstance(request, dict) or
                not isinstance(request.get('database_target_id'), str) or
                not request['database_target_id']):
            raise ProviderWorkspaceError('Select a registered SQLite database file')
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=request['database_target_id'])
        if (context.profile_id != 'sqlite-native' or
                context.provider_id != 'org.cdeadmin.sqlite'):
            raise ProviderWorkspaceError('Select a native SQLite endpoint')
        assets = self.firebird_design_assets.assets
        try:
            return NativeDesignAssets(assets, engine='sqlite').apply(
                self._principal_id(server), {
                    'endpoint_id': str(context.endpoint_id),
                    'database_target_id': request['database_target_id']},
                action, request)
        except ProjectAssetError as error:
            raise ProviderWorkspaceError(str(error)) from None
        except (IntegrityError, StaleDataError):
            assets.repository.rollback()
            raise ProviderWorkspaceError(
                'Design storage changed concurrently; reload before saving') from None

    def duckdb_schema_plan(self, server, request):
        from .firebird_catalog_import import read_catalog
        from .firebird_catalog_export import build_export
        from .duckdb_schema_plan import plan
        from ..providers.duckdb.provider import DuckDBPilotProvider
        if not isinstance(request, dict) or set(request) != {'database_target_id', 'baseline', 'desired'}:
            raise ProviderWorkspaceError('DuckDB schema preview requires exact baseline and desired DDN')
        target = request['database_target_id']
        if not isinstance(target, str) or not target:
            raise ProviderWorkspaceError('Select a registered DuckDB database file')
        try:
            baseline = read_catalog(request['baseline'], engine='duckdb')
            desired = read_catalog(request['desired'], engine='duckdb')
            context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
            provider = self.endpoint_service.provider_registry.resolve(context).instance
            if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
                raise ValueError('Select a native DuckDB endpoint')
            if any(model['provenance']['endpoint_id'] != str(context.endpoint_id) or
                   model['provenance']['database_target_id'] != target for model in (baseline, desired)):
                raise ValueError('Design belongs to another endpoint or registered DuckDB file')
            captured = provider.capture_catalog(endpoint['route'], include_system=False)
            live = build_export(captured['resources'], endpoint_id=str(context.endpoint_id),
                target_id=target, generation=captured['generation'], include_system=False,
                refreshed=True, engine='duckdb', native_model=True)
            return plan(baseline, desired, live)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def duckdb_schema_application(self, server, action, request):
        from dataclasses import asdict
        import os
        import stat
        from .duckdb_schema_apply import DuckDBSchemaApplications
        from .firebird_catalog_import import read_catalog
        from .firebird_schema_plan import digest
        from ..operations.store import JsonOperationStore
        from ..providers.duckdb.provider import DuckDBPilotProvider
        from ..providers.duckdb.schema_application import apply_review
        from ..providers.embedded_route import contained_database
        if not isinstance(request, dict) or not isinstance(request.get('database_target_id'), str) or not request['database_target_id']:
            raise ProviderWorkspaceError('Select an exact DuckDB registered file')
        target = request['database_target_id']
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
            raise ProviderWorkspaceError('Native application requires DuckDB')
        provider._require('administer', 'resource')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Native application requires durable receipt storage')
        try:
            path = contained_database(endpoint['route'])
            if path == ':memory:':
                raise ValueError('Native application requires an existing writable registered file')
            info = os.stat(path)
            if not stat.S_ISREG(info.st_mode) or endpoint['route'].get('read_only') is True:
                raise ValueError('Native application requires an existing writable registered file')
            applications = DuckDBSchemaApplications(str(store.path) + '.duckdb-schema-applications.json')
            owner = self._principal_id(server)
            binding = digest({'context': asdict(context), 'route': endpoint['route'],
                'target': target, 'file_identity': [info.st_dev, info.st_ino]})
            if action == 'duckdb_schema_review':
                if set(request) != {'database_target_id', 'baseline', 'desired', 'execution_sha256'}:
                    raise ValueError('Invalid native schema review request')
                preview = self.duckdb_schema_plan(server, {key: value for key, value in request.items()
                    if key != 'execution_sha256'})
                if preview['execution_sha256'] != request['execution_sha256']:
                    raise ValueError('Displayed plan changed; preview native changes again')
                return applications.review(preview, read_catalog(request['baseline'], engine='duckdb'),
                    read_catalog(request['desired'], engine='duckdb'), owner, binding, target,
                    file_identity=[info.st_dev, info.st_ino])
            if action == 'duckdb_schema_receipt':
                if set(request) != {'database_target_id', 'review_id'} or not isinstance(request['review_id'], str):
                    raise ValueError('Invalid native schema receipt request')
                return applications.get(request['review_id'], owner, binding)
            if action != 'duckdb_schema_apply' or set(request) != {
                    'database_target_id', 'review_id', 'review_digest', 'confirmed'}:
                raise ValueError('Invalid native schema application request')
            def execute(record):
                outcome = apply_review(provider, endpoint['route'], record)
                if outcome['state'] != 'not_dispatched':
                    try:
                        self.resource_service.invalidate(context)
                        outcome['explorer_invalidated'] = True
                    except Exception as error:
                        outcome.update(explorer_invalidated=False, refresh_error_type=type(error).__name__)
                return outcome
            return applications.apply({key: value for key, value in request.items()
                if key != 'database_target_id'}, owner, binding, execute)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def export_firebird_catalog(self, server, request, *, _native_model=False):
        """Capture one admitted catalog generation into documentary DDN."""
        from .firebird_catalog_export import build_export, MAX_RESOURCES
        if (not isinstance(request, dict) or set(request) - {
                'generation', 'database_target_id', 'resource_id',
                'include_system', 'refresh'}):
            raise ProviderWorkspaceError('Invalid Firebird catalog export request')
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) not in {
                'firebird-native', 'firebird-embedded'}:
            raise ProviderWorkspaceError('Select a native Firebird endpoint')
        generation = request.get('generation')
        if not isinstance(generation, str) or not generation:
            raise ProviderWorkspaceError('Catalog generation is required')
        for name in ('include_system', 'refresh'):
            if name in request and type(request[name]) is not bool:
                raise ProviderWorkspaceError('Invalid catalog export option')
        resource_id = request.get('resource_id')
        if resource_id is not None and (not isinstance(resource_id, str) or not resource_id):
            raise ProviderWorkspaceError('Invalid catalog export resource')
        target = request.get('database_target_id', Ellipsis)
        context, endpoint, root = self.endpoint_service.workspace(server, database_target_id=target)
        if not endpoint['route'].get('database'):
            raise ProviderWorkspaceError('Select a registered Firebird database')
        resolved_target = target
        if target is Ellipsis:
            # Bind provenance to the route actually captured above, not whichever
            # target may have become active by the time export completes.
            targets = self.endpoint_service.database_catalog(server)['targets']
            matches = [item['target_id'] for item in targets
                       if item['database'] == endpoint['route']['database']]
            if len(matches) != 1:
                raise ProviderWorkspaceError('Select an unambiguous registered database target')
            resolved_target = matches[0]
        first = self.resource_service.list_page(
            context, root, page_size=500, expected_generation=generation,
            provider_route=endpoint['route']).to_dict()
        # Reject stale/foreign selections before an explicit invalidation.
        if resource_id is not None:
            self.resource_service.inspect(context, ResourceRef(context.endpoint_id, resource_id),
                expected_generation=generation, provider_route=endpoint['route'])
        if request.get('refresh', False):
            self.resource_service.invalidate(context)
            first = self.resource_service.list_page(
                context, root, page_size=500, provider_route=endpoint['route']).to_dict()
        generation = first['generation']
        resources = list(first['items'])
        continuation = first.get('next_cursor')
        while continuation is not None:
            if len(resources) >= MAX_RESOURCES:
                raise ProviderWorkspaceError('Catalog exceeds the export resource limit')
            page = self.resource_service.list_page(
                context, root, page_size=500, cursor=continuation,
                expected_generation=generation, provider_route=endpoint['route']).to_dict()
            resources.extend(page['items'])
            continuation = page.get('next_cursor')
        try:
            return build_export(resources, endpoint_id=context.endpoint_id,
                target_id=resolved_target,
                generation=generation, resource_id=resource_id,
                include_system=request.get('include_system', False),
                refreshed=request.get('refresh', False), native_model=_native_model)
        except (ValueError, TypeError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def capture_firebird_registered_catalog(self, server, request):
        """Capture an explicitly selected registration without activating it."""
        if (not isinstance(request, dict) or set(request) - {
                'target_id', 'include_system', 'refresh'} or
                not isinstance(request.get('target_id'), str) or
                not request['target_id'] or len(request['target_id']) > 1024):
            raise ProviderWorkspaceError('Select a registered Firebird database')
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) not in {
                'firebird-native', 'firebird-embedded'}:
            raise ProviderWorkspaceError('Select a native Firebird endpoint')
        for key in ('include_system', 'refresh'):
            if key in request and type(request[key]) is not bool:
                raise ProviderWorkspaceError('Invalid catalog capture option')
        target = request['target_id']
        if not any(item['target_id'] == target for item in
                   self.endpoint_service.database_catalog(server)['targets']):
            raise ProviderWorkspaceError('Database registration is unavailable')
        snapshot = self.navigator_snapshot(server, database_target_id=target)
        result = self.export_firebird_catalog(server, {
            'generation': snapshot['generation'], 'database_target_id': target,
            'include_system': request.get('include_system', False),
            'refresh': request.get('refresh', False)})
        return {'target_id': target, **result}

    def firebird_design_asset(self, server, action, request):
        from .assets import ProjectAssetError
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.exc import StaleDataError
        if (not isinstance(request, dict) or
                getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None)
                not in {'firebird-native', 'firebird-embedded'}):
            raise ProviderWorkspaceError('Select a registered Firebird design scope')
        target = request.get('database_target_id')
        if not isinstance(target, str) or not target or not any(
                item['target_id'] == target for item in
                self.endpoint_service.database_catalog(server)['targets']):
            raise ProviderWorkspaceError('Design database registration is unavailable')
        context, _endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        try:
            return self.firebird_design_assets.apply(self._principal_id(server), {
                'endpoint_id': str(context.endpoint_id), 'database_target_id': target}, action, request)
        except ProjectAssetError as error:
            raise ProviderWorkspaceError(str(error)) from None
        except (IntegrityError, StaleDataError):
            self.firebird_design_assets.assets.repository.rollback()
            raise ProviderWorkspaceError('Design storage changed concurrently; reload before saving') from None

    def firebird_relational_review(self, server, request):
        from .firebird_relational_review import handoff
        if not isinstance(request, dict) or not {'original', 'snapshot'} <= request.keys():
            raise ProviderWorkspaceError('Original and edited relational designs are required')
        options = dict(request)
        original, snapshot = options.pop('original'), options.pop('snapshot')
        options['refresh'] = True
        catalog = self.export_firebird_catalog(server, options)
        try:
            return handoff(catalog['snapshot'], original, snapshot)
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def plan_firebird_data_import(self, server, request):
        from .firebird_data_import import preview
        if not isinstance(request, dict) or 'source' not in request:
            raise ProviderWorkspaceError('Data archive source is required')
        options = dict(request)
        source = options.pop('source')
        row_order = options.pop('row_order', None)
        model = self.export_firebird_catalog(server, options, _native_model=True)
        try:
            return preview(source, model, row_order=row_order)
        except (ValueError, TypeError, KeyError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def export_firebird_data(self, server, request):
        from .firebird_data_export import capture
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Invalid data export request')
        options = dict(request)
        contents = options.pop('contents', 'data')
        if options.get('include_system'):
            raise ProviderWorkspaceError('System rows are not portable user data')
        model = self.export_firebird_catalog(server, options, _native_model=True)
        try:
            return capture(self, server, model, contents=contents)
        except (ValueError, TypeError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def export_firebird_sql(self, server, request):
        from .firebird_sql_export import build_metadata
        model = self.export_firebird_catalog(server, request, _native_model=True)
        try:
            return build_metadata(model)
        except (ValueError, TypeError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def compare_firebird_catalog(self, server, request):
        """Compare an untrusted document with an authorized catalog capture."""
        from .firebird_catalog_import import read_catalog, compare_catalogs
        if not isinstance(request, dict) or 'source' not in request:
            raise ProviderWorkspaceError('Catalog document source is required')
        options = {key: value for key, value in request.items() if key != 'source'}
        # The existing exporter validates scope and authorizes access before the
        # document parser is admitted. Document provenance cannot select routes.
        current = self.export_firebird_catalog(server, options, _native_model=True)
        try:
            document = read_catalog(request['source'])
            return compare_catalogs(document, current)
        except (ValueError, RecursionError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def plan_firebird_schema(self, server, request):
        from .firebird_catalog_import import read_catalog
        from .firebird_schema_plan import build_plan
        if (not isinstance(request, dict) or set(request) - {
                'generation', 'database_target_id', 'baseline', 'desired', 'refresh'} or
                not {'baseline', 'desired'} <= request.keys()):
            raise ProviderWorkspaceError('Invalid Firebird schema planning request')
        options = {key: value for key, value in request.items() if key not in {'baseline', 'desired'}}
        options['include_system'] = True  # Index names share the database-wide namespace.
        # Current metadata and endpoint/version context always come from the
        # authorized provider, not imported document provenance.
        current = self.export_firebird_catalog(server, options, _native_model=True)
        try:
            return build_plan(read_catalog(request['baseline']), read_catalog(request['desired']), current)
        except (ValueError, RecursionError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def firebird_schema_application(self, server, action, request):
        from .firebird_schema_apply import SchemaApplications, SchemaApplyError
        from .firebird_schema_plan import digest
        from .firebird_catalog_import import read_catalog
        from ..operations.store import JsonOperationStore
        from ..providers.firebird.provider import FirebirdProvider
        from ..providers.firebird.schema_application import apply_review
        from dataclasses import asdict
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Schema application request must be an object')
        target = request.get('database_target_id')
        if not isinstance(target, str) or not target:
            raise ProviderWorkspaceError('Select an explicit registered database target')
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, FirebirdProvider):
            raise ProviderWorkspaceError('Native schema application requires Firebird')
        provider._admit_transport({'route': endpoint['route']})
        provider.permissions.require('administer', 'resource')
        store = getattr(self.operation_bus, 'store', None)
        if not isinstance(store, JsonOperationStore):
            raise ProviderWorkspaceError('Native schema application requires durable operation storage')
        applications = SchemaApplications(str(store.path) + '.schema-applications.json')
        owner = self._principal_id(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': target})
        try:
            if action == 'firebird_schema_review':
                if set(request) - {'baseline', 'desired', 'generation', 'execution_sha256', 'database_target_id'} or not {
                        'baseline', 'desired', 'execution_sha256'} <= request.keys():
                    raise SchemaApplyError('Invalid schema review request')
                plan = self.plan_firebird_schema(server, {key: value for key, value in {
                    **request, 'refresh': True}.items() if key != 'execution_sha256'})
                if plan['execution_sha256'] != request['execution_sha256']:
                    raise SchemaApplyError('The displayed plan changed; preview native changes again')
                return applications.review(plan, read_catalog(request['baseline']), read_catalog(request['desired']),
                                           owner, binding, endpoint['route']['database'])
            if action == 'firebird_schema_receipt':
                if set(request) != {'review_id', 'database_target_id'} or not isinstance(request['review_id'], str):
                    raise SchemaApplyError('Invalid schema receipt request')
                return applications.get(request['review_id'], owner, binding)
            if action != 'firebird_schema_apply':
                raise SchemaApplyError('Unknown schema application action')
            def execute(record):
                result = apply_review(provider, endpoint['route'], record)
                try:
                    self.resource_service.invalidate(context)
                    result['explorer_invalidated'] = True
                except Exception as error:
                    result['explorer_invalidated'] = False
                    result['refresh_error_type'] = type(error).__name__
                return result
            return applications.apply({key: value for key, value in request.items()
                                       if key != 'database_target_id'}, owner, binding, execute)
        except (ValueError, RecursionError) as error:
            raise ProviderWorkspaceError(str(error)) from None

    def inspect_resource(self, server, request):
        """Inspect one cached resource without trusting browser identity."""
        if not isinstance(request, dict) or set(request).difference({
                'resource_id', 'generation', 'database_target_id'}):
            raise ProviderWorkspaceError(
                'resource inspect request is invalid'
            )
        resource_id = request.get('resource_id')
        generation = request.get('generation')
        database_target_id = request.get('database_target_id', Ellipsis)
        if not isinstance(resource_id, str) or not resource_id:
            raise ProviderWorkspaceError('resource ID is required')
        if generation is not None and not isinstance(generation, str):
            raise ProviderWorkspaceError(
                'resource generation must be text'
            )
        context, endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id,
        )
        return self.resource_service.inspect(
            context, ResourceRef(context.endpoint_id, resource_id),
            expected_generation=generation,
            provider_route=endpoint['route'],
        )

    def semantic_model_action(self, server, action, request):
        """Apply an endpoint-scoped semantic-model lifecycle action."""
        if self.semantic_model_service is None:
            raise ProviderWorkspaceError(
                'semantic model service is not initialized'
            )
        if not isinstance(request, dict):
            raise ProviderWorkspaceError(
                'semantic model request must be an object'
            )
        context, _endpoint, _root = self.endpoint_service.workspace(server)
        user_id = self._principal_id(server)
        service = self.semantic_model_service
        if action == 'semantic_model_list':
            return {'items': service.list(user_id, context.endpoint_id)}
        if action == 'semantic_model_get':
            return service.get(user_id, context.endpoint_id,
                               request.get('model_id'))
        if action == 'semantic_model_create':
            return service.create(user_id, context.endpoint_id,
                                  self._semantic_definition(
                                      context, request.get('definition')
                                  ))
        if action == 'semantic_model_update':
            return service.update(
                user_id, context.endpoint_id, request.get('model_id'),
                request.get('expected_revision'), self._semantic_definition(
                    context, request.get('definition')
                )
            )
        if action == 'semantic_model_status':
            return service.set_status(
                user_id, context.endpoint_id, request.get('model_id'),
                request.get('expected_revision'), request.get('status')
            )
        if action == 'semantic_model_clone':
            return service.clone(
                user_id, context.endpoint_id, request.get('model_id'),
                request.get('name')
            )
        if action == 'semantic_model_delete':
            return service.delete(
                user_id, context.endpoint_id, request.get('model_id'),
                request.get('expected_revision')
            )
        if action == 'semantic_model_history':
            return {'items': service.history(
                user_id, context.endpoint_id, request.get('model_id')
            )}
        if action == 'semantic_model_compare':
            return service.compare(
                user_id, context.endpoint_id, request.get('model_id'),
                request.get('left_revision'), request.get('right_revision')
            )
        if action == 'semantic_model_validate':
            return service.validate(self._semantic_definition(
                context, request.get('definition')
            ))
        if action == 'semantic_model_lineage':
            return service.lineage(self._semantic_definition(
                context, request.get('definition')
            ))
        if action in {
            'semantic_query_compile', 'semantic_query_execute',
            'semantic_query_diagnostics',
        }:
            return self._semantic_query_action(
                server, context, action, request
            )
        if action == 'semantic_materialization_plan':
            return self._semantic_materialization_plan(
                server, context, request
            )
        raise ProviderWorkspaceError('semantic model action is unavailable')

    def _semantic_definition(self, context, value):
        if not isinstance(value, dict):
            raise ProviderWorkspaceError(
                'semantic model definition must be an object'
            )
        definition = copy.deepcopy(value)
        binding = self.endpoint_service.provider_registry.resolve(context)
        capabilities = self.semantic_model_service.capabilities(
            binding.instance
        )
        expected = capabilities['analytical_profile']['semantic_family']
        declared = definition.get('semantic_family')
        if declared is None:
            definition['semantic_family'] = expected
        elif declared != expected:
            raise ProviderWorkspaceError(
                'semantic model family does not match the endpoint provider'
            )
        return definition

    def _semantic_materialization_plan(self, server, context, request):
        user_id = self._principal_id(server)
        record = self.semantic_model_service.get(
            user_id, context.endpoint_id, request.get('model_id')
        )
        model = record['definition']
        materialization_id = request.get('materialization_id')
        materialization = next((item for item in model.get(
            'materializations', []
        ) if item.get('id') == materialization_id), None)
        if materialization is None:
            raise ProviderWorkspaceError('materialization is unavailable')
        materialization = copy.deepcopy(materialization)
        if not materialization.get('target') and model.get('sources'):
            relation = model['sources'][0].get('relation', [])
            materialization['target'] = relation[:-1]
        axes = [item['id'] for item in model.get('dimensions', [])]
        query = {
            'axes': {'rows': axes, 'columns': [], 'pages': []},
            'measures': [item['id'] for item in model.get('measures', [])],
            'filters': [], 'totals': False, 'limit': 10000,
        }
        binding = self.endpoint_service.provider_registry.resolve(context)
        compiled = self.semantic_model_service.compile(
            binding.instance, model, query
        )
        callback = getattr(
            binding.instance, 'plan_semantic_materialization', None
        )
        if not callable(callback):
            raise ProviderWorkspaceError(
                'provider has no semantic materialization planner'
            )
        endpoint = self.endpoint_service.workspace(server)[1]
        return callback({
            'materialization': materialization,
            'compiled': compiled,
            '_provider_route': copy.deepcopy(endpoint['route']),
        })

    def _semantic_query_action(self, server, context, action, request):
        service = self.semantic_model_service
        user_id = self._principal_id(server)
        record = None
        if request.get('model_id'):
            record = service.get(
                user_id, context.endpoint_id, request['model_id']
            )
            model = record['definition']
        else:
            model = request.get('definition')
        query = request.get('query')
        binding = self.endpoint_service.provider_registry.resolve(context)
        security_context = {
            'claims': {'user_id': self._principal_id(server)},
        }
        if action == 'semantic_query_diagnostics':
            diagnostics = service.diagnostics(
                binding.instance, model, query,
                security_context=security_context,
            )
            diagnostics['reproducibility']['model_id'] = (
                record['model_id'] if record else None
            )
            diagnostics['reproducibility']['model_revision'] = (
                record['revision'] if record else None
            )
            return diagnostics
        compiled = service.compile(
            binding.instance, model, query,
            security_context=security_context,
        )
        compiled['reproducibility']['model_id'] = (
            record['model_id'] if record else None
        )
        compiled['reproducibility']['model_revision'] = (
            record['revision'] if record else None
        )
        response = {'compiled': compiled}
        if action == 'semantic_query_compile':
            return response
        session_id = request.get('session_id')
        if not isinstance(session_id, str) or not session_id:
            opened = self.studio_service.open_session(
                context, self.endpoint_service.workspace(server)[1],
                compiled['language_profile'],
            )
            session_id = opened['provider_session']['session_id']
            response['session_id'] = session_id
        occurrence = self.studio_service.execute(
            context, session_id, compiled['source'],
            parameters=compiled.get('parameters', {}),
            output_policy={'redact_keys': []},
        )
        response['occurrence'] = occurrence
        with self._semantic_lock:
            if len(self._semantic_executions) >= 1024:
                self._semantic_executions.pop(next(iter(
                    self._semantic_executions
                )))
            self._semantic_executions[occurrence['occurrence_id']] = {
                'endpoint_id': context.endpoint_id,
                'model': copy.deepcopy(model),
                'query': copy.deepcopy(query),
                'reproducibility': copy.deepcopy(
                    compiled['reproducibility']
                ),
            }
        return response

    def validate_visual_admin(self, server, request):
        return self._visual_admin_call(
            server, 'validate_visual_admin', request
        )

    def plan_visual_admin(self, server, request):
        return self._visual_admin_call(server, 'plan_visual_admin', request)

    def apply_visual_admin(self, server, request):
        context, callback, payload = self._prepare_visual_admin_call(
            server, 'apply_visual_admin', request
        )
        try:
            result = callback(payload)
        except VisualAdminExecutionError as exc:
            self._record_visual_admin_audit(
                server, context, exc.operation
            )
            # The provider may have applied the mutation before its response
            # was lost.  Force subsequent discovery to observe provider state
            # instead of serving a potentially stale cached resource tree.
            self.resource_service.invalidate(context)
            raise
        operation = result.get('control_operation')
        if isinstance(operation, dict):
            self._record_visual_admin_audit(server, context, operation)
        created_target = result.get('provider_result', {}).get(
            'endpoint_database_target'
        ) if isinstance(result.get('provider_result'), dict) else None
        if isinstance(created_target, dict):
            self._database_target_follow_up(
                result, 'register_created_database',
                lambda: self.endpoint_service.retain_created_database(
                    server, created_target),
            )
        dropped_target = result.get('provider_result', {}).get(
            'dropped_endpoint_database_target'
        ) if isinstance(result.get('provider_result'), dict) else None
        if isinstance(dropped_target, dict):
            self._database_target_follow_up(
                result, 'remove_dropped_database_registration',
                lambda: self.endpoint_service.delete_database_target(
                    server, dropped_target.get('target_id'), {
                        'confirmation': dropped_target.get('confirmation'),
                    }),
            )
        self.resource_service.invalidate(context)
        return result

    @staticmethod
    def _database_target_follow_up(result, action, callback):
        """Keep native execution and local registration outcomes distinct."""
        try:
            result['database_targets'] = callback()
            result.setdefault('workspace_follow_up', []).append({
                'action': action, 'state': 'complete',
            })
        except Exception as error:
            # The native operation already returned. Do not hide that receipt,
            # suggest replay, or compensate by dropping/recreating a database.
            result.setdefault('workspace_follow_up', []).append({
                'action': action, 'state': 'failed',
                'error_type': type(error).__name__,
                'automatic_mutation_retry': False,
                'message': (
                    'The provider response was recorded, but the local '
                    'database registration could not be synchronized. '
                    'Do not repeat the native operation. Refresh and review '
                    'the database and its connection registration separately.'
                ),
            })

    def plan_visual_admin_bulk(self, server, request):
        """Create bounded, provider-native previews for an ordered batch."""
        if not isinstance(request, dict) or set(request) != {'items'}:
            raise ProviderWorkspaceError('bulk plan request is invalid')
        items = request.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= 500:
            raise ProviderWorkspaceError(
                'bulk plan requires between 1 and 500 items'
            )
        validations = []
        for item in items:
            if not isinstance(item, dict):
                raise ProviderWorkspaceError('bulk plan item is invalid')
            validations.append(self.validate_visual_admin(server, item))
        if not all(item.get('valid') is True for item in validations):
            return {
                'schema': 'cdeadmin.visual-admin.bulk-plan.v1',
                'item_count': len(items),
                'ready': False,
                'atomicity': 'not-claimed',
                'automatic_retry': False,
                'validations': validations,
                'plans': [],
            }
        plans = []
        for index, item in enumerate(items):
            plan = self.plan_visual_admin(server, item)
            plans.append({'index': index, 'plan': plan})
        ready = all(
            item['plan'].get('state') == 'ready' and
            item['plan'].get('execution_available') is True
            for item in plans
        )
        return {
            'schema': 'cdeadmin.visual-admin.bulk-plan.v1',
            'item_count': len(plans),
            'ready': ready,
            'atomicity': 'not-claimed',
            'automatic_retry': False,
            'plans': plans,
        }

    def apply_visual_admin_bulk(self, server, request):
        """Apply an explicitly confirmed ordered batch without retry."""
        if not isinstance(request, dict) or set(request) != {
                'plans', 'confirmed'}:
            raise ProviderWorkspaceError('bulk apply request is invalid')
        plans = request.get('plans')
        if request.get('confirmed') is not True:
            raise ProviderWorkspaceError(
                'bulk apply requires explicit confirmation'
            )
        if not isinstance(plans, list) or not 1 <= len(plans) <= 500:
            raise ProviderWorkspaceError(
                'bulk apply requires between 1 and 500 plans'
            )
        results = []
        failed_index = None
        for index, item in enumerate(plans):
            if not isinstance(item, dict) or set(item) != {
                    'plan_id', 'plan_digest'}:
                raise ProviderWorkspaceError('bulk apply plan is invalid')
            try:
                result = self.apply_visual_admin(server, {
                    **item, 'confirmed': True,
                })
            except (
                ProviderWorkspaceError,
                VisualAdminAccessError,
                VisualAdminExecutionError,
            ) as exc:
                failed_index = index
                results.append({
                    'index': index,
                    'applied': False,
                    'error_type': type(exc).__name__,
                    'outcome': 'unknown-or-failed-provider-owned',
                })
                break
            results.append({
                'index': index, 'applied': True, 'result': result,
            })
        return {
            'schema': 'cdeadmin.visual-admin.bulk-result.v1',
            'requested_count': len(plans),
            'attempted_count': len(results),
            'applied_count': sum(
                item['applied'] is True for item in results
            ),
            'complete': failed_index is None,
            'failed_index': failed_index,
            'atomicity': 'not-claimed',
            'automatic_retry': False,
            'results': results,
        }

    def read_visual_admin_rows(self, server, request):
        return self._visual_admin_call(
            server, 'read_visual_admin_rows', request
        )

    def cancel_visual_admin_rows(self, server, request):
        return self._visual_admin_call(
            server, 'cancel_visual_admin_rows', request
        )

    def visual_admin_operation_action(self, server, action, request):
        methods = {
            'visual_admin_operation_list': 'list_visual_admin_operations',
            'visual_admin_operation_get': 'get_visual_admin_operation',
            'visual_admin_operation_refresh': (
                'refresh_visual_admin_operation'
            ),
            'visual_admin_operation_cancel': 'cancel_visual_admin_operation',
            'visual_admin_operation_post_state': (
                'validate_visual_admin_post_state'
            ),
        }
        try:
            method = methods[action]
        except KeyError as exc:
            raise ProviderWorkspaceError(
                'visual administration operation action is unavailable'
            ) from exc
        context, callback, payload = self._prepare_visual_admin_call(
            server, method, request or {}
        )
        principal = self._operation_principal(server)
        if action == 'visual_admin_operation_list':
            live = callback(payload)
            live_items = live.get('items', [])
            for item in live_items:
                self._record_visual_admin_audit(server, context, item)
            durable = (
                self.operation_bus.list_provider_audit(
                    context.endpoint_id, principal
                ) if self.operation_bus is not None else []
            )
            merged = {
                item['operation_id']: {
                    **item, 'durable_audit': True,
                    'live_provider_handle_available': False,
                }
                for item in durable
            }
            merged.update({
                item['operation_id']: {
                    **item, 'durable_audit': self.operation_bus is not None,
                    'live_provider_handle_available': True,
                }
                for item in live_items
            })
            return {
                'schema': 'cdeadmin.visual-admin.operation-list.v1',
                'items': list(merged.values()),
                'restart_safe_audit': self.operation_bus is not None,
            }
        try:
            result = callback(payload)
        except VisualAdminExecutionError as exc:
            self._record_visual_admin_audit(server, context, exc.operation)
            if action in {
                    'visual_admin_operation_cancel',
                    'visual_admin_operation_post_state'}:
                self.resource_service.invalidate(context)
            raise
        except VisualAdminAccessError:
            if action != 'visual_admin_operation_get' or \
                    self.operation_bus is None:
                raise
            operation_id = (request or {}).get('operation_id')
            result = self.operation_bus.get_provider_audit(
                context.endpoint_id, principal, operation_id
            )
            return {
                **result,
                'durable_audit': True,
                'live_provider_handle_available': False,
                'restart_safe_audit': True,
            }
        if action in {
                'visual_admin_operation_cancel',
                'visual_admin_operation_post_state'}:
            self.resource_service.invalidate(context)
        if isinstance(result, dict) and result.get('operation_id'):
            self._record_visual_admin_audit(server, context, result)
            return {
                **result,
                'durable_audit': self.operation_bus is not None,
                'live_provider_handle_available': True,
                'restart_safe_audit': self.operation_bus is not None,
            }
        return result

    def _record_visual_admin_audit(self, server, context, operation):
        if self.operation_bus is None:
            return
        self.operation_bus.record_provider_audit(
            context.endpoint_id, self._operation_principal(server), operation
        )

    def _operation_principal(self, server):
        return f'user:{self._principal_id(server)}'

    def _history_context(self, server, target, dialect):
        from .query_history import HistoryScope
        profile = getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None)
        if profile not in {None, 'postgresql-native', 'firebird-native', 'firebird-embedded', 'mysql-native', 'mariadb-native', 'duckdb-native', 'sqlite-native'}:
            raise ProviderWorkspaceError('SQL history is not admitted for this engine')
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        if profile in {None, 'postgresql-native'}:
            from ..providers.postgresql.connection_target import database_oid
            try:
                oid = database_oid(target)
            except ValueError:
                raise ProviderWorkspaceError('Select an explicit native PostgreSQL database for history') from None
            if context.profile_id != 'postgresql-native' or oid is None or dialect is not None:
                raise ProviderWorkspaceError('PostgreSQL history requires its native database target and language')
            return HistoryScope(self._principal_id(server), server.id, target, 'postgresql-sql', engine='postgresql')
        if profile == 'duckdb-native':
            if context.profile_id != profile or dialect is not None:
                raise ProviderWorkspaceError('DuckDB history requires its native database target and language')
            targets = self.endpoint_service.database_catalog(server)['targets']
            matches = [item for item in targets if item['target_id'] == target]
            if (not isinstance(target, str) or not target or len(matches) != 1 or
                    not matches[0].get('database') or
                    matches[0]['database'] != endpoint['route'].get('database')):
                raise ProviderWorkspaceError('Select an explicit registered DuckDB file for history')
            return HistoryScope(self._principal_id(server), server.id, target, 'duckdb-sql', engine='duckdb')
        if profile == 'sqlite-native':
            if context.profile_id != profile or dialect is not None:
                raise ProviderWorkspaceError('SQLite history requires its native file target and language')
            targets = self.endpoint_service.database_catalog(server)['targets']
            matches = [item for item in targets if item['target_id'] == target]
            if (not isinstance(target, str) or not target or len(matches) != 1 or
                    not matches[0].get('database') or
                    matches[0]['database'] != endpoint['route'].get('database')):
                raise ProviderWorkspaceError('Select an explicit registered SQLite file for history')
            return HistoryScope(self._principal_id(server), server.id, target, 'sqlite-sql', engine='sqlite')
        if profile in {'mysql-native', 'mariadb-native'}:
            engine = 'mariadb' if profile == 'mariadb-native' else 'mysql'
            label = 'MariaDB' if engine == 'mariadb' else 'MySQL'
            if context.profile_id != profile or dialect is not None:
                raise ProviderWorkspaceError(f'{label} history requires its native database target and language')
            targets = self.endpoint_service.database_catalog(server)['targets']
            matches = [item for item in targets if item['target_id'] == target]
            if (not isinstance(target, str) or not target or len(matches) != 1 or
                    not matches[0].get('database') or
                    matches[0]['database'] != endpoint['route'].get('database')):
                raise ProviderWorkspaceError(f'Select an explicit registered {label} database for history')
            return HistoryScope(self._principal_id(server), server.id, target, engine + '-sql', engine=engine)
        if not isinstance(target, str) or not target:
            matches = [item['target_id'] for item in self.endpoint_service.database_catalog(server)['targets']
                       if item['database'] == endpoint['route']['database']]
            if len(matches) != 1:
                raise ProviderWorkspaceError('Select a registered database target for SQL history')
            target = matches[0]
        return HistoryScope(self._principal_id(server), server.id, target, 3 if dialect is None else dialect)

    def firebird_object_templates(self, server, request):
        from .firebird_templates import context as template_context, render
        if not isinstance(request, dict) or set(request) - {
                'resource_id', 'generation', 'database_target_id', 'template', 'new_name'}:
            raise ProviderWorkspaceError('Invalid object-template request')
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) not in {
                'firebird-native', 'firebird-embedded'}:
            raise ProviderWorkspaceError('Native templates require Firebird')
        target = request.get('database_target_id')
        snapshot = self.navigator_snapshot(server, database_target_id=target)
        if request.get('generation') != snapshot['generation']:
            raise ProviderWorkspaceError('Catalog changed; refresh the object before rendering a template')
        try:
            result = template_context(snapshot, request.get('resource_id'))
            if 'template' in request:
                return render(result, request['template'], request.get('new_name'))
            return result
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from error

    def firebird_isql_context(self, server, request):
        """Describe an owned TCP target; never launch or export its secrets."""
        from ..providers.firebird.connection_strings import database_dsn
        if not isinstance(request, dict) or set(request) != {'database_target_id'}:
            raise ProviderWorkspaceError('Select one registered Firebird database')
        target = request['database_target_id']
        if not isinstance(target, str) or not target:
            raise ProviderWorkspaceError('Select one registered Firebird database')
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) != 'firebird-native':
            raise ProviderWorkspaceError('Desktop ISQL requires a Firebird TCP registration')
        _context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        route = endpoint['route']
        if not route.get('host') or route.get('protocol') == 'XNET':
            raise ProviderWorkspaceError('Desktop ISQL requires an explicit TCP host')
        dialect = route.get('sql_dialect', 3)
        if type(dialect) not in (int, str) or str(dialect) not in {'1', '3'}:
            raise ProviderWorkspaceError('Native client SQL dialect must be 1 or 3')
        return {'schema': 'scratchrobin.firebird.isql-context@1',
                'database_target_id': target,
                'dsn': database_dsn(route['database'], route['host'], route.get('port'), route.get('protocol') or 'INET'),
                'user': route.get('user') or '', 'role': route.get('role') or '',
                'charset': route.get('charset') or 'UTF8', 'sql_dialect': int(dialect)}

    def firebird_event_action(self, server, request):
        from ..providers.firebird.provider import FirebirdProvider
        from .firebird_schema_plan import digest
        from dataclasses import asdict
        if not isinstance(request, dict) or set(request) - {
                'action', 'database_target_id', 'names', 'subscription_id'}:
            raise ProviderWorkspaceError('Invalid native event request')
        target = request.get('database_target_id')
        if not isinstance(target, str) or not target:
            raise ProviderWorkspaceError('Select a registered database for events')
        context, endpoint, _root = self.endpoint_service.workspace(server, database_target_id=target)
        provider = self.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, FirebirdProvider):
            raise ProviderWorkspaceError('Native event monitoring requires Firebird')
        provider._admit_transport({'route': endpoint['route']})
        owner = self._operation_principal(server)
        binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': target})
        action = request.get('action')
        try:
            if action == 'start':
                if set(request) != {'action', 'database_target_id', 'names'}:
                    raise ValueError('Invalid event start request')
                route = copy.deepcopy(endpoint['route'])
                native_session = {}
                def connect():
                    opened = provider.open_session({'route': route})
                    native_session['id'] = opened['session_id']
                    return provider._sessions[opened['session_id']].handle
                def close(_handle):
                    provider.close_session({'session_id': native_session['id']})
                return self.firebird_events.start(owner, binding, request['names'], connect, close)
            if action in {'poll', 'stop'}:
                if set(request) != {'action', 'database_target_id', 'subscription_id'} or not isinstance(request['subscription_id'], str):
                    raise ValueError('Invalid event subscription request')
                return self.firebird_events.action(owner, binding, request['subscription_id'], stop=action == 'stop')
            raise ValueError('Unknown native event action')
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from error

    def firebird_metadata_search(self, server, request):
        from .firebird_search import validate, search
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) not in {
                'firebird-native', 'firebird-embedded'}:
            raise ProviderWorkspaceError('Metadata search requires a Firebird endpoint')
        try:
            target, query, fields, kind = validate(request)
        except ValueError as error:
            raise ProviderWorkspaceError(str(error)) from error
        registered = self.endpoint_service.database_catalog(server)['targets']
        if not any(item['target_id'] == target for item in registered):
            raise ProviderWorkspaceError('Database registration is unavailable')
        snapshot = self.navigator_snapshot(server, database_target_id=target)
        return {'target_id': target, **search(snapshot, query, fields, kind)}

    def firebird_editor_metadata(self, server, database_target_id):
        if getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) not in {
                'firebird-native', 'firebird-embedded'}:
            raise ProviderWorkspaceError('Firebird editor metadata requires a Firebird endpoint')
        snapshot = self.navigator_snapshot(server, database_target_id=database_target_id)
        from .firebird_editor import metadata
        return metadata(snapshot)

    def query_history_action(self, server, action, request):
        from .query_history import HistoryError
        factory = getattr(self, 'query_history_factory', None)
        if factory is None:
            raise ProviderWorkspaceError('SQL history persistence is unavailable')
        if not isinstance(request, dict) or set(request) - {
                'database_target_id', 'client_sql_dialect', 'search', 'policy', 'confirmed'}:
            raise ProviderWorkspaceError('Invalid SQL history request')
        scope = self._history_context(server, request.get('database_target_id'), request.get('client_sql_dialect'))
        try:
            history = factory()
            if action == 'query_history_read':
                return history.read(scope, request.get('search', ''))
            if action == 'query_history_configure':
                return {'policy': history.configure(scope, request.get('policy'))}
            if action == 'query_history_clear' and request.get('confirmed') is True:
                return history.clear(scope)
            raise HistoryError('Unknown SQL history action or missing clear confirmation')
        except HistoryError as error:
            raise ProviderWorkspaceError(str(error)) from None

    def _record_query_request(self, server, target, dialect, source, sensitive, kind, execute):
        factory = getattr(self, 'query_history_factory', None)
        admitted = getattr(getattr(server, 'endpoint_profile', None), 'profile_id', None) in {
            None, 'postgresql-native', 'firebird-native', 'firebird-embedded', 'mysql-native', 'mariadb-native', 'duckdb-native', 'sqlite-native'}
        if factory is None or not admitted:
            return execute()
        history = scope = entry = None
        notice = None
        try:
            scope = self._history_context(server, target, dialect)
            history = factory()
            entry = history.record(scope, source, sensitive=sensitive, kind=kind)
        except Exception as error:
            notice = 'SQL history recording unavailable (' + type(error).__name__ + ')'
        try:
            result = execute()
        except Exception:
            if entry and entry.get('recorded'):
                try:
                    history.observation(scope, entry['entry_id'], 'request-error')
                except Exception:
                    pass  # Preserve the original native request error.
            raise
        if entry and entry.get('recorded'):
            try:
                state = 'accepted'
                if kind == 'script-prepared':
                    state = 'preparation-rejected' if result.get('state') == 'invalid' else 'prepared'
                history.observation(scope, entry['entry_id'], state)
            except Exception as error:
                notice = 'SQL history observation unavailable (' + type(error).__name__ + ')'
        if isinstance(result, dict):
            result = {**result, 'sql_history': {**(entry or {}), 'warning': notice}}
        return result

    def open_session(
        self, server, language_profile, database_target_id=None, *, session_purpose=None,
    ):
        context, endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        if session_purpose is not None:
            if (session_purpose not in {'firebird-test-data', 'firebird-data-export', 'firebird-data-import', 'firebird-row-grid'} or
                    context.profile_id not in {'firebird-native', 'firebird-embedded'} or
                    language_profile != 'firebird-sql'):
                raise ProviderWorkspaceError('Session purpose is not admitted for this engine')
            endpoint = {**endpoint, 'route': {**endpoint['route'],
                'transaction_isolation': 'SNAPSHOT',
                'transaction_access': 'READ' if session_purpose == 'firebird-data-export' else 'WRITE',
                'transaction_lock_timeout': 10, 'transaction_auto_commit': False,
                'transaction_no_auto_undo': False, 'transaction_ignore_limbo': False}}
        opened = self.studio_service.open_session(
            context, endpoint, language_profile
        )
        return {
            **opened,
            'session_id': opened['provider_session']['session_id'],
        }

    def execute(
        self, server, session_id, source, parameters=None,
        database_target_id=Ellipsis, *, max_rows=None, client_sql_dialect=None,
        script_mode=False, plan_mode=False, history_sensitive=False, profile_mode=False, statistics_mode=False,
    ):
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        if type(history_sensitive) is not bool:
            raise ProviderWorkspaceError('History sensitive flag must be boolean')
        if not isinstance(source, str) or not source.strip():
            raise ProviderWorkspaceError('query source must not be empty')
        if parameters is not None and not isinstance(parameters, (dict, list)):
            raise ProviderWorkspaceError(
                'query parameters must be an object or array')
        policy = {'redact_keys': []}
        if context.provider_id in {'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'} and not script_mode and not plan_mode:
            policy['firebird_statement_metrics'] = True
        if type(profile_mode) is not bool or profile_mode and (script_mode or plan_mode or context.provider_id not in {
                'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'}):
            raise ProviderWorkspaceError('Native profiling requires one Firebird statement')
        if profile_mode:
            policy['firebird_profile'] = True
        if type(statistics_mode) is not bool or statistics_mode and (script_mode or plan_mode or context.provider_id not in {
                'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'}):
            raise ProviderWorkspaceError('Query statistics require one Firebird statement')
        if statistics_mode:
            policy['firebird_statistics'] = True
        if type(script_mode) is not bool:
            raise ProviderWorkspaceError('script mode must be boolean')
        if script_mode:
            if context.provider_id not in {
                    'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'}:
                raise ProviderWorkspaceError(
                    'Provider has not admitted SQL scripts')
            policy['firebird_script'] = True
        if type(plan_mode) is not bool:
            raise ProviderWorkspaceError('plan mode must be boolean')
        if plan_mode:
            if (script_mode or context.provider_id not in {
                    'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded',
                    'org.pgadmin.postgresql'}):
                raise ProviderWorkspaceError(
                    'Provider has not admitted single-statement plans')
            policy['postgresql_plan' if context.provider_id ==
                   'org.pgadmin.postgresql' else 'firebird_plan'] = True
        if client_sql_dialect is not None:
            if context.provider_id not in {
                    'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'}:
                raise ProviderWorkspaceError(
                    'client SQL dialect selection is only admitted for '
                    'Firebird')
            if (type(client_sql_dialect) is not int or
                    client_sql_dialect not in (1, 2, 3)):
                raise ProviderWorkspaceError(
                    'Firebird client SQL dialect must be integer 1, 2 or 3')
            policy['client_sql_dialect'] = client_sql_dialect
        if max_rows is not None:
            if context.provider_id not in {
                    'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'}:
                raise ProviderWorkspaceError(
                    'this provider has not admitted a maximum-row fetch '
                    'policy')
            if type(max_rows) is not int or not 1 <= max_rows <= 1_000_000:
                raise ProviderWorkspaceError(
                    'maximum fetched rows must be an integer from 1 to '
                    '1000000')
            policy['max_rows'] = max_rows
        def execute():
            return self.studio_service.execute(context, session_id, source,
                parameters=copy.deepcopy(parameters), output_policy=policy)
        if plan_mode:
            return execute()
        return self._record_query_request(server, database_target_id, client_sql_dialect,
            source, history_sensitive, 'script' if script_mode else 'statement', execute)

    def language_tool_action(self, server, action, data):
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=data.get('database_target_id'))
        from pgadmin.cdeadmin.data_studio.language_tools import LanguageToolError
        try:
            if action == 'source_catalog':
                return self.studio_service.session_catalog(context, data.get('session_id'),
                    include_system=data.get('include_system', False))
            if action == 'source_complete':
                source, prefix = data.get('source'), data.get('source_before_cursor')
                if (not isinstance(source, str) or not isinstance(prefix, str) or
                        len(source.encode('utf8')) > 1024 * 1024 or not source.startswith(prefix)):
                    raise ProviderWorkspaceError('Completion requires bounded source and its exact cursor prefix')
                options = {'client_sql_dialect': data['client_sql_dialect']} if 'client_sql_dialect' in data else {}
                return self.studio_service.complete(context, data.get('session_id'), source, prefix, **options)
            if action == 'source_validate':
                options = {'client_sql_dialect': data['client_sql_dialect']} if 'client_sql_dialect' in data else {}
                if 'script' in data:
                    options['script'] = data['script']
                return self.studio_service.validate_source(context, data.get('session_id'), data.get('source'), **options)
            if action == 'native_script_prepare':
                parameters = data.get('parameters', {})
                if not isinstance(parameters, (dict, list)) or parameters:
                    raise ProviderWorkspaceError('Retained scripts require empty parameter bindings')
                return self._record_query_request(server, data.get('database_target_id'), data.get('client_sql_dialect'),
                    data.get('source'), data.get('history_sensitive', False), 'script-prepared',
                    lambda: self.studio_service.scripts.prepare(context, data.get('session_id'), data.get('source')))
            if action == 'native_script_advance':
                return self.studio_service.scripts.advance(context, data.get('plan_id'), data.get('revision'))
            if action == 'native_script_stop':
                return self.studio_service.scripts.stop(context, data.get('plan_id'))
            if action == 'native_script_discard':
                return self.studio_service.scripts.discard(context, data.get('plan_id'))
        except LanguageToolError as exc:
            raise ProviderWorkspaceError(str(exc)) from exc
        raise ProviderWorkspaceError('Unknown language-tool action')

    def preview_script(self, server, session_id, source,
                       database_target_id=Ellipsis):
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id)
        return self.studio_service.preview_script(context, session_id, source)

    def query_stream(self, server, session_id, request,
                     database_target_id=Ellipsis):
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id)
        if not isinstance(request, dict):
            raise ProviderWorkspaceError('Streaming request must be an object')
        try:
            return self.studio_service.query_stream(
                context, session_id, request)
        except Exception as exc:
            # Native messages may include SQL, paths, or credentials.
            from ..sdk.relational import RelationalClientError
            detail = (str(exc) if isinstance(exc, RelationalClientError)
                      else type(exc).__name__)
            raise ProviderWorkspaceError(
                'Stream request failed (' + detail +
                '). Close the stream before retrying; no rollback or '
                'commit is implied.') from None

    def poll(self, server, occurrence_id, database_target_id=Ellipsis, *, buffer_rows=None):
        if buffer_rows is not None and (type(buffer_rows) is not int or not 1 <= buffer_rows <= 500):
            raise ProviderWorkspaceError('Result buffer rows must be an integer from 1 to 500')
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        occurrence = self.studio_service.poll(context, occurrence_id)
        response = {'occurrence': occurrence, 'rendered_result': None}
        result = occurrence.get('result')
        pending_firebird = (
            result is not None and result.get('complete') is False and
            result.get('extensions', {}).get('firebird', {}).get(
                'payload', {}).get('execution_state') == 'running'
        )
        # An asynchronous status observation is not a new result set. Do not
        # allocate/store/render an empty descriptor on every native poll.
        if result is not None and not pending_firebird:
            binding = self.endpoint_service.provider_registry.resolve(context)
            renderer = binding.instance.select_renderer(
                copy.deepcopy(result)
            )
            capabilities = renderer.get('capability_ids', ())
            descriptor = self.studio_service.admit_result(
                context, occurrence_id, capabilities
            )
            response['rendered_result'] = self.result_service.render(
                descriptor['result_id'], page_size=min(buffer_rows or 500,
                    descriptor.get('limits', {}).get('max_page_size', 500)),
                endpoint_id=context.endpoint_id,
            )
            with self._semantic_lock:
                semantic = self._semantic_executions.get(occurrence_id)
            if semantic is not None:
                if semantic['endpoint_id'] != context.endpoint_id:
                    raise ProviderWorkspaceError(
                        'semantic execution belongs to another endpoint'
                    )
                rendered = response['rendered_result']
                view = rendered.get('view_model') or {}
                records = view.get('rows', view.get('records', []))
                rendered['renderer_id'] = 'cdeadmin.result.cellset.pivot'
                rendered['component_reference'] = (
                    'cdeadmin/results/CubePivotView'
                )
                rendered['view_model'] = self.semantic_model_service.cellset(
                    semantic['model'], semantic['query'], records
                )
                rendered['reproducibility'] = {
                    **copy.deepcopy(semantic['reproducibility']),
                    'rendered_page_digest': hashlib.sha256(json.dumps(
                        rendered['view_model'], sort_keys=True,
                        separators=(',', ':'), ensure_ascii=False,
                        default=repr,
                    ).encode('utf-8')).hexdigest(),
                    'provider_snapshot': None,
                    'exact_data_replay_requires_provider_snapshot': True,
                    'common_layer_infers_snapshot_or_finality': False,
                }
        if buffer_rows is not None and response['rendered_result'] is not None:
            # Keep the original admitted result on the server. Do not duplicate
            # its native row arrays alongside the bounded browser page.
            response['occurrence'] = copy.deepcopy(occurrence)
            native_result = response['occurrence'].get('result') or {}
            fields = {'rows', 'records', 'entries', 'documents', 'points', 'graphs', 'matches', 'hits'}
            profile = getattr(binding.instance, 'profile', None)
            record_field = getattr(profile, 'result_records_field', None)
            if record_field:
                fields.add(record_field)
            page = response['rendered_result']['page']
            count = min(page['page_size'], max(0, page['sampled_count'] - page['offset']))
            for extension in (native_result.get('extensions') or {}).values():
                if not isinstance(extension, dict):
                    continue
                payload = extension.get('payload')
                if isinstance(payload, dict):
                    for field in fields:
                        if isinstance(payload.get(field), list):
                            payload.pop(field)
                    payload['buffered_row_count'] = count
                elif isinstance(payload, list):
                    extension['payload'] = []
            response['buffered_rows_only'] = True
        return response

    def result_page(self, server, request):
        """Render one endpoint-bound local result page."""
        if not isinstance(request, dict) or set(request).difference({
                'result_id', 'cursor', 'page_size'}):
            raise ProviderWorkspaceError('result page request is invalid')
        result_id = request.get('result_id')
        cursor = request.get('cursor')
        page_size = request.get('page_size', 500)
        if not isinstance(result_id, str) or not result_id:
            raise ProviderWorkspaceError('result ID is required')
        if cursor is not None and not isinstance(cursor, str):
            raise ProviderWorkspaceError('result cursor must be text')
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            raise ProviderWorkspaceError('result page size must be an integer')
        context, _endpoint, _root = self.endpoint_service.workspace(server)
        return self.result_service.render(
            result_id, page_size=page_size, cursor=cursor,
            endpoint_id=context.endpoint_id,
        )

    def export_result(self, server, request):
        """Return one bounded, redacted result export for browser download."""
        if not isinstance(request, dict) or set(request) != {
                'result_id', 'format'}:
            raise ProviderWorkspaceError('result export request is invalid')
        result_id = request.get('result_id')
        export_format = request.get('format')
        if not isinstance(result_id, str) or not result_id:
            raise ProviderWorkspaceError('result ID is required')
        if not isinstance(export_format, str) or not export_format:
            raise ProviderWorkspaceError('result export format is required')
        context, _endpoint, _root = self.endpoint_service.workspace(server)
        exported = self.result_service.export(
            result_id, export_format, endpoint_id=context.endpoint_id
        )
        content = exported.pop('content')
        return {
            **exported,
            'content_base64': base64.b64encode(content).decode('ascii'),
            'media_type': self._export_media_type(export_format),
            'filename': f'cdeadmin-result-{result_id}.' + ('ddn-workspace.json' if export_format == 'ddn' else export_format),
        }

    @staticmethod
    def _export_media_type(export_format):
        media_types = {
            'csv': 'text/csv', 'json': 'application/json', 'ddn': 'application/json',
            'jsonl': 'application/x-ndjson',
            'xlsx': ('application/vnd.openxmlformats-officedocument.'
                     'spreadsheetml.sheet'),
            'svg': 'image/svg+xml', 'pdf': 'application/pdf',
        }
        return media_types.get(export_format, 'application/octet-stream')

    def compare_results(self, server, request):
        """Compare two retained redacted presentations from one endpoint."""
        if not isinstance(request, dict) or set(request) != {
                'left_result_id', 'right_result_id'}:
            raise ProviderWorkspaceError(
                'result comparison request is invalid'
            )
        values = (
            request.get('left_result_id'), request.get('right_result_id')
        )
        if any(not isinstance(item, str) or not item for item in values):
            raise ProviderWorkspaceError(
                'result comparison IDs are required'
            )
        context, _endpoint, _root = self.endpoint_service.workspace(server)
        return self.result_service.compare(
            values[0], values[1], endpoint_id=context.endpoint_id
        )

    def cancel(self, server, occurrence_id, database_target_id=Ellipsis):
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        return self.studio_service.request_cancel(context, occurrence_id)

    def transaction(self, server, session_id, database_target_id=None):
        """Return the provider presentation without interpreting its state."""
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        return self.studio_service.refresh_transaction(context, session_id)

    def transaction_action(
        self, server, session_id, action, database_target_id=None,
    ):
        """Dispatch a provider-owned transaction action without inference."""
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        return self.studio_service.control_transaction(
            context, session_id, action
        )

    def close_session(
        self, server, session_id, database_target_id=None,
    ):
        """Release one provider session in its original database scope."""
        context, _endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        return self.studio_service.close_session(context, session_id)

    def _visual_admin_call(self, server, method_name, request):
        _context, callback, payload = self._prepare_visual_admin_call(
            server, method_name, request
        )
        return callback(payload)

    def _prepare_visual_admin_call(self, server, method_name, request):
        """Resolve execution and invalidation against the same scope."""
        if not isinstance(request, dict):
            raise ProviderWorkspaceError(
                'visual administration request must be an object'
            )
        payload = copy.deepcopy(request)
        database_target_id = payload.pop('database_target_id', Ellipsis)
        if database_target_id is not Ellipsis and (
                not isinstance(database_target_id, str) or
                not database_target_id):
            raise ProviderWorkspaceError(
                'database target identity is invalid'
            )
        target = payload.get('target_resource')
        if database_target_id is Ellipsis and isinstance(target, dict):
            extensions = target.get('extensions')
            cdeadmin = extensions.get('cdeadmin') if isinstance(
                extensions, dict
            ) else None
            candidate = cdeadmin.get('database_target_id') if isinstance(
                cdeadmin, dict
            ) else None
            if candidate is not None:
                if not isinstance(candidate, str) or not candidate:
                    raise ProviderWorkspaceError(
                        'database target identity is invalid'
                    )
                database_target_id = candidate
        context, endpoint, _root = self.endpoint_service.workspace(
            server, database_target_id=database_target_id
        )
        if isinstance(database_target_id, str) and isinstance(target, dict):
            extensions = target.setdefault('extensions', {})
            if not isinstance(extensions, dict):
                raise ProviderWorkspaceError(
                    'target resource extensions are invalid'
                )
            cdeadmin = extensions.setdefault('cdeadmin', {})
            if not isinstance(cdeadmin, dict):
                raise ProviderWorkspaceError(
                    'target CDEadmin extensions are invalid'
                )
            retained_target_id = cdeadmin.get('database_target_id')
            if retained_target_id not in {None, database_target_id}:
                raise ProviderWorkspaceError(
                    'target database identity conflicts with request scope'
                )
            cdeadmin['database_target_id'] = database_target_id
        binding = self.endpoint_service.provider_registry.resolve(context)
        callback = getattr(binding.instance, method_name, None)
        if not callable(callback):
            raise ProviderWorkspaceError(
                'endpoint provider has no visual administration contract'
            )
        # Route authority is server-side. Never accept a browser-supplied
        # route, even under the reserved internal key.
        payload.pop('_provider_route', None)
        payload['_provider_route'] = copy.deepcopy(endpoint['route'])
        return context, callback, payload

    @staticmethod
    def _principal_id(server):
        value = getattr(server, 'user_id', None)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProviderWorkspaceError(
                'workspace owner identity is unavailable'
            )
        return value


def init_app(
    app, endpoint_service, resource_service, studio_service, result_service,
    semantic_model_service=None, operation_bus=None,
    report_delivery_service=None, report_scheduler_service=None,
):
    from .transfer import init_app as init_transfer_app
    from .assets import init_app as init_project_assets
    from .monitoring_host import init_app as init_monitoring

    init_transfer_app(app)
    init_project_assets(app)
    init_monitoring(app, endpoint_service)
    existing = app.extensions.get(APP_EXTENSION_KEY)
    if existing is not None:
        return existing
    service = ProviderWorkspaceService(
        endpoint_service, resource_service, studio_service, result_service,
        semantic_model_service, operation_bus, report_delivery_service,
        report_scheduler_service,
    )
    from .query_history import repository as query_history_repository
    service.query_history_factory = query_history_repository
    from .firebird_design_assets import FirebirdDesignAssets
    from .assets import service_for_app as asset_service
    service.firebird_design_assets = FirebirdDesignAssets(asset_service(app))
    import atexit
    atexit.register(service.firebird_events.close)
    app.extensions[APP_EXTENSION_KEY] = service
    return service


def service_for_app(app):
    try:
        return app.extensions[APP_EXTENSION_KEY]
    except (AttributeError, KeyError) as exc:
        raise ProviderWorkspaceError(
            'CDEadmin provider workspace is not initialized'
        ) from exc
