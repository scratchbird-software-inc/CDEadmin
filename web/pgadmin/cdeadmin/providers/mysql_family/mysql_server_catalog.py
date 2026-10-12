"""Credential-free native MySQL server discovery; no implicit database expansion."""
import json
import time
import uuid

from .mysql_catalog import _value, DENIED, SYSTEM

MAX_FACTS = 20000
MAX_BYTES = 8 * 1024 * 1024
SECTIONS = (
    ('databases', 'database', 'SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME, DEFAULT_ENCRYPTION FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME', ('schema_name',)),
    ('accounts', 'user', 'SELECT User, Host, account_locked, password_expired, password_lifetime, max_questions, max_updates, max_connections, max_user_connections FROM mysql.user ORDER BY User, Host', ('user','host')),
    ('role-edges', 'role-membership', 'SELECT FROM_USER, FROM_HOST, TO_USER, TO_HOST, WITH_ADMIN_OPTION FROM mysql.role_edges ORDER BY FROM_USER, FROM_HOST, TO_USER, TO_HOST', ('from_user','from_host','to_user','to_host')),
    ('default-roles', 'default-role', 'SELECT USER, HOST, DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST FROM mysql.default_roles ORDER BY USER, HOST, DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST', ('user','host','default_role_user','default_role_host')),
    ('visible-global-grants', 'privilege', 'SELECT GRANTEE, PRIVILEGE_TYPE, IS_GRANTABLE FROM information_schema.USER_PRIVILEGES ORDER BY GRANTEE, PRIVILEGE_TYPE', ('grantee','privilege_type')),
    ('plugins', 'plugin', 'SELECT PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_STATUS, PLUGIN_TYPE, PLUGIN_TYPE_VERSION, PLUGIN_LIBRARY, PLUGIN_LIBRARY_VERSION, PLUGIN_LICENSE, LOAD_OPTION FROM information_schema.PLUGINS ORDER BY PLUGIN_NAME', ('plugin_name',)),
    ('components', 'component', 'SELECT component_id, component_group_id, component_urn FROM mysql.component ORDER BY component_id', ('component_id',)),
    ('character-sets', 'character-set', 'SELECT CHARACTER_SET_NAME, DEFAULT_COLLATE_NAME, DESCRIPTION, MAXLEN FROM information_schema.CHARACTER_SETS ORDER BY CHARACTER_SET_NAME', ('character_set_name',)),
    ('collations', 'collation', 'SELECT COLLATION_NAME, CHARACTER_SET_NAME, ID, IS_DEFAULT, IS_COMPILED, SORTLEN, PAD_ATTRIBUTE FROM information_schema.COLLATIONS ORDER BY COLLATION_NAME', ('collation_name',)),
    ('storage-engines', 'storage-engine', 'SELECT ENGINE, SUPPORT, COMMENT, TRANSACTIONS, XA, SAVEPOINTS FROM information_schema.ENGINES ORDER BY ENGINE', ('engine',)),
    ('tablespaces', 'tablespace', 'SELECT SPACE, NAME, ROW_FORMAT, PAGE_SIZE, FS_BLOCK_SIZE, FILE_SIZE, ALLOCATED_SIZE, ENCRYPTION, STATE FROM information_schema.INNODB_TABLESPACES ORDER BY SPACE', ('space',)),
)


def capture(connection):
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
    identity = list(read('SELECT VERSION() AS version, @@server_uuid AS server_uuid, '
        '@@lower_case_table_names AS lower_case_table_names, @@sql_mode AS sql_mode'))
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
    for section,kind,source,keys in SECTIONS:
        try:
            rows = list(read(source))
        except Exception as error:
            if getattr(error,'errno',None) not in DENIED:raise
            observations.append({'section':section,'available':False,'error_code':error.errno,
                'sqlstate':getattr(error,'sqlstate',None)})
        else:
            for row in rows:add(section,kind,row,keys)
            observations.append({'section':section,'available':True,'rows':len(rows)})
    if len({row['resource_id'] for row in resources}) != len(resources):
        raise ValueError('Server catalog contains ambiguous native identities')
    warnings = ['Privilege-filtered observational server metadata; full coverage is not asserted.',
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
