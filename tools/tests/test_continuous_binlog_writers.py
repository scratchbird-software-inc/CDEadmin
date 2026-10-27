"""Real native receiver ownership, parser scope and clean restart checkpoints."""
import os
from pathlib import Path
import socket
import threading
import time
import uuid

import psutil
import pytest

from native_binlog_qualification_support import waiting_binlog
from pgadmin.cdeadmin.operations.native_writers import executable_hash
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace.continuous_binlog_service import ReceiverJobs
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs


@pytest.fixture(params=['mysql','mariadb'])
def owned(tmp_path,request):
    family=request.param
    decoder=os.environ.get('CDEADMIN_'+('MYSQL_BINLOG_BINARY' if family=='mysql' else 'MARIADB_BINLOG_BINARY'))
    if not decoder or not Path(decoder).is_file():pytest.skip('An explicit native binlog decoder is required')
    jobs=ReceiverJobs(tmp_path/'receivers.json',tmp_path/'receivers')
    archives=MySQLBinlogJobs(tmp_path/'archives.json',tmp_path/'archives');endpoint=str(uuid.uuid4())
    program={'executable_sha256':executable_hash(decoder),'execution_host':{'hostname':socket.gethostname()}}
    review=jobs.review(1,endpoint,{'start_file':'native.000001','receiver_server_id':99},
        {'identity':{'server_id':42,'server_uuid':'owned'},'state':{}},'owned',program,continuation={'writer_scope_index':1})
    record=jobs.load(review['job_id'],1,endpoint)
    jobs.update(record,state='active',worker_identity=[999999999,0],started_at=time.time())
    try:yield jobs,archives,record,endpoint,Path(decoder),family
    finally:jobs.close();archives.close()


def observe(jobs,record,process):
    jobs.update(record,progress={'pid':process.pid,'process_create_time':process.create_time()})


@pytest.mark.parametrize('recorded',[True,False])
def test_orphan_and_unrecorded_receiver_stopped_while_neighbor_survives(owned,recorded):
    jobs,archives,record,endpoint,decoder,family=owned;directory=jobs.directory(record)
    with waiting_binlog(directory,decoder,family,orphan=True) as process, waiting_binlog(directory.parent/'peer',decoder,family) as peer:
        if recorded:observe(jobs,record,process)
        result=jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint,archives)
        proof=result['writer_reconciliation']
        assert result['state']=='unknown' and proof['process_scope_stopped']
        assert proof['artifact_verified'] is False and proof['remote_finality_inferred'] is False
        assert [item['pid'] for item in proof['processes']]==[process.pid]
        assert peer.is_running() and peer.status()!=psutil.STATUS_ZOMBIE
        assert jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint,archives)['writer_reconciliation']==proof


@pytest.mark.parametrize('fault',['owner','endpoint','unconfirmed','worker','workspace','executable','birth','host','reused_pid'])
def test_refusal_never_signals_an_unadmitted_process(owned,fault):
    jobs,archives,record,endpoint,decoder,family=owned
    directory=jobs.directory(record);selected=directory.parent/'peer' if fault=='workspace' else directory
    with waiting_binlog(selected,decoder,family) as process:
        observe(jobs,record,process)
        if fault=='worker':jobs.workers[record['job_id']]=(threading.current_thread(),None)
        if fault=='executable':jobs.update(record,program={**record['program'],'executable_sha256':'0'*64})
        if fault=='birth':jobs.update(record,progress={'pid':process.pid})
        if fault=='host':jobs.update(record,program={**record['program'],'execution_host':{'hostname':'other-host.invalid'}})
        if fault=='reused_pid':jobs.update(record,progress={'pid':process.pid,'process_create_time':process.create_time()-100})
        try:
            with pytest.raises(BinlogArchiveError):
                jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':fault!='unconfirmed'},2 if fault=='owner' else 1,
                    str(uuid.uuid4()) if fault=='endpoint' else endpoint,archives)
            assert process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
        finally:jobs.workers.pop(record['job_id'],None)


@pytest.mark.parametrize('legacy',[False,True])
def test_only_linked_snapshot_parser_workspaces_are_admitted(owned,legacy):
    jobs,archives,record,endpoint,decoder,family=owned
    def child(parent_id):
        review=archives.review(1,endpoint,{}, {'identity':record['source'],'state':{}},'owned',record['program'],
            continuation={'continuous_receiver_job_id':parent_id})
        return archives.load(review['job_id'],1,endpoint)
    linked=child(record['job_id']);other=child(str(uuid.uuid4()))
    if legacy:jobs.update(record,continuation=None)
    else:
        index=jobs.directory(record)/'snapshots';index.mkdir();(index/linked['job_id']).touch()
    with waiting_binlog(archives.directory(linked),decoder,family,orphan=True) as parser, waiting_binlog(archives.directory(other),decoder,family) as peer:
        result=jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint,archives)
        assert [item['pid'] for item in result['writer_reconciliation']['processes']]==[parser.pid]
        assert peer.is_running() and peer.status()!=psutil.STATUS_ZOMBIE


def test_restart_requires_clean_checkpoint_and_rechecks_writer_scopes(owned):
    jobs,archives,record,endpoint,decoder,family=owned
    with pytest.raises(BinlogArchiveError,match='clean stopped'):jobs.restart_checkpoint(record['job_id'],1,endpoint,archives)
    jobs.update(record,state='cancelled',native_process_termination_confirmed=True,result={'next_file':'native.000002'})
    previous,checkpoint=jobs.restart_checkpoint(record['job_id'],1,endpoint,archives)
    assert previous['job_id']==record['job_id'] and checkpoint=='native.000002'
    with waiting_binlog(jobs.directory(record),decoder,family) as process:
        with pytest.raises(BinlogArchiveError,match='Reconcile remaining'):jobs.restart_checkpoint(record['job_id'],1,endpoint,archives)
        observe(jobs,record,process);jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint,archives)
    assert jobs.restart_checkpoint(record['job_id'],1,endpoint,archives)[1]==checkpoint
    jobs.update(record,state='unknown')
    with pytest.raises(BinlogArchiveError,match='clean stopped'):jobs.restart_checkpoint(record['job_id'],1,endpoint,archives)



def test_stopped_file_inspection_requires_proof_and_rechecks_new_orphans(owned):
    from pgadmin.cdeadmin.workspace.continuous_binlog_tails import stopped_parent
    jobs,archives,record,endpoint,decoder,family=owned
    with pytest.raises(BinlogArchiveError,match='Confirm stopped'):stopped_parent(jobs,archives,record['job_id'],1,endpoint)
    jobs.reconcile_writer({'job_id':record['job_id'],'confirmed':True},1,endpoint,archives)
    assert stopped_parent(jobs,archives,record['job_id'],1,endpoint)['state']=='unknown'
    with waiting_binlog(jobs.directory(record),decoder,family,orphan=True):
        with pytest.raises(BinlogArchiveError,match='Reconcile remaining'):stopped_parent(jobs,archives,record['job_id'],1,endpoint)
