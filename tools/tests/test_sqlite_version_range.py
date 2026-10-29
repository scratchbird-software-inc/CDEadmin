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


def test_contract_planned_work_without_proof_is_refused(monkeypatch):
    """Fail closed: off the reference runtime, a task needs live proof."""
    from pgadmin.cdeadmin.providers.sqlite import dialect_versions
    monkeypatch.setattr(dialect_versions, 'task_proven',
                        lambda _task, _version: False)
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


def test_task_proven_on_the_runtime_version_follows_contract():
    provider = _provider_reporting('3.45.1')
    try:
        state = provider.engine_contract_descriptor()['dialect']['state']
        assert state == 'passed'
        assert provider._visual_admin_operation_gate('table', 'create')
    finally:
        provider.close()


def test_task_failed_live_on_its_version_stays_refused():
    """FTS5 'flush' fails live on 3.35.0 (SQL logic error) and is not
    offered on runtimes served from the 3.35.0 table."""
    from pgadmin.cdeadmin.providers.sqlite.dialect_versions import (
        task_proven)
    assert not task_proven('visual_admin.fts-table.fts_flush', '3.35.0')
    assert not task_proven('visual_admin.fts-table.fts_flush', '3.44.2')
    assert task_proven('visual_admin.fts-table.fts_flush', '3.45.1')
    assert task_proven('visual_admin.table.create', '3.35.0')
    provider = _provider_reporting('3.40.1')
    try:
        assert provider._visual_admin_operation_gate(
            'fts-table', 'fts_flush') is False
    finally:
        provider.close()


def test_contract_planned_work_on_the_reference_runtime_follows_contract():
    provider = _provider_reporting('3.53.0')
    try:
        state = provider.engine_contract_descriptor()['dialect']['state']
        assert state == 'passed'
        assert provider._visual_admin_operation_gate('table', 'create')
    finally:
        provider.close()


def test_fresh_provider_gates_on_the_loaded_runtime_before_any_session():
    """An embedded provider knows its runtime before a session opens; the
    descriptor must not hide contract-planned work in that window."""
    from test_cdeadmin_relational_providers import Permissions, context
    from pgadmin.cdeadmin.providers.sqlite.dialect_versions import (
        task_proven)
    from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider
    provider = SQLiteProvider(context(PROFILE), Permissions(),
                              _create_client())
    try:
        assert getattr(provider, '_observed_version', None) is None
        state = provider.engine_contract_descriptor()['dialect']['state']
        assert state == 'passed'
        runtime = sqlite3.sqlite_version
        for kind, operation in (('table', 'create'),
                                ('fts-table', 'fts_flush')):
            expected = runtime == PROFILE.exact_version or task_proven(
                f'visual_admin.{kind}.{operation}', runtime)
            assert provider._visual_admin_operation_gate(
                kind, operation) is bool(expected), (kind, operation)
        flags = []

        def walk(value):
            if isinstance(value, dict):
                if 'operation_id' in value and 'native_supported' in value:
                    flags.append((value['operation_id'],
                                  value['native_supported']))
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(provider.visual_admin_descriptor())
        unsupported = {name for name, supported in flags if not supported}
        assert unsupported <= {'fts_flush'}
        assert ('fts_flush' in unsupported) == (not task_proven(
            'visual_admin.fts-table.fts_flush', runtime) and
            runtime != PROFILE.exact_version)
    finally:
        provider.close()
