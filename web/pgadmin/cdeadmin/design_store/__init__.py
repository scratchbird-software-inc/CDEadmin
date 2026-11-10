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

__all__ = (
    'APP_EXTENSION_KEY',
    'BINDING_STATES',
    'DESIGN_KINDS',
    'GIT_SYNC_STATES',
    'MAX_BLOB_BYTES',
    'SAVE_POINT_STATUSES',
    'TARGET_KINDS',
    'DesignStore',
    'DesignStoreConflict',
    'DesignStoreError',
    'DesignStoreForbidden',
    'DesignStoreNotFound',
    'apply_schema',
    'assign_uuid7_element_ids',
    'ddn_text_to_workspace',
    'default_store_path',
    'deterministic_uuid7',
    'init_app',
    'inspect_ddn_text',
    'is_uuid7',
    'sha256_text',
    'store_for_app',
    'uuid7',
    'workspace_to_ddn_text',
)
