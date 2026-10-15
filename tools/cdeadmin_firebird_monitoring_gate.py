#!/usr/bin/env python3
"""Qualify monitoring with a disposable database/user on a reference server."""

import argparse
import base64
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import sys
import threading
import time
import traceback
from types import ModuleType, SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.firebird.provider import (  # noqa: E402
    _create_client, _route_arguments,
)
from pgadmin.cdeadmin.providers.firebird.monitoring import FirebirdMonitor  # noqa: E402
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from pgadmin.cdeadmin.workspace.monitoring import (  # noqa: E402
    MonitoringPolicy, MonitoringRuntime,
)
from pgadmin.cdeadmin.workspace.monitoring_delegation import MonitoringGrant  # noqa: E402
from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyRing  # noqa: E402


def run(profiles):
    document = json.loads(profiles.read_text())
    profile = next(dict(p) for p in document['profiles'] if p['engine'] == 'firebird')
    profile.setdefault('host', document.get('host', '127.0.0.1'))
    password = profile.pop('password')
    identifier = uuid.uuid4().hex[:16].upper()
    profile['database'] = str(PurePosixPath(profile['database']).parent /
                              ('cde_monitor_' + identifier + '.fdb'))
    username = 'CDE_MON_' + identifier
    user_password = secrets.token_hex(24)
    route = {**profile, 'credential_reference_id': 'gate-admin',
             'principal_reference': 'gate-owner'}
    user_route = {**route, 'user': username, 'credential_reference_id': 'gate-user'}

    def acquire(reference, principal, purpose, kind):
        assert principal == 'gate-owner' and purpose == 'connect'
        assert kind == 'database_password'
        assert reference in ('gate-admin', 'gate-user')
        return SecretLease(password if reference == 'gate-admin' else user_password)

    permissions = SimpleNamespace(acquire_secret=acquire)
    owned = []
    result = {'status': 'failed', 'checks': [], 'fixture_removed': False,
              'temporary_user_removed': False, 'failures': []}
    database = None
    user_created = False
    runtime = MonitoringRuntime()
    grant = None
    # Configures the client library using the provider's ordinary factory.
    client = _create_client(permissions)
    owned.append(client)
    from firebird import driver

    try:
        database = driver.create_database(password=password,
                                          **_route_arguments(profile, driver))
        with database.cursor() as cursor:
            cursor.execute('CREATE TABLE MONITOR_GATE (ID INTEGER)')
            cursor.execute('CREATE USER ' + username +
                           " PASSWORD '" + user_password + "'")
        database.commit()
        user_created = True
        user = client._connect({'route': route})
        with user.cursor() as cursor:
            cursor.execute('INSERT INTO MONITOR_GATE VALUES (1)')
            cursor.execute('SELECT CURRENT_CONNECTION, CURRENT_TRANSACTION '
                           'FROM RDB$DATABASE')
            attachment, transaction = cursor.fetchone()
        held_cursor = user.cursor()
        held_cursor.execute('SELECT ID FROM MONITOR_GATE')
        monitor = FirebirdMonitor(permissions, route)
        owned.append(monitor)
        first = monitor.sample()
        assert first['status'] == 'available', first.get('error_type')
        assert first['collector']['attachment_id'] != str(attachment)
        assert first['collector']['transaction_id'] != str(transaction)
        assert first['transaction_refresh']['status'] == 'completed'
        rows = first['groups']['attachment_details']['values']['rows']
        assert any(row['attachment_id'] == str(attachment) for row in rows)
        assert all(row['attachment_id'] != first['collector']['attachment_id'] for row in rows)
        rows = first['groups']['transaction_details']['values']['rows']
        assert any(row['transaction_id'] == str(transaction) for row in rows)
        result['checks'].append('native-activity-identities-and-collector-exclusion')
        statement = next(row for row in first['groups']['statement_details']['values']['rows']
                         if row['attachment_id'] == str(attachment))
        request_detail = monitor.inspect_statement({**{key: statement[key] for key in (
            'statement_id', 'attachment_id', 'compiled_statement_id', 'timestamp')},
            'source_epoch': first['source_epoch']})
        assert request_detail['status'] == 'available'
        assert request_detail['call_stack']['status'] == 'available'
        assert 'MONITOR_GATE' in request_detail['sql_text']['value']
        held_cursor.close()
        result['checks'].append('native-request-plan-and-call-stack-inspection')
        compiled = first['groups']['compiled_details']['values']['rows']
        assert compiled, 'Native compiled inventory must observe the fixture statements'
        reference = {**compiled[0], 'kind': 'compiled',
                     'source_epoch': first['source_epoch']}
        inspected = monitor.inspect_statement(reference)
        assert inspected['status'] in ('available', 'gone')
        if inspected['status'] == 'available':
            assert inspected['identity']['compiled_statement_id'] == reference['compiled_statement_id']
            assert all(value['value'] is None or len(value['value']) <= 4096
                       for value in (inspected['sql_text'], inspected['explained_plan']))
        assert not monitor._connection.main_transaction.is_active()
        assert first['groups']['page_inventory']['status'] == 'available'
        assert first['groups']['schema_counts']['values']['rows']
        result['checks'].append('native-inventories-page-allocation-and-bounded-compiled-inspection')

        assert user.main_transaction.info.id == transaction
        assert not monitor._connection.main_transaction.is_active()
        result['checks'].append('separate-attachment-and-fresh-readonly-transaction')
        limited = FirebirdMonitor(permissions, user_route)
        owned.append(limited)
        visible = limited.sample()
        assert visible['status'] in ('available', 'partial'), visible.get('error_type')
        result['restricted_unavailable_groups'] = [name for name, group in visible['groups'].items()
                                                   if group['status'] != 'available']
        assert all('values' not in group for group in visible['groups'].values()
                   if group['status'] == 'unavailable')
        assert visible['coverage'] == 'visible-to-collector'
        assert visible['groups']['attachment_details']['values']['rows'] == []
        assert visible['groups']['transaction_details']['values']['rows'] == []
        assert visible['groups']['attachments']['values']['user'] == '0'
        second = monitor.sample()
        assert second['status'] == 'available'
        assert (second['collector']['transaction_id'] !=
                first['collector']['transaction_id'])
        assert (int(second['groups']['attachments']['values']['user']) ==
                int(first['groups']['attachments']['values']['user']) + 1)
        assert second['rates']['status'] == 'available'
        result['checks'].append(
            'restricted-user-visible-scope-and-fresh-attachment-count')
        with database.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM MONITOR_GATE')
            assert cursor.fetchone()[0] == 0
        database.rollback()
        with user.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM MONITOR_GATE')
            assert cursor.fetchone()[0] == 1
        assert user.main_transaction.info.id == transaction
        result['checks'].append('uncommitted-user-effect-not-committed-or-rolled-back')
        services = FirebirdMonitor(permissions, route, scope='server')
        owned.append(services)
        service_sample = services.sample()
        assert service_sample['status'] == 'available'
        result['engine_version'] = service_sample['groups']['version']['values']
        result['checks'].append('dedicated-service-manager-source')
        accounts = monitor.inspect_details('accounts', second['source_epoch'])
        assert accounts['status'] == 'available'
        assert any(row['user_name'].strip() == username for row in accounts['rows'])
        assert not monitor._connection.main_transaction.is_active()
        paths = services.inspect_details('server-paths', service_sample['source_epoch'])
        assert paths['status'] == 'available' and len(paths['rows']) == 4
        log = services.inspect_details('server-log', service_sample['source_epoch'])
        assert log['status'] == 'available' and len(log['text'].encode('utf8')) <= 65536
        assert len(services._client._connections) == 1
        result['checks'].append('authorized-account-path-log-inspection-and-owned-handle-release')
        collected = threading.Event()
        observations = []
        enabled = [True]

        def factory(_policy):
            background = grant.open_source(_policy)
            owned.append(background)

            class Source:
                def sample(self):
                    value = background.sample()
                    observations.append(value)
                    if len(observations) >= 2:
                        collected.set()
                    return value

                def close(self):
                    background.close()

            return Source()

        def authorize(_policy, purpose):
            return purpose != 'collect' or enabled[0]

        policy = MonitoringPolicy(1, 'native-gate', identifier, heartbeat_enabled=True)
        keys = WorkerKeyRing({
            'gate': base64.b64encode(os.urandom(32)).decode('ascii')}, 'gate')
        grant = MonitoringGrant.issue(
            policy, route, 'native-gate-generation', permissions, keys,
            lambda current, purpose, generation, digest:
                authorize(current, purpose),
            credentials={'username': username, 'password': user_password})
        rejected = MonitoringGrant.issue(
            policy, route, 'native-gate-generation', permissions, keys,
            lambda *_: True,
            credentials={'username': username, 'password': secrets.token_hex(24)})
        rejected_source = rejected.open_source(policy)
        owned.append(rejected_source)
        failed = rejected_source.sample()
        assert failed['status'] == 'unavailable'
        assert failed.get('transaction_refresh', {}).get('status') != 'completed'
        rejected_source.close()
        rejected.revoke()
        result['checks'].append('wrong-monitor-password-fails-without-refresh-success')
        revision = runtime.enable(policy, factory, authorize)
        assert runtime.enable(policy, factory, authorize) == revision
        assert collected.wait(12), 'No second background sample'
        assert all(s['status'] in ('available', 'partial') and
                   s['transaction_refresh']['status'] == 'completed' for s in observations)
        assert all(s['collector']['user'] == username for s in observations)
        assert grant.authentication['username'] != route['user']
        result['checks'].append('independent-monitoring-account-native-authentication')
        assert len(runtime.snapshot(policy, authorize)['samples']) == 2
        assert runtime.snapshot(policy, authorize)['heartbeat']['status'] == 'observed'
        result['checks'].append(
            'live-background-samples-without-viewers-and-coalescing')
        result['checks'].append('policy-heartbeat-from-completed-mga-refreshes')
        result['checks'].append('sealed-delegated-credentials-in-native-worker')
        enabled[0] = False
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if runtime.snapshot(policy, authorize)['state'] == 'authorization-denied':
                break
            time.sleep(0.1)
        assert runtime.snapshot(policy, authorize)['state'] == 'authorization-denied'
        assert runtime.disable(policy, authorize)
        result['checks'].append('revocation-stops-and-releases-native-collector')
        services.close()
        limited.close()
        monitor.close()
        assert user.main_transaction.info.id == transaction
        assert not database.is_closed()
        result['checks'].append('collector-shutdown-leaves-user-and-fixture-attached')
        user.rollback()
        result['status'] = 'passed'
    except Exception as error:
        result['failures'].append({
            'phase': 'qualification', 'type': type(error).__name__,
            'frames': [{'function': f.name, 'line': f.lineno}
                       for f in traceback.extract_tb(error.__traceback__)]})
    finally:
        if grant is not None:
            grant.revoke()
        if not runtime.close():
            result['failures'].append({
                'phase': 'runtime-release', 'type': 'Unconfirmed'})
        for item in reversed(owned):
            try:
                item.close()
            except Exception as error:
                result['failures'].append({
                    'phase': 'source-release', 'type': type(error).__name__})
        if database is not None:
            try:
                # Native client lifecycle release may also have invalidated a
                # fixture cursor. Cleanup uses a fresh administrative attachment.
                database.close()
                database = driver.connect(password=password,
                                          **_route_arguments(profile, driver))
                if user_created:
                    with database.cursor() as cursor:
                        cursor.execute('DROP USER ' + username)
                    database.commit()
                result['temporary_user_removed'] = True
                database.drop_database()
                result['fixture_removed'] = True
            except Exception as error:
                result['failures'].append({
                    'phase': 'fixture-cleanup', 'type': type(error).__name__,
                    'frames': [{'function': f.name, 'line': f.lineno}
                               for f in traceback.extract_tb(error.__traceback__)]})
        if result['failures']:
            result['status'] = 'failed'
            # Useful cleanup identifiers, never credentials.
            result['fixture_database'] = profile['database']
            result['fixture_user'] = username
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.profiles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
