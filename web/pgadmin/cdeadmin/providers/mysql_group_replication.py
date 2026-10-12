"""Native Group Replication lifecycle and its registered administration UDFs."""
import re
from ..sdk.relational import RelationalClientError

OPERATIONS=frozenset({'start','stop','set_primary','single_primary','multi_primary','set_protocol',
    'set_write_concurrency','enable_member_action','disable_member_action','reset_member_actions'})
FUNCTIONS={'set_primary':'group_replication_set_as_primary','single_primary':'group_replication_switch_to_single_primary_mode',
    'multi_primary':'group_replication_switch_to_multi_primary_mode','set_protocol':'group_replication_set_communication_protocol',
    'set_write_concurrency':'group_replication_set_write_concurrency','enable_member_action':'group_replication_enable_member_action',
    'disable_member_action':'group_replication_disable_member_action','reset_member_actions':'group_replication_reset_member_actions'}
FIELDS={'start':{'user','password','default_auth'},'set_primary':{'member_uuid','timeout'},'single_primary':{'member_uuid'},
    'set_protocol':{'version'},'set_write_concurrency':{'concurrency'},'enable_member_action':{'action_name','event_name'},
    'disable_member_action':{'action_name','event_name'}}


def text(value,label,limit):
    if not isinstance(value,str) or not value or len(value.encode('utf8'))>limit or any(char in value for char in '\x00\r\n'):
        raise RelationalClientError(label+' requires bounded exact native text')
    return value


def compile_operation(operation,draft,target):
    native=(target or {}).get('native') or (target or {}).get('extensions',{}).get('mysql',{}).get('native',{})
    if operation not in OPERATIONS or not isinstance(draft,dict) or native.get('group_replication_plugin_status')!='ACTIVE':
        raise RelationalClientError('An observed active native Group Replication plugin is required')
    if set(draft)-({'confirmation'}|FIELDS.get(operation,set())):
        raise RelationalClientError('Unknown native Group Replication option')
    parameters=[]
    def bind(value):parameters.append(value);return '%s'
    if operation=='start':
        options=[]
        for field,keyword,limit in [('user','USER',32),('password','PASSWORD',32),('default_auth','DEFAULT_AUTH',64)]:
            if field in draft and draft[field] is not None:
                value=draft[field]
                if field=='password' and value=='':value=''
                else:value=text(value,keyword,limit)
                options.append(keyword+'='+bind(value))
        source='START GROUP_REPLICATION'+(' '+','.join(options) if options else '')
    elif operation=='stop':source='STOP GROUP_REPLICATION'
    else:
        arguments=[]
        if operation in {'set_primary','single_primary'}:
            member=draft.get('member_uuid')
            if member not in (None,'') or operation=='set_primary':
                if not isinstance(member,str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',member):
                    raise RelationalClientError('Exact native member UUID is required')
                arguments.append(bind(member))
        if operation=='set_primary' and draft.get('timeout') is not None:
            timeout=draft['timeout']
            if type(timeout) is not int or not 0<=timeout<=3600:raise RelationalClientError('Native transaction timeout is 0 to 3600 seconds')
            arguments.append(bind(timeout))
        if operation=='set_protocol':
            version=draft.get('version')
            if not isinstance(version,str) or not re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}',version):
                raise RelationalClientError('Native communication protocol requires an exact version')
            arguments.append(bind(version))
        if operation=='set_write_concurrency':
            value=draft.get('concurrency')
            if type(value) is not int or not 1<=value<=2**32-1:raise RelationalClientError('Native write concurrency requires a positive 32-bit integer')
            arguments.append(bind(value))
        if operation in {'enable_member_action','disable_member_action'}:
            arguments=[bind(text(draft.get(field),field,128)) for field in ('action_name','event_name')]
        source='SELECT '+FUNCTIONS[operation]+'('+','.join(arguments)+')'
    return {'source':source,'preview_source':source.replace('%s','<bound-value>'),'parameters':tuple(parameters)}


def form(operation,field):
    fields=[]
    if operation=='start':fields=[field('user','Recovery user (optional)','text'),
        field('password','Recovery password (omit to retain)','password',sensitive=True),field('default_auth','Recovery authentication plugin (optional)','text')]
    if operation in {'set_primary','single_primary'}:fields.append(field('member_uuid','Native member UUID', 'text',operation=='set_primary',
        help_text='Exact server UUID from the observed group member inventory. Blank single-primary selection uses native election.'))
    if operation=='set_primary':fields.append(field('timeout','Running transaction timeout (seconds; optional)','integer'))
    if operation=='set_protocol':fields.append(field('version','Native communication protocol version','text',True))
    if operation=='set_write_concurrency':fields.append(field('concurrency','Native write concurrency','integer',True))
    if operation in {'enable_member_action','disable_member_action'}:fields += [field('action_name','Native member action name','text',True),field('event_name','Native event name','text',True)]
    fields.append(field('confirmation','Confirmation','text',True))
    return {'form_id':'mysql.group-replication.'+operation,'title':operation.replace('_',' ').title()+' — native MySQL Group Replication','fields':fields}
