"""Native asynchronous source lists; no application election or credential store."""
from collections.abc import Mapping
from copy import deepcopy
from uuid import UUID

from ...sdk import RelationalClientError
from .mysql_instance import environment, target_uuid
from .relay_positions import peer, failure
from ..mysql_replication import text

OPERATIONS={'add_failover_source':'add_source','remove_failover_source':'delete_source',
    'add_managed_failover':'add_managed','remove_managed_failover':'delete_managed',
    'reset_failover_sources':'reset'}
COLLECTIONS={
    'failover_sources':('replication_asynchronous_connection_failover',
        'CHANNEL_NAME,HOST,PORT,NETWORK_NAMESPACE,WEIGHT,MANAGED_NAME','CHANNEL_NAME,HOST,PORT,NETWORK_NAMESPACE,MANAGED_NAME'),
    'failover_managed':('replication_asynchronous_connection_failover_managed',
        'CHANNEL_NAME,MANAGED_NAME,MANAGED_TYPE,CONFIGURATION','CHANNEL_NAME,MANAGED_NAME')}


def queries(channel=None):
    return [(key,'SELECT '+columns+' FROM performance_schema.'+table+
        (' WHERE CHANNEL_NAME=%s' if channel is not None else '')+' ORDER BY '+order)
        for key,(table,columns,order) in COLLECTIONS.items()]


def integer(value,minimum,maximum):
    if type(value) is not int or not minimum<=value<=maximum:
        raise RelationalClientError('Select a native failover integer in range '+str(minimum)+'..'+str(maximum))
    return value


def uuid(value):
    try:UUID(value);return value
    except (ValueError,TypeError,AttributeError):raise RelationalClientError('An observed native UUID is required') from None


def compile_operation(operation,draft,target):
    if operation not in OPERATIONS or not isinstance(draft,Mapping) or not isinstance(target,Mapping):
        raise RelationalClientError('Select a native asynchronous failover operation')
    reset=operation=='reset_failover_sources'
    native=target.get('native') or target.get('extensions',{}).get('mysql',{}).get('native',{})
    instance=target_uuid(target) if reset else uuid(native.get('server_uuid'))
    channel=None if reset else text(native.get('channel_name'),64)
    if not reset and (target.get('resource_kind')!='replication-channel' or channel.lower().startswith('group_replication_')):
        raise RelationalClientError('Select an asynchronous channel, not a Group Replication internal channel')
    allowed={'confirmation'};parameters=[]
    if reset:
        allowed.add('all_channels')
        if draft.get('all_channels') is not True:raise RelationalClientError('Confirm removal of failover configuration for every channel')
    else:parameters.append(channel)
    if operation in {'add_managed_failover','remove_managed_failover'}:
        allowed.add('managed_name');managed=uuid(draft.get('managed_name')) if operation=='add_managed_failover' else text(draft.get('managed_name'),64)
        if not managed:raise RelationalClientError('A managed source name is required')
        parameters.extend(['GroupReplication',managed] if operation=='add_managed_failover' else [managed])
    if operation in {'add_failover_source','remove_failover_source','add_managed_failover'}:
        allowed|={'host','port'};host=text(draft.get('host'),255)
        if not host or not host.isascii():raise RelationalClientError('Use the native nonempty ASCII source host')
        parameters.extend([host,integer(draft.get('port',3306),1 if operation=='add_managed_failover' else 0,
            65535 if operation=='add_managed_failover' else 2**32-1),''])
    if operation=='add_failover_source':allowed.add('weight');parameters.append(integer(draft.get('weight',50),1,100))
    if operation=='add_managed_failover':
        allowed|={'primary_weight','secondary_weight'}
        parameters.extend([integer(draft.get('primary_weight',80),1,100),integer(draft.get('secondary_weight',60),1,100)])
    if set(draft)-allowed or draft.get('confirmation')!=target.get('display_name'):
        raise RelationalClientError('Confirm the selected native object and failover options')
    source='SELECT asynchronous_connection_failover_'+OPERATIONS[operation]+'('+','.join(['%s']*len(parameters))+')'
    return {'statements':[{'source':source,'parameters':tuple(parameters)}],
        'mysql_failover':{'operation':operation,'draft':deepcopy(dict(draft)),'target':deepcopy(dict(target)),
            'server_uuid':instance,'channel':channel},
        'warnings':['MySQL owns candidate weights, managed membership and automatic source selection. This changes persistent native configuration, not the channel credentials or its SOURCE_CONNECTION_AUTO_FAILOVER flag.',
            'Native failover functions convert string arguments to Latin1 and can reject channel names with native error3854. MySQL9.7 ignores the deprecated failover namespace argument; these calls send an empty value. Managed groups use GroupReplication and the native group UUID.',
            'Review is observational; native monitor or external administration can change these lists. No external writers are fenced, no connection or event delivery is attested and no mutation is automatically replayed.']}


def sections(operation):
    return ('failover_sources',) if operation in {'add_failover_source','remove_failover_source'} else tuple(COLLECTIONS)


def observe(cursor,channel,operation=None):
    result={}
    for key,source in queries(channel):
        if key not in sections(operation):continue
        cursor.execute(source,(channel,) if channel is not None else None)
        names=[column[0].lower() for column in cursor.description]
        rows=cursor.fetchmany(20001)
        if len(rows)>20000:raise RelationalClientError('Native failover inventory exceeds 20000 rows')
        result[key]=[dict(zip(names,row)) for row in rows]
    return result


def bind_review(client,planned):
    payload=planned['provider_payload'];intent=payload['compiled']['mysql_failover']
    with peer(client,payload) as cursor:
        actor=environment(cursor)
        if actor['server_uuid']!=intent['server_uuid']:raise RelationalClientError('Selected failover instance changed')
        before=observe(cursor,intent['channel'],intent['operation']);intent['review']={'identity':actor,'before':before}
        planned['command_preview'].update(native_execution_identity=actor,native_failover_configuration=before)
    return planned


def apply(client,request,connection=None):
    if connection is not None:raise RelationalClientError('Failover configuration requires an independent native connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled['mysql_failover']
    checked=deepcopy(compiled);review=checked['mysql_failover'].pop('review',None)
    if not isinstance(review,Mapping) or compile_operation(intent['operation'],intent['draft'],intent['target'])!=checked:
        raise RelationalClientError('Review the exact native failover change before dispatch')
    dispatched=acknowledged=False
    try:
        with peer(client,payload) as cursor:
            actor=environment(cursor);before=observe(cursor,intent['channel'],intent['operation'])
            if actor!=review['identity'] or before!=review['before']:raise RelationalClientError('Native failover identity or configuration changed since review')
            statement=compiled['statements'][0];dispatched=True
            cursor.execute(statement['source'],statement['parameters'] or None)
            rows=cursor.fetchall()
            if len(rows)!=1 or len(rows[0])!=1 or not isinstance(rows[0][0],str):raise RelationalClientError('Native failover function result is unavailable')
            acknowledged=True;after=observe(cursor,intent['channel'],intent['operation'])
            return {'accepted':True,'native_acknowledged':True,'automatic_retry':False,
                'commit_requested':False,'rollback_requested':False,'staged_in_provider_session':False,
                'driver_observation_only':True,'transaction_finality_interpreted_by_common_code':False,
                'failover_observation':{'execution_identity':actor,'before':before,'after':after,
                    'native_result':rows[0][0],'external_writers_fenced':False,'source_selection_or_delivery_attested':False}}
    except Exception as error:raise failure(error,dispatched,acknowledged) from None
