"""Native view/index/trigger replacement without executing preview DDL."""
from copy import deepcopy
import re

from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest
from .sqlite_schema_plan import _source, _quote, _definition, _compile_exact
from ..providers.sqlite.provider import _resource_id

DEPENDENCY_KINDS = {'table', 'view', 'index', 'trigger', 'fts-table', 'virtual-table'}


def trigger_event(source):
    """Read a native SQLite trigger's defining event, without scanning its body."""
    import sqlparse
    from sqlparse.tokens import Comment
    cleaned = ''.join(' ' if token.ttype in Comment else token.value
                      for statement in sqlparse.parse(source) for token in statement.flatten())
    identifier = r'''(?:"(?:[^"]|"")*"|`(?:[^`]|``)*`|\[[^\]]*\]|'(?:[^']|'')*'|[A-Za-z_\u0080-\U0010ffff][A-Za-z_0-9$\u0080-\U0010ffff]*)'''
    pattern = (r'^\s*CREATE\s+(?:(?:TEMP|TEMPORARY)\s+)?TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?' +
               identifier + r'(?:\s*\.\s*' + identifier + r')?\s+' +
               r'(?:(?:BEFORE|AFTER|INSTEAD\s+OF)\s+)?(INSERT|UPDATE|DELETE)\b')
    match = re.match(pattern, cleaned, re.I)
    if match is None:
        raise ValueError('SQLite trigger event could not be observed')
    return match[1].upper()


def dependencies(rows, excluded):
    return {identity: digest(_definition(row)) for identity, row in rows.items()
            if identity != excluded and row['kind'] in DEPENDENCY_KINDS and row['system'] == 'false'}


def normalized(source):
    return re.sub(r'^(\s*CREATE\s+(?:UNIQUE\s+)?(?:VIEW|INDEX|TRIGGER)\s+)"main"\.',
                  r'\1', source.strip().rstrip(';'), count=1, flags=re.I)


def matches(wanted, observed):
    return (all(wanted.get(key) == observed.get(key) for key in ('resource_id', 'kind', 'path', 'name', 'system')) and
            normalized(wanted['native']['ddl']) == normalized(observed['native'].get('ddl') or '') and
            _equal(wanted['native'].get('catalog_metadata'), observed['native'].get('catalog_metadata')) and
            (wanted['kind']!='view' or (_equal(wanted['native'].get('columns'),observed['native'].get('columns')) and
                sorted((item['resource_id'],normalized(item['ddl'])) for item in wanted['native'].get('triggers',[]))==
                sorted((item['resource_id'],normalized(item['ddl'])) for item in observed['native'].get('triggers',[])))))


def validate_view_children(view,desired):
    """The defining SELECT and every individual desired child must agree."""
    for kind,field in (('column','columns'),('trigger','triggers')):
        items=view['native'].get(field)
        if not isinstance(items,list):raise ValueError('Desired SQLite view child facts are unavailable')
        ids={item.get('resource_id') for item in items}
        rows={identity:row for identity,row in desired['rows'].items() if row['kind']==kind and row['path'][:2]==view['path']}
        if len(ids)!=len(items) or ids!=set(rows):raise ValueError('Desired SQLite view must retain every defined child record')
        for item in items:
            row=rows[item['resource_id']]
            if (row['path']!=[*view['path'],item.get('name')] or row['system']!='false' or
                    item['resource_id']!=_resource_id(kind,view['path'],item.get('name'))):
                raise ValueError('Desired SQLite view child identity is inconsistent')
            if kind=='column' and not _equal({key:value for key,value in item.items() if key not in {'resource_id','name'}},row['native'].get('catalog_metadata')):
                raise ValueError('Desired SQLite view column facts disagree')
            if kind=='trigger' and normalized(item.get('ddl') or '')!=normalized(row['native'].get('ddl') or ''):
                raise ValueError('Desired SQLite view trigger definitions disagree')


def plan_replace(before, after, baseline, connection=None, *, probe_name=None):
    kind, path, identity = before['kind'], before['path'], before['resource_id']
    if (kind not in {'view','index', 'trigger'} or after['kind'] != kind or
            before['system'] != 'false' or before['native'].get('system_object') is not False or
            len(path) != (2 if kind=='view' else 3) or path[0] != 'main' or path[-1] != before['name'] or
            after['resource_id'] != identity or after['path'] != path or
            after['name'] != before['name'] or identity != _resource_id(kind, path[:-1], path[-1]) or
            not isinstance(before['native'].get('ddl'), str) or not before['native']['ddl']):
        raise ValueError('SQLite replacement requires an observed explicit user view, index or trigger')
    source = _source(after)
    if normalized(source) == normalized(before['native']['ddl']):
        raise ValueError('SQLite replacement requires a changed native definition')
    owners = [row for row in baseline['rows'].values() if row['path'] == path[:2] and
              row['kind'] in ({'table'} if kind == 'index' else {'table', 'view'}) and row['system'] == 'false']
    if len(owners) != 1:
        raise ValueError('SQLite replacement requires one retained ordinary table or trigger view')
    # The service recomputes the plan at review time. Stable names keep its
    # execution digest bound to the displayed SQL when native facts agree.
    probe_name = probe_name or '__cde_replace_' + digest({'before':_definition(before),'after':_definition(after)})[:32]
    if not re.fullmatch(r'__cde_replace_[0-9a-f]{32}', probe_name):
        raise ValueError('SQLite replacement probe identity is invalid')
    # Preparing CREATE under the existing name would fail (or IF NOT EXISTS
    # would skip compilation). Change only the admitted declaration name.
    pattern = re.compile(r'^(\s*CREATE\s+(?:UNIQUE\s+)?' + kind + r'\s+)' +
                         re.escape('"main".' + _quote(before['name'])), re.I)
    probe_source = pattern.sub(lambda match: match[1] + '"main".' + _quote(probe_name), source, count=1)
    if probe_source == source:
        raise ValueError('SQLite replacement declaration cannot be bound exactly')
    if connection is not None:
        probe = deepcopy(after)
        probe.update(name=probe_name, path=[*path[:-1], probe_name],
                     resource_id=_resource_id(kind, path[:-1], probe_name))
        probe['native']['ddl'] = probe_source
        _compile_exact(connection, probe, _source(probe))
    drop = 'DROP ' + kind.upper() + ' "main".' + _quote(before['name'])
    stages = [drop, source]
    if kind=='view':
        # DROP VIEW also drops its native INSTEAD OF triggers. Restore their
        # observed definitions before later admitted trigger replacements run.
        # No view DML is stepped between these schema stages.
        stages.extend(item['ddl'] for item in before['native'].get('triggers',[]))
    return {'operation':'replace', 'resource_id':identity, 'name':before['name'], 'kind':kind,
            'source':'\n'.join(stage.rstrip(';') + ';' for stage in stages),
            'stages':stages, 'probe_name':probe_name,
            'baseline_sha256':digest(_definition(before)), 'desired_sha256':digest(_definition(after)),
            'dependency_sha256':dependencies(baseline['rows'], identity),
            'warnings':['Native DROP and CREATE run in one owned SQLite write transaction.',
                        *(['Existing view triggers are recreated before later trigger changes. Final view columns and all view/trigger bindings are checked before commit.'] if kind=='view' else []),
                        'Native unique-index checks and trigger binding checks can refuse the change; rollback restores the original definition.']}
