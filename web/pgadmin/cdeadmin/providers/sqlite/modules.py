"""Nonexecuting native identification of virtual-table module declarations."""
from functools import lru_cache
import sqlite3


@lru_cache(maxsize=512)
def declaration(source):
    if not isinstance(source,str) or not source or len(source.encode('utf8'))>1024*1024:
        return None
    probe=sqlite3.connect(':memory:');observed=[]
    def authorize(action,name,module,database,_context):
        if action==sqlite3.SQLITE_CREATE_VTABLE:observed.append((name,module,database))
        return sqlite3.SQLITE_OK
    try:
        probe.set_authorizer(authorize)
        probe.execute('EXPLAIN '+source).fetchone()
        return observed[0] if len(observed)==1 else None
    except sqlite3.Error:return None
    finally:probe.close()


def family(source):
    native=declaration(source)
    return 'fts-table' if native is not None and native[1].lower() in {'fts3','fts4','fts5'} else 'virtual-table'


def arguments(source):
    """Split native constructor arguments; this does not assert SQL grammar."""
    parts=[];current=[];depth=0;started=False;i=0
    while i<len(source):
        char=source[i];pair=source[i:i+2]
        if pair=='--':
            end=source.find('\n',i+2);i=len(source) if end<0 else end+1
            if started:current.append(' ')
            continue
        if pair=='/*':
            end=source.find('*/',i+2)
            if end<0:raise ValueError('Incomplete native module comment')
            i=end+2
            if started:current.append(' ')
            continue
        if char in {'\'', '"', '`', '['}:
            close=']' if char=='[' else char;start=i;i+=1
            while i<len(source):
                if source[i]==close:
                    i+=1
                    if close!=']' and i<len(source) and source[i]==close:i+=1;continue
                    break
                i+=1
            if started:current.append(source[start:i])
            continue
        if char=='(':
            if started:current.append(char)
            else:started=True
            depth+=1
        elif started and char==')':
            depth-=1
            if depth==0:
                if current or parts:parts.append(''.join(current).strip())
                return parts
            current.append(char)
        elif started and char==',' and depth==1:
            parts.append(''.join(current).strip());current=[]
        elif started:current.append(char)
        i+=1
    if started:raise ValueError('Incomplete native module constructor')
    return []


def unquote(value):
    value=value.strip()
    if len(value)>=2 and value[0] in {'\'', '"', '`', '['} and value[-1]==(']' if value[0]=='[' else value[0]):
        return value[1:-1].replace(value[0]*2,value[0])
    return value


def option(source,name):
    found=[]
    for argument in arguments(source):
        key,separator,value=argument.partition('=')
        if separator and unquote(key).lower()==name:found.append(unquote(value))
    if len(found)>1:raise ValueError('Ambiguous native module option')
    return found[0] if found else None
