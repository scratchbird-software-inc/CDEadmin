"""Generated original-session maintenance uses retained native script execution."""
import time
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_sqlite_connection_pragmas import native  # noqa: F401
from pgadmin.cdeadmin.data_studio.scripts import ScriptCoordinator
from pgadmin.cdeadmin.data_studio.studio import DataStudioService
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider


@pytest.mark.parametrize('maintenance',['reindex','analyze','shrink_memory'])
@pytest.mark.parametrize('stale',[False,True])
def test_native_retained_maintenance_preserves_caller_savepoint_and_stops_changed_work(native,maintenance,stale):
    path,client,handle,_=native
    provider=SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),client)
    provider._sessions={'native':SimpleNamespace(handle=handle)}
    context=SimpleNamespace(endpoint_id='owned',provider_id='org.cdeadmin.sqlite',isolation_key='owned')
    session=SimpleNamespace(language_profile='sqlite-sql',provider_session={'session_id':'native'},native_work_revision=0,provider_isolation_key='owned')
    class Studio:
        def __init__(self):
            self.scripts=ScriptCoordinator(self);self.tokens={};self.calls=[];self._occurrences={};self._sessions={'public':session}
        def _operational_session(self,_context,session_id):
            assert session_id=='public';return session,SimpleNamespace(instance=provider)
        def execute(self,_context,session_id,source,*,_script_plan_id):
            token=client.execute(handle,{'source':source,'parameters':{}})
            occurrence=str(len(self.calls));self.calls.append(source);self.tokens[occurrence]=token
            session.native_work_revision+=1
            return {'occurrence_id':occurrence}
        def poll(self,_context,occurrence):
            page=client.describe_result(self.tokens[occurrence])
            return {'operation':{'terminal':page['complete']},'result':{'complete':page['complete'],'extensions':{'sqlite':{'payload':page['payload']}}}}
    studio=Studio()
    handle.executescript('CREATE TABLE pending(value);CREATE INDEX by_value ON pending(value);SAVEPOINT caller;INSERT INTO pending VALUES(7)')
    result=DataStudioService.sqlite_connection_maintenance_review(studio,context,'public',{'maintenance':maintenance})
    assert result['state']=='ready',result
    assert studio.calls==[] and handle.in_transaction
    if stale:session.native_work_revision+=1
    deadline=time.monotonic()+10
    while result['state'] not in {'complete','stopped'}:
        assert time.monotonic()<deadline
        result=studio.scripts.advance(context,result['plan_id'],result['revision'])
        if result['state']=='waiting':time.sleep(.005)
    if stale:
        assert result['state']=='stopped' and result['stop_reason']=='source-native-work-changed' and studio.calls==[]
    else:
        assert result['state']=='complete',result
        assert len(studio.calls)==1
        again=studio.scripts.advance(context,result['plan_id'],result['revision'])
        assert again['state']=='complete' and len(studio.calls)==1
    assert handle.in_transaction and handle.execute('SELECT * FROM pending').fetchall()==[(7,)]
    handle.execute('ROLLBACK TO caller');handle.execute('RELEASE caller')
    assert handle.execute('SELECT * FROM pending').fetchall()==[]
