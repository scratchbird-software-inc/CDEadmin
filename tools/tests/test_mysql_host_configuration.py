"""Prospective native option-file metadata and private review admission."""
import base64
import hashlib
from pathlib import Path
import uuid
import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_host_worker as worker
from pgadmin.cdeadmin.workspace import mysql_host_service as service
from test_mysql_host import host


def replacement(data):return {'base64':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest()}


@pytest.mark.skipif(__import__('sys').platform!='linux',reason='Linux native option-file adapter')
def test_prospective_graph_reads_proposed_bytes_at_the_original_include_identity_without_installing(host):
    proposed=b'[mysqld]\n!include '+str(host.configuration).encode()+b'\nmax_connections=153\n'
    observed=worker.dispatch({**host.request,'configuration_replacement':replacement(proposed)})
    graph=observed['configuration_deployment']['prospective_configuration_graph']
    assert len([row for row in graph['entries'] if row.get('sha256')==hashlib.sha256(proposed).hexdigest()])>1
    assert host.configuration.read_text()=='[mysqld]\n'
    assert observed['configuration']['sha256']==hashlib.sha256(b'[mysqld]\n').hexdigest()


def test_replacement_bytes_are_private_but_the_review_retains_their_exact_digest(tmp_path):
    data=b'[mysqld]\n# private configuration value\n'
    selected=service.options({'connection':{'host':'owned','port':22,'username':'operator','host_key':'key','authentication':'password','platform':'posix','python':'python3'},
        'executable':'mysqld','configuration_file':'/owned/current.cnf','workspace':'/owned/jobs','timeout_seconds':60,
        'operation':'deploy_config','configuration_replacement':{'base64':replacement(data)['base64']}})
    jobs=service.HostJobs(tmp_path/'jobs',tmp_path/'files')
    review=jobs.review(1,str(uuid.uuid4()),selected,{'identity':{'server_uuid':str(uuid.uuid4())},'state':{'remote_review':{}}},'configuration',{'execution_host':{'hostname':'owned'}})
    assert review['options']['configuration_replacement']=={'sha256':hashlib.sha256(data).hexdigest(),'content_omitted':True}
    original=jobs.load(review['job_id'],1,review['endpoint_id'])
    assert original['options']['configuration_replacement']['base64']==replacement(data)['base64']
    jobs.close()


@pytest.mark.parametrize('value',[{'base64':'bad'},{'base64':123},{'base64':'AA=='},{'base64':'','sha256':'changed'}])
def test_unsafe_or_changed_native_file_bytes_are_not_an_admitted_replacement(value):
    with pytest.raises(ValueError):service.options({'connection':{'host':'owned','port':22,'username':'operator','host_key':'key','authentication':'password','platform':'posix','python':'python3'},
        'executable':'mysqld','configuration_file':'/owned/current.cnf','workspace':'/owned/jobs','timeout_seconds':60,
        'operation':'deploy_config','configuration_replacement':value})


@pytest.mark.skipif(__import__('sys').platform!='linux',reason='Linux native option-file adapter')
def test_native_extended_attributes_are_bound_as_digests_without_exposing_values(host):
    import os
    value=b'private native attribute\x00\xff'
    os.setxattr(host.configuration,'user.scratchrobin-test',value)
    data=b'[mysqld]\nmax_connections=153\n'
    observed=worker.dispatch({**host.request,'configuration_replacement':replacement(data)})
    original=observed['configuration_deployment']['original']
    assert original['extended_attributes']['user.scratchrobin-test']==hashlib.sha256(value).hexdigest()
    assert os.getxattr(host.configuration,'user.scratchrobin-test')==value


@pytest.mark.skipif(__import__('sys').platform!='linux',reason='Linux native option-file adapter')
def test_concurrent_original_file_installer_is_refused_before_validation_or_replacement(host):
    import fcntl
    data=b'[mysqld]\nmax_connections=153\n'
    request={**host.request,'configuration_replacement':replacement(data)}
    reviewed=worker.dispatch(request)
    run={**host.run,'action':'deploy_config','configuration_replacement':request['configuration_replacement'],'reviewed':reviewed}
    with host.configuration.open('rb') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(worker.Refused,match='active installer'):worker.dispatch(run)
    assert host.configuration.read_text()=='[mysqld]\n'
    assert all('--version' in arguments for _program,arguments in host.calls)
