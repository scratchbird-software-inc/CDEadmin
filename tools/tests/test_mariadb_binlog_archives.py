"""Native closed-log range admission preserves identity/order and engine scope."""
import pytest

from pgadmin.cdeadmin.providers.mysql_family.mariadb_binlog_archives import options,selected_logs,BinlogArchiveError
from pgadmin.cdeadmin.workspace.mariadb_binlog_service import MariaDBBinlogJobs
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs


@pytest.mark.parametrize('value',[{}, {'log_names':['../outside']},{'log_names':['C:outside']},{'log_names':['bin.1','bin.1']},
    {'log_names':['bin.1'],'start_position':'4'},{'log_names':['bin.1'],'timeout_seconds':False},{'log_names':['bin.1\x00']},
    {'log_names':['bin.1'],'output':'/arbitrary'}])
def test_raw_archives_refuse_paths_repeated_files_and_inapplicable_mysql_options(value):
    with pytest.raises(BinlogArchiveError):options(value)


def test_native_catalog_order_and_closure_are_required_without_inventing_missing_files():
    catalog={'status':'available','identity':{'server_uid':'observed-native-uid'},'logs':[
        {'Log_name':'native.1','closed':True},{'Log_name':'native.2','closed':True},
        {'Log_name':'native.3','closed':True},{'Log_name':'native.4','closed':False}]}
    assert [row['Log_name'] for row in selected_logs(catalog,options({'log_names':['native.2','native.3']}))]==['native.2','native.3']
    for names in (['native.0'],['native.4'],['native.1','native.3'],['native.3','native.2']):
        with pytest.raises(BinlogArchiveError):selected_logs(catalog,options({'log_names':names}))
    with pytest.raises(BinlogArchiveError):selected_logs({**catalog,'identity':{'server_uid':'unknown'}},options({'log_names':['native.1']}))


def test_lifecycle_sharing_keeps_native_archive_verifiers_and_operations_distinct():
    assert MariaDBBinlogJobs.operation!=MySQLBinlogJobs.operation
    assert MariaDBBinlogJobs.native_verify is not MySQLBinlogJobs.native_verify
