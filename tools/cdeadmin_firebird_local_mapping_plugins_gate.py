#!/usr/bin/env python3
"""Effective USER/ROLE mappings for every shipped Linux password plugin.

Uses only the owned password fixture. Windows/macOS teams must repeat native
plugins and add platform-specific identity producers; no SSPI is simulated.
"""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

from tools.cdeadmin_firebird_password_gate import run as password_run
from tools.cdeadmin_firebird_admin_mapping_gate import (
    ADMINISTRATION, _create_client, _route_arguments,
)


def verify_plugin(route, plugin, users, evidence):
    import firebird.driver as native
    evidence.mkdir()
    wire = 'Enabled' if plugin == 'Legacy_Auth' else 'Required'
    selected = {**route, 'user': users[0][0], 'auth_plugin_list': plugin,
                'wire_crypt': wire,
                'database': '/var/lib/firebird/data/map_' +
                uuid.uuid4().hex + '.fdb'}
    client = _create_client(SimpleNamespace(acquire_secret=None))
    checks = []
    with native.create_database(password=users[0][1],
                                **_route_arguments(selected, native)) as owner:
        owner.execute_immediate('CREATE ROLE CDE_PLUGIN_ROLE')
        owner.commit()
        for target in ('USER', 'ROLE'):
            for wildcard in (False, True):
                name = 'CDE_PLUGIN_MAP'
                draft = {'name': name, 'using_mode': 'PLUGIN',
                         'plugin': plugin, 'from_type': 'USER',
                         'from_any': wildcard, 'from_name': users[0][0],
                         'to_type': target, 'to_name': (
                             'CDE_PLUGIN_USER' if target == 'USER'
                             else 'CDE_PLUGIN_ROLE')}
                plan = ADMINISTRATION.plan({
                    '_provider_route': selected,
                    'resource_kind': 'authentication-mapping',
                    'operation_id': 'create', 'draft': draft})
                ADMINISTRATION.apply(client, plan, connection=owner)
                owner.commit()
                arguments = _route_arguments(selected, native)
                with native.connect(password=users[0][1], **arguments) as db:
                    with db.cursor() as cursor:
                        cursor.execute('SELECT CURRENT_USER, CURRENT_ROLE '
                                       'FROM RDB$DATABASE')
                        identity = tuple(v.strip() for v in cursor.fetchone())
                        assert identity == (
                            ('CDE_PLUGIN_USER', 'NONE') if target == 'USER'
                            else (users[0][0], 'CDE_PLUGIN_ROLE'))
                drop = ADMINISTRATION.plan({
                    '_provider_route': selected,
                    'resource_kind': 'authentication-mapping',
                    'operation_id': 'drop', 'draft': {'confirmation': name},
                    'target_resource': {'display_name': name}})
                ADMINISTRATION.apply(client, drop, connection=owner)
                owner.commit()
                checks.append({'target': target, 'wildcard': wildcard,
                               'identity_observed': True})
    result = {'passed': len(checks) == 4, 'evidence_kind': 'native',
              'plugin': plugin, 'checks': checks}
    (evidence / 'native.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    args = parser.parse_args()
    result = password_run(args.evidence_root, verify_plugin)
    # The reused fixture calls its optional callback slot "browser". Rename
    # it in this native-only report so no browser verification is inferred.
    for case in result['cases']:
        case['local_mapping'] = case.pop('browser')
    (args.evidence_root / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['complete'] else 1)
