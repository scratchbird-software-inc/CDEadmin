"""Regression and provenance unit tests for MariaDB Batch 8 final qualification."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import mariadb
import pytest

from pgadmin.cdeadmin.engine_contracts import (
    contract_descriptor,
    validate_dialect_contract,
    validate_metrics_contract,
)
from pgadmin.cdeadmin.providers.mysql_family import mariadb_administration
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_ADMINISTRATION,
    MARIADB_PROFILE,
)
from pgadmin.cdeadmin.workspace import firebird_catalog_import as catalog_import
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from ui_descriptor_roundtrip import engine_operations

ROOT = Path(__file__).resolve().parents[2]
PROVIDER_DIR = ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family'
PROOFS_DIR = Path('/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/mariadb-batch8-qualification/proofs')
DONOR_ARCHIVE = Path('/home/dcalford/Sandbox/donor_release_acquisition/mariadb/12.2.2/source-archive/mariadb-12.2.2.tar.gz')


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_mariadb_proof_provenance_and_task_reconciliation_are_100_percent_resolved():
    dialect = json.loads((PROVIDER_DIR / 'mariadb_dialect_12_2_2.json').read_text(encoding='utf-8'))
    metrics = json.loads((PROVIDER_DIR / 'mariadb_metrics_12_2_2.json').read_text(encoding='utf-8'))

    checked_dialect = validate_dialect_contract(
        dialect, MARIADB_PROFILE, MARIADB_ADMINISTRATION.dialect_task_ids()
    )
    checked_metrics = validate_metrics_contract(metrics, MARIADB_PROFILE)
    activation = contract_descriptor(
        MARIADB_PROFILE,
        'pgadmin.cdeadmin.providers.mysql_family.provider',
        MARIADB_ADMINISTRATION.dialect_task_ids(),
    )
    assert activation['state'] == 'passed'
    assert len(checked_dialect['task_templates']) == 129
    assert checked_metrics['authoritative_observation_count'] == 571
    assert checked_metrics['authoritative_metric_count'] == 43

    driver_init = Path(mariadb.__file__).resolve()

    def _resolve(artifact: str) -> Path:
        if artifact == 'mariadb-12.2.2.tar.gz':
            return DONOR_ARCHIVE
        if artifact == 'mariadb/__init__.py':
            return driver_init
        if (PROVIDER_DIR / artifact).is_file():
            return PROVIDER_DIR / artifact
        if (PROOFS_DIR / artifact).is_file():
            return PROOFS_DIR / artifact
        raise FileNotFoundError(artifact)

    declarations = [
        dialect['grammar_evidence'],
        dialect['complete_grammar_inventory'],
        *dialect['proof_records'],
        metrics['catalog_evidence'],
        *metrics['classification_evidence'],
    ]
    for decl in declarations:
        resolved = _resolve(decl['artifact'])
        assert resolved.is_file(), f'Missing proof artifact: {resolved}'
        assert _sha256(resolved) == decl['sha256'], (decl['artifact'], resolved)

    supported = MARIADB_ADMINISTRATION.dialect.supported
    inspect_ops = [f'{rk}.inspect' for rk, ops in supported.items() if 'inspect' in ops]
    non_inspect_ops = [
        f'visual_admin.{rk}.{op}'
        for rk, ops in supported.items()
        for op in ops
        if op != 'inspect'
    ]
    sql_tasks = set(MARIADB_ADMINISTRATION.dialect_task_ids())
    utility_ops = sorted(set(non_inspect_ops) - sql_tasks)
    assert len(inspect_ops) == 40
    assert len(non_inspect_ops) == 138
    assert len(sql_tasks) == 129
    assert len(utility_ops) == 9
    assert len(engine_operations('mariadb')) == 90


def test_catalog_reader_preserves_15s_deadline_and_recovers_semaphore_slots():
    src = inspect.getsource(catalog_import)
    assert 'timeout=15' in src
    assert 'BoundedSemaphore(2)' in src
    assert catalog_import._SLOTS._initial_value == 2

    valid_ddn = json.dumps(
        build_export(
            [],
            endpoint_id='ep-test',
            target_id='tgt-test',
            generation='1',
            include_system=False,
            refreshed=True,
            engine='mariadb',
        )['snapshot']
    )

    assert catalog_import._SLOTS.acquire(timeout=1)
    assert catalog_import._SLOTS.acquire(timeout=1)
    try:
        with pytest.raises(ValueError, match='Catalog reader is busy; retry shortly'):
            catalog_import.read_catalog(valid_ddn, engine='mariadb')
    finally:
        catalog_import._SLOTS.release()
        catalog_import._SLOTS.release()

    def _raise_timeout(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get('timeout', 15))

    with patch.object(catalog_import.subprocess, 'run', side_effect=_raise_timeout):
        with pytest.raises(ValueError, match='Catalog reader could not admit this document'):
            catalog_import.read_catalog(valid_ddn, engine='mariadb')

    # Both permits must be released after TimeoutExpired
    assert catalog_import._SLOTS.acquire(timeout=1)
    assert catalog_import._SLOTS.acquire(timeout=1)
    catalog_import._SLOTS.release()
    catalog_import._SLOTS.release()


def _sources(planned: dict) -> list[str]:
    return [stmt['source'] for stmt in planned['command_preview']['statements']]


def test_mariadb_batch8_compiler_and_contract_regressions():
    route = {'host': '127.0.0.1'}
    col_plan = MARIADB_ADMINISTRATION.plan({
        '_provider_route': route,
        'resource_kind': 'column',
        'operation_id': 'create',
        'draft': {'parent': 'demo_db', 'table': 'items', 'name': 'extra_col', 'data_type': 'VARCHAR(64)', 'nullable': False},
    })
    assert _sources(col_plan) == ['ALTER TABLE `items` ADD `extra_col` VARCHAR(64) NOT NULL']

    tbl_alter = MARIADB_ADMINISTRATION.plan({
        '_provider_route': route,
        'resource_kind': 'table',
        'operation_id': 'alter',
        'target_resource': {'resource_kind': 'table', 'display_name': 'items', 'display_path': ['demo_db', 'items']},
        'draft': {
            'add_columns': [{'name': 'added_c', 'type': 'INT', 'nullable': True}],
            'rename_columns': [{'from': 'old_c', 'to': 'new_c'}],
            'drop_columns': ['legacy_c'],
        },
    })
    stmt = '\n'.join(_sources(tbl_alter))
    assert 'ADD `added_c` INT' in stmt
    assert 'RENAME COLUMN `old_c` TO `new_c`' in stmt
    assert 'DROP COLUMN `legacy_c`' in stmt

    idx_alter = MARIADB_ADMINISTRATION.plan({
        '_provider_route': route,
        'resource_kind': 'index',
        'operation_id': 'alter',
        'target_resource': {'resource_kind': 'index', 'display_name': 'idx_items', 'display_path': ['demo_db', 'items', 'idx_items']},
        'draft': {'active': False},
    })
    assert 'ALTER INDEX `idx_items` IGNORED' in _sources(idx_alter)[0]

    seq_contract = mariadb_administration.field_contract({'resource_kind': 'sequence', 'operation_id': 'create'})
    fields_by_id = {f['field_id']: f for f in seq_contract['fields']}
    assert 'cycle' in fields_by_id and fields_by_id['cycle']['control'] == 'boolean'
    assert fields_by_id['start']['control'] == 'json' and fields_by_id['start']['json_type'] == 'scalar'

    seq_plan = MARIADB_ADMINISTRATION.plan({
        '_provider_route': route,
        'resource_kind': 'sequence',
        'operation_id': 'create',
        'draft': {
            'parent': 'demo_db',
            'name': 'seq_u64',
            'integer_type': 'BIGINT',
            'unsigned': True,
            'start': 100,
            'increment': 5,
            'maximum': '18446744073709551615',
            'cycle': True,
        },
    })
    seq_sql = _sources(seq_plan)[0]
    assert 'AS BIGINT UNSIGNED' in seq_sql
    assert 'START WITH 100' in seq_sql
    assert 'MAXVALUE 18446744073709551615' in seq_sql
    assert 'CYCLE' in seq_sql

    pub = MARIADB_ADMINISTRATION._public_row_values({
        'vec': b'\x00\x00\x80\x3f',
        'bit64': mariadb_administration._BitValue(b'\xaa\xf0\xaa\xf0\xaa\xf0\xaa\xf1'),
        'u64': 18446744073709551615,
        'tm6': '-838:59:59.123456',
        'nil': None,
    })
    assert pub['vec'] == {'encoding': 'base64', 'data': 'AACAPw==', 'byte_length': 4}
    assert pub['bit64'] == {'encoding': 'base64', 'data': 'qvCq8KrwqvE=', 'byte_length': 8}
    assert pub['u64'] == '18446744073709551615'
    assert pub['tm6'] == '-838:59:59.123456'
    assert pub['nil'] is None
