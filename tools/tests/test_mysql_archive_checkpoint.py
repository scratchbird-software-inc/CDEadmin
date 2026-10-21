"""Native rotation boundaries, sealed catalog successors and dispatch fences."""
from copy import deepcopy
import hashlib
import json
import struct
import threading
from types import SimpleNamespace
import uuid
import zlib

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_archive_checkpoint as native
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace import mysql_receiver_checkpoints as workspace


def rotation(name, *, checksum=True, position=4):
    body=struct.pack('<Q',position)+name.encode('utf8')
    event=struct.pack('<IBIIIH',123,4,101,19+len(body)+(4 if checksum else 0),0,0)+body
    return event+struct.pack('<I',zlib.crc32(event)) if checksum else event


@pytest.mark.parametrize('checksum',[True,False])
@pytest.mark.parametrize('name',['native.000002',"native '雪'.000002",'a'*248+'.000002'])
def test_terminal_rotation_preserves_exact_native_name_and_position(tmp_path,checksum,name):
    path=tmp_path/'native.000001';data=b'\xfebin'+b'x'*600+rotation(name,checksum=checksum);path.write_bytes(data)
    value=native.rotation_successor(path,{'size':len(data)},'crc32' if checksum else 'native_none')
    assert value['file']==name and value['position']=='4'


@pytest.mark.parametrize('kind',['wrong_crc','noninitial_position','truncated','bad_name','wrong_size','nonrotation'])
def test_malformed_rotation_never_becomes_a_guessed_checkpoint(tmp_path,kind):
    value=rotation('../outside' if kind=='bad_name' else 'native.000002',position=42 if kind=='noninitial_position' else 4)
    if kind=='wrong_crc':value=value[:-1]+bytes([value[-1]^1])
    elif kind=='truncated':value=value[:-3]
    elif kind=='nonrotation':value=b'x'*40
    data=b'\xfebin'+value;path=tmp_path/'native.000001';path.write_bytes(data)
    with pytest.raises(BinlogArchiveError):native.rotation_successor(path,{'size':len(data)+(1 if kind=='wrong_size' else 0)},'crc32')


def sealed(tmp_path, *, rotate=True, catalog=True):
    source={'server_uuid':str(uuid.uuid4()),'version':'9.7.0'}
    directory=tmp_path/'archive';directory.mkdir()
    data=b'\xfebin'+rotation('native.000002') if rotate else b'\xfebin'+b'closed-native-file'
    (directory/'native.000001').write_bytes(data)
    metadata={'format':'mysql-raw-binlog@9.7.0','source':source,
              'logs':[{'name':'native.000001','last_event_type':4 if rotate else 3}]}
    if catalog:metadata['source_successor']={'file':'native.000002','position':'4','scope':native.SUCCESSOR_SCOPE}
    def save():
        (directory/'archive.json').write_text(json.dumps(metadata),encoding='utf8')
        return {'format':'mysql-raw-binlog@9.7.0','end_at':{'file':'native.000001','position':str(len(data))},
                'files':[{'path':p.name,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in directory.iterdir()],
                'event_integrity':[{'binlog':'native.000001','checksum_algorithm':'crc32'}]}
    return directory,source,metadata,save


@pytest.mark.parametrize('rotate,catalog,authority',[(True,True,'native-terminal-rotation'),(True,False,'native-terminal-rotation'),(False,True,'sealed-native-closed-catalog-successor')])
def test_new_and_legacy_successors_have_explicit_native_authority(tmp_path,rotate,catalog,authority):
    directory,source,_metadata,save=sealed(tmp_path,rotate=rotate,catalog=catalog)
    value=native.successor(directory,save(),source)
    assert value['next_file']=='native.000002' and value['successor_authority']==authority


@pytest.mark.parametrize('change',['metadata_bytes','source','catalog_conflict','catalog_scope','missing_evidence'])
def test_unsealed_or_conflicting_successor_evidence_is_refused(tmp_path,change):
    directory,source,metadata,save=sealed(tmp_path,rotate=change!='missing_evidence',catalog=change!='missing_evidence')
    if change=='catalog_conflict':metadata['source_successor']['file']='different.000002'
    elif change=='catalog_scope':metadata['source_successor']['scope']='unqualified'
    artifact=save()
    if change=='metadata_bytes':(directory/'archive.json').write_bytes(b'{}')
    elif change=='source':source={**source,'server_uuid':str(uuid.uuid4())}
    with pytest.raises(BinlogArchiveError):native.successor(directory,artifact,source)


def test_catalog_successor_uses_observed_order_without_incrementing_a_filename():
    value=native.catalog_successor({'logs':[{'Log_name':'z-last.000999','closed':True},{'Log_name':'a-new-base.000001','closed':False}]},'z-last.000999')
    assert value['file']=='a-new-base.000001'
    with pytest.raises(BinlogArchiveError):native.catalog_successor({'logs':[{'Log_name':'only.1','closed':True}]},'only.1')


@pytest.mark.parametrize('change',['changed_bytes','purged_successor','foreign_producer','removed'])
def test_full_verification_ownership_and_source_availability_precede_dispatch(tmp_path,monkeypatch,change):
    from pgadmin.cdeadmin.workspace import continuous_binlog_service
    directory,source,_metadata,save=sealed(tmp_path);artifact=save()
    original={'job_id':str(uuid.uuid4()),'owner':1,'endpoint_id':str(uuid.uuid4()),'source':source}
    archive={'job_id':str(uuid.uuid4()),'state':'completed','source':source,'result':{'artifact':artifact},
             'native_process_termination_confirmed':True,'continuation':{'continuous_receiver_job_id':original['job_id']}}
    captured={'identity':source,'status':'available','logs':[{'Log_name':'native.000002'}]}
    monkeypatch.setattr(continuous_binlog_service,'recollection_checkpoint',lambda *_args:{'native_gtid_baseline_checked':False})
    if change=='purged_successor':captured['logs']=[]
    elif change=='foreign_producer':archive['continuation']['continuous_receiver_job_id']=str(uuid.uuid4())
    elif change=='removed':archive['artifact_removed']=True
    archives=SimpleNamespace(load=lambda *_args:deepcopy(archive),directory=lambda _record:directory.parent,
        native_verify=lambda *_args,**_kwargs:{**artifact,'changed':True} if change=='changed_bytes' else deepcopy(artifact))
    with pytest.raises(BinlogArchiveError):workspace.checkpoint(archives,original,archive['job_id'],captured,object(),verify=True,cancel=threading.Event())
