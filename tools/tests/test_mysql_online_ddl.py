"""Controlled native ALTER preserves review binding and server finality."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from tools.tests.test_mysql_schema_plan import captured, table
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_online_policy import policy, structural_definition
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications
from pgadmin.cdeadmin.providers.mysql_schema_application import apply_review

SELECTED={'method':'native','algorithm':'INPLACE','lock':'NONE','lock_wait_seconds':4,'timeout_seconds':30}


def controlled(tmp_path,selected=None):
    before=captured();desired=deepcopy(before)
    table(desired)['native']['definition']=table(desired)['native']['definition'].replace('varchar(80)','varchar(120)')
    preview=plan(before,desired,before,execution=selected or SELECTED)
    preview['native_grammar_validated']=True
    applications=MySQLSchemaApplications(tmp_path/'reviews.json')
    receipt=applications.review(preview,before,desired,'owner','binding','target')
    return applications,receipt,before,desired


def test_policy_is_bound_to_exact_native_source_and_no_fallback(tmp_path):
    _,receipt,_,_=controlled(tmp_path)
    operation=receipt['plan']['operations'][0]
    assert operation['source'].endswith(', ALGORITHM=INPLACE, LOCK=NONE')
    assert operation['execution']==SELECTED
    assert 'COPY' not in operation['source']


@pytest.mark.parametrize('change',[{'algorithm':'DEFAULT'},{'algorithm':'INSTANT','lock':'NONE'},
    {'lock':'NONE; DROP TABLE t'},{'timeout_seconds':0},{'timeout_seconds':True},{'lock_wait_seconds':61}])
def test_unbounded_or_ambiguous_native_policy_is_not_admitted(change):
    with pytest.raises(ValueError):policy({**SELECTED,**change})


def test_volatile_auto_increment_is_ignored_without_touching_literals():
    first="CREATE TABLE `t` (`id` int) ENGINE=InnoDB AUTO_INCREMENT=2 COMMENT='AUTO_INCREMENT=123'"
    second=first.replace('AUTO_INCREMENT=2 ','AUTO_INCREMENT=99 ')
    assert structural_definition(first,'')==structural_definition(second,'')
    assert "'AUTO_INCREMENT=123'" in structural_definition(first,'')
    assert structural_definition(first.replace('AUTO_INCREMENT=2 ',''),'')==structural_definition(first,'')


def test_controlled_apply_uses_advisory_lock_and_retains_native_refusal(tmp_path):
    applications,receipt,before,desired=controlled(tmp_path)
    cursor=Mock();connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    cursor.fetchone.side_effect=[('9.7.0','server','demo`db'),(1,),('t',table(before)['native']['definition']),(1,)]
    error=RuntimeError('native refusal with private source');error.errno=1846
    runtime=Mock();runtime.execute.side_effect=error
    result=applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},
        'owner','binding',lambda record:apply_review(connection,record,runtime))
    assert result['state']=='unknown_outcome' and result['outcome']['native_error_reply_received']
    assert result['outcome']['error_code']==1846
    sources=[c.args[0] for c in cursor.execute.call_args_list]
    assert any('GET_LOCK' in sql for sql in sources) and not any(sql.startswith('LOCK TABLES') for sql in sources)
    assert sources[-1].startswith('SELECT RELEASE_LOCK')
    assert 'private source' not in str(result)


def test_controlled_policy_cannot_use_the_synchronous_legacy_dispatch(tmp_path):
    applications,receipt,_,_=controlled(tmp_path)
    cursor=Mock();connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    result=applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},
        'owner','binding',lambda record:apply_review(connection,record))
    assert result['state']=='not_dispatched'
    cursor.execute.assert_not_called()


def test_cancelled_before_dispatch_preserves_not_dispatched(tmp_path):
    applications,receipt,before,_=controlled(tmp_path)
    cursor=Mock();connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    cursor.fetchone.side_effect=[('9.7.0','server','demo`db'),(1,),('t',table(before)['native']['definition']),(1,)]
    runtime=Mock();runtime.checkpoint.side_effect=ValueError('cancelled before native dispatch')
    result=applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},
        'owner','binding',lambda record:apply_review(connection,record,runtime))
    assert result['state']=='not_dispatched';runtime.execute.assert_not_called()


def test_replica_scope_is_exact_and_stopped_or_unknown_lag_pauses_without_touching_credentials(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from pgadmin.cdeadmin.workspace import mysql_online_replicas as replicas
    item={'endpoint_id':2,'channel':'default`雪','max_lag_seconds':1}
    assert replicas.selected([item])==[item]
    with pytest.raises(ValueError):replicas.selected([item,item])
    observed={'source_uuid':'source','seconds_behind_source':None,'io_running':'Yes','sql_running':'No','last_io_errno':0,'last_sql_errno':0}
    monkeypatch.setattr(replicas,'sample',Mock(return_value=({'server_uuid':'replica','account':'observer@%'},observed)))
    runtime=SimpleNamespace(copy_monitors=[({**item,'server_uuid':'replica','account':'observer@%'},object(),Mock())],
        review={'plan':{'server_uuid':'source'}},copy_workspace=tmp_path,update=Mock())
    assert not replicas.observe(runtime) and (tmp_path/'lag.pause').exists()
    assert runtime.update.call_args.kwargs['replica_observations'][0]['seconds_behind_source'] is None
    observed.update(seconds_behind_source='0',sql_running='Yes')
    assert replicas.observe(runtime) and not (tmp_path/'lag.pause').exists() and (tmp_path/'heartbeat').exists()


def test_replica_channel_from_another_source_or_same_server_is_not_admitted(monkeypatch):
    from pgadmin.cdeadmin.workspace import mysql_online_replicas as replicas
    monkeypatch.setattr(replicas,'rows',Mock(side_effect=[{'server_uuid':'replica','version':'9.7.0','account':'observer@%'}]))
    replicas.rows.side_effect=[[{'server_uuid':'replica','version':'9.7.0','account':'observer@%'}],[{'Source_UUID':'other'}]]
    with pytest.raises(ValueError,match='reviewed source'):replicas.sample(object(),'channel','source')


def test_durable_worker_start_failure_is_terminal_and_releases_owned_connections(tmp_path,monkeypatch):
    from pgadmin.cdeadmin.workspace.mysql_online_jobs import OnlineJobs,status
    import threading
    applications,receipt,_,_=controlled(tmp_path)
    monkeypatch.setattr(threading.Thread,'start',Mock(side_effect=RuntimeError('native thread unavailable')))
    dispose=Mock();jobs=OnlineJobs()
    request={k:receipt[k] for k in ('review_id','review_digest')};request['confirmed']=True
    with pytest.raises(RuntimeError):jobs.start(applications,request,'owner','binding',Mock(),Mock(),dispose,Mock())
    observed=status(applications,receipt['review_id'],'owner','binding')
    assert observed['controlled_terminal'] and observed['controlled_job']['error_type']=='worker-start-failed'
    assert dispose.call_count==2 and not observed['automatic_retry']


def test_a_lost_application_worker_never_redispatches_a_durable_controlled_claim(tmp_path):
    from pgadmin.cdeadmin.workspace.mysql_online_jobs import OnlineJobs,status
    applications,receipt,_,_=controlled(tmp_path)
    with applications._store() as store:
        store.change(lambda state:state['schema_applications'][receipt['review_id']].update(
            controlled_job={'state':'starting','worker_pid':999999999,'worker_created':0}))
    assert status(applications,receipt['review_id'],'owner','binding')['controlled_job']['worker_lost']
    dispose=Mock();jobs=OnlineJobs();request={k:receipt[k] for k in ('review_id','review_digest')};request['confirmed']=True
    observed=jobs.start(applications,request,'owner','binding',Mock(),Mock(),dispose,Mock())
    assert observed['controlled_terminal'] and not jobs.jobs and dispose.call_count==2
