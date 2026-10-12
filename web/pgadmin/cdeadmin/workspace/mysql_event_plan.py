"""Exact event identity with complete native schedule/body and definer retained."""
import re
from ..providers.mysql_family.mysql_catalog import identifier

TOKEN=r'(?:`(?:``|[^`])+`|"(?:""|[^"])+")'
HEADER=re.compile(r'^\s*CREATE\s+(?:DEFINER\s*=\s*'+TOKEN+r'\s*@\s*'+TOKEN+r'\s+)?EVENT\s+'
    r'(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?(?=\s)',re.I)


def compile_event(row,operation,database):
    source=row['native'].get('definition')
    if not isinstance(source,str) or not source or '\x00' in source:raise ValueError('Exact native event definition is required')
    match=HEADER.match(source)
    if not match:raise ValueError('Exact quoted native event header is required')
    names=[value[1:-1].replace(value[0]*2,value[0]) for value in (match['first'],match['second']) if value is not None]
    if names not in ([row['name']],[database,row['name']]):raise ValueError('Native event header disagrees with catalog identity')
    target=identifier(database)+'.'+identifier(row['name'])
    intent=row['native'].get('mysql_change')
    if operation=='drop':
        if intent!={'action':'drop','confirmation':row['name']}:raise ValueError('Event removal requires exact native name confirmation')
        return 'DROP EVENT '+target
    if operation not in {'create','alter'} or intent:raise ValueError('Unsupported native event intent')
    if not re.match(r'^\s+ON\s+SCHEDULE\b',source[match.end():],re.I):raise ValueError('Native event schedule is required')
    prefix=re.sub(r'^\s*CREATE\b',operation.upper(),source[:match.start('first')],count=1,flags=re.I)
    return prefix+target+source[match.end():]
