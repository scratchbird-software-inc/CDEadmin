"""Typed JSON constants for native secret options; never evaluate expressions."""
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


def compile_secret(adapter, name, options):
    persistent = options.get('persistent', False)
    if type(persistent) is not bool:
        raise RelationalClientError('Native secret persistence requires a Boolean choice')
    secret_type = options.get('secret_type')
    if not isinstance(secret_type, str) or not secret_type:
        raise RelationalClientError('Select an exact native secret type')
    secret_type = adapter._literal(secret_type)
    storage = options.get('storage')
    storage_sql = ' IN ' + adapter._quote(storage) if storage else ''
    properties = ['TYPE ' + secret_type]
    preview_properties = list(properties)
    values = Values(adapter)
    scope = options.get('scope')
    if scope is not None:
        if not isinstance(scope, (str, list)) or isinstance(scope, list) and any(not isinstance(item, str) for item in scope):
            raise RelationalClientError('Native secret scope requires text or a list of text scopes')
        properties.append('SCOPE ' + values.source(scope));preview_properties.append('SCOPE <redacted>')
    for key, value in options.items():
        if key in {'secret_type', 'scope', 'storage', 'persistent', 'parent'}:continue
        keyword = adapter._quote(key)
        properties.append(keyword + ' ' + values.source(value))
        preview_properties.append(keyword + ' <redacted>')
    prefix = 'CREATE ' + ('PERSISTENT ' if persistent else '') + 'SECRET ' + name + storage_sql + ' ('
    source = prefix + ', '.join(properties) + ')'
    if len(source.encode('utf8')) > MAX_BYTES:
        raise RelationalClientError('Native secret statement exceeds the SQL byte budget')
    return source, prefix + ', '.join(preview_properties) + ')'
