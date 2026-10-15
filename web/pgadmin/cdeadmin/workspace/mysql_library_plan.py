"""Exact library targets and native comment-only alteration, never replacement."""
import re
from ..providers.mysql_family.mysql_catalog import identifier
from .mysql_relational_fields import tokens

TOKEN=r'(?:`(?:``|[^`])+`|"(?:""|[^"])+")'
HEADER=re.compile(r'^\s*CREATE\s+LIBRARY\s+(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?(?=\s)',re.I)


def layout(row,database):
    source=row['native'].get('definition')
    if not isinstance(source,str) or not source or '\x00' in source:
        raise ValueError('Exact native library definition is required')
    match=HEADER.match(source)
    if not match:raise ValueError('Exact quoted native library header is required')
    names=[value[1:-1].replace(value[0]*2,value[0]) for value in (match['first'],match['second']) if value is not None]
    if names not in ([row['name']],[database,row['name']]):raise ValueError('Library header disagrees with native identity')
    tail=source[match.end():].strip();comment=None
    if re.match(r'^COMMENT\b',tail,re.I):
        # Tokenize only the comment literal; library bodies are opaque native
        # source (including dollar quoting/binary) and are never SQL rewritten.
        mode=row['native'].get('definition_context',{}).get('sql_mode','')
        prefix=re.match(r'^COMMENT\s+',tail,re.I)
        if not prefix:raise ValueError('Native library comment is ambiguous')
        rest=tail[prefix.end():]
        # Extract a single quote-aware literal without tokenizing the body.
        if not rest.startswith("'"):raise ValueError('Native library comment requires a string literal')
        i=1;no_escape='NO_BACKSLASH_ESCAPES' in mode.split(',')
        while i<len(rest):
            if rest[i]=='\\' and not no_escape:i+=2;continue
            if rest[i]=="'":
                if i+1<len(rest) and rest[i+1]=="'":i+=2;continue
                comment=rest[:i+1];tail=rest[i+1:].strip();break
            i+=1
        else:raise ValueError('Unclosed native library comment')
        parsed=tokens(comment,mode)
        if len(parsed)!=1 or parsed[0][0]!='quoted':raise ValueError('Native library comment is ambiguous')
    if not re.match(r'^LANGUAGE\s+JAVASCRIPT\s+AS\s+\S',tail,re.I):
        raise ValueError('Exact native JavaScript library body is required')
    return source[match.end():],comment,tail


def compile_library(row,operation,database,before=None):
    tail,comment,body=layout(row,database)
    target=identifier(database)+'.'+identifier(row['name'])
    intent=row['native'].get('mysql_change')
    if operation=='drop':
        if intent!={'action':'drop','confirmation':row['name']}:raise ValueError('Library removal requires exact name confirmation')
        return 'DROP LIBRARY '+target
    if intent:raise ValueError('Unsupported native library intent')
    if operation=='create':return 'CREATE LIBRARY '+target+tail
    if operation!='alter' or before is None:raise ValueError('Library alteration requires its exact baseline')
    _old_tail,_old_comment,old_body=layout(before,database)
    if body!=old_body or before['native'].get('definition_context')!=row['native'].get('definition_context'):
        raise ValueError('ALTER LIBRARY changes only COMMENT; body/language/context replacement is unavailable')
    return 'ALTER LIBRARY '+target+' COMMENT '+(comment if comment is not None else "''")
