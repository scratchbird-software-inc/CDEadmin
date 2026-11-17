"""Plan visual relation instances before emitting a FROM/JOIN clause."""
from collections import defaultdict
from collections.abc import Mapping
import re


_REVERSE = {'INNER': 'INNER', 'LEFT': 'RIGHT', 'RIGHT': 'LEFT',
            'FULL': 'FULL', 'CROSS': 'CROSS'}
_QUALIFIER = re.compile(r'(?:"((?:[^"]|"")+)"|`((?:[^`]|``)+)`|([\w$]+))\s*\.')
_LITERALS = re.compile(r"'(?:[^']|'')*'|--[^\n]*|/\*[\s\S]*?\*/")


class VisualJoinPlan:
    def __init__(self, tables, joins):
        self.tables = []
        self.by_id = {}
        self.references = {}
        self.names = defaultdict(list)
        bindings = set()
        for index, value in enumerate(tables):
            if not isinstance(value, Mapping) or not str(value.get('name') or '').strip():
                raise ValueError('Select a named visual relation')
            table = dict(value)
            tid = str(table.get('id') or f'tbl_{index + 1}')
            name = str(table.get('name') or tid)
            alias = str(table.get('alias') or '').strip()
            if tid in self.by_id:
                raise ValueError(f'Duplicate visual relation identity: {tid}')
            binding = alias or name
            if binding in bindings:
                raise ValueError(f'Each relation needs a unique alias: {binding}')
            bindings.add(binding)
            table.update(id=tid, name=name, alias=alias)
            self.tables.append(table)
            self.by_id[tid] = table
            self.names[name].append(tid)
        for table in self.tables:
            for reference in (table['id'], table['alias']):
                if not reference:
                    continue
                if reference in self.references and self.references[reference] != table['id']:
                    raise ValueError(f'Ambiguous relation identity or alias: {reference}')
                self.references[reference] = table['id']
        for name, tids in self.names.items():
            if len(tids) == 1 and name not in self.references:
                self.references[name] = tids[0]
        self.joins = []
        for value in joins:
            if not isinstance(value, Mapping):
                raise ValueError('Select a structured join relationship')
            join = dict(value)
            left = self.resolve(join.get('left_table'))
            right = self.resolve(join.get('right_table'))
            if left == right:
                raise ValueError('A self join needs two relation instances with distinct aliases')
            kind = str(join.get('join_type') or 'INNER').strip().upper()
            if kind.endswith(' OUTER'):
                kind = kind[:-6]
            if kind not in _REVERSE:
                raise ValueError(f'Unsupported join type: {kind}')
            if kind != 'CROSS' and not str(join.get('custom_on') or '').strip() and (
                    not join.get('left_column') or not join.get('right_column')):
                raise ValueError('Select both join columns or supply an ON predicate')
            join.update(left_table=left, right_table=right, join_type=kind)
            self.joins.append(join)

    def resolve(self, reference):
        token = str(reference or '')
        if token in self.references:
            return self.references[token]
        if len(self.names.get(token, ())) > 1:
            raise ValueError(f'Ambiguous relation name; use its instance identity or alias: {token}')
        raise ValueError(f'Unknown join relation: {token}')

    def qualifier(self, tid, quote):
        table = self.by_id[tid]
        return quote(table['alias'] or table['name'])

    def render(self, quote, relation):
        """Each instance appears once; predicates only use introduced aliases.

        Multiple predicates on one relationship share an ON clause. Inner
        cycle constraints become WHERE predicates. Cyclic outer relationships
        require explicit nesting rather than an arbitrary semantic rewrite.
        """
        groups = {}
        adjacent = defaultdict(set)
        for join in self.joins:
            left, right, kind = join['left_table'], join['right_table'], join['join_type']
            pair = tuple(sorted((left, right)))
            canonical_kind = kind if pair[0] == left else _REVERSE[kind]
            if pair in groups and groups[pair]['canonical_kind'] != canonical_kind:
                raise ValueError('Conflicting join types for the same relation pair')
            group = groups.setdefault(pair, {'left': left, 'right': right, 'kind': kind,
                'canonical_kind': canonical_kind, 'predicates': [], 'dependencies': {left, right}})
            if kind != 'CROSS':
                predicate = str(join.get('custom_on') or '').strip() or (
                    f'{self.qualifier(left, quote)}.{quote(str(join["left_column"]))} = '
                    f'{self.qualifier(right, quote)}.{quote(str(join["right_column"]))}')
                if predicate not in group['predicates']:
                    group['predicates'].append(predicate)
                # Recognise references to other known canvas instances in a
                # custom ON without treating string literals as dependencies.
                for match in _QUALIFIER.finditer(_LITERALS.sub(' ', predicate)):
                    token = next(part for part in match.groups() if part is not None)
                    token = token.replace('""', '"').replace('``', '`')
                    if token in self.references or token in self.names:
                        group['dependencies'].add(self.resolve(token))
            for tid in group['dependencies']:
                adjacent[left].add(tid)
                adjacent[tid].add(left)

        components = []
        seen = set()
        extra_where = []
        for table in self.tables:
            root = table['id']
            if root in seen:
                continue
            component, queue = set(), [root]
            while queue:
                tid = queue.pop()
                if tid not in component:
                    component.add(tid)
                    queue.extend(adjacent[tid] - component)
            seen.update(component)
            pending = [g for g in groups.values() if g['left'] in component]
            introduced = {root}
            lines = [relation(self.by_id[root])]
            while pending:
                progressed = False
                for group in list(pending):
                    left, right = group['left'], group['right']
                    if not group['dependencies'] <= introduced | {left, right}:
                        continue
                    left_present, right_present = left in introduced, right in introduced
                    if not left_present and not right_present:
                        continue
                    predicates = group['predicates']
                    condition = (' AND '.join(f'({p})' for p in predicates)
                                 if len(predicates) > 1 else predicates[0] if predicates else '')
                    if left_present and right_present:
                        if group['kind'] not in {'INNER', 'CROSS'}:
                            raise ValueError('Cyclic outer joins require an explicitly nested join model')
                        if condition:
                            extra_where.append(condition)
                    else:
                        tid = right if left_present else left
                        kind = group['kind'] if left_present else _REVERSE[group['kind']]
                        if not left_present and group['kind'] == 'LEFT':
                            # Keep a reversed LEFT edge as native LEFT syntax,
                            # including on supported SQLite versions before
                            # RIGHT JOIN was introduced. Group the whole prefix
                            # so its null-preservation semantics stay intact.
                            prefix = lines[0] if len(introduced) == 1 else '(\n' + '\n'.join(lines) + '\n)'
                            lines = [relation(self.by_id[tid]), f'LEFT JOIN {prefix} ON {condition}']
                        else:
                            text = f'{kind} JOIN {relation(self.by_id[tid])}'
                            if kind != 'CROSS':
                                text += f' ON {condition}'
                            lines.append(text)
                        introduced.add(tid)
                    pending.remove(group)
                    progressed = True
                    break
                if not progressed:
                    # An ON can depend on an otherwise unrelated relation;
                    # make that dependency visible before the ON is emitted.
                    needed = set().union(*(g['dependencies'] - introduced for g in pending))
                    tid = next(t['id'] for t in self.tables if t['id'] in needed)
                    lines.append(f'CROSS JOIN {relation(self.by_id[tid])}')
                    introduced.add(tid)
            components.append((lines, len(introduced)))
        if not components:
            return '', extra_where
        lines = ['FROM ' + '\n'.join(components[0][0])]
        for component, relation_count in components[1:]:
            text = component[0] if relation_count == 1 else '(\n' + '\n'.join(component) + '\n)'
            lines.append('CROSS JOIN ' + text)
        return '\n'.join(lines), extra_where
