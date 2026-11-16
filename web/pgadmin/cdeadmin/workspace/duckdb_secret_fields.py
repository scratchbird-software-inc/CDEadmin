"""Typed, bounded private native secret constants; never parse JSON controls."""
import math
import re


def properties(rows):
    if not isinstance(rows, list) or len(rows) > 16384:
        raise ValueError('Private secret property tree exceeds its node budget')
    nodes, children = {}, {}
    for row in rows:
        identity, parent = row.get('node_id'), row.get('parent_id', '')
        if (not isinstance(identity, str) or not 1 <= len(identity) <= 128 or identity in nodes or
                not isinstance(parent, str) or len(parent) > 128):
            raise ValueError('Private secret nodes require distinct bounded identities and valid parents')
        nodes[identity] = row
        children.setdefault(parent, []).append(identity)
    if any(parent and parent not in nodes for parent in children):
        raise ValueError('Private secret node parent is unavailable')
    visited = set()
    def value(identity, depth=0):
        if depth > 32 or identity in visited:
            raise ValueError('Private secret property tree is cyclic or exceeds its depth budget')
        visited.add(identity)
        row = nodes[identity]
        kind = row['kind']
        nested = children.get(identity, [])
        if kind not in {'LIST', 'MAP'} and nested:
            raise ValueError('Private scalar secret nodes cannot have children')
        if kind in {'NULL', 'LIST', 'MAP'}:
            if row.get('value') not in (None, '') or row.get('boolean_value') not in (None, ''):
                raise ValueError('Private secret containers and NULL have no scalar value')
            if kind == 'NULL':
                return None
            if kind == 'MAP':
                return mapping(nested, depth + 1)
            if any(nodes[child].get('key') not in (None, '') for child in nested):
                raise ValueError('Private secret list children do not have map keys')
            return [value(child, depth + 1) for child in nested]
        if kind == 'BOOLEAN':
            if row.get('value') not in (None, '') or row.get('boolean_value') not in {'TRUE', 'FALSE'}:
                raise ValueError('Select a typed private secret Boolean')
            return row['boolean_value'] == 'TRUE'
        if row.get('boolean_value') not in (None, ''):
            raise ValueError('A private scalar cannot carry an unrelated Boolean choice')
        text = row.get('value')
        if not isinstance(text, str):
            raise ValueError('Private secret scalar requires its typed value')
        if kind == 'TEXT':
            return text
        if kind == 'INTEGER':
            if not re.fullmatch(r'0|-?[1-9][0-9]*', text):
                raise ValueError('Private secret integer requires canonical decimal text')
            try:
                return int(text)
            except ValueError:
                raise ValueError('Private secret integer exceeds the input conversion budget') from None
        if kind == 'DOUBLE':
            try:
                number = float(text)
            except (ValueError, OverflowError):
                raise ValueError('Private secret double requires finite numeric text') from None
            if not math.isfinite(number):
                raise ValueError('Private secret double requires finite numeric text')
            return number
        raise ValueError('Private secret scalar kind is unavailable')
    def mapping(identities, depth=0, root=False):
        result = {}
        for identity in identities:
            key = nodes[identity].get('key')
            if not isinstance(key, str) or root and not key or key in result:
                raise ValueError('Private secret property/map keys must be explicit and distinct')
            result[key] = value(identity, depth)
        return result
    result = mapping(children.get('', []), root=True)
    if len(visited) != len(nodes):
        raise ValueError('Private secret property tree has unreachable or cyclic nodes')
    return result


def expressions(rows):
    result, names = {}, set()
    for row in rows:
        name = row['name']
        if name.casefold() in names:
            raise ValueError('Private secret expression names must be distinct')
        names.add(name.casefold())
        result[name] = row['expression']
    return result
