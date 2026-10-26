"""Explicit, noncredential projections of installed native MySQL interfaces."""
PLUGIN_COLUMNS = ('PLUGIN_NAME PLUGIN_STATUS PLUGIN_TYPE PLUGIN_LIBRARY PLUGIN_LICENSE '
                  'PLUGIN_VERSION PLUGIN_TYPE_VERSION PLUGIN_LIBRARY_VERSION '
                  'PLUGIN_AUTHOR PLUGIN_DESCRIPTION LOAD_OPTION').split()
PLUGINS = 'SELECT '+','.join(PLUGIN_COLUMNS)+' FROM information_schema.PLUGINS ORDER BY PLUGIN_NAME'
FUNCTIONS = ('SELECT UDF_NAME,UDF_RETURN_TYPE,UDF_TYPE,UDF_LIBRARY,UDF_USAGE_COUNT '
             'FROM performance_schema.user_defined_functions ORDER BY UDF_NAME')
CHANNEL_COLUMNS = ('CHANNEL_NAME HOST PORT USER NETWORK_INTERFACE AUTO_POSITION SSL_ALLOWED '
    'SSL_CA_FILE SSL_CA_PATH SSL_CERTIFICATE SSL_CIPHER SSL_KEY SSL_VERIFY_SERVER_CERTIFICATE '
    'SSL_CRL_FILE SSL_CRL_PATH CONNECTION_RETRY_INTERVAL CONNECTION_RETRY_COUNT HEARTBEAT_INTERVAL '
    'TLS_VERSION PUBLIC_KEY_PATH GET_PUBLIC_KEY NETWORK_NAMESPACE COMPRESSION_ALGORITHM '
    'ZSTD_COMPRESSION_LEVEL TLS_CIPHERSUITES SOURCE_CONNECTION_AUTO_FAILOVER GTID_ONLY').split()
def channel_query(table, columns):
    wide = {'CONNECTION_RETRY_COUNT','COUNT_TRANSACTIONS_RETRIES','COUNT_RECEIVED_HEARTBEATS','THREAD_ID','WORKER_ID'}
    return 'SELECT '+','.join('CAST('+key+' AS CHAR) AS '+key if key in wide or key.endswith(('_TIMESTAMP','_RETRIES_COUNT')) else key for key in columns)+' FROM performance_schema.replication_'+table+' ORDER BY CHANNEL_NAME'+(', replication_'+table+'.WORKER_ID' if table.endswith('_by_worker') else '')


def transaction_columns(previous, current, action):
    return [prefix+suffix for prefix,suffixes in [(previous,('', '_ORIGINAL_COMMIT_TIMESTAMP','_IMMEDIATE_COMMIT_TIMESTAMP','_START_'+action+'_TIMESTAMP','_END_'+action+'_TIMESTAMP')),
        (current,('', '_ORIGINAL_COMMIT_TIMESTAMP','_IMMEDIATE_COMMIT_TIMESTAMP','_START_'+action+'_TIMESTAMP'))] for suffix in suffixes]


STATUS_COLUMNS = 'CHANNEL_NAME THREAD_ID SERVICE_STATE LAST_ERROR_NUMBER LAST_ERROR_MESSAGE LAST_ERROR_TIMESTAMP'.split()
RECEIVER_COLUMNS = 'CHANNEL_NAME GROUP_NAME SOURCE_UUID THREAD_ID SERVICE_STATE COUNT_RECEIVED_HEARTBEATS LAST_HEARTBEAT_TIMESTAMP RECEIVED_TRANSACTION_SET LAST_ERROR_NUMBER LAST_ERROR_MESSAGE LAST_ERROR_TIMESTAMP'.split()+transaction_columns('LAST_QUEUED_TRANSACTION','QUEUEING_TRANSACTION','QUEUE')
COORDINATOR_COLUMNS = STATUS_COLUMNS+transaction_columns('LAST_PROCESSED_TRANSACTION','PROCESSING_TRANSACTION','BUFFER')
WORKER_COLUMNS = STATUS_COLUMNS[:1]+['WORKER_ID']+STATUS_COLUMNS[1:]+transaction_columns('LAST_APPLIED_TRANSACTION','APPLYING_TRANSACTION','APPLY')+[
    prefix+suffix for prefix in ('LAST_APPLIED_TRANSACTION','APPLYING_TRANSACTION') for suffix in ('_RETRIES_COUNT','_LAST_TRANSIENT_ERROR_NUMBER','_LAST_TRANSIENT_ERROR_MESSAGE','_LAST_TRANSIENT_ERROR_TIMESTAMP')]


CHANNELS = channel_query('connection_configuration', CHANNEL_COLUMNS)
APPLIER_COLUMNS = ('CHANNEL_NAME DESIRED_DELAY PRIVILEGE_CHECKS_USER REQUIRE_ROW_FORMAT '
    'REQUIRE_TABLE_PRIMARY_KEY_CHECK ASSIGN_GTIDS_TO_ANONYMOUS_TRANSACTIONS_TYPE '
    'ASSIGN_GTIDS_TO_ANONYMOUS_TRANSACTIONS_VALUE').split()
CHANNEL_OBSERVATIONS = (
    ('applier_configuration',channel_query('applier_configuration',APPLIER_COLUMNS)),
    ('receiver',channel_query('connection_status',RECEIVER_COLUMNS)),
    ('applier',channel_query('applier_status','CHANNEL_NAME SERVICE_STATE REMAINING_DELAY COUNT_TRANSACTIONS_RETRIES'.split())),
    ('coordinator',channel_query('applier_status_by_coordinator',COORDINATOR_COLUMNS)),
    ('workers',channel_query('applier_status_by_worker',WORKER_COLUMNS)),
)


def catalog_status(row):
    return {key:({'redacted':True,'is_null':value is None,'is_empty':value==''} if key.endswith('_message') else value) for key,value in row.items()}


def channel_native(row):
    return {**row,'replication_password_returned':False,
        **({'administration':{'allowed_operations':['inspect']}}
           if row['channel_name'].lower().startswith('group_replication_') else {})}
