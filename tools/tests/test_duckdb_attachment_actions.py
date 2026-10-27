"""Retained native attachment finality, identity, namespace and replay guards."""
from unittest.mock import Mock, patch
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import _create_client, DuckDBPilotProvider
from pgadmin.cdeadmin.providers.duckdb.attachments import action, catalogs
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.fixture(params=['file', 'memory'])
def fixture(tmp_path, request):
    import duckdb
    primary = ':memory:' if request.param == 'memory' else str(tmp_path/'primary.duckdb')
    route = {'database': primary, 'filesystem_root': str(tmp_path), 'allow_memory': request.param == 'memory'}
    other = tmp_path/'other.duckdb';native = duckdb.connect(str(other));native.execute('CREATE TABLE data(id INT)');native.execute('INSERT INTO data VALUES (7)');native.close()
    client = _create_client();handle = client.open_session({'route': route})
    handle.execute('CREATE TABLE pending(id INT)');client.control_transaction(handle, 'commit')
    try:
        yield client, handle, route, other
    finally:
        client.close()


def review(fixture, **draft):
    client, handle, route, other = fixture
    return action(client, handle, route, {'operation': 'review', 'draft': {
        'action': 'attach', 'alias': 'extra . " é', 'path': str(other), 'read_only': True,
        'conflict': 'ERROR', 'create_if_missing': False, **draft}})


def apply(fixture, record):
    client, handle, route, _ = fixture
    return action(client, handle, route, {'operation': 'apply',
        'review_id': record['review_id'], 'review_digest': record['review_digest'],
        'confirmation': record['alias'], 'confirmed': True})


def test_attach_uses_original_pending_transaction_and_repeats_only_read(fixture):
    client, handle, route, _ = fixture
    handle.execute('INSERT INTO pending VALUES (42)');handle.execute('CREATE TEMP TABLE private(id INT)')
    record = review(fixture);result = apply(fixture, record)
    assert result['state'] == 'acknowledged' and result['rediscovery_verified']
    assert result['caller_transaction_decision_requested'] is False
    assert handle.execute('SELECT id FROM "extra . "" é".main.data').fetchall() == [(7,)]
    assert handle.execute('SELECT id FROM pending').fetchall() == [(42,)]
    assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary AND table_name='private'").fetchone() == (1,)
    assert apply(fixture, record) == result
    handle.rollback()
    assert handle.execute('SELECT id FROM pending').fetchall() == []
    assert 'extra . " é' not in [row['name'] for row in catalogs(handle)]
    assert client._attachment_contexts[id(handle)]['route'] == route


def test_detach_is_not_restored_by_rollback_and_preserves_pending_rows(fixture):
    client, handle, route, _ = fixture
    attached = apply(fixture, review(fixture));assert attached['rediscovery_verified']
    client.control_transaction(handle, 'commit')
    handle.execute('INSERT INTO pending VALUES (42)')
    record = action(client, handle, route, {'operation': 'review',
        'draft': {'action': 'detach', 'alias': attached['alias'], 'if_exists': False}})
    result = apply(fixture, record)
    assert result['state'] == 'acknowledged' and result['rediscovery_verified']
    assert handle.execute('SELECT id FROM pending').fetchall() == [(42,)]
    handle.rollback()
    assert handle.execute('SELECT id FROM pending').fetchall() == []
    assert attached['alias'] not in [row['name'] for row in catalogs(handle)]


def test_creation_requires_explicit_intent_and_file_is_not_deleted_on_rollback(fixture):
    _, handle, _, other = fixture
    path = other.parent/'created.duckdb'
    with pytest.raises(ValueError, match='existing DuckDB file'):
        review(fixture, path=str(path), read_only=False)
    record = review(fixture, path=str(path), read_only=False, create_if_missing=True)
    result = apply(fixture, record)
    assert result['state'] == 'acknowledged' and result['rediscovery_verified'] and path.is_file()
    handle.rollback();assert path.is_file()


def test_native_ascii_alias_resolution_and_ignore_do_not_read_unused_file(fixture):
    _, handle, _, other = fixture
    record = review(fixture, alias='MiXeD é');assert apply(fixture, record)['rediscovery_verified']
    missing = other.parent/'unused.duckdb'
    ignored = review(fixture, alias='mixed é', path=str(missing), conflict='IGNORE')
    assert ignored['alias'] == 'MiXeD é'
    result = apply(fixture, ignored)
    assert result['state'] == 'acknowledged' and result['rediscovery_verified'] and not missing.exists()
    assert handle.execute('SELECT id FROM "MiXeD é".main.data').fetchall() == [(7,)]


def test_stale_namespace_or_file_retires_review_before_dispatch(fixture):
    _, handle, route, other = fixture
    record = review(fixture)
    handle.execute("ATTACH '"+str(other).replace("'","''")+"' AS external_change (READ_ONLY)")
    result = apply(fixture, record)
    assert result['state'] == 'refused' and not result['native_dispatched']
    handle.execute('DETACH external_change')
    assert apply(fixture, record) == result
    record = review(fixture)
    other.rename(other.with_suffix('.moved'))
    result = apply(fixture, record)
    assert result['state'] == 'refused' and not result['native_dispatched']


def test_review_cannot_move_to_another_native_session_or_registration(fixture):
    client, handle, route, _ = fixture
    record = review(fixture);second = client.open_session({'route': route})
    request = {'operation': 'apply', 'review_id': record['review_id'], 'review_digest': record['review_digest'], 'confirmed': True, 'confirmation': record['alias']}
    with pytest.raises(ValueError, match='another or closed'):
        action(client, second, route, request)
    with pytest.raises(ValueError, match='changed registration'):
        action(client, handle, {**route, 'read_only': True}, request)


def test_primary_and_internal_catalogs_are_protected(fixture):
    client, handle, route, _ = fixture
    original = client._attachment_contexts[id(handle)]['origin'][0]
    for alias in (original.upper(), 'system', 'temp'):
        with pytest.raises(ValueError, match='original registered'):
            action(client, handle, route, {'operation': 'review', 'draft': {'action': 'detach', 'alias': alias}})


def test_valid_native_aliases_are_not_limited_to_128_bytes(fixture):
    alias = 'quoted " é . '+ 'long'*60
    record = review(fixture, alias=alias)
    result = apply(fixture, record)
    assert result['rediscovery_verified'] and result['alias'] == alias


def test_native_post_acknowledgement_failure_blocks_session_and_reads_receipt(fixture):
    client, handle, route, _ = fixture
    record = review(fixture);before = catalogs(handle)
    with patch('pgadmin.cdeadmin.providers.duckdb.attachments.catalogs', side_effect=[before, OSError('observation failed'), before]):
        result = apply(fixture, record)
    assert result['state'] == 'acknowledged' and result['native_acknowledged']
    assert not result['rediscovery_verified'] and client.describe_transaction(handle)['session_reuse_blocked']
    assert apply(fixture, record) == result
    assert action(client, handle, route, {'operation': 'receipt', 'review_id': record['review_id']}) == result


def test_native_provider_requires_authority_and_serializes_handle(fixture):
    from types import SimpleNamespace
    client, handle, route, _ = fixture
    permission = SimpleNamespace(require=Mock())
    provider = DuckDBPilotProvider(SimpleNamespace(endpoint_id='owned'), permission, client)
    provider._sessions['owned-session'] = SimpleNamespace(handle=handle)
    request = {'session_id': 'owned-session', 'language_profile': 'duckdb-sql', 'operation': 'inventory'}
    assert provider.attachment_action(request, route)['catalogs']
    client._busy.add(id(handle))
    with pytest.raises(RelationalClientError, match='active'):
        provider.attachment_action(request, route)
    client._busy.discard(id(handle))
    permission.require.side_effect = RelationalClientError('permission denied')
    with pytest.raises(RelationalClientError, match='permission denied'):
        provider.attachment_action(request, route)


def test_replace_and_missing_ok_preserve_native_behavior(fixture):
    import duckdb
    client, handle, route, other = fixture
    attached = apply(fixture, review(fixture));assert attached['rediscovery_verified']
    client.control_transaction(handle, 'commit')
    replacement = other.parent/'replacement.duckdb';native = duckdb.connect(str(replacement))
    native.execute('CREATE TABLE data(id INT)');native.execute('INSERT INTO data VALUES (9)');native.close()
    replaced = apply(fixture, review(fixture, path=str(replacement), conflict='REPLACE'))
    assert replaced['state'] == 'acknowledged' and replaced['rediscovery_verified']
    assert handle.execute('SELECT id FROM "extra . "" é".main.data').fetchall() == [(9,)]
    missing = action(client, handle, route, {'operation': 'review',
        'draft': {'action': 'detach', 'alias': 'not attached', 'if_exists': True}})
    assert apply(fixture, missing)['rediscovery_verified']


def test_changed_target_confirmation_and_readonly_authorization_never_dispatch(fixture):
    client, handle, route, _ = fixture
    record = review(fixture)
    with pytest.raises(ValueError, match='Confirm'):
        action(client, handle, route, {'operation': 'apply', 'review_id': record['review_id'],
            'review_digest': record['review_digest'], 'confirmed': True, 'confirmation': 'another'})
    assert record['alias'] not in [row['name'] for row in catalogs(handle)]
    client._attachment_contexts[id(handle)]['route'] = {**route, 'read_only': True}
    with pytest.raises(ValueError, match='writable authorization'):
        action(client, handle, {**route, 'read_only': True}, {'operation': 'review',
            'draft': {'action': 'attach', 'alias': 'writable', 'path': str(fixture[3]), 'read_only': False}})


def test_native_storage_options_create_an_observed_file_without_deciding_user_transaction(fixture):
    client, handle, route, other = fixture
    path=other.parent/'storage.duckdb'
    handle.execute('CREATE TEMP TABLE private_storage(value INT)')
    transaction=handle.execute('SELECT current_transaction_id()').fetchone()[0]
    requested={'block_size':'32768','row_group_size':'4096','storage_version':'v1.5.0'}
    record=review(fixture,path=str(path),read_only=False,create_if_missing=True,storage_options=requested)
    result=apply(fixture,record)
    assert result['state']=='acknowledged' and result['rediscovery_verified']
    selected=next(row for row in result['native_catalogs'] if row['name']==record['alias'])
    assert all(selected['options'][key]==value for key,value in requested.items())
    assert result['native_storage']['block_size']=='32768'
    assert handle.execute('SELECT current_transaction_id()').fetchone()[0]==transaction
    assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary AND table_name='private_storage'").fetchone()==(1,)
    handle.execute('CREATE TABLE "extra . "" é".main.data(id INT)')
    handle.execute('INSERT INTO "extra . "" é".main.data SELECT * FROM range(9000)')
    assert handle.execute('SELECT count(*) FROM "extra . "" é".main.data').fetchone()==(9000,)
    assert apply(fixture,record)==result
    handle.rollback()
    assert path.exists() and record['alias'] not in [row['name'] for row in catalogs(handle)]


def test_memory_compression_is_separately_authorized_and_observed(fixture):
    client,handle,route,_=fixture
    route['allow_memory']=True
    client._attachment_contexts[id(handle)]['route']['allow_memory']=True
    record=review(fixture,path=':memory:',read_only=False,storage_options={'compress':True})
    result=apply(fixture,record)
    assert result['rediscovery_verified'] and result['native_storage']['block_size']=='0'
    assert next(row for row in result['native_catalogs'] if row['name']==record['alias'])['options']['compress']=='true'
    handle.execute('CREATE TABLE "extra . "" é".main.data(id INT)')
    handle.execute('INSERT INTO "extra . "" é".main.data VALUES (42)')
    assert handle.execute('SELECT * FROM "extra . "" é".main.data').fetchall()==[(42,)]


@pytest.mark.parametrize('options',[
    {'block_size':True},{'row_group_size':4096},{'block_size':'18446744073709551616'},
    {'block_size':'1;ROLLBACK'},{'storage_version':'v1.5.0\x00'},
    {'compress':True},{'encryption_key':'must-not-enter-a-public-review'}])
def test_storage_options_refuse_unsafe_representations_and_inapplicable_compression(fixture,options):
    with pytest.raises(ValueError):
        review(fixture,storage_options=options)


def test_native_storage_refusal_is_terminal_without_retry_or_automatic_rollback(fixture):
    client,handle,_,other=fixture
    record=review(fixture,path=str(other.parent/'bad.duckdb'),read_only=False,
        create_if_missing=True,storage_options={'row_group_size':'1'})
    result=apply(fixture,record)
    assert result['state']=='refused' and not result['native_acknowledged']
    assert apply(fixture,record)==result
    assert result['caller_transaction_decision_requested'] is False


def test_detached_alias_cannot_be_reused_before_an_explicit_transaction_decision(fixture):
    client,handle,route,other=fixture
    attached=apply(fixture,review(fixture));client.control_transaction(handle,'commit')
    detached=action(client,handle,route,{'operation':'review','draft':{
        'action':'detach','alias':attached['alias'],'if_exists':False}})
    assert apply(fixture,detached)['rediscovery_verified']
    with pytest.raises(ValueError,match='current transaction'):
        review(fixture)
    assert not client.describe_transaction(handle)['session_reuse_blocked']
    client.control_transaction(handle,'commit')
    assert apply(fixture,review(fixture))['rediscovery_verified']


@pytest.mark.parametrize('cipher',['GCM','CTR'])
def test_encrypted_file_key_is_bound_privately_and_independently_reopens(fixture,cipher):
    import duckdb,hashlib,json
    client,handle,route,other=fixture
    path=other.parent/('encrypted-'+cipher+'.duckdb');key='owned private key '+cipher+" ' "+r'\xC3\xA9 \x5C'
    record=review(fixture,path=str(path),read_only=False,create_if_missing=True,
        encryption_key=key,encryption_cipher=cipher)
    assert key not in json.dumps(record,ensure_ascii=False) and 'ENCRYPTION_KEY ?' in record['source']
    descriptor={name:value for name,value in record.items() if name!='review_digest'}
    assert hashlib.sha256(json.dumps(descriptor,sort_keys=True).encode()).hexdigest()==record['review_digest']
    retained=client._attachment_reviews[record['review_id']]
    assert retained['compiled']['parameters']==(key,)
    result=apply(fixture,record)
    assert result['state']=='acknowledged' and result['rediscovery_verified']
    found=next(row for row in result['native_catalogs'] if row['name']==record['alias'])
    assert found['encrypted'] and found['cipher']==cipher
    assert key not in json.dumps(result,ensure_ascii=False)
    assert not retained['compiled'].get('parameters') and 'encryption_key' not in retained['compiled']['draft']
    assert record['review_id'] not in client._attachment_key_timers
    handle.execute('CREATE TABLE "extra . "" é".main.protected(id INT, value VARCHAR)')
    handle.execute('INSERT INTO "extra . "" é".main.protected VALUES (?,?)',[42,'private native payload 119'])
    client.control_transaction(handle,'commit')
    detached=action(client,handle,route,{'operation':'review','draft':{'action':'detach','alias':record['alias']}})
    assert apply(fixture,detached)['rediscovery_verified'];client.control_transaction(handle,'commit')
    independent=duckdb.connect()
    try:
        independent.execute("ATTACH '"+str(path).replace("'","''")+"' AS protected_file (READ_ONLY,ENCRYPTION_KEY ?,ENCRYPTION_CIPHER '"+cipher+"')",[key])
        assert independent.execute('SELECT id,value FROM protected_file.main.protected').fetchone()==(42,'private native payload 119')
        assert independent.execute("SELECT encrypted,cipher FROM duckdb_databases() WHERE database_name='protected_file'").fetchone()==(True,cipher)
    finally:independent.close()
    assert b'private native payload 119' not in path.read_bytes()


def test_unused_private_key_expires_without_dispatch_and_discard_is_immediate(fixture):
    import json,weakref
    from pgadmin.cdeadmin.providers.duckdb.attachments import expire_key
    client,handle,route,other=fixture;path=other.parent/'unused-encrypted.duckdb';key='private unused key'
    record=review(fixture,path=str(path),read_only=False,create_if_missing=True,encryption_key=key)
    expire_key(weakref.ref(client),record['review_id'])
    result=apply(fixture,record)
    assert result['state']=='credential_expired' and not path.exists()
    assert key not in json.dumps(client._attachment_reviews[record['review_id']],ensure_ascii=False)
    record=review(fixture,path=str(path),read_only=False,create_if_missing=True,encryption_key=key)
    request={'operation':'discard','review_id':record['review_id'],'review_digest':record['review_digest']}
    result=action(client,handle,route,request)
    assert result['state']=='discarded' and not result['native_dispatched'] and not path.exists()
    assert apply(fixture,record)==result
    assert key not in json.dumps(client._attachment_reviews[record['review_id']],ensure_ascii=False)


def test_native_session_close_releases_private_review_key(fixture):
    import json
    client,handle,_,other=fixture;key='private key for closed session'
    record=review(fixture,path=str(other.parent/'closed-key.duckdb'),read_only=False,create_if_missing=True,encryption_key=key)
    client.close_session(handle)
    assert not client._attachment_key_timers
    retained=client._attachment_reviews[record['review_id']]
    assert retained['state']=='credential_unavailable' and key not in json.dumps(retained,ensure_ascii=False)


def test_native_key_encoding_refusal_does_not_echo_or_retain_private_input(fixture):
    import json
    client,_,_,other=fixture;key='owned invalid native é key'
    record=review(fixture,path=str(other.parent/'bad-key-format.duckdb'),read_only=False,
        create_if_missing=True,encryption_key=key)
    result=apply(fixture,record)
    assert result['state']=='refused' and not result['native_acknowledged']
    assert result['refusal_code']=='native-key-encoding' and key not in json.dumps(result,ensure_ascii=False)
    assert not client._attachment_key_timers
    assert key not in json.dumps(client._attachment_reviews[record['review_id']],ensure_ascii=False)


def test_private_key_deadline_is_rechecked_after_native_review_revalidation(fixture,monkeypatch):
    from pgadmin.cdeadmin.providers.duckdb import attachments
    client,_,_,other=fixture;path=other.parent/'deadline-key.duckdb'
    record=review(fixture,path=str(path),read_only=False,create_if_missing=True,encryption_key='owned deadline key')
    deadline=client._attachment_reviews[record['review_id']]['deadline']
    compile_native=attachments.compile_operation
    def delayed_validation(*args,**kwargs):
        compiled=compile_native(*args,**kwargs)
        monkeypatch.setattr(attachments.time,'monotonic',lambda:deadline+1)
        return compiled
    monkeypatch.setattr(attachments,'compile_operation',delayed_validation)
    result=apply(fixture,record)
    assert result['state']=='credential_expired' and not result['native_dispatched'] and not path.exists()
    assert not client._attachment_key_timers


@pytest.mark.parametrize('options',[{'encryption_key':''},{'encryption_key':None},
    {'encryption_key':False},{'encryption_key':{'private':'value'}},
    {'encryption_cipher':'GCM'},{'encryption_key':'private','encryption_cipher':'injected;ROLLBACK'}])
def test_private_key_admission_refuses_invalid_types_and_cipher_combinations(fixture,options):
    with pytest.raises(ValueError):review(fixture,**options)
