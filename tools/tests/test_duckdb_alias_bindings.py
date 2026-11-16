"""Durable binding invalidation from acknowledged/uncertain native alias facts."""
from copy import deepcopy
import sqlite3
from types import SimpleNamespace

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from test_design_store import SAMPLE_DDN
from pgadmin.cdeadmin.design_store import DesignStore, DesignStoreConflict, is_uuid7
from pgadmin.cdeadmin.workspace.duckdb_alias_bindings import record_binding_notice

RESOURCE = 'duckdb:["table","Before","main","data"]'


@pytest.fixture
def rig(tmp_path):
    store = DesignStore(db_path=tmp_path / 'designs.db')
    design = store.create_design(project_id='owned-alias', key='bindings', kind='erd',
        title='Owned alias binding checks', ddn_text=SAMPLE_DDN, actor_id=7)
    with sqlite3.connect(store.db_path) as connection:
        elements = [row[0] for row in connection.execute('SELECT id FROM element WHERE design_id=? ORDER BY id', (design['id'],))]
    identity = store.register_resource_identity(engine='duckdb', endpoint_id='ep',
        database_target_id='target', resource_kind='table', resource_id=RESOURCE)
    rows = []
    for element, ref, endpoint in [(elements[0], RESOURCE, 'ep'),
            (elements[1], identity['id'], 'ep'), (elements[1], RESOURCE, 'other-endpoint')]:
        rows.append(store.add_binding(design_id=design['id'], element_id=element,
            target_kind='resource', target_ref=ref, target_engine='duckdb',
            target_endpoint_id=endpoint, target_database_target_id='target', state='valid'))
    result = dict(action='rename', review_id='owned-review', native_acknowledged=True,
        native_dispatched=True, state='acknowledged', invalidate_resource_ids=[RESOURCE],
        alias_review={'descendants': [{'resource_id': RESOURCE}]})
    return SimpleNamespace(store=store, design=design, bindings=rows,
        context=SimpleNamespace(endpoint_id='ep'), result=result)


def notify(rig):
    return record_binding_notice(SimpleNamespace(design_store=rig.store), rig.context, 'target', rig.result)


def states(rig):
    return {row['id']: row['state'] for row in rig.store.list_bindings(rig.design['id'])}


def test_raw_and_uuid_bindings_become_suspect_without_touching_other_endpoints(rig):
    receipt = notify(rig)
    assert receipt['native_acknowledged'] and receipt['binding_notice']['status'] == 'recorded'
    assert receipt['binding_notice']['affected_bindings'] == 2
    assert is_uuid7(receipt['binding_notice']['notice_id'])
    actual = states(rig)
    assert [actual[row['id']] for row in rig.bindings] == ['suspect', 'suspect', 'valid']


def test_confirmation_survives_replayed_receipt_and_store_recreation(rig):
    first = notify(rig)
    for row in rig.bindings[:2]: rig.store.confirm_binding(row['id'], 7)
    rig.store = DesignStore(db_path=rig.store.db_path)
    assert notify(rig) == first
    assert set(states(rig).values()) == {'valid'}
    rig.result['review_id'] = 'another-native-change'
    assert notify(rig)['binding_notice']['notice_id'] != first['binding_notice']['notice_id']
    assert [states(rig)[row['id']] for row in rig.bindings[:2]] == ['suspect', 'suspect']


def test_local_record_failure_is_atomic_and_native_acknowledgement_survives(rig):
    with sqlite3.connect(rig.store.db_path) as connection:
        connection.execute("CREATE TRIGGER reject_notice BEFORE INSERT ON catalog_binding_notice BEGIN SELECT RAISE(ABORT,'owned test'); END")
    result = notify(rig)
    assert result['native_acknowledged'] and result['binding_notice']['status'] == 'unconfirmed'
    assert result['binding_notice']['native_retry'] is False
    assert set(states(rig).values()) == {'valid'}
    with sqlite3.connect(rig.store.db_path) as connection: connection.execute('DROP TRIGGER reject_notice')
    assert notify(rig)['binding_notice']['affected_bindings'] == 2


def test_uncertain_dispatched_alias_uses_reviewed_identity_inventory(rig):
    rig.result.update(state='unknown_outcome', native_acknowledged=False)
    rig.result.pop('invalidate_resource_ids')
    result = notify(rig)
    assert not result['native_acknowledged'] and result['binding_notice']['affected_bindings'] == 2


def test_pre_dispatch_refusal_does_not_invalidate_bindings(rig):
    rig.result.update(state='refused', native_dispatched=False, native_acknowledged=False)
    assert notify(rig) == rig.result
    assert set(states(rig).values()) == {'valid'}


def test_same_notice_cannot_be_rebound_to_different_native_resources(rig):
    first = notify(rig)
    rig.store.confirm_binding(rig.bindings[0]['id'], 7)
    with pytest.raises(DesignStoreConflict):
        rig.store.mark_native_catalog_bindings_suspect(engine='duckdb', endpoint_id='ep',
            database_target_id='target', event_key='duckdb-alias:owned-review',
            resource_ids=[RESOURCE, 'duckdb:["table","Other","main","data"]'])
    assert states(rig)[rig.bindings[0]['id']] == 'valid'
