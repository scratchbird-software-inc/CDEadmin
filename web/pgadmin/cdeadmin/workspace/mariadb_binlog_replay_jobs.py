"""MariaDB replay shares durable claims while retaining native server_uid."""
from contextlib import contextmanager
import uuid

from .mysql_binlog_replay_jobs import MySQLBinlogReplayJobs


class MariaDBBinlogReplayJobs(MySQLBinlogReplayJobs):
    operation='mariadb_binary_log_replay'

    @staticmethod
    def target_identity(record):return record['source']['server_uid']

    @contextmanager
    def fence_store(self,target_uid):
        # UUID is a filesystem key only; receipts retain the native MariaDB UID.
        with super().fence_store(str(uuid.uuid5(uuid.NAMESPACE_URL,'mariadb:'+target_uid))) as store:yield store
