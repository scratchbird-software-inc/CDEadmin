"""Partition, CHECK and group operation inputs bind existing native contracts."""
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers import mysql_constraints, mysql_group_replication, mysql_partitions
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import backend_draft, engine_operations, operation_draft

OPERATIONS = engine_operations('mysql')
UUID = '12345678-1234-1234-1234-123456789abc'
CASES = ([('group-replication', op) for op in sorted(mysql_group_replication.OPERATIONS)] +
         [(kind, op) for kind, ops in mysql_partitions.OPERATIONS.items() for op in sorted(ops) if op != 'drop'] +
         [('constraint', 'enforcement'), ('privilege', 'inspect')])


def request_for(kind, operation, values=None):
    path = ['db`雪', 't`雪'] + (['p`0'] if kind == 'partition' else ['c`雪'] if kind == 'constraint' else [])
    target = {'resource_kind': kind, 'display_name': path[-1], 'display_path': path,
              'native': {'group_replication_plugin_status': 'ACTIVE', 'constraint_type': 'CHECK'}}
    samples = {'member_uuid': UUID, 'timeout': 0, 'concurrency': 2**32-1, 'version': '9.7.0',
               'action_name': 'mysql_disable_super_read_only_if_primary', 'event_name': 'AFTER_PRIMARY_ELECTION',
               'user': '雪'*32, 'password': 'native\rquote"slash\\雪', 'default_auth': 'caching_sha2_password',
               'mode': 'DEFINITIONS', 'count': 2, 'definitions': 'PARTITION p1 VALUES LESS THAN (MAXVALUE)',
               'partition_clause': 'PARTITION BY HASH (id) PARTITIONS 2', 'enforcement': 'NOT ENFORCED',
               'partitions': [{'value': 'p`0'}], 'exchange_database': 'other`雪', 'exchange_table': 'swap`雪'}
    declared = OPERATIONS[operation + '@' + kind]
    ui = operation_draft(declared, {field['field_id']: samples[field['field_id']] for field in declared['fields']
                                  if field['field_id'] in samples}, target['display_name'])
    ui.update(values or {})
    draft = backend_draft({'tabs': [{'fields': declared['fields']}]}, ui)
    return {'resource_kind': kind, 'operation_id': operation, 'draft': draft, 'target_resource': target}, ui


@pytest.mark.parametrize('kind,operation', CASES)
def test_projected_dialog_values_reach_the_existing_native_compiler(kind, operation):
    request, _ = request_for(kind, operation)
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    declared = OPERATIONS[operation + '@' + kind]
    assert declared['status'] == 'draft' and declared['produces_log']
    if kind == 'privilege':
        assert not declared['fields']
        return
    direct = (mysql_group_replication.compile_operation(operation, request['draft'], request['target_resource'])
              if kind == 'group-replication' else
              mysql_constraints.compile_operation(operation, request['draft'], request['target_resource'])
              if kind == 'constraint' else
              mysql_partitions.compile_operation(kind, operation, request['draft'], request['target_resource']))
    assert MYSQL_ADMINISTRATION._compile(request)['statements'] == [direct]


def test_add_partition_modes_hide_only_the_other_mode_inputs():
    request, _ = request_for('table', 'add_partitions', {'mode': 'COUNT', 'count': 8192})
    assert 'definitions' not in request['draft']
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0]['source'].endswith('ADD PARTITION PARTITIONS 8192')
    request, _ = request_for('table', 'add_partitions')
    assert 'count' not in request['draft']
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0]['source'].endswith('ADD PARTITION (PARTITION p1 VALUES LESS THAN (MAXVALUE))')


def test_partition_list_projection_preserves_exact_identifiers_and_native_target_membership():
    request, ui = request_for('partition', 'reorganize')
    assert request['draft']['partitions'] == ['p`0']
    assert 'REORGANIZE PARTITION `p``0` INTO (' in MYSQL_ADMINISTRATION._compile(request)['statements'][0]['source']
    request['draft']['partitions'] = ui['partitions']
    with pytest.raises(RelationalClientError):
        MYSQL_ADMINISTRATION._compile(request)
    request['draft']['partitions'] = ['another']
    with pytest.raises(RelationalClientError):
        MYSQL_ADMINISTRATION._compile(request)


def test_partition_drop_keeps_its_existing_tier1_identity_and_confirmation_contract():
    catalog = MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    partition = next(row for row in catalog['objects'] if row['resource_kind'] == 'partition')
    drop = next(op for op in partition['operations'] if op['operation_id'] == 'drop')
    assert drop['form']['form_id'] == 'mysql.partition.drop'
    assert [field['field_id'] for field in drop['form']['fields']] == ['confirmation']
    assert 'drop@partition' not in OPERATIONS


def test_optional_group_credentials_preserve_absent_and_explicit_empty_password():
    declaration = OPERATIONS['start@group-replication']
    target = {'native': {'group_replication_plugin_status': 'ACTIVE'}}
    absent = backend_draft({'tabs': [{'fields': declaration['fields']}]}, operation_draft(declaration))
    explicit = {**absent, 'password': ''}
    assert mysql_group_replication.compile_operation('start', absent, target)['source'] == 'START GROUP_REPLICATION'
    assert mysql_group_replication.compile_operation('start', explicit, target)['parameters'] == ('',)
    request, _ = request_for('group-replication', 'start')
    result = MYSQL_ADMINISTRATION._compile(request)['statements'][0]
    assert result['parameters'][1] == 'native\rquote"slash\\雪'
    assert result['parameters'][1] not in result['preview_source']


@pytest.mark.parametrize('fragment', ['PARTITION BY HASH (id); SHUTDOWN', 'PARTITION p1 VALUES LESS THAN (10), ADD COLUMN x INT'])
def test_typed_sql_definition_cannot_become_an_unrelated_native_command(fragment):
    kind, operation, field = ('table', 'partition_by', 'partition_clause') if fragment.startswith('PARTITION BY') else ('partition', 'reorganize', 'definitions')
    request, _ = request_for(kind, operation, {field: fragment})
    with pytest.raises(RelationalClientError):
        MYSQL_ADMINISTRATION._compile(request)
