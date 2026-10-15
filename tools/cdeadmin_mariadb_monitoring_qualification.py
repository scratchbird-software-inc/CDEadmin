"""Qualify dedicated native MariaDB probes without interactive finality effects."""
import argparse
import json
from pathlib import Path
import secrets
from types import SimpleNamespace

from tools.cdeadmin_mariadb_driver_gate import run
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.mariadb_monitoring import MariaDBMonitor


def qualify(route, evidence, *, password=None):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': []}
    owner = mariadb.connect(**route, **({'password': password} if password is not None else {}))
    schema = 'owned_monitor_' + secrets.token_hex(8)
    username = 'monitor_' + secrets.token_hex(6)
    role = 'monitor_role_' + secrets.token_hex(6)
    account_password = secrets.token_urlsafe(32)
    monitors = []
    interactive = None
    cursor = owner.cursor()
    try:
        cursor.execute(f'CREATE DATABASE `{schema}`')
        cursor.execute(f'CREATE TABLE `{schema}`.pending (id INT) ENGINE=InnoDB')
        interactive = mariadb.connect(**route, database=schema, autocommit=False,
            **({'password': password} if password is not None else {}))
        with interactive.cursor() as pending:
            pending.execute('INSERT INTO pending VALUES (1)')
        native_route, permissions = provider_access(route, password)
        monitor = MariaDBMonitor(permissions, {**native_route, 'database': schema})
        monitors.append(monitor)
        first, second = monitor.sample(), monitor.sample()
        for sample in (first, second):
            assert sample['transaction_completed'], sample
            assert sample['identity']['database_name'] == schema
            assert sample['identity']['version'].startswith('12.2.2-MariaDB')
            assert sample['identity']['server_uid']
            assert sample['identity']['collector_id'] != str(interactive.connection_id)
            for name in ('status', 'settings', 'storage', 'activity', 'replication'):
                assert sample['groups'][name]['status'] == 'available', (name, sample['groups'][name])
        assert second['rates']['status'] == 'available', second['rates']
        assert interactive.server_status & 1
        with owner.cursor() as observer:
            observer.execute(f'SELECT COUNT(*) FROM `{schema}`.pending')
            assert observer.fetchone()[0] == 0
        owner.rollback()
        assert not monitor._connection.server_status & 1
        proof['checks'].append('independent_native_database_probes_preserve_pending_work')
        proof['checks'].append('native_server_uid_and_exact_counter_rates')
        server = MariaDBMonitor(permissions, {**native_route, 'database': None}, scope='server')
        monitors.append(server)
        observed = server.sample()
        assert observed['transaction_completed'], observed
        assert observed['identity']['database_name'] is None
        assert observed['service_probe']['status'] == 'completed'
        proof['checks'].append('server_scope_without_fictitious_database')
        cursor.execute(f"CREATE USER '{username}'@'%' IDENTIFIED BY ?", (account_password,))
        cursor.execute(f"GRANT SELECT ON `{schema}`.* TO '{username}'@'%'")
        restricted_route, restricted_permissions = provider_access({**route, 'user': username}, account_password)
        restricted = MariaDBMonitor(restricted_permissions, {**restricted_route, 'database': schema})
        monitors.append(restricted)
        limited = restricted.sample()
        assert limited['transaction_completed'], limited
        assert limited['groups']['replication']['status'] == 'unavailable'
        assert limited['groups']['replication']['error_code'] in {1227, 1142}
        assert limited['identity']['account'].startswith(username + '@')
        assert limited['identity']['collector_id'] != first['identity']['collector_id']
        assert account_password not in json.dumps(limited)
        proof['checks'].append('dedicated_restricted_account_and_denied_replication_gap')
        cursor.execute(f"REVOKE SELECT ON `{schema}`.* FROM '{username}'@'%'")
        cursor.execute(f'CREATE ROLE `{role}`')
        cursor.execute(f'GRANT SELECT ON `{schema}`.* TO `{role}`')
        cursor.execute(f"GRANT `{role}` TO '{username}'@'%'")
        role_monitor = MariaDBMonitor(restricted_permissions,
            {**restricted_route, 'database': schema, 'role': role})
        monitors.append(role_monitor)
        role_sample = role_monitor.sample()
        assert role_sample['transaction_completed'], role_sample
        assert role_sample['groups']['storage']['status'] == 'available'
        assert role_sample['identity']['database_name'] == schema
        assert role_sample['identity']['account'].startswith(username + '@')
        assert account_password not in json.dumps(role_sample)
        proof['checks'].append('dedicated_role_activated_before_database_selection')
        proof['native_version'] = first['identity']['version']
        proof['complete'] = True
    finally:
        for monitor in monitors:
            monitor.close()
        if interactive is not None:
            interactive.rollback()
            interactive.close()
        cursor.execute(f"DROP USER IF EXISTS '{username}'@'%'")
        cursor.execute(f'DROP ROLE IF EXISTS `{role}`')
        cursor.execute(f'DROP DATABASE IF EXISTS `{schema}`')
        cursor.close()
        owner.close()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run(options.image, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)
