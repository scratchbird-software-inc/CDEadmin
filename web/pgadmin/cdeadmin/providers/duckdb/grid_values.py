"""Exact native row pages and private optimistic identities.

Python fetchall() narrows TIMESTAMP_NS to microseconds. Keep display values
in the existing Arrow wire format, and bind private originals from native
scalar text inside their native container/type. Neither representation is
executable user SQL. The outer lambda observes each source value once.
"""
from copy import deepcopy
from dataclasses import dataclass

from ...sdk import RelationalClientError
from .unions import capture, quote, restore
from .values import scalar

NATIVE = '"system"."main".'


def _binding_source(expression, kind, counter):
    """Produce nullable strings at leaves without a Python scalar conversion."""
    children = dict(kind.children) if kind.id in {
        'struct', 'union', 'list', 'array', 'map'} else {}
    if not children:
        return f'CAST({expression} AS VARCHAR)'
    counter[0] += 1
    variable = '__cde_bound_' + str(counter[0])
    if kind.id in {'list', 'array'}:
        return (f'{NATIVE}list_transform({expression}, lambda {variable}: '
                + _binding_source(variable, children['child'], counter) + ')')
    if kind.id == 'map':
        key = _binding_source(variable + '.key', children['key'], counter)
        value = _binding_source(variable + '.value', children['value'], counter)
        return (f'{NATIVE}list_transform({NATIVE}map_entries({expression}), '
                f'lambda {variable}: {NATIVE}struct_pack(key := {key}, value := {value}))')
    if kind.id == 'union':
        fields = [quote(name) + ' := ' + _binding_source(
            f'{NATIVE}union_extract({expression}, '
            + "'" + name.replace("'", "''") + "')", child, counter)
            for name, child in kind.children[1:]]
        body = (f'{NATIVE}struct_pack(tag := CAST({NATIVE}union_tag({expression}) AS VARCHAR), '
                f'members := {NATIVE}struct_pack(' + ', '.join(fields) + '))')
    else:
        fields = [quote(name) + ' := ' + _binding_source(
            expression + '.' + quote(name), child, counter)
            for name, child in kind.children]
        body = NATIVE + 'struct_pack(' + ', '.join(fields) + ')'
    return f'CASE WHEN {expression} IS NULL THEN NULL ELSE {body} END'


def _bound_expression(value, kind):
    """Reconstruct a private original using bound leaves and native types."""
    native_type = str(kind)  # An engine-supplied DuckDBPyType, never a draft.
    if value is None:
        return f'CAST(? AS {native_type})', [None]
    sources, parameters = [], []

    def child(item, child_type):
        source, bound = _bound_expression(item, child_type)
        parameters.extend(bound)
        return source

    children = dict(kind.children) if kind.id in {
        'struct', 'union', 'list', 'array', 'map'} else {}
    if kind.id == 'struct':
        sources = [quote(name) + ' := ' + child(value[name], child_type)
                   for name, child_type in kind.children]
        source = NATIVE + 'struct_pack(' + ', '.join(sources) + ')'
    elif kind.id == 'union':
        tag = value['tag']
        if tag not in children:
            raise RelationalClientError('Native union identity is unavailable')
        source = (NATIVE + 'union_value(' + quote(tag) + ' := '
                  + child(value['members'][tag], children[tag]) + ')')
    elif kind.id in {'list', 'array'}:
        source = '[' + ', '.join(
            child(item, children['child']) for item in value) + ']'
    elif kind.id == 'map':
        keys = [child(item['key'], children['key']) for item in value]
        values = [child(item['value'], children['value']) for item in value]
        source = (NATIVE + 'map([' + ', '.join(keys) + '], ['
                  + ', '.join(values) + '])')
    else:
        return f'CAST(? AS {native_type})', [value]
    return f'CAST({source} AS {native_type})', parameters


@dataclass(frozen=True)
class NativeCell:
    kind: object
    public: object
    original: object

    def __deepcopy__(self, memo):
        # Private cells are never exposed or edited. Copy only their public
        # wire values at the presentation boundary, not the native type object.
        return self

    def binding(self):
        return _bound_expression(self.original, self.kind)


class RowCursor:
    def __init__(self, connection):
        self.connection = connection
        self.relation = None
        self.kinds = None
        self.description = None
        self.lossless = connection.execute(
            f"SELECT {NATIVE}current_setting('arrow_lossless_conversion')"
        ).fetchone()[0]

    def execute(self, source):
        self.connection.execute('SET arrow_lossless_conversion=true')
        relation = self.connection.sql(source)
        self.kinds = list(relation.types)
        self.description = [(name, kind) for name, kind in
                            zip(relation.columns, self.kinds)]
        fields = []
        for index, kind in enumerate(self.kinds):
            variable = '__cde_value_' + str(index)
            public = capture(variable, kind, [0], NATIVE)
            original = _binding_source(variable, kind, [0])
            fields.append(
                f'{NATIVE}list_transform([#{index + 1}], lambda {variable}: '
                f'{NATIVE}struct_pack(public_value := {public}, original := {original}))'
                f'[1] AS __cde_cell_{index}')
        self.relation = relation.project(', '.join(fields))
        return self

    def fetchall(self):
        table = self.relation.to_arrow_table()
        return [tuple(NativeCell(
            kind, restore(scalar(table.column(index)[row]['public_value']), kind),
            table.column(index)[row]['original'].as_py())
            for index, kind in enumerate(self.kinds))
            for row in range(table.num_rows)]

    def close(self):
        self.relation = None
        self.kinds = None
        if not self.lossless:
            self.connection.execute('SET arrow_lossless_conversion=false')


def public_values(values):
    return {name: deepcopy(value.public) if isinstance(value, NativeCell)
            else deepcopy(value) for name, value in values.items()}


def identity_predicate(quote_name, identity):
    clauses, parameters = [], []
    originals = dict(zip(identity.key_columns, identity.key_values))
    originals.update({name: value for name, value in identity.original.items()
                      if name not in originals})
    for name, value in originals.items():
        if not isinstance(value, NativeCell):
            raise RelationalClientError('Native row identity needs a fresh page')
        source, bound = value.binding()
        clauses.append(quote_name(name) + ' IS NOT DISTINCT FROM ' + source)
        parameters.extend(bound)
    return ' AND '.join(clauses), tuple(parameters)
