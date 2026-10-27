"""Native MariaDB lineage, exact transaction boundaries and target guards."""
import json
import struct

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mariadb_binlog_replay as native
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError

UID='aBcDeFgHiJkLmNoPqRsTuVwXyZ0='


@pytest.mark.parametrize('value',['01-1-2','0-1-18446744073709551616','4294967296-1-1','0-4294967296-1','0-1-1,0-2-2','not-a-gtid'])
def test_native_position_refuses_noncanonical_or_duplicate_domains(value):
    with pytest.raises(BinlogArchiveError):native.gtids(value)


def test_native_gtid_uses_unsigned_64bit_sequences_and_domain_server_identity():
    assert native.position(native.gtids('4294967295-4294967295-18446744073709551615,0-1-9007199254740993'))=='0-1-9007199254740993,4294967295-4294967295-18446744073709551615'
    assert native.options({'target_confirmation':UID,'stop_mode':'before','stop_gtid':'0-173-18446744073709551615'})['stop_gtid']=='0-173-18446744073709551615'


@pytest.mark.parametrize('extra',[{'stop_mode':[]},{'stop_gtid':'0-173-1'},{'stop_mode':'before','stop_gtid':'0-1-1,1-1-1'},{'timeout_seconds':True},{'target_confirmation':'../unregistered'},{'path':'/unregistered'}])
def test_options_preserve_engine_native_scope(extra):
    with pytest.raises(BinlogArchiveError):native.options({'target_confirmation':UID,**extra})


def event(kind,body,server=173):
    return struct.pack('<IBIIIH',1,kind,server,19+len(body),0,0)+body


def native_log(path,baseline,events):
    state=struct.pack('<I',len(baseline))+b''.join(struct.pack('<IIQ',domain,server,seq) for domain,server,seq in baseline)
    path.write_bytes(b'\xfebin'+event(163,state)+b''.join(event(162,struct.pack('<QIB',seq,domain,0),server) for domain,server,seq in events))


def test_inventory_tracks_global_file_boundaries_and_native_multi_domain_lineage(tmp_path):
    names=['z-native.000001','a-native.000002']
    native_log(tmp_path/names[0],[(0,173,9007199254740993)],[(0,173,9007199254740994),(7,222,4)])
    native_log(tmp_path/names[1],[(0,173,9007199254740994),(7,222,4)],[(0,174,9007199254740998),(7,222,8)])
    (tmp_path/'archive.json').write_text(json.dumps({'logs':[{'name':name} for name in names]}))
    observed=native.inventory(tmp_path,{},wanted=['0-174-9007199254740998','7-999-8'],stop='7-222-4')
    assert observed['log_names']==names and observed['start_gtid_pos']=='0-173-9007199254740993'
    assert observed['end_gtid_pos']=='0-174-9007199254740998,7-222-8'
    assert observed['matched_gtids']==['0-174-9007199254740998'] and observed['gtid_events']=='4'
    assert observed['stop_before']['file_index']==0 and observed['stop_after']['file_index']==1
    # A gap between closed files must not become apparent success.
    native_log(tmp_path/names[1],[(0,173,9007199254740995),(7,222,4)],[(0,174,9007199254740998)])
    with pytest.raises(BinlogArchiveError,match='gap'):native.inventory(tmp_path,{})


def test_lineage_admission_distinguishes_sequence_and_source_server(monkeypatch):
    target={'identity':{'server_uid':UID},'state':{'log_bin':1,'gtid_strict_mode':1,'replay_gtid_pos':'0-173-8'}}
    monkeypatch.setattr(native,'capture_target',lambda _connection:target)
    selected=native.options({'target_confirmation':UID})
    observed={'start_gtid_pos':'0-173-7','end_gtid_pos':'0-174-10','matched_gtids':['0-173-8']}
    assert native.admission(object(),{'source_uid':'other'},selected,observed)==target
    target['state']['replay_gtid_pos']='0-174-8'
    with pytest.raises(BinlogArchiveError,match='lineage'):native.admission(object(),{'source_uid':'other'},selected,observed)
    target['state']['replay_gtid_pos']='0-174-7'
    with pytest.raises(BinlogArchiveError,match='base first'):native.admission(object(),{'source_uid':'other'},selected,observed)


def test_guard_uses_noninterpolated_native_literals_and_checks_after_lock():
    target={'server_uid':UID,'server_id':173,'version':'12.2.2-MariaDB','authenticated_principal':"a'\\\n雪@%",'active_role':None}
    source=native.guard(target,{'gtid_current_pos':'0-173-7','gtid_binlog_pos':'0-173-9007199254740993','gtid_slave_pos':'0-173-7','log_bin':1,'gtid_strict_mode':1},'nonce')
    assert "a'" not in source and '雪' not in source and ' <=> NULL' in source
    assert source.index('GET_LOCK(')<source.index('@@global.gtid_current_pos')
    assert 'RESIGNAL' in source and ':refused' not in source  # control literals are hex encoded
