"""Recovery dependencies survive restart and cannot release unrelated holds."""
from copy import deepcopy
import uuid
import pytest
from pgadmin.cdeadmin.workspace import mysql_recovery_chains as chains
from pgadmin.cdeadmin.workspace.mysql_backup_protection import Registry
from test_mysql_archive_retention import fixture, wait  # noqa: F401


def test_dependency_retirement_is_reviewed_and_cannot_resurrect_a_chain(tmp_path):
    registry=Registry(tmp_path); endpoint=str(uuid.uuid4()); chain_id=str(uuid.uuid4()); job=str(uuid.uuid4())
    record={'chain_id':chain_id,'state':'active','created_at':1,'archives':[
        {'job_id':job,'operation':'mysql_binary_log_archive','endpoint_id':endpoint}],
        'source':{'server_uuid':str(uuid.uuid4())}}
    with registry.store(1,endpoint) as store:
        store.change(lambda state:state.setdefault('mysql_recovery_chains',{}).update({chain_id:record}))
    archived={'job_id':job,'operation':'mysql_binary_log_archive','endpoint_id':endpoint,'source':record['source']}
    assert registry.protected(archived,registry.protections(1,endpoint))
    assert not registry.protected({**archived,'operation':'mysql_closed_raw_binary_log_archive'},registry.protections(1,endpoint))
    assert not registry.protected({**archived,'job_id':str(uuid.uuid4())},registry.protections(1,endpoint))
    registry=Registry(tmp_path)
    assert chains.offline(registry,1,endpoint,'list',{})['chains']==[record]
    review=chains.offline(registry,1,endpoint,'review_retire',{'chain_id':chain_id})
    request={key:review[key] for key in ('review_id','review_digest')}|{'confirmed':True}
    for owner,scope in ((2,endpoint),(1,str(uuid.uuid4()))):
        with pytest.raises(chains.BinlogArchiveError):chains.offline(registry,owner,scope,'retire',request)
    with pytest.raises(chains.BinlogArchiveError):chains.offline(registry,1,endpoint,'retire',{**request,'confirmed':False})
    result=chains.offline(registry,1,endpoint,'retire',request)
    assert result['state']=='retired' and chains.offline(registry,1,endpoint,'retire',request)==result
    assert not registry.protected(archived,registry.protections(1,endpoint))


def test_changed_dependencies_require_a_new_retirement_review(tmp_path):
    registry=Registry(tmp_path); endpoint=str(uuid.uuid4()); chain_id=str(uuid.uuid4())
    record={'chain_id':chain_id,'state':'active','created_at':1,'archives':[]}
    with registry.store(1,endpoint) as store:
        store.change(lambda state:state.setdefault('mysql_recovery_chains',{}).update({chain_id:record}))
    review=chains.offline(registry,1,endpoint,'review_retire',{'chain_id':chain_id})
    with registry.store(1,endpoint) as store:
        store.change(lambda state:state['mysql_recovery_chains'][chain_id].update(archives=['changed']))
    with pytest.raises(chains.BinlogArchiveError,match='changed'):
        chains.offline(registry,1,endpoint,'retire',{key:review[key] for key in ('review_id','review_digest')}|{'confirmed':True})


@pytest.mark.parametrize('change',[{'archive_job_ids':[[]]},{'archive_job_ids':[]},{'archive_job_ids':['bad']},
    {'stop_mode':'timestamp'},{'stop_mode':'before','stop_gtid':'a:1'}, {'unexpected':True}])
def test_dependency_selection_cannot_accept_ambiguous_or_unbound_inputs(change):
    request={'backup_id':str(uuid.uuid4()),'archive_job_ids':[str(uuid.uuid4())],'stop_mode':'all','stop_gtid':None}
    with pytest.raises(chains.BinlogArchiveError):chains.selection({**request,**change})


def test_retiring_a_blanket_backup_hold_does_not_remove_chain_dependencies(tmp_path):
    registry=Registry(tmp_path); endpoint=str(uuid.uuid4()); job=str(uuid.uuid4()); source={'server_uuid':str(uuid.uuid4())}
    ticket=registry.scoped(1,endpoint).begin(source,'native','/owned/dump',{})
    chain={'chain_id':str(uuid.uuid4()),'state':'active','created_at':1,'archives':[
        {'job_id':job,'operation':'mysql_binary_log_archive','endpoint_id':endpoint}],'source':source}
    with registry.store(1,endpoint) as store:
        store.change(lambda state:state.setdefault('mysql_recovery_chains',{}).update({chain['chain_id']:deepcopy(chain)}))
    review=registry.review_retire(1,endpoint,ticket.backup_id)
    registry.retire(1,endpoint,{key:review[key] for key in ('review_id','review_digest')}|{'confirmed':True})
    archived={'job_id':job,'operation':'mysql_binary_log_archive','endpoint_id':endpoint,'source':source}
    with pytest.raises(chains.BinlogArchiveError,match='Managed backup protection'):
        with registry.guard(1,endpoint,archived):pass
    with registry.guard(1,endpoint,{**archived,'job_id':str(uuid.uuid4())}):pass


def test_a_new_chain_blocks_an_already_reviewed_retention_before_any_file_removal(fixture,tmp_path):
    from pgadmin.cdeadmin.workspace import mysql_archive_retention as retention
    f=fixture;old=f.archive();f.archive(days=1)
    registry=f.jobs.backup_protection=Registry(tmp_path/'protection')
    review=f.action('retention_review',{'policy':{'retention_days':30,'keep_latest':1}})
    chain={'chain_id':str(uuid.uuid4()),'state':'active','created_at':1,'source':f.source,'archives':[
        {'job_id':old['job_id'],'operation':old['operation'],'endpoint_id':f.endpoint}]}
    with registry.store(1,f.endpoint) as store:
        store.change(lambda state:state.setdefault('mysql_recovery_chains',{}).update({chain['chain_id']:chain}))
    started=f.action('retention_start',{key:review[key] for key in ('job_id','review_digest')}|{'confirmed':True})
    stopped=wait(retention.manager(f.service,f.jobs),started['job_id'],f.endpoint)
    assert stopped['state']=='interrupted'
    assert not f.jobs.load(old['job_id'],1,f.endpoint).get('artifact_removal')
    assert (f.jobs.directory(old)/'archive/owned.bin').is_file()
    assert retention.candidates(f.jobs,1,f.endpoint,{'retention_days':30,'keep_latest':1})[1]['managed_backup_protected']==1
