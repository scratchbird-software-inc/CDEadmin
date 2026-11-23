"""One-use local, remote (httpfs), and foreign scanner attachment reviews (DU-AUD-06)."""
from copy import deepcopy
import hashlib
import json
import os
import re
import stat
import threading
import time
import uuid
from urllib.parse import urlsplit
import weakref

from ...sdk import RelationalClientError
from ..embedded_route import contained_database

QUERY = (
    'SELECT database_name,database_oid,path,type,readonly,options,encrypted,cipher '
    'FROM duckdb_databases() WHERE NOT internal ORDER BY database_name'
)

FOREIGN_SCANNER_EXTENSIONS = {
    'sqlite': 'sqlite_scanner',
    'postgres': 'postgres_scanner',
    'mysql': 'mysql_scanner',
}

SAFE_DSN_KEYS = frozenset({'host', 'port', 'dbname', 'database', 'user', 'sslmode', 'connect_timeout', 'socket'})


def catalogs(connection):
    from .catalog import database_location
    keys = ('name', 'oid', 'path', 'type', 'read_only', 'options', 'encrypted', 'cipher')
    rows = [dict(zip(keys, row)) for row in connection.execute(QUERY).fetchall()]
    for row in rows:
        row['oid'] = str(row['oid'])
        row.update(database_location(row['path'], row['type'], row['options']))
    return rows


def source_adapters(handle):
    """Report actual runtime availability for local, httpfs, and foreign scanner attachments."""
    ext_rows = {
        str(r[0]).lower(): {'installed': bool(r[1]), 'loaded': bool(r[2]), 'install_mode': str(r[3]), 'version': str(r[4] or '')}
        for r in handle.execute(
            'SELECT extension_name, installed, loaded, install_mode, extension_version '
            'FROM "system"."main".duckdb_extensions()'
        ).fetchall()
    }
    httpfs = ext_rows.get('httpfs', {'installed': False, 'loaded': False, 'install_mode': 'NOT_INSTALLED', 'version': ''})
    adapters = {
        'duckdb': {
            'source_type': 'duckdb',
            'available': True,
            'installed': True,
            'loaded': True,
            'extension': None,
            'read_only_only': False,
            'supports_encryption_key': True,
            'supports_memory': True,
        },
        'httpfs': {
            'source_type': 'httpfs',
            'available': httpfs['loaded'],
            'can_load_locally': httpfs['installed'] and not httpfs['loaded'],
            'installed': httpfs['installed'],
            'loaded': httpfs['loaded'],
            'extension': 'httpfs',
            'version': httpfs['version'],
            'protocols': ['http://', 'https://', 's3://'],
            'read_only_only': True,
            'secret_types': ['http', 's3'],
        },
    }
    for src_type, ext_name in FOREIGN_SCANNER_EXTENSIONS.items():
        info = ext_rows.get(ext_name, {'installed': False, 'loaded': False, 'install_mode': 'NOT_INSTALLED', 'version': ''})
        adapters[src_type] = {
            'source_type': src_type,
            'available': info['loaded'],
            'can_load_locally': info['installed'] and not info['loaded'],
            'installed': info['installed'],
            'loaded': info['loaded'],
            'extension': ext_name,
            'version': info['version'],
            'read_only_only': False,
            'requires_secret_for_credentials': src_type in {'postgres', 'mysql'},
            'unavailable_reason': (
                None if info['loaded']
                else f'Load installed {ext_name} on this session first' if info['installed']
                else f'Optional scanner extension {ext_name} is not installed in this runtime'
            ),
        }
    return adapters


def discover_foreign(handle, alias):
    """Discover schemas, relations, columns, and DDL/type limits of an attached catalog."""
    if not isinstance(alias, str) or not alias.strip():
        raise ValueError('Select an attached catalog alias to inspect')
    live = catalogs(handle)
    cat = next((row for row in live if identifier_key(row['name']) == identifier_key(alias)), None)
    if cat is None:
        raise ValueError('Selected catalog alias is not currently attached')
    cname = cat['name']
    schemas = [
        r[0] for r in handle.execute(
            'SELECT schema_name FROM "system"."main".duckdb_schemas() '
            'WHERE database_name = ? AND NOT internal ORDER BY schema_name LIMIT 1024',
            [cname],
        ).fetchall()
    ]
    tables = [
        {'schema': r[0], 'name': r[1], 'column_count': int(r[2] or 0), 'estimated_rows': r[3]}
        for r in handle.execute(
            'SELECT schema_name, table_name, column_count, estimated_size '
            'FROM "system"."main".duckdb_tables() '
            'WHERE database_name = ? AND NOT internal ORDER BY 1, 2 LIMIT 4096',
            [cname],
        ).fetchall()
    ]
    views = [
        {'schema': r[0], 'name': r[1], 'column_count': int(r[2] or 0)}
        for r in handle.execute(
            'SELECT schema_name, view_name, column_count '
            'FROM "system"."main".duckdb_views() '
            'WHERE database_name = ? AND NOT internal ORDER BY 1, 2 LIMIT 4096',
            [cname],
        ).fetchall()
    ]
    columns = [
        {'schema': r[0], 'table': r[1], 'name': r[2], 'data_type': r[3], 'nullable': bool(r[4])}
        for r in handle.execute(
            'SELECT schema_name, table_name, column_name, data_type, is_nullable '
            'FROM "system"."main".duckdb_columns() '
            'WHERE database_name = ? AND NOT internal ORDER BY 1, 2, column_index LIMIT 8192',
            [cname],
        ).fetchall()
    ]
    is_foreign = cat['type'] != 'duckdb'
    raw_path = str(cat.get('path') or '')
    is_remote = raw_path.startswith(('http://', 'https://', 's3://'))
    return {
        'catalog': cat['name'],
        'catalog_type': cat['type'],
        'read_only': bool(cat['read_only']),
        'is_foreign': is_foreign,
        'is_remote_uri': is_remote,
        'advertised_as_duckdb_server': False,
        'schemas': schemas,
        'tables': tables,
        'views': views,
        'columns': columns,
        'capabilities': {
            'duckdb_macros_supported': not is_foreign and not is_remote,
            'duckdb_sequences_supported': not is_foreign and not is_remote,
            'copy_from_database_source': True,
            'copy_from_database_destination': not bool(cat['read_only']) and not is_remote,
        },
    }


def identifier_key(value):
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
        info = os.fstat(descriptor)
        header = os.read(descriptor, 12)
        if not stat.S_ISREG(info.st_mode) or info.st_size < 12 or header[8:12] != b'DUCK':
            raise ValueError('The attachment target is not a native DuckDB file')
        return {
            'path': path, 'exists': True, 'device': str(info.st_dev), 'inode': str(info.st_ino),
            'bytes': str(info.st_size), 'modified_ns': str(info.st_mtime_ns),
        }
    finally:
        os.close(descriptor)


def sqlite_file_identity(route, value, *, create=False):
    if not isinstance(value, str) or not os.path.isabs(value) or '\x00' in value:
        raise ValueError('Select an absolute SQLite file under the registered root')
    path = contained_database({**route, 'database': value})
    if os.path.islink(value):
        raise ValueError('Attachment targets cannot be symbolic links')
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        if not create or not os.path.isdir(os.path.dirname(path)):
            raise ValueError('Select an existing SQLite file or explicitly allow creation') from None
        return {'path': path, 'exists': False, 'source_type': 'sqlite'}
    except OSError:
        raise ValueError('The SQLite attachment file is unavailable') from None
    try:
        info = os.fstat(descriptor)
        header = os.read(descriptor, 16)
        if not stat.S_ISREG(info.st_mode) or (info.st_size > 0 and header != b'SQLite format 3\x00'):
            raise ValueError('The attachment target is not a native SQLite3 file')
        return {
            'path': path, 'exists': True, 'source_type': 'sqlite',
            'device': str(info.st_dev), 'inode': str(info.st_ino),
            'bytes': str(info.st_size), 'modified_ns': str(info.st_mtime_ns),
        }
    finally:
        os.close(descriptor)


def validate_remote_uri(uri):
    if not isinstance(uri, str) or not uri.strip() or '\x00' in uri or len(uri.encode('utf-8')) > 4096:
        raise ValueError('Remote httpfs attachment requires a bounded HTTP(S) or S3 URI')
    parsed = urlsplit(uri.strip())
    if (any(ord(ch) < 32 or ord(ch) == 127 for ch in uri) or
            parsed.scheme not in {'http', 'https', 's3'} or not parsed.netloc or
            parsed.username is not None or parsed.password is not None or
            parsed.query or parsed.fragment):
        raise ValueError(
            'Remote attachment URI must use http://, https://, or s3:// without inline credentials, query, or fragment; '
            'bind credentials via a DuckDB HTTP/S3 secret'
        )
    return uri.strip(), ('s3' if parsed.scheme == 's3' else 'http')


def validate_foreign_dsn(source_type, options):
    if not isinstance(options, dict) or not options or set(options) - SAFE_DSN_KEYS:
        raise ValueError(
            f'Foreign {source_type} attachment options accept only host, port, dbname/database, user, sslmode, connect_timeout, socket '
            '(credentials must use a DuckDB SECRET, never inline passwords)'
        )
    parts = []
    for key in sorted(options):
        val = options[key]
        if key in {'port', 'connect_timeout'}:
            if type(val) is not int or not (1 <= val <= 65535):
                raise ValueError(f'Foreign {source_type} {key} must be an integer in 1..65535')
            parts.append(f'{key}={val}')
        else:
            if not isinstance(val, str) or not val or any(ch in val for ch in ("'", '\\', '\x00', '\n', '\r', ';')):
                raise ValueError(f'Foreign {source_type} {key} must be a clean scalar identifier/value')
            if 'password' in val.lower() or 'secret' in val.lower():
                raise ValueError('Inline passwords are forbidden in foreign attachment options; use secret_name')
            parts.append(f'{key}={val}')
    return ' '.join(parts)


def storage_options(draft, memory):
    value = draft.get('storage_options', {})
    if not isinstance(value, dict) or set(value) - {'block_size', 'row_group_size', 'storage_version', 'compress'}:
        raise ValueError('Select native block size, row-group size, storage version or memory compression')
    source = []
    for key in ('block_size', 'row_group_size'):
        if key in value:
            text = value[key]
            if not isinstance(text, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', text) or int(text) > 2**64 - 1:
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
        timer = threading.Timer(
            max(0, record['deadline'] - time.monotonic()),
            expire_key, args=(weakref.ref(client), record['review_id']),
        )
        timer.daemon = True
        client._attachment_key_timers[record['review_id']] = timer
        timer.start()


def compile_operation(route, draft, origin, before, *, handle=None, authorize_secret=None):
    if not isinstance(draft, dict) or draft.get('action') not in {'attach', 'detach', 'rename'}:
        raise ValueError('Select native ATTACH, DETACH or SET ALIAS')
    attaching = draft['action'] == 'attach'
    renaming = draft['action'] == 'rename'
    allowed = (
        {
            'action', 'alias', 'path', 'read_only', 'conflict', 'create_if_missing',
            'storage_options', 'encryption_key', 'encryption_cipher',
            'source_type', 'secret_name', 'expected_secret', 'foreign_options',
        }
        if attaching else {'action', 'alias', 'if_exists'}
    )
    if renaming:
        allowed = {'action', 'alias', 'new_alias', 'dependent_sql_confirmed'}
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
    source_type = draft.get('source_type', 'duckdb') if attaching else None

    if renaming:
        new_alias = draft.get('new_alias')
        if (target is None or target['type'] != 'duckdb' or not isinstance(new_alias, str)
                or not new_alias or '\x00' in new_alias or len(new_alias.encode()) > 65536
                or identifier_key(new_alias) in {'system', 'temp'}
                or any(identifier_key(row['name']) == identifier_key(new_alias) for row in before)):
            raise ValueError('Select an attached native DuckDB catalog and an unused exact new alias')
        if draft.get('dependent_sql_confirmed') is not True:
            raise ValueError('Confirm that stored/external SQL can retain the old alias and that rollback does not restore it')
        if target['path'] and str(target['path']).startswith(('http://', 'https://', 's3://')):
            identity = {'remote_uri': target['path'], 'source_type': 'httpfs'}
        else:
            identity = file_identity(route, target['path']) if target['path'] else {'path': ':memory:', 'memory': True}
        source = 'ALTER DATABASE ' + quote(alias) + ' SET ALIAS TO ' + quote(new_alias)
    elif attaching:
        if source_type not in {'duckdb', 'httpfs', 'sqlite', 'postgres', 'mysql'}:
            raise ValueError('Unsupported attachment source_type')
        read_only = draft.get('read_only', True)
        create = draft.get('create_if_missing', False)
        conflict = draft.get('conflict', 'ERROR')
        if type(read_only) is not bool or type(create) is not bool or conflict not in {'ERROR', 'IGNORE', 'REPLACE'}:
            raise ValueError('Select exact native access, creation and conflict options')
        if create and read_only or route.get('read_only') is True and not read_only:
            raise ValueError('Native file creation and writable attachment require writable authorization')
        if target is not None and conflict == 'ERROR':
            raise ValueError('The exact native catalog alias is already attached')

        if source_type == 'duckdb':
            if any(k in draft for k in ('secret_name', 'expected_secret', 'foreign_options')):
                raise ValueError('Foreign/remote secret options do not apply to local duckdb attachments')
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
            target_spec = identity['path']
            attach_opts = ['READ_ONLY' if read_only else 'READ_WRITE', *options]

        elif source_type == 'httpfs':
            if not read_only or create:
                raise ValueError('Remote httpfs attachments must be READ_ONLY with create_if_missing=false')
            if any(k in draft for k in ('storage_options', 'encryption_key', 'encryption_cipher', 'foreign_options', 'secret_name')):
                raise ValueError('Unsupported options for remote httpfs attachment')
            uri, secret_kind = validate_remote_uri(draft.get('path'))
            adapters = source_adapters(handle) if handle is not None else {}
            if handle is None or not adapters.get('httpfs', {}).get('loaded'):
                raise ValueError('Load native httpfs on this session before attaching a remote URI')
            matches = handle.execute('SELECT name, persistent, storage FROM which_secret(?, ?)', [uri, secret_kind]).fetchall()
            if len(matches) > 1:
                raise ValueError('Remote URI secret selection is ambiguous')
            selected_secret = dict(zip(('name', 'persistent', 'storage'), matches[0])) if matches else None
            expected_secret = draft.get('expected_secret')
            if expected_secret is not None:
                if not isinstance(expected_secret, str) or not expected_secret.strip():
                    raise ValueError('expected_secret must be a non-empty secret name')
                if selected_secret is None or selected_secret['name'] != expected_secret:
                    raise ValueError('Selected native HTTP/S3 secret does not match expected_secret')
            if selected_secret is not None:
                if authorize_secret is None:
                    raise RelationalClientError('Remote attachment with secret credentials requires secret-read authority')
                authorize_secret()
            identity = {
                'remote_uri': uri,
                'source_type': 'httpfs',
                'secret_kind': secret_kind,
                'selected_secret': selected_secret,
            }
            target_spec = uri
            attach_opts = ['TYPE duckdb', 'READ_ONLY']

        elif source_type == 'sqlite':
            if any(k in draft for k in ('storage_options', 'encryption_key', 'encryption_cipher', 'foreign_options', 'secret_name', 'expected_secret')):
                raise ValueError('Unsupported options for foreign sqlite attachment')
            adapters = source_adapters(handle) if handle is not None else {}
            if handle is None or not adapters.get('sqlite', {}).get('loaded'):
                reason = adapters.get('sqlite', {}).get('unavailable_reason') or 'Extension sqlite_scanner is not loaded'
                raise ValueError(reason)
            identity = sqlite_file_identity(route, draft.get('path'), create=create)
            target_spec = identity['path']
            attach_opts = ['TYPE sqlite', 'READ_ONLY' if read_only else 'READ_WRITE']

        else:
            if create or any(k in draft for k in ('storage_options', 'encryption_key', 'encryption_cipher', 'expected_secret', 'path')):
                raise ValueError(f'Foreign {source_type} attachment requires foreign_options and optional secret_name, not file paths')
            adapters = source_adapters(handle) if handle is not None else {}
            if handle is None or not adapters.get(source_type, {}).get('loaded'):
                reason = adapters.get(source_type, {}).get('unavailable_reason') or f'Extension {FOREIGN_SCANNER_EXTENSIONS[source_type]} is not loaded'
                raise ValueError(reason)
            dsn = validate_foreign_dsn(source_type, draft.get('foreign_options'))
            attach_opts = [f'TYPE {source_type}']
            sec_name = draft.get('secret_name')
            if sec_name is not None:
                if not isinstance(sec_name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', sec_name):
                    raise ValueError('Foreign attachment secret_name must be a valid DuckDB secret identifier')
                sec_exists = handle.execute(
                    'SELECT 1 FROM "system"."main".duckdb_secrets() WHERE name = ?', [sec_name]
                ).fetchone()
                if not sec_exists:
                    raise ValueError(f'DuckDB secret {sec_name!r} does not exist in this session')
                if authorize_secret is None:
                    raise RelationalClientError('Foreign attachment secret binding requires secret-read authority')
                authorize_secret()
                attach_opts.append(f'SECRET {quote(sec_name)}')
            attach_opts.append('READ_ONLY' if read_only else 'READ_WRITE')
            identity = {
                'source_type': source_type,
                'dsn_redacted': dsn,
                'secret_name': sec_name,
            }
            target_spec = dsn

        prefix = 'ATTACH ' + ('IF NOT EXISTS ' if conflict == 'IGNORE' else 'OR REPLACE ' if conflict == 'REPLACE' else '')
        source = prefix + "'" + target_spec.replace("'", "''") + "' AS " + quote(alias)
        source += ' (' + ', '.join(attach_opts) + ')'
    else:
        missing_ok = draft.get('if_exists', False)
        if type(missing_ok) is not bool or target is None and not missing_ok:
            raise ValueError('Select an attached exact alias or explicitly select IF EXISTS')
        source = 'DETACH DATABASE ' + ('IF EXISTS ' if missing_ok else '') + quote(alias)

    import duckdb
    statements = duckdb.extract_statements(source)
    expected = duckdb.StatementType.ALTER if renaming else duckdb.StatementType.ATTACH if attaching else duckdb.StatementType.DETACH
    if len(statements) != 1 or statements[0].type != expected:
        raise ValueError('Exactly one provider-built native attachment statement is required')
    return {
        'source': source,
        'draft': deepcopy(draft),
        'file_identity': identity,
        'alias': alias,
        'parameters': parameters,
    }


def action(client, handle, route, request, *, authorize_secret=None):
    if not isinstance(request, dict):
        raise ValueError('Select a native attachment operation')
    operation = request.get('operation')
    allowed = (
        {'operation', 'draft'} if operation == 'review'
        else {'operation', 'review_id', 'review_digest', 'confirmation', 'confirmed'} if operation == 'apply'
        else {'operation', 'review_id', 'review_digest'} if operation == 'discard'
        else {'operation', 'review_id'} if operation == 'receipt'
        else {'operation', 'alias'} if operation == 'discover_foreign'
        else {'operation'}
    )
    if operation not in {'inventory', 'discover_foreign', 'review', 'apply', 'receipt', 'discard'} or set(request) - allowed:
        raise ValueError('Unknown native attachment workflow request')
    context = client._attachment_contexts.get(id(handle))
    if not context or context['route'] != route:
        raise ValueError('The retained DuckDB session belongs to another or changed registration')
    scope = context['session_scope_id']
    now = time.monotonic()

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
        return {
            'session_scope_id': scope,
            'catalogs': before,
            'original_catalog': origin[0],
            'source_adapters': source_adapters(handle),
            'automatic_retry': False,
            'caller_transaction_decision_requested': False,
        }
    if operation == 'discover_foreign':
        return discover_foreign(handle, request.get('alias'))

    if operation == 'review':
        for key in list(client._attachment_reviews):
            old = client._attachment_reviews[key]
            if old['deadline'] < now or old['session_scope_id'] not in {
                    value['session_scope_id'] for value in client._attachment_contexts.values()}:
                release_key(client, old)
                del client._attachment_reviews[key]
        if len(client._attachment_reviews) >= 256:
            raise ValueError('Close old attachment reviews before creating another')
        compiled = compile_operation(
            route, request.get('draft'), origin, before,
            handle=handle, authorize_secret=authorize_secret,
        )
        alias_reuse(context, handle, compiled)
        if compiled['draft']['action'] == 'rename':
            from .catalog_alias import snapshot
            compiled['alias_snapshot'] = snapshot(handle, compiled['alias'])
        record = {
            'review_id': str(uuid.uuid4()), 'state': 'reviewed', 'session_scope_id': scope,
            'deadline': now + 300, 'compiled': compiled, 'baseline': before,
            'source': compiled['source'], 'alias': compiled['alias'],
            'action': compiled['draft']['action'],
            'source_type': compiled['draft'].get('source_type', 'duckdb') if compiled['draft']['action'] == 'attach' else None,
            'file_identity': compiled['file_identity'],
            'key_bound': bool(compiled['parameters']),
            'encryption_cipher_requested': compiled['draft'].get('encryption_cipher'),
            'automatic_retry': False, 'caller_transaction_decision_requested': False,
            'warnings': [
                'Changes use the original native session. Attached catalogs can be visible to other connections sharing its DuckDB instance.',
                'Storage options follow native file creation/open rules. Existing file headers can retain their prior storage format; supplied options do not rewrite a file.',
                'ATTACH follows its native transaction. Rollback does not restore a detached catalog or remove a file created by ATTACH.',
                'Registered automatic attachments can be restored when another connection opens. External file/instance changes are not fenced.',
            ],
        }
        if compiled['draft']['action'] == 'rename':
            record.update(new_alias=compiled['draft']['new_alias'], alias_review=deepcopy(compiled['alias_snapshot']))
            record['warnings'] += [
                'SET ALIAS changes the native namespace immediately and rollback does not restore the old alias. No physical file is renamed.',
                'Native stored SQL and external/dynamic references are not rewritten; views or macros retaining the old alias can fail. Source hashes and native dependency rows are observations, not complete reference analysis.',
                'Descendant resource IDs change. Invalidate the old IDs and refresh the complete returned identity inventory; confirm affected design bindings separately.',
            ]
        record['review_digest'] = hashlib.sha256(json.dumps(public(record), sort_keys=True).encode()).hexdigest()
        client._attachment_reviews[record['review_id']] = record
        retain_key_until_deadline(client, record)
        return public(record)

    record = client._attachment_reviews.get(request.get('review_id'))
    if not record or record['session_scope_id'] != scope or request.get('review_digest') != record['review_digest']:
        raise ValueError('The attachment review belongs to another or closed native session')
    if record['state'] != 'reviewed':
        return public(record)
    if record['deadline'] < now or request.get('confirmed') is not True or request.get('confirmation') != record['alias']:
        raise ValueError('Confirm the current reviewed native attachment alias')
    try:
        rebuilt = compile_operation(
            route, record['compiled']['draft'], origin, before,
            handle=handle, authorize_secret=authorize_secret,
        )
        transaction = alias_reuse(context, handle, rebuilt)
        if rebuilt['draft']['action'] == 'rename':
            from .catalog_alias import snapshot
            rebuilt['alias_snapshot'] = snapshot(handle, rebuilt['alias'])
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
    try:
        client.publish_receipt(handle, 'attachments', public(record))
    except Exception:
        release_key(client, record)
        record.update(state='refused', native_dispatched=False, native_catalog_or_file_effects_possible=False,
                      reason='Durable native dispatch receipt could not be recorded')
        raise
    try:
        handle.execute(record['source'], record['compiled'].get('parameters') or ())
        handle.fetchall()
        record['native_acknowledged'] = True
        client.publish_receipt(handle, 'attachments', public(record))
        after = catalogs(handle)
        selected = next((row for row in after if row['name'] == record['alias']), None)
        if record['action'] == 'rename':
            new_alias = record['compiled']['draft']['new_alias']
            renamed = next((row for row in after if row['name'] == new_alias), None)
            prior = next(row for row in before if row['name'] == record['alias'])
            verified = selected is None and renamed is not None and {**renamed, 'name': prior['name']} == prior
            from .catalog_alias import snapshot
            refreshed = snapshot(handle, new_alias)
            record.update(
                invalidate_resource_ids=[row['resource_id'] for row in record['alias_review']['descendants']],
                refreshed_descendant_identities=refreshed['descendants'],
                stored_sql_rewritten=False, physical_file_renamed=False,
                alias_restored_by_rollback=False,
            )
            if verified:
                context['detached_aliases'][identifier_key(record['alias'])] = transaction
        elif record['action'] == 'detach':
            verified = selected is None
            if verified and any(identifier_key(row['name']) == identifier_key(record['alias']) for row in before):
                context['detached_aliases'][identifier_key(record['alias'])] = transaction
        else:
            old = next((row for row in before if row['name'] == record['alias']), None)
            src_type = record['compiled']['draft'].get('source_type', 'duckdb')
            if record['compiled']['draft'].get('conflict') == 'IGNORE' and old is not None:
                verified = selected == old
            elif src_type == 'duckdb':
                expected = record['compiled']['file_identity']['path']
                memory = record['compiled']['file_identity'].get('memory', False)
                verified = (
                    selected is not None
                    and (selected['path'] is None if memory else selected['path'] == expected)
                    and selected['read_only'] == record['compiled']['draft'].get('read_only', True)
                )
                if verified:
                    prior = record['compiled']['file_identity']
                    if not memory:
                        record['observed_file_identity'] = file_identity(route, expected)
                        verified = not prior['exists'] or all(
                            prior[key] == record['observed_file_identity'][key] for key in ('device', 'inode')
                        )
                    requested = record['compiled']['draft'].get('storage_options', {})
                    verified = verified and all(
                        str(selected['options'].get(key)).lower() == str(value).lower()
                        for key, value in requested.items()
                    )
                    if record.get('key_bound'):
                        verified = verified and selected['encrypted'] is True
                        cipher = record.get('encryption_cipher_requested')
                        if cipher and not prior.get('exists', False):
                            verified = verified and selected['cipher'] == cipher
                    storage = handle.execute(
                        'SELECT database_name,block_size,total_blocks,used_blocks,free_blocks '
                        'FROM pragma_database_size() WHERE database_name=?',
                        [selected['name']],
                    ).fetchone()
                    record['native_storage'] = dict(zip(
                        ('catalog', 'block_size', 'total_blocks', 'used_blocks', 'free_blocks'),
                        (storage[0], *(str(value) for value in storage[1:])),
                    )) if storage else None
            elif src_type == 'httpfs':
                expected_uri = record['compiled']['file_identity']['remote_uri']
                verified = selected is not None and selected['path'] == expected_uri and selected['read_only'] is True
            elif src_type == 'sqlite':
                expected_path = record['compiled']['file_identity']['path']
                verified = (
                    selected is not None
                    and selected['type'] == 'sqlite'
                    and selected['path'] == expected_path
                    and selected['read_only'] == record['compiled']['draft'].get('read_only', True)
                )
                if verified:
                    record['foreign_catalog'] = discover_foreign(handle, selected['name'])
            else:
                verified = (
                    selected is not None
                    and selected['type'] == src_type
                    and selected['read_only'] == record['compiled']['draft'].get('read_only', True)
                )
                if verified:
                    record['foreign_catalog'] = discover_foreign(handle, selected['name'])
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
        record.update(
            state='acknowledged' if record['native_acknowledged'] else 'unknown_outcome' if uncertain(error) else 'refused',
            error_type=type(error).__name__, rediscovery_verified=False,
        )
    finally:
        release_key(client, record)
    record['session_reuse_blocked'] = bool(client._states[id(handle)].get('session_reuse_blocked'))
    return public(record)
