"""Native stored-routine identity and explicit characteristic-only ALTER intent."""
import re
from ..providers.mysql_family.mysql_catalog import identifier
from .firebird_catalog_import import _equal

TOKEN=r'`(?:``|[^`])+`'
HEADER=re.compile(r'^\s*CREATE\s+(?:DEFINER\s*=\s*'+TOKEN+r'\s*@\s*'+TOKEN+r'\s+)?'
    r'(?P<kind>PROCEDURE|FUNCTION)\s+(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?(?=\s*\()',re.I)


def compile_routine(row,operation,database,before=None):
    source=row['native'].get('definition');kind=row['kind']
    if kind not in {'procedure','function'} or not isinstance(source,str) or not source or '\x00' in source:
        raise ValueError('Exact native stored-routine definition is required')
    match=HEADER.match(source)
    if not match or match['kind'].lower()!=kind:raise ValueError('Exact quoted native routine header is required')
    names=[value[1:-1].replace('``','`') for value in (match['first'],match['second']) if value is not None]
    if names not in ([row['name']],[database,row['name']]):raise ValueError('Routine header disagrees with native identity')
    target=identifier(database)+'.'+identifier(row['name']);intent=row['native'].get('mysql_change')
    if operation=='create' and not intent:return source[:match.start('first')]+target+source[match.end():]
    if operation=='drop' and intent=={'action':'drop','confirmation':row['name']}:
        return 'DROP '+kind.upper()+' '+target
    if operation!='alter' or before is None or not isinstance(intent,dict) or intent.get('action')!='alter-characteristics':
        raise ValueError('Routine body replacement is unavailable; use separately reviewed explicit DROP and CREATE or alter-characteristics intent')
    if (set(intent)-{'action','sql_security','data_access','comment'} or len(intent)<2 or
            not _equal({key:before['native'].get(key) for key in ('definition','definition_context')},
                       {key:row['native'].get(key) for key in ('definition','definition_context')})):
        raise ValueError('Characteristic ALTER cannot replace routine body, header or creation context')
    clauses=[]
    if 'sql_security' in intent:
        if intent['sql_security'] not in {'DEFINER','INVOKER'}:raise ValueError('Invalid native routine SQL security')
        clauses.append('SQL SECURITY '+intent['sql_security'])
    if 'data_access' in intent:
        if intent['data_access'] not in {'CONTAINS SQL','NO SQL','READS SQL DATA','MODIFIES SQL DATA'}:
            raise ValueError('Invalid native routine data-access characteristic')
        clauses.append(intent['data_access'])
    if 'comment' in intent:
        comment=intent['comment']
        if not isinstance(comment,str) or len(comment)>65535 or '\x00' in comment:raise ValueError('Invalid native routine comment')
        mode=row['native'].get('definition_context',{}).get('sql_mode','')
        if 'NO_BACKSLASH_ESCAPES' not in mode.split(','):comment=comment.replace('\\','\\\\')
        clauses.append("COMMENT '"+comment.replace("'","''")+"'")
    return 'ALTER '+kind.upper()+' '+target+' '+' '.join(clauses)
