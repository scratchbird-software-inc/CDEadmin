"""Preserve the named native projection contract of an FTS content view."""
from copy import deepcopy

from .sqlite_fts_rebind import equal,quote
from .sqlite_native_rebind import tokens
from ..providers.sqlite.modules import declaration,option,unquote


def content_views(baseline):
    views={}
    for row in baseline['rows'].values():
        if row['kind']!='fts-table' or row['path'][0]!='main' or row['system']!='false':continue
        source=row['native'].get('ddl');native=declaration(source)
        if not native or native[1].lower() not in {'fts4','fts5'}:continue
        content=option(source,'content')
        if not content:continue
        matches=[view for view in baseline['rows'].values() if view['kind']=='view' and
            view['path'][0]=='main' and view['system']=='false' and equal(view['name'],content)]
        if len(matches)>1:raise ValueError('Native FTS content view identity is ambiguous')
        if matches:views[matches[0]['resource_id']]=matches[0]
    return views


def preserve_columns(row):
    """Extend only an admitted CREATE VIEW header; leave its SELECT exact."""
    source=row['native']['ddl'];parts=tokens(source)
    try:
        position=next(index for index,item in enumerate(parts) if item[2].upper()=='VIEW')+1
        if [item[2].upper() for item in parts[position:position+3]]==['IF','NOT','EXISTS']:position+=3
        if parts[position+1][2]=='.':position+=2
        name=parts[position][2]
        # Bracket identifiers have no doubled-opening-bracket escape. Keep
        # literal '[' characters in a native name instead of collapsing them.
        observed=name[1:-1] if name.startswith('[') and name.endswith(']') else unquote(name)
        if not equal(observed,row['name']):raise ValueError()
        following=parts[position+1][2]
        if following=='(':return deepcopy(row)
        if following.upper()!='AS':raise ValueError()
        names=[column['name'] for column in row['native']['columns']]
        if not names:raise ValueError()
    except (ValueError,KeyError,IndexError,StopIteration):
        raise ValueError('Native FTS content view declaration cannot retain its projection names') from None
    result=deepcopy(row);end=parts[position][1]
    result['native']['ddl']=source[:end]+'('+','.join(quote(name) for name in names)+')'+source[end:]
    return result


def changed_columns(baseline,generated):
    result=set()
    for identity,row in content_views(baseline).items():
        current=generated['rows'].get(identity)
        if current is None:raise ValueError('Native rename removed an FTS content view')
        before=row['native']['columns'];after=current['native']['columns']
        if len(before)!=len(after):raise ValueError('Native rename changed an FTS content projection width')
        if [column['name'] for column in before]!=[column['name'] for column in after]:result.add(identity)
    return result
