"""Durable review ownership, dispatch uncertainty and locked native revalidation."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from tools.tests.test_mysql_schema_plan import captured, table
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplyError
from pgadmin.cdeadmin.providers.mysql_schema_application import apply_review


def reviewed(tmp_path, drop=False):
    before=captured();desired=deepcopy(before)
    if drop:table(desired)['native']['mysql_change']={'action':'drop','confirmation':'t'}
    else:table(desired)['native']['definition']=table(desired)['native']['definition'].replace('varchar(80)','varchar(120)')
    preview=plan(before,desired,before);preview['native_grammar_validated']=True
    applications=MySQLSchemaApplications(tmp_path/'receipts.json',clock=lambda:100)
    receipt=applications.review(preview,before,desired,'owner','binding','target')
    return applications,receipt,before,desired


def request(receipt):
    return {'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}


def test_claim_survives_restart_and_does_not_redispatch_after_process_death(tmp_path):
    applications,receipt,_,_=reviewed(tmp_path)
    class ProcessDeath(BaseException):pass
    with pytest.raises(ProcessDeath):
        applications.apply(request(receipt),'owner','binding',lambda _: (_ for _ in ()).throw(ProcessDeath()))
    restarted=MySQLSchemaApplications(tmp_path/'receipts.json')
    execute=Mock()
    result=restarted.apply(request(receipt),'owner','binding',execute)
    assert result['state']=='unknown_outcome' and not result['automatic_retry']
    execute.assert_not_called()
    with pytest.raises(SchemaApplyError):restarted.get(receipt['review_id'],'other','binding')
    with pytest.raises(SchemaApplyError):restarted.get(receipt['review_id'],'owner','other-target')


def test_confirmation_and_fingerprint_required_and_results_are_not_replayed(tmp_path):
    applications,receipt,_,_=reviewed(tmp_path)
    for change in ({'confirmed':False},{'review_digest':'wrong'}):
        with pytest.raises(SchemaApplyError):applications.apply({**request(receipt),**change},'owner','binding',Mock())
    execute=Mock(return_value={'state':'committed','rediscovery_verified':True})
    result=applications.apply(request(receipt),'owner','binding',execute)
    assert result['state']=='committed'
    applications.apply(request(receipt),'owner','binding',execute)
    execute.assert_called_once()
    assert 'baseline' not in result and 'desired' not in result


def execute_fixture(tmp_path):
    applications,receipt,before,desired=reviewed(tmp_path)
    cursor=Mock();cursor.fetchone.side_effect=[('9.7.0','server','demo`db'),('t',table(before)['native']['definition']),('t',table(desired)['native']['definition'])]
    connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    return applications,receipt,connection,cursor


def test_native_lock_precedes_revalidation_dispatch_and_rediscovery(tmp_path):
    applications,receipt,connection,cursor=execute_fixture(tmp_path)
    result=applications.apply(request(receipt),'owner','binding',lambda record:apply_review(connection,record))
    assert result['state']=='committed' and result['outcome']['rediscovery_verified']
    sources=[call.args[0] for call in cursor.execute.call_args_list]
    assert sources.index('LOCK TABLES `demo``db`.`t` WRITE')<sources.index('SHOW CREATE TABLE `demo``db`.`t`')<next(i for i,s in enumerate(sources) if s.startswith('ALTER TABLE'))
    assert sources[-1]=='UNLOCK TABLES' and not any(s.startswith('ROLLBACK') for s in sources)


def test_locked_drift_refuses_dispatch_and_success_ack_survives_rediscovery_failure(tmp_path):
    applications,receipt,connection,cursor=execute_fixture(tmp_path)
    cursor.fetchone.side_effect=[('9.7.0','server','demo`db'),('t','changed')]
    result=applications.apply(request(receipt),'owner','binding',lambda record:apply_review(connection,record))
    assert result['state']=='not_dispatched'
    assert not any(call.args[0].startswith('ALTER TABLE') for call in cursor.execute.call_args_list)
    applications,receipt,connection,cursor=execute_fixture(tmp_path/'second')
    cursor.fetchone.side_effect=[('9.7.0','server','demo`db'),('t',table(captured())['native']['definition']),RuntimeError('read failed')]
    result=applications.apply(request(receipt),'owner','binding',lambda record:apply_review(connection,record))
    assert result['state']=='committed' and not result['outcome']['rediscovery_verified']


def test_native_dispatch_interruption_is_unknown_and_cleaned_up(tmp_path):
    applications,receipt,connection,cursor=execute_fixture(tmp_path)
    def execute(source):
        if source.startswith('ALTER TABLE'):raise OSError('lost acknowledgement')
    cursor.execute.side_effect=execute
    result=applications.apply(request(receipt),'owner','binding',lambda record:apply_review(connection,record))
    assert result['state']=='unknown_outcome' and not result['outcome']['rediscovery_verified']
    assert cursor.execute.call_args_list[-1].args[0]=='UNLOCK TABLES'
    cursor.close.assert_called_once()


def test_separate_process_claim_and_exit_preserves_unknown_receipt(tmp_path):
    import os
    import subprocess
    import sys
    applications,receipt,_,_=reviewed(tmp_path)
    script='''
import config, json, os, sys
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications
applications=MySQLSchemaApplications(sys.argv[1],clock=lambda:101)
def execute(record):
    os._exit(37)
applications.apply(json.loads(sys.argv[2]),'owner','binding',execute)
'''
    process=subprocess.run([sys.executable,'-c',script,str(applications.path),__import__('json').dumps(request(receipt))],
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True)
    assert process.returncode==37,process.stderr.decode()
    restarted=MySQLSchemaApplications(applications.path)
    execute=Mock()
    assert restarted.apply(request(receipt),'owner','binding',execute)['state']=='unknown_outcome'
    execute.assert_not_called()


def reviewed_creation(tmp_path):
    desired=captured();before=deepcopy(desired)
    del before['rows'][table(desired)['resource_id']]
    preview=plan(before,desired,before);preview['native_grammar_validated']=True
    applications=MySQLSchemaApplications(tmp_path/'receipts.json',clock=lambda:100)
    receipt=applications.review(preview,before,desired,'owner','binding','target')
    return applications,receipt,before,desired


def test_creation_receipt_requires_absence_and_recompiles_exact_desired_definition(tmp_path):
    applications,receipt,before,desired=reviewed_creation(tmp_path)
    missing=RuntimeError('missing table');missing.errno=1146
    cursor=Mock();cursor.fetchone.side_effect=[('9.7.0','server','demo`db'),('t',table(desired)['native']['definition'])]
    def execute(source):
        if source.startswith('SHOW CREATE') and not any(c.args[0].startswith('CREATE TABLE') for c in cursor.execute.call_args_list):
            raise missing
    cursor.execute.side_effect=execute
    connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    result=applications.apply(request(receipt),'owner','binding',lambda record:apply_review(connection,record))
    assert result['state']=='committed' and result['outcome']['rediscovery_verified']
    sources=[call.args[0] for call in cursor.execute.call_args_list]
    assert len([source for source in sources if source.startswith('CREATE TABLE')])==1
    assert not any(source.startswith(('LOCK TABLES','UNLOCK TABLES','DROP TABLE')) for source in sources)
    again=Mock();assert applications.apply(request(receipt),'owner','binding',again)==result;again.assert_not_called()


def test_creation_refuses_target_that_appeared_after_review(tmp_path):
    applications,receipt,before,desired=reviewed_creation(tmp_path)
    cursor=Mock();cursor.fetchone.side_effect=[('9.7.0','server','demo`db'),('t','competing native table')]
    connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    result=applications.apply(request(receipt),'owner','binding',lambda record:apply_review(connection,record))
    assert result['state']=='not_dispatched' and 'already exists' in result['outcome']['rejection_reason']
    assert not any(call.args[0].startswith('CREATE TABLE') for call in cursor.execute.call_args_list)


def test_creation_receipt_rejects_desired_fingerprint_drift(tmp_path):
    applications,receipt,before,desired=reviewed_creation(tmp_path)
    preview=plan(before,desired,before);preview['native_grammar_validated']=True
    table(desired)['native']['definition']+=' COMMENT=\'changed\''
    with pytest.raises(SchemaApplyError,match='desired'):
        applications.review(preview,before,desired,'owner','binding','target')


def batch_review(tmp_path):
    from tools.tests.test_mysql_sql_export import model
    before=model([('table',name,'CREATE TABLE `'+name+'` (`id` int PRIMARY KEY, `note` varchar(80))',{}) for name in ('a','b','c')])
    desired=deepcopy(before)
    for row in desired['rows'].values():
        if row['kind']=='table':row['native']['definition']=row['native']['definition'].replace('varchar(80)','varchar(100)')
    preview=plan(before,desired,before);preview['native_grammar_validated']=True
    applications=MySQLSchemaApplications(tmp_path/'batch.json',clock=lambda:100)
    receipt=applications.review(preview,before,desired,'owner','binding','target')
    return applications,receipt,before,desired


def test_batch_durably_retains_committed_prefix_and_uncertainty_across_process_death(tmp_path):
    applications,receipt,_,_=batch_review(tmp_path)
    class ProcessDeath(BaseException):pass
    calls=[]
    def execute(record):
        calls.append(record['plan']['operations'][0]['name'])
        # Each provider call receives the existing single-statement contract.
        assert len(record['plan']['operations'])==1 and len(record['desired']['rows'])==1
        from pgadmin.cdeadmin.workspace.firebird_schema_plan import digest
        assert record['plan']['execution_sha256']==digest(record['plan']['operations'])
        if len(calls)==2:raise ProcessDeath()
        return {'state':'committed','rediscovery_verified':True}
    with pytest.raises(ProcessDeath):applications.apply(request(receipt),'owner','binding',execute)
    restarted=MySQLSchemaApplications(tmp_path/'batch.json',clock=lambda:101)
    observed=restarted.get(receipt['review_id'],'owner','binding')
    assert observed['state']=='unknown_outcome'
    assert [entry['state'] for entry in observed['statement_outcomes']]==['committed','unknown_outcome','not_dispatched']
    replay=Mock()
    assert restarted.apply(request(receipt),'owner','binding',replay)==observed
    replay.assert_not_called()
    assert calls==['a','b']


@pytest.mark.parametrize('second', [
    {'state':'not_dispatched','rejection_reason':'changed baseline'},
    {'state':'unknown_outcome'},
    {'state':'committed','rediscovery_verified':False},
])
def test_batch_stops_without_replaying_or_undoing_committed_prefix(tmp_path,second):
    applications,receipt,_,_=batch_review(tmp_path)
    execute=Mock(side_effect=[{'state':'committed','rediscovery_verified':True},second])
    result=applications.apply(request(receipt),'owner','binding',execute)
    assert execute.call_count==2
    assert result['statement_outcomes'][0]['state']=='committed'
    assert result['statement_outcomes'][2]['state']=='not_dispatched'
    assert result['state']==('unknown_outcome' if second['state']=='unknown_outcome' else 'partially_committed')
    assert not result['outcome']['rediscovery_verified']
    assert not result['outcome']['transactional_rollback_available']
    assert applications.apply(request(receipt),'owner','binding',execute)==result
    assert execute.call_count==2


def test_batch_success_retains_each_statement_and_rejects_duplicate_targets(tmp_path):
    applications,receipt,before,desired=batch_review(tmp_path)
    execute=Mock(return_value={'state':'committed','rediscovery_verified':True})
    result=applications.apply(request(receipt),'owner','binding',execute)
    assert result['state']=='committed' and execute.call_count==3
    assert result['outcome']['completed_statements']==3
    assert all(entry['state']=='committed' for entry in result['statement_outcomes'])
    preview=plan(before,desired,before);preview['native_grammar_validated']=True
    preview['operations'].append(deepcopy(preview['operations'][0]))
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import digest
    preview['execution_sha256']=digest(preview['operations'])
    with pytest.raises(SchemaApplyError):applications.review(preview,before,desired,'owner','binding','target')
