"""Full recollection cannot turn an uncertain cursor into a native checkpoint."""
from copy import deepcopy
import socket
from types import SimpleNamespace
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace.continuous_binlog_service import ReceiverJobs, recollection_checkpoint
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    from pgadmin.cdeadmin.workspace import continuous_binlog_tails
    monkeypatch.setattr(continuous_binlog_tails,'inspect',lambda *_args,**_kwargs:([],[]))
    endpoint=str(uuid.uuid4())
    jobs=ReceiverJobs(tmp_path/'receiver-jobs',tmp_path/'receivers')
    archives=MySQLBinlogJobs(tmp_path/'archive-jobs',tmp_path/'archives')
    source={'version':'9.7.0','server_uuid':str(uuid.uuid4()),'server_id':101,'authenticated_principal':'receiver@%','active_role':'NONE'}
    capture={'identity':source,'state':{'gtid_mode':'ON','gtid_executed':str(uuid.uuid4())+':1-4'}}
    program={'executable_sha256':'owned-program','execution_host':{'kind':'application-host','hostname':socket.gethostname()}}
    result=jobs.review(1,endpoint,{'start_file':'native.000001','receiver_server_id':103},capture,'config',program,
                       continuation={'writer_scope_index':1})
    parent=jobs.load(result['job_id'],1,endpoint)
    jobs.update(parent,state='unknown',native_process_termination_confirmed=True,
                progress={'next_file':'unconfirmed.999999'},result={'next_file':'unconfirmed.999999'})
    yield SimpleNamespace(jobs=jobs,archives=archives,endpoint=endpoint,parent=jobs.load(result['job_id'],1,endpoint),capture=capture)
    jobs.close();archives.close()


def test_recollection_preserves_unknown_and_ignores_uncertain_cursors(fixture):
    f=fixture
    parent=f.jobs.recollection_parent(f.parent['job_id'],1,f.endpoint,f.archives,{'start_file':'native.000001'})
    assert parent['state']=='unknown' and parent['options']['start_file']=='native.000001'
    with pytest.raises(BinlogArchiveError,match='original native file'):
        f.jobs.recollection_parent(f.parent['job_id'],1,f.endpoint,f.archives,{'start_file':'unconfirmed.999999'})
    with pytest.raises(BinlogArchiveError,match='clean stopped'):
        f.jobs.restart_checkpoint(f.parent['job_id'],1,f.endpoint,f.archives)
    assert f.jobs.get(f.parent['job_id'],1,f.endpoint)['state']=='unknown'


def test_writer_proof_and_owner_scope_are_required(fixture):
    f=fixture
    f.jobs.update(f.parent,native_process_termination_confirmed=False)
    with pytest.raises(BinlogArchiveError,match='stopped receiver writers'):
        f.jobs.recollection_parent(f.parent['job_id'],1,f.endpoint,f.archives,{'start_file':'native.000001'})
    for owner,endpoint in ((2,f.endpoint),(True,f.endpoint),(1,str(uuid.uuid4()))):
        with pytest.raises(BinlogArchiveError):
            f.jobs.recollection_parent(f.parent['job_id'],owner,endpoint,f.archives,{'start_file':'native.000001'})


@pytest.mark.parametrize('mode',['OFF','OFF_PERMISSIVE'])
def test_non_gtid_recollection_does_not_invent_log_epoch_or_recovery_verification(fixture,mode):
    f=fixture;parent=deepcopy(f.parent);captured=deepcopy(f.capture)
    parent['source_state']['gtid_mode']=captured['state']['gtid_mode']=mode
    value=recollection_checkpoint(parent,captured,object())
    assert value['start_file']=='native.000001'
    assert value['unresolved_cursor_used'] is False and value['parent_outcome_rewritten'] is False
    assert value['native_gtid_baseline_checked'] is False
    assert value['binary_log_epoch_verified'] is False and value['database_recovery_verified'] is False


def test_native_gtid_baseline_is_observed_instead_of_comparing_strings(fixture,monkeypatch):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_clone
    f=fixture;calls=[]
    def rows(connection,statement,parameters):
        calls.append((connection,statement,parameters));return [{'valid':1}]
    monkeypatch.setattr(mysql_clone,'rows',rows)
    connection=object();value=recollection_checkpoint(f.parent,f.capture,connection)
    assert value['native_gtid_baseline_checked'] is True
    assert calls==[(connection,'SELECT GTID_SUBSET(%s,@@global.gtid_executed) AS valid',(f.parent['source_state']['gtid_executed'],))]
    monkeypatch.setattr(mysql_clone,'rows',lambda *_args:[{'valid':0}])
    with pytest.raises(BinlogArchiveError,match='lineage changed'):
        recollection_checkpoint(f.parent,f.capture,connection)


@pytest.mark.parametrize('change',['identity','mode','missing_mode'])
def test_changed_native_identity_mode_or_missing_admission_fact_is_refused(fixture,change):
    f=fixture;parent=deepcopy(f.parent);captured=deepcopy(f.capture)
    if change=='identity':captured['identity']['server_uuid']=str(uuid.uuid4())
    elif change=='mode':captured['state']['gtid_mode']='OFF'
    else:parent['source_state'].pop('gtid_mode')
    with pytest.raises(BinlogArchiveError):recollection_checkpoint(parent,captured,object())
