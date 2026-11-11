##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""CDEadmin semantic model and cube workspace services."""

from .models import (
    SEMI_ADDITIVE_AGGREGATIONS,
    SemanticCompilationUnavailable,
    SemanticModelConflict,
    SemanticModelError,
    localize_model,
    public_model,
    validate_model,
    validate_query,
)
from .service import DatabaseSemanticModelRepository, SemanticModelService
from .profiles import SEMANTIC_PROFILE_SCHEMA, analytical_profile


APP_EXTENSION_KEY = 'cdeadmin_semantic_model_service'


def init_app(app):
    existing = app.extensions.get(APP_EXTENSION_KEY)
    if existing is not None:
        return existing
    service = SemanticModelService()
    app.extensions[APP_EXTENSION_KEY] = service
    return service


__all__ = (
    'DatabaseSemanticModelRepository', 'SEMI_ADDITIVE_AGGREGATIONS',
    'SemanticCompilationUnavailable',
    'SemanticModelConflict', 'SemanticModelError', 'SemanticModelService',
    'init_app', 'localize_model', 'public_model', 'validate_model',
    'validate_query', 'SEMANTIC_PROFILE_SCHEMA', 'analytical_profile',
)
