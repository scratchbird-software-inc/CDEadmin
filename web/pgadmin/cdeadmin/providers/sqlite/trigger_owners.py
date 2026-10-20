"""TEMP trigger identities and native compilation of their declared owner."""
import re
import sqlite3
import uuid

from ...sdk import RelationalClientError


IDENTIFIER = r'''(?:"(?:[^"]|"")*"|`(?:[^`]|``)*`|\[[^\]]*\]|'(?:[^']|'')*'|[A-Za-z_\u0080-\U0010ffff][A-Za-z_0-9$\u0080-\U0010ffff]*)'''
HEADER = re.compile(r'^\s*CREATE\s+(?:(?:TEMP|TEMPORARY)\s+)?TRIGGER\s+'
    r'(?:IF\s+NOT\s+EXISTS\s+)?' + IDENTIFIER + r'(?:\s*\.\s*' + IDENTIFIER + r')?', re.I)
FOLD = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')


class AuthorizationCleanupUnconfirmed(RelationalClientError):
    """The caller must discard a connection whose policy was not restored."""


def declaration(source):
    """Replace only the declaration name; SQL grammar remains native-owned."""
    if not isinstance(source, str) or '\x00' in source or len(source.encode('utf8')) > 1024 * 1024:
        raise ValueError('Native trigger declaration is unavailable')
    import sqlparse
    from sqlparse.tokens import Comment, Whitespace
    try:
        tokens = [token for statement in sqlparse.parse(source) for token in statement.flatten()]
    except sqlparse.exceptions.SQLParseError:
        raise ValueError('Native trigger declaration exceeds the token budget') from None
    cleaned = ''.join(' ' if token.ttype in Comment else token.value for token in tokens)
    matched = HEADER.match(cleaned)
    if matched is None:
        raise ValueError('Native trigger declaration header is unavailable')
    significant = [token.value for token in tokens
                   if token.ttype not in Whitespace and token.ttype not in Comment]
    on = next((index for index, value in enumerate(significant) if value.upper() == 'ON'), None)
    if on is None:
        raise ValueError('Native trigger owner declaration is unavailable')
    qualified = len(significant) > on + 2 and significant[on + 2] == '.'
    name = '__scratchrobin_trigger_owner_' + uuid.uuid4().hex
    # With an explicitly qualified trigger namespace, SQLite's CREATE_TRIGGER
    # authorization reports the table database. The TEMP keyword reports the
    # temporary namespace instead and cannot identify an attached owner.
    return name, 'CREATE TRIGGER "temp"."' + name + '"' + cleaned[matched.end():], qualified


def observe(connection, resource, resources):
    """Never execute CREATE or trigger DML and never replace hidden policy."""
    result = {'available': False, 'authority': 'native-nonexecuting-declaration-prepare',
              'existing_trigger_execution_observed': False}
    if not hasattr(connection, '_cdeadmin_authorizer'):
        return {**result, 'reason': 'connection_authorization_policy_unobservable'}
    metadata = resource['native']['catalog_metadata']
    expected = metadata['table_name']
    candidates = [row for row in resources.values() if row['resource_kind'] in {
        'table', 'view', 'virtual-table', 'fts-table'} and
        row['display_name'].translate(FOLD) == expected.translate(FOLD)]
    try:
        name, source, qualified = declaration(resource['native']['ddl'])
    except (ValueError, RecursionError):
        return {**result, 'reason': 'native_declaration_unavailable'}
    if not qualified and len(candidates) > 1:
        return {**result, 'reason': 'unqualified_owner_has_multiple_native_candidates',
                'candidate_paths': [row['display_path'] for row in candidates]}
    observed = []
    previous = connection._cdeadmin_authorizer
    def authorize(action, target, owner, database, context):
        permitted = previous(action, target, owner, database, context) if previous else sqlite3.SQLITE_OK
        if permitted == sqlite3.SQLITE_OK and action in {
                sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_TEMP_TRIGGER}:
            observed.append((target, owner, database))
        return permitted
    cursor = None
    try:
        connection.set_authorizer(authorize)
        cursor = connection.execute('EXPLAIN ' + source)
        cursor.fetchone()
    except sqlite3.Error as error:
        return {**result, 'reason': 'native_declaration_prepare_refused',
                'native_error_code': getattr(error, 'sqlite_errorcode', None)}
    finally:
        cleanup_failed = False
        if cursor is not None:
            try:cursor.close()
            except Exception:cleanup_failed = True
        try:connection.set_authorizer(previous)
        except Exception:cleanup_failed = True
        if cleanup_failed:
            raise AuthorizationCleanupUnconfirmed('SQLite trigger catalog authorization cleanup is unconfirmed; close this session')
    if len(observed) != 1 or observed[0][:2] != (name, expected):
        return {**result, 'reason': 'native_owner_observation_inconsistent'}
    owner = next((row for row in candidates if row['display_path'] == [observed[0][2], expected]), None)
    if owner is None:
        return {**result, 'reason': 'native_owner_not_in_visible_catalog'}
    return {**result, 'available': True, 'database': observed[0][2],
            'table': expected, 'resource_id': owner['resource_id'],
            'qualified_owner': qualified}


def reconcile(connection, resources):
    temporary = [row for row in resources.values() if row['resource_kind'] == 'trigger' and row['display_path'][0] == 'temp']
    if not temporary:return
    ids = {row['resource_id'] for row in temporary}
    for row in resources.values():
        if 'triggers' in row['native']:
            row['native']['triggers'] = [item for item in row['native']['triggers'] if item['resource_id'] not in ids]
    for row in temporary:
        result = observe(connection, row, resources)
        row['native']['owner_binding_observation'] = result
        if not result['available']:continue
        row['native']['catalog_metadata']['owner_database'] = result['database']
        row['native']['navigator_parent_resource_id'] = result['resource_id']
        resources[result['resource_id']]['native']['triggers'].append({
            'resource_id': row['resource_id'], 'name': row['display_name'],
            'ddl': row['native']['ddl'], 'schema': 'temp',
            'owner_database': result['database']})
