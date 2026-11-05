"""Native SHOW CREATE view headers, including engine materialization diagnostics."""
import re
TOKEN=r'(?:`(?:``|[^`])+`|"(?:""|[^"])+")'
HEADER=re.compile(r'^\s*CREATE\s+(?:ALGORITHM\s*=\s*(?:UNDEFINED|MERGE|TEMPTABLE)\s+)?'
    r'(?:(?P<materialized>MATERIALIZED)\s+(?:/\*\(BY ENGINE=(?P<engine>[A-Za-z0-9_]+)\)\*/\s+)?)?'
    r'(?:DEFINER\s*=\s*'+TOKEN+r'\s*@\s*'+TOKEN+r'\s+)?'
    r'(?:SQL\s+SECURITY\s+(?:DEFINER|INVOKER)\s+)?VIEW\s+'
    r'(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?(?=\s|\()',re.I)
ALIASES=re.compile(r'\s*\((?P<names>'+TOKEN+r'(?:\s*,\s*'+TOKEN+r')*)\)\s+AS\b',re.I)


def declared_aliases(source):
    """The column list a view declares in its SHOW CREATE source, in order; empty when it has none."""
    header=HEADER.match(source or '')
    found=header and ALIASES.match(source,header.end())
    if not found:
        return []
    return [token[1:-1].replace(token[0]*2,token[0]) for token in re.findall(TOKEN,found['names'])]
