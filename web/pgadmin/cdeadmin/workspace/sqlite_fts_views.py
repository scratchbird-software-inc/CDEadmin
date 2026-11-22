"""Preserve the named native projection contract of an FTS content view (SQ-AUD-06 namespace-aware)."""
from copy import deepcopy

from .sqlite_fts_rebind import equal, quote
from .sqlite_native_rebind import tokens
from ..providers.sqlite.modules import declaration, option, unquote


def content_views(baseline, *, namespace='main'):
    views = {}
    for row in baseline['rows'].values():
        if row['kind'] != 'fts-table' or row['path'][0] != namespace or row['system'] != 'false':
            continue
        source = row['native'].get('ddl')
        native = declaration(source)
        if not native or native[1].lower() not in {'fts4', 'fts5'}:
            continue
        content = option(source, 'content')
        if not content:
            continue
        if namespace != 'temp':
            temp_shadows = [
                r for r in baseline['rows'].values()
                if r['kind'] in {'table', 'view', 'fts-table', 'virtual-table'}
                and r['path'][0] == 'temp'
                and equal(r['name'], content)
            ]
            if temp_shadows:
                raise ValueError(
                    f'TEMP object {temp_shadows[0]["name"]!r} shadows external-content FTS target {content!r} in namespace {namespace!r}'
                )
        matches = [
            view for view in baseline['rows'].values()
            if view['kind'] == 'view'
            and view['path'][0] == namespace
            and view['system'] == 'false'
            and equal(view['name'], content)
        ]
        if len(matches) > 1:
            raise ValueError('Native FTS content view identity is ambiguous')
        if matches:
            views[matches[0]['resource_id']] = matches[0]
    return views


def preserve_columns(row):
    """Extend only an admitted CREATE VIEW header; leave its SELECT exact."""
    source = row['native']['ddl']
    parts = tokens(source)
    try:
        position = next(index for index, item in enumerate(parts) if item[2].upper() == 'VIEW') + 1
        if [item[2].upper() for item in parts[position:position + 3]] == ['IF', 'NOT', 'EXISTS']:
            position += 3
        if parts[position + 1][2] == '.':
            position += 2
        name = parts[position][2]
        observed = name[1:-1] if name.startswith('[') and name.endswith(']') else unquote(name)
        if not equal(observed, row['name']):
            raise ValueError()
        following = parts[position + 1][2]
        if following == '(':
            return deepcopy(row)
        if following.upper() != 'AS':
            raise ValueError()
        names = [column['name'] for column in row['native']['columns']]
        if not names:
            raise ValueError()
    except (ValueError, KeyError, IndexError, StopIteration):
        raise ValueError('Native FTS content view declaration cannot retain its projection names') from None
    result = deepcopy(row)
    end = parts[position][1]
    result['native']['ddl'] = source[:end] + '(' + ','.join(quote(name) for name in names) + ')' + source[end:]
    return result


def changed_columns(baseline, generated, *, namespace='main'):
    result = set()
    for identity, row in content_views(baseline, namespace=namespace).items():
        current = generated['rows'].get(identity)
        if current is None:
            raise ValueError('Native rename removed an FTS content view')
        before = row['native']['columns']
        after = current['native']['columns']
        if len(before) != len(after):
            raise ValueError('Native rename changed an FTS content projection width')
        if [column['name'] for column in before] != [column['name'] for column in after]:
            result.add(identity)
    return result
