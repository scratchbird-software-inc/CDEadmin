"""Exact extension sources, original native-session effects and non-replay."""
from unittest.mock import patch
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import _create_client
from pgadmin.cdeadmin.providers.duckdb import extension_actions as module


def test_native_repository_alias_url_version_and_force_are_provider_built(tmp_path):
    result=module.compile_operation({'filesystem_root':str(tmp_path)}, {'action':'install','extension_name':'httpfs',
        'force':True,'repository_kind':'URL','repository':'https://extensions.duckdb.org','version':'13e18b3'})
    assert result['source']=="FORCE INSTALL 'httpfs' FROM 'https://extensions.duckdb.org' VERSION '13e18b3'"
    assert module.compile_operation({}, {'action':'install','extension_name':'httpfs','repository_kind':'ALIAS','repository':'core'})['source']=="INSTALL 'httpfs' FROM \"core\""


@pytest.mark.parametrize('draft',[{'source_kind':'URL','source':'https://user:secret@example.test/httpfs.duckdb_extension'},
    {'repository_kind':'URL','repository':'https://user:secret@example.test'},
    {'repository_kind':'URL','repository':'https://example.test/?token=secret'},
    {'extension_name':"httpfs'; DROP TABLE t"},{'source':"another"},
    {'repository_kind':'ALIAS','repository':'core; DROP TABLE t'},{'source_sql':'LOAD httpfs'},
    {'action':'load','force':True},{'action':'load','version':'13e18b3'}])
def test_untyped_sources_credentials_and_invalid_native_options_are_refused(draft):
    with pytest.raises(ValueError):module.compile_operation({}, {'action':'install','extension_name':'httpfs',**draft})


def test_direct_public_url_installs_without_inventing_remote_native_load_support():
    source='https://example.test/httpfs.duckdb_extension'
    draft={'action':'install','extension_name':'httpfs','source_kind':'URL','source':source,'force':True}
    assert module.compile_operation({},draft)['source']=="FORCE INSTALL '"+source+"'"
    for change in [{'action':'load'},{'version':'13e18b3'},{'repository_kind':'ALIAS','repository':'core'},
            {'source':'https://example.test/\r\nhttpfs.duckdb_extension'}]:
        with pytest.raises(ValueError):module.compile_operation({},{**draft,**change})


def test_local_source_is_bound_to_root_and_file_bytes(tmp_path):
    path=tmp_path/"httpfs ' é.duckdb_extension";path.write_bytes(b'qualified by native engine at dispatch')
    route={'filesystem_root':str(tmp_path)}
    result=module.compile_operation(route,{'action':'load','extension_name':'httpfs','source_kind':'FILE','source':str(path)})
    assert "httpfs '' é" in result['source'] and result['file_identity']['sha256']
    path.write_bytes(b'changed')
    assert module.file_identity(route,str(path))!=result['file_identity']
    with pytest.raises(ValueError):module.file_identity(route,str(tmp_path/'missing'))
    with pytest.raises(Exception):module.file_identity(route,str(tmp_path.parent/'outside'))


@pytest.fixture(params=['file','memory'])
def fixture(tmp_path,request):
    route={'database':':memory:' if request.param=='memory' else str(tmp_path/'owned.duckdb'),
        'allow_memory':request.param=='memory','filesystem_root':str(tmp_path),
        'config':{'extension_directory':str(tmp_path/'cache'),'autoload_known_extensions':False,'autoinstall_known_extensions':False}}
    client=_create_client();handle=client.open_session({'route':route})
    handle.execute('CREATE TABLE pending(id INT)');client.control_transaction(handle,'commit')
    try:yield client,handle,route
    finally:client.close()


def review(fixture):
    client,handle,route=fixture
    return module.action(client,handle,route,{'operation':'review','draft':{'action':'load','extension_name':'json'}})


def apply(fixture,record):
    client,handle,route=fixture
    return module.action(client,handle,route,{'operation':'apply','review_id':record['review_id'],'review_digest':record['review_digest'],
        'confirmation':record['extension_name'],'confirmed':True})


def test_load_uses_original_native_session_without_deciding_pending_work(fixture):
    client,handle,route=fixture
    handle.execute('INSERT INTO pending VALUES (42)');handle.execute('CREATE TEMP TABLE private(id INT)')
    record=review(fixture);result=apply(fixture,record)
    assert result['state']=='acknowledged' and result['rediscovery_verified']
    assert handle.execute("SELECT json_extract('{\"a\":7}', '$.a')").fetchone()==('7',)
    assert handle.execute('SELECT id FROM pending').fetchall()==[(42,)]
    assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary AND table_name='private'").fetchone()==(1,)
    assert apply(fixture,record)==result
    handle.rollback();assert handle.execute('SELECT * FROM pending').fetchall()==[]


def test_changed_native_admission_is_refused_before_dispatch(fixture):
    _,handle,_=fixture;record=review(fixture)
    handle.execute('SET autoload_known_extensions=true')
    result=apply(fixture,record)
    assert result['state']=='refused' and result['native_dispatched'] is False


def test_review_cannot_move_to_another_native_connection(fixture):
    client,_,route=fixture;record=review(fixture);other=client.open_session({'route':route})
    try:
        with pytest.raises(ValueError,match='another or closed'):
            apply((client,other,route),record)
    finally:client.close_session(other)


def test_post_acknowledgement_failure_keeps_a_readable_receipt_without_replay(fixture):
    client,_,route=fixture;record=review(fixture);original=module.inventory;calls=[]
    def observed(handle):
        calls.append(1)
        if len(calls)>1:raise OSError('native observation unavailable')
        return original(handle)
    with patch.object(module,'inventory',side_effect=observed):
        result=apply(fixture,record)
    assert result['native_acknowledged'] and result['state']=='acknowledged' and not result['rediscovery_verified']
    with patch.object(module,'inventory',side_effect=AssertionError('mutation or native read replayed')):
        assert apply(fixture,record)==result
        assert module.action(client,fixture[1],route,{'operation':'receipt','review_id':record['review_id']})==result
