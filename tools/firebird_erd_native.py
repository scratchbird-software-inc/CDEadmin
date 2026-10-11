"""Render relational DDN from a real Firebird catalog with composite keys."""
import json
from pathlib import Path
import subprocess


def qualify(connection, evidence):
    from pgadmin.cdeadmin.providers.firebird.provider import _resources
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE ERD_PARENT (A INTEGER, B INTEGER, PRIMARY KEY (A,B))')
        cursor.execute('CREATE DOMAIN ERD_NONNULL AS INTEGER NOT NULL')
        cursor.execute('CREATE TABLE ERD_ARRAY (A INTEGER[-2:2,1:3], D ERD_NONNULL)')
        cursor.execute('CREATE TABLE ERD_CHILD (A INTEGER, B INTEGER, CONSTRAINT ERD_COMPOSITE FOREIGN KEY (A,B) REFERENCES ERD_PARENT (A,B))')
    connection.commit()
    resources = _resources(connection, {})
    connection.rollback()
    result = build_export(resources, endpoint_id='native', target_id='fixture', generation='native-erd')
    diagram = result['diagram']
    assert diagram and not diagram.get('unavailable'), diagram
    array = next(row for row in resources if row['resource_kind'] == 'column' and row['display_path'] == ['ERD_ARRAY', 'A'])
    assert array['native']['array_dimensions'] == [{'position': 0, 'lower_bound': -2, 'upper_bound': 2}, {'position': 1, 'lower_bound': 1, 'upper_bound': 3}], array
    domain = next(row for row in resources if row['resource_kind'] == 'column' and row['display_path'] == ['ERD_ARRAY', 'D'])
    assert str(domain['native']['domain_not_null']) == '1', domain
    assert 'INTEGER[-2:2,1:3]' in diagram['snapshot']['files']['relations.ddn']
    assert diagram['foreign_keys'] >= 1
    assert 'ERD_COMPOSITE (A, B) -> (A, B)' in diagram['snapshot']['files']['relations.ddn']
    (evidence / 'native-relational-diagram.json').write_text(json.dumps(diagram, ensure_ascii=False))
    (evidence / 'native-catalog-export.json').write_text(json.dumps(result, ensure_ascii=False))
    runner = Path(__file__).parent / 'tests/check_firebird_catalog_ddn.mjs'
    checked = subprocess.run(['node', str(runner)], input=json.dumps(result), capture_output=True, text=True, timeout=60)
    assert checked.returncode == 0, checked.stderr
    return {'passed': True, 'composite_foreign_key_preserved': True,
            'views_rendered': len(diagram['views']), 'native_identity_count': len(diagram['resource_mapping']),
            'warnings': diagram['warnings']}
