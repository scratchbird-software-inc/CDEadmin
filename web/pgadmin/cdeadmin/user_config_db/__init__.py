##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Encrypted UserConfigurationDatabase backed by FirebirdSQL Embedded."""

from .service import (
    UserConfigAuthError,
    UserConfigKeyError,
    UserConfigLockedError,
    UserConfigurationDatabase,
    consume_desktop_handoff_ticket,
    ensure_flask_security_user_for_vault_user,
    get_user_config_db,
    init_user_config_db_app,
    mint_desktop_handoff_ticket,
    normalize_column_display_prefs,
    reset_default_user_config_db_for_tests,
    sync_runtime_orm_to_user_config_db,
)

__all__ = [
    'UserConfigAuthError',
    'UserConfigKeyError',
    'UserConfigLockedError',
    'UserConfigurationDatabase',
    'consume_desktop_handoff_ticket',
    'ensure_flask_security_user_for_vault_user',
    'get_user_config_db',
    'init_user_config_db_app',
    'mint_desktop_handoff_ticket',
    'normalize_column_display_prefs',
    'reset_default_user_config_db_for_tests',
    'sync_runtime_orm_to_user_config_db',
]
