from copy import deepcopy
from itertools import permutations
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.providers.firebird.trigger_types import action, DDL_ACTIONS
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def trigger(**changes):
    result = obj('trigger', 'T"ü', **{'relation': None, 'trigger_type': 8192,
        'inactive': 0, 'position': 0, 'metadata_source': 'AS BEGIN END',
        'description': None, 'sql_security': None, 'entrypoint': None, 'engine_name': None, **changes})
    if changes.get('relation'):
        result['display_path'] = [changes['relation'], result['display_name']]
    return result


def test_every_dml_permutation_and_ddl_bit_is_lossless():
    names = {1: 'INSERT', 2: 'UPDATE', 3: 'DELETE'}
    for count in range(1, 4):
        for events in permutations((1, 2, 3), count):
            for timing in (0, 1):
                mask = timing - 1 + sum(event << (slot * 2 + 1) for slot, event in enumerate(events))
                assert action(mask) == ('BEFORE ' if timing == 0 else 'AFTER ') + ' OR '.join(names[item] for item in events)
    for bit, name in DDL_ACTIONS.items():
        assert action(16384 | 1 << bit) == 'BEFORE ' + name
    for event, name in enumerate(['CONNECT', 'DISCONNECT', 'TRANSACTION START', 'TRANSACTION COMMIT', 'TRANSACTION ROLLBACK']):
        assert action(8192 + event) == 'ON ' + name
    assert action(((1 << 63) - 1) & ~(1 << 13)) == 'AFTER ANY DDL STATEMENT'


@pytest.mark.parametrize('value', [0, 127, 128, 8197, 24576, 16384, 16384 | 1 << 48, 16384 | 1 << 15, 9])
def test_invalid_masks_never_reduce_to_a_subset(value):
    with pytest.raises((ValueError, RelationalClientError)):
        action(value)


def test_database_create_alter_and_security_reset():
    base = document([])
    desired = document([trigger(sql_security=True)])
    created = build_plan(base, desired, base)
    assert created['status'] == 'review-ready', created['blockers']
    assert created['operations'][0]['statements'] == [
        'CREATE TRIGGER "T""ü" ACTIVE ON CONNECT POSITION 0\nSQL SECURITY DEFINER\nAS\nBEGIN END']
    changed = document([trigger(metadata_source='BEGIN EXIT; END', position=3)])
    altered = build_plan(desired, changed, desired)
    assert altered['status'] == 'review-ready', altered['blockers']
    assert altered['operations'][0]['statements'] == [
        'ALTER TRIGGER "T""ü" ACTIVE POSITION 3\nDROP SQL SECURITY\nAS\nBEGIN EXIT; END']
    assert 'SET TERM' in altered['script']


@pytest.mark.parametrize('changes', [{'trigger_type': 8193}, {'constraint_owner': 'CHECK_1'},
    {'engine_name': 'UDR', 'sql_security': True}, {'metadata_source': None}, {'position': -1}, {'owner': 'OTHER'}])
def test_unsupported_or_incomplete_changes_block(changes):
    base = document([trigger()]); desired = document([trigger(**changes)])
    result = build_plan(base, desired, base)
    assert result['status'] == 'blocked' and result['script'] is None


def test_relation_is_guarded_and_not_silently_rebound():
    table = obj('table', 'TAB')
    base = document([table, trigger(relation='TAB', trigger_type=1)])
    desired = deepcopy(base)
    row = next(row for row in desired['rows'].values() if row['kind'] == 'trigger')
    row['native'].update(trigger_type=4, description='Changed')
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    operation = result['operations'][0]
    assert operation['statements'][0].startswith('ALTER TRIGGER "T""ü" ACTIVE AFTER UPDATE')
    assert table['resource_id'] in operation['native_preconditions']
    row['native']['relation'] = 'MISSING'
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_new_table_and_nested_trigger_create_in_native_dependency_order():
    from tools.tests.test_firebird_table_plan import table
    child = trigger(relation='T', trigger_type=1)
    native = child['extensions']['firebird']['native']
    parent = table(triggers=[{'name': 'T"ü', **native}])
    base = document([]); desired = document([parent, child])
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert [op['kind'] for op in result['operations']] == ['table', 'trigger']
    assert result['script'].count('CREATE TRIGGER') == 1
    desired['rows']['table:T']['native']['triggers'][0]['metadata_source'] = 'BEGIN EXIT; END'
    assert build_plan(base, desired, base)['status'] == 'blocked'
