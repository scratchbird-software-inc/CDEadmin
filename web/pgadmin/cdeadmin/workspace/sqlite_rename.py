"""SQLite-owned schema rewriting for reviewed DDN table and column renames."""
from copy import deepcopy
from collections import Counter
import os
import sqlite3
import stat

from .firebird_catalog_export import build_export
from .firebird_schema_plan import digest
from .sqlite_schema_plan import FORMAT,_definition,_quote
from ..providers.sqlite.provider import _resources
from ..providers.sqlite.driver import uncertain_error

KINDS={'table','view','column','constraint','index','trigger','fts-table','virtual-table'}
RENAME_MODULES={'fts3','fts4','fts5','rtree','rtree_i32','geopoly'}


def virtual_module(connection,row):
    """Use native authorizer arguments, including quoted module declarations."""
    observed=[]
    def authorize(action,name,module,database,_context):
        if action==sqlite3.SQLITE_CREATE_VTABLE:observed.append((name,module,database))
        return sqlite3.SQLITE_OK
    connection.set_authorizer(authorize)
    try:connection.execute('EXPLAIN '+row['native']['ddl']).fetchone()
    finally:connection.set_authorizer(None)
    if len(observed)!=1 or observed[0][0]!=row['name'] or observed[0][2]!='main':
        raise ValueError('Native virtual-table declaration targets a different rename scope')
    module=observed[0][1]
    if module.lower() not in RENAME_MODULES:
        raise ValueError('Native rename design generation requires an adapter for installed module '+module)
    return module


def schema(model):
    return {identity:_definition(row) for identity,row in model['rows'].items()
            if row['kind'] in KINDS and row['system']=='false' and row['path'][0]=='main'}


def model(connection,baseline):
    return build_export(_resources(connection,{}),endpoint_id=baseline['provenance']['endpoint_id'],
        target_id=baseline['provenance']['database_target_id'],generation='native-rename',
        engine='sqlite',native_model=True)


def options(renames):
    if not isinstance(renames,(list,tuple)) or not 1<=len(renames)<=16:
        raise ValueError('Select one to sixteen exact native SQLite renames')
    result=[]
    for row in renames:
        if (not isinstance(row,dict) or row.get('kind') not in {'table','column'} or
                set(row)!=({'kind','table','to'} if row['kind']=='table' else {'kind','table','from','to'})):
            raise ValueError('Native rename requires exact kind, owning table and names')
        for key,value in row.items():
            if key!='kind':_quote(value)
        if row['to']==row.get('from',row['table']):raise ValueError('Select a different native name')
        result.append(dict(row))
    return result


def generate(baseline,renames):
    """Run schema-only native rewriting in an empty independent database."""
    selected=options(renames);probe=sqlite3.connect(':memory:')
    try:
        probe.execute('PRAGMA legacy_alter_table=OFF')
        probe.execute('PRAGMA foreign_keys=ON')
        rows=[row for row in baseline['rows'].values() if row['kind'] in KINDS and row['system']=='false']
        from ..providers.sqlite.modules import option,declaration
        for row in rows:
            declared=declaration(row['native'].get('ddl')) if row['kind']=='fts-table' else None
            if declared and declared[1].lower() in {'fts4','fts5'}:
                content=option(row['native']['ddl'],'content')
                fold=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')
                if content and any(item['table'].translate(fold)==content.translate(fold) for item in selected):
                    raise ValueError('Renaming an external-content owner requires the native FTS rebinding adapter')
        if any(row['path'][0]!='main' for row in rows):
            raise ValueError('Native rename design generation for attached environments requires its attachment adapter')
        declarations=sorted((row for row in rows if row['kind'] in {'table','view','index','trigger','fts-table','virtual-table'}),
            key=lambda row:({'table':0,'fts-table':0,'virtual-table':0,'view':1,'index':2,'trigger':3}[row['kind']],row['resource_id']))
        for row in declarations:
            source=row['native'].get('ddl')
            if not isinstance(source,str) or not source or len(source.encode('utf8'))>1024*1024:
                raise ValueError('Native rename requires complete bounded schema declarations')
            if row['kind'] in {'fts-table','virtual-table'}:virtual_module(probe,row)
            # Source is compared with the fresh registered catalog at the service
            # boundary; execute() still rejects additional statements.
            probe.execute(source)
        if schema(model(probe,baseline))!=schema(baseline):
            raise ValueError('The empty native rename schema cannot reproduce all baseline facts')
        stages=[]
        for item in selected:
            if probe.execute('SELECT type FROM main.sqlite_schema WHERE name=?',(item['table'],)).fetchone()!=('table',):
                raise ValueError('Select an observed native table for each rename')
            source='ALTER TABLE "main".'+_quote(item['table'])+' RENAME '+(
                'TO '+_quote(item['to']) if item['kind']=='table' else 'COLUMN '+_quote(item['from'])+' TO '+_quote(item['to']))
            probe.execute(source);stages.append(source)
        generated=model(probe,baseline)
        desired=deepcopy(baseline)
        desired['rows']={identity:row for identity,row in desired['rows'].items() if row['kind'] not in KINDS}
        desired['rows'].update({identity:deepcopy(row) for identity,row in generated['rows'].items()
            if row['kind'] in KINDS and row['system']=='false'})
        return desired,selected,stages
    except sqlite3.Error as error:
        raise ValueError('Native SQLite rename refused ('+str(getattr(error,'sqlite_errorname','SQLITE_ERROR'))+'): '+str(error)) from None
    finally:probe.close()


def plan(baseline,desired,live,renames):
    generated,selected,stages=generate(baseline,renames)
    conflicts=[];blockers=[]
    if schema(baseline)!=schema(live):conflicts.append({'resource_id':'','name':'SQLite rename','reason':'Native schema changed since the captured baseline'})
    if schema(generated)!=schema(desired):blockers.append({'resource_id':'','name':'SQLite rename','reason':'Desired DDN differs from the native rewritten schema; generate the rename design again'})
    operation={'operation':'rename-batch','kind':'table','resource_id':'sqlite-native-rename-batch',
        'name':'Native table/column renames','renames':selected,'stages':stages,
        'source':'\n'.join(stage+';' for stage in stages),'baseline_schema_sha256':digest(schema(baseline)),
        'desired_schema_sha256':digest(schema(generated))}
    ready=not conflicts and not blockers
    return {'format':FORMAT,'engine':'sqlite','database_target_id':baseline['provenance']['database_target_id'],
        'operations':[operation],'blockers':blockers,'conflicts':conflicts,'execution_sha256':digest([operation]),
        'native_grammar_validated':True,'ready_for_review':ready,'application_supported':ready,
        'warnings':['SQLite rewrites table/column references using its native ALTER TABLE implementation. All original schema facts are rechecked before dispatch; the complete rewritten schema and bindings are checked before commit. No rows are copied and trigger DML is not executed by this operation.']}


def apply(provider,route,record):
    from ..providers.embedded_route import contained_database
    from .sqlite_schema_apply import _validate_dependencies
    path=contained_database(route);connection=None;dispatched=False;committed=False;close_failed=False
    def identity():
        info=os.stat(path)
        return stat.S_ISREG(info.st_mode) and [info.st_dev,info.st_ino]==record['file_identity']
    try:
        if path==':memory:' or route.get('read_only') is True or not identity():
            return {'state':'not_dispatched','reason':'Native SQLite rename file identity changed'}
        operation=record['plan']['operations'][0]
        expected=plan(record['baseline'],record['desired'],record['baseline'],operation['renames'])
        if expected['operations']!=[operation] or not expected['ready_for_review']:
            return {'state':'not_dispatched','reason':'Reviewed native rename design changed'}
        connection=provider.client._connect({'route':route})
        connection.execute('PRAGMA legacy_alter_table=OFF');connection.execute('PRAGMA foreign_keys=ON')
        if connection.execute('PRAGMA legacy_alter_table').fetchone()!=(0,) or connection.execute('PRAGMA foreign_keys').fetchone()!=(1,):
            return {'state':'not_dispatched','reason':'Native SQLite rename modes unavailable'}
        connection.execute('BEGIN IMMEDIATE')
        if not identity() or digest(schema(model(connection,record['baseline'])))!=operation['baseline_schema_sha256']:
            connection.rollback();return {'state':'not_dispatched','reason':'Native SQLite rename schema or file changed since review'}
        violations=list(connection.execute('PRAGMA foreign_key_check'))
        for source in operation['stages']:
            dispatched=True;connection.execute(source)
        if digest(schema(model(connection,record['baseline'])))!=operation['desired_schema_sha256']:
            raise ValueError('Native SQLite rewritten schema differs from the reviewed postimage')
        _validate_dependencies(connection,{row['resource_id']:row for row in _resources(connection,{})})
        def renamed(name):
            for item in operation['renames']:
                if item['kind']=='table' and name==item['table']:name=item['to']
            return name
        preserved=Counter((renamed(table),rowid,renamed(parent),foreign_id) for table,rowid,parent,foreign_id in violations)
        if Counter(connection.execute('PRAGMA foreign_key_check'))!=preserved:
            raise ValueError('Native SQLite rename changed foreign-key violations')
        connection.commit();committed=True
    except Exception as error:
        uncertain=committed or (dispatched and uncertain_error(error) and not isinstance(error,ValueError))
        if connection is not None:
            try:connection.rollback()
            except Exception:uncertain=True
        return {'state':'unknown_outcome' if uncertain else 'rolled_back' if dispatched else 'not_dispatched',
            'rediscovery_verified':False,'error_type':type(error).__name__}
    finally:
        if connection is not None:
            try:provider.client._discard_failed_session(connection)
            except Exception:close_failed=True
    if close_failed:
        return {'state':'unknown_outcome','rediscovery_verified':False,'error_type':'SQLiteConnectionReleaseError'}
    try:
        captured=provider.capture_catalog(route,include_system=False)
        fresh=build_export(captured['resources'],endpoint_id=record['baseline']['provenance']['endpoint_id'],
            target_id=record['baseline']['provenance']['database_target_id'],generation=captured['generation'],engine='sqlite',native_model=True)
        verified=identity() and digest(schema(fresh))==operation['desired_schema_sha256']
        return {'state':'committed' if verified else 'unknown_outcome','rediscovery_verified':verified,'operations':len(operation['stages'])}
    except Exception as error:return {'state':'unknown_outcome','rediscovery_verified':False,'error_type':type(error).__name__}
