##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

import os
from flask import g


def register_migrate(app):
    """Register Flask-Migrate when a migration needs it.

    Flask-Migrate imports alembic, which a running application does not
    otherwise need, so it is not registered at startup (performance review
    2026-11-07).
    """
    if 'migrate' not in app.extensions:
        from flask_migrate import Migrate
        from pgadmin.model import db
        Migrate(app, db)


def db_upgrade(app, *, one_transaction=False):
    """Upgrade the configuration database to the latest revision.

    ``one_transaction`` builds a fresh SQLite database in a single
    transaction (see migrations/env.py). Without it SQLite commits every DDL
    statement on its own, and on a real disk the first build's 900 syncs took
    5.4 s at idle (performance review 2026-11-07).
    """
    from pgadmin.utils import u_encode, fs_encoding
    with app.app_context():
        migration_folder = os.path.join(
            os.path.dirname(os.path.realpath(u_encode(__file__, fs_encoding))),
            os.pardir, os.pardir,
            'migrations'
        )
        # Below line is a workaround to make Flask-Migrate>=4.0.6 work.
        g.x_arg = []
        g.migrate_in_one_transaction = one_transaction
        import flask_migrate
        register_migrate(app)
        flask_migrate.upgrade(migration_folder)
