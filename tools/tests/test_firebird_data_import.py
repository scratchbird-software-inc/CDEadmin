"""Data import never treats archived names, DDL or type claims as authority."""
import json
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.workspace.firebird_data_import import preview


def column(name, **extra):
    return {'name': name, 'field_type': 8, 'field_scale': 0, **extra}


def fixture():
    columns = [column('ID', identity_type=0), column('VALUE'), column('CALCULATED', computed_source='VALUE * 2')]
    table = {'resource_id': 'destination-id', 'name': 'T', 'kind': 'table', 'path': ['T'], 'system': 'false',
             'native': {'relation_type': 0, 'columns': columns, 'constraints': []}}
    source = {'format': 'scratchrobin.firebird.data@1', 'contents': 'both', 'row_count': 1,
              'metadata': {'ddl': 'DROP DATABASE'}, 'tables': [{'name': 'T', 'resource_id': 'untrusted-id',
                  'native_columns': columns, 'rows': [{'ID': 42, 'VALUE': 7, 'CALCULATED': 14}]}]}
    return source, {'rows': {'destination-id': table}, 'provenance': {'generation': 'current'}}


def test_preview_binds_destination_and_preserves_identity_but_excludes_computed():
    source, current = fixture()
    result = preview(json.dumps(source), current)
    assert result['operations'] == [{'table': 'T', 'row': 0, 'values': {'ID': 42, 'VALUE': 7}, 'override_identity': True}]
    assert result['catalogs']['T']['resource']['resource_id'] == 'destination-id'
    assert result['metadata_execution'] is False
    assert result['identity_requirements'][0]['columns'] == ['ID']
    assert 'DROP DATABASE' not in json.dumps(result)


def test_types_duplicates_counts_and_external_tables_fail_before_dispatch():
    source, current = fixture()
    changed = json.loads(json.dumps(source)); changed['tables'][0]['native_columns'][1]['field_scale'] = -2
    with pytest.raises(ValueError, match='layout differs'): preview(json.dumps(changed), current)
    changed = json.loads(json.dumps(source)); changed['tables'].append(changed['tables'][0])
    with pytest.raises(ValueError, match='Duplicate archived table'): preview(json.dumps(changed), current)
    changed = json.loads(json.dumps(source)); changed['row_count'] = 2
    with pytest.raises(ValueError, match='row count'): preview(json.dumps(changed), current)
    with pytest.raises(ValueError, match='duplicate property'): preview('{"tables": [], "tables": []}', current)
    current['rows']['destination-id']['native']['relation_type'] = 2
    with pytest.raises(ValueError, match='persistent table'): preview(json.dumps(source), current)


def test_fk_cycles_are_not_hidden_and_external_rows_are_named():
    source, current = fixture()
    constraints = current['rows']['destination-id']['native']['constraints']
    constraints.append({'constraint_type': 'FOREIGN KEY', 'referenced_relation': 'PARENT'})
    result = preview(json.dumps(source), current)
    assert result['external_prerequisites'] == [{'table': 'T', 'requires_existing_rows_in': 'PARENT'}]
    constraints[0]['referenced_relation'] = 'T'
    with pytest.raises(ValueError, match='cycle'): preview(json.dumps(source), current)


def request(value=True):
    return {'resource_kind': 'table', 'target_resource': {'resource_kind': 'table', 'display_name': 'T', 'display_path': ['T']},
            'draft': {'values': {'ID': 42}, 'override_identity': value}}


def test_native_identity_override_is_explicit_and_bound():
    result = ADMINISTRATION._compile_insert(request())
    assert result == {'source': 'INSERT INTO "T" ("ID") OVERRIDING SYSTEM VALUE VALUES (?)', 'parameters': (42,)}
    assert 'OVERRIDING' not in ADMINISTRATION._compile_insert(request(False))['source']
    with pytest.raises(RelationalClientError, match='Boolean'): ADMINISTRATION._compile_insert(request('true'))
    assert any(f['field_id'] == 'override_identity' for f in ADMINISTRATION._existing_operation_form('table', 'insert')['fields'])


def test_json_numeric_transport_never_rounds_before_native_binding():
    source, current = fixture()
    source['tables'][0]['rows'][0]['VALUE'] = 2**100
    with pytest.raises(ValueError, match='Invalid data archive'):
        preview(json.dumps(source), current)
    source['tables'][0]['rows'][0]['VALUE'] = str(2**100)
    assert preview(json.dumps(source), current)['operations'][0]['values']['VALUE'] == str(2**100)
    source['tables'][0]['rows'][0]['VALUE'] = 1.25
    assert preview(json.dumps(source), current)['operations'][0]['values']['VALUE'] == '1.25'


def test_explicit_row_order_admits_cycles_without_changing_values_or_constraints():
    source, current = fixture()
    current['rows']['destination-id']['native']['constraints'] = [
        {'constraint_type': 'FOREIGN KEY', 'referenced_relation': 'T'}]
    source['tables'][0]['rows'].append({'ID': 41, 'VALUE': None, 'CALCULATED': None})
    source['row_count'] = 2
    result = preview(json.dumps(source), current, row_order=[{'table': 'T', 'row': 1}, {'table': 'T', 'row': 0}])
    assert result['ordering'] == 'explicit-row-order'
    assert [item['values']['ID'] for item in result['operations']] == [41, 42]
    assert result['constraints_disabled'] is False
    for order in ([], [{'table': 'T', 'row': 0}] * 2,
                  [{'table': 'T', 'row': True}, {'table': 'T', 'row': 0}],
                  [{'table': 'other', 'row': 1}, {'table': 'T', 'row': 0}]):
        with pytest.raises(ValueError):
            preview(json.dumps(source), current, row_order=order)


def test_allocation_handoffs_use_observed_native_identities():
    source, current = fixture()
    current['rows']['column:T:ID'] = {'resource_id': 'column:T:ID', 'kind': 'column',
        'path': ['T', 'ID'], 'name': 'ID', 'system': 'false', 'native': {}}
    for name, system in [('USER_SEQ', 'false'), ('RDB$IDENTITY', 'true')]:
        current['rows'][name] = {'resource_id': 'sequence:' + name, 'kind': 'sequence',
            'name': name, 'path': [name], 'system': system, 'native': {}}
    result = preview(json.dumps(source), current)
    assert [item['resource_id'] for item in result['allocation_targets']] == ['column:T:ID', 'sequence:USER_SEQ']
