"""Native pointer parameters with SQLite 3.53 variable-token and slot rules."""
from collections.abc import Mapping
from dataclasses import dataclass
import uuid
import sqlite3

from ...sdk import RelationalClientError


@dataclass(frozen=True)
class ArrayReference:
    array_id:str

    def __post_init__(self):
        try:
            if not isinstance(self.array_id,str) or str(uuid.UUID(self.array_id))!=self.array_id:raise ValueError()
        except (TypeError,ValueError,AttributeError):raise RelationalClientError('Native CARRAY binding requires its exact connection-owned identity') from None


def idchar(char):return ord(char)>=128 or char in '_$' or 'a'<=char<='z' or 'A'<=char<='Z' or '0'<=char<='9'


def tokens(source):
    position=0;length=len(source)
    while position<length:
        char=source[position]
        if char in "'\"`":
            quote=char;position+=1
            while position<length:
                if source[position]==quote:
                    position+=1
                    if position>=length or source[position]!=quote:break
                position+=1
            continue
        if char=='[':
            end=source.find(']',position+1);position=length if end<0 else end+1;continue
        if source.startswith('--',position):
            end=source.find('\n',position+2);position=length if end<0 else end+1;continue
        if source.startswith('/*',position):
            end=source.find('*/',position+2);position=length if end<0 else end+2;continue
        if char=='?':
            end=position+1
            while end<length and '0'<=source[end]<='9':end+=1
            yield position,end,source[position:end];position=end;continue
        if char in ':@$#':
            end=position+1;named=0
            while end<length:
                if idchar(source[end]):named+=1;end+=1
                elif source.startswith('::',end):end+=2
                elif source[end]=='(' and named:
                    end+=1
                    while end<length and source[end] not in ' \t\n\r\v\f)':end+=1
                    if end>=length or source[end]!=')':raise RelationalClientError('Native SQLite variable suffix is incomplete')
                    end+=1;break
                else:break
            if named:yield position,end,source[position:end];position=end;continue
        if idchar(char):
            position+=1
            while position<length and idchar(source[position]):position+=1
            continue
        position+=1


def bind_arrays(connection,source,bound):
    values=bound.values() if isinstance(bound,Mapping) else bound
    if not any(isinstance(value,ArrayReference) for value in values):return source,bound
    highest=0;names={};named={};spans=[]
    for start,end,token in tokens(source):
        if token=='?':highest+=1;index=highest
        elif token.startswith('?'):
            try:index=int(token[1:])
            except ValueError:raise RelationalClientError('Native SQLite numeric binding is invalid') from None
            if index<1 or index>connection.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER):
                raise RelationalClientError('Native SQLite numeric binding exceeds the connection limit')
            highest=max(highest,index)
            if names.get(index) is None:names[index]=token
        else:
            index=named.get(token)
            if index is None:highest+=1;index=highest;named[token]=index;names[index]=token
        spans.append((start,end,index))
    api=connection._cdeadmin_array_api;resolved=dict(bound) if isinstance(bound,Mapping) else list(bound);native_slots=set()
    if not isinstance(bound,Mapping) and len(bound)!=highest:raise RelationalClientError('SQLite binding count differs from the native variable slots')
    for index in range(1,highest+1):
        if isinstance(bound,Mapping):
            name=names.get(index)
            if name is None:raise RelationalClientError('An anonymous SQLite slot requires positional bindings')
            key=name[1:]
            if key not in bound:raise RelationalClientError('A native SQLite binding is missing')
        else:key=index-1
        value=bound[key]
        if isinstance(value,ArrayReference):
            if api is None or value.array_id not in api.arrays:raise RelationalClientError('Native CARRAY belongs to another or closed query connection')
            resolved[key]=value.array_id;native_slots.add(index)
    if not native_slots:return source,bound
    replacement='"'+api.getter_name+'"'
    for start,end,index in reversed(spans):
        if index in native_slots:source=source[:start]+replacement+'('+source[start:end]+')'+source[end:]
    return source,resolved if isinstance(bound,Mapping) else tuple(resolved)
