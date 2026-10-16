"""Exact native grantees and privilege scope projections, without secrets."""
import re

QUERIES = (
    ('schema-grants', 'database', 'SELECT GRANTEE,TABLE_SCHEMA,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.SCHEMA_PRIVILEGES ORDER BY GRANTEE,TABLE_SCHEMA,PRIVILEGE_TYPE', ('grantee', 'table_schema', 'privilege_type')),
    ('table-grants', 'table', 'SELECT GRANTEE,TABLE_SCHEMA,TABLE_NAME,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.TABLE_PRIVILEGES ORDER BY GRANTEE,TABLE_SCHEMA,TABLE_NAME,PRIVILEGE_TYPE', ('grantee', 'table_schema', 'table_name', 'privilege_type')),
    ('column-grants', 'column', 'SELECT GRANTEE,TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.COLUMN_PRIVILEGES ORDER BY GRANTEE,TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,PRIVILEGE_TYPE', ('grantee', 'table_schema', 'table_name', 'column_name', 'privilege_type')),
    ('routine-grants', 'routine', "SELECT CONCAT(QUOTE(User),'@',QUOTE(Host)) AS GRANTEE,Db AS TABLE_SCHEMA,Routine_name AS ROUTINE_NAME,Routine_type AS ROUTINE_TYPE,'EXECUTE' AS PRIVILEGE_TYPE,IF(FIND_IN_SET('Grant',Proc_priv)>0,'YES','NO') AS IS_GRANTABLE FROM mysql.procs_priv WHERE FIND_IN_SET('Execute',Proc_priv)>0 UNION ALL SELECT CONCAT(QUOTE(User),'@',QUOTE(Host)),Db,Routine_name,Routine_type,'ALTER ROUTINE',IF(FIND_IN_SET('Grant',Proc_priv)>0,'YES','NO') FROM mysql.procs_priv WHERE FIND_IN_SET('Alter Routine',Proc_priv)>0", ('grantee', 'table_schema', 'routine_name', 'routine_type', 'privilege_type')),
)


def routine_grants(accounts, read):
    """Use native ACL observations, not mysql.procs_priv's storage encoding.

    MySQL 9.7 can persist a non-ASCII routine grantee with a different encoding
    while SHOW GRANTS still reports the effective account correctly. Never
    guess a charset conversion or authorize using the storage spelling.
    """
    quoted = r'`((?:``|[^`])*)`'
    header = re.compile(r'^GRANT (EXECUTE(?:, ALTER ROUTINE)?|ALTER ROUTINE(?:, EXECUTE)?) ON '
                        r'(PROCEDURE|FUNCTION|LIBRARY) ' + quoted + r'\.' + quoted + r' TO ')
    for account in accounts:
        for result in read('SHOW GRANTS FOR %s@%s', (account['user'], account['host'])):
            source = next(iter(result.values()))
            if not isinstance(source, str):
                raise ValueError('Native SHOW GRANTS returned an unsupported value')
            match = header.match(source)
            if not match:
                if re.match(r'^GRANT .* ON (PROCEDURE|FUNCTION|LIBRARY) ', source):
                    raise ValueError('Native routine grant syntax is unavailable')
                continue
            privileges, kind, database, name = match.groups()
            for privilege in privileges.split(', '):
                yield {'grantee': account['grantee_identity'], 'grantee_user': account['user'],
                    'grantee_host': account['host'], 'grantee_identity_available': True,
                    'table_schema': database.replace('``', '`'), 'routine_name': name.replace('``', '`'),
                    'routine_type': kind, 'privilege_type': privilege,
                    'is_grantable': 'YES' if source.endswith(' WITH GRANT OPTION') else 'NO'}


def grantee(value):
    """Decode MySQL QUOTE-style native account pairs, including embedded @."""
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('Native grantee identity is unavailable')
    position = 0
    def part():
        nonlocal position
        if position >= len(value) or value[position] != "'":
            raise ValueError('Native grantee component must be quoted')
        position += 1
        result = []
        while position < len(value):
            char = value[position]
            position += 1
            if char == '\\':
                if position == len(value):
                    break
                escaped = value[position]; position += 1
                result.append({'0': '\0', 'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'Z': '\x1a'}.get(escaped, escaped))
            elif char == "'":
                if position < len(value) and value[position] == "'":
                    result.append("'"); position += 1
                else:
                    return ''.join(result)
            else:
                result.append(char)
        raise ValueError('Unterminated native grantee component')
    user = part()
    if position >= len(value) or value[position] != '@':
        raise ValueError('Native grantee host is unavailable')
    position += 1
    host = part()
    if position != len(value) or not host or '\0' in user + host:
        raise ValueError('Invalid native grantee identity')
    return user, host


def scoped_statement(facts, section, action, grant_option):
    from .mysql_roles import account
    from .mysql_family.mysql_catalog import identifier
    if facts.get('grantee_identity_available') is False:
        raise ValueError('Separate native account identity must be visible before changing this grant')
    privilege = facts.get('privilege_type')
    if not isinstance(privilege, str) or not re.fullmatch(r'[A-Z][A-Z0-9_ ]{0,127}', privilege):
        raise ValueError('Exact native privilege type is required')
    user, host = grantee(facts.get('grantee'))
    if any(key in facts and facts[key] != expected for key, expected in (('grantee_user', user), ('grantee_host', host))):
        raise ValueError('Grantee fields disagree with native account identity')
    scope = '*.*'
    if section == 'schema-grants':
        scope = identifier(facts['table_schema']) + '.*'
    elif section in {'table-grants', 'column-grants'}:
        scope = identifier(facts['table_schema']) + '.' + identifier(facts['table_name'])
        if section == 'column-grants':
            privilege += '(' + identifier(facts['column_name']) + ')'
    elif section == 'routine-grants':
        if facts['routine_type'] not in {'FUNCTION', 'PROCEDURE', 'LIBRARY'}:
            raise ValueError('Exact native routine privilege kind is required')
        scope = facts['routine_type'] + ' ' + identifier(facts['table_schema']) + '.' + identifier(facts['routine_name'])
    elif section != 'visible-global-grants':
        raise ValueError('Unknown native privilege scope')
    return {'source': ('GRANT ' if action == 'grant' else 'REVOKE ') + privilege + ' ON ' + scope +
            (' TO ' if action == 'grant' else ' FROM ') + account(user, host) + (' WITH GRANT OPTION' if grant_option else ''), 'parameters': []}
