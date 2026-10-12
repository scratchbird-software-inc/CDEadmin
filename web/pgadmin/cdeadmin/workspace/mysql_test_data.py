"""Bounded MySQL-native recipe materialization. Generation executes no writes."""
import base64
import hashlib
import json
import re
from ..providers.mysql_family.mysql_catalog import identifier

FORMAT = 'scratchrobin.mysql.test-data@1'
LIMIT = 4 * 1024 * 1024
SQL_LIMIT = 1024 * 1024


def integer(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?[0-9]{1,65}', value):
        raise ValueError('Integer sources require exact decimal strings up to 65 digits')
    return int(value)


def literal(value):
    if value is None:return 'NULL'
    if type(value) is bool:return 'TRUE' if value else 'FALSE'
    if type(value) is int and abs(value) <= 2**53-1:return str(value)
    if isinstance(value, str):
        if len(value.encode('utf8')) > SQL_LIMIT:raise ValueError('Text value exceeds 1 MiB')
        return "CONVERT(X'" + value.encode('utf8').hex() + "' USING utf8mb4)"
    if isinstance(value, dict) and set(value) == {'type','value'} and isinstance(value['value'],str):
        kind, data = value['type'], value['value']
        if len(data) > SQL_LIMIT:raise ValueError('Typed value exceeds 1 MiB')
        if kind == 'integer':return str(integer(data))
        if kind == 'decimal' and re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)',data):return data
        if kind == 'binary':
            try:encoded = base64.b64decode(data,validate=True)
            except ValueError:raise ValueError('Invalid base64 binary source') from None
            return "X'" + encoded.hex() + "'"
        if kind == 'json':
            json.loads(data,parse_constant=lambda token: (_ for _ in ()).throw(ValueError('Non-finite JSON source')))
            return 'CAST(' + literal(data) + ' AS JSON)'
        if kind == 'vector':
            components = json.loads(data)
            if not isinstance(components,list) or not 1 <= len(components) <= 16383 or any(
                type(part) not in {int,float} for part in components):raise ValueError('Vector requires bounded numeric components')
            json.dumps(components,allow_nan=False)
            return 'STRING_TO_VECTOR(' + literal(data) + ')'
    raise ValueError('Use text, safe integers or explicit integer/decimal/binary/json/vector sources')


def tables(model):
    if model['provenance'].get('mapping') != 'scratchrobin.mysql.catalog@1':
        raise ValueError('MySQL native catalog is required')
    result = {key:row for key,row in model['rows'].items() if row['kind']=='table' and row.get('system')=='false'}
    for row in result.values():
        identifier(row['native']['database']);identifier(row['name'])
    return result


def columns(row):
    return {fact['column_name']:fact for fact in row['native'].get('children',{}).get('COLUMNS',[])}


def generated(fact):
    return bool(fact.get('generation_expression')) or 'GENERATED' in str(fact.get('extra','')).upper().replace('DEFAULT_GENERATED','')


def template(model):
    return {'format':FORMAT,'scope':{key:model['provenance'][key] for key in ('endpoint_id','database_target_id')},
        'tables':[{'resource_id':key,'schema':row['native']['database'],'name':row['name'],
          'columns':[{'name':name,'data_type':fact['column_type'],'insertable':not generated(fact),
            'auto_increment':'auto_increment' in str(fact.get('extra','')).lower()}
            for name,fact in sorted(columns(row).items(),key=lambda pair:int(pair[1].get('ordinal_position',0)))]}
          for key,row in sorted(tables(model).items())],'executed':False}


def generate(model,recipe):
    scope = {key:model['provenance'][key] for key in ('endpoint_id','database_target_id')}
    if (not isinstance(recipe,dict) or set(recipe) != {'format','scope','seed','tables'} or recipe['format']!=FORMAT or
        recipe['scope']!=scope or type(recipe['seed']) is not int or not 0<=recipe['seed']<=2**32-1 or
        not isinstance(recipe['tables'],list) or not 1<=len(recipe['tables'])<=32):raise ValueError('Invalid or foreign MySQL recipe')
    if len(json.dumps(recipe,allow_nan=False).encode('utf8'))>LIMIT:raise ValueError('Recipe exceeds 4 MiB')
    available,selected,dependencies = tables(model),{},{}
    kinds = {'constant':{'value'},'default':set(),'sequential':{'start','step'},'random-integer':{'min','max'},
        'choice':{'values'},'file':{'values'},'generated':{'table','column'},'returned':{'table','column'},
        'existing':{'table','column','order_by'}}
    for entry in recipe['tables']:
        if not isinstance(entry,dict) or set(entry)!={'table','count','columns'}:raise ValueError('Invalid recipe table')
        key,count,sources=entry['table'],entry['count'],entry['columns']
        if (not isinstance(key,str) or key not in available or key in selected or type(count) is not int or
            not 1<=count<=1000 or not isinstance(sources,dict)):raise ValueError('Unknown/duplicate table or invalid count/sources')
        native_columns = columns(available[key]);dependencies[key]=set()
        for name,source in sources.items():
            if name not in native_columns or not isinstance(source,dict):raise ValueError('Unknown column or invalid source')
            kind=source.get('kind')
            if not isinstance(kind,str) or kind not in kinds or set(source)!=kinds[kind]|{'kind'}:raise ValueError('Unknown generator or fields')
            if generated(native_columns[name]) and kind!='default':raise ValueError('Generated columns require native defaults')
            if kind=='constant':literal(source['value'])
            if kind=='sequential':integer(source['start']);integer(source['step'])
            if kind=='random-integer' and not 1<=integer(source['max'])-integer(source['min'])+1<=2**32:
                raise ValueError('Random range requires 1 to 2^32 values')
            if kind in {'choice','file'}:
                if not isinstance(source['values'],list) or not 1<=len(source['values'])<=1000:raise ValueError('Choice/file sources require 1 to 1000 values')
                for value in source['values']:literal(value)
            if kind in {'generated','returned','existing'}:
                parent=available.get(source['table']) if isinstance(source['table'],str) else None
                if not parent or not isinstance(source['column'],str) or source['column'] not in columns(parent):raise ValueError('Parent column is unavailable')
                if kind in {'generated','returned'}:dependencies[key].add(source['table'])
                else:
                    order=source['order_by']
                    if not isinstance(order,list) or not order or any(not isinstance(name,str) or name not in columns(parent) for name in order) or len(order)!=len(set(order)):
                        raise ValueError('Existing sources require native ordering columns')
                    uniques={}
                    for index in parent['native'].get('children',{}).get('STATISTICS',[]):
                        if index.get('non_unique') in (0,'0'):
                            uniques.setdefault(index['index_name'],[]).append(index)
                    if not any(all(part.get('column_name') in order and not part.get('sub_part') and
                        columns(parent)[part['column_name']].get('is_nullable')=='NO' for part in parts)
                        for parts in uniques.values()):
                        raise ValueError('Existing ordering must contain a captured nonnullable unique key')
        selected[key]=entry
    if sum(row['count'] for row in selected.values())>5000:raise ValueError('Recipe exceeds 5000 rows')
    for key,entry in selected.items():
        dependencies[key].update(source['table'] for source in entry['columns'].values()
            if source['kind']=='existing' and source['table'] in selected and source['table']!=key)
    ordered=[];pending={key:value.copy() for key,value in dependencies.items()}
    while pending:
        ready=sorted(key for key,needs in pending.items() if not needs)
        if not ready:raise ValueError('Generated parent dependency cycle or missing recipe parent')
        for key in ready:ordered.append(key);del pending[key]
        for needs in pending.values():needs.difference_update(ready)
    for key in ordered:
        for source in selected[key]['columns'].values():
            if source['kind'] not in {'generated','returned'}:continue
            parent=selected.get(source['table']);fact=columns(available[source['table']])[source['column']]
            if parent is None:raise ValueError('Generated/returned parent must appear in the recipe')
            if source['kind']=='generated' and parent['columns'].get(source['column'],{}).get('kind') in {None,'default','existing'}:
                raise ValueError('Generated reference requires an explicit generated parent value')
            if source['kind']=='returned' and ('auto_increment' not in str(fact.get('extra','')).lower() or
                parent['columns'].get(source['column'],{}).get('kind','default')!='default'):
                raise ValueError('Returned source requires a native default AUTO_INCREMENT parent')
    namespace='sr_'+hashlib.sha256(json.dumps(recipe,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    lines=['-- MySQL native test data. Review and run in the shared Query Tool.',
        '-- This script does not start, commit or rollback a transaction or disable constraints.',
        '-- Native defaults, triggers, permissions and nontransactional-engine effects apply.']
    materialized={};variables=[];counter=0;size=0
    def emit(source):
        nonlocal size
        size+=len(source.encode('utf8'))+1
        if size>SQL_LIMIT:raise ValueError('Generated script exceeds 1 MiB')
        lines.append(source)
    def random_index(limit):
        nonlocal counter
        counter+=1
        return int.from_bytes(hashlib.sha256(f'{recipe["seed"]}:{counter}'.encode()).digest(),'big')%limit
    for key in ordered:
        entry,row=selected[key],available[key]
        qualified=identifier(row['native']['database'])+'.'+identifier(row['name'])
        for position in range(entry['count']):
            values={}
            for name,source in sorted(entry['columns'].items()):
                kind=source['kind']
                if kind=='default':values[name]='DEFAULT'
                elif kind=='constant':values[name]=literal(source['value'])
                elif kind=='sequential':values[name]=str(integer(source['start'])+position*integer(source['step']))
                elif kind=='random-integer':values[name]=str(integer(source['min'])+random_index(integer(source['max'])-integer(source['min'])+1))
                elif kind in {'choice','file'}:values[name]=literal(source['values'][random_index(len(source['values']))] if kind=='choice' else source['values'][position%len(source['values'])])
                elif kind in {'generated','returned'}:
                    parent_position=position%selected[source['table']]['count']
                    values[name]=materialized[(source['table'],parent_position,source['column'])]
                else:
                    parent=available[source['table']]
                    values[name]='(SELECT '+identifier(source['column'])+' FROM '+identifier(parent['native']['database'])+'.'+identifier(parent['name'])+' ORDER BY '+','.join(identifier(name) for name in source['order_by'])+' LIMIT 1 OFFSET '+str(position%200)+')'
            auto_default = any('auto_increment' in str(fact.get('extra','')).lower() and
                values.get(name,'DEFAULT')=='DEFAULT' for name,fact in columns(row).items())
            if auto_default:emit('DO LAST_INSERT_ID(0);')
            emit('INSERT INTO '+qualified+' ('+','.join(identifier(name) for name in values)+') VALUES ('+','.join(values.values())+');' if values else 'INSERT INTO '+qualified+' () VALUES ();')
            for name,fact in columns(row).items():
                if 'auto_increment' in str(fact.get('extra','')).lower() and values.get(name,'DEFAULT')=='DEFAULT':
                    variable='@'+namespace+'_'+str(len(variables));variables.append(variable)
                    emit('SET '+variable+' = NULLIF(LAST_INSERT_ID(),0);');materialized[(key,position,name)]=variable
                elif name in values and values[name]!='DEFAULT':
                    # Freeze generated values, including scalar dependencies,
                    # for children rather than reevaluating their expressions.
                    variable='@'+namespace+'_'+str(len(variables));variables.append(variable)
                    emit('SET '+variable+' = '+values[name]+';');materialized[(key,position,name)]=variable
    for variable in variables:emit('SET '+variable+' = NULL;')
    output='\n'.join(lines)+'\n'
    if len(output.encode('utf8'))>SQL_LIMIT:raise ValueError('Generated script exceeds 1 MiB')
    return {'format':FORMAT,'source':output,'source_sha256':hashlib.sha256(output.encode()).hexdigest(),
        'rows':sum(entry['count'] for entry in selected.values()),'tables':len(selected),'executed':False,
        'warnings':['Generation performs no native writes; native execution can reject types, constraints or privileges.',
            'Existing sources are read during execution and may change between statements.',
            'LAST_INSERT_ID captures native AUTO_INCREMENT allocation; trigger-supplied IDs without allocation produce NULL parent references.',
            'Autocommit, nontransactional storage and trigger effects determine rollback behavior.']}
