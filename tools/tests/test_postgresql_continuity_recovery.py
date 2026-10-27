"""Recovery admission, independent bytes, native SQL identities and receipts."""
import csv
import json
import os
from pathlib import Path
import threading

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_recovery import independent_copy, recovery_options, recovery_command, read_result


@pytest.mark.parametrize('value',[
    {'database':'x'*64},{'database':'x\x00y'},{'checks':{}},{'checks':[{'schema':'public','table':'t','sql':'arbitrary'}]},
    {'checks':[{'schema':'public','table':'t','expected_rows':9007199254740993}]},
    {'checks':[{'schema':'public','table':'t','expected_rows':'9223372036854775808'}]},
    {'checks':[{'schema':'public','table':'t'}]*2}, {'timeout_seconds':False},
])
def test_recovery_options_refuse_ambiguous_native_inputs(value):
    with pytest.raises(ContinuityError):recovery_options(value)


def test_independent_copy_remaps_tablespace_without_modifying_hardlinked_input(tmp_path):
    source=tmp_path/'source/backup';source.mkdir(parents=True)
    original=tmp_path/'original';original.write_bytes(b'original backup bytes')
    os.link(original,source/'data')
    (source/'pg_tblspc').mkdir()
    space=tmp_path/'source/tablespaces/123';space.mkdir(parents=True);(space/'table').write_bytes(b'tablespace')
    (source/'pg_tblspc/123').symlink_to(space,target_is_directory=True)
    target=tmp_path/'job/recovered-clone';target.parent.mkdir()
    receipt=independent_copy(source,target,[{'oid':123,'location':'/native-space'}],progress=lambda _event:None,cancel_signal=threading.Event())
    assert receipt['independent_byte_copy'] and receipt['copied_bytes']==31
    (target/'data').write_bytes(b'changed recovery copy')
    (target/'pg_tblspc/123/table').write_bytes(b'recovered tablespace')
    assert original.read_bytes()==b'original backup bytes' and (space/'table').read_bytes()==b'tablespace'
    assert (target/'pg_tblspc/123').resolve()==tmp_path/'job/tablespaces/123'


@pytest.mark.parametrize('live_lock',[False,True])
def test_recovery_refuses_unmanaged_links_and_live_input(tmp_path,live_lock):
    source=tmp_path/'source';source.mkdir();(source/'escape').symlink_to(tmp_path)
    if live_lock:(source/'postmaster.pid').write_text('live')
    with pytest.raises(ContinuityError):
        independent_copy(source,tmp_path/'copy',[],progress=lambda _event:None,cancel_signal=threading.Event())


def test_copy_cancellation_stops_before_any_file_is_written(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'data').write_bytes(b'input')
    signal=threading.Event()
    def cancel(_event):signal.set()
    with pytest.raises(ContinuityError,match='cancelled'):
        independent_copy(source,tmp_path/'copy',[],progress=cancel,cancel_signal=signal)
    assert not (tmp_path/'copy').exists() and (source/'data').read_bytes()==b'input'


def test_standalone_command_preserves_identifiers_and_discards_only_clone_configuration(tmp_path):
    clone=tmp_path/'recovered-clone';clone.mkdir()
    for name in ('standby.signal','recovery.signal','tablespace_map'):(clone/name).write_text('old')
    (clone/'postgresql.auto.conf').write_text('shared_preload_libraries=untrusted')
    options=recovery_options({'database':'-ü\nDb','checks':[{'schema':'s\n$$','table':'t"😀\n','expected_rows':'9007199254740993'}]})
    args,sql,output=recovery_command(tmp_path,options,'job-token')
    assert args[:2]==['--single','-j'] and args[-2:]==['--','-ü\nDb']
    assert sql.endswith(b'\n\n') and b'\n\n' not in sql[:-2]
    assert sql.isascii() and b"ENCODING 'UTF8'" in sql
    assert b'\\+01F600' in sql and b'BEGIN READ ONLY' in sql and b"a.amname=''heap''" in sql
    assert output==tmp_path/'recovery-result.csv'
    assert (clone/'postgresql.auto.conf').read_bytes()==b''
    assert not (clone/'tablespace_map').exists() and "restore_command = ''" in (tmp_path/'recovery.conf').read_text()


def result_file(path,value):
    with path.open('w',newline='',encoding='utf8') as stream:csv.writer(stream).writerow([json.dumps(value)])


def test_native_result_requires_exact_identity_completion_and_reviewed_row_counts(tmp_path):
    options=recovery_options({'checks':[{'schema':'public','table':'native','expected_rows':'9007199254740993'}]})
    value={'token':'job','system_identifier':'123','database':'postgres','server_version':180003,'in_recovery':False,
           'checks':[{'schema':'public','table':'native','rows':'9007199254740993'}]}
    path=tmp_path/'result.csv';result_file(path,value)
    assert read_result(path,options,'job','123')['checks'][0]['rows']=='9007199254740993'
    for changed in ({'token':'other'},{'system_identifier':'124'},{'in_recovery':True},{'server_version':180003.0},
                    {'checks':[{'schema':'public','table':'native','rows':'9007199254740994'}]}):
        result_file(path,{**value,**changed})
        with pytest.raises(ContinuityError):read_result(path,options,'job','123')
    path.unlink()
    with pytest.raises(ContinuityError,match='SQL result'):read_result(path,options,'job','123')
