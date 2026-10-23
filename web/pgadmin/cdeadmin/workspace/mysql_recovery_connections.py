"""Reviewed native-driver registrations for managed recovery instances."""
from copy import deepcopy
import json
import uuid

from ..providers.mysql_family import mysql_recovery_bridge as bridge
from . import mysql_physical_service as physical
from .mysql_binlog_jobs import MySQLBinlogJobs,digest
from .mysql_monitoring_host import MySQLMonitoringHost


class Connections(MySQLBinlogJobs):
    operation='mysql_recovery_connection'
    review_warnings=(
        'Creates or reattaches a separate native MySQL registration. Source registrations and their SQL sessions are preserved.',
        'Native MySQL protocol, authentication, TLS, data types and transactions pass through a process-bound SSH stream to the reviewed loopback listener. No database password is delegated to the relay.',
        'This transport belongs to the current application process. After application restart, reattach with fresh private SSH authentication. Missing or changed instances refuse connection; there is no network fallback.',
        'The registered recovery instance retains its reviewed read-only or writable replay startup policy and lifetime. Raw and POSIX Shell replay retain their original utility leases. Independent utility observations remain available when SQL transport is unavailable; full post-replay acceptance remains separate.',
    )


def marker(server):
    extension=server.endpoint_profile.extension_profile
    if extension is None or extension.schema_reference!=bridge.SCHEMA:return None
    return json.loads(extension.profile_data)


def targets(owner,job):
    from pgadmin.model import Server,EndpointProfile,EndpointExtensionProfile
    values=Server.query.join(EndpointProfile,EndpointProfile.legacy_server_id==Server.id).join(
        EndpointExtensionProfile,EndpointExtensionProfile.endpoint_id==EndpointProfile.id).filter(
            Server.user_id==owner,EndpointExtensionProfile.schema_reference==bridge.SCHEMA).limit(1001).all()
    if len(values)>1000:raise physical.native.HostError('Select an explicit recovery registration after reducing the registration inventory')
    return [server for server in values if (value:=marker(server))['source_job_id']==job['job_id'] and value['source_endpoint_id']==job['endpoint_id']]


def registration(server):
    value=marker(server);binding=value['binding']
    try:active=bridge.bridges.get(binding).active
    except Exception:active=False
    return {'server_id':server.id,'servergroup_id':server.servergroup_id,'endpoint_id':server.endpoint_profile.id,
        'name':server.name,'binding':binding,'transport_attached':active,
        'database_target_id':next((item.id for item in server.endpoint_profile.database_targets if item.active),None),
        'runtime_scope':'this-application-process','verification_state':server.endpoint_profile.runtime_identity.verification_state}


def manager(service,server):
    jobs,owner,endpoint=physical.manager(service,server)
    with service._semantic_lock:
        connections=getattr(service,'mysql_recovery_connections',None)
        if connections is None:
            path=service.operation_bus.store.path
            connections=service.mysql_recovery_connections=Connections(str(path)+'.mysql-recovery-connections',str(path.parent/'mysql-recovery-connections'))
    return jobs,connections,owner,endpoint


def source_job(jobs,server,owner,endpoint,job_id):
    value=marker(server)
    if value is not None:
        if job_id not in (None,value['source_job_id']):raise physical.native.HostError('Select this registration\'s original recovery instance')
        job_id=value['source_job_id'];endpoint_id=value['source_endpoint_id']
    else:endpoint_id=endpoint.id
    job=jobs.load(job_id,owner,endpoint_id)
    if job['options']['phase']!='recover':raise physical.native.HostError('Select a managed recovery instance')
    return job


def observed(transport,job):
    value=transport.request(physical.remote_request(job,'status'))
    if value.get('input_digest')!=job['review_digest'] or not value.get('recovery_running_verified'):
        raise physical.native.HostError('Original recovery instance is not independently observed as running')
    if not value.get('sql_identity',{}).get('port') or value['sql_identity'].get('skip_networking')!=0:
        raise physical.native.HostError('Start a recovery instance with an explicitly reviewed loopback TCP port for editor access')
    return {'server_uuid':value['sql_identity']['server_uuid'],'version':value['sql_identity']['version'],
        'recovery_mode':job['options'].get('recovery_mode','read_only'),
        'datadir':value['data_directory'],'runtime_process':deepcopy(value['runtime_process'])}


def action(service,server,operation,request):
    jobs,connections,owner,endpoint=manager(service,server)
    if operation=='info' and not request:
        value=marker(server)
        if value is None:raise physical.native.HostError('Select a recovery job or a registered recovery target')
        return jobs.get(value['source_job_id'],owner,value['source_endpoint_id'])
    if operation=='status' and set(request)=={'review_id'}:
        ticket=connections.load(request['review_id'],owner,endpoint.id)
        job=source_job(jobs,server,owner,endpoint,ticket['options']['source_job_id'])
        found=targets(owner,job)
        result=connections.public(ticket)
        result['registration_observation']=[registration(item) for item in found]
        result['original_connection_reply_unchanged']=True
        return result
    if operation=='detach' and set(request)=={'server_id'}:
        from pgadmin.model import Server
        target=Server.query.filter_by(id=request['server_id'],user_id=owner).first()
        if target is None or marker(target) is None:raise physical.native.HostError('Recovery registration is unavailable')
        value=marker(target)
        if marker(server) is None and value['source_endpoint_id']!=endpoint.id or marker(server) is not None and target.id!=server.id:
            raise physical.native.HostError('Recovery registration belongs to another source')
        try:service.endpoint_service.release_native_connections(target,lambda:bridge.bridges.detach(value['binding']))
        except Exception as error:raise physical.native.HostError(str(error)) from None
        return registration(target)
    if operation=='review' and set(request)=={'job_id','name','credentials'}:
        job=source_job(jobs,server,owner,endpoint,request['job_id'])
        name=request['name']
        if not isinstance(name,str) or not name.strip() or len(name)>128 or any(c in name for c in '\x00\r\n'):
            raise physical.native.HostError('Select a bounded recovery registration name')
        found=targets(owner,job)
        if len(found)>1:raise physical.native.HostError('The recovery instance has multiple registrations; select its original registration')
        selected_server=found[0] if found else server
        selected={'source_job_id':job['job_id'],'target_server_id':found[0].id if found else None,'name':found[0].name if found else name.strip(),
            'initial_database':next((item.database for item in selected_server.endpoint_profile.database_targets if item.active),None)}
        ticket=None
    elif operation=='connect' and set(request)=={'review_id','review_digest','confirmed','delegate_database_credentials','credentials'}:
        ticket=connections.load(request['review_id'],owner,endpoint.id);selected=ticket['options']
        if request['confirmed'] is not True or request['review_digest']!=ticket['review_digest']:
            raise physical.native.HostError('Confirm the exact recovery connection review')
        if ticket['state']!='reviewed':return connections.public(ticket)
        job=source_job(jobs,server,owner,endpoint,selected['source_job_id'])
    else:raise physical.native.HostError('Recovery connection action is unavailable')
    configuration=digest(MySQLMonitoringHost._configuration(server))
    if ticket and (ticket['configuration']!=configuration or ticket['program']['adapter']!=physical.native.program()):
        raise physical.native.HostError('Recovery connection registration or transport changed after review')
    transport=physical.native.Transport(job['options']['connection'],physical.host.credentials(request['credentials']));retained=False
    try:
        peer=transport.connect();current=observed(transport,job)
        program={'adapter':physical.native.program(),'execution_host':{**peer,'workspace':job['options']['workspace']}}
        if operation=='review':
            return connections.review(owner,endpoint.id,selected,{'identity':current,'state':{'source_job_digest':job['review_digest']}},configuration,program)
        if current!=ticket['source'] or job['review_digest']!=ticket['source_state']['source_job_digest'] or program!=ticket['program']:
            raise physical.native.HostError('Original native recovery instance changed after connection review')
        if request['delegate_database_credentials'] is not True:
            raise physical.native.HostError('Confirm use of the registered database credential for the separate recovery registration')
        credentials=physical.delegate(service,server)
        if not physical.claim(connections,ticket,owner,endpoint.id,{'confirmed':True,'review_digest':request['review_digest']}):return connections.get(ticket['job_id'],owner,endpoint.id)
        from pgadmin.model import db,Server,EndpointProfile,EndpointDatabaseTarget
        target=None;binding=None;installed=None
        try:
            if selected['target_server_id'] is None:
                from ..endpoints.profiles import registration_profile
                _context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
                route=deepcopy(payload['route'])
                for key in ('credential_reference_id','credential_references','principal_reference','route_id','database_target_id','database','failover','init_command','unix_socket'):
                    route.pop(key,None)
                target=Server(user_id=owner,servergroup_id=server.servergroup_id,name=selected['name'],
                    host='managed-recovery.invalid',port=3306,username=credentials['user'],maintenance_db='mysql',save_password=0)
                target._cde_endpoint_registration=registration_profile('mysql-native')
                target._cde_endpoint_route_configuration={**route,'host':target.host,'port':target.port,'user':target.username}
                db.session.add(target);db.session.flush()
                target_endpoint=EndpointProfile.query.filter_by(legacy_server_id=target.id).one()
                binding={'id':str(uuid.uuid4()),'owner':owner,'endpoint_id':target_endpoint.id,'job_id':job['job_id'],
                    **{key:current[key] for key in ('server_uuid','version','datadir','recovery_mode')}}
                model=target_endpoint.routes[0];route=json.loads(model.configuration);route[bridge.ROUTE_KEY]=binding;model.configuration=json.dumps(route)
                target_endpoint.extension_profile.schema_reference=bridge.SCHEMA
                target_endpoint.extension_profile.profile_data=json.dumps({'binding':binding,'source_job_id':job['job_id'],
                    'source_endpoint_id':job['endpoint_id'],'connection_review_id':ticket['job_id']})
                target_endpoint.extension_profile.redaction_state='no_credentials'
                if selected['initial_database']:
                    db.session.add(EndpointDatabaseTarget(id=str(uuid.uuid4()),endpoint_id=target_endpoint.id,
                        display_name=selected['initial_database'],database=selected['initial_database'],configuration='{}',active=1))
                db.session.commit();db.session.expire(target,['endpoint_profile'])
            else:
                target=Server.query.filter_by(id=selected['target_server_id'],user_id=owner).first()
                if target is None or marker(target) is None:raise physical.native.HostError('Original recovery registration is unavailable')
                binding=marker(target)['binding']
                if binding['server_uuid']!=current['server_uuid']:raise physical.native.HostError('Recovery registration refers to another native instance')
            connections.update(ticket,target_server_id=target.id,target_endpoint_id=target.endpoint_profile.id)
            stream={'schema':'cdeadmin.mysql-recovery-stream.v1','workspace':job['options']['workspace'],
                'job_id':job['job_id'],'input_digest':job['review_digest'],'binding':deepcopy(job['source_state']['host_binding']),
                'expected':{key:deepcopy(current[key]) for key in ('server_uuid','datadir','runtime_process')}}
            def attach():
                nonlocal retained,installed
                installed=bridge.bridges.install(binding,transport,stream);retained=True
                verification=service.endpoint_service.verify_server(target,password=credentials['password'])
                if selected['initial_database']:
                    from ..endpoints.profiles import registration_profile
                    service.endpoint_service._verify_database_target(target,target.endpoint_profile,registration_profile('mysql-native'),selected['initial_database'])
                return verification
            verification=service.endpoint_service.release_native_connections(target,attach)
            value=registration(target);value['verification']=verification
            connections.update(ticket,state='connection_returned',result=value,original_connection_reply_observed=True)
            return connections.get(ticket['job_id'],owner,endpoint.id)
        except BaseException as error:
            db.session.rollback()
            if installed is not None:bridge.bridges.detach(binding,expected=installed,force=True)
            connections.update(ticket,state='unknown',error_type=type(error).__name__)
            # Keep a committed registration as independent evidence of an
            # interrupted original request. A later review reattaches it.
            raise physical.native.HostError('Recovery connection outcome is unknown ('+type(error).__name__+'); observe its original registration before reviewing a new attachment') from None
    finally:
        if not retained:transport.close()
