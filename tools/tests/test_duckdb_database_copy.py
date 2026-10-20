"""Real native schema/data copies, transaction ownership and one-use finality."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb import database_copy as copying
from pgadmin.cdeadmin.providers.duckdb.provider import _create_client, DuckDBPilotProvider
from pgadmin.cdeadmin.providers.duckdb.attachments import quote
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.fixture(params=['file', 'memory'])
def native(tmp_path, request):
    import duckdb
    source = tmp_path / 'source . é.duckdb'
    seed = duckdb.connect(str(source))
    seed.execute('CREATE SCHEMA "area . é"; CREATE TYPE "area . é".mood AS ENUM (\'calm\',\'busy\'); '
        'CREATE SEQUENCE "area . é".counter START 11; '
        'CREATE TABLE "area . é".rows(id BIGINT, mood "area . é".mood, '
        'payload STRUCT("quoted . é" VARCHAR, numbers INT[]), bytes BLOB, exact DECIMAL(30,8)); '
        'CREATE INDEX by_id ON "area . é".rows(id); '
        'CREATE VIEW "area . é".visible AS SELECT id,payload FROM "area . é".rows; '
        'CREATE MACRO "area . é".plus_one(x) AS x+1; '
        'CREATE MACRO "area . é".selected() AS TABLE SELECT id FROM "area . é".rows; '
        'COMMENT ON TABLE "area . é".rows IS \'native comment\'')
    seed.execute('INSERT INTO "area . é".rows VALUES '
        '(1,\'calm\', {\'quoted . é\':\'α\',numbers:[1,NULL,3]}, \'\\x00\\xFF\'::BLOB, 12345678901234567890.12345678),'
        '(1,\'calm\', {\'quoted . é\':\'α\',numbers:[1,NULL,3]}, \'\\x00\\xFF\'::BLOB, 12345678901234567890.12345678),'
        '(NULL,NULL,NULL,NULL,NULL)')
    seed.close()
    destination = tmp_path / 'destination . é.duckdb'
    duckdb.connect(str(destination)).close()
    route = {'database': ':memory:' if request.param == 'memory' else str(tmp_path / 'primary.duckdb'),
        'filesystem_root': str(tmp_path), 'allow_memory': True}
    client = _create_client()
    handle = client.open_session({'route': route})
    aliases = ('Source . " é', 'Destination . " é')
    for path, alias in ((source, aliases[0]), (destination, aliases[1])):
        handle.execute("ATTACH '" + str(path).replace("'", "''") + "' AS " + quote(alias))
    client.control_transaction(handle, 'commit')
    provider = DuckDBPilotProvider(SimpleNamespace(endpoint_id='owned'), SimpleNamespace(require=Mock()), client)
    provider._sessions['original'] = SimpleNamespace(handle=handle)
    fixture = SimpleNamespace(client=client, handle=handle, route=route, aliases=aliases,
        provider=provider, destination=destination)
    try:
        yield fixture
    finally:
        for record in client._database_copy_reviews.values():
            if record.get('worker'):
                record['worker'].join(timeout=20)
        client.close()


def call(native, operation, **fields):
    return native.provider.database_copy_action({'session_id': 'original',
        'language_profile': 'duckdb-sql', 'operation': operation, **fields}, native.route)


def finished(native, result):
    native.client._database_copy_reviews[result['review_id']]['worker'].join(timeout=20)
    receipt = call(native, 'receipt', review_id=result['review_id'])
    assert receipt['phase'] == 'finished', receipt
    return receipt


def review(native, mode='ALL'):
    return finished(native, call(native, 'review', draft={'source_catalog': native.aliases[0],
        'destination_catalog': native.aliases[1], 'mode': mode}))


def apply(native, record):
    return finished(native, call(native, 'apply', review_id=record['review_id'],
        review_digest=record['review_digest'], confirmation=record['destination_catalog'], confirmed=True))


def table(native):
    return quote(native.aliases[1]) + '."area . é".rows'


def test_complete_native_copy_preserves_rows_types_objects_and_original_transaction(native):
    handle = native.handle
    handle.execute('CREATE TEMP TABLE private_rows AS SELECT 42 id')
    transaction = handle.execute('SELECT current_transaction_id()').fetchone()[0]
    before = handle.execute('SELECT * FROM ' + quote(native.aliases[0]) + '."area . é".rows').fetchall()
    record = review(native)
    assert record['state'] == 'reviewed', record
    assert 'BEGIN' not in record['source'] and 'COMMIT' not in record['source']
    result = apply(native, record)
    assert result['state'] == 'acknowledged' and result['rediscovery_verified'], result
    assert all(step['native_acknowledged'] for step in result['steps'])
    assert handle.execute('SELECT current_transaction_id()').fetchone()[0] == transaction
    assert handle.execute('SELECT * FROM ' + table(native)).fetchall() == before
    assert handle.execute('SELECT id FROM private_rows').fetchall() == [(42,)]
    assert handle.execute('SELECT ' + quote(native.aliases[1]) + '."area . é".plus_one(7)').fetchone() == (8,)
    assert handle.execute('SELECT count(*) FROM ' + quote(native.aliases[1]) + '."area . é".visible').fetchone() == (3,)
    assert apply(native, record) == result
    assert not result['automatic_retry'] and not result['caller_transaction_decision_requested']
    handle.rollback()
    assert handle.execute('SELECT count(*) FROM duckdb_tables() WHERE database_name=?',
        [native.aliases[1]]).fetchone() == (0,)


def test_schema_and_append_data_are_separate_native_modes_with_independent_commit_observation(native):
    schema = apply(native, review(native, 'SCHEMA'))
    assert schema['rediscovery_verified'], schema
    assert native.handle.execute('SELECT count(*) FROM ' + table(native)).fetchone() == (0,)
    native.client.control_transaction(native.handle, 'commit')
    for count in (3, 6):
        result = apply(native, review(native, 'DATA'))
        assert result['rediscovery_verified'], result
        assert native.handle.execute('SELECT count(*) FROM ' + table(native)).fetchone() == (count,)
        observer = native.handle.cursor()
        try:
            assert observer.execute('SELECT count(*) FROM ' + table(native)).fetchone() == (count - 3,)
            native.client.control_transaction(native.handle, 'commit')
            assert observer.execute('SELECT count(*) FROM ' + table(native)).fetchone() == (count,)
        finally:
            observer.close()


def test_changed_native_data_retires_review_before_any_mutation(native):
    record = review(native)
    native.handle.execute('UPDATE ' + quote(native.aliases[0]) + '."area . é".rows SET id=9 WHERE id=1')
    result = apply(native, record)
    assert result['state'] == 'refused' and not result['native_dispatched'], result
    assert apply(native, record) == result
    assert native.handle.execute('SELECT count(*) FROM duckdb_tables() WHERE database_name=?',
        [native.aliases[1]]).fetchone() == (0,)


def test_native_conflicts_return_failure_without_overwriting_or_transaction_decision(native):
    assert apply(native, review(native))['rediscovery_verified']
    native.client.control_transaction(native.handle, 'commit')
    result = apply(native, review(native))
    assert result['state'] == 'refused' and result['native_dispatched'] and not result['native_acknowledged'], result
    assert apply(native, result) == result
    native.client.control_transaction(native.handle, 'rollback')
    assert native.handle.execute('SELECT count(*) FROM ' + table(native)).fetchone() == (3,)


@pytest.mark.parametrize('fault', ['lost_reply', 'partial', 'post_acknowledgement'])
def test_native_effects_and_fault_receipts_are_never_replayed(native, fault):
    import duckdb
    record = review(native)
    dispatch = copying.dispatch
    observed = copying.observe
    calls = []
    def injected_dispatch(handle, source):
        calls.append(source)
        if fault == 'partial' and len(calls) == 2:
            raise duckdb.ConstraintException('owned native fault boundary')
        dispatch(handle, source)
        if fault == 'lost_reply':
            raise OSError('reply lost after native dispatch')
    def injected_observe(handle, alias, current):
        if fault == 'post_acknowledgement' and current['native_acknowledged']:
            raise OSError('post-ack observation lost')
        return observed(handle, alias, current)
    with patch.object(copying, 'dispatch', side_effect=injected_dispatch), patch.object(copying, 'observe', side_effect=injected_observe):
        result = apply(native, record)
        assert result['state'] == {'lost_reply':'unknown_outcome', 'partial':'partial',
            'post_acknowledgement':'acknowledged'}[fault], result
        count = len(calls)
        assert apply(native, record) == result and len(calls) == count
        assert not result['rediscovery_verified'] and not result['automatic_retry']
    if fault != 'partial':
        assert result['session_reuse_blocked']


def test_cancellation_before_dispatch_releases_busy_handle_and_reads_same_receipt(native):
    entered, release = threading.Event(), threading.Event()
    observe = copying.observe
    def pause(handle, alias, record):
        entered.set()
        assert release.wait(timeout=5)
        return observe(handle, alias, record)
    with patch.object(copying, 'observe', side_effect=pause):
        result = call(native, 'review', draft={'source_catalog': native.aliases[0],
            'destination_catalog': native.aliases[1], 'mode':'ALL'})
        assert entered.wait(timeout=5)
        assert id(native.handle) in native.client._busy
        with pytest.raises(RelationalClientError, match='active'):
            native.client.close_session(native.handle)
        call(native, 'cancel', review_id=result['review_id'])
        release.set()
        receipt = finished(native, result)
    assert receipt['state'] == 'cancelled' and not receipt['native_dispatched'], receipt
    assert id(native.handle) not in native.client._busy


def test_review_is_bound_to_session_registration_confirmation_transaction_and_authority(native):
    record = review(native)
    with pytest.raises(ValueError, match='Confirm'):
        call(native, 'apply', review_id=record['review_id'], review_digest=record['review_digest'],
            confirmation='another', confirmed=True)
    second = native.client.open_session({'route':native.route})
    try:
        with pytest.raises(ValueError, match='another or closed'):
            copying.action(native.client, second, native.route, {'operation':'receipt','review_id':record['review_id']})
        with pytest.raises(ValueError, match='changed registration'):
            copying.action(native.client, native.handle, {**native.route,'read_only':True},
                {'operation':'receipt','review_id':record['review_id']})
    finally:
        native.client.close_session(second)
    native.client.control_transaction(native.handle, 'commit')
    assert apply(native, record)['state'] == 'refused'
    native.provider.permissions.require.side_effect = RelationalClientError('permission denied')
    with pytest.raises(RelationalClientError, match='permission denied'):
        call(native, 'inventory')


@pytest.mark.parametrize('change', [
    {'destination_catalog':'missing'}, {'destination_catalog':'source . " é'},
    {'mode':[]}, {'mode':'REPLACE'}, {'source':'DROP TABLE existing'},
])
def test_invalid_copy_intent_never_starts_a_worker(native, change):
    with pytest.raises((ValueError, RelationalClientError)):
        call(native, 'review', draft={'source_catalog':native.aliases[0],
            'destination_catalog':native.aliases[1], 'mode':'ALL', **change})
    assert not native.client._database_copy_reviews


def test_native_one_writable_database_rule_preserves_existing_pending_work(native):
    native.handle.execute('CREATE TABLE pending(id INT)')
    native.client.control_transaction(native.handle, 'commit')
    native.handle.execute('INSERT INTO pending VALUES (42)')
    observer = native.handle.cursor()
    try:
        result = apply(native, review(native))
        assert result['state'] == 'refused' and result['error_type'] == 'TransactionException', result
        assert observer.execute('SELECT * FROM pending').fetchall() == []
        assert not result['caller_transaction_decision_requested']
        native.client.control_transaction(native.handle, 'rollback')
        assert native.handle.execute('SELECT * FROM pending').fetchall() == []
    finally:
        observer.close()


def test_readonly_destination_and_external_files_are_refused_before_worker(native):
    native.client.control_transaction(native.handle, 'commit')
    native.handle.execute('DETACH ' + quote(native.aliases[1]))
    native.client.control_transaction(native.handle, 'commit')
    native.handle.execute("ATTACH '" + str(native.destination).replace("'", "''") + "' AS " +
        quote(native.aliases[1]) + ' (READ_ONLY)')
    with pytest.raises(ValueError, match='writable authorized'):
        call(native, 'review', draft={'source_catalog':native.aliases[0],
            'destination_catalog':native.aliases[1], 'mode':'ALL'})
    assert not native.client._database_copy_reviews
    with patch.object(copying, 'file_identity', side_effect=RelationalClientError('outside registered root')):
        with pytest.raises(RelationalClientError, match='outside registered root'):
            call(native, 'review', draft={'source_catalog':native.aliases[0],
                'destination_catalog':native.aliases[1], 'mode':'ALL'})


def test_expired_and_discarded_reviews_never_dispatch(native):
    record = review(native)
    native.client._database_copy_reviews[record['review_id']]['deadline'] = 0
    with pytest.raises(ValueError, match='Confirm'):
        apply(native, record)
    record = review(native)
    discarded = call(native, 'discard', review_id=record['review_id'], review_digest=record['review_digest'])
    assert discarded['state'] == 'discarded' and apply(native, record) == discarded


def test_data_mode_preserves_native_type_conversion_without_cross_type_hash_comparison(native):
    assert apply(native, review(native, 'SCHEMA'))['rediscovery_verified']
    native.handle.execute('DROP INDEX ' + quote(native.aliases[1]) + '."area . é".by_id')
    native.client.control_transaction(native.handle, 'commit')
    native.handle.execute('ALTER TABLE ' + table(native) + ' ALTER COLUMN id TYPE VARCHAR')
    native.client.control_transaction(native.handle, 'commit')
    result = apply(native, review(native, 'DATA'))
    assert result['state'] == 'acknowledged' and result['rediscovery_verified'], result
    assert native.handle.execute('SELECT id FROM ' + table(native) + ' ORDER BY id NULLS LAST').fetchall() == [('1',), ('1',), (None,)]
    checks = list(result['observation']['native_table_postconditions'].values())
    assert checks[0]['method'] == 'native_row_count_after_conversion' and checks[0]['observed_rows'] == '3'


def test_native_generated_columns_primary_keys_and_checks_survive_copy(native):
    import duckdb
    source = quote(native.aliases[0]) + '."area . é".constrained'
    destination = quote(native.aliases[1]) + '."area . é".constrained'
    native.handle.execute('CREATE TABLE ' + source +
        '(id INT PRIMARY KEY,flag INT CHECK(flag>=0),derived INT GENERATED ALWAYS AS (id+flag))')
    native.handle.execute('INSERT INTO ' + source + '(id,flag) VALUES (1,3),(2,4)')
    native.client.control_transaction(native.handle, 'commit')
    result = apply(native, review(native))
    assert result['state'] == 'acknowledged' and result['rediscovery_verified'], result
    assert native.handle.execute('SELECT * FROM ' + destination + ' ORDER BY id').fetchall() == [(1,3,4),(2,4,6)]
    with pytest.raises(duckdb.ConstraintException):
        native.handle.execute('INSERT INTO ' + destination + '(id,flag) VALUES (1,7)')


def test_volatile_virtual_columns_are_recomputed_by_native_copy_without_false_staleness(native):
    source = quote(native.aliases[0]) + '."area . é"."volatile . é"'
    destination = quote(native.aliases[1]) + '."area . é"."volatile . é"'
    native.handle.execute('CREATE TABLE ' + source +
        '("physical . é" INT, "volatile . é" DOUBLE GENERATED ALWAYS AS (random()),'
        'literal VARCHAR DEFAULT \'GENERATED ALWAYS AS (fake)\')')
    native.handle.execute('INSERT INTO ' + source + '("physical . é") VALUES (42)')
    native.client.control_transaction(native.handle, 'commit')
    result = apply(native, review(native))
    assert result['state'] == 'acknowledged' and result['rediscovery_verified'], result
    assert native.handle.execute('SELECT "physical . é",literal FROM ' + destination).fetchone() == (42,'GENERATED ALWAYS AS (fake)')
