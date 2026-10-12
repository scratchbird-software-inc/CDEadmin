"""Three-way native MySQL table previews; no grammar or execution authority."""
from copy import deepcopy
import json
import re
from ..providers.mysql_family.mysql_catalog import identifier,SYSTEM
from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest
from .mysql_table_clauses import table_layout

TOKEN=r'(?:`(?:``|[^`])+`|"(?:""|[^"])+")'
IDENTIFIER=re.compile(TOKEN)
HEADER=re.compile(r'^\s*CREATE\s+TABLE\s+('+TOKEN+r')(?:\s*\.\s*('+TOKEN+r'))?\s*$',re.I)


def name(token):return token[1:-1].replace(token[0]*2,token[0])


def root(model):
    if model['provenance'].get('mapping')!='scratchrobin.mysql.catalog@1':raise ValueError('Native MySQL catalog is required')
    rows=[row for row in model['rows'].values() if row['kind']=='database']
    if len(rows)!=1:raise ValueError('Capture one exact MySQL database for native review')
    facts=rows[0]['native'].get('catalog_row',{})
    database=rows[0]['name']
    if database in SYSTEM or facts.get('database_name')!=database or str(facts.get('version','')).split('-')[0]!='9.7.0' or not facts.get('server_uuid'):
        raise ValueError('Native MySQL database/server identity is unavailable')
    return database,facts


def schema(row):
    return {key:deepcopy(row['native'].get(key)) for key in ('definition','definition_context')}


def parts(row,sql_mode):
    statement=row['native'].get('definition')
    if not isinstance(statement,str) or not statement or '\x00' in statement:raise ValueError('Exact native table definition is unavailable')
    layout=table_layout(statement,sql_mode)
    header=HEADER.fullmatch(layout['prefix'])
    if not header:raise ValueError('Native table header requires its exact quoted target')
    names=[name(token) for token in header.groups() if token is not None]
    if names not in ([row['name']],[row['native']['database'],row['name']]):raise ValueError('Native CREATE TABLE target disagrees with catalog identity')
    clauses={};order=[]
    for clause in layout['clauses']:
        stripped=clause.strip();first=IDENTIFIER.match(stripped)
        if first:
            key=('column',name(first.group()));order.append(key[1])
        elif re.match(r'^PRIMARY\s+KEY\b',stripped,re.I):key=('primary','PRIMARY')
        else:
            match=re.match(r'^(?:UNIQUE\s+(?:KEY|INDEX)|(?:FULLTEXT\s+|SPATIAL\s+)?(?:KEY|INDEX))\s+('+TOKEN+r')\s*\(',stripped,re.I)
            if match:key=('index',name(match.group(1)))
            else:
                match=re.match(r'^CONSTRAINT\s+('+TOKEN+r')\s+(FOREIGN\s+KEY|CHECK)\b',stripped,re.I)
                if not match:raise ValueError('Unsupported or ambiguous native table clause')
                key=('foreign-key' if match.group(2).upper().startswith('FOREIGN') else 'check',name(match.group(1)))
        if key in clauses:raise ValueError('Duplicate native table clause identity')
        clauses[key]=stripped
    return layout,clauses,order


def address(row,database):
    native=row['native'];identity='mysql:'+json.dumps([database,row['kind'],native.get('navigator_parent_resource_id'),row['name']],ensure_ascii=False,separators=(',',':'))
    parent='mysql:'+json.dumps([database,'database',None,database],ensure_ascii=False,separators=(',',':'))
    if native.get('navigator_parent_resource_id')!=parent or row['resource_id']!=identity or row.get('path')!=[database,row['name']] or native.get('database')!=database or row.get('system')!='false':
        raise ValueError('Native object identity or user-table scope is inconsistent')


def alteration(before,after,sql_mode):
    old,columns,old_order=parts(before,sql_mode);new,desired,new_order=parts(after,sql_mode)
    intent=after['native'].get('mysql_change',{})
    if not isinstance(intent,dict) or set(intent)-{'drop_columns','rename_columns'}:raise ValueError('Unknown table alteration intent')
    renames=intent.get('rename_columns',{})
    if (not isinstance(renames,dict) or len(renames)>128 or
            any(not isinstance(value,str) or not 1<=len(value)<=64 or '\x00' in value
                for pair in renames.items() for value in pair) or
            len(set(renames.values()))!=len(renames) or any(
                ('column',old) not in columns or ('column',old) in desired or
                ('column',new) in columns or ('column',new) not in desired
                for old,new in renames.items())):
        raise ValueError('Column rename requires distinct exact baseline and desired native names')
    inverse={new:old for old,new in renames.items()}
    removals={key[1] for key in columns.keys()-desired.keys() if key[0]=='column' and key[1] not in renames}
    declared=intent.get('drop_columns',[])
    if not isinstance(declared,list) or any(not isinstance(value,str) for value in declared) or len(set(declared))!=len(declared) or set(declared)!=removals:
        raise ValueError('Column removal requires exact explicit mysql_change.drop_columns intent')
    drops=[];mutations=[];additions=[]
    for key in sorted(columns):
        if key in desired and columns[key]==desired[key]:continue
        kind,value=key
        if kind=='column':
            if key not in desired and value not in renames:drops.append('DROP COLUMN '+identifier(value))
        elif kind=='primary':drops.insert(0,'DROP PRIMARY KEY')
        elif kind=='index':drops.insert(0,'DROP INDEX '+identifier(value))
        elif kind=='foreign-key':drops.insert(0,'DROP FOREIGN KEY '+identifier(value))
        else:drops.insert(0,'DROP CHECK '+identifier(value))
    for index,value in enumerate(new_order):
        key=('column',value)
        previous=new_order[index-1] if index else None
        original=inverse.get(value,value)
        old_previous=old_order[old_order.index(original)-1] if original in old_order and old_order.index(original)>0 else None
        old_previous=renames.get(old_previous,old_previous)
        if value in inverse or key not in columns or columns[key]!=desired[key] or previous!=old_previous:
            placement=' AFTER '+identifier(previous) if previous is not None else ' FIRST'
            mutations.append(('CHANGE COLUMN '+identifier(inverse[value])+' ' if value in inverse else
                'ADD COLUMN ' if key not in columns else 'MODIFY COLUMN ')+desired[key]+placement)
    for key in sorted(desired):
        if key[0]!='column' and (key not in columns or columns[key]!=desired[key]):additions.append('ADD '+desired[key])
    if old['suffix'].strip()!=new['suffix'].strip():
        if not new['suffix'].strip():raise ValueError('Removing native table options requires an explicit option adapter')
        additions.append(new['suffix'].strip())
    result=drops+mutations+additions
    if not result:raise ValueError('Definition changes do not produce an unambiguous native alteration')
    return 'ALTER TABLE '+identifier(before['native']['database'])+'.'+identifier(before['name'])+' '+', '.join(result)


def creation(row,sql_mode,database):
    layout,_clauses,_order=parts(row,sql_mode)
    return 'CREATE TABLE '+identifier(database)+'.'+identifier(row['name'])+' ('+','.join(layout['clauses'])+')'+layout['suffix']


def plan(baseline,desired,live):
    database,identity=root(live)
    for document in (baseline,desired):
        other,observed=root(document)
        if other!=database or observed['server_uuid']!=identity['server_uuid'] or any(
            document['provenance'].get(key)!=live['provenance'].get(key) for key in ('endpoint_id','database_target_id')):
            raise ValueError('DDN review belongs to another endpoint, database or native server')
    operations=[];blockers=[];ignored=[];conflicts=[]
    for key,after in sorted(desired['rows'].items()):
        if after['kind']=='database':continue
        before,current=baseline['rows'].get(key),live['rows'].get(key)
        intent=after['native'].get('mysql_change')
        if before is not None and _equal(schema(before),schema(after)) and not intent:continue
        try:
            address(after,database)
            if before is not None:
                address(before,database)
                if current is not None:address(current,database)
                if before['kind']!=after['kind'] or (current is not None and current['kind']!=after['kind']):
                    raise ValueError('Native object kind changed across the review')
            if after['kind'] not in {'table','view','library','event'}:raise ValueError('Native adapter for this object kind is not yet admitted')
            if before is not None and (current is None or not _equal(schema(before),schema(current))):
                conflicts.append({'resource_id':key,'reason':'Live native definition changed since baseline'});continue
            if before is None:
                if current is not None:raise ValueError('New native target already exists')
                if intent:raise ValueError('Creation does not accept alteration/removal intent')
                operation='create'
            elif isinstance(intent,dict) and intent.get('action')=='drop':
                if set(intent)!={'action','confirmation'} or intent['confirmation']!=before['name']:
                    raise ValueError('Removal requires exact native name confirmation')
                operation='drop'
            else:operation='alter'
            if after['kind']=='event':
                from .mysql_event_plan import compile_event
                source=compile_event(after,operation,database)
                context={name:after['native'].get('definition_context',{}).get(name)
                    for name in ('sql_mode','character_set_client','collation_connection','time_zone')}
                if any(not isinstance(value,str) or '\x00' in value for value in context.values()):
                    raise ValueError('Native event SQL/character/time-zone context is required')
            elif after['kind']=='library':
                from .mysql_library_plan import compile_library
                source=compile_library(after,operation,database,before)
                context={name:after['native'].get('definition_context',{}).get(name,identity[name])
                    for name in ('sql_mode','character_set_client','collation_connection')}
            elif after['kind']=='view':
                from .mysql_view_plan import compile_view
                source=compile_view(after,operation,database)
                context={name:after['native'].get('definition_context',{}).get(name,identity[name])
                    for name in ('sql_mode','character_set_client','collation_connection')}
            else:
                source=(creation(after,identity['sql_mode'],database) if operation=='create' else
                    'DROP TABLE '+identifier(database)+'.'+identifier(before['name']) if operation=='drop' else
                    alteration(before,after,identity['sql_mode']))
                context={name:identity[name] for name in ('sql_mode','character_set_client','collation_connection')}
            operations.append({'resource_id':key,'kind':after['kind'],'name':after['name'],'database':database,'operation':operation,
                'source':source,'context':context,
                'baseline_schema_sha256':digest(schema(before)) if before else None,'desired_schema_sha256':digest(schema(after))})
        except (ValueError,KeyError,TypeError) as error:
            blockers.append({'resource_id':key,'name':after['name'],'reason':str(error)})
    for key,row in baseline['rows'].items():
        if key not in desired['rows']:ignored.append({'resource_id':key,'reason':'Missing desired selection is not removal intent'})
    return {'format':'scratchrobin.mysql.schema-plan@1','engine_id':'mysql','operations':operations,'blockers':blockers,
        'conflicts':conflicts,'ignored':ignored,'database':database,'server_uuid':identity['server_uuid'],
        'execution_sha256':digest(operations),'ready_for_review':not blockers and not conflicts and bool(operations),
        'native_grammar_validated':False,'application_supported':False,'executed':False,
        'warnings':['Native clause separation is not grammar validation. This preview grants no execution.',
            'MySQL DDL commits implicitly; rollback cannot provide multi-statement atomicity.',
            'Native baseline/absence revalidation, durable reviewed admission and rediscovery are required before application.'] +
            (['View/library/event updates/removals recheck observed baselines with a cooperating advisory lock only. External DDL is not fenced; use an exclusive DDL maintenance window to prevent replacement races.']
             if any(op['kind'] in {'view','library','event'} and op['operation']!='create' for op in operations) else [])}
