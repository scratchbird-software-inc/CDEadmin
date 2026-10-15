"""Explicit selected-database option ALTER; no implicit root replacement."""
import re
from ..providers.mysql_family.mysql_catalog import identifier
from .firebird_catalog_import import _equal


def compile_database(row,operation,database,before):
    intent=row['native'].get('mysql_change')
    if not isinstance(row['native'].get('definition'),str) or not row['native']['definition'] or '\x00' in row['native']['definition']:
        raise ValueError('Database-root changes require an available exact native definition')
    if (operation!='alter' or before is None or row['name']!=database or
            not isinstance(intent,dict) or intent.get('action')!='alter-options' or
            set(intent)-{'action','character_set','collation','encryption'} or len(intent)<2 or
            not _equal({key:before['native'].get(key) for key in ('definition','definition_context')},
                       {key:row['native'].get(key) for key in ('definition','definition_context')})):
        raise ValueError('Database-root changes require explicit alter-options intent with unchanged native baseline; lifecycle belongs to database administration')
    clauses=[]
    for key,prefix in [('character_set','DEFAULT CHARACTER SET '),('collation','DEFAULT COLLATE ')]:
        if key not in intent:continue
        value=intent[key]
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}',value):
            raise ValueError('Exact native charset/collation identifier is required')
        clauses.append(prefix+identifier(value))
    if 'encryption' in intent:
        if intent['encryption'] not in {'Y','N'}:raise ValueError('Native database encryption is Y or N')
        clauses.append("ENCRYPTION = '"+intent['encryption']+"'")
    return 'ALTER DATABASE '+identifier(database)+' '+' '.join(clauses)
