"""SQLite admission from the declared floor (owner direction, 2026-10-29)."""
import json
import sqlite3
from pathlib import Path

import pytest

# Reuse only the established package bootstrap, not a fake SQLite driver.
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import PROFILE, _create_client
from pgadmin.cdeadmin.sdk import PilotProviderError, RelationalClientError

DESCRIPTOR = (Path(__file__).resolve().parents[2] /
              'web/pgadmin/cdeadmin/ui_descriptors/sqlite/capabilities.json')


def test_floor_and_tested_versions_come_from_the_descriptor():
    declared = json.loads(DESCRIPTOR.read_text())['version_range']
    assert PROFILE.minimum_version == declared['minimum'] == '3.35.0'
    assert PROFILE.exact_version == '3.53.0'
    assert set(PROFILE.tested_versions) <= set(declared['tested'])
    assert PROFILE.version_requirement == '>=3.35.0'


@pytest.mark.parametrize('version', ['3.35.0', '3.45.1', '3.53.0', '3.53.1',
                                     '3.60.0', '4.0.0'])
def test_versions_at_or_above_the_floor_are_admitted(version):
    assert PROFILE.accepts_runtime_version(version)


@pytest.mark.parametrize('version', ['3.34.1', '3.8.11', '2.8.17', '', 'x.y'])
def test_versions_below_the_floor_or_malformed_are_refused(version):
    assert not PROFILE.accepts_runtime_version(version)


@pytest.mark.parametrize('version,status', [
    ('3.53.0', 'reference'),
    ('3.45.1', 'untested_in_range'),
    ('3.35.0', 'untested_in_range'),
    ('3.53.1', 'newer_than_tracked'),
    ('3.60.0', 'newer_than_tracked'),
])
def test_version_support_status(version, status):
    support = PROFILE.version_support(version)
    assert support['status'] == status
    assert support['requirement'] == '>=3.35.0'
    assert support['reference_version'] == '3.53.0'
    assert support['observed_version'] == version


def test_tested_versions_outside_the_range_are_rejected():
    from dataclasses import replace
    with pytest.raises(PilotProviderError):
        replace(PROFILE, tested_versions=('3.34.1',))
    with pytest.raises(PilotProviderError):
        replace(PROFILE, minimum_version=None, tested_versions=('3.45.1',))


def test_running_runtime_is_admitted_and_reported(tmp_path):
    """Real driver against whatever SQLite this process loaded."""
    client = _create_client()
    try:
        identity = client.runtime_identity({'route': {
            'database': str(tmp_path / 'range.sqlite'),
            'filesystem_root': str(tmp_path)}})
        assert identity['version'] == sqlite3.sqlite_version
        assert PROFILE.version_support(identity['version'])['status'] in {
            'reference', 'tested', 'untested_in_range', 'newer_than_tracked'}
    finally:
        client.close()


def test_runtime_below_the_floor_is_refused_with_the_range(
        monkeypatch, tmp_path):
    client = _create_client()
    try:
        monkeypatch.setattr(client.module, 'sqlite_version', '3.34.1')
        with pytest.raises(RelationalClientError,
                           match=r'3\.34\.1.*>=3\.35\.0'):
            client.open_session({'route': {
                'database': str(tmp_path / 'old.sqlite'),
                'filesystem_root': str(tmp_path)}})
    finally:
        client.close()


def _provider_reporting(version):
    from test_cdeadmin_relational_providers import Permissions, context
    from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider
    client = _create_client()
    original = client.runtime_identity

    def identity(*args, **kwargs):
        return {**original(*args, **kwargs), 'version': version}

    client.runtime_identity = identity
    provider = SQLiteProvider(context(PROFILE), Permissions(), client)
    provider.open_session({'route': {
        'database': ':memory:', 'allow_memory': True, 'route_id': 'local'}})
    return provider


def test_contract_planned_work_is_refused_off_the_reference_runtime():
    """Fail closed: the 3.53.0 contract does not cover other versions."""
    assert PROFILE.dialect_contract_id == 'sqlite.dialect.3.53.0.v1'
    provider = _provider_reporting('3.45.1')
    try:
        assert provider._visual_admin_operation_gate('table', 'create') is (
            False)
        # Work that emits no generated dialect SQL is not affected.
        requires = provider.client.admin_operation_requires_dialect
        assert not requires('database', 'inspect')
        assert provider._visual_admin_operation_gate('database', 'inspect')
    finally:
        provider.close()


def test_contract_planned_work_on_the_reference_runtime_follows_contract():
    provider = _provider_reporting('3.53.0')
    try:
        state = provider.engine_contract_descriptor()['dialect']['state']
        assert provider._visual_admin_operation_gate('table', 'create') is (
            state == 'passed')
    finally:
        provider.close()
