##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""ScratchRobin versioned DDN design store (designs.db)."""

from .ddn_elements import (
    assign_uuid7_element_ids,
    ddn_text_to_workspace,
    inspect_ddn_text,
    sha256_text,
    workspace_to_ddn_text,
)
from .identifiers import deterministic_uuid7, is_uuid7, uuid7
from .schema import (
    BINDING_STATES,
    DESIGN_KINDS,
    GIT_SYNC_STATES,
    MAX_BLOB_BYTES,
    SAVE_POINT_STATUSES,
    TARGET_KINDS,
    apply_schema,
)
from .routes import (
    PROCESS_EXTENSION_KEY,
    init_app as init_routes_app,
    process_for_app,
)
from .service import (
    APP_EXTENSION_KEY,
    DesignStore,
    DesignStoreConflict,
    DesignStoreError,
    DesignStoreForbidden,
    DesignStoreNotFound,
    default_store_path,
    init_app,
    store_for_app,
)
from .shared_ddn import (
    DEFAULT_LOGICAL_TYPE_MAPS,
    DESTRUCTIVE_METADATA_WARNING,
    DIALECT_EXPANSION_ORDER,
    ERD_LEVELS,
    GLOBAL_TILE_CACHE,
    LOGICAL_TYPES,
    ServerTileCache,
    StoreDDNProcess,
    apply_layout_to_ddn_text,
    build_four_level_erd_ddn,
    compute_server_layout,
    compute_system_diagram_drift,
    convert_erd_design_engine,
    copy_type_map,
    normalize_to_logical_type,
    preview_erd_alter_plan,
    propose_system_diagram_change,
)

__all__ = (
    'APP_EXTENSION_KEY',
    'BINDING_STATES',
    'DEFAULT_LOGICAL_TYPE_MAPS',
    'DESIGN_KINDS',
    'DESTRUCTIVE_METADATA_WARNING',
    'DIALECT_EXPANSION_ORDER',
    'ERD_LEVELS',
    'GIT_SYNC_STATES',
    'GLOBAL_TILE_CACHE',
    'LOGICAL_TYPES',
    'MAX_BLOB_BYTES',
    'PROCESS_EXTENSION_KEY',
    'SAVE_POINT_STATUSES',
    'TARGET_KINDS',
    'DesignStore',
    'DesignStoreConflict',
    'DesignStoreError',
    'DesignStoreForbidden',
    'DesignStoreNotFound',
    'ServerTileCache',
    'StoreDDNProcess',
    'apply_layout_to_ddn_text',
    'apply_schema',
    'assign_uuid7_element_ids',
    'build_four_level_erd_ddn',
    'compute_server_layout',
    'compute_system_diagram_drift',
    'convert_erd_design_engine',
    'copy_type_map',
    'ddn_text_to_workspace',
    'default_store_path',
    'deterministic_uuid7',
    'init_app',
    'init_routes_app',
    'inspect_ddn_text',
    'is_uuid7',
    'normalize_to_logical_type',
    'preview_erd_alter_plan',
    'process_for_app',
    'propose_system_diagram_change',
    'sha256_text',
    'store_for_app',
    'uuid7',
    'workspace_to_ddn_text',
)
