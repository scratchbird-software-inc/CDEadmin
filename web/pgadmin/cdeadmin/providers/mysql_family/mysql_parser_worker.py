"""Isolated stdlib bridge to MySQL Shell's versioned server grammar C ABI.

This helper parses bytes only. It does not connect to a database or execute SQL.
Each native parser is created, used and destroyed on the same process thread.
"""
import ctypes
import json
import os
from pathlib import Path
import sys


class ParserUnavailable(ValueError):
    pass


def check(request):
    if not isinstance(request, dict) or request.get('version') != '9.7.0':
        raise ParserUnavailable('Select the exact native grammar version')
    library = Path(request['library']).resolve(strict=True)
    dll_directory = os.add_dll_directory(str(library.parent)) if os.name == 'nt' else None
    try:
        native = ctypes.CDLL(str(library))
        abi = {
            'parser_version': ([], ctypes.c_char_p),
            'parser_create': ([ctypes.POINTER(ctypes.c_void_p)], ctypes.c_int),
            'parser_destroy': ([ctypes.c_void_p], ctypes.c_int),
            'parser_set_sql_mode': ([ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t], ctypes.c_int),
            'parser_check_syntax': ([ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t], ctypes.c_int),
            'parser_pending_errors': ([ctypes.c_void_p], ctypes.c_size_t),
            'parser_next_error': ([ctypes.c_void_p], ctypes.c_void_p),
            'parser_error_message': ([ctypes.c_void_p], ctypes.c_char_p),
            **{name: ([ctypes.c_void_p], ctypes.c_size_t) for name in (
                'parser_error_token_offset', 'parser_error_token_length', 'parser_error_line', 'parser_error_line_offset')},
        }
        for name, (arguments, result) in abi.items():
            function = getattr(native, name); function.argtypes = arguments; function.restype = result
        version = native.parser_version().decode('ascii')
        if version != request['version']:
            raise ParserUnavailable('The native grammar library version differs')
        statements = request['statements']
        if not isinstance(statements, list) or not 1 <= len(statements) <= 1000:
            raise ParserUnavailable('Select a bounded native statement batch')
        if sum(len(item['source'].encode('utf8')) for item in statements) > 2 * 1024 * 1024:
            raise ParserUnavailable('Native statement bytes exceed the editor bound')
        handle = ctypes.c_void_p()
        if native.parser_create(ctypes.byref(handle)) != 0 or not handle.value:
            raise ParserUnavailable('Native grammar parser creation failed')
        try:
            results = []; total_errors = 0
            for item in statements:
                source, mode = item['source'], item['sql_mode']
                if '\x00' in source or not isinstance(mode, str) or len(mode) > 4096 or '\x00' in mode:
                    raise ParserUnavailable('Native source or language mode is unavailable')
                encoded = mode.encode('ascii')
                if native.parser_set_sql_mode(handle, encoded, len(encoded)) != 0:
                    raise ParserUnavailable('The selected native SQL mode is unavailable')
                encoded = source.encode('utf8')
                status = native.parser_check_syntax(handle, encoded, len(encoded))
                if status not in {0, 2}:
                    raise ParserUnavailable('The native parser returned an invalid status')
                errors = []
                while native.parser_pending_errors(handle):
                    total_errors += 1
                    if total_errors > 1000:
                        raise ParserUnavailable('Native diagnostic count exceeds its bound')
                    error = native.parser_next_error(handle)
                    if not error:
                        raise ParserUnavailable('The native diagnostic handle is unavailable')
                    message = native.parser_error_message(error)
                    if message is None:
                        raise ParserUnavailable('The native diagnostic is unavailable')
                    # Upstream deliberately reports invalid optimizer hints as
                    # parser failures although the server can execute the SQL
                    # with a warning. Keep those separate from SQL rejection.
                    errors.append({'optimizer_hint': b'(optimizer hints)' in message,
                        'byte_offset': int(native.parser_error_token_offset(error)),
                        'byte_length': int(native.parser_error_token_length(error)),
                        'native_line': int(native.parser_error_line(error)),
                        'native_line_offset': int(native.parser_error_line_offset(error))})
                if status == 2 and not errors:
                    raise ParserUnavailable('Native parser failure has no diagnostic')
                results.append({'accepted': not errors, 'sql_syntax_valid': not any(not row['optimizer_hint'] for row in errors),
                                'native_status': status, 'diagnostics': errors})
            return {'available': True, 'parser_version': version, 'statements': results,
                    'input_character_set': 'utf8mb4', 'sql_executed': False, 'database_connection_opened': False}
        finally:
            if native.parser_destroy(handle) != 0:
                raise ParserUnavailable('Native grammar parser release is unconfirmed')
    finally:
        if dll_directory is not None: dll_directory.close()


if __name__ == '__main__':
    try:
        data = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024: raise ParserUnavailable('Native grammar input exceeds its bound')
        result = check(json.loads(data))
    except Exception as error:
        result = {'available': False, 'error_type': type(error).__name__, 'sql_executed': False}
    print(json.dumps(result, ensure_ascii=True, separators=(',', ':')), flush=True)
