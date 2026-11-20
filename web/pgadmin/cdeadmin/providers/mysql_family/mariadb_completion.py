"""Committed-catalog completion without commands on the retained session."""
from copy import deepcopy
import hashlib
import json

from ...sdk.relational import RelationalClientError

IDENTITY_SQL = 'SELECT @@server_uid,CURRENT_USER(),VERSION(),CONNECTION_ID()'


def identity(handle):
    cursor = handle.cursor()
    try:
        cursor.execute(IDENTITY_SQL)
        row = cursor.fetchone()
        if (not row or len(row) != 4 or not all(row[:3])
                or type(row[3]) is not int or row[3] != handle.connection_id):
            raise RelationalClientError('MariaDB editor identity is unavailable')
        return tuple(row)
    finally:
        cursor.close()


def admit(client, handle):
    """Capture native identity before returning a new session to its caller."""
    try:
        observed = identity(handle)
    except Exception:
        raise RelationalClientError('MariaDB editor identity admission failed') from None
    client._completion_identities[id(handle)] = (handle, observed)


def complete(client, handle, *, source_context=None):
    from ..native_editor import metadata
    from .mariadb_connections import POOL_ARGUMENTS

    peer = None
    failed = False
    try:
        # The caller holds session_access: no concurrent user command or close.
        client._executions.sessions.get(handle)
        entry = client._completion_identities.get(id(handle))
        if entry is None or entry[0] is not handle or handle.connection_id != entry[1][3]:
            raise RelationalClientError('MariaDB source identity is unconfirmed')
        request = deepcopy(client._session_requests[id(handle)])
        for key in POOL_ARGUMENTS:
            request['route'].pop(key, None)
        request['route']['reconnect'] = False
        request['route']['autocommit'] = True
        if source_context is not None:
            if tuple(source_context.get(key) for key in ('server_uid','principal','version','connection_id')) != entry[1]:
                raise RelationalClientError('Original context identity is unavailable')
            request['route'].pop('database',None)
            if source_context.get('default_schema') is not None:
                request['route']['database']=source_context['default_schema']
        peer = client._connect(request)
        if peer is handle or peer.connection_id == entry[1][3]:
            peer = None  # Never release a source handle returned by a broken connector.
            raise RelationalClientError('MariaDB completion requires a private connection')
        observed = identity(peer)
        if observed[:3] != entry[1][:3] or observed[3] == entry[1][3]:
            raise RelationalClientError('MariaDB private catalog identity changed')
        if source_context is not None:
            from .mariadb_editor_context import apply_to_peer
            apply_to_peer(peer,source_context)
        result = metadata(peer, 'mariadb')
        context = result['context']
        if context.get('version') != observed[2]:
            raise RelationalClientError('MariaDB private catalog version changed')
        revisions = getattr(client, '_source_revisions', None)
        snapshots = getattr(client, '_editor_context_snapshots', None)
        revision = revisions.get(id(handle), 0) if isinstance(revisions, dict) else 0
        snapshot_valid = (
            isinstance(snapshots, dict) and snapshots.get(id(handle)) == revision
            if source_context is None else True
        )
        # Peer settings are not observations of the caller's active context.
        context['metadata_peer_context'] = {key: context.pop(key) for key in (
            'default_schema', 'sql_mode', 'character_set_client', 'active_role')
            if key in context}
        context['original_session_context_observed'] = False
        context['source_work_revision'] = revision
        context['explicit_context_snapshot_valid'] = snapshot_valid
        for row in context.get('routine_type_candidates', []):
            row['original_session_mode_observed'] = False
            row['availability'] = 'requires-original-session-mode-check'
        result['observations'].append({
            'section': 'retained-session-overlays', 'available': False,
            'reason': 'source-role-settings-temporary-and-uncommitted-catalog-unobserved'})
        result.update(complete=False, observation_source='private-native-peer',
            original_session_commands_sent=0, original_diagnostics_preserved=True,
            original_session_catalog_binding_validated=False,
            original_active_roles_observed=False, original_temporary_objects_observed=False,
            coverage='Committed catalog on a separate same-server authenticated connection. '
                     'Source role, settings, temporary objects and uncommitted DDL are unobserved.')
        if source_context is not None:
            for key in ('default_schema','sql_mode','character_set_client','active_role',
                        'character_set_connection','character_set_results','collation_connection'):
                context[key]=source_context[key]
            context['original_session_context_observed']=True
            oracle='ORACLE' in str(source_context['sql_mode']).split(',')
            for row in context.get('routine_type_candidates',[]):
                row['original_session_mode_observed']=True
                row['available']=(row['required_sql_mode']=='oracle')==oracle
                row['availability']='observed-original-session-mode' if row['available'] else 'requires-other-native-mode'
            commands_sent = int(source_context.get('original_session_commands_sent', 1))
            has_temp_overlay = 'temporary_tables' in source_context
            temp_tables = source_context.get('temporary_tables') or []
            temp_complete = bool(source_context.get('temporary_enumeration_complete', True))
            if temp_tables:
                lctn = int(source_context.get('lower_case_table_names') or context.get('lower_case_table_names') or 0)
                norm = (lambda d, t: (str(d).lower(), str(t).lower())) if lctn else (lambda d, t: (str(d), str(t)))
                temp_by_key = {norm(item['database'], item['name']): item for item in temp_tables}
                shadowed_keys = set()
                rewritten = []
                for sym in result['resources']:
                    kind = sym.get('resource_kind')
                    path = sym.get('display_path') or []
                    if kind == 'table' and len(path) == 2 and norm(path[0], path[1]) in temp_by_key:
                        shadowed_keys.add(norm(path[0], path[1]))
                        rewritten.append({
                            **sym,
                            'resource_kind': 'shadowed-table',
                            'resource_id': f'table:{path[0]}:{path[1]}',
                            'detail': 'BASE TABLE shadowed by session TEMPORARY table',
                            'shadowed_by_temporary': True,
                            'authority_scope': 'committed-catalog',
                        })
                    elif kind == 'column' and len(path) == 3 and norm(path[0], path[1]) in temp_by_key:
                        # Omit shadowed base-table columns from active relation column completion
                        continue
                    else:
                        rewritten.append(sym)
                for item in temp_tables:
                    db_name, tbl_name = item['database'], item['name']
                    shadows_base = norm(db_name, tbl_name) in shadowed_keys
                    rewritten.append({
                        'resource_kind': 'table',
                        'resource_id': f'temporary-table:{db_name}:{tbl_name}',
                        'display_path': [db_name, tbl_name],
                        'display_name': tbl_name,
                        'detail': 'TEMPORARY' + (' (shadows BASE TABLE)' if shadows_base else ''),
                        'temporary': True,
                        'authority_scope': 'retained-session',
                        'shadows_base_table': shadows_base,
                    })
                    for col in item.get('columns', []):
                        col_entry = {
                            'resource_kind': 'column',
                            'resource_id': f"temporary-column:{db_name}:{tbl_name}:{col['name']}",
                            'display_path': [db_name, tbl_name, col['name']],
                            'display_name': col['name'],
                            'detail': col['column_type'],
                            'temporary': True,
                            'authority_scope': 'retained-session',
                        }
                        if col.get('hidden_from_star'):
                            col_entry['hidden_from_star'] = True
                        rewritten.append(col_entry)
                result['resources'] = rewritten
                result['visible_resource_count'] = len(rewritten)
            context['temporary_table_count'] = int(source_context.get('temporary_table_count', len(temp_tables)))
            result.update(
                complete=False,
                original_session_commands_sent=commands_sent,
                original_diagnostics_preserved=False,
                original_active_roles_observed=True,
                original_temporary_objects_observed=has_temp_overlay,
                temporary_enumeration_complete=temp_complete if has_temp_overlay else False,
                snapshot_invalidated_by_next_source_command=True,
                coverage=(
                    'Explicit original-session language/role/default-schema and session TEMPORARY table '
                    'observation merged with a same-context private committed catalog. Uncommitted DDL/state remains unobserved.'
                    if has_temp_overlay else
                    'Explicit original-session language/role/default-schema observation and same-context private committed catalog. Temporary objects and uncommitted schema remain unobserved.'
                ),
            )
            result['observations'][-1]['reason'] = (
                'source-language-role-and-temporary-tables-observed;uncommitted-catalog-unobserved'
                if (has_temp_overlay and temp_complete)
                else 'source-language-and-role-observed;temporary-tables-truncated-and-uncommitted-catalog-unobserved'
                if has_temp_overlay
                else 'source-language-and-role-observed;temporary-and-uncommitted-catalog-unobserved'
            )
        context.pop('context_revision', None)
        context['context_revision'] = hashlib.sha256(json.dumps({
            'context': context, 'resources': result['resources'],
            'observations': result['observations'],
            'visible_resource_count': result['visible_resource_count']},
            sort_keys=True, default=str).encode()).hexdigest()
        return result
    except Exception:
        failed = True
        error = RelationalClientError('Private MariaDB completion is unavailable; '
            'no original-session metadata command was substituted')
        error.original_session_commands_sent = 1 if source_context is not None else 0
        error.original_diagnostics_preserved = source_context is None
        raise error from None
    finally:
        if peer is not None:
            if failed and isinstance(getattr(client, '_uncertain_sessions', None), set):
                client._uncertain_sessions.add(id(peer))
            try:
                released = client._close_idle_session(peer)
                if not released.get('connection_released'):
                    raise RelationalClientError('Private completion release is unconfirmed')
            except Exception:
                error = RelationalClientError('Private MariaDB completion release is unconfirmed; '
                    'the original session was not used for metadata')
                error.original_session_commands_sent = 1 if source_context is not None else 0
                error.original_diagnostics_preserved = source_context is None
                raise error from None
