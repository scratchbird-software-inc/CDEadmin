"""Classify qualified MySQL9.7 post-parse refusals; never validate SQL here.

sql/sql_prepare.cc parses the complete native source before prepare_query()
refuses these command families. A header match alone is never acceptance:
the caller must have observed the native 1295 response from that preparation.
"""
import re


FAMILIES={'PROCEDURE','FUNCTION','TRIGGER','VIEW','DATABASE','TABLE'}


def header_tokens(source,modes,version_id):
    """Read only lexical header identities, retaining native quote/comment roles."""
    no_escape='NO_BACKSLASH_ESCAPES' in modes;ansi='ANSI_QUOTES' in modes
    budget=[64]
    def scan(text):
        i=0
        while i<len(text) and budget[0]>0:
            char=text[i];pair=text[i:i+2]
            if char.isspace():i+=1;continue
            if char=='#' or pair=='--' and i+2<len(text) and ord(text[i+2])<=32:
                ends=[position for position in (text.find('\r',i),text.find('\n',i)) if position>=0]
                i=min(ends) if ends else len(text);continue
            if pair=='/*':
                end=text.find('*/',i+2)
                if end<0:return
                if text[i+2:i+3]=='!':
                    body=text[i+3:end];directive=re.match(r'([0-9]{5,6})(?=\s|$)',body)
                    if directive is not None:
                        if int(directive[1])>version_id:i=end+2;continue
                        body=body[directive.end():]
                    yield from scan(body)
                i=end+2;continue
            if char in "'\"`":
                quote=char;i+=1
                escapes=not no_escape and quote!='`' and not (quote=='"' and ansi)
                while i<len(text):
                    if text[i]=='\\' and escapes:i+=2;continue
                    if text[i]==quote:
                        if text[i+1:i+2]==quote:i+=2;continue
                        i+=1;break
                    i+=1
                else:return
                budget[0]-=1;yield ('quoted',None);continue
            word=re.match(r'[A-Za-z0-9_$\u0080-\uffff]+',text[i:])
            if word is not None:
                # Native keywords use ASCII folding, not Unicode uppercasing.
                value=word[0].translate(str.maketrans('abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
                i+=len(word[0]);budget[0]-=1;yield ('word',value);continue
            i+=1;budget[0]-=1;yield ('punctuation',char)
    return list(scan(source))


def post_parse_family(source,modes,version):
    if not re.match(r'^9\.7\.0(?:[-\s]|$)',str(version)):return None
    tokens=header_tokens(source,modes,90700);i=0
    def value(at):return tokens[at][1] if at<len(tokens) else None
    def name(at):return at<len(tokens) and tokens[at][0] in {'word','quoted'}
    if value(i) not in {'CREATE','ALTER','DROP'}:return None
    operation=value(i);i+=1
    if value(i)=='OR' and value(i+1)=='REPLACE':i+=2
    # Native view/routine prefixes precede the owning command keyword.
    if value(i)=='ALGORITHM':
        if value(i+1)!='=' or not name(i+2):return None
        i+=3
    if value(i)=='DEFINER':
        if value(i+1)!='=' or not name(i+2):return None
        i+=2
        if value(i)=='CURRENT_USER':
            i+=1
            if value(i)=='(' and value(i+1)==')':i+=2
        else:
            i+=1
            if value(i)=='@':
                if not name(i+1):return None
                i+=2
                while value(i)=='.' and name(i+1):i+=2
    if value(i)=='SQL' and value(i+1)=='SECURITY' and value(i+2) in {'DEFINER','INVOKER'}:i+=3
    if operation=='CREATE' and value(i)=='AGGREGATE':i+=1
    family=value(i)
    return family.lower() if family in FAMILIES else None
