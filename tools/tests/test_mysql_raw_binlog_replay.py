"""Native raw group admission, credential positions and filesystem grants."""
import json
from pathlib import Path
import struct
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_raw_binlog_replay as native
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError


def options(**changes):return native.options({'target_confirmation':str(uuid.uuid4()),**changes})


@pytest.mark.parametrize('extra',[{'stop_mode':[]},{'stop_mode':'before','stop_file':'../outside','stop_position':'4'},
    {'stop_mode':'after','stop_file':'native.1','stop_position':9007199254740993},{'stop_mode':'all','stop_file':'native.1'},
    {'start_file':'native.1'},{'start_file':'native.1','start_position':'18446744073709551616'},
    {'timeout_seconds':True},{'target_confirmation':'not-native'},{'path':'/outside'}])
def test_raw_options_refuse_unscoped_or_inexact_boundaries(extra):
    with pytest.raises(BinlogArchiveError):options(**extra)


def test_unsigned_file_positions_remain_decimal_strings():
    selected=options(stop_mode='before',stop_file='native.000001',stop_position='18446744073709551615',start_file='native.000001',start_position='9007199254740993')
    assert selected['stop_position']=='18446744073709551615' and selected['start_position']=='9007199254740993'


def frame(kind):return struct.pack('<IBIIIH',1,kind,101,19,0,0)


def test_native_order_group_windows_and_cross_file_after_boundary(tmp_path):
    names=['z-source.1','a-source.2']
    (tmp_path/'archive.json').write_text(json.dumps({'format':'mysql-raw-binlog@9.7.0','logs':[{'name':name} for name in names]}))
    (tmp_path/names[0]).write_bytes(b'\xfebin'+frame(15)+frame(34)+frame(16)+frame(33)+frame(16))
    (tmp_path/names[1]).write_bytes(b'\xfebin'+frame(15)+frame(42)+frame(16)+frame(34)+frame(16))
    page=native.inventory(tmp_path,offset=1,limit=2)
    assert page['total']==4 and page['more'] and [row['event_type'] for row in page['groups']]==[33,42]
    assert page['log_names']==names
    selected=options(start_file=names[1],start_position='61',stop_mode='after',stop_file=names[1],stop_position='61')
    observed=native.inventory(tmp_path,selected=selected)
    assert observed['anonymous_groups_present'] and not observed['named_groups_present']
    selected=options(stop_mode='after',stop_file=names[0],stop_position='61')
    assert native.inventory(tmp_path,selected=selected)['stop_after']['file']==names[1]
    for bad in [options(start_file=names[0],start_position='24'),options(stop_mode='before',stop_file=names[0],stop_position='24'),
                options(start_file=names[1],start_position='61',stop_mode='before',stop_file=names[0],stop_position='61')]:
        with pytest.raises(BinlogArchiveError):native.inventory(tmp_path,selected=bad)


def test_native_factor_three_is_not_shifted_into_factor_two():
    class Client:
        def _tool_secrets(self,route,seal):return seal(['one\n"\\雪','three\r'])
    route={'credential_references':{'database_password':'first','database_password_3':'third'}}
    with native.delegate_credentials(Client(),route) as lease:
        actual=lease.use(lambda view:bytes(view).decode('utf8'))
    assert actual=='[client]\npassword1="one\\n\\"\\\\雪"\npassword3="three\\r"\n'
    assert 'password2' not in actual


def test_native_header_is_staged_inside_the_filesystem_grant(tmp_path):
    source=tmp_path/'source';work=tmp_path/'work';source.mkdir();work.mkdir()
    original=b'\xfebin'+frame(15)+frame(34);(source/'native.1').write_bytes(original)
    class Runner:
        def run(self,grant,args,**_kwargs):
            staged=Path(args[-1]);assert staged.parent==work and staged.read_bytes()==original[:23]
            destination=Path(next(value.split('=',1)[1] for value in args if value.startswith('--result-file=')))
            destination.write_bytes(b'# native banner\n# event\tPrevious-GTIDs\n# native-gtid-set\n# at 23\n')
            return {'return_code':0,'executable_sha256':'decoder'}
    observed={'first_group':{},'start_boundary':{'file':'native.1'},'header_end_position':'23'}
    assert native.previous_gtids(type('Client',(),{'_tool_runner':Runner()})(),{'host':'localhost'},source,observed,work,
        {'decoder':{'executable_sha256':'decoder'}})=='native-gtid-set'
    assert (source/'native.1').read_bytes()==original
