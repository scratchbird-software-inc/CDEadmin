"""Native stored libraries and server loadable functions are distinct objects."""
import base64
from ..sdk.relational import RelationalClientError
from .mysql_tablespaces import identifier

OPERATIONS={'library':frozenset({'create','alter','drop'}),'loadable-function':frozenset({'create','drop'})}
RETURNS=('STRING','REAL','INTEGER','DECIMAL')


def text(value,label,limit=65535):
    if not isinstance(value,str) or '\x00' in value or len(value.encode('utf8'))>limit:
        raise RelationalClientError(label+' requires bounded native text without NUL')
    return value


def compile_operation(kind,operation,draft,target):
    if operation not in OPERATIONS.get(kind,()) or not isinstance(draft,dict):
        raise RelationalClientError('Native program object operation is unavailable')
    options=({'name','database','body','source_format','comment','if_not_exists'} if kind=='library' else
             {'name','return_type','aggregate','library'}) if operation=='create' else {'confirmation'}|({'comment'} if operation=='alter' else set())
    if set(draft)-options:raise RelationalClientError('Unknown native program object option')
    path=([draft.get('database'),draft.get('name')] if kind=='library' else [draft.get('name')]) if operation=='create' else (target or {}).get('display_path',[])
    if not isinstance(path,list) or len(path)!=(2 if kind=='library' else 1):raise RelationalClientError('Exact native program object identity is required')
    qualified='.'.join(identifier(part) for part in path)
    if kind=='loadable-function' and operation!='create':
        native=(target or {}).get('native') or (target or {}).get('extensions',{}).get('mysql',{}).get('native',{})
        if native.get('registration_origin')!='mysql.func':raise RelationalClientError('Component/plugin runtime functions use their owning lifecycle')
    if operation=='drop':return {'source':'DROP '+('LIBRARY ' if kind=='library' else 'FUNCTION ')+qualified,'parameters':()}
    if operation=='alter':return {'source':'ALTER LIBRARY '+qualified+' COMMENT %s','parameters':(text(draft.get('comment'),'Comment'),)}
    if kind=='loadable-function':
        result=draft.get('return_type');aggregate=draft.get('aggregate',False)
        if result not in RETURNS or type(aggregate) is not bool:raise RelationalClientError('Select a native return type and aggregate state')
        library=text(draft.get('library'),'Native SONAME',255)
        if not library:raise RelationalClientError('Native SONAME is required')
        return {'source':'CREATE '+('AGGREGATE ' if aggregate else '')+'FUNCTION '+qualified+' RETURNS '+result+' SONAME %s','parameters':(library,)}
    existence=draft.get('if_not_exists',False)
    if type(existence) is not bool:raise RelationalClientError('IF NOT EXISTS must be boolean')
    source='CREATE LIBRARY '+('IF NOT EXISTS ' if existence else '')+qualified+' LANGUAGE JAVASCRIPT'
    parameters=[]
    if 'comment' in draft:source+=' COMMENT %s';parameters.append(text(draft['comment'],'Comment'))
    mode=draft.get('source_format','text');body=draft.get('body')
    if mode=='text':
        parameters.append(text(body,'Library source',1024*1024));source+=' AS %s'
    elif mode=='binary_base64':
        if not isinstance(body,str) or len(body)>1400000:raise RelationalClientError('Binary library requires bounded base64')
        try:binary=base64.b64decode(body,validate=True)
        except ValueError as error:raise RelationalClientError('Binary library requires exact base64') from error
        if len(binary)>1024*1024:raise RelationalClientError('Library source exceeds 1 MiB')
        source+=" AS X'"+binary.hex()+"'"
    else:raise RelationalClientError('Select text or binary_base64 source')
    return {'source':source,'parameters':tuple(parameters)}


def form(kind,operation,field):
    fields=[]
    if operation=='create':
        if kind=='library':fields.append(field('database','Database','text',True))
        fields.append(field('name','Native name','text',True))
        if kind=='library':fields += [field('if_not_exists','IF NOT EXISTS','boolean',default=False),
            field('source_format','Source format','select',True,default='text',options=('text','binary_base64')),
            field('body','JavaScript source or exact base64 bytes','multiline',True),field('comment','Comment (optional)','text')]
        else:fields += [field('return_type','Native return type','select',True,options=RETURNS),
            field('aggregate','Aggregate function','boolean',default=False),field('library','Native SONAME','text',True)]
    if operation=='alter':fields.append({**field('comment','Comment','text',True),'initial_value_path':['library_comment']})
    if operation!='create':fields.append(field('confirmation','Confirmation','text',True))
    return {'form_id':'mysql.'+kind+'.'+operation,'title':operation.title()+' native MySQL '+kind,'fields':fields}
