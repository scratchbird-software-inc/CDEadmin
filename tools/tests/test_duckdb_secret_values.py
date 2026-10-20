"""Native typed secret constants and caller-owned administration failures."""
from types import SimpleNamespace

import pytest
import test_cdeadmin_relational_providers  # noqa: F401

from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _create_client
from pgadmin.cdeadmin.providers.duckdb.secret_values import Values
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.fixture(params=['file', 'memory'])
def native(tmp_path, request):
    route={'database':str(tmp_path/'primary.duckdb') if request.param=='file' else ':memory:',
        'filesystem_root':str(tmp_path),'allow_memory':True,
        'config':{'home_directory':str(tmp_path),'secret_directory':str(tmp_path/'secrets')}}
    client=_create_client();handle=client.open_session({'route':route})
    handle.execute('CREATE TABLE pending(id INT)');client.control_transaction(handle,'commit')
    try:yield SimpleNamespace(client=client,handle=handle,route=route)
    finally:client.close()


def plan(native, name, properties, **fields):
    return ADMINISTRATION.plan({'resource_kind':'secret','operation_id':'create',
        '_provider_route':native.route,'draft':{'name':name,'secret_type':'HTTP',
            'properties':properties,**fields}})


def test_typed_native_headers_scope_and_boolean_keep_pending_work_and_redact_preview(native):
    handle=native.handle;name='typed . " é'
    handle.execute("CREATE MACRO map(k,v) AS error('caller map must not execute')")
    native.client.control_transaction(handle,'commit')
    handle.execute('INSERT INTO pending VALUES (42)')
    transaction=handle.execute('SELECT current_transaction_id()').fetchone()[0]
    token="private ' bearer . é"
    record=plan(native,name,{'bearer_token':token,'verify_ssl':True,
        'extra_http_headers':{'X-Native-Private':token,'X-Empty':''}},
        scope=['https://first.example.test/','https://second.example.test/'])
    preview=str(record['command_preview']);assert token not in preview and 'first.example' not in preview
    result=ADMINISTRATION.apply(native.client,record,connection=handle)
    assert result['accepted'] and not result['commit_requested'] and not result['rollback_requested']
    assert handle.execute('SELECT current_transaction_id()').fetchone()[0]==transaction
    assert handle.execute('SELECT id FROM pending').fetchall()==[(42,)]
    assert handle.execute('SELECT name,type,provider,persistent,storage,scope FROM duckdb_secrets() WHERE name=?',
        [name]).fetchone()==(name,'http','config',False,'memory',
            ['https://first.example.test/','https://second.example.test/'])
    native.client.control_transaction(handle,'rollback')
    assert handle.execute('SELECT id FROM pending').fetchall()==[]


def test_native_administration_refusal_does_not_rollback_caller_pending_data(native):
    handle=native.handle;handle.execute('INSERT INTO pending VALUES (42)')
    record=plan(native,'refused',{'unknown_native_http_property':'owned invalid option'})
    with pytest.raises(RelationalClientError):
        ADMINISTRATION.apply(native.client,record,connection=handle)
    assert handle.execute('SELECT id FROM pending').fetchall()==[(42,)]
    native.client.control_transaction(handle,'rollback')
    assert handle.execute('SELECT id FROM pending').fetchall()==[]


def test_native_row_count_refusal_does_not_rollback_caller_pending_data(native):
    handle=native.handle;handle.execute('INSERT INTO pending VALUES (42)')
    record={'provider_payload':{'route':native.route,'compiled':{'statements':[
        {'source':'UPDATE pending SET id=id WHERE id=0','parameters':(), 'expected_rowcount':1}]}}}
    with pytest.raises(RelationalClientError,match='row identity'):
        ADMINISTRATION.apply(native.client,record,connection=handle)
    assert handle.execute('SELECT id FROM pending').fetchall()==[(42,)]
    native.client.control_transaction(handle,'rollback')


def test_shared_administration_refusal_preserves_native_sqlite_caller_transaction(tmp_path):
    import sqlite3
    from pgadmin.cdeadmin.providers.sqlite.provider import ADMINISTRATION as sqlite_admin
    handle=sqlite3.connect(':memory:');handle.execute('CREATE TABLE pending(id INT)')
    handle.execute('INSERT INTO pending VALUES (42)')
    try:
        record=sqlite_admin.plan({'resource_kind':'table','operation_id':'create',
            '_provider_route':{'database':str(tmp_path/'approved.sqlite'),'filesystem_root':str(tmp_path)},
            'draft':{'name':'pending','columns':[{'name':'id','type':'INTEGER'}]}})
        client=SimpleNamespace(_safe_close=lambda cursor:cursor.close())
        with pytest.raises(RelationalClientError):sqlite_admin.apply(client,record,connection=handle)
        assert handle.in_transaction and handle.execute('SELECT id FROM pending').fetchall()==[(42,)]
        handle.rollback();assert handle.execute('SELECT id FROM pending').fetchall()==[]
    finally:handle.close()


@pytest.mark.parametrize('value',[float('nan'),float('inf'),set(),object()])
def test_non_json_secret_values_are_refused_without_echo(value):
    with pytest.raises(RelationalClientError,match='finite JSON'):
        Values(ADMINISTRATION).source(value)


def test_secret_constant_budgets_and_scope_persistence_types_are_explicit(native):
    nested='owned private value'
    for _ in range(34):nested=[nested]
    with pytest.raises(RelationalClientError,match='traversal budget'):Values(ADMINISTRATION).source(nested)
    with pytest.raises(RelationalClientError,match='byte budget'):Values(ADMINISTRATION).source('x'*(1024*1024+1))
    with pytest.raises(RelationalClientError,match='Boolean'):
        plan(native,'invalid',{},persistent='false')
    with pytest.raises(RelationalClientError,match='text scopes'):
        plan(native,'invalid',{},scope=[False])
