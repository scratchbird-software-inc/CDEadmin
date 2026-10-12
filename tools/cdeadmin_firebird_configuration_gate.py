#!/usr/bin/env python3
"""Exact configuration discovery and native privilege visibility."""
import argparse
import json
import os
from pathlib import Path
import secrets
from unittest.mock import patch

from tools.cdeadmin_firebird_admin_mapping_gate import (
    _resources, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.providers.firebird import configuration


def inspect(connection, route):
    with connection.cursor() as query:
        query.execute(configuration.SQL)
        expected = {row[0]: row for row in query.fetchall()}
    assert set(expected) == set(configuration.KEYS)
    resources = _resources(connection, {'route': route})
    actual = {item['display_name']: item['native'] for item in resources
              if item['resource_kind'] == 'configuration'}
    assert set(actual) == set(expected)
    fields = ('config_id', 'value', 'default_value', 'explicitly_set',
              'value_source')
    for name, row in expected.items():
        assert tuple(actual[name][key] for key in fields) == row[1:]
    assert not any(item['resource_kind'] == 'plugin' for item in resources)
    return expected, actual


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'configuration.fdb'))
    limited_password = secrets.token_urlsafe(24)
    with admin.cursor() as query:
        query.execute("CREATE USER OWNED_CONFIG_LIMIT PASSWORD '" +
                      limited_password + "' USING PLUGIN Srp")
    admin.commit()
    checks = []
    with native.create_database(
            password=password, **_route_arguments(selected, native)) as owner:
        expected, actual = inspect(owner, selected)
        checks.append({'case': 'complete-native-configuration',
                       'count': len(actual), 'all_fields_exact': True})
        owner.rollback()
        original_cursor = owner.cursor

        class UnavailableConfigurationCursor:
            def __init__(self):
                self.inner = original_cursor()

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def execute(self, source, *arguments):
                if source == configuration.SQL:
                    raise RuntimeError('Owned unavailable catalog query')
                return self.inner.execute(source, *arguments)

        with patch.object(owner, 'cursor', UnavailableConfigurationCursor):
            unavailable = _resources(owner, {'route': selected})
        database = next(item['native'] for item in unavailable
                        if item['resource_kind'] == 'database')
        assert database['configuration_catalog']['available'] is False
        assert database['configuration_catalog']['visible_row_count'] is None
        assert any('configuration' in warning
                   for warning in database['catalog_warnings'])
        owner.rollback()
        checks.append({'case': 'unavailable-is-not-empty',
                       'native_other_catalogs_preserved': True})
        limited = dict(selected, user='OWNED_CONFIG_LIMIT')
        with native.connect(password=limited_password,
                            **_route_arguments(limited, native)) as connection:
            with connection.cursor() as query:
                query.execute(configuration.SQL)
                assert query.fetchall() == []
            resources = _resources(connection, {'route': limited})
            assert not any(item['resource_kind'] == 'configuration'
                           for item in resources)
            database = next(item['native'] for item in resources
                            if item['resource_kind'] == 'database')
            assert database['configuration_catalog']['visible_row_count'] == 0
            assert 'privileges' in database['configuration_catalog'][
                'empty_result_note']
            connection.rollback()
        checks.append({'case': 'native-principal-limited-visibility',
                       'no_privilege_escalation': True})
        with owner.cursor() as query:
            query.execute('CREATE ROLE CONFIG_READ SET SYSTEM PRIVILEGES '
                          'TO SELECT_ANY_OBJECT_IN_DATABASE')
            query.execute('GRANT CONFIG_READ TO USER OWNED_CONFIG_LIMIT')
        owner.commit()
        with native.connect(password=limited_password, **_route_arguments(
                dict(limited, role='CONFIG_READ'), native)) as connection:
            resources = _resources(connection, {'route': limited})
            observed = {item['display_name'] for item in resources
                        if item['resource_kind'] == 'configuration'}
            assert observed == set(expected)
            connection.rollback()
        checks.append({'case': 'native-system-privilege-admission',
                       'count': len(expected)})
    (evidence / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')


def embedded(native, admin, route, accounts, evidence, root):
    selected = {'attachment_mode': 'embedded', 'filesystem_root': str(root),
                'user': 'OWNED_LOCAL', 'database': str(root / 'config.fdb')}
    with native.create_database(**_route_arguments(selected, native)) as con:
        with con.cursor() as query:
            query.execute('SELECT MON$REMOTE_PROTOCOL,MON$SERVER_PID '
                          'FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID='
                          'CURRENT_CONNECTION')
            protocol, pid = query.fetchone()
        assert protocol is None and pid == os.getpid()
        expected, actual = inspect(con, selected)
        con.rollback()
    (evidence / 'checks.json').write_text(json.dumps({
        'count': len(actual), 'all_fields_exact': True,
        'same_process': True}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
        result = run_embedded(options.runtime, options.evidence,
                              fixture_check=embedded)
    else:
        result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
