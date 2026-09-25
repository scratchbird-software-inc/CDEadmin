#!/usr/bin/env python3
"""Verify production embedded attachment boundaries on an isolated local file.

Run in a fresh process with FIREBIRD, LD_LIBRARY_PATH and
CDEADMIN_FIREBIRD_CLIENT_LIBRARY selecting a complete Firebird 5 runtime.
No reference or demo database is opened or modified.
"""

import argparse
import json
import os
from pathlib import Path
import tempfile

if __package__:
    from .cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
else:
    from cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa

from pgadmin.cdeadmin.providers.firebird.provider import _create_client
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


class LocalPermissions:
    def require(self, name):
        if name not in {'embedded_runtime', 'filesystem'}:
            raise PermissionError(name)

    def acquire_secret(self, *_args):
        raise AssertionError('Embedded attachment requested a secret')


def run(root):
    results = {}
    with tempfile.TemporaryDirectory(
            prefix='owned-embedded-', dir=root) as tmp:
        path = str(Path(tmp) / 'owned.fdb')
        route = {'attachment_mode': 'embedded', 'database': path,
                 'filesystem_root': tmp, 'user': 'SYSDBA'}
        client = _create_client(LocalPermissions())
        connection = None
        try:
            if os.name == 'posix' and os.geteuid() != 0:
                denied = Path(tmp) / 'no-write'
                denied.mkdir(mode=0o500)
                denied_file = str(denied / 'denied.fdb')
                try:
                    arguments = client.config.database_create_arguments(
                        route, denied_file, {})
                    try:
                        unexpected = client.config.database_creator(
                            **arguments)
                    except client.module.DatabaseError:
                        assert not Path(denied_file).exists()
                        results['os_creation_permission_enforced'] = True
                    else:
                        unexpected.drop_database()
                        raise AssertionError('OS write restriction bypassed')
                finally:
                    denied.chmod(0o700)
            else:
                raise RuntimeError(
                    'This permission gate requires an unprivileged POSIX user')
            args = client.config.database_create_arguments(route, path, {})
            connection = client.config.database_creator(**args)
            cursor = connection.cursor()
            cursor.execute('CREATE TABLE OWNED_PRIVATE (ID INTEGER)')
            connection.commit()
            cursor.execute('INSERT INTO OWNED_PRIVATE VALUES (1)')
            connection.rollback()
            cursor.execute('SELECT COUNT(*) FROM OWNED_PRIVATE')
            assert cursor.fetchone() == (0,)
            cursor.execute('INSERT INTO OWNED_PRIVATE VALUES (2)')
            connection.commit()
            connection.close()
            connection = None
            results['create_commit_rollback'] = True
            connection = client.open_session({'route': route})
            cursor = connection.cursor()
            cursor.execute(
                "SELECT RDB$GET_CONTEXT('SYSTEM', 'ENGINE_VERSION'), "
                'MON$REMOTE_PROTOCOL FROM MON$ATTACHMENTS '
                'WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')
            version, protocol = cursor.fetchone()
            assert version == '5.0.4' and protocol is None
            cursor.execute('SELECT ID FROM OWNED_PRIVATE')
            assert cursor.fetchone() == (2,)
            connection.rollback()
            client.close_session(connection)
            connection = None
            results['production_attach_engine13_only'] = True
            connection = client.open_session({'route': {
                **route, 'user': 'OWNED_EMBEDDED_READER'}})
            cursor = connection.cursor()
            cursor.execute('SELECT CURRENT_USER FROM RDB$DATABASE')
            assert cursor.fetchone()[0].strip() == 'OWNED_EMBEDDED_READER'
            try:
                cursor.execute('SELECT ID FROM OWNED_PRIVATE')
            except client.module.DatabaseError:
                results['sql_privileges_enforced_without_password'] = True
            else:
                raise AssertionError('Embedded user bypassed SQL privileges')
            connection.rollback()
            client.close_session(connection)
            connection = None
            try:
                client.runtime_identity({'route': {
                    **route, 'database': None}})
            except RelationalClientError:
                results['server_scope_refused'] = True
            else:
                raise AssertionError('Embedded server scope was accepted')
            connection = client.open_session({'route': route})
            connection.drop_database()
            client.close_session(connection)
            connection = None
            assert not Path(path).exists()
            results['drop'] = True
        finally:
            if connection is not None and not connection.is_closed():
                connection.close()
            client.close()
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', required=True, type=Path)
    args = parser.parse_args()
    args.evidence_root.mkdir(parents=True, exist_ok=False)
    outcome = run(args.evidence_root)
    (args.evidence_root / 'result.json').write_text(
        json.dumps(outcome, indent=2) + '\n')
