"""Credential-free native MariaDB server discovery; no implicit database expansion."""
import json
import time
import uuid

from .mariadb_catalog import _value, DENIED, SYSTEM
from ..mysql_grants import QUERIES as GRANTS

MAX_FACTS = 20000
MAX_BYTES = 8 * 1024 * 1024
SECTIONS = (
    ('databases', 'database', 'SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME', ('schema_name',)),
    ('accounts', 'user', "SELECT User, Host, plugin, password_expired, is_role, default_role, max_questions, max_updates, max_connections, max_user_connections, max_statement_time, CONCAT(QUOTE(User),'@',QUOTE(Host)) AS grantee_identity FROM mysql.user ORDER BY User, Host", ('user', 'host')),
    ('role-edges', 'role-membership', 'SELECT Host, User, Role, Admin_option FROM mysql.roles_mapping ORDER BY Host, User, Role', ('host', 'user', 'role')),
    ('visible-global-grants', 'privilege', 'SELECT GRANTEE, PRIVILEGE_TYPE, IS_GRANTABLE FROM information_schema.USER_PRIVILEGES ORDER BY GRANTEE, PRIVILEGE_TYPE', ('grantee', 'privilege_type')),
    ('plugins', 'plugin', 'SELECT PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_STATUS, PLUGIN_TYPE, PLUGIN_TYPE_VERSION, PLUGIN_LIBRARY, PLUGIN_LIBRARY_VERSION, PLUGIN_LICENSE, LOAD_OPTION FROM information_schema.PLUGINS ORDER BY PLUGIN_NAME', ('plugin_name', 'plugin_type')),
    ('character-sets', 'character-set', 'SELECT CHARACTER_SET_NAME, DEFAULT_COLLATE_NAME, DESCRIPTION, MAXLEN FROM information_schema.CHARACTER_SETS ORDER BY CHARACTER_SET_NAME', ('character_set_name',)),
    ('collations', 'collation', 'SELECT COLLATION_NAME, CHARACTER_SET_NAME, ID, IS_DEFAULT, IS_COMPILED, SORTLEN FROM information_schema.COLLATIONS ORDER BY COLLATION_NAME', ('collation_name',)),
    ('storage-engines', 'storage-engine', 'SELECT ENGINE, SUPPORT, COMMENT, TRANSACTIONS, XA, SAVEPOINTS FROM information_schema.ENGINES ORDER BY ENGINE', ('engine',)),
    ('tablespaces', 'tablespace', 'SELECT SPACE, NAME, FLAG, ROW_FORMAT, PAGE_SIZE, FILENAME, FS_BLOCK_SIZE, FILE_SIZE, ALLOCATED_SIZE FROM information_schema.INNODB_SYS_TABLESPACES ORDER BY SPACE', ('space',)),
    ('loadable-functions', 'loadable-function', 'SELECT name,ret,dl,type FROM mysql.func ORDER BY name', ('name',)),
    ('server-links', 'server-link', 'SELECT Server_name, Host, Db, Username, Port, Socket, Wrapper, Owner FROM mysql.servers ORDER BY Server_name', ('server_name',)),
    *[(section, 'privilege', source, keys) for section, _scope, source, keys in GRANTS],
    ('system-variables', 'system-variable', "SELECT VARIABLE_NAME,GLOBAL_VALUE,DEFAULT_VALUE,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,NUMERIC_MIN_VALUE,NUMERIC_MAX_VALUE,ENUM_VALUE_LIST FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_NAME NOT REGEXP 'PASSWORD|SECRET|TOKEN|CREDENTIAL|INIT_CONNECT|INIT_SLAVE' ORDER BY VARIABLE_NAME", ('variable_name',)),
    ('replication', 'replication-channel', 'SELECT Connection_name,Master_Host,Master_User,Master_Port,Slave_IO_Running,Slave_SQL_Running,Using_Gtid,Gtid_IO_Pos,Last_Errno FROM information_schema.SLAVE_STATUS ORDER BY Connection_name', ('connection_name',)),
    ('sessions', 'session', 'SELECT ID,USER,HOST,DB,COMMAND,TIME,STATE,MEMORY_USED,MAX_MEMORY_USED,EXAMINED_ROWS,SENT_ROWS FROM information_schema.PROCESSLIST ORDER BY ID', ('id',)),
    ('status', 'metric', 'SELECT VARIABLE_NAME,VARIABLE_VALUE FROM information_schema.GLOBAL_STATUS ORDER BY VARIABLE_NAME', ('variable_name',)),
)


def capture(connection):
    if type(connection.server_status) is not int or connection.server_status & 1:
        raise ValueError('Server inventory requires an independently owned idle attachment')
    connection.autocommit = True
    policy = connection.cursor()
    try:
        policy.execute('SET SESSION max_statement_time=15')
        policy.execute('SET SESSION lock_wait_timeout=2')
    finally:
        policy.close()
    resources, observations = [], []
    size = facts = 0
    identities = set()
    started = time.monotonic()
    def account(value):
        nonlocal size, facts
        size += len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf8'))
        facts += 1
        if size > MAX_BYTES or facts > MAX_FACTS or time.monotonic() - started > 60:
            raise ValueError('Server inventory exceeds 20,000 facts, 8 MiB or 60 seconds')
    def read(source):
        cursor = connection.cursor(buffered=False)
        try:
            cursor.execute(source)
            names = [str(column[0]).lower() for column in cursor.description or ()]
            while True:
                rows = cursor.fetchmany(128)
                if not rows: break
                for row in rows:
                    value = {key: _value(item) for key, item in zip(names,row)}
                    account(value)
                    yield value
        finally:
            cursor.close()
    identity = list(read('SELECT VERSION() AS version, @@server_uid AS server_uid, '
        '@@lower_case_table_names AS lower_case_table_names, @@sql_mode AS sql_mode'))
    if (len(identity) != 1 or str(identity[0]['version']).split('-')[0] != '12.2.2' or
            not isinstance(identity[0]['server_uid'],str) or not identity[0]['server_uid']):
        raise ValueError('Server inventory requires native MariaDB 12.2.2 identity')
    instance = identity[0]
    server_uid = instance['server_uid']
    def add(section,kind,row,keys):
        address = [row[key] for key in keys]
        if any(value is None or isinstance(value,(dict,list)) for value in address):
            raise ValueError('Native server object identity is unavailable')
        token = json.dumps([server_uid,section,address],ensure_ascii=False,separators=(',',':'))
        name = ' / '.join(str(value) for value in address)
        system = section in {'character-sets','collations','storage-engines'} or (
            section == 'plugins' and row.get('plugin_library') is None) or (
            section == 'databases' and row['schema_name'] in SYSTEM) or (
            section == 'accounts' and row['user'] in {'mariadb.sys'})
        resource = {'resource_id':'mariadb-server:'+token,'resource_kind':kind,'display_name':name,
            'display_path':[server_uid,section,name], 'native':{'system_object':system,
                'server_uid':server_uid,'section':section,'catalog_row':row}}
        if resource['resource_id'] in identities:
            raise ValueError('Ambiguous native server object identity in ' + section)
        identities.add(resource['resource_id'])
        account(resource);resources.append(resource)
    observed_accounts = []
    for section,kind,source,keys in SECTIONS:
        try:
            if section == 'routine-grants':
                from ..mariadb_grants import routine_grants
                rows = list(routine_grants(observed_accounts, read))
            else:
                rows = list(read(source))
        except Exception as error:
            if getattr(error,'errno',None) not in DENIED:raise
            observations.append({'section':section,'available':False,'error_code':error.errno,
                'sqlstate':getattr(error,'sqlstate',None)})
        else:
            if section == 'accounts':
                try:
                    locks = list(read("SELECT User,Host,COALESCE(JSON_VALUE(Priv,'$.account_locked'),'false') IN ('true','1') AS account_locked FROM mysql.global_priv"))
                except Exception as error:
                    if getattr(error,'errno',None) not in DENIED: raise
                    observations.append({'section':'account-lock-state','available':False,
                        'error_code':error.errno,'sqlstate':getattr(error,'sqlstate',None)})
                    locks = []
                else:
                    observations.append({'section':'account-lock-state','available':True,'rows':len(locks)})
                locked = {(item['user'],item['host']):item['account_locked'] for item in locks}
                for row in rows:
                    pair = row['user'],row['host']
                    row.update(account_lock_observed=pair in locked, account_locked=locked.get(pair))
            for row in rows:
                if section == 'accounts':
                    observed_accounts.append(row)
                if kind == 'privilege':
                    from ..mariadb_grants import resolve
                    row.update(resolve(row['grantee'], observed_accounts))
                native_kind = 'role' if section == 'accounts' and row.get('is_role') == 'Y' else kind
                add(section, native_kind, row, keys)
            observations.append({'section':section,'available':True,'rows':len(rows)})
    if len({row['resource_id'] for row in resources}) != len(resources):
        raise ValueError('Server catalog contains ambiguous native identities')
    warnings = ['Privilege-filtered observational server metadata; full coverage is not asserted.',
        'Authentication strings, password hashes and replication-secret stores are excluded.',
        'Roles use native is_role; confidential server-link options are not exported.',
        'Database captures are independent; this is not a consistent server backup or a migration.']
    root={'resource_id':'mariadb-server:'+json.dumps([server_uid,'server'],separators=(',',':')),
        'resource_kind':'server','display_name':'MariaDB '+server_uid,'display_path':[server_uid],
        'native':{'system_object':False,'catalog_row':instance,'server_uid':server_uid,
            'catalog_observations':observations,'catalog_warnings':warnings,'coverage_complete':False}}
    account(root);resources.insert(0,root)
    return {'resources':resources,'observations':observations,'server_uid':server_uid,
            'generation':str(uuid.uuid4()),'warnings':warnings,'complete':False}
