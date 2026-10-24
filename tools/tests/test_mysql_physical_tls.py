"""Registered TLS policy, private host delegation and certificate recovery."""
from copy import deepcopy
import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as worker
from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_worker as recovery
from pgadmin.cdeadmin.workspace import mysql_physical_service as physical
from pgadmin.cdeadmin.workspace import mysql_physical_backup_schedule as backups


def material(tmp_path):
    route={'ssl_verify_identity':True,'tls_versions':['TLSv1.2','TLSv1.3']}
    for name in ('ssl_ca','ssl_cert','ssl_key'):
        path=tmp_path/(name+'.pem');path.write_bytes(('private original '+name+' 雪\n').encode())
        route[name]=str(path)
    service=SimpleNamespace(endpoint_service=SimpleNamespace(workspace=lambda *_args,**_kwargs:(None,{'route':route},None)))
    return route,physical.sql_tls(service,None)


def test_registered_tls_policy_binds_exact_bytes_without_exposing_private_material(tmp_path):
    route,tls=material(tmp_path)
    assert tls['policy']['options']=={'ssl-mode':'VERIFY_IDENTITY','tls-version':'TLSv1.2,TLSv1.3'}
    for name,encoded in tls['files'].items():
        data=base64.b64decode(encoded)
        assert data==open(route[name],'rb').read()
        assert hashlib.sha256(data).hexdigest()==tls['policy']['files'][name]
        assert encoded not in json.dumps(tls['policy']) and route[name] not in json.dumps(tls['policy'])
    record={'options':dict(workspace='/jobs',executable='/xb',mysql='/mysql',phase='backup',sql_host='db.example',sql_port=3306,
        input_job_id=None,parallel=1,memory_bytes=67108864,timeout_seconds=60),'source':{},
        'source_state':{'host_binding':{'server_uuid':'00000000-0000-4000-8000-000000000230','hostname':'db.example','datadir':'/mysql'},'remote_review':{},'sql_tls_policy':tls['policy']},'job_id':'job','review_digest':'review'}
    request=physical.remote_request(record,'inspect')
    assert request['sql_tls_policy']==tls['policy'] and 'private original' not in json.dumps(request)


def test_host_tls_files_preserve_native_policy_and_are_private_then_erased(tmp_path):
    app=tmp_path/'application';app.mkdir();_,tls=material(app)
    host=tmp_path/'host';host.mkdir()
    request={'sql_host':'db.example','sql_port':3306,'sql_tls_policy':tls['policy'],
        'database_credentials':{'user':'native','password':'private\npassword','tls':tls}}
    option=worker.client_options(request,host);text=option.read_text()
    assert 'ssl-mode="VERIFY_IDENTITY"' in text and 'tls-version="TLSv1.2,TLSv1.3"' in text
    assert 'password="private\\npassword"' in text
    for name,encoded in tls['files'].items():
        path=host/('client-'+name+'.pem')
        assert path.read_bytes()==base64.b64decode(encoded) and path.stat().st_mode&0o077==0
        assert str(path) in text and str(app) not in text
    worker.clean_client_options(host);assert not list(host.iterdir())


@pytest.mark.parametrize('fault',['lowered-mode','changed-file','missing-file','unadmitted-option','missing-delegation'])
def test_native_tls_changes_refuse_before_dispatch_and_clean_partial_material(tmp_path,monkeypatch,fault):
    _,tls=material(tmp_path);host=tmp_path/'job';host.mkdir()
    request={'job_id':'owned','input_digest':'review','phase':'backup','sql_host':'db.example','sql_port':3306,
        'sql_tls_policy':deepcopy(tls['policy']),'reviewed':{'native':'same'},
        'database_credentials':{'user':'native','password':'secret','tls':tls}}
    if fault=='lowered-mode':tls['policy']['options']['ssl-mode']='REQUIRED'
    elif fault=='changed-file':tls['files']['ssl_key']=base64.b64encode(b'other private key').decode()
    elif fault=='missing-file':tls['files'].pop('ssl_key')
    elif fault=='unadmitted-option':tls['policy']['options']['init-command']='unsafe';request['sql_tls_policy']=deepcopy(tls['policy'])
    else:request['database_credentials'].pop('tls')
    worker.host.save(host/'request.json',request)
    monkeypatch.setattr(worker,'inspection',lambda _request:request['reviewed'])
    def forbidden(*_args,**_kwargs):raise AssertionError('Native dispatch must not occur')
    monkeypatch.setattr(worker.subprocess,'Popen',forbidden)
    worker.execute(host);result=worker.read_json(host/'result.json')
    assert not result['native_may_have_dispatched'] and result['state']=='not_dispatched'
    assert result['credential_cleanup_confirmed'] and worker.read_json(host/'request.json')['database_credentials'] is None
    assert not list(host.glob('client*'))


@pytest.mark.parametrize('fault',['empty','oversized','directory'])
def test_application_tls_material_is_bounded_and_regular(tmp_path,fault):
    path=tmp_path/'ca'
    if fault=='directory':path.mkdir()
    else:path.write_bytes(b'' if fault=='empty' else b'x'*131073)
    service=SimpleNamespace(endpoint_service=SimpleNamespace(workspace=lambda *_args,**_kwargs:(None,{'route':{'ssl_ca':str(path)}},None)))
    with pytest.raises(physical.native.HostError):physical.sql_tls(service,None)


def test_native_server_tls_review_detects_replacement_and_requires_loopback(tmp_path):
    route,_=material(tmp_path)
    request={'recovery_port':3307,'recovery_tls':route|{}}
    request['recovery_tls']={name:route[name] for name in ('ssl_ca','ssl_cert','ssl_key')}
    original=recovery.tls_files(request)
    (tmp_path/'ssl_key.pem').write_bytes(b'changed key')
    assert recovery.tls_files(request)!=original
    with pytest.raises(worker.Refused):recovery.tls_files({**request,'recovery_port':0})


def test_scheduled_tls_delegation_preserves_private_copy_and_excludes_unscoped_credentials(tmp_path):
    _,tls=material(tmp_path)
    host=object.__new__(backups.ScheduleHost)
    secret={'ssh':{'private_key':'owned-key'},'database':{'user':'native','password':'secret','tls':tls}}
    result=host.validate_credentials(secret);result['database']['tls']['files'].clear()
    assert secret['database']['tls']['files']
    with pytest.raises(physical.native.HostError):host.validate_credentials({**secret,'database':{**secret['database'],'unscoped':'secret'}})


@pytest.mark.parametrize('member,identity',[
    ('m','schema/m'),('./m','schema/m'),('../other/m','other/m'),('./other/m','other/m'),
    ('/live/source/m','source/m'),('../../live/m','live/m'),('/old/root/other/m','other/m')])
def test_merge_children_use_native_final_database_table_identity_and_preserve_metadata(tmp_path,member,identity):
    from test_mysql_physical import artifact
    directory=tmp_path/'base';artifact(directory);schema=directory/'schema';schema.mkdir()
    body=member+'\n#INSERT_METHOD=LAST\n';(schema/'combined.MRG').write_text(body)
    child=directory/identity;child.parent.mkdir(exist_ok=True)
    for suffix in ('.MYD','.MYI'):child.with_name(child.name+suffix).write_bytes(b'owned native MyISAM payload')
    result=worker.artifact(directory)
    expected=[{'metadata_file':'schema/combined.MRG','native_member':member,'table_file_identity':identity}]
    assert worker.merge_members(directory,worker.manifest(directory))==expected
    if member.startswith(('/','../../')):assert result['merge_members']==expected
    else:assert 'merge_members' not in result  # Preserve sealed pre-upgrade receipt shape.
    assert (schema/'combined.MRG').read_text()==body


@pytest.mark.parametrize('fault',['missing-data','missing-index','backslash','nul','missing-database','oversized'])
def test_unusable_merge_child_metadata_or_missing_payload_cannot_be_verified(tmp_path,fault):
    from test_mysql_physical import artifact
    directory=tmp_path/'base';artifact(directory);schema=directory/'schema';schema.mkdir()
    member={'backslash':'C:\\live\\m','nul':'m\0','missing-database':'/m','oversized':'x'*511}.get(fault,'m')
    (schema/'combined.MRG').write_text(member+'\n#INSERT_METHOD=LAST\n')
    for suffix in ('.MYD','.MYI'):
        if suffix==('.MYD' if fault=='missing-data' else '.MYI' if fault=='missing-index' else ''):continue
        (schema/('m'+suffix)).write_bytes(b'owned native payload')
    with pytest.raises(worker.Refused,match='MERGE'):worker.artifact(directory)
