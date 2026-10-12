"""Bounded native inventory queries. No user SQL or BLOB materialization."""

from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def query(table, fields, prefix='RDB$', where='', order=None):
    columns = ', '.join(prefix + field.upper() for field in fields)
    return (f'SELECT FIRST 101 {columns} FROM {table}' +
            (' WHERE ' + where if where else '') +
            ' ORDER BY ' + (order or '1'))


def rows(cursor, sql, fields, parameters=None):
    if parameters is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, parameters)
    values = cursor.fetchmany(101)
    if any(len(row) != len(fields) for row in values):
        raise RelationalClientError('Invalid native inventory row')
    return {'rows': [dict(zip(fields, row)) for row in values[:100]],
            'limit': 100, 'truncated': len(values) > 100}


COMPILED = ('compiled_statement_id', 'object_name', 'object_type',
            'package_name', 'stat_id')
CLIENTS = ('attachment_id', 'remote_protocol', 'auth_method', 'wire_encrypted',
           'wire_compressed', 'wire_crypt_plugin', 'client_version',
           'remote_version')
FILES = ('file_name', 'file_sequence', 'file_start', 'file_length',
         'file_flags', 'shadow_number')
BACKUPS = ('backup_id', 'timestamp', 'backup_level', 'guid', 'scn', 'file_name')
PUBLICATIONS = ('publication_name', 'owner_name', 'system_flag',
                'active_flag', 'auto_enable')
TABLE_COUNTERS = ('record_seq_reads', 'record_idx_reads', 'record_inserts',
                  'record_updates', 'record_deletes', 'record_backouts',
                  'record_purges', 'record_expunges', 'record_waits',
                  'record_conflicts', 'backversion_reads')
TABLE_FIELDS = ('table_name', 'record_stat_id', 'relation_id') + TABLE_COUNTERS

ACTIVITY = {
    'wire_counts': ('MON$ATTACHMENTS visible noncollector user attachments',
        ('transport', 'encrypted', 'count'),
        "SELECT FIRST 101 CASE WHEN MON$REMOTE_PROTOCOL IS NULL OR MON$REMOTE_PROTOCOL = 'XNET' "
        "THEN 'local' WHEN MON$REMOTE_PROTOCOL STARTING WITH 'TCP' THEN 'wire' ELSE 'unknown' END, "
        'MON$WIRE_ENCRYPTED, COUNT(*) FROM MON$ATTACHMENTS '
        'WHERE MON$ATTACHMENT_ID <> CURRENT_CONNECTION AND MON$SYSTEM_FLAG = 0 '
        'GROUP BY 1, 2 ORDER BY 1, 2'),
    'protection_details': ('MON$DATABASE',
        ('crypt_state', 'crypt_page', 'replica_mode', 'backup_state', 'sec_database'),
        query('MON$DATABASE', ('crypt_state', 'crypt_page', 'replica_mode',
                              'backup_state', 'sec_database'), 'MON$')),
    'compiled_counts': ('MON$COMPILED_STATEMENTS', ('count',),
                        'SELECT COUNT(*) FROM MON$COMPILED_STATEMENTS'),
    'table_details': ('MON$TABLE_STATS / MON$RECORD_STATS group 0', TABLE_FIELDS,
        'SELECT FIRST 101 T.MON$TABLE_NAME, T.MON$RECORD_STAT_ID, C.RDB$RELATION_ID, ' +
        ', '.join('R.MON$' + field.upper() for field in TABLE_COUNTERS) +
        ' FROM MON$TABLE_STATS T JOIN MON$DATABASE D '
        'ON T.MON$STAT_ID = D.MON$STAT_ID JOIN MON$RECORD_STATS R '
        'ON R.MON$STAT_ID = T.MON$RECORD_STAT_ID '
        'AND R.MON$STAT_GROUP = T.MON$STAT_GROUP '
        'JOIN RDB$RELATIONS C ON C.RDB$RELATION_NAME = T.MON$TABLE_NAME '
        'WHERE T.MON$STAT_GROUP = 0 ORDER BY T.MON$TABLE_NAME'),
    'compiled_details': ('MON$COMPILED_STATEMENTS', COMPILED,
                        query('MON$COMPILED_STATEMENTS', COMPILED, 'MON$')),
    'client_details': ('MON$ATTACHMENTS', CLIENTS,
                      query('MON$ATTACHMENTS', CLIENTS, 'MON$',
                            'MON$ATTACHMENT_ID <> CURRENT_CONNECTION')),
}

METADATA = {
    'creator_details': ('SEC$DB_CREATORS', ('user', 'user_type'),
                        query('SEC$DB_CREATORS', ('user', 'user_type'), 'SEC$')),
    'global_mapping_details': ('SEC$GLOBAL_AUTH_MAPPING',
        ('map_name', 'map_using', 'map_plugin', 'map_db', 'map_from_type',
         'map_from', 'map_to_type', 'map_to'),
        query('SEC$GLOBAL_AUTH_MAPPING', ('map_name', 'map_using', 'map_plugin', 'map_db',
                                          'map_from_type', 'map_from', 'map_to_type', 'map_to'), 'SEC$')),
    'role_details': ('RDB$ROLES', ('role_name', 'owner_name', 'system_flag'),
                     query('RDB$ROLES', ('role_name', 'owner_name', 'system_flag'))),
    'grant_details': ('RDB$USER_PRIVILEGES',
        ('user', 'grantor', 'privilege', 'grant_option', 'relation_name',
         'field_name', 'user_type', 'object_type'),
        query('RDB$USER_PRIVILEGES', ('user', 'grantor', 'privilege', 'grant_option',
                                    'relation_name', 'field_name', 'user_type', 'object_type'),
              order='RDB$USER, RDB$RELATION_NAME, RDB$PRIVILEGE, RDB$FIELD_NAME, RDB$GRANTOR')),
    'mapping_details': ('RDB$AUTH_MAPPING',
        ('map_name', 'map_using', 'map_plugin', 'map_db', 'map_from_type',
         'map_from', 'map_to_type', 'map_to'),
        query('RDB$AUTH_MAPPING', ('map_name', 'map_using', 'map_plugin', 'map_db',
                                  'map_from_type', 'map_from', 'map_to_type', 'map_to'))),
    'configuration_details': ('RDB$CONFIG safe operational subset',
        ('config_name', 'config_value', 'config_default', 'config_is_set', 'config_source'),
        query('RDB$CONFIG', ('config_name', 'config_value', 'config_default',
                            'config_is_set', 'config_source'), where=
              "RDB$CONFIG_NAME IN ('ServerMode', 'DefaultDbCachePages', "
              "'TempCacheLimit', 'LockMemSize', 'LockHashSlots', 'WireCrypt', "
              "'WireCompression', 'AuthServer', 'AuthClient', 'UserManager', "
              "'MaxParallelWorkers', 'ParallelWorkers', 'StatementTimeout', "
              "'ConnectionIdleTimeout')")),
    'file_details': ('RDB$FILES', FILES, query('RDB$FILES', FILES)),
    'backup_details': ('RDB$BACKUP_HISTORY', BACKUPS,
                       query('RDB$BACKUP_HISTORY', BACKUPS,
                             order='RDB$TIMESTAMP DESC, RDB$BACKUP_ID DESC')),
    'publication_details': ('RDB$PUBLICATIONS', PUBLICATIONS,
                            query('RDB$PUBLICATIONS', PUBLICATIONS)),
    'publication_table_details': ('RDB$PUBLICATION_TABLES',
                                 ('publication_name', 'table_name'),
                                 query('RDB$PUBLICATION_TABLES',
                                       ('publication_name', 'table_name'))),
    'security_counts': ('visible native security catalogs', ('kind', 'count'),
        "SELECT 'roles', COUNT(*) FROM RDB$ROLES UNION ALL "
        "SELECT 'grants', COUNT(*) FROM RDB$USER_PRIVILEGES UNION ALL "
        "SELECT 'local mappings', COUNT(*) FROM RDB$AUTH_MAPPING UNION ALL "
        "SELECT 'global mappings', COUNT(*) FROM SEC$GLOBAL_AUTH_MAPPING"),
    'user_counts': ('SEC$USERS', ('plugin', 'active', 'admin', 'count'),
        'SELECT FIRST 101 SEC$PLUGIN, SEC$ACTIVE, SEC$ADMIN, COUNT(*) '
        'FROM SEC$USERS GROUP BY SEC$PLUGIN, SEC$ACTIVE, SEC$ADMIN '
        'ORDER BY SEC$PLUGIN, SEC$ACTIVE, SEC$ADMIN'),
    'schema_counts': ('RDB$RELATIONS', ('kind', 'system_flag', 'count'),
        "SELECT CASE WHEN RDB$VIEW_BLR IS NULL THEN 'table' ELSE 'view' END, "
        'COALESCE(RDB$SYSTEM_FLAG, 0), COUNT(*) FROM RDB$RELATIONS '
        'GROUP BY 1, 2 ORDER BY 1, 2'),
    'schema_health': ('native index/trigger/routine catalogs',
        ('kind', 'name', 'condition'),
        "SELECT FIRST 101 'index', RDB$INDEX_NAME, 'inactive' FROM RDB$INDICES "
        'WHERE RDB$INDEX_INACTIVE = 1 UNION ALL '
        "SELECT 'trigger', RDB$TRIGGER_NAME, 'inactive' FROM RDB$TRIGGERS "
        'WHERE RDB$TRIGGER_INACTIVE = 1 UNION ALL '
        "SELECT 'trigger', RDB$TRIGGER_NAME, 'invalid BLR' FROM RDB$TRIGGERS "
        'WHERE RDB$VALID_BLR = 0 UNION ALL '
        "SELECT 'procedure', RDB$PROCEDURE_NAME, 'invalid BLR' FROM RDB$PROCEDURES "
        'WHERE RDB$VALID_BLR = 0 UNION ALL '
        "SELECT 'function', RDB$FUNCTION_NAME, 'invalid BLR' FROM RDB$FUNCTIONS "
        'WHERE RDB$VALID_BLR = 0 ORDER BY 1, 2'),
}

# Catalog class counts are grouped at the source; no full metadata export or
# source/description BLOB reads are needed for a dashboard refresh.
_COUNTS = (
    ('columns', 'RDB$RELATION_FIELDS'), ('indices', 'RDB$INDICES'),
    ('triggers', 'RDB$TRIGGERS'), ('procedures', 'RDB$PROCEDURES'),
    ('functions', 'RDB$FUNCTIONS'), ('packages', 'RDB$PACKAGES'),
    ('domains', 'RDB$FIELDS'), ('sequences', 'RDB$GENERATORS'),
)
METADATA['schema_counts'] = (
    'native schema catalogs', ('kind', 'system_flag', 'count'),
    METADATA['schema_counts'][2].removesuffix(' ORDER BY 1, 2') +
    ''.join(" UNION ALL SELECT '" + kind + "', COALESCE(RDB$SYSTEM_FLAG, 0), "
            'COUNT(*) FROM ' + table + ' GROUP BY 2' for kind, table in _COUNTS) +
    " UNION ALL SELECT 'constraints', NULL, COUNT(*) FROM RDB$RELATION_CONSTRAINTS" +
    " UNION ALL SELECT 'dependencies', NULL, COUNT(*) FROM RDB$DEPENDENCIES" +
    ' ORDER BY 1, 2',
)
