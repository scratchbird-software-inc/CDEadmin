"""MariaDB partition lifecycle; shared lexical checks do not grant native grammar."""
from copy import deepcopy
import re
from . import mysql_partitions as common
from .mysql_tablespaces import identifier
from ..sdk.relational import RelationalClientError

OPERATIONS = {kind: operations | ({'repair','convert_to_table'} if kind=='partition' else {'convert_from_table'})
              for kind, operations in common.OPERATIONS.items()}


def compile_operation(kind, operation, draft, target):
    rows = draft.get('partitions') if isinstance(draft, dict) else None
    if isinstance(rows, list) and any(isinstance(row, dict) for row in rows):
        # The dialog's string-list grid emits {'value': name} rows.
        draft = {**draft, 'partitions': [row.get('value') if isinstance(row, dict) and set(row) <= {'value', '_id'} else row
                                         for row in rows]}
    if operation in common.OPERATIONS.get(kind, ()):
        return common.compile_operation(kind, operation, draft, target)
    if operation not in OPERATIONS.get(kind, ()) or not isinstance(draft, dict):
        raise RelationalClientError('Native MariaDB partition operation is unavailable')
    allowed = {'confirmation'} | ({'exchange_database','exchange_table','validation'} if operation=='convert_to_table'
        else {'exchange_database','exchange_table','definitions','validation'} if operation=='convert_from_table' else set())
    if set(draft)-allowed:raise RelationalClientError('Unknown native MariaDB partition option')
    path=(target or {}).get('display_path')
    if not isinstance(path,list) or len(path)!=(3 if kind=='partition' else 2):
        raise RelationalClientError('Exact native database/table/partition identity is required')
    source='ALTER TABLE '+'.'.join(identifier(value) for value in path[:2])+' '
    if operation=='repair':source+='REPAIR PARTITION '+identifier(path[2])
    else:
        other=identifier(draft.get('exchange_database'))+'.'+identifier(draft.get('exchange_table'))
        validation=draft.get('validation','WITH VALIDATION')
        if validation not in {'WITH VALIDATION','WITHOUT VALIDATION'}:
            raise RelationalClientError('Choose native conversion validation')
        if operation=='convert_to_table':
            source+='CONVERT PARTITION '+identifier(path[2])+' TO TABLE '+other+' '+validation
        else:source+='CONVERT TABLE '+other+' TO PARTITION '+re.sub(r'^PARTITION\s+', '', common.fragment(draft.get('definitions'),True), count=1, flags=re.I)+' '+validation
    return {'source':source,'parameters':()}


def form(kind,operation,field):
    if operation in common.OPERATIONS.get(kind, ()):
        value=deepcopy(common.form(kind,operation,field))
    else:
        fields=[]
        if operation in {'convert_to_table','convert_from_table'}:
            fields += [field('exchange_database','Standalone table database','text',True),
                       field('exchange_table','Standalone table name','text',True)]
        if operation in {'convert_to_table','convert_from_table'}:
            fields.append(field('validation','Validate row placement','select',True,
                default='WITH VALIDATION',options=('WITH VALIDATION','WITHOUT VALIDATION')))
        if operation=='convert_from_table':
            fields.append(field('definitions','Native PARTITION definition','multiline',True))
        fields.append(field('confirmation','Confirmation','text',True))
        value={'fields':fields}
    for item in value['fields']:
        if item['control']=='integer':item.update(control='number',minimum=1,maximum=8192)
    value.update(form_key='mariadb-native-partition-operation', form_id='mariadb.'+kind+'.'+operation,
                 title=operation.replace('_',' ').title()+' native MariaDB partitioning')
    return value
