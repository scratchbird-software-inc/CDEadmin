"""Registered native replica observers; no utility credential delegation."""
from copy import deepcopy
from ..providers.mysql_family.mysql_clone import rows
from .mysql_monitoring_host import MySQLMonitoringHost


def selected(value):
    if not isinstance(value,list) or len(value)>16:raise ValueError('Select at most 16 registered replica channels')
    result=[];seen=set()
    for item in value:
        if not isinstance(item,dict) or set(item)!={'endpoint_id','channel','max_lag_seconds'}:
            raise ValueError('Select an exact registered replica, channel and lag bound')
        if type(item['endpoint_id']) is not int or item['endpoint_id']<=0:
            raise ValueError('Select a registered native replica endpoint')
        channel=item['channel']
        if not isinstance(channel,str) or len(channel)>64 or '\0' in channel:
            raise ValueError('Select an exact native replication channel')
        lag=item['max_lag_seconds']
        if type(lag) is not int or not 0<=lag<=3600:raise ValueError('Select a native replica lag bound from 0 to 3600 seconds')
        key=item['endpoint_id'],channel
        if key in seen:raise ValueError('Select distinct registered replica channels')
        seen.add(key);result.append(deepcopy(item))
    return result


def available(owner,offset):
    from pgadmin.model import Server
    if type(offset) is not int or not 0<=offset<=1000000:raise ValueError('Select a bounded registration page')
    values=[row for row in Server.query.filter_by(user_id=owner).order_by(Server.id).all()
        if row.endpoint_profile and row.endpoint_profile.profile_id=='mysql-native']
    return {'rows':[{'endpoint_id':row.id,'label':row.name} for row in values[offset:offset+100]],
        'next_offset':offset+100 if len(values)>offset+100 else None}


def resolve(service,owner,item):
    from pgadmin.model import Server
    from ..providers.mysql_family.provider import MySQLPilotProvider
    server=Server.query.filter_by(id=item['endpoint_id'],user_id=owner).first()
    if server is None:raise ValueError('The selected replica registration is unavailable for this owner')
    context,endpoint,_=service.endpoint_service.workspace(server)
    provider=service.endpoint_service.provider_registry.resolve(context).instance
    if context.profile_id!='mysql-native' or not isinstance(provider,MySQLPilotProvider):raise ValueError('Select a native MySQL replica registration')
    provider._require('data_read','resource');provider._require('execute')
    route=deepcopy(endpoint['route'])
    for key in ('pool_name','pool_size','pool_reset_session','init_command'):route.pop(key,None)
    route.update(autocommit=True,connection_timeout=5,read_timeout=2,write_timeout=2)
    return server,provider,route


def sample(connection,channel,source):
    identity=rows(connection,'SELECT @@server_uuid AS server_uuid,VERSION() AS version,CURRENT_USER() AS account')[0]
    status=rows(connection,'SHOW REPLICA STATUS FOR CHANNEL %s',(channel,))
    if identity['version'].split('-')[0]!='9.7.0' or len(status)!=1 or status[0].get('Source_UUID')!=source or identity['server_uuid']==source:
        raise ValueError('The registered native channel does not attest replication from the reviewed source')
    row=status[0]
    lag=row.get('Seconds_Behind_Source')
    return identity,{'channel':channel,'source_uuid':row['Source_UUID'],
        'io_running':row.get('Replica_IO_Running'),'sql_running':row.get('Replica_SQL_Running'),
        'last_io_errno':row.get('Last_IO_Errno'),'last_sql_errno':row.get('Last_SQL_Errno'),
        'seconds_behind_source':str(lag) if type(lag) is int else None}


def admission(service,owner,items,source):
    result=[]
    for item in selected(items):
        server,provider,route=resolve(service,owner,item)
        connection=provider.client._connect({'route':route})
        try:
            identity,_=sample(connection,item['channel'],source)
            result.append({**item,'server_uuid':identity['server_uuid'],'account':identity['account'],
                'configuration_sha256':MySQLMonitoringHost._configuration(server)})
        finally:provider.client._discard_failed_session(connection)
    return result


def open_monitors(service,owner,admitted,source):
    monitors=[]
    try:
        for item in admitted:
            server,provider,route=resolve(service,owner,item)
            if MySQLMonitoringHost._configuration(server)!=item['configuration_sha256']:raise ValueError('The reviewed replica registration changed')
            connection=provider.client._connect({'route':route})
            monitors.append((item,connection,provider.client._discard_failed_session))
            identity,_=sample(connection,item['channel'],source)
            if identity['server_uuid']!=item['server_uuid'] or identity['account']!=item['account']:
                raise ValueError('A replica observer reached another native identity')
        return monitors
    except BaseException:
        for _item,connection,dispose in monitors:dispose(connection)
        raise


def observe(runtime):
    observations=[];ready=True
    for item,connection,_dispose in getattr(runtime,'copy_monitors',[]):
        try:
            identity,value=sample(connection,item['channel'],runtime.review['plan']['server_uuid'])
            if identity['server_uuid']!=item['server_uuid'] or identity['account']!=item['account']:
                raise ValueError('Replica observer identity changed')
            healthy=(value['io_running']=='Yes' and value['sql_running']=='Yes' and not value['last_io_errno'] and not value['last_sql_errno'] and
                value['seconds_behind_source'] is not None and int(value['seconds_behind_source'])<=item['max_lag_seconds'])
            observations.append({**value,'endpoint_id':item['endpoint_id'],'max_lag_seconds':item['max_lag_seconds'],'within_policy':healthy})
            ready=ready and healthy
        except Exception as error:
            ready=False;observations.append({'endpoint_id':item['endpoint_id'],'channel':item['channel'],'within_policy':False,
                'error_type':type(error).__name__,'error_code':getattr(error,'errno',None)})
    root=runtime.copy_workspace
    if root.is_dir():
        pause=root/'lag.pause'
        if ready:pause.unlink(missing_ok=True)
        else:pause.touch(mode=0o600,exist_ok=True)
        (root/'heartbeat').touch(mode=0o600,exist_ok=True)
    runtime.update(replica_observations=observations,replica_policy_ready=ready)
    return ready
