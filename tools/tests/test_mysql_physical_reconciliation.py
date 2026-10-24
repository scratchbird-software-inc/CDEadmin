"""Original recovery control survives upgrades without admitting new work."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

from pgadmin.cdeadmin.workspace import mysql_physical_service as service


def legacy_record(tmp_path):
    jobs=service.PhysicalJobs(tmp_path/'jobs',tmp_path/'artifacts');owner=1;endpoint=str(uuid.uuid4())
    binding={'server_uuid':str(uuid.uuid4()),'hostname':'retained-native-host','datadir':'/original/datadir'}
    options={'phase':'recover','connection':{'host':'retained-ssh-peer','platform':'posix'},'workspace':'/private/workspace',
        'executable':'/usr/bin/xtrabackup','mysql':'/usr/bin/mysql','sql_host':'127.0.0.1','sql_port':3306,
        'input_job_id':str(uuid.uuid4()),'parallel':1,'memory_bytes':67108864,'timeout_seconds':300}
    value=jobs.review(owner,endpoint,options,{'identity':{'server_uuid':binding['server_uuid']},
        'state':{'remote_review':{'host':{**binding,'platform':'linux'}},'source_connection_class':'native'}},
        'original-configuration',{'physical_sha256':'original-adapter','execution_host':{'host':'retained-ssh-peer'}})
    record=jobs.load(value['job_id'],owner,endpoint);jobs.update(record,state='unknown')
    return jobs,owner,endpoint,binding,jobs.load(value['job_id'],owner,endpoint)


@pytest.mark.parametrize('action',['reconcile','cancel','output'])
def test_original_control_uses_retained_peer_binding_and_digest_after_upgrade_without_sql(tmp_path,monkeypatch,action):
    jobs,owner,endpoint,binding,record=legacy_record(tmp_path);before=deepcopy(record)
    monkeypatch.setattr(service,'manager',lambda *_:(jobs,owner,SimpleNamespace(id=endpoint)))
    monkeypatch.setattr(service.MySQLMonitoringHost,'_configuration',lambda *_:{'changed':'registration'})
    monkeypatch.setattr(service.native,'program',Mock(side_effect=AssertionError('No new adapter admission for original control')))
    monkeypatch.setattr(service.host,'source',Mock(side_effect=AssertionError('Original source SQL must not be contacted')))
    calls=[]
    class Channel:
        def __init__(self,route,credentials):assert route==record['options']['connection'];assert credentials=={}
        def connect(self):return {'host':'retained-ssh-peer'}
        def request(self,request):
            calls.append(request)
            return {'input_digest':record['review_digest'],'state':'native_returned','return_code':0,
                'native_reply_observed':True,'supervisor_finished':True,'process_termination_confirmed':True}
        def close(self):pass
    monkeypatch.setattr(service.native,'Transport',Channel)
    result=service._action(SimpleNamespace(),object(),action,{'job_id':record['job_id'],'credentials':{}})
    assert calls[0]['binding']==binding and calls[0]['input_digest']==before['review_digest']
    assert calls[0]['action']==('status' if action=='reconcile' else action)
    after=jobs.load(record['job_id'],owner,endpoint)
    assert after['source_state']==before['source_state'] and after['program']==before['program']
    assert after['review_digest']==before['review_digest'] and after['state']=='unknown'
    if action!='output':assert result['native_process_termination_confirmed'] and result['state']=='unknown'


def test_missing_duplicate_binding_remains_listable_and_does_not_rewrite_review(tmp_path):
    jobs,owner,endpoint,binding,record=legacy_record(tmp_path)
    result=jobs.get(record['job_id'],owner,endpoint)
    assert result['host_binding']==binding and result['host_binding_source']=='retained_original_host_review'
    assert 'host_binding' not in jobs.load(record['job_id'],owner,endpoint)['source_state']
    assert result['review_digest']==record['review_digest']


@pytest.mark.parametrize('fault',['missing-host','different-uuid','invalid-uuid','relative-datadir'])
def test_missing_or_conflicting_original_binding_is_not_replaced_with_live_source(tmp_path,fault):
    jobs,owner,endpoint,_binding,record=legacy_record(tmp_path)
    if fault=='missing-host':record['source_state']['remote_review'].pop('host')
    elif fault=='different-uuid':record['source_state']['remote_review']['host']['server_uuid']=str(uuid.uuid4())
    elif fault=='invalid-uuid':record['source']['server_uuid']=record['source_state']['remote_review']['host']['server_uuid']='invalid'
    else:record['source_state']['remote_review']['host']['datadir']='relative'
    with pytest.raises(service.native.HostError):service.original_binding(record)
    assert jobs.public(record)['host_binding_unavailable']


def test_upgrade_still_prevents_new_dispatch_from_an_obsolete_review(tmp_path,monkeypatch):
    jobs,owner,endpoint,_binding,record=legacy_record(tmp_path);jobs.update(record,state='reviewed')
    monkeypatch.setattr(service,'manager',lambda *_:(jobs,owner,SimpleNamespace(id=endpoint)))
    monkeypatch.setattr(service.MySQLMonitoringHost,'_configuration',lambda *_:{'changed':'registration'})
    channel=Mock(side_effect=AssertionError('Must refuse before SSH or SQL'))
    monkeypatch.setattr(service.native,'Transport',channel)
    with pytest.raises(service.native.HostError,match='changed'):
        service._action(SimpleNamespace(),object(),'start',{'job_id':record['job_id'],'credentials':{},
            'confirmed':True,'review_digest':record['review_digest'],'delegate_database_credentials':True})
    assert not channel.called
