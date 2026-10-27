"""Native MySQL partition operations with explicit table and partition identity."""
import re
from ..sdk.relational import RelationalClientError
from .mysql_tablespaces import identifier

OPERATIONS = {
    'partition': frozenset({'analyze','check','optimize','rebuild','truncate','drop','exchange','reorganize'}),
    'table': frozenset({'add_partitions','coalesce_partitions','remove_partitioning','partition_by'}),
}


def fragment(value, definitions=False):
    if not isinstance(value,str) or not value.strip() or len(value.encode('utf8'))>262144 or '\x00' in value:
        raise RelationalClientError('A bounded native partition fragment is required')
    value=value.strip();quote=None;depth=0;i=0;start=0;clauses=[]
    while i<len(value):
        char=value[i]
        if char=='\\':raise RelationalClientError('Use doubled quotes rather than mode-dependent backslash escapes')
        if quote:
            if char==quote:
                if i+1<len(value) and value[i+1]==quote:i+=2;continue
                quote=None
        elif char in "'\"`":quote=char
        elif char in ';#' or value[i:i+2] in {'/*','--'}:
            raise RelationalClientError('Partition fragments do not accept comments or statement separators')
        elif char=='(':depth+=1
        elif char==',' and depth==0:
            clauses.append(value[start:i]);start=i+1
        elif char==')':
            depth-=1
            if depth<0:raise RelationalClientError('Unbalanced native partition fragment')
        i+=1
    if quote or depth:raise RelationalClientError('Unbalanced native partition fragment')
    if definitions:
        # Every top-level clause must be a native PARTITION definition. Nested
        # VALUES and SUBPARTITION lists remain native grammar, not client SQL.
        clauses.append(value[start:])
        if any(not re.match(r'^\s*PARTITION\s+(?:`(?:``|[^`])+`|[A-Za-z_][A-Za-z_0-9$]*)\s+',clause,re.I) for clause in clauses):
            raise RelationalClientError('Supply native PARTITION definitions without enclosing parentheses')
    elif not re.match(r'^PARTITION\s+BY\s+',value,re.I):
        raise RelationalClientError('Supply a native PARTITION BY clause')
    return value


def compile_operation(kind,operation,draft,target):
    if operation not in OPERATIONS.get(kind,()) or not isinstance(draft,dict):raise RelationalClientError('Native partition operation is unavailable')
    allowed={'confirmation'} | {'exchange':{'exchange_database','exchange_table','validation'},'reorganize':{'partitions','definitions'},
        'add_partitions':{'mode','count','definitions'},'coalesce_partitions':{'count'},'partition_by':{'partition_clause'}}.get(operation,set())
    if set(draft)-allowed:raise RelationalClientError('Unknown native partition option')
    path=(target or {}).get('display_path',[])
    if not isinstance(path,list) or len(path)!=(3 if kind=='partition' else 2):raise RelationalClientError('Exact native database/table/partition identity is required')
    database,table=path[:2];source='ALTER TABLE '+identifier(database)+'.'+identifier(table)+' '
    partition=identifier(path[2]) if kind=='partition' else None
    if operation in {'analyze','check','optimize','rebuild','truncate','drop'}:source+=operation.upper()+' PARTITION '+partition
    elif operation=='exchange':
        validation=draft.get('validation','WITH VALIDATION')
        if validation not in {'WITH VALIDATION','WITHOUT VALIDATION'}:raise RelationalClientError('Choose native exchange validation')
        source+='EXCHANGE PARTITION '+partition+' WITH TABLE '+identifier(draft.get('exchange_database'))+'.'+identifier(draft.get('exchange_table'))+' '+validation
    elif operation=='reorganize':
        selected=draft.get('partitions') or [path[2]]
        if not isinstance(selected,list) or not 1<=len(selected)<=8192 or any(not isinstance(name,str) for name in selected) or len(set(selected))!=len(selected) or path[2] not in selected:
            raise RelationalClientError('Select distinct native partition names including the context partition')
        source+='REORGANIZE PARTITION '+','.join(identifier(name) for name in selected)+' INTO ('+fragment(draft.get('definitions'),True)+')'
    elif operation in {'add_partitions','coalesce_partitions'}:
        mode=draft.get('mode','DEFINITIONS') if operation=='add_partitions' else 'COUNT'
        if mode=='COUNT':
            count=draft.get('count')
            if type(count) is not int or not 1<=count<=8192:raise RelationalClientError('Native partition count requires 1 to 8192')
            source+=('ADD PARTITION PARTITIONS ' if operation=='add_partitions' else 'COALESCE PARTITION ')+str(count)
        elif mode=='DEFINITIONS':source+='ADD PARTITION ('+fragment(draft.get('definitions'),True)+')'
        else:raise RelationalClientError('Choose native partition count or definitions')
    elif operation=='remove_partitioning':source+='REMOVE PARTITIONING'
    else:source+=fragment(draft.get('partition_clause'))
    return {'source':source,'parameters':()}


def form(kind,operation,field):
    fields=[]
    fields.append(field('confirmation','Confirmation','text',True))
    return {'form_id':'mysql.'+kind+'.'+operation,'title':operation.replace('_',' ').title()+' native MySQL partitioning','fields':fields}
