"""Exact native trigger CREATE/DROP; MySQL has no trigger body ALTER."""
import re
from ..providers.mysql_family.mysql_catalog import identifier

TOKEN=r'(?:`(?:``|[^`])+`|"(?:""|[^"])+")'
HEADER=re.compile(r'^\s*CREATE\s+(?:DEFINER\s*=\s*'+TOKEN+r'\s*@\s*'+TOKEN+r'\s+)?TRIGGER\s+'
    r'(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?\s+'
    r'(?P<timing>BEFORE|AFTER)\s+(?P<event>INSERT|UPDATE|DELETE)\s+ON\s+'
    r'(?P<table_first>'+TOKEN+r')(?:\s*\.\s*(?P<table_second>'+TOKEN+r'))?\s+FOR\s+EACH\s+ROW\b',re.I)


def compile_trigger(row,operation,database):
    source=row['native'].get('definition');facts=row['native'].get('trigger_identity',{})
    if not isinstance(source,str) or not source or '\x00' in source:raise ValueError('Exact native trigger definition is required')
    match=HEADER.match(source)
    if not match:raise ValueError('Exact quoted native trigger/owner header is required')
    def values(*keys):return [match[key][1:-1].replace(match[key][0]*2,match[key][0]) for key in keys if match[key] is not None]
    if values('first','second') not in ([row['name']],[database,row['name']]):raise ValueError('Trigger header disagrees with native identity')
    if (facts.get('database')!=database or not isinstance(facts.get('table'),str) or
        values('table_first','table_second') not in ([facts['table']],[database,facts['table']]) or
        facts.get('timing')!=match['timing'].upper() or facts.get('event')!=match['event'].upper()):
        raise ValueError('Trigger owner, timing or event disagrees with native identity')
    target=identifier(database)+'.'+identifier(row['name']);intent=row['native'].get('mysql_change')
    if operation=='drop' and intent=={'action':'drop','confirmation':row['name']}:return 'DROP TRIGGER '+target
    if operation!='create' or intent:raise ValueError('MySQL has no ALTER TRIGGER; use separately reviewed explicit DROP and CREATE')
    return source[:match.start('first')]+target+source[match.end('second') if match['second'] is not None else match.end('first'):]
