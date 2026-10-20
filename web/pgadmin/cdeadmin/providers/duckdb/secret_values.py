"""Native secret constants and explicitly selected, parse-only SQL expressions."""
from collections.abc import Mapping
import math

from ...sdk import RelationalClientError

MAX_BYTES = 1024 * 1024
MAX_NODES = 16384


class Values:
    def __init__(self, adapter):
        self.adapter = adapter
        self.bytes = 0
        self.nodes = 0

    def source(self, value):
        tokens = []
        def emit(text):
            self.bytes += len(text.encode('utf8'))
            if self.bytes > MAX_BYTES:
                raise RelationalClientError('Native secret constants exceed the SQL byte budget')
            tokens.append(text)
        def walk(item, depth=0):
            self.nodes += 1
            if depth > 32 or self.nodes > MAX_NODES:
                raise RelationalClientError('Native secret constants exceed the traversal budget')
            if item is None:emit('NULL')
            elif type(item) is bool:emit('TRUE' if item else 'FALSE')
            elif isinstance(item, str):
                if len(item.encode('utf8')) > MAX_BYTES:
                    raise RelationalClientError('Native secret text exceeds the SQL byte budget')
                emit(self.adapter._literal(item))
            elif type(item) is int:emit(str(item))
            elif type(item) is float and math.isfinite(item):emit(repr(item))
            elif isinstance(item, list):
                emit('[')
                for index, child in enumerate(item):
                    if index:emit(', ')
                    walk(child, depth+1)
                emit(']')
            elif isinstance(item, Mapping):
                if any(not isinstance(key, str) for key in item):
                    raise RelationalClientError('Native secret maps require JSON string keys')
                # Qualify the native constructor so a caller's same-named
                # macro cannot execute while constructing a constant map.
                emit('"system"."main"."map"(');walk(list(item), depth+1);emit(', ')
                walk(list(item.values()), depth+1);emit(')')
            else:
                raise RelationalClientError('Native secret constants require finite JSON values')
        walk(value)
        return ''.join(tokens)


def compile_secret(adapter, name, options, *, persistence_mode=None, on_conflict='ERROR', expressions=None, native_properties=None):
    persistent = options.get('persistent', False)
    if type(persistent) is not bool:
        raise RelationalClientError('Native secret persistence requires a Boolean choice')
    mode = persistence_mode if persistence_mode is not None else ('PERSISTENT' if persistent else 'DEFAULT')
    if not isinstance(mode, str) or mode not in {'DEFAULT', 'TEMPORARY', 'PERSISTENT'}:
        raise RelationalClientError('Select a native secret persistence mode')
    if persistence_mode is not None and 'persistent' in options:
        raise RelationalClientError('Select one native secret persistence control')
    if not isinstance(on_conflict, str) or on_conflict not in {'ERROR', 'IF NOT EXISTS', 'OR REPLACE'}:
        raise RelationalClientError('Select a native secret conflict mode')
    expressions = {} if expressions is None else expressions
    if not isinstance(expressions, Mapping):
        raise RelationalClientError('Native secret expressions require a JSON object')
    secret_type = options.get('secret_type')
    if (not isinstance(secret_type, str) or not secret_type) and 'type' not in expressions:
        raise RelationalClientError('Select an exact native secret type')
    if 'type' in expressions and (secret_type or not name):
        raise RelationalClientError('A native secret type expression requires an explicit name and no literal type')
    storage = options.get('storage')
    storage_sql = ' IN ' + adapter._quote(storage) if storage else ''
    properties = ['TYPE ' + adapter._literal(secret_type)] if secret_type else []
    preview_properties = list(properties)
    property_bytes = sum(len(item.encode('utf8')) for item in properties)
    def append(source, preview):
        nonlocal property_bytes
        property_bytes += len(source.encode('utf8')) + 2
        if property_bytes > MAX_BYTES:
            raise RelationalClientError('Native secret statement exceeds the SQL byte budget')
        properties.append(source);preview_properties.append(preview)
    values = Values(adapter)
    scope = options.get('scope')
    if scope is not None:
        if not isinstance(scope, (str, list)) or isinstance(scope, list) and any(not isinstance(item, str) for item in scope):
            raise RelationalClientError('Native secret scope requires text or a list of text scopes')
        append('SCOPE ' + values.source(scope), 'SCOPE <redacted>')
    constants = {key: value for key, value in options.items()
                 if key not in {'secret_type', 'scope', 'storage', 'persistent', 'parent'}}
    occupied = {'type'} if secret_type else set()
    if scope is not None:occupied.add('scope')
    for key, value in (native_properties or {}).items():
        if not isinstance(key, str) or not key or any(key.casefold() == old.casefold() for old in constants):
            raise RelationalClientError('Native secret properties require distinct text names')
        constants[key] = value
    for key, value in constants.items():
        if key.casefold() in occupied:
            raise RelationalClientError('Native secret properties must have distinct names')
        occupied.add(key.casefold())
        keyword = adapter._quote(key)
        append(keyword + ' ' + values.source(value), keyword + ' <redacted>')
    for key, source in expressions.items():
        if not isinstance(key, str) or not key or key.casefold() in occupied:
            raise RelationalClientError('Native secret properties must have distinct names across constants and expressions')
        occupied.add(key.casefold())
        if not isinstance(source, str) or not source or len(source.encode('utf8')) > MAX_BYTES:
            raise RelationalClientError('Native secret expression exceeds the SQL byte budget or is empty')
        try:
            import duckdb
            expression = str(duckdb.SQLExpression(source))
        except Exception:
            raise RelationalClientError('Native secret property requires one parseable SQL expression') from None
        keyword = adapter._quote(key)
        append(keyword + ' (' + expression + ')', keyword + ' <redacted expression>')
    prefix = ('CREATE ' + ('OR REPLACE ' if on_conflict == 'OR REPLACE' else '') +
        (mode + ' ' if mode != 'DEFAULT' else '') + 'SECRET ' +
        ('IF NOT EXISTS ' if on_conflict == 'IF NOT EXISTS' else '') + name + storage_sql + ' (')
    source = prefix + ', '.join(properties) + ')'
    if len(source.encode('utf8')) > MAX_BYTES:
        raise RelationalClientError('Native secret statement exceeds the SQL byte budget')
    return source, prefix + ', '.join(preview_properties) + ')'
