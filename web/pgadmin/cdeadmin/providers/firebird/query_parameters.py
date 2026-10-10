"""Firebird driver bindings are positional, not dictionary-based."""

from collections.abc import Mapping

from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def normalize_parameters(parameters):
    if parameters is None or (isinstance(parameters, Mapping) and
                              not parameters):
        return ()
    if not isinstance(parameters, (list, tuple)):
        raise RelationalClientError(
            'Firebird query parameters must be an ordered array matching '
            'the ? placeholders; named parameter objects are not supported')
    from .zoned_values import KINDS, parse
    from .grid_values import bind_value

    def decode(value):
        if (isinstance(value, Mapping) and
                value.get('encoding') in KINDS.values()):
            return parse(value)
        if (isinstance(value, Mapping) and
                value.get('encoding') in {'float32', 'float64'}):
            return bind_value(value)
        if isinstance(value, (list, tuple)):
            return [decode(item) for item in value]
        return value

    return tuple(decode(value) for value in parameters)
