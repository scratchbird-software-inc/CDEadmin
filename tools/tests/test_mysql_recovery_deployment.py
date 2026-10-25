"""Cold deployment ownership, exact native log bytes and read-only startup."""
from copy import deepcopy
from pathlib import Path
import socket
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_deployment as deploy
from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_worker as recovery
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as physical


def cold(tmp_path,monkeypatch):
    root=tmp_path/'physical';root.mkdir(mode=0o700);job=str(uuid.uuid4());directory=root/job;directory.mkdir()
    data=directory/'runtime-data';data.mkdir();uuid_value=str(uuid.uuid4())
    (data/'auto.cnf').write_text('[auto]\nserver-uuid='+uuid_value+'\n');(data/'mysql.ibd').write_bytes(b'owned cold dictionary')
    binding={'server_uuid':str(uuid.uuid4()),'hostname':socket.gethostname(),'datadir':str(tmp_path/'source')}
    request={'workspace':str(root),'input_job_id':job,'binding':binding}
    prior={'phase':'recover','job_id':job,'workspace':str(root),'binding':binding,'reviewed':{}}
    receipt={'sql_ready_observed':True,'runtime_process':{'birth':'runtime'},'supervisor_process':{'birth':'supervisor'},
        'sql_identity':{'server_uuid':uuid_value}}
    physical.host.save(directory/'request.json',prior);physical.host.save(directory/'result.json',receipt)
    monkeypatch.setattr(recovery,'present',lambda _:False)
    return request,directory,data


@pytest.mark.parametrize('live',['runtime','supervisor'])
def test_cold_deployment_refuses_either_original_writer_still_alive(tmp_path,monkeypatch,live):
    request,_,_=cold(tmp_path,monkeypatch)
    monkeypatch.setattr(recovery,'present',lambda value:value['birth']==live)
    with pytest.raises(deploy.Refused,match='original'):deploy.cold_input(request)


def test_cold_deployment_binds_native_filesystem_uuid_and_does_not_require_live_source_sql(tmp_path,monkeypatch):
    request,directory,data=cold(tmp_path,monkeypatch)
    assert not Path(request['binding']['datadir']).exists()
    _,_,_,snapshot=deploy.cold_input(request)
    assert snapshot['data_sha256']==physical.host.digest(physical.manifest(data))
    (data/'auto.cnf').write_text('[auto]\nserver-uuid='+str(uuid.uuid4())+'\n')
    with pytest.raises(deploy.Refused,match='selected native instance'):deploy.cold_input(request)


def test_cold_deployment_preserves_binary_log_bytes_and_rebases_only_the_native_index(tmp_path,monkeypatch):
    request,directory,_=cold(tmp_path,monkeypatch)
    log=directory/'recovery-bin.000001';log.write_bytes(b'\xfebin\x00\xffnative encrypted or plain payload')
    (directory/'recovery-bin.index').write_text(str(log)+'\n')
    snapshot=deploy.cold_input(request)[3];target=tmp_path/'permanent';target.mkdir()
    deploy.copy_logs(directory,target,snapshot['binary_logs'])
    assert (target/log.name).read_bytes()==log.read_bytes()
    assert (target/'recovery-bin.index').read_text()==str(target/log.name)+'\n'
    log.write_bytes(b'changed source bytes')
    with pytest.raises(deploy.Refused,match='changed'):deploy.copy_logs(directory,tmp_path/'another',snapshot['binary_logs'])


@pytest.mark.parametrize('entry',['../other.bin','/another/recovery-bin.000001','recovery-bin.index','recovery-bin.000001\nrecovery-bin.000001'])
def test_deployment_does_not_copy_unbound_or_duplicate_log_files(tmp_path,monkeypatch,entry):
    request,directory,_=cold(tmp_path,monkeypatch)
    (directory/'recovery-bin.000001').write_bytes(b'owned log')
    (directory/'recovery-bin.index').write_text(entry+'\n')
    with pytest.raises(deploy.Refused):deploy.cold_input(request)


@pytest.mark.parametrize('mode',['read_only','replay'])
def test_permanent_service_starts_read_only_with_native_logging_and_explicit_listener(tmp_path,mode):
    request={'recovery_gtid_mode':'ON','memory_bytes':67108864,'recovery_mode':mode,'recovery_server_id':22,'recovery_port':3344}
    observed={'os_account':{'name':'native-user'},'configuration':{}}
    selected={'bind_address':'::1','port':3355,'server_id':33}
    args,aliases=recovery.runtime_arguments(request,observed,tmp_path,tmp_path/'data',deployment=selected)
    assert aliases is None
    assert '--read-only=OFF' not in args and '--super-read-only=OFF' not in args and '--skip-log-bin' not in args
    assert all(value in args for value in ['--read-only=ON','--super-read-only=ON','--event-scheduler=OFF','--bind-address=::1','--port=3355','--server-id=33','--skip-replica-start','--loose-group-replication-start-on-boot=OFF','--upgrade=NONE'])
    assert len([value for value in args if value.startswith('--log-bin=')])==1
    assert [value for value in args if value.startswith('--datadir=')]==['--datadir='+str(tmp_path/'data')]


def test_linux_host_paths_are_validated_without_using_the_desktop_filesystem(tmp_path):
    selected={'directory':'/var/lib/owned-new-instance','service':'owned-native.service','bind_address':'0.0.0.0','port':3306,'server_id':34}
    assert deploy.options(deepcopy(selected),host_paths=False)==selected
    for changes in ({'service':True},{'service':'bad/name.service'},{'port':True},{'server_id':0},{'directory':'relative'},{'bind_address':'a hostname'}):
        with pytest.raises(deploy.Refused):deploy.options({**selected,**changes},host_paths=False)


def test_writable_startup_claim_cannot_be_replayed_or_reassigned_after_a_lost_reply(tmp_path,monkeypatch):
    target=tmp_path/'permanent';target.mkdir();directory=tmp_path/'job';directory.mkdir()
    uuid_value=str(uuid.uuid4());job=str(uuid.uuid4())
    physical.host.save(directory/'request.json',{'job_id':job,'input_digest':'stage-digest','deployment':{'directory':str(target)}})
    physical.host.save(directory/'result.json',{'original_outcome':'unknown'})
    manifest={'arguments':['--read-only=ON','--super-read-only=ON','--event-scheduler=OFF','--port=3355']}
    physical.host.save(target/'deployment.json',manifest)
    monkeypatch.setattr(deploy,'observe',lambda *_:{'deployment_observation':{'permanent_native_process_verified':True,'recovered_uuid':uuid_value}})
    selected={'job_id':str(uuid.uuid4()),'review_digest':'a'*64,'target_uuid':uuid_value,'event_scheduler':'OFF'}
    result=deploy.activate_policy(directory,selected);activation=result['activation']
    assert activation['manifest_sha256']==physical.host.file_hash(target/'deployment.json')
    assert '--read-only=OFF' in physical.read_json(target/'deployment.json')['arguments']
    assert physical.read_json(directory/'result.json')=={'original_outcome':'unknown'}
    assert deploy.activate_policy(directory,selected)['original_claim_exists'] is True
    with pytest.raises(deploy.Refused,match='Another cutover'):deploy.activate_policy(directory,{**selected,'job_id':str(uuid.uuid4())})
    (target/'activation.json').unlink()
    assert deploy.activate_policy(directory,selected)=={'automatic_retry':False,'original_claim_exists':True,'activation':None}


def test_offline_service_binding_uses_owned_private_data_when_native_names_alias_the_old_source(tmp_path):
    import sys
    host=physical.host;source=tmp_path/'original';source.mkdir();target=tmp_path/'permanent';target.mkdir()
    data=target/'runtime-data';data.mkdir();uuid_value=str(uuid.uuid4());program=Path(sys.executable).resolve()
    (source/'auto.cnf').write_text('[auto]\nserver-uuid='+str(uuid.uuid4())+'\n')
    (data/'auto.cnf').write_text('[auto]\nserver-uuid='+uuid_value+'\n')
    claim={'job_id':str(uuid.uuid4()),'input_digest':'reviewed'}
    host.save(target/'claim.json',claim)
    manifest={**claim,'recovered_uuid':uuid_value,'aliases':[{'source_root':str(source),'private_root':str(data)}],
        'selected':{'directory':str(target),'service':'recovered.service'},'program':{'path':str(program),'sha256':host.file_hash(program),'version_output':'native version metadata'}}
    host.save(target/'deployment.json',manifest)
    request={'binding':{'server_uuid':uuid_value,'hostname':socket.gethostname(),'datadir':str(source)},
        'service':{'manager':'systemd','name':'recovered.service'},'native_pid_file':str(target/'runtime.pid'),'executable':str(program)}
    result=host.request_binding(request)
    assert result['datadir']==str(data) and result['native_namespace_datadir']==str(source)
    with pytest.raises(host.Refused):host.request_binding({**request,'service':{'manager':'systemd','name':'unrelated.service'}})
    (data/'auto.cnf').write_text('[auto]\nserver-uuid='+str(uuid.uuid4())+'\n')
    with pytest.raises(host.Refused):host.request_binding(request)


def test_inactive_unit_does_not_prove_that_no_manual_process_owns_the_original_dictionary(tmp_path):
    from pgadmin.cdeadmin.providers.mysql_family.mysql_host_services import dictionary_writers
    data=tmp_path/'original';data.mkdir();dictionary=data/'mysql.ibd';dictionary.write_bytes(b'original')
    processes=tmp_path/'proc';processes.mkdir();descriptors=processes/'42'/'fd';descriptors.mkdir(parents=True)
    (descriptors/'3').symlink_to(dictionary)
    result=dictionary_writers(data,process_root=processes)
    assert result['observed'] and result['native_dictionary_writers_absent'] is False and result['holder_pids']==[42]
    (descriptors/'3').unlink()
    assert dictionary_writers(data,process_root=processes)['native_dictionary_writers_absent'] is True
