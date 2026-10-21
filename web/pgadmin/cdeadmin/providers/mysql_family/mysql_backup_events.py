"""Request-scoped backup bookkeeping, separate from native dump finality."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
from pathlib import Path

from ...sdk.relational import RelationalClientError
from .mysql_clone import rows

_sink = ContextVar('mysql_backup_dependency_sink', default=None)


def document(path, expected):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Ambiguous native backup metadata')
            result[key] = value
        return result
    with path.open('rb') as stream:
        data = stream.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
        raise RelationalClientError('Native backup metadata differs from the acknowledged artifact manifest')
    value = json.loads(data, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise RelationalClientError('Native backup metadata is not an object')
    return value


@contextmanager
def observe(sink):
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


@contextmanager
def track(client, route, path, options):
    sink = _sink.get()
    if sink is None or options.get('dry_run'):
        yield None
        return
    connection = client._connect({'route': {**route, 'database': None, 'autocommit': True}})
    try:
        observed = rows(connection, 'SELECT VERSION() AS version,@@server_uuid AS server_uuid,'
            'CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role')[0]
        if observed['version'].split('-')[0] != '9.7.0':
            raise RelationalClientError('Native backup protection requires MySQL9.7.0')
    finally:
        client._forget_and_close(connection)
    ticket = sink.begin(observed, str(route['database']), str(Path(path).resolve()), options)
    try:
        yield ticket
    except BaseException:
        # A bookkeeping failure cannot replace the original native exception.
        # The already durable pending intent continues protecting archives.
        try:
            ticket.unconfirmed()
        except Exception:
            pass
        raise


def completed(ticket, result):
    if ticket is None:
        return result
    try:
        files = {row['path']: row['sha256'] for row in result['artifact_manifest']}
        top = document(Path(result['artifact_path']) / '@.json', files['@.json'])
        done = document(Path(result['artifact_path']) / '@.done.json', files['@.done.json'])
        registration = ticket.completed(top, done, result)
    except Exception as error:
        try:
            ticket.update(state='protection_unconfirmed', native_dump_completion_acknowledged=True)
        except Exception:
            pass
        registration = {'backup_id': ticket.backup_id, 'state': 'pending_or_unconfirmed',
                        'error_type': type(error).__name__, 'automatic_retry': False,
                        'native_backup_acknowledgement_unchanged': True}
    return {**result, 'archive_backup_protection': registration}
