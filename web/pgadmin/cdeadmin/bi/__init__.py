##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""CDEadmin provider-neutral BI saved questions and collections."""

from .models import (
    BIConflict, BIError, validate_collection, validate_question,
)
from .service import BIService, DatabaseBIRepository


APP_EXTENSION_KEY = 'cdeadmin_bi_service'


def init_app(app, semantic_model_service):
    existing = app.extensions.get(APP_EXTENSION_KEY)
    if existing is not None:
        return existing
    service = BIService(semantic_model_service)
    app.extensions[APP_EXTENSION_KEY] = service
    return service


__all__ = (
    'BIConflict', 'BIError', 'BIService', 'DatabaseBIRepository',
    'init_app', 'validate_collection', 'validate_question',
)
