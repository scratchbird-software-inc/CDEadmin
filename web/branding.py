##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

##########################################################################
# Application branding
##########################################################################

# Product identity. The copyright below is retained from the pgAdmin 4 code
# base under the PostgreSQL Licence; see the repository NOTICE file for the
# hard-fork statement and complete attribution.
# Owner direction 2026-11-07: the product is ScratchRobin, short name Robin
# (as ScratchBird's is Bird). "CDE admin" names the class of product: a
# console that administers many different types of engines and offers
# unified cross-engine tools, producing results that one engine alone, or a
# set of specialised single-engine tools, would not. CDE stands for
# convergent data engine. CDEadmin is also the repository name; the cdeadmin
# directory and namespace names below are kept.
APP_NAME = 'ScratchRobin'
APP_DISPLAY_SHORT_NAME = 'Robin'
APP_ICON = 'fa fa-database'

# To help define the configuration directory and data directory
APP_SHORT_NAME = 'cdeadmin'
APP_PATH = 'cdeadmin'
APP_WIN_PATH = 'CDEadmin'

# Copyright string for display in the app
APP_COPYRIGHT = (
    'ScratchRobin, a hard fork derived from pgAdmin 4; '
    'Copyright (C) 2013 - 2026, The pgAdmin Development Team'
)

# User ID (email address) to use for the default user in desktop mode.
# The default should be fine here, as it's not exposed in the app.
APP_DEFAULT_EMAIL = 'cdeadmin@localhost'
