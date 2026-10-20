"""One-use attachment reviews on the original DuckDB native query handle."""
from copy import deepcopy
import hashlib
import json
import os
import re
import stat
import threading
import time
import uuid
import weakref

from ...sdk import RelationalClientError
from ..embedded_route import contained_database

QUERY = ('SELECT database_name,database_oid,path,type,readonly,options,encrypted,cipher FROM duckdb_databases() '
    'WHERE NOT internal ORDER BY database_name')


def catalogs(connection):
    from .catalog import database_location
    keys = ('name', 'oid', 'path', 'type', 'read_only', 'options', 'encrypted', 'cipher')
    rows = [dict(zip(keys, row)) for row in connection.execute(QUERY).fetchall()]
    for row in rows:
        row['oid'] = str(row['oid'])
        row.update(database_location(row['path'], row['type'], row['options']))
    return rows


def identifier_key(value):
    # Native quoted and unquoted identifiers use ASCII case comparison.
    return value.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def file_identity(route, value, *, create=False):
    if value == ':memory:':
        if route.get('allow_memory') is not True:
            raise ValueError('In-memory attachment requires registered memory authorization')
        return {'path': ':memory:', 'memory': True}
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


def storage_options(draft, memory):
    value = draft.get('storage_options', {})
    if not isinstance(value, dict) or set(value) - {'block_size', 'row_group_size', 'storage_version', 'compress'}:
        raise ValueError('Select native block size, row-group size, storage version or memory compression')
    source = []
    for key in ('block_size', 'row_group_size'):
        if key in value:
            text = value[key]
            if not isinstance(text, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', text) or int(text) > 2**64-1:
                raise ValueError('Native storage sizes require exact unsigned 64-bit decimal text')
            source.append(key.upper() + ' ' + text)
    if 'storage_version' in value:
        version = value['storage_version']
        if not isinstance(version, str) or not version or len(version.encode()) > 128 or any(ord(c) < 32 for c in version):
            raise ValueError('Select a bounded exact native storage version')
        source.append("STORAGE_VERSION '" + version.replace("'", "''") + "'")
    if 'compress' in value:
        if type(value['compress']) is not bool or not memory:
            raise ValueError('Native COMPRESS requires an authorized in-memory attachment and a Boolean choice')
        source.append('COMPRESS ' + str(value['compress']).lower())
    return source


def alias_reuse(context, handle, compiled):
    transaction = str(handle.execute('SELECT current_transaction_id()').fetchone()[0])
    retired = context.setdefault('detached_aliases', {})
    context['detached_aliases'] = {name: value for name, value in retired.items() if value == transaction}
    if compiled['draft']['action'] == 'attach' and identifier_key(compiled['alias']) in context['detached_aliases']:
        raise ValueError('This native alias was detached in the current transaction; commit or rollback before reusing it')
    return transaction


def release_key(client, record):
    compiled = record.get('compiled', {})
    compiled.pop('parameters', None)
    compiled.get('draft', {}).pop('encryption_key', None)
    timer = getattr(client, '_attachment_key_timers', {}).pop(record['review_id'], None)
    if timer is not None:
        timer.cancel()


def release_session_keys(client, scope):
    for record in client._attachment_reviews.values():
        if record['session_scope_id'] == scope and record.get('key_bound'):
            release_key(client, record)
            if record['state'] == 'reviewed':
                record.update(state='credential_unavailable', native_dispatched=False, native_acknowledged=False)


def expire_key(reference, identity):
    client = reference()
    if client is None:
        return
    with client._lock:
        record = client._attachment_reviews.get(identity)
        if record is not None:
            release_key(client, record)
            if record['state'] == 'reviewed':
                record.update(state='credential_expired', native_dispatched=False, native_acknowledged=False)


def retain_key_until_deadline(client, record):
    if record.get('key_bound'):
        if not hasattr(client, '_attachment_key_timers'):
            client._attachment_key_timers = {}
        timer = threading.Timer(max(0, record['deadline'] - time.monotonic()),
            expire_key, args=(weakref.ref(client), record['review_id']))
        timer.daemon = True
        client._attachment_key_timers[record['review_id']] = timer
        timer.start()


def compile_operation(route, draft, origin, before):
    if not isinstance(draft, dict) or draft.get('action') not in {'attach', 'detach'}:
        raise ValueError('Select native ATTACH or DETACH')
    attaching = draft['action'] == 'attach'
    allowed = {'action', 'alias', 'path', 'read_only', 'conflict', 'create_if_missing', 'storage_options', 'encryption_key', 'encryption_cipher'} if attaching else {'action', 'alias', 'if_exists'}
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
    parameters = ()
    if attaching:
        read_only = draft.get('read_only', True);create = draft.get('create_if_missing', False)
        conflict = draft.get('conflict', 'ERROR')
        if type(read_only) is not bool or type(create) is not bool or conflict not in {'ERROR', 'IGNORE', 'REPLACE'}:
            raise ValueError('Select exact native access, creation and conflict options')
        if create and read_only or route.get('read_only') is True and not read_only:
            raise ValueError('Native file creation and writable attachment require writable authorization')
        memory = draft.get('path') == ':memory:'
        options = storage_options(draft, memory)
        if 'encryption_key' in draft:
            key = draft['encryption_key']
            if memory or not isinstance(key, str) or not key or '\x00' in key or len(key.encode()) > 65536:
                raise ValueError('File encryption requires a nonempty bounded text key')
            options.append('ENCRYPTION_KEY ?')
            parameters = (key,)
        if 'encryption_cipher' in draft:
            cipher = draft['encryption_cipher']
            if not parameters or not isinstance(cipher, str) or cipher not in {'GCM', 'CTR'}:
                raise ValueError('Select native GCM or CTR with a bound encryption key')
            options.append("ENCRYPTION_CIPHER '" + cipher + "'")
        if memory and (read_only or route.get('allow_memory') is not True):
            raise ValueError('In-memory attachment requires registered memory authorization and writable access')
        if target is not None and conflict == 'IGNORE':
            value = draft.get('path')
            if not isinstance(value, str) or (not memory and not os.path.isabs(value)) or '\x00' in value:
                raise ValueError('Select an absolute native attachment path')
            identity = {'path': ':memory:' if memory else contained_database({**route, 'database': value}), 'ignored': True}
        else:
            identity = file_identity(route, draft.get('path'), create=create)
        primary = contained_database(route)
        if not memory and not identity.get('ignored') and (identity['path'] == primary or any(
                row['path'] == identity['path'] and row['name'] == origin[0] for row in before)):
            raise ValueError('The registered primary file cannot be reattached through another alias')
        if target is not None and conflict == 'ERROR':
            raise ValueError('The exact native catalog alias is already attached')
        prefix = 'ATTACH ' + ('IF NOT EXISTS ' if conflict == 'IGNORE' else 'OR REPLACE ' if conflict == 'REPLACE' else '')
        source = prefix + "'" + identity['path'].replace("'", "''") + "' AS " + quote(alias)
        source += ' (' + ', '.join(['READ_ONLY' if read_only else 'READ_WRITE', *options]) + ')'
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
    return {'source': source, 'draft': deepcopy(draft), 'file_identity': identity, 'alias': alias, 'parameters': parameters}


def action(client, handle, route, request):
    if not isinstance(request, dict):
        raise ValueError('Select a native attachment operation')
    operation = request.get('operation')
    allowed = {'operation', 'draft'} if operation == 'review' else {'operation', 'review_id', 'review_digest', 'confirmation', 'confirmed'} if operation == 'apply' else {'operation', 'review_id', 'review_digest'} if operation == 'discard' else {'operation', 'review_id'} if operation == 'receipt' else {'operation'}
    if operation not in {'inventory', 'review', 'apply', 'receipt', 'discard'} or set(request) - allowed:
        raise ValueError('Unknown native attachment workflow request')
    context = client._attachment_contexts.get(id(handle))
    if not context or context['route'] != route:
        raise ValueError('The retained DuckDB session belongs to another or changed registration')
    scope = context['session_scope_id'];now = time.monotonic()
    def public(record):
        return deepcopy({key: value for key, value in record.items() if key not in {'compiled', 'baseline', 'deadline'}})
    if operation == 'discard':
        record = client._attachment_reviews.get(request.get('review_id'))
        if not record or record['session_scope_id'] != scope or request.get('review_digest') != record['review_digest']:
            raise ValueError('The attachment review belongs to another or closed native session')
        release_key(client, record)
        if record['state'] == 'reviewed':
            record.update(state='discarded', native_dispatched=False, native_acknowledged=False)
        return public(record)
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
                release_key(client, old)
                del client._attachment_reviews[key]
        if len(client._attachment_reviews) >= 256:
            raise ValueError('Close old attachment reviews before creating another')
        compiled = compile_operation(route, request.get('draft'), origin, before)
        alias_reuse(context, handle, compiled)
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed', 'session_scope_id': scope,
            'deadline': now + 300, 'compiled': compiled, 'baseline': before,
            'source': compiled['source'], 'alias': compiled['alias'],
            'action': compiled['draft']['action'], 'file_identity': compiled['file_identity'],
            'key_bound': bool(compiled['parameters']),
            'encryption_cipher_requested': compiled['draft'].get('encryption_cipher'),
            'automatic_retry': False, 'caller_transaction_decision_requested': False,
            'warnings': ['Changes use the original native session. Attached catalogs can be visible to other connections sharing its DuckDB instance.',
                'Storage options follow native file creation/open rules. Existing file headers can retain their prior storage format; supplied options do not rewrite a file.',
                'ATTACH follows its native transaction. Rollback does not restore a detached catalog or remove a file created by ATTACH.',
                'Registered automatic attachments can be restored when another connection opens. External file/instance changes are not fenced.']}
        # A public review fingerprint must not be derived from a private key.
        record['review_digest'] = hashlib.sha256(json.dumps(public(record), sort_keys=True).encode()).hexdigest()
        client._attachment_reviews[record['review_id']] = record
        retain_key_until_deadline(client, record)
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
        transaction = alias_reuse(context, handle, rebuilt)
    except (ValueError, RelationalClientError):
        record.update(state='refused', native_dispatched=False, native_acknowledged=False,
            reason='Native attachment namespace or file changed since review')
        release_key(client, record)
        return public(record)
    if rebuilt != record['compiled'] or before != record['baseline']:
        record.update(state='refused', native_dispatched=False, native_acknowledged=False,
            reason='Native attachment namespace or file changed since review')
        release_key(client, record)
        return public(record)
    if record['deadline'] < time.monotonic():
        release_key(client, record)
        record.update(state='credential_expired' if record.get('key_bound') else 'expired',
            native_dispatched=False, native_acknowledged=False)
        return public(record)
    record.update(state='unknown_outcome', native_dispatched=True, native_acknowledged=False,
        native_catalog_or_file_effects_possible=True)
    try:client.publish_receipt(handle,'attachments',public(record))
    except Exception:
        release_key(client,record)
        record.update(state='refused',native_dispatched=False,native_catalog_or_file_effects_possible=False,
            reason='Durable native dispatch receipt could not be recorded')
        raise
    try:
        handle.execute(record['source'], record['compiled'].get('parameters') or ())
        handle.fetchall()
        record['native_acknowledged'] = True
        client.publish_receipt(handle,'attachments',public(record))
        after = catalogs(handle)
        selected = next((row for row in after if row['name'] == record['alias']), None)
        if record['action'] == 'detach':
            verified = selected is None
            if verified and any(identifier_key(row['name']) == identifier_key(record['alias']) for row in before):
                context['detached_aliases'][identifier_key(record['alias'])] = transaction
        else:
            old = next((row for row in before if row['name'] == record['alias']), None)
            if record['compiled']['draft'].get('conflict') == 'IGNORE' and old is not None:
                verified = selected == old
            else:
                expected = record['compiled']['file_identity']['path']
                memory = record['compiled']['file_identity'].get('memory', False)
                verified = selected is not None and (selected['path'] is None if memory else selected['path'] == expected) and selected['read_only'] == record['compiled']['draft'].get('read_only', True)
                if verified:
                    prior = record['compiled']['file_identity']
                    if not memory:
                        record['observed_file_identity'] = file_identity(route, expected)
                        verified = not prior['exists'] or all(prior[key] == record['observed_file_identity'][key] for key in ('device', 'inode'))
                    requested = record['compiled']['draft'].get('storage_options', {})
                    verified = verified and all(str(selected['options'].get(key)).lower() == str(value).lower() for key, value in requested.items())
                    if record.get('key_bound'):
                        verified = verified and selected['encrypted'] is True
                        cipher = record.get('encryption_cipher_requested')
                        if cipher and not prior.get('exists', False):
                            verified = verified and selected['cipher'] == cipher
                    storage = handle.execute(
                        'SELECT database_name,block_size,total_blocks,used_blocks,free_blocks FROM pragma_database_size() WHERE database_name=?',
                        [selected['name']]).fetchone()
                    record['native_storage'] = dict(zip(('catalog', 'block_size', 'total_blocks', 'used_blocks', 'free_blocks'),
                        (storage[0], *(str(value) for value in storage[1:])))) if storage else None
        client._observe(handle, blocked=not verified)
        record.update(state='acknowledged', native_catalogs=after, rediscovery_verified=verified)
    except Exception as error:
        from .driver import uncertain
        import duckdb
        if record.get('key_bound') and isinstance(error, duckdb.InvalidInputException) and 'STRING -> BLOB conversion' in str(error):
            record['refusal_code'] = 'native-key-encoding'
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
    finally:
        release_key(client, record)
    record['session_reuse_blocked'] = bool(client._states[id(handle)].get('session_reuse_blocked'))
    return public(record)
