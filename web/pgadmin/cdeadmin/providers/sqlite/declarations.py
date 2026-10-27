"""Bind catalog CREATE declarations without rewriting expression or trigger bodies.

This reads declaration identifiers, not SQLite SQL grammar. The native compiler
still owns syntax, installed module/function/collation and authorization checks.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int
    quoted: bool = False


def tokens(source):
    if not isinstance(source,str) or not source or '\0' in source or len(source.encode('utf8'))>1024*1024:
        raise ValueError('One bounded native SQLite declaration is required')
    position=0
    while position<len(source):
        char=source[position]
        if char in ' \t\r\n\v\f' or char=='\ufeff':position+=1;continue
        if source.startswith('--',position):
            while position<len(source) and source[position] not in '\r\n':position+=1
            continue
        if source.startswith('/*',position):
            end=source.find('*/',position+2)
            if end<0:raise ValueError('Unterminated SQLite declaration comment')
            position=end+2;continue
        start=position
        if char in "\"`['":
            closing=']' if char=='[' else char
            position+=1;value=[]
            while position<len(source):
                if source[position]==closing:
                    if closing!=']' and position+1<len(source) and source[position+1]==closing:
                        value.append(closing);position+=2;continue
                    position+=1;break
                value.append(source[position]);position+=1
            else:raise ValueError('Unterminated SQLite declaration identifier')
            yield Token(''.join(value),start,position,True)
        elif char=='_' or char.isalpha() or ord(char)>=128:
            position+=1
            while position<len(source) and (source[position].isalnum() or source[position] in '_$' or ord(source[position])>=128):position+=1
            yield Token(source[start:position],start,position)
        else:
            position+=1;yield Token(char,start,position)


def quote(value):
    if not isinstance(value,str) or not value or '\0' in value:raise ValueError('An exact SQLite declaration identifier is required')
    return '"'+value.replace('"','""')+'"'


def fold(value):return value.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))


def canonical_create(source,kind,schema,name,*,owner=None,owner_schema=None):
    """Generate a native CREATE header for the DDN target's explicit scope.

    Catalog SQL commonly omits its database qualifier. A contradictory explicit
    qualifier is refused. IF NOT EXISTS is a creation policy, not a property of
    the desired object; reviewed migrations create the object explicitly.
    """
    if kind not in {'table','view','index','trigger','fts-table','virtual-table'}:
        raise ValueError('Select a native SQLite CREATE declaration kind')
    quote(schema);quote(name)
    stream=iter(tokens(source));pending=None
    def take():
        nonlocal pending
        if pending is not None:item=pending;pending=None;return item
        try:return next(stream)
        except StopIteration:raise ValueError('Incomplete SQLite CREATE declaration') from None
    def word(item,value):return not item.quoted and fold(item.value)==value.lower()
    def identifier(item):
        if not item.quoted and (not item.value or not (item.value[0]=='_' or item.value[0].isalpha() or ord(item.value[0])>=128)):
            raise ValueError('A native SQLite declaration identifier is required')
        if not item.value:raise ValueError('An empty SQLite declaration identifier is unavailable')
        return item
    if not word(take(),'CREATE'):raise ValueError('One native SQLite CREATE declaration is required')
    item=take();temporary=word(item,'TEMP') or word(item,'TEMPORARY')
    if temporary:item=take()
    virtual=word(item,'VIRTUAL');unique=word(item,'UNIQUE')
    if virtual or unique:item=take()
    native_kind='table' if kind in {'fts-table','virtual-table'} else kind
    if (not word(item,native_kind.upper()) or virtual!=(kind in {'fts-table','virtual-table'}) or
            unique and kind!='index' or temporary and (kind not in {'table','view','trigger'} or fold(schema)!='temp')):
        raise ValueError('SQLite declaration kind or TEMP scope differs from its DDN target')
    item=take()
    if word(item,'IF'):
        if not word(take(),'NOT') or not word(take(),'EXISTS'):raise ValueError('Invalid SQLite CREATE existence clause')
        item=take()
    first=identifier(item);item=take()
    if item.value=='.' and not item.quoted:
        declared_schema=first.value;declared_name=identifier(take());item=take()
        if fold(declared_schema)!=fold(schema):raise ValueError('SQLite CREATE names another database namespace')
    else:declared_name=first
    if declared_name.value!=name:raise ValueError('SQLite CREATE name differs from its exact DDN identity')
    if kind=='table' and (item.value!='(' or item.quoted):
        raise ValueError('SQLite catalog table generation requires its native column declaration')
    header='CREATE '+('VIRTUAL ' if virtual else 'UNIQUE ' if unique else '')+native_kind.upper()+' '+quote(schema)+'.'+quote(name)
    tail=source[declared_name.end:]
    if tail and tail[0] not in ' \t\r\n\v\f(' and not tail.startswith(('/*','--')):
        tail=' '+tail
    if kind not in {'index','trigger'}:return header+tail
    quote(owner)
    # INDEX requires ON immediately. A trigger's event header can contain UPDATE
    # OF identifiers; quoted tokens never masquerade as the ON keyword.
    if kind=='index':
        if not word(item,'ON'):raise ValueError('Native SQLite index owner is unavailable')
    else:
        while not word(item,'ON'):
            if word(item,'BEGIN') or item.value==';':raise ValueError('Native SQLite trigger owner is unavailable')
            item=take()
    owner_token=identifier(take());next_token=take();owner_start=owner_token.start
    expected_schema=owner_schema or schema
    quote(expected_schema)
    if next_token.value=='.' and not next_token.quoted:
        if kind=='index':raise ValueError('Native SQLite CREATE INDEX requires an unqualified owning table')
        if fold(owner_token.value)!=fold(expected_schema):raise ValueError('SQLite declaration names another owning database')
        owner_token=identifier(take())
    if fold(owner_token.value)!=fold(owner):raise ValueError('SQLite declaration names another owning relation')
    if kind=='index' and fold(expected_schema)!=fold(schema):raise ValueError('A native SQLite index must share its owning database')
    if kind=='trigger' and fold(schema)=='temp' and owner_schema is None:
        raise ValueError('A TEMP trigger requires an observed exact owning database')
    if kind=='trigger' and fold(schema)!='temp' and fold(expected_schema)!=fold(schema):
        raise ValueError('A persistent SQLite trigger must share its owning database')
    target=(quote(expected_schema)+'.' if kind=='trigger' and fold(schema)=='temp' else '')+quote(owner)
    between=source[declared_name.end:owner_start]
    if between and between[0] not in ' \t\r\n\v\f' and not between.startswith(('/*','--')):between=' '+between
    return header+between+target+source[owner_token.end:]
