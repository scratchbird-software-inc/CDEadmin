"""Typed maintenance controls retain native binding types and legacy APIs."""
import json
import pytest
from test_cdeadmin_visual_admin import Permissions, context
from test_cdeadmin_relational_visual_admin import AdministrationClient
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MySQLDBAPIClient
from pgadmin.cdeadmin.providers import mysql_replication
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
from ui_descriptor_roundtrip import backend_draft, engine_operations, operation_draft

OPERATIONS = engine_operations('mysql')


class Client(AdministrationClient):
    admin_operation_field_contract = MySQLDBAPIClient.admin_operation_field_contract


def provider():
    return ProviderVisualAdministration(context(), Permissions(), 'mysql', '9.7.0', Client(MYSQL_ADMINISTRATION))


def request(kind, operation, values=None, target=None):
    target = target or {'resource_kind': kind, 'display_name': 'max_execution_time'}
    declaration = OPERATIONS[operation + '@' + kind]
    ui = operation_draft(declaration, values, target['display_name'])
    draft = backend_draft({'tabs': [{'fields': declaration['fields']}]}, ui)
    return {'resource_kind': kind, 'operation_id': operation, 'target_resource': target,
            'draft': draft, '_provider_route': {'host': 'owned'}}


@pytest.mark.parametrize('operation', ['set_global', 'set_persist', 'set_persist_only'])
@pytest.mark.parametrize('mode,field,value', [('TEXT', 'value_text', 'text "literal" 雪'),
    ('TEXT', 'value_text', ''), ('BOOLEAN', 'value_boolean', False), ('BOOLEAN', 'value_boolean', True),
    ('SAFE_INTEGER', 'value_integer', 0), ('SAFE_INTEGER', 'value_integer', 2**53-1),
    ('INTEGER', 'value_text', str(2**64-1)), ('DECIMAL', 'value_text', '0.1234567890123456789'),
    ('DOUBLE', 'value_text', '1e-300')])
def test_typed_scalar_inputs_cross_real_facade_without_json_coercion(operation, mode, field, value):
    payload = request('system-variable', operation, {'value_type': mode, field: value})
    service = provider()
    admitted = service.validate(payload)
    assert admitted['valid'], admitted['errors']
    assert admitted['draft']['value'] == value and type(admitted['draft']['value']) is type(value)
    compiled = MYSQL_ADMINISTRATION._compile({**payload, 'draft': admitted['draft']})['statements'][0]
    assert compiled['parameters'] == (value,)
    planned = service.plan(payload)
    assert planned['command_preview']['statements'][0]['parameters_redacted']
    assert planned['command_preview']['statements'][0]['source'].endswith('<redacted>')


@pytest.mark.parametrize('mode', ['DEFAULT', 'NULL'])
def test_default_and_null_do_not_require_or_bind_a_scalar(mode):
    payload = request('system-variable', 'set_global', {'value_mode': mode, 'value_type': 'BOOLEAN'})
    admitted = provider().validate(payload)
    assert admitted['valid'], admitted['errors']
    compiled = MYSQL_ADMINISTRATION._compile({**payload, 'draft': admitted['draft']})['statements'][0]
    assert compiled['source'].endswith(' = ' + mode) and compiled['parameters'] == ()
    payload['draft'].update(value={'ignored': 'native DEFAULT/NULL'}, value_type='AUTO')
    admitted = provider().validate(payload)
    assert admitted['valid'] and 'value' not in admitted['draft']


@pytest.mark.parametrize('value,expected', [(True, True), (42, 42), ('"legacy text"', 'legacy text'), ('123', 123)])
def test_legacy_auto_scalar_transport_keeps_its_existing_decode_contract(value, expected):
    payload = {'resource_kind': 'system-variable', 'operation_id': 'set_global',
               'target_resource': {'display_name': 'max_execution_time'},
               'draft': {'value': value, 'confirmation': 'max_execution_time'}}
    admitted = provider().validate(payload)
    assert admitted['valid'], admitted['errors']
    assert admitted['draft']['value_type'] == 'AUTO' and admitted['draft']['value'] == expected


@pytest.mark.parametrize('mode,value', [('TEXT', True), ('BOOLEAN', 'false'), ('SAFE_INTEGER', 1.5),
    ('SAFE_INTEGER', 2**53), ('INTEGER', '01'), ('DECIMAL', 'NaN'), ('DOUBLE', 'Infinity')])
def test_wrong_scalar_types_or_inexact_native_numbers_cannot_reach_planning(mode, value):
    payload = {'resource_kind': 'system-variable', 'operation_id': 'set_persist',
               'target_resource': {'display_name': 'max_execution_time'},
               'draft': {'value_type': mode, 'value': value, 'confirmation': 'max_execution_time'}}
    assert not provider().validate(payload)['valid']


@pytest.mark.parametrize('mode', [['TEXT'], {'input': 'TEXT'}])
def test_malformed_input_type_is_a_validation_error(mode):
    from pgadmin.cdeadmin.providers.mysql_server_operations import compile_operation
    from pgadmin.cdeadmin.sdk import RelationalClientError
    payload = {'resource_kind': 'system-variable', 'operation_id': 'set_global',
               'target_resource': {'display_name': 'max_execution_time'},
               'draft': {'value_type': mode, 'value': '10', 'confirmation': 'max_execution_time'}}
    assert not provider().validate(payload)['valid']
    with pytest.raises(RelationalClientError):
        compile_operation('system-variable', 'set_global', payload['draft'], payload['target_resource'])


CHANNEL = {'resource_kind': 'replication-channel', 'display_name': 'Named channel',
           'native': {'channel_name': "native ' 雪"}}


@pytest.mark.parametrize('kind,values,parameters', [
    ('NONE', {}, ("native ' 雪",)),
    ('SQL_BEFORE_GTIDS', {'sql_before_gtids': 'uuid:1-10'}, ('uuid:1-10', "native ' 雪")),
    ('SQL_AFTER_GTIDS', {'sql_after_gtids': ''}, ('', "native ' 雪")),
    ('SQL_AFTER_MTS_GAPS', {}, ("native ' 雪",)),
    ('SOURCE', {'source_file': 'native-bin.000001', 'source_pos': str(2**64-1)}, ('native-bin.000001', "native ' 雪")),
    ('RELAY', {'relay_file': 'native-relay.000001', 'relay_pos': str(2**32-1)}, ('native-relay.000001', "native ' 雪")),
])
def test_every_native_until_family_projects_without_hidden_default_conditions(kind, values, parameters):
    payload = request('replication-channel', 'start', {'until_kind': kind, **values}, CHANNEL)
    admitted = provider().validate(payload)
    assert admitted['valid'], admitted['errors']
    assert 'until_kind' not in admitted['draft']
    if kind == 'NONE':
        assert 'until' not in admitted['draft']
    compiled = MYSQL_ADMINISTRATION._compile({**payload, 'draft': admitted['draft']})['statements'][0]
    assert compiled['parameters'] == parameters


@pytest.mark.parametrize('key,records,legacy', [
    ('REPLICATE_DO_DB', [{'value': 'db`雪'}], ['db`雪']),
    ('REPLICATE_IGNORE_DB', [{'value': 'db'}], ['db']),
    ('REPLICATE_WILD_DO_TABLE', [{'value': 'db.odd%雪'}], ['db.odd%雪']),
    ('REPLICATE_WILD_IGNORE_TABLE', [{'value': 'db.ignore_%'}], ['db.ignore_%']),
    ('REPLICATE_DO_TABLE', [{'database': 'db`雪', 'table': 't`雪'}], [['db`雪', 't`雪']]),
    ('REPLICATE_IGNORE_TABLE', [{'database': 'db', 'table': 't'}], [['db', 't']]),
    ('REPLICATE_REWRITE_DB', [{'source': 'old`雪', 'target': 'new`雪'}], [['old`雪', 'new`雪']]),
])
def test_typed_filter_records_generate_identical_native_sql_to_legacy_pairs(key, records, legacy):
    payload = request('replication-channel', 'filter', {'edit_' + key.lower(): True, key.lower(): records}, CHANNEL)
    admitted = provider().validate(payload)
    assert admitted['valid'], admitted['errors']
    actual = mysql_replication.compile_operation('filter', admitted['draft'], CHANNEL)
    old = mysql_replication.compile_operation('filter', {'filters': {key: legacy}}, CHANNEL)
    assert actual == old


def test_filter_selection_preserves_unselected_rules_and_can_explicitly_clear_selected_rules():
    payload = request('replication-channel', 'filter', {'edit_replicate_ignore_db': True}, CHANNEL)
    assert payload['draft']['filters'] == {'REPLICATE_IGNORE_DB': []}
    assert provider().validate(payload)['valid']
    payload = request('replication-channel', 'filter', target=CHANNEL)
    assert 'filters' not in payload['draft'] and not provider().validate(payload)['valid']


@pytest.mark.parametrize('root,operation,value', [('filters', 'filter', {'REPLICATE_IGNORE_DB': []}),
    ('until', 'start', {'SQL_AFTER_GTIDS': 'uuid:1'})])
def test_legacy_encoded_mapping_payloads_remain_accepted(root, operation, value):
    payload = {'resource_kind': 'replication-channel', 'operation_id': operation, 'target_resource': CHANNEL,
               'draft': {root: json.dumps(value), 'confirmation': CHANNEL['display_name']}}
    admitted = provider().validate(payload)
    assert admitted['valid'] and admitted['draft'][root] == value


def test_lossless_thread_grid_and_process_target_identity_stay_distinct():
    payload = request('resource-group', 'assign', {'thread_ids': [{'value': str(2**64-1)}]},
                      {'resource_kind': 'resource-group', 'display_name': 'g`雪'})
    admitted = provider().validate(payload)
    assert admitted['valid'], admitted['errors']
    assert MYSQL_ADMINISTRATION._compile({**payload, 'draft': admitted['draft']})['statements'][0]['source'].endswith(str(2**64-1))
    for op,keyword in [('terminate_query', 'QUERY'), ('terminate_connection', 'CONNECTION')]:
        target = {'resource_kind': 'session', 'display_name': 'owned',
                  'native': {'processlist_id': '9007199254740993', 'thread_id': '7'}}
        payload = request('session', op, target=target)
        assert provider().validate(payload)['valid']
        assert MYSQL_ADMINISTRATION._compile(payload)['statements'][0]['source'] == 'KILL ' + keyword + ' 9007199254740993'
