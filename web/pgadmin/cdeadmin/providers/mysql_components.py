"""Native MySQL component lifecycle and install-time scalar configuration."""
import math
import re
from ..sdk.relational import RelationalClientError

OPERATIONS=frozenset({'create','drop'})


def urn(value):
    if not isinstance(value,str) or not 1<=len(value)<=1024 or '\x00' in value:
        raise RelationalClientError('Component requires an exact bounded native URN')
    return value


def compile_operation(operation,draft,target):
    if operation not in OPERATIONS or not isinstance(draft,dict):
        raise RelationalClientError('Native component operation is unavailable')
    if operation=='drop':
        if set(draft)-{'confirmation'}:raise RelationalClientError('Unknown component removal option')
        path=(target or {}).get('display_path',[])
        if not isinstance(path,list) or len(path)!=1:raise RelationalClientError('Exact discovered component URN is required')
        return {'source':'UNINSTALL COMPONENT %s','parameters':(urn(path[0]),)}
    if set(draft)-{'urns','settings'}:raise RelationalClientError('Unknown component installation option')
    values=draft.get('urns')
    if not isinstance(values,list) or not 1<=len(values)<=32:
        raise RelationalClientError('Install requires 1 to 32 distinct component URNs')
    values=[urn(value) for value in values]
    if len(set(values))!=len(values):raise RelationalClientError('Component URNs must be distinct')
    source='INSTALL COMPONENT '+','.join('%s' for _ in values)
    settings=draft.get('settings',[])
    if not isinstance(settings,list) or len(settings)>128:
        raise RelationalClientError('Component settings require at most 128 ordered entries')
    clauses=[];seen=set()
    for item in settings:
        if not isinstance(item,dict) or set(item)!={'scope','name','value'} or item['scope'] not in {'GLOBAL','PERSIST'}:
            raise RelationalClientError('Each component setting requires GLOBAL/PERSIST, name and scalar value')
        name=item['name'];value=item['value']
        if not isinstance(name,str) or len(name)>129 or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}(?:\.[A-Za-z_][A-Za-z_0-9]{0,63})?',name):
            raise RelationalClientError('Exact native component variable name is required')
        if name.lower() in seen:raise RelationalClientError('Component settings must have distinct variable names')
        seen.add(name.lower())
        if (type(value) not in {str,int,float,bool,type(None)} or
                isinstance(value,str) and ('\x00' in value or len(value.encode('utf8'))>16384) or
                type(value) is int and abs(value)>2**53-1 or
                type(value) is float and not math.isfinite(value)):
            raise RelationalClientError('Component setting requires a bounded exact scalar literal')
        clauses.append(item['scope']+' '+name+'=%s');values.append(value)
    if clauses:source+=' SET '+','.join(clauses)
    return {'source':source,'parameters':tuple(values)}


def form(operation,field):
    fields=([field('urns','Native component URNs (JSON array)','json',True,default=[]),
        field('settings','Install-time settings (JSON array)','json',default=[],
            help_text='Each entry: scope GLOBAL or PERSIST, exact name, and scalar value. No expression text.')]
        if operation=='create' else [field('confirmation','Confirmation','text',True)])
    return {'form_id':'mysql.component.'+operation,'title':('Install' if operation=='create' else 'Uninstall')+' native MySQL component','fields':fields}
