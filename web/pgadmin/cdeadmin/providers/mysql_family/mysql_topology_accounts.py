"""Native account setup admission without retaining authentication material.

Account methods write the native primary. Admission uses that registration and
binds native role metadata, the account row fingerprint and visible grants.
"""
import re

from .mysql_binlog_archives import BinlogArchiveError, rows


def capture(connection, account, context):
    queries = []
    results = []

    def read(source, driver_source=None, parameters=(), *, ordered=False):
        values = [list(row.values()) for row in rows(connection, driver_source or source, parameters)]
        if ordered: values.sort()
        queries.append({'sql': source, 'parameters': list(parameters), 'ordered': ordered})
        results.append(values)
        return values

    instance = read('SELECT CAST(cluster_id AS CHAR),cluster_type FROM mysql_innodb_cluster_metadata.v2_this_instance')
    if len(instance) != 1 or instance[0][1] != ('ar' if context == 'replica_set' else 'gr'):
        raise BinlogArchiveError('Select the native account setup topology and its current primary registration')
    writable = read('SELECT CAST(@@global.read_only AS CHAR),CAST(@@global.super_read_only AS CHAR)')
    if writable != [['0', '0']]:
        raise BinlogArchiveError('Account setup requires the writable native primary registration')
    if context == 'replica_set':
        role = read('SELECT member_role FROM mysql_innodb_cluster_metadata.v2_ar_members WHERE member_id=@@server_uuid')
        if role != [['PRIMARY']]:
            raise BinlogArchiveError('Select the native ReplicaSet primary for account setup')
    else:
        role = read('SELECT MEMBER_ROLE,MEMBER_STATE FROM performance_schema.replication_group_members WHERE MEMBER_ID=@@server_uuid')
        if role != [['PRIMARY', 'ONLINE']]:
            raise BinlogArchiveError('Select an online native Group Replication primary for account setup')
        cluster_set = read('SELECT member_role,CAST(invalidated AS CHAR) FROM mysql_innodb_cluster_metadata.v2_cs_members WHERE cluster_id=?',
            'SELECT member_role,CAST(invalidated AS CHAR) FROM mysql_innodb_cluster_metadata.v2_cs_members WHERE cluster_id=%s', (instance[0][0],))
        if (cluster_set and cluster_set != [['PRIMARY', '0']]) or (context == 'cluster_set' and not cluster_set):
            raise BinlogArchiveError('Select the native ClusterSet primary cluster for account setup')
    columns = read("SELECT COLUMN_NAME,DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='mysql' AND TABLE_NAME='user' ORDER BY ORDINAL_POSITION")
    if not columns: raise BinlogArchiveError('Native account column metadata is unavailable')
    encoded = []
    for name, datatype in columns:
        identifier = '`' + name.replace('`', '``') + '`'
        value = 'UNIX_TIMESTAMP(' + identifier + ')' if datatype == 'timestamp' else identifier
        if datatype == 'json': value = 'CAST(' + identifier + ' AS CHAR CHARACTER SET utf8mb4)'
        encoded.append("IFNULL(HEX(CAST(" + value + " AS BINARY)),'NULL')")
    # HEX values cannot contain the delimiter or the NULL sentinel. Sensitive
    # native values remain on the server; only a SHA256 fingerprint is read.
    prefix = "SELECT CAST(User AS CHAR) AS account_user,CAST(Host AS CHAR) AS account_host,SHA2(CONCAT_WS(','," + ','.join(encoded) + "),256) AS fingerprint FROM mysql.user WHERE User="
    values = read(prefix + '? AND Host=?', prefix + '%s AND Host=%s', (account['user'], account['host']))
    if len(values) > 1 or values and (not isinstance(values[0][2], str) or not re.fullmatch(r'[0-9a-fA-F]{64}', values[0][2])):
        raise BinlogArchiveError('Native account state cannot be bound to one exact account')
    grants = read('SHOW GRANTS FOR ?@?', 'SHOW GRANTS FOR %s@%s', (account['user'], account['host']), ordered=True) if values else []
    return {'account': dict(account), 'exists': bool(values), 'native_grants': grants,
        'queries': queries, 'results': results,
        'scope': 'Current writable native primary and visible account state; concurrent native administrators are not frozen'}
