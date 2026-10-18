"""Stopped adoption preserves native catalog order and exact file postimages."""
import pytest

from pgadmin.cdeadmin.providers.mysql_family import continuous_binlog as receiver
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace.continuous_binlog_tails import selected_files


@pytest.mark.parametrize('family',['mysql','mariadb'])
def test_only_complete_closed_native_files_have_reviewable_postimages(tmp_path,family):
    adapter=receiver.adapter(family);directory=tmp_path/'receiving';directory.mkdir()
    identity={'server_uuid':'owned'} if family=='mysql' else {'server_uid':'owned'}
    extra={'Encrypted':'No'} if family=='mysql' else {}
    captured={'status':'available','identity':identity,'logs':[
        {'Log_name':'native.000001','closed':True,'File_size':'8',**extra},
        {'Log_name':'native.000002','closed':False,'File_size':'8',**extra}]}
    (directory/'native.000001').write_bytes(b'complete');(directory/'native.000002').write_bytes(b'active')
    chosen,postimages=selected_files(adapter,tmp_path,captured,{'log_names':['native.000001']})
    assert chosen==captured['logs'][:1] and postimages['native.000001']['st_size']=='8'
    with pytest.raises(BinlogArchiveError):selected_files(adapter,tmp_path,captured,{'log_names':['native.000002']})
    (directory/'native.000001').write_bytes(b'short')
    with pytest.raises(BinlogArchiveError,match='incomplete'):selected_files(adapter,tmp_path,captured,{'log_names':['native.000001']})
    (directory/'native.000001').unlink();(directory/'native.000001').symlink_to(directory/'native.000002')
    with pytest.raises(BinlogArchiveError,match='regular'):selected_files(adapter,tmp_path,captured,{'log_names':['native.000001']})
