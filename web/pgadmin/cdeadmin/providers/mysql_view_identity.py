"""Native SHOW CREATE view headers, including engine materialization diagnostics."""
import re
TOKEN=r'(?:`(?:``|[^`])+`|"(?:""|[^"])+")'
HEADER=re.compile(r'^\s*CREATE\s+(?:ALGORITHM\s*=\s*(?:UNDEFINED|MERGE|TEMPTABLE)\s+)?'
    r'(?:(?P<materialized>MATERIALIZED)\s+(?:/\*\(BY ENGINE=(?P<engine>[A-Za-z0-9_]+)\)\*/\s+)?)?'
    r'(?:DEFINER\s*=\s*'+TOKEN+r'\s*@\s*'+TOKEN+r'\s+)?'
    r'(?:SQL\s+SECURITY\s+(?:DEFINER|INVOKER)\s+)?VIEW\s+'
    r'(?P<first>'+TOKEN+r')(?:\s*\.\s*(?P<second>'+TOKEN+r'))?(?=\s|\()',re.I)
