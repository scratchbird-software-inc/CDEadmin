"""Complete native event controls; omitted ALTER settings remain unchanged."""
import re
from ..sdk.relational import RelationalClientError
from ..data_studio.language_tools import analyze
from .mysql_tablespaces import identifier
from .mysql_views import _account_part
from .mysql_program_objects import text

OPERATIONS=frozenset({'create','alter','rename','drop'})
STATES=('UNCHANGED','ENABLE','DISABLE','DISABLE ON REPLICA')
COMPLETION=('UNCHANGED','PRESERVE','NOT PRESERVE')


def schedule_expression(value):
    value=text(value,'Native event schedule',16384).strip()
    if not re.match(r'^(AT|EVERY)\b',value,re.I):raise RelationalClientError('Native event schedule must begin with AT or EVERY')
    for no_escape in (False,True):
        result=analyze('SELECT '+value,'mysql-sql',script=True,settings={'no_backslash_escapes':no_escape})
        if result['diagnostics'] or len(result['statements'])!=1 or result['statements'][0]['source']!='SELECT '+value:
            raise RelationalClientError('Native event schedule requires one lexically complete expression without a statement delimiter')
    return value


def compile_operation(operation,draft,target,definition):
    if operation not in OPERATIONS or not isinstance(draft,dict):raise RelationalClientError('Native event operation is unavailable')
    draft=dict(draft)
    for alias,canonical in [('parent','database'),('definition','body')]:
        if alias in draft:
            if canonical in draft:raise RelationalClientError('Ambiguous native event option')
            draft[canonical]=draft.pop(alias)
    allowed=({'name','database','schedule','body','preserve','enabled','completion','status','comment','clear_comment','definer_user','definer_host','time_zone','if_not_exists'} if operation=='create' else
        {'schedule','body','preserve','enabled','completion','status','comment','clear_comment','definer_user','definer_host','time_zone','confirmation'} if operation=='alter' else
        {'new_name','new_database','confirmation'} if operation=='rename' else {'confirmation'})
    if set(draft)-allowed:raise RelationalClientError('Unknown native event option')
    path=[draft.get('database'),draft.get('name')] if operation=='create' else (target or {}).get('display_path',[])
    if not isinstance(path,list) or len(path)!=2:raise RelationalClientError('Exact native event database/name is required')
    qualified='.'.join(identifier(part) for part in path)
    if operation=='drop':return {'source':'DROP EVENT '+qualified,'parameters':()}
    if operation=='rename':
        return {'source':'ALTER EVENT '+qualified+' RENAME TO '+identifier(draft.get('new_database') or path[0])+'.'+identifier(draft.get('new_name')),'parameters':()}
    for alias,canonical,true,false in [('preserve','completion','PRESERVE','NOT PRESERVE'),('enabled','status','ENABLE','DISABLE')]:
        if alias in draft:
            if canonical in draft or type(draft[alias]) is not bool:raise RelationalClientError('Ambiguous native event state')
            draft[canonical]=true if draft.pop(alias) else false
    completion=draft.get('completion','NOT PRESERVE' if operation=='create' else 'UNCHANGED')
    state=draft.get('status','ENABLE' if operation=='create' else 'UNCHANGED')
    if completion not in COMPLETION or state not in STATES or (operation=='create' and 'UNCHANGED' in (completion,state)):
        raise RelationalClientError('Select native event completion/status')
    source=operation.upper()+' '
    if 'definer_user' in draft or 'definer_host' in draft:
        source+='DEFINER='+_account_part(draft.get('definer_user'),32)+'@'+_account_part(draft.get('definer_host'),255)+' '
    source+='EVENT '
    exists=draft.get('if_not_exists',False)
    if type(exists) is not bool:raise RelationalClientError('IF NOT EXISTS must be boolean')
    if exists:source+='IF NOT EXISTS '
    source+=qualified;clauses=[];parameters=[]
    schedule=draft.get('schedule')
    if schedule:clauses.append('ON SCHEDULE '+schedule_expression(schedule))
    elif operation=='create':raise RelationalClientError('Native event schedule is required')
    if completion!='UNCHANGED':clauses.append('ON COMPLETION '+completion)
    if state!='UNCHANGED':clauses.append(state)
    clear=draft.get('clear_comment',False)
    if type(clear) is not bool or (clear and 'comment' in draft):raise RelationalClientError('Select either comment text or explicit comment clearing')
    if clear or 'comment' in draft:
        clauses.append('COMMENT %s');parameters.append('' if clear else text(draft['comment'],'Event comment'))
    body=draft.get('body')
    if body:clauses.append('DO '+definition(body))
    elif operation=='create':raise RelationalClientError('Native event body is required')
    if not clauses:raise RelationalClientError('Select at least one native event change')
    statement={'source':source+' '+' '.join(clauses),'parameters':tuple(parameters)}
    zone=draft.get('time_zone')
    if zone is not None:
        if not text(zone,'Event time zone',64):raise RelationalClientError('Event time zone must not be empty')
        statement['mysql_event_time_zone']=zone
    return statement


def form(operation,field):
    if operation=='drop':fields=[]
    elif operation=='rename':fields=[field('new_name','New event name','text',True),field('new_database','New database (blank keeps current)','text')]
    else:
        fields=([field('database','Database','text',True),field('name','Event name','text',True),field('if_not_exists','IF NOT EXISTS','boolean',default=False)] if operation=='create' else [])
        fields += [field('schedule','Native schedule expression','text',operation=='create'),
            field('completion','After completion','select',True,default='NOT PRESERVE' if operation=='create' else 'UNCHANGED',options=COMPLETION[1:] if operation=='create' else COMPLETION),
            field('status','Event status','select',True,default='ENABLE' if operation=='create' else 'UNCHANGED',options=STATES[1:] if operation=='create' else STATES),
            field('time_zone','Event time zone (blank uses connection setting)','text'),
            field('comment','Comment (optional)','text'),field('clear_comment','Clear comment','boolean',default=False),
            field('definer_user','Definer user (optional exact account)','text'),field('definer_host','Definer host (required with user)','text'),
            field('body','Native event body','code',operation=='create')]
    if operation!='create':fields.append(field('confirmation','Confirmation','text',True))
    return {'form_id':'mysql.event.'+operation,'title':operation.title()+' native MySQL event','fields':fields}
