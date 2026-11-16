"""MariaDB named/segmented MyISAM cache management and native index handlers."""
from collections.abc import Mapping
import hashlib
from ...sdk import RelationalClientError
from .mariadb_server_diagnostics import form, target_uid
from .mysql_catalog import identifier
from .mariadb_values import value
from . import mariadb_reviewed_server as lifecycle

KEY='mariadb_key_caches'
VARIABLES=('key_buffer_size','key_cache_block_size','key_cache_division_limit',
           'key_cache_age_threshold','key_cache_file_hash_size','key_cache_segments')
OPERATIONS={op:(title,'')for op,title in (
    ('inspect_key_caches','Inspect installed index caches'),('inspect_key_cache','Inspect named index cache'),('configure_key_cache','Configure named index cache'),
    ('release_key_cache','Release named index cache'),('assign_index_cache','Assign indexes to a cache'),
    ('preload_index_cache','Preload index cache'))}
INSPECTIONS={'inspect_key_cache','inspect_key_caches'}
WARNINGS=(
    'Native runtime cache settings are not persisted to server configuration. Native bounds, allocation, rounding and warnings remain authoritative.',
    'KEY_CACHES supplies native configured cache/segment enumeration and counters. Selected prefix variables do not alone prove a prefix is configured; six native variables include segmentation and file-hash sizing.',
    'Release sets the named buffer to zero; native semantics reassign its tables. Default-cache release is refused. No cache contents or durable data recovery is inferred.',
    'CACHE INDEX and LOAD INDEX INTO CACHE are native MyISAM operations with implicit commits on an owned connection. Original-session work is not settled.',
    'Native definition/index/cache observations are not an atomic table-generation or external-writer fence; native acknowledgement and handler result rows are separate. No replay.')


def name(value,label):
    if not isinstance(value,str)or not value or len(value)>64 or '\0'in value:raise RelationalClientError('Select a bounded exact '+label)
    return value


def targets(draft):
    rows=draft.get('tables')
    if rows is None:
        rows=[{key:draft[key] for key in ('database','table','ignore_leaves')if key in draft}]
    elif any(key in draft for key in ('database','table','ignore_leaves')):
        raise RelationalClientError('Use either a table list or one exact table')
    if not isinstance(rows,list)or not 1<=len(rows)<=32:raise RelationalClientError('Select 1 to 32 native MyISAM tables')
    result=[]
    for row in rows:
        if not isinstance(row,dict)or set(row)-{'database','table','ignore_leaves'}:raise RelationalClientError('Use typed native table selections')
        leaves=row.get('ignore_leaves',False)
        if type(leaves)is not bool:raise RelationalClientError('IGNORE LEAVES must be Boolean')
        result.append(dict(database=name(row.get('database'),'database'),table=name(row.get('table'),'table'),indexes=[],ignore_leaves=leaves))
    if len({(row['database'],row['table'])for row in result})!=len(result):raise RelationalClientError('Select distinct native tables')
    indexes=draft.get('indexes',[])
    if indexes and len(result)!=1:raise RelationalClientError('Use indexed table selections for multiple tables')
    selections=draft.get('index_selection',[])
    if not isinstance(selections,list)or len(selections)>2048 or indexes and selections:raise RelationalClientError('Select one native index selection format')
    if not isinstance(indexes,list)or len(indexes)>64:raise RelationalClientError('Select at most 64 indexes per table')
    result[0]['indexes']=[name(n,'index')for n in indexes]
    for row in selections:
        if not isinstance(row,dict)or set(row)!={'table_index','index_name'}or type(row['table_index'])is not int or not 0<=row['table_index']<len(result):raise RelationalClientError('Select the exact zero-based table row for an index')
        result[row['table_index']]['indexes'].append(name(row['index_name'],'index'))
    for row in result:
        if len(row['indexes'])>64 or len(set(row['indexes']))!=len(row['indexes']):raise RelationalClientError('Select distinct native indexes')
    partitions=draft.get('partitions',[])
    if not isinstance(partitions,list)or len(partitions)>1024 or any(not isinstance(n,str)for n in partitions)or len(set(partitions))!=len(partitions):raise RelationalClientError('Select distinct native partition names')
    for partition in partitions:name(partition,'partition')
    all_parts=draft.get('all_partitions',False)
    if type(all_parts)is not bool or partitions and all_parts or (partitions or all_parts)and len(result)!=1:raise RelationalClientError('Native partition cache syntax selects exactly one table')
    return result


def compile_operation(operation,draft,target):
    if operation not in OPERATIONS or not isinstance(draft,Mapping):raise RelationalClientError('Select a typed native cache operation')
    target_uid(target)
    allowed={'confirmation'}|({'cache_name'}if operation not in {'preload_index_cache','inspect_key_caches'}else set())
    if operation=='configure_key_cache':allowed|={'variable','value_mode','value'}
    table_operation=operation in {'assign_index_cache','preload_index_cache'}
    if table_operation:allowed|={'database','table','indexes','tables','index_selection','partitions','all_partitions','ignore_leaves'}
    if set(draft)-allowed or draft.get('confirmation')!=target.get('display_name'):raise RelationalClientError('Confirm the exact server and cache fields')
    cache=name(draft.get('cache_name','default'),'native cache prefix');params=()
    if operation=='inspect_key_caches':sql='SELECT * FROM information_schema.KEY_CACHES ORDER BY KEY_CACHE_NAME,SEGMENT_NUMBER'
    elif operation=='inspect_key_cache':sql=cache_source(cache)
    elif operation in {'configure_key_cache','release_key_cache'}:
        field='key_buffer_size'if operation=='release_key_cache'else draft.get('variable')
        if field not in VARIABLES:raise RelationalClientError('Select one of the six native key-cache variables')
        if operation=='release_key_cache'and cache=='default':raise RelationalClientError('The default cache cannot be released')
        mode='VALUE'if operation=='release_key_cache'else draft.get('value_mode','VALUE')
        if mode=='DEFAULT':
            if draft.get('value')not in (None,''):raise RelationalClientError('Omit the explicit value when selecting native DEFAULT')
            operand='DEFAULT'
        elif mode=='VALUE':
            text='0'if operation=='release_key_cache'else draft.get('value')
            import re
            if not isinstance(text,str)or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})',text)or int(text)>2**64-1:raise RelationalClientError('Use exact unsigned 64-bit decimal text')
            operand='%s';params=(int(text),)
        else:raise RelationalClientError('Select VALUE or native DEFAULT')
        sql='SET GLOBAL '+identifier(cache)+'.'+identifier(field)+'='+operand
    else:
        selections=targets(draft);clauses=[]
        for row in selections:
            clause=identifier(row['database'])+'.'+identifier(row['table'])
            partitions=draft.get('partitions',[])
            if partitions or draft.get('all_partitions'):clause+=' PARTITION ('+(','.join(map(identifier,partitions))if partitions else'ALL')+')'
            if row['indexes']:clause+=' INDEX ('+','.join(map(identifier,row['indexes']))+')'
            if operation=='preload_index_cache'and row['ignore_leaves']:clause+=' IGNORE LEAVES'
            if operation=='assign_index_cache'and row['ignore_leaves']:raise RelationalClientError('IGNORE LEAVES applies only to preloading')
            clauses.append(clause)
        sql=('CACHE INDEX 'if operation=='assign_index_cache'else'LOAD INDEX INTO CACHE ')+','.join(clauses)
        if operation=='assign_index_cache':sql+=' IN '+identifier(cache)
    return lifecycle.pack(__import__(__name__,fromlist=['']),operation,draft,target,sql,params,table_operation)


def cache_source(cache):return 'SELECT '+','.join('@@GLOBAL.'+identifier(cache)+'.'+identifier(field)for field in VARIABLES)


def observe(cursor,intent):
    draft=intent['draft'];cache=draft.get('cache_name','default')
    cursor.execute(cache_source(cache));row=cursor.fetchone()
    if not row or len(row)!=len(VARIABLES)or any(type(v)is not int or not 0<=v<=2**64-1 for v in row):raise RelationalClientError('Native cache values are unavailable')
    result={'cache_name':cache,'values':dict(zip(VARIABLES,map(str,row))),'cache_existence_attested':False}
    if intent['operation']=='preload_index_cache':
        result={'table_cache_assignment_observed':False,'default_cache_values':result['values']}
    cursor.execute('SELECT VARIABLE_NAME,VARIABLE_TYPE,VARIABLE_SCOPE,READ_ONLY,NUMERIC_MIN_VALUE,NUMERIC_MAX_VALUE,NUMERIC_BLOCK_SIZE FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_NAME IN ('+','.join(['%s']*len(VARIABLES))+') ORDER BY VARIABLE_NAME',VARIABLES)
    facts=cursor.fetchall()
    if len(facts)!=6:raise RelationalClientError('Native cache variable eligibility is incomplete')
    result['native_variable_admission']=[[value(v)for v in row]for row in facts]
    result['native_variable_admission_columns']=['variable_name','type','scope','read_only','minimum','maximum','block_size']
    cursor.execute('SELECT DISTINCT KEY_CACHE_NAME,SEGMENTS FROM information_schema.KEY_CACHES ORDER BY KEY_CACHE_NAME LIMIT 20001')
    layout=cursor.fetchall()
    if len(layout)>20000:raise RelationalClientError('Native cache inventory exceeds the 20000-entry budget')
    result['configured_cache_layout']=[[value(v)for v in row]for row in layout]
    result['cache_existence_attested']=any(row[0]==cache for row in result['configured_cache_layout'])
    if intent['operation']in {'assign_index_cache','preload_index_cache'}:
        result['tables']=[]
        for selection in targets(draft):
            path=(selection['database'],selection['table'])
            cursor.execute('SELECT ENGINE,TABLE_TYPE FROM information_schema.TABLES WHERE BINARY TABLE_SCHEMA=BINARY %s AND BINARY TABLE_NAME=BINARY %s',path)
            if cursor.fetchone()!=('MyISAM','BASE TABLE'):raise RelationalClientError('Native cache handlers require visible MyISAM base tables')
            cursor.execute('SHOW CREATE TABLE '+'.'.join(map(identifier,path)));definition=cursor.fetchone()
            if not definition or definition[0]!=path[1]:raise RelationalClientError('Native table definition is unavailable')
            cursor.execute('SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS WHERE BINARY TABLE_SCHEMA=BINARY %s AND BINARY TABLE_NAME=BINARY %s ORDER BY INDEX_NAME',path)
            indexes=[row[0]for row in cursor.fetchall()]
            if any(n not in indexes for n in selection['indexes']):raise RelationalClientError('An exact selected index is unavailable')
            cursor.execute('SELECT PARTITION_NAME FROM information_schema.PARTITIONS WHERE BINARY TABLE_SCHEMA=BINARY %s AND BINARY TABLE_NAME=BINARY %s AND PARTITION_NAME IS NOT NULL ORDER BY PARTITION_NAME',path)
            partitions=[row[0]for row in cursor.fetchall()]
            if any(n not in partitions for n in draft.get('partitions',[]))or draft.get('all_partitions')and not partitions:raise RelationalClientError('A native partition selection is unavailable')
            result['tables'].append(dict(table_path=list(path),indexes=indexes,partitions=partitions,
                definition_sha256=hashlib.sha256(definition[1].encode()).hexdigest(),table_generation_attested=False))
        if intent['operation']=='assign_index_cache'and result['values']['key_buffer_size']=='0':raise RelationalClientError('Configure the selected native cache before assignment')
    return result


def reported_success(intent,columns,rows):
    if intent['operation']not in {'assign_index_cache','preload_index_cache'}:return True
    return bool(rows)and columns==['Table','Op','Msg_type','Msg_text']and all(row[2]=='status'and row[3]=='OK'for row in rows)


def bind_review(client,planned):return lifecycle.bind_review(__import__(__name__,fromlist=['']),client,planned)
def apply(client,request,connection=None):return lifecycle.apply(__import__(__name__,fromlist=['']),client,request,connection)
