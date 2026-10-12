"""Capture native UNION validity before Arrow discards its parent null bit.

Projection operates on the native relation. A list-lambda binds each original
value once, including volatile expressions. No original SQL is replayed.
"""


def contains_union(kind):
    if kind.id == 'union':
        return True
    if kind.id in {'list', 'array', 'struct', 'map'}:
        return any(contains_union(child) for _, child in kind.children
                   if hasattr(child, 'id'))
    return False


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def literal(name):
    return "'" + name.replace("'", "''") + "'"


def capture(expression, kind, counter):
    if not contains_union(kind):
        return expression
    counter[0] += 1
    variable = '__cde_union_' + str(counter[0])
    children = dict(kind.children)
    if kind.id in {'list', 'array'}:
        body = capture(variable, children['child'], counter)
        return f'list_transform({expression}, lambda {variable}: {body})'
    if kind.id == 'map':
        key = capture(variable + '.key', children['key'], counter)
        value = capture(variable + '.value', children['value'], counter)
        return ('map_from_entries(list_transform(map_entries(' + expression +
                f'), lambda {variable}: struct_pack(key := {key}, '
                f'value := {value})))')
    if kind.id == 'union':
        members = []
        for name, child in kind.children[1:]:
            source = f'union_extract({variable}, {literal(name)})'
            members.append(quote(name) + ' := ' +
                           capture(source, child, counter))
        body = ('struct_pack(__tag := CAST(union_tag(' + variable +
                ') AS VARCHAR), __members := struct_pack(' +
                ', '.join(members) + '))')
    else:
        members = [quote(name) + ' := ' + capture(
            variable + '.' + quote(name), child, counter)
            for name, child in kind.children]
        body = 'struct_pack(' + ', '.join(members) + ')'
    body = f'CASE WHEN {variable} IS NULL THEN NULL ELSE {body} END'
    return f'list_transform([{expression}], lambda {variable}: {body})[1]'


def project(relation):
    kinds = list(relation.types)
    if not any(contains_union(kind) for kind in kinds):
        return relation, kinds
    expressions = [capture(f'#{index + 1}', kind, [0]) +
                   f' AS __cde_column_{index}'
                   for index, kind in enumerate(kinds)]
    return relation.project(', '.join(expressions)), kinds


def restore(value, kind):
    if value is None or not contains_union(kind):
        return value
    children = dict(kind.children)
    if kind.id == 'union':
        tag = value['__tag']
        return {'tag': tag, 'type_code': [
            name for name, _ in kind.children[1:]].index(tag),
            'value': restore(value['__members'][tag], children[tag])}
    if kind.id in {'list', 'array'}:
        return [restore(item, children['child']) for item in value]
    if kind.id == 'struct':
        return {name: restore(value[name], child)
                for name, child in kind.children}
    if kind.id == 'map':
        return {'encoding': 'map', 'entries': [
            [restore(key, children['key']), restore(item, children['value'])]
            for key, item in value['entries']]}
    return value
