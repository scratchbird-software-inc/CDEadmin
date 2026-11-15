"""Typed object edits into the existing reviewed native SQLite DDN pipeline.

Generation reproduces schema only in an empty prototype. It never copies live
rows or applies the result. The existing three-way preview/review/apply owns
identity checks, dependency decisions, data conversion and atomic rollback.
"""
from copy import deepcopy
from .sqlite_schema_plan import _scope, _quote
from .sqlite_columns import _clauses, _modeled
from .sqlite_retained_schema import _prototype
from ..providers.sqlite.provider import ADMINISTRATION, _resources
from ..providers.sqlite.declarations import tokens, fold

COLUMN_FIELDS = {'name','type','nullable','primary_key','unique','autoincrement',
    'default','collation','check_expression','generated_storage','generated_expression',
    'not_null_conflict','unique_conflict','primary_key_conflict','_id'}


def generate(baseline, identity, operation, fields):
    _scope(baseline)
    before=baseline['rows'].get(identity)
    kind={'rebuild':'table','replace':'view'}.get(operation)
    if (kind is None or before is None or before['kind']!=kind or before['system']!='false'
            or before['path']!=['main',before['name']] or not isinstance(fields,dict)):
        raise ValueError('Select one observed ordinary SQLite main-file table or view')
    name=before['name'];prefix='CREATE '+kind.upper()+' "main".'+_quote(name)
    if kind=='view':
        if set(fields)-{'query','column_names'}:raise ValueError('Unknown view replacement field')
        query=fields.get('query')
        if not isinstance(query,str) or not query.strip() or '\x00' in query or len(query.encode())>2*1024*1024:
            raise ValueError('One bounded native view SELECT is required')
        names=fields.get('column_names',[])
        if not isinstance(names,list) or len(names)>2000:raise ValueError('Select typed view column aliases')
        aliases=[]
        for row in names:
            if not isinstance(row,dict) or set(row)-{'name','_id'}:raise ValueError('Each view alias requires its name')
            aliases.append(_quote(row.get('name')))
        source=prefix+(' ('+','.join(aliases)+')' if aliases else '')+' AS '+query
    else:
        if set(fields)!={'columns'}:raise ValueError('Table rebuild requires the complete typed column grid')
        columns=fields['columns']
        if not isinstance(columns,list) or not 1<=len(columns)<=2000:raise ValueError('Select one through 2000 desired columns')
        declarations=[]
        for column in columns:
            if not isinstance(column,dict) or set(column)-COLUMN_FIELDS:raise ValueError('Unknown table rebuild column field')
            declarations.append(ADMINISTRATION._column_definition(column))
        # Preserve table-level constraints verbatim. Inline constraints are
        # represented by the complete desired column grid, not guessed away.
        for clause in _clauses(before['native']['ddl']):
            items=list(tokens(clause))
            if items and not items[0].quoted and fold(items[0].value) in {'constraint','primary','unique','check','foreign'}:
                declarations.append(clause)
        depth=0;tail=None
        original=before['native']['ddl']
        for token in tokens(original):
            if token.quoted:continue
            if token.value=='(':depth+=1
            elif token.value==')':
                depth-=1
                if depth==0:
                    tail=original[token.end:].strip();break
        if tail is None:raise ValueError('Native table options are unavailable')
        source=prefix+' ('+',\n'.join(declarations)+')'+(' '+tail if tail else '')
    probe=_prototype(baseline,{'main'})
    try:
        children=[row for row in baseline['rows'].values()
            if row['kind'] in {'index','trigger'} and row['path'][:2]==before['path']
            and row['native'].get('ddl') and row['system']=='false']
        probe.execute('DROP '+kind.upper()+' "main".'+_quote(name))
        probe.execute(source)
        for child in children:probe.execute(child['native']['ddl'])
        observed=_resources(probe,{})
        if any(row['resource_kind']=='view' and row['native'].get('column_observation',{}).get('available') is False for row in observed):
            raise ValueError('Desired view or a dependent view does not bind on the native prototype')
        modeled=_modeled(observed)
        desired=deepcopy(baseline)
        # Copy affected catalog facts only: changing a view/table may change
        # projections of dependent views, while other object identities remain.
        affected={tuple(row['path']) for row in baseline['rows'].values() if row['kind']=='view'}|{tuple(before['path'])}
        def selected(row):return tuple(row['path'][:2]) in affected
        for key,row in list(desired['rows'].items()):
            if selected(row):del desired['rows'][key]
        desired['rows'].update({key:row for key,row in modeled.items() if selected(row) and row['system']=='false'})
        return desired
    finally:probe.close()
