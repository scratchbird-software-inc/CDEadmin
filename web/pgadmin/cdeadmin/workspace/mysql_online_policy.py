"""Explicit MySQL DDN execution policy; the server decides ALTER support."""
from copy import deepcopy
import hashlib
import re


def policy(value):
    if value is None:return None
    if not isinstance(value,dict) or set(value)-{'method','algorithm','lock','lock_wait_seconds','timeout_seconds','replicas'} or not {'method','algorithm','lock','lock_wait_seconds','timeout_seconds'}<=set(value):
        raise ValueError('Select an exact controlled MySQL ALTER policy')
    if value['method'] not in {'native','pt-online-schema-change'}:
        raise ValueError('Select native ALTER or the admitted online-copy utility')
    if value['algorithm'] not in {'INSTANT','INPLACE','COPY'} or value['lock'] not in {'DEFAULT','NONE','SHARED','EXCLUSIVE'}:
        raise ValueError('Select an explicit native ALGORITHM and LOCK expectation')
    if value['method']=='native' and value['algorithm']=='INSTANT' and value['lock']!='DEFAULT':
        raise ValueError('Native INSTANT requires LOCK=DEFAULT')
    if (type(value['lock_wait_seconds']) is not int or not 1<=value['lock_wait_seconds']<=60 or
            type(value['timeout_seconds']) is not int or not 1<=value['timeout_seconds']<=86400):
        raise ValueError('Select 1–60 lock-wait seconds and 1–86400 runtime seconds')
    if value['method']=='pt-online-schema-change' and (value['algorithm'],value['lock'])!=('COPY','NONE'):
        raise ValueError('The online-copy backend uses explicit COPY / NONE workflow expectations, not native ALGORITHM=')
    if 'replicas' in value:
        from .mysql_online_replicas import selected
        selected(value['replicas'])
        if value['method']!='pt-online-schema-change' and value['replicas']:
            raise ValueError('Only the online-copy backend can pause between chunks for replica lag')
    return deepcopy(value)


def statement(source, selected):
    selected=policy(selected)
    if selected is None or selected['method']!='native':return source
    return source+', ALGORITHM='+selected['algorithm']+', LOCK='+selected['lock']


def advisory(database, table):
    # Shared by controlled native ALTER and utility execution. It fences only
    # cooperating application jobs; it is not a native external-DDL fence.
    import json
    return 'sr-ddn-alter:'+hashlib.sha256(json.dumps([database,table],ensure_ascii=True).encode()).hexdigest()[:48]


def structural_definition(source, mode):
    """Ignore only the volatile next AUTO_INCREMENT counter, outside literals."""
    from .mysql_table_clauses import table_layout
    from .mysql_relational_fields import tokens
    layout=table_layout(source,mode);suffix=layout['suffix'];parsed=tokens(suffix,mode)
    for index,item in enumerate(parsed):
        if item[0]=='word' and item[1].upper()=='AUTO_INCREMENT':
            rest=suffix[item[3]:]
            match=re.match(r'\s*=\s*[0-9]+\b',rest)
            if match:
                suffix=suffix[:item[2]]+suffix[item[3]+match.end():]
                break
    return source[:len(source)-len(layout['suffix'])]+' '.join(item[1] for item in tokens(suffix,mode))
