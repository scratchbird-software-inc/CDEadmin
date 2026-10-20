"""Derive native ADD COLUMN stages from complete desired catalog declarations."""
import sqlite3

from .firebird_schema_plan import digest
from .sqlite_schema_plan import _source, _definition, _quote, _compile_exact
from ..providers.sqlite.declarations import tokens, fold
from ..providers.sqlite.provider import _resources, _resource_id


def signature(source):
    # Preserve quoted identifiers and literal spelling. Ignore only comments,
    # inter-token whitespace and ASCII case of unquoted native SQL tokens.
    return [(source[item.start:item.end] if item.quoted else fold(item.value))
            for item in tokens(source.strip().rstrip(';'))]


def _clauses(source):
    depth=0;start=None;clauses=[]
    for item in tokens(source):
        if item.quoted:continue
        if item.value=='(':
            depth+=1
            if depth==1:start=item.end
        elif item.value==')':
            depth-=1
            if depth==0:
                clauses.append(source[start:item.start].strip())
                return clauses
        elif item.value==',' and depth==1:
            clauses.append(source[start:item.start].strip());start=item.end
    raise ValueError('SQLite column generation requires a complete native table declaration')


def _modeled(rows):
    return {row['resource_id']:{'resource_id':row['resource_id'],'kind':row['resource_kind'],
        'path':row['display_path'],'name':row['display_name'],
        'system':'true' if row['native'].get('system_object') else 'false','native':row['native']}
        for row in rows}


def children(model,path):
    return {identity:digest(_definition(row)) for identity,row in model['rows'].items()
        if row['system']=='false' and len(row['path'])>len(path) and row['path'][:len(path)]==path}


def plan_append(before,after,baseline,desired,connection=None):
    """Qualify append-only native grammar on an owned empty prototype.

    The prototype proves definitions, never existing-row suitability. SQLite's
    native write VM checks CHECK/NOT NULL/STRICT, nonconstant defaults, foreign
    keys and generated storage against the actual data during atomic apply.
    """
    if (before['kind']!='table' or after['kind']!='table' or
            before['resource_id']!=after['resource_id'] or before['path']!=after['path'] or
            before['path']!=['main',before['name']] or
            before['native'].get('catalog_metadata',{}).get('table_list_type')!='table' or
            before['native'].get('catalog_metadata')!=after['native'].get('catalog_metadata')):
        raise ValueError('SQLite native column append requires the same ordinary main-file table')
    old_source,new_source=_source(before),_source(after)
    path=before['path'];name=before['name'];target='"main".'+_quote(name)
    probe=sqlite3.connect(':memory:')
    try:
        probe.execute(new_source)
        wanted_columns=list(probe.execute('PRAGMA main.table_xinfo('+_quote(name)+')'))
        clauses={}
        for clause in _clauses(new_source):
            first=next(tokens(clause))
            if first.value in {item[1] for item in wanted_columns}:clauses[first.value]=clause
        expected=_modeled(_resources(probe,{}))
        expected={identity:row for identity,row in expected.items() if row['path'][:2]==path and
            row['kind'] in {'column','constraint'}}
        intended={identity:row for identity,row in desired['rows'].items() if row['path'][:2]==path and
            row['kind'] in {'column','constraint'}}
        if set(expected)!=set(intended) or any(_definition(row)!=_definition(intended[identity])
                for identity,row in expected.items()):
            raise ValueError('Desired SQLite column and constraint facts differ from native CREATE TABLE')
        if after['native'].get('columns')!=expected_table_columns(wanted_columns,path):
            raise ValueError('Desired SQLite parent column facts differ from native CREATE TABLE')
        probe.execute('DROP TABLE '+target);probe.execute(old_source)
        old_columns=list(probe.execute('PRAGMA main.table_xinfo('+_quote(name)+')'))
        if ([item[1] for item in wanted_columns[:len(old_columns)]]!=[item[1] for item in old_columns] or
                not 1<=len(wanted_columns)-len(old_columns)<=32):
            raise ValueError('SQLite ADD COLUMN requires one to 32 columns appended in native order')
        stages=[]
        for item in wanted_columns[len(old_columns):]:
            column=desired['rows'][_resource_id('column',path,item[1])]
            if item[1] not in clauses:raise ValueError('Native SQLite column declaration is unavailable')
            stage='ALTER TABLE '+target+' ADD COLUMN '+clauses[item[1]]
            _compile_exact(probe,column,stage);probe.execute(stage);stages.append(stage)
        actual=probe.execute('SELECT sql FROM main.sqlite_schema WHERE type=\'table\' AND name=?',(name,)).fetchone()[0]
        from ..providers.sqlite.declarations import canonical_create
        expected_ddl=canonical_create(actual,'table','main',name)
        if signature(expected_ddl)!=signature(new_source):
            raise ValueError('Native column append cannot change existing columns, constraints or table options; review a rebuild')
        # Explicit index/trigger changes retain their own independent review.
        # An absent child cannot silently authorize removal through this stage.
        for identity,row in baseline['rows'].items():
            if row['path'][:2]==path and row['kind'] in {'index','trigger'} and row['native'].get('ddl'):
                if identity not in desired['rows']:
                    raise ValueError('Native SQLite column append must retain existing index and trigger records')
        if connection is not None:
            first=desired['rows'][_resource_id('column',path,wanted_columns[len(old_columns)][1])]
            _compile_exact(connection,first,stages[0])
        return {'operation':'append-columns','kind':'table','resource_id':before['resource_id'],'name':name,
            'stages':stages,'baseline_sha256':digest(_definition(before)),
            'baseline_child_sha256':children(baseline,path),
            'desired_sha256':digest(_definition(after)),
            'desired_child_sha256':{identity:digest(_definition(row)) for identity,row in intended.items()},
            'expected_ddl':expected_ddl,'added_columns':[item[1] for item in wanted_columns[len(old_columns):]],
            'existing_data_validation':'native-write-vm-during-atomic-apply'}
    finally:probe.close()


def expected_table_columns(rows,path):
    return [{'resource_id':_resource_id('column',path,name),'name':name,
        'ordinal_position':cid,'data_type':str(data_type or ''),'nullable':not bool(not_null),
        'default':default,'primary_key_position':int(pk or 0),'hidden':int(hidden or 0)}
        for cid,name,data_type,not_null,default,pk,hidden in rows]


def verify(operation,observed):
    """Check the resulting native definition and every derived column fact."""
    from ..providers.sqlite.declarations import canonical_create
    by_id=_modeled(observed)
    row=by_id.get(operation['resource_id'])
    if row is None:return False
    try:actual=canonical_create(row['native']['ddl'],'table','main',operation['name'])
    except (KeyError,ValueError):return False
    return (signature(actual)==signature(operation['expected_ddl']) and all(
        identity in by_id and digest(_definition(by_id[identity]))==expected
        for identity,expected in operation['desired_child_sha256'].items()))


def verify_views(desired,observed):
    """Native SELECT projections, including SELECT *, own their column facts."""
    actual=_modeled(observed)
    for row in desired['rows'].values():
        if row['kind']!='view':continue
        wanted={identity:_definition(column) for identity,column in desired['rows'].items()
            if column['kind']=='column' and column['path'][:2]==row['path']}
        current={identity:_definition(column) for identity,column in actual.items()
            if column['kind']=='column' and column['path'][:2]==row['path']}
        if row['resource_id'] not in actual or wanted!=current:return False
    return True
