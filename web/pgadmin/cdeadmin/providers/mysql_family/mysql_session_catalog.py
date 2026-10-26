"""Explicit retained-session inspection and temporary-table lifecycle.

MySQL has no complete temporary-table enumeration interface. The caller selects
names to inspect; native SHOW CREATE distinguishes a shadow from a base table.
Only this explicit action touches source diagnostics. Ordinary completion uses
the last snapshot until any source command invalidates it.
"""
from copy import deepcopy
import json
import hashlib
from ...sdk import RelationalClientError
from .mysql_indexes import identifier
from .relay_positions import failure


def compile_operation(operation, draft, target):
    if not isinstance(draft, dict) or not isinstance(target, dict):
        raise RelationalClientError('Select a retained session and native object')
    if draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the selected object name')
    if operation == 'refresh_session_metadata':
        if set(draft) - {'confirmation', 'replace_diagnostics', 'temporary_tables'} or draft.get('replace_diagnostics') is not True:
            raise RelationalClientError('Explicitly allow replacement of source-session diagnostics')
        tables = draft.get('temporary_tables', [])
        if not isinstance(tables, list) or len(tables) > 128:
            raise RelationalClientError('Select at most 128 temporary tables')
        for row in tables:
            if not isinstance(row, dict) or set(row) != {'database', 'name'}:
                raise RelationalClientError('Supply separate database and table names')
            identifier(row['database']); identifier(row['name'])
        statements = []
    elif operation == 'drop_temporary':
        if set(draft) != {'confirmation'} or len(target.get('display_path', [])) != 2:
            raise RelationalClientError('Select the temporary table database and name')
        statements = [{'source': 'DROP TEMPORARY TABLE ' + '.'.join(identifier(part) for part in target['display_path']), 'parameters': ()}]
    else:
        raise RelationalClientError('Unknown retained-session operation')
    return {'statements': statements, 'mysql_session_catalog': {'operation': operation, 'draft': deepcopy(draft)},
            'warnings': ['Requires the selected retained native session. Explicit inspection replaces its diagnostics. Temporary-table names are selected, not inferred from the committed catalog. No commit, rollback or automatic retry is sent.']}


def invalidate(client, handle):
    client._session_catalogs.pop(id(handle), None)


def inspect(handle, tables):
    cursor = handle.cursor(); commands = 0; resources = []; selected = []
    try:
        cursor.execute('SELECT CURRENT_ROLE(), CURRENT_USER(), DATABASE()'); commands += 1
        roles, principal, database = cursor.fetchone()
        cursor.execute('SELECT ROLE_NAME, ROLE_HOST FROM information_schema.ENABLED_ROLES ORDER BY ROLE_NAME, ROLE_HOST'); commands += 1
        enabled_roles = cursor.fetchall()
        for row in tables:
            path = [row['database'], row['name']]
            qualified = '.'.join(identifier(part) for part in path)
            cursor.execute('SHOW CREATE TABLE ' + qualified); commands += 1
            definition = cursor.fetchone()[1]
            if not definition.startswith('CREATE TEMPORARY TABLE '):
                raise RelationalClientError('A selected name resolves to a base table, not a temporary table')
            selected.append(path)
            resources.append({'resource_kind': 'table', 'display_path': path, 'display_name': path[-1], 'detail': 'temporary table', 'temporary': True})
            cursor.execute('SHOW FULL COLUMNS FROM ' + qualified); commands += 1
            names = [column[0].lower() for column in cursor.description]
            for values in cursor.fetchall():
                column = dict(zip(names, values))
                resources.append({'resource_kind': 'column', 'display_path': path + [column['field']],
                    'display_name': column['field'], 'detail': column['type'], 'temporary': True,
                    'hidden_from_star': 'INVISIBLE' in column['extra'].upper().split()})
            from ..native_editor import MAX_BYTES, MAX_SYMBOLS
            if len(resources) > MAX_SYMBOLS or len(json.dumps(resources).encode()) > MAX_BYTES:
                raise RelationalClientError('Selected temporary metadata exceeds the editor resource budget')
        return {'active_role': roles, 'enabled_roles': enabled_roles, 'authenticated_principal': principal, 'default_schema': database,
                'selected_temporary_tables': selected, 'resources': resources,
                'original_session_commands_sent': commands, 'original_diagnostics_preserved': False,
                'temporary_enumeration_complete': False}
    finally:
        cursor.close()


def editor_snapshot(connection, snapshot):
    from ..native_editor import metadata
    commands = 0
    class Cursor:
        def __init__(self): self.native = connection.cursor()
        def __getattr__(self, name): return getattr(self.native, name)
        def execute(self, *args, **kwargs):
            nonlocal commands
            commands += 1
            return self.native.execute(*args, **kwargs)
    class Source:
        def __getattr__(self, name): return getattr(connection, name)
        def cursor(self): return Cursor()
    result = metadata(Source(), 'mysql')
    snapshot['original_session_commands_sent'] += commands
    result['observations'].append({'section': 'retained-session-overlays'})
    overlay(result, snapshot)
    result.update(complete=False, original_session_commands_sent=snapshot['original_session_commands_sent'],
        original_diagnostics_preserved=False, original_session_catalog_binding_validated=True)
    context = result['context']
    context.pop('context_revision', None)
    context['context_revision'] = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
    return result


def overlay(result, snapshot):
    if snapshot is None:
        return
    context = result['context']
    context.update(active_role=snapshot['active_role'], original_active_roles_observed=True,
        original_temporary_objects_observed=True, temporary_enumeration_complete=False)
    def key(path):
        return tuple(part.lower() if context.get('lower_case_table_names') else part for part in path[:2])
    selected = {key(path) for path in snapshot['selected_temporary_tables']}
    result['resources'] = [row for row in result['resources'] if key(row['display_path']) not in selected] + deepcopy(snapshot['resources'])
    result['visible_resource_count'] = len(result['resources'])
    result['session_catalog_snapshot'] = {key: deepcopy(value) for key, value in snapshot.items() if key not in {'resources', 'editor_context'}}
    result['observations'][-1] = {'section': 'retained-session-overlays', 'available': True,
        'scope': 'Explicit active roles and selected temporary names; invalidated by the next source command. Native MySQL cannot enumerate every temporary table.'}
    result['coverage'] = result['observations'][-1]['scope']


def apply(client, request, connection=None):
    from ..native_editor import session_access
    from .mysql_charsets import explicit_source
    compiled = request['provider_payload']['compiled']
    intent = compiled['mysql_session_catalog']; dispatched = acknowledged = False
    if connection is None or not compiled.get('mysql_session_id'):
        raise RelationalClientError('This operation requires its reviewed retained session')
    with session_access(client, connection, 'mysql'), explicit_source(connection) as explicit:
        invalidate(client, connection)
        try:
            client._executions.sessions.get(connection)
            if intent['operation'] == 'refresh_session_metadata':
                dispatched = True
                snapshot = inspect(connection, intent['draft'].get('temporary_tables', [])); acknowledged = True
                if snapshot['selected_temporary_tables']:
                    connection._cdeadmin_temporary_management_used = True
                snapshot['editor_context'] = editor_snapshot(connection, snapshot)
                snapshot['original_session_commands_sent'] += explicit['commands']
                snapshot['editor_context']['original_session_commands_sent'] = snapshot['original_session_commands_sent']
                snapshot['editor_context']['session_catalog_snapshot']['original_session_commands_sent'] = snapshot['original_session_commands_sent']
                client._session_catalogs[id(connection)] = deepcopy(snapshot)
                result = {'session_catalog': snapshot}
            else:
                # Shared execution with a borrowed connection neither commits
                # nor closes it. DROP TEMPORARY never drops a base table.
                from ..relational_admin import RelationalAdministration
                connection._cdeadmin_temporary_management_used = True
                dispatched = True
                result = RelationalAdministration.apply(client.config.administration, client, request, connection)
                acknowledged = True
            return {**result, 'accepted': True, 'native_acknowledged': True,
                    'commit_requested': False, 'rollback_requested': False,
                    'staged_in_provider_session': True, 'automatic_retry': False}
        except Exception as error:
            code = getattr(error, 'errno', None)
            if dispatched and not acknowledged and not isinstance(error, RelationalClientError) and (code is None or 2000 <= code < 3000):
                client._uncertain_sessions.add(id(connection))
            raise failure(error, dispatched, acknowledged) from None
