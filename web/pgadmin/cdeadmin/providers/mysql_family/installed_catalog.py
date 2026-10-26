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
    wide = {'CONNECTION_RETRY_COUNT','COUNT_TRANSACTIONS_RETRIES'}
    return 'SELECT '+','.join('CAST('+key+' AS CHAR) AS '+key if key in wide or key.endswith('_TIMESTAMP') else key for key in columns)+' FROM performance_schema.replication_'+table+' ORDER BY CHANNEL_NAME'


CHANNELS = channel_query('connection_configuration', CHANNEL_COLUMNS)
APPLIER_COLUMNS = ('CHANNEL_NAME DESIRED_DELAY PRIVILEGE_CHECKS_USER REQUIRE_ROW_FORMAT '
    'REQUIRE_TABLE_PRIMARY_KEY_CHECK ASSIGN_GTIDS_TO_ANONYMOUS_TRANSACTIONS_TYPE '
    'ASSIGN_GTIDS_TO_ANONYMOUS_TRANSACTIONS_VALUE').split()
CHANNEL_OBSERVATIONS = (
    ('applier_configuration',channel_query('applier_configuration',APPLIER_COLUMNS)),
    ('receiver',channel_query('connection_status','CHANNEL_NAME SERVICE_STATE SOURCE_UUID RECEIVED_TRANSACTION_SET LAST_ERROR_NUMBER LAST_ERROR_TIMESTAMP'.split())),
    ('applier',channel_query('applier_status','CHANNEL_NAME SERVICE_STATE REMAINING_DELAY COUNT_TRANSACTIONS_RETRIES'.split())),
)


def channel_native(row):
    return {**row,'replication_password_returned':False,
        **({'administration':{'allowed_operations':['inspect']}}
           if row['channel_name'].lower().startswith('group_replication_') else {})}
