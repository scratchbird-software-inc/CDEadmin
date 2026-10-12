"""Exact native ordinary-view targets; the server validates the query grammar."""
import re
from ..providers.mysql_family.mysql_catalog import identifier

TOKEN = r'(?:`(?:``|[^`])+`|"(?:""|[^"])+")'
HEADER = re.compile(r'^\s*CREATE\s+(?:ALGORITHM\s*=\s*(?:UNDEFINED|MERGE|TEMPTABLE)\s+)?'
    r'(?:DEFINER\s*=\s*'+TOKEN+r'\s*@\s*'+TOKEN+r'\s+)?'
    r'(?:SQL\s+SECURITY\s+(?:DEFINER|INVOKER)\s+)?VIEW\s+'
    r'(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?(?=\s|\()',re.I)


def compile_view(row, operation, database):
    source=row['native'].get('definition')
    if not isinstance(source,str) or not source or '\x00' in source:
        raise ValueError('Exact native view definition is required')
    match=HEADER.match(source)
    if not match:raise ValueError('Exact quoted native ordinary-view header is required')
    def unquote(value):return value[1:-1].replace(value[0]*2,value[0])
    names=[unquote(value) for value in (match['first'],match['second']) if value is not None]
    if names not in ([row['name']],[database,row['name']]):
        raise ValueError('Native view header disagrees with catalog identity')
    target=identifier(database)+'.'+identifier(row['name'])
    if operation=='drop':
        if row['native'].get('mysql_change')!={'action':'drop','confirmation':row['name']}:
            raise ValueError('View removal requires exact native name confirmation')
        return 'DROP VIEW '+target
    if operation not in {'create','alter'} or row['native'].get('mysql_change'):
        raise ValueError('Unsupported native view intent')
    prefix=re.sub(r'^\s*CREATE\b','CREATE OR REPLACE' if operation=='alter' else 'CREATE',source[:match.start('first')],count=1,flags=re.I)
    return prefix+target+source[match.end():]
