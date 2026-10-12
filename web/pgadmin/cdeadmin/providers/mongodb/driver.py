"""Worker-owned MongoDB sessions and untruncated native BSON streams."""
import json

from .client import MongoDBClient, MongoDBClientError
from ..native_distributed import NativeResult
from ..retained_native import RetainedNativeClient


class MongoDBDriverBackend(MongoDBClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending_cursors = []

    def iterate(self, handle, command, parameters):
        if parameters:
            raise MongoDBClientError('MongoDB parameters belong in Query JSON')
        if not isinstance(command, dict):
            raise MongoDBClientError('MongoDB query must be an object')
        query = self._from_extended_json(command)
        operation = query.get('operation')
        database = handle.client[query.get(
            'database', handle.default_database)]
        collection = database[query['collection']] if query.get(
            'collection') else None
        options = dict(query.get('options') or {})
        if 'session' in options:
            raise MongoDBClientError('MongoDB session is provider-owned')
        options['session'] = handle.driver_session
        cursor, values = None, None
        live = operation == 'watch'
        limits = [query[k] for k in ('limit', 'max_documents')
                  if query.get(k) is not None]
        if any(type(value) is not int or value < 1 for value in limits):
            raise MongoDBClientError('MongoDB limits must be positive')
        limit = min(limits) if limits else None
        batch_size = query.get('batch_size', 256)
        if type(batch_size) is not int or not 1 <= batch_size <= 500:
            raise MongoDBClientError('MongoDB batch_size must be 1 to 500')
        try:
            if operation == 'find':
                cursor = collection.find(query.get('filter', {}),
                                         query.get('projection'), **options)
                if query.get('sort') is not None:
                    cursor = cursor.sort(query['sort'])
                if query.get('skip') is not None:
                    cursor = cursor.skip(query['skip'])
                if limit is not None:
                    cursor = cursor.limit(limit)
                cursor = cursor.batch_size(batch_size)
            elif operation == 'aggregate':
                options.setdefault('batchSize', batch_size)
                cursor = collection.aggregate(query.get('pipeline', []),
                                              **options)
            elif live:
                for name in ('resume_after', 'start_after',
                             'start_at_operation_time', 'full_document',
                             'full_document_before_change',
                             'show_expanded_events', 'max_await_time_ms'):
                    if name in query:
                        options[name] = query[name]
                options.setdefault('max_await_time_ms', 1000)
                options.setdefault('batch_size', batch_size)
                cursor = collection.watch(query.get('pipeline', []), **options)
            elif operation == 'command':
                native = query.get('command')
                reserved = {
                    'lsid', 'txnNumber', 'autocommit', 'startTransaction',
                    'commitTransaction', 'abortTransaction', 'endSessions'}
                if (not isinstance(native, dict) or not native or
                        set(native) & reserved):
                    raise MongoDBClientError(
                        'MongoDB command identity invalid')
                values = [database.command(native, **options)]
            else:
                callbacks = {
                    'insert_one': ('document',),
                    'insert_many': ('documents',),
                    'update_one': ('filter', 'update'),
                    'update_many': ('filter', 'update'),
                    'replace_one': ('filter', 'replacement'),
                    'delete_one': ('filter',), 'delete_many': ('filter',),
                    'find_one_and_update': ('filter', 'update'),
                    'find_one_and_replace': ('filter', 'replacement'),
                    'find_one_and_delete': ('filter',),
                }
                if operation not in callbacks or collection is None:
                    raise MongoDBClientError('MongoDB operation unavailable')
                value = getattr(collection, operation)(
                    *(query[name] for name in callbacks[operation]), **options)
                if operation.startswith('find_one'):
                    values = [value]
                else:
                    reply = {'acknowledged': value.acknowledged}
                    if value.acknowledged:
                        for name in ('inserted_id', 'inserted_ids',
                                     'matched_count', 'modified_count',
                                     'deleted_count', 'upserted_id'):
                            if hasattr(value, name):
                                reply[name] = getattr(value, name)
                    values = [reply]
            iterator = iter(values) if values is not None else iter(cursor)
            offset, page, size = 0, [], 0
            while limit is None or offset + len(page) < limit:
                if live:
                    item = cursor.try_next()
                    if item is None:
                        yield self._page(page, operation, offset, cursor)
                        offset += len(page)
                        page, size = [], 0
                        continue
                else:
                    try:
                        item = next(iterator)
                    except StopIteration:
                        break
                item = self._extended_json(item)
                if live:
                    yield self._page([item], operation, offset, cursor)
                    offset += 1
                    continue
                length = len(json.dumps(item).encode())
                if page and (len(page) >= min(batch_size, 256) or
                             size + length > 1048576):
                    yield self._page(page, operation, offset, cursor)
                    offset += len(page)
                    page, size = [], 0
                page.append(item)
                size += length
            if page:
                yield self._page(page, operation, offset, cursor)
        finally:
            if cursor is not None:
                self._pending_cursors.append(cursor)
                cursor.close()
                self._pending_cursors.remove(cursor)

    def _page(self, rows, operation, offset, cursor):
        token = getattr(cursor, 'resume_token', None)
        return NativeResult('document', 'documents', rows,
                            {'encoding': 'mongodb-canonical-extended-json'},
                            {'operation': operation, 'row_offset': offset,
                             'resume_token': self._extended_json(token)})

    def close_session(self, handle, _unknown=False):
        # Preserve the owner on cleanup failure so the caller can retry close.
        handle.driver_session.end_session()
        handle.client.close()
        handle.closed = True
        if handle in self._sessions:
            self._sessions.remove(handle)
        if handle.client in self._clients:
            self._clients.remove(handle.client)

    def close(self):
        for cursor in list(self._pending_cursors):
            cursor.close()
            self._pending_cursors.remove(cursor)
        for handle in list(self._sessions):
            self.close_session(handle, True)
        super().close()


class MongoDBDriver(RetainedNativeClient):
    transaction_actions = ('begin', 'commit', 'rollback')

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def inspect_resource(self, request):
        return self.backend.inspect_resource(request)

    def describe_result(self, token):
        result = super().describe_result(token)
        native = result['payload'].get('native', {})
        result['payload'].update(native)
        return result

    def describe_transaction(self, session):
        with session.lock:
            if session.active is None and not session.blocked:
                session.observation = session.worker.submit(
                    self.backend.describe_transaction, session.handle).result()
            return super().describe_transaction(session)
