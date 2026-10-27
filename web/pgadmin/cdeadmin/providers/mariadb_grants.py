"""MariaDB grant scopes and separately observed account/role identities."""
import re
from .mysql_roles import account
from .mysql_family.mariadb_catalog import identifier


def resolve(grantee, accounts):
    matches = [row for row in accounts if grantee in {
        "'" + row['user'] + "'@'" + row['host'] + "'", row.get('grantee_identity')}]
    if len(matches) != 1:
        return {'grantee_identity_available': False}
    row = matches[0]
    return {'grantee_identity_available': True, 'grantee_user': row['user'],
            'grantee_host': row['host'], 'grantee_is_role': row.get('is_role') == 'Y'}


def routine_grants(accounts, read):
    """Observe effective native ACLs, without guessing storage encodings.

    SHOW GRANTS can include authentication clauses on global lines. Only
    bounded routine-grant facts are retained; unrelated lines never leave this
    function or enter a DDN document, preview or receipt.
    """
    quoted = r'`((?:``|[^`])*)`'
    pattern = re.compile(r'^GRANT (USAGE|EXECUTE(?:, ALTER ROUTINE)?|ALTER ROUTINE(?:, EXECUTE)?) ON '
        r'(PROCEDURE|FUNCTION|PACKAGE BODY|PACKAGE) ' + quoted + r'\.' + quoted + r' TO ')
    for principal in accounts:
        target = identifier(principal['user']) if principal.get('is_role') == 'Y' else account(principal['user'], principal['host'])
        for result in read('SHOW GRANTS FOR ' + target):
            source = next(iter(result.values()))
            if not isinstance(source, str) or len(source.encode('utf8')) > 65536:
                raise ValueError('Native grant observation exceeds its supported bound')
            match = pattern.match(source)
            if not match:
                if re.match(r'^GRANT .* ON (PROCEDURE|FUNCTION|PACKAGE) ', source):
                    raise ValueError('Native routine grant syntax is unavailable')
                continue
            privileges, kind, database, name = match.groups()
            for privilege in privileges.split(', '):
                yield {'grantee': principal['grantee_identity'], 'grantee_user': principal['user'],
                    'grantee_host': principal['host'], 'grantee_is_role': principal.get('is_role') == 'Y',
                    'grantee_identity_available': True, 'table_schema': database.replace('``','`'),
                    'routine_name': name.replace('``','`'), 'routine_type': kind,
                    'privilege_type': privilege, 'is_grantable': 'YES' if source.endswith(' WITH GRANT OPTION') else 'NO'}


def scoped_statement(facts, section, action, grant_option, grant_option_only=False):
    if facts.get('grantee_identity_available') is not True:
        raise ValueError('Separate native account or role identity is required')
    user, host = facts.get('grantee_user'), facts.get('grantee_host')
    if facts.get('grantee_is_role') is True:
        if host != '':
            raise ValueError('A MariaDB role has no host suffix')
        principal = identifier(user)
    else:
        principal = account(user, host)
    privilege = facts.get('privilege_type')
    if not isinstance(privilege, str) or not re.fullmatch(r'[A-Z][A-Z0-9_ ]{0,127}', privilege):
        raise ValueError('Exact native privilege type is required')
    scope = '*.*'
    if section == 'schema-grants':
        scope = identifier(facts['table_schema']) + '.*'
    elif section in {'table-grants', 'column-grants'}:
        scope = identifier(facts['table_schema']) + '.' + identifier(facts['table_name'])
        if section == 'column-grants':
            privilege += '(' + identifier(facts['column_name']) + ')'
    elif section == 'routine-grants':
        if facts['routine_type'] not in {'FUNCTION', 'PROCEDURE', 'PACKAGE', 'PACKAGE BODY'}:
            raise ValueError('Exact native MariaDB routine kind is required')
        scope = facts['routine_type'] + ' ' + identifier(facts['table_schema']) + '.' + identifier(facts['routine_name'])
    elif section != 'visible-global-grants':
        raise ValueError('Unknown native privilege scope')
    if grant_option_only:
        if action != 'revoke' or section == 'column-grants':
            raise ValueError('Grant-option removal requires an explicit object scope')
        privilege = 'GRANT OPTION'
    return {'source': ('GRANT ' if action == 'grant' else 'REVOKE ') + privilege + ' ON ' + scope +
            (' TO ' if action == 'grant' else ' FROM ') + principal + (' WITH GRANT OPTION' if grant_option else ''),
            'parameters': []}
