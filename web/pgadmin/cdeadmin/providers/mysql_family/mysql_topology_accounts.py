"""Native account setup admission without retaining authentication material.

Account methods write the native primary. Admission uses that registration and
binds native role metadata, the account row fingerprint and visible grants.
"""
import re
import json
import uuid

from ...sdk.tooling import ProviderToolGrant

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

    if context == 'instance':
        read('SELECT CAST(@@global.read_only AS CHAR),CAST(@@global.super_read_only AS CHAR)')
    else:
        primary(connection, context, read)
    return account_state(connection, account, queries, results, read, context)


def primary(connection, context, read):
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


def account_state(connection, account, queries, results, read, context):
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
        'scope': ('Current selected native instance and visible bootstrap account state; native configuration owns its privilege and creation rules'
                  if context == 'instance' else 'Current writable native primary and visible account state; concurrent native administrators are not frozen')}


def bootstrap_name(selected):
    arguments = json.loads(selected['arguments_json'])
    return (arguments[0] or {}).get('clusterAdmin') if arguments else None


def parse_bootstrap(client, route, workspace, selected):
    name = bootstrap_name(selected)
    if not name: return None
    marker = 'CDEADMIN_BOOTSTRAP_ACCOUNT_' + uuid.uuid4().hex + ':'
    source = 'import json;print(' + repr(marker) + '+json.dumps(mysql.split_account(' + repr(name) + ')))'
    grant = ProviderToolGrant('mysql-shell', str(workspace), route.get('host') or 'localhost', int(route.get('port', 3306)), timeout_seconds=30)
    observed = client._tool_runner.run(grant, ['--no-defaults', '--py', '--quiet-start=2', '--log-level=none', '--execute=' + source])
    values = []
    for line in observed['stdout'].splitlines():
        if line.startswith(marker):
            try: values.append(json.loads(line[len(marker):]))
            except ValueError: pass
    if (observed['return_code'] != 0 or len(values) != 1 or not isinstance(values[0], dict) or
            set(values[0]) != {'user', 'host'} or any(not isinstance(value, str) for value in values[0].values())):
        raise BinlogArchiveError('The native SDK could not parse the selected bootstrap administrator account')
    return values[0]


def capture_bootstrap(connection, account):
    # IInstance::user_exists maps an omitted host to % before SHOW GRANTS;
    # configure_instance also uses % for the eventual account identity.
    effective = {**account, 'host': account['host'] or '%'}
    return capture(connection, effective, 'instance')
