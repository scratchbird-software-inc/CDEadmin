"""Batch 6 regression tests: DuckDB 1.5.2 proof provenance, descriptor completeness & OWNED BY durability."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService

ROOT = Path(__file__).resolve().parents[2]
QUAL_DIR = Path('/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/duckdb-qualification')
DONOR_DIR = Path('/home/dcalford/Sandbox/donor_release_acquisition/duckdb/1.5.2')


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_duckdb_descriptor_bundle_complete_for_all_16_kinds():
    bundle = UIDescriptorService().engine('duckdb')
    kinds = bundle['capabilities']['kinds']
    assert len(kinds) == 16
    for entry in kinds:
        assert entry.get('form'), f"Kind {entry['resource_kind']} missing form declaration"
    assert len(bundle['forms']) == 15
    assert all(op.get('status') == 'complete' for op in bundle['operations'])
    assert len(bundle['operations']) == 34


def test_duckdb_sequence_owned_by_reopen_non_durability(tmp_path):
    db_file = tmp_path / 'owned_by_probe.duckdb'
    c1 = duckdb.connect(str(db_file))
    c1.execute('CREATE TABLE t_owner (id INTEGER)')
    c1.execute('CREATE SEQUENCE s_owned START 5')
    c1.execute('ALTER SEQUENCE s_owned OWNED BY t_owner')
    assert c1.execute('SELECT count(*) FROM duckdb_dependencies()').fetchone()[0] == 1
    c1.execute('CHECKPOINT')
    c1.close()

    c2 = duckdb.connect(str(db_file))
    try:
        assert c2.execute('SELECT count(*) FROM duckdb_dependencies()').fetchone()[0] == 0
        c2.execute('DROP TABLE t_owner')
        assert c2.execute("SELECT count(*) FROM duckdb_sequences() WHERE sequence_name='s_owned'").fetchone()[0] == 1
    finally:
        c2.close()


@pytest.mark.skipif(not (QUAL_DIR / 'summary.json').is_file(), reason='Live qualification receipts not present')
def test_duckdb_manifest_and_dialect_proof_hashes_match_resolved_files():
    import _duckdb

    ext_so = Path(_duckdb.__file__).resolve()
    dialect = json.loads((ROOT / 'web/pgadmin/cdeadmin/providers/duckdb/duckdb_dialect_1_5_2.json').read_text())
    for rec in dialect['proof_records']:
        art = rec['artifact']
        if art == 'duckdb-1.5.2.tar.gz':
            target = DONOR_DIR / 'source-archive/duckdb-1.5.2.tar.gz'
        elif art == 'duckdb_dialect_inventory_1_5_2.json':
            target = ROOT / 'web/pgadmin/cdeadmin/providers/duckdb/duckdb_dialect_inventory_1_5_2.json'
        elif art == ext_so.name:
            target = ext_so
        elif art.startswith('duckdb-qualification/'):
            target = QUAL_DIR.parent / art
        else:
            raise AssertionError(f'Unexpected unresolved dialect proof artifact: {art}')
        assert target.is_file(), f'Missing proof artifact {target}'
        assert _sha256(target) == rec['sha256'], f'SHA-256 mismatch for {art}'

    metrics = json.loads((ROOT / 'web/pgadmin/cdeadmin/providers/duckdb/duckdb_metrics_1_5_2.json').read_text())
    for rec in metrics['classification_evidence']:
        art = rec['artifact']
        if art == 'duckdb-1.5.2.tar.gz':
            target = DONOR_DIR / 'source-archive/duckdb-1.5.2.tar.gz'
        elif art == 'duckdb_metrics_inventory_1_5_2.json':
            target = ROOT / 'web/pgadmin/cdeadmin/providers/duckdb/duckdb_metrics_inventory_1_5_2.json'
        elif art.startswith('duckdb-qualification/'):
            target = QUAL_DIR.parent / art
        else:
            raise AssertionError(f'Unexpected unresolved metrics proof artifact: {art}')
        assert target.is_file(), f'Missing metrics proof artifact {target}'
        assert _sha256(target) == rec['sha256'], f'SHA-256 mismatch for {art}'

    summary = json.loads((QUAL_DIR / 'summary.json').read_text())
    assert summary['all_passed'] is True
