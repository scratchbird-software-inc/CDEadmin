import config
import json
import subprocess
from pathlib import Path
from pgadmin.cdeadmin.workspace.firebird_erd import build_diagram
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export


def row(kind, name, parent=None, **native):
    path = [parent, name] if parent else [name]
    return {'resource_id': kind + ':' + ':'.join(path), 'resource_kind': kind, 'display_name': name,
            'display_path': path, 'native': native}


def fixture():
    return [row('table', 'Child'), row('table', 'Parent'),
            row('column', 'Exact"A', 'Child', field_type=16, field_scale=0, position=0, not_null=1),
            row('column', 'ID', 'Parent', field_type=16, field_scale=0, position=0),
            row('index', 'FK_IDX', 'Child', segments=[{'field_name': 'Exact"A', 'position': 0}]),
            row('index', 'PK_IDX', 'Parent', segments=[{'field_name': 'ID', 'position': 0}]),
            row('constraint', 'FK_CHILD', 'Child', constraint_type='FOREIGN KEY', index_name='FK_IDX',
                referenced_relation='Parent', referenced_index='PK_IDX')]


def test_native_fields_and_fk_tuple_render_through_paired_runtime():
    result = build_export(fixture(), endpoint_id='engine', target_id='db', generation='g')
    diagram = result['diagram']
    assert diagram['foreign_keys'] == 1
    assert diagram['warnings'] == []
    source = diagram['snapshot']['files']['relations.ddn']
    assert 'datatype: "BIGINT"' in source and 'nullable: false;' in source
    assert 'nullable: true;' not in source
    runner = """
import runtime from './web/pgadmin/static/vendor/ddn/current/ddn.mjs';
let input='';for await(const x of process.stdin)input+=x;
const d=JSON.parse(input),w=runtime.createWorkspace(d.snapshot.files);
try {for(const v of d.views){const r=w.renderSync({entry:v.entry,view:v.id});
const errors=r.diagnostics.filter(x=>x.severity==='error');if(errors.length)throw Error(JSON.stringify(errors));
if(!r.svg.includes('Child') || !r.svg.includes('Parent'))throw Error('Missing native table labels');}
process.stdout.write('ok');} finally{w.destroy();}
"""
    process = subprocess.run(['node', '--input-type=module', '-e', runner],
        input=json.dumps(diagram), capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2], timeout=30)
    assert process.returncode == 0, process.stderr


def test_missing_foreign_target_is_disclosed_not_fabricated():
    rows = [item for item in fixture() if item['display_name'] != 'Parent']
    diagram = build_diagram(rows, {'endpoint_id': 'e', 'database_target_id': 'd'})
    assert diagram['foreign_keys'] == 0
    assert any('outside visible selection' in warning for warning in diagram['warnings'])


def test_view_membership_retains_exact_native_identities():
    rows = [row('table', 'T'+str(i)) for i in range(30)]
    diagram = build_diagram(rows, {'endpoint_id': 'e', 'database_target_id': 'd'})
    assert len(diagram['views']) == 2
    assert set(diagram['resource_mapping'].values()) == {item['resource_id'] for item in rows}


def test_arrays_without_visible_bounds_are_never_labeled_scalar():
    rows = [row('table', 'T'), row('column', 'A', 'T', field_type=8, field_scale=0,
            position=0, alteration={'array': True})]
    diagram = build_diagram(rows, {'endpoint_id': 'e', 'database_target_id': 'd'})
    source = diagram['snapshot']['files']['relations.ddn']
    assert 'shape: array;' in source
    assert 'array bounds unavailable' in source
    assert diagram['warnings'] == ['Array bounds unavailable: T.A']


def test_native_array_dimension_count_discloses_missing_bounds():
    rows = [row('table', 'T'), row('column', 'A', 'T', field_type=8,
            field_scale=0, position=0, dimensions='2', array_dimensions=[])]
    diagram = build_diagram(rows, {'endpoint_id': 'e', 'database_target_id': 'd'})
    assert diagram['warnings'] == ['Array bounds unavailable: T.A']
    assert 'shape: array;' in diagram['snapshot']['files']['relations.ddn']


def test_domain_nonnull_is_preserved_without_the_domain_branch():
    rows = [row('table', 'T'), row('column', 'A', 'T', field_type=8,
            field_scale=0, domain='Required', position=0, domain_not_null='1')]
    diagram = build_diagram(rows, {'endpoint_id': 'e', 'database_target_id': 'd'})
    assert 'nullable: false;' in diagram['snapshot']['files']['relations.ddn']
