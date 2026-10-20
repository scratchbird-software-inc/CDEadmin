"""Native outcome retention without reconnect, replay or transaction inference."""
import json
import uuid
from unittest.mock import patch

import pytest

from test_duckdb_database_copy import native,review,apply  # noqa: F401
from pgadmin.cdeadmin.workspace.duckdb_session_receipts import DuckDBSessionReceipts,action
from pgadmin.cdeadmin.providers.duckdb import database_copy
from pgadmin.cdeadmin.sdk import RelationalClientError


def bind(native,tmp_path):
    endpoint=str(uuid.uuid4())
    archive=DuckDBSessionReceipts(tmp_path/'receipts',1,endpoint,'owned-target')
    native.client.bind_receipt_archive(native.handle,archive,native.route)
    return archive


def test_copy_acknowledgement_survives_original_close_and_archive_reconstruction(native,tmp_path):
    archive=bind(native,tmp_path)
    result=apply(native,review(native))
    assert result['native_acknowledged'] and result['rediscovery_verified']
    before=archive.get(result['review_id'])
    assert before['receipt']['native_acknowledged'] and not before['transaction_finality_inferred']
    assert before['revision']>=5
    native.handle.rollback()
    closed=native.client.close_session(native.handle)
    assert closed['connection_released'] and closed['receipt_release_recorded']
    restored=DuckDBSessionReceipts(*archive.binding)
    with patch.object(native.client,'_connect',side_effect=AssertionError('Archive opened a native connection')):
        retained=restored.get(result['review_id'])
        assert retained['original_session']['state']=='released'
        assert retained['receipt']['native_acknowledged'] and not retained['transaction_finality_inferred']
        assert action(restored,{'operation':'list'})['total']==1
        with pytest.raises(ValueError):action(restored,{'operation':'apply','review_id':result['review_id']})
    import duckdb
    with duckdb.connect(str(native.destination),read_only=True) as independent:
        assert independent.execute('SELECT count(*) FROM duckdb_tables() WHERE NOT internal').fetchone()==(0,)


def test_encrypted_attachment_and_extension_receipts_never_persist_private_key(native,tmp_path):
    archive=bind(native,tmp_path)
    key='private native attachment canary 12345'
    def attach(operation,**fields):
        return native.provider.attachment_action({'session_id':'original','language_profile':'duckdb-sql',
            'operation':operation,**fields},native.route)
    reviewed=attach('review',draft={'action':'attach','alias':'owned encrypted','path':str(tmp_path/'encrypted.duckdb'),
        'read_only':False,'create_if_missing':True,'conflict':'ERROR','encryption_key':key,'encryption_cipher':'GCM'})
    attached=attach('apply',review_id=reviewed['review_id'],review_digest=reviewed['review_digest'],
        confirmation='owned encrypted',confirmed=True)
    assert attached['native_acknowledged'] and attached['rediscovery_verified']
    def extension(operation,**fields):
        return native.provider.extension_action({'session_id':'original','language_profile':'duckdb-sql',
            'operation':operation,**fields},native.route)
    reviewed=extension('review',draft={'action':'load','extension_name':'json'})
    loaded=extension('apply',review_id=reviewed['review_id'],review_digest=reviewed['review_digest'],
        confirmation=reviewed['extension_name'],confirmed=True)
    assert loaded['native_acknowledged'] and loaded['rediscovery_verified']
    native.client.close_session(native.handle)
    for value in (attached,loaded):
        kept=archive.get(value['review_id'])
        assert kept['receipt']['native_acknowledged'] and kept['original_session']['state']=='released'
    for path in archive.root.rglob('*.json'):assert key.encode() not in path.read_bytes()


def test_failed_durable_dispatch_receipt_prevents_native_copy(native,tmp_path):
    archive=bind(native,tmp_path)
    record=review(native)
    original=archive.publish
    def unavailable(family,value):
        if value.get('native_dispatched'):raise OSError('Owned receipt store unavailable')
        original(family,value)
    with patch.object(archive,'publish',side_effect=unavailable),patch.object(database_copy,'dispatch',side_effect=AssertionError('Unrecorded dispatch')) as dispatch:
        result=apply(native,record)
        assert not result['native_dispatched'] and not result['native_acknowledged']
        assert result['native_catalog_or_data_effects_possible'] is False
        dispatch.assert_not_called()
    assert native.handle.execute('SELECT count(*) FROM duckdb_tables() WHERE database_name=?',[native.aliases[1]]).fetchone()==(0,)
    assert archive.get(record['review_id'])['receipt']['native_dispatched'] is False


def test_post_acknowledgement_recording_failure_preserves_uncertainty_without_replay(native,tmp_path):
    archive=bind(native,tmp_path);record=review(native);original=archive.publish
    def unavailable(family,value):
        if any(step['native_acknowledged'] for step in value.get('steps',[])):
            raise OSError('Owned receipt store failed after native return')
        original(family,value)
    with patch.object(archive,'publish',side_effect=unavailable):
        applying=native.provider.database_copy_action({'session_id':'original','language_profile':'duckdb-sql',
            'operation':'apply','review_id':record['review_id'],'review_digest':record['review_digest'],
            'confirmation':record['destination_catalog'],'confirmed':True},native.route)
        native.client._database_copy_reviews[record['review_id']]['worker'].join(timeout=20)
        retained=native.client._database_copy_reviews[record['review_id']]
        assert retained['steps'][0]['native_acknowledged'] and retained['state']=='partial'
    persisted=archive.get(record['review_id'])
    assert not persisted['receipt']['steps'][0]['native_acknowledged']
    with patch.object(database_copy,'dispatch',side_effect=AssertionError('Partial native operation replayed')):
        observed=apply(native,record)
        assert observed['state']=='partial' and observed['steps'][0]['native_acknowledged']
    native.handle.rollback()


def test_receipt_scope_and_lost_owner_do_not_grant_replay_or_imply_commit(native,tmp_path):
    archive=bind(native,tmp_path);record=review(native)
    for changes in ({'owner':2},{'endpoint':str(uuid.uuid4())},{'target':'another-target'}):
        fields={'path':archive.binding[0],'owner':1,'endpoint':archive.binding[2],'target':'owned-target',**changes}
        with pytest.raises(ValueError):DuckDBSessionReceipts(**fields).get(record['review_id'])
    with pytest.raises(RelationalClientError):native.client.bind_receipt_archive(native.handle,archive,{**native.route,'database':':other:'})
    with archive.store('sessions',record['session_scope_id']) as store:
        store.change(lambda state:state['duckdb_session_observation'].update(process_identity=[999999999,0]))
    pending=native.client._database_copy_reviews[record['review_id']].copy()
    pending.update(state='applying',phase='starting');pending=database_copy.public(pending)
    archive.publish('database_copy',pending)
    value=archive.get(record['review_id'])
    assert value['outcome_observation']=='unknown' and value['original_session']['state']=='owner_unavailable'
    assert not value['automatic_retry'] and not value['transaction_finality_inferred']


def test_receipt_redaction_and_read_only_admission(native,tmp_path):
    archive=bind(native,tmp_path);record=review(native)
    altered={**record,'native_message':'https://alice:password@native.invalid/file?token=private-value'}
    archive.publish('database_copy',altered)
    kept=json.dumps(archive.get(record['review_id']))
    assert 'alice:password' not in kept and 'private-value' not in kept
    for request in ({'operation':'list','limit':True},{'operation':'get','review_id':'../owned'},
        {'operation':'start','review_id':record['review_id']},{'operation':'get','review_id':record['review_id'],'confirmed':True}):
        with pytest.raises(ValueError):action(archive,request)


def test_receipt_storage_failure_cannot_prevent_native_connection_release(native,tmp_path):
    archive=bind(native,tmp_path);record=review(native)
    bound=native.client._receipt_archives[id(native.handle)]
    with patch.object(bound,'release',side_effect=OSError('Owned receipt storage unavailable')):
        result=native.client.close_session(native.handle)
    assert result['connection_released'] is True and result['receipt_release_recorded'] is False
    assert native.handle not in native.client._connections
    import duckdb
    with pytest.raises(duckdb.ConnectionException):native.handle.execute('SELECT 1')
    retained=archive.get(record['review_id'])
    assert retained['original_session']['state']=='open'  # Last persisted state, never a live observation.
    assert retained['live_session_observed'] is False and retained['transaction_finality_inferred'] is False
