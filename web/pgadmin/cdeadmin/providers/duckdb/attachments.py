"""One-use attachment reviews on the original DuckDB native query handle."""
from copy import deepcopy
import hashlib
import json
import os
import stat
import time
import uuid

from ...sdk import RelationalClientError
from ..embedded_route import contained_database

QUERY = ('SELECT database_name,database_oid,path,type,readonly FROM duckdb_databases() '
    'WHERE NOT internal ORDER BY database_name')


def catalogs(connection):
    keys = ('name', 'oid', 'path', 'type', 'read_only')
    rows = [dict(zip(keys, row)) for row in connection.execute(QUERY).fetchall()]
    for row in rows:
        row['oid'] = str(row['oid'])
    return rows


def identifier_key(value):
    # Native quoted and unquoted identifiers use ASCII case comparison.
    return value.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def file_identity(route, value, *, create=False):
    if not isinstance(value, str) or not os.path.isabs(value) or '\x00' in value:
        raise ValueError('Select an absolute DuckDB file under the registered root')
    path = contained_database({**route, 'database': value})
    if os.path.islink(value):
        raise ValueError('Attachment targets cannot be symbolic links')
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        if not create or not os.path.isdir(os.path.dirname(path)):
            raise ValueError('Select an existing DuckDB file or explicitly allow native creation') from None
        return {'path': path, 'exists': False}
    except OSError:
        raise ValueError('The native attachment file is unavailable') from None
    try:
        info = os.fstat(descriptor);header = os.read(descriptor, 12)
        if not stat.S_ISREG(info.st_mode) or info.st_size < 12 or header[8:12] != b'DUCK':
            raise ValueError('The attachment target is not a native DuckDB file')
        return {'path': path, 'exists': True, 'device': str(info.st_dev), 'inode': str(info.st_ino),
            'bytes': str(info.st_size), 'modified_ns': str(info.st_mtime_ns)}
    finally:
        os.close(descriptor)


def compile_operation(route, draft, origin, before):
    if not isinstance(draft, dict) or draft.get('action') not in {'attach', 'detach'}:
        raise ValueError('Select native ATTACH or DETACH')
    attaching = draft['action'] == 'attach'
    allowed = {'action', 'alias', 'path', 'read_only', 'conflict', 'create_if_missing'} if attaching else {'action', 'alias', 'if_exists'}
    if set(draft) - allowed:
        raise ValueError('Unknown native attachment option')
    alias = draft.get('alias')
    if not isinstance(alias, str) or not alias or '\x00' in alias or len(alias.encode()) > 65536:
        raise ValueError('Select a bounded exact native catalog alias')
    if identifier_key(alias) in {'system', 'temp'} or identifier_key(alias) == identifier_key(origin[0]):
        raise ValueError('The original registered catalog and internal catalogs cannot be replaced or detached')
    target = next((row for row in before if identifier_key(row['name']) == identifier_key(alias)), None)
    if target is not None:
        alias = target['name']
    identity = None
    if attaching:
        read_only = draft.get('read_only', True);create = draft.get('create_if_missing', False)
        conflict = draft.get('conflict', 'ERROR')
        if type(read_only) is not bool or type(create) is not bool or conflict not in {'ERROR', 'IGNORE', 'REPLACE'}:
            raise ValueError('Select exact native access, creation and conflict options')
        if create and read_only or route.get('read_only') is True and not read_only:
            raise ValueError('Native file creation and writable attachment require writable authorization')
        if target is not None and conflict == 'IGNORE':
            value = draft.get('path')
            if not isinstance(value, str) or not os.path.isabs(value) or '\x00' in value:
                raise ValueError('Select an absolute native attachment path')
            identity = {'path': contained_database({**route, 'database': value}), 'ignored': True}
        else:
            identity = file_identity(route, draft.get('path'), create=create)
        primary = contained_database(route)
        if not identity.get('ignored') and (identity['path'] == primary or any(
                row['path'] == identity['path'] and row['name'] == origin[0] for row in before)):
            raise ValueError('The registered primary file cannot be reattached through another alias')
        if target is not None and conflict == 'ERROR':
            raise ValueError('The exact native catalog alias is already attached')
        prefix = 'ATTACH ' + ('IF NOT EXISTS ' if conflict == 'IGNORE' else 'OR REPLACE ' if conflict == 'REPLACE' else '')
        source = prefix + "'" + identity['path'].replace("'", "''") + "' AS " + quote(alias)
        source += ' (READ_ONLY)' if read_only else ' (READ_WRITE)'
    else:
        missing_ok = draft.get('if_exists', False)
        if type(missing_ok) is not bool or target is None and not missing_ok:
            raise ValueError('Select an attached exact alias or explicitly select IF EXISTS')
        source = 'DETACH DATABASE ' + ('IF EXISTS ' if missing_ok else '') + quote(alias)
    import duckdb
    statements = duckdb.extract_statements(source)
    expected = duckdb.StatementType.ATTACH if attaching else duckdb.StatementType.DETACH
    if len(statements) != 1 or statements[0].type != expected:
        raise ValueError('Exactly one provider-built native attachment statement is required')
    return {'source': source, 'draft': deepcopy(draft), 'file_identity': identity, 'alias': alias}


def action(client, handle, route, request):
    if not isinstance(request, dict):
        raise ValueError('Select a native attachment operation')
    operation = request.get('operation')
    allowed = {'operation', 'draft'} if operation == 'review' else {'operation', 'review_id', 'review_digest', 'confirmation', 'confirmed'} if operation == 'apply' else {'operation', 'review_id'} if operation == 'receipt' else {'operation'}
    if operation not in {'inventory', 'review', 'apply', 'receipt'} or set(request) - allowed:
        raise ValueError('Unknown native attachment workflow request')
    context = client._attachment_contexts.get(id(handle))
    if not context or context['route'] != route:
        raise ValueError('The retained DuckDB session belongs to another or changed registration')
    scope = context['session_scope_id'];now = time.monotonic()
    def public(record):
        return deepcopy({key: value for key, value in record.items() if key not in {'compiled', 'baseline', 'deadline'}})
    if operation == 'receipt':
        record = client._attachment_reviews.get(request.get('review_id'))
        if not record or record['session_scope_id'] != scope:
            raise ValueError('The attachment receipt belongs to another or closed native session')
        return public(record)
    if operation == 'apply':
        record = client._attachment_reviews.get(request.get('review_id'))
        if not record or record['session_scope_id'] != scope or request.get('review_digest') != record['review_digest']:
            raise ValueError('The attachment review belongs to another or closed native session')
        if record['state'] != 'reviewed':
            return public(record)
    before = catalogs(handle)
    origin = context['origin']
    live_origin = next((row for row in before if row['name'] == origin[0]), None)
    if not live_origin or (live_origin['name'], live_origin['oid'], live_origin['path']) != (origin[0], str(origin[1]), origin[2]):
        raise ValueError('The original retained DuckDB catalog identity changed')
    if operation == 'inventory':
        return {'session_scope_id': scope, 'catalogs': before, 'original_catalog': origin[0],
            'automatic_retry': False, 'caller_transaction_decision_requested': False}
    if operation == 'review':
        for key in list(client._attachment_reviews):
            old = client._attachment_reviews[key]
            if old['deadline'] < now or old['session_scope_id'] not in {
                    value['session_scope_id'] for value in client._attachment_contexts.values()}:
                del client._attachment_reviews[key]
        if len(client._attachment_reviews) >= 256:
            raise ValueError('Close old attachment reviews before creating another')
        compiled = compile_operation(route, request.get('draft'), origin, before)
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed', 'session_scope_id': scope,
            'deadline': now + 300, 'compiled': compiled, 'baseline': before,
            'source': compiled['source'], 'alias': compiled['alias'],
            'action': compiled['draft']['action'], 'file_identity': compiled['file_identity'],
            'automatic_retry': False, 'caller_transaction_decision_requested': False,
            'warnings': ['Changes use the original native session. Attached catalogs can be visible to other connections sharing its DuckDB instance.',
                'ATTACH follows its native transaction. Rollback does not restore a detached catalog or remove a file created by ATTACH.',
                'Registered automatic attachments can be restored when another connection opens. External file/instance changes are not fenced.']}
        record['review_digest'] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        client._attachment_reviews[record['review_id']] = record
        return public(record)
    record = client._attachment_reviews.get(request.get('review_id'))
    if not record or record['session_scope_id'] != scope or request.get('review_digest') != record['review_digest']:
        raise ValueError('The attachment review belongs to another or closed native session')
    # Every completed or uncertain record is read without redispatch.
    if record['state'] != 'reviewed':
        return public(record)
    if record['deadline'] < now or request.get('confirmed') is not True or request.get('confirmation') != record['alias']:
        raise ValueError('Confirm the current reviewed native attachment alias')
    try:
        rebuilt = compile_operation(route, record['compiled']['draft'], origin, before)
    except (ValueError, RelationalClientError):
        record.update(state='refused', native_dispatched=False, native_acknowledged=False,
            reason='Native attachment namespace or file changed since review')
        return public(record)
    if rebuilt != record['compiled'] or before != record['baseline']:
        record.update(state='refused', native_dispatched=False, native_acknowledged=False,
            reason='Native attachment namespace or file changed since review')
        return public(record)
    record.update(state='unknown_outcome', native_dispatched=True, native_acknowledged=False,
        native_catalog_or_file_effects_possible=True)
    try:
        handle.execute(record['source'])
        handle.fetchall()
        record['native_acknowledged'] = True
        after = catalogs(handle)
        selected = next((row for row in after if row['name'] == record['alias']), None)
        if record['action'] == 'detach':
            verified = selected is None
        else:
            old = next((row for row in before if row['name'] == record['alias']), None)
            if record['compiled']['draft'].get('conflict') == 'IGNORE' and old is not None:
                verified = selected == old
            else:
                expected = record['compiled']['file_identity']['path']
                verified = selected is not None and selected['path'] == expected and selected['read_only'] == record['compiled']['draft'].get('read_only', True)
                if verified:
                    record['observed_file_identity'] = file_identity(route, expected)
                    prior = record['compiled']['file_identity']
                    verified = not prior['exists'] or all(prior[key] == record['observed_file_identity'][key] for key in ('device', 'inode'))
        client._observe(handle, blocked=not verified)
        record.update(state='acknowledged', native_catalogs=after, rediscovery_verified=verified)
    except Exception as error:
        from .driver import uncertain
        try:
            record['native_catalogs_after_error'] = catalogs(handle)
        except Exception as observation_error:
            record['observation_error_type'] = type(observation_error).__name__
        try:
            client._observe(handle, blocked=uncertain(error))
        except Exception:
            client._observe(handle, blocked=True)
        record.update(state='acknowledged' if record['native_acknowledged'] else 'unknown_outcome' if uncertain(error) else 'refused',
            error_type=type(error).__name__, rediscovery_verified=False)
    record['session_reuse_blocked'] = bool(client._states[id(handle)].get('session_reuse_blocked'))
    return public(record)
