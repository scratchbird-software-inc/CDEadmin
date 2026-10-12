"""Native prepare-only plans, preserving charset and truncation receipts."""
import ctypes
import hashlib
import weakref

from ...sdk.relational import RelationalClientError
from .query_dialect import requested_dialect

MAX_SOURCE_BYTES = 1024 * 1024
PLAN_BUFFER_BYTES = 65539


def validate_source(source):
    if not isinstance(source, str) or not source.strip() or '\0' in source:
        raise RelationalClientError(
            'Plan source must be nonempty text without NUL')
    try:
        size = len(source.encode('utf8'))
    except UnicodeEncodeError:
        raise RelationalClientError(
            'Plan source must be valid UTF-8') from None
    if size > MAX_SOURCE_BYTES:
        raise RelationalClientError('Plan source exceeds 1 MiB UTF-8')


def decode_info(raw, item, encoding):
    """One native plan item followed by its explicit completeness marker."""
    text = None
    if not raw:
        raise RelationalClientError('Empty native plan response')
    marker = raw[0]
    if marker == item:
        if len(raw) < 4:
            raise RelationalClientError('Incomplete native plan header')
        length = int.from_bytes(raw[1:3], 'little')
        end = 3 + length
        if end >= len(raw):
            raise RelationalClientError('Invalid native plan item length')
        try:
            text = raw[3:end].decode(encoding)
        except (UnicodeError, LookupError):
            raise RelationalClientError(
                'Native plan text could not be decoded with the '
                'attachment encoding') from None
        marker = raw[end]
    if marker not in (1, 2):  # isc_info_end / isc_info_truncated
        raise RelationalClientError('Invalid native plan completion marker')
    return {'text': text, 'truncated': marker == 2,
            'complete': marker == 1, 'supplied': text is not None}


def read_plan(statement, item, encoding, *, buffer_size=PLAN_BUFFER_BYTES):
    if not 4 <= buffer_size <= PLAN_BUFFER_BYTES:
        raise RelationalClientError('Invalid native plan buffer size')
    buffer = ctypes.create_string_buffer(buffer_size)
    statement.get_info(bytes([item]), buffer)
    return decode_info(buffer.raw, item, encoding)


class PreparedPlan:
    """Explicit ownership, also visible to native attachment cleanup."""

    def __init__(self, connection):
        self.statement = None
        self.metadata = []
        connection._statements.append(weakref.ref(
            self, connection._Connection__stmt_deleted))

    def count(self, metadata):
        self.metadata.append(metadata)
        count = metadata.get_count()
        metadata.release()
        self.metadata.remove(metadata)
        return count

    def parameters(self, metadata):
        self.metadata.append(metadata)
        count = metadata.get_count()
        descriptors = []
        if count <= 512:
            for position in range(count):
                kind = metadata.get_type(position)
                descriptors.append({'position': position, 'native_type': kind.name,
                    'type_code': int(kind), 'field': metadata.get_field(position),
                    'relation': metadata.get_relation(position),
                    'subtype': metadata.get_subtype(position),
                    'length': metadata.get_length(position), 'scale': metadata.get_scale(position),
                    'charset': metadata.get_charset(position), 'nullable': bool(metadata.is_nullable(position))})
        metadata.release()
        self.metadata.remove(metadata)
        return count, descriptors

    def free(self):
        while self.metadata:
            self.metadata[-1].release()
            self.metadata.pop()
        if self.statement is not None:
            self.statement.free()
            self.statement = None

    close = free


def acquire(client, handle, request, state):
    validate_source(request.get('source'))
    dialect = requested_dialect(request) or handle.sql_dialect
    active = handle.main_transaction.is_active()
    owner = PreparedPlan(handle)
    try:
        if not active:
            handle.main_transaction.begin()
        owner.statement = handle._att.prepare(
            handle.main_transaction._tra, request['source'], dialect)
        statement = owner.statement
        encoding = getattr(handle._att, 'encoding', None)
        if not isinstance(encoding, str):
            encoding = handle._encoding
        parameter_count, parameters = owner.parameters(statement.get_input_metadata())
        native = {
            'source_sha256': hashlib.sha256(request['source'].encode('utf-8')).hexdigest(),
            'parameters': parameters, 'parameters_complete': len(parameters) == parameter_count,
            'statement_type': statement.get_type().name,
            'parameter_count': parameter_count,
            'column_count': owner.count(statement.get_output_metadata()),
            'legacy': read_plan(statement, 22, encoding),
            'detailed': read_plan(statement, 26, encoding),
            'client_sql_dialect': dialect,
            'transaction_was_active': active,
            'transaction_started': not active,
            'transaction_action_requested': False,
            'statement_execution_requested': False,
            'parameter_binding_requested': False,
            'sql_rewritten': False,
        }
    except Exception:
        try:
            handle.ping()
        except Exception:
            state.attachment_liveness_failed = True
        raise
    finally:
        try:
            owner.close()
        except BaseException:
            with state.lock:
                state.result_cleanup_failed = True
                state.failed_cursors.append(owner)
            raise
    return {
        'result_kind': client.config.profile.result_kind,
        'schema': {'columns': [
            {'name': 'Format', 'native_type': 'VARCHAR'},
            {'name': 'Plan', 'native_type': 'VARCHAR'},
            {'name': 'Truncated', 'native_type': 'BOOLEAN'}]},
        'complete': True, 'stream_reference': None,
        'payload': {'rows': [[name, native[name]['text'],
                              native[name]['truncated']]
                             for name in ('legacy', 'detailed')],
                    'rowcount': 2, 'execution_state': 'succeeded',
                    'query_plan': native},
    }
