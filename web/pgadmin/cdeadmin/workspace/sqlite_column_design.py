"""Structured column definitions to native catalog DDN, without file mutation."""
from copy import deepcopy
import sqlite3

from .sqlite_schema_plan import _scope,_source,_quote,_require_virtual_module,CREATABLE
from .sqlite_columns import plan_append
from ..providers.sqlite.provider import _resources


def _text(value,label,*,optional=False):
    if optional and value in (None,''):return None
    if not isinstance(value,str) or not value or '\0' in value or len(value.encode('utf8'))>262144:
        raise ValueError('One bounded native SQLite '+label+' is required')
    return value


def declaration(column):
    if not isinstance(column,dict) or set(column)-{'name','data_type','nullable','default','generated',
            'check','collation','references','constraint_names'}:
        raise ValueError('Invalid structured SQLite column definition')
    name=_text(column.get('name'),'column name');data_type=column.get('data_type','')
    if not isinstance(data_type,str) or '\0' in data_type or len(data_type.encode('utf8'))>4096:
        raise ValueError('Invalid native SQLite declared type')
    nullable=column.get('nullable',True)
    if type(nullable) is not bool:raise ValueError('Invalid SQLite column nullability')
    names=column.get('constraint_names',{})
    if not isinstance(names,dict) or set(names)-{'not_null','default','generated','check','collation','references'}:
        raise ValueError('Invalid SQLite column constraint names')
    for value in names.values():_text(value,'constraint name')
    used=set()
    def constraint(kind,source):
        used.add(kind)
        return ('CONSTRAINT '+_quote(names[kind])+' ' if kind in names else '')+source
    parts=[_quote(name)]
    if data_type:parts.append(data_type)
    if not nullable:parts.append(constraint('not_null','NOT NULL'))
    collation=_text(column.get('collation'),'collation',optional=True)
    if collation:parts.append(constraint('collation','COLLATE '+_quote(collation)))
    default=_text(column.get('default'),'default expression',optional=True)
    if default:parts.append(constraint('default','DEFAULT ('+default+')'))
    generated=column.get('generated')
    if generated is not None:
        if not isinstance(generated,dict) or set(generated)!={'expression','storage'} or generated['storage'] not in {'virtual','stored'}:
            raise ValueError('A native generated column requires its expression and storage kind')
        parts.append(constraint('generated','GENERATED ALWAYS AS ('+_text(generated['expression'],'generated expression')+') '+generated['storage'].upper()))
    check=_text(column.get('check'),'CHECK expression',optional=True)
    if check:parts.append(constraint('check','CHECK ('+check+')'))
    reference=column.get('references')
    if reference is not None:
        if not isinstance(reference,dict) or set(reference)-{'table','column','on_update','on_delete','match','deferrable','initially'}:
            raise ValueError('Invalid native SQLite column reference')
        source='REFERENCES '+_quote(_text(reference.get('table'),'referenced table'))
        referenced=_text(reference.get('column'),'referenced column',optional=True)
        if referenced:source+=' ('+_quote(referenced)+')'
        for field,clause in (('on_update','ON UPDATE'),('on_delete','ON DELETE')):
            action=reference.get(field)
            if action is not None:
                if action not in {'NO ACTION','RESTRICT','SET NULL','SET DEFAULT','CASCADE'}:
                    raise ValueError('Invalid native SQLite foreign-key action')
                source+=' '+clause+' '+action
        match=_text(reference.get('match'),'reference MATCH name',optional=True)
        if match:source+=' MATCH '+_quote(match)
        deferred=reference.get('deferrable')
        if deferred is not None:
            if type(deferred) is not bool:raise ValueError('Invalid native SQLite deferrability')
            source+=' '+('DEFERRABLE' if deferred else 'NOT DEFERRABLE')
        initially=reference.get('initially')
        if initially is not None:
            if initially not in {'DEFERRED','IMMEDIATE'}:raise ValueError('Invalid native SQLite initial constraint timing')
            source+=' INITIALLY '+initially
        parts.append(constraint('references',source))
    if set(names)-used:raise ValueError('A named SQLite column constraint requires its definition')
    return '\n'.join(parts)


def generate(baseline,identity,columns):
    _scope(baseline)
    before=baseline['rows'].get(identity)
    if (before is None or before['kind']!='table' or before['path']!=['main',before['name']] or
            before['system']!='false' or before['native'].get('catalog_metadata',{}).get('table_list_type')!='table'):
        raise ValueError('Select an observed ordinary SQLite main-file table')
    if not isinstance(columns,list) or not 1<=len(columns)<=32:
        raise ValueError('Design one to 32 native SQLite column additions')
    sources=[declaration(column) for column in columns]
    probe=sqlite3.connect(':memory:')
    try:
        # Materialize definitions only. No user rows, files or pending query
        # work are copied. Configured native capabilities still govern binding.
        rows=[row for row in baseline['rows'].values() if row['kind'] in CREATABLE and
            row['system']=='false' and row['path'][0]=='main' and row['native'].get('ddl')]
        for row in sorted(rows,key=lambda row:{'table':0,'fts-table':1,'virtual-table':1,'view':2,'index':3,'trigger':4}[row['kind']]):
            source=_source(row)
            if row['kind'] in {'fts-table','virtual-table'}:
                from ..providers.sqlite.modules import declaration as module_declaration
                if module_declaration(source)[1].lower() not in {'fts3','fts4','fts5','rtree','rtree_i32'}:
                    raise ValueError('The installed virtual module needs an owned native preview adapter')
            _require_virtual_module(probe,row,source);probe.execute(source)
        for source,column in zip(sources,columns):
            old=[item[1] for item in probe.execute('PRAGMA main.table_xinfo('+_quote(before['name'])+')')]
            probe.execute('ALTER TABLE "main".'+_quote(before['name'])+' ADD COLUMN '+source)
            current=[item[1] for item in probe.execute('PRAGMA main.table_xinfo('+_quote(before['name'])+')')]
            if current!=[*old,column['name']]:raise ValueError('A structured native column must add its exact single identifier')
        captured=_resources(probe,{})
        if any(row['resource_kind']=='view' and row['native'].get('column_observation',{}).get('available') is False for row in captured):
            raise ValueError('Native view projection binding is unavailable on the owned preview')
        desired=deepcopy(baseline)
        views={tuple(row['path']) for row in baseline['rows'].values() if row['kind']=='view' and row['path'][0]=='main'}
        def selected(kind,path):return path[:2]==before['path'] or (tuple(path[:2]) in views and kind in {'view','column'})
        for key,row in list(desired['rows'].items()):
            if selected(row['kind'],row['path']):del desired['rows'][key]
        for row in captured:
            if selected(row['resource_kind'],row['display_path']) and not row['native'].get('system_object'):
                desired['rows'][row['resource_id']]={'resource_id':row['resource_id'],'kind':row['resource_kind'],
                    'path':row['display_path'],'name':row['display_name'],'system':'false','native':row['native']}
        plan_append(before,desired['rows'][identity],baseline,desired)
        return desired
    finally:probe.close()
