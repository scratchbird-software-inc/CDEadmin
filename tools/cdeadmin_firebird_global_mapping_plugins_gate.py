#!/usr/bin/env python3
"""FM-FB02-007: effective global mappings across Linux password plugins.

Windows/macOS teams must repeat with platform clients and UI; Windows must
add Win_Sspi identity contexts. This gate owns its entire security database.
"""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_password_gate import run, PLUGINS
from tools.cdeadmin_firebird_admin_mapping_gate import (
    ADMINISTRATION, _create_client, _route_arguments,
)


def verify(native, admin, route, accounts, evidence):
    client = _create_client(SimpleNamespace(acquire_secret=None))
    kind = 'global-authentication-mapping'
    checks, failures = [], []
    admin.execute_immediate('CREATE ROLE CDE_GLOBAL_PLUGIN_ROLE')
    admin.commit()

    def apply(operation, draft):
        plan = ADMINISTRATION.plan({
            '_provider_route': route, 'resource_kind': kind,
            'operation_id': operation, 'draft': draft,
            'target_resource': {'display_name': 'CDE_GLOBAL_PLUGIN'}})
        ADMINISTRATION.apply(client, plan, connection=admin)
        admin.commit()

    for plugin in PLUGINS:
        manager = 'Legacy_UserManager' if plugin == 'Legacy_Auth' else 'Srp'
        user, password = accounts[manager][0]
        selected = {**route, 'user': user, 'auth_plugin_list': plugin,
                    'wire_crypt': ('Enabled' if plugin == 'Legacy_Auth'
                                   else 'Required')}
        for target in ('USER', 'ROLE'):
            for wildcard in (False, True):
                created = False
                try:
                    apply('create', {
                        'name': 'CDE_GLOBAL_PLUGIN', 'using_mode': 'PLUGIN',
                        'plugin': plugin, 'from_type': 'USER',
                        'from_any': wildcard, 'from_name': user,
                        'to_type': target, 'to_name': (
                            'CDE_GLOBAL_PLUGIN_USER' if target == 'USER'
                            else 'CDE_GLOBAL_PLUGIN_ROLE')})
                    created = True
                    with native.connect(password=password, **_route_arguments(
                            selected, native)) as db:
                        with db.cursor() as cursor:
                            cursor.execute('SELECT CURRENT_USER, CURRENT_ROLE '
                                           'FROM RDB$DATABASE')
                            observed = tuple(v.strip() for v in
                                             cursor.fetchone())
                    expected = (('CDE_GLOBAL_PLUGIN_USER', 'NONE') if
                                target == 'USER' else
                                (user, 'CDE_GLOBAL_PLUGIN_ROLE'))
                    assert observed == expected
                    checks.append({'plugin': plugin, 'target': target,
                                   'wildcard': wildcard, 'identity': observed})
                except Exception as error:
                    # Error text can contain credentials; retain type/scope.
                    failures.append({'plugin': plugin, 'target': target,
                                     'wildcard': wildcard,
                                     'error_type': type(error).__name__})
                    if admin.main_transaction.is_active():
                        admin.rollback()
                finally:
                    if created:
                        apply('drop', {'confirmation': 'CDE_GLOBAL_PLUGIN'})
    admin.execute_immediate('DROP ROLE CDE_GLOBAL_PLUGIN_ROLE')
    admin.commit()
    (evidence / 'global-identities.json').write_text(json.dumps({
        'passed': len(checks) == 24 and not failures,
        'checks': checks, 'failures': failures}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.evidence_root, fixture_check=verify)
    identities = json.loads((args.evidence_root /
                             'global-identities.json').read_text())
    result['global_mapping_passed'] = identities['passed']
    result['complete'] = result['complete'] and identities['passed']
    (args.evidence_root / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['complete'] else 1)
