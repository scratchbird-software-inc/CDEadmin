"""Native observation generations, typed transport and transaction preservation."""
import os
from types import SimpleNamespace
import pytest
from test_sqlite_preupdate_api import native
from pgadmin.cdeadmin.providers.sqlite.preupdate_actions import action
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError


def test_lazy_inventory_and_exact_generation_admission(native,tmp_path):
    connection,api,_sessions=native;client=SimpleNamespace(close=connection.close);library=os.environ['CDEADMIN_SQLITE_PREUPDATE_LIBRARY']
    def run(operation,**fields):return action(client,connection,{'operation':operation,**fields},library)
    assert run('inventory')['helper_available']
    observed=action(client,connection,{'operation':'inventory'},str(tmp_path/'missing'))
    assert observed['helper_available'] and not observed['installed_helper_available']
    connection.execute('CREATE TABLE "native\n雪"(id INTEGER,body TEXT,b BLOB)')
    state=run('start')['status'];assert state['run_id'] and state['enabled']
    connection.execute('INSERT INTO "native\n雪" VALUES(9007199254740993,CAST(x\'FF8000\' AS TEXT),x\'\')')
    page=run('events',run_id=state['run_id']);event=page['events'][0]
    assert event['table']=='native\n雪' and event['new_values']==[{'native_type':'integer','data':'9007199254740993'},{'native_type':'text','data':{'encoding':'base64','data':'/4AA','byte_length':3,'native_storage_class':'text'}},{'native_type':'blob','data':{'encoding':'base64','data':'','byte_length':0}}]
    assert page['transaction_open'] and 'do not establish' in page['scope']
    with pytest.raises(SessionAPIError,match='Confirm'):run('clear',run_id=state['run_id'])
    changed=run('clear',run_id=state['run_id'],confirmed=True)['status'];assert changed['run_id']!=state['run_id'] and changed['enabled']
    with pytest.raises(SessionAPIError,match='identity changed'):run('events',run_id=state['run_id'])
    assert run('stop',run_id=changed['run_id'])['transaction_open']
    assert connection.execute('SELECT count(*) FROM "native\n雪"').fetchone()==(1,)
    connection.rollback();assert run('status')['status']['retained_events']==0


@pytest.mark.parametrize('native_request',[
    {'operation':'start','max_events':True}, {'operation':'start','max_json_bytes':'01'},
    {'operation':'start','max_json_bytes':'2147483648'}, {'operation':'start','extra':1},
])
def test_invalid_limits_never_enable_callback(native,native_request):
    connection,api,_sessions=native
    with pytest.raises(SessionAPIError):action(SimpleNamespace(close=connection.close),connection,native_request,os.environ['CDEADMIN_SQLITE_PREUPDATE_LIBRARY'])
    assert not api.status()['enabled']
