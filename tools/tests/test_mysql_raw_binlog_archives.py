"""Native closed-log observation races and independent MySQL raw archive grants."""
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.providers.mysql_family import closed_binlog_catalog as catalog
from pgadmin.cdeadmin.providers.mysql_family import mysql_raw_binlog_archives as raw
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace.mysql_raw_binlog_service import MySQLRawBinlogJobs
from pgadmin.cdeadmin.workspace.mariadb_binlog_service import MariaDBBinlogJobs
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs


def test_rotation_between_catalog_and_current_file_reads_is_retried(monkeypatch):
    values=iter([[{'File':'bin.2','Position':80}], [{'Log_name':'bin.1','File_size':90},{'Log_name':'bin.2','File_size':91},{'Log_name':'bin.3','File_size':92}],
        [{'File':'bin.3','Position':81}], [{'File':'bin.3','Position':81}], [{'Log_name':'bin.1','File_size':90},{'Log_name':'bin.2','File_size':91},{'Log_name':'bin.3','File_size':92}],
        [{'File':'bin.3','Position':9007199254740993}]])
    monkeypatch.setattr(catalog,'rows',lambda *_args:next(values))
    current,logs=catalog.observe(object(),'SHOW BINARY LOG STATUS')
    assert current['Position']=='9007199254740993' and [row['closed'] for row in logs]==[True,True,False]
    assert all(isinstance(row['File_size'],str) for row in logs)


def test_persistent_rotation_or_inconsistent_native_inventory_cannot_admit_an_active_log(monkeypatch):
    calls=[]
    def changing(_connection,statement):
        calls.append(statement)
        return [{'Log_name':'future.2','File_size':90}] if statement=='SHOW BINARY LOGS' else [{'File':'old.1','Position':80}]
    monkeypatch.setattr(catalog,'rows',changing)
    with pytest.raises(BinlogArchiveError,match='changed during observation'):catalog.observe(object(),'SHOW MASTER STATUS')
    assert len(calls)==9


def test_native_raw_range_requires_closed_contiguous_server_order():
    captured={'status':'available','identity':{'server_uuid':'native'},'logs':[
        {'Log_name':'bin.1','closed':True},{'Log_name':'bin.2','closed':True},{'Log_name':'bin.3','closed':False}]}
    assert len(raw.selected_logs(captured,raw.options({'log_names':['bin.1','bin.2']})))==2
    for names in (['bin.3'],['bin.2','bin.1'],['purged.1']):
        with pytest.raises(BinlogArchiveError):raw.selected_logs(captured,raw.options({'log_names':names}))


@pytest.mark.parametrize('value',[{}, {'log_names':['../outside']},{'log_names':['C:outside']},{'log_names':['bin.1','bin.1']},
    {'log_names':['bin.1'],'stop_position':'4'},{'log_names':['bin.1'],'timeout_seconds':False},{'log_names':['bin.1\x00']},
    {'log_names':['bin.1'],'output':'/arbitrary'}])
def test_native_raw_options_do_not_accept_paths_or_implicit_replay_options(value):
    with pytest.raises(BinlogArchiveError):raw.options(value)


def test_mysql_raw_archive_cannot_silently_drop_an_authentication_factor():
    client=SimpleNamespace(_tool_secrets=lambda *_args:pytest.fail('Credentials must not be acquired after an unsupported binding'))
    for kind in ('database_password_2','database_password_3'):
        with pytest.raises(BinlogArchiveError,match='factor-two/three'):raw.delegate_credentials(client,{'credential_references':{kind:'owned'}})


def test_private_defaults_credential_preserves_native_escape_sequences():
    password='LF\nCR\rquote"slash\\雪é'
    client=SimpleNamespace(_tool_secrets=lambda _route,callback:callback([password]))
    lease=raw.delegate_credentials(client,{})
    try:assert lease.use(lambda view:bytes(view))=='[client]\npassword="LF\\nCR\\rquote\\"slash\\\\雪é"\n'.encode('utf8')
    finally:lease.close()
    assert lease.closed


def test_registered_native_transport_policy_is_kept_without_reading_login_paths():
    client=SimpleNamespace(_shell_connection_arguments=lambda _route:['--host=registered','--port=3307','--user=owner','--ssl-mode=VERIFY_IDENTITY',
        '--ssl-ca=/owned/ca.pem','--compress=REQUIRED','--tls-version=TLSv1.3'])
    arguments=raw.connection_arguments(client,{'host':'registered','port':3307})
    assert {'--no-login-paths','--protocol=TCP','--ssl-mode=VERIFY_IDENTITY','--ssl-ca=/owned/ca.pem','--tls-version=TLSv1.3','--compression-algorithms=zlib'}<=set(arguments)
    assert not any('password' in item for item in arguments)


def test_native_format_verifiers_and_durable_operation_identities_are_separate():
    assert len({cls.operation for cls in (MySQLRawBinlogJobs,MariaDBBinlogJobs,MySQLBinlogJobs)})==3
    assert MySQLRawBinlogJobs.native_verify is raw.verify
    assert MySQLRawBinlogJobs.native_verify is not MariaDBBinlogJobs.native_verify


def test_native_encrypted_header_length_is_distinct_from_plaintext_event_bytes():
    assert raw.decoded_length({'File_size':'1536','Encrypted':'Yes'})==1024
    assert raw.decoded_length({'File_size':'1536','Encrypted':'No'})==1536
    for value in ({'File_size':'1536'}, {'File_size':'512','Encrypted':'Yes'}, {'File_size':True,'Encrypted':'No'}):
        with pytest.raises(BinlogArchiveError):raw.decoded_length(value)


@pytest.mark.parametrize('uncertain_stage',['retrieval','parser'])
def test_unconfirmed_native_writers_never_publish_a_checkpoint(tmp_path,monkeypatch,uncertain_stage):
    import threading
    from pathlib import Path
    from pgadmin.cdeadmin.security import SecretLease
    source={'server_uuid':'owned'}
    program={'executable_sha256':'trusted','tool_version':'9.7.0','execution_host':{'kind':'application-host'}}
    monkeypatch.setattr(raw,'capture',lambda _connection:{'identity':source})
    monkeypatch.setattr(raw,'program_identity',lambda *_args,**_kwargs:program)
    monkeypatch.setattr(raw,'connection_arguments',lambda *_args:['--host=localhost'])
    monkeypatch.setattr(raw,'framing',lambda *_args,**_kwargs:(4,1,4))
    monkeypatch.setattr(raw,'verify_frames',lambda *_args,**_kwargs:{})
    class Runner:
        def run(self,grant,arguments,**_kwargs):
            stage='retrieval' if '--raw' in arguments else 'parser'
            if stage=='retrieval':(Path(grant.workspace)/'archive.incoming/native.1').write_bytes(b'\xfebin')
            return {'return_code':0,'executable_sha256':'trusted','process_observation':{'cleanup_confirmed':stage!=uncertain_stage}}
    client=SimpleNamespace(_tool_runner=Runner(),_discard_failed_session=lambda _connection:None)
    transport=raw.ArchiveTransport(client,{},SecretLease(b'[client]\n'),object())
    record={'source':source,'program':program,'options':{'log_names':['native.1'],'timeout_seconds':30},
        'source_state':{'selected_logs':[{'Log_name':'native.1','File_size':'4','Encrypted':'No'}]}}
    try:
        with pytest.raises(BinlogArchiveError,match='cleanup is unconfirmed') as observed:
            transport.execute(record,tmp_path,threading.Event(),lambda _event:None)
        assert observed.value.observation['process_observation']['cleanup_confirmed'] is False
        assert (tmp_path/'archive.incoming/native.1').is_file() and not (tmp_path/'archive').exists()
    finally:transport.close()
