"""Database descriptor inputs retain native option types through the real facade."""
from copy import deepcopy
import json
import pytest
from test_cdeadmin_visual_admin import Permissions, context
from test_cdeadmin_relational_visual_admin import AdministrationClient
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MySQLDBAPIClient
from pgadmin.cdeadmin.providers.mysql_family.database_inputs import normalize, OPERATIONS
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import backend_draft, engine_operations, operation_draft

DECLARED = engine_operations('mysql')
TARGET = {'resource_kind': 'database', 'display_name': 'inventory', 'display_path': ['inventory']}
ROUTE = {'host': 'owned', 'database': 'inventory', 'tool_workspace': '/owned'}


class Client(AdministrationClient):
    admin_operation_field_contract = MySQLDBAPIClient.admin_operation_field_contract


def service():
    return ProviderVisualAdministration(context(), Permissions({'data_read', 'data_write', 'administer', 'maintenance_admin', 'backup_admin', 'restore_admin'}), 'mysql', '9.7.0', Client(MYSQL_ADMINISTRATION))


def payload(operation, values=None):
    declaration = DECLARED[operation + '@database']
    values = operation_draft(declaration, values, 'inventory')
    draft = backend_draft({'tabs': [{'fields': declaration['fields']}]}, values)
    return {'resource_kind': 'database', 'operation_id': operation, 'target_resource': TARGET,
            'draft': draft, '_provider_route': ROUTE}


@pytest.mark.parametrize('operation', sorted(OPERATIONS))
def test_each_database_operation_reaches_descriptor_fields_and_existing_permissions(operation):
    value = payload(operation, {'path': 'dump', 'tables': [{'value': 't`雪'}]})
    admitted = service().validate(value)
    assert admitted['valid'], admitted['errors']
    assert service().plan(value)['state'] == 'ready'
    database = next(row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects']
                    if row['resource_kind'] == 'database')
    catalog_operation = next(row for row in database['operations'] if row['operation_id'] == operation)
    assert catalog_operation['form']['form_id'] == 'mysql.database.' + operation
    assert catalog_operation['required_permissions']
    assert DECLARED[operation+'@database']['status'] == 'draft'


@pytest.mark.parametrize('operation', ['backup_logical', 'restore_logical'])
def test_unselected_optional_collections_are_absent_and_selected_empty_is_explicit(operation):
    value = payload(operation, {'path': 'dump'})
    assert not any(key.startswith(('include_', 'exclude_')) or key in {'where', 'partitions', 'compatibility', 'session_init_sql'} for key in value['draft'])
    value = payload(operation, {'path': 'dump', 'set_include_tables': True})
    assert value['draft']['include_tables'] == []
    assert service().validate(value)['valid']


def test_shell_filter_records_and_nested_partition_lists_keep_native_names_and_conditions():
    value = payload('backup_logical', {'path': 'dump', 'set_partitions': True,
        'partitions': [{'table': 'inventory.t`雪', 'partitions': [{'value': 'p`雪'}, {'value': 'p2'}]}],
        'set_where': True, 'where': [{'table': 'inventory.t`雪', 'condition': 'id > 0 AND note = \'雪\''}],
        'set_include_tables': True, 'include_tables': [{'value': 'inventory.t`雪'}]})
    admitted = service().validate(value)
    assert admitted['valid'], admitted['errors']
    native = normalize('backup_logical', admitted['draft'])
    assert native['partitions'] == {'inventory.t`雪': ['p`雪', 'p2']}
    assert native['where'] == {'inventory.t`雪': "id > 0 AND note = '雪'"}
    assert native['include_tables'] == ['inventory.t`雪']
    assert MySQLDBAPIClient._shell_options('backup_logical', native)['partitions'] == native['partitions']
    assert service().plan(value)['state'] == 'ready'


@pytest.mark.parametrize('name,value', [('partitions', {'inventory.t': ['p0']}), ('where', {'inventory.t': 'id > 0'})])
@pytest.mark.parametrize('encoded', [False, True])
def test_existing_shell_mapping_and_encoded_transport_remain_accepted(name, value, encoded):
    request = payload('backup_logical', {'path': 'dump'})
    request['draft'][name] = json.dumps(value) if encoded else value
    admitted = service().validate(request)
    assert admitted['valid'], admitted['errors']
    assert admitted['draft'][name] == value


@pytest.mark.parametrize('rows', [[{'table': 'd.t', 'condition': 'id=1'}, {'table': 'd.t', 'condition': 'id=2'}],
    [{'table': 'd.t', 'condition': 'id=1', 'extra': 'ignored'}], [{'table': 'd.t'}], [{'table': '', 'condition': '1'}]])
def test_invalid_filter_records_cannot_be_planned(rows):
    request = payload('backup_logical', {'path': 'dump', 'set_where': True, 'where': rows})
    assert not service().validate(request)['valid']


def histogram(kind='singleton', data_type='int', rows=None):
    return {'tables': [{'value': 't'}], 'histogram_action': 'UPDATE',
            'histogram_columns': [{'value': 'v'}], 'histogram_source': 'IMPORT',
            'histogram_type': kind, 'histogram_data_type': data_type,
            'histogram_bucket_rows': rows or [{'lower': '1', 'frequency': 1}]}


@pytest.mark.parametrize('kind,rows,expected', [('singleton', [{'lower': str(2**64-1), 'frequency': 1}], [[2**64-1, 1.0]]),
    ('equi-height', [{'lower': '1', 'upper': str(2**64-1), 'frequency': .75, 'distinct': str(2**64-1)}], [[1, 2**64-1, .75, 2**64-1]])])
def test_typed_histogram_buckets_preserve_exact_unsigned_endpoints_and_counts(kind, rows, expected):
    request = payload('analyze_tables', histogram(kind, 'uint', rows))
    admitted = service().validate(request)
    assert admitted['valid'], admitted['errors']
    imported = normalize('analyze_tables', admitted['draft'])['histogram_data']
    assert imported['buckets'] == expected
    assert type(imported['sampling-rate']) is type(imported['null-values']) is float
    plan = MYSQL_ADMINISTRATION.plan({**request, 'draft': admitted['draft']})
    sql = plan['command_preview']['statements'][0]['source']
    assert str(2**64-1) in sql and 'USING DATA' in sql


@pytest.mark.parametrize('data_type,text,expected', [('int', str(-(2**63)), -(2**63)), ('enum', '1', 1),
    ('set', '2', 2), ('double', '1e-300', 1e-300), ('decimal', '0.125', .125),
    ('string', 'base64:type254:6Zuq', 'base64:type254:6Zuq'), ('date', '2026-10-26', '2026-10-26'),
    ('time', '01:02:03.123456', '01:02:03.123456'), ('datetime', '2026-10-26 01:02:03', '2026-10-26 01:02:03')])
def test_every_native_histogram_value_family_has_a_typed_transport(data_type, text, expected):
    request = payload('analyze_tables', histogram(data_type=data_type, rows=[{'lower': text, 'frequency': 1}]))
    assert service().validate(request)['valid']
    assert normalize('analyze_tables', request['draft'])['histogram_data']['buckets'] == [[expected, 1.0]]


@pytest.mark.parametrize('row', [{'lower': '1', 'frequency': True}, {'lower': str(2**64), 'frequency': 1},
    {'lower': '01', 'frequency': 1}, {'lower': '1', 'frequency': float('nan')},
    {'lower': '1', 'frequency': 1, 'extra': 'ignored'}, {'lower': '1', 'upper': '2', 'frequency': 1}])
def test_invalid_histogram_records_fail_before_native_dispatch(row):
    request = payload('analyze_tables', histogram(data_type='uint', rows=[row]))
    assert not service().validate(request)['valid']


def test_original_exported_histograms_are_not_reinterpreted_as_grid_records():
    exported = {'histogram-type': 'singleton', 'data-type': 'int', 'buckets': [[1, 1.0]],
                'sampling-rate': 1.0, 'null-values': 0.0, 'auto-update': False,
                'number-of-buckets-specified': 100, 'collation-id': 8}
    request = payload('analyze_tables', {'tables': ['t'], 'histogram_action': 'UPDATE', 'histogram_columns': ['v']})
    request['draft']['histogram_data'] = exported
    assert service().validate(request)['valid']
    before = deepcopy(exported)
    assert normalize('analyze_tables', request['draft'])['histogram_data'] == before
    request['draft']['histogram_data'] = json.dumps(exported)
    assert service().validate(request)['valid']


@pytest.mark.parametrize('operation,changes', [('backup_logical', {'ddl_only': True, 'data_only': True}),
    ('backup_logical', {'consistent': False, 'skip_consistency_checks': True}),
    ('restore_logical', {'drop_existing_objects': True, 'ignore_existing_objects': True}),
    ('restore_logical', {'confirmation': 'other'}), ('verify_logical', {'confirmation': 'other'}),
    ('restore_logical', {'background_threads': .5}), ('backup_logical', {'threads': True})])
def test_typed_controls_do_not_bypass_existing_native_conflicts_or_confirmation(operation, changes):
    assert not service().validate(payload(operation, {'path': 'dump', **changes}))['valid']


def test_empty_histogram_keeps_numeric_frequency_types_required_by_mysql():
    request = payload('analyze_tables', {**histogram(), 'histogram_bucket_rows': []})
    imported = normalize('analyze_tables', request['draft'])['histogram_data']
    assert imported['buckets'] == []
    assert type(imported['sampling-rate']) is type(imported['null-values']) is float


@pytest.mark.parametrize('operation', ['backup_logical', 'restore_logical'])
def test_all_declared_shell_option_fields_resolve_to_the_existing_native_contract(operation):
    row = DECLARED[operation+'@database']
    roots = {(f.get('backend_field_id') or f['field_id']).split('.')[0]
             for f in row['fields'] if not f.get('ui_only')}
    assert roots == set(MySQLDBAPIClient._OPTION_NAMES[operation]) | {'path'} | (
        {'confirmation', 'enable_local_infile'} if operation == 'restore_logical' else set())


def test_retired_dump_browser_gate_fails_explicitly_before_creating_a_fixture(tmp_path):
    from cdeadmin_mysql_dump_verification_qualification import qualify
    with pytest.raises(RuntimeError, match='Decision12'):
        qualify(tmp_path/'unused', '/unused/mysqlsh', browser_binary='/unused/browser')
    assert not list(tmp_path.iterdir())


def test_retired_backup_browser_gate_cannot_claim_the_empty_fallback_is_a_form():
    from cdeadmin_mysql_backup_restore_ui_gate import _operations
    with pytest.raises(RuntimeError, match='Decision12'):
        _operations()
