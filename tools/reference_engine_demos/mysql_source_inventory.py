"""Read native MySQL grammar facts without treating C++ actions as SQL."""
from bisect import bisect_right
import re

TOKEN=re.compile(r'''(?P<quoted>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")|(?P<word>%?[A-Za-z_][A-Za-z_0-9]*)|(?P<punct>[:|;])''')


def masked(text,actions=False):
    result=list(text);index=depth=0
    def erase(start,end):
        for pos in range(start,end):
            if result[pos]!='\n':result[pos]=' '
    while index<len(text):
        start=index
        if text.startswith('/*',index):
            end=text.find('*/',index+2)
            if end<0:raise ValueError('Unterminated native source comment')
            index=end+2;erase(start,index);continue
        if text.startswith('//',index):
            end=text.find('\n',index+2);index=len(text) if end<0 else end;erase(start,index);continue
        raw=re.match(r'(?:u8|u|U|L)?R"([^\s()\\]{0,16})\(',text[index:]) if text[index] in 'uULR' else None
        if raw:
            end=text.find(')'+raw[1]+'"',index+raw.end())
            if end<0:raise ValueError('Unterminated native raw string')
            index=end+len(raw[1])+2
            if depth:erase(start,index)
            continue
        if text[index] in "'\"":
            quote=text[index];index+=1
            while index<len(text):
                if text[index]=='\\':index+=2;continue
                if text[index]==quote:index+=1;break
                index+=1
            else:raise ValueError('Unterminated native source literal')
            if depth:erase(start,index)
            continue
        if actions and text[index]=='{':depth+=1;erase(index,index+1)
        elif actions and text[index]=='}':
            if depth<=0:raise ValueError('Unbalanced native semantic action')
            depth-=1;erase(index,index+1)
        elif depth:erase(index,index+1)
        index+=1
    if depth:raise ValueError('Unterminated native semantic action')
    return ''.join(result)


class Grammar:
    def __init__(self,text):
        sections=list(re.finditer(r'(?m)^%%\s*$',text))
        if len(sections) not in (1,2):raise ValueError('Select a complete native Bison grammar')
        self.newlines=[match.start() for match in re.finditer('\n',text)]
        self.text=text;self.rules={}
        start,end=sections[0].end(),sections[1].start() if len(sections)==2 else len(text)
        clean=masked(text[start:end],True)
        tokens=[(match.group(),match.lastgroup,start+match.start()) for match in TOKEN.finditer(clean)]
        starts=[index for index,token in enumerate(tokens[:-1]) if token[1]=='word' and tokens[index+1][:2]==(':','punct')]
        for number,index in enumerate(starts):
            name,kind,offset=tokens[index]
            if name in self.rules:raise ValueError('Duplicate native grammar rule: '+name)
            end=starts[number+1] if number+1<len(starts) else len(tokens)
            index+=2;alternatives=[];current=[];terminated=False
            while index<end:
                value,token_kind,position=tokens[index];index+=1
                if token_kind=='punct' and value in ('|',';'):
                    alternatives.append(current);current=[]
                    if value==';':terminated=True;break
                elif value=='%prec':
                    if index>=end:raise ValueError('Incomplete native precedence clause')
                    index+=1
                elif not value.startswith('%'):current.append((value,token_kind,position))
            if not terminated:alternatives.append(current)
            self.rules[name]={'line':self.line(offset),'alternatives':alternatives}

    def line(self,offset):return bisect_right(self.newlines,offset)+1

    def alternatives(self,name,category):
        if name not in self.rules:raise ValueError('Missing native grammar rule: '+name)
        return [{'item_id':category+'.'+str(index).zfill(4),'native_name':' '.join(token[0] for token in rhs),
            'source':'sql/sql_yacc.yy:'+str(self.line(rhs[0][2])),'production':name,
            'inventory_kind':'grammar-entry'} for index,rhs in enumerate((rhs for rhs in self.rules[name]['alternatives'] if rhs),1)]


def command_inventory(text):
    clean=masked(text)
    match=re.search(r'\benum\s+enum_sql_command\s*\{(?P<body>.*?)\};',clean,re.S)
    if match is None:raise ValueError('Native command enum is absent')
    result=[]
    for item in TOKEN.finditer(match['body']):
        name=item.group()
        if item.lastgroup!='word' or not name.startswith('SQLCOM_') or name=='SQLCOM_END':continue
        result.append({'item_id':'commands.'+str(len(result)+1).zfill(4),'native_name':name,
            'source':'include/my_sqlcommand.h:'+str(text.count('\n',0,match.start('body')+item.start())+1),
            'inventory_kind':'native-dispatch-id'})
    if not result or len({row['native_name'] for row in result})!=len(result):raise ValueError('Native command identifiers are ambiguous')
    return result


def type_inventory(grammar,lexical):
    clean=masked(lexical)
    array=re.search(r'static\s+const\s+SYMBOL\s+symbols\[\]\s*=\s*\{(?P<body>.*?)\};',clean,re.S)
    if array is None:raise ValueError('Native lexical symbol registry is absent')
    aliases={}
    for match in re.finditer(r'\bSYM(?:_FN|_HK)?\("([A-Z][A-Z0-9_]*)",\s*([A-Z][A-Z0-9_]*)\)',array['body']):
        aliases.setdefault(match[2],set()).add(match[1])
    heads={'type','int_type','real_type','numeric_type','spatial_type','nchar','varchar','nvarchar','opt_PRECISION'}
    def expand(name,active=()):
        if name in active or name not in grammar.rules:raise ValueError('Unresolved native type head: '+name)
        output=[]
        for rhs in grammar.rules[name]['alternatives']:
            values=[()]
            for token,kind,_offset in rhs:
                if kind=='quoted':break
                if token in aliases:parts=[(word,) for word in sorted(aliases[token])]
                elif token in heads:parts=expand(token,(*active,name))
                else:break
                values=[(*prefix,*part) for prefix in values for part in parts]
            if rhs and values==[()]:raise ValueError('Unrecognized native type head in '+name+': '+rhs[0][0])
            output.extend(values)
        return output
    names=sorted({' '.join(value) for value in expand('type') if value})
    if not names:raise ValueError('No native type spellings were observed')
    return [{'item_id':'data_types.'+str(index).zfill(4),'native_name':name,'source':'sql/sql_yacc.yy:'+str(grammar.rules['type']['line']),
        'lexical_source':'sql/lex.h','inventory_kind':'native-type-keywords'} for index,name in enumerate(names,1)]
