"""Credential-free native MySQL server discovery; no implicit database expansion."""
import json
import time
import uuid

from .mysql_catalog import _value, DENIED, SYSTEM
from ..mysql_grants import QUERIES as GRANTS
from .system_variables import SELECT as VARIABLES_SELECT

MAX_FACTS = 20000
MAX_BYTES = 8 * 1024 * 1024
SECTIONS = (
    ('databases', 'database', 'SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME, DEFAULT_ENCRYPTION FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME', ('schema_name',)),
    ('accounts', 'user', "SELECT User, Host, account_locked, password_expired, password_lifetime, max_questions, max_updates, max_connections, max_user_connections, CONCAT(QUOTE(User),'@',QUOTE(Host)) AS grantee_identity FROM mysql.user ORDER BY User, Host", ('user','host')),
    ('role-edges', 'role-membership', 'SELECT FROM_USER, FROM_HOST, TO_USER, TO_HOST, WITH_ADMIN_OPTION FROM mysql.role_edges ORDER BY FROM_USER, FROM_HOST, TO_USER, TO_HOST', ('from_user','from_host','to_user','to_host')),
    ('default-roles', 'default-role', 'SELECT USER, HOST, DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST FROM mysql.default_roles ORDER BY USER, HOST, DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST', ('user','host','default_role_user','default_role_host')),
    ('visible-global-grants', 'privilege', 'SELECT GRANTEE, PRIVILEGE_TYPE, IS_GRANTABLE FROM information_schema.USER_PRIVILEGES ORDER BY GRANTEE, PRIVILEGE_TYPE', ('grantee','privilege_type')),
    ('plugins', 'plugin', 'SELECT PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_STATUS, PLUGIN_TYPE, PLUGIN_TYPE_VERSION, PLUGIN_LIBRARY, PLUGIN_LIBRARY_VERSION, PLUGIN_LICENSE, LOAD_OPTION FROM information_schema.PLUGINS ORDER BY PLUGIN_NAME', ('plugin_name',)),
    ('components', 'component', 'SELECT component_id, component_group_id, component_urn FROM mysql.component ORDER BY component_id', ('component_urn',)),
    ('character-sets', 'character-set', 'SELECT CHARACTER_SET_NAME, DEFAULT_COLLATE_NAME, DESCRIPTION, MAXLEN FROM information_schema.CHARACTER_SETS ORDER BY CHARACTER_SET_NAME', ('character_set_name',)),
    ('collations', 'collation', 'SELECT COLLATION_NAME, CHARACTER_SET_NAME, ID, IS_DEFAULT, IS_COMPILED, SORTLEN, PAD_ATTRIBUTE FROM information_schema.COLLATIONS ORDER BY COLLATION_NAME', ('collation_name',)),
    ('storage-engines', 'storage-engine', 'SELECT ENGINE, SUPPORT, COMMENT, TRANSACTIONS, XA, SAVEPOINTS FROM information_schema.ENGINES ORDER BY ENGINE', ('engine',)),
    ('tablespaces', 'tablespace', 'SELECT s.SPACE, s.NAME, s.SPACE_TYPE, s.ROW_FORMAT, s.PAGE_SIZE, s.FS_BLOCK_SIZE, s.FILE_SIZE, s.ALLOCATED_SIZE, s.ENCRYPTION, s.STATE, s.AUTOEXTEND_SIZE, e.ENGINE_ATTRIBUTE FROM information_schema.INNODB_TABLESPACES s LEFT JOIN information_schema.TABLESPACES_EXTENSIONS e ON e.TABLESPACE_NAME=s.NAME ORDER BY s.NAME', ('name',)),
    ('resource-groups', 'resource-group', 'SELECT RESOURCE_GROUP_NAME, RESOURCE_GROUP_TYPE, RESOURCE_GROUP_ENABLED, VCPU_IDS, THREAD_PRIORITY FROM information_schema.RESOURCE_GROUPS ORDER BY RESOURCE_GROUP_NAME', ('resource_group_name',)),
    ('system-variables', 'system-variable', VARIABLES_SELECT, ('variable_name',)),
    ('foreign-servers', 'server-link', 'SELECT Server_name,Host,Db,Username,Port,Socket,Wrapper,Owner FROM mysql.servers ORDER BY Server_name', ('server_name',)),
    ('spatial-reference-systems', 'spatial-reference-system', 'SELECT SRS_NAME,SRS_ID,ORGANIZATION,ORGANIZATION_COORDSYS_ID,DEFINITION,DESCRIPTION FROM information_schema.ST_SPATIAL_REFERENCE_SYSTEMS', ('srs_id',)),
    ('replication-channels', 'replication-channel', 'SELECT CHANNEL_NAME,HOST,PORT,USER,AUTO_POSITION,CONNECTION_RETRY_INTERVAL,CONNECTION_RETRY_COUNT,HEARTBEAT_INTERVAL,TLS_VERSION,SSL_ALLOWED,SSL_VERIFY_SERVER_CERTIFICATE FROM performance_schema.replication_connection_configuration ORDER BY CHANNEL_NAME', ('channel_name',)),
) + tuple((section, 'privilege', sql, keys) for section, _scope, sql, keys in GRANTS)


def spatial_ids(value):
    if (not isinstance(value, list) or len(value) > 128 or
            any(type(item) is not int or not 0 <= item <= 4294967295 for item in value) or
            len(set(value)) != len(value)):
        raise ValueError('Select at most 128 distinct native unsigned 32-bit SRIDs')
    return sorted(value)


def capture(connection, *, spatial_reference_ids=None):
    selected = spatial_ids([] if spatial_reference_ids is None else spatial_reference_ids)
    if connection.in_transaction:
        raise ValueError('Server inventory requires an independently owned idle attachment')
    connection.autocommit = True
    policy = connection.cursor()
    try:
        policy.execute('SET SESSION max_execution_time=15000')
        policy.execute('SET SESSION lock_wait_timeout=2')
    finally:
        policy.close()
    resources, observations = [], []
    size = facts = 0
    started = time.monotonic()
    def account(value):
        nonlocal size, facts
        size += len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf8'))
        facts += 1
        if size > MAX_BYTES or facts > MAX_FACTS or time.monotonic() - started > 60:
            raise ValueError('Server inventory exceeds 20,000 facts, 8 MiB or 60 seconds')
    def read(source, parameters=None):
        cursor = connection.cursor(buffered=False)
        try:
            if parameters is None:
                cursor.execute(source)
            else:
                cursor.execute(source, parameters)
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
    identity = list(read('SELECT VERSION() AS version, @@server_uuid AS server_uuid, '
        '@@lower_case_table_names AS lower_case_table_names, @@sql_mode AS sql_mode, '
        'CURRENT_USER() AS effective_principal, USER() AS authenticated_principal, CURRENT_ROLE() AS active_roles'))
    if (len(identity) != 1 or str(identity[0]['version']).split('-')[0] != '9.7.0' or
            not isinstance(identity[0]['server_uuid'],str) or not identity[0]['server_uuid']):
        raise ValueError('Server inventory requires native MySQL 9.7.0 identity')
    instance = identity[0]
    server_uuid = instance['server_uuid']
    def add(section,kind,row,keys):
        address = [row[key] for key in keys]
        if any(value is None or isinstance(value,(dict,list)) for value in address):
            raise ValueError('Native server object identity is unavailable')
        token = json.dumps([server_uuid,section,address],ensure_ascii=False,separators=(',',':'))
        name = ' / '.join(str(value) for value in address)
        system = section in {'character-sets','collations','storage-engines'} or (
            section == 'databases' and row['schema_name'] in SYSTEM) or (
            section == 'accounts' and row['user'] in {'mysql.infoschema','mysql.session','mysql.sys'})
        resource = {'resource_id':'mysql-server:'+token,'resource_kind':kind,'display_name':name,
            'display_path':[server_uuid,section,name], 'native':{'system_object':system,
                'server_uuid':server_uuid,'section':section,'catalog_row':row}}
        account(resource);resources.append(resource)
    accounts = {}
    account_rows = None
    for section,kind,source,keys in SECTIONS:
        if section == 'spatial-reference-systems' and not selected:
            observations.append({'section':section,'available':False,
                'reason':'Select explicit SRIDs for bounded native definition exchange', 'selected_ids':[]})
            continue
        try:
            if section == 'routine-grants':
                from ..mysql_grants import routine_grants
                if account_rows is None:
                    observations.append({'section': section, 'available': False,
                        'reason': 'Separate account identities are not visible'})
                    continue
                rows = list(routine_grants(account_rows, read))
            elif section == 'spatial-reference-systems':
                rows = list(read(source+' WHERE SRS_ID IN ('+','.join(['%s']*len(selected))+') ORDER BY SRS_ID', tuple(selected)))
            else:
                rows = list(read(source))
        except Exception as error:
            if getattr(error,'errno',None) not in DENIED:raise
            observations.append({'section':section,'available':False,'error_code':error.errno,
                'sqlstate':getattr(error,'sqlstate',None)})
        else:
            if section == 'accounts':
                account_rows = rows
                # I_S GRANTEE wraps raw components in quotes without escaping.
                # Resolve through separately observed User/Host, never SQL-parse it.
                for row in rows:
                    raw = "'" + row['user'] + "'@'" + row['host'] + "'"
                    accounts[raw] = row if raw not in accounts else None
            if section in {'visible-global-grants', 'schema-grants', 'table-grants', 'column-grants'}:
                for row in rows:
                    account_row = accounts.get(row['grantee'])
                    row['grantee_identity_available'] = account_row is not None
                    if account_row:
                        row.update(information_schema_grantee=row['grantee'],
                            grantee=account_row['grantee_identity'],
                            grantee_user=account_row['user'], grantee_host=account_row['host'])
            for row in rows:add(section,kind,row,keys)
            observations.append({'section':section,'available':True,'rows':len(rows),
                **({'selected_ids':selected} if section == 'spatial-reference-systems' else {})})
    if len({row['resource_id'] for row in resources}) != len(resources):
        raise ValueError('Server catalog contains ambiguous native identities')
    warnings = ['Privilege-filtered observational server metadata; full coverage is not asserted.',
        'Persisted-only settings retain identity and presence; their values are redacted because native sensitivity metadata is unavailable.',
        'Authentication strings, password hashes and replication-secret stores are excluded.',
        'Accounts without visible role edges are not classified as roles.',
        'Database captures are independent; this is not a consistent server backup or a migration.']
    root={'resource_id':'mysql-server:'+json.dumps([server_uuid,'server'],separators=(',',':')),
        'resource_kind':'server','display_name':'MySQL '+server_uuid,'display_path':[server_uuid],
        'native':{'system_object':False,'catalog_row':instance,'server_uuid':server_uuid,
            'catalog_observations':observations,'catalog_warnings':warnings,'coverage_complete':False}}
    account(root);resources.insert(0,root)
    return {'resources':resources,'observations':observations,'server_uuid':server_uuid,
            'generation':str(uuid.uuid4()),'warnings':warnings,'complete':False}
