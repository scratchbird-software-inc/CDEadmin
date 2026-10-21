"""Exact MySQL text-protocol values at the query/browser boundary."""
import base64
import binascii
import codecs
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import math
import re

from mysql.connector.constants import FieldType, FieldFlag, CharacterSet

from pgadmin.cdeadmin.sdk import RelationalClientError


SAFE_INTEGER = (1 << 53) - 1
INTEGER_TYPES = frozenset({
    FieldType.TINY, FieldType.SHORT, FieldType.LONG, FieldType.INT24,
    FieldType.LONGLONG, FieldType.YEAR,
})
EXACT_TEXT_TYPES = frozenset({
    FieldType.DECIMAL, FieldType.NEWDECIMAL, FieldType.FLOAT, FieldType.DOUBLE,
    FieldType.DATE, FieldType.NEWDATE, FieldType.TIME, FieldType.TIMESTAMP,
    FieldType.DATETIME,
})
BINARY_TYPES = frozenset({FieldType.GEOMETRY, FieldType.VECTOR})
CHARSETS = CharacterSet()
CHARSETS.set_mysql_version((9, 7, 0))
CODEC_NAMES = {
    'utf8mb4': 'utf8', 'utf8mb3': 'utf8', 'ucs2': 'utf_16_be',
    'utf16': 'utf_16_be', 'utf16le': 'utf_16_le', 'utf32': 'utf_32_be',
    'latin2': 'iso8859_2', 'latin5': 'iso8859_9', 'latin7': 'iso8859_13',
    'greek': 'iso8859_7', 'hebrew': 'iso8859_8', 'koi8r': 'koi8_r',
    'koi8u': 'koi8_u', 'macce': 'mac_latin2', 'macroman': 'mac_roman',
    'ujis': 'euc_jp', 'sjis': 'shift_jis',
}
LATIN1_TRANSLATION = {
    byte: ord(bytes([byte]).decode('cp1252')) for byte in range(0x80, 0xa0)
    if byte not in {0x81, 0x8d, 0x8f, 0x90, 0x9d}
}


@lru_cache(maxsize=512)
def text_codec(charset):
    try:
        name = CHARSETS.get_info(charset)[0]
    except Exception:
        return None, None
    codec = CODEC_NAMES.get(name, name)
    if name == 'latin1':
        return name, 'mysql_latin1'
    try:
        codecs.lookup(codec)
    except LookupError:
        codec = None
    return name, codec


def decode_text(raw, charset):
    name, codec = text_codec(charset)
    if codec == 'mysql_latin1':
        # MySQL maps undefined Windows-1252 positions to their C1 controls.
        return raw.decode('latin1').translate(LATIN1_TRANSLATION)
    if codec is not None:
        return raw.decode(codec)
    return dict(binary(raw), native_charset=name, charset_id=charset)


def binary(value):
    return {'encoding': 'base64',
            'data': base64.b64encode(value).decode('ascii'),
            'byte_length': len(value)}


def value(raw, column, encoding):
    if raw is None:
        return None
    raw = bytes(raw)
    kind = column[1]
    if kind in INTEGER_TYPES or kind == FieldType.BIT:
        number = (int.from_bytes(raw, 'big') if kind == FieldType.BIT
                  else int(raw))
        return number if abs(number) <= SAFE_INTEGER else str(number)
    if kind in EXACT_TEXT_TYPES:
        return raw.decode('ascii')
    if kind == FieldType.JSON:
        return raw.decode('utf-8')
    charset = column[8] if len(column) > 8 else None
    if kind in BINARY_TYPES or charset == 63:
        return binary(raw)
    if kind in {FieldType.STRING, FieldType.VAR_STRING, FieldType.VARCHAR,
                FieldType.ENUM, FieldType.SET, FieldType.BLOB,
                FieldType.TINY_BLOB, FieldType.MEDIUM_BLOB,
                FieldType.LONG_BLOB}:
        if charset is None:
            raise RelationalClientError('MySQL text result charset is absent')
        return decode_text(raw, charset)
    raise RelationalClientError('MySQL result type is not admitted')


def columns(cursor):
    descriptions = cursor.description or ()
    labels = [str(item[0]) for item in descriptions]
    bases = [name or f'column_{i + 1}' for i, name in enumerate(labels)]
    reserved, used = set(bases), set()
    result = []
    for index, item in enumerate(descriptions):
        base = bases[index]
        name, suffix = base, 2
        while name in used:
            name = f'{base}#{suffix}'
            suffix += 1
            if name in reserved:
                name = base
        used.add(name)
        kind = item[1]
        flags = item[7] if len(item) > 7 else None
        charset = item[8] if len(item) > 8 else None
        opaque_text = (kind in {
            FieldType.STRING, FieldType.VAR_STRING, FieldType.VARCHAR,
            FieldType.ENUM, FieldType.SET, FieldType.BLOB,
            FieldType.TINY_BLOB, FieldType.MEDIUM_BLOB, FieldType.LONG_BLOB,
        } and text_codec(charset)[1] is None)
        result.append({
            'name': name, 'native_name': labels[index], 'ordinal': index,
            'native_type': FieldType.get_info(kind) or str(kind),
            'native_type_code': kind, 'native_flags': flags,
            'charset_id': charset,
            'nullable': item[6] if len(item) > 6 else None,
            'unsigned': (bool(flags & FieldFlag.UNSIGNED)
                         if flags is not None else None),
            'cell_type': ('json' if opaque_text or kind in BINARY_TYPES or (
                charset == 63 and kind not in INTEGER_TYPES and
                kind not in EXACT_TEXT_TYPES and kind not in {
                    FieldType.BIT, FieldType.JSON}) else 'text'),
            'metadata_source': 'mysql-connector-python.column-definition',
        })
    return result


def parameter(item):
    if item is None or isinstance(item, (str, bool, bytes, bytearray)):
        return item
    if type(item) is int and abs(item) <= SAFE_INTEGER:
        return item
    if type(item) is float and math.isfinite(item):
        return item
    if isinstance(item, Mapping):
        encoding, data = item.get('encoding'), item.get('data')
        if (set(item) - {'encoding', 'data', 'byte_length'} or
                not isinstance(data, str)):
            raise RelationalClientError('MySQL typed parameter is invalid')
        if encoding == 'base64':
            try:
                raw = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error):
                raise RelationalClientError(
                    'MySQL binary parameter is invalid') from None
            if 'byte_length' in item and (
                    type(item['byte_length']) is not int or
                    item['byte_length'] != len(raw)):
                raise RelationalClientError(
                    'MySQL binary parameter length does not match')
            return raw
        if set(item) != {'encoding', 'data'}:
            raise RelationalClientError('MySQL numeric parameter is invalid')
        if encoding == 'integer' and re.fullmatch(r'-?[0-9]{1,65}', data):
            return int(data)
        if encoding == 'decimal' and len(data) <= 1024:
            try:
                number = Decimal(data)
                if number.is_finite():
                    return number
            except InvalidOperation:
                pass
    raise RelationalClientError(
        'MySQL parameter requires an exact supported value or typed envelope')


def parameters(items):
    if items is None:
        return ()
    if isinstance(items, Mapping):
        if not all(isinstance(name, str) for name in items):
            raise RelationalClientError('MySQL parameter names must be text')
        return {name: parameter(item) for name, item in items.items()}
    if isinstance(items, (list, tuple)):
        return tuple(parameter(item) for item in items)
    raise RelationalClientError('MySQL parameters must be an object or array')


class MySQLParameterAdmissionError(RelationalClientError):
    """The current command was refused by native language/metadata admission."""
    commands_dispatched = 0


def observed_language(connection):
    """Read the retained native language without changing session policy."""
    from .mysql_session_variables import observe
    observed = observe(connection)
    if observed is not None:
        connection._sql_mode = observed['variables']['sql_mode']
        return observed['version'], observed['variables']['sql_mode']
    observation = connection.cursor()
    try:
        observation.execute('SELECT VERSION(), @@SESSION.sql_mode')
        version, mode = observation.fetchone()
    finally:
        observation.close()
    if isinstance(mode, bytes): mode = mode.decode('ascii')
    if isinstance(version, bytes): version = version.decode('ascii')
    # Synchronize the client's cache only. No native language setting changes.
    connection._sql_mode = mode
    return version, mode


CLIENT_DELIMITER = re.compile(r'^[ \t]*DELIMITER[ \t]+', re.I | re.M | re.A)


def framed_source(source, version, mode):
    from ...data_studio.mysql_quoting import available
    modes = set(mode.split(','))
    if CLIENT_DELIMITER.search(source):
        from ...data_studio.language_tools import analyze
        framed = analyze(source, 'mysql-sql', script=True, settings={
            'ansi_quotes':'ANSI_QUOTES' in modes, 'no_backslash_escapes':'NO_BACKSLASH_ESCAPES' in modes,
            'mysql_dollar_quotes':available(version)})
        if framed['client_directives']:
            if not framed['script_ready']:
                raise MySQLParameterAdmissionError('MySQL client script framing is unconfirmed before query dispatch')
            source = ';\n'.join(item['source'] for item in framed['statements'])
    return source


def unbound_source(connection, source):
    if CLIENT_DELIMITER.search(source):
        source = framed_source(source, *observed_language(connection))
    try: return source.encode(connection.python_charset)
    except (UnicodeError, LookupError):
        raise MySQLParameterAdmissionError('MySQL command encoding failed before dispatch') from None


def bound_source(connection, cursor, source, params):
    """Bind only lexical markers, using the selected driver's native literals."""
    from ...data_studio.mysql_quoting import available, parameter_spans
    version, mode = observed_language(connection)
    source = framed_source(source, version, mode)
    modes = set(mode.split(','))
    spans = list(parameter_spans(source, modes, dollar_quotes=available(version)))
    named = isinstance(params, Mapping)
    if ((named and any(name is None or name not in params for _start, _end, name in spans)) or
            (not named and (not isinstance(params, (list, tuple)) or len(params) != len(spans) or
                            any(name is not None for _start, _end, name in spans)))):
        raise MySQLParameterAdmissionError('MySQL parameter bindings do not match the native source markers')
    try:
        # This lexical port bypasses native cursor.execute(), including the
        # charset adapter used there. Keep both entry points on the same exact
        # MySQL latin1 mapping before asking the driver to escape its values.
        from .mysql_charsets import parameter_values
        native_params = parameter_values(dict(params) if named else params,
                                         connection.charset)
        previous_mode = getattr(connection, '_cdeadmin_parameter_sql_mode', None)
        connection._cdeadmin_parameter_sql_mode = mode
        try:
            if getattr(connection, '_cmysql', None) is not None:
                from mysql.connector.constants import ServerFlag
                from .mysql_session_variables import SessionVariables, SourceIdentityUnavailable
                observer = getattr(connection, '_cdeadmin_session_variable_observer', None)
                separate = False
                if isinstance(observer, SessionVariables):
                    native_no_backslash = bool(connection._cmysql.st_server_status() & ServerFlag.STATUS_NO_BACKSLASH_ESCAPES)
                    if native_no_backslash != ('NO_BACKSLASH_ESCAPES' in modes):
                        try:
                            converted = observer.native_literals(native_params, mode)
                        except Exception as error:
                            failure = MySQLParameterAdmissionError('Private native C parameter conversion is unavailable; the user command was not dispatched')
                            failure.original_session_identity_unconfirmed = isinstance(error, SourceIdentityUnavailable)
                            failure.original_diagnostics_preserved = not failure.original_session_identity_unconfirmed
                            failure.native_observer_errno = getattr(error, 'errno', None)
                            failure.native_observer_error_type = type(error).__name__
                            raise failure from None
                        separate = True
                if not separate:
                    converted = connection.prepare_for_mysql(native_params)
            elif named:
                converted = cursor._process_params_dict(native_params)
            else:
                converted = cursor._process_params(native_params)
        finally:
            connection._cdeadmin_parameter_sql_mode = previous_mode
        pieces = []; previous = 0
        for index, (start, end, name) in enumerate(spans):
            pieces.append(source[previous:start].encode(connection.python_charset))
            literal = converted[name.encode()] if named else converted[index]
            if not isinstance(literal, (bytes, bytearray)):
                raise TypeError('Native parameter conversion did not return statement bytes')
            pieces.append(bytes(literal)); previous = end
        pieces.append(source[previous:].encode(connection.python_charset))
        return b''.join(pieces)
    except MySQLParameterAdmissionError:
        raise
    except Exception:
        raise MySQLParameterAdmissionError('MySQL parameter conversion failed before query dispatch') from None


class Cursor:
    """Convert raw query rows independently from catalog reads."""

    def __init__(self, connection, *, cancel_requested=None):
        self.connection = connection
        self.cancel_requested = cancel_requested
        self.native = connection.cursor(raw=True)
        self.encoding = connection.python_charset
        self._native_c_api = getattr(connection, '_cmysql', None)
        self._script = None
        self._commands_dispatched = 0

    def execute(self, operation, params=None, *args, **kwargs):
        self._script = None
        self._commands_dispatched = 0
        changes_context = isinstance(operation, str) and re.search(
            r'\b(?:SET|CALL)\b|^[ \t]*DELIMITER[ \t]+', operation, re.I | re.M | re.A) is not None
        if ((bool(params) or changes_context) and isinstance(operation, str) and not args and
                not (set(kwargs) - {'map_results'}) and not kwargs.get('map_results', False)):
            from .mysql_script import Statements
            if params and not isinstance(params, (Mapping, list, tuple)):
                raise MySQLParameterAdmissionError('MySQL parameters must be an object or array')
            self._script = Statements(operation)
            self._parameters = params if params else None
            self._parameter_position = 0
            self._next_command()
            return None
        return self._execute(operation, params, *args, **kwargs)

    def _next_command(self):
        from .mysql_script import MySQLScriptFramingError
        try:
            if self.cancel_requested is not None and self.cancel_requested():
                raise MySQLParameterAdmissionError('MySQL query cancelled before command dispatch')
            from ...data_studio.mysql_quoting import available, parameter_spans
            # Finishing a script must not send a metadata command after its
            # last native response: that would replace ROW_COUNT/diagnostics.
            # Empty tails have no next command in any supported quote mode.
            # A meaningful or ambiguous tail still gets its own current-mode
            # admission below; do not guess its language from an earlier SET.
            finished = self._commands_dispatched and all(
                not self._script.has_next(self._framing_version, candidate)
                for candidate in ('', 'ANSI_QUOTES', 'NO_BACKSLASH_ESCAPES',
                                  'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'))
            if finished:
                source = None
            else:
                version, mode = observed_language(self.connection)
                self._framing_version = version
                source = self._script.next(version, mode)
            if source is None:
                if self._parameters is not None and not isinstance(self._parameters, Mapping) and self._parameter_position != len(self._parameters):
                    raise MySQLParameterAdmissionError('Unused MySQL query parameters remain after the dispatched commands')
                self._script = None
                return False
            spans = list(parameter_spans(source, set(mode.split(',')), dollar_quotes=available(version))) if self._parameters is not None else []
            if self._parameters is None:
                selected = None
            elif isinstance(self._parameters, Mapping):
                if any(name is None or name not in self._parameters for _start, _end, name in spans):
                    raise MySQLParameterAdmissionError('MySQL parameters do not match this native command')
                selected = {name:self._parameters[name] for _start, _end, name in spans}
            else:
                count = len(spans)
                remaining = self._parameters[self._parameter_position:]
                selected = remaining[:count] if self._script.has_next(version, mode) else remaining
                self._parameter_position += len(selected)
                if len(selected) != count:
                    raise MySQLParameterAdmissionError('MySQL parameters do not match this native command')
            # Empty selections still require lexical admission: a later command
            # can contain a named marker missing from the supplied mapping.
            if isinstance(selected, Mapping) or selected:
                self._execute(source, selected)
            else:
                self._execute(source)
            self.encoding = self.connection.python_charset
            return True
        except MySQLParameterAdmissionError as error:
            self._script = None
            error.commands_dispatched = self._commands_dispatched
            raise
        except MySQLScriptFramingError:
            self._script = None
            error = MySQLParameterAdmissionError('MySQL client command framing failed before this command was dispatched')
            error.commands_dispatched = self._commands_dispatched
            raise error from None
        except BaseException:
            self._script = None
            raise

    def nextset(self):
        try: value = self.native.nextset()
        except BaseException:
            self._script = None
            raise
        if value or self._script is None: return value
        if self.cancel_requested is not None and self.cancel_requested(): return None
        return True if self._next_command() else None

    def _execute(self, operation, params=None, *args, **kwargs):
        if self.cancel_requested is not None and self.cancel_requested():
            raise MySQLParameterAdmissionError('MySQL query cancelled before dispatch')
        native_bound = (bool(params) and isinstance(operation, str) and not args and
            not (set(kwargs) - {'map_results'}) and not kwargs.get('map_results', False))
        native_direct = native_bound or (not params and isinstance(operation, str) and not args and
            not (set(kwargs) - {'map_results'}) and not kwargs.get('map_results', False) and
            (self._script is not None or re.search(r'DELIMITER', operation, re.I | re.A) is not None))
        if native_bound:
            operation = bound_source(self.connection, self.native, operation, params)
            params = None
        elif native_direct:
            operation = unbound_source(self.connection, operation)
        if self.cancel_requested is not None and self.cancel_requested():
            raise MySQLParameterAdmissionError('MySQL query cancelled before dispatch')
        if self._native_c_api is not None:
            # Connector/Python 26.7's C query path returns early for an OK
            # response before applying raw=True. A following SELECT in that
            # batch would otherwise inherit the last catalog cursor's mode.
            # This changes client conversion only; no SQL is dispatched here.
            self._native_c_api.raw(True)
        if native_direct:
            # The native COM_QUERY port retains result ownership in the same
            # driver cursor. Its client script preprocessor must not interpret
            # DELIMITER words inside already converted values or native bodies.
            self.connection.handle_unread_result()
            self.native._reset_result()
            self.native._executed = operation
            options = ({'raw':True,'buffered':False,'raw_as_string':False}
                if self._native_c_api is not None else
                {'read_timeout':self.native._read_timeout,'write_timeout':self.native._write_timeout})
            self._commands_dispatched += 1
            from .mysql_session_variables import invalidate
            try:
                self.native._handle_result(self.connection.cmd_query(operation, **options))
            finally:
                invalidate(self.connection)
            return None
        self._commands_dispatched += 1
        from .mysql_session_variables import invalidate
        try:
            if params is None:
                return self.native.execute(operation, *args, **kwargs)
            return self.native.execute(operation, params, *args, **kwargs)
        finally:
            invalidate(self.connection)

    def __getattr__(self, name):
        return getattr(self.native, name)

    def fetchall(self):
        description = self.native.description or ()
        return [tuple(value(item, column, self.encoding)
                      for item, column in zip(row, description))
                for row in self.native.fetchall()]

    def fetchone(self):
        row = self.native.fetchone()
        if row is None:
            return None
        return tuple(value(item, column, self.encoding)
                     for item, column in zip(row, self.native.description))
