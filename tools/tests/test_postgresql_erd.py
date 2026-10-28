"""PostgreSQL relation identities, exact column facts and paired graph output."""
import json
import subprocess
from pathlib import Path

from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.postgresql_erd import build_diagram

ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = {'endpoint_id': 'ep', 'database_target_id': 'postgresql-database:42'}


def relation(oid, schema, kind='table'):
    return {'resource_id': f'postgresql:pg_class:{oid}', 'resource_kind': kind, 'display_name': 'same',
            'display_path': ['db', schema, 'same'], 'native': {'catalog': 'pg_class', 'oid': oid,
            'children': {'pg_attribute': [{'attnum': 1, 'attname': 'id', 'formatted_type': 'bigint', 'attnotnull': True},
                {'attnum': 2, 'attname': 'array', 'formatted_type': 'integer[]', 'attndims': 1, 'comment': 'native ü'}]}}}


def constraint(source, target):
    return {'resource_id': 'postgresql:pg_constraint:900', 'resource_kind': 'constraint',
            'display_name': 'fk', 'native': {'catalog': 'pg_constraint', 'catalog_row': {
                'contype': 'f', 'conrelid': str(source), 'confrelid': str(target), 'conkey': [1], 'confkey': [1]}}}


def test_equal_names_in_different_schemas_have_distinct_identity_and_edge():
    result = build_diagram([relation(100, 'a'), relation(200, 'b', 'partitioned-table'), constraint(100, 200)], PROVENANCE)
    assert result['foreign_keys'] == 1
    source = result['snapshot']['files']['relations.ddn']
    assert 'a.same [table]' in source and 'b.same [partitioned-table]' in source
    assert 'integer[]' in source and '""shape"": ""array""' in source and 'nullable false' in source
    assert 'fk (id) -> (id)' in source
    assert len(set(result['resource_mapping'].values())) == 7
    # Validate every actual view through the consumed public DDN runtime.
    checker=Path(__file__).with_name('check_firebird_catalog_ddn.mjs')
    process=subprocess.run(['node',str(checker)],input=json.dumps(result),text=True,capture_output=True,timeout=30)
    assert process.returncode==0,process.stderr


def test_outside_scope_target_is_not_replaced_by_same_name():
    result = build_diagram([relation(100, 'a'), relation(300, 'b'), constraint(100, 200)], PROVENANCE)
    assert result['foreign_keys'] == 0
    assert 'OID 200' in result['warnings'][0]


def test_projection_pagination_keeps_complete_source_and_stable_mapping():
    result = build_diagram([relation(i, 'a') for i in range(1, 60)], PROVENANCE)
    assert len(result['views']) == 3
    assert len(result['resource_mapping']) == 59 * 3
    assert result['snapshot']['files']['relations.ddn'].count(' as "table"') == 59


def test_page_expansion_is_one_hop_and_independent_of_edge_order():
    rows = [relation(i, 'a') for i in range(1, 151)]
    for number, row in enumerate(rows, 1):
        row['display_name'] = row['display_path'][-1] = f'T{number:03}'
    edges = []
    for i in range(1, 150):
        item = constraint(i, i + 1)
        item['resource_id'] = f'postgresql:pg_constraint:{900 + i}'
        edges.append(item)
    forward = build_diagram(rows + edges, PROVENANCE)
    reverse = build_diagram(rows + list(reversed(edges)), PROVENANCE)
    def first_view(result):
        source = result['snapshot']['files']['relations.ddn']
        return source[source.index('view "relations_1" '):source.index('view "relations_2" ')]
    assert first_view(forward) == first_view(reverse)
    assert first_view(forward).count('    use "n_') == 51
