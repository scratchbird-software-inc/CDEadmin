##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Visual SQL builder: a neutral query model written in one SQL dialect.

Owner direction 2026-11-06 (option b): a form opened from the SQL tab writes
a query into the active editor; nothing is run. Every builder option is
shown for every engine. An engine declares in its ui_descriptors
capabilities.json (``sql_builder.options``) whether it has each option, from
which version, and why not; unavailable options are greyed out, and the
server refuses them here even if a client sends them. The model carries no
SQL text: names are written by the engine's own quoting and literal values
by this module.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

# Every option, in the order the form shows them.
OPTIONS = (
    ('cte', 'Common table expressions (WITH)'),
    ('cte.recursive', 'Recursive common table expressions'),
    ('cte.materialized', 'MATERIALIZED and NOT MATERIALIZED'),
    ('distinct', 'SELECT DISTINCT'),
    ('distinct_on', 'DISTINCT ON'),
    ('join.inner', 'Inner join'),
    ('join.left', 'Left outer join'),
    ('join.right', 'Right outer join'),
    ('join.full', 'Full outer join'),
    ('join.cross', 'Cross join'),
    ('join.natural', 'Natural join'),
    ('join.using', 'Join on equal column names (USING)'),
    ('where', 'WHERE'),
    ('where.or', 'OR conditions'),
    ('aggregate', 'Aggregate functions'),
    ('aggregate.distinct', 'Aggregates of distinct values'),
    ('group_by', 'GROUP BY'),
    ('group_by.rollup', 'GROUP BY ROLLUP'),
    ('group_by.cube', 'GROUP BY CUBE'),
    ('group_by.grouping_sets', 'GROUP BY GROUPING SETS'),
    ('group_by.all', 'GROUP BY ALL'),
    ('having', 'HAVING'),
    ('order_by', 'ORDER BY'),
    ('order_by.nulls', 'NULLS FIRST and NULLS LAST'),
    ('limit', 'LIMIT'),
    ('offset', 'OFFSET'),
    ('set.union', 'UNION'),
    ('set.union_all', 'UNION ALL'),
    ('set.intersect', 'INTERSECT'),
    ('set.except', 'EXCEPT'),
)
OPTION_IDS = tuple(option for option, _label in OPTIONS)
AGGREGATES = ('count', 'sum', 'avg', 'min', 'max')
COMPARISONS = ('=', '<>', '<', '<=', '>', '>=', 'LIKE', 'NOT LIKE')
JOINS = {'inner': 'JOIN', 'left': 'LEFT JOIN', 'right': 'RIGHT JOIN',
         'full': 'FULL OUTER JOIN', 'cross': 'CROSS JOIN',
         'natural': 'NATURAL JOIN'}
SET_OPERATORS = {'union': 'UNION', 'union_all': 'UNION ALL',
                 'intersect': 'INTERSECT', 'except': 'EXCEPT'}
GROUPINGS = {'columns': 'group_by', 'rollup': 'group_by.rollup',
             'cube': 'group_by.cube',
             'grouping_sets': 'group_by.grouping_sets',
             'all': 'group_by.all'}
LIMITS = {'ctes': 16, 'selects': 8, 'joins': 16, 'items': 200,
          'depth': 8, 'name': 128, 'text': 4096}
# How an engine writes what standard SQL leaves open. ``rollup``: 'function'
# writes GROUP BY ROLLUP (a, b), 'with_rollup' writes GROUP BY a, b WITH
# ROLLUP. ``rollup_order_by``: None, or why ROLLUP and ORDER BY cannot be
# combined. ``text``: 'standard', or 'mysql' for engines whose string
# literals treat a backslash as an escape unless the session's sql_mode
# says otherwise; the text is written before any session exists.
STANDARD_DIALECT = {'rollup': 'function', 'rollup_order_by': None,
                    'text': 'standard'}


class SqlBuilderError(ValueError):
    """The query model is invalid or uses an option the engine lacks."""


def resolve_options(declared: Mapping[str, Any] | None,
                    runtime_version: str | None) -> dict[str, dict]:
    """Every option with ``available`` and ``reason`` for one runtime.

    ``declared`` is the engine's ``sql_builder`` section. An option it does
    not list is unavailable; a version gate is applied to the connected
    runtime's version as the descriptor service applies field gates.
    """
    from pgadmin.cdeadmin.ui_descriptors import version_gate_state
    options = (declared or {}).get('options') or {}
    resolved = {}
    for option, label in OPTIONS:
        entry = options.get(option) or {}
        available = entry.get('available') is True
        reason = entry.get('reason') or ''
        if available and entry.get('version'):
            available, gate_reason = version_gate_state(
                entry['version'], runtime_version)
            reason = '' if available else (gate_reason or reason)
        if not available and not reason:
            reason = 'This connection does not support it.'
        resolved[option] = {'label': label, 'available': available,
                            'reason': '' if available else reason}
    return resolved


def literal(value: Any, text: str = 'standard') -> str:
    """A SQL literal: text, a finite number, TRUE, FALSE or NULL.

    With ``text='mysql'`` a value containing a backslash is written as a
    hexadecimal utf8mb4 literal, which reads back the same in every sql_mode
    (a backslash escapes in quoted text unless NO_BACKSLASH_ESCAPES is set);
    ``text='mysql-hex'`` writes every text value that way.
    """
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SqlBuilderError('Numbers must be finite.')
        return repr(value)
    if isinstance(value, str):
        if '\0' in value or len(value) > LIMITS['text']:
            raise SqlBuilderError('Text values cannot contain NUL and are '
                                  'limited to 4096 characters.')
        if text == 'mysql-hex' or (text == 'mysql' and '\\' in value):
            return "_utf8mb4 X'" + value.encode('utf-8').hex().upper() + "'"
        return "'" + value.replace("'", "''") + "'"
    raise SqlBuilderError('Values are text, numbers, true, false or null.')


def _object(value, keys, label, required=()):
    if not isinstance(value, Mapping):
        raise SqlBuilderError(f'{label} must be an object.')
    unknown = set(value) - set(keys)
    if unknown:
        raise SqlBuilderError(
            f'{label} has unknown parts: {", ".join(sorted(unknown))}.')
    missing = [key for key in required if key not in value]
    if missing:
        raise SqlBuilderError(f'{label} needs {", ".join(missing)}.')
    return value


def _one_of(value, label):
    if len(value) != 1:
        raise SqlBuilderError(f'{label} has exactly one form.')
    return next(iter(value.items()))


def _list(value, label, *, empty=True, limit=None):
    if not isinstance(value, list) or (not empty and not value):
        raise SqlBuilderError(
            f'{label} must be a {"" if empty else "non-empty "}list.')
    if len(value) > (limit or LIMITS['items']):
        raise SqlBuilderError(f'{label} has too many entries.')
    return value


def _flag(value, label):
    if type(value) is not bool:
        raise SqlBuilderError(f'{label} must be true or false.')
    return value


def _name(value, label):
    if (not isinstance(value, str) or not value.strip() or
            '\0' in value or len(value) > LIMITS['name']):
        raise SqlBuilderError(
            f'{label} must be a name of 1 to 128 characters.')
    return value


class _Writer:
    def __init__(self, names: Callable[[str], str],
                 available: Mapping[str, Mapping[str, Any]],
                 dialect: Mapping[str, Any] | None = None):
        self.names = names
        self.available = available
        unknown = set(dialect or {}) - set(STANDARD_DIALECT)
        if unknown:
            raise ValueError(f'unknown SQL builder dialect keys: {unknown}')
        self.dialect = {**STANDARD_DIALECT, **(dialect or {})}
        self.backslash = False

    def literal(self, value):
        if isinstance(value, str) and '\\' in value:
            self.backslash = True
        return literal(value, self.dialect['text'])

    def need(self, option):
        state = self.available.get(option) or {}
        if state.get('available') is not True:
            raise SqlBuilderError(
                f'{state.get("label") or option} is not available here: '
                f'{state.get("reason") or "not supported"}')

    def name(self, value, label):
        return self.names(_name(value, label))

    def name_list(self, values, label):
        return ', '.join(self.name(value, label) for value in
                         _list(values, label, empty=False))

    # -- expressions -----------------------------------------------------
    def expression(self, value, label='Expression', aggregates=True):
        # An aggregate's argument is a column or a value: SQL does not nest
        # aggregates, and this keeps the model's depth bounded.
        value = _object(value, ('column', 'value', 'aggregate')
                        if aggregates else ('column', 'value'), label)
        kind, body = _one_of(value, label)
        if kind == 'column':
            parts = _list(body, f'{label} column', empty=False, limit=2)
            return '.'.join(self.name(part, 'Column name') for part in parts)
        if kind == 'value':
            return self.literal(body)
        aggregate = _object(body, ('function', 'distinct', 'argument'),
                            'Aggregate', ('function', 'argument'))
        self.need('aggregate')
        function = aggregate['function']
        if function not in AGGREGATES:
            raise SqlBuilderError(
                f'Aggregate must be one of {", ".join(AGGREGATES)}.')
        distinct = _flag(aggregate.get('distinct', False),
                         'Aggregate distinct')
        if aggregate['argument'] == '*':
            if function != 'count' or distinct:
                raise SqlBuilderError('Only count takes *.')
            return 'count(*)'
        if distinct:
            self.need('aggregate.distinct')
        argument = self.expression(aggregate['argument'],
                                   'Aggregate argument', aggregates=False)
        return f'{function}({"DISTINCT " if distinct else ""}{argument})'

    def expressions(self, values, label):
        return ', '.join(self.expression(item, label) for item in
                         _list(values, label, empty=False))

    def condition(self, value, depth=0):
        if depth > LIMITS['depth']:
            raise SqlBuilderError('Conditions are nested too deeply.')
        value = _object(value, ('all', 'any', 'compare', 'is_null',
                                'is_not_null', 'in'), 'Condition')
        kind, body = _one_of(value, 'A condition')
        if kind in ('all', 'any'):
            if kind == 'any':
                self.need('where.or')
            items = _list(body, 'Condition group', empty=False)
            joined = (' AND ' if kind == 'all' else ' OR ').join(
                self.condition(item, depth + 1) for item in items)
            return joined if len(items) == 1 else f'({joined})'
        if kind == 'compare':
            body = _object(body, ('left', 'op', 'right'), 'Comparison',
                           ('left', 'op', 'right'))
            if body['op'] not in COMPARISONS:
                raise SqlBuilderError(
                    f'Comparison must be one of {", ".join(COMPARISONS)}.')
            return (f'{self.expression(body["left"])} {body["op"]} '
                    f'{self.expression(body["right"])}')
        if kind in ('is_null', 'is_not_null'):
            return (f'{self.expression(body)} IS '
                    f'{"NULL" if kind == "is_null" else "NOT NULL"}')
        body = _object(body, ('expr', 'values'), 'IN condition',
                       ('expr', 'values'))
        values = _list(body['values'], 'IN values', empty=False)
        return (f'{self.expression(body["expr"])} IN ('
                f'{", ".join(self.literal(item) for item in values)})')

    # -- sources ---------------------------------------------------------
    def source(self, value, alias, visible_ctes):
        value = _object(value, ('relation', 'cte'), 'Source')
        kind, body = _one_of(value, 'A source')
        if kind == 'relation':
            parts = _list(body, 'Relation', empty=False, limit=4)
            text = '.'.join(self.name(part, 'Relation name')
                            for part in parts)
        else:
            name = _name(body, 'CTE name')
            if name not in visible_ctes:
                raise SqlBuilderError(
                    f'No CTE named {name} is defined before it is used.')
            text = self.names(name)
        if alias is not None:
            text += ' AS ' + self.name(alias, 'Alias')
        return text

    def join(self, value, visible_ctes, pad):
        value = _object(value, ('type', 'source', 'alias', 'on', 'using'),
                        'Join', ('type', 'source'))
        kind = value['type']
        if kind not in JOINS:
            raise SqlBuilderError(
                f'Join type must be one of {", ".join(JOINS)}.')
        self.need(f'join.{kind}')
        source = self.source(value['source'], value.get('alias'),
                             visible_ctes)
        text = f'{pad}  {JOINS[kind]} {source}'
        if kind in ('cross', 'natural'):
            if 'on' in value or 'using' in value:
                raise SqlBuilderError(f'A {kind} join has no ON or USING.')
            return text
        if ('on' in value) == ('using' in value):
            raise SqlBuilderError('A join needs either ON or USING.')
        if 'on' in value:
            return text + ' ON ' + self.condition(value['on'])
        self.need('join.using')
        return (text + ' USING (' +
                self.name_list(value['using'], 'USING column') + ')')

    # -- one SELECT ------------------------------------------------------
    def column(self, value):
        value = _object(value, ('expr', 'alias', 'all'), 'Column')
        if 'all' in value:
            if len(value) != 1:
                raise SqlBuilderError('An all-columns entry has no alias.')
            qualifier = value['all']
            return ('*' if qualifier is None else
                    self.name(qualifier, 'Qualifier') + '.*')
        text = self.expression(value.get('expr'), 'Column')
        if value.get('alias') is not None:
            text += ' AS ' + self.name(value['alias'], 'Alias')
        return text

    def grouping(self, value, pad):
        value = _object(value, ('kind', 'items', 'sets'), 'GROUP BY',
                        ('kind',))
        kind = value['kind']
        if kind not in GROUPINGS:
            raise SqlBuilderError(
                f'Grouping must be one of {", ".join(GROUPINGS)}.')
        self.need('group_by')
        if kind != 'columns':
            self.need(GROUPINGS[kind])
        if kind == 'all':
            return f'{pad}GROUP BY ALL'
        if kind == 'grouping_sets':
            sets = _list(value.get('sets'), 'Grouping sets', empty=False)
            written = ', '.join(
                '(' + ', '.join(self.expression(item) for item in
                                _list(entry, 'Grouping set')) + ')'
                for entry in sets)
            return f'{pad}GROUP BY GROUPING SETS ({written})'
        items = self.expressions(value.get('items'), 'Grouping column')
        if kind == 'rollup' and self.dialect['rollup'] == 'with_rollup':
            return f'{pad}GROUP BY {items} WITH ROLLUP'
        return f'{pad}GROUP BY ' + (
            items if kind == 'columns' else f'{kind.upper()} ({items})')

    def select(self, value, visible_ctes, indent):
        value = _object(value, ('distinct', 'distinct_on', 'columns',
                                'from', 'joins', 'where', 'group_by',
                                'having'), 'SELECT', ('from',))
        pad = ' ' * indent
        head = 'SELECT'
        if _flag(value.get('distinct', False), 'distinct'):
            self.need('distinct')
            head += ' DISTINCT'
        if value.get('distinct_on'):
            self.need('distinct_on')
            head += (' DISTINCT ON (' +
                     self.expressions(value['distinct_on'], 'DISTINCT ON') +
                     ')')
        columns = [self.column(item) for item in
                   _list(value.get('columns', []), 'Columns')] or ['*']
        last = len(columns) - 1
        lines = [pad + head]
        lines.extend(f'{pad}  {text}{"," if index < last else ""}'
                     for index, text in enumerate(columns))
        source = _object(value['from'], ('source', 'alias'), 'FROM',
                         ('source',))
        lines.append(f'{pad}FROM ' + self.source(
            source['source'], source.get('alias'), visible_ctes))
        lines.extend(self.join(item, visible_ctes, pad) for item in
                     _list(value.get('joins', []), 'Joins',
                           limit=LIMITS['joins']))
        if value.get('where') is not None:
            self.need('where')
            lines.append(f'{pad}WHERE {self.condition(value["where"])}')
        if value.get('group_by') is not None:
            lines.append(self.grouping(value['group_by'], pad))
        if value.get('having') is not None:
            self.need('having')
            lines.append(f'{pad}HAVING {self.condition(value["having"])}')
        return lines

    # -- a compound query ------------------------------------------------
    def order(self, value):
        value = _object(value, ('expr', 'direction', 'nulls'), 'Order',
                        ('expr',))
        direction = value.get('direction', 'asc')
        if direction not in ('asc', 'desc'):
            raise SqlBuilderError('Direction must be asc or desc.')
        text = f'{self.expression(value["expr"])} {direction.upper()}'
        if value.get('nulls') is not None:
            if value['nulls'] not in ('first', 'last'):
                raise SqlBuilderError('NULLS must be first or last.')
            self.need('order_by.nulls')
            text += f' NULLS {value["nulls"].upper()}'
        return text

    def compound(self, value, visible_ctes, indent=0):
        value = _object(value, ('selects', 'operators', 'order_by', 'limit',
                                'offset'), 'Query', ('selects',))
        selects = _list(value['selects'], 'Query', empty=False,
                        limit=LIMITS['selects'])
        operators = _list(value.get('operators', []), 'Set operators')
        if len(operators) != len(selects) - 1:
            raise SqlBuilderError(
                'Each SELECT after the first needs a set operator.')
        pad = ' ' * indent
        lines = self.select(selects[0], visible_ctes, indent)
        for operator, select in zip(operators, selects[1:]):
            if operator not in SET_OPERATORS:
                raise SqlBuilderError('Set operator must be one of '
                                      f'{", ".join(SET_OPERATORS)}.')
            self.need(f'set.{operator}')
            lines.append(pad + SET_OPERATORS[operator])
            lines.extend(self.select(select, visible_ctes, indent))
        order = _list(value.get('order_by', []), 'ORDER BY')
        if order:
            self.need('order_by')
            refusal = self.dialect['rollup_order_by']
            if refusal and any(
                    isinstance(select.get('group_by'), Mapping) and
                    select['group_by'].get('kind') == 'rollup'
                    for select in selects):
                raise SqlBuilderError(refusal)
            lines.append(f'{pad}ORDER BY ' + ', '.join(
                self.order(item) for item in order))
        for key in ('limit', 'offset'):
            number = value.get(key)
            if number is None:
                continue
            if type(number) is not int or number < 0:
                raise SqlBuilderError(
                    f'{key.upper()} must be a whole number of 0 or more.')
            self.need(key)
        if value.get('offset') is not None and value.get('limit') is None:
            raise SqlBuilderError('OFFSET needs LIMIT.')
        if value.get('limit') is not None:
            offset = value.get('offset')
            lines.append(f'{pad}LIMIT {value["limit"]}' + (
                f' OFFSET {offset}' if offset is not None else ''))
        return lines

    # -- the whole statement ---------------------------------------------
    def cte(self, value, visible, recursive):
        value = _object(value, ('name', 'columns', 'materialized', 'query'),
                        'CTE', ('name', 'query'))
        name = _name(value['name'], 'CTE name')
        if name in visible:
            raise SqlBuilderError(f'Two CTEs are named {name}.')
        head = '  ' + self.names(name)
        if value.get('columns'):
            head += f' ({self.name_list(value["columns"], "CTE column")})'
        head += ' AS'
        materialized = value.get('materialized')
        if materialized is not None:
            self.need('cte.materialized')
            head += (' MATERIALIZED' if _flag(materialized, 'materialized')
                     else ' NOT MATERIALIZED')
        # A recursive CTE may read itself; any CTE reads earlier ones.
        scope = visible + [name] if recursive else list(visible)
        body = self.compound(value['query'], scope, indent=4)
        return name, [head + ' (', *body]

    def statement(self, model):
        model = _object(model, ('with', 'recursive', 'query'),
                        'Query model', ('query',))
        ctes = _list(model.get('with', []), 'WITH', limit=LIMITS['ctes'])
        recursive = _flag(model.get('recursive', False), 'recursive')
        if recursive and not ctes:
            raise SqlBuilderError('RECURSIVE needs a CTE.')
        lines, visible = [], []
        if ctes:
            self.need('cte')
            if recursive:
                self.need('cte.recursive')
            lines.append('WITH RECURSIVE' if recursive else 'WITH')
            for index, item in enumerate(ctes):
                name, written = self.cte(item, visible, recursive)
                lines.extend(written)
                lines.append('  )' + (',' if index < len(ctes) - 1 else ''))
                visible.append(name)
        lines.extend(self.compound(model['query'], visible))
        return '\n'.join(lines)


def build(model: Mapping[str, Any], names: Callable[[str], str],
          available: Mapping[str, Mapping[str, Any]],
          dialect: Mapping[str, Any] | None = None) -> str:
    """The statement for ``model``, or SqlBuilderError."""
    writer = _Writer(names, available, dialect)
    statement = writer.statement(model)
    if writer.backslash and writer.dialect['text'] == 'mysql':
        # A hexadecimal literal takes the charset's default collation and a
        # quoted one the connection's; MariaDB refuses to compare the two
        # (illegal mix of collations), so one hex value makes them all hex.
        statement = _Writer(names, available, {
            **writer.dialect, 'text': 'mysql-hex'}).statement(model)
    return statement


def relations(catalog: Sequence[Mapping[str, Any]], kinds: Sequence[str],
              columns: Callable[[Mapping[str, Any]], list[str]]
              ) -> list[dict]:
    """The catalog's relations with their columns, for the form's pickers."""
    found = [{'path': list(resource.get('display_path') or ()),
              'kind': resource['resource_kind'],
              'name': resource.get('display_name'),
              'columns': columns(resource)}
             for resource in catalog
             if resource.get('resource_kind') in kinds]
    return sorted(found, key=lambda item: item['path'])
