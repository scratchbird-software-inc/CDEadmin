"""Native MariaDB three-way table changes; lexical compilation grants no execution."""
from copy import deepcopy
import json
import re
from ..providers.mysql_family.mariadb_catalog import identifier, SYSTEM
from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest
from .mysql_table_clauses import table_layout

TOKEN = r'(?:`(?:``|[^`])+`|"(?:""|[^"])+")'
IDENTIFIER = re.compile(TOKEN)
HEADER = re.compile(r'^\s*CREATE\s+TABLE\s+('+TOKEN+r')(?:\s*\.\s*('+TOKEN+r'))?\s*$', re.I)

def name(token):return token[1:-1].replace(token[0]*2,token[0])

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
        elif re.match(r'^PERIOD\s+FOR\s+SYSTEM_TIME\s*\(',stripped,re.I):key=('period','SYSTEM_TIME')
        elif re.match(r'^PERIOD\s+FOR\s+',stripped,re.I):
            match=re.match(r'^PERIOD\s+FOR\s+('+TOKEN+r')\s*\(',stripped,re.I)
            if not match:raise ValueError('Exact quoted native application-period identity is required')
            key=('period',name(match.group(1)))
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

def alteration(before,after,sql_mode):
    old,columns,old_order=parts(before,sql_mode);new,desired,new_order=parts(after,sql_mode)
    intent=after['native'].get('mariadb_change',{})
    if not isinstance(intent,dict) or set(intent)-{'drop_columns','drop_periods','temporal_history'}:raise ValueError('Unknown table alteration intent')
    temporal='WITH SYSTEM VERSIONING' in old['suffix'].upper()
    if temporal and intent.get('temporal_history') != 'KEEP':
        raise ValueError('System-versioned schema alteration requires explicit mariadb_change.temporal_history=KEEP acceptance of native history semantics')
    if 'temporal_history' in intent and (not temporal or intent['temporal_history'] != 'KEEP'):
        raise ValueError('Native temporal history policy is KEEP on an existing system-versioned table')
    inverse={};renames={};automatic_references=set()
    removals={key[1] for key in columns.keys()-desired.keys() if key[0]=='column'}
    declared=intent.get('drop_columns',[])
    if not isinstance(declared,list) or any(not isinstance(value,str) for value in declared) or len(set(declared))!=len(declared) or set(declared)!=removals:
        raise ValueError('Column removal requires exact explicit mariadb_change.drop_columns intent')
    periods={key[1] for key in columns.keys()-desired.keys() if key[0]=='period'}
    declared=intent.get('drop_periods',[])
    if not isinstance(declared,list) or any(not isinstance(value,str) for value in declared) or len(set(declared))!=len(declared) or set(declared)!=periods:
        raise ValueError('Period removal requires exact explicit mariadb_change.drop_periods intent')
    if ('period','SYSTEM_TIME') in columns and ('period','SYSTEM_TIME') not in desired:
        raise ValueError('Removing system-time history requires a separate explicit native temporal lifecycle operation')
    for key in columns.keys() & desired.keys():
        if key[0]=='foreign-key' and columns[key]!=desired[key] and key not in automatic_references:
            raise ValueError('Same-name foreign-key replacement requires separately reviewed DROP and ADD or an explicit new constraint name; foreign-key checks are never disabled')
    for key in columns.keys() & desired.keys():
        if key[0]=='period' and columns[key]!=desired[key]:
            raise ValueError('Period boundary replacement requires separately reviewed native DROP and ADD')
    drops=[];mutations=[];additions=[]
    for key in sorted(columns):
        if key in automatic_references or key in desired and columns[key]==desired[key]:continue
        kind,value=key
        if kind=='column':
            if key not in desired and value not in renames:drops.append('DROP COLUMN '+identifier(value))
        elif kind=='primary':drops.insert(0,'DROP PRIMARY KEY')
        elif kind=='index':drops.insert(0,'DROP INDEX '+identifier(value))
        elif kind=='foreign-key':drops.insert(0,'DROP FOREIGN KEY '+identifier(value))
        elif kind=='period':drops.insert(0,'DROP PERIOD FOR '+identifier(value))
        else:drops.insert(0,'DROP CONSTRAINT '+identifier(value))
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
        if key[0]!='column' and key not in automatic_references and (key not in columns or columns[key]!=desired[key]):additions.append('ADD '+desired[key])
    if old['suffix'].strip()!=new['suffix'].strip():
        if 'WITH SYSTEM VERSIONING' in old['suffix'].upper() and 'WITH SYSTEM VERSIONING' not in new['suffix'].upper():
            raise ValueError('Removing system versioning requires a separate explicit native temporal lifecycle operation')
        if not new['suffix'].strip():raise ValueError('Removing native table options requires an explicit option adapter')
        additions.append(new['suffix'].strip())
    result=drops+mutations+additions
    if not result:raise ValueError('Definition changes do not produce an unambiguous native alteration')
    return 'ALTER TABLE '+identifier(before['native']['database'])+'.'+identifier(before['name'])+' '+', '.join(result)

def creation(row,sql_mode,database):
    layout,_clauses,_order=parts(row,sql_mode)
    return 'CREATE TABLE '+identifier(database)+'.'+identifier(row['name'])+' ('+','.join(layout['clauses'])+')'+layout['suffix']


def schema(row):
    return {key: deepcopy(row['native'].get(key)) for key in ('definition', 'definition_context')}


def root(document):
    if document['provenance'].get('mapping') != 'scratchrobin.mariadb.catalog@1':
        raise ValueError('A native MariaDB database catalog is required')
    roots = [row for row in document['rows'].values() if row['kind'] == 'database']
    if len(roots) != 1:
        raise ValueError('Capture one exact native MariaDB database')
    row = roots[0]
    database = row['name']
    facts = row['native'].get('catalog_row', {})
    if (database in SYSTEM or facts.get('database_name') != database or
            str(facts.get('version', '')).split('-')[0] != '12.2.2' or not facts.get('server_uid')):
        raise ValueError('Exact native MariaDB 12.2.2 database/server identity is required')
    address(row, database)
    context = row['native'].get('definition_context', {})
    if any(not isinstance(context.get(key), str) for key in ('sql_mode', 'character_set_client', 'collation_connection')):
        raise ValueError('Native database creation context is unavailable')
    return database, facts, context


def address(row, database):
    native = row['native']
    parent = 'mariadb:' + json.dumps([database, 'database', None, database], ensure_ascii=False, separators=(',', ':'))
    if row['kind'] == 'database':
        expected, expected_parent, path = parent, None, [database]
    else:
        expected_parent, path = parent, [database, row['name']]
        expected = 'mariadb:' + json.dumps([database, row['kind'], parent, row['name']], ensure_ascii=False, separators=(',', ':'))
    if (row.get('resource_id') != expected or row.get('path') != path or
            native.get('navigator_parent_resource_id') != expected_parent or
            native.get('database') != database or row.get('system') != 'false' or native.get('system_object') is not False):
        raise ValueError('Native user-object identity or database scope is inconsistent')
    identifier(row['name'])


def compile_table(before, after, operation, context, database):
    if after['kind'] != 'table' or (before is not None and before['kind'] != 'table'):
        raise ValueError('This native clause adapter requires an ordinary table')
    address(after, database)
    if before is not None: address(before, database)
    intent = after['native'].get('mariadb_change')
    if operation == 'create' and before is None and not intent:
        return creation(after, context['sql_mode'], database)
    if operation == 'alter' and before is not None:
        return alteration(before, after, context['sql_mode'])
    if operation == 'drop' and before is not None and intent == {'action': 'drop', 'confirmation': before['name']}:
        return 'DROP TABLE ' + identifier(database) + '.' + identifier(before['name'])
    raise ValueError('Native table operation disagrees with baseline or explicit intent')


def plan(baseline, desired, live):
    database, facts, context = root(live)
    for document in (baseline, desired):
        other, identity, _context = root(document)
        if (other != database or identity['server_uid'] != facts['server_uid'] or any(
                document['provenance'].get(key) != live['provenance'].get(key)
                for key in ('endpoint_id', 'database_target_id'))):
            raise ValueError('Native review belongs to another endpoint, database or server UID')
    operations, blockers, conflicts, ignored = [], [], [], []
    for key, after in sorted(desired['rows'].items()):
        before, current = baseline['rows'].get(key), live['rows'].get(key)
        intent = after['native'].get('mariadb_change')
        if before is not None and _equal(schema(before), schema(after)) and not intent:
            continue
        try:
            address(after, database)
            if before is not None:
                address(before, database)
                if current is None or not _equal(schema(before), schema(current)):
                    conflicts.append({'resource_id': key, 'reason': 'Live native definition changed since baseline'})
                    continue
                address(current, database)
            elif current is not None:
                raise ValueError('Native creation target already exists')
            if before is None: operation = 'create'
            elif isinstance(intent, dict) and intent.get('action') == 'drop': operation = 'drop'
            else: operation = 'alter'
            source = compile_table(before, after, operation, context, database)
            operation_context=deepcopy(context)
            if isinstance(intent,dict) and intent.get('temporal_history')=='KEEP':
                operation_context['system_versioning_alter_history']='KEEP'
            operations.append({'resource_id': key, 'kind': after['kind'], 'name': after['name'],
                'database': database, 'operation': operation, 'source': source, 'context': operation_context,
                'baseline_schema_sha256': digest(schema(before)) if before else None,
                'desired_schema_sha256': digest(schema(after))})
        except (ValueError, KeyError, TypeError) as error:
            blockers.append({'resource_id': key, 'name': after['name'], 'reason': str(error)})
    for key in baseline['rows'].keys() - desired['rows'].keys():
        ignored.append({'resource_id': key, 'reason': 'Missing desired selection is not removal intent'})
    return {'format': 'scratchrobin.mariadb.schema-plan@1', 'engine_id': 'mariadb',
        'database': database, 'server_uid': facts['server_uid'], 'operations': operations,
        'execution_sha256': digest(operations), 'blockers': blockers, 'conflicts': conflicts,
        'ignored': ignored, 'ready_for_review': bool(operations) and not blockers and not conflicts,
        'native_grammar_validated': False, 'application_supported': False, 'executed': False,
        'warnings': ['Native clause separation is not grammar validation or permission to execute.',
            'MariaDB DDL commits independently; rollback cannot make a sequence of changes atomic.',
            'The current table adapter preserves temporal clauses. Temporal history removal requires separate explicit lifecycle review.',
            'Native baseline/absence revalidation, durable reviewed admission and rediscovery are required before application.']}
