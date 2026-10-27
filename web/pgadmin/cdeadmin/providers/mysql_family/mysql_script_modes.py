"""Nonexecuting script framing through deterministic SQL mode assignments.

Native SQL validates grammar and canonicalizes mode values on the private peer.
Runtime expressions with no known value leave subsequent framing unconfirmed.
"""
import hashlib
import re

from .mysql_script import Statements, MySQLScriptFramingError


UNKNOWN = object()
UNOBSERVED = object()
WORD = re.compile(r'[A-Za-z0-9_$\u0080-\U0010ffff]+')


def fold(value):
    return value.translate(str.maketrans('abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'))


def tokens(source, mode, head_only=False):
    modes=set(mode.split(','));result=[];position=0
    while position<len(source):
        if head_only and result:return result[:1]
        if len(result)>2048:raise ValueError('Mode expression exceeds its inference bound')
        char=source[position];pair=source[position:position+2]
        if char.isspace():position+=1;continue
        if char=='#' or pair=='--' and (position+2==len(source) or ord(source[position+2])<=32):
            end=source.find('\n',position);position=len(source) if end<0 else end;continue
        if pair=='/*':
            end=source.find('*/',position+2)
            if end<0:raise ValueError('Unterminated mode comment')
            if source[position+2:position+3]=='!':
                body=source[position+3:end];version=re.match(r'([0-9]{5,6})',body)
                if version is None or int(version[1])<=90700:
                    result.extend(tokens(body[version.end():] if version else body,mode,head_only))
            position=end+2;continue
        if char in "'\"`":
            quote=char;identifier=quote=='`' or quote=='"' and 'ANSI_QUOTES' in modes
            position+=1;value=[]
            while position<len(source):
                char=source[position];position+=1
                if char==quote:
                    if source[position:position+1]==quote:value.append(quote);position+=1;continue
                    break
                if char=='\\' and not identifier and 'NO_BACKSLASH_ESCAPES' not in modes:
                    if position==len(source):raise ValueError('Unterminated mode literal')
                    escaped=source[position];position+=1
                    value.append({'0':'\x00','b':'\b','n':'\n','r':'\r','t':'\t','Z':'\x1a','%':'\\%','_':'\\_'}.get(escaped,escaped))
                else:value.append(char)
            else:raise ValueError('Unterminated mode literal')
            result.append(('identifier' if identifier else 'literal',''.join(value)));continue
        word=WORD.match(source,position)
        if word:
            result.append(('word',word[0]));position=word.end();continue
        result.append(('punctuation',char));position+=1
    return result


def groups(items, separator=','):
    result=[];part=[];depth=0
    for kind,value in items:
        if kind=='punctuation' and value=='(':depth+=1
        if kind=='punctuation' and value==')':depth-=1
        if not depth and kind=='punctuation' and value==separator:result.append(part);part=[]
        else:part.append((kind,value))
    result.append(part)
    return result


class Modes:
    def __init__(self, mode, canonicalize):
        self.mode=mode;self.canonicalize=canonicalize;self.variables={};self.global_mode=UNOBSERVED

    def global_value(self):
        if self.global_mode is UNOBSERVED:
            self.global_mode=self.canonicalize.default_mode() if self.canonicalize is not None else UNKNOWN
        return self.global_mode

    def expression(self, items):
        if not items:return UNKNOWN
        if len(items)==1:
            kind,value=items[0]
            if kind=='literal':return value
            if kind=='word' and value.isascii() and value.isdigit():return int(value)
            if kind=='word' and fold(value) in {'TRUE','FALSE'}:return int(fold(value)=='TRUE')
            if kind=='word' and fold(value)=='DEFAULT':return self.global_value()
        if items[0]==('punctuation','@'):
            if len(items)==2 and items[1][0] in {'word','identifier','literal'}:
                name=items[1][1]
                # Native variable-name collations are not approximated with
                # Python Unicode folding. Such values remain runtime context.
                return self.variables.get(fold(name),UNKNOWN) if name.isascii() else UNKNOWN
            if items[1:2]==[('punctuation','@')]:
                tail=items[2:]
                if not (len(tail)==1 and tail[0][0] in {'word','identifier'} or
                        len(tail)==3 and tail[0][0] in {'word','identifier'} and
                        tail[1]==('punctuation','.') and tail[2][0] in {'word','identifier'}):return UNKNOWN
                names=[fold(value) for kind,value in tail if kind in {'word','identifier'}]
                if names in (['SQL_MODE'],['SESSION','SQL_MODE'],['LOCAL','SQL_MODE']):return self.mode
                if names==['GLOBAL','SQL_MODE']:return self.global_value()
        if items[0][0]=='word' and fold(items[0][1])=='CONCAT' and items[1:2]==[('punctuation','(')] and items[-1:]==[('punctuation',')')]:
            values=[self.expression(part) for part in groups(items[2:-1])]
            if all(isinstance(value,(str,int)) and type(value) is not bool for value in values):return ''.join(map(str,values))
        if len(items)==2 and items[0][0]=='word' and items[0][1].startswith('_') and items[1][0]=='literal':
            return items[1][1] if items[1][1].isascii() else UNKNOWN
        return UNKNOWN

    def apply(self, source):
        head=tokens(source,self.mode,head_only=True)
        if not head:return
        first=fold(head[0][1]) if head[0][0]=='word' else ''
        if first!='SET':
            if self.variables:
                # Preserve saved values across declarative DDL only. Executable
                # expressions, CTAS and invoked programs may change variables.
                try:
                    declarative=first in {'CREATE','ALTER','DROP','TRUNCATE','RENAME'} and not any(
                        kind=='word' and fold(value)=='SELECT' or (kind,value)==('punctuation','@')
                        for kind,value in tokens(source,self.mode))
                except ValueError:declarative=False
                if not declarative:self.variables.clear()
            return
        items=tokens(source,self.mode)
        items=items[1:];scope='SESSION'
        if items and items[0][0]=='word' and fold(items[0][1]) in {'GLOBAL','SESSION','LOCAL','PERSIST','PERSIST_ONLY'}:
            scope=fold(items[0][1]);items=items[1:]
        for part in groups(items):
            equal=next((index for index,value in enumerate(part) if value==('punctuation','=')),None)
            if equal is None:continue
            left=part[:equal];right=part[equal+1:]
            if left[-1:]==[('punctuation',':')]:left=left[:-1]
            value=self.expression(right)
            if value is UNKNOWN:self.variables.clear()
            if left[:1]==[('punctuation','@')] and left[1:2]!=[('punctuation','@')]:
                if len(left)==2 and left[1][0] in {'word','identifier','literal'} and left[1][1].isascii():
                    self.variables[fold(left[1][1])]=value
                else:self.variables.clear()
                continue
            names=[fold(text) for kind,text in left if kind in {'word','identifier'}]
            if not names or names[-1]!='SQL_MODE':continue
            selected=names[0] if len(names)>1 else scope
            if selected=='PERSIST_ONLY':continue
            if selected in {'GLOBAL','PERSIST'} and len(right)==1 and right[0][0]=='word' and fold(right[0][1])=='DEFAULT':
                # GLOBAL DEFAULT is the compiled server default, whereas
                # SESSION DEFAULT reads the global value. Never substitute one.
                self.global_mode=UNKNOWN
                continue
            canonical=UNKNOWN
            if value is not UNKNOWN and self.canonicalize is not None:
                try:canonical=self.canonicalize(value)
                except Exception:canonical=UNKNOWN
            if selected in {'GLOBAL','PERSIST'}:self.global_mode=canonical
            else:self.mode=canonical


def frame(source, mode, canonicalize):
    model=Modes(mode,canonicalize);framer=Statements(source);statements=[];diagnostics=[]
    result={'language_profile':'mysql-sql','source_sha256':hashlib.sha256(source.encode('utf8')).hexdigest(),
        'statements':statements,'diagnostics':diagnostics,'client_directives':[],
        'grammar_valid':None,'syntax_valid':None,'script_ready':False}
    while True:
        if model.mode is UNKNOWN:
            if any(framer.has_next('9.7.0',candidate) for candidate in ('','ANSI_QUOTES','NO_BACKSLASH_ESCAPES','ANSI_QUOTES,NO_BACKSLASH_ESCAPES')):
                offset=framer.position
                diagnostics.append({'code':'NATIVE_FUTURE_MODE','message':'A runtime SQL mode value is required before the remaining script can be framed. No submitted SQL was executed.',
                    'severity':'warning','offset':offset,'line':source.count('\n',0,offset)+1,'column':offset-source.rfind('\n',0,offset)})
            break
        try:
            start=framer.position;raw=framer.next('9.7.0',model.mode)
            if raw is None:break
            if len(statements)>=1000:
                diagnostics.append({'code':'SCRIPT_LIMIT','message':'Script exceeds 1000 statements.','severity':'error','offset':start,'line':1,'column':1});break
            # The returned source is an exact suffix before the client delimiter.
            # Locate it from the end so comments/empty earlier commands cannot
            # make a repeated token produce an earlier diagnostic position.
            at=source.rfind(raw,start,framer.position)
            if at<0:raise MySQLScriptFramingError('Native script source position is unavailable')
            leading=len(raw)-len(raw.lstrip());text=raw.strip()
            item={'ordinal':len(statements)+1,'source':text,'start':at+leading,'end':at+len(raw.rstrip()),
                  'sql_mode':model.mode,'syntax_context':{'sql_mode':model.mode},'syntax_context_statement':True}
            statements.append(item)
            model.apply(text)
        except (ValueError,TypeError):
            diagnostics.append({'code':'NATIVE_SCRIPT_FRAMING','message':'The next native command or its future language context is unconfirmed.',
                'severity':'warning','offset':framer.position,'line':1,'column':1});break
    if not statements and not diagnostics:
        diagnostics.append({'code':'EMPTY_SOURCE','message':'Source is empty.','severity':'error','offset':0,'line':1,'column':1})
    return result
