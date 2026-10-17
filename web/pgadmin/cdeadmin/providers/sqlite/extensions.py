"""Reviewed, session-local loading of operator-approved native libraries."""
import copy
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import tempfile
import uuid

from ...sdk import RelationalClientError

MAX_LIBRARY_BYTES = 128 * 1024 * 1024


def approved(manifest):
    if not manifest:
        return {}
    path = Path(manifest)
    if not path.is_absolute() or path.stat().st_size > 256 * 1024:
        raise ValueError('Invalid operator SQLite extension manifest')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or set(value) != {'format', 'extensions'} or value['format'] != 'scratchrobin.sqlite.extensions@1':
        raise ValueError('Invalid operator SQLite extension manifest')
    entries = value['extensions']
    if not isinstance(entries, list) or len(entries) > 128:
        raise ValueError('Invalid approved extension inventory')
    result = {}
    for entry in entries:
        if not isinstance(entry, dict) or not {'id', 'path', 'sha256'} <= set(entry) or set(entry) - {'id', 'path', 'sha256', 'entrypoint'}:
            raise ValueError('Invalid approved native library')
        identity, filename, digest = entry['id'], entry['path'], entry['sha256']
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', identity) or identity in result:
            raise ValueError('Invalid or duplicate extension identity')
        if not isinstance(filename, str) or not Path(filename).is_absolute() or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('Approved library requires an absolute host path and SHA-256')
        if 'entrypoint' in entry and (not isinstance(entry['entrypoint'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,255}', entry['entrypoint'])):
            raise ValueError('Invalid native extension entry point')
        result[identity] = dict(entry)
    return result


def public(entry):
    return {key: value for key, value in entry.items() if key != 'path'}


def library(entry, destination=None):
    path = Path(entry['path'])
    digest = hashlib.sha256()
    total = 0
    with path.open('rb') as source:
        if not path.is_file():
            raise ValueError('Approved extension is not a regular file')
        while block := source.read(1024 * 1024):
            total += len(block)
            if total > MAX_LIBRARY_BYTES:
                raise ValueError('Approved extension exceeds the native library size limit')
            digest.update(block)
            if destination is not None:
                destination.write(block)
    if not total or digest.hexdigest() != entry['sha256']:
        raise ValueError('Approved native library changed; loading was not dispatched')
    return total


def capabilities(connection):
    return bool(callable(getattr(connection, 'load_extension', None)) and
                callable(getattr(connection, 'setconfig', None)) and
                hasattr(sqlite3, 'SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION'))


def observe(connection):
    # Fixed PRAGMAs do not run user functions or settle an application transaction.
    return {name: [list(row) for row in connection.execute('PRAGMA ' + name)]
            for name in ('module_list', 'function_list', 'collation_list')}


def action(client, connection, request, manifest):
    if not isinstance(request, dict) or not {'operation'} <= set(request) or set(request) - {'operation', 'extension_id', 'review_id', 'confirmed'}:
        raise ValueError('Invalid SQLite extension request')
    operation = request['operation']
    reviews = getattr(connection, '_cdeadmin_extension_reviews', None)
    if reviews is None:
        reviews = connection._cdeadmin_extension_reviews = {}
    if operation in {'receipt', 'load'}:
        review = reviews.get(request.get('review_id'))
        if review is None:
            raise ValueError('Extension review belongs to another or closed session')
        if operation == 'receipt' or review['state'] != 'reviewed':
            return copy.deepcopy(review)
    entries = approved(manifest)
    if operation == 'inventory':
        return {'extensions': [public(entry) for entry in entries.values()],
                'loader_available': capabilities(connection), 'execution_host': platform.node(),
                'scope': 'this retained connection; native process-wide effects may survive its closure',
                'native': observe(connection)}
    if operation not in {'review', 'load'}:
        raise ValueError('Unknown SQLite extension operation')
    if not capabilities(connection):
        raise ValueError('CPython SQLite extension loading API is unavailable; rebuild the native interpreter')
    if connection.in_transaction:
        raise ValueError('Finish pending transaction work before reviewing or loading a native library')
    if operation == 'review':
        entry = entries.get(request.get('extension_id'))
        if entry is None:
            raise ValueError('Native library is not approved by this application operator')
        if len(reviews) >= 16:
            raise ValueError('Extension review limit reached; close this session')
        size = library(entry)
        review = {'review_id': str(uuid.uuid4()), 'state': 'reviewed', 'extension': public(entry),
                  'bytes': size, 'execution_host': platform.node(), 'native_sqlite_version': sqlite3.sqlite_version,
                  'scope': 'session-local native code; extension initialization can have irreversible effects',
                  'dependency_scope': 'native dependencies resolve through the application host loader; operator approval includes those dependencies',
                  'automatic_reload': False, 'retry_allowed': False}
        reviews[review['review_id']] = review
        return copy.deepcopy(review)
    if request.get('confirmed') is not True:
        raise ValueError('Confirm the reviewed native library load')
    entry = entries.get(review['extension']['id'])
    if entry is None or public(entry) != review['extension']:
        raise ValueError('Operator approval changed; loading was not dispatched')
    before = observe(connection)
    # Stage the exact verified bytes under a private name. Replacing the source
    # after verification cannot substitute a different library for this dispatch.
    directory = tempfile.mkdtemp(prefix='scratchrobin-sqlite-extension-')
    staged = Path(directory) / Path(entry['path']).name
    try:
        with staged.open('xb') as target:
            library(entry, target)
        staged.chmod(0o500)
    except BaseException:
        shutil.rmtree(directory)
        raise
    connection._cdeadmin_extension_directories.append(directory)
    review['state'] = 'dispatching'
    try:
        # This C API flag leaves the SQL load_extension() function disabled.
        connection.enable_load_extension(False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, True)
        connection.load_extension(str(staged), **({'entrypoint': entry['entrypoint']} if 'entrypoint' in entry else {}))
        review['state'] = 'loaded'
    except BaseException as error:
        review.update(state='unknown_outcome', native_error_type=type(error).__name__,
                      outcome='Native initialization may have partially registered code or changed data. Close this session; do not retry.')
        client._uncertain.add(id(connection))
    finally:
        try:
            connection.enable_load_extension(False)
            if connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION):
                raise RuntimeError('Native loader remains enabled')
        except BaseException:
            review.update(state='unknown_outcome', loader_cleanup_confirmed=False)
            client._uncertain.add(id(connection))
        else:
            review['loader_cleanup_confirmed'] = True
    if review['state'] == 'loaded':
        try:
            after = observe(connection)
            review['native_additions'] = {key: [row for row in rows if row not in before[key]] for key, rows in after.items()}
        except Exception:
            review['native_observation_available'] = False
    return copy.deepcopy(review)
