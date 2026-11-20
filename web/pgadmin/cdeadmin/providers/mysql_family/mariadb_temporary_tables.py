"""Retained-session MariaDB temporary-table creation, drop and catalog separation.

MariaDB 12.2.2 enumerates original-session temporary tables through
information_schema.TABLES (TABLE_TYPE='TEMPORARY'). Temporary DDL executes ONLY
on the explicitly bound retained session without committing active transaction
work, DROP TEMPORARY TABLE never drops a committed base table of the same name,
and closing a session that held temporary tables discards the physical
connection so pooled borrowers never inherit session temporary objects.
"""
from collections.abc import Mapping
from copy import deepcopy
import json

from ...sdk import RelationalClientError
from .mariadb_catalog import identifier as quote_identifier

KEY = 'mariadb_temporary_table'
TABLE_OPERATIONS = {
    'drop_temporary': ('Drop temporary table', 'DROP TEMPORARY TABLE'),
}


def identifier(value):
    try:
        if isinstance(value, str):
            value.encode('utf8')
        return quote_identifier(value)
    except ValueError:
        raise RelationalClientError('Native MariaDB identifier must be nonempty text without NUL') from None


def temporary_table_resource_id(schema_name, table_name):
    schema_text, table_text = str(schema_name), str(table_name)
    if ':' in schema_text or ':' in table_text:
        return 'mariadb-temporary-table:' + json.dumps(
            [schema_text, table_text], ensure_ascii=False, separators=(',', ':')
        )
    return f'temporary-table:{schema_text}:{table_text}'


def temporary_column_resource_id(schema_name, table_name, column_name):
    parts = [str(schema_name), str(table_name), str(column_name)]
    if any(':' in part for part in parts):
        return 'mariadb-temporary-column:' + json.dumps(
            parts, ensure_ascii=False, separators=(',', ':')
        )
    return 'temporary-column:' + ':'.join(parts)


def temporary_storage_resource_id(schema_name, table_name):
    parts = [str(schema_name), str(table_name)]
    if any(':' in part for part in parts):
        return 'mariadb-temporary-table-storage:' + json.dumps(
            parts, ensure_ascii=False, separators=(',', ':')
        )
    return 'temporary-table-storage:' + ':'.join(parts)


def is_temporary_flag(options):
    value = options.get('temporary', False)
    if type(value) is not bool:
        raise RelationalClientError('Temporary must be boolean')
    return value


def form(operation, kind='table'):
    from ...ui_descriptors import UIDescriptorService
    from .descriptor_contracts import field_contract
    row = next(
        item for item in UIDescriptorService().engine('mariadb')['operations']
        if item['resource_kind'] == kind and item['operation_id'] == operation
    )
    return {
        'form_id': f'mariadb.{kind}.{operation}',
        'title': row['title'],
        'fields': [field_contract(field) for field in row['fields']],
    }


def compile_operation(operation, draft, target):
    if operation != 'drop_temporary':
        raise RelationalClientError('Unsupported MariaDB temporary-table operation')
    if not isinstance(draft, Mapping) or not isinstance(target, Mapping):
        raise RelationalClientError('Select a retained session and temporary table')
    draft = dict(draft)
    if set(draft) != {'confirmation'} or draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the exact temporary table name')
    path = target.get('display_path')
    if not isinstance(path, list) or len(path) != 2 or target.get('resource_kind') != 'table':
        raise RelationalClientError('Select the temporary table database and name')
    native = target.get('native')
    if not isinstance(native, Mapping):
        ext = (target.get('extensions') or {}).get('mariadb')
        native = ext.get('native') if isinstance(ext, Mapping) else {}
    if isinstance(native, Mapping) and native.get('table_type') == 'BASE TABLE' and native.get('temporary') is False:
        raise RelationalClientError('Selected resource is a committed base table; select the temporary table resource or retained session shadow')
    qualified = '.'.join(identifier(part) for part in path)
    return {
        'statements': [{'source': 'DROP TEMPORARY TABLE ' + qualified, 'parameters': ()}],
        KEY: {
            'operation': 'drop_temporary',
            'path': [str(path[0]), str(path[1])],
            'draft': deepcopy(draft),
            'retained_session_required': True,
        },
        'warnings': [
            'Executes DROP TEMPORARY TABLE on the bound retained MariaDB session only.',
            'Never drops a committed BASE TABLE if the session temporary table is absent.',
            'Does not commit or roll back active transaction work on the retained session.',
        ],
    }


def bind_review(client, planned, session_id=None):
    compiled = planned['provider_payload']['compiled']
    intent = compiled[KEY]
    session_id = session_id or intent.get('mariadb_session_id')
    if not isinstance(session_id, str) or not session_id:
        raise RelationalClientError('Select a retained MariaDB session before reviewing a temporary-table operation')
    intent['mariadb_session_id'] = session_id
    planned['command_preview']['retained_session_id'] = session_id
    planned['command_preview']['session_scoped'] = True
    return planned


def apply(client, request, connection=None):
    from ..native_editor import session_access
    from ..relational_admin import RelationalAdministration

    compiled = (request.get('provider_payload') or {}).get('compiled', {})
    intent = compiled.get(KEY) or {}
    bound_session_id = intent.get('mariadb_session_id')
    if connection is None or not bound_session_id:
        raise RelationalClientError('Temporary-table operations require their reviewed retained MariaDB session')
    if request.get('session_id') not in {None, bound_session_id}:
        raise RelationalClientError('Retained MariaDB session differs from the reviewed temporary-table plan')

    dispatched = acknowledged = False
    with session_access(client, connection, 'mariadb'):
        entry = client._completion_identities.get(id(connection))
        if entry is None or entry[0] is not connection or connection.connection_id != entry[1][3]:
            raise RelationalClientError('Retained MariaDB session identity changed before temporary-table execution')
        client._executions.sessions.get(connection)
        if callable(getattr(client, '_invalidate_editor_context', None)):
            client._invalidate_editor_context(connection)
        try:
            client._temporary_session_handles.add(id(connection))
            connection._cdeadmin_temporary_management_used = True
            dispatched = True
            result = RelationalAdministration.apply(
                client.config.administration, client, request, connection
            )
            acknowledged = True
            tbl_loc = intent.get('path') or intent.get('table') or []
            after_temp_exists = None
            if len(tbl_loc) == 2:
                obs_cur = connection.cursor()
                try:
                    obs_cur.execute(
                        "SELECT COUNT(*) FROM information_schema.TABLES "
                        "WHERE TABLE_TYPE = 'TEMPORARY' AND TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                        (tbl_loc[0], tbl_loc[1]),
                    )
                    (cnt,) = obs_cur.fetchone()
                    after_temp_exists = bool(cnt)
                finally:
                    obs_cur.close()
            return {
                **result,
                'accepted': True,
                'native_acknowledged': True,
                'native_implicit_commit': False,
                'commit_requested': False,
                'rollback_requested': False,
                'staged_in_provider_session': True,
                'retained_session_id': bound_session_id,
                'connection_id': connection.connection_id,
                'automatic_retry': False,
                'temporary_table_observation': {
                    'operation': intent.get('operation'),
                    'table': tbl_loc,
                    'after_temporary_exists': after_temp_exists,
                },
            }
        except Exception as error:
            code = getattr(error, 'errno', None)
            if (
                dispatched
                and not acknowledged
                and not isinstance(error, RelationalClientError)
                and (code is None or 2000 <= code < 3000)
            ):
                client._uncertain_sessions.add(id(connection))
            failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
                f'MariaDB temporary-table operation failed ({type(error).__name__}: {error})'
            )
            failure.native_dispatched = dispatched
            failure.native_acknowledged = acknowledged
            failure.automatic_retry = False
            failure.errno = code
            failure.sqlstate = getattr(error, 'sqlstate', None)
            raise failure from None
