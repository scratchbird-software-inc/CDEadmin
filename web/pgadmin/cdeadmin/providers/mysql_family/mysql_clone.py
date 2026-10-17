"""Native MySQL 9.7 local physical clone and correlated PFS observations."""
from pathlib import PurePosixPath, PureWindowsPath
import re
import uuid


class CloneError(ValueError):
    pass


def rows(connection,source,parameters=()):
    cursor=connection.cursor(dictionary=True)
    try:
        cursor.execute(source,parameters or None)
        return cursor.fetchall() if cursor.description else []
    finally:cursor.close()


def configure(connection):
    if connection.in_transaction:raise CloneError('Local cloning requires an independently owned idle native connection')
    connection.autocommit=True
    connection.set_charset_collation(charset='utf8mb4',collation='utf8mb4_0900_ai_ci')
    rows(connection,"SET SESSION time_zone='+00:00'")


def capture(connection):
    import mysql.connector
    identity=rows(connection,"SELECT VERSION() AS `version`,@@server_uuid AS `server_uuid`,@@version_comment AS `edition`,@@version_compile_os AS `operating_system`,@@datadir AS `data_directory`,CURRENT_USER() AS `authenticated_principal`,@@character_set_filesystem AS `filesystem_charset`,@@sql_mode AS `sql_mode`")[0]
    if identity['version'].split('-')[0]!='9.7.0':raise CloneError('Local cloning requires the selected native MySQL 9.7.0 profile')
    try:uuid.UUID(identity['server_uuid'])
    except (TypeError,ValueError):raise CloneError('Native MySQL server identity is unavailable') from None
    plugins=rows(connection,"SELECT PLUGIN_VERSION AS `version`,PLUGIN_LIBRARY AS `library`,PLUGIN_STATUS AS `state` FROM information_schema.PLUGINS WHERE PLUGIN_NAME='clone'")
    if len(plugins)!=1 or plugins[0]['state']!='ACTIVE':
        raise CloneError('Install and activate the native clone plugin through the Plugins workspace before local cloning')
    identity['clone_plugin']=plugins[0]
    identity['client_interface']=type(connection).__name__
    identity['client_version']=mysql.connector.__version__
    identity['clone_settings']={row['Variable_name']:row['Value'] for row in rows(connection,
        "SHOW GLOBAL VARIABLES WHERE Variable_name IN ('clone_autotune_concurrency','clone_buffer_size','clone_max_concurrency','clone_block_ddl','clone_ddl_timeout','clone_max_data_bandwidth')")}
    return identity


def options(value):
    if not isinstance(value,dict) or set(value)-{'destination','confirmation','timeout_seconds'}:
        raise CloneError('Invalid native local clone options')
    path=value.get('destination')
    if not isinstance(path,str) or not path or '\x00' in path or len(path)>510:
        raise CloneError('Select an exact bounded native server directory')
    if value.get('confirmation')!=path:raise CloneError('Confirm the exact destination on the database-server host')
    timeout=value.get('timeout_seconds',3600)
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):
        raise CloneError('Clone timeout requires positive seconds or null for no client deadline')
    return {'destination':path,'confirmation':path,'timeout_seconds':timeout}


def destination(connection,path,source):
    native=PureWindowsPath(path) if source['operating_system'].lower().startswith('win') else PurePosixPath(path)
    if not native.is_absolute():raise CloneError('Native clone destination must be an absolute database-server path')
    charset=source['filesystem_charset']
    if not isinstance(charset,str) or not re.fullmatch(r'[A-Za-z0-9_]+',charset):
        raise CloneError('Native filesystem character set is unavailable')
    encoded=rows(connection,'SELECT OCTET_LENGTH(CONVERT(%s USING '+charset+')) AS `bytes`, '
        'CAST(CONVERT(CONVERT(%s USING '+charset+') USING utf8mb4) AS BINARY)=CAST(%s AS BINARY) AS `exact`',
        (path,path,path))[0]
    if not encoded['exact'] or encoded['bytes']>=511:
        raise CloneError('Native filesystem conversion cannot preserve this path within MySQL\'s directory buffer')
    return encoded['bytes']


def thread_identity(connection):
    result=rows(connection,'SELECT CAST(CONNECTION_ID() AS CHAR) AS `connection_id`,CAST(PS_CURRENT_THREAD_ID() AS CHAR) AS `thread_id`')[0]
    for key in ('connection_id','thread_id'):
        value=result[key]
        if key=='thread_id' and value is None:continue
        if not isinstance(value,str) or not re.fullmatch(r'[1-9][0-9]{0,19}',value) or int(value)>2**64-1:
            raise CloneError('Exact native clone thread identity is unavailable')
    return result


def thread_matches(connection,identity):
    if identity.get('thread_id') is None:return False
    observed=rows(connection,'SELECT CAST(THREAD_ID AS CHAR) AS `thread_id` FROM performance_schema.threads WHERE PROCESSLIST_ID=%s',
        (identity['connection_id'],))
    return len(observed)==1 and observed[0]['thread_id']==identity['thread_id']


def observation(connection):
    try:
        status=rows(connection,"SELECT CAST(ID AS CHAR) AS `id`,CAST(PID AS CHAR) AS `pid`,STATE AS `state`,"
            "CAST(BEGIN_TIME AS CHAR) AS `begin_time`,CAST(END_TIME AS CHAR) AS `end_time`,SOURCE AS `source`,DESTINATION AS `destination`,"
            "ERROR_NO AS `error_number`,ERROR_MESSAGE AS `error_message`,BINLOG_FILE AS `binlog_file`,CAST(BINLOG_POSITION AS CHAR) AS `binlog_position`,"
            "LEFT(GTID_EXECUTED,65536) AS `gtid_executed_prefix`,CAST(CHAR_LENGTH(GTID_EXECUTED) AS CHAR) AS `gtid_executed_length`,"
            "SHA2(GTID_EXECUTED,256) AS `gtid_executed_sha256` FROM performance_schema.clone_status LIMIT 1")
        progress=rows(connection,'SELECT CAST(ID AS CHAR) AS `id`,STAGE AS `stage`,STATE AS `state`,CAST(BEGIN_TIME AS CHAR) AS `begin_time`,'
            'CAST(END_TIME AS CHAR) AS `end_time`,THREADS AS `threads`,CAST(ESTIMATE AS CHAR) AS `estimated_bytes`,CAST(DATA AS CHAR) AS `copied_bytes`,'
            'CAST(NETWORK AS CHAR) AS `network_bytes`,CAST(DATA_SPEED AS CHAR) AS `data_bytes_per_second`,CAST(NETWORK_SPEED AS CHAR) AS `network_bytes_per_second` '
            'FROM performance_schema.clone_progress')
        if status:
            value=status[0];value['gtid_executed_truncated']=int(value['gtid_executed_length'] or '0')>65536
        return {'available':True,'status':status[0] if status else None,'progress':progress,'time_zone':'UTC'}
    except Exception as error:
        return {'available':False,'error_type':type(error).__name__,'error_number':getattr(error,'errno',None)}


def operation_key(status):
    return {key:status.get(key) for key in ('id','pid','begin_time')} if status else None


def correlated(observed,record,*,allow_new=False):
    status=observed.get('status') if observed.get('available') else None
    if not status or not str(status.get('id','')).isdigit():return False
    native=PureWindowsPath if record['source']['operating_system'].lower().startswith('win') else PurePosixPath
    key=operation_key(status)
    bound=record.get('native_operation_key')
    return (status.get('pid')==record['native_thread']['connection_id'] and status.get('source')=='LOCAL INSTANCE' and
            native(status.get('destination') or '')==native(record['options']['destination']) and
            status.get('begin_time') is not None and
            (key==bound if bound is not None else allow_new and key!=record.get('baseline_operation_key')))


class CloneTransport:
    def __init__(self,client,worker,monitor):
        self.client,self.worker,self.monitor=client,worker,monitor
        self.closed=False

    def close(self):
        if self.closed:return
        self.closed=True
        for connection in (self.worker,self.monitor):
            self.client._discard_failed_session(connection)


def connect(provider,route,timeout):
    # Pool leases and user editor sessions cannot own an administration worker.
    from .mysql_connections import POOL_ARGUMENTS
    route={key:value for key,value in route.items() if key not in POOL_ARGUMENTS}
    client=provider.client;worker=monitor=None
    try:
        # The native C interface accepts I/O deadlines only at connect time.
        worker=client._connect({'route':{**route,'read_timeout':timeout,'write_timeout':15}});configure(worker)
        monitor=client._connect({'route':{**route,'read_timeout':5,'write_timeout':15}});configure(monitor)
        source=capture(worker)
        if capture(monitor)!=source:raise CloneError('Native clone connections reached different identities or policies')
        return source,CloneTransport(client,worker,monitor)
    except BaseException:
        for connection in (worker,monitor):
            if connection is not None:client._discard_failed_session(connection)
        raise
