##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for engine connector, CDE server, and database statistics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(WEB / 'pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.server_statistics import (  # noqa: E402
    AUTH_STATS_MESSAGE,
    build_connector_statistics,
    build_endpoint_statistics,
    firebird_client_statistics,
)


def _fake_firebird_server(verified=True):
    route = SimpleNamespace(
        id=1,
        priority=1,
        configuration=json.dumps({
            'host': 'localhost',
            'port': 53050,
            'protocol': 'INET',
        }),
    )
    runtime = SimpleNamespace(
        verification_state='verified' if verified else 'unverified',
        verified_runtime_version='5.0.4' if verified else None,
    )
    endpoint = SimpleNamespace(
        provider_id='org.cdeadmin.firebird',
        provider_version='5.0.4',
        routes=[route],
        runtime_identity=runtime,
    )
    return SimpleNamespace(
        id=7,
        name='Firebird 5.0 on localhost',
        host='localhost',
        port=53050,
        shared=False,
        user_id=1,
        endpoint_profile=endpoint,
    )


def test_live_firebird_client_library_statistics_available_without_connection():
    rows = firebird_client_statistics()
    if rows:
        by_name = {r['Statistic']: r['Value'] for r in rows}
        assert 'Firebird' in by_name.get('Client version', '')
        assert 'Client library' in by_name


def test_connector_statistics_includes_client_version_and_auth_guidance():
    payload = build_connector_statistics(
        'firebird',
        'Firebird',
        {'available': True, 'ports': [3050], 'listening_ports': [3050]},
        client_stats_fn=lambda: [
            {'Statistic': 'Client version', 'Value': 'LI-V5.0.4.1701 Firebird 5.0'},
        ],
    )
    rows = {r['Statistic']: r['Value'] for r in payload['rows']}
    assert rows['Engine'] == 'Firebird'
    assert rows['Client version'] == 'LI-V5.0.4.1701 Firebird 5.0'
    assert rows['Server statistics'] == AUTH_STATS_MESSAGE


def test_firebird_server_statistics_without_database_connection():
    server = _fake_firebird_server(verified=True)
    profile = {
        'workflow': 'provider_endpoint',
        'engine_id': 'firebird',
        'profile_id': 'firebird-native',
        'engine_display_name': 'Firebird',
    }
    calls = []

    def loader(srv, db_target):
        calls.append((srv, db_target))
        return {
            'resources': [
                {
                    'resource_id': 'server:Firebird',
                    'resource_kind': 'server',
                    'display_name': 'Firebird',
                    'native': {
                        'version': 'LI-V5.0.4.1701 Firebird 5.0',
                        'architecture': 'SuperServer',
                        'home_directory': '/opt/firebird',
                        'connection_count': 2,
                        'scope': 'server',
                    },
                },
                {
                    'resource_id': 'metric:security_db',
                    'resource_kind': 'metric',
                    'display_name': 'security_database',
                    'native': {
                        'native_name': 'security_database',
                        'description': 'security database path',
                        'value': '/opt/firebird/security5.fdb',
                        'observation_error': None,
                    },
                },
            ],
        }

    data, info = build_endpoint_statistics(
        server,
        profile,
        database_target_id=None,
        snapshot_loader=loader,
        client_stats_fn=lambda: [
            {'Statistic': 'Client version', 'Value': 'LI-V5.0.4.1701 Firebird 5.0'},
            {'Statistic': 'Client library', 'Value': 'libfbclient.so.2'},
        ],
    )
    assert calls == [(server, None)]
    assert info is None
    rows = {r['Statistic']: r['Value'] for r in data['rows']}
    assert rows['Client version'] == 'LI-V5.0.4.1701 Firebird 5.0'
    assert rows['Client library'] == 'libfbclient.so.2'
    assert rows['Server version'] == 'LI-V5.0.4.1701 Firebird 5.0'
    assert rows['Server architecture'] == 'SuperServer'
    assert rows['Server home directory'] == '/opt/firebird'
    assert rows['Active attachments'] == '2'
    assert rows['Security database'] == '/opt/firebird/security5.fdb'
    assert AUTH_STATS_MESSAGE not in rows.values()


def test_unverified_server_statistics_returns_auth_guidance_and_firebird_client_info():
    fb_server = _fake_firebird_server(verified=False)
    fb_profile = {
        'workflow': 'provider_endpoint',
        'engine_id': 'firebird',
        'profile_id': 'firebird-native',
        'engine_display_name': 'Firebird',
    }
    fb_data, fb_info = build_endpoint_statistics(
        fb_server,
        fb_profile,
        database_target_id=None,
        snapshot_loader=None,
        client_stats_fn=lambda: [
            {'Statistic': 'Client version', 'Value': 'LI-V5.0.4.1701 Firebird 5.0'},
        ],
    )
    assert fb_info is None
    fb_rows = {r['Statistic']: r['Value'] for r in fb_data['rows']}
    assert fb_rows['Client version'] == 'LI-V5.0.4.1701 Firebird 5.0'
    assert fb_rows['Server statistics'] == AUTH_STATS_MESSAGE

    mysql_server = _fake_firebird_server(verified=False)
    mysql_profile = {
        'workflow': 'provider_endpoint',
        'engine_id': 'mysql',
        'profile_id': 'mysql-native',
        'engine_display_name': 'MySQL',
    }
    my_data, my_info = build_endpoint_statistics(
        mysql_server,
        mysql_profile,
        database_target_id=None,
        snapshot_loader=None,
    )
    assert my_data is None
    assert my_info == AUTH_STATS_MESSAGE


def test_database_target_statistics_extracts_mon_database_metrics():
    server = _fake_firebird_server(verified=True)
    profile = {
        'workflow': 'provider_endpoint',
        'engine_id': 'firebird',
        'profile_id': 'firebird-native',
        'engine_display_name': 'Firebird',
    }
    calls = []

    def loader(srv, db_target):
        calls.append((srv, db_target))
        return {
            'resources': [
                {
                    'resource_id': 'database:employee',
                    'resource_kind': 'database',
                    'display_name': 'employee',
                    'native': {
                        'database_name': '/var/lib/firebird/employee.fdb',
                        'ods_major': '13',
                        'ods_minor': '1',
                        'sql_dialect': '3',
                        'page_size': '8192',
                        'allocated_pages': '412',
                    },
                },
            ],
        }

    data, info = build_endpoint_statistics(
        server,
        profile,
        database_target_id='emp_1',
        snapshot_loader=loader,
        client_stats_fn=list,
    )
    assert calls == [(server, 'emp_1')]
    assert info is None
    rows = {r['Statistic']: r['Value'] for r in data['rows']}
    assert rows['ODS version'] == '13.1'
    assert rows['SQL dialect'] == '3'
    assert rows['Page size (bytes)'] == '8192'
    assert rows['Allocated pages'] == '412'
