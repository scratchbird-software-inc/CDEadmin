##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Authenticated Flask routes for the DDN DesignStore and StoreDDNProcess."""

from __future__ import annotations

from typing import Any

from .service import (
    APP_EXTENSION_KEY,
    DesignStore,
    DesignStoreConflict,
    DesignStoreError,
    DesignStoreForbidden,
    DesignStoreNotFound,
)
from .shared_ddn import (
    StoreDDNProcess,
    build_four_level_erd_ddn,
    compute_server_layout,
    compute_system_diagram_drift,
    convert_erd_design_engine,
    preview_erd_alter_plan,
    propose_system_diagram_change,
)

PROCESS_EXTENSION_KEY = 'cdeadmin_store_ddn_process'
_ACCESS_RANK = {'viewer': 1, 'editor': 2, 'manager': 3, 'owner': 4}


def init_app(app, project_asset_service=None) -> DesignStore:
    """Register the shared DesignStore, StoreDDNProcess and HTTP blueprint."""
    existing = app.extensions.get(APP_EXTENSION_KEY)
    if existing is not None:
        return existing
    db_path = app.config.get('CDEADMIN_DESIGN_STORE_PATH')
    store = DesignStore(db_path=db_path)
    process = StoreDDNProcess(store)
    app.extensions[APP_EXTENSION_KEY] = store
    app.extensions[PROCESS_EXTENSION_KEY] = process
    _register_routes(app, project_asset_service)
    return store


def store_for_app(app) -> DesignStore:
    try:
        return app.extensions[APP_EXTENSION_KEY]
    except (AttributeError, KeyError) as exc:
        raise DesignStoreError(
            'ScratchRobin design store is not initialized'
        ) from exc


def process_for_app(app) -> StoreDDNProcess:
    try:
        return app.extensions[PROCESS_EXTENSION_KEY]
    except (AttributeError, KeyError) as exc:
        store = store_for_app(app)
        process = StoreDDNProcess(store)
        app.extensions[PROCESS_EXTENSION_KEY] = process
        return process


def _check_project_access(
    project_asset_service,
    user_id: int,
    role_ids: tuple[int, ...],
    project_id: str,
    needed: str,
) -> str:
    """Verify project access when ProjectAssetService has a project record."""
    if project_asset_service is None:
        return 'owner'
    try:
        state = project_asset_service.project_state(
            user_id, role_ids, project_id
        )
        access = state.get('access') or 'viewer'
    except Exception:
        # If the project is not registered in legacy project_assets, allow
        # authenticated user access scoped by project_id in designs.db.
        return 'owner'
    if _ACCESS_RANK.get(access, 0) < _ACCESS_RANK.get(needed, 1):
        raise DesignStoreForbidden(
            f'Project {needed} access is required for this design action'
        )
    return access


def _register_routes(app, project_asset_service) -> None:
    from flask import Blueprint, current_app, jsonify, request
    from flask_security import current_user
    from pgadmin.user_login_check import pga_login_required

    api = Blueprint('cdeadmin_design_store', __name__)

    def principal() -> tuple[int, tuple[int, ...]]:
        uid = int(getattr(current_user, 'id', 1) or 1)
        roles = tuple(
            int(r.id) for r in getattr(current_user, 'roles', ())
            if getattr(r, 'id', None) is not None
        )
        return uid, roles

    def invoke(callback):
        store = store_for_app(current_app)
        process = process_for_app(current_app)
        try:
            return jsonify(success=1, data=callback(store, process))
        except DesignStoreError as exc:
            payload: dict[str, Any] = {'success': 0, 'errormsg': str(exc)}
            if isinstance(exc, DesignStoreConflict):
                payload['code'] = exc.code
            return jsonify(**payload), exc.status_code
        except Exception:
            current_app.logger.exception('Unexpected design store failure')
            return (
                jsonify(
                    success=0,
                    errormsg='Design store request failed.',
                ),
                500,
            )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs',
        methods=['GET', 'POST'],
    )
    @pga_login_required
    def designs(project_id: str):
        uid, role_ids = principal()
        if request.method == 'GET':
            _check_project_access(
                project_asset_service, uid, role_ids, project_id, 'viewer'
            )
            kind = request.args.get('kind') or None
            query = request.args.get('q') or None
            if query:
                return invoke(
                    lambda store, _proc: store.search(
                        query, project_id=project_id, kind=kind
                    )
                )
            return invoke(
                lambda store, _proc: store.list_designs(
                    project_id=project_id, kind=kind
                )
            )

        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'editor'
        )
        body = request.get_json(silent=True) or {}
        mode = body.get('mode') or 'create'
        if mode == 'import_physical_erd':
            return invoke(
                lambda store, _proc: store.import_physical_erd_workspace(
                    project_id=project_id,
                    key=str(body.get('key') or ''),
                    title=str(body.get('title') or body.get('key') or ''),
                    workspace=body.get('workspace') or body.get('ddn_text'),
                    actor_id=uid,
                    note=str(body.get('note') or ''),
                )
            )
        if mode == 'import_ddn':
            return invoke(
                lambda store, _proc: store.import_ddn(
                    project_id=project_id,
                    key=str(body.get('key') or ''),
                    kind=str(body.get('kind') or 'erd'),
                    title=str(body.get('title') or body.get('key') or ''),
                    ddn_or_workspace=(
                        body.get('workspace') or body.get('ddn_text') or ''
                    ),
                    actor_id=uid,
                    origin=str(body.get('origin') or 'import:file'),
                    loss_report=body.get('loss_report'),
                    observe_resources=bool(
                        body.get('observe_resources', False)
                    ),
                    note=str(body.get('note') or ''),
                )
            )
        if mode == 'create_erd':
            title = str(body.get('title') or body.get('key') or 'Data Model')
            ddn_text = build_four_level_erd_ddn(
                title=title,
                conceptual_entities=body.get('conceptual_entities'),
                logical_entities=body.get('logical_entities'),
                physical_tables=body.get('physical_tables'),
                deployment_nodes=body.get('deployment_nodes'),
                level_links=body.get('level_links'),
                extensions=body.get('extensions'),
            )
            return invoke(
                lambda store, _proc: store.create_design(
                    project_id=project_id,
                    key=str(body.get('key') or ''),
                    kind='erd',
                    title=title,
                    ddn_text=ddn_text,
                    actor_id=uid,
                    status=str(body.get('status') or 'draft'),
                    note=str(body.get('note') or ''),
                    origin=str(body.get('origin') or 'local'),
                    observe_resources=bool(
                        body.get('observe_resources', False)
                    ),
                )
            )
        return invoke(
            lambda store, _proc: store.create_design(
                project_id=project_id,
                key=str(body.get('key') or ''),
                kind=str(body.get('kind') or 'erd'),
                title=str(body.get('title') or body.get('key') or ''),
                ddn_text=str(body.get('ddn_text') or ''),
                actor_id=uid,
                status=str(body.get('status') or 'draft'),
                note=str(body.get('note') or ''),
                origin=str(body.get('origin') or 'local'),
                loss_report=body.get('loss_report'),
                observe_resources=bool(body.get('observe_resources', False)),
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>',
        methods=['GET', 'PUT', 'DELETE'],
    )
    @pga_login_required
    def design_detail(project_id: str, design_id: str):
        uid, role_ids = principal()
        if request.method == 'GET':
            _check_project_access(
                project_asset_service, uid, role_ids, project_id, 'viewer'
            )
            version = request.args.get('version', type=int)
            active_only = request.args.get('active_only') in ('1', 'true')
            view_id = request.args.get('view') or None
            tile_size = request.args.get('tile_size', default=1024, type=int)
            return invoke(
                lambda _store, proc: proc.open_session(
                    design_id,
                    version=version,
                    active_only=active_only,
                    view_id=view_id,
                    tile_size=tile_size,
                )
            )
        if request.method == 'DELETE':
            _check_project_access(
                project_asset_service, uid, role_ids, project_id, 'manager'
            )
            body = request.get_json(silent=True) or {}
            return invoke(
                lambda store, _proc: store.delete_design(
                    design_id,
                    expected_head_version=body.get('expected_head_version'),
                )
            )

        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'editor'
        )
        body = request.get_json(silent=True) or {}
        return invoke(
            lambda _store, proc: proc.save_from_ddn(
                design_id,
                expected_head_version=int(
                    body.get('expected_head_version') or 0
                ),
                ddn_or_workspace=(
                    body.get('workspace') or body.get('ddn_text') or ''
                ),
                actor_id=uid,
                pinned_positions=body.get('pinned_positions'),
                status=str(body.get('status') or 'draft'),
                note=str(body.get('note') or ''),
                origin=str(body.get('origin') or 'local'),
                loss_report=body.get('loss_report'),
                observe_resources=bool(body.get('observe_resources', False)),
                allow_conflict_note=bool(
                    body.get('allow_conflict_note', False)
                ),
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>/versions',
        methods=['GET'],
    )
    @pga_login_required
    def design_versions(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'viewer'
        )
        return invoke(lambda store, _proc: store.list_versions(design_id))

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>'
        '/versions/<int:version>/status',
        methods=['POST'],
    )
    @pga_login_required
    def version_status(project_id: str, design_id: str, version: int):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'editor'
        )
        body = request.get_json(silent=True) or {}
        return invoke(
            lambda store, _proc: store.advance_status(
                design_id,
                version,
                str(body.get('status') or ''),
                actor_id=uid,
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>'
        '/versions/<int:version>/accept',
        methods=['POST'],
    )
    @pga_login_required
    def version_accept(project_id: str, design_id: str, version: int):
        uid, role_ids = principal()
        access = _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'viewer'
        )
        has_perm = _ACCESS_RANK.get(access, 0) >= _ACCESS_RANK['manager']
        body = request.get_json(silent=True) or {}
        if body.get('has_scratchrobin_permission') is False:
            has_perm = False
        return invoke(
            lambda _store, proc: proc.accept_with_policy(
                design_id,
                version,
                actor_id=uid,
                has_scratchrobin_permission=has_perm,
                require_git_review=bool(body.get('require_git_review', False)),
                git_review_ref=body.get('git_review_ref'),
                comment=str(body.get('comment') or ''),
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>'
        '/versions/<int:version>/rollback',
        methods=['POST'],
    )
    @pga_login_required
    def version_rollback(project_id: str, design_id: str, version: int):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'manager'
        )
        body = request.get_json(silent=True) or {}
        return invoke(
            lambda store, _proc: store.rollback_to_version(
                design_id,
                version,
                actor_id=uid,
                comment=str(body.get('comment') or ''),
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>/branch',
        methods=['POST'],
    )
    @pga_login_required
    def design_branch(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'editor'
        )
        body = request.get_json(silent=True) or {}
        return invoke(
            lambda store, _proc: store.branch_draft_from_accepted(
                design_id,
                actor_id=uid,
                note=str(body.get('note') or ''),
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>'
        '/bindings/<binding_id>/confirm',
        methods=['POST'],
    )
    @pga_login_required
    def binding_confirm(
        project_id: str, design_id: str, binding_id: str
    ):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'editor'
        )
        body = request.get_json(silent=True) or {}
        return invoke(
            lambda store, _proc: store.confirm_binding(
                binding_id,
                actor_id=uid,
                new_target_ref=body.get('new_target_ref'),
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>/includes',
        methods=['POST'],
    )
    @pga_login_required
    def design_includes(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'editor'
        )
        body = request.get_json(silent=True) or {}
        return invoke(
            lambda _store, proc: proc.include_design(
                design_id,
                int(body.get('version') or 1),
                depends_on_design_id=str(
                    body.get('depends_on_design_id') or ''
                ),
                pin_version=bool(body.get('pin_version', True)),
                explicit_version=body.get('explicit_version'),
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>/layout',
        methods=['POST'],
    )
    @pga_login_required
    def design_layout(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'viewer'
        )
        body = request.get_json(silent=True) or {}

        def _compute(store: DesignStore, _proc: StoreDDNProcess):
            ddn_text = body.get('ddn_text')
            if not ddn_text:
                design = store.get_design(
                    design_id, version=body.get('version')
                )
                ddn_text = design['version']['ddn_text']
            return compute_server_layout(
                ddn_text,
                view_id=body.get('view_id'),
                pinned_positions=body.get('pinned_positions'),
                tile_size=int(body.get('tile_size') or 1024),
            )

        return invoke(_compute)

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>/export',
        methods=['GET'],
    )
    @pga_login_required
    def design_export(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'viewer'
        )
        version = request.args.get('version', type=int)
        entry = request.args.get('entry') or None
        view = request.args.get('view') or None
        return invoke(
            lambda store, _proc: store.export_ddn(
                design_id, version=version, entry=entry, view=view
            )
        )

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>/erd/convert',
        methods=['POST'],
    )
    @pga_login_required
    def erd_convert(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'editor'
        )
        body = request.get_json(silent=True) or {}

        def _convert(store: DesignStore, proc: StoreDDNProcess):
            design = store.get_design(
                design_id, version=body.get('version')
            )
            converted = convert_erd_design_engine(
                design['version']['ddn_text'],
                source_engine=str(body.get('source_engine') or 'sqlite'),
                target_engine=str(body.get('target_engine') or 'duckdb'),
                custom_type_map=body.get('custom_type_map'),
                loss_choices=body.get('loss_choices'),
                strict=bool(body.get('strict', True)),
            )
            if body.get('save_version'):
                saved = proc.save_from_ddn(
                    design_id,
                    expected_head_version=design['head_version'],
                    ddn_or_workspace=converted['ddn_text'],
                    actor_id=uid,
                    note=str(
                        body.get('note')
                        or f'Converted to {body.get("target_engine")}'
                    ),
                    origin='conversion:engine',
                    loss_report=converted['loss_report'],
                )
                return {**converted, 'saved': saved}
            return converted

        return invoke(_convert)

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>/erd/drift',
        methods=['POST'],
    )
    @pga_login_required
    def erd_drift(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'viewer'
        )
        body = request.get_json(silent=True) or {}

        def _drift(store: DesignStore, _proc: StoreDDNProcess):
            design = store.get_design(
                design_id, version=body.get('version')
            )
            if body.get('propose_change'):
                return propose_system_diagram_change(
                    design_id=design_id,
                    version=design['version']['version'],
                    element_id=str(body.get('element_id') or ''),
                    action=str(body.get('action') or ''),
                    parameters=body.get('parameters'),
                    actor_id=uid,
                )
            return compute_system_diagram_drift(
                design['version']['ddn_text'],
                body.get('live_nodes') or [],
            )

        return invoke(_drift)

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>/erd/model',
        methods=['POST'],
    )
    @pga_login_required
    def erd_model(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'editor'
        )
        body = request.get_json(silent=True) or {}

        def _save_model(store: DesignStore, proc: StoreDDNProcess):
            design = store.get_design(design_id)
            title = str(body.get('title') or design['title'])
            ddn_text = build_four_level_erd_ddn(
                title=title,
                conceptual_entities=body.get('conceptual_entities'),
                logical_entities=body.get('logical_entities'),
                physical_tables=body.get('physical_tables'),
                deployment_nodes=body.get('deployment_nodes'),
                level_links=body.get('level_links'),
                extensions=body.get('extensions'),
            )
            return proc.save_from_ddn(
                design_id,
                expected_head_version=int(
                    body.get('expected_head_version')
                    or design['head_version']
                ),
                ddn_or_workspace=ddn_text,
                actor_id=uid,
                pinned_positions=body.get('pinned_positions'),
                status=str(body.get('status') or 'draft'),
                note=str(body.get('note') or 'Updated ERD model'),
                observe_resources=bool(body.get('observe_resources', False)),
            )

        return invoke(_save_model)

    @api.route(
        '/cdeadmin/api/projects/<project_id>/designs/<design_id>'
        '/erd/alter-plan',
        methods=['POST'],
    )
    @pga_login_required
    def erd_alter_plan(project_id: str, design_id: str):
        uid, role_ids = principal()
        _check_project_access(
            project_asset_service, uid, role_ids, project_id, 'viewer'
        )
        body = request.get_json(silent=True) or {}
        return invoke(
            lambda store, _proc: preview_erd_alter_plan(
                store,
                design_id,
                base_version=body.get('base_version'),
                desired_version=body.get('desired_version'),
                selected_difference_ids=body.get('selected_difference_ids'),
                target_engine=str(body.get('target_engine') or 'sqlite'),
                catalog_snapshot=body.get('catalog_snapshot'),
                handoff_options=body.get('handoff_options'),
            )
        )

    app.register_blueprint(api)
