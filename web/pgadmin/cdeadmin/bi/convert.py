##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""SQL-to-question: map a raw SELECT onto builder state, or report loss.

Only a deliberately small, unambiguous SELECT shape maps:

* one relation (optionally schema qualified) with an optional alias;
* plain column references and SUM/COUNT/COUNT DISTINCT/MIN/MAX/AVG;
* a WHERE made of AND-ed ``column op literal`` / ``IN`` / ``BETWEEN`` /
  ``IS [NOT] NULL`` terms, where a right-hand side may be ``{{parameter}}``;
* GROUP BY on the selected plain columns, ORDER BY, LIMIT.

Anything else (joins, subqueries, expressions, OR, DISTINCT, HAVING, window
functions, ``*`` ...) is not guessed at.  The result is then a raw ``sql``
question that preserves the text exactly, with ``fidelity`` ``none`` and every
blocking reason listed.  A mapped statement can still be ``lossy`` (for
instance a missing LIMIT becomes the builder default); each difference is
listed in ``loss``.
"""

from __future__ import annotations

import copy

from .models import BIError, output_id, validate_question
from .sqltext import significant, tokenize

AGGREGATES = {'sum': 'sum', 'count': 'count', 'min': 'min', 'max': 'max',
              'avg': 'avg'}
_BLOCKERS = {
    'join': 'joins are not expressible in builder state',
    'inner': 'joins are not expressible in builder state',
    'left': 'joins are not expressible in builder state',
    'right': 'joins are not expressible in builder state',
    'full': 'joins are not expressible in builder state',
    'cross': 'joins are not expressible in builder state',
    'natural': 'joins are not expressible in builder state',
    'union': 'set operations are not expressible in builder state',
    'intersect': 'set operations are not expressible in builder state',
    'except': 'set operations are not expressible in builder state',
    'distinct': 'DISTINCT is not expressible in builder state',
    'having': 'HAVING is not expressible in builder state',
    'over': 'window functions are not expressible in builder state',
    'window': 'window functions are not expressible in builder state',
    'offset': 'OFFSET is not expressible in builder state',
    'fetch': 'FETCH FIRST is not expressible in builder state',
    'case': 'CASE expressions are not expressible in builder state',
    'or': 'OR is not expressible in builder filters',
    'like': 'LIKE is not an admitted builder operator',
    'ilike': 'LIKE is not an admitted builder operator',
    'exists': 'subqueries are not expressible in builder state',
    'with': 'common table expressions are not expressible in builder state',
}


class Unmappable(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


def _loss(code, severity, detail):
    return {'code': code, 'severity': severity, 'detail': detail}


def _ident(token):
    if token.kind == 'qident':
        quote = token.text[0]
        return token.text[1:-1].replace(quote * 2, quote)
    return token.text


def _string(token):
    return token.text[1:-1].replace("''", "'")


class _Parser:
    def __init__(self, tokens, parameter_types):
        self.tokens = tokens
        self.index = 0
        self.parameter_types = parameter_types
        self.parameters = {}
        self.loss = []
        self.relation = None
        self.qualifiers = set()
        self.pending_qualifiers = []

    # token helpers -------------------------------------------------------
    def peek(self, offset=0):
        i = self.index + offset
        return self.tokens[i] if i < len(self.tokens) else None

    def word(self, *names, offset=0):
        token = self.peek(offset)
        return token is not None and token.kind == 'word' and (
            token.text.lower() in names)

    def punct(self, text, offset=0):
        token = self.peek(offset)
        return token is not None and token.kind == 'punct' and (
            token.text == text)

    def take(self):
        token = self.peek()
        if token is None:
            raise Unmappable('truncated', 'statement ends unexpectedly')
        self.index += 1
        return token

    def expect_word(self, name):
        if not self.word(name):
            raise Unmappable('syntax', f'expected {name.upper()}')
        self.index += 1

    # grammar -------------------------------------------------------------
    def parse(self):
        self.expect_word('select')
        items = self.select_list()
        self.expect_word('from')
        self.relation_clause()
        where, group_by, order_by, limit = [], [], [], None
        if self.word('where'):
            self.index += 1
            where = self.conditions()
        if self.word('group'):
            self.index += 1
            self.expect_word('by')
            group_by = self.expression_list()
        if self.word('order'):
            self.index += 1
            self.expect_word('by')
            order_by = self.order_list()
        if self.word('limit'):
            self.index += 1
            token = self.take()
            if token.kind != 'number' or not token.text.isdigit():
                raise Unmappable('limit', 'LIMIT must be an integer literal')
            limit = int(token.text)
        if self.punct(';'):
            self.index += 1
        if self.peek() is not None:
            raise Unmappable(
                'trailing', f'unsupported clause near {self.peek().text!r}')
        return items, where, group_by, order_by, limit

    def select_list(self):
        items = []
        while True:
            items.append(self.select_item())
            if self.punct(','):
                self.index += 1
                continue
            return items

    def select_item(self):
        token = self.peek()
        if token is None:
            raise Unmappable('syntax', 'empty select list')
        if token.kind == 'punct' and token.text == '*':
            raise Unmappable(
                'star', 'SELECT * needs the catalog to expand columns')
        if token.kind == 'word' and token.text.lower() in AGGREGATES and \
                self.punct('(', offset=1):
            item = self.aggregate()
        else:
            column = self.column_ref()
            item = {'kind': 'column', 'column': column}
        alias = self.alias()
        if alias is not None:
            item['alias'] = alias
        if self.punct('.') or self.punct('(') or (
                self.peek() is not None and self.peek().kind == 'punct' and
                self.peek().text in {'+', '-', '*', '/', '||', '::', '%'}):
            raise Unmappable(
                'expression', 'computed columns are not builder state')
        return item

    def aggregate(self):
        function = AGGREGATES[self.take().text.lower()]
        self.index += 1  # (
        distinct = False
        if self.word('distinct'):
            if function != 'count':
                raise Unmappable(
                    'distinct', f'{function.upper()}(DISTINCT ...) is not '
                    'builder state')
            self.index += 1
            distinct = True
        token = self.peek()
        column = None
        if token is not None and token.kind == 'punct' and token.text == '*':
            if function != 'count' or distinct:
                raise Unmappable('star', 'only COUNT(*) may use *')
            self.index += 1
        else:
            column = self.column_ref()
        if not self.punct(')'):
            raise Unmappable('expression', 'aggregate argument is not a '
                             'plain column')
        self.index += 1
        item = {'kind': 'aggregate',
                'function': 'count_distinct' if distinct else function}
        if column is not None:
            item['column'] = column
        return item

    def alias(self):
        if self.word('as'):
            self.index += 1
            token = self.take()
            if token.kind not in {'word', 'qident'}:
                raise Unmappable('alias', 'unsupported alias')
            return _ident(token)
        token = self.peek()
        if token is not None and (token.kind == 'qident' or (
                token.kind == 'word' and token.text.lower() not in {
                    'from', 'where', 'group', 'order', 'limit', 'having',
                    'union', 'join', 'inner', 'left', 'right', 'full',
                    'cross', 'natural', 'offset', 'fetch', 'and', 'or',
                    'on', 'asc', 'desc', 'intersect', 'except', 'window',
                    'for'})):
            self.index += 1
            return _ident(token)
        return None

    def column_ref(self):
        token = self.take()
        if token.kind not in {'word', 'qident'}:
            raise Unmappable('expression',
                             f'unsupported expression {token.text!r}')
        if token.kind == 'word' and token.text.lower() in {
                'null', 'true', 'false', 'case', 'cast', 'not', 'exists'}:
            raise Unmappable('expression',
                             f'unsupported expression {token.text!r}')
        name = _ident(token)
        if self.punct('.'):
            self.index += 1
            qualifier = name
            token = self.take()
            if token.kind not in {'word', 'qident'}:
                raise Unmappable('expression', 'unsupported column')
            name = _ident(token)
            if qualifier.lower() not in self.qualifiers and (
                    self.relation is not None):
                raise Unmappable(
                    'qualifier', f'column qualifier {qualifier!r} is not '
                    'the single relation')
            if self.relation is None:
                # SELECT list is parsed before FROM: remember to verify.
                self.pending_qualifiers.append(qualifier)
        return name

    def relation_clause(self):
        parts = []
        token = self.take()
        if token.kind not in {'word', 'qident'}:
            raise Unmappable('subquery', 'FROM must name a relation')
        parts.append(_ident(token))
        while self.punct('.'):
            self.index += 1
            token = self.take()
            if token.kind not in {'word', 'qident'}:
                raise Unmappable('syntax', 'malformed relation name')
            parts.append(_ident(token))
        self.relation = parts
        self.qualifiers = {parts[-1].lower()}
        if self.punct(','):
            raise Unmappable('join', 'multiple relations are not builder '
                             'state')
        alias = self.alias()
        if alias is not None:
            self.qualifiers.add(alias.lower())
        for qualifier in self.pending_qualifiers:
            if qualifier.lower() not in self.qualifiers:
                raise Unmappable(
                    'qualifier', f'column qualifier {qualifier!r} is not '
                    'the single relation')

    def literal(self):
        token = self.take()
        sign = 1
        if token.kind == 'punct' and token.text in {'-', '+'}:
            sign = -1 if token.text == '-' else 1
            token = self.take()
            if token.kind != 'number':
                raise Unmappable('literal', 'unsupported signed value')
        if token.kind == 'number':
            text = token.text
            number = int(text) if text.isdigit() else float(text)
            return sign * number
        if token.kind == 'string':
            if token.text.startswith('$'):
                raise Unmappable('literal', 'dollar-quoted strings are not '
                                 'builder values')
            return _string(token)
        if token.kind == 'word' and token.text.lower() in {'true', 'false'}:
            return token.text.lower() == 'true'
        if token.kind == 'param':
            return ('param', token.text)
        raise Unmappable('literal',
                         f'unsupported value {token.text!r}')

    def value_entry(self, entry, value):
        if isinstance(value, tuple):
            entry['parameter_id'] = value[1]
            self.parameters.setdefault(value[1], None)
        else:
            entry['value'] = value
        return entry

    def conditions(self):
        filters = []
        while True:
            filters.append(self.condition())
            if self.word('and'):
                self.index += 1
                continue
            return filters

    def condition(self):
        if self.punct('('):
            raise Unmappable('parenthesis', 'grouped predicates are not '
                             'builder filters')
        column = self.column_ref()
        entry = {'column': column}
        if self.word('is'):
            self.index += 1
            negate = False
            if self.word('not'):
                self.index += 1
                negate = True
            self.expect_word('null')
            entry['operator'] = 'is_not_null' if negate else 'is_null'
            return entry
        negate = False
        if self.word('not'):
            self.index += 1
            negate = True
            if not self.word('in'):
                raise Unmappable('operator', 'only NOT IN may follow NOT')
        if self.word('in'):
            self.index += 1
            if not self.punct('('):
                raise Unmappable('subquery', 'IN needs a literal list')
            self.index += 1
            values = []
            while True:
                value = self.literal()
                if isinstance(value, tuple):
                    raise Unmappable('parameter', 'a parameter inside an IN '
                                     'list is not builder state')
                values.append(value)
                if self.punct(','):
                    self.index += 1
                    continue
                break
            if not self.punct(')'):
                raise Unmappable('subquery', 'IN needs a literal list')
            self.index += 1
            entry.update(operator='not_in' if negate else 'in',
                         value=values)
            return entry
        if self.word('between'):
            self.index += 1
            low = self.literal()
            self.expect_word('and')
            high = self.literal()
            if isinstance(low, tuple) or isinstance(high, tuple):
                raise Unmappable('parameter', 'BETWEEN with a parameter is '
                                 'not builder state')
            entry.update(operator='between', value=[low, high])
            return entry
        token = self.take()
        operators = {'=': 'eq', '==': 'eq', '<>': 'ne', '!=': 'ne',
                     '<': 'lt', '<=': 'lte', '>': 'gt', '>=': 'gte'}
        if token.kind != 'punct' or token.text not in operators:
            raise Unmappable('operator',
                             f'unsupported operator {token.text!r}')
        entry['operator'] = operators[token.text]
        value = self.literal()
        if value is None:
            raise Unmappable('literal', 'NULL comparison')
        return self.value_entry(entry, value)

    def expression_list(self):
        values = []
        while True:
            token = self.peek()
            if token is not None and token.kind == 'number' and (
                    token.text.isdigit()):
                self.index += 1
                values.append(('position', int(token.text)))
            else:
                values.append(('column', self.column_ref()))
            if self.punct(','):
                self.index += 1
                continue
            return values

    def order_list(self):
        values = []
        while True:
            token = self.peek()
            if token is not None and token.kind == 'word' and \
                    token.text.lower() in AGGREGATES and self.punct(
                        '(', offset=1):
                key = ('aggregate', self.aggregate())
            elif token is not None and token.kind == 'number' and (
                    token.text.isdigit()):
                self.index += 1
                key = ('position', int(token.text))
            else:
                key = ('column', self.column_ref())
            direction = 'asc'
            if self.word('asc', 'desc'):
                direction = self.take().text.lower()
            if self.word('nulls'):
                raise Unmappable('nulls', 'NULLS FIRST/LAST is not builder '
                                 'state')
            values.append((key, direction))
            if self.punct(','):
                self.index += 1
                continue
            return values


def _alias_id(alias, loss, fallback_context):
    """Builder aliases are portable identifiers; keep or report."""
    from pgadmin.cdeadmin.semantic_models.models import _ID
    if _ID.fullmatch(alias or ''):
        return alias
    renamed = output_id(alias)
    loss.append(_loss(
        'alias_renamed', 'warning',
        f'output name {alias!r} is not a portable identifier; builder uses '
        f'{renamed!r}'))
    return renamed


def _map(parser_result, parser, relation, loss):
    items, where, group_by, order_by, limit = parser_result
    aggregates = [i for i in items if i['kind'] == 'aggregate']
    plain = [i for i in items if i['kind'] == 'column']
    positions = {}
    for number, item in enumerate(items, start=1):
        positions[number] = item
    builder = {'source': {'relation': relation}, 'filters': where}
    # select-list order is columns first, aggregates last in builder SQL
    if aggregates:
        seen_aggregate = False
        for item in items:
            if item['kind'] == 'aggregate':
                seen_aggregate = True
            elif seen_aggregate:
                loss.append(_loss(
                    'column_order', 'warning',
                    'builder output lists grouped columns before '
                    'aggregates; the original select order differs'))
                break
    grouped = []
    for kind, value in group_by:
        if kind == 'position':
            target = positions.get(value)
            if target is None or target['kind'] != 'column':
                raise Unmappable('group_by', 'GROUP BY position is not a '
                                 'plain selected column')
            grouped.append(target['column'])
        else:
            grouped.append(value)
    if group_by and not aggregates:
        raise Unmappable('group_by', 'GROUP BY without an aggregate is not '
                         'builder state')
    if aggregates:
        selected = [i['column'] for i in plain]
        if sorted(set(selected)) != sorted(set(selected) & set(grouped)):
            raise Unmappable(
                'ungrouped', 'selected columns that are not grouped need '
                'an engine-specific bare-column rule')
        extra = [c for c in grouped if c not in selected]
        if extra:
            loss.append(_loss(
                'group_column_added', 'warning',
                'grouped column(s) ' + ', '.join(extra) + ' are output by '
                'the builder but were not selected'))
        aliases = {i['column']: i.get('alias') for i in plain}
        builder['group_by'] = []
        for column in dict.fromkeys(grouped):
            entry = {'column': column}
            if aliases.get(column):
                entry['alias'] = _alias_id(aliases[column], loss, 'group')
            builder['group_by'].append(entry)
        builder['columns'] = []
        builder['aggregations'] = []
        used = set()
        for item in aggregates:
            entry = {'function': item['function']}
            if 'column' in item:
                entry['column'] = item['column']
            if item.get('alias'):
                entry['alias'] = _alias_id(item['alias'], loss, 'agg')
            else:
                loss.append(_loss(
                    'aggregate_alias_generated', 'info',
                    'unaliased aggregate gets a generated output name'))
            key = (entry['function'], entry.get('column'))
            used.add(key)
            builder['aggregations'].append(entry)
    else:
        builder['columns'] = []
        for item in plain:
            entry = {'column': item['column']}
            if item.get('alias'):
                entry['alias'] = _alias_id(item['alias'], loss, 'column')
            builder['columns'].append(entry)
        builder['group_by'], builder['aggregations'] = [], []
    # order by -----------------------------------------------------------
    outputs = {}
    if aggregates:
        for entry in builder['group_by']:
            outputs.setdefault(entry['column'], entry.get('alias') or
                               output_id(entry['column']))
            outputs.setdefault(entry.get('alias'), outputs[entry['column']])
        for entry in builder['aggregations']:
            default = entry['function'] + (
                '_' + output_id(entry['column']) if entry.get('column')
                else '')
            outputs.setdefault(entry.get('alias') or default,
                               entry.get('alias') or default)
    else:
        for entry in builder['columns']:
            outputs.setdefault(entry['column'], entry['column'])
            if entry.get('alias'):
                outputs.setdefault(entry['alias'], entry['alias'])
    builder['order_by'] = []
    for (kind, value), direction in order_by:
        if kind == 'position':
            target = positions.get(value)
            if target is None:
                raise Unmappable('order_by', 'ORDER BY position is out of '
                                 'range')
            kind, value = (('aggregate', target) if target['kind'] ==
                           'aggregate' else ('column', target['column']))
        if kind == 'aggregate':
            match = next((e for e in builder['aggregations']
                          if e['function'] == value['function'] and
                          e.get('column') == value.get('column')), None)
            if match is None:
                raise Unmappable('order_by', 'ORDER BY aggregate is not in '
                                 'the select list')
            default = match['function'] + (
                '_' + output_id(match['column']) if match.get('column')
                else '')
            column = match.get('alias') or default
        else:
            column = value
            if aggregates and column not in outputs:
                raise Unmappable('order_by', f'ORDER BY {column!r} is not '
                                 'an output column')
            if not aggregates and column not in outputs:
                raise Unmappable('order_by', f'ORDER BY {column!r} is not '
                                 'a selected column')
        builder['order_by'].append({'column': column, 'direction': direction})
    # limit --------------------------------------------------------------
    if limit is None:
        loss.append(_loss(
            'implicit_limit', 'warning',
            'the statement has no LIMIT; builder state applies the default '
            'row cap of 500, so a larger result is truncated'))
    elif limit < 1:
        raise Unmappable('limit', 'LIMIT 0 is not builder state')
    elif limit > 10000:
        loss.append(_loss('limit_clamped', 'warning',
                          'LIMIT above 10000 is clamped to 10000'))
        builder['limit'] = 10000
    if limit is not None and 'limit' not in builder:
        builder['limit'] = limit
    return builder


def sql_to_question(sql, name='Converted question', parameter_types=None,
                    collection_id=None):
    """Convert ``sql`` into ``{fidelity, question, loss, ...}``.

    ``fidelity`` is ``exact`` (builder state reproduces the statement),
    ``lossy`` (mapped, with differences listed in ``loss``) or ``none``
    (kept as a raw ``sql`` question; ``loss`` lists the blocking reasons).
    """
    if not isinstance(sql, str) or not sql.strip():
        raise BIError('sql must be non-empty text')
    parameter_types = dict(parameter_types or {})
    tokens = significant(tokenize(sql))
    body = list(tokens)
    while body and body[-1].kind == 'punct' and body[-1].text == ';':
        body.pop()
    names = list(dict.fromkeys(t.text for t in tokens if t.kind == 'param'))
    loss, blockers = [], []
    comments = any(t.kind == 'comment' for t in tokenize(sql))
    for token in body:
        if token.kind == 'word' and token.text.lower() in _BLOCKERS:
            reason = _BLOCKERS[token.text.lower()]
            # COUNT(DISTINCT x) is mapped; only report DISTINCT elsewhere
            blockers.append((token.text.lower(), reason))
    if any(t.kind == 'punct' and t.text == ';' for t in body):
        blockers.append(('statements', 'multiple statements'))
    if sum(1 for t in body if t.kind == 'punct' and t.text == '(') > \
            sum(1 for t in body if t.kind == 'word' and
                t.text.lower() in {'count', 'sum', 'min', 'max', 'avg',
                                   'in'}):
        blockers.append(('subquery', 'parentheses outside aggregates and '
                         'IN lists are not builder state'))
    if sum(1 for t in body if t.kind == 'word' and
           t.text.lower() == 'select') > 1:
        blockers.append(('subquery', 'subqueries are not expressible in '
                         'builder state'))
    parser = _Parser(body, parameter_types)
    question = None
    builder = None
    try:
        parsed = parser.parse()
        # COUNT(DISTINCT x) is the one admitted DISTINCT
        blockers = [b for b in blockers if not (
            b[0] == 'distinct' and any(
                i['kind'] == 'aggregate' and
                i['function'] == 'count_distinct' for i in parsed[0]))]
        if blockers:
            raise Unmappable(blockers[0][0], blockers[0][1])
        builder = _map(parsed, parser, parser.relation, loss)
        parameters = [{
            'id': pid, 'name': pid,
            'type': parameter_types.get(pid, 'string'), 'required': True,
        } for pid in parser.parameters]
        for pid in parser.parameters:
            if pid not in parameter_types:
                loss.append(_loss(
                    'parameter_type_assumed', 'info',
                    f'parameter {pid!r} is declared as string; pass '
                    'parameter_types to override'))
        if comments:
            loss.append(_loss('comments_dropped', 'info',
                              'SQL comments are not kept in builder state'))
        question = validate_question({
            'name': name, 'collection_id': collection_id,
            'parameters': parameters,
            'query': {'kind': 'builder', 'builder': builder},
        })
    except Unmappable as exc:
        for code, reason in dict.fromkeys(blockers + [(exc.code,
                                                       exc.detail)]):
            loss.append(_loss(f'unmappable_{code}', 'blocking', reason))
        builder = None
    except BIError as exc:
        loss.append(_loss('rejected_by_validation', 'blocking', str(exc)))
        builder = None
    if builder is None:
        question = validate_question({
            'name': name, 'collection_id': collection_id,
            'parameters': [{'id': pid, 'name': pid,
                            'type': parameter_types.get(pid, 'string'),
                            'required': True} for pid in names],
            'query': {'kind': 'sql', 'sql': sql},
        })
        fidelity = 'none'
    else:
        fidelity = 'lossy' if any(
            item['severity'] == 'warning' for item in loss) else 'exact'
    return {
        'fidelity': fidelity,
        'mapped': builder is not None,
        'question': question,
        'builder': copy.deepcopy(builder),
        'loss': loss,
    }
