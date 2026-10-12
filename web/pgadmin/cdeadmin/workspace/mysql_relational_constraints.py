"""Explicit DDN relationship intent becomes reviewed native foreign-key clauses."""
import json
from .firebird_catalog_import import _equal
from .mysql_schema_plan import parts
from ..providers.mysql_family.mysql_catalog import identifier as quote_identifier


def identifier(value):
    if not isinstance(value,str) or not 1<=len(value)<=64:raise ValueError("Native foreign-key names require 1 to 64 characters")
    return quote_identifier(value)

FORMAT='scratchrobin.mysql.foreign-key@1'
ACTIONS={'RESTRICT','CASCADE','SET NULL','NO ACTION','SET DEFAULT'}


def relationship_changes(before,after,current):
    previous={edge.get('uid'):edge for edge in before}
    if len(previous)!=len(before):raise ValueError('Duplicate original relationship UID')
    changes={};seen=set()
    for edge in after:
        uid=edge.get('uid')
        if not isinstance(uid,str) or not uid or len(uid)>4096 or uid in seen:raise ValueError('A relationship requires a bounded unique UID')
        seen.add(uid);old=previous.get(uid)
        if old is not None and _equal(old,edge):continue
        owner=current.get(edge.get('source'));target=current.get(edge.get('target'))
        if owner is None or target is None or owner['kind']!='table' or target['kind']!='table':
            raise ValueError('Native foreign keys require exact visible source and target tables')
        if edge.get('kind')!='ref' or edge.get('enforcement')!='database':raise ValueError('Native foreign keys require ref/database enforcement')
        intent=edge.get('native_json')
        if not isinstance(intent,dict) or intent.get('format')!=FORMAT:raise ValueError('Relationship changes require explicit native foreign-key design intent')
        action=intent.get('action');old_name=None
        if old is not None:
            if old['source']!=edge['source']:raise ValueError('Existing native foreign keys cannot move between source tables')
            facts=old.get('native_json')
            if not isinstance(facts,list) or not facts or not all(isinstance(row,dict) for row in facts):raise ValueError('Exact original native foreign-key facts are required')
            names={row.get('constraint_name') for row in facts}
            if len(names)!=1:raise ValueError('Original foreign-key identity is ambiguous')
            old_name=next(iter(names));identifier(old_name)
            expected=owner['uid']+':foreign-key:'+json.dumps(old_name,ensure_ascii=False,separators=(',',':'))
            if uid!=expected:raise ValueError('Original relationship UID does not identify its native foreign key')
        if action=='drop':
            if old_name is None or set(intent)!={'format','action','confirmation'} or intent['confirmation']!=old_name:
                raise ValueError('Foreign-key removal requires its exact original UID and name confirmation')
            clause=name=None
        else:
            if action!=('replace' if old_name is not None else 'create') or set(intent)-{'format','action','name','columns','referenced_columns','on_delete','on_update'}:
                raise ValueError('Select explicit create/replace foreign-key intent')
            name=intent.get('name');identifier(name)
            source_columns=intent.get('columns');target_columns=intent.get('referenced_columns')
            if (not isinstance(source_columns,list) or not isinstance(target_columns,list) or
                    not 1<=len(source_columns)<=16 or len(source_columns)!=len(target_columns) or
                    any(not isinstance(value,str) for value in source_columns+target_columns) or
                    len(set(source_columns))!=len(source_columns) or len(set(target_columns))!=len(target_columns)):
                raise ValueError('Native foreign-key columns require 1 to 16 distinct ordered name pairs')
            delete=intent.get('on_delete','RESTRICT');update=intent.get('on_update','RESTRICT')
            if delete not in ACTIONS or update not in ACTIONS:raise ValueError('Select native foreign-key update/delete rules')
            target_path=target.get('path')
            if not isinstance(target_path,list) or len(target_path)!=2:raise ValueError('Exact native parent database/table identity is required')
            clause='CONSTRAINT '+identifier(name)+' FOREIGN KEY ('+', '.join(identifier(value) for value in source_columns)+') REFERENCES '+'.'.join(identifier(value) for value in target_path)+' ('+', '.join(identifier(value) for value in target_columns)+') ON DELETE '+delete+' ON UPDATE '+update
        rows=changes.setdefault(owner['resource_id'],[])
        if len(rows)>=128 or any((old_name is not None and row['old_name']==old_name) or (name is not None and row['name']==name) for row in rows):
            raise ValueError('Duplicate or excessive foreign-key design changes')
        rows.append({'old_name':old_name,'name':name,'clause':clause})
    return changes


def merge_constraints(before,native,changes,mode):
    _layout,original,_order=parts(before,mode)
    layout,desired,_order=parts({'name':before['name'],'native':native},mode)
    replacements={};additions=[]
    for change in changes:
        old_key=('foreign-key',change['old_name']);new_key=('foreign-key',change['name'])
        if change['old_name'] is not None:
            if old_key not in original:raise ValueError('Original native foreign-key clause is unavailable')
            if old_key in desired and desired[old_key] not in {original[old_key],change['clause']}:
                raise ValueError('Graphical and native foreign-key edits disagree')
            replacements[old_key]=change['clause']
        else:
            if new_key in original or new_key in desired:raise ValueError('New foreign-key name already exists')
            additions.append(change['clause'])
        if change['name'] is not None and new_key!=old_key and new_key in desired:raise ValueError('Foreign-key replacement name already exists')
    clauses=[replacements.get(key,value) for key,value in desired.items()]
    # An explicit native omission and explicit graphical drop are compatible.
    for key,value in replacements.items():
        if key not in desired and value is not None:clauses.append(value)
    native['definition']=layout['prefix']+'('+','.join([value for value in clauses if value is not None]+additions)+')'+layout['suffix']
    return native
