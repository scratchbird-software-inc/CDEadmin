"""Global heap changes run in disposable worker processes, never the test host."""
import json,os,subprocess,sys
from pathlib import Path
from unittest.mock import Mock
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.heap_settings import action
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.mark.parametrize('name',['soft_heap_limit','hard_heap_limit'])
@pytest.mark.parametrize('value',[True,1,'-1','01','1e6','9223372036854775808'])
def test_invalid_exact_bytes_never_acquires_a_cursor(name,value):
    handle=Mock()
    with pytest.raises(RelationalClientError):action(handle,{'operation':'review','pragma':name,'value':value})
    handle.cursor.assert_not_called()


@pytest.mark.parametrize('name',['soft_heap_limit','hard_heap_limit'])
def test_process_policy_requires_separate_scope_and_irreversibility_ack(name):
    handle=Mock()
    with pytest.raises(RelationalClientError):
        action(handle,{'operation':'set_connection_pragma','pragma':name,'value':'1','expected_value':'0','confirmed':True})
    handle.cursor.assert_not_called()


@pytest.mark.parametrize('name',['soft_heap_limit','hard_heap_limit'])
def test_native_descriptor_global_effect_lowering_cas_and_pending_work_in_owned_process(tmp_path,name):
    code=r'''
import json,sqlite3,sys
from types import SimpleNamespace
from unittest.mock import Mock
import test_cdeadmin_relational_providers
from pgadmin.cdeadmin.providers.sqlite.provider import _create_client,SQLiteProvider
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations,operation_draft
name=sys.argv[1];root=sys.argv[2];client=_create_client()
source=client.open_session({'route':{'database':root+'/heap.db','filesystem_root':root}})
provider=SimpleNamespace(client=client,_require=Mock(),_editor_session=lambda request:source)
def call(operation,**args):return SQLiteProvider.native_connection_pragmas_action(provider,{'operation':operation,'pragma':name,**args})
def apply(value):
    review=call('review',value=value)
    fields={'value':value,'expected_value':review['expected_value'],'confirmed':True,'process_wide_change_confirmed':True}
    if name=='hard_heap_limit':fields['irreversible_lowering_confirmed']=True
    draft=operation_draft(engine_operations('sqlite')['set_connection_pragma_'+name+'@database'],fields)
    return call('set_connection_pragma',**draft)
try:
    source.executescript('CREATE TABLE owned(value);SAVEPOINT caller;INSERT INTO owned VALUES(7)')
    peer=sqlite3.connect(':memory:')
    result=apply('1073741824')
    assert result['effective_value']=='1073741824'
    assert peer.execute('PRAGMA '+name).fetchone()==(1073741824,)
    assert source.in_transaction and source.execute('SELECT * FROM owned').fetchall()==[(7,)]
    with_peer=apply('2147483648')
    if name=='hard_heap_limit':assert with_peer['effective_value']=='1073741824' and with_peer['outcome']=='native_adjusted'
    else:assert with_peer['effective_value']=='2147483648'
    source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    assert call('inspect')['effective_value']==with_peer['effective_value']
    stale=False
    try:call('set_connection_pragma',value='1073741824',expected_value='0',confirmed=True,process_wide_change_confirmed=True,irreversible_lowering_confirmed=True)
    except RelationalClientError:stale=True
    assert stale and not result['connection_local'] and not result['rollback_restores_policy']
    provider._require.assert_any_call('administer');provider._require.assert_any_call('execute')
    print(json.dumps({'native_version':sqlite3.sqlite_version,'policy':name,'result':result,'higher_request':with_peer}))
finally:client.close()
'''
    result=subprocess.run([sys.executable,'-B','-c',code,name,str(tmp_path)],env=dict(os.environ,PYTHONPATH=str(Path(__file__).parent)+os.pathsep+os.environ.get('PYTHONPATH','')),text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    proof=json.loads(result.stdout.strip().splitlines()[-1]);assert proof['policy']==name
